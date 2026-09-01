"""Create complete Experiment-bound ResearchAssessment revisions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, cast
from uuid import UUID

from market_regime_alpha.research_qualification.application._command_support import (
    replay_concurrent_success,
    retry_transient_transaction,
    terminal_failure_boundary,
)
from market_regime_alpha.research_qualification.application._results import (
    ensure_replay_succeeded,
)
from market_regime_alpha.research_qualification.domain.assessment import (
    ResearchAssessmentPlan,
)
from market_regime_alpha.research_qualification.ports.assessment_uow import (
    AssessmentUnitOfWork,
    AssessmentUnitOfWorkProvider,
    ResearchAssessmentRecord,
)
from market_regime_alpha.runtime.application import (
    CommandContext,
    RuntimeCommandFailureRecorder,
)
from market_regime_alpha.runtime.errors import ArtifactIntegrityError
from market_regime_alpha.runtime.ports import (
    AttemptClaim,
    CommandFailureUnitOfWorkProvider,
    ReceiptRecord,
)
from market_regime_alpha.shared.hashing import canonical_json_sha256


@dataclass(frozen=True, slots=True)
class AssessmentMutationResult:
    aggregate_kind: str
    aggregate_id: UUID
    revision: int
    assessment_status: str
    evaluation_count: int
    evidence_count: int
    receipt_id: UUID
    result_hash: str
    replayed: bool


class AssessmentCommands:
    def __init__(
        self,
        uow_provider: AssessmentUnitOfWorkProvider,
        *,
        id_factory: Callable[[], UUID],
    ) -> None:
        self._uow_provider = uow_provider
        self._id_factory = id_factory
        self._failure_recorder = RuntimeCommandFailureRecorder(
            cast(CommandFailureUnitOfWorkProvider, uow_provider),
            id_factory=id_factory,
        )

    @retry_transient_transaction
    @replay_concurrent_success
    def assess(
        self,
        plan: ResearchAssessmentPlan,
        context: CommandContext,
        *,
        runtime_claim: AttemptClaim | None = None,
    ) -> AssessmentMutationResult:
        request_hash = canonical_json_sha256(plan)
        with terminal_failure_boundary(
            self._failure_recorder,
            operation="ASSESS_RESEARCH_EXPERIMENT",
            scope_id=plan.assessment_code,
            request_hash=request_hash,
            error_class="COMMAND",
            error_code="ASSESS_RESEARCH_EXPERIMENT_REJECTED",
            context=context,
            runtime_claim=runtime_claim,
        ):
            return self._assess_once(
                plan,
                context,
                request_hash=request_hash,
                runtime_claim=runtime_claim,
            )

    def _assess_once(
        self,
        plan: ResearchAssessmentPlan,
        context: CommandContext,
        *,
        request_hash: str,
        runtime_claim: AttemptClaim | None,
    ) -> AssessmentMutationResult:
        with self._uow_provider() as uow:
            if runtime_claim is not None:
                uow.runtime_finalization.lock_live(runtime_claim)
            receipt = uow.receipts.start(
                receipt_id=self._id_factory(),
                command_kind="ASSESS_RESEARCH_EXPERIMENT",
                scope_id=plan.assessment_code,
                idempotency_key=context.idempotency_key,
                request_hash=request_hash,
            )
            if not receipt.is_new:
                return self._replay(uow, receipt, runtime_claim)
            uow.assessments.lock_identity(plan.assessment_code)
            uow.artifacts.require_exact(plan.code_artifact, lock=True)
            uow.artifacts.require_exact(plan.config_artifact, lock=True)
            record = uow.assessments.assess(
                plan,
                request_identity=context.idempotency_key,
                request_sha256=request_hash,
            )
            result_hash = canonical_json_sha256(record)
            self._finish(
                uow,
                record,
                receipt.receipt_id,
                result_hash,
                context,
                runtime_claim,
            )
            uow.commit()
            return self._result(
                record,
                receipt_id=receipt.receipt_id,
                result_hash=result_hash,
                replayed=False,
            )

    def _finish(
        self,
        uow: AssessmentUnitOfWork,
        record: ResearchAssessmentRecord,
        receipt_id: UUID,
        result_hash: str,
        context: CommandContext,
        runtime_claim: AttemptClaim | None,
    ) -> None:
        uow.receipts.succeed(
            receipt_id=receipt_id,
            aggregate_kind="RESEARCH_ASSESSMENT",
            aggregate_id=str(record.research_assessment_id),
            aggregate_version=record.revision,
            result_hash=result_hash,
            runtime_claim=runtime_claim,
        )
        uow.audit.append(
            audit_event_id=self._id_factory(),
            receipt_id=receipt_id,
            actor_type=context.actor_type.value,
            actor_id=context.actor_id,
            aggregate_kind="RESEARCH_ASSESSMENT",
            aggregate_id=str(record.research_assessment_id),
            action="RESEARCH_ASSESSMENT_RECORDED",
            reason_code=context.reason_code,
            before_version=None,
            after_version=record.revision,
            runtime_claim=runtime_claim,
        )
        if runtime_claim is not None:
            uow.runtime_finalization.succeed(
                runtime_claim,
                receipt_id=receipt_id,
                result_hash=result_hash,
            )

    def _replay(
        self,
        uow: AssessmentUnitOfWork,
        receipt: ReceiptRecord,
        runtime_claim: AttemptClaim | None,
    ) -> AssessmentMutationResult:
        ensure_replay_succeeded(receipt)
        if (
            receipt.result_aggregate_kind != "RESEARCH_ASSESSMENT"
            or receipt.result_aggregate_id is None
            or receipt.result_hash is None
        ):
            raise ArtifactIntegrityError("ResearchAssessment receipt is incomplete")
        assessment_id = UUID(receipt.result_aggregate_id)
        record = uow.assessments.record(assessment_id, lock=False)
        if canonical_json_sha256(record) != receipt.result_hash:
            raise ArtifactIntegrityError(
                "ResearchAssessment receipt and Authority differ"
            )
        if runtime_claim is not None:
            uow.runtime_finalization.succeed(
                runtime_claim,
                receipt_id=receipt.receipt_id,
                result_hash=receipt.result_hash,
            )
            uow.commit()
        return self._result(
            record,
            receipt_id=receipt.receipt_id,
            result_hash=receipt.result_hash,
            replayed=True,
        )

    @staticmethod
    def _result(
        record: ResearchAssessmentRecord,
        *,
        receipt_id: UUID,
        result_hash: str,
        replayed: bool,
    ) -> AssessmentMutationResult:
        return AssessmentMutationResult(
            aggregate_kind="RESEARCH_ASSESSMENT",
            aggregate_id=record.research_assessment_id,
            revision=record.revision,
            assessment_status=record.assessment_status,
            evaluation_count=record.evaluation_count,
            evidence_count=record.evidence_count,
            receipt_id=receipt_id,
            result_hash=result_hash,
            replayed=replayed,
        )


__all__ = ["AssessmentCommands", "AssessmentMutationResult"]
