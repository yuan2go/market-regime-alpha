"""Complete Experiment-bound Research Assessment semantics."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from market_regime_alpha.research_qualification.domain.evidence import EvidenceDirection
from market_regime_alpha.research_qualification.domain.research_vocabulary import EvaluationRunStatus


class AssessmentStatus(StrEnum):
    SUPPORTED = "SUPPORTED"
    REJECTED = "REJECTED"
    NOT_ESTIMABLE = "NOT_ESTIMABLE"
    INCONCLUSIVE = "INCONCLUSIVE"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class AssessmentEvaluationSummary:
    evaluation_run_id: UUID
    status: EvaluationRunStatus
    metric_count: int
    rejected_metric_count: int
    not_estimable_metric_count: int

    def __post_init__(self) -> None:
        for name, value in (
            ("metric_count", self.metric_count),
            ("rejected_metric_count", self.rejected_metric_count),
            ("not_estimable_metric_count", self.not_estimable_metric_count),
        ):
            if isinstance(value, bool) or value < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.rejected_metric_count + self.not_estimable_metric_count > self.metric_count:
            raise ValueError("Evaluation metric summary exceeds metric_count")
        if self.status is EvaluationRunStatus.COMPLETED and self.metric_count < 1:
            raise ValueError("completed Evaluation requires metrics")


def derive_assessment_status(
    evaluations: tuple[AssessmentEvaluationSummary, ...],
    evidence_directions: tuple[EvidenceDirection, ...],
) -> AssessmentStatus:
    if not evaluations:
        raise ValueError("Assessment Evaluation roster must be non-empty")
    if not evidence_directions:
        raise ValueError("Assessment Evidence roster must be non-empty")
    terminal = {EvaluationRunStatus.COMPLETED, EvaluationRunStatus.FAILED}
    if any(item.status not in terminal for item in evaluations):
        raise ValueError("Assessment requires terminal Evaluation Runs")
    if any(item.status is EvaluationRunStatus.FAILED for item in evaluations):
        return AssessmentStatus.BLOCKED
    if any(item.rejected_metric_count > 0 for item in evaluations):
        return AssessmentStatus.REJECTED
    metric_count = sum(item.metric_count for item in evaluations)
    not_estimable_count = sum(item.not_estimable_metric_count for item in evaluations)
    if metric_count > 0 and not_estimable_count == metric_count:
        return AssessmentStatus.NOT_ESTIMABLE
    if EvidenceDirection.COUNTER in evidence_directions:
        return AssessmentStatus.INCONCLUSIVE
    if not_estimable_count > 0:
        return AssessmentStatus.INCONCLUSIVE
    if EvidenceDirection.SUPPORT not in evidence_directions:
        return AssessmentStatus.INCONCLUSIVE
    return AssessmentStatus.SUPPORTED


def validate_assessment_revision(
    *,
    assessment_code: str,
    experiment_id: UUID,
    revision: int,
    supersedes_assessment_id: UUID | None,
    predecessor: tuple[UUID, str, UUID, int] | None,
) -> None:
    if isinstance(revision, bool) or revision < 1:
        raise ValueError("Assessment revision must be positive")
    if revision == 1:
        if supersedes_assessment_id is not None or predecessor is not None:
            raise ValueError("Assessment revision one cannot supersede")
        return
    if supersedes_assessment_id is None or predecessor is None:
        raise ValueError("Assessment revision requires a predecessor")
    prior_id, prior_code, prior_experiment_id, prior_revision = predecessor
    if prior_id != supersedes_assessment_id:
        raise ValueError("Assessment predecessor identity does not match")
    if prior_code != assessment_code or prior_experiment_id != experiment_id:
        raise ValueError("Assessment predecessor belongs to another series")
    if prior_revision + 1 != revision:
        raise ValueError("Assessment revisions must be contiguous")


__all__ = [
    "AssessmentEvaluationSummary",
    "AssessmentStatus",
    "derive_assessment_status",
    "validate_assessment_revision",
]
