"""Typed read-only Outcome replay and reconciliation results."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from market_regime_alpha.outcome.domain.vocabulary import OutcomeMismatchKind


@dataclass(frozen=True, slots=True)
class OutcomeMismatch:
    kind: OutcomeMismatchKind
    path: str
    expected: str
    actual: str


@dataclass(frozen=True, slots=True)
class OutcomeVerificationReport:
    market_target_outcome_id: UUID | None
    market_target_outcome_revision_id: UUID
    matched: bool
    mismatch_count: int
    mismatches: tuple[OutcomeMismatch, ...]

    @classmethod
    def create(
        cls,
        *,
        market_target_outcome_id: UUID | None,
        revision_id: UUID,
        mismatches: tuple[OutcomeMismatch, ...],
    ) -> OutcomeVerificationReport:
        return cls(
            market_target_outcome_id=market_target_outcome_id,
            market_target_outcome_revision_id=revision_id,
            matched=not mismatches,
            mismatch_count=len(mismatches),
            mismatches=mismatches,
        )


__all__ = ["OutcomeMismatch", "OutcomeVerificationReport"]
