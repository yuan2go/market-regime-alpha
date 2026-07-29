"""Versioned Trade Decision boundary restricted to simulation semantics."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from market_regime_alpha.core.identity import ArtifactId


class TradeDecisionState(str, Enum):
    REJECT = "REJECT"
    WATCH = "WATCH"
    WAIT_CONFIRMATION = "WAIT_CONFIRMATION"
    ENTER_SIMULATION = "ENTER_SIMULATION"

@dataclass(frozen=True, slots=True)
class TradeDecision:
    schema_version: str
    symbol: str
    candidate_set_id: ArtifactId
    signal_snapshot_id: ArtifactId | None
    forecast_id: ArtifactId | None
    decision_state: TradeDecisionState
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != "trade-decision-v1":
            raise ValueError("unsupported TradeDecision schema")
        if self.decision_state is TradeDecisionState.ENTER_SIMULATION and (
            self.signal_snapshot_id is None or self.forecast_id is None
        ):
            raise ValueError("simulation entry requires Signal and Forecast evidence")
