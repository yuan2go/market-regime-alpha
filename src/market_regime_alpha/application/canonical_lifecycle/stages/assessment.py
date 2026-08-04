"""Fail-closed health, holding, exit, and outcome lifecycle adapters."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from market_regime_alpha.application.canonical_lifecycle.contracts import (
    LifecycleObjectId,
    LifecycleObjectReference,
    LifecycleObjectType,
    LifecycleReaderKind,
)
from market_regime_alpha.application.canonical_lifecycle.stages.contracts import (
    LifecycleStageContext,
    StageExecutionResult,
    StageMutationKind,
)
from market_regime_alpha.application.canonical_lifecycle.stages.evidence import (
    ordered_references,
    references_for_type,
    require_single_reference,
)
from market_regime_alpha.application.canonical_lifecycle.states import (
    LifecycleRunStatus,
    LifecycleStageName,
    LifecycleStageStatus,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.position.thesis_health import ThesisHealthRepository


class ThesisHealthStageHandler:
    """Load the command-bound H5 authority as it existed at decision as-of."""

    stage_name = LifecycleStageName.THESIS_HEALTH
    mutation_kind = StageMutationKind.READ_ONLY

    def __init__(self, *, repository: ThesisHealthRepository) -> None:
        self._repository = repository

    def recover(self, context: LifecycleStageContext) -> StageExecutionResult | None:
        return self.execute(context)

    def execute(self, context: LifecycleStageContext) -> StageExecutionResult:
        position_reference = require_single_reference(
            context, LifecycleObjectType.POSITION_SNAPSHOT
        )
        risk_reference = require_single_reference(
            context, LifecycleObjectType.RISK_REDUCING_DECISION
        )
        initial_health = require_single_reference(
            context, LifecycleObjectType.THESIS_HEALTH_OBSERVATION
        )
        confirmation = references_for_type(
            context, LifecycleObjectType.RISK_REDUCTION_CONFIRMATION
        )
        if len(confirmation) != 1:
            raise ValueError("Thesis health requires one H4.5 confirmation")
        verified = self._repository.get_verified_thesis_health_bundle(
            ArtifactId(str(initial_health.object_id))
        )
        _verify_reference(
            initial_health,
            object_id=verified.observation.observation_id,
            payload=verified.observation.to_canonical_dict(),
        )
        if verified.observation.assessed_at > context.run.as_of_time:
            raise ValueError("Thesis health was unavailable at lifecycle as-of")
        as_of_reason = "LATEST_DURABLE_THESIS_HEALTH_VERIFIED"
        if not verified.is_latest:
            latest = self._repository.get_latest_observation(
                verified.observation.thesis_id
            )
            if latest is None:
                raise ValueError("Thesis health chain lost its latest authority")
            if latest.assessed_at <= context.run.as_of_time:
                return _block_for_assessment_authority(
                    inputs=(position_reference, risk_reference, initial_health),
                    reason_code="COMMAND_BOUND_THESIS_HEALTH_SUPERSEDED_AT_AS_OF",
                    blocker=(
                        "A newer Thesis health authority existed by lifecycle as-of "
                        "but was not command-bound"
                    ),
                )
            as_of_reason = "COMMAND_BOUND_AS_OF_THESIS_HEALTH_VERIFIED"
        output = _repository_reference(
            object_type=LifecycleObjectType.THESIS_HEALTH_OBSERVATION,
            object_id=verified.observation.observation_id,
            payload=verified.observation.to_canonical_dict(),
            reader_kind=LifecycleReaderKind.THESIS_HEALTH_REPOSITORY,
            available_at=verified.observation.assessed_at,
        )
        return StageExecutionResult(
            stage_status=LifecycleStageStatus.COMPLETED,
            run_status=LifecycleRunStatus.READY_FOR_HOLDING_ASSESSMENT,
            input_references=ordered_references(
                (position_reference, risk_reference, initial_health)
            ),
            output_references=(output,),
            model_versions=(),
            configuration_hashes=(
                verified.input_bundle.configuration.configuration_hash,
            ),
            reason_codes=(as_of_reason, "READY_FOR_HOLDING_ASSESSMENT"),
            blocker_reason=None,
        )


class HoldingAssessmentStageHandler:
    """Fail closed until a durable H7 HoldingAssessment Reader is implemented."""

    stage_name = LifecycleStageName.HOLDING_ASSESSMENT
    mutation_kind = StageMutationKind.READ_ONLY

    def recover(self, context: LifecycleStageContext) -> StageExecutionResult | None:
        return self.execute(context)

    def execute(self, context: LifecycleStageContext) -> StageExecutionResult:
        return _block_for_assessment_authority(
            inputs=ordered_references(
                (
                    *references_for_type(
                        context, LifecycleObjectType.POSITION_SNAPSHOT
                    ),
                    *references_for_type(
                        context, LifecycleObjectType.THESIS_HEALTH_OBSERVATION
                    ),
                )
            ),
            reason_code="DURABLE_HOLDING_ASSESSMENT_READER_NOT_IMPLEMENTED",
            blocker=(
                "Holding assessment requires durable H7 inputs and a controlled "
                "Reader; no assessment was synthesized"
            ),
        )


class ExitAssessmentStageHandler:
    """Fail closed until a durable H7 ExitAssessment Reader is implemented."""

    stage_name = LifecycleStageName.EXIT_ASSESSMENT
    mutation_kind = StageMutationKind.READ_ONLY

    def recover(self, context: LifecycleStageContext) -> StageExecutionResult | None:
        return self.execute(context)

    def execute(self, context: LifecycleStageContext) -> StageExecutionResult:
        return _block_for_assessment_authority(
            inputs=references_for_type(
                context, LifecycleObjectType.HOLDING_ASSESSMENT
            ),
            reason_code="DURABLE_EXIT_ASSESSMENT_READER_NOT_IMPLEMENTED",
            blocker=(
                "Exit assessment requires durable H7 inputs and a controlled "
                "Reader; no assessment was synthesized"
            ),
        )


class OutcomeReviewStageHandler:
    """Fail closed until a durable outcome/review authority is available."""

    stage_name = LifecycleStageName.OUTCOME_REVIEW
    mutation_kind = StageMutationKind.READ_ONLY

    def recover(self, context: LifecycleStageContext) -> StageExecutionResult | None:
        return self.execute(context)

    def execute(self, context: LifecycleStageContext) -> StageExecutionResult:
        return _block_for_assessment_authority(
            inputs=references_for_type(context, LifecycleObjectType.EXIT_ASSESSMENT),
            reason_code="DURABLE_OUTCOME_REVIEW_READER_NOT_IMPLEMENTED",
            blocker=(
                "Outcome review requires a complete Fill-derived trade and a "
                "durable Review Reader; no outcome was synthesized"
            ),
        )


def _block_for_assessment_authority(
    *,
    inputs: tuple[LifecycleObjectReference, ...],
    reason_code: str,
    blocker: str,
) -> StageExecutionResult:
    return StageExecutionResult(
        stage_status=LifecycleStageStatus.BLOCKED,
        run_status=LifecycleRunStatus.BLOCKED_BY_MODEL_VALIDATION,
        input_references=ordered_references(inputs),
        output_references=(),
        model_versions=(),
        configuration_hashes=(),
        reason_codes=(reason_code,),
        blocker_reason=blocker,
    )


def _verify_reference(
    reference: LifecycleObjectReference,
    *,
    object_id: ArtifactId,
    payload: Mapping[str, Any],
) -> None:
    if (
        str(reference.object_id) != str(object_id)
        or reference.content_hash != canonical_hash(payload)
    ):
        raise ValueError(f"{reference.object_type.value} reference mismatch")


def _repository_reference(
    *,
    object_type: LifecycleObjectType,
    object_id: ArtifactId,
    payload: Mapping[str, Any],
    reader_kind: LifecycleReaderKind,
    available_at: datetime,
) -> LifecycleObjectReference:
    canonical_available_at = available_at.astimezone(timezone.utc)
    if canonical_available_at.microsecond:
        raise ValueError("repository output available_at must have second precision")
    return LifecycleObjectReference(
        object_type=object_type,
        object_id=LifecycleObjectId(str(object_id)),
        content_hash=canonical_hash(payload),
        reader_kind=reader_kind,
        locator=None,
        available_at=canonical_available_at,
    )
