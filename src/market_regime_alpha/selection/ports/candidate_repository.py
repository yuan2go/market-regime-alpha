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
class CandidateSetBinding:
    candidate_set_id: UUID
    candidate_policy_id: UUID
    candidate_policy_content_sha256: str
    dataset_id: UUID
    dataset_content_sha256: str
    dependency_sha256: str
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

    def lock_candidate_set_identity(self, candidate_set_id: UUID) -> None: ...

    def insert_candidate_set(self, plan: CandidateRankingPlan) -> None: ...

    def candidate_set_binding(
        self,
        *,
        candidate_policy_id: UUID,
        dataset_id: UUID,
        lock: bool,
    ) -> CandidateSetBinding | None: ...

    def persisted_candidate_set(
        self,
        *,
        candidate_policy_id: UUID,
        dataset_id: UUID,
        lock: bool,
    ) -> CandidateRankingPlan | None: ...

    def reconciliation(
        self,
        candidate_set_id: UUID,
    ) -> CandidatePersistenceReconciliation: ...


__all__ = [
    "CandidatePersistenceReconciliation",
    "CandidateRepository",
    "CandidateSetBinding",
]
