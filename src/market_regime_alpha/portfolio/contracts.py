"""Versioned PositionPlan boundary restricted to research simulation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from market_regime_alpha.core.identity import ArtifactId


class PositionPlanState(str, Enum):
    NOT_AUTHORIZED = "NOT_AUTHORIZED"
    RESEARCH_SIMULATION = "RESEARCH_SIMULATION"


@dataclass(frozen=True, slots=True)
class PositionPlan:
    schema_version: str
    trade_decision_id: ArtifactId
    symbol: str
    plan_state: PositionPlanState
    maximum_portfolio_fraction: float | None
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != "position-plan-v1":
            raise ValueError("unsupported PositionPlan schema")
        if self.maximum_portfolio_fraction is not None and not (
            0.0 <= self.maximum_portfolio_fraction <= 1.0
        ):
            raise ValueError("portfolio fraction must be within [0, 1]")

