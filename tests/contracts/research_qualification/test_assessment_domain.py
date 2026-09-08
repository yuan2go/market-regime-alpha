from __future__ import annotations

from uuid import uuid4

import pytest

from market_regime_alpha.research_qualification.domain.assessment import (
    AssessmentEvaluationSummary,
    AssessmentStatus,
    derive_assessment_status,
    validate_assessment_revision,
)
from market_regime_alpha.research_qualification.domain.evidence import EvidenceDirection
from market_regime_alpha.research_qualification.domain.research_vocabulary import EvaluationRunStatus


def _evaluation(
    *,
    status: EvaluationRunStatus = EvaluationRunStatus.COMPLETED,
    metric_count: int = 2,
    rejected_count: int = 0,
    not_estimable_count: int = 0,
) -> AssessmentEvaluationSummary:
    return AssessmentEvaluationSummary(
        evaluation_run_id=uuid4(),
        status=status,
        metric_count=metric_count,
        rejected_metric_count=rejected_count,
        not_estimable_metric_count=not_estimable_count,
    )


@pytest.mark.parametrize(
    ("evaluations", "directions", "expected"),
    [
        ((_evaluation(),), (EvidenceDirection.SUPPORT,), AssessmentStatus.SUPPORTED),
        ((_evaluation(rejected_count=1),), (EvidenceDirection.SUPPORT,), AssessmentStatus.REJECTED),
        ((_evaluation(not_estimable_count=2),), (EvidenceDirection.NEUTRAL,), AssessmentStatus.NOT_ESTIMABLE),
        ((_evaluation(),), (EvidenceDirection.SUPPORT, EvidenceDirection.COUNTER), AssessmentStatus.INCONCLUSIVE),
        ((_evaluation(status=EvaluationRunStatus.FAILED, metric_count=0),), (EvidenceDirection.NEUTRAL,), AssessmentStatus.BLOCKED),
    ],
)
def test_assessment_status_preserves_terminal_research_outcomes(
    evaluations: tuple[AssessmentEvaluationSummary, ...],
    directions: tuple[EvidenceDirection, ...],
    expected: AssessmentStatus,
) -> None:
    assert derive_assessment_status(evaluations, directions) is expected


def test_assessment_requires_non_empty_evaluation_and_evidence_rosters() -> None:
    with pytest.raises(ValueError, match="Evaluation roster"):
        derive_assessment_status((), (EvidenceDirection.SUPPORT,))
    with pytest.raises(ValueError, match="Evidence roster"):
        derive_assessment_status((_evaluation(),), ())


def test_assessment_rejects_non_terminal_evaluation() -> None:
    with pytest.raises(ValueError, match="terminal"):
        derive_assessment_status(
            (_evaluation(status=EvaluationRunStatus.OPEN),),
            (EvidenceDirection.SUPPORT,),
        )


def test_assessment_revision_is_contiguous_and_same_series() -> None:
    experiment_id = uuid4()
    prior_id = uuid4()
    validate_assessment_revision(
        assessment_code="mr1-assessment",
        experiment_id=experiment_id,
        revision=1,
        supersedes_assessment_id=None,
        predecessor=None,
    )
    validate_assessment_revision(
        assessment_code="mr1-assessment",
        experiment_id=experiment_id,
        revision=2,
        supersedes_assessment_id=prior_id,
        predecessor=(prior_id, "mr1-assessment", experiment_id, 1),
    )
    with pytest.raises(ValueError, match="contiguous"):
        validate_assessment_revision(
            assessment_code="mr1-assessment",
            experiment_id=experiment_id,
            revision=3,
            supersedes_assessment_id=prior_id,
            predecessor=(prior_id, "mr1-assessment", experiment_id, 1),
        )
