"""OPEN_DECISION_RUN command with exact replay and fenced atomic closure."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Callable
from uuid import UUID, uuid4

from market_regime_alpha.decision_support.domain import (
    DecisionRunAuthority,
    OpenDecisionRunRequest,
    PreparedDecisionInputs,
    build_decision_authority,
)
from market_regime_alpha.decision_support.errors import (
    CandidateSetAlreadyCommittedError,
    DecisionAuthorityIntegrityError,
    DecisionCommitOutcomeUnknownError,
    DecisionRetryableTransactionError,
    DecisionTransactionRetryExhaustedError,
)
from market_regime_alpha.decision_support.ports import (
    DecisionInputPreparationProvider,
    DecisionRunQueryProvider,
    DecisionRunSnapshot,
    DecisionSupportUnitOfWorkProvider,
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
class OpenDecisionRunResult:
    decision_run_id: UUID
    candidate_set_id: UUID
    candidate_count: int
    target_count: int
    commitment_count: int
    reference_count: int
    candidate_roster_sha256: str
    target_roster_sha256: str
    commitment_roster_sha256: str
    definition_summary_sha256: str
    commitment_recorded_at: datetime
    runtime_run_id: UUID
    runtime_step_id: UUID
    runtime_attempt_id: UUID
    runtime_fence_token: int
    receipt_id: UUID
    result_hash: str
    replayed: bool

    def as_replay(self) -> OpenDecisionRunResult:
        return replace(self, replayed=True)


class DecisionSupportApplication:
    """Own the only command that closes one canonical Decision Run."""

    def __init__(
        self,
        preparation: DecisionInputPreparationProvider,
        uow_provider: DecisionSupportUnitOfWorkProvider,
        queries: DecisionRunQueryProvider,
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

    def open_decision_run(
        self,
        request: OpenDecisionRunRequest,
        context: CommandContext,
        *,
        runtime_claim: AttemptClaim,
    ) -> OpenDecisionRunResult:
        raw_request_hash = canonical_json_sha256(
            {
                "actor_id": context.actor_id,
                "actor_type": context.actor_type,
                "candidate_set_id": request.candidate_set_id,
                "reason_code": context.reason_code,
                "runtime_run_id": runtime_claim.run_id,
                "target_roster": request.targets,
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
        try:
            return self._open(
                request,
                context,
                runtime_claim=runtime_claim,
                raw_request_hash=raw_request_hash,
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

    def _open(
        self,
        request: OpenDecisionRunRequest,
        context: CommandContext,
        *,
        runtime_claim: AttemptClaim,
        raw_request_hash: str,
    ) -> OpenDecisionRunResult:
        descriptor = _failure_descriptor(request, raw_request_hash)
        try:
            request.validated_targets()
            request_received_at = require_utc(
                self._clock(),
                field="Decision request received time",
            )
            prepared = self._preparation.prepare(request, runtime_claim)
            _validate_runtime_claim(prepared, runtime_claim)
            request_hash = prepared.semantic_request_sha256(
                request=request,
                actor_type=context.actor_type.value,
                actor_id=context.actor_id,
                reason_code=context.reason_code,
            )
            descriptor = _failure_descriptor(request, request_hash)
            identities = _DecisionIdentities.create(prepared, self._id_factory)
            return self._write_with_bounded_retry(
                request,
                prepared,
                identities,
                request_hash=request_hash,
                request_received_at=request_received_at,
                context=context,
                runtime_claim=runtime_claim,
            )
        except StaleFenceError:
            raise
        except DecisionCommitOutcomeUnknownError:
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
            CandidateSetAlreadyCommittedError,
            CommandPreviouslyFailedError,
            DecisionAuthorityIntegrityError,
            DecisionTransactionRetryExhaustedError,
            RuntimeNotFoundError,
            RuntimeStateConflictError,
            ValueError,
        ) as exc:
            failure_descriptor = replace(
                descriptor,
                error_code=getattr(exc, "code", descriptor.error_code),
            )
            self._failure_recorder.record(
                failure_descriptor,
                context=context,
                runtime_claim=runtime_claim,
            )
            raise

    def _write_with_bounded_retry(
        self,
        request: OpenDecisionRunRequest,
        prepared: PreparedDecisionInputs,
        identities: _DecisionIdentities,
        *,
        request_hash: str,
        request_received_at: datetime,
        context: CommandContext,
        runtime_claim: AttemptClaim,
    ) -> OpenDecisionRunResult:
        for attempt_number in range(1, _MAX_TRANSACTION_ATTEMPTS + 1):
            try:
                return self._write_once(
                    request,
                    prepared,
                    identities,
                    request_hash=request_hash,
                    request_received_at=request_received_at,
                    context=context,
                    runtime_claim=runtime_claim,
                )
            except DecisionRetryableTransactionError as exc:
                if attempt_number == _MAX_TRANSACTION_ATTEMPTS:
                    raise DecisionTransactionRetryExhaustedError(
                        f"OPEN_DECISION_RUN exhausted {_MAX_TRANSACTION_ATTEMPTS} "
                        f"whole-transaction attempts after {exc.sqlstate}"
                    ) from exc
        raise AssertionError("bounded retry loop terminated without a result")

    def _write_once(
        self,
        request: OpenDecisionRunRequest,
        prepared: PreparedDecisionInputs,
        identities: _DecisionIdentities,
        *,
        request_hash: str,
        request_received_at: datetime,
        context: CommandContext,
        runtime_claim: AttemptClaim,
    ) -> OpenDecisionRunResult:
        with self._uow_provider() as uow:
            uow.runtime_finalization.lock_live_for_step(
                runtime_claim,
                expected_step_kind="OPEN_DECISION_RUN",
            )
            uow.decision_runs.lock_candidate_set_identity(request.candidate_set_id)
            uow.dependencies.lock_and_revalidate(prepared)
            receipt = uow.receipts.start(
                receipt_id=identities.receipt_id,
                command_kind="OPEN_DECISION_RUN",
                scope_id=str(request.candidate_set_id),
                idempotency_key=context.idempotency_key,
                request_hash=request_hash,
            )
            if not receipt.is_new:
                if receipt.status == "SUCCEEDED":
                    raise ConcurrentCommandSucceeded()
                if receipt.status == "FAILED":
                    raise CommandPreviouslyFailedError(
                        receipt.error_code or "OPEN_DECISION_RUN_FAILED"
                    )
                raise RuntimeStateConflictError(
                    "OPEN_DECISION_RUN receipt is not a replayable terminal result"
                )
            commitment_recorded_at = uow.decision_runs.authoritative_recorded_at()
            authority = build_decision_authority(
                decision_run_id=identities.decision_run_id,
                command_receipt_id=identities.receipt_id,
                candidate_set=prepared.candidate_set,
                targets=prepared.targets,
                references=prepared.references,
                runtime=prepared.runtime,
                request_identity=context.idempotency_key,
                request_sha256=request_hash,
                request_received_at=request_received_at,
                commitment_recorded_at=commitment_recorded_at,
                actor_type=context.actor_type.value,
                actor_id=context.actor_id,
                reason_code=context.reason_code,
                target_id_factory=identities.target_id,
                commitment_id_factory=identities.commitment_id,
                observation_id_factory=identities.observation_id,
            )
            uow.decision_runs.insert(authority)
            reconciliation = uow.decision_runs.reconcile(
                authority.decision_run_id,
                lock=True,
            )
            if (
                not reconciliation.matched
                or reconciliation.actual_target_count != authority.target_count
                or reconciliation.actual_commitment_count
                != authority.commitment_count
                or reconciliation.actual_reference_count != authority.reference_count
                or reconciliation.candidate_roster_sha256
                != authority.candidate_roster_sha256
                or reconciliation.target_roster_sha256
                != authority.target_roster_sha256
                or reconciliation.commitment_roster_sha256
                != authority.commitment_roster_sha256
            ):
                raise DecisionAuthorityIntegrityError(
                    "Decision Run relational closure did not reconcile"
                )
            result_hash = _authority_result_hash(authority)
            uow.receipts.succeed(
                receipt_id=receipt.receipt_id,
                aggregate_kind="DECISION_RUN",
                aggregate_id=str(authority.decision_run_id),
                aggregate_version=1,
                result_hash=result_hash,
                runtime_claim=runtime_claim,
            )
            uow.audit.append(
                audit_event_id=identities.audit_event_id,
                receipt_id=receipt.receipt_id,
                actor_type=context.actor_type.value,
                actor_id=context.actor_id,
                aggregate_kind="DECISION_RUN",
                aggregate_id=str(authority.decision_run_id),
                action="OPEN_DECISION_RUN",
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
            return _result(
                authority,
                receipt_id=receipt.receipt_id,
                result_hash=result_hash,
                replayed=False,
            )

    def _probe_existing(
        self,
        request: OpenDecisionRunRequest,
        context: CommandContext,
        *,
        runtime_claim: AttemptClaim,
        raise_conflict: bool,
    ) -> DecisionRunSnapshot | None:
        existing = self._queries.find_by_candidate_set(request.candidate_set_id)
        if existing is None:
            return None
        authority = existing.authority
        requested_targets = tuple(
            (item.target_definition_id, item.reference_provider_product_id)
            for item in request.targets
        )
        persisted_targets = tuple(
            (
                item.target.target_definition_id,
                item.target.reference_provider_product.provider_product_id,
            )
            for item in authority.targets
        )
        exact = (
            authority.request_identity == context.idempotency_key
            and requested_targets == persisted_targets
            and authority.runtime.run_id == runtime_claim.run_id
            and authority.actor_type == context.actor_type.value
            and authority.actor_id == context.actor_id
            and authority.reason_code == context.reason_code
        )
        if exact:
            return existing
        if not raise_conflict:
            return None
        if authority.request_identity == context.idempotency_key:
            raise IdempotencyKeyReusedError(
                "OPEN_DECISION_RUN idempotency identity has another request"
            )
        raise CandidateSetAlreadyCommittedError(
            f"CandidateSet {request.candidate_set_id} already has a DecisionRun"
        )


@dataclass(frozen=True, slots=True)
class _DecisionIdentities:
    decision_run_id: UUID
    receipt_id: UUID
    audit_event_id: UUID
    target_ids: dict[UUID, UUID]
    commitment_ids: dict[tuple[UUID, UUID], UUID]
    observation_ids: dict[UUID, UUID]

    @classmethod
    def create(
        cls,
        prepared: PreparedDecisionInputs,
        id_factory: Callable[[], UUID],
    ) -> _DecisionIdentities:
        target_ids = {
            target.target_definition_id: id_factory() for target in prepared.targets
        }
        commitment_ids = {
            (candidate.candidate_id, target.target_definition_id): id_factory()
            for target in prepared.targets
            for candidate in prepared.candidate_set.candidates
        }
        observation_ids = {
            commitment_id: id_factory()
            for commitment_id in commitment_ids.values()
        }
        return cls(
            decision_run_id=id_factory(),
            receipt_id=id_factory(),
            audit_event_id=id_factory(),
            target_ids=target_ids,
            commitment_ids=commitment_ids,
            observation_ids=observation_ids,
        )

    def target_id(self, target, ordinal):
        del ordinal
        return self.target_ids[target.target_definition_id]

    def commitment_id(self, candidate, target):
        return self.commitment_ids[(candidate.candidate_id, target.target_definition_id)]

    def observation_id(self, commitment_id):
        return self.observation_ids[commitment_id]


def _validate_runtime_claim(
    prepared: PreparedDecisionInputs,
    claim: AttemptClaim,
) -> None:
    runtime = prepared.runtime
    if (
        runtime.run_id != claim.run_id
        or runtime.step_id != claim.step_id
        or runtime.attempt_id != claim.attempt_id
        or runtime.fence_token != claim.fence_token
        or runtime.step_key != claim.step_key
    ):
        raise DecisionAuthorityIntegrityError(
            "prepared Runtime identity differs from the execution claim"
        )


def _authority_result_hash(authority: DecisionRunAuthority) -> str:
    return canonical_json_sha256(
        {
            "candidate_count": authority.candidate_count,
            "candidate_roster_sha256": authority.candidate_roster_sha256,
            "commitment_count": authority.commitment_count,
            "commitment_recorded_at": authority.commitment_recorded_at,
            "commitment_roster_sha256": authority.commitment_roster_sha256,
            "decision_run_id": authority.decision_run_id,
            "definition_summary_sha256": authority.definition_summary_sha256,
            "reference_count": authority.reference_count,
            "runtime_attempt_id": authority.runtime.attempt_id,
            "runtime_fence_token": authority.runtime.fence_token,
            "runtime_run_id": authority.runtime.run_id,
            "runtime_step_id": authority.runtime.step_id,
            "target_count": authority.target_count,
            "target_roster_sha256": authority.target_roster_sha256,
        }
    )


def _result(
    authority: DecisionRunAuthority,
    *,
    receipt_id: UUID,
    result_hash: str,
    replayed: bool,
) -> OpenDecisionRunResult:
    return OpenDecisionRunResult(
        decision_run_id=authority.decision_run_id,
        candidate_set_id=authority.candidate_set.candidate_set_id,
        candidate_count=authority.candidate_count,
        target_count=authority.target_count,
        commitment_count=authority.commitment_count,
        reference_count=authority.reference_count,
        candidate_roster_sha256=authority.candidate_roster_sha256,
        target_roster_sha256=authority.target_roster_sha256,
        commitment_roster_sha256=authority.commitment_roster_sha256,
        definition_summary_sha256=authority.definition_summary_sha256,
        commitment_recorded_at=authority.commitment_recorded_at,
        runtime_run_id=authority.runtime.run_id,
        runtime_step_id=authority.runtime.step_id,
        runtime_attempt_id=authority.runtime.attempt_id,
        runtime_fence_token=authority.runtime.fence_token,
        receipt_id=receipt_id,
        result_hash=result_hash,
        replayed=replayed,
    )


def _result_from_snapshot(
    snapshot: DecisionRunSnapshot,
    *,
    replayed: bool,
) -> OpenDecisionRunResult:
    expected = _authority_result_hash(snapshot.authority)
    if expected != snapshot.result_hash:
        raise DecisionAuthorityIntegrityError(
            "Decision Run receipt and Authority result hash differ"
        )
    return _result(
        snapshot.authority,
        receipt_id=snapshot.receipt_id,
        result_hash=snapshot.result_hash,
        replayed=replayed,
    )


def _failure_descriptor(
    request: OpenDecisionRunRequest,
    request_hash: str,
) -> CommandFailureDescriptor:
    return CommandFailureDescriptor(
        command_kind="OPEN_DECISION_RUN",
        scope_id=str(request.candidate_set_id),
        request_hash=request_hash,
        error_class="COMMAND",
        error_code="OPEN_DECISION_RUN_REJECTED",
        aggregate_kind="DECISION_RUN",
        failure_action="OPEN_DECISION_RUN_FAILED",
        rejection_command_kind="OPEN_DECISION_RUN_REJECTION",
        rejection_action="OPEN_DECISION_RUN_REJECTED",
        rejection_key_prefix="open-decision-run-rejection",
    )


__all__ = ["DecisionSupportApplication", "OpenDecisionRunResult"]
