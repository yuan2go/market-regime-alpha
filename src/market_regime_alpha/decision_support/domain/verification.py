"""Typed, read-only Decision Run replay and reconciliation results."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from market_regime_alpha.decision_support.domain.vocabulary import (
    DecisionRunMismatchKind,
)


@dataclass(frozen=True, slots=True)
class DecisionRunMismatch:
    kind: DecisionRunMismatchKind
    fact_path: str
    expected: str
    actual: str


@dataclass(frozen=True, slots=True)
class DecisionRunVerification:
    decision_run_id: UUID
    mismatches: tuple[DecisionRunMismatch, ...]

    @property
    def matched(self) -> bool:
        return not self.mismatches

    @property
    def mismatch_count(self) -> int:
        return len(self.mismatches)


__all__ = ["DecisionRunMismatch", "DecisionRunVerification"]
