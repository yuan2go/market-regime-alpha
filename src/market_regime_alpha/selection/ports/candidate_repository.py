"""Persistence port for Selection-owned Candidate Authority."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol
from uuid import UUID

if TYPE_CHECKING:
    from market_regime_alpha.selection.domain.candidate_policy import CandidatePolicy
    from market_regime_alpha.selection.domain.candidate_results import (
        CandidateRankingPlan,
    )


@dataclass(frozen=True, slots=True)
class CandidateSetRecord:
    candidate_set_id: UUID
    candidate_policy_id: UUID
    dataset_id: UUID
    result_sha256: str


@dataclass(frozen=True, slots=True)
class CandidatePersistenceReconciliation:
    population_count: int
    selected_count: int
    ranked_not_selected_count: int
    unrankable_count: int
    score_component_count: int
    population_reconciled: bool
    rankable_reconciled: bool
    component_matrix_reconciled: bool
    ranking_reconciled: bool


class CandidateRepository(Protocol):
    def insert_policy(self, policy: CandidatePolicy) -> None: ...

    def policy(self, candidate_policy_id: UUID, *, lock: bool) -> CandidatePolicy: ...

    def insert_candidate_set(self, plan: CandidateRankingPlan) -> None: ...

    def find_candidate_set(
        self,
        *,
        candidate_policy_id: UUID,
        dataset_id: UUID,
        lock: bool,
    ) -> CandidateSetRecord | None: ...

    def reconciliation(
        self,
        candidate_set_id: UUID,
    ) -> CandidatePersistenceReconciliation: ...


__all__ = [
    "CandidatePersistenceReconciliation",
    "CandidateRepository",
    "CandidateSetRecord",
]
