"""Complete Opportunity creation and immutable Thesis registration."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable
from uuid import UUID, uuid4

from market_regime_alpha.decision_support.domain import (
    PreparedOpportunityInputs,
    ThesisPlan,
    build_opportunity_authority,
)
from market_regime_alpha.decision_support.errors import (
    DecisionCommitOutcomeUnknownError,
    DecisionRetryableTransactionError,
    DecisionTransactionRetryExhaustedError,
    DecisionAuthorityIntegrityError,
)
from market_regime_alpha.decision_support.ports import (
    OpportunityInputPreparationProvider,
    OpportunityQueryProvider,
    OpportunitySetRecord,
    OpportunityUnitOfWork,
    OpportunityUnitOfWorkProvider,
    ThesisRecord,
)
from market_regime_alpha.runtime.application import CommandContext
from market_regime_alpha.runtime.errors import CommandInProgressError, CommandPreviouslyFailedError, IdempotencyKeyReusedError
from market_regime_alpha.runtime.ports import AttemptClaim, ReceiptRecord
from market_regime_alpha.shared.hashing import canonical_json_sha256


@dataclass(frozen=True, slots=True)
class OpportunityMutationResult:
    aggregate_kind: str
    aggregate_id: UUID
    aggregate_version: int
    child_count: int
    secondary_count: int
    receipt_id: UUID
    result_hash: str
    replayed: bool

    def as_replay(self) -> OpportunityMutationResult:
        return replace(self, replayed=True)


class OpportunityCommands:
    def __init__(
        self,
        preparation: OpportunityInputPreparationProvider,
        uow_provider: OpportunityUnitOfWorkProvider,
        queries: OpportunityQueryProvider,
        *,
        id_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self._preparation = preparation
        self._uow_provider = uow_provider
        self._queries = queries
        self._id_factory = id_factory

    def create_opportunities(
        self,
        decision_run_id: UUID,
        strategy_version_id: UUID,
        context: CommandContext,
        *,
        runtime_claim: AttemptClaim,
    ) -> OpportunityMutationResult:
        request_hash = _request_hash(
            context,
            {
                "decision_run_id": decision_run_id,
                "strategy_version_id": strategy_version_id,
            },
        )
        existing = self._queries.find_set_request(decision_run_id, strategy_version_id, context.idempotency_key)
        if existing is not None:
            return _set_replay(existing, request_hash)
        prepared = self._preparation.prepare(decision_run_id, strategy_version_id)
        if prepared.decision_run_id != decision_run_id or prepared.strategy_version_id != strategy_version_id:
            raise DecisionAuthorityIntegrityError("Opportunity preparation identity differs")
        ids = _OpportunityIds.create(prepared, self._id_factory)

        def operation() -> OpportunityMutationResult:
            with self._uow_provider() as uow:
                uow.runtime_finalization.lock_live_for_step(runtime_claim, expected_step_kind="DECIDE_AND_RISK")
                receipt = uow.receipts.start(
                    receipt_id=ids.receipt_id,
                    command_kind="CREATE_OPPORTUNITIES",
                    scope_id=f"{decision_run_id}:{strategy_version_id}",
                    idempotency_key=context.idempotency_key,
                    request_hash=request_hash,
                )
                if not receipt.is_new:
                    return self._replay_set_in_transaction(uow, receipt, request_hash)
                uow.opportunities.lock_set_identity(decision_run_id, strategy_version_id)
                uow.dependencies.lock_and_revalidate(prepared)
                authority = build_opportunity_authority(
                    opportunity_set_id=ids.opportunity_set_id,
                    prepared=prepared,
                    request_identity=context.idempotency_key,
                    request_sha256=request_hash,
                    command_receipt_id=receipt.receipt_id,
                    recorded_at=uow.opportunities.authoritative_time(),
                    opportunity_id_factory=ids.opportunity_id,
                    context_id_factory=ids.context_id,
                )
                record = uow.opportunities.insert_set(authority)
                reconciliation = uow.opportunities.reconcile(record.opportunity_set_id, lock=True)
                if (
                    not reconciliation.matched
                    or reconciliation.opportunity_count != len(authority.opportunities)
                    or reconciliation.context_count != authority.context_count
                    or reconciliation.opportunity_roster_sha256 != authority.opportunity_roster_sha256
                ):
                    raise DecisionAuthorityIntegrityError("Opportunity relational closure differs")
                result_hash = canonical_json_sha256(record)
                _finish(
                    uow,
                    receipt,
                    record.opportunity_set_id,
                    1,
                    result_hash,
                    context,
                    ids.audit_event_id,
                    "OPPORTUNITY_SET",
                    "OPPORTUNITIES_CREATED",
                    runtime_claim,
                )
                uow.commit()
                return _set_result(record, result_hash=result_hash, replayed=False)

        return self._retry(operation, lambda: self._probe_set(decision_run_id, strategy_version_id, context, request_hash))

    def create_thesis(self, plan: ThesisPlan, context: CommandContext) -> OpportunityMutationResult:
        request_hash = _request_hash(context, {"plan": plan})
        existing = self._queries.find_thesis_request(plan.opportunity_id, context.idempotency_key)
        if existing is not None:
            return _thesis_replay(existing, plan, request_hash)
        receipt_id, audit_id = self._id_factory(), self._id_factory()

        def operation() -> OpportunityMutationResult:
            with self._uow_provider() as uow:
                receipt = uow.receipts.start(
                    receipt_id=receipt_id,
                    command_kind="CREATE_THESIS",
                    scope_id=str(plan.opportunity_id),
                    idempotency_key=context.idempotency_key,
                    request_hash=request_hash,
                )
                if not receipt.is_new:
                    return self._replay_thesis_in_transaction(uow, receipt, plan, request_hash)
                uow.opportunities.lock_thesis_identity(plan.opportunity_id)
                scope = uow.dependencies.require_opportunity(
                    plan.opportunity_id,
                    plan.opportunity_content_sha256,
                    lock=True,
                )
                uow.artifacts.require_exact(plan.code_artifact, lock=True)
                uow.artifacts.require_exact(plan.config_artifact, lock=True)
                record = uow.opportunities.insert_thesis(
                    plan,
                    opportunity_scope=scope,
                    request_identity=context.idempotency_key,
                    request_sha256=request_hash,
                )
                result_hash = canonical_json_sha256(record)
                _finish(uow, receipt, record.thesis_id, record.revision, result_hash, context, audit_id, "THESIS", "THESIS_CREATED", None)
                uow.commit()
                return _thesis_result(record, result_hash=result_hash, replayed=False)

        return self._retry(operation, lambda: self._probe_thesis(plan, context, request_hash))

    def _replay_set_in_transaction(
        self, uow: OpportunityUnitOfWork, receipt: ReceiptRecord, request_hash: str
    ) -> OpportunityMutationResult:
        _require_succeeded(receipt)
        if receipt.request_hash != request_hash:
            raise IdempotencyKeyReusedError("Opportunity replay inputs differ")
        assert receipt.result_aggregate_id and receipt.result_hash
        record = uow.opportunities.set_record(UUID(receipt.result_aggregate_id), lock=False)
        if canonical_json_sha256(record) != receipt.result_hash:
            raise DecisionAuthorityIntegrityError("Opportunity receipt differs")
        return _set_result(record, result_hash=receipt.result_hash, replayed=True)

    def _replay_thesis_in_transaction(
        self, uow: OpportunityUnitOfWork, receipt: ReceiptRecord, plan: ThesisPlan, request_hash: str
    ) -> OpportunityMutationResult:
        _require_succeeded(receipt)
        if receipt.request_hash != request_hash:
            raise IdempotencyKeyReusedError("Thesis replay inputs differ")
        assert receipt.result_aggregate_id and receipt.result_hash
        record = uow.opportunities.thesis_record(UUID(receipt.result_aggregate_id), lock=False)
        if record.content_sha256 != plan.content_sha256 or canonical_json_sha256(record) != receipt.result_hash:
            raise DecisionAuthorityIntegrityError("Thesis receipt differs")
        return _thesis_result(record, result_hash=receipt.result_hash, replayed=True)

    def _probe_set(self, decision_run_id, strategy_version_id, context, request_hash):
        record = self._queries.find_set_request(decision_run_id, strategy_version_id, context.idempotency_key)
        return None if record is None else _set_replay(record, request_hash)

    def _probe_thesis(self, plan, context, request_hash):
        record = self._queries.find_thesis_request(plan.opportunity_id, context.idempotency_key)
        return None if record is None else _thesis_replay(record, plan, request_hash)

    @staticmethod
    def _retry(operation, replay):
        for attempt in range(3):
            try:
                return operation()
            except (DecisionRetryableTransactionError, DecisionCommitOutcomeUnknownError) as exc:
                existing = replay()
                if existing is not None:
                    return existing
                if attempt == 2:
                    if isinstance(exc, DecisionRetryableTransactionError):
                        raise DecisionTransactionRetryExhaustedError("Opportunity transaction retries exhausted") from exc
                    raise
        raise AssertionError("Opportunity retry loop did not terminate")


@dataclass(frozen=True, slots=True)
class _OpportunityIds:
    opportunity_set_id: UUID
    receipt_id: UUID
    audit_event_id: UUID
    opportunity_ids: dict[UUID, UUID]
    context_ids: dict[tuple[UUID, UUID], UUID]

    @classmethod
    def create(cls, prepared: PreparedOpportunityInputs, factory: Callable[[], UUID]) -> _OpportunityIds:
        return cls(
            opportunity_set_id=factory(),
            receipt_id=factory(),
            audit_event_id=factory(),
            opportunity_ids={item.forecast_id: factory() for item in prepared.items},
            context_ids={
                (item.forecast_id, context.signal_context_binding_id): factory() for item in prepared.items for context in item.contexts
            },
        )

    def opportunity_id(self, item):
        return self.opportunity_ids[item.forecast_id]

    def context_id(self, item, context):
        return self.context_ids[(item.forecast_id, context.signal_context_binding_id)]


def _finish(uow, receipt, aggregate_id, version, result_hash, context, audit_id, kind, action, runtime_claim):
    uow.receipts.succeed(
        receipt_id=receipt.receipt_id,
        aggregate_kind=kind,
        aggregate_id=str(aggregate_id),
        aggregate_version=version,
        result_hash=result_hash,
        runtime_claim=runtime_claim,
    )
    uow.audit.append(
        audit_event_id=audit_id,
        receipt_id=receipt.receipt_id,
        actor_type=context.actor_type.value,
        actor_id=context.actor_id,
        aggregate_kind=kind,
        aggregate_id=str(aggregate_id),
        action=action,
        reason_code=context.reason_code,
        before_version=None,
        after_version=version,
        runtime_claim=runtime_claim,
    )


def _request_hash(context, value):
    return canonical_json_sha256(
        {
            "actor_id": context.actor_id,
            "actor_type": context.actor_type,
            "reason_code": context.reason_code,
            "value": value,
        }
    )


def _require_succeeded(receipt):
    if receipt.status == "FAILED":
        raise CommandPreviouslyFailedError(receipt.error_code or "DECISION_SUPPORT_COMMAND_FAILED")
    if receipt.status != "SUCCEEDED" or receipt.result_aggregate_id is None or receipt.result_hash is None:
        raise CommandInProgressError("Decision Support command is not complete")


def _set_replay(record, request_hash):
    if record.request_sha256 != request_hash:
        raise IdempotencyKeyReusedError("Opportunity replay inputs differ")
    return _set_result(record, result_hash=canonical_json_sha256(record), replayed=True)


def _thesis_replay(record, plan, request_hash):
    if record.request_sha256 != request_hash:
        raise IdempotencyKeyReusedError("Thesis replay inputs differ")
    if record.content_sha256 != plan.content_sha256:
        raise DecisionAuthorityIntegrityError("Thesis identity binds different content")
    return _thesis_result(record, result_hash=canonical_json_sha256(record), replayed=True)


def _set_result(record: OpportunitySetRecord, *, result_hash: str, replayed: bool):
    return OpportunityMutationResult(
        aggregate_kind="OPPORTUNITY_SET",
        aggregate_id=record.opportunity_set_id,
        aggregate_version=1,
        child_count=record.opportunity_count,
        secondary_count=record.context_count,
        receipt_id=record.receipt_id,
        result_hash=result_hash,
        replayed=replayed,
    )


def _thesis_result(record: ThesisRecord, *, result_hash: str, replayed: bool):
    return OpportunityMutationResult(
        aggregate_kind="THESIS",
        aggregate_id=record.thesis_id,
        aggregate_version=record.revision,
        child_count=record.condition_count,
        secondary_count=0,
        receipt_id=record.receipt_id,
        result_hash=result_hash,
        replayed=replayed,
    )


__all__ = ["OpportunityCommands", "OpportunityMutationResult"]
