"""Read-only Candidate funnel and dossier query contracts."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class CandidateFunnelComponentDiagnostic:
    candidate_policy_component_id: UUID
    feature_definition_id: UUID
    observed_count: int
    distinct_count: int
    raw_available_count: int
    missing_count: int
    unknown_count: int
    stale_count: int
    conflict_count: int
    available_but_not_observed_count: int
    rank_information_status: str


@dataclass(frozen=True, slots=True)
class CandidateFunnelRecord:
    candidate_set_id: UUID
    candidate_policy_id: UUID
    dataset_id: UUID
    dataset_population_count: int
    population_count: int
    rankable_count: int
    unrankable_count: int
    selected_count: int
    ranked_not_selected_count: int
    score_component_count: int
    ranking_status: str
    composite_distinct_count: int
    requested_top_k: int
    boundary_score: Decimal | None
    boundary_rank: int | None
    strictly_above_boundary_count: int
    boundary_group_count: int
    selected_overflow_count: int
    boundary_has_tie: bool
    boundary_tie_expanded: bool
    actual_population_count: int
    actual_selected_count: int
    actual_ranked_not_selected_count: int
    actual_unrankable_count: int
    strict_complete_case_unrankable_count: int
    actual_score_component_count: int
    population_reconciled: bool
    rankable_reconciled: bool
    component_matrix_reconciled: bool
    ranking_reconciled: bool
    component_diagnostics: tuple[CandidateFunnelComponentDiagnostic, ...]


@dataclass(frozen=True, slots=True)
class CandidateDossierComponent:
    candidate_policy_component_id: UUID
    feature_definition_id: UUID
    feature_content_sha256: str
    feature_value_type: str
    dataset_feature_source_id: UUID
    direction: str
    declared_weight: Decimal
    raw_cell_status: str
    raw_decimal_value: Decimal | None
    raw_integer_value: int | None
    raw_reason_code: str
    percentile: Decimal | None
    projected_normalized_weight: Decimal
    contribution: Decimal | None
    cell_source_lineage_hash: str
    observed_count: int
    distinct_count: int
    missing_count: int
    unknown_count: int
    stale_count: int
    conflict_count: int
    raw_available_count: int
    available_but_not_observed_count: int
    rank_information_status: str


@dataclass(frozen=True, slots=True)
class CandidateDossierRecord:
    candidate_set_id: UUID
    candidate_id: UUID
    candidate_policy_id: UUID
    dataset_id: UUID
    dataset_content_sha256: str
    dataset_manifest_artifact_id: UUID
    dataset_manifest_content_sha256: str
    dataset_manifest_size_bytes: int
    instrument_id: UUID
    population_dataset_source_id: UUID
    population_universe_member_id: UUID
    population_eligibility_assessment_id: UUID
    disposition: str
    reason_code: str
    composite_score: Decimal | None
    competition_rank: int | None
    components: tuple[CandidateDossierComponent, ...]


class CandidateQueryProvider(Protocol):
    def funnel(self, candidate_set_id: UUID) -> CandidateFunnelRecord: ...

    def dossier(
        self,
        *,
        candidate_set_id: UUID,
        instrument_id: UUID,
    ) -> CandidateDossierRecord: ...


__all__ = [
    "CandidateDossierComponent",
    "CandidateDossierRecord",
    "CandidateFunnelComponentDiagnostic",
    "CandidateFunnelRecord",
    "CandidateQueryProvider",
]
