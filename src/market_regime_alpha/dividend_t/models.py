"""Core data contracts for the dividend T-trading model."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


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


@dataclass(frozen=True)
class WatchlistItem:
    symbol: str
    name: str
    industry: str
    is_cycle_stock: bool = True
    notes: str = ""
