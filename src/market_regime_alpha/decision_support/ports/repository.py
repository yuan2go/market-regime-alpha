"""Decision Run persistence and relational reconciliation ports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from market_regime_alpha.decision_support.domain import (
    DecisionRunAuthority,
    ExploratoryRetrospectiveDecisionScope,
)


@dataclass(frozen=True, slots=True)
class DecisionRunReconciliation:
    decision_run_id: UUID
    actual_target_count: int
    actual_commitment_count: int
    actual_reference_count: int
    actual_research_qualification_count: int
    missing_commitment_count: int
    extra_commitment_count: int
    candidate_roster_sha256: str
    target_roster_sha256: str
    commitment_roster_sha256: str
    research_qualification_roster_sha256: str
    matched: bool


class DecisionRunRepository(Protocol):
    def lock_candidate_set_identity(self, candidate_set_id: UUID) -> None: ...

    def authoritative_recorded_at(self) -> datetime: ...

    def insert(self, authority: DecisionRunAuthority) -> None: ...

    def bind_exploratory_retrospective(
        self,
        authority: DecisionRunAuthority,
        scope: ExploratoryRetrospectiveDecisionScope,
    ) -> str: ...

    def reconcile(
        self,
        decision_run_id: UUID,
        *,
        lock: bool,
    ) -> DecisionRunReconciliation: ...


__all__ = ["DecisionRunReconciliation", "DecisionRunRepository"]
