"""Versioned ExecutionRecord boundary; LIVE execution is intentionally absent."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from market_regime_alpha.core.identity import ArtifactId


class ExecutionState(str, Enum):
    NOT_EXECUTED = "NOT_EXECUTED"
    SIMULATED = "SIMULATED"


@dataclass(frozen=True, slots=True)
class ExecutionRecord:
    schema_version: str
    position_plan_id: ArtifactId
    symbol: str
    execution_state: ExecutionState
    simulated_price: float | None
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != "execution-record-v1":
            raise ValueError("unsupported ExecutionRecord schema")
        if (
            self.execution_state is ExecutionState.SIMULATED
            and (self.simulated_price is None or self.simulated_price <= 0.0)
        ):
            raise ValueError("simulated execution requires a positive price")
        if (
            self.execution_state is ExecutionState.NOT_EXECUTED
            and self.simulated_price is not None
        ):
            raise ValueError("non-execution cannot carry a price")

