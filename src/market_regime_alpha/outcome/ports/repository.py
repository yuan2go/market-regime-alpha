"""Append-only Outcome persistence and reconciliation contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from market_regime_alpha.outcome.domain import (
    MarketTargetOutcomeAuthority,
    OutcomeRevisionAuthority,
)


@dataclass(frozen=True, slots=True)
class OutcomeHead:
    market_target_outcome_id: UUID
    market_target_outcome_revision_id: UUID
    revision_ordinal: int


@dataclass(frozen=True, slots=True)
class OutcomeReconciliation:
    market_target_outcome_revision_id: UUID
    source_count: int
    observation_count: int
    metric_count: int
    reference_dependency_count: int
    observation_dependency_count: int
    reason_count: int
    source_roster_sha256: str
    observation_roster_sha256: str
    metric_roster_sha256: str
    reference_dependency_roster_sha256: str
    observation_dependency_roster_sha256: str
    reason_roster_sha256: str
    definition_summary_sha256: str
    matched: bool

    @classmethod
    def from_revision(
        cls,
        revision: OutcomeRevisionAuthority,
        *,
        matched: bool,
    ) -> OutcomeReconciliation:
        return cls(
            market_target_outcome_revision_id=(
                revision.market_target_outcome_revision_id
            ),
            source_count=revision.source_count,
            observation_count=revision.observation_count,
            metric_count=revision.metric_count,
            reference_dependency_count=revision.reference_dependency_count,
            observation_dependency_count=revision.observation_dependency_count,
            reason_count=revision.reason_count,
            source_roster_sha256=revision.source_roster_sha256,
            observation_roster_sha256=revision.observation_roster_sha256,
            metric_roster_sha256=revision.metric_roster_sha256,
            reference_dependency_roster_sha256=(
                revision.reference_dependency_roster_sha256
            ),
            observation_dependency_roster_sha256=(
                revision.observation_dependency_roster_sha256
            ),
            reason_roster_sha256=revision.reason_roster_sha256,
            definition_summary_sha256=revision.definition_summary_sha256,
            matched=matched,
        )


class OutcomeRepository(Protocol):
    def lock_scope_and_head(self, commitment_id: UUID) -> OutcomeHead | None: ...

    def authoritative_settled_at(self) -> datetime: ...

    def insert(
        self,
        authority: MarketTargetOutcomeAuthority,
        *,
        create_root: bool,
    ) -> None: ...

    def reconcile(
        self,
        revision_id: UUID,
        *,
        lock: bool,
    ) -> OutcomeReconciliation: ...


__all__ = ["OutcomeHead", "OutcomeReconciliation", "OutcomeRepository"]
