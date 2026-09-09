"""Retained account child order and exact upstream-reference serialization."""
from __future__ import annotations


from dataclasses import replace






from market_regime_alpha.application.continuous_research.journal import (
    ContinuousChildKind,
)


from market_regime_alpha.application.continuous_research.ports import (
    ChildExecutionRequest,
    ChildExecutionResult,
)


from market_regime_alpha.application.continuous_research.journal import (
    RuntimeArtifactReference,
)






CONTINUOUS_CHILD_ORDER = (
    ContinuousChildKind.DAILY_DATASET,
    ContinuousChildKind.FEATURE_MATERIALIZATION,
    ContinuousChildKind.STATE_SYSTEM,
    ContinuousChildKind.CONTROLLED_OPERATION,
    ContinuousChildKind.CANONICAL_LIFECYCLE,
    ContinuousChildKind.DECISION_SYSTEM,
    ContinuousChildKind.STRATEGY_RUNTIME,
    ContinuousChildKind.DAILY_ALPHA_SNAPSHOT,
)


def _with_upstream_result(
    request: ChildExecutionRequest,
    result: ChildExecutionResult,
) -> ChildExecutionRequest:
    references = [
        RuntimeArtifactReference(
            reference_kind=f"{result.child_kind.value}_OUTPUT",
            artifact_id=(
                result.child_receipt_id
                if result.child_kind is ContinuousChildKind.STATE_SYSTEM or result.child_artifact_id is None
                else result.child_artifact_id
            ),
            content_hash=(
                result.child_receipt_hash
                if result.child_kind is ContinuousChildKind.STATE_SYSTEM or result.child_artifact_hash is None
                else result.child_artifact_hash
            ),
        )
    ]
    if (
        result.child_kind is ContinuousChildKind.STATE_SYSTEM
        and result.child_artifact_id is not None
        and result.child_artifact_hash is not None
    ):
        references.append(
            RuntimeArtifactReference(
                reference_kind="STATE_SYSTEM_PIPELINE_ARTIFACT",
                artifact_id=result.child_artifact_id,
                content_hash=result.child_artifact_hash,
            )
        )
    return replace(
        request,
        input_references=tuple(
            sorted(
                {*request.input_references, *references},
                key=lambda item: (
                    item.reference_kind,
                    str(item.artifact_id),
                    item.content_hash,
                ),
            )
        ),
    )


