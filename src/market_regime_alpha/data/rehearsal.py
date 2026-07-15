"""Controlled rehearsal market observations for the first R5 Candidate pipeline.

These objects are intentionally scoped to rehearsal research. They are not a canonical
provider schema and do not grant PIT or FORMAL_RESEARCH authority to any data source.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import math

from market_regime_alpha.core.time import AvailabilityTime, DecisionTime


def _require_symbol(symbol: str) -> None:
    if not isinstance(symbol, str) or not symbol.strip() or symbol != symbol.strip():
        raise ValueError("symbol must be a non-empty trimmed string")


def _require_positive_finite(label: str, value: float) -> None:
    if not math.isfinite(float(value)) or float(value) <= 0.0:
        raise ValueError(f"{label} must be positive and finite")


def _require_non_negative_finite(label: str, value: float) -> None:
    if not math.isfinite(float(value)) or float(value) < 0.0:
        raise ValueError(f"{label} must be non-negative and finite")


@dataclass(frozen=True, slots=True)
class RehearsalDailyBar:
    """One finalized historical daily observation available before a Candidate decision."""

    symbol: str
    session_date: date
    close: float
    amount: float
    available_at: AvailabilityTime
    finalized: bool = True

    def __post_init__(self) -> None:
        _require_symbol(self.symbol)
        if not isinstance(self.session_date, date):
            raise TypeError("session_date must be a date")
        _require_positive_finite("close", self.close)
        _require_non_negative_finite("amount", self.amount)
        if not isinstance(self.finalized, bool):
            raise TypeError("finalized must be boolean")


@dataclass(frozen=True, slots=True)
class RehearsalDecisionSnapshot:
    """Price reference actually available at the declared Candidate Decision Time."""

    symbol: str
    decision_time: DecisionTime
    reference_price: float
    available_at: AvailabilityTime

    def __post_init__(self) -> None:
        _require_symbol(self.symbol)
        _require_positive_finite("reference_price", self.reference_price)
        if self.available_at.value > self.decision_time.value:
            raise ValueError("decision snapshot must be available by decision_time")


@dataclass(frozen=True, slots=True)
class RehearsalNextSessionClose:
    """Observed next-session close used only on the future Target side of R5 rehearsal."""

    symbol: str
    session_date: date
    close: float
    available_at: AvailabilityTime

    def __post_init__(self) -> None:
        _require_symbol(self.symbol)
        if not isinstance(self.session_date, date):
            raise TypeError("session_date must be a date")
        _require_positive_finite("close", self.close)
