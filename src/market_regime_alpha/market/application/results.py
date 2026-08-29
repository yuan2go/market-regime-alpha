"""Stable Market command result DTOs."""

from dataclasses import dataclass
from uuid import UUID

from market_regime_alpha.market.domain import ProviderCapture
from market_regime_alpha.runtime.ports import ArtifactRecord
from market_regime_alpha.shared.time import DecisionTime


@dataclass(frozen=True, slots=True)
class MarketMutationResult:
    aggregate_kind: str
    aggregate_id: str
    aggregate_version: int
    result_hash: str
    receipt_id: UUID
    replayed: bool
    decision_visible_at: DecisionTime | None = None


@dataclass(frozen=True, slots=True)
class CaptureMutationResult:
    capture: ProviderCapture
    artifact: ArtifactRecord | None
    result_hash: str
    receipt_id: UUID
    replayed: bool
