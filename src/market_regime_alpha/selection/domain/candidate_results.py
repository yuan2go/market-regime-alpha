"""Immutable Candidate ranking write plan and explanatory results."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from market_regime_alpha.selection.domain.candidate_inputs import CandidateCellStatus
from market_regime_alpha.selection.domain.candidate_policy import (
    CandidateFeatureValueType,
    CandidatePolicy,
)
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.identity import ContentHash
from market_regime_alpha.shared.time import DecisionTime


class CandidateDisposition(StrEnum):
    SELECTED = "SELECTED"
    RANKED_NOT_SELECTED = "RANKED_NOT_SELECTED"
    UNRANKABLE = "UNRANKABLE"


class CandidateRankingStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    CONSTANT = "CONSTANT"
    NOT_ESTIMABLE = "NOT_ESTIMABLE"


@dataclass(frozen=True, slots=True)
class CandidateSetResult:
    candidate_set_id: UUID
    candidate_policy_id: UUID
    candidate_policy_content_sha256: ContentHash
    dataset_id: UUID
    dataset_content_sha256: ContentHash
    universe_revision_id: UUID
    eligibility_policy_id: UUID
    decision_time: DecisionTime
    decimal_projection_precision: int
    requested_top_k: int
    component_count: int
    population_count: int
    rankable_count: int
    unrankable_count: int
    selected_count: int
    ranked_not_selected_count: int
    score_component_count: int
    available_component_count: int
    constant_component_count: int
    not_estimable_component_count: int
    ranking_status: CandidateRankingStatus
    composite_distinct_count: int
    boundary_score: Decimal | None
    boundary_rank: int | None
    strictly_above_boundary_count: int
    boundary_group_count: int
    selected_overflow_count: int
    boundary_has_tie: bool
    boundary_tie_expanded: bool
    dependency_sha256: ContentHash
    content_sha256: ContentHash

    @property
    def boundary_contains_tie(self) -> bool:
        return self.boundary_has_tie

    @property
    def result_sha256(self) -> ContentHash:
        return self.content_sha256


@dataclass(frozen=True, slots=True)
class CandidateRecord:
    candidate_id: UUID
    candidate_set_id: UUID
    candidate_policy_id: UUID
    dataset_id: UUID
    instrument_id: UUID
    dataset_population_source_id: UUID
    dataset_source_role: str
    disposition: CandidateDisposition
    composite_score: Decimal | None
    competition_rank: int | None
    reason_code: str

    @property
    def population_source_id(self) -> UUID:
        return self.dataset_population_source_id

    @property
    def disposition_reason(self) -> str:
        return self.reason_code


@dataclass(frozen=True, slots=True)
class CandidateScoreComponentRecord:
    candidate_score_component_id: UUID
    candidate_id: UUID
    candidate_set_id: UUID
    candidate_policy_id: UUID
    candidate_policy_component_id: UUID
    feature_definition_id: UUID
    feature_content_sha256: ContentHash
    feature_value_type: CandidateFeatureValueType
    dataset_id: UUID
    instrument_id: UUID
    raw_status: CandidateCellStatus
    raw_decimal_value: Decimal | None
    raw_integer_value: int | None
    raw_reason_code: str
    cell_source_lineage_hash: ContentHash
    normalized_weight: Decimal
    percentile: Decimal | None
    contribution: Decimal | None
    candidate_disposition: CandidateDisposition

    @property
    def disposition(self) -> CandidateDisposition:
        return self.candidate_disposition


@dataclass(frozen=True, slots=True)
class CandidateComponentDiagnostic:
    candidate_policy_component_id: UUID
    feature_definition_id: UUID
    observed_count: int
    distinct_count: int
    raw_available_count: int
    available_but_not_observed_count: int
    missing_count: int
    unknown_count: int
    stale_count: int
    conflict_count: int
    rank_information_status: CandidateRankingStatus

    @property
    def ranking_status(self) -> CandidateRankingStatus:
        return self.rank_information_status


@dataclass(frozen=True, slots=True)
class CandidateRankingPlan:
    candidate_set: CandidateSetResult
    candidates: tuple[CandidateRecord, ...]
    score_components: tuple[CandidateScoreComponentRecord, ...]
    component_diagnostics: tuple[CandidateComponentDiagnostic, ...]

    @property
    def candidate_set_id(self) -> UUID:
        return self.candidate_set.candidate_set_id

    @property
    def result_sha256(self) -> ContentHash:
        return self.candidate_set.content_sha256


CandidateBuildResult = CandidateRankingPlan


def candidate_result_content_sha256(
    *,
    policy: CandidatePolicy,
    candidate_set_id: UUID,
    dataset_id: UUID,
    dataset_content_sha256: ContentHash,
    dependency_sha256: ContentHash,
    projection_precision: int,
    candidates: Sequence[CandidateRecord],
    score_components: Sequence[CandidateScoreComponentRecord],
    component_diagnostics: Sequence[CandidateComponentDiagnostic],
) -> ContentHash:
    """Hash persisted Candidate results without recomputing ranking semantics."""

    return ContentHash(
        canonical_json_sha256(
            {
                "algorithm": {
                    "missing_policy": policy.missing_policy,
                    "normalization_method": policy.normalization_method,
                    "decimal_projection_method": (
                        policy.decimal_projection_method
                    ),
                    "decimal_projection_version": (
                        policy.decimal_projection_version
                    ),
                    "rank_method": policy.rank_method,
                    "selection_method": policy.selection_method,
                    "tie_policy": policy.tie_policy,
                },
                "candidate_set_id": candidate_set_id,
                "candidates": list(candidates),
                "component_diagnostics": list(component_diagnostics),
                "dataset_content_sha256": dataset_content_sha256,
                "dataset_id": dataset_id,
                "dependency_sha256": dependency_sha256,
                "policy_content_sha256": policy.content_sha256,
                "policy_id": policy.candidate_policy_id,
                "projection_precision": projection_precision,
                "score_components": list(score_components),
            }
        )
    )


__all__ = [
    "CandidateBuildResult",
    "CandidateComponentDiagnostic",
    "CandidateDisposition",
    "CandidateRankingPlan",
    "CandidateRankingStatus",
    "CandidateRecord",
    "CandidateScoreComponentRecord",
    "CandidateSetResult",
    "candidate_result_content_sha256",
]
