"""Immutable PortfolioPolicy registration and complete proposal command."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable
from uuid import UUID, uuid4

from market_regime_alpha.decision_support.domain import PortfolioPolicyPlan, build_portfolio_proposal
from market_regime_alpha.decision_support.errors import (
    DecisionAuthorityIntegrityError,
    DecisionCommitOutcomeUnknownError,
    DecisionRetryableTransactionError,
    DecisionTransactionRetryExhaustedError,
)
from market_regime_alpha.decision_support.ports import (
    PortfolioPolicyRecord,
    PortfolioProposalRecord,
    PortfolioQueryProvider,
    PortfolioUnitOfWork,
    PortfolioUnitOfWorkProvider,
)
from market_regime_alpha.runtime.application import CommandContext
from market_regime_alpha.runtime.errors import CommandInProgressError, CommandPreviouslyFailedError, IdempotencyKeyReusedError
from market_regime_alpha.runtime.ports import AttemptClaim, ReceiptRecord
from market_regime_alpha.shared.hashing import canonical_json_sha256


@dataclass(frozen=True, slots=True)
class PortfolioMutationResult:
    aggregate_kind: str
    aggregate_id: UUID
    aggregate_version: int
    line_count: int
    included_count: int
    receipt_id: UUID
    result_hash: str
    replayed: bool

    def as_replay(self) -> PortfolioMutationResult:
        return replace(self, replayed=True)


class PortfolioCommands:
    def __init__(
        self,
        preparation,
        uow_provider: PortfolioUnitOfWorkProvider,
        queries: PortfolioQueryProvider,
        *,
        id_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self._preparation = preparation
        self._uow_provider = uow_provider
        self._queries = queries
        self._id_factory = id_factory

    def register_policy(self, plan: PortfolioPolicyPlan, context: CommandContext) -> PortfolioMutationResult:
        request_hash = _request_hash(context, plan)
        existing = self._queries.find_policy_request(plan.policy_code, context.idempotency_key)
        if existing is not None:
            return _policy_replay(existing, plan, request_hash)
        receipt_id, audit_id = self._id_factory(), self._id_factory()

        def operation():
            with self._uow_provider() as uow:
                receipt = uow.receipts.start(
                    receipt_id=receipt_id,
                    command_kind="REGISTER_PORTFOLIO_POLICY",
                    scope_id=plan.policy_code,
                    idempotency_key=context.idempotency_key,
                    request_hash=request_hash,
                )
                if not receipt.is_new:
                    return self._replay_policy_tx(uow, receipt, plan, request_hash)
                uow.portfolios.lock_policy_identity(plan.policy_code)
                uow.artifacts.require_exact(plan.code_artifact, lock=True)
                uow.artifacts.require_exact(plan.config_artifact, lock=True)
                record = uow.portfolios.register_policy(plan, request_identity=context.idempotency_key, request_sha256=request_hash)
                result_hash = canonical_json_sha256(record)
                _finish(
                    uow,
                    receipt,
                    record.portfolio_policy_id,
                    record.version,
                    result_hash,
                    context,
                    audit_id,
                    "PORTFOLIO_POLICY",
                    "PORTFOLIO_POLICY_REGISTERED",
                    None,
                )
                uow.commit()
                return _policy_result(record, result_hash=result_hash, replayed=False)

        return self._retry(operation, lambda: self._probe_policy(plan, context, request_hash))

    def propose(
        self, opportunity_set_id: UUID, portfolio_policy_id: UUID, context: CommandContext, *, runtime_claim: AttemptClaim
    ) -> PortfolioMutationResult:
        request_hash = _request_hash(context, {"opportunity_set_id": opportunity_set_id, "portfolio_policy_id": portfolio_policy_id})
        existing = self._queries.find_proposal_request(opportunity_set_id, portfolio_policy_id, context.idempotency_key)
        if existing is not None:
            return _proposal_replay(existing, request_hash)
        prepared, policy = self._preparation.prepare(opportunity_set_id, portfolio_policy_id)
        proposal_id, receipt_id, audit_id = self._id_factory(), self._id_factory(), self._id_factory()
        line_ids = {item.opportunity_id: self._id_factory() for item in prepared.opportunities}

        def operation():
            with self._uow_provider() as uow:
                uow.runtime_finalization.lock_live_for_step(runtime_claim, expected_step_kind="DECIDE_AND_RISK")
                receipt = uow.receipts.start(
                    receipt_id=receipt_id,
                    command_kind="PROPOSE_PORTFOLIO",
                    scope_id=f"{opportunity_set_id}:{portfolio_policy_id}",
                    idempotency_key=context.idempotency_key,
                    request_hash=request_hash,
                )
                if not receipt.is_new:
                    return self._replay_proposal_tx(uow, receipt, request_hash)
                uow.portfolios.lock_proposal_identity(prepared.decision_run_id, prepared.strategy_version_id, portfolio_policy_id)
                uow.dependencies.lock_and_revalidate(prepared, policy)
                authority = build_portfolio_proposal(
                    portfolio_proposal_id=proposal_id,
                    prepared=prepared,
                    policy=policy,
                    request_identity=context.idempotency_key,
                    request_sha256=request_hash,
                    command_receipt_id=receipt.receipt_id,
                    recorded_at=uow.portfolios.authoritative_time(),
                    line_id_factory=lambda item: line_ids[item.opportunity_id],
                )
                record = uow.portfolios.insert_proposal(authority)
                reconciliation = uow.portfolios.reconcile(record.portfolio_proposal_id, lock=True)
                if (
                    not reconciliation.matched
                    or reconciliation.line_count != len(authority.lines)
                    or reconciliation.line_roster_sha256 != authority.line_roster_sha256
                    or reconciliation.gross_weight != str(authority.gross_weight)
                ):
                    raise DecisionAuthorityIntegrityError("Portfolio relational closure differs")
                result_hash = canonical_json_sha256(record)
                _finish(
                    uow,
                    receipt,
                    record.portfolio_proposal_id,
                    1,
                    result_hash,
                    context,
                    audit_id,
                    "PORTFOLIO_PROPOSAL",
                    "PORTFOLIO_PROPOSED",
                    runtime_claim,
                )
                uow.commit()
                return _proposal_result(record, result_hash=result_hash, replayed=False)

        return self._retry(operation, lambda: self._probe_proposal(opportunity_set_id, portfolio_policy_id, context, request_hash))

    def _replay_policy_tx(self, uow: PortfolioUnitOfWork, receipt: ReceiptRecord, plan, request_hash):
        _require_succeeded(receipt, request_hash)
        assert receipt.result_aggregate_id and receipt.result_hash
        record = uow.portfolios.policy_record(UUID(receipt.result_aggregate_id), lock=False)
        if record.content_sha256 != plan.content_sha256 or canonical_json_sha256(record) != receipt.result_hash:
            raise DecisionAuthorityIntegrityError("PortfolioPolicy receipt differs")
        return _policy_result(record, result_hash=receipt.result_hash, replayed=True)

    def _replay_proposal_tx(self, uow: PortfolioUnitOfWork, receipt: ReceiptRecord, request_hash):
        _require_succeeded(receipt, request_hash)
        assert receipt.result_aggregate_id and receipt.result_hash
        record = uow.portfolios.proposal_record(UUID(receipt.result_aggregate_id), lock=False)
        if canonical_json_sha256(record) != receipt.result_hash:
            raise DecisionAuthorityIntegrityError("PortfolioProposal receipt differs")
        return _proposal_result(record, result_hash=receipt.result_hash, replayed=True)

    def _probe_policy(self, plan, context, request_hash):
        record = self._queries.find_policy_request(plan.policy_code, context.idempotency_key)
        return None if record is None else _policy_replay(record, plan, request_hash)

    def _probe_proposal(self, set_id, policy_id, context, request_hash):
        record = self._queries.find_proposal_request(set_id, policy_id, context.idempotency_key)
        return None if record is None else _proposal_replay(record, request_hash)

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
                        raise DecisionTransactionRetryExhaustedError("Portfolio transaction retries exhausted") from exc
                    raise
        raise AssertionError("Portfolio retry loop did not terminate")


def _request_hash(context, value):
    return canonical_json_sha256(
        {"actor_id": context.actor_id, "actor_type": context.actor_type, "reason_code": context.reason_code, "value": value}
    )


def _require_succeeded(receipt, request_hash):
    if receipt.request_hash != request_hash:
        raise IdempotencyKeyReusedError("Portfolio replay inputs differ")
    if receipt.status == "FAILED":
        raise CommandPreviouslyFailedError(receipt.error_code or "PORTFOLIO_COMMAND_FAILED")
    if receipt.status != "SUCCEEDED" or receipt.result_aggregate_id is None or receipt.result_hash is None:
        raise CommandInProgressError("Portfolio command is not complete")


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


def _policy_replay(record, plan, request_hash):
    if record.request_sha256 != request_hash:
        raise IdempotencyKeyReusedError("PortfolioPolicy replay inputs differ")
    if record.content_sha256 != plan.content_sha256:
        raise DecisionAuthorityIntegrityError("PortfolioPolicy identity differs")
    return _policy_result(record, result_hash=canonical_json_sha256(record), replayed=True)


def _proposal_replay(record, request_hash):
    if record.request_sha256 != request_hash:
        raise IdempotencyKeyReusedError("PortfolioProposal replay inputs differ")
    return _proposal_result(record, result_hash=canonical_json_sha256(record), replayed=True)


def _policy_result(record: PortfolioPolicyRecord, *, result_hash, replayed):
    return PortfolioMutationResult(
        "PORTFOLIO_POLICY", record.portfolio_policy_id, record.version, 0, 0, record.receipt_id, result_hash, replayed
    )


def _proposal_result(record: PortfolioProposalRecord, *, result_hash, replayed):
    return PortfolioMutationResult(
        "PORTFOLIO_PROPOSAL",
        record.portfolio_proposal_id,
        1,
        record.line_count,
        record.included_count,
        record.receipt_id,
        result_hash,
        replayed,
    )


__all__ = ["PortfolioCommands", "PortfolioMutationResult"]
