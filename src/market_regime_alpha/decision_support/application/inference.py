"""One transaction freezes complete Signal and Forecast rosters."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable
from uuid import UUID, uuid4

from market_regime_alpha.decision_support.domain import (
    PreparedForecastInputs,
    PreparedInferenceInputs,
    build_forecast_authority,
    build_signal_authority,
)
from market_regime_alpha.decision_support.errors import (
    DecisionCommitOutcomeUnknownError,
    DecisionRetryableTransactionError,
    DecisionTransactionRetryExhaustedError,
    InferenceAuthorityIntegrityError,
)
from market_regime_alpha.decision_support.ports import (
    InferenceInputPreparationProvider,
    InferenceQueryProvider,
    InferenceRecord,
    InferenceUnitOfWork,
    InferenceUnitOfWorkProvider,
)
from market_regime_alpha.runtime.application import CommandContext
from market_regime_alpha.runtime.errors import (
    CommandInProgressError,
    CommandPreviouslyFailedError,
    IdempotencyKeyReusedError,
    StaleFenceError,
)
from market_regime_alpha.runtime.ports import AttemptClaim, ReceiptRecord
from market_regime_alpha.shared.hashing import canonical_json_sha256


_MAX_TRANSACTION_ATTEMPTS = 3


@dataclass(frozen=True, slots=True)
class ProduceInferenceResult:
    decision_run_id: UUID
    strategy_version_id: UUID
    signal_group_id: UUID
    forecast_group_id: UUID
    signal_count: int
    forecast_count: int
    context_binding_count: int
    estimate_count: int
    receipt_id: UUID
    result_hash: str
    replayed: bool

    def as_replay(self) -> ProduceInferenceResult:
        return replace(self, replayed=True)


class InferenceCommands:
    def __init__(
        self,
        preparation: InferenceInputPreparationProvider,
        uow_provider: InferenceUnitOfWorkProvider,
        queries: InferenceQueryProvider,
        *,
        id_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self._preparation = preparation
        self._uow_provider = uow_provider
        self._queries = queries
        self._id_factory = id_factory

    def produce(
        self,
        decision_run_id: UUID,
        strategy_version_id: UUID,
        context: CommandContext,
        *,
        runtime_claim: AttemptClaim,
    ) -> ProduceInferenceResult:
        request_hash = canonical_json_sha256(
            {
                "actor_id": context.actor_id,
                "actor_type": context.actor_type,
                "decision_run_id": decision_run_id,
                "reason_code": context.reason_code,
                "strategy_version_id": strategy_version_id,
            }
        )
        existing = self._queries.find_request(
            decision_run_id,
            strategy_version_id,
            context.idempotency_key,
        )
        if existing is not None:
            if existing.request_sha256 != request_hash:
                raise IdempotencyKeyReusedError("Inference replay inputs differ")
            return _result(existing, replayed=True)
        prepared = self._preparation.prepare(decision_run_id, strategy_version_id)
        if (
            prepared.signal_inputs.decision_run_id != decision_run_id
            or prepared.signal_inputs.strategy_version.strategy_version_id != strategy_version_id
        ):
            raise InferenceAuthorityIntegrityError("Inference preparation returned a different Authority identity")
        identities = _InferenceIdentities.create(prepared, self._id_factory)
        for attempt in range(_MAX_TRANSACTION_ATTEMPTS):
            try:
                return self._produce_once(
                    prepared,
                    context,
                    request_hash=request_hash,
                    identities=identities,
                    runtime_claim=runtime_claim,
                )
            except (DecisionRetryableTransactionError, DecisionCommitOutcomeUnknownError) as exc:
                existing = self._queries.find_request(
                    decision_run_id,
                    strategy_version_id,
                    context.idempotency_key,
                )
                if existing is not None:
                    if existing.request_sha256 != request_hash:
                        raise IdempotencyKeyReusedError("Inference replay inputs differ") from exc
                    return _result(existing, replayed=True)
                if attempt == _MAX_TRANSACTION_ATTEMPTS - 1:
                    if isinstance(exc, DecisionRetryableTransactionError):
                        raise DecisionTransactionRetryExhaustedError("Inference exhausted transaction retries") from exc
                    raise
            except StaleFenceError as exc:
                existing = self._queries.find_request(
                    decision_run_id,
                    strategy_version_id,
                    context.idempotency_key,
                )
                if existing is not None:
                    if existing.request_sha256 != request_hash:
                        raise IdempotencyKeyReusedError("Inference replay inputs differ") from exc
                    return _result(existing, replayed=True)
                raise
        raise AssertionError("Inference bounded retry loop did not terminate")

    def _produce_once(
        self,
        prepared: PreparedInferenceInputs,
        context: CommandContext,
        *,
        request_hash: str,
        identities: _InferenceIdentities,
        runtime_claim: AttemptClaim,
    ) -> ProduceInferenceResult:
        signal_inputs = prepared.signal_inputs
        with self._uow_provider() as uow:
            uow.runtime_finalization.lock_live_for_step(
                runtime_claim,
                expected_step_kind="SIGNAL_AND_FORECAST",
            )
            receipt = uow.receipts.start(
                receipt_id=identities.receipt_id,
                command_kind="PRODUCE_SIGNAL_AND_FORECAST",
                scope_id=(f"{signal_inputs.decision_run_id}:{signal_inputs.strategy_version.strategy_version_id}"),
                idempotency_key=context.idempotency_key,
                request_hash=request_hash,
            )
            if not receipt.is_new:
                return self._replay_in_transaction(
                    uow,
                    receipt,
                    runtime_claim,
                    request_hash=request_hash,
                )
            uow.inference.lock_identity(
                signal_inputs.decision_run_id,
                signal_inputs.strategy_version.strategy_version_id,
            )
            uow.dependencies.lock_and_revalidate(prepared)
            recorded_at = uow.inference.authoritative_recorded_at()
            signal = build_signal_authority(
                signal_group_id=identities.signal_group_id,
                prepared=signal_inputs,
                request_identity=context.idempotency_key,
                request_sha256=request_hash,
                command_receipt_id=receipt.receipt_id,
                recorded_at=recorded_at,
                signal_id_factory=identities.signal_id,
                binding_id_factory=identities.binding_id,
            )
            forecast = build_forecast_authority(
                forecast_group_id=identities.forecast_group_id,
                prepared=PreparedForecastInputs(
                    decision_run_id=signal_inputs.decision_run_id,
                    strategy_version=signal_inputs.strategy_version,
                    signal_authority=signal,
                    commitments=prepared.commitments,
                ),
                request_identity=context.idempotency_key,
                request_sha256=request_hash,
                command_receipt_id=receipt.receipt_id,
                recorded_at=recorded_at,
                forecast_id_factory=identities.forecast_id,
                estimate_id_factory=identities.estimate_id,
            )
            record = uow.inference.insert(signal, forecast)
            reconciliation = uow.inference.reconcile(
                signal.signal_group_id,
                forecast.forecast_group_id,
                lock=True,
            )
            if (
                not reconciliation.matched
                or reconciliation.signal_count != signal.signal_count
                or reconciliation.context_binding_count != signal.context_binding_count
                or reconciliation.forecast_count != forecast.forecast_count
                or reconciliation.estimate_count != forecast.estimate_count
            ):
                raise InferenceAuthorityIntegrityError("Signal/Forecast relational closure did not reconcile")
            result_hash = _record_hash(record)
            uow.receipts.succeed(
                receipt_id=receipt.receipt_id,
                aggregate_kind="SIGNAL_FORECAST_AUTHORITY",
                aggregate_id=str(signal.signal_group_id),
                aggregate_version=1,
                result_hash=result_hash,
                runtime_claim=runtime_claim,
            )
            uow.audit.append(
                audit_event_id=identities.audit_event_id,
                receipt_id=receipt.receipt_id,
                actor_type=context.actor_type.value,
                actor_id=context.actor_id,
                aggregate_kind="SIGNAL_FORECAST_AUTHORITY",
                aggregate_id=str(signal.signal_group_id),
                action="SIGNAL_AND_FORECAST_PRODUCED",
                reason_code=context.reason_code,
                before_version=None,
                after_version=1,
                runtime_claim=runtime_claim,
            )
            uow.runtime_finalization.succeed(
                runtime_claim,
                receipt_id=receipt.receipt_id,
                result_hash=result_hash,
            )
            uow.commit()
            return _result(record, result_hash=result_hash, replayed=False)

    def _replay_in_transaction(
        self,
        uow: InferenceUnitOfWork,
        receipt: ReceiptRecord,
        runtime_claim: AttemptClaim,
        *,
        request_hash: str,
    ) -> ProduceInferenceResult:
        _require_succeeded(receipt)
        if receipt.request_hash != request_hash:
            raise IdempotencyKeyReusedError("Inference replay inputs differ")
        assert receipt.result_aggregate_id is not None
        assert receipt.result_hash is not None
        signal_group_id = UUID(receipt.result_aggregate_id)
        record = uow.inference.record(
            signal_group_id,
            uow.inference.forecast_group_for_signal(signal_group_id, lock=False),
            lock=False,
        )
        if _record_hash(record) != receipt.result_hash:
            raise InferenceAuthorityIntegrityError("Inference receipt and Authority differ")
        uow.runtime_finalization.succeed(
            runtime_claim,
            receipt_id=receipt.receipt_id,
            result_hash=receipt.result_hash,
        )
        uow.commit()
        return _result(record, result_hash=receipt.result_hash, replayed=True)


@dataclass(frozen=True, slots=True)
class _InferenceIdentities:
    signal_group_id: UUID
    forecast_group_id: UUID
    receipt_id: UUID
    audit_event_id: UUID
    signal_ids: dict[UUID, UUID]
    binding_ids: dict[tuple[UUID, UUID], UUID]
    forecast_ids: dict[tuple[UUID, UUID], UUID]
    estimate_ids: dict[tuple[UUID, UUID], UUID]

    @classmethod
    def create(
        cls,
        prepared: PreparedInferenceInputs,
        factory: Callable[[], UUID],
    ) -> _InferenceIdentities:
        signal_ids = {candidate.candidate_id: factory() for candidate in prepared.signal_inputs.candidates}
        binding_ids = {
            (candidate.candidate_id, item.strategy_context_requirement_id): factory()
            for candidate in prepared.signal_inputs.candidates
            for item in candidate.contexts
        }
        forecast_ids = {(commitment.candidate_id, commitment.commitment_id): factory() for commitment in prepared.commitments}
        estimate_ids = {
            (commitment.commitment_id, rule.strategy_forecast_rule_id): factory()
            for commitment in prepared.commitments
            for rule in prepared.signal_inputs.strategy_version.forecast_rules
            if rule.target_definition_id == commitment.target_definition_id
        }
        return cls(
            signal_group_id=factory(),
            forecast_group_id=factory(),
            receipt_id=factory(),
            audit_event_id=factory(),
            signal_ids=signal_ids,
            binding_ids=binding_ids,
            forecast_ids=forecast_ids,
            estimate_ids=estimate_ids,
        )

    def signal_id(self, candidate, ordinal: int) -> UUID:
        del ordinal
        return self.signal_ids[candidate.candidate_id]

    def binding_id(self, candidate, item) -> UUID:
        return self.binding_ids[(candidate.candidate_id, item.strategy_context_requirement_id)]

    def forecast_id(self, signal, commitment) -> UUID:
        return self.forecast_ids[(signal.candidate.candidate_id, commitment.commitment_id)]

    def estimate_id(self, rule, forecast) -> UUID:
        return self.estimate_ids[(forecast.commitment.commitment_id, rule.strategy_forecast_rule_id)]


def _require_succeeded(receipt: ReceiptRecord) -> None:
    if receipt.status == "FAILED":
        raise CommandPreviouslyFailedError(receipt.error_code or "PRODUCE_SIGNAL_AND_FORECAST_FAILED")
    if receipt.status != "SUCCEEDED":
        raise CommandInProgressError("Inference command is in progress")
    if receipt.result_aggregate_id is None or receipt.result_hash is None:
        raise InferenceAuthorityIntegrityError("Inference receipt is incomplete")


def _record_hash(record: InferenceRecord) -> str:
    return canonical_json_sha256(
        {
            "forecast_content_sha256": record.forecast_content_sha256,
            "forecast_group_id": record.forecast_group_id,
            "signal_content_sha256": record.signal_content_sha256,
            "signal_group_id": record.signal_group_id,
        }
    )


def _result(
    record: InferenceRecord,
    *,
    result_hash: str | None = None,
    replayed: bool,
) -> ProduceInferenceResult:
    return ProduceInferenceResult(
        decision_run_id=record.decision_run_id,
        strategy_version_id=record.strategy_version_id,
        signal_group_id=record.signal_group_id,
        forecast_group_id=record.forecast_group_id,
        signal_count=record.signal_count,
        forecast_count=record.forecast_count,
        context_binding_count=record.context_binding_count,
        estimate_count=record.estimate_count,
        receipt_id=record.receipt_id,
        result_hash=result_hash or _record_hash(record),
        replayed=replayed,
    )


__all__ = ["InferenceCommands", "ProduceInferenceResult"]
