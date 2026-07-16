"""Rehearsal-scoped future path evidence for Entry Target materialization.

These contracts describe future market observations. They do not contain Entry outcomes,
policies, proposals, or execution authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import math

from market_regime_alpha.core.time import AvailabilityTime, FinalizationTime


def _require_symbol(symbol: str) -> None:
    if (
        not isinstance(symbol, str)
        or not symbol.strip()
        or symbol != symbol.strip()
    ):
        raise ValueError("symbol must be a non-empty trimmed string")


def _require_text(label: str, value: str) -> None:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
    ):
        raise ValueError(f"{label} must be a non-empty trimmed string")


def _require_positive_finite(label: str, value: float) -> None:
    if isinstance(value, bool) or not math.isfinite(float(value)) or float(value) <= 0.0:
        raise ValueError(f"{label} must be positive and finite")


def _require_evidence_times(
    available_at: AvailabilityTime,
    finalized_at: FinalizationTime,
) -> None:
    if not isinstance(available_at, AvailabilityTime):
        raise TypeError("available_at must be an AvailabilityTime")
    if not isinstance(finalized_at, FinalizationTime):
        raise TypeError("finalized_at must be a FinalizationTime")
    if available_at.value < finalized_at.value:
        raise ValueError("available_at must not precede finalized_at")


@dataclass(frozen=True, slots=True)
class RehearsalFutureDailyBar:
    """Finalized future daily OHLC evidence for path-dependent research Targets."""

    symbol: str
    session_date: date
    open: float
    high: float
    low: float
    close: float
    price_adjustment_basis: str
    available_at: AvailabilityTime
    finalized_at: FinalizationTime

    def __post_init__(self) -> None:
        _require_symbol(self.symbol)
        if not isinstance(self.session_date, date):
            raise TypeError("session_date must be a date")
        for label, value in (
            ("open", self.open),
            ("high", self.high),
            ("low", self.low),
            ("close", self.close),
        ):
            _require_positive_finite(label, value)
        if self.low > self.high:
            raise ValueError("future daily OHLC requires low <= high")
        if not self.low <= self.open <= self.high:
            raise ValueError("future daily OHLC requires low <= open <= high")
        if not self.low <= self.close <= self.high:
            raise ValueError("future daily OHLC requires low <= close <= high")
        _require_text("price_adjustment_basis", self.price_adjustment_basis)
        _require_evidence_times(self.available_at, self.finalized_at)


@dataclass(frozen=True, slots=True)
class RehearsalFutureSuspensionEvidence:
    """Explicit future session suspension state used when a daily bar is absent."""

    symbol: str
    session_date: date
    is_suspended: bool
    available_at: AvailabilityTime
    finalized_at: FinalizationTime

    def __post_init__(self) -> None:
        _require_symbol(self.symbol)
        if not isinstance(self.session_date, date):
            raise TypeError("session_date must be a date")
        if not isinstance(self.is_suspended, bool):
            raise TypeError("is_suspended must be boolean")
        _require_evidence_times(self.available_at, self.finalized_at)
