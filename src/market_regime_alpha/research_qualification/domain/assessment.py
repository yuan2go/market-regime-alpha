"""Complete Experiment-bound Research Assessment semantics."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
import re
from uuid import UUID

from market_regime_alpha.research_qualification.domain.evidence import EvidenceDirection
from market_regime_alpha.research_qualification.domain.model import ArtifactBinding
from market_regime_alpha.research_qualification.domain.research_vocabulary import EvaluationRunStatus
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.identity import ContentHash


_CODE = re.compile(r"^[a-z][a-z0-9_-]{0,99}$")


class AssessmentStatus(StrEnum):
    SUPPORTED = "SUPPORTED"
    REJECTED = "REJECTED"
    NOT_ESTIMABLE = "NOT_ESTIMABLE"
    INCONCLUSIVE = "INCONCLUSIVE"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class ResearchAssessmentPlan:
    research_assessment_id: UUID
    assessment_code: str
    revision: int
    supersedes_assessment_id: UUID | None
    experiment_id: UUID
    knowledge_cutoff: datetime
    code_artifact: ArtifactBinding
    config_artifact: ArtifactBinding
    provenance_sha256: ContentHash | str
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        if not _CODE.fullmatch(self.assessment_code):
            raise ValueError("assessment_code has an invalid format")
        if self.knowledge_cutoff.tzinfo is None or self.knowledge_cutoff.utcoffset() is None:
            raise ValueError("knowledge_cutoff must be timezone-aware")
        if isinstance(self.revision, bool) or self.revision < 1:
            raise ValueError("Assessment revision must be positive")
        if (self.revision == 1) != (self.supersedes_assessment_id is None):
            raise ValueError("Assessment supersession shape is invalid")
        provenance_hash = ContentHash(str(self.provenance_sha256))
        object.__setattr__(self, "provenance_sha256", provenance_hash)
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(
                canonical_json_sha256(
                    {
                        "assessment_code": self.assessment_code,
                        "code_artifact": self.code_artifact,
                        "config_artifact": self.config_artifact,
                        "experiment_id": self.experiment_id,
                        "knowledge_cutoff": self.knowledge_cutoff,
                        "provenance_sha256": provenance_hash,
                        "revision": self.revision,
                        "supersedes_assessment_id": self.supersedes_assessment_id,
                    }
                )
            ),
        )


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
    "ResearchAssessmentPlan",
    "derive_assessment_status",
    "validate_assessment_revision",
]
