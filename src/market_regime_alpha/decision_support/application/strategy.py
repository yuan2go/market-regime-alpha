"""Immutable StrategyVersion registration."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable
from uuid import UUID, uuid4

from market_regime_alpha.decision_support.domain import StrategyVersionPlan
from market_regime_alpha.decision_support.errors import (
    DecisionCommitOutcomeUnknownError,
    DecisionRetryableTransactionError,
    DecisionTransactionRetryExhaustedError,
    StrategyAuthorityIntegrityError,
)
from market_regime_alpha.decision_support.ports import (
    StrategyQueryProvider,
    StrategyUnitOfWork,
    StrategyUnitOfWorkProvider,
    StrategyVersionRecord,
)
from market_regime_alpha.runtime.application import CommandContext
from market_regime_alpha.runtime.errors import (
    CommandInProgressError,
    CommandPreviouslyFailedError,
    IdempotencyKeyReusedError,
)
from market_regime_alpha.runtime.ports import ReceiptRecord
from market_regime_alpha.shared.hashing import canonical_json_sha256


_MAX_TRANSACTION_ATTEMPTS = 3


@dataclass(frozen=True, slots=True)
class RegisterStrategyResult:
    strategy_id: UUID
    strategy_version_id: UUID
    version: int
    context_requirement_count: int
    forecast_rule_count: int
    receipt_id: UUID
    result_hash: str
    replayed: bool

    def as_replay(self) -> RegisterStrategyResult:
        return replace(self, replayed=True)


class StrategyCommands:
    def __init__(
        self,
        uow_provider: StrategyUnitOfWorkProvider,
        queries: StrategyQueryProvider,
        *,
        id_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self._uow_provider = uow_provider
        self._queries = queries
        self._id_factory = id_factory

    def register(
        self,
        plan: StrategyVersionPlan,
        context: CommandContext,
    ) -> RegisterStrategyResult:
        request_hash = canonical_json_sha256(
            {
                "actor_id": context.actor_id,
                "actor_type": context.actor_type,
                "plan": plan,
                "reason_code": context.reason_code,
            }
        )
        existing = self._queries.find_request(
            plan.strategy.strategy_id,
            context.idempotency_key,
        )
        if existing is not None:
            return self._replay_result(existing, plan, request_hash)
        receipt_id = self._id_factory()
        audit_event_id = self._id_factory()
        for attempt in range(_MAX_TRANSACTION_ATTEMPTS):
            try:
                return self._register_once(
                    plan,
                    context,
                    request_hash=request_hash,
                    receipt_id=receipt_id,
                    audit_event_id=audit_event_id,
                )
            except (DecisionRetryableTransactionError, DecisionCommitOutcomeUnknownError) as exc:
                existing = self._queries.find_request(
                    plan.strategy.strategy_id,
                    context.idempotency_key,
                )
                if existing is not None:
                    return self._replay_result(existing, plan, request_hash)
                if attempt == _MAX_TRANSACTION_ATTEMPTS - 1:
                    if isinstance(exc, DecisionRetryableTransactionError):
                        raise DecisionTransactionRetryExhaustedError(
                            "Strategy registration exhausted transaction retries"
                        ) from exc
                    raise
        raise AssertionError("Strategy bounded retry loop did not terminate")

    def _register_once(
        self,
        plan: StrategyVersionPlan,
        context: CommandContext,
        *,
        request_hash: str,
        receipt_id: UUID,
        audit_event_id: UUID,
    ) -> RegisterStrategyResult:
        with self._uow_provider() as uow:
            receipt = uow.receipts.start(
                receipt_id=receipt_id,
                command_kind="REGISTER_STRATEGY_VERSION",
                scope_id=str(plan.strategy.strategy_id),
                idempotency_key=context.idempotency_key,
                request_hash=request_hash,
            )
            if not receipt.is_new:
                return self._replay_in_transaction(uow, receipt, plan, request_hash)
            uow.strategies.lock_identity(plan.strategy.strategy_id)
            uow.artifacts.require_exact(plan.code_artifact, lock=True)
            uow.artifacts.require_exact(plan.config_artifact, lock=True)
            record = uow.strategies.register(
                plan,
                request_identity=context.idempotency_key,
                request_sha256=request_hash,
            )
            reconciliation = uow.strategies.reconcile(
                plan.strategy_version_id,
                lock=True,
            )
            if (
                not reconciliation.matched
                or reconciliation.context_requirement_count
                != plan.context_requirement_count
                or reconciliation.signal_rule_count != 1
                or reconciliation.forecast_rule_count != plan.forecast_rule_count
                or reconciliation.context_requirement_roster_sha256
                != plan.context_requirement_roster_sha256
                or reconciliation.forecast_rule_roster_sha256
                != plan.forecast_rule_roster_sha256
            ):
                raise StrategyAuthorityIntegrityError(
                    "StrategyVersion relational closure did not reconcile"
                )
            result_hash = canonical_json_sha256(record)
            uow.receipts.succeed(
                receipt_id=receipt.receipt_id,
                aggregate_kind="STRATEGY_VERSION",
                aggregate_id=str(record.strategy_version_id),
                aggregate_version=record.version,
                result_hash=result_hash,
                runtime_claim=None,
            )
            uow.audit.append(
                audit_event_id=audit_event_id,
                receipt_id=receipt.receipt_id,
                actor_type=context.actor_type.value,
                actor_id=context.actor_id,
                aggregate_kind="STRATEGY_VERSION",
                aggregate_id=str(record.strategy_version_id),
                action="STRATEGY_VERSION_REGISTERED",
                reason_code=context.reason_code,
                before_version=None,
                after_version=record.version,
                runtime_claim=None,
            )
            uow.commit()
            return _result(record, result_hash=result_hash, replayed=False)

    def _replay_in_transaction(
        self,
        uow: StrategyUnitOfWork,
        receipt: ReceiptRecord,
        plan: StrategyVersionPlan,
        request_hash: str,
    ) -> RegisterStrategyResult:
        _require_succeeded(receipt)
        if receipt.request_hash != request_hash:
            raise IdempotencyKeyReusedError(
                "Strategy registration replay inputs differ"
            )
        assert receipt.result_aggregate_id is not None
        assert receipt.result_hash is not None
        record = uow.strategies.record(
            UUID(receipt.result_aggregate_id),
            lock=False,
        )
        if (
            record.content_sha256 != plan.content_sha256
            or canonical_json_sha256(record) != receipt.result_hash
        ):
            raise StrategyAuthorityIntegrityError(
                "StrategyVersion receipt and Authority differ"
            )
        return _result(record, result_hash=receipt.result_hash, replayed=True)

    @staticmethod
    def _replay_result(
        record: StrategyVersionRecord,
        plan: StrategyVersionPlan,
        request_hash: str,
    ) -> RegisterStrategyResult:
        if record.request_sha256 != request_hash:
            raise IdempotencyKeyReusedError(
                "Strategy registration replay inputs differ"
            )
        if record.content_sha256 != plan.content_sha256:
            raise StrategyAuthorityIntegrityError(
                "Strategy registration identity resolves different content"
            )
        return _result(
            record,
            result_hash=canonical_json_sha256(record),
            replayed=True,
        )


def _require_succeeded(receipt: ReceiptRecord) -> None:
    if receipt.status == "FAILED":
        raise CommandPreviouslyFailedError(
            receipt.error_code or "REGISTER_STRATEGY_VERSION_FAILED"
        )
    if receipt.status != "SUCCEEDED":
        raise CommandInProgressError("Strategy registration is in progress")
    if receipt.result_aggregate_id is None or receipt.result_hash is None:
        raise StrategyAuthorityIntegrityError("Strategy receipt is incomplete")


def _result(
    record: StrategyVersionRecord,
    *,
    result_hash: str,
    replayed: bool,
) -> RegisterStrategyResult:
    return RegisterStrategyResult(
        strategy_id=record.strategy_id,
        strategy_version_id=record.strategy_version_id,
        version=record.version,
        context_requirement_count=record.context_requirement_count,
        forecast_rule_count=record.forecast_rule_count,
        receipt_id=record.receipt_id,
        result_hash=result_hash,
        replayed=replayed,
    )


__all__ = ["RegisterStrategyResult", "StrategyCommands"]
