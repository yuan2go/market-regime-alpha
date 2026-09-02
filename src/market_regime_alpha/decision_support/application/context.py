"""Immutable Context policy registration and PIT assessment commands."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable, cast
from uuid import UUID, uuid4

from market_regime_alpha.decision_support.domain import (
    ContextPolicyPlan,
    ExploratoryRetrospectiveDecisionScope,
    PreparedContextInputs,
    build_context_assessment_authority,
)
from market_regime_alpha.decision_support.errors import (
    ContextAlreadyAssessedError,
    ContextAuthorityIntegrityError,
    DecisionCommitOutcomeUnknownError,
    DecisionRetryableTransactionError,
    DecisionTransactionRetryExhaustedError,
)
from market_regime_alpha.decision_support.ports import (
    ContextAssessmentRecord,
    ContextInputPreparationProvider,
    ContextPolicyRecord,
    ContextQueryProvider,
    ContextUnitOfWork,
    ContextUnitOfWorkProvider,
)
from market_regime_alpha.runtime.application import (
    CommandContext,
    CommandFailureDescriptor,
    ConcurrentCommandSucceeded,
    RuntimeCommandFailureRecorder,
)
from market_regime_alpha.runtime.errors import (
    ArtifactIntegrityError,
    CommandInProgressError,
    CommandPreviouslyFailedError,
    IdempotencyKeyReusedError,
    RuntimeNotFoundError,
    RuntimeStateConflictError,
    StaleFenceError,
)
from market_regime_alpha.runtime.ports import (
    AttemptClaim,
    CommandFailureUnitOfWorkProvider,
    ReceiptRecord,
)
from market_regime_alpha.shared.hashing import canonical_json_sha256


_MAX_TRANSACTION_ATTEMPTS = 3


@dataclass(frozen=True, slots=True)
class ContextMutationResult:
    aggregate_kind: str
    aggregate_id: UUID
    aggregate_version: int
    child_count: int
    source_count: int
    receipt_id: UUID
    result_hash: str
    replayed: bool

    def as_replay(self) -> ContextMutationResult:
        return replace(self, replayed=True)


class ContextCommands:
    """Own the two Context transactions without exposing an Outcome port."""

    def __init__(
        self,
        preparation: ContextInputPreparationProvider,
        uow_provider: ContextUnitOfWorkProvider,
        queries: ContextQueryProvider,
        *,
        id_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self._preparation = preparation
        self._uow_provider = uow_provider
        self._queries = queries
        self._id_factory = id_factory
        self._failure_recorder = RuntimeCommandFailureRecorder(
            cast(CommandFailureUnitOfWorkProvider, uow_provider),
            id_factory=id_factory,
        )

    def register_policy(
        self,
        plan: ContextPolicyPlan,
        context: CommandContext,
        *,
        runtime_claim: AttemptClaim | None = None,
    ) -> ContextMutationResult:
        request_hash = canonical_json_sha256(
            {
                "actor_id": context.actor_id,
                "actor_type": context.actor_type,
                "plan": plan,
                "reason_code": context.reason_code,
            }
        )
        existing = self._queries.find_policy_request(
            plan.policy_code,
            context.idempotency_key,
        )
        if existing is not None:
            return self._policy_replay_result(existing, plan)
        descriptor = _failure_descriptor(
            operation="REGISTER_CONTEXT_POLICY",
            scope_id=plan.policy_code,
            request_hash=request_hash,
        )
        try:
            return self._retry(
                lambda: self._register_policy_once(
                    plan,
                    context,
                    request_hash=request_hash,
                    runtime_claim=runtime_claim,
                ),
                replay=lambda: self._probe_policy(plan, context),
            )
        except StaleFenceError:
            raise
        except (CommandInProgressError, IdempotencyKeyReusedError) as exc:
            self._failure_recorder.record_idempotency_rejection(
                descriptor,
                rejection_code=exc.code,
                context=context,
                runtime_claim=runtime_claim,
            )
            raise
        except _RECORDED_FAILURES as exc:
            self._failure_recorder.record(
                replace(
                    descriptor,
                    error_code=getattr(exc, "code", descriptor.error_code),
                ),
                context=context,
                runtime_claim=runtime_claim,
            )
            raise

    def assess_context(
        self,
        decision_run_id: UUID,
        context_policy_id: UUID,
        context: CommandContext,
        *,
        runtime_claim: AttemptClaim,
    ) -> ContextMutationResult:
        return self._assess_context(
            decision_run_id,
            context_policy_id,
            context,
            runtime_claim=runtime_claim,
            retrospective_scope=None,
        )

    def assess_exploratory_retrospective_context(
        self,
        decision_run_id: UUID,
        context_policy_id: UUID,
        retrospective_scope: ExploratoryRetrospectiveDecisionScope,
        context: CommandContext,
        *,
        runtime_claim: AttemptClaim,
    ) -> ContextMutationResult:
        return self._assess_context(
            decision_run_id,
            context_policy_id,
            context,
            runtime_claim=runtime_claim,
            retrospective_scope=retrospective_scope,
        )

    def _assess_context(
        self,
        decision_run_id: UUID,
        context_policy_id: UUID,
        context: CommandContext,
        *,
        runtime_claim: AttemptClaim,
        retrospective_scope: ExploratoryRetrospectiveDecisionScope | None,
    ) -> ContextMutationResult:
        existing = self._queries.find_assessment_request(
            decision_run_id,
            context_policy_id,
            context.idempotency_key,
        )
        if existing is not None:
            return _assessment_result(existing, replayed=True)
        prepared: PreparedContextInputs
        if retrospective_scope is None:
            prepared = self._preparation.prepare(decision_run_id, context_policy_id)
        else:
            prepared = self._preparation.prepare_exploratory_retrospective(
                decision_run_id,
                context_policy_id,
                retrospective_scope,
            )
        if prepared.decision_run_id != decision_run_id or prepared.policy.context_policy_id != context_policy_id:
            raise ContextAuthorityIntegrityError("Context preparation returned a different Authority identity")
        request_hash = canonical_json_sha256(
            {
                "actor_id": context.actor_id,
                "actor_type": context.actor_type,
                "candidate_roster_sha256": prepared.candidate_roster_sha256,
                "context_policy_id": context_policy_id,
                "decision_run_id": decision_run_id,
                "policy_content_sha256": prepared.policy.content_sha256,
                "reason_code": context.reason_code,
                "retrospective_scope": retrospective_scope,
                "source_roster_sha256": prepared.source_roster_sha256,
            }
        )
        identities = _ContextIdentities.create(prepared, self._id_factory)
        recorded_at = self._queries.authoritative_time()
        authority = build_context_assessment_authority(
            assessment_group_id=identities.assessment_group_id,
            prepared=prepared,
            request_identity=context.idempotency_key,
            request_sha256=request_hash,
            command_receipt_id=identities.receipt_id,
            recorded_at=recorded_at,
            assessment_id_factory=identities.assessment_id,
            metric_id_factory=identities.metric_id,
            source_id_factory=identities.source_id,
        )
        descriptor = _failure_descriptor(
            operation="ASSESS_CONTEXT",
            scope_id=f"{decision_run_id}:{context_policy_id}",
            request_hash=request_hash,
        )
        try:
            return self._retry(
                lambda: self._assess_once(
                    authority,
                    prepared,
                    context,
                    receipt_id=identities.receipt_id,
                    audit_event_id=identities.audit_event_id,
                    runtime_claim=runtime_claim,
                ),
                replay=lambda: self._probe_assessment(
                    decision_run_id,
                    context_policy_id,
                    context,
                    request_hash=request_hash,
                ),
            )
        except StaleFenceError:
            replay = self._probe_assessment(
                decision_run_id,
                context_policy_id,
                context,
                request_hash=request_hash,
            )
            if replay is not None:
                return replay
            raise
        except (CommandInProgressError, IdempotencyKeyReusedError) as exc:
            self._failure_recorder.record_idempotency_rejection(
                descriptor,
                rejection_code=exc.code,
                context=context,
                runtime_claim=runtime_claim,
            )
            raise
        except _RECORDED_FAILURES as exc:
            self._failure_recorder.record(
                replace(
                    descriptor,
                    error_code=getattr(exc, "code", descriptor.error_code),
                ),
                context=context,
                runtime_claim=runtime_claim,
            )
            raise

    def _register_policy_once(
        self,
        plan: ContextPolicyPlan,
        context: CommandContext,
        *,
        request_hash: str,
        runtime_claim: AttemptClaim | None,
    ) -> ContextMutationResult:
        with self._uow_provider() as uow:
            if runtime_claim is not None:
                uow.runtime_finalization.lock_live(runtime_claim)
            receipt = uow.receipts.start(
                receipt_id=self._id_factory(),
                command_kind="REGISTER_CONTEXT_POLICY",
                scope_id=plan.policy_code,
                idempotency_key=context.idempotency_key,
                request_hash=request_hash,
            )
            if not receipt.is_new:
                return self._replay_policy_in_transaction(
                    uow,
                    receipt,
                    plan,
                    runtime_claim,
                )
            uow.contexts.lock_policy_identity(plan.policy_code)
            uow.artifacts.require_exact(plan.code_artifact, lock=True)
            uow.artifacts.require_exact(plan.config_artifact, lock=True)
            record = uow.contexts.register_policy(
                plan,
                request_identity=context.idempotency_key,
                request_sha256=request_hash,
            )
            result_hash = canonical_json_sha256(record)
            self._finish(
                uow,
                receipt_id=receipt.receipt_id,
                aggregate_kind="CONTEXT_POLICY",
                aggregate_id=record.context_policy_id,
                aggregate_version=record.version,
                result_hash=result_hash,
                action="CONTEXT_POLICY_REGISTERED",
                context=context,
                runtime_claim=runtime_claim,
            )
            uow.commit()
            return _policy_result(
                record,
                result_hash=result_hash,
                replayed=False,
            )

    def _assess_once(
        self,
        authority,
        prepared,
        context: CommandContext,
        *,
        receipt_id: UUID,
        audit_event_id: UUID,
        runtime_claim: AttemptClaim,
    ) -> ContextMutationResult:
        with self._uow_provider() as uow:
            uow.runtime_finalization.lock_live_for_step(
                runtime_claim,
                expected_step_kind="ASSESS_CONTEXT",
            )
            receipt = uow.receipts.start(
                receipt_id=receipt_id,
                command_kind="ASSESS_CONTEXT",
                scope_id=(f"{authority.decision_run_id}:{authority.context_policy_id}"),
                idempotency_key=context.idempotency_key,
                request_hash=authority.request_sha256,
            )
            if not receipt.is_new:
                return self._replay_assessment_in_transaction(
                    uow,
                    receipt,
                    runtime_claim,
                )
            uow.contexts.lock_assessment_identity(
                authority.decision_run_id,
                authority.context_policy_id,
            )
            uow.dependencies.lock_and_revalidate(prepared)
            record = uow.contexts.insert_assessment(authority)
            reconciliation = uow.contexts.reconcile(
                authority.assessment_group_id,
                lock=True,
            )
            if (
                not reconciliation.matched
                or reconciliation.actual_assessment_count != authority.assessment_count
                or reconciliation.actual_metric_count != authority.metric_count
                or reconciliation.actual_source_count != authority.source_count
                or reconciliation.assessment_roster_sha256 != authority.assessment_roster_sha256
            ):
                raise ContextAuthorityIntegrityError("Context relational closure did not reconcile")
            result_hash = canonical_json_sha256(record)
            self._finish(
                uow,
                receipt_id=receipt.receipt_id,
                aggregate_kind="CONTEXT_ASSESSMENT_GROUP",
                aggregate_id=record.assessment_group_id,
                aggregate_version=1,
                result_hash=result_hash,
                action="CONTEXT_ASSESSED",
                context=context,
                runtime_claim=runtime_claim,
                audit_event_id=audit_event_id,
            )
            uow.commit()
            return _assessment_result(
                record,
                result_hash=result_hash,
                replayed=False,
            )

    def _finish(
        self,
        uow: ContextUnitOfWork,
        *,
        receipt_id: UUID,
        aggregate_kind: str,
        aggregate_id: UUID,
        aggregate_version: int,
        result_hash: str,
        action: str,
        context: CommandContext,
        runtime_claim: AttemptClaim | None,
        audit_event_id: UUID | None = None,
    ) -> None:
        uow.receipts.succeed(
            receipt_id=receipt_id,
            aggregate_kind=aggregate_kind,
            aggregate_id=str(aggregate_id),
            aggregate_version=aggregate_version,
            result_hash=result_hash,
            runtime_claim=runtime_claim,
        )
        uow.audit.append(
            audit_event_id=audit_event_id or self._id_factory(),
            receipt_id=receipt_id,
            actor_type=context.actor_type.value,
            actor_id=context.actor_id,
            aggregate_kind=aggregate_kind,
            aggregate_id=str(aggregate_id),
            action=action,
            reason_code=context.reason_code,
            before_version=None,
            after_version=aggregate_version,
            runtime_claim=runtime_claim,
        )
        if runtime_claim is not None:
            uow.runtime_finalization.succeed(
                runtime_claim,
                receipt_id=receipt_id,
                result_hash=result_hash,
            )

    def _replay_policy_in_transaction(
        self,
        uow: ContextUnitOfWork,
        receipt: ReceiptRecord,
        plan: ContextPolicyPlan,
        runtime_claim: AttemptClaim | None,
    ) -> ContextMutationResult:
        _ensure_succeeded(receipt, "ContextPolicy")
        assert receipt.result_aggregate_id is not None
        assert receipt.result_hash is not None
        record = uow.contexts.policy_record(
            UUID(receipt.result_aggregate_id),
            lock=False,
        )
        if record.content_sha256 != plan.content_sha256:
            raise IdempotencyKeyReusedError("ContextPolicy replay content differs from request")
        if canonical_json_sha256(record) != receipt.result_hash:
            raise ContextAuthorityIntegrityError("ContextPolicy receipt and Authority differ")
        self._finish_replay_runtime(uow, receipt, runtime_claim)
        return _policy_result(
            record,
            result_hash=receipt.result_hash,
            replayed=True,
        )

    def _replay_assessment_in_transaction(
        self,
        uow: ContextUnitOfWork,
        receipt: ReceiptRecord,
        runtime_claim: AttemptClaim,
    ) -> ContextMutationResult:
        _ensure_succeeded(receipt, "ContextAssessment")
        assert receipt.result_aggregate_id is not None
        assert receipt.result_hash is not None
        record = uow.contexts.assessment_record(
            UUID(receipt.result_aggregate_id),
            lock=False,
        )
        if canonical_json_sha256(record) != receipt.result_hash:
            raise ContextAuthorityIntegrityError("ContextAssessment receipt and Authority differ")
        self._finish_replay_runtime(uow, receipt, runtime_claim)
        return _assessment_result(
            record,
            result_hash=receipt.result_hash,
            replayed=True,
        )

    @staticmethod
    def _finish_replay_runtime(
        uow: ContextUnitOfWork,
        receipt: ReceiptRecord,
        runtime_claim: AttemptClaim | None,
    ) -> None:
        if runtime_claim is not None:
            assert receipt.result_hash is not None
            uow.runtime_finalization.succeed(
                runtime_claim,
                receipt_id=receipt.receipt_id,
                result_hash=receipt.result_hash,
            )
            uow.commit()

    def _probe_policy(
        self,
        plan: ContextPolicyPlan,
        context: CommandContext,
    ) -> ContextMutationResult | None:
        record = self._queries.find_policy_request(
            plan.policy_code,
            context.idempotency_key,
        )
        return None if record is None else self._policy_replay_result(record, plan)

    @staticmethod
    def _policy_replay_result(
        record: ContextPolicyRecord,
        plan: ContextPolicyPlan,
    ) -> ContextMutationResult:
        if record.content_sha256 != plan.content_sha256:
            raise IdempotencyKeyReusedError("ContextPolicy replay content differs from request")
        return _policy_result(
            record,
            result_hash=canonical_json_sha256(record),
            replayed=True,
        )

    def _probe_assessment(
        self,
        decision_run_id: UUID,
        context_policy_id: UUID,
        context: CommandContext,
        *,
        request_hash: str,
    ) -> ContextMutationResult | None:
        record = self._queries.find_assessment_request(
            decision_run_id,
            context_policy_id,
            context.idempotency_key,
        )
        if record is None:
            return None
        if record.request_sha256 != request_hash:
            raise IdempotencyKeyReusedError("ContextAssessment replay inputs differ from request")
        return _assessment_result(record, replayed=True)

    def _retry(
        self,
        operation: Callable[[], ContextMutationResult],
        *,
        replay: Callable[[], ContextMutationResult | None],
    ) -> ContextMutationResult:
        for attempt in range(_MAX_TRANSACTION_ATTEMPTS):
            try:
                return operation()
            except ConcurrentCommandSucceeded:
                existing = replay()
                if existing is not None:
                    return existing
                if attempt == _MAX_TRANSACTION_ATTEMPTS - 1:
                    raise
            except (
                DecisionRetryableTransactionError,
                DecisionCommitOutcomeUnknownError,
            ) as exc:
                existing = replay()
                if existing is not None:
                    return existing
                if attempt == _MAX_TRANSACTION_ATTEMPTS - 1:
                    if isinstance(exc, DecisionRetryableTransactionError):
                        raise DecisionTransactionRetryExhaustedError("Context command exhausted whole-transaction retries") from exc
                    raise
        raise AssertionError("Context bounded retry loop did not terminate")


@dataclass(frozen=True, slots=True)
class _ContextIdentities:
    assessment_group_id: UUID
    receipt_id: UUID
    audit_event_id: UUID
    assessment_ids: dict[object, UUID]
    metric_ids: dict[UUID, UUID]
    source_ids: dict[tuple[UUID, int], UUID]

    @classmethod
    def create(cls, prepared, factory: Callable[[], UUID]) -> _ContextIdentities:
        assessment_ids = {kind: factory() for kind in dict.fromkeys(metric.context_kind for metric in prepared.policy.metrics)}
        return cls(
            assessment_group_id=factory(),
            receipt_id=factory(),
            audit_event_id=factory(),
            assessment_ids=assessment_ids,
            metric_ids={metric.context_policy_metric_id: factory() for metric in prepared.policy.metrics},
            source_ids={(source.context_policy_metric_id, source.source_ordinal): factory() for source in prepared.sources},
        )

    def assessment_id(self, kind, ordinal: int) -> UUID:
        del ordinal
        return self.assessment_ids[kind]

    def metric_id(self, metric) -> UUID:
        return self.metric_ids[metric.context_policy_metric_id]

    def source_id(self, metric, source) -> UUID:
        return self.source_ids[(metric.context_policy_metric_id, source.source_ordinal)]


def _policy_result(
    record: ContextPolicyRecord,
    *,
    result_hash: str,
    replayed: bool,
) -> ContextMutationResult:
    return ContextMutationResult(
        aggregate_kind="CONTEXT_POLICY",
        aggregate_id=record.context_policy_id,
        aggregate_version=record.version,
        child_count=record.metric_count,
        source_count=0,
        receipt_id=record.receipt_id,
        result_hash=result_hash,
        replayed=replayed,
    )


def _assessment_result(
    record: ContextAssessmentRecord,
    *,
    result_hash: str | None = None,
    replayed: bool,
) -> ContextMutationResult:
    return ContextMutationResult(
        aggregate_kind="CONTEXT_ASSESSMENT_GROUP",
        aggregate_id=record.assessment_group_id,
        aggregate_version=1,
        child_count=record.metric_count,
        source_count=record.source_count,
        receipt_id=record.receipt_id,
        result_hash=result_hash or canonical_json_sha256(record),
        replayed=replayed,
    )


def _ensure_succeeded(receipt: ReceiptRecord, label: str) -> None:
    if receipt.status == "FAILED":
        raise CommandPreviouslyFailedError(receipt.error_code or f"{label}_FAILED")
    if receipt.status != "SUCCEEDED":
        raise CommandInProgressError(f"{label} receipt is not terminal")
    if receipt.result_aggregate_id is None or receipt.result_hash is None:
        raise ContextAuthorityIntegrityError(f"{label} receipt is incomplete")


def _failure_descriptor(
    *,
    operation: str,
    scope_id: str,
    request_hash: str,
) -> CommandFailureDescriptor:
    return CommandFailureDescriptor(
        command_kind=operation,
        scope_id=scope_id,
        request_hash=request_hash,
        error_class="COMMAND",
        error_code=f"{operation}_REJECTED",
        aggregate_kind="DECISION_SUPPORT_COMMAND",
        failure_action="DECISION_SUPPORT_COMMAND_FAILED",
        rejection_command_kind="DECISION_SUPPORT_COMMAND_REJECTION",
        rejection_action="DECISION_SUPPORT_COMMAND_REJECTED",
        rejection_key_prefix="decision-support-command-rejection",
    )


_RECORDED_FAILURES = (
    ArtifactIntegrityError,
    CommandPreviouslyFailedError,
    ContextAlreadyAssessedError,
    ContextAuthorityIntegrityError,
    DecisionTransactionRetryExhaustedError,
    RuntimeNotFoundError,
    RuntimeStateConflictError,
    ValueError,
)


__all__ = ["ContextCommands", "ContextMutationResult"]
