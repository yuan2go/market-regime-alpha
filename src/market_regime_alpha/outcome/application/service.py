"""Fenced SETTLE_MARKET_TARGET_OUTCOME command and exact replay."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Callable
from uuid import UUID, uuid4

from market_regime_alpha.outcome.domain import (
    MarketTargetOutcomeAuthority,
    MarketTargetOutcomeIdentityPlan,
    OutcomeRevisionDraft,
    PreparedOutcomeInputs,
    OutcomeStatus,
    build_market_target_outcome_authority,
    calculate_market_target_outcome,
)
from market_regime_alpha.outcome.errors import (
    OutcomeAuthorityIntegrityError,
    OutcomeCommitResultUnknownError,
    OutcomeInputResolutionError,
    OutcomeRetryableTransactionError,
    OutcomeRevisionConflictError,
    OutcomeTransactionRetryExhaustedError,
)
from market_regime_alpha.outcome.ports import (
    OutcomeInputPreparationProvider,
    OutcomeReadPort,
    OutcomeReconciliation,
    OutcomeSnapshot,
    OutcomeUnitOfWorkProvider,
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
from market_regime_alpha.runtime.ports import AttemptClaim
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.time import require_utc


_MAX_TRANSACTION_ATTEMPTS = 3


@dataclass(frozen=True, slots=True)
class SettleMarketTargetOutcomeRequest:
    commitment_id: UUID
    observation_cutoff: datetime
    knowledge_cutoff: datetime
    expected_current_revision_id: UUID | None

    def __post_init__(self) -> None:
        observation = require_utc(
            self.observation_cutoff,
            field="Outcome observation cutoff",
        )
        knowledge = require_utc(
            self.knowledge_cutoff,
            field="Outcome knowledge cutoff",
        )
        object.__setattr__(self, "observation_cutoff", observation)
        object.__setattr__(self, "knowledge_cutoff", knowledge)


@dataclass(frozen=True, slots=True)
class OutcomeNotDueResult:
    commitment_id: UUID
    due_at: datetime
    observation_cutoff: datetime
    knowledge_cutoff: datetime
    status: str = "NOT_DUE"
    database_writes: int = 0


@dataclass(frozen=True, slots=True)
class SettleMarketTargetOutcomeResult:
    market_target_outcome_id: UUID
    market_target_outcome_revision_id: UUID
    commitment_id: UUID
    revision_ordinal: int
    supersedes_revision_id: UUID | None
    status: OutcomeStatus
    source_count: int
    observation_count: int
    metric_count: int
    reference_dependency_count: int
    observation_dependency_count: int
    reason_count: int
    source_roster_sha256: str
    observation_roster_sha256: str
    metric_roster_sha256: str
    reference_dependency_roster_sha256: str
    observation_dependency_roster_sha256: str
    reason_roster_sha256: str
    definition_summary_sha256: str
    observation_cutoff: datetime
    knowledge_cutoff: datetime
    settled_at: datetime
    runtime_run_id: UUID
    runtime_step_id: UUID
    runtime_attempt_id: UUID
    runtime_fence_token: int
    receipt_id: UUID
    result_hash: str
    replayed: bool

    def as_replay(self) -> SettleMarketTargetOutcomeResult:
        return replace(self, replayed=True)


OutcomeSettlementResult = OutcomeNotDueResult | SettleMarketTargetOutcomeResult


class OutcomeApplication:
    """Own the only writer of Market Target Outcome revisions."""

    def __init__(
        self,
        preparation: OutcomeInputPreparationProvider,
        uow_provider: OutcomeUnitOfWorkProvider,
        queries: OutcomeReadPort,
        *,
        id_factory: Callable[[], UUID] = uuid4,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._preparation = preparation
        self._uow_provider = uow_provider
        self._queries = queries
        self._id_factory = id_factory
        self._clock = clock
        self._failure_recorder = RuntimeCommandFailureRecorder(
            uow_provider,
            id_factory=id_factory,
        )

    def settle_market_target_outcome(
        self,
        request: SettleMarketTargetOutcomeRequest,
        context: CommandContext,
        *,
        runtime_claim: AttemptClaim,
    ) -> OutcomeSettlementResult:
        raw_request_hash = canonical_json_sha256(
            {
                "actor_id": context.actor_id,
                "actor_type": context.actor_type,
                "commitment_id": request.commitment_id,
                "expected_current_revision_id": (
                    request.expected_current_revision_id
                ),
                "knowledge_cutoff": request.knowledge_cutoff,
                "observation_cutoff": request.observation_cutoff,
                "reason_code": context.reason_code,
                "runtime_attempt_id": runtime_claim.attempt_id,
                "runtime_fence_token": runtime_claim.fence_token,
                "runtime_run_id": runtime_claim.run_id,
                "runtime_step_id": runtime_claim.step_id,
            }
        )
        existing = self._probe_existing(
            request,
            context,
            runtime_claim=runtime_claim,
            raise_conflict=True,
        )
        if existing is not None:
            return _result_from_snapshot(existing, replayed=True)
        descriptor = _failure_descriptor(request, raw_request_hash)
        try:
            received_at = require_utc(
                self._clock(),
                field="Outcome request received time",
            )
            prepared = self._preparation.prepare(request, runtime_claim)
            _validate_prepared(request, prepared, runtime_claim)
            if not prepared.is_due:
                return OutcomeNotDueResult(
                    commitment_id=request.commitment_id,
                    due_at=prepared.due_at,
                    observation_cutoff=request.observation_cutoff,
                    knowledge_cutoff=request.knowledge_cutoff,
                )
            draft = calculate_market_target_outcome(
                target=prepared.target,
                reference=prepared.commitment.reference,
                sessions=prepared.sessions,
                sources=prepared.sources,
                observation_cutoff=request.observation_cutoff,
                knowledge_cutoff=request.knowledge_cutoff,
            )
            request_hash = prepared.semantic_request_sha256(
                observation_cutoff=request.observation_cutoff,
                knowledge_cutoff=request.knowledge_cutoff,
                expected_current_revision_id=(
                    request.expected_current_revision_id
                ),
                actor_type=context.actor_type.value,
                actor_id=context.actor_id,
                reason_code=context.reason_code,
            )
            descriptor = _failure_descriptor(request, request_hash)
            identities = MarketTargetOutcomeIdentityPlan.create(
                draft,
                self._id_factory,
            )
            receipt_id = self._id_factory()
            audit_event_id = self._id_factory()
            return self._write_with_bounded_retry(
                request,
                prepared,
                draft,
                identities,
                request_hash=request_hash,
                request_received_at=received_at,
                receipt_id=receipt_id,
                audit_event_id=audit_event_id,
                context=context,
                runtime_claim=runtime_claim,
            )
        except (StaleFenceError, ConcurrentCommandSucceeded):
            existing = self._probe_existing(
                request,
                context,
                runtime_claim=runtime_claim,
                raise_conflict=True,
            )
            if existing is not None:
                return _result_from_snapshot(existing, replayed=True)
            raise
        except OutcomeCommitResultUnknownError:
            existing = self._probe_existing(
                request,
                context,
                runtime_claim=runtime_claim,
                raise_conflict=False,
            )
            if existing is not None:
                return _result_from_snapshot(existing, replayed=True)
            raise
        except (CommandInProgressError, IdempotencyKeyReusedError) as exc:
            self._failure_recorder.record_idempotency_rejection(
                descriptor,
                rejection_code=exc.code,
                context=context,
                runtime_claim=runtime_claim,
            )
            raise
        except (
            ArtifactIntegrityError,
            CommandPreviouslyFailedError,
            OutcomeAuthorityIntegrityError,
            OutcomeInputResolutionError,
            OutcomeRevisionConflictError,
            OutcomeTransactionRetryExhaustedError,
            RuntimeNotFoundError,
            RuntimeStateConflictError,
            ValueError,
        ) as exc:
            self._failure_recorder.record(
                replace(
                    descriptor,
                    error_code=getattr(exc, "code", descriptor.error_code),
                ),
                context=context,
                runtime_claim=runtime_claim,
            )
            raise

    def _write_with_bounded_retry(
        self,
        request: SettleMarketTargetOutcomeRequest,
        prepared: PreparedOutcomeInputs,
        draft: OutcomeRevisionDraft,
        identities: MarketTargetOutcomeIdentityPlan,
        *,
        request_hash: str,
        request_received_at: datetime,
        receipt_id: UUID,
        audit_event_id: UUID,
        context: CommandContext,
        runtime_claim: AttemptClaim,
    ) -> SettleMarketTargetOutcomeResult:
        for attempt_number in range(1, _MAX_TRANSACTION_ATTEMPTS + 1):
            try:
                return self._write_once(
                    request,
                    prepared,
                    draft,
                    identities,
                    request_hash=request_hash,
                    request_received_at=request_received_at,
                    receipt_id=receipt_id,
                    audit_event_id=audit_event_id,
                    context=context,
                    runtime_claim=runtime_claim,
                )
            except OutcomeRetryableTransactionError as exc:
                if attempt_number == _MAX_TRANSACTION_ATTEMPTS:
                    raise OutcomeTransactionRetryExhaustedError(
                        "SETTLE_MARKET_TARGET_OUTCOME exhausted "
                        f"{_MAX_TRANSACTION_ATTEMPTS} whole-transaction attempts "
                        f"after {exc.sqlstate}"
                    ) from exc
        raise AssertionError("bounded retry loop terminated without a result")

    def _write_once(
        self,
        request: SettleMarketTargetOutcomeRequest,
        prepared: PreparedOutcomeInputs,
        draft: OutcomeRevisionDraft,
        identities: MarketTargetOutcomeIdentityPlan,
        *,
        request_hash: str,
        request_received_at: datetime,
        receipt_id: UUID,
        audit_event_id: UUID,
        context: CommandContext,
        runtime_claim: AttemptClaim,
    ) -> SettleMarketTargetOutcomeResult:
        with self._uow_provider() as uow:
            uow.runtime_finalization.lock_live_for_step(
                runtime_claim,
                expected_step_kind="SETTLE_OUTCOME",
            )
            uow.dependencies.lock_and_revalidate(prepared)
            receipt = uow.receipts.start(
                receipt_id=receipt_id,
                command_kind="SETTLE_MARKET_TARGET_OUTCOME",
                scope_id=str(request.commitment_id),
                idempotency_key=context.idempotency_key,
                request_hash=request_hash,
            )
            if not receipt.is_new:
                if receipt.status == "SUCCEEDED":
                    raise ConcurrentCommandSucceeded()
                if receipt.status == "FAILED":
                    raise CommandPreviouslyFailedError(
                        receipt.error_code or "SETTLE_MARKET_TARGET_OUTCOME_FAILED"
                    )
                raise RuntimeStateConflictError(
                    "Outcome receipt is not a replayable terminal result"
                )
            head = uow.outcomes.lock_scope_and_head(request.commitment_id)
            if request.expected_current_revision_id is None:
                if head is not None:
                    raise OutcomeRevisionConflictError(
                        "initial Outcome settlement found an existing revision"
                    )
                create_root = True
                revision_ordinal = 1
                supersedes_revision_id = None
                planned = identities
            else:
                if (
                    head is None
                    or head.market_target_outcome_revision_id
                    != request.expected_current_revision_id
                ):
                    raise OutcomeRevisionConflictError(
                        "Outcome correction does not name the current leaf"
                    )
                create_root = False
                revision_ordinal = head.revision_ordinal + 1
                supersedes_revision_id = head.market_target_outcome_revision_id
                planned = replace(
                    identities,
                    market_target_outcome_id=head.market_target_outcome_id,
                )
            settled_at = uow.outcomes.authoritative_settled_at()
            authority = build_market_target_outcome_authority(
                identities=planned,
                commitment=prepared.commitment,
                target=prepared.target,
                draft=draft,
                runtime=prepared.runtime,
                revision_ordinal=revision_ordinal,
                supersedes_revision_id=supersedes_revision_id,
                request_identity=context.idempotency_key,
                request_sha256=request_hash,
                request_received_at=request_received_at,
                settled_at=settled_at,
                command_receipt_id=receipt.receipt_id,
                actor_type=context.actor_type.value,
                actor_id=context.actor_id,
                reason_code=context.reason_code,
            )
            uow.outcomes.insert(authority, create_root=create_root)
            actual = uow.outcomes.reconcile(
                authority.revision.market_target_outcome_revision_id,
                lock=True,
            )
            expected = OutcomeReconciliation.from_revision(
                authority.revision,
                matched=True,
            )
            if not actual.matched or actual != expected:
                raise OutcomeAuthorityIntegrityError(
                    "Outcome relational revision did not reconcile"
                )
            result_hash = _authority_result_hash(authority)
            uow.receipts.succeed(
                receipt_id=receipt.receipt_id,
                aggregate_kind="MARKET_TARGET_OUTCOME",
                aggregate_id=str(authority.root.market_target_outcome_id),
                aggregate_version=revision_ordinal,
                result_hash=result_hash,
                runtime_claim=runtime_claim,
            )
            uow.audit.append(
                audit_event_id=audit_event_id,
                receipt_id=receipt.receipt_id,
                actor_type=context.actor_type.value,
                actor_id=context.actor_id,
                aggregate_kind="MARKET_TARGET_OUTCOME",
                aggregate_id=str(authority.root.market_target_outcome_id),
                action="SETTLE_MARKET_TARGET_OUTCOME",
                reason_code=context.reason_code,
                before_version=(None if revision_ordinal == 1 else revision_ordinal - 1),
                after_version=revision_ordinal,
                runtime_claim=runtime_claim,
            )
            uow.runtime_finalization.succeed(
                runtime_claim,
                receipt_id=receipt.receipt_id,
                result_hash=result_hash,
            )
            uow.commit()
            return _result(
                authority,
                receipt_id=receipt.receipt_id,
                result_hash=result_hash,
                replayed=False,
            )

    def _probe_existing(
        self,
        request: SettleMarketTargetOutcomeRequest,
        context: CommandContext,
        *,
        runtime_claim: AttemptClaim,
        raise_conflict: bool,
    ) -> OutcomeSnapshot | None:
        existing = self._queries.find_by_request(
            request.commitment_id,
            context.idempotency_key,
        )
        if existing is None:
            return None
        revision = existing.authority.revision
        exact = (
            existing.authority.commitment.commitment_id == request.commitment_id
            and revision.draft.observation_cutoff == request.observation_cutoff
            and revision.draft.knowledge_cutoff == request.knowledge_cutoff
            and revision.supersedes_revision_id
            == request.expected_current_revision_id
            and revision.runtime.run_id == runtime_claim.run_id
            and revision.runtime.step_id == runtime_claim.step_id
            and revision.runtime.attempt_id == runtime_claim.attempt_id
            and revision.runtime.fence_token == runtime_claim.fence_token
            and revision.actor_type == context.actor_type.value
            and revision.actor_id == context.actor_id
            and revision.reason_code == context.reason_code
        )
        if exact:
            return existing
        if raise_conflict:
            raise IdempotencyKeyReusedError(
                "SETTLE_MARKET_TARGET_OUTCOME identity has another request"
            )
        return None


def _validate_prepared(
    request: SettleMarketTargetOutcomeRequest,
    prepared: PreparedOutcomeInputs,
    claim: AttemptClaim,
) -> None:
    runtime = prepared.runtime
    if prepared.commitment.commitment_id != request.commitment_id:
        raise OutcomeAuthorityIntegrityError(
            "prepared commitment differs from Outcome request"
        )
    if (
        prepared.observation_cutoff != request.observation_cutoff
        or prepared.knowledge_cutoff != request.knowledge_cutoff
    ):
        raise OutcomeAuthorityIntegrityError(
            "prepared Outcome cutoffs differ from request"
        )
    if (
        runtime.run_id != claim.run_id
        or runtime.step_id != claim.step_id
        or runtime.attempt_id != claim.attempt_id
        or runtime.fence_token != claim.fence_token
        or runtime.step_key != claim.step_key
    ):
        raise OutcomeAuthorityIntegrityError(
            "prepared Runtime identity differs from execution claim"
        )
    due = request.observation_cutoff >= prepared.due_at
    if prepared.is_due != due:
        raise OutcomeAuthorityIntegrityError(
            "prepared Outcome due assessment disagrees with cutoff"
        )


def _authority_result_hash(authority: MarketTargetOutcomeAuthority) -> str:
    revision = authority.revision
    return canonical_json_sha256(
        {
            "commitment_id": authority.commitment.commitment_id,
            "definition_summary_sha256": revision.definition_summary_sha256,
            "knowledge_cutoff": revision.draft.knowledge_cutoff,
            "market_target_outcome_id": authority.root.market_target_outcome_id,
            "market_target_outcome_revision_id": (
                revision.market_target_outcome_revision_id
            ),
            "observation_cutoff": revision.draft.observation_cutoff,
            "revision_ordinal": revision.revision_ordinal,
            "runtime_attempt_id": revision.runtime.attempt_id,
            "runtime_fence_token": revision.runtime.fence_token,
            "runtime_run_id": revision.runtime.run_id,
            "runtime_step_id": revision.runtime.step_id,
            "settled_at": revision.settled_at,
            "status": revision.draft.status,
            "supersedes_revision_id": revision.supersedes_revision_id,
        }
    )


def _result(
    authority: MarketTargetOutcomeAuthority,
    *,
    receipt_id: UUID,
    result_hash: str,
    replayed: bool,
) -> SettleMarketTargetOutcomeResult:
    revision = authority.revision
    return SettleMarketTargetOutcomeResult(
        market_target_outcome_id=authority.root.market_target_outcome_id,
        market_target_outcome_revision_id=(
            revision.market_target_outcome_revision_id
        ),
        commitment_id=authority.commitment.commitment_id,
        revision_ordinal=revision.revision_ordinal,
        supersedes_revision_id=revision.supersedes_revision_id,
        status=revision.draft.status,
        source_count=revision.source_count,
        observation_count=revision.observation_count,
        metric_count=revision.metric_count,
        reference_dependency_count=revision.reference_dependency_count,
        observation_dependency_count=revision.observation_dependency_count,
        reason_count=revision.reason_count,
        source_roster_sha256=revision.source_roster_sha256,
        observation_roster_sha256=revision.observation_roster_sha256,
        metric_roster_sha256=revision.metric_roster_sha256,
        reference_dependency_roster_sha256=(
            revision.reference_dependency_roster_sha256
        ),
        observation_dependency_roster_sha256=(
            revision.observation_dependency_roster_sha256
        ),
        reason_roster_sha256=revision.reason_roster_sha256,
        definition_summary_sha256=revision.definition_summary_sha256,
        observation_cutoff=revision.draft.observation_cutoff,
        knowledge_cutoff=revision.draft.knowledge_cutoff,
        settled_at=revision.settled_at,
        runtime_run_id=revision.runtime.run_id,
        runtime_step_id=revision.runtime.step_id,
        runtime_attempt_id=revision.runtime.attempt_id,
        runtime_fence_token=revision.runtime.fence_token,
        receipt_id=receipt_id,
        result_hash=result_hash,
        replayed=replayed,
    )


def _result_from_snapshot(
    snapshot: OutcomeSnapshot,
    *,
    replayed: bool,
) -> SettleMarketTargetOutcomeResult:
    expected = _authority_result_hash(snapshot.authority)
    if expected != snapshot.result_hash:
        raise OutcomeAuthorityIntegrityError(
            "Outcome receipt and Authority result hash differ"
        )
    return _result(
        snapshot.authority,
        receipt_id=snapshot.receipt_id,
        result_hash=snapshot.result_hash,
        replayed=replayed,
    )


def _failure_descriptor(
    request: SettleMarketTargetOutcomeRequest,
    request_hash: str,
) -> CommandFailureDescriptor:
    return CommandFailureDescriptor(
        command_kind="SETTLE_MARKET_TARGET_OUTCOME",
        scope_id=str(request.commitment_id),
        request_hash=request_hash,
        error_class="COMMAND",
        error_code="SETTLE_MARKET_TARGET_OUTCOME_REJECTED",
        aggregate_kind="MARKET_TARGET_OUTCOME",
        failure_action="SETTLE_MARKET_TARGET_OUTCOME_FAILED",
        rejection_command_kind="SETTLE_MARKET_TARGET_OUTCOME_REJECTION",
        rejection_action="SETTLE_MARKET_TARGET_OUTCOME_REJECTED",
        rejection_key_prefix="settle-market-target-outcome-rejection",
    )


__all__ = [
    "OutcomeApplication",
    "OutcomeNotDueResult",
    "OutcomeSettlementResult",
    "SettleMarketTargetOutcomeRequest",
    "SettleMarketTargetOutcomeResult",
]
