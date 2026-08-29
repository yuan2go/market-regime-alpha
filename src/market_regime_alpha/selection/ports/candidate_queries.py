"""Read-only Candidate funnel and dossier query contracts."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class CandidateFunnelRecord:
    candidate_set_id: UUID
    population_count: int
    rankable_count: int
    unrankable_count: int
    selected_count: int
    ranked_not_selected_count: int
    score_component_count: int
    population_reconciled: bool
    rankable_reconciled: bool
    component_matrix_reconciled: bool


@dataclass(frozen=True, slots=True)
class CandidateDossierComponent:
    candidate_policy_component_id: UUID
    feature_definition_id: UUID
    raw_cell_status: str
    raw_value_numeric: Decimal | None
    percentile: Decimal | None
    projected_normalized_weight: Decimal
    contribution: Decimal | None
    cell_source_lineage_hash: str


@dataclass(frozen=True, slots=True)
class CandidateDossierRecord:
    candidate_set_id: UUID
    candidate_id: UUID
    dataset_id: UUID
    instrument_id: UUID
    population_dataset_source_id: UUID
    disposition: str
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
    "CandidateFunnelRecord",
    "CandidateQueryProvider",
]
