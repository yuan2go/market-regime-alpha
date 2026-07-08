"""Dividend long-term holding plus T-trading platform modules."""

from market_regime_alpha.dividend_t.models import (
    FundamentalInputs,
    PositionState,
    RetreatInputs,
    Signal,
    TechnicalInputs,
    TrendState,
)
from market_regime_alpha.dividend_t.strategy import DividendTStrategy

__all__ = [
    "DividendTStrategy",
    "FundamentalInputs",
    "PositionState",
    "RetreatInputs",
    "Signal",
    "TechnicalInputs",
    "TrendState",
]
