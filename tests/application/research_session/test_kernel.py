from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from market_regime_alpha.application.research_session.kernel import (
    ResearchDecisionSessionKernel,
    ResearchSessionStage,
    SessionStageComputation,
    SessionStageStatus,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash
from tests.application.research_session.test_contracts import DECISION_TIME, _request


HASH = canonical_hash({"kernel": "test"})


class DeterministicOwner:
    def compute_stage(
        self,
        *,
        request,
        stage: ResearchSessionStage,
        input_references: tuple[ValidationArtifactReference, ...],
    ) -> SessionStageComputation:
        del request
        completed_at = DECISION_TIME + timedelta(seconds=stage.ordinal)
        return SessionStageComputation(
            status=SessionStageStatus.COMPLETE,
            output_references=(
                ValidationArtifactReference(
                    f"{stage.value}_OUTPUT",
                    ArtifactId(f"output-{stage.value.lower()}"),
                    HASH,
                ),
            ),
            input_references=input_references,
            completed_at=completed_at,
            reason_codes=(f"{stage.value}_COMPLETE",),
        )


def test_kernel_executes_exact_stage_order_with_deterministic_lineage() -> None:
    kernel = ResearchDecisionSessionKernel(DeterministicOwner())
    request = _request()

    first = kernel.run(request=request)
    second = kernel.run(request=request)

    assert first == second
    assert tuple(item.stage for item in first) == tuple(ResearchSessionStage)
    assert first[1].predecessor_receipt_ids == (first[0].receipt_id,)
    assert first[-1].predecessor_receipt_ids == tuple(
        item.receipt_id for item in first[:-1]
    )
    assert first[-1].entry_authority_granted is False


def test_kernel_resumes_from_verified_prefix_without_recomputing_prefix() -> None:
    kernel = ResearchDecisionSessionKernel(DeterministicOwner())
    request = _request()
    complete = kernel.run(request=request)

    resumed = kernel.run(request=request, completed_prefix=complete[:3])

    assert resumed == complete


def test_kernel_rejects_out_of_order_or_substituted_prefix() -> None:
    kernel = ResearchDecisionSessionKernel(DeterministicOwner())
    request = _request()
    complete = kernel.run(request=request)

    with pytest.raises(ValueError, match="contiguous stage prefix"):
        kernel.run(request=request, completed_prefix=(complete[1],))
    other = _request().create(
        **{
            **_request().semantic_values(),
            "materialized_at": datetime(2026, 8, 10, 6, 56, tzinfo=UTC),
        }
    )
    with pytest.raises(ValueError, match="different decision session"):
        kernel.run(request=other, completed_prefix=complete[:1])


def test_blocked_stage_stops_downstream_without_empty_success() -> None:
    class BlockedOwner(DeterministicOwner):
        def compute_stage(self, *, request, stage, input_references):
            if stage is ResearchSessionStage.DECISION:
                return SessionStageComputation(
                    status=SessionStageStatus.BLOCKED,
                    output_references=(),
                    input_references=input_references,
                    completed_at=DECISION_TIME,
                    reason_codes=("DECISION_FACT_MISSING",),
                )
            return super().compute_stage(
                request=request,
                stage=stage,
                input_references=input_references,
            )

    receipts = ResearchDecisionSessionKernel(BlockedOwner()).run(request=_request())

    assert tuple(item.stage for item in receipts) == (
        ResearchSessionStage.SCOPE,
        ResearchSessionStage.DECISION,
    )
    assert receipts[-1].status is SessionStageStatus.BLOCKED
    assert receipts[-1].reason_codes == ("DECISION_FACT_MISSING",)
