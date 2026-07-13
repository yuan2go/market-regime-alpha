"""Core data contracts for the dividend T-trading model."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import TYPE_CHECKING

from market_regime_alpha.dividend_t.macd import MACDCross, MACDDataReason, MACDHistogramTrend, MACDZeroAxis

if TYPE_CHECKING:
    from market_regime_alpha.dividend_t.signal_intent import DecisionTrace


class Signal(str, Enum):
    BUILD_BASE = "BUILD_BASE"
    HOLD = "HOLD"
    BUY_T = "BUY_T"
    SELL_T = "SELL_T"
    SELL_REVERSE_T = "SELL_REVERSE_T"
    BUY_BACK_REVERSE_T = "BUY_BACK_REVERSE_T"
    STOP_T = "STOP_T"
    REDUCE = "REDUCE"
    CLEAR = "CLEAR"


class TrendState(str, Enum):
    UPTREND = "UPTREND"
    RANGE = "RANGE"
    DOWNTREND = "DOWNTREND"
    BREAKOUT = "BREAKOUT"
    EXHAUSTION = "EXHAUSTION"


@dataclass(frozen=True)
class FundamentalInputs:
    dividend_sustainability: float
    valuation_margin: float
    cycle_prosperity: float
    financial_quality: float
    catalyst_stability: float


@dataclass(frozen=True)
class RetreatInputs:
    market_attention: float
    upside_certainty: float
    risk_reward_ratio: float
    sell_pressure: float


@dataclass(frozen=True)
class TechnicalInputs:
    position_quality: float
    volume_structure: float
    trend_quality: float
    intraday_support: float
    chan_score: float = 65.0
    trend_state: TrendState = TrendState.RANGE
    near_support: bool = False
    near_resistance: bool = False
    shrinking_pullback: bool = False
    volume_stalling: bool = False
    intraday_reversal: bool = False
    sector_healthy: bool = True
    chan_structure_type: str = "unknown"
    chan_trend_direction: str = "range"
    chan_divergence_type: str = "none"
    chan_buy_point_type: str = "none"
    chan_sell_point_type: str = "none"
    chan_pivot_low: float | None = None
    chan_pivot_high: float | None = None
    chan_invalid_price: float | None = None
    macd_dif: float | None = None
    macd_dea: float | None = None
    macd_histogram: float | None = None
    macd_histogram_delta: float | None = None
    macd_histogram_trend: MACDHistogramTrend = MACDHistogramTrend.FLAT
    macd_cross: MACDCross = MACDCross.NONE
    macd_cross_age: int | None = None
    macd_zero_axis: MACDZeroAxis = MACDZeroAxis.STRADDLING
    macd_data_ready: bool = False
    macd_data_reason: MACDDataReason = MACDDataReason.INSUFFICIENT_BARS
    macd_score: float = 50.0

    def __post_init__(self) -> None:
        validate_macd_consistency(self)


def validate_macd_consistency(technical: TechnicalInputs) -> None:
    """Validate the flat TechnicalInputs representation of MACD state."""

    if not isinstance(technical.macd_data_ready, bool):
        raise ValueError("macd_data_ready must be boolean")
    if not isinstance(technical.macd_data_reason, MACDDataReason):
        raise ValueError("macd_data_reason must be a MACDDataReason")
    if not isinstance(technical.macd_histogram_trend, MACDHistogramTrend):
        raise ValueError("macd_histogram_trend must be a MACDHistogramTrend")
    if not isinstance(technical.macd_cross, MACDCross):
        raise ValueError("macd_cross must be a MACDCross")
    if not isinstance(technical.macd_zero_axis, MACDZeroAxis):
        raise ValueError("macd_zero_axis must be a MACDZeroAxis")

    raw = (technical.macd_dif, technical.macd_dea, technical.macd_histogram)
    if technical.macd_data_ready:
        if technical.macd_data_reason is not MACDDataReason.READY or any(value is None for value in raw):
            raise ValueError("ready MACD requires READY reason and DIF/DEA/Histogram")
        assert technical.macd_dif is not None and technical.macd_dea is not None and technical.macd_histogram is not None
        ready_values = tuple(float(value) for value in raw if value is not None)
        if any(not math.isfinite(value) for value in ready_values):
            raise ValueError("ready MACD raw values must be finite")
        if technical.macd_histogram_delta is not None and not math.isfinite(float(technical.macd_histogram_delta)):
            raise ValueError("macd histogram delta must be finite when present")
        if not math.isfinite(float(technical.macd_score)) or not 0.0 <= technical.macd_score <= 100.0:
            raise ValueError("macd score must be in [0, 100]")
        if technical.macd_cross is MACDCross.NONE and technical.macd_cross_age is not None:
            raise ValueError("NONE cross cannot have an age")
        if technical.macd_cross is not MACDCross.NONE:
            if isinstance(technical.macd_cross_age, bool) or not isinstance(technical.macd_cross_age, int) or technical.macd_cross_age < 0:
                raise ValueError("live cross requires a non-negative cross age")
        dif = float(technical.macd_dif)
        dea = float(technical.macd_dea)
        expected_axis = (
            MACDZeroAxis.ABOVE
            if dif > 0.0 and dea > 0.0
            else MACDZeroAxis.BELOW
            if dif < 0.0 and dea < 0.0
            else MACDZeroAxis.STRADDLING
        )
        if technical.macd_zero_axis is not expected_axis:
            raise ValueError("macd_zero_axis must match unrounded DIF and DEA")
        return

    if technical.macd_data_reason is MACDDataReason.READY:
        raise ValueError("unready MACD cannot use READY reason")
    if technical.macd_score != 50.0 or technical.macd_cross is not MACDCross.NONE or technical.macd_cross_age is not None:
        raise ValueError("unready MACD must use neutral score and cross")
    if any(value is not None for value in (*raw, technical.macd_histogram_delta)):
        raise ValueError("unready MACD raw fields must be None")
    if technical.macd_histogram_trend is not MACDHistogramTrend.FLAT or technical.macd_zero_axis is not MACDZeroAxis.STRADDLING:
        raise ValueError("unready MACD must use neutral trend and zero axis")


@dataclass(frozen=True)
class PositionState:
    total_equity: float = 1.0
    symbol_position_pct: float = 0.0
    base_position_pct: float = 0.0
    t_position_pct: float = 0.0
    cash_pct: float = 1.0
    available_cash_pct: float = 1.0
    available_sell_pct: float = 0.0
    is_cycle_stock: bool = True
    consecutive_t_failures: int = 0


@dataclass(frozen=True)
class ScoreBreakdown:
    F_score: float
    G_score: float
    Z_score: float
    K_score: float
    S_score: float
    R_score: float
    T_score: float
    total_score: float
    C_score: float = 65.0


@dataclass(frozen=True)
class OrderIntent:
    symbol: str
    side: str
    position_type: str
    signal: Signal
    notional_pct: float
    reason: str


@dataclass(frozen=True)
class StrategyDecision:
    symbol: str
    signal: Signal
    score: ScoreBreakdown
    base_position_limit_pct: float
    suggested_trade_pct: float
    reasons: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    order_intent: OrderIntent | None = None
    decision_trace: DecisionTrace | None = None


@dataclass(frozen=True)
class WatchlistItem:
    symbol: str
    name: str
    industry: str
    is_cycle_stock: bool = True
    notes: str = ""
