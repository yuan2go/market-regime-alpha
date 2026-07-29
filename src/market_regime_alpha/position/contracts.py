"""Versioned ExitDecision boundary restricted to research simulation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from market_regime_alpha.core.identity import ArtifactId


class ExitDecisionState(str, Enum):
    NO_ACTION = "NO_ACTION"
    WAIT = "WAIT"
    EXIT_SIMULATION = "EXIT_SIMULATION"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"


@dataclass(frozen=True, slots=True)
class ExitDecision:
    schema_version: str
    position_evidence_id: ArtifactId
    symbol: str
    exit_state: ExitDecisionState
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != "exit-decision-v1":
            raise ValueError("unsupported ExitDecision schema")

