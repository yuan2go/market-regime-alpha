"""Immutable Decision Run query contract used by replay and exact command retry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from market_regime_alpha.decision_support.domain import DecisionRunAuthority


@dataclass(frozen=True, slots=True)
class DecisionRunSnapshot:
    authority: DecisionRunAuthority
    receipt_id: UUID
    result_hash: str


class DecisionRunQueryProvider(Protocol):
    def load(self, decision_run_id: UUID) -> DecisionRunSnapshot: ...

    def find_by_candidate_set(
        self,
        candidate_set_id: UUID,
    ) -> DecisionRunSnapshot | None: ...


__all__ = ["DecisionRunQueryProvider", "DecisionRunSnapshot"]
