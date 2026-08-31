"""Permanent typed read-only Outcome snapshot port."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from market_regime_alpha.outcome.domain import MarketTargetOutcomeAuthority


@dataclass(frozen=True, slots=True)
class OutcomeSnapshot:
    authority: MarketTargetOutcomeAuthority
    receipt_id: UUID
    result_hash: str


class OutcomeReadPort(Protocol):
    def load(self, revision_id: UUID) -> OutcomeSnapshot: ...

    def find_by_request(
        self,
        commitment_id: UUID,
        request_identity: str,
    ) -> OutcomeSnapshot | None: ...

    def current_for_commitment(
        self,
        commitment_id: UUID,
    ) -> OutcomeSnapshot | None: ...


__all__ = ["OutcomeReadPort", "OutcomeSnapshot"]
