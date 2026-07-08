"""Shared data contracts for the COSCO 5-minute timing engine."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from market_regime_alpha.dividend_t.attention import AttentionScore
    from market_regime_alpha.dividend_t.certainty import CertaintyScore
    from market_regime_alpha.dividend_t.chan import ChanStructure
    from market_regime_alpha.dividend_t.dynamic_weights import DynamicWeights
    from market_regime_alpha.dividend_t.force_ratio import ForceRatioEstimate
    from market_regime_alpha.dividend_t.memory import MemoryScore
    from market_regime_alpha.dividend_t.sell_pressure import SellPressureEstimate

@dataclass(frozen=True)
class ReferencePrices:
    current_price: float
    support_price: float
    resistance_price: float
    buy_reference_price: float | None
    sell_reference_price: float | None
    stop_price: float | None
    buy_back_reference_price: float | None = None


@dataclass(frozen=True)
class SignalStrength:
    score: float
    label: str
    estimated_win_rate: float
    reward_risk_ratio: float
    kelly_fraction: float
    reasons: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class MarketRegime:
    state: str
    label: str
    base_position_target_pct: float
    base_position_limit_pct: float
    t_trade_limit_pct: float
    active_position_cap_pct: float = 0.0
    max_total_position_pct: float = 0.0
    reasons: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class MultiPeriodTrend:
    score: float
    daily_5d_state: str
    weekly_state: str
    monthly_state: str
    reasons: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CapitalFlowEstimate:
    score: float
    state: str
    short_flow_ratio: float
    medium_flow_ratio: float
    long_flow_ratio: float
    confirmation_score: float
    confirmation_state: str
    confidence: float
    source_type: str
    reasons: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class VolumePriceStructure:
    score: float
    state: str
    volume_breakout_score: float = 50.0
    low_volume_pullback_score: float = 50.0
    high_volume_stall_score: float = 0.0
    price_up_volume_down_score: float = 0.0
    vwap_support_score: float = 50.0
    post_breakout_volume_persistence_score: float = 50.0
    volume_expansion_ratio: float = 1.0
    price_efficiency: float = 0.0
    reasons: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class TrendProbability:
    up_1d: float
    down_1d: float
    up_3d: float
    down_3d: float
    edge_1d: float
    edge_3d: float
    state: str
    reasons: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class BreakoutSetup:
    score: float
    state: str
    breakout_level: float | None
    trigger_price: float | None
    day_return: float
    recent_return: float
    volume_expansion: float
    distance_to_breakout: float | None
    breakout_confirmed: bool
    pre_breakout_watch: bool
    reasons: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DailyContext:
    score: float
    state: str
    fundamental_score: float
    base_position_limit_pct: float
    close: float
    previous_close: float | None
    ma3: float | None
    ma5: float | None
    daily_support: float | None
    daily_resistance: float | None
    allow_t: bool
    allow_overnight: bool
    buyback_allowed: bool
    position_multiplier: float
    reasons: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class IntradayContext:
    score: float
    state: str
    support_confirmed: bool
    resistance_confirmed: bool
    late_session: bool
    near_support: bool
    near_resistance: bool
    rebound_from_low: bool
    five_min_reclaim: bool
    reasons: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CoscoTimingSnapshot:
    symbol: str
    name: str
    timestamp: str
    generated_at: str
    data_source: str
    data_age_minutes: float
    data_fresh: bool
    freshness_status: str
    freshness_limit_minutes: float
    interval_minutes: int
    action: str
    confidence: float
    prices: ReferencePrices
    attention: AttentionScore
    certainty: CertaintyScore
    memory: MemoryScore
    sell_pressure: SellPressureEstimate
    weights: DynamicWeights
    force: ForceRatioEstimate
    market_regime: MarketRegime
    multi_period_trend: MultiPeriodTrend
    capital_flow: CapitalFlowEstimate
    volume_price_structure: VolumePriceStructure
    chan_structure: ChanStructure
    trend_probability: TrendProbability
    breakout_setup: BreakoutSetup
    signal_strength: SignalStrength
    risk_reward_ratio: float
    trend_state: str
    daily_context: DailyContext
    intraday_context: IntradayContext
    reasons: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    data_attempts: tuple[dict[str, object], ...] = field(default_factory=tuple)
    runtime_profile: tuple[dict[str, object], ...] = field(default_factory=tuple)
    manual_only: bool = True
    is_realtime: bool = False
    signal_blocked: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CoscoTimingUnavailable:
    symbol: str
    status: str
    message: str
    required_user_steps: tuple[str, ...]
    data_source: str = "tushare_stk_mins_5min"
    is_realtime: bool = False
    data_attempts: tuple[dict[str, object], ...] = field(default_factory=tuple)
    runtime_profile: tuple[dict[str, object], ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
