"""Backtest loop for the COSCO dividend T timing model.

The backtest is intentionally conservative:

- signals are generated with bars available up to the previous 5-minute close;
- execution happens on the next bar open;
- the engine only simulates manual T timing, not live broker execution.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Callable

from market_regime_alpha.dividend_t.cosco_timing import CoscoTimingEngine
from market_regime_alpha.dividend_t.buy_point_quality import BUY_POINT_SUBTYPE_PULLBACK_LOW_BUY, classify_buy_point_subtype
from market_regime_alpha.dividend_t.market_environment import (
    MARKET_CAUTION,
    MARKET_NEUTRAL,
    MARKET_RISK_OFF,
    MARKET_RISK_ON,
    MarketEnvironmentFilter,
    MarketEnvironmentPoint,
    market_environment_point_with_model_state,
)
from market_regime_alpha.dividend_t.macd_experiments import (
    CounterfactualEvent,
    CounterfactualEventType,
    CounterfactualPathOutcome,
    ExecutionResolution,
    LEGACY_CACHE_COMPATIBILITY_MODE,
    MACD_CACHE_SCHEMA_VERSION,
    MACDExperimentIdentity,
    cache_metadata,
    experiment_config_hash,
    signal_cache_path,
    validate_runtime_identity,
)
from market_regime_alpha.dividend_t.bar_store import load_raw_5min_bars_csv, load_raw_5min_bars_path
from market_regime_alpha.dividend_t.position_sizing import MAX_BASE_POSITION_PCT, MIN_BASE_POSITION_PCT, PositionBudget
from market_regime_alpha.dividend_t.models import Signal
from market_regime_alpha.dividend_t.signal_intent import (
    CandidateContractError,
    DecisionTrace,
    PolicyDecision,
    RiskEnforcement,
    SignalIntent,
    SizingDecision,
    MACDPolicyConfig,
    apply_macd_sizing_once,
)
from market_regime_alpha.dividend_t.strategy_modes import apply_strategy_mode


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SIGNAL_CACHE_DIR = PROJECT_ROOT / "data" / "processed" / "dividend_t_signal_cache"
SIGNAL_CACHE_VERSION = "v32_macd_policy_trace"
DEFAULT_SIGNAL_HISTORY_BARS = 48 * 20
ATTACK_INACTIVE = "INACTIVE"
ATTACK_WATCH = "WATCH"
ATTACK_CONFIRMED = "CONFIRMED"
ATTACK_FULL = "FULL_ATTACK"
ATTACK_BETA_HOLD = "BETA_HOLD"
VOLUME_PRICE_NONE = "NONE"
VOLUME_PRICE_ROTATION = "ROTATION"
VOLUME_PRICE_WARNING = "WARNING"
VOLUME_PRICE_DISTRIBUTION = "DISTRIBUTION"
T_POSITION_MODE_FULL = "full"
T_POSITION_MODE_LIGHT = "light"
T_POSITION_MODE_NONE = "none"
T_POSITION_MODE_REDUCE_ONLY = "reduce-only"
T_POSITION_MODE_ADD_ONLY = "add-only"
T_POSITION_MODES = {
    T_POSITION_MODE_FULL,
    T_POSITION_MODE_LIGHT,
    T_POSITION_MODE_NONE,
    T_POSITION_MODE_REDUCE_ONLY,
    T_POSITION_MODE_ADD_ONLY,
}


@dataclass(frozen=True)
class DividendTBacktestConfig:
    initial_cash: float = 100_000.0
    initial_base_position_pct: float = 0.10
    t_position_mode: str = T_POSITION_MODE_FULL
    enable_t_sell: bool = False
    t_trade_pct: float = 1.00
    min_t_trade_pct: float = 0.03
    strategy_mode: str = "balanced"
    strong_trend_base_position_pct: float = 0.10
    base_rebalance_threshold_pct: float = 0.03
    base_rebalance_step_pct: float = 0.05
    base_rebalance_cooldown_bars: int = 48
    strong_trend_confirm_signals: int = 3
    trend_exit_confirm_signals: int = 4
    defensive_confirm_signals: int = 2
    kelly_fraction_scale: float = 0.65
    min_buy_signal_strength: float = 66.0
    min_buy_point_quality_score: float = 0.42
    min_main_rise_buy_quality_score: float = 0.46
    min_breakout_buy_quality_score: float = 0.42
    min_breakout_buy_main_rise_quality_score: float = 0.46
    min_base_rebalance_buy_quality_score: float = 0.50
    min_risk_on_add_quality_score: float = 0.50
    min_risk_on_add_main_rise_quality_score: float = 0.58
    enable_point_hit_rate_sell_calibration: bool = False
    buy_t_failure_cooldown_bars: int = 96
    max_signal_position_pct: float = 1.00
    strong_trend_signal_position_pct: float = 0.80
    trend_watch_signal_position_pct: float = 0.50
    range_signal_position_pct: float = 0.35
    enable_attack_state_machine: bool = True
    attack_watch_position_pct: float = 0.25
    attack_confirm_position_pct: float = 0.70
    attack_full_position_pct: float = 1.00
    attack_watch_min_breakout_score: float = 82.0
    attack_confirm_min_breakout_score: float = 92.0
    attack_confirm_min_buy_strength: float = 70.0
    attack_full_confirm_signals: int = 1
    attack_min_hold_bars: int = 6
    trend_follow_min_hold_bars: int = 18
    enable_beta_hold_state: bool = True
    beta_hold_target_position_pct: float = 1.00
    beta_hold_min_confirmations: int = 2
    beta_hold_min_strength: float = 62.0
    beta_hold_min_bars: int = 1440
    beta_hold_exit_confirm_bars: int = 4
    beta_hold_soft_exit_confirm_bars: int = 6
    beta_hold_distribution_confirm_bars: int = 3
    beta_hold_hard_stop_loss_pct: float = 0.10
    beta_hold_main_rise_core_floor_pct: float = 0.80
    beta_hold_main_rise_core_min_confirmations: int = 3
    beta_hold_core_break_vwap_score: float = 58.0
    beta_hold_core_break_flow_score: float = 56.0
    beta_hold_core_break_force_ratio: float = 0.72
    beta_hold_soft_exit_sell_fraction: float = 0.08
    beta_hold_soft_stop_sell_fraction: float = 0.18
    beta_hold_distribution_sell_fraction: float = 0.22
    beta_hold_trailing_pullback_multiplier: float = 2.80
    beta_hold_trailing_light_sell_fraction: float = 0.0
    beta_hold_trailing_mid_sell_fraction: float = 0.16
    beta_hold_trailing_hard_sell_fraction: float = 0.32
    attack_exit_sell_pressure_score: float = 78.0
    attack_exit_confirm_bars: int = 3
    attack_distribution_confirm_bars: int = 2
    attack_exit_force_ratio: float = 0.00
    attack_exit_down_probability: float = 0.60
    attack_hard_exit_sell_pressure_score: float = 88.0
    attack_hard_exit_down_probability: float = 0.68
    offensive_hold_extension_enabled: bool = True
    sell_point_continuation_quality_score: float = 0.52
    offensive_soft_exit_sell_fraction: float = 0.35
    offensive_soft_stop_sell_fraction: float = 0.50
    offensive_stop_hold_loss_pct: float = 0.035
    offensive_trend_add_floor_pct: float = 0.85
    offensive_full_add_floor_pct: float = 0.95
    offensive_trailing_profit_enabled: bool = True
    offensive_trailing_profit_trigger_pct: float = 0.055
    offensive_trailing_profit_mid_pct: float = 0.11
    offensive_trailing_profit_high_pct: float = 0.18
    offensive_trailing_pullback_pct: float = 0.025
    offensive_trailing_pullback_mid_pct: float = 0.045
    offensive_trailing_pullback_high_pct: float = 0.07
    offensive_trailing_light_sell_fraction: float = 0.18
    offensive_trailing_mid_sell_fraction: float = 0.32
    offensive_trailing_hard_sell_fraction: float = 0.55
    offensive_beta_trend_pullback_multiplier: float = 1.80
    offensive_volume_distribution_enabled: bool = True
    offensive_volume_stall_reduce_score: float = 76.0
    offensive_price_up_volume_down_reduce_score: float = 82.0
    offensive_volume_distribution_hard_stall_score: float = 86.0
    offensive_volume_distribution_hard_up_down_score: float = 88.0
    offensive_volume_distribution_min_profit_pct: float = 0.06
    offensive_volume_distribution_min_peak_profit_pct: float = 0.10
    offensive_volume_distribution_absorption_vwap_score: float = 68.0
    offensive_volume_distribution_absorption_persistence_score: float = 70.0
    offensive_volume_distribution_continuation_min_confirmations: int = 3
    offensive_volume_distribution_reduce_pressure_count: int = 2
    offensive_volume_distribution_distribution_pressure_count: int = 3
    offensive_volume_distribution_distribution_vwap_break_score: float = 58.0
    offensive_volume_distribution_distribution_flow_score: float = 56.0
    volume_price_continuation_lookback_bars: int = 48
    volume_price_continuation_min_return_pct: float = 0.012
    volume_price_continuation_max_volume_ratio: float = 0.95
    enable_buy_volume_price_window_filter: bool = True
    buy_volume_price_short_lookback_bars: int = 12
    buy_volume_price_mid_lookback_bars: int = 24
    buy_volume_price_filter_min_return_pct: float = 0.004
    buy_volume_price_filter_max_contract_ratio: float = 0.82
    buy_volume_price_filter_min_quality_score: float = 0.34
    offensive_volume_distribution_low_vwap_score: float = 62.0
    offensive_volume_distribution_low_persistence_score: float = 62.0
    offensive_volume_distribution_low_flow_score: float = 66.0
    offensive_volume_distribution_low_force_ratio: float = 0.85
    offensive_volume_distribution_low_force_score: float = 52.0
    offensive_volume_distribution_low_volume_price_score: float = 64.0
    offensive_volume_distribution_sell_fraction: float = 0.45
    offensive_volume_distribution_hard_sell_fraction: float = 0.70
    fallback_kelly_fraction: float = 0.05
    confirmed_flow_position_bonus_pct: float = 0.15
    commission_rate: float = 0.00025
    stamp_duty_rate: float = 0.0005
    slippage_bps: float = 2.0
    min_lot: int = 100
    min_lookback_bars: int = 48
    allow_reverse_t: bool = True
    enable_profit_protection: bool = True
    profit_protect_trigger_pct: float = 0.012
    profit_protect_sell_fraction: float = 0.50
    periods_per_year: int = 252 * 48
    max_history_bars: int = DEFAULT_SIGNAL_HISTORY_BARS
    signal_step_bars: int = 1
    signal_cache_dir: Path | None = None
    signal_cache_save_every: int = 200
    signal_cache_tag: str = "profile"
    enable_market_filter: bool = False
    market_filter_name: str = "none"
    enable_stock_risk_on_regime: bool = True
    stock_risk_on_hold_bars: int = 720
    stock_risk_on_sustain_bars: int = 240
    market_risk_off_passthrough_cap_pct: float = 0.45
    enable_risk_on_continuation_add: bool = True
    risk_on_continuation_min_confirmations: int = 2
    risk_on_continuation_min_strength: float = 68.0
    enable_risk_on_position_target_engine: bool = True
    risk_on_position_target_min_confirmations: int = 2
    risk_on_position_target_min_strength: float = 45.0
    risk_on_position_target_min_gap_pct: float = 0.05
    risk_on_target_add_min_target_pct: float = 0.75
    risk_on_target_add_bonus_pct: float = 0.00
    risk_on_first_add_cap_pct: float = 0.60
    risk_on_low_position_add_cap_pct: float = 0.65
    risk_on_mid_position_add_cap_pct: float = 0.85
    enable_risk_on_high_position_reinforcement: bool = False
    risk_on_high_position_reinforce_cap_pct: float = 0.85
    risk_on_full_add_min_quality_score: float = 0.86
    risk_on_full_add_min_main_rise_quality_score: float = 0.78
    risk_on_secondary_add_quality_buffer: float = 0.18
    risk_on_secondary_add_main_rise_quality_buffer: float = 0.12
    risk_on_secondary_add_min_vwap_score: float = 76.0
    risk_on_secondary_add_min_volume_price_score: float = 70.0
    risk_on_secondary_add_min_volume_breakout_score: float = 72.0
    risk_on_secondary_add_min_volume_persistence_score: float = 76.0
    risk_on_secondary_add_min_flow_score: float = 70.0
    risk_on_secondary_add_max_sell_pressure_score: float = 64.0
    risk_on_secondary_add_max_down_probability_1d: float = 0.58
    risk_on_secondary_add_max_down_probability_3d: float = 0.60
    risk_on_secondary_add_min_confirmations: int = 3
    risk_on_beta_hold_secondary_min_confirmations: int = 3
    risk_on_high_quality_breakout_upgrade_target_pct: float = 0.95
    risk_on_add_follow_through_bars: int = 10
    risk_on_add_follow_through_min_high_return_pct: float = 0.005
    risk_on_add_follow_through_volume_ratio: float = 0.85
    risk_on_add_follow_through_vwap_tolerance_pct: float = 0.008
    risk_on_add_follow_through_failure_cooldown_bars: int = 96
    late_stage_stall_entry_filter_enabled: bool = True
    late_stage_recent_high_lookback_bars: int = 48
    late_stage_near_high_pct: float = 0.015
    late_stage_stall_lookback_bars: int = 6
    late_stage_max_stall_bars: int = 2
    late_stage_max_upper_shadow_ratio: float = 0.45
    late_stage_min_body_progress_ratio: float = 0.25
    late_stage_min_range_pct: float = 0.004
    enable_core_position_floor: bool = True
    risk_on_core_floor_l1_pct: float = 0.45
    risk_on_core_floor_l2_pct: float = 0.65
    risk_on_core_floor_l3_pct: float = 0.85
    risk_on_core_floor_ramp_step_pct: float = 0.15
    enable_portfolio_main_rise_position_target: bool = True
    portfolio_main_rise_position_target_pct: float = 0.95
    portfolio_main_rise_min_model_state_score: float = 62.0
    portfolio_main_rise_min_holding_win_rate: float = 0.56
    portfolio_main_rise_min_profit_spread: float = 0.62
    portfolio_main_rise_min_new_buy_success_rate: float = 0.45
    enable_candidate_entry: bool = False
    candidate_entry_start_target_pct: float = 0.55
    candidate_entry_start_max_bars: int = 48
    candidate_entry_start_respect_market_cap: bool = True
    candidate_entry_start_min_market_cap_pct: float = 0.10
    candidate_entry_confirm_target_pct: float = 0.95
    candidate_entry_confirm_min_strength: float = 64.0
    candidate_entry_confirm_min_confirmations: int = 2
    candidate_entry_confirm_probe_target_pct: float = 0.45
    candidate_entry_confirm_requires_follow_through: bool = True
    candidate_entry_confirm_market_passthrough: bool = True
    candidate_entry_min_hold_bars: int = 480
    candidate_entry_hard_stop_loss_pct: float = 0.08
    breakout_follow_through_bars: int = 10
    breakout_follow_through_min_high_return_pct: float = 0.005
    breakout_follow_through_volume_ratio: float = 1.00
    breakout_follow_through_failure_cooldown_bars: int = 96
    enable_breakout_direct_buy: bool = False
    breakout_direct_buy_probe_target_pct: float = 0.0
    breakout_direct_buy_requires_risk_on_confirmation: bool = True
    suppress_beta_hold_breakout_direct_buy: bool = False
    enable_a_share_constraints: bool = True
    enable_t1: bool = True
    enable_limit_price_constraints: bool = True
    enable_suspension_constraints: bool = True
    enable_dividend_adjustments: bool = True
    limit_price_tolerance_bps: float = 2.0

    @property
    def default_buy_total_cap_pct(self) -> float:
        return round(min(self.t_trade_pct, self.max_signal_position_pct), 4)

    @property
    def default_active_position_cap_pct(self) -> float:
        return round(max(0.0, self.default_buy_total_cap_pct - self.initial_base_position_pct), 4)

    @property
    def default_position_budget(self) -> PositionBudget:
        return PositionBudget.from_total_cap(
            base_target_pct=self.initial_base_position_pct,
            max_total_position_pct=self.default_buy_total_cap_pct,
        )


@dataclass(frozen=True)
class DividendTTrade:
    timestamp: str
    action: str
    side: str
    shares: int
    price: float
    cash_after: float
    equity_after: float
    reason: str
    realized_pnl: float | None = None
    execution_setup_code: str | None = None
    risk_enforcement: str = RiskEnforcement.NONE.value
    original_suggested_trade_pct: float | None = None
    macd_sizing_multiplier: float = 1.0
    adjusted_suggested_trade_pct: float | None = None
    macd_sizing_applied: bool = False
    macd_sizing_owner: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class DividendTBacktestPoint:
    timestamp: str
    close: float
    equity: float
    cash: float
    base_shares: int
    t_shares: int
    sellable_base_shares: int
    sellable_t_shares: int
    pending_buyback_shares: int
    pending_buyback_target_price: float | None
    action: str
    daily_state: str
    intraday_state: str
    market_regime_state: str
    attack_state: str
    strategy_mode: str
    market_environment_state: str
    market_environment_score: float
    base_target_pct: float
    t_trade_limit_pct: float
    market_trend_score: float = 0.0
    market_breadth_score: float = 0.0
    market_amount_score: float = 0.0
    market_limit_structure_score: float = 0.0
    market_industry_diffusion_score: float = 0.0
    market_model_state_score: float = 0.0
    market_advance_ratio: float = 0.0
    market_above_ma20_ratio: float = 0.0
    market_amount_ratio20: float = 0.0
    market_limit_up_ratio: float = 0.0
    market_limit_down_ratio: float = 0.0
    market_industry_risk_on_ratio: float = 0.0
    model_holding_win_rate: float = 0.0
    model_holding_profit_spread: float = 0.0
    model_new_buy_success_rate: float = 0.0
    active_position_cap_pct: float = 0.0
    max_total_position_pct: float = 0.0
    core_position_floor_pct: float = 0.0
    beta_hold_exit_confirm_streak: int = 0
    beta_hold_soft_exit_confirm_streak: int = 0
    beta_hold_distribution_confirm_streak: int = 0
    attack_exit_confirm_streak: int = 0
    trend_state: str = "RANGE"
    buy_point_subtype: str = "none"
    buy_signal_strength: float = 0.0
    breakout_score: float = 0.0
    breakout_state: str = "NONE"
    breakout_confirmed: bool = False
    pre_breakout_watch: bool = False
    volume_price_score: float = 50.0
    volume_price_state: str = "NEUTRAL"
    volume_breakout_score: float = 50.0
    post_breakout_volume_persistence_score: float = 50.0
    vwap_support_score: float = 50.0
    capital_flow_score: float = 50.0
    capital_flow_confirmation_score: float = 50.0
    capital_flow_confirmation_state: str = "UNCONFIRMED"
    capital_flow_confidence: float = 0.0
    force_weighted_score: float = 50.0
    force_ratio: float = 1.0
    sell_pressure_score: float = 50.0
    up_probability_1d: float = 0.50
    up_probability_3d: float = 0.50
    down_probability_1d: float = 0.50
    down_probability_3d: float = 0.50
    high_volume_stall_score: float = 0.0
    price_up_volume_down_score: float = 0.0
    pretrade_volume_price_state_12: str = "UNKNOWN"
    pretrade_price_return_pct_12: float = 0.0
    pretrade_volume_ratio_to_prev_12: float = 1.0
    pretrade_volume_price_state_24: str = "UNKNOWN"
    pretrade_price_return_pct_24: float = 0.0
    pretrade_volume_ratio_to_prev_24: float = 1.0
    pretrade_volume_price_state: str = "UNKNOWN"
    pretrade_volume_price_lookback_bars: int = 0
    pretrade_price_return_pct: float = 0.0
    pretrade_volume_ratio_to_prev: float = 1.0
    chan_score: float = 50.0
    chan_buy_point_type: str = "none"
    chan_structure_type: str = "insufficient"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class DividendTBacktestResult:
    symbol: str
    start: str
    end: str
    rows: int
    config: DividendTBacktestConfig
    initial_cash: float
    final_equity: float
    total_return: float
    benchmark_return: float
    excess_return: float
    annualized_return: float
    max_drawdown: float
    trade_count: int
    completed_trades: int
    win_rate: float | None
    realized_pnl: float
    action_counts: dict[str, int]
    gate_counts: dict[str, int]
    regime_counts: dict[str, int]
    attack_counts: dict[str, int]
    strategy_mode_counts: dict[str, int] = field(default_factory=dict)
    execution_block_counts: dict[str, int] = field(default_factory=dict)
    cache_hits: int = 0
    cache_misses: int = 0
    buyback_trade_count: int = 0
    corporate_action_count: int = 0
    cash_dividend_total: float = 0.0
    trades: tuple[DividendTTrade, ...] = field(default_factory=tuple)
    equity_curve: tuple[DividendTBacktestPoint, ...] = field(default_factory=tuple)
    signals: tuple[BacktestSignal, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["config"] = asdict(self.config)
        return data


@dataclass(frozen=True)
class BacktestSignal:
    timestamp: str
    action: str
    daily_state: str
    intraday_state: str
    trend_state: str
    market_regime_state: str
    position_multiplier: float
    fundamental_score: float
    base_position_limit_pct: float
    base_position_target_pct: float
    t_trade_limit_pct: float
    active_position_cap_pct: float = 0.0
    max_total_position_pct: float = 0.0
    multi_period_score: float = 50.0
    capital_flow_score: float = 50.0
    capital_flow_confirmation_score: float = 50.0
    capital_flow_confirmation_state: str = "UNCONFIRMED"
    capital_flow_confidence: float = 0.0
    capital_flow_source_type: str = "UNKNOWN"
    force_ratio: float = 1.0
    force_weighted_score: float = 50.0
    attention_score: float = 50.0
    certainty_score: float = 50.0
    memory_score: float = 50.0
    sell_pressure_score: float = 50.0
    up_probability_1d: float = 0.50
    up_probability_3d: float = 0.50
    down_probability_1d: float = 0.50
    down_probability_3d: float = 0.50
    probability_state: str = "RANGE"
    candidate_signal: str | None = None
    candidate_setup_code: str | None = None
    primary_setup_code: str | None = None
    signal_intent: str = "NONE"
    risk_enforcement: str = RiskEnforcement.NONE.value
    entry_confirmations: tuple[str, ...] = ("NONE",)
    exit_confirmations: tuple[str, ...] = ("NONE",)
    raw_candidate_action: str = "WAIT"
    quality_filtered_action: str = "WAIT"
    macd_filtered_action: str = "WAIT"
    freshness_filtered_action: str = "WAIT"
    final_action: str = "WAIT"
    final_signal: str = Signal.HOLD.value
    signal_downgraded: bool = False
    downgrade_source: str | None = None
    downgrade_reason: str | None = None
    original_suggested_trade_pct: float | None = None
    macd_sizing_multiplier: float = 1.0
    adjusted_suggested_trade_pct: float | None = None
    sizing_adjustment_source: str | None = None
    macd_sizing_applied: bool = False
    macd_sizing_owner: str | None = None
    macd_policy_applied: bool = False
    technical_score_without_macd: float = 50.0
    technical_score_with_macd: float = 50.0
    candidate_without_macd_score: str | None = None
    candidate_with_macd_score: str | None = None
    macd_score_changed_candidate: bool = False
    macd_policy_changed_candidate: bool = False
    macd_score: float = 50.0
    macd_cross: str = "NONE"
    macd_zero_axis: str = "STRADDLING"
    macd_histogram_trend: str = "FLAT"
    experiment_config_hash: str | None = None
    cache_schema_version: str | None = None
    git_commit: str | None = None
    dataset_version: str | None = None
    pipeline_id: str | None = None
    cache_compatibility_mode: str | None = None
    buy_point_subtype: str = "none"
    breakout_score: float = 0.0
    breakout_state: str = "NONE"
    breakout_confirmed: bool = False
    pre_breakout_watch: bool = False
    volume_price_score: float = 50.0
    volume_price_state: str = "NEUTRAL"
    volume_breakout_score: float = 50.0
    low_volume_pullback_score: float = 50.0
    high_volume_stall_score: float = 0.0
    price_up_volume_down_score: float = 0.0
    pretrade_volume_price_state_12: str = "UNKNOWN"
    pretrade_price_return_pct_12: float = 0.0
    pretrade_volume_ratio_to_prev_12: float = 1.0
    pretrade_volume_price_state_24: str = "UNKNOWN"
    pretrade_price_return_pct_24: float = 0.0
    pretrade_volume_ratio_to_prev_24: float = 1.0
    pretrade_volume_price_state: str = "UNKNOWN"
    pretrade_volume_price_lookback_bars: int = 0
    pretrade_price_return_pct: float = 0.0
    pretrade_volume_ratio_to_prev: float = 1.0
    vwap_support_score: float = 50.0
    post_breakout_volume_persistence_score: float = 50.0
    chan_score: float = 50.0
    chan_structure_type: str = "insufficient"
    chan_trend_direction: str = "range"
    chan_divergence_type: str = "none"
    chan_buy_point_type: str = "none"
    chan_sell_point_type: str = "none"
    chan_pivot_low: float | None = None
    chan_pivot_high: float | None = None
    chan_invalid_price: float | None = None
    buy_signal_strength: float = 0.0
    kelly_fraction: float = 0.0
    estimated_win_rate: float = 0.0
    buy_reference_price: float | None = None
    sell_reference_price: float | None = None
    buy_back_reference_price: float | None = None
    stop_price: float | None = None
    market_environment_state: str = "UNFILTERED"
    market_environment_score: float = 0.0
    market_trend_score: float = 0.0
    market_breadth_score: float = 0.0
    market_amount_score: float = 0.0
    market_limit_structure_score: float = 0.0
    market_industry_diffusion_score: float = 0.0
    market_model_state_score: float = 50.0
    model_holding_win_rate: float = 0.50
    model_holding_profit_spread: float = 0.50
    model_new_buy_success_rate: float = 0.50

    @classmethod
    def from_snapshot(cls, snapshot: Any) -> "BacktestSignal":
        signal_strength = getattr(snapshot, "signal_strength", None)
        market_regime = getattr(snapshot, "market_regime", None)
        multi_period = getattr(snapshot, "multi_period_trend", None)
        capital_flow = getattr(snapshot, "capital_flow", None)
        force = getattr(snapshot, "force", None)
        attention = getattr(snapshot, "attention", None)
        certainty = getattr(snapshot, "certainty", None)
        memory = getattr(snapshot, "memory", None)
        sell_pressure = getattr(snapshot, "sell_pressure", None)
        trend_probability = getattr(snapshot, "trend_probability", None)
        breakout_setup = getattr(snapshot, "breakout_setup", None)
        volume_price = getattr(snapshot, "volume_price_structure", None)
        chan_structure = getattr(snapshot, "chan_structure", None)
        decision_trace = getattr(snapshot, "decision_trace", None)
        macd_diagnostics = getattr(snapshot, "macd_diagnostics", None)
        base_limit = float(snapshot.daily_context.base_position_limit_pct)
        base_target = float(getattr(market_regime, "base_position_target_pct", min(base_limit, MAX_BASE_POSITION_PCT)))
        legacy_total_cap = float(getattr(market_regime, "t_trade_limit_pct", 0.10))
        max_total = float(getattr(market_regime, "max_total_position_pct", legacy_total_cap if legacy_total_cap > 0 else base_target))
        active_cap = float(getattr(market_regime, "active_position_cap_pct", max(0.0, max_total - base_target)))
        return cls(
            timestamp=str(snapshot.timestamp),
            action=str(snapshot.action),
            daily_state=str(snapshot.daily_context.state),
            intraday_state=str(snapshot.intraday_context.state),
            trend_state=str(getattr(snapshot, "trend_state", "RANGE")),
            market_regime_state=str(getattr(market_regime, "state", "RANGE_T")),
            position_multiplier=float(snapshot.daily_context.position_multiplier),
            fundamental_score=float(snapshot.daily_context.fundamental_score),
            base_position_limit_pct=base_limit,
            base_position_target_pct=base_target,
            t_trade_limit_pct=legacy_total_cap,
            active_position_cap_pct=active_cap,
            max_total_position_pct=max_total,
            multi_period_score=float(getattr(multi_period, "score", 50.0)),
            capital_flow_score=float(getattr(capital_flow, "score", 50.0)),
            capital_flow_confirmation_score=float(getattr(capital_flow, "confirmation_score", getattr(capital_flow, "score", 50.0))),
            capital_flow_confirmation_state=str(getattr(capital_flow, "confirmation_state", "UNCONFIRMED")),
            capital_flow_confidence=float(getattr(capital_flow, "confidence", 0.0)),
            capital_flow_source_type=str(getattr(capital_flow, "source_type", "UNKNOWN")),
            force_ratio=float(getattr(force, "force_ratio", 1.0)),
            force_weighted_score=float(getattr(force, "weighted_score", 50.0)),
            attention_score=float(getattr(attention, "score", 50.0)),
            certainty_score=float(getattr(certainty, "score", 50.0)),
            memory_score=float(getattr(memory, "score", 50.0)),
            sell_pressure_score=float(getattr(sell_pressure, "score", 50.0)),
            up_probability_1d=float(getattr(trend_probability, "up_1d", 0.50)),
            up_probability_3d=float(getattr(trend_probability, "up_3d", 0.50)),
            down_probability_1d=float(getattr(trend_probability, "down_1d", 0.50)),
            down_probability_3d=float(getattr(trend_probability, "down_3d", 0.50)),
            probability_state=str(getattr(trend_probability, "state", "RANGE")),
            candidate_signal=getattr(decision_trace, "candidate_signal", None),
            candidate_setup_code=getattr(decision_trace, "candidate_setup_code", None),
            primary_setup_code=getattr(decision_trace, "primary_setup_code", None),
            signal_intent=str(getattr(decision_trace, "candidate_signal_intent", "NONE")),
            risk_enforcement=str(getattr(decision_trace, "risk_enforcement", RiskEnforcement.NONE.value)),
            entry_confirmations=tuple(getattr(decision_trace, "entry_confirmations", ("NONE",))),
            exit_confirmations=tuple(getattr(decision_trace, "exit_confirmations", ("NONE",))),
            raw_candidate_action=str(getattr(decision_trace, "raw_candidate_action", snapshot.action)),
            quality_filtered_action=str(getattr(decision_trace, "quality_filtered_action", snapshot.action)),
            macd_filtered_action=str(getattr(decision_trace, "macd_filtered_action", snapshot.action)),
            freshness_filtered_action=str(getattr(decision_trace, "freshness_filtered_action", snapshot.action)),
            final_action=str(getattr(decision_trace, "final_action", snapshot.action)),
            final_signal=str(getattr(decision_trace, "final_signal", Signal.HOLD.value)),
            signal_downgraded=bool(getattr(decision_trace, "signal_downgraded", False)),
            downgrade_source=_optional_text(getattr(decision_trace, "downgrade_source", None)),
            downgrade_reason=_optional_text(getattr(decision_trace, "downgrade_reason", None)),
            original_suggested_trade_pct=_optional_float(getattr(decision_trace, "original_suggested_trade_pct", None)),
            macd_sizing_multiplier=float(getattr(decision_trace, "macd_sizing_multiplier", 1.0)),
            adjusted_suggested_trade_pct=_optional_float(getattr(decision_trace, "adjusted_suggested_trade_pct", None)),
            sizing_adjustment_source=_optional_text(getattr(decision_trace, "sizing_adjustment_source", None)),
            macd_sizing_applied=bool(getattr(decision_trace, "macd_sizing_applied", False)),
            macd_sizing_owner=_optional_text(getattr(decision_trace, "macd_sizing_owner", None)),
            macd_policy_applied=bool(getattr(decision_trace, "macd_policy_applied", False)),
            technical_score_without_macd=float(getattr(macd_diagnostics, "technical_score_without_macd", 50.0)),
            technical_score_with_macd=float(getattr(macd_diagnostics, "technical_score_with_macd", 50.0)),
            candidate_without_macd_score=_candidate_signal_value(getattr(macd_diagnostics, "candidate_without_macd_score", None)),
            candidate_with_macd_score=_candidate_signal_value(getattr(macd_diagnostics, "candidate_with_macd_score", None)),
            macd_score_changed_candidate=bool(getattr(macd_diagnostics, "macd_score_changed_candidate", False)),
            macd_policy_changed_candidate=bool(
                getattr(
                    macd_diagnostics,
                    "macd_policy_changed_candidate",
                    getattr(decision_trace, "macd_policy_changed_candidate", False),
                )
            ),
            macd_score=float(getattr(decision_trace, "macd_score", 50.0)),
            macd_cross=str(getattr(decision_trace, "macd_cross", "NONE")),
            macd_zero_axis=str(getattr(decision_trace, "macd_zero_axis", "STRADDLING")),
            macd_histogram_trend=str(getattr(decision_trace, "macd_histogram_trend", "FLAT")),
            buy_point_subtype=str(getattr(snapshot, "buy_point_subtype", "none")),
            breakout_score=float(getattr(breakout_setup, "score", 0.0)),
            breakout_state=str(getattr(breakout_setup, "state", "NONE")),
            breakout_confirmed=bool(getattr(breakout_setup, "breakout_confirmed", False)),
            pre_breakout_watch=bool(getattr(breakout_setup, "pre_breakout_watch", False)),
            volume_price_score=float(getattr(volume_price, "score", 50.0)),
            volume_price_state=str(getattr(volume_price, "state", "NEUTRAL")),
            volume_breakout_score=float(getattr(volume_price, "volume_breakout_score", 50.0)),
            low_volume_pullback_score=float(getattr(volume_price, "low_volume_pullback_score", 50.0)),
            high_volume_stall_score=float(getattr(volume_price, "high_volume_stall_score", 0.0)),
            price_up_volume_down_score=float(getattr(volume_price, "price_up_volume_down_score", 0.0)),
            vwap_support_score=float(getattr(volume_price, "vwap_support_score", 50.0)),
            post_breakout_volume_persistence_score=float(getattr(volume_price, "post_breakout_volume_persistence_score", 50.0)),
            chan_score=float(getattr(chan_structure, "score", 50.0)),
            chan_structure_type=str(getattr(chan_structure, "structure_type", "insufficient")),
            chan_trend_direction=str(getattr(chan_structure, "trend_direction", "range")),
            chan_divergence_type=str(getattr(chan_structure, "divergence_type", "none")),
            chan_buy_point_type=str(getattr(chan_structure, "buy_point_type", "none")),
            chan_sell_point_type=str(getattr(chan_structure, "sell_point_type", "none")),
            chan_pivot_low=getattr(chan_structure, "pivot_low", None),
            chan_pivot_high=getattr(chan_structure, "pivot_high", None),
            chan_invalid_price=getattr(chan_structure, "invalid_price", None),
            buy_signal_strength=float(getattr(signal_strength, "score", 0.0)),
            kelly_fraction=float(getattr(signal_strength, "kelly_fraction", 0.0)),
            estimated_win_rate=float(getattr(signal_strength, "estimated_win_rate", 0.0)),
            buy_reference_price=snapshot.prices.buy_reference_price,
            sell_reference_price=snapshot.prices.sell_reference_price,
            buy_back_reference_price=snapshot.prices.buy_back_reference_price,
            stop_price=snapshot.prices.stop_price,
        )


@dataclass(frozen=True)
class TradeExecutionConstraints:
    can_buy: bool = True
    can_sell: bool = True
    suspended: bool = False
    at_limit_up: bool = False
    at_limit_down: bool = False
    reason: str = ""


@dataclass(frozen=True)
class CounterfactualExecutionContext:
    equity_before: float
    cash: float
    total_sell_shares: int = 0
    sellable_shares: int = 0
    previous_daily_close: float | None = None
    base_shares: int = 0
    base_locked_shares: int = 0
    t_shares: int = 0
    t_locked_shares: int = 0
    core_position_floor_pct: float = 0.0
    hard_risk_exit: bool = False
    pending_buyback_shares: int = 0
    pending_buyback_target_price: float | None = None


EXECUTION_CONSTRAINT_VERSION = "a-share-execution-v1"


def counterfactual_event_from_signal(
    signal: BacktestSignal,
    *,
    symbol: str,
    next_eligible_execution_time: str,
    original_suggested_trade_pct: float,
    adjusted_suggested_trade_pct: float,
) -> CounterfactualEvent:
    """Create an offline event from persisted score, policy, intent, and MACD trace fields."""

    if not signal.experiment_config_hash:
        raise ValueError("COUNTERFACTUAL_EXPERIMENT_HASH_REQUIRED")
    candidate_before = signal.candidate_with_macd_score or signal.candidate_signal
    candidate_after = signal.final_signal if signal.macd_policy_changed_candidate else candidate_before
    return CounterfactualEvent.create(
        symbol=symbol,
        candidate_bar_close_time=signal.timestamp,
        next_eligible_execution_time=next_eligible_execution_time,
        candidate_without_macd_score=signal.candidate_without_macd_score,
        candidate_with_macd_score=signal.candidate_with_macd_score,
        candidate_before_policy=candidate_before,
        candidate_after_policy=candidate_after,
        original_suggested_trade_pct=original_suggested_trade_pct,
        adjusted_suggested_trade_pct=adjusted_suggested_trade_pct,
        signal_intent=signal.signal_intent,
        primary_setup_code=signal.primary_setup_code,
        risk_enforcement=signal.risk_enforcement,
        macd_score=signal.macd_score,
        macd_cross=signal.macd_cross,
        macd_zero_axis=signal.macd_zero_axis,
        macd_histogram_trend=signal.macd_histogram_trend,
        experiment_config_hash=signal.experiment_config_hash,
        macd_score_changed_candidate=signal.macd_score_changed_candidate,
        macd_policy_changed_candidate=signal.macd_policy_changed_candidate,
    )


def resolve_counterfactual_execution(
    event: CounterfactualEvent,
    *,
    next_bar: Any,
    context: CounterfactualExecutionContext,
    config: DividendTBacktestConfig,
    trade_pct: float,
) -> ExecutionResolution:
    """Apply the production execution rules at the next eligible bar open."""

    import pandas as pd

    execution_time = str(next_bar["timestamp"])
    validate_execution_after_signal(event.candidate_bar_close_time, execution_time)
    if pd.Timestamp(execution_time) != pd.Timestamp(event.next_eligible_execution_time):
        raise ValueError("COUNTERFACTUAL_NOT_NEXT_ELIGIBLE_BAR")
    if not math.isfinite(trade_pct) or trade_pct < 0.0:
        raise ValueError("counterfactual trade_pct must be finite and non-negative")
    signal = event.candidate_before_policy
    if event.event_type is CounterfactualEventType.SCORE_SUPPRESSED:
        signal = event.candidate_without_macd_score
    return resolve_execution_request(
        signal=signal,
        symbol=event.symbol,
        candidate_bar_close_time=event.candidate_bar_close_time,
        next_bar=next_bar,
        context=context,
        config=config,
        trade_pct=trade_pct,
        expected_execution_time=event.next_eligible_execution_time,
    )


def resolve_execution_request(
    *,
    signal: str | None,
    symbol: str,
    candidate_bar_close_time: str,
    next_bar: Any,
    context: CounterfactualExecutionContext,
    config: DividendTBacktestConfig,
    trade_pct: float,
    expected_execution_time: str | None = None,
) -> ExecutionResolution:
    """Resolve one offline execution with the same A-share constraints as replay.

    This is deliberately public so candidate labeling and counterfactual replay
    cannot grow separate interpretations of tradability, T+1, costs, or lots.
    """

    import pandas as pd

    execution_time = str(next_bar["timestamp"])
    validate_execution_after_signal(candidate_bar_close_time, execution_time)
    if expected_execution_time is not None and pd.Timestamp(execution_time) != pd.Timestamp(expected_execution_time):
        raise ValueError("COUNTERFACTUAL_NOT_NEXT_ELIGIBLE_BAR")
    if not math.isfinite(trade_pct) or trade_pct < 0.0:
        raise ValueError("counterfactual trade_pct must be finite and non-negative")
    constraints = _trade_execution_constraints(
        next_bar,
        symbol=symbol,
        previous_daily_close=context.previous_daily_close,
        config=config,
    )
    raw_open = float(next_bar["open"])
    normalized_signal = str(signal or "")
    buy_signals = {Signal.BUY_T.value, "BUY_BACK_REVERSE_T", "BUILD_BASE"}
    sell_signals = {
        Signal.SELL_T.value,
        Signal.CLEAR.value,
        Signal.REDUCE.value,
        Signal.STOP_T.value,
        "TAKE_PROFIT_T",
        "REDUCE_T",
        "EXIT_T",
        "REVERSE_T_SELL",
    }
    if normalized_signal in buy_signals:
        if not constraints.can_buy:
            return _blocked_counterfactual(execution_time, constraints.reason or "BUY_BLOCKED")
        buyback = normalized_signal == "BUY_BACK_REVERSE_T"
        if buyback and (context.pending_buyback_shares <= 0 or context.pending_buyback_target_price is None):
            return _blocked_counterfactual(execution_time, "BUYBACK_CONTEXT_MISSING")
        buyback_target = context.pending_buyback_target_price
        if buyback:
            if buyback_target is None:
                return _blocked_counterfactual(execution_time, "BUYBACK_CONTEXT_MISSING")
            if float(next_bar["low"]) > buyback_target:
                return _blocked_counterfactual(execution_time, "BUYBACK_TARGET_NOT_REACHED")
            raw_price = min(raw_open, buyback_target)
        else:
            raw_price = raw_open
        fill = _buy_price(raw_price, config)
        requested = context.pending_buyback_shares if buyback else context.equity_before * trade_pct / fill
        budget = min(context.equity_before * trade_pct, context.cash) if not buyback else context.cash
        shares = _floor_lot(min(requested, budget / fill, context.cash / _buy_cost_per_share(fill, config)), config.min_lot)
        if shares <= 0:
            return _blocked_counterfactual(execution_time, "CASH_OR_MIN_LOT")
        gross = fill * shares
        fee = _buy_cost(fill, shares, config) - gross
        return ExecutionResolution(
            True,
            None,
            execution_time,
            fill,
            shares,
            (fill - raw_price) * shares,
            fee,
            fee + abs((fill - raw_price) * shares),
            EXECUTION_CONSTRAINT_VERSION,
        )
    if normalized_signal in sell_signals:
        if not constraints.can_sell:
            return _blocked_counterfactual(execution_time, constraints.reason or "SELL_BLOCKED")
        reverse_t = normalized_signal == "REVERSE_T_SELL"
        if reverse_t and not _t_mode_allows_reverse_t(config):
            return _blocked_counterfactual(execution_time, "REVERSE_T_NOT_ALLOWED")
        if reverse_t and context.pending_buyback_shares > 0:
            return _blocked_counterfactual(execution_time, "PENDING_BUYBACK")
        t_total = context.t_shares or context.total_sell_shares
        t_locked = context.t_locked_shares
        total = context.base_shares + context.t_shares if context.base_shares + context.t_shares > 0 else context.total_sell_shares
        if normalized_signal in {Signal.CLEAR.value, "EXIT_T", Signal.STOP_T.value}:
            eligible = _sellable_shares(total, context.base_locked_shares + context.t_locked_shares, config=config)
        elif reverse_t:
            eligible = _sellable_shares(context.base_shares, context.base_locked_shares, config=config)
        else:
            eligible = _sellable_shares(t_total, t_locked, config=config)
            if context.t_shares <= 0 and context.total_sell_shares > 0 and config.enable_a_share_constraints and config.enable_t1:
                eligible = context.sellable_shares
        if (context.total_sell_shares > 0 or t_total > 0 or total > 0) and eligible <= 0:
            return _blocked_counterfactual(execution_time, "T1_LOCK")
        fill = _sell_price(raw_open, config)
        if config.enable_core_position_floor and not context.hard_risk_exit and context.core_position_floor_pct > 0.0:
            floor_shares = math.ceil((context.equity_before * context.core_position_floor_pct / fill) / config.min_lot) * config.min_lot
            eligible = min(eligible, max(total - floor_shares, 0))
        shares = _floor_lot(min(eligible, context.equity_before * trade_pct / fill), config.min_lot)
        if shares <= 0:
            return _blocked_counterfactual(execution_time, "CORE_POSITION_FLOOR" if eligible <= 0 else "POSITION_OR_MIN_LOT")
        gross = fill * shares
        fee = gross - _sell_proceeds(fill, shares, config)
        return ExecutionResolution(
            True,
            None,
            execution_time,
            fill,
            shares,
            (raw_open - fill) * shares,
            fee,
            fee + abs((raw_open - fill) * shares),
            EXECUTION_CONSTRAINT_VERSION,
        )
    return _blocked_counterfactual(execution_time, "UNSUPPORTED_CANDIDATE_SIGNAL")


def evaluate_sizing_counterfactual_paths(
    event: CounterfactualEvent,
    *,
    next_bar: Any,
    context: CounterfactualExecutionContext,
    config: DividendTBacktestConfig,
    forward_bars: object | None = None,
    outcome_resolver: (Callable[[CounterfactualEvent, ExecutionResolution, object], CounterfactualPathOutcome] | None) = None,
) -> CounterfactualEvent:
    """Evaluate actual adjusted sizing and its original-size counterfactual under identical execution."""

    adjusted = resolve_counterfactual_execution(
        event,
        next_bar=next_bar,
        context=context,
        config=config,
        trade_pct=event.adjusted_suggested_trade_pct,
    )
    original = resolve_counterfactual_execution(
        event,
        next_bar=next_bar,
        context=context,
        config=config,
        trade_pct=event.original_suggested_trade_pct,
    )
    if (forward_bars is None) != (outcome_resolver is None):
        raise ValueError("COUNTERFACTUAL_OUTCOME_INPUTS_INCOMPLETE")
    adjusted_outcome = outcome_resolver(event, adjusted, forward_bars) if outcome_resolver is not None and adjusted.executable else None
    original_outcome = outcome_resolver(event, original, forward_bars) if outcome_resolver is not None and original.executable else None
    return replace(
        event,
        adjusted_path_executable=adjusted.executable,
        adjusted_path_fill_price=adjusted.reference_fill_price,
        adjusted_path_shares=adjusted.shares,
        adjusted_path_slippage_amount=adjusted.slippage_amount,
        adjusted_path_fee_amount=adjusted.fee_amount,
        adjusted_path_net_pnl=adjusted_outcome.net_pnl if adjusted_outcome is not None else None,
        adjusted_path_holding_period_bars=(adjusted_outcome.holding_period_bars if adjusted_outcome is not None else None),
        adjusted_path_max_adverse_excursion=(adjusted_outcome.max_adverse_excursion if adjusted_outcome is not None else None),
        original_path_executable=original.executable,
        original_path_fill_price=original.reference_fill_price,
        original_path_shares=original.shares,
        original_path_slippage_amount=original.slippage_amount,
        original_path_fee_amount=original.fee_amount,
        original_path_net_pnl=original_outcome.net_pnl if original_outcome is not None else None,
        original_path_holding_period_bars=(original_outcome.holding_period_bars if original_outcome is not None else None),
        original_path_max_adverse_excursion=(original_outcome.max_adverse_excursion if original_outcome is not None else None),
    )


def _blocked_counterfactual(execution_time: str, reason: str) -> ExecutionResolution:
    return ExecutionResolution(False, reason, execution_time, None, 0, 0.0, 0.0, 0.0, EXECUTION_CONSTRAINT_VERSION)


class BacktestSignalCache:
    def __init__(self, path: Path, *, expected_metadata: dict[str, str] | None = None) -> None:
        self.path = path
        self.expected_metadata = expected_metadata
        self.records: dict[str, BacktestSignal] = {}
        self.dirty = False
        self.unsaved_count = 0
        self.hits = 0
        self.misses = 0
        self._load()

    @classmethod
    def for_symbol(
        cls,
        symbol: str,
        config: DividendTBacktestConfig,
        *,
        identity: MACDExperimentIdentity | None = None,
    ) -> "BacktestSignalCache | None":
        if config.signal_cache_dir is None:
            return None
        if identity is not None:
            path = signal_cache_path(Path(config.signal_cache_dir), symbol=symbol, identity=identity)
            return cls(path, expected_metadata=cache_metadata(identity))
        safe_symbol = symbol.replace(".", "_")
        safe_tag = _safe_cache_part(config.signal_cache_tag)
        path = Path(config.signal_cache_dir) / f"{safe_symbol}_mh{config.max_history_bars}_{safe_tag}_{SIGNAL_CACHE_VERSION}.csv"
        return cls(path)

    def get(self, timestamp: str) -> BacktestSignal | None:
        signal = self.records.get(timestamp)
        if signal is None:
            self.misses += 1
            return None
        self.hits += 1
        return signal

    def set(self, signal: BacktestSignal) -> None:
        self.records[signal.timestamp] = signal
        self.dirty = True
        self.unsaved_count += 1

    def save(self) -> None:
        if not self.dirty:
            return
        import pandas as pd

        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = [asdict(signal) for signal in sorted(self.records.values(), key=lambda item: item.timestamp)]
        if self.expected_metadata is not None:
            payload = [{**row, **self.expected_metadata} for row in payload]
        pd.DataFrame(payload).to_csv(self.path, index=False)
        self.dirty = False
        self.unsaved_count = 0

    def _load(self) -> None:
        if not self.path.exists():
            return
        import pandas as pd

        data = pd.read_csv(self.path)
        self._validate_metadata(data)
        required = {
            "timestamp",
            "action",
            "daily_state",
            "intraday_state",
            "position_multiplier",
            "fundamental_score",
            "base_position_limit_pct",
        }
        if not required.issubset(data.columns):
            return
        for row in data.to_dict("records"):
            timestamp = str(row["timestamp"])
            base_target = float(row.get("base_position_target_pct", min(float(row["base_position_limit_pct"]), MAX_BASE_POSITION_PCT)))
            legacy_total_cap = float(row.get("t_trade_limit_pct", 0.10))
            max_total = float(row.get("max_total_position_pct", legacy_total_cap if legacy_total_cap > 0 else base_target))
            active_cap = float(row.get("active_position_cap_pct", max(0.0, max_total - base_target)))
            self.records[timestamp] = BacktestSignal(
                timestamp=timestamp,
                action=str(row["action"]),
                daily_state=str(row["daily_state"]),
                intraday_state=str(row["intraday_state"]),
                trend_state=str(row.get("trend_state", "RANGE")),
                market_regime_state=str(row.get("market_regime_state", "RANGE_T")),
                position_multiplier=float(row["position_multiplier"]),
                fundamental_score=float(row["fundamental_score"]),
                base_position_limit_pct=float(row["base_position_limit_pct"]),
                base_position_target_pct=base_target,
                t_trade_limit_pct=legacy_total_cap,
                active_position_cap_pct=active_cap,
                max_total_position_pct=max_total,
                multi_period_score=float(row.get("multi_period_score", 50.0)),
                capital_flow_score=float(row.get("capital_flow_score", 50.0)),
                capital_flow_confirmation_score=float(row.get("capital_flow_confirmation_score", row.get("capital_flow_score", 50.0))),
                capital_flow_confirmation_state=str(row.get("capital_flow_confirmation_state", "UNCONFIRMED")),
                capital_flow_confidence=float(row.get("capital_flow_confidence", 0.0)),
                capital_flow_source_type=str(row.get("capital_flow_source_type", "UNKNOWN")),
                force_ratio=float(row.get("force_ratio", 1.0)),
                force_weighted_score=float(row.get("force_weighted_score", 50.0)),
                attention_score=float(row.get("attention_score", 50.0)),
                certainty_score=float(row.get("certainty_score", 50.0)),
                memory_score=float(row.get("memory_score", 50.0)),
                sell_pressure_score=float(row.get("sell_pressure_score", 50.0)),
                up_probability_1d=float(row.get("up_probability_1d", 0.50)),
                up_probability_3d=float(row.get("up_probability_3d", 0.50)),
                down_probability_1d=float(row.get("down_probability_1d", 0.50)),
                down_probability_3d=float(row.get("down_probability_3d", 0.50)),
                probability_state=str(row.get("probability_state", "RANGE")),
                candidate_signal=_optional_text(row.get("candidate_signal")),
                candidate_setup_code=_optional_text(row.get("candidate_setup_code")),
                primary_setup_code=_optional_text(row.get("primary_setup_code")),
                signal_intent=str(row.get("signal_intent", "NONE")),
                risk_enforcement=str(row.get("risk_enforcement", RiskEnforcement.NONE.value)),
                entry_confirmations=_cached_string_tuple(row.get("entry_confirmations"), default=("NONE",)),
                exit_confirmations=_cached_string_tuple(row.get("exit_confirmations"), default=("NONE",)),
                raw_candidate_action=str(row.get("raw_candidate_action", row["action"])),
                quality_filtered_action=str(row.get("quality_filtered_action", row["action"])),
                macd_filtered_action=str(row.get("macd_filtered_action", row["action"])),
                freshness_filtered_action=str(row.get("freshness_filtered_action", row["action"])),
                final_action=str(row.get("final_action", row["action"])),
                final_signal=str(row.get("final_signal", Signal.HOLD.value)),
                signal_downgraded=_optional_bool(row.get("signal_downgraded")),
                downgrade_source=_optional_text(row.get("downgrade_source")),
                downgrade_reason=_optional_text(row.get("downgrade_reason")),
                original_suggested_trade_pct=_optional_float(row.get("original_suggested_trade_pct")),
                macd_sizing_multiplier=float(row.get("macd_sizing_multiplier", 1.0)),
                adjusted_suggested_trade_pct=_optional_float(row.get("adjusted_suggested_trade_pct")),
                sizing_adjustment_source=_optional_text(row.get("sizing_adjustment_source")),
                macd_sizing_applied=_optional_bool(row.get("macd_sizing_applied")),
                macd_sizing_owner=_optional_text(row.get("macd_sizing_owner")),
                macd_policy_applied=_optional_bool(row.get("macd_policy_applied")),
                technical_score_without_macd=float(row.get("technical_score_without_macd", 50.0)),
                technical_score_with_macd=float(row.get("technical_score_with_macd", 50.0)),
                candidate_without_macd_score=_optional_text(row.get("candidate_without_macd_score")),
                candidate_with_macd_score=_optional_text(row.get("candidate_with_macd_score")),
                macd_score_changed_candidate=_optional_bool(row.get("macd_score_changed_candidate")),
                macd_policy_changed_candidate=_optional_bool(row.get("macd_policy_changed_candidate")),
                macd_score=float(row.get("macd_score", 50.0)),
                macd_cross=str(row.get("macd_cross", "NONE")),
                macd_zero_axis=str(row.get("macd_zero_axis", "STRADDLING")),
                macd_histogram_trend=str(row.get("macd_histogram_trend", "FLAT")),
                experiment_config_hash=_optional_text(row.get("experiment_config_hash")),
                cache_schema_version=_optional_text(row.get("cache_schema_version")),
                git_commit=_optional_text(row.get("git_commit")),
                dataset_version=_optional_text(row.get("dataset_version")),
                pipeline_id=_optional_text(row.get("pipeline_id")),
                cache_compatibility_mode=_optional_text(row.get("cache_compatibility_mode")),
                buy_point_subtype=str(row.get("buy_point_subtype", "none")),
                breakout_score=float(row.get("breakout_score", 0.0)),
                breakout_state=str(row.get("breakout_state", "NONE")),
                breakout_confirmed=_optional_bool(row.get("breakout_confirmed")),
                pre_breakout_watch=_optional_bool(row.get("pre_breakout_watch")),
                volume_price_score=float(row.get("volume_price_score", 50.0)),
                volume_price_state=str(row.get("volume_price_state", "NEUTRAL")),
                volume_breakout_score=float(row.get("volume_breakout_score", 50.0)),
                low_volume_pullback_score=float(row.get("low_volume_pullback_score", 50.0)),
                high_volume_stall_score=float(row.get("high_volume_stall_score", 0.0)),
                price_up_volume_down_score=float(row.get("price_up_volume_down_score", 0.0)),
                pretrade_volume_price_state_12=str(row.get("pretrade_volume_price_state_12", "UNKNOWN")),
                pretrade_price_return_pct_12=float(row.get("pretrade_price_return_pct_12", 0.0)),
                pretrade_volume_ratio_to_prev_12=float(row.get("pretrade_volume_ratio_to_prev_12", 1.0)),
                pretrade_volume_price_state_24=str(row.get("pretrade_volume_price_state_24", "UNKNOWN")),
                pretrade_price_return_pct_24=float(row.get("pretrade_price_return_pct_24", 0.0)),
                pretrade_volume_ratio_to_prev_24=float(row.get("pretrade_volume_ratio_to_prev_24", 1.0)),
                pretrade_volume_price_state=str(row.get("pretrade_volume_price_state", "UNKNOWN")),
                pretrade_volume_price_lookback_bars=int(float(row.get("pretrade_volume_price_lookback_bars", 0) or 0)),
                pretrade_price_return_pct=float(row.get("pretrade_price_return_pct", 0.0)),
                pretrade_volume_ratio_to_prev=float(row.get("pretrade_volume_ratio_to_prev", 1.0)),
                vwap_support_score=float(row.get("vwap_support_score", 50.0)),
                post_breakout_volume_persistence_score=float(row.get("post_breakout_volume_persistence_score", 50.0)),
                chan_score=float(row.get("chan_score", 50.0)),
                chan_structure_type=str(row.get("chan_structure_type", "insufficient")),
                chan_trend_direction=str(row.get("chan_trend_direction", "range")),
                chan_divergence_type=str(row.get("chan_divergence_type", "none")),
                chan_buy_point_type=str(row.get("chan_buy_point_type", "none")),
                chan_sell_point_type=str(row.get("chan_sell_point_type", "none")),
                chan_pivot_low=_optional_float(row.get("chan_pivot_low")),
                chan_pivot_high=_optional_float(row.get("chan_pivot_high")),
                chan_invalid_price=_optional_float(row.get("chan_invalid_price")),
                buy_signal_strength=float(row.get("buy_signal_strength", 0.0)),
                kelly_fraction=float(row.get("kelly_fraction", 0.0)),
                estimated_win_rate=float(row.get("estimated_win_rate", 0.0)),
                buy_reference_price=_optional_float(row.get("buy_reference_price")),
                sell_reference_price=_optional_float(row.get("sell_reference_price")),
                buy_back_reference_price=_optional_float(row.get("buy_back_reference_price")),
                stop_price=_optional_float(row.get("stop_price")),
                market_environment_state=str(row.get("market_environment_state", "UNFILTERED")),
                market_environment_score=float(row.get("market_environment_score", 0.0)),
                market_trend_score=float(row.get("market_trend_score", 0.0)),
                market_breadth_score=float(row.get("market_breadth_score", 0.0)),
                market_amount_score=float(row.get("market_amount_score", 0.0)),
                market_limit_structure_score=float(row.get("market_limit_structure_score", 0.0)),
                market_industry_diffusion_score=float(row.get("market_industry_diffusion_score", 0.0)),
                market_model_state_score=float(row.get("market_model_state_score", 50.0)),
                model_holding_win_rate=float(row.get("model_holding_win_rate", 0.50)),
                model_holding_profit_spread=float(row.get("model_holding_profit_spread", 0.50)),
                model_new_buy_success_rate=float(row.get("model_new_buy_success_rate", 0.50)),
            )

    def _validate_metadata(self, data: Any) -> None:
        if self.expected_metadata is None:
            return
        missing = sorted(set(self.expected_metadata) - set(data.columns))
        if missing:
            raise ValueError(f"CACHE_IDENTITY_MISSING: {','.join(missing)}")
        for key, expected in self.expected_metadata.items():
            actual_values = {str(value) for value in data[key].dropna().unique()}
            if actual_values != {expected}:
                code = "CACHE_CONFIG_HASH_MISMATCH" if key == "_experiment_config_hash" else "CACHE_IDENTITY_MISMATCH"
                raise ValueError(f"{code}: {key}")


def load_5min_bars_csv(path: str | Path, *, symbol: str | None = None) -> Any:
    return normalize_backtest_bars(load_raw_5min_bars_csv(path, symbol=symbol))


def load_5min_bars_path(path: str | Path, *, symbol: str) -> Any:
    return normalize_backtest_bars(load_raw_5min_bars_path(path, symbol=symbol))


def normalize_backtest_bars(frame: Any) -> Any:
    import pandas as pd

    required = {"symbol", "timestamp", "open", "high", "low", "close", "volume"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"backtest bars missing required fields: {', '.join(missing)}")
    data = frame.copy()
    data["timestamp"] = pd.to_datetime(data["timestamp"])
    data = data.sort_values("timestamp").reset_index(drop=True)
    if "amount" not in data.columns:
        data["amount"] = data["close"] * data["volume"]
    data["amount"] = data["amount"].fillna(data["close"] * data["volume"])
    if "source_freq" not in data.columns:
        data["source_freq"] = "5min"
    if "is_suspended" not in data.columns:
        data["is_suspended"] = False
    if "is_st" not in data.columns:
        data["is_st"] = False
    if "prev_close" not in data.columns:
        data["prev_close"] = None
    if "cash_dividend_per_share" not in data.columns:
        data["cash_dividend_per_share"] = 0.0
    if "share_bonus_ratio" not in data.columns:
        data["share_bonus_ratio"] = 0.0
    return data


def build_sample_cosco_backtest_bars() -> Any:
    """Build deterministic multi-day sample bars for local smoke tests."""
    import pandas as pd

    rows: list[dict[str, object]] = []
    sessions = [
        ("2026-05-25", 14.20, 0.004),
        ("2026-05-26", 14.38, 0.006),
        ("2026-05-27", 14.68, 0.003),
        ("2026-05-28", 15.05, -0.001),
        ("2026-05-29", 14.92, -0.006),
        ("2026-06-01", 14.60, 0.007),
    ]
    for day_index, (day, start_price, drift) in enumerate(sessions):
        base_time = pd.Timestamp(f"{day} 09:35")
        price = start_price
        for index in range(48):
            if index < 12:
                step = drift + 0.004
            elif index < 25:
                step = drift - 0.005
            elif index < 36:
                step = drift + 0.002
            else:
                step = drift - 0.003
            if day_index == 3 and index > 34:
                step -= 0.012
            if day_index == 5 and 20 <= index <= 30:
                step += 0.010
            price += step
            volume = float(900_000 + (index % 8) * 65_000)
            if index in {10, 11, 35, 36}:
                volume *= 1.8
            rows.append(
                {
                    "symbol": "601919.SH",
                    "timestamp": base_time + pd.Timedelta(minutes=5 * index),
                    "open": round(price - 0.012, 3),
                    "high": round(price + 0.036, 3),
                    "low": round(price - 0.038, 3),
                    "close": round(price, 3),
                    "volume": float(volume),
                    "amount": float(volume * price),
                    "source_freq": "5min",
                }
            )
    return pd.DataFrame(rows)


def run_cosco_dividend_t_backtest(
    bars: Any,
    *,
    config: DividendTBacktestConfig | None = None,
    engine: CoscoTimingEngine | None = None,
    market_filter: MarketEnvironmentFilter | None = None,
    experiment_identity: MACDExperimentIdentity | None = None,
    pipeline_id: str = "cosco-dividend-t-5m",
    macd_result_provider: Callable[[Any], Any] | None = None,
) -> DividendTBacktestResult:
    data = normalize_backtest_bars(bars)
    cfg = config or DividendTBacktestConfig()
    _validate_config(cfg)
    if len(data) <= cfg.min_lookback_bars + 1:
        raise ValueError("not enough 5-minute bars for lookback and next-bar execution")

    symbols = set(data["symbol"].astype(str))
    if len(symbols) != 1:
        raise ValueError(f"expected one symbol, found: {', '.join(sorted(symbols))}")
    symbol = next(iter(symbols))

    timing_engine = engine or CoscoTimingEngine()
    policy_config = getattr(timing_engine, "macd_policy_config", None)
    if experiment_identity is not None:
        if not isinstance(policy_config, MACDPolicyConfig):
            raise ValueError("EXPERIMENT_IDENTITY_REQUIRES_MACD_POLICY_CONFIG")
        validate_runtime_identity(
            experiment_identity,
            policy_config=policy_config,
            execution_config=cfg,
            expected_pipeline_id=pipeline_id,
            expected_sizing_owner="dividend_t_backtest_execution",
        )
    elif isinstance(policy_config, MACDPolicyConfig) and (policy_config.score_weight != 0.0 or policy_config.conflict_gate_enabled):
        raise ValueError("MACD_EXPERIMENT_IDENTITY_REQUIRED")
    previous_daily_closes = _previous_daily_close_by_date(data)
    first_bar = data.iloc[0]
    signal_cache = BacktestSignalCache.for_symbol(symbol, cfg, identity=experiment_identity)
    cash = float(cfg.initial_cash)
    base_entry_price = _buy_price(float(first_bar["open"]), cfg)
    base_shares = _floor_lot((cfg.initial_cash * cfg.initial_base_position_pct) / base_entry_price, cfg.min_lot)
    base_cost = _buy_cost(base_entry_price, base_shares, cfg)
    cash -= base_cost
    current_trade_date = _trade_date(first_bar["timestamp"])
    base_locked_shares = 0
    t_shares = 0
    t_locked_shares = 0
    t_cost_basis = 0.0
    breakout_t_shares = 0
    breakout_t_locked_shares = 0
    breakout_t_cost_basis = 0.0
    pending_buyback_shares = 0
    pending_reverse_proceeds = 0.0
    pending_buyback_target_price: float | None = None
    trades: list[DividendTTrade] = []
    equity_curve: list[DividendTBacktestPoint] = []
    action_counts: dict[str, int] = {}
    regime_counts: dict[str, int] = {}
    attack_counts: dict[str, int] = {}
    strategy_mode_counts: dict[str, int] = {}
    execution_block_counts: dict[str, int] = {}
    processed_corporate_action_dates: set[object] = set()
    corporate_action_count = 0
    cash_dividend_total = 0.0
    active_base_target_pct = cfg.initial_base_position_pct
    strong_regime_streak = 0
    defensive_regime_streak = 0
    non_strong_regime_streak = 0
    attack_state = ATTACK_INACTIVE
    attack_state_age = 0
    attack_confirm_streak = 0
    beta_hold_exit_confirm_streak = 0
    beta_hold_soft_exit_confirm_streak = 0
    beta_hold_distribution_confirm_streak = 0
    attack_exit_confirm_streak = 0
    attack_distribution_confirm_streak = 0
    core_position_floor_pct = 0.0
    active_peak_profit_pct = 0.0
    last_base_rebalance_index = -(10**9)
    stock_risk_on_bars_remaining = 0
    buy_t_failure_cooldown_remaining = 0
    breakout_follow_through_cooldown_remaining = 0
    risk_on_add_follow_through_cooldown_remaining = 0
    pending_breakout_follow_through_index: int | None = None
    pending_breakout_follow_through_price = 0.0
    pending_breakout_follow_through_high = 0.0
    pending_risk_on_add_follow_through_index: int | None = None
    pending_risk_on_add_follow_through_price = 0.0
    pending_risk_on_add_follow_through_high = 0.0
    model_buy_follow_success_count = 0
    model_buy_follow_failure_count = 0
    candidate_entry_start_done = not cfg.enable_candidate_entry
    candidate_entry_confirm_done = not cfg.enable_candidate_entry
    candidate_entry_hold_bars_remaining = 0
    last_action = "WARMUP"
    last_daily_state = "-"
    last_intraday_state = "-"
    last_market_regime_state = "-"
    last_point_attack_state = attack_state
    last_point_strategy_mode = cfg.strategy_mode
    last_market_environment_state = "UNFILTERED"
    last_market_environment_score = 0.0
    last_market_environment_metrics = _empty_market_environment_metrics()
    last_base_target_pct = cfg.initial_base_position_pct
    last_t_trade_limit_pct = cfg.default_buy_total_cap_pct
    last_max_total_position_pct = cfg.default_buy_total_cap_pct
    last_active_position_cap_pct = cfg.default_active_position_cap_pct
    last_core_position_floor_pct = 0.0
    last_point_signal: BacktestSignal | None = None
    signal_trace: list[BacktestSignal] = []

    for index in range(1, len(data)):
        active_position_added_this_bar = False
        if stock_risk_on_bars_remaining > 0:
            stock_risk_on_bars_remaining -= 1
        if buy_t_failure_cooldown_remaining > 0:
            buy_t_failure_cooldown_remaining -= 1
        if breakout_follow_through_cooldown_remaining > 0:
            breakout_follow_through_cooldown_remaining -= 1
        if risk_on_add_follow_through_cooldown_remaining > 0:
            risk_on_add_follow_through_cooldown_remaining -= 1
        if (
            pending_breakout_follow_through_index is not None
            and index - pending_breakout_follow_through_index >= cfg.breakout_follow_through_bars
        ):
            breakout_follow_through_confirmed = _breakout_follow_through_confirmed(
                data,
                buy_index=pending_breakout_follow_through_index,
                buy_price=pending_breakout_follow_through_price,
                buy_high=pending_breakout_follow_through_high,
                config=cfg,
            )
            if breakout_follow_through_confirmed:
                model_buy_follow_success_count += 1
            else:
                model_buy_follow_failure_count += 1
                breakout_follow_through_cooldown_remaining = max(
                    breakout_follow_through_cooldown_remaining,
                    cfg.breakout_follow_through_failure_cooldown_bars,
                )
            pending_breakout_follow_through_index = None
            pending_breakout_follow_through_price = 0.0
            pending_breakout_follow_through_high = 0.0
        if (
            pending_risk_on_add_follow_through_index is not None
            and index - pending_risk_on_add_follow_through_index >= cfg.risk_on_add_follow_through_bars
        ):
            risk_on_add_follow_through_confirmed = _risk_on_add_follow_through_confirmed(
                data,
                buy_index=pending_risk_on_add_follow_through_index,
                buy_price=pending_risk_on_add_follow_through_price,
                buy_high=pending_risk_on_add_follow_through_high,
                config=cfg,
            )
            if risk_on_add_follow_through_confirmed:
                model_buy_follow_success_count += 1
            else:
                model_buy_follow_failure_count += 1
                risk_on_add_follow_through_cooldown_remaining = max(
                    risk_on_add_follow_through_cooldown_remaining,
                    cfg.risk_on_add_follow_through_failure_cooldown_bars,
                )
            pending_risk_on_add_follow_through_index = None
            pending_risk_on_add_follow_through_price = 0.0
            pending_risk_on_add_follow_through_high = 0.0
        if t_shares <= 0:
            candidate_entry_hold_bars_remaining = 0
        elif candidate_entry_hold_bars_remaining > 0:
            candidate_entry_hold_bars_remaining -= 1
        row = data.iloc[index]
        trade_date = _trade_date(row["timestamp"])
        if cfg.enable_a_share_constraints and cfg.enable_t1 and trade_date != current_trade_date:
            base_locked_shares = 0
            t_locked_shares = 0
            breakout_t_locked_shares = 0
            current_trade_date = trade_date
        if cfg.enable_a_share_constraints and cfg.enable_dividend_adjustments and trade_date not in processed_corporate_action_dates:
            adjustment = _apply_corporate_action(
                row,
                cash=cash,
                base_shares=base_shares,
                t_shares=t_shares,
                base_locked_shares=base_locked_shares,
                t_locked_shares=t_locked_shares,
                breakout_t_shares=breakout_t_shares,
                breakout_t_locked_shares=breakout_t_locked_shares,
            )
            cash = adjustment["cash"]
            base_shares = adjustment["base_shares"]
            t_shares = adjustment["t_shares"]
            base_locked_shares = adjustment["base_locked_shares"]
            t_locked_shares = adjustment["t_locked_shares"]
            breakout_t_shares = adjustment["breakout_t_shares"]
            breakout_t_locked_shares = adjustment["breakout_t_locked_shares"]
            if adjustment["applied"]:
                corporate_action_count += 1
                cash_dividend_total += adjustment["cash_dividend"]
            processed_corporate_action_dates.add(trade_date)
        action = last_action
        daily_state = last_daily_state
        intraday_state = last_intraday_state
        market_regime_state = last_market_regime_state
        point_attack_state = last_point_attack_state
        point_strategy_mode = last_point_strategy_mode
        market_environment_state = last_market_environment_state
        market_environment_score = last_market_environment_score
        market_environment_metrics = last_market_environment_metrics
        base_target_pct = last_base_target_pct
        t_trade_limit_pct = last_t_trade_limit_pct
        max_total_position_pct = last_max_total_position_pct
        active_position_cap_pct = last_active_position_cap_pct
        point_core_position_floor_pct = last_core_position_floor_pct
        if not candidate_entry_start_done and index <= cfg.candidate_entry_start_max_bars:
            execution = data.iloc[index]
            start_market_environment = _previous_market_environment_at(
                execution["timestamp"],
                config=cfg,
                market_filter=market_filter,
            )
            start_target_pct = _candidate_entry_start_target_pct(
                config=cfg,
                market_environment=start_market_environment,
            )
            constraints = _trade_execution_constraints(
                execution,
                symbol=symbol,
                previous_daily_close=previous_daily_closes.get(_trade_date(execution["timestamp"])),
                config=cfg,
            )
            start_entry = _apply_candidate_entry_target(
                execution=execution,
                target_pct=start_target_pct,
                reason=_candidate_entry_start_reason(cfg.candidate_entry_start_target_pct, start_target_pct, start_market_environment),
                action="CANDIDATE_ENTRY_START",
                side="BUY_CANDIDATE_START",
                equity_before=_mark_to_market(cash, base_shares, t_shares, float(execution["open"])),
                cash=cash,
                base_shares=base_shares,
                t_shares=t_shares,
                t_locked_shares=t_locked_shares,
                t_cost_basis=t_cost_basis,
                breakout_t_shares=breakout_t_shares,
                breakout_t_locked_shares=breakout_t_locked_shares,
                breakout_t_cost_basis=breakout_t_cost_basis,
                constraints=constraints,
                config=cfg,
                mark_as_breakout=False,
            )
            cash = start_entry["cash"]
            t_shares = start_entry["t_shares"]
            t_locked_shares = start_entry["t_locked_shares"]
            t_cost_basis = start_entry["t_cost_basis"]
            breakout_t_shares = start_entry["breakout_t_shares"]
            breakout_t_locked_shares = start_entry["breakout_t_locked_shares"]
            breakout_t_cost_basis = start_entry["breakout_t_cost_basis"]
            if start_entry["blocked"] is not None:
                _increment_count(execution_block_counts, start_entry["blocked"])
            if start_entry["trade"] is not None:
                trades.append(start_entry["trade"])
                action_counts[start_entry["trade"].action] = action_counts.get(start_entry["trade"].action, 0) + 1
                active_position_added_this_bar = True
                candidate_entry_start_done = True
                candidate_entry_hold_bars_remaining = max(
                    candidate_entry_hold_bars_remaining,
                    cfg.candidate_entry_min_hold_bars,
                )
        elif not candidate_entry_start_done and index > cfg.candidate_entry_start_max_bars:
            candidate_entry_start_done = True

        if index >= cfg.min_lookback_bars and (index - cfg.min_lookback_bars) % cfg.signal_step_bars == 0:
            history_start = max(0, index - cfg.max_history_bars)
            history = data.iloc[history_start:index].copy()
            generated_at = history["timestamp"].iloc[-1].to_pydatetime()
            signal_key = str(history["timestamp"].iloc[-1])
            signal = signal_cache.get(signal_key) if signal_cache is not None else None
            if signal is None:
                if macd_result_provider is None:
                    snapshot = timing_engine.evaluate(
                        history,
                        require_fresh=False,
                        generated_at=generated_at,
                    )
                else:
                    snapshot = timing_engine.evaluate(
                        history,
                        require_fresh=False,
                        generated_at=generated_at,
                        macd_result=macd_result_provider(history),
                    )
                signal = BacktestSignal.from_snapshot(snapshot)
            signal = _with_pretrade_volume_price_context(signal, history, cfg)
            if experiment_identity is None:
                signal = replace(signal, cache_compatibility_mode=LEGACY_CACHE_COMPATIBILITY_MODE)
            else:
                signal = replace(
                    signal,
                    experiment_config_hash=experiment_config_hash(experiment_identity),
                    cache_schema_version=MACD_CACHE_SCHEMA_VERSION,
                    git_commit=experiment_identity.git_commit,
                    dataset_version=experiment_identity.dataset_version,
                    pipeline_id=experiment_identity.pipeline_id,
                    cache_compatibility_mode=None,
                )
            if signal_cache is not None:
                signal_cache.set(signal)
                if signal_cache.unsaved_count >= cfg.signal_cache_save_every:
                    signal_cache.save()
            market_environment = _market_environment_at(
                generated_at,
                config=cfg,
                market_filter=market_filter,
            )
            if market_environment is not None:
                model_state_metrics = _current_model_state_metrics(
                    trades=trades,
                    active_profit_pct=(
                        _active_position_profit_pct(
                            price=float(history["close"].iloc[-1]),
                            t_shares=t_shares,
                            t_cost_basis=t_cost_basis,
                        )
                        if t_shares > 0
                        else 0.0
                    ),
                    has_active_position=t_shares > 0,
                    buy_follow_success_count=model_buy_follow_success_count,
                    buy_follow_failure_count=model_buy_follow_failure_count,
                )
                market_environment = market_environment_point_with_model_state(
                    market_environment,
                    model_holding_win_rate=model_state_metrics["model_holding_win_rate"],
                    model_holding_profit_spread=model_state_metrics["model_holding_profit_spread"],
                    model_new_buy_success_rate=model_state_metrics["model_new_buy_success_rate"],
                )
                stock_risk_on_bars_remaining = _next_stock_risk_on_bars_remaining(
                    signal=signal,
                    config=cfg,
                    market_environment=market_environment,
                    current_bars=stock_risk_on_bars_remaining,
                )
                signal = _apply_market_environment_filter(
                    signal,
                    market_environment,
                    config=cfg,
                    stock_risk_on_active=stock_risk_on_bars_remaining > 0,
                )
                market_environment_state = (
                    signal.market_environment_state if signal.market_environment_state != "UNFILTERED" else market_environment.state
                )
                market_environment_score = market_environment.score
                market_environment_metrics = _market_environment_point_metrics(market_environment)
            signal_cfg = _effective_signal_config(
                cfg,
                signal=signal,
                market_environment=market_environment,
                attack_state=attack_state,
            )
            signal = _apply_risk_on_continuation_add(signal, signal_cfg)
            if signal_cfg.enable_point_hit_rate_sell_calibration:
                raise ValueError("LEGACY_POINT_HIT_RATE_CALIBRATION_FORBIDDEN")
            if _buy_t_failure_cooldown_blocks_signal(
                signal,
                signal_cfg,
                bars_remaining=buy_t_failure_cooldown_remaining,
            ):
                signal = replace(
                    signal,
                    action="WAIT_BUY_T_COOLDOWN",
                    buy_signal_strength=0.0,
                    kelly_fraction=0.0,
                )
            if _breakout_follow_through_cooldown_blocks_signal(
                signal,
                signal_cfg,
                bars_remaining=breakout_follow_through_cooldown_remaining,
                current_position_shares=base_shares + t_shares,
            ):
                signal = replace(
                    signal,
                    action="WAIT_BREAKOUT_FOLLOW_THROUGH",
                    buy_signal_strength=0.0,
                    kelly_fraction=0.0,
                )
            point_strategy_mode = signal_cfg.strategy_mode
            action = signal.action
            daily_state = signal.daily_state
            intraday_state = signal.intraday_state
            market_regime_state = signal.market_regime_state
            previous_attack_state = attack_state
            active_profit_for_state_pct = (
                _active_position_profit_pct(price=float(history["close"].iloc[-1]), t_shares=t_shares, t_cost_basis=t_cost_basis)
                if t_shares > 0
                else 0.0
            )
            active_peak_for_state_pct = max(active_peak_profit_pct, active_profit_for_state_pct)
            beta_hold_exit_risk = attack_state == ATTACK_BETA_HOLD and _beta_hold_hard_exit_signal(
                signal,
                signal_cfg,
                active_profit_pct=active_profit_for_state_pct,
                active_peak_profit_pct=active_peak_for_state_pct,
            )
            if beta_hold_exit_risk:
                beta_hold_exit_confirm_streak += 1
            else:
                beta_hold_exit_confirm_streak = 0
            beta_hold_distribution_risk = (
                attack_state == ATTACK_BETA_HOLD
                and not beta_hold_exit_risk
                and _beta_hold_distribution_reduce_signal(
                    signal,
                    signal_cfg,
                    active_profit_pct=active_profit_for_state_pct,
                    active_peak_profit_pct=active_peak_for_state_pct,
                )
            )
            if beta_hold_distribution_risk:
                beta_hold_distribution_confirm_streak += 1
            else:
                beta_hold_distribution_confirm_streak = 0
            beta_hold_soft_exit_risk = (
                attack_state == ATTACK_BETA_HOLD
                and not beta_hold_exit_risk
                and not beta_hold_distribution_risk
                and _beta_hold_soft_exit_signal(
                    signal,
                    signal_cfg,
                    active_profit_pct=active_profit_for_state_pct,
                    active_peak_profit_pct=active_peak_for_state_pct,
                )
            )
            if beta_hold_soft_exit_risk:
                beta_hold_soft_exit_confirm_streak += 1
            else:
                beta_hold_soft_exit_confirm_streak = 0
            attack_exit_risk = (
                attack_state not in {ATTACK_INACTIVE, ATTACK_BETA_HOLD}
                and _attack_exit_signal(signal, signal_cfg)
                and not _attack_hard_exit_signal(
                    signal,
                    signal_cfg,
                    active_profit_pct=active_profit_for_state_pct,
                    active_peak_profit_pct=active_peak_for_state_pct,
                )
            )
            if attack_exit_risk:
                attack_exit_confirm_streak += 1
            else:
                attack_exit_confirm_streak = 0
            attack_distribution_risk = (
                attack_state not in {ATTACK_INACTIVE, ATTACK_BETA_HOLD}
                and _offensive_volume_distribution_reduce_signal(
                    signal,
                    signal_cfg,
                    active_profit_pct=active_profit_for_state_pct,
                    active_peak_profit_pct=active_peak_for_state_pct,
                )
                and not _offensive_volume_distribution_hard_exit_signal(
                    signal,
                    signal_cfg,
                    active_profit_pct=active_profit_for_state_pct,
                    active_peak_profit_pct=active_peak_for_state_pct,
                )
            )
            if attack_distribution_risk:
                attack_distribution_confirm_streak += 1
            else:
                attack_distribution_confirm_streak = 0
            beta_hold_exit_confirmed = beta_hold_exit_confirm_streak >= max(
                1, signal_cfg.beta_hold_exit_confirm_bars
            ) or _beta_hold_catastrophic_exit_signal(
                signal,
                signal_cfg,
                active_profit_pct=active_profit_for_state_pct,
            )
            beta_hold_soft_exit_confirmed = beta_hold_soft_exit_confirm_streak >= max(1, signal_cfg.beta_hold_soft_exit_confirm_bars)
            beta_hold_distribution_confirmed = beta_hold_distribution_confirm_streak >= max(
                1, signal_cfg.beta_hold_distribution_confirm_bars
            )
            attack_exit_confirmed = attack_exit_confirm_streak >= max(1, signal_cfg.attack_exit_confirm_bars)
            attack_distribution_confirmed = attack_distribution_confirm_streak >= max(1, signal_cfg.attack_distribution_confirm_bars)
            attack_state, attack_confirm_streak = _next_attack_state(
                signal=signal,
                config=signal_cfg,
                current_state=attack_state,
                confirm_streak=attack_confirm_streak,
                state_age_bars=attack_state_age,
                active_profit_pct=active_profit_for_state_pct,
                active_peak_profit_pct=active_peak_for_state_pct,
                beta_hold_exit_confirmed=beta_hold_exit_confirmed,
                beta_hold_soft_exit_confirmed=beta_hold_soft_exit_confirmed,
                beta_hold_distribution_confirmed=beta_hold_distribution_confirmed,
                attack_exit_confirmed=attack_exit_confirmed,
                attack_distribution_confirmed=attack_distribution_confirmed,
            )
            if attack_state != ATTACK_BETA_HOLD:
                beta_hold_exit_confirm_streak = 0
                beta_hold_soft_exit_confirm_streak = 0
                beta_hold_distribution_confirm_streak = 0
            if attack_state in {ATTACK_INACTIVE, ATTACK_BETA_HOLD}:
                attack_exit_confirm_streak = 0
                attack_distribution_confirm_streak = 0
            if attack_state == previous_attack_state:
                attack_state_age = attack_state_age + 1 if attack_state != ATTACK_INACTIVE else 0
            elif attack_state == ATTACK_INACTIVE:
                attack_state_age = 0
            else:
                attack_state_age = 1
            if _beta_hold_blocks_soft_exit(
                signal=signal,
                config=signal_cfg,
                attack_state=attack_state,
                state_age_bars=attack_state_age,
                active_profit_pct=active_profit_for_state_pct,
                active_peak_profit_pct=active_peak_for_state_pct,
                beta_hold_exit_confirmed=beta_hold_exit_confirmed,
                beta_hold_soft_exit_confirmed=beta_hold_soft_exit_confirmed,
                beta_hold_distribution_confirmed=beta_hold_distribution_confirmed,
            ):
                action = "WAIT_BETA_HOLD"
                signal = replace(signal, action=action)
            point_attack_state = attack_state
            core_position_floor_pct = _next_core_position_floor_pct(
                signal=signal,
                config=signal_cfg,
                attack_state=attack_state,
                current_floor_pct=core_position_floor_pct,
                active_profit_pct=active_profit_for_state_pct,
            )
            point_core_position_floor_pct = core_position_floor_pct
            t_trade_limit_pct = _signal_t_trade_cap(signal, signal_cfg, attack_state=attack_state)
            max_total_position_pct = max(t_trade_limit_pct, core_position_floor_pct)
            strong_regime_streak = strong_regime_streak + 1 if market_regime_state == "STRONG_TREND" else 0
            defensive_regime_streak = defensive_regime_streak + 1 if market_regime_state == "DEFENSIVE" else 0
            non_strong_regime_streak = 0 if market_regime_state == "STRONG_TREND" else non_strong_regime_streak + 1
            active_base_target_pct = _next_active_base_target_pct(
                signal=signal,
                config=signal_cfg,
                current_target_pct=active_base_target_pct,
                strong_regime_streak=strong_regime_streak,
                defensive_regime_streak=defensive_regime_streak,
                non_strong_regime_streak=non_strong_regime_streak,
            )
            base_target_pct = active_base_target_pct
            max_total_position_pct = round(max(max_total_position_pct, base_target_pct), 4)
            active_position_cap_pct = round(max(0.0, max_total_position_pct - base_target_pct), 4)
            last_action = action
            last_daily_state = daily_state
            last_intraday_state = intraday_state
            last_market_regime_state = market_regime_state
            last_point_attack_state = point_attack_state
            last_point_strategy_mode = point_strategy_mode
            last_market_environment_state = market_environment_state
            last_market_environment_score = market_environment_score
            last_market_environment_metrics = market_environment_metrics
            last_base_target_pct = base_target_pct
            last_t_trade_limit_pct = t_trade_limit_pct
            last_max_total_position_pct = max_total_position_pct
            last_active_position_cap_pct = active_position_cap_pct
            last_core_position_floor_pct = point_core_position_floor_pct
            signal_trace.append(signal)
            last_point_signal = signal
            action_counts[action] = action_counts.get(action, 0) + 1
            regime_counts[market_regime_state] = regime_counts.get(market_regime_state, 0) + 1
            attack_counts[attack_state] = attack_counts.get(attack_state, 0) + 1
            strategy_mode_counts[point_strategy_mode] = strategy_mode_counts.get(point_strategy_mode, 0) + 1
            execution = data.iloc[index]
            validate_execution_after_signal(signal.timestamp, execution["timestamp"])
            constraints = _trade_execution_constraints(
                execution,
                symbol=symbol,
                previous_daily_close=previous_daily_closes.get(_trade_date(execution["timestamp"])),
                config=signal_cfg,
            )
            equity_before = _mark_to_market(cash, base_shares, t_shares, float(history["close"].iloc[-1]))
            allow_base_rebalance = index - last_base_rebalance_index >= signal_cfg.base_rebalance_cooldown_bars
            rebalance: dict[str, Any]
            if allow_base_rebalance:
                rebalance = _rebalance_base_position(
                    execution=execution,
                    signal=signal,
                    equity_before=equity_before,
                    target_pct=base_target_pct,
                    cash=cash,
                    base_shares=base_shares,
                    base_locked_shares=base_locked_shares,
                    t_shares=t_shares,
                    constraints=constraints,
                    config=signal_cfg,
                )
            else:
                rebalance = {
                    "cash": cash,
                    "base_shares": base_shares,
                    "base_locked_shares": base_locked_shares,
                    "trade": None,
                    "blocked": None,
                }
            cash = rebalance["cash"]
            base_shares = rebalance["base_shares"]
            base_locked_shares = rebalance["base_locked_shares"]
            if rebalance["blocked"] is not None:
                _increment_count(execution_block_counts, rebalance["blocked"])
            if rebalance["trade"] is not None:
                trades.append(rebalance["trade"])
                action_counts[rebalance["trade"].action] = action_counts.get(rebalance["trade"].action, 0) + 1
                last_base_rebalance_index = index
            equity_before = _mark_to_market(cash, base_shares, t_shares, float(history["close"].iloc[-1]))
            active_profit_for_candidate_hold = (
                _active_position_profit_pct(price=float(execution["open"]), t_shares=t_shares, t_cost_basis=t_cost_basis)
                if t_shares > 0
                else 0.0
            )
            candidate_entry_hold_blocks_exit = _candidate_entry_hold_blocks_exit(
                signal=signal,
                config=signal_cfg,
                bars_remaining=candidate_entry_hold_bars_remaining,
                active_profit_pct=active_profit_for_candidate_hold,
            )
            if candidate_entry_hold_blocks_exit:
                attack_reduction: dict[str, Any] = {
                    "cash": cash,
                    "t_shares": t_shares,
                    "t_locked_shares": t_locked_shares,
                    "t_cost_basis": t_cost_basis,
                    "breakout_t_shares": breakout_t_shares,
                    "breakout_t_locked_shares": breakout_t_locked_shares,
                    "breakout_t_cost_basis": breakout_t_cost_basis,
                    "trade": None,
                    "blocked": None,
                }
            else:
                attack_reduction = _reduce_attack_position(
                    previous_attack_state=previous_attack_state,
                    attack_state=attack_state,
                    action=action,
                    execution=execution,
                    equity_before=equity_before,
                    cash=cash,
                    base_shares=base_shares,
                    t_shares=t_shares,
                    t_locked_shares=t_locked_shares,
                    t_cost_basis=t_cost_basis,
                    breakout_t_shares=breakout_t_shares,
                    breakout_t_locked_shares=breakout_t_locked_shares,
                    breakout_t_cost_basis=breakout_t_cost_basis,
                    constraints=constraints,
                    config=signal_cfg,
                )
            cash = attack_reduction["cash"]
            t_shares = attack_reduction["t_shares"]
            t_locked_shares = attack_reduction["t_locked_shares"]
            t_cost_basis = attack_reduction["t_cost_basis"]
            breakout_t_shares = attack_reduction["breakout_t_shares"]
            breakout_t_locked_shares = attack_reduction["breakout_t_locked_shares"]
            breakout_t_cost_basis = attack_reduction["breakout_t_cost_basis"]
            if attack_reduction["blocked"] is not None:
                _increment_count(execution_block_counts, attack_reduction["blocked"])
            if attack_reduction["trade"] is not None:
                trades.append(attack_reduction["trade"])
                action_counts[attack_reduction["trade"].action] = action_counts.get(attack_reduction["trade"].action, 0) + 1
            equity_before = _mark_to_market(cash, base_shares, t_shares, float(history["close"].iloc[-1]))
            if t_shares > 0:
                active_peak_profit_pct = max(
                    active_peak_profit_pct,
                    _active_position_profit_pct(price=float(execution["open"]), t_shares=t_shares, t_cost_basis=t_cost_basis),
                )
            execution_action = action
            if candidate_entry_hold_blocks_exit and action in {"SELL_T_TIMING", "STOP_T_WAIT", "WAIT_DAILY_WEAK"}:
                execution_action = "WAIT_CANDIDATE_ENTRY_HOLD"
                action_counts[execution_action] = action_counts.get(execution_action, 0) + 1
            trade = _execute_action(
                action=execution_action,
                execution=execution,
                signal=signal,
                equity_before=equity_before,
                cash=cash,
                base_shares=base_shares,
                base_locked_shares=base_locked_shares,
                t_shares=t_shares,
                t_locked_shares=t_locked_shares,
                t_cost_basis=t_cost_basis,
                breakout_t_shares=breakout_t_shares,
                breakout_t_locked_shares=breakout_t_locked_shares,
                breakout_t_cost_basis=breakout_t_cost_basis,
                pending_buyback_shares=pending_buyback_shares,
                pending_reverse_proceeds=pending_reverse_proceeds,
                pending_buyback_target_price=pending_buyback_target_price,
                attack_state=attack_state,
                active_peak_profit_pct=active_peak_profit_pct,
                constraints=constraints,
                config=signal_cfg,
                core_position_floor_pct=core_position_floor_pct,
            )
            cash = trade["cash"]
            base_shares = trade["base_shares"]
            base_locked_shares = trade["base_locked_shares"]
            t_shares = trade["t_shares"]
            t_locked_shares = trade["t_locked_shares"]
            t_cost_basis = trade["t_cost_basis"]
            breakout_t_shares = trade["breakout_t_shares"]
            breakout_t_locked_shares = trade["breakout_t_locked_shares"]
            breakout_t_cost_basis = trade["breakout_t_cost_basis"]
            pending_buyback_shares = trade["pending_buyback_shares"]
            pending_reverse_proceeds = trade["pending_reverse_proceeds"]
            pending_buyback_target_price = trade["pending_buyback_target_price"]
            if trade["blocked"] is not None:
                _increment_count(execution_block_counts, trade["blocked"])
            if trade["trade"] is not None:
                trades.append(trade["trade"])
                active_position_added_this_bar = trade["trade"].side in {"BUY_T", "BUY_BREAKOUT"}
                if trade["trade"].side == "BUY_BREAKOUT":
                    pending_breakout_follow_through_index = index
                    pending_breakout_follow_through_price = float(trade["trade"].price)
                    pending_breakout_follow_through_high = float(execution["high"])
                if _buy_t_failure_cooldown_trigger_trade(trade["trade"]):
                    buy_t_failure_cooldown_remaining = max(
                        buy_t_failure_cooldown_remaining,
                        signal_cfg.buy_t_failure_cooldown_bars,
                    )
            equity_before = _mark_to_market(cash, base_shares, t_shares, float(execution["open"]))
            target_add_blocked_by_follow_through = _risk_on_add_follow_through_cooldown_blocks_target(
                bars_remaining=risk_on_add_follow_through_cooldown_remaining,
                config=signal_cfg,
            )
            if target_add_blocked_by_follow_through:
                target_add = _target_engine_state(
                    cash=cash,
                    t_shares=t_shares,
                    t_locked_shares=t_locked_shares,
                    t_cost_basis=t_cost_basis,
                    breakout_t_shares=breakout_t_shares,
                    breakout_t_locked_shares=breakout_t_locked_shares,
                    breakout_t_cost_basis=breakout_t_cost_basis,
                    trade=None,
                    blocked="RISK_ON_TARGET_FOLLOW_THROUGH_COOLDOWN",
                )
            else:
                target_add = _apply_risk_on_position_target_engine(
                    execution=execution,
                    signal=signal,
                    history=history,
                    equity_before=equity_before,
                    cash=cash,
                    base_shares=base_shares,
                    base_locked_shares=base_locked_shares,
                    t_shares=t_shares,
                    t_locked_shares=t_locked_shares,
                    t_cost_basis=t_cost_basis,
                    breakout_t_shares=breakout_t_shares,
                    breakout_t_locked_shares=breakout_t_locked_shares,
                    breakout_t_cost_basis=breakout_t_cost_basis,
                    attack_state=attack_state,
                    constraints=constraints,
                    config=signal_cfg,
                )
            cash = target_add["cash"]
            t_shares = target_add["t_shares"]
            t_locked_shares = target_add["t_locked_shares"]
            t_cost_basis = target_add["t_cost_basis"]
            breakout_t_shares = target_add["breakout_t_shares"]
            breakout_t_locked_shares = target_add["breakout_t_locked_shares"]
            breakout_t_cost_basis = target_add["breakout_t_cost_basis"]
            if target_add["blocked"] is not None:
                _increment_count(execution_block_counts, target_add["blocked"])
            if target_add["trade"] is not None:
                trades.append(target_add["trade"])
                action_counts[target_add["trade"].action] = action_counts.get(target_add["trade"].action, 0) + 1
                active_position_added_this_bar = True
                pending_risk_on_add_follow_through_index = index
                pending_risk_on_add_follow_through_price = float(target_add["trade"].price)
                pending_risk_on_add_follow_through_high = float(execution["high"])
            if not candidate_entry_confirm_done and _candidate_entry_confirm_signal(signal, signal_cfg):
                equity_before = _mark_to_market(cash, base_shares, t_shares, float(execution["open"]))
                confirm_target_pct = _candidate_entry_confirm_target_pct(signal_cfg)
                current_position_pct = ((base_shares + t_shares) * float(execution["open"]) / equity_before) if equity_before > 0 else 0.0
                if confirm_target_pct - current_position_pct < signal_cfg.risk_on_position_target_min_gap_pct:
                    candidate_entry_confirm_done = True
                else:
                    confirm_entry = _apply_candidate_entry_target(
                        execution=execution,
                        target_pct=confirm_target_pct,
                        reason=(
                            "候选池首次强趋势试探确认仓，"
                            f"目标限制 {confirm_target_pct:.0%}，"
                            f"非 force 确认 {_non_force_position_confirmation_count(signal)}，"
                            f"强度 {signal.buy_signal_strength:.1f}"
                        ),
                        action="CANDIDATE_ENTRY_CONFIRM_ADD",
                        side="BUY_CANDIDATE_CONFIRM",
                        equity_before=equity_before,
                        cash=cash,
                        base_shares=base_shares,
                        t_shares=t_shares,
                        t_locked_shares=t_locked_shares,
                        t_cost_basis=t_cost_basis,
                        breakout_t_shares=breakout_t_shares,
                        breakout_t_locked_shares=breakout_t_locked_shares,
                        breakout_t_cost_basis=breakout_t_cost_basis,
                        constraints=constraints,
                        config=signal_cfg,
                        mark_as_breakout=signal.breakout_confirmed or signal.breakout_score >= 88.0,
                    )
                    cash = confirm_entry["cash"]
                    t_shares = confirm_entry["t_shares"]
                    t_locked_shares = confirm_entry["t_locked_shares"]
                    t_cost_basis = confirm_entry["t_cost_basis"]
                    breakout_t_shares = confirm_entry["breakout_t_shares"]
                    breakout_t_locked_shares = confirm_entry["breakout_t_locked_shares"]
                    breakout_t_cost_basis = confirm_entry["breakout_t_cost_basis"]
                    if confirm_entry["blocked"] is not None:
                        _increment_count(execution_block_counts, confirm_entry["blocked"])
                    if confirm_entry["trade"] is not None:
                        trades.append(confirm_entry["trade"])
                        action_counts[confirm_entry["trade"].action] = action_counts.get(confirm_entry["trade"].action, 0) + 1
                        active_position_added_this_bar = True
                        candidate_entry_confirm_done = True
                        candidate_entry_hold_bars_remaining = max(
                            candidate_entry_hold_bars_remaining,
                            signal_cfg.candidate_entry_min_hold_bars,
                        )

        close = float(data.iloc[index]["close"])
        if t_shares <= 0:
            active_peak_profit_pct = 0.0
        else:
            close_active_profit_pct = _active_position_profit_pct(price=close, t_shares=t_shares, t_cost_basis=t_cost_basis)
            active_peak_profit_pct = (
                max(0.0, close_active_profit_pct)
                if active_position_added_this_bar
                else max(active_peak_profit_pct, close_active_profit_pct)
            )
        equity = _mark_to_market(cash, base_shares, t_shares, close)
        point_signal = last_point_signal
        equity_curve.append(
            DividendTBacktestPoint(
                timestamp=str(data.iloc[index]["timestamp"]),
                close=round(close, 3),
                equity=round(equity, 2),
                cash=round(cash, 2),
                base_shares=base_shares,
                t_shares=t_shares,
                sellable_base_shares=_sellable_shares(base_shares, base_locked_shares, config=cfg),
                sellable_t_shares=_sellable_shares(t_shares, t_locked_shares, config=cfg),
                pending_buyback_shares=pending_buyback_shares,
                pending_buyback_target_price=round(pending_buyback_target_price, 3) if pending_buyback_target_price is not None else None,
                action=action,
                daily_state=daily_state,
                intraday_state=intraday_state,
                market_regime_state=market_regime_state,
                attack_state=point_attack_state,
                strategy_mode=point_strategy_mode,
                market_environment_state=market_environment_state,
                market_environment_score=round(market_environment_score, 2),
                base_target_pct=round(base_target_pct, 4),
                t_trade_limit_pct=round(t_trade_limit_pct, 4),
                **market_environment_metrics,
                active_position_cap_pct=active_position_cap_pct,
                max_total_position_pct=round(max_total_position_pct, 4),
                core_position_floor_pct=round(point_core_position_floor_pct, 4),
                beta_hold_exit_confirm_streak=beta_hold_exit_confirm_streak,
                beta_hold_soft_exit_confirm_streak=beta_hold_soft_exit_confirm_streak,
                beta_hold_distribution_confirm_streak=beta_hold_distribution_confirm_streak,
                attack_exit_confirm_streak=attack_exit_confirm_streak,
                trend_state=str(getattr(point_signal, "trend_state", "RANGE")),
                buy_point_subtype=str(getattr(point_signal, "buy_point_subtype", "none")),
                buy_signal_strength=round(float(getattr(point_signal, "buy_signal_strength", 0.0)), 2),
                breakout_score=round(float(getattr(point_signal, "breakout_score", 0.0)), 2),
                breakout_state=str(getattr(point_signal, "breakout_state", "NONE")),
                breakout_confirmed=bool(getattr(point_signal, "breakout_confirmed", False)),
                pre_breakout_watch=bool(getattr(point_signal, "pre_breakout_watch", False)),
                volume_price_score=round(float(getattr(point_signal, "volume_price_score", 50.0)), 2),
                volume_price_state=str(getattr(point_signal, "volume_price_state", "NEUTRAL")),
                volume_breakout_score=round(float(getattr(point_signal, "volume_breakout_score", 50.0)), 2),
                post_breakout_volume_persistence_score=round(
                    float(getattr(point_signal, "post_breakout_volume_persistence_score", 50.0)),
                    2,
                ),
                vwap_support_score=round(float(getattr(point_signal, "vwap_support_score", 50.0)), 2),
                capital_flow_score=round(float(getattr(point_signal, "capital_flow_score", 50.0)), 2),
                capital_flow_confirmation_score=round(float(getattr(point_signal, "capital_flow_confirmation_score", 50.0)), 2),
                capital_flow_confirmation_state=str(getattr(point_signal, "capital_flow_confirmation_state", "UNCONFIRMED")),
                capital_flow_confidence=round(float(getattr(point_signal, "capital_flow_confidence", 0.0)), 4),
                force_weighted_score=round(float(getattr(point_signal, "force_weighted_score", 50.0)), 2),
                force_ratio=round(float(getattr(point_signal, "force_ratio", 1.0)), 4),
                sell_pressure_score=round(float(getattr(point_signal, "sell_pressure_score", 50.0)), 2),
                up_probability_1d=round(float(getattr(point_signal, "up_probability_1d", 0.50)), 4),
                up_probability_3d=round(float(getattr(point_signal, "up_probability_3d", 0.50)), 4),
                down_probability_1d=round(float(getattr(point_signal, "down_probability_1d", 0.50)), 4),
                down_probability_3d=round(float(getattr(point_signal, "down_probability_3d", 0.50)), 4),
                high_volume_stall_score=round(float(getattr(point_signal, "high_volume_stall_score", 0.0)), 2),
                price_up_volume_down_score=round(float(getattr(point_signal, "price_up_volume_down_score", 0.0)), 2),
                pretrade_volume_price_state_12=str(getattr(point_signal, "pretrade_volume_price_state_12", "UNKNOWN")),
                pretrade_price_return_pct_12=round(float(getattr(point_signal, "pretrade_price_return_pct_12", 0.0)), 6),
                pretrade_volume_ratio_to_prev_12=round(float(getattr(point_signal, "pretrade_volume_ratio_to_prev_12", 1.0)), 4),
                pretrade_volume_price_state_24=str(getattr(point_signal, "pretrade_volume_price_state_24", "UNKNOWN")),
                pretrade_price_return_pct_24=round(float(getattr(point_signal, "pretrade_price_return_pct_24", 0.0)), 6),
                pretrade_volume_ratio_to_prev_24=round(float(getattr(point_signal, "pretrade_volume_ratio_to_prev_24", 1.0)), 4),
                pretrade_volume_price_state=str(getattr(point_signal, "pretrade_volume_price_state", "UNKNOWN")),
                pretrade_volume_price_lookback_bars=int(getattr(point_signal, "pretrade_volume_price_lookback_bars", 0) or 0),
                pretrade_price_return_pct=round(float(getattr(point_signal, "pretrade_price_return_pct", 0.0)), 6),
                pretrade_volume_ratio_to_prev=round(float(getattr(point_signal, "pretrade_volume_ratio_to_prev", 1.0)), 4),
                chan_score=round(float(getattr(point_signal, "chan_score", 50.0)), 2),
                chan_buy_point_type=str(getattr(point_signal, "chan_buy_point_type", "none")),
                chan_structure_type=str(getattr(point_signal, "chan_structure_type", "insufficient")),
            )
        )

    final_equity = equity_curve[-1].equity
    total_return = final_equity / cfg.initial_cash - 1.0
    benchmark_return = float(data["close"].iloc[-1]) / float(data["open"].iloc[0]) - 1.0
    realized_values = [trade.realized_pnl for trade in trades if trade.realized_pnl is not None]
    wins = [value for value in realized_values if value > 0]
    buyback_trade_count = sum(1 for trade in trades if trade.side == "BUY_BACK_REVERSE_T")
    gate_counts = {
        key: action_counts.get(key, 0)
        for key in (
            "WAIT_DAILY_WEAK",
            "WAIT_CONFIRMATION",
            "WAIT_LATE_SESSION",
            "WAIT_STRONG_TREND",
            "WAIT_MARKET_CAUTION",
            "WAIT_BUY_T_COOLDOWN",
        )
    }
    if signal_cache is not None:
        signal_cache.save()

    return DividendTBacktestResult(
        symbol=symbol,
        start=str(data["timestamp"].iloc[0]),
        end=str(data["timestamp"].iloc[-1]),
        rows=len(data),
        config=cfg,
        initial_cash=round(cfg.initial_cash, 2),
        final_equity=round(final_equity, 2),
        total_return=round(total_return, 6),
        benchmark_return=round(benchmark_return, 6),
        excess_return=round(total_return - benchmark_return, 6),
        annualized_return=round(_annualized_return(total_return, max(len(equity_curve), 1), cfg.periods_per_year), 6),
        max_drawdown=round(_max_drawdown([point.equity for point in equity_curve]), 6),
        trade_count=len(trades),
        completed_trades=len(realized_values),
        win_rate=round(len(wins) / len(realized_values), 6) if realized_values else None,
        realized_pnl=round(sum(realized_values), 2),
        action_counts=action_counts,
        gate_counts=gate_counts,
        regime_counts=regime_counts,
        attack_counts=attack_counts,
        strategy_mode_counts=strategy_mode_counts,
        execution_block_counts=execution_block_counts,
        cache_hits=signal_cache.hits if signal_cache is not None else 0,
        cache_misses=signal_cache.misses if signal_cache is not None else 0,
        buyback_trade_count=buyback_trade_count,
        corporate_action_count=corporate_action_count,
        cash_dividend_total=round(cash_dividend_total, 2),
        trades=tuple(trades),
        equity_curve=tuple(equity_curve),
        signals=tuple(signal_trace),
    )


def format_cosco_backtest_report(result: DividendTBacktestResult, *, title: str = "中远海控长期红利做 T 回测") -> str:
    trades = "\n".join(
        f"- {trade.timestamp} {trade.action} {trade.side} {trade.shares} 股 @ {trade.price:.3f}，"
        f"realized={_fmt_money(trade.realized_pnl)}，{trade.reason}"
        for trade in result.trades[:20]
    )
    if not trades:
        trades = "- 无交易"
    gates = ", ".join(f"{key}={value}" for key, value in result.gate_counts.items())
    actions = ", ".join(f"{key}={value}" for key, value in sorted(result.action_counts.items()))
    regimes = ", ".join(f"{key}={value}" for key, value in sorted(result.regime_counts.items()))
    attacks = ", ".join(f"{key}={value}" for key, value in sorted(result.attack_counts.items()))
    strategy_modes = ", ".join(f"{key}={value}" for key, value in sorted(result.strategy_mode_counts.items()))
    execution_blocks = ", ".join(f"{key}={value}" for key, value in sorted(result.execution_block_counts.items()))
    return (
        f"# {title}\n\n"
        f"## 数据范围\n\n"
        f"- 标的：`{result.symbol}`\n"
        f"- 时间：`{result.start}` 至 `{result.end}`\n"
        f"- 频率：5 分钟\n"
        f"- 行数：{result.rows}\n\n"
        f"## 参数\n\n"
        f"- 初始资金：{result.initial_cash:,.2f}\n"
        f"- 策略模式：{result.config.strategy_mode}\n"
        f"- 市场环境过滤：{'开启' if result.config.enable_market_filter else '关闭'}（{result.config.market_filter_name}）\n"
        f"- 个股级 RISK_ON 状态机：{'开启' if result.config.enable_stock_risk_on_regime else '关闭'}；"
        f"确认后维持 {result.config.stock_risk_on_hold_bars} 根，趋势续期至少 {result.config.stock_risk_on_sustain_bars} 根\n"
        f"- RISK_ON 延续加仓：{'开启' if result.config.enable_risk_on_continuation_add else '关闭'}；"
        f"至少 {result.config.risk_on_continuation_min_confirmations} 个非 force 确认，"
        f"买入强度 ≥ {result.config.risk_on_continuation_min_strength:.1f}\n"
        f"- RISK_ON 持仓目标引擎：{'开启' if result.config.enable_risk_on_position_target_engine else '关闭'}；"
        f"至少 {result.config.risk_on_position_target_min_confirmations} 个非 force 确认，"
        f"强度 ≥ {result.config.risk_on_position_target_min_strength:.1f}，"
        f"仓位缺口 ≥ {result.config.risk_on_position_target_min_gap_pct:.1%}，"
        f"目标加仓底线 {result.config.risk_on_target_add_min_target_pct:.0%} + bonus {result.config.risk_on_target_add_bonus_pct:.0%}，"
        f"首买/低仓/中仓/高仓核心 cap {result.config.risk_on_first_add_cap_pct:.0%}/"
        f"{result.config.risk_on_low_position_add_cap_pct:.0%}/{result.config.risk_on_mid_position_add_cap_pct:.0%}，"
        f"{result.config.risk_on_high_position_reinforce_cap_pct:.0%}，"
        f"高质量突破升级目标 {result.config.risk_on_high_quality_breakout_upgrade_target_pct:.0%}，"
        f"高仓核心强化 {'开启' if result.config.enable_risk_on_high_position_reinforcement else '关闭'}，"
        f"二次加仓至少 {result.config.risk_on_secondary_add_min_confirmations} 个确认"
        f"（BETA_HOLD {result.config.risk_on_beta_hold_secondary_min_confirmations} 个），满仓需极强确认\n"
        f"- 组合层主升目标：{'开启' if result.config.enable_portfolio_main_rise_position_target else '关闭'}；"
        f"目标 {result.config.portfolio_main_rise_position_target_pct:.0%}，"
        f"模型状态 ≥ {result.config.portfolio_main_rise_min_model_state_score:.1f}，"
        f"持仓胜率/浮盈扩散/新买点成功率 ≥ "
        f"{result.config.portfolio_main_rise_min_holding_win_rate:.0%}/"
        f"{result.config.portfolio_main_rise_min_profit_spread:.0%}/"
        f"{result.config.portfolio_main_rise_min_new_buy_success_rate:.0%}\n"
        f"- RISK_ON 买后跟随确认：{result.config.risk_on_add_follow_through_bars} 根内新高 ≥ "
        f"{result.config.risk_on_add_follow_through_min_high_return_pct:.1%}，"
        f"量能 ≥ 前段均量 {result.config.risk_on_add_follow_through_volume_ratio:.0%}，"
        f"VWAP 容忍 {result.config.risk_on_add_follow_through_vwap_tolerance_pct:.1%}，"
        f"失败冷却 {result.config.risk_on_add_follow_through_failure_cooldown_bars} 根，"
        f"高位滞涨过滤 {'开启' if result.config.late_stage_stall_entry_filter_enabled else '关闭'}，"
        f"量价延续窗口 {result.config.volume_price_continuation_lookback_bars} 根，"
        f"价涨量缩延续阈值 {result.config.volume_price_continuation_min_return_pct:.1%}/"
        f"{result.config.volume_price_continuation_max_volume_ratio:.0%}\n"
        f"- 12/24bar 买点量价过滤：{'开启' if result.config.enable_buy_volume_price_window_filter else '关闭'}；"
        f"窗口 {result.config.buy_volume_price_short_lookback_bars}/{result.config.buy_volume_price_mid_lookback_bars} 根，"
        f"最小涨幅 {result.config.buy_volume_price_filter_min_return_pct:.1%}，"
        f"缩量阈值 {result.config.buy_volume_price_filter_max_contract_ratio:.0%}，"
        f"质量底线 {result.config.buy_volume_price_filter_min_quality_score:.2f}\n"
        f"- 主升买点过滤：买点质量 ≥ {result.config.min_buy_point_quality_score:.2f}，"
        f"主升质量 ≥ {result.config.min_main_rise_buy_quality_score:.2f}，"
        f"RISK_ON 加仓主升质量 ≥ {result.config.min_risk_on_add_main_rise_quality_score:.2f}，"
        f"BUY_T 失败冷却 {result.config.buy_t_failure_cooldown_bars} 根\n"
        f"- 候选池入选建仓：{'开启' if result.config.enable_candidate_entry else '关闭'}；"
        f"验证期启动目标 {result.config.candidate_entry_start_target_pct:.0%}，"
        f"启动仓市场折扣 {'开启' if result.config.candidate_entry_start_respect_market_cap else '关闭'}，"
        f"启动窗口 {result.config.candidate_entry_start_max_bars} 根，"
        f"首次强趋势确认目标 {result.config.candidate_entry_confirm_target_pct:.0%}，"
        f"试探上限 {result.config.candidate_entry_confirm_probe_target_pct:.0%}，"
        f"跟随确认 {'开启' if result.config.candidate_entry_confirm_requires_follow_through else '关闭'}，"
        f"确认强度 ≥ {result.config.candidate_entry_confirm_min_strength:.1f}，"
        f"非 force 确认 ≥ {result.config.candidate_entry_confirm_min_confirmations}，"
        f"保护持有 {result.config.candidate_entry_min_hold_bars} 根，"
        f"硬止损 {result.config.candidate_entry_hard_stop_loss_pct:.0%}\n"
        f"- A 股成交约束：{'开启' if result.config.enable_a_share_constraints else '关闭'}；"
        f"T+1={'开启' if result.config.enable_t1 else '关闭'}，"
        f"涨跌停={'开启' if result.config.enable_limit_price_constraints else '关闭'}，"
        f"停牌={'开启' if result.config.enable_suspension_constraints else '关闭'}，"
        f"除权除息={'开启' if result.config.enable_dividend_adjustments else '关闭'}\n"
        f"- 防守/震荡初始底仓比例：{result.config.initial_base_position_pct:.0%}\n"
        f"- T 仓对比模式：{result.config.t_position_mode}\n"
        f"- T_SELL 执行：{'开启' if result.config.enable_t_sell else '关闭'}；关闭时普通 T 卖和倒 T 卖只计信号、不执行\n"
        f"- 底仓目标上限：{result.config.strong_trend_base_position_pct:.0%}\n"
        f"- 全局最大总仓位硬上限：{result.config.max_signal_position_pct:.0%}\n"
        f"- 强趋势/趋势观察/震荡目标上限：{result.config.strong_trend_signal_position_pct:.0%} / "
        f"{result.config.trend_watch_signal_position_pct:.0%} / {result.config.range_signal_position_pct:.0%}\n"
        f"- 进攻状态机：{'开启' if result.config.enable_attack_state_machine else '关闭'}；"
        f"预警 {result.config.attack_watch_position_pct:.0%} / 确认 {result.config.attack_confirm_position_pct:.0%} / 满攻 {result.config.attack_full_position_pct:.0%}\n"
        f"- 满攻触发：突破分 ≥ {result.config.attack_confirm_min_breakout_score:.1f}，买入强度 ≥ {result.config.attack_confirm_min_buy_strength:.1f}，确认 {result.config.attack_full_confirm_signals} 次\n"
        f"- 进攻仓降仓冷却：{result.config.attack_min_hold_bars} 根 5 分钟 K 线；"
        f"趋势跟随持有冷却：{result.config.trend_follow_min_hold_bars} 根；"
        f"硬退出卖压 ≥ {result.config.attack_hard_exit_sell_pressure_score:.1f}，硬退出下跌概率 ≥ {result.config.attack_hard_exit_down_probability:.0%}\n"
        f"- 进攻退出：卖压 ≥ {result.config.attack_exit_sell_pressure_score:.1f}，"
        f"{'或买卖力比 < ' + f'{result.config.attack_exit_force_ratio:.2f}，' if result.config.attack_exit_force_ratio > 0 else ''}"
        f"或 1 日下跌概率 ≥ {result.config.attack_exit_down_probability:.0%}\n"
        f"- 进攻持仓延展：{'开启' if result.config.offensive_hold_extension_enabled else '关闭'}；"
        f"普通卖点降仓 {result.config.offensive_soft_exit_sell_fraction:.0%}，"
        f"软止损降仓 {result.config.offensive_soft_stop_sell_fraction:.0%}，"
        f"软止损容忍浮亏 {result.config.offensive_stop_hold_loss_pct:.1%}\n"
        f"- 趋势确认加仓下限：确认 {result.config.offensive_trend_add_floor_pct:.0%} / 强确认 {result.config.offensive_full_add_floor_pct:.0%}\n"
        f"- 分层移动止盈：{'开启' if result.config.offensive_trailing_profit_enabled else '关闭'}；"
        f"触发/中/高 {result.config.offensive_trailing_profit_trigger_pct:.1%} / "
        f"{result.config.offensive_trailing_profit_mid_pct:.1%} / {result.config.offensive_trailing_profit_high_pct:.1%}，"
        f"回撤 {result.config.offensive_trailing_pullback_pct:.1%} / "
        f"{result.config.offensive_trailing_pullback_mid_pct:.1%} / {result.config.offensive_trailing_pullback_high_pct:.1%}，"
        f"主升 continuation 放宽 {result.config.offensive_beta_trend_pullback_multiplier:.2f}x\n"
        f"- 进攻量价分歧降仓：{'开启' if result.config.offensive_volume_distribution_enabled else '关闭'}；"
        f"放量滞涨 ≥ {result.config.offensive_volume_stall_reduce_score:.1f} / "
        f"价涨量缩 ≥ {result.config.offensive_price_up_volume_down_reduce_score:.1f} 时降级，"
        f"当前浮盈 ≥ {result.config.offensive_volume_distribution_min_profit_pct:.1%} 或峰值浮盈 ≥ {result.config.offensive_volume_distribution_min_peak_profit_pct:.1%}，"
        f"承接 VWAP/量能持续 ≥ {result.config.offensive_volume_distribution_absorption_vwap_score:.1f}/"
        f"{result.config.offensive_volume_distribution_absorption_persistence_score:.1f} 先豁免，"
        f"低承接 VWAP/量能持续 < {result.config.offensive_volume_distribution_low_vwap_score:.1f}/"
        f"{result.config.offensive_volume_distribution_low_persistence_score:.1f}，"
        f"强分歧卖出 {result.config.offensive_volume_distribution_hard_sell_fraction:.0%}\n"
        f"- 单次底仓再平衡步长：{result.config.base_rebalance_step_pct:.0%}\n"
        f"- 底仓再平衡冷却：{result.config.base_rebalance_cooldown_bars} 根 5 分钟 K 线\n"
        f"- 强趋势确认次数：{result.config.strong_trend_confirm_signals}\n"
        f"- 趋势退出确认次数：{result.config.trend_exit_confirm_signals}\n"
        f"- 防守确认次数：{result.config.defensive_confirm_signals}\n"
        f"- 默认买入后总仓位上限：{result.config.default_buy_total_cap_pct:.0%}（legacy `t_trade_pct`）\n"
        f"- 默认主动增量上限：{result.config.default_active_position_cap_pct:.0%}（总仓位上限 - 初始底仓）\n"
        f"- 最小主动试探增量：{result.config.min_t_trade_pct:.0%}\n"
        f"- Kelly 折扣：{result.config.kelly_fraction_scale:.0%}\n"
        f"- 最低买入强度：{result.config.min_buy_signal_strength:.1f}\n"
        f"- 倒 T 闭环：{'开启' if result.config.allow_reverse_t else '关闭'}\n"
        f"- 突破仓利润保护：{'开启' if result.config.enable_profit_protection else '关闭'}，触发浮盈 {result.config.profit_protect_trigger_pct:.1%}，卖出比例 {result.config.profit_protect_sell_fraction:.0%}\n"
        f"- 手续费：{result.config.commission_rate:.4%}\n"
        f"- 印花税：{result.config.stamp_duty_rate:.4%}\n"
        f"- 滑点：{result.config.slippage_bps:.1f} bps\n"
        f"- 最小回看：{result.config.min_lookback_bars} 根 5 分钟 K 线\n\n"
        f"## 结果\n\n"
        f"- 期末权益：{result.final_equity:,.2f}\n"
        f"- 总收益：{result.total_return:.2%}\n"
        f"- 买入持有基准收益：{result.benchmark_return:.2%}\n"
        f"- 超额收益：{result.excess_return:.2%}\n"
        f"- 年化收益：{result.annualized_return:.2%}\n"
        f"- 最大回撤：{result.max_drawdown:.2%}\n"
        f"- 交易次数：{result.trade_count}\n"
        f"- 完成交易：{result.completed_trades}\n"
        f"- 胜率：{_fmt_pct(result.win_rate)}\n"
        f"- 已实现 T 收益：{result.realized_pnl:,.2f}\n\n"
        f"- 现金分红调整：{result.cash_dividend_total:,.2f}（事件 {result.corporate_action_count} 次）\n\n"
        f"## 信号统计\n\n"
        f"- 动作分布：{actions or '无'}\n"
        f"- 行情状态分布：{regimes or '无'}\n"
        f"- 进攻状态分布：{attacks or '无'}\n"
        f"- 策略模式分布：{strategy_modes or result.config.strategy_mode}\n"
        f"- 成交约束拦截：{execution_blocks or '无'}\n"
        f"- 时间尺度门控：{gates}\n\n"
        f"## 交易明细\n\n"
        f"{trades}\n\n"
        f"## 解释\n\n"
        f"- 本回测使用上一根 5 分钟 K 线生成信号，下一根 K 线开盘执行，避免未来函数。\n"
        f"- 默认启用 A 股成交约束：当日新买入股票按 T+1 锁定，涨停价不买入、跌停价不卖出，停牌或零成交量 K 线不成交。\n"
        f"- 除权除息只在行情数据提供 `cash_dividend_per_share` / `share_bonus_ratio` 字段时调整；普通分钟 CSV 缺少这些字段时仍可能低估除息日表现。\n"
        f"- `WAIT_DAILY_WEAK`、`WAIT_CONFIRMATION`、`WAIT_LATE_SESSION` 是时间尺度门控，用于避免把盘中价格触达误判为可隔夜买回。\n"
        f"- `WAIT_STRONG_TREND` 是强趋势保护，用于避免在日线和 5 分钟仍强时过早倒 T。\n"
        f"- `WAIT_MARKET_CAUTION` 是市场环境过滤，用于在组合代理行情偏弱时拦截非强买点。\n"
        f"- 缠论结构门已进入回测：三买可提高进攻状态和仓位分层，三卖/跌破中枢会触发主动仓位退出。\n"
        f"- 底仓长期控制在 10% 以下；BUY 信号按强度分层、Kelly 和进攻状态机将总仓位最高提升到 100%，SELL/STOP 信号卖出主动仓位。\n"
        f"- 进攻状态机进入 `FULL_ATTACK` 后，突破买入可使用接近 100% 的账户资金；退出条件触发后，重新降回低底仓。\n"
        f"- 倒 T 闭环开启时，SELL_T 可卖出已有底仓并等待买回；突破仓盈利后若买卖力转弱，会先卖出部分突破 T 仓锁定利润。\n"
        f"- 该结果只用于研究模型规则，不代表真实下单表现。\n"
    )


def _rebalance_base_position(
    *,
    execution: Any,
    signal: BacktestSignal,
    equity_before: float,
    target_pct: float,
    cash: float,
    base_shares: int,
    base_locked_shares: int,
    t_shares: int,
    constraints: TradeExecutionConstraints,
    config: DividendTBacktestConfig,
) -> dict[str, Any]:
    price = float(execution["open"])
    timestamp = str(execution["timestamp"])
    close_for_mark = float(execution["close"])
    current_base_pct = (base_shares * price / equity_before) if equity_before > 0 else 0.0
    trade: DividendTTrade | None = None
    blocked: str | None = None

    if target_pct > current_base_pct + config.base_rebalance_threshold_pct:
        if not _base_rebalance_buy_quality_allows(signal, config):
            return {
                "cash": cash,
                "base_shares": base_shares,
                "base_locked_shares": base_locked_shares,
                "trade": trade,
                "blocked": "REBALANCE_BASE_UP_LOW_QUALITY",
            }
        if not constraints.can_buy:
            return {
                "cash": cash,
                "base_shares": base_shares,
                "base_locked_shares": base_locked_shares,
                "trade": trade,
                "blocked": _block_key("REBALANCE_BASE_UP", constraints),
            }
        buy_price = _buy_price(price, config)
        gap_pct = min(target_pct - current_base_pct, config.base_rebalance_step_pct)
        target_notional = equity_before * gap_pct
        shares = _floor_lot(min(target_notional / buy_price, cash / _buy_cost_per_share(buy_price, config)), config.min_lot)
        if shares > 0:
            cost = _buy_cost(buy_price, shares, config)
            cash -= cost
            base_shares += shares
            if config.enable_a_share_constraints and config.enable_t1:
                base_locked_shares += shares
            trade = _trade(
                timestamp,
                "REBALANCE_BASE_UP",
                "BUY_BASE_TREND",
                shares,
                buy_price,
                cash,
                base_shares,
                t_shares,
                close_for_mark,
                f"{signal.market_regime_state} 底仓上调，目标 {target_pct:.0%}",
                None,
            )
    elif current_base_pct > target_pct + config.base_rebalance_threshold_pct:
        if _base_rebalance_sell_quality_holds(signal, config):
            return {
                "cash": cash,
                "base_shares": base_shares,
                "base_locked_shares": base_locked_shares,
                "trade": trade,
                "blocked": "REBALANCE_BASE_DOWN_TREND_HOLD",
            }
        if not constraints.can_sell:
            return {
                "cash": cash,
                "base_shares": base_shares,
                "base_locked_shares": base_locked_shares,
                "trade": trade,
                "blocked": _block_key("REBALANCE_BASE_DOWN", constraints),
            }
        sell_price = _sell_price(price, config)
        gap_pct = min(current_base_pct - target_pct, config.base_rebalance_step_pct)
        target_notional = equity_before * gap_pct
        sellable_base_shares = _sellable_shares(base_shares, base_locked_shares, config=config)
        shares = _floor_lot(min(sellable_base_shares, target_notional / sell_price), config.min_lot)
        if shares <= 0 and base_shares > 0:
            blocked = "REBALANCE_BASE_DOWN_T1_LOCK"
        if shares > 0:
            proceeds = _sell_proceeds(sell_price, shares, config)
            cash += proceeds
            base_shares -= shares
            trade = _trade(
                timestamp,
                "REBALANCE_BASE_DOWN",
                "SELL_BASE_REGIME",
                shares,
                sell_price,
                cash,
                base_shares,
                t_shares,
                close_for_mark,
                f"{signal.market_regime_state} 底仓下调，目标 {target_pct:.0%}",
                None,
            )

    return {
        "cash": cash,
        "base_shares": base_shares,
        "base_locked_shares": base_locked_shares,
        "trade": trade,
        "blocked": blocked,
    }


def _apply_risk_on_position_target_engine(
    *,
    execution: Any,
    signal: BacktestSignal,
    history: Any | None = None,
    equity_before: float,
    cash: float,
    base_shares: int,
    base_locked_shares: int,
    t_shares: int,
    t_locked_shares: int,
    t_cost_basis: float,
    breakout_t_shares: int,
    breakout_t_locked_shares: int,
    breakout_t_cost_basis: float,
    attack_state: str,
    constraints: TradeExecutionConstraints,
    config: DividendTBacktestConfig,
) -> dict[str, Any]:
    trade: DividendTTrade | None = None
    blocked: str | None = None
    price = float(execution["open"])
    if price <= 0 or equity_before <= 0:
        return _target_engine_state(
            cash=cash,
            t_shares=t_shares,
            t_locked_shares=t_locked_shares,
            t_cost_basis=t_cost_basis,
            breakout_t_shares=breakout_t_shares,
            breakout_t_locked_shares=breakout_t_locked_shares,
            breakout_t_cost_basis=breakout_t_cost_basis,
            trade=trade,
            blocked=blocked,
        )
    current_position_pct = ((base_shares + t_shares) * price / equity_before) if equity_before > 0 else 0.0
    target_pct = _risk_on_position_target_pct(
        signal,
        config,
        attack_state=attack_state,
        current_position_pct=current_position_pct,
    )
    if target_pct <= 0:
        return _target_engine_state(
            cash=cash,
            t_shares=t_shares,
            t_locked_shares=t_locked_shares,
            t_cost_basis=t_cost_basis,
            breakout_t_shares=breakout_t_shares,
            breakout_t_locked_shares=breakout_t_locked_shares,
            breakout_t_cost_basis=breakout_t_cost_basis,
            trade=trade,
            blocked=blocked,
        )
    gap_pct = max(target_pct - current_position_pct, 0.0)
    if gap_pct < config.risk_on_position_target_min_gap_pct:
        return _target_engine_state(
            cash=cash,
            t_shares=t_shares,
            t_locked_shares=t_locked_shares,
            t_cost_basis=t_cost_basis,
            breakout_t_shares=breakout_t_shares,
            breakout_t_locked_shares=breakout_t_locked_shares,
            breakout_t_cost_basis=breakout_t_cost_basis,
            trade=trade,
            blocked=blocked,
        )
    if _late_stage_stall_entry_blocks(history, execution=execution, signal=signal, config=config):
        return _target_engine_state(
            cash=cash,
            t_shares=t_shares,
            t_locked_shares=t_locked_shares,
            t_cost_basis=t_cost_basis,
            breakout_t_shares=breakout_t_shares,
            breakout_t_locked_shares=breakout_t_locked_shares,
            breakout_t_cost_basis=breakout_t_cost_basis,
            trade=trade,
            blocked="RISK_ON_LATE_STAGE_STALL_ENTRY",
        )
    if not constraints.can_buy:
        return _target_engine_state(
            cash=cash,
            t_shares=t_shares,
            t_locked_shares=t_locked_shares,
            t_cost_basis=t_cost_basis,
            breakout_t_shares=breakout_t_shares,
            breakout_t_locked_shares=breakout_t_locked_shares,
            breakout_t_cost_basis=breakout_t_cost_basis,
            trade=trade,
            blocked=_block_key("RISK_ON_TARGET_ADD", constraints),
        )

    buy_price = _buy_price(price, config)
    target_notional = equity_before * gap_pct
    shares = _floor_lot(min(target_notional / buy_price, cash / _buy_cost_per_share(buy_price, config)), config.min_lot)
    if shares <= 0:
        return _target_engine_state(
            cash=cash,
            t_shares=t_shares,
            t_locked_shares=t_locked_shares,
            t_cost_basis=t_cost_basis,
            breakout_t_shares=breakout_t_shares,
            breakout_t_locked_shares=breakout_t_locked_shares,
            breakout_t_cost_basis=breakout_t_cost_basis,
            trade=trade,
            blocked=blocked,
        )

    cost = _buy_cost(buy_price, shares, config)
    cash -= cost
    t_shares += shares
    t_cost_basis += cost
    if config.enable_a_share_constraints and config.enable_t1:
        t_locked_shares += shares
    if signal.breakout_confirmed or signal.breakout_score >= 88.0:
        breakout_t_shares += shares
        breakout_t_cost_basis += cost
        if config.enable_a_share_constraints and config.enable_t1:
            breakout_t_locked_shares += shares
    trade = _trade(
        str(execution["timestamp"]),
        "RISK_ON_TARGET_ADD",
        "BUY_RISK_ON_TARGET",
        shares,
        buy_price,
        cash,
        base_shares,
        t_shares,
        float(execution["close"]),
        (
            f"RISK_ON 持仓目标引擎补仓，目标 {target_pct:.1%}，"
            f"当前 {current_position_pct:.1%}，非 force 确认 {_non_force_position_confirmation_count(signal)}，"
            f"量价质量 {_risk_on_volume_price_quality(signal):.2f}，"
            f"分段 {_risk_on_position_stage_label(signal, current_position_pct=current_position_pct, config=config, attack_state=attack_state)}"
        ),
        None,
    )
    return _target_engine_state(
        cash=cash,
        t_shares=t_shares,
        t_locked_shares=t_locked_shares,
        t_cost_basis=t_cost_basis,
        breakout_t_shares=breakout_t_shares,
        breakout_t_locked_shares=breakout_t_locked_shares,
        breakout_t_cost_basis=breakout_t_cost_basis,
        trade=trade,
        blocked=blocked,
    )


def _apply_candidate_entry_target(
    *,
    execution: Any,
    target_pct: float,
    reason: str,
    action: str,
    side: str,
    equity_before: float,
    cash: float,
    base_shares: int,
    t_shares: int,
    t_locked_shares: int,
    t_cost_basis: float,
    breakout_t_shares: int,
    breakout_t_locked_shares: int,
    breakout_t_cost_basis: float,
    constraints: TradeExecutionConstraints,
    config: DividendTBacktestConfig,
    mark_as_breakout: bool,
) -> dict[str, Any]:
    trade: DividendTTrade | None = None
    blocked: str | None = None
    price = float(execution["open"])
    if not config.enable_candidate_entry or target_pct <= 0 or price <= 0 or equity_before <= 0:
        return _target_engine_state(
            cash=cash,
            t_shares=t_shares,
            t_locked_shares=t_locked_shares,
            t_cost_basis=t_cost_basis,
            breakout_t_shares=breakout_t_shares,
            breakout_t_locked_shares=breakout_t_locked_shares,
            breakout_t_cost_basis=breakout_t_cost_basis,
            trade=trade,
            blocked=blocked,
        )
    target_pct = round(clamp(target_pct, config.initial_base_position_pct, config.max_signal_position_pct), 4)
    current_position_pct = ((base_shares + t_shares) * price / equity_before) if equity_before > 0 else 0.0
    gap_pct = max(target_pct - current_position_pct, 0.0)
    if gap_pct < config.risk_on_position_target_min_gap_pct:
        return _target_engine_state(
            cash=cash,
            t_shares=t_shares,
            t_locked_shares=t_locked_shares,
            t_cost_basis=t_cost_basis,
            breakout_t_shares=breakout_t_shares,
            breakout_t_locked_shares=breakout_t_locked_shares,
            breakout_t_cost_basis=breakout_t_cost_basis,
            trade=trade,
            blocked=blocked,
        )
    if not constraints.can_buy:
        return _target_engine_state(
            cash=cash,
            t_shares=t_shares,
            t_locked_shares=t_locked_shares,
            t_cost_basis=t_cost_basis,
            breakout_t_shares=breakout_t_shares,
            breakout_t_locked_shares=breakout_t_locked_shares,
            breakout_t_cost_basis=breakout_t_cost_basis,
            trade=trade,
            blocked=_block_key(action, constraints),
        )

    buy_price = _buy_price(price, config)
    target_notional = equity_before * gap_pct
    shares = _floor_lot(min(target_notional / buy_price, cash / _buy_cost_per_share(buy_price, config)), config.min_lot)
    if shares <= 0:
        return _target_engine_state(
            cash=cash,
            t_shares=t_shares,
            t_locked_shares=t_locked_shares,
            t_cost_basis=t_cost_basis,
            breakout_t_shares=breakout_t_shares,
            breakout_t_locked_shares=breakout_t_locked_shares,
            breakout_t_cost_basis=breakout_t_cost_basis,
            trade=trade,
            blocked=blocked,
        )

    cost = _buy_cost(buy_price, shares, config)
    cash -= cost
    t_shares += shares
    t_cost_basis += cost
    if config.enable_a_share_constraints and config.enable_t1:
        t_locked_shares += shares
    if mark_as_breakout:
        breakout_t_shares += shares
        breakout_t_cost_basis += cost
        if config.enable_a_share_constraints and config.enable_t1:
            breakout_t_locked_shares += shares
    trade = _trade(
        str(execution["timestamp"]),
        action,
        side,
        shares,
        buy_price,
        cash,
        base_shares,
        t_shares,
        float(execution["close"]),
        f"{reason}，目标总仓位 {target_pct:.1%}，当前 {current_position_pct:.1%}",
        None,
    )
    return _target_engine_state(
        cash=cash,
        t_shares=t_shares,
        t_locked_shares=t_locked_shares,
        t_cost_basis=t_cost_basis,
        breakout_t_shares=breakout_t_shares,
        breakout_t_locked_shares=breakout_t_locked_shares,
        breakout_t_cost_basis=breakout_t_cost_basis,
        trade=trade,
        blocked=blocked,
    )


def _candidate_entry_start_target_pct(
    *,
    config: DividendTBacktestConfig,
    market_environment: MarketEnvironmentPoint | None,
) -> float:
    target_pct = config.candidate_entry_start_target_pct
    if not config.candidate_entry_start_respect_market_cap or market_environment is None:
        return target_pct
    market_cap = max(config.candidate_entry_start_min_market_cap_pct, market_environment.max_total_position_pct)
    return min(target_pct, market_cap)


def _candidate_entry_start_reason(
    configured_target_pct: float,
    effective_target_pct: float,
    market_environment: MarketEnvironmentPoint | None,
) -> str:
    if market_environment is None or abs(effective_target_pct - configured_target_pct) < 1e-9:
        return "候选池验证期启动仓，避免等待滞后信号错过主升段"
    return f"候选池验证期启动仓，市场环境{market_environment.state}先降到{effective_target_pct:.0%}，等待个股强确认再加仓"


def _target_engine_state(
    *,
    cash: float,
    t_shares: int,
    t_locked_shares: int,
    t_cost_basis: float,
    breakout_t_shares: int,
    breakout_t_locked_shares: int,
    breakout_t_cost_basis: float,
    trade: DividendTTrade | None,
    blocked: str | None,
) -> dict[str, Any]:
    return {
        "cash": cash,
        "t_shares": t_shares,
        "t_locked_shares": t_locked_shares,
        "t_cost_basis": max(t_cost_basis, 0.0),
        "breakout_t_shares": breakout_t_shares,
        "breakout_t_locked_shares": breakout_t_locked_shares,
        "breakout_t_cost_basis": max(breakout_t_cost_basis, 0.0),
        "trade": trade,
        "blocked": blocked,
    }


def _reduce_attack_position(
    *,
    previous_attack_state: str,
    attack_state: str,
    action: str,
    execution: Any,
    equity_before: float,
    cash: float,
    base_shares: int,
    t_shares: int,
    t_locked_shares: int,
    t_cost_basis: float,
    breakout_t_shares: int,
    breakout_t_locked_shares: int,
    breakout_t_cost_basis: float,
    constraints: TradeExecutionConstraints,
    config: DividendTBacktestConfig,
    core_position_floor_pct: float = 0.0,
) -> dict[str, Any]:
    trade: DividendTTrade | None = None
    if _attack_rank(attack_state) >= _attack_rank(previous_attack_state):
        return {
            "cash": cash,
            "t_shares": t_shares,
            "t_locked_shares": t_locked_shares,
            "t_cost_basis": t_cost_basis,
            "breakout_t_shares": breakout_t_shares,
            "breakout_t_locked_shares": breakout_t_locked_shares,
            "breakout_t_cost_basis": breakout_t_cost_basis,
            "trade": trade,
            "blocked": None,
        }
    if action in {"SELL_T_TIMING", "STOP_T_WAIT", "WAIT_DAILY_WEAK"} or t_shares <= 0:
        return {
            "cash": cash,
            "t_shares": t_shares,
            "t_locked_shares": t_locked_shares,
            "t_cost_basis": t_cost_basis,
            "breakout_t_shares": breakout_t_shares,
            "breakout_t_locked_shares": breakout_t_locked_shares,
            "breakout_t_cost_basis": breakout_t_cost_basis,
            "trade": trade,
            "blocked": None,
        }
    if not constraints.can_sell:
        return {
            "cash": cash,
            "t_shares": t_shares,
            "t_locked_shares": t_locked_shares,
            "t_cost_basis": t_cost_basis,
            "breakout_t_shares": breakout_t_shares,
            "breakout_t_locked_shares": breakout_t_locked_shares,
            "breakout_t_cost_basis": breakout_t_cost_basis,
            "trade": trade,
            "blocked": _block_key("REDUCE_ATTACK_POSITION", constraints),
        }

    price = float(execution["open"])
    close_for_mark = float(execution["close"])
    timestamp = str(execution["timestamp"])
    target_pct = max(_attack_position_floor_pct(attack_state, config), core_position_floor_pct)
    current_total_shares = base_shares + t_shares
    target_total_shares = (equity_before * target_pct) / price if price > 0 else current_total_shares
    excess_shares = max(current_total_shares - target_total_shares, 0.0)
    sellable_t_shares = _sellable_shares(t_shares, t_locked_shares, config=config)
    shares = _floor_lot(min(sellable_t_shares, excess_shares), config.min_lot)
    if attack_state == ATTACK_INACTIVE and core_position_floor_pct <= 0.0 and shares <= 0:
        shares = sellable_t_shares
    if shares <= 0:
        return {
            "cash": cash,
            "t_shares": t_shares,
            "t_locked_shares": t_locked_shares,
            "t_cost_basis": t_cost_basis,
            "breakout_t_shares": breakout_t_shares,
            "breakout_t_locked_shares": breakout_t_locked_shares,
            "breakout_t_cost_basis": breakout_t_cost_basis,
            "trade": trade,
            "blocked": "REDUCE_ATTACK_POSITION_CORE_FLOOR"
            if sellable_t_shares > 0
            else ("REDUCE_ATTACK_POSITION_T1_LOCK" if t_shares > 0 else None),
        }

    sell_price = _sell_price(price, config)
    cost_portion = t_cost_basis * (shares / t_shares)
    sellable_breakout_t_shares = _sellable_shares(breakout_t_shares, breakout_t_locked_shares, config=config)
    breakout_reduce_shares = min(shares, sellable_breakout_t_shares)
    breakout_cost_portion = breakout_t_cost_basis * (breakout_reduce_shares / breakout_t_shares) if breakout_t_shares > 0 else 0.0
    proceeds = _sell_proceeds(sell_price, shares, config)
    realized = proceeds - cost_portion
    cash += proceeds
    t_shares -= shares
    t_cost_basis -= cost_portion
    breakout_t_shares -= breakout_reduce_shares
    breakout_t_cost_basis -= breakout_cost_portion
    trade = _trade(
        timestamp,
        "REDUCE_ATTACK_POSITION",
        "SELL_ATTACK_REDUCE",
        shares,
        sell_price,
        cash,
        base_shares,
        t_shares,
        close_for_mark,
        f"进攻状态 {previous_attack_state} -> {attack_state}，主动仓位降到 {target_pct:.0%}",
        realized,
    )
    return {
        "cash": cash,
        "t_shares": t_shares,
        "t_locked_shares": t_locked_shares,
        "t_cost_basis": max(t_cost_basis, 0.0),
        "breakout_t_shares": breakout_t_shares,
        "breakout_t_locked_shares": breakout_t_locked_shares,
        "breakout_t_cost_basis": max(breakout_t_cost_basis, 0.0),
        "trade": trade,
        "blocked": None,
    }


def _core_floor_hard_exit_signal(
    signal: BacktestSignal,
    config: DividendTBacktestConfig,
    *,
    active_profit_pct: float = 0.0,
) -> bool:
    return (
        active_profit_pct <= -config.beta_hold_hard_stop_loss_pct
        or signal.market_regime_state == "DEFENSIVE"
        or signal.probability_state == "DOWN_RISK"
        or signal.chan_sell_point_type == "sell3"
        or signal.chan_structure_type == "breakdown"
        or signal.sell_pressure_score >= config.attack_hard_exit_sell_pressure_score
        or signal.down_probability_1d >= config.attack_hard_exit_down_probability
        or signal.down_probability_3d >= config.attack_hard_exit_down_probability
        or _offensive_volume_distribution_hard_exit_signal(
            signal,
            config,
            active_profit_pct=active_profit_pct,
            active_peak_profit_pct=max(active_profit_pct, config.offensive_volume_distribution_min_peak_profit_pct),
        )
    )


def _core_floor_protects_action(
    *,
    action: str,
    signal: BacktestSignal,
    config: DividendTBacktestConfig,
    attack_state: str,
    core_position_floor_pct: float,
    active_profit_pct: float = 0.0,
) -> bool:
    if not config.enable_core_position_floor or core_position_floor_pct <= 0.0:
        return False
    if action not in {
        "PROTECT_BREAKOUT_PROFIT",
        "SELL_T_TIMING",
        "STOP_T_WAIT",
        "WAIT_DAILY_WEAK",
        "REDUCE_ATTACK_POSITION",
        "SELL_REVERSE_T",
    }:
        return False
    if _core_floor_hard_exit_signal(signal, config, active_profit_pct=active_profit_pct):
        if (
            attack_state == ATTACK_BETA_HOLD
            and active_profit_pct > -config.beta_hold_hard_stop_loss_pct
            and _beta_hold_main_rise_core_floor_signal(signal, config)
        ):
            return True
        return False
    return (
        attack_state in {ATTACK_WATCH, ATTACK_CONFIRMED, ATTACK_FULL, ATTACK_BETA_HOLD}
        or signal.market_environment_state == MARKET_RISK_ON
        or signal.market_regime_state in {"BREAKOUT_ATTACK", "STRONG_TREND", "TREND_WATCH"}
    )


def _core_floor_protected_t_shares(
    *,
    price: float,
    equity_before: float,
    base_shares: int,
    t_shares: int,
    core_position_floor_pct: float,
    config: DividendTBacktestConfig,
) -> int:
    if price <= 0.0 or equity_before <= 0.0 or core_position_floor_pct <= 0.0 or t_shares <= 0:
        return 0
    target_total_shares = equity_before * core_position_floor_pct / price
    target_t_shares = max(target_total_shares - base_shares, 0.0)
    protected = math.ceil(target_t_shares / config.min_lot) * config.min_lot
    return min(t_shares, max(0, protected))


def _core_floor_sellable_t_shares(
    *,
    price: float,
    equity_before: float,
    base_shares: int,
    t_shares: int,
    t_locked_shares: int,
    action: str,
    signal: BacktestSignal,
    config: DividendTBacktestConfig,
    attack_state: str,
    core_position_floor_pct: float,
    active_profit_pct: float = 0.0,
) -> int:
    sellable = _sellable_shares(t_shares, t_locked_shares, config=config)
    if sellable <= 0:
        return 0
    if not _core_floor_protects_action(
        action=action,
        signal=signal,
        config=config,
        attack_state=attack_state,
        core_position_floor_pct=core_position_floor_pct,
        active_profit_pct=active_profit_pct,
    ):
        return sellable
    protected = _core_floor_protected_t_shares(
        price=price,
        equity_before=equity_before,
        base_shares=base_shares,
        t_shares=t_shares,
        core_position_floor_pct=core_position_floor_pct,
        config=config,
    )
    return min(sellable, max(0, t_shares - protected))


def _t_mode_allows_timing_buy(action: str, config: DividendTBacktestConfig) -> bool:
    if action == "BREAKOUT_BUY_TIMING":
        return True
    if action != "BUY_T_TIMING":
        return True
    return config.t_position_mode in {T_POSITION_MODE_FULL, T_POSITION_MODE_LIGHT, T_POSITION_MODE_ADD_ONLY}


def _t_mode_allows_timing_sell(config: DividendTBacktestConfig) -> bool:
    return config.enable_t_sell and config.t_position_mode in {T_POSITION_MODE_FULL, T_POSITION_MODE_LIGHT, T_POSITION_MODE_REDUCE_ONLY}


def _t_mode_allows_reverse_t(config: DividendTBacktestConfig) -> bool:
    return config.enable_t_sell and config.allow_reverse_t and config.t_position_mode == T_POSITION_MODE_FULL


def _t_mode_allows_breakout_profit_protection(config: DividendTBacktestConfig) -> bool:
    return config.t_position_mode in {T_POSITION_MODE_FULL, T_POSITION_MODE_LIGHT, T_POSITION_MODE_REDUCE_ONLY}


def _t_mode_scaled_buy_target_pct(
    *,
    action: str,
    target_pct: float,
    current_position_pct: float,
    config: DividendTBacktestConfig,
) -> float:
    if action != "BUY_T_TIMING" or config.t_position_mode != T_POSITION_MODE_LIGHT:
        return target_pct
    add_pct = max(target_pct - current_position_pct, 0.0)
    return round(current_position_pct + add_pct * 0.5, 4)


def _t_mode_scaled_sell_fraction(sell_fraction: float, config: DividendTBacktestConfig) -> float:
    if config.t_position_mode == T_POSITION_MODE_LIGHT:
        return sell_fraction * 0.5
    return sell_fraction


def _apply_backtest_macd_sizing(
    signal: BacktestSignal,
    *,
    original_trade_pct: float,
    minimum_trade_pct: float,
) -> SizingDecision:
    """Apply the MACD multiplier once at the position-aware execution boundary."""

    try:
        candidate_signal = Signal(signal.candidate_signal) if signal.candidate_signal is not None else _signal_for_action(signal.action)
        intent = SignalIntent(signal.signal_intent)
        risk_enforcement = RiskEnforcement(signal.risk_enforcement)
    except ValueError as exc:
        raise CandidateContractError(f"INVALID_BACKTEST_SIGNAL_CONTRACT: {exc}") from exc
    multiplier = float(signal.macd_sizing_multiplier)
    if not math.isfinite(multiplier) or not 0.0 <= multiplier <= 1.0:
        raise CandidateContractError("INVALID_MACD_SIZING_MULTIPLIER")
    trace = DecisionTrace(
        candidate_signal=candidate_signal,
        candidate_signal_intent=intent,
        candidate_setup_code=signal.candidate_setup_code,
        primary_setup_code=signal.primary_setup_code,
        entry_confirmations=signal.entry_confirmations,
        exit_confirmations=signal.exit_confirmations,
        candidate_reasons=(),
        final_signal=candidate_signal,
        risk_enforcement=risk_enforcement,
        macd_policy_applied=signal.macd_policy_applied,
        signal_downgraded=signal.signal_downgraded,
        downgrade_source=signal.downgrade_source,
        downgrade_reason=signal.downgrade_reason,
        original_suggested_trade_pct=signal.original_suggested_trade_pct,
        macd_sizing_multiplier=multiplier,
        adjusted_suggested_trade_pct=signal.adjusted_suggested_trade_pct,
        sizing_adjustment_source=signal.sizing_adjustment_source,
        macd_sizing_applied=signal.macd_sizing_applied,
        macd_sizing_owner=signal.macd_sizing_owner,
    )
    if risk_enforcement is RiskEnforcement.HARD or intent in {
        SignalIntent.RISK_REDUCTION,
        SignalIntent.BASE_ACCUMULATION,
        SignalIntent.NONE,
    }:
        return SizingDecision(
            candidate_signal,
            float(original_trade_pct),
            replace(
                trace,
                original_suggested_trade_pct=float(original_trade_pct),
                adjusted_suggested_trade_pct=float(original_trade_pct),
                macd_sizing_applied=False,
                macd_sizing_owner=None,
            ),
        )
    if multiplier != 1.0 and intent is not SignalIntent.MEAN_REVERSION_T:
        raise CandidateContractError("MACD_SIZING_NOT_ALLOWED_FOR_INTENT")
    policy = PolicyDecision(candidate_signal, multiplier, trace)
    return apply_macd_sizing_once(
        policy,
        original_suggested_trade_pct=original_trade_pct,
        effective_minimum_trade_pct=minimum_trade_pct,
        sizing_owner="dividend_t_backtest_execution",
    )


def _signal_for_action(action: str) -> Signal:
    if action in {"BUY_T_TIMING", "BREAKOUT_BUY_TIMING"}:
        return Signal.BUY_T
    if action == "SELL_T_TIMING":
        return Signal.SELL_T
    return Signal.HOLD


def validate_execution_after_signal(signal_time: str, execution_time: Any) -> None:
    """Reject same-bar or earlier execution to prevent close-bar look-ahead."""

    import pandas as pd

    if pd.Timestamp(execution_time) <= pd.Timestamp(signal_time):
        raise ValueError("EXECUTION_NOT_AFTER_SIGNAL_BAR")


def _execute_action(
    *,
    action: str,
    execution: Any,
    signal: BacktestSignal,
    equity_before: float,
    cash: float,
    base_shares: int,
    base_locked_shares: int,
    t_shares: int,
    t_locked_shares: int,
    t_cost_basis: float,
    breakout_t_shares: int,
    breakout_t_locked_shares: int,
    breakout_t_cost_basis: float,
    pending_buyback_shares: int,
    pending_reverse_proceeds: float,
    pending_buyback_target_price: float | None,
    attack_state: str,
    active_peak_profit_pct: float,
    constraints: TradeExecutionConstraints,
    config: DividendTBacktestConfig,
    core_position_floor_pct: float = 0.0,
) -> dict[str, Any]:
    price = float(execution["open"])
    timestamp = str(execution["timestamp"])
    close_for_mark = float(execution["close"])
    trade: DividendTTrade | None = None
    low_price = float(execution["low"])
    blocked: str | None = None

    buyback_limit_touched = (
        pending_buyback_shares > 0
        and pending_buyback_target_price is not None
        and low_price <= pending_buyback_target_price
        and action not in {"STOP_T_WAIT", "WAIT_DAILY_WEAK"}
        and constraints.can_buy
        and config.t_position_mode == T_POSITION_MODE_FULL
    )

    protect_breakout_profit = (
        config.enable_profit_protection
        and _t_mode_allows_breakout_profit_protection(config)
        and breakout_t_shares > 0
        and action
        not in {
            "BUY_T_TIMING",
            "BREAKOUT_BUY_TIMING",
            "SELL_T_TIMING",
            "STOP_T_WAIT",
            "WAIT_DAILY_WEAK",
            "WAIT_CANDIDATE_ENTRY_HOLD",
            "WAIT_BETA_HOLD",
        }
    )
    if protect_breakout_profit:
        breakout_avg_cost = breakout_t_cost_basis / breakout_t_shares if breakout_t_shares > 0 else 0.0
        breakout_profit_pct = price / breakout_avg_cost - 1.0 if breakout_avg_cost > 0 else 0.0
        if attack_state == ATTACK_BETA_HOLD:
            weakening = (
                signal.sell_pressure_score >= 74.0
                or signal.down_probability_1d >= config.attack_exit_down_probability
                or signal.down_probability_3d >= config.attack_hard_exit_down_probability
            )
        else:
            weakening = signal.force_ratio < 0.85 or signal.sell_pressure_score >= 62.0
        if attack_state not in {ATTACK_FULL, ATTACK_BETA_HOLD}:
            weakening = weakening or action == "WAIT_STRONG_TREND"
        trailing_sell_fraction = _offensive_trailing_profit_sell_fraction(
            action="PROTECT_BREAKOUT_PROFIT",
            signal=signal,
            config=config,
            active_profit_pct=breakout_profit_pct,
            active_peak_profit_pct=max(active_peak_profit_pct, breakout_profit_pct),
        )
        if trailing_sell_fraction == 0.0:
            weakening = False
        elif trailing_sell_fraction is not None:
            weakening = True
        if _offensive_risk_on_continuation_signal(signal, config) and breakout_profit_pct < config.offensive_trailing_profit_mid_pct:
            weakening = False
        if breakout_profit_pct >= config.profit_protect_trigger_pct and weakening:
            sell_fraction = trailing_sell_fraction if trailing_sell_fraction is not None else config.profit_protect_sell_fraction
            sell_fraction = _t_mode_scaled_sell_fraction(sell_fraction, config)
            if _profit_protection_defer_signal(
                signal=signal,
                config=config,
                breakout_profit_pct=breakout_profit_pct,
                active_peak_profit_pct=active_peak_profit_pct,
                sell_fraction=sell_fraction,
            ):
                blocked = "PROTECT_BREAKOUT_PROFIT_TREND_HOLD"
            else:
                sell_price = _sell_price(price, config)
                shares = _floor_lot(breakout_t_shares * sell_fraction, config.min_lot)
                if shares <= 0:
                    shares = (
                        min(breakout_t_shares, config.min_lot) if config.t_position_mode == T_POSITION_MODE_LIGHT else breakout_t_shares
                    )
                core_sellable_t_shares = _core_floor_sellable_t_shares(
                    price=price,
                    equity_before=equity_before,
                    base_shares=base_shares,
                    t_shares=t_shares,
                    t_locked_shares=t_locked_shares,
                    action="PROTECT_BREAKOUT_PROFIT",
                    signal=signal,
                    config=config,
                    attack_state=attack_state,
                    core_position_floor_pct=core_position_floor_pct,
                    active_profit_pct=breakout_profit_pct,
                )
                shares = min(
                    shares,
                    _sellable_shares(breakout_t_shares, breakout_t_locked_shares, config=config),
                    core_sellable_t_shares,
                )
                if shares > 0:
                    cost_portion = breakout_t_cost_basis * (shares / breakout_t_shares)
                    proceeds = _sell_proceeds(sell_price, shares, config)
                    realized = proceeds - cost_portion
                    cash += proceeds
                    t_shares -= shares
                    t_cost_basis -= cost_portion
                    breakout_t_shares -= shares
                    breakout_t_cost_basis -= cost_portion
                    trade = _trade(
                        timestamp,
                        "PROTECT_BREAKOUT_PROFIT",
                        "SELL_BREAKOUT_PROFIT",
                        shares,
                        sell_price,
                        cash,
                        base_shares,
                        t_shares,
                        close_for_mark,
                        f"突破仓利润保护，浮盈 {breakout_profit_pct:.1%}，买卖力转弱先卖出 {shares} 股",
                        realized,
                    )
                    return {
                        "cash": cash,
                        "base_shares": base_shares,
                        "base_locked_shares": base_locked_shares,
                        "t_shares": t_shares,
                        "t_locked_shares": t_locked_shares,
                        "t_cost_basis": max(t_cost_basis, 0.0),
                        "breakout_t_shares": breakout_t_shares,
                        "breakout_t_locked_shares": breakout_t_locked_shares,
                        "breakout_t_cost_basis": max(breakout_t_cost_basis, 0.0),
                        "pending_buyback_shares": pending_buyback_shares,
                        "pending_reverse_proceeds": pending_reverse_proceeds,
                        "pending_buyback_target_price": pending_buyback_target_price,
                        "trade": trade,
                        "blocked": blocked,
                    }
                blocked = "PROTECT_BREAKOUT_PROFIT_T1_LOCK"
    if buyback_limit_touched:
        if pending_buyback_shares > 0:
            raw_buy_price = min(price, pending_buyback_target_price) if pending_buyback_target_price is not None else price
            buy_price = _buy_price(raw_buy_price, config)
            original_pending = pending_buyback_shares
            shares = _floor_lot(min(pending_buyback_shares, cash / _buy_cost_per_share(buy_price, config)), config.min_lot)
            if shares > 0:
                cost = _buy_cost(buy_price, shares, config)
                cash -= cost
                base_shares += shares
                if config.enable_a_share_constraints and config.enable_t1:
                    base_locked_shares += shares
                pending_buyback_shares -= shares
                allocated_proceeds = pending_reverse_proceeds * (shares / original_pending)
                pending_reverse_proceeds -= allocated_proceeds
                realized = allocated_proceeds - cost
                if pending_buyback_shares == 0:
                    pending_reverse_proceeds = 0.0
                    pending_buyback_target_price = None
                trade = _trade(
                    timestamp,
                    "BUY_BACK_LIMIT",
                    "BUY_BACK_REVERSE_T",
                    shares,
                    buy_price,
                    cash,
                    base_shares,
                    t_shares,
                    close_for_mark,
                    "倒 T 到达计划价买回",
                    realized,
                )
    elif action in {"BUY_T_TIMING", "BREAKOUT_BUY_TIMING"}:
        if not _t_mode_allows_timing_buy(action, config):
            return _execution_state(
                cash=cash,
                base_shares=base_shares,
                base_locked_shares=base_locked_shares,
                t_shares=t_shares,
                t_locked_shares=t_locked_shares,
                t_cost_basis=t_cost_basis,
                breakout_t_shares=breakout_t_shares,
                breakout_t_locked_shares=breakout_t_locked_shares,
                breakout_t_cost_basis=breakout_t_cost_basis,
                pending_buyback_shares=pending_buyback_shares,
                pending_reverse_proceeds=pending_reverse_proceeds,
                pending_buyback_target_price=pending_buyback_target_price,
                trade=None,
                blocked=f"{action}_T_MODE_BLOCKED",
            )
        if not constraints.can_buy:
            blocked = _block_key(action, constraints)
            return _execution_state(
                cash=cash,
                base_shares=base_shares,
                base_locked_shares=base_locked_shares,
                t_shares=t_shares,
                t_locked_shares=t_locked_shares,
                t_cost_basis=t_cost_basis,
                breakout_t_shares=breakout_t_shares,
                breakout_t_locked_shares=breakout_t_locked_shares,
                breakout_t_cost_basis=breakout_t_cost_basis,
                pending_buyback_shares=pending_buyback_shares,
                pending_reverse_proceeds=pending_reverse_proceeds,
                pending_buyback_target_price=pending_buyback_target_price,
                trade=None,
                blocked=blocked,
            )
        buy_price = _buy_price(price, config)
        target_pct = _signal_target_position_pct(signal, config, attack_state=attack_state)
        current_position_pct = ((base_shares + t_shares) * buy_price / equity_before) if equity_before > 0 else 0.0
        target_pct = _t_mode_scaled_buy_target_pct(
            action=action,
            target_pct=target_pct,
            current_position_pct=current_position_pct,
            config=config,
        )
        add_pct = max(target_pct - current_position_pct, 0.0)
        sizing = _apply_backtest_macd_sizing(
            signal,
            original_trade_pct=add_pct,
            minimum_trade_pct=config.min_t_trade_pct,
        )
        if sizing.final_signal is Signal.HOLD:
            return _execution_state(
                cash=cash,
                base_shares=base_shares,
                base_locked_shares=base_locked_shares,
                t_shares=t_shares,
                t_locked_shares=t_locked_shares,
                t_cost_basis=t_cost_basis,
                breakout_t_shares=breakout_t_shares,
                breakout_t_locked_shares=breakout_t_locked_shares,
                breakout_t_cost_basis=breakout_t_cost_basis,
                pending_buyback_shares=pending_buyback_shares,
                pending_reverse_proceeds=pending_reverse_proceeds,
                pending_buyback_target_price=pending_buyback_target_price,
                trade=None,
                blocked="MACD_SIZING_TO_ZERO",
            )
        add_pct = sizing.adjusted_suggested_trade_pct
        target_notional = equity_before * add_pct
        shares = _floor_lot(min(target_notional / buy_price, cash / _buy_cost_per_share(buy_price, config)), config.min_lot)
        if shares > 0:
            cost = _buy_cost(buy_price, shares, config)
            cash -= cost
            previous_cost = t_cost_basis
            t_shares += shares
            if config.enable_a_share_constraints and config.enable_t1:
                t_locked_shares += shares
            t_cost_basis = previous_cost + cost
            if action == "BREAKOUT_BUY_TIMING":
                breakout_t_shares += shares
                if config.enable_a_share_constraints and config.enable_t1:
                    breakout_t_locked_shares += shares
                breakout_t_cost_basis += cost
            trade = _trade(
                timestamp,
                action,
                "BUY_BREAKOUT" if action == "BREAKOUT_BUY_TIMING" else "BUY_T",
                shares,
                buy_price,
                cash,
                base_shares,
                t_shares,
                close_for_mark,
                f"主动仓位买入，强度 {signal.buy_signal_strength:.1f}，Kelly {signal.kelly_fraction:.1%}，突破分 {signal.breakout_score:.1f}，目标总仓位 {target_pct:.1%}",
                None,
                sizing_trace=sizing.trace,
            )

    elif action == "SELL_T_TIMING":
        if not _t_mode_allows_timing_sell(config):
            return _execution_state(
                cash=cash,
                base_shares=base_shares,
                base_locked_shares=base_locked_shares,
                t_shares=t_shares,
                t_locked_shares=t_locked_shares,
                t_cost_basis=t_cost_basis,
                breakout_t_shares=breakout_t_shares,
                breakout_t_locked_shares=breakout_t_locked_shares,
                breakout_t_cost_basis=breakout_t_cost_basis,
                pending_buyback_shares=pending_buyback_shares,
                pending_reverse_proceeds=pending_reverse_proceeds,
                pending_buyback_target_price=pending_buyback_target_price,
                trade=None,
                blocked="SELL_T_TIMING_T_MODE_BLOCKED",
            )
        t_profit_pct = _active_position_profit_pct(price=price, t_shares=t_shares, t_cost_basis=t_cost_basis)
        if not constraints.can_sell:
            blocked = _block_key(action, constraints)
            return _execution_state(
                cash=cash,
                base_shares=base_shares,
                base_locked_shares=base_locked_shares,
                t_shares=t_shares,
                t_locked_shares=t_locked_shares,
                t_cost_basis=t_cost_basis,
                breakout_t_shares=breakout_t_shares,
                breakout_t_locked_shares=breakout_t_locked_shares,
                breakout_t_cost_basis=breakout_t_cost_basis,
                pending_buyback_shares=pending_buyback_shares,
                pending_reverse_proceeds=pending_reverse_proceeds,
                pending_buyback_target_price=pending_buyback_target_price,
                trade=None,
                blocked=blocked,
            )
        sell_price = _sell_price(price, config)
        if t_shares > 0:
            sell_fraction = _offensive_exit_sell_fraction(
                action=action,
                signal=signal,
                config=config,
                attack_state=attack_state,
                active_profit_pct=t_profit_pct,
                active_peak_profit_pct=active_peak_profit_pct,
            )
            sell_fraction = _t_mode_scaled_sell_fraction(sell_fraction, config)
            if sell_fraction <= 0.0:
                return _execution_state(
                    cash=cash,
                    base_shares=base_shares,
                    base_locked_shares=base_locked_shares,
                    t_shares=t_shares,
                    t_locked_shares=t_locked_shares,
                    t_cost_basis=t_cost_basis,
                    breakout_t_shares=breakout_t_shares,
                    breakout_t_locked_shares=breakout_t_locked_shares,
                    breakout_t_cost_basis=breakout_t_cost_basis,
                    pending_buyback_shares=pending_buyback_shares,
                    pending_reverse_proceeds=pending_reverse_proceeds,
                    pending_buyback_target_price=pending_buyback_target_price,
                    trade=None,
                    blocked=None,
                )
            raw_sellable_t_shares = _sellable_shares(t_shares, t_locked_shares, config=config)
            sellable_t_shares = _core_floor_sellable_t_shares(
                price=price,
                equity_before=equity_before,
                base_shares=base_shares,
                t_shares=t_shares,
                t_locked_shares=t_locked_shares,
                action=action,
                signal=signal,
                config=config,
                attack_state=attack_state,
                core_position_floor_pct=core_position_floor_pct,
                active_profit_pct=t_profit_pct,
            )
            max_sell_trade_pct = (raw_sellable_t_shares * sell_price / equity_before) if equity_before > 0 else 0.0
            sizing = _apply_backtest_macd_sizing(
                signal,
                original_trade_pct=max_sell_trade_pct * sell_fraction,
                minimum_trade_pct=config.min_t_trade_pct,
            )
            if sizing.final_signal is Signal.HOLD:
                return _execution_state(
                    cash=cash,
                    base_shares=base_shares,
                    base_locked_shares=base_locked_shares,
                    t_shares=t_shares,
                    t_locked_shares=t_locked_shares,
                    t_cost_basis=t_cost_basis,
                    breakout_t_shares=breakout_t_shares,
                    breakout_t_locked_shares=breakout_t_locked_shares,
                    breakout_t_cost_basis=breakout_t_cost_basis,
                    pending_buyback_shares=pending_buyback_shares,
                    pending_reverse_proceeds=pending_reverse_proceeds,
                    pending_buyback_target_price=pending_buyback_target_price,
                    trade=None,
                    blocked="MACD_SIZING_TO_ZERO",
                )
            if max_sell_trade_pct > 0.0:
                sell_fraction = sizing.adjusted_suggested_trade_pct / max_sell_trade_pct
            requested_shares = _floor_lot(raw_sellable_t_shares * sell_fraction, config.min_lot)
            if requested_shares <= 0 and raw_sellable_t_shares > 0:
                requested_shares = (
                    min(raw_sellable_t_shares, config.min_lot) if config.t_position_mode == T_POSITION_MODE_LIGHT else raw_sellable_t_shares
                )
            shares = min(requested_shares, sellable_t_shares)
            if shares <= 0:
                blocked = "SELL_T_TIMING_CORE_FLOOR" if raw_sellable_t_shares > 0 else "SELL_T_TIMING_T1_LOCK"
                return _execution_state(
                    cash=cash,
                    base_shares=base_shares,
                    base_locked_shares=base_locked_shares,
                    t_shares=t_shares,
                    t_locked_shares=t_locked_shares,
                    t_cost_basis=t_cost_basis,
                    breakout_t_shares=breakout_t_shares,
                    breakout_t_locked_shares=breakout_t_locked_shares,
                    breakout_t_cost_basis=breakout_t_cost_basis,
                    pending_buyback_shares=pending_buyback_shares,
                    pending_reverse_proceeds=pending_reverse_proceeds,
                    pending_buyback_target_price=pending_buyback_target_price,
                    trade=None,
                    blocked=blocked,
                )
            proceeds = _sell_proceeds(sell_price, shares, config)
            cost_portion = t_cost_basis * (shares / t_shares)
            realized = proceeds - cost_portion
            cash += proceeds
            t_shares -= shares
            t_cost_basis -= cost_portion
            breakout_reduce_shares = min(shares, _sellable_shares(breakout_t_shares, breakout_t_locked_shares, config=config))
            breakout_cost_portion = breakout_t_cost_basis * (breakout_reduce_shares / breakout_t_shares) if breakout_t_shares > 0 else 0.0
            breakout_t_shares -= breakout_reduce_shares
            breakout_t_cost_basis -= breakout_cost_portion
            reason = "卖出 T 仓" if sell_fraction >= 0.999 else f"offensive 普通卖点只降主动仓 {sell_fraction:.0%}，延展趋势持仓"
            trade = _trade(
                timestamp,
                action,
                "SELL_T",
                shares,
                sell_price,
                cash,
                base_shares,
                t_shares,
                close_for_mark,
                reason,
                realized,
                execution_setup_code=signal.primary_setup_code,
                sizing_trace=sizing.trace,
            )
        elif _t_mode_allows_reverse_t(config) and pending_buyback_shares == 0:
            if _core_floor_protects_action(
                action="SELL_REVERSE_T",
                signal=signal,
                config=config,
                attack_state=attack_state,
                core_position_floor_pct=core_position_floor_pct,
                active_profit_pct=0.0,
            ):
                blocked = "SELL_REVERSE_T_CORE_FLOOR"
                return _execution_state(
                    cash=cash,
                    base_shares=base_shares,
                    base_locked_shares=base_locked_shares,
                    t_shares=t_shares,
                    t_locked_shares=t_locked_shares,
                    t_cost_basis=t_cost_basis,
                    breakout_t_shares=breakout_t_shares,
                    breakout_t_locked_shares=breakout_t_locked_shares,
                    breakout_t_cost_basis=breakout_t_cost_basis,
                    pending_buyback_shares=pending_buyback_shares,
                    pending_reverse_proceeds=pending_reverse_proceeds,
                    pending_buyback_target_price=pending_buyback_target_price,
                    trade=None,
                    blocked=blocked,
                )
            original_trade_pct = _signal_t_trade_cap(signal, config, attack_state=attack_state)
            sizing = _apply_backtest_macd_sizing(
                signal,
                original_trade_pct=original_trade_pct,
                minimum_trade_pct=config.min_t_trade_pct,
            )
            if sizing.final_signal is Signal.HOLD:
                return _execution_state(
                    cash=cash,
                    base_shares=base_shares,
                    base_locked_shares=base_locked_shares,
                    t_shares=t_shares,
                    t_locked_shares=t_locked_shares,
                    t_cost_basis=t_cost_basis,
                    breakout_t_shares=breakout_t_shares,
                    breakout_t_locked_shares=breakout_t_locked_shares,
                    breakout_t_cost_basis=breakout_t_cost_basis,
                    pending_buyback_shares=pending_buyback_shares,
                    pending_reverse_proceeds=pending_reverse_proceeds,
                    pending_buyback_target_price=pending_buyback_target_price,
                    trade=None,
                    blocked="MACD_SIZING_TO_ZERO",
                )
            target_notional = equity_before * sizing.adjusted_suggested_trade_pct
            sellable_base_shares = _sellable_shares(base_shares, base_locked_shares, config=config)
            shares = _floor_lot(min(sellable_base_shares, target_notional / sell_price), config.min_lot)
            if shares <= 0 and base_shares > 0:
                blocked = "SELL_REVERSE_T_T1_LOCK"
            if shares > 0:
                proceeds = _sell_proceeds(sell_price, shares, config)
                cash += proceeds
                base_shares -= shares
                pending_buyback_shares += shares
                pending_reverse_proceeds += proceeds
                pending_buyback_target_price = signal.buy_back_reference_price or price * 0.985
                trade = _trade(
                    timestamp,
                    action,
                    "SELL_REVERSE_T",
                    shares,
                    sell_price,
                    cash,
                    base_shares,
                    t_shares,
                    close_for_mark,
                    "倒 T 卖出",
                    None,
                    execution_setup_code="reverse_t_sell",
                    sizing_trace=sizing.trace,
                )

    elif action in {"STOP_T_WAIT", "WAIT_DAILY_WEAK"} and t_shares > 0:
        t_profit_pct = _active_position_profit_pct(price=price, t_shares=t_shares, t_cost_basis=t_cost_basis)
        sell_fraction = _offensive_exit_sell_fraction(
            action=action,
            signal=signal,
            config=config,
            attack_state=attack_state,
            active_profit_pct=t_profit_pct,
            active_peak_profit_pct=active_peak_profit_pct,
        )
        if sell_fraction <= 0.0:
            return _execution_state(
                cash=cash,
                base_shares=base_shares,
                base_locked_shares=base_locked_shares,
                t_shares=t_shares,
                t_locked_shares=t_locked_shares,
                t_cost_basis=t_cost_basis,
                breakout_t_shares=breakout_t_shares,
                breakout_t_locked_shares=breakout_t_locked_shares,
                breakout_t_cost_basis=breakout_t_cost_basis,
                pending_buyback_shares=pending_buyback_shares,
                pending_reverse_proceeds=pending_reverse_proceeds,
                pending_buyback_target_price=pending_buyback_target_price,
                trade=None,
                blocked=None,
            )
        if not constraints.can_sell:
            blocked = _block_key(action, constraints)
            return _execution_state(
                cash=cash,
                base_shares=base_shares,
                base_locked_shares=base_locked_shares,
                t_shares=t_shares,
                t_locked_shares=t_locked_shares,
                t_cost_basis=t_cost_basis,
                breakout_t_shares=breakout_t_shares,
                breakout_t_locked_shares=breakout_t_locked_shares,
                breakout_t_cost_basis=breakout_t_cost_basis,
                pending_buyback_shares=pending_buyback_shares,
                pending_reverse_proceeds=pending_reverse_proceeds,
                pending_buyback_target_price=pending_buyback_target_price,
                trade=None,
                blocked=blocked,
            )
        sell_price = _sell_price(price, config)
        raw_sellable_t_shares = _sellable_shares(t_shares, t_locked_shares, config=config)
        sellable_t_shares = _core_floor_sellable_t_shares(
            price=price,
            equity_before=equity_before,
            base_shares=base_shares,
            t_shares=t_shares,
            t_locked_shares=t_locked_shares,
            action=action,
            signal=signal,
            config=config,
            attack_state=attack_state,
            core_position_floor_pct=core_position_floor_pct,
            active_profit_pct=t_profit_pct,
        )
        requested_shares = _floor_lot(raw_sellable_t_shares * sell_fraction, config.min_lot)
        if requested_shares <= 0 and raw_sellable_t_shares > 0:
            requested_shares = raw_sellable_t_shares
        shares = min(requested_shares, sellable_t_shares)
        if shares <= 0:
            blocked = f"{action}_CORE_FLOOR" if raw_sellable_t_shares > 0 else f"{action}_T1_LOCK"
            return _execution_state(
                cash=cash,
                base_shares=base_shares,
                base_locked_shares=base_locked_shares,
                t_shares=t_shares,
                t_locked_shares=t_locked_shares,
                t_cost_basis=t_cost_basis,
                breakout_t_shares=breakout_t_shares,
                breakout_t_locked_shares=breakout_t_locked_shares,
                breakout_t_cost_basis=breakout_t_cost_basis,
                pending_buyback_shares=pending_buyback_shares,
                pending_reverse_proceeds=pending_reverse_proceeds,
                pending_buyback_target_price=pending_buyback_target_price,
                trade=None,
                blocked=blocked,
            )
        proceeds = _sell_proceeds(sell_price, shares, config)
        cost_portion = t_cost_basis * (shares / t_shares)
        realized = proceeds - cost_portion
        cash += proceeds
        t_shares -= shares
        t_cost_basis -= cost_portion
        breakout_reduce_shares = min(shares, _sellable_shares(breakout_t_shares, breakout_t_locked_shares, config=config))
        breakout_cost_portion = breakout_t_cost_basis * (breakout_reduce_shares / breakout_t_shares) if breakout_t_shares > 0 else 0.0
        breakout_t_shares -= breakout_reduce_shares
        breakout_t_cost_basis -= breakout_cost_portion
        reason = "T 仓止损/失效卖出" if sell_fraction >= 0.999 else f"offensive 软止损只降主动仓 {sell_fraction:.0%}，等待趋势确认"
        trade = _trade(
            timestamp,
            action,
            "STOP_T",
            shares,
            sell_price,
            cash,
            base_shares,
            t_shares,
            close_for_mark,
            reason,
            realized,
            execution_setup_code=signal.primary_setup_code,
            risk_enforcement=RiskEnforcement(signal.risk_enforcement),
        )

    return {
        "cash": cash,
        "base_shares": base_shares,
        "base_locked_shares": base_locked_shares,
        "t_shares": t_shares,
        "t_locked_shares": t_locked_shares,
        "t_cost_basis": max(t_cost_basis, 0.0),
        "breakout_t_shares": breakout_t_shares,
        "breakout_t_locked_shares": breakout_t_locked_shares,
        "breakout_t_cost_basis": max(breakout_t_cost_basis, 0.0),
        "pending_buyback_shares": pending_buyback_shares,
        "pending_reverse_proceeds": pending_reverse_proceeds,
        "pending_buyback_target_price": pending_buyback_target_price,
        "trade": trade,
        "blocked": blocked,
    }


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        import pandas as pd

        if pd.isna(value):
            return None
    except Exception:  # noqa: BLE001
        pass
    text = str(value).strip()
    if not text:
        return None
    return float(text)


def _optional_bool(value: Any) -> bool:
    if value is None:
        return False
    try:
        import pandas as pd

        if pd.isna(value):
            return False
    except Exception:  # noqa: BLE001
        pass
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    try:
        import pandas as pd

        if pd.isna(value):
            return None
    except Exception:  # noqa: BLE001
        pass
    text = str(value).strip()
    return text or None


def _candidate_signal_value(candidate: Any) -> str | None:
    if candidate is None:
        return None
    signal = getattr(candidate, "candidate_signal", candidate)
    if signal is None:
        return None
    return str(getattr(signal, "value", signal))


def _cached_string_tuple(value: Any, *, default: tuple[str, ...]) -> tuple[str, ...]:
    text = _optional_text(value)
    if text is None:
        return default
    import ast

    try:
        parsed = ast.literal_eval(text)
    except (SyntaxError, ValueError):
        return (text,)
    if isinstance(parsed, (tuple, list)) and all(isinstance(item, str) for item in parsed):
        return tuple(parsed)
    return default


def _execution_state(
    *,
    cash: float,
    base_shares: int,
    base_locked_shares: int,
    t_shares: int,
    t_locked_shares: int,
    t_cost_basis: float,
    breakout_t_shares: int,
    breakout_t_locked_shares: int,
    breakout_t_cost_basis: float,
    pending_buyback_shares: int,
    pending_reverse_proceeds: float,
    pending_buyback_target_price: float | None,
    trade: DividendTTrade | None,
    blocked: str | None,
) -> dict[str, Any]:
    return {
        "cash": cash,
        "base_shares": base_shares,
        "base_locked_shares": base_locked_shares,
        "t_shares": t_shares,
        "t_locked_shares": t_locked_shares,
        "t_cost_basis": max(t_cost_basis, 0.0),
        "breakout_t_shares": breakout_t_shares,
        "breakout_t_locked_shares": breakout_t_locked_shares,
        "breakout_t_cost_basis": max(breakout_t_cost_basis, 0.0),
        "pending_buyback_shares": pending_buyback_shares,
        "pending_reverse_proceeds": pending_reverse_proceeds,
        "pending_buyback_target_price": pending_buyback_target_price,
        "trade": trade,
        "blocked": blocked,
    }


def _trade_date(timestamp: Any) -> object:
    import pandas as pd

    return pd.Timestamp(timestamp).date()


def _previous_daily_close_by_date(data: Any) -> dict[object, float]:
    daily = data.copy()
    daily["trade_date"] = daily["timestamp"].map(_trade_date)
    closes = daily.sort_values("timestamp").groupby("trade_date", sort=True)["close"].last().astype(float)
    result: dict[object, float] = {}
    previous_close: float | None = None
    for trade_date, close in closes.items():
        if previous_close is not None:
            result[trade_date] = previous_close
        previous_close = float(close)
    return result


def _trade_execution_constraints(
    row: Any,
    *,
    symbol: str,
    previous_daily_close: float | None,
    config: DividendTBacktestConfig,
) -> TradeExecutionConstraints:
    if not config.enable_a_share_constraints:
        return TradeExecutionConstraints()
    suspended = _is_suspended_bar(row) if config.enable_suspension_constraints else False
    if suspended:
        return TradeExecutionConstraints(can_buy=False, can_sell=False, suspended=True, reason="SUSPENDED")
    if not config.enable_limit_price_constraints:
        return TradeExecutionConstraints()

    prev_close = _optional_float(row.get("prev_close", None)) or previous_daily_close
    if prev_close is None or prev_close <= 0:
        return TradeExecutionConstraints()
    open_price = float(row["open"])
    limit_pct = _limit_pct_for_symbol(symbol, row)
    tolerance = config.limit_price_tolerance_bps / 10_000.0
    up_limit = prev_close * (1.0 + limit_pct)
    down_limit = prev_close * (1.0 - limit_pct)
    at_limit_up = open_price >= up_limit * (1.0 - tolerance)
    at_limit_down = open_price <= down_limit * (1.0 + tolerance)
    if at_limit_up and at_limit_down:
        return TradeExecutionConstraints(can_buy=False, can_sell=False, at_limit_up=True, at_limit_down=True, reason="LIMIT_LOCK")
    if at_limit_up:
        return TradeExecutionConstraints(can_buy=False, can_sell=True, at_limit_up=True, reason="LIMIT_UP")
    if at_limit_down:
        return TradeExecutionConstraints(can_buy=True, can_sell=False, at_limit_down=True, reason="LIMIT_DOWN")
    return TradeExecutionConstraints()


def _is_suspended_bar(row: Any) -> bool:
    if _optional_bool(row.get("is_suspended", False)):
        return True
    try:
        volume = float(row.get("volume", 0.0))
    except (TypeError, ValueError):
        volume = 0.0
    values = [
        _optional_float(row.get("open", None)),
        _optional_float(row.get("high", None)),
        _optional_float(row.get("low", None)),
        _optional_float(row.get("close", None)),
    ]
    return volume <= 0 or any(value is None or value <= 0 for value in values)


def _limit_pct_for_symbol(symbol: str, row: Any) -> float:
    if _optional_bool(row.get("is_st", False)):
        return 0.05
    code = symbol.split(".")[0]
    suffix = symbol.split(".")[-1].upper() if "." in symbol else ""
    if suffix == "BJ" or code.startswith(("4", "8", "9")):
        return 0.30
    if code.startswith(("300", "301", "688")):
        return 0.20
    return 0.10


def _sellable_shares(total_shares: int, locked_shares: int, *, config: DividendTBacktestConfig) -> int:
    if not config.enable_a_share_constraints or not config.enable_t1:
        return total_shares
    return max(total_shares - locked_shares, 0)


def _block_key(action: str, constraints: TradeExecutionConstraints) -> str:
    suffix = constraints.reason or "BLOCKED"
    return f"{action}_{suffix}"


def _increment_count(counts: dict[str, int], key: str | None) -> None:
    if key:
        counts[key] = counts.get(key, 0) + 1


def _apply_corporate_action(
    row: Any,
    *,
    cash: float,
    base_shares: int,
    t_shares: int,
    base_locked_shares: int,
    t_locked_shares: int,
    breakout_t_shares: int,
    breakout_t_locked_shares: int,
) -> dict[str, Any]:
    cash_dividend_per_share = _optional_float(row.get("cash_dividend_per_share", 0.0)) or 0.0
    share_bonus_ratio = _optional_float(row.get("share_bonus_ratio", 0.0)) or 0.0
    total_shares = base_shares + t_shares
    cash_dividend = round(total_shares * cash_dividend_per_share, 2) if cash_dividend_per_share > 0 else 0.0
    if cash_dividend > 0:
        cash += cash_dividend
    if share_bonus_ratio > 0:
        base_bonus = int(base_shares * share_bonus_ratio)
        t_bonus = int(t_shares * share_bonus_ratio)
        base_locked_bonus = int(base_locked_shares * share_bonus_ratio)
        t_locked_bonus = int(t_locked_shares * share_bonus_ratio)
        breakout_bonus = int(breakout_t_shares * share_bonus_ratio)
        breakout_locked_bonus = int(breakout_t_locked_shares * share_bonus_ratio)
        base_shares += base_bonus
        t_shares += t_bonus
        base_locked_shares += base_locked_bonus
        t_locked_shares += t_locked_bonus
        breakout_t_shares += breakout_bonus
        breakout_t_locked_shares += breakout_locked_bonus
    return {
        "cash": cash,
        "base_shares": base_shares,
        "t_shares": t_shares,
        "base_locked_shares": base_locked_shares,
        "t_locked_shares": t_locked_shares,
        "breakout_t_shares": breakout_t_shares,
        "breakout_t_locked_shares": breakout_t_locked_shares,
        "cash_dividend": cash_dividend,
        "applied": cash_dividend > 0 or share_bonus_ratio > 0,
    }


def _market_environment_at(
    timestamp: Any,
    *,
    config: DividendTBacktestConfig,
    market_filter: MarketEnvironmentFilter | None,
) -> MarketEnvironmentPoint | None:
    if not config.enable_market_filter or market_filter is None:
        return None
    return market_filter.point_at(timestamp)


def _previous_market_environment_at(
    timestamp: Any,
    *,
    config: DividendTBacktestConfig,
    market_filter: MarketEnvironmentFilter | None,
) -> MarketEnvironmentPoint | None:
    if not config.enable_market_filter or market_filter is None:
        return None
    import pandas as pd

    return market_filter.point_at(pd.Timestamp(timestamp) - pd.Timedelta(days=1))


def _empty_market_environment_metrics() -> dict[str, float]:
    return {
        "market_trend_score": 0.0,
        "market_breadth_score": 0.0,
        "market_amount_score": 0.0,
        "market_limit_structure_score": 0.0,
        "market_industry_diffusion_score": 0.0,
        "market_model_state_score": 0.0,
        "market_advance_ratio": 0.0,
        "market_above_ma20_ratio": 0.0,
        "market_amount_ratio20": 0.0,
        "market_limit_up_ratio": 0.0,
        "market_limit_down_ratio": 0.0,
        "market_industry_risk_on_ratio": 0.0,
        "model_holding_win_rate": 0.0,
        "model_holding_profit_spread": 0.0,
        "model_new_buy_success_rate": 0.0,
    }


def _market_environment_point_metrics(point: MarketEnvironmentPoint) -> dict[str, float]:
    return {
        "market_trend_score": round(float(point.trend_score), 2),
        "market_breadth_score": round(float(point.breadth_score), 2),
        "market_amount_score": round(float(point.amount_score), 2),
        "market_limit_structure_score": round(float(point.limit_structure_score), 2),
        "market_industry_diffusion_score": round(float(point.industry_diffusion_score), 2),
        "market_model_state_score": round(float(point.model_state_score), 2),
        "market_advance_ratio": round(float(point.advance_ratio), 4),
        "market_above_ma20_ratio": round(float(point.above_ma20_ratio), 4),
        "market_amount_ratio20": round(float(point.amount_ratio20), 4),
        "market_limit_up_ratio": round(float(point.limit_up_ratio), 4),
        "market_limit_down_ratio": round(float(point.limit_down_ratio), 4),
        "market_industry_risk_on_ratio": round(float(point.industry_risk_on_ratio), 4),
        "model_holding_win_rate": round(float(point.model_holding_win_rate), 4),
        "model_holding_profit_spread": round(float(point.model_holding_profit_spread), 4),
        "model_new_buy_success_rate": round(float(point.model_new_buy_success_rate), 4),
    }


def _current_model_state_metrics(
    *,
    trades: list[DividendTTrade],
    active_profit_pct: float,
    has_active_position: bool,
    buy_follow_success_count: int,
    buy_follow_failure_count: int,
) -> dict[str, float]:
    realized_values = [float(trade.realized_pnl) for trade in trades if trade.realized_pnl is not None]
    wins = sum(1 for value in realized_values if value > 0.0)
    observations = len(realized_values)
    if has_active_position:
        observations += 1
        wins += 1 if active_profit_pct > 0.0 else 0
    holding_win_rate = wins / observations if observations >= 3 else 0.50
    if not has_active_position:
        holding_profit_spread = 0.50
    elif active_profit_pct >= 0.03:
        holding_profit_spread = 0.75
    elif active_profit_pct > 0.0:
        holding_profit_spread = 0.62
    elif active_profit_pct <= -0.03:
        holding_profit_spread = 0.25
    else:
        holding_profit_spread = 0.38
    follow_count = buy_follow_success_count + buy_follow_failure_count
    new_buy_success_rate = buy_follow_success_count / follow_count if follow_count >= 3 else 0.50
    return {
        "model_holding_win_rate": round(clamp(holding_win_rate, 0.0, 1.0), 4),
        "model_holding_profit_spread": round(clamp(holding_profit_spread, 0.0, 1.0), 4),
        "model_new_buy_success_rate": round(clamp(new_buy_success_rate, 0.0, 1.0), 4),
    }


def _effective_signal_config(
    config: DividendTBacktestConfig,
    *,
    signal: BacktestSignal,
    market_environment: MarketEnvironmentPoint | None,
    attack_state: str = ATTACK_INACTIVE,
) -> DividendTBacktestConfig:
    if config.strategy_mode != "dynamic":
        return config
    selected_mode = _select_dynamic_strategy_mode(signal, market_environment)
    selected_config = apply_strategy_mode(config, selected_mode)
    if selected_mode == "defensive" and config.enable_attack_state_machine and attack_state != ATTACK_INACTIVE:
        return replace(
            selected_config,
            enable_attack_state_machine=True,
            enable_beta_hold_state=config.enable_beta_hold_state,
            beta_hold_min_bars=max(selected_config.beta_hold_min_bars, config.beta_hold_min_bars),
            beta_hold_exit_confirm_bars=max(selected_config.beta_hold_exit_confirm_bars, config.beta_hold_exit_confirm_bars),
            beta_hold_soft_exit_confirm_bars=max(
                selected_config.beta_hold_soft_exit_confirm_bars,
                config.beta_hold_soft_exit_confirm_bars,
            ),
            beta_hold_distribution_confirm_bars=max(
                selected_config.beta_hold_distribution_confirm_bars,
                config.beta_hold_distribution_confirm_bars,
            ),
            attack_exit_confirm_bars=max(selected_config.attack_exit_confirm_bars, config.attack_exit_confirm_bars),
            attack_distribution_confirm_bars=max(
                selected_config.attack_distribution_confirm_bars,
                config.attack_distribution_confirm_bars,
            ),
        )
    return selected_config


def _select_dynamic_strategy_mode(signal: BacktestSignal, market_environment: MarketEnvironmentPoint | None) -> str:
    if market_environment is None:
        return "balanced"
    beta_hold_candidate = _beta_hold_core_signal(
        signal,
        DividendTBacktestConfig(),
        min_confirmations=2,
        min_strength=62.0,
        allow_soft_action=True,
    )
    if (market_environment.state == MARKET_RISK_ON or signal.market_environment_state == MARKET_RISK_ON or beta_hold_candidate) and (
        _offensive_signal_eligible(signal) or beta_hold_candidate
    ):
        return "offensive"
    return "defensive"


def _offensive_signal_eligible(signal: BacktestSignal) -> bool:
    if signal.action in {"SELL_T_TIMING", "STOP_T_WAIT", "WAIT_DAILY_WEAK", "WAIT_MARKET_CAUTION"}:
        return False
    if signal.market_regime_state == "DEFENSIVE" or signal.probability_state == "DOWN_RISK":
        return False
    if signal.chan_sell_point_type in {"sell1", "sell2", "sell3"} or signal.chan_structure_type == "breakdown":
        return False
    if signal.sell_pressure_score >= 72.0 or signal.down_probability_1d >= 0.58 or signal.down_probability_3d >= 0.60:
        return False
    if _offensive_volume_distribution_blocks_entry_signal(signal, DividendTBacktestConfig()):
        return False

    strong_trend = (
        signal.market_regime_state in {"STRONG_TREND", "BREAKOUT_ATTACK"}
        and (signal.trend_state == "UPTREND" or signal.breakout_score >= 84.0)
        and signal.buy_signal_strength >= 70.0
    )
    chan_buy3 = signal.chan_buy_point_type == "buy3" and signal.chan_score >= 76.0
    confirmed_flow = _signal_capital_flow_confirmed(signal, min_score=66.0) and signal.buy_signal_strength >= 72.0
    volume_price_gate = (
        signal.volume_price_score >= 72.0
        and (
            signal.volume_breakout_score >= 70.0
            or signal.post_breakout_volume_persistence_score >= 70.0
            or signal.low_volume_pullback_score >= 72.0
        )
        and signal.vwap_support_score >= 58.0
        and signal.buy_signal_strength >= 70.0
    )
    return strong_trend or chan_buy3 or confirmed_flow or volume_price_gate


def _apply_risk_on_continuation_add(signal: BacktestSignal, config: DividendTBacktestConfig) -> BacktestSignal:
    if not _risk_on_continuation_add_signal(signal, config):
        return signal
    next_action = "BREAKOUT_BUY_TIMING" if signal.breakout_confirmed or signal.breakout_score >= 88.0 else "BUY_T_TIMING"
    return _with_buy_point_subtype(replace(signal, action=next_action))


def _risk_on_continuation_add_signal(signal: BacktestSignal, config: DividendTBacktestConfig) -> bool:
    if not config.enable_risk_on_continuation_add:
        return False
    if signal.action in {
        "BUY_T_TIMING",
        "BREAKOUT_BUY_TIMING",
        "SELL_T_TIMING",
        "STOP_T_WAIT",
        "WAIT_DAILY_WEAK",
        "WAIT_MARKET_CAUTION",
        "WAIT_LATE_SESSION",
        "WAIT_CONFIRMATION",
        "WAIT_STALE_DATA",
        "WATCH_BREAKOUT_NEXT_DAY",
        "WAIT_BREAKOUT_FOLLOW_THROUGH",
    }:
        return False
    if _signal_buy_point_subtype(replace(signal, action="BUY_T_TIMING")) != BUY_POINT_SUBTYPE_PULLBACK_LOW_BUY:
        return False
    if signal.market_environment_state != MARKET_RISK_ON:
        return False
    if signal.market_regime_state not in {"BREAKOUT_ATTACK", "STRONG_TREND", "TREND_WATCH"}:
        return False
    if not _offensive_signal_eligible(signal):
        return False
    if signal.buy_signal_strength < max(config.min_buy_signal_strength, config.risk_on_continuation_min_strength):
        return False
    non_force_confirmations = _non_force_position_confirmation_count(signal)
    force_confirmed = signal.force_ratio >= 1.18 or signal.force_weighted_score >= 68.0
    if non_force_confirmations < config.risk_on_continuation_min_confirmations and not (non_force_confirmations >= 1 and force_confirmed):
        return False
    if signal.sell_pressure_score >= config.attack_exit_sell_pressure_score:
        return False
    if signal.down_probability_1d >= config.attack_exit_down_probability:
        return False
    if signal.down_probability_3d >= config.attack_hard_exit_down_probability:
        return False
    if _offensive_volume_distribution_blocks_entry_signal(signal, config):
        return False
    return True


def _apply_market_environment_filter(
    signal: BacktestSignal,
    point: MarketEnvironmentPoint,
    *,
    config: DividendTBacktestConfig | None = None,
    stock_risk_on_active: bool = False,
) -> BacktestSignal:
    if point.state == MARKET_RISK_ON:
        return _signal_with_market_environment(signal, point)
    if point.state == MARKET_RISK_OFF:
        if config is not None and _stock_market_filter_passthrough_signal(signal, config):
            cap = max(
                point.max_total_position_pct,
                min(config.market_risk_off_passthrough_cap_pct, config.max_signal_position_pct),
            )
            return _cap_signal_total_position(
                _signal_with_market_environment(signal, point, state=MARKET_RISK_ON),
                cap,
            )
        base_target = round(clamp(min(signal.base_position_target_pct, MIN_BASE_POSITION_PCT), 0.0, MAX_BASE_POSITION_PCT), 4)
        return replace(
            _signal_with_market_environment(signal, point),
            action="STOP_T_WAIT",
            trend_state="DOWNTREND",
            market_regime_state="DEFENSIVE",
            base_position_target_pct=base_target,
            t_trade_limit_pct=base_target,
            active_position_cap_pct=0.0,
            max_total_position_pct=base_target,
            buy_signal_strength=0.0,
            kelly_fraction=0.0,
            breakout_confirmed=False,
            pre_breakout_watch=False,
        )
    if point.state in {MARKET_CAUTION, MARKET_NEUTRAL} and (stock_risk_on_active or _individual_stock_risk_on_signal(signal)):
        return _signal_with_market_environment(signal, point, state=MARKET_RISK_ON)
    cap = point.max_total_position_pct
    if point.state == MARKET_CAUTION:
        action = signal.action
        strong_buy = signal.buy_signal_strength >= 84.0 and (
            signal.breakout_confirmed
            or signal.breakout_score >= 92.0
            or (signal.chan_buy_point_type == "buy3" and signal.chan_score >= 80.0)
        )
        if action in {"BUY_T_TIMING", "BREAKOUT_BUY_TIMING"} and not strong_buy:
            action = "WAIT_MARKET_CAUTION"
        return _cap_signal_total_position(
            replace(_signal_with_market_environment(signal, point), action=action),
            cap,
        )
    if point.state == MARKET_NEUTRAL:
        return _cap_signal_total_position(
            _signal_with_market_environment(signal, point),
            cap,
        )
    if not point.allow_new_buy and signal.action in {"BUY_T_TIMING", "BREAKOUT_BUY_TIMING"}:
        return _cap_signal_total_position(
            replace(_signal_with_market_environment(signal, point), action="WAIT_MARKET_CAUTION"),
            cap,
        )
    return _cap_signal_total_position(
        _signal_with_market_environment(signal, point),
        cap,
    )


def _signal_with_market_environment(
    signal: BacktestSignal,
    point: MarketEnvironmentPoint,
    *,
    state: str | None = None,
) -> BacktestSignal:
    return replace(
        signal,
        market_environment_state=state or point.state,
        market_environment_score=point.score,
        market_trend_score=point.trend_score,
        market_breadth_score=point.breadth_score,
        market_amount_score=point.amount_score,
        market_limit_structure_score=point.limit_structure_score,
        market_industry_diffusion_score=point.industry_diffusion_score,
        market_model_state_score=point.model_state_score,
        model_holding_win_rate=point.model_holding_win_rate,
        model_holding_profit_spread=point.model_holding_profit_spread,
        model_new_buy_success_rate=point.model_new_buy_success_rate,
    )


def _apply_sell_point_hit_rate_calibration(signal: BacktestSignal) -> BacktestSignal:
    if signal.action == "SELL_T_TIMING":
        return replace(
            signal,
            action="WAIT_CONFIRMATION",
            sell_reference_price=None,
            buy_back_reference_price=None,
        )
    if signal.action != "STOP_T_WAIT":
        return signal
    if signal.capital_flow_confirmation_state != "DIVERGENT" and signal.vwap_support_score < 50.0:
        return signal
    return replace(
        signal,
        action="WAIT_CONFIRMATION",
        sell_reference_price=None,
        buy_back_reference_price=None,
        stop_price=None,
    )


def _next_stock_risk_on_bars_remaining(
    *,
    signal: BacktestSignal,
    config: DividendTBacktestConfig,
    market_environment: MarketEnvironmentPoint,
    current_bars: int,
) -> int:
    if not config.enable_stock_risk_on_regime:
        return 0
    if market_environment.state == MARKET_RISK_OFF:
        return 0
    if _stock_risk_on_exit_signal(signal, config):
        return 0
    if _individual_stock_risk_on_signal(signal):
        return max(current_bars, config.stock_risk_on_hold_bars)
    if current_bars > 0 and _stock_risk_on_sustain_signal(signal, config):
        return max(current_bars, config.stock_risk_on_sustain_bars)
    return current_bars


def _individual_stock_risk_on_signal(signal: BacktestSignal) -> bool:
    if not _offensive_signal_eligible(signal):
        return False
    if signal.action not in {"BUY_T_TIMING", "BREAKOUT_BUY_TIMING", "WAIT_STRONG_TREND", "WATCH_BREAKOUT_NEXT_DAY"}:
        return False
    strong_trend = (
        signal.market_regime_state in {"BREAKOUT_ATTACK", "STRONG_TREND", "TREND_WATCH"}
        and (signal.trend_state == "UPTREND" or signal.breakout_score >= 84.0)
        and signal.buy_signal_strength >= 70.0
    )
    if not strong_trend:
        return False
    breakout_confirmed = signal.breakout_confirmed or signal.breakout_score >= 88.0
    buy3_confirmed = signal.chan_buy_point_type == "buy3" and signal.chan_score >= 76.0
    flow_confirmed = _signal_capital_flow_confirmed(signal, min_score=62.0)
    volume_confirmed = _volume_price_confirmed(signal)
    force_confirmed = signal.force_ratio >= 1.18 or signal.force_weighted_score >= 68.0
    confirmations = sum((breakout_confirmed, buy3_confirmed, flow_confirmed, volume_confirmed, force_confirmed))
    required_confirmations = 2 if signal.action in {"BUY_T_TIMING", "BREAKOUT_BUY_TIMING"} else 3
    return confirmations >= required_confirmations


def _stock_market_filter_passthrough_signal(signal: BacktestSignal, config: DividendTBacktestConfig) -> bool:
    if signal.action not in {"BUY_T_TIMING", "BREAKOUT_BUY_TIMING", "WAIT_STRONG_TREND", "WATCH_BREAKOUT_NEXT_DAY"}:
        return False
    if signal.market_regime_state not in {"BREAKOUT_ATTACK", "STRONG_TREND"}:
        return False
    if signal.trend_state != "UPTREND" and signal.breakout_score < 90.0:
        return False
    if signal.buy_signal_strength < 78.0:
        return False
    if signal.probability_state == "DOWN_RISK":
        return False
    if signal.chan_sell_point_type in {"sell2", "sell3"} or signal.chan_structure_type == "breakdown":
        return False
    if signal.sell_pressure_score >= min(config.attack_exit_sell_pressure_score, 76.0):
        return False
    if signal.down_probability_1d >= min(config.attack_exit_down_probability, 0.60):
        return False
    if signal.down_probability_3d >= min(config.attack_hard_exit_down_probability, 0.62):
        return False
    if _offensive_volume_distribution_blocks_entry_signal(signal, config):
        return False
    return _non_force_position_confirmation_count(signal) >= 3


def _stock_risk_on_sustain_signal(signal: BacktestSignal, config: DividendTBacktestConfig) -> bool:
    if _stock_risk_on_exit_signal(signal, config):
        return False
    if signal.action in {"SELL_T_TIMING", "STOP_T_WAIT", "WAIT_DAILY_WEAK", "WAIT_MARKET_CAUTION"}:
        return False
    constructive = signal.market_regime_state in {"BREAKOUT_ATTACK", "STRONG_TREND", "TREND_WATCH"} and (
        signal.trend_state == "UPTREND"
        or signal.breakout_score >= 82.0
        or (signal.chan_buy_point_type == "buy3" and signal.chan_score >= 72.0)
        or signal.post_breakout_volume_persistence_score >= 68.0
        or signal.vwap_support_score >= 68.0
    )
    support = (
        _signal_capital_flow_confirmed(signal, min_score=58.0)
        or signal.force_weighted_score >= 52.0
        or signal.force_ratio >= 0.88
        or signal.post_breakout_volume_persistence_score >= 68.0
        or signal.vwap_support_score >= 68.0
    )
    return (
        constructive
        and support
        and signal.sell_pressure_score < config.attack_exit_sell_pressure_score
        and signal.down_probability_1d < config.attack_exit_down_probability
        and signal.down_probability_3d < config.attack_hard_exit_down_probability
    )


def _stock_risk_on_exit_signal(signal: BacktestSignal, config: DividendTBacktestConfig) -> bool:
    return (
        signal.action in {"STOP_T_WAIT", "WAIT_DAILY_WEAK"}
        or signal.market_regime_state == "DEFENSIVE"
        or signal.probability_state == "DOWN_RISK"
        or signal.chan_sell_point_type in {"sell2", "sell3"}
        or signal.chan_structure_type == "breakdown"
        or signal.sell_pressure_score >= config.attack_hard_exit_sell_pressure_score
        or signal.down_probability_1d >= config.attack_hard_exit_down_probability
        or signal.down_probability_3d >= config.attack_hard_exit_down_probability
        or _offensive_volume_distribution_hard_exit_signal(signal, config)
    )


def _cap_signal_total_position(signal: BacktestSignal, max_total_position_pct: float) -> BacktestSignal:
    base_target = round(clamp(signal.base_position_target_pct, 0.0, MAX_BASE_POSITION_PCT), 4)
    max_total = round(clamp(max(max_total_position_pct, base_target), 0.0, 1.0), 4)
    active_cap = round(max(0.0, max_total - base_target), 4)
    return replace(
        signal,
        t_trade_limit_pct=min(signal.t_trade_limit_pct if signal.t_trade_limit_pct > 0 else max_total, max_total),
        active_position_cap_pct=active_cap,
        max_total_position_pct=max_total,
    )


def _base_target_pct(signal: BacktestSignal, config: DividendTBacktestConfig) -> float:
    if signal.market_regime_state == "DEFENSIVE":
        upper = MAX_BASE_POSITION_PCT
    else:
        upper = MAX_BASE_POSITION_PCT
    target = min(signal.base_position_target_pct, upper)
    if signal.fundamental_score < 50.0:
        return 0.0
    if signal.market_regime_state == "DEFENSIVE":
        return round(clamp(target, 0.0, MIN_BASE_POSITION_PCT), 4)
    return round(clamp(target, MIN_BASE_POSITION_PCT, MAX_BASE_POSITION_PCT), 4)


def _next_active_base_target_pct(
    *,
    signal: BacktestSignal,
    config: DividendTBacktestConfig,
    current_target_pct: float,
    strong_regime_streak: int,
    defensive_regime_streak: int,
    non_strong_regime_streak: int,
) -> float:
    raw_target = _base_target_pct(signal, config)
    if signal.market_regime_state == "STRONG_TREND":
        if strong_regime_streak >= config.strong_trend_confirm_signals:
            return raw_target
        return min(current_target_pct, MAX_BASE_POSITION_PCT)
    if signal.market_regime_state == "DEFENSIVE":
        if signal.trend_state == "DOWNTREND" or defensive_regime_streak >= config.defensive_confirm_signals:
            return raw_target
        return current_target_pct
    if current_target_pct > MAX_BASE_POSITION_PCT:
        if non_strong_regime_streak >= config.trend_exit_confirm_signals:
            return raw_target
        return current_target_pct
    return raw_target


def _next_attack_state(
    *,
    signal: BacktestSignal,
    config: DividendTBacktestConfig,
    current_state: str,
    confirm_streak: int,
    state_age_bars: int,
    active_profit_pct: float = 0.0,
    active_peak_profit_pct: float = 0.0,
    beta_hold_exit_confirmed: bool = True,
    beta_hold_soft_exit_confirmed: bool = True,
    beta_hold_distribution_confirmed: bool = True,
    attack_exit_confirmed: bool = True,
    attack_distribution_confirmed: bool = True,
) -> tuple[str, int]:
    if not config.enable_attack_state_machine:
        return ATTACK_INACTIVE, 0
    if current_state == ATTACK_BETA_HOLD:
        if _beta_hold_hard_exit_signal(
            signal,
            config,
            active_profit_pct=active_profit_pct,
            active_peak_profit_pct=active_peak_profit_pct,
        ):
            if beta_hold_exit_confirmed:
                return ATTACK_INACTIVE, 0
            return ATTACK_BETA_HOLD, max(confirm_streak, config.attack_full_confirm_signals)
        if _beta_hold_distribution_reduce_signal(
            signal,
            config,
            active_profit_pct=active_profit_pct,
            active_peak_profit_pct=active_peak_profit_pct,
        ):
            if not beta_hold_distribution_confirmed:
                return ATTACK_BETA_HOLD, max(confirm_streak, config.attack_full_confirm_signals)
            return ATTACK_FULL, max(confirm_streak, config.attack_full_confirm_signals)
        if state_age_bars < config.beta_hold_min_bars or _beta_hold_sustain_signal(signal, config):
            return ATTACK_BETA_HOLD, max(confirm_streak, config.attack_full_confirm_signals)
        if _attack_exit_signal(signal, config):
            if not beta_hold_soft_exit_confirmed:
                return ATTACK_BETA_HOLD, max(confirm_streak, config.attack_full_confirm_signals)
            return ATTACK_CONFIRMED, max(1, min(confirm_streak, config.attack_full_confirm_signals))

    if _attack_hard_exit_signal(
        signal,
        config,
        active_profit_pct=active_profit_pct,
        active_peak_profit_pct=active_peak_profit_pct,
    ):
        return ATTACK_INACTIVE, 0
    distribution_state = _attack_volume_distribution_next_state(
        signal=signal,
        config=config,
        current_state=current_state,
        active_profit_pct=active_profit_pct,
        active_peak_profit_pct=active_peak_profit_pct,
    )
    if distribution_state is not None:
        if current_state != ATTACK_INACTIVE and not attack_distribution_confirmed:
            return current_state, confirm_streak
        return distribution_state, min(confirm_streak, _attack_rank(distribution_state))

    if _beta_hold_entry_signal(signal, config):
        return ATTACK_BETA_HOLD, max(confirm_streak + 1, config.attack_full_confirm_signals)

    confirmed = _attack_confirm_signal(signal, config)
    if confirmed:
        next_confirm_streak = confirm_streak + 1
        if next_confirm_streak >= config.attack_full_confirm_signals:
            return ATTACK_FULL, next_confirm_streak
        return ATTACK_CONFIRMED, next_confirm_streak

    if (
        current_state != ATTACK_INACTIVE
        and _offensive_hold_extension_signal(signal, config)
        and (state_age_bars < config.trend_follow_min_hold_bars or signal.market_regime_state in {"BREAKOUT_ATTACK", "STRONG_TREND"})
    ):
        return current_state, confirm_streak

    if _attack_exit_signal(signal, config):
        if (
            current_state != ATTACK_INACTIVE
            and not attack_exit_confirmed
            and _attack_soft_exit_defer_signal(
                signal,
                config,
                current_state=current_state,
                active_profit_pct=active_profit_pct,
                active_peak_profit_pct=active_peak_profit_pct,
            )
        ):
            return current_state, confirm_streak
        if current_state != ATTACK_INACTIVE and state_age_bars < config.attack_min_hold_bars and _attack_grace_signal(signal, config):
            return current_state, confirm_streak
        return ATTACK_INACTIVE, 0

    if current_state != ATTACK_INACTIVE and state_age_bars < config.attack_min_hold_bars and _attack_grace_signal(signal, config):
        return current_state, confirm_streak
    if current_state == ATTACK_FULL and _attack_full_sustain_signal(signal, config):
        return ATTACK_FULL, confirm_streak
    if current_state == ATTACK_FULL and _attack_sustain_signal(signal, config):
        return ATTACK_WATCH, 0
    if current_state == ATTACK_CONFIRMED and _attack_sustain_signal(signal, config):
        return ATTACK_CONFIRMED, confirm_streak
    if _attack_watch_signal(signal, config) or (current_state == ATTACK_WATCH and _attack_sustain_signal(signal, config)):
        return ATTACK_WATCH, 0
    return ATTACK_INACTIVE, 0


def _attack_watch_signal(signal: BacktestSignal, config: DividendTBacktestConfig) -> bool:
    return (
        signal.pre_breakout_watch
        or signal.chan_buy_point_type == "buy3"
        or signal.action == "WATCH_BREAKOUT_NEXT_DAY"
        or (
            signal.breakout_score >= config.attack_watch_min_breakout_score
            and signal.sell_pressure_score < config.attack_exit_sell_pressure_score
            and signal.down_probability_1d < config.attack_exit_down_probability
        )
    )


def _attack_confirm_signal(signal: BacktestSignal, config: DividendTBacktestConfig) -> bool:
    if signal.action not in {"BREAKOUT_BUY_TIMING", "BUY_T_TIMING"}:
        return False
    chan_confirmed = signal.chan_buy_point_type == "buy3" and signal.chan_score >= 76.0
    volume_confirmed = (
        signal.volume_price_score >= 72.0
        and (signal.volume_breakout_score >= 70.0 or signal.post_breakout_volume_persistence_score >= 70.0)
        and signal.high_volume_stall_score < 72.0
    )
    return (
        (signal.breakout_confirmed or chan_confirmed or volume_confirmed)
        and (signal.breakout_score >= config.attack_confirm_min_breakout_score or chan_confirmed or volume_confirmed)
        and signal.buy_signal_strength >= config.attack_confirm_min_buy_strength
        and signal.market_regime_state in {"BREAKOUT_ATTACK", "STRONG_TREND"}
        and (config.attack_exit_force_ratio <= 0 or signal.force_ratio >= config.attack_exit_force_ratio or volume_confirmed)
        and signal.sell_pressure_score < config.attack_exit_sell_pressure_score
        and signal.down_probability_1d < config.attack_exit_down_probability
    )


def _attack_sustain_signal(signal: BacktestSignal, config: DividendTBacktestConfig) -> bool:
    return (
        signal.market_regime_state in {"BREAKOUT_ATTACK", "STRONG_TREND", "TREND_WATCH"}
        and signal.chan_sell_point_type not in {"sell1", "sell2", "sell3"}
        and signal.sell_pressure_score < config.attack_exit_sell_pressure_score
        and (
            config.attack_exit_force_ratio <= 0
            or signal.force_ratio >= config.attack_exit_force_ratio
            or signal.post_breakout_volume_persistence_score >= 68.0
            or signal.vwap_support_score >= 68.0
        )
        and signal.down_probability_1d < config.attack_exit_down_probability
        and signal.action not in {"SELL_T_TIMING", "STOP_T_WAIT", "WAIT_DAILY_WEAK"}
    )


def _attack_full_sustain_signal(signal: BacktestSignal, config: DividendTBacktestConfig) -> bool:
    return (
        signal.market_regime_state in {"BREAKOUT_ATTACK", "STRONG_TREND"}
        and signal.chan_sell_point_type not in {"sell1", "sell2", "sell3"}
        and signal.sell_pressure_score < config.attack_exit_sell_pressure_score
        and (
            config.attack_exit_force_ratio <= 0
            or signal.force_ratio >= config.attack_exit_force_ratio
            or signal.post_breakout_volume_persistence_score >= 70.0
            or signal.vwap_support_score >= 70.0
        )
        and signal.down_probability_1d < config.attack_exit_down_probability
        and signal.action not in {"SELL_T_TIMING", "STOP_T_WAIT", "WAIT_DAILY_WEAK"}
    )


def _attack_exit_signal(signal: BacktestSignal, config: DividendTBacktestConfig) -> bool:
    if _offensive_volume_distribution_hard_exit_signal(signal, config):
        return True
    if signal.action == "SELL_T_TIMING" and _offensive_hold_extension_signal(signal, config):
        return False
    volume_price_holds = signal.post_breakout_volume_persistence_score >= 68.0 or signal.vwap_support_score >= 68.0
    return (
        signal.action == "SELL_T_TIMING"
        or signal.chan_sell_point_type in {"sell1", "sell2", "sell3"}
        or signal.chan_structure_type == "breakdown"
        or signal.sell_pressure_score >= config.attack_exit_sell_pressure_score
        or (config.attack_exit_force_ratio > 0 and signal.force_ratio < config.attack_exit_force_ratio and not volume_price_holds)
        or signal.down_probability_1d >= config.attack_exit_down_probability
    )


def _attack_hard_exit_signal(
    signal: BacktestSignal,
    config: DividendTBacktestConfig,
    *,
    active_profit_pct: float = 0.0,
    active_peak_profit_pct: float = 0.0,
) -> bool:
    if signal.action in {"STOP_T_WAIT", "WAIT_DAILY_WEAK"}:
        return not _stop_wait_observation_signal(
            signal=signal,
            config=config,
            active_profit_pct=active_profit_pct,
            active_peak_profit_pct=active_peak_profit_pct,
        )
    return (
        signal.market_regime_state == "DEFENSIVE"
        or signal.probability_state == "DOWN_RISK"
        or signal.chan_sell_point_type == "sell3"
        or signal.chan_structure_type == "breakdown"
        or signal.sell_pressure_score >= config.attack_hard_exit_sell_pressure_score
        or signal.down_probability_1d >= config.attack_hard_exit_down_probability
        or _offensive_volume_distribution_hard_exit_signal(signal, config)
    )


def _attack_soft_exit_defer_signal(
    signal: BacktestSignal,
    config: DividendTBacktestConfig,
    *,
    current_state: str,
    active_profit_pct: float = 0.0,
    active_peak_profit_pct: float = 0.0,
) -> bool:
    if current_state not in {ATTACK_WATCH, ATTACK_CONFIRMED, ATTACK_FULL}:
        return False
    if _attack_hard_exit_signal(
        signal,
        config,
        active_profit_pct=active_profit_pct,
        active_peak_profit_pct=active_peak_profit_pct,
    ):
        return False
    if signal.market_regime_state not in {"BREAKOUT_ATTACK", "STRONG_TREND", "TREND_WATCH"}:
        return False
    if signal.probability_state == "DOWN_RISK" or signal.chan_sell_point_type == "sell3" or signal.chan_structure_type == "breakdown":
        return False
    if signal.sell_pressure_score >= config.attack_hard_exit_sell_pressure_score:
        return False
    if signal.down_probability_1d >= config.attack_hard_exit_down_probability:
        return False
    if _trend_follow_hold_signal(signal, config) or _offensive_hold_extension_signal(signal, config):
        return True
    trend_intact = signal.trend_state == "UPTREND" or signal.breakout_score >= 82.0 or signal.chan_buy_point_type == "buy3"
    support_intact = (
        signal.vwap_support_score >= 64.0
        or signal.post_breakout_volume_persistence_score >= 64.0
        or _signal_capital_flow_confirmed(signal, min_score=58.0)
    )
    return trend_intact and support_intact and _non_force_position_confirmation_count(signal) >= 2


def _attack_volume_distribution_next_state(
    *,
    signal: BacktestSignal,
    config: DividendTBacktestConfig,
    current_state: str,
    active_profit_pct: float = 0.0,
    active_peak_profit_pct: float = 0.0,
) -> str | None:
    if current_state == ATTACK_INACTIVE:
        return None
    if _offensive_volume_distribution_hard_exit_signal(
        signal,
        config,
        active_profit_pct=active_profit_pct,
        active_peak_profit_pct=active_peak_profit_pct,
    ):
        return ATTACK_INACTIVE
    if not _offensive_volume_distribution_reduce_signal(
        signal,
        config,
        active_profit_pct=active_profit_pct,
        active_peak_profit_pct=active_peak_profit_pct,
    ):
        return None
    if current_state == ATTACK_FULL:
        return ATTACK_CONFIRMED
    if current_state == ATTACK_CONFIRMED:
        return ATTACK_WATCH
    if current_state == ATTACK_WATCH and (
        signal.sell_pressure_score >= config.attack_exit_sell_pressure_score
        or signal.down_probability_1d >= config.attack_exit_down_probability
        or signal.down_probability_3d >= config.attack_hard_exit_down_probability
    ):
        return ATTACK_INACTIVE
    return None


def _offensive_volume_distribution_reduce_signal(
    signal: BacktestSignal,
    config: DividendTBacktestConfig,
    *,
    active_profit_pct: float = 0.0,
    active_peak_profit_pct: float = 0.0,
) -> bool:
    state = _volume_price_distribution_state(signal, config)
    if state == VOLUME_PRICE_ROTATION:
        return False
    high_profit_position = _offensive_volume_distribution_high_profit_position(
        config=config,
        active_profit_pct=active_profit_pct,
        active_peak_profit_pct=active_peak_profit_pct,
    )
    low_absorption = _offensive_volume_distribution_low_absorption_signal(signal, config)
    if state == VOLUME_PRICE_DISTRIBUTION:
        return _volume_price_distribution_hard_breakdown_signal(signal, config) and (
            high_profit_position or low_absorption or active_profit_pct <= -config.offensive_stop_hold_loss_pct
        )
    if state != VOLUME_PRICE_WARNING:
        return False
    pressure_count = _offensive_volume_distribution_pressure_count(signal, config)
    return high_profit_position and low_absorption and pressure_count >= config.offensive_volume_distribution_reduce_pressure_count


def _offensive_volume_distribution_soft_signal(signal: BacktestSignal, config: DividendTBacktestConfig) -> bool:
    return _volume_price_distribution_state(signal, config) in {VOLUME_PRICE_WARNING, VOLUME_PRICE_DISTRIBUTION}


def _offensive_volume_distribution_blocks_entry_signal(signal: BacktestSignal, config: DividendTBacktestConfig) -> bool:
    return _volume_price_distribution_state(signal, config) == VOLUME_PRICE_DISTRIBUTION


def _volume_price_distribution_state(signal: BacktestSignal, config: DividendTBacktestConfig) -> str:
    if not config.offensive_volume_distribution_enabled:
        return VOLUME_PRICE_NONE
    if signal.market_regime_state not in {"BREAKOUT_ATTACK", "STRONG_TREND", "TREND_WATCH"}:
        return VOLUME_PRICE_NONE
    stall = signal.high_volume_stall_score >= config.offensive_volume_stall_reduce_score
    up_volume_down = signal.price_up_volume_down_score >= config.offensive_price_up_volume_down_reduce_score
    if not (stall or up_volume_down):
        return VOLUME_PRICE_NONE
    if up_volume_down:
        pressure_count = _offensive_volume_distribution_pressure_count(signal, config)
        if _volume_price_distribution_hard_breakdown_signal(signal, config, pressure_count=pressure_count):
            return VOLUME_PRICE_DISTRIBUTION
        if _price_up_volume_down_main_rise_continuation_signal(signal, config):
            return VOLUME_PRICE_ROTATION
        if not stall:
            return VOLUME_PRICE_ROTATION
    if (
        _offensive_volume_distribution_absorbed(signal, config)
        or _offensive_volume_distribution_continuation_confirmed(signal, config)
        or _strong_trend_volume_distribution_override_signal(signal, config)
    ):
        return VOLUME_PRICE_ROTATION

    pressure_count = _offensive_volume_distribution_pressure_count(signal, config)
    low_absorption = _offensive_volume_distribution_low_absorption_signal(signal, config)
    severe = _offensive_volume_distribution_severe_signal(signal, config)
    if _volume_price_distribution_hard_breakdown_signal(signal, config, pressure_count=pressure_count):
        return VOLUME_PRICE_DISTRIBUTION
    if up_volume_down:
        return VOLUME_PRICE_ROTATION
    if stall and up_volume_down and (low_absorption or pressure_count >= 2 or severe):
        return VOLUME_PRICE_WARNING
    if pressure_count >= 2 and low_absorption:
        return VOLUME_PRICE_WARNING
    return VOLUME_PRICE_ROTATION


def _offensive_volume_distribution_pressure_count(signal: BacktestSignal, config: DividendTBacktestConfig) -> int:
    pressure_flags = (
        signal.sell_pressure_score >= 66.0,
        signal.down_probability_1d >= 0.56,
        signal.down_probability_3d >= 0.58,
        signal.force_ratio < 0.78,
        signal.volume_price_score < 70.0,
        signal.post_breakout_volume_persistence_score < config.offensive_volume_distribution_absorption_persistence_score - 4.0,
        signal.vwap_support_score < config.offensive_volume_distribution_absorption_vwap_score - 2.0,
    )
    return sum(bool(flag) for flag in pressure_flags)


def _offensive_volume_distribution_severe_signal(signal: BacktestSignal, config: DividendTBacktestConfig) -> bool:
    return (
        signal.high_volume_stall_score >= config.offensive_volume_stall_reduce_score + 4.0
        and signal.price_up_volume_down_score >= config.offensive_price_up_volume_down_reduce_score + 4.0
    )


def _offensive_volume_distribution_hard_exit_signal(
    signal: BacktestSignal,
    config: DividendTBacktestConfig,
    *,
    active_profit_pct: float = 0.0,
    active_peak_profit_pct: float = 0.0,
) -> bool:
    if _volume_price_distribution_state(signal, config) != VOLUME_PRICE_DISTRIBUTION:
        return False
    high_profit_position = _offensive_volume_distribution_high_profit_position(
        config=config,
        active_profit_pct=active_profit_pct,
        active_peak_profit_pct=active_peak_profit_pct,
    )
    if not high_profit_position and active_profit_pct > -config.offensive_stop_hold_loss_pct:
        return False
    hard_pressure_count = sum(
        bool(flag)
        for flag in (
            signal.sell_pressure_score >= config.attack_exit_sell_pressure_score,
            signal.down_probability_1d >= config.attack_exit_down_probability,
            signal.down_probability_3d >= 0.62,
            signal.force_ratio < 0.68,
        )
    )
    return hard_pressure_count >= 1 and _offensive_volume_distribution_pressure_count(signal, config) >= 2


def _offensive_volume_distribution_high_profit_position(
    *,
    config: DividendTBacktestConfig,
    active_profit_pct: float,
    active_peak_profit_pct: float,
) -> bool:
    return active_profit_pct >= config.offensive_volume_distribution_min_profit_pct or (
        active_peak_profit_pct >= config.offensive_volume_distribution_min_peak_profit_pct and active_profit_pct >= 0.0
    )


def _offensive_volume_distribution_low_absorption_signal(signal: BacktestSignal, config: DividendTBacktestConfig) -> bool:
    weak_vwap = signal.vwap_support_score < config.offensive_volume_distribution_low_vwap_score
    weak_persistence = signal.post_breakout_volume_persistence_score < config.offensive_volume_distribution_low_persistence_score
    weak_flow = (
        not _signal_capital_flow_confirmed(signal, min_score=62.0)
        and signal.capital_flow_confirmation_score < config.offensive_volume_distribution_low_flow_score
    )
    weak_force = (
        signal.force_ratio < config.offensive_volume_distribution_low_force_ratio
        and signal.force_weighted_score < config.offensive_volume_distribution_low_force_score
    )
    if weak_vwap and weak_persistence:
        return True
    if (weak_vwap or weak_persistence) and weak_flow and weak_force:
        return True
    return signal.volume_price_score < config.offensive_volume_distribution_low_volume_price_score and weak_flow


def _signal_capital_flow_outflow_confirmed(signal: BacktestSignal, *, max_score: float) -> bool:
    if signal.capital_flow_confirmation_state == "CONFIRMED_OUTFLOW":
        return True
    weak_score = (
        signal.capital_flow_score <= max_score
        and signal.capital_flow_confirmation_score <= max_score
        and signal.capital_flow_confidence >= 0.45
    )
    weak_force = signal.force_ratio < 0.72 and signal.force_weighted_score < 50.0
    if signal.capital_flow_source_type == "REAL_MONEY_FLOW":
        return weak_score or (signal.capital_flow_confirmation_score <= max_score - 2.0 and weak_force)
    return weak_score and weak_force


def _offensive_volume_distribution_absorbed(signal: BacktestSignal, config: DividendTBacktestConfig) -> bool:
    support = (
        signal.post_breakout_volume_persistence_score >= config.offensive_volume_distribution_absorption_persistence_score
        and signal.vwap_support_score >= config.offensive_volume_distribution_absorption_vwap_score
        and (
            _signal_capital_flow_confirmed(signal, min_score=62.0)
            or signal.capital_flow_confirmation_score >= 72.0
            or signal.force_weighted_score >= 54.0
        )
    )
    continuation_confirmed = _offensive_volume_distribution_continuation_confirmed(signal, config)
    return (
        (support or continuation_confirmed)
        and signal.sell_pressure_score < 72.0
        and signal.down_probability_1d < 0.60
        and signal.down_probability_3d < 0.62
        and signal.chan_sell_point_type not in {"sell2", "sell3"}
        and signal.chan_structure_type != "breakdown"
    )


def _offensive_volume_distribution_continuation_confirmed(signal: BacktestSignal, config: DividendTBacktestConfig) -> bool:
    confirmations = sum(
        bool(flag)
        for flag in (
            signal.breakout_confirmed or signal.breakout_score >= 88.0,
            signal.chan_buy_point_type == "buy3" and signal.chan_score >= 76.0,
            _signal_capital_flow_confirmed(signal, min_score=62.0),
            signal.post_breakout_volume_persistence_score >= config.offensive_volume_distribution_absorption_persistence_score,
            signal.vwap_support_score >= config.offensive_volume_distribution_absorption_vwap_score,
            signal.volume_breakout_score >= 74.0,
        )
    )
    return confirmations >= config.offensive_volume_distribution_continuation_min_confirmations and signal.volume_price_score >= 66.0


def _price_up_volume_down_main_rise_continuation_signal(signal: BacktestSignal, config: DividendTBacktestConfig) -> bool:
    if signal.pretrade_volume_price_state != "price_up_volume_down":
        return False
    if signal.pretrade_volume_price_lookback_bars < max(16, config.volume_price_continuation_lookback_bars // 2):
        return False
    if signal.pretrade_price_return_pct < config.volume_price_continuation_min_return_pct:
        return False
    if signal.pretrade_volume_ratio_to_prev > config.volume_price_continuation_max_volume_ratio:
        return False
    if signal.market_regime_state not in {"BREAKOUT_ATTACK", "STRONG_TREND", "TREND_WATCH"}:
        return False
    if signal.probability_state == "DOWN_RISK" or signal.chan_sell_point_type in {"sell2", "sell3"}:
        return False
    if signal.chan_structure_type == "breakdown":
        return False
    if signal.sell_pressure_score >= config.attack_exit_sell_pressure_score:
        return False
    if signal.down_probability_1d >= config.attack_exit_down_probability:
        return False
    if signal.down_probability_3d >= config.attack_hard_exit_down_probability:
        return False
    trend_intact = (
        signal.trend_state == "UPTREND"
        or signal.breakout_confirmed
        or signal.breakout_score >= 84.0
        or (signal.chan_buy_point_type == "buy3" and signal.chan_score >= 74.0)
    )
    support_intact = (
        signal.vwap_support_score >= 64.0
        or signal.post_breakout_volume_persistence_score >= 64.0
        or signal.low_volume_pullback_score >= 72.0
    )
    flow_not_out = not _signal_capital_flow_outflow_confirmed(
        signal,
        max_score=config.offensive_volume_distribution_distribution_flow_score,
    )
    return trend_intact and support_intact and flow_not_out and _non_force_position_confirmation_count(signal) >= 2


def _strong_trend_volume_distribution_override_signal(signal: BacktestSignal, config: DividendTBacktestConfig) -> bool:
    if signal.market_regime_state not in {"BREAKOUT_ATTACK", "STRONG_TREND", "TREND_WATCH"}:
        return False
    if signal.probability_state == "DOWN_RISK":
        return False
    if signal.chan_sell_point_type in {"sell2", "sell3"} or signal.chan_structure_type == "breakdown":
        return False
    if signal.sell_pressure_score >= config.attack_exit_sell_pressure_score:
        return False
    if signal.down_probability_1d >= config.attack_exit_down_probability:
        return False
    if signal.down_probability_3d >= config.attack_exit_down_probability:
        return False
    if signal.volume_price_score < 58.0:
        return False
    if signal.buy_signal_strength < max(config.beta_hold_min_strength, config.attack_confirm_min_buy_strength - 6.0):
        return False

    trend_confirmed = (
        signal.trend_state == "UPTREND"
        or signal.breakout_confirmed
        or signal.breakout_score >= 86.0
        or _qualified_breakout_hold_signal(signal, config)
        or (signal.chan_buy_point_type == "buy3" and signal.chan_score >= 74.0)
    )
    if not trend_confirmed:
        return False

    has_absorption_floor = (
        signal.post_breakout_volume_persistence_score >= 62.0
        or signal.vwap_support_score >= 62.0
        or signal.volume_breakout_score >= 68.0
        or signal.low_volume_pullback_score >= 74.0
    )
    if not has_absorption_floor:
        return False

    structural_confirmations = sum(
        bool(flag)
        for flag in (
            signal.breakout_confirmed or signal.breakout_score >= 88.0,
            signal.chan_buy_point_type == "buy3" and signal.chan_score >= 76.0,
            _signal_capital_flow_confirmed(signal, min_score=60.0),
            signal.post_breakout_volume_persistence_score >= 62.0 or signal.vwap_support_score >= 62.0,
            signal.volume_breakout_score >= 68.0,
        )
    )
    return _non_force_position_confirmation_count(signal) >= 3 and structural_confirmations >= 2


def _volume_price_distribution_hard_breakdown_signal(
    signal: BacktestSignal,
    config: DividendTBacktestConfig,
    *,
    pressure_count: int | None = None,
) -> bool:
    if pressure_count is None:
        pressure_count = _offensive_volume_distribution_pressure_count(signal, config)
    stall = signal.high_volume_stall_score >= config.offensive_volume_stall_reduce_score
    up_volume_down = signal.price_up_volume_down_score >= config.offensive_price_up_volume_down_reduce_score
    repeated_up_volume_down = (
        up_volume_down
        and signal.pretrade_volume_price_state == "price_up_volume_down"
        and signal.pretrade_price_return_pct >= config.volume_price_continuation_min_return_pct
    )
    if not (up_volume_down and (stall or repeated_up_volume_down)):
        return False

    persistent_divergence = pressure_count >= max(3, config.offensive_volume_distribution_distribution_pressure_count)
    hard_divergence = signal.price_up_volume_down_score >= config.offensive_volume_distribution_hard_up_down_score and (
        signal.high_volume_stall_score >= config.offensive_volume_distribution_hard_stall_score or repeated_up_volume_down
    )
    if not (persistent_divergence or hard_divergence):
        return False

    vwap_or_structure_break = (
        signal.vwap_support_score <= config.offensive_volume_distribution_distribution_vwap_break_score
        or signal.post_breakout_volume_persistence_score <= config.offensive_volume_distribution_distribution_vwap_break_score
        or signal.chan_sell_point_type in {"sell2", "sell3"}
        or signal.chan_structure_type in {"weakening", "breakdown"}
    )
    if not vwap_or_structure_break:
        return False

    if not _signal_capital_flow_outflow_confirmed(
        signal,
        max_score=config.offensive_volume_distribution_distribution_flow_score,
    ):
        return False

    down_probability_rising = (
        signal.probability_state == "DOWN_RISK"
        or signal.sell_pressure_score >= config.attack_exit_sell_pressure_score
        or signal.down_probability_1d >= config.attack_exit_down_probability
        or signal.down_probability_3d >= 0.62
    )
    return down_probability_rising


def _beta_hold_core_floor_hard_break_signal(signal: BacktestSignal, config: DividendTBacktestConfig) -> bool:
    hard_structure_break = signal.chan_sell_point_type == "sell3" or signal.chan_structure_type == "breakdown"
    if not hard_structure_break:
        return False
    vwap_break = (
        signal.vwap_support_score <= config.beta_hold_core_break_vwap_score
        and signal.post_breakout_volume_persistence_score <= config.offensive_volume_distribution_low_persistence_score
    )
    if not vwap_break:
        return False
    if not _signal_capital_flow_outflow_confirmed(signal, max_score=config.beta_hold_core_break_flow_score):
        return False
    down_confirmed = (
        signal.probability_state == "DOWN_RISK"
        or signal.sell_pressure_score >= config.attack_exit_sell_pressure_score
        or signal.down_probability_1d >= config.attack_exit_down_probability
        or signal.down_probability_3d >= 0.62
    )
    return down_confirmed


def _beta_hold_main_rise_core_floor_signal(signal: BacktestSignal, config: DividendTBacktestConfig) -> bool:
    if not config.enable_beta_hold_state:
        return False
    if signal.market_environment_state != MARKET_RISK_ON:
        return False
    if signal.market_regime_state not in {"BREAKOUT_ATTACK", "STRONG_TREND", "TREND_WATCH"}:
        return False
    if signal.action in {"WAIT_MARKET_CAUTION", "WAIT_LATE_SESSION", "WAIT_STALE_DATA"}:
        return False
    if signal.sell_pressure_score >= max(config.attack_hard_exit_sell_pressure_score + 4.0, 92.0):
        return False
    if signal.down_probability_1d >= max(config.attack_hard_exit_down_probability + 0.04, 0.72):
        return False
    if signal.down_probability_3d >= max(config.attack_hard_exit_down_probability + 0.04, 0.72):
        return False
    if _beta_hold_core_floor_hard_break_signal(signal, config):
        return False

    confirmations = _non_force_position_confirmation_count(signal)
    if confirmations < config.beta_hold_main_rise_core_min_confirmations:
        return False
    trend_confirmed = (
        signal.trend_state == "UPTREND"
        or signal.breakout_confirmed
        or signal.breakout_score >= 86.0
        or (signal.chan_buy_point_type == "buy3" and signal.chan_score >= 74.0)
    )
    support_intact = (
        signal.vwap_support_score >= 64.0
        or signal.post_breakout_volume_persistence_score >= 66.0
        or _signal_capital_flow_confirmed(signal, min_score=60.0)
        or signal.volume_breakout_score >= 70.0
    )
    stock_strong = (
        signal.buy_signal_strength >= config.beta_hold_min_strength
        or signal.breakout_score >= 88.0
        or (signal.chan_buy_point_type == "buy3" and signal.chan_score >= 76.0)
    )
    return trend_confirmed and support_intact and stock_strong


def _attack_grace_signal(signal: BacktestSignal, config: DividendTBacktestConfig) -> bool:
    return (
        signal.action not in {"STOP_T_WAIT", "WAIT_DAILY_WEAK"}
        and signal.market_regime_state in {"BREAKOUT_ATTACK", "STRONG_TREND", "TREND_WATCH", "RANGE_T"}
        and signal.chan_sell_point_type not in {"sell1", "sell2", "sell3"}
        and signal.sell_pressure_score < config.attack_hard_exit_sell_pressure_score
        and signal.down_probability_1d < config.attack_hard_exit_down_probability
    )


def _trend_follow_hold_signal(signal: BacktestSignal, config: DividendTBacktestConfig) -> bool:
    if signal.action in {"STOP_T_WAIT", "WAIT_DAILY_WEAK"}:
        return False
    if signal.chan_sell_point_type in {"sell1", "sell2", "sell3"} or signal.chan_structure_type == "breakdown":
        return False
    constructive_trend = (
        signal.trend_state == "UPTREND"
        or (
            signal.breakout_score >= 84.0
            and signal.market_regime_state in {"BREAKOUT_ATTACK", "STRONG_TREND", "TREND_WATCH"}
            and signal.sell_pressure_score < 66.0
        )
        or (signal.chan_buy_point_type == "buy3" and signal.chan_score >= 72.0)
    )
    return (
        signal.market_regime_state in {"BREAKOUT_ATTACK", "STRONG_TREND", "TREND_WATCH"}
        and constructive_trend
        and (
            _signal_capital_flow_confirmed(signal, min_score=62.0)
            or signal.post_breakout_volume_persistence_score >= 68.0
            or signal.vwap_support_score >= 68.0
        )
        and (
            signal.force_ratio >= 0.72
            or signal.force_weighted_score >= 48.0
            or (signal.capital_flow_confirmation_score >= 70.0 and signal.sell_pressure_score < 60.0)
            or signal.post_breakout_volume_persistence_score >= 70.0
        )
        and signal.sell_pressure_score < config.attack_hard_exit_sell_pressure_score
        and signal.down_probability_1d < config.attack_hard_exit_down_probability
        and signal.down_probability_3d < config.attack_hard_exit_down_probability
    )


def _offensive_hold_extension_signal(signal: BacktestSignal, config: DividendTBacktestConfig) -> bool:
    if not config.offensive_hold_extension_enabled:
        return False
    if signal.action in {"STOP_T_WAIT", "WAIT_DAILY_WEAK"}:
        return _offensive_soft_stop_extension_signal(signal, config)
    if signal.chan_sell_point_type in {"sell2", "sell3"} or signal.chan_structure_type == "breakdown":
        return False
    if signal.market_regime_state not in {"BREAKOUT_ATTACK", "STRONG_TREND", "TREND_WATCH"}:
        return False
    constructive = (
        signal.trend_state == "UPTREND"
        or signal.breakout_score >= 82.0
        or (signal.chan_buy_point_type == "buy3" and signal.chan_score >= 72.0)
        or signal.post_breakout_volume_persistence_score >= 70.0
    )
    support = (
        _signal_capital_flow_confirmed(signal, min_score=58.0)
        or signal.force_ratio >= 0.78
        or signal.force_weighted_score >= 50.0
        or signal.capital_flow_confirmation_score >= 68.0
        or signal.post_breakout_volume_persistence_score >= 68.0
        or signal.vwap_support_score >= 68.0
    )
    return (
        constructive
        and support
        and signal.sell_pressure_score < config.attack_hard_exit_sell_pressure_score
        and signal.down_probability_1d < config.attack_hard_exit_down_probability
        and signal.down_probability_3d < config.attack_hard_exit_down_probability
    )


def _offensive_soft_stop_extension_signal(signal: BacktestSignal, config: DividendTBacktestConfig) -> bool:
    if not config.offensive_hold_extension_enabled:
        return False
    if signal.market_regime_state not in {"BREAKOUT_ATTACK", "STRONG_TREND"}:
        return False
    if signal.probability_state == "DOWN_RISK" or signal.chan_sell_point_type == "sell3" or signal.chan_structure_type == "breakdown":
        return False
    if signal.sell_pressure_score >= config.attack_hard_exit_sell_pressure_score:
        return False
    if (
        signal.down_probability_1d >= config.attack_hard_exit_down_probability
        or signal.down_probability_3d >= config.attack_hard_exit_down_probability
    ):
        return False
    return (
        signal.trend_state == "UPTREND"
        or signal.breakout_score >= 86.0
        or (signal.chan_buy_point_type == "buy3" and signal.chan_score >= 76.0)
        or signal.post_breakout_volume_persistence_score >= 72.0
    ) and (
        _signal_capital_flow_confirmed(signal, min_score=60.0)
        or signal.force_weighted_score >= 52.0
        or signal.capital_flow_confirmation_score >= 70.0
        or signal.vwap_support_score >= 68.0
    )


def _sell_point_continuation_hold_signal(
    *,
    action: str,
    signal: BacktestSignal,
    config: DividendTBacktestConfig,
    active_profit_pct: float,
    active_peak_profit_pct: float,
) -> bool:
    if not config.offensive_hold_extension_enabled:
        return False
    if action not in {"SELL_T_TIMING", "STOP_T_WAIT", "WAIT_DAILY_WEAK"}:
        return False
    if signal.probability_state == "DOWN_RISK" or signal.chan_sell_point_type == "sell3" or signal.chan_structure_type == "breakdown":
        return False
    if signal.sell_pressure_score >= config.attack_hard_exit_sell_pressure_score:
        return False
    if (
        signal.down_probability_1d >= config.attack_hard_exit_down_probability
        or signal.down_probability_3d >= config.attack_hard_exit_down_probability
    ):
        return False
    if action in {"STOP_T_WAIT", "WAIT_DAILY_WEAK"} and active_profit_pct < -(config.offensive_stop_hold_loss_pct * 1.25):
        return False
    pullback = max(active_peak_profit_pct - active_profit_pct, 0.0)
    if active_peak_profit_pct >= config.offensive_trailing_profit_trigger_pct and pullback >= config.offensive_trailing_pullback_pct:
        return False
    score = _sell_point_continuation_quality_score(signal, config)
    required = config.sell_point_continuation_quality_score
    if action in {"STOP_T_WAIT", "WAIT_DAILY_WEAK"}:
        required += 0.03
    return score >= required


def _sell_point_continuation_quality_score(signal: BacktestSignal, config: DividendTBacktestConfig) -> float:
    if signal.market_regime_state not in {"BREAKOUT_ATTACK", "STRONG_TREND", "TREND_WATCH"}:
        return 0.0
    confirmations = min(_non_force_position_confirmation_count(signal) / 4.0, 1.0)
    trend = 0.0
    if signal.trend_state == "UPTREND":
        trend = 1.0
    elif signal.breakout_score >= 86.0 or (signal.chan_buy_point_type == "buy3" and signal.chan_score >= 76.0):
        trend = 0.82
    elif signal.breakout_score >= 78.0 or signal.chan_buy_point_type == "buy3":
        trend = 0.55
    support = max(
        clamp((signal.vwap_support_score - 56.0) / 28.0, 0.0, 1.0),
        clamp((signal.post_breakout_volume_persistence_score - 56.0) / 28.0, 0.0, 1.0),
        clamp((signal.low_volume_pullback_score - 62.0) / 24.0, 0.0, 1.0),
    )
    flow = (
        1.0
        if _signal_capital_flow_confirmed(signal, min_score=60.0)
        else clamp((signal.capital_flow_confirmation_score - 50.0) / 28.0, 0.0, 1.0)
    )
    force = max(
        clamp((signal.force_ratio - 0.72) / 0.56, 0.0, 1.0),
        clamp((signal.force_weighted_score - 44.0) / 30.0, 0.0, 1.0),
    )
    probability = clamp(
        0.50 * clamp((signal.up_probability_1d - 0.48) / 0.12, 0.0, 1.0)
        + 0.35 * clamp((signal.up_probability_3d - 0.48) / 0.12, 0.0, 1.0)
        - 0.35 * clamp((signal.down_probability_1d - 0.54) / 0.14, 0.0, 1.0),
        0.0,
        1.0,
    )
    volume = _risk_on_volume_price_quality(signal)
    score = 0.24 * trend + 0.20 * support + 0.16 * flow + 0.14 * volume + 0.12 * confirmations + 0.08 * force + 0.06 * probability
    if signal.chan_sell_point_type in {"sell1", "sell2"}:
        score -= 0.14
    if signal.sell_pressure_score >= 72.0:
        score -= 0.12
    elif signal.sell_pressure_score >= 66.0:
        score -= 0.06
    if signal.down_probability_1d >= 0.58 or signal.down_probability_3d >= 0.60:
        score -= 0.12
    if _offensive_volume_distribution_blocks_entry_signal(signal, config):
        score -= 0.18
    elif _offensive_volume_distribution_soft_signal(signal, config):
        score -= 0.06
    return round(clamp(score, 0.0, 1.0), 4)


def _stop_wait_observation_signal(
    *,
    signal: BacktestSignal,
    config: DividendTBacktestConfig,
    active_profit_pct: float,
    active_peak_profit_pct: float,
    beta_hold: bool = False,
) -> bool:
    if signal.action not in {"STOP_T_WAIT", "WAIT_DAILY_WEAK"}:
        return False
    if signal.probability_state == "DOWN_RISK" or signal.chan_sell_point_type == "sell3" or signal.chan_structure_type == "breakdown":
        return False
    if signal.sell_pressure_score >= config.attack_hard_exit_sell_pressure_score:
        return False
    if (
        signal.down_probability_1d >= config.attack_hard_exit_down_probability
        or signal.down_probability_3d >= config.attack_hard_exit_down_probability
    ):
        return False

    max_observation_loss = config.beta_hold_hard_stop_loss_pct if beta_hold else config.offensive_stop_hold_loss_pct * 1.6
    if active_profit_pct < -max_observation_loss:
        return False
    peak_giveback = max(active_peak_profit_pct - active_profit_pct, 0.0)
    if active_peak_profit_pct >= config.offensive_trailing_profit_mid_pct and peak_giveback >= config.offensive_trailing_pullback_mid_pct:
        return False

    trend_context = signal.market_regime_state in {"BREAKOUT_ATTACK", "STRONG_TREND"} or (
        signal.market_regime_state == "TREND_WATCH" and signal.market_environment_state == MARKET_RISK_ON
    )
    if not trend_context:
        return False
    trend_intact = (
        signal.trend_state == "UPTREND"
        or signal.breakout_confirmed
        or signal.breakout_score >= 84.0
        or (signal.chan_buy_point_type == "buy3" and signal.chan_score >= 74.0)
    )
    support_intact = (
        signal.vwap_support_score >= 66.0
        or signal.post_breakout_volume_persistence_score >= 66.0
        or _signal_capital_flow_confirmed(signal, min_score=60.0)
        or signal.force_weighted_score >= 54.0
    )
    risk_mild = (
        signal.sell_pressure_score < config.attack_exit_sell_pressure_score
        and signal.down_probability_1d < config.attack_exit_down_probability
        and signal.down_probability_3d < config.attack_hard_exit_down_probability
    )
    continuation_quality = _sell_point_continuation_quality_score(signal, config)
    return (
        trend_intact
        and support_intact
        and risk_mild
        and continuation_quality >= max(0.38, config.sell_point_continuation_quality_score - 0.12)
    )


def _profit_protection_defer_signal(
    *,
    signal: BacktestSignal,
    config: DividendTBacktestConfig,
    breakout_profit_pct: float,
    active_peak_profit_pct: float,
    sell_fraction: float,
) -> bool:
    if not config.offensive_hold_extension_enabled:
        return False
    if sell_fraction <= 0.0:
        return True
    if signal.probability_state == "DOWN_RISK" or signal.chan_sell_point_type == "sell3" or signal.chan_structure_type == "breakdown":
        return False
    hard_pressure = signal.sell_pressure_score >= config.attack_hard_exit_sell_pressure_score and (
        signal.down_probability_1d >= config.attack_exit_down_probability
        or signal.down_probability_3d >= config.attack_exit_down_probability
        or signal.force_ratio < 0.72
    )
    hard_probability = (
        signal.down_probability_1d >= config.attack_hard_exit_down_probability
        or signal.down_probability_3d >= config.attack_hard_exit_down_probability
    )

    peak_profit = max(active_peak_profit_pct, breakout_profit_pct)
    pullback = max(peak_profit - breakout_profit_pct, 0.0)
    continuation_quality = _sell_point_continuation_quality_score(signal, config)
    continuation = _offensive_risk_on_continuation_signal(signal, config)
    required = max(0.40, config.sell_point_continuation_quality_score - 0.08)
    pressure_confirmed = (
        signal.sell_pressure_score >= config.attack_exit_sell_pressure_score
        or signal.down_probability_1d >= config.attack_exit_down_probability
        or signal.down_probability_3d >= config.attack_exit_down_probability
    )
    force_break = signal.force_ratio < 0.72 and signal.force_weighted_score < config.offensive_volume_distribution_low_force_score
    distribution_exit = _offensive_volume_distribution_hard_exit_signal(
        signal,
        config,
        active_profit_pct=breakout_profit_pct,
        active_peak_profit_pct=peak_profit,
    )
    confirmed_pullback = peak_profit >= config.offensive_trailing_profit_mid_pct and pullback >= config.offensive_trailing_pullback_mid_pct

    if continuation:
        return True
    if continuation_quality >= required:
        return True
    if breakout_profit_pct < config.offensive_trailing_profit_trigger_pct:
        return True
    if not pressure_confirmed and not force_break and not hard_probability and not distribution_exit:
        return True
    if peak_profit < config.offensive_trailing_profit_mid_pct:
        return True
    if pullback < config.offensive_trailing_pullback_pct and continuation_quality >= config.sell_point_continuation_quality_score:
        return True
    if not confirmed_pullback and continuation_quality >= required - 0.10:
        return True
    if distribution_exit and continuation_quality < required:
        return False
    if hard_probability and confirmed_pullback:
        return False
    if hard_pressure and confirmed_pullback and continuation_quality < required - 0.10:
        return False
    return True


def _active_position_profit_pct(*, price: float, t_shares: int, t_cost_basis: float) -> float:
    if t_shares <= 0 or t_cost_basis <= 0:
        return 0.0
    return price / (t_cost_basis / t_shares) - 1.0


def _offensive_risk_on_continuation_signal(signal: BacktestSignal, config: DividendTBacktestConfig) -> bool:
    stock_trend_risk_on = (
        signal.market_regime_state in {"BREAKOUT_ATTACK", "STRONG_TREND", "TREND_WATCH"}
        and _non_force_position_confirmation_count(signal) >= 2
        and (
            signal.trend_state == "UPTREND"
            or signal.breakout_confirmed
            or signal.breakout_score >= 86.0
            or signal.chan_buy_point_type == "buy3"
        )
    )
    if signal.market_environment_state != MARKET_RISK_ON and not stock_trend_risk_on:
        return False
    if signal.market_regime_state not in {"BREAKOUT_ATTACK", "STRONG_TREND", "TREND_WATCH"}:
        return False
    if _offensive_volume_distribution_reduce_signal(signal, config):
        return False
    if signal.probability_state == "DOWN_RISK" or signal.chan_sell_point_type == "sell3" or signal.chan_structure_type == "breakdown":
        return False
    if signal.sell_pressure_score >= config.attack_hard_exit_sell_pressure_score:
        return False
    if (
        signal.down_probability_1d >= config.attack_hard_exit_down_probability
        or signal.down_probability_3d >= config.attack_hard_exit_down_probability
    ):
        return False
    buy3_confirmed = signal.chan_buy_point_type == "buy3" and signal.chan_score >= 74.0
    breakout_confirmed = signal.breakout_confirmed or signal.breakout_score >= 86.0
    flow_confirmed = _signal_capital_flow_confirmed(signal, min_score=60.0)
    volume_confirmed = (
        signal.volume_price_score >= 70.0
        and (
            signal.volume_breakout_score >= 68.0
            or signal.post_breakout_volume_persistence_score >= 70.0
            or signal.vwap_support_score >= 70.0
        )
        and signal.high_volume_stall_score < 72.0
    )
    return (buy3_confirmed or breakout_confirmed or flow_confirmed or volume_confirmed) and (
        signal.buy_signal_strength >= config.attack_confirm_min_buy_strength - 4.0
        or (stock_trend_risk_on and _non_force_position_confirmation_count(signal) >= 3)
    )


def _beta_hold_entry_signal(signal: BacktestSignal, config: DividendTBacktestConfig) -> bool:
    if signal.action in {"SELL_T_TIMING", "STOP_T_WAIT", "WAIT_DAILY_WEAK", "WAIT_MARKET_CAUTION"}:
        return False
    stock_risk_on = signal.market_environment_state == MARKET_RISK_ON or _individual_stock_risk_on_signal(signal)
    return stock_risk_on and _beta_hold_core_signal(
        signal,
        config,
        min_confirmations=config.beta_hold_min_confirmations,
        min_strength=config.beta_hold_min_strength,
    )


def _beta_hold_sustain_signal(signal: BacktestSignal, config: DividendTBacktestConfig) -> bool:
    if _beta_hold_hard_exit_signal(signal, config, active_profit_pct=0.0, active_peak_profit_pct=0.0):
        return False
    if _offensive_risk_on_continuation_signal(signal, config):
        return True
    return _beta_hold_core_signal(
        signal,
        config,
        min_confirmations=max(1, config.beta_hold_min_confirmations - 1),
        min_strength=max(config.min_buy_signal_strength, config.beta_hold_min_strength - 8.0),
        allow_soft_action=True,
    )


def _beta_hold_core_signal(
    signal: BacktestSignal,
    config: DividendTBacktestConfig,
    *,
    min_confirmations: int,
    min_strength: float,
    allow_soft_action: bool = False,
) -> bool:
    if not config.enable_beta_hold_state:
        return False
    if signal.market_regime_state not in {"BREAKOUT_ATTACK", "STRONG_TREND", "TREND_WATCH"}:
        return False
    if signal.probability_state == "DOWN_RISK" or signal.chan_sell_point_type == "sell3":
        return False
    if signal.chan_structure_type == "breakdown":
        return False
    if signal.sell_pressure_score >= config.attack_hard_exit_sell_pressure_score:
        return False
    if signal.down_probability_1d >= config.attack_hard_exit_down_probability:
        return False
    if signal.down_probability_3d >= config.attack_hard_exit_down_probability:
        return False
    if not allow_soft_action and signal.action in {"SELL_T_TIMING", "STOP_T_WAIT", "WAIT_DAILY_WEAK"}:
        return False
    confirmations = _non_force_position_confirmation_count(signal)
    if confirmations < min_confirmations:
        return False
    constructive = (
        signal.trend_state == "UPTREND"
        or signal.breakout_confirmed
        or signal.breakout_score >= 86.0
        or _qualified_breakout_hold_signal(signal, config)
        or (signal.chan_buy_point_type == "buy3" and signal.chan_score >= 74.0)
        or signal.post_breakout_volume_persistence_score >= 72.0
    )
    support = (
        _signal_capital_flow_confirmed(signal, min_score=58.0)
        or signal.vwap_support_score >= 68.0
        or signal.post_breakout_volume_persistence_score >= 68.0
        or signal.volume_breakout_score >= 72.0
        or (signal.low_volume_pullback_score >= 74.0 and signal.sell_pressure_score < 76.0)
    )
    strong_structure = (
        signal.breakout_score >= 90.0
        or (signal.chan_buy_point_type == "buy3" and signal.chan_score >= 80.0)
        or confirmations >= min_confirmations + 1
    )
    if not constructive or not support:
        return False
    if signal.buy_signal_strength < min_strength and not strong_structure:
        return False
    if _offensive_volume_distribution_blocks_entry_signal(signal, config) and not _offensive_volume_distribution_continuation_confirmed(
        signal, config
    ):
        return False
    return True


def _beta_hold_blocks_soft_exit(
    *,
    signal: BacktestSignal,
    config: DividendTBacktestConfig,
    attack_state: str,
    state_age_bars: int,
    active_profit_pct: float,
    active_peak_profit_pct: float,
    beta_hold_exit_confirmed: bool = True,
    beta_hold_soft_exit_confirmed: bool = True,
    beta_hold_distribution_confirmed: bool = True,
) -> bool:
    if attack_state != ATTACK_BETA_HOLD:
        return False
    if signal.action not in {"SELL_T_TIMING", "STOP_T_WAIT", "WAIT_DAILY_WEAK"}:
        return False
    if _beta_hold_hard_exit_signal(
        signal,
        config,
        active_profit_pct=active_profit_pct,
        active_peak_profit_pct=active_peak_profit_pct,
    ):
        return not beta_hold_exit_confirmed
    if _beta_hold_distribution_reduce_signal(
        signal,
        config,
        active_profit_pct=active_profit_pct,
        active_peak_profit_pct=active_peak_profit_pct,
    ):
        return not beta_hold_distribution_confirmed
    if _beta_hold_soft_exit_signal(
        signal,
        config,
        active_profit_pct=active_profit_pct,
        active_peak_profit_pct=active_peak_profit_pct,
    ):
        return not beta_hold_soft_exit_confirmed
    return state_age_bars < config.beta_hold_min_bars or _beta_hold_sustain_signal(signal, config)


def _beta_hold_soft_exit_signal(
    signal: BacktestSignal,
    config: DividendTBacktestConfig,
    *,
    active_profit_pct: float,
    active_peak_profit_pct: float,
) -> bool:
    if _beta_hold_hard_exit_signal(
        signal,
        config,
        active_profit_pct=active_profit_pct,
        active_peak_profit_pct=active_peak_profit_pct,
    ):
        return False
    if _beta_hold_sustain_signal(signal, config):
        return False
    if signal.action in {"SELL_T_TIMING", "STOP_T_WAIT", "WAIT_DAILY_WEAK"}:
        return True
    if signal.chan_sell_point_type == "sell1":
        return True
    if signal.sell_pressure_score >= config.attack_exit_sell_pressure_score:
        return True
    if signal.down_probability_1d >= config.attack_exit_down_probability:
        return True
    return signal.market_regime_state == "DEFENSIVE" and signal.trend_state != "UPTREND"


def _beta_hold_catastrophic_exit_signal(
    signal: BacktestSignal,
    config: DividendTBacktestConfig,
    *,
    active_profit_pct: float,
) -> bool:
    return (
        active_profit_pct <= -config.beta_hold_hard_stop_loss_pct
        or signal.sell_pressure_score >= max(config.attack_hard_exit_sell_pressure_score + 4.0, 92.0)
        or signal.down_probability_1d >= max(config.attack_hard_exit_down_probability + 0.04, 0.72)
        or signal.down_probability_3d >= max(config.attack_hard_exit_down_probability + 0.04, 0.72)
        or (
            signal.chan_structure_type == "breakdown"
            and signal.probability_state == "DOWN_RISK"
            and signal.sell_pressure_score >= config.attack_exit_sell_pressure_score
        )
    )


def _beta_hold_hard_exit_signal(
    signal: BacktestSignal,
    config: DividendTBacktestConfig,
    *,
    active_profit_pct: float,
    active_peak_profit_pct: float,
) -> bool:
    if active_profit_pct <= -config.beta_hold_hard_stop_loss_pct:
        return True
    if _beta_hold_main_rise_core_floor_signal(signal, config) and not _beta_hold_core_floor_hard_break_signal(signal, config):
        return False
    if signal.sell_pressure_score >= max(config.attack_hard_exit_sell_pressure_score, 90.0):
        return True
    if signal.down_probability_1d >= max(config.attack_hard_exit_down_probability, 0.70):
        return True
    if signal.down_probability_3d >= max(config.attack_hard_exit_down_probability, 0.70):
        return True
    risk_confirmed = (
        active_profit_pct < 0.0
        or signal.sell_pressure_score >= config.attack_exit_sell_pressure_score
        or signal.down_probability_1d >= config.attack_exit_down_probability
        or signal.down_probability_3d >= config.attack_exit_down_probability
    )
    if signal.chan_structure_type == "breakdown" and risk_confirmed:
        return True
    if signal.chan_sell_point_type == "sell3" and risk_confirmed:
        return True
    if (
        signal.market_regime_state == "DEFENSIVE"
        and signal.trend_state == "DOWNTREND"
        and (risk_confirmed or signal.probability_state == "DOWN_RISK")
    ):
        return True
    return _beta_hold_distribution_hard_exit_signal(
        signal,
        config,
        active_profit_pct=active_profit_pct,
        active_peak_profit_pct=active_peak_profit_pct,
    )


def _beta_hold_distribution_reduce_signal(
    signal: BacktestSignal,
    config: DividendTBacktestConfig,
    *,
    active_profit_pct: float,
    active_peak_profit_pct: float,
) -> bool:
    state = _volume_price_distribution_state(signal, config)
    if state == VOLUME_PRICE_ROTATION or state == VOLUME_PRICE_NONE:
        return False
    high_profit = _offensive_volume_distribution_high_profit_position(
        config=config,
        active_profit_pct=active_profit_pct,
        active_peak_profit_pct=active_peak_profit_pct,
    )
    low_absorption = _offensive_volume_distribution_low_absorption_signal(signal, config)
    if state == VOLUME_PRICE_DISTRIBUTION:
        return _volume_price_distribution_hard_breakdown_signal(signal, config) and (high_profit or low_absorption)
    return (
        high_profit
        and low_absorption
        and _offensive_volume_distribution_pressure_count(signal, config)
        >= max(2, config.offensive_volume_distribution_reduce_pressure_count)
    )


def _beta_hold_distribution_hard_exit_signal(
    signal: BacktestSignal,
    config: DividendTBacktestConfig,
    *,
    active_profit_pct: float,
    active_peak_profit_pct: float,
) -> bool:
    if not _beta_hold_distribution_reduce_signal(
        signal,
        config,
        active_profit_pct=active_profit_pct,
        active_peak_profit_pct=active_peak_profit_pct,
    ):
        return False
    hard_distribution = _volume_price_distribution_hard_breakdown_signal(signal, config)
    hard_pressure = (
        signal.sell_pressure_score >= config.attack_exit_sell_pressure_score
        or signal.down_probability_1d >= config.attack_exit_down_probability
        or signal.down_probability_3d >= config.attack_exit_down_probability
    )
    peak_giveback = (
        active_peak_profit_pct >= config.offensive_trailing_profit_mid_pct and active_profit_pct <= active_peak_profit_pct * 0.45
    )
    return hard_distribution and hard_pressure and peak_giveback


def _offensive_trailing_profit_sell_fraction(
    *,
    action: str,
    signal: BacktestSignal,
    config: DividendTBacktestConfig,
    active_profit_pct: float,
    active_peak_profit_pct: float,
    beta_hold: bool = False,
) -> float | None:
    if not config.offensive_trailing_profit_enabled:
        return None
    peak_profit = max(active_peak_profit_pct, active_profit_pct)
    if peak_profit < config.offensive_trailing_profit_trigger_pct:
        return None
    continuation = _offensive_risk_on_continuation_signal(signal, config)
    pullback = max(peak_profit - active_profit_pct, 0.0)
    pullback_multiplier = config.offensive_beta_trend_pullback_multiplier if continuation else 1.0
    if beta_hold:
        pullback_multiplier = max(pullback_multiplier, config.beta_hold_trailing_pullback_multiplier)
    pressure_exit = signal.sell_pressure_score >= config.attack_exit_sell_pressure_score
    probability_exit = signal.down_probability_1d >= config.attack_exit_down_probability
    pressure_take_profit = pressure_exit and (probability_exit or not continuation)
    if peak_profit >= config.offensive_trailing_profit_high_pct:
        required_pullback = config.offensive_trailing_pullback_high_pct * pullback_multiplier
        if pullback >= required_pullback or (pressure_exit and probability_exit):
            return config.beta_hold_trailing_hard_sell_fraction if beta_hold else config.offensive_trailing_hard_sell_fraction
        return 0.0
    if peak_profit >= config.offensive_trailing_profit_mid_pct:
        required_pullback = config.offensive_trailing_pullback_mid_pct * pullback_multiplier
        if pullback >= required_pullback or pressure_take_profit:
            return config.beta_hold_trailing_mid_sell_fraction if beta_hold else config.offensive_trailing_mid_sell_fraction
        return 0.0
    required_pullback = config.offensive_trailing_pullback_pct * pullback_multiplier
    if pullback >= required_pullback or (action != "SELL_T_TIMING" and pressure_take_profit):
        return config.beta_hold_trailing_light_sell_fraction if beta_hold else config.offensive_trailing_light_sell_fraction
    return 0.0


def _exit_support_broken_signal(signal: BacktestSignal, config: DividendTBacktestConfig) -> bool:
    weak_vwap = signal.vwap_support_score < config.offensive_volume_distribution_low_vwap_score
    weak_persistence = signal.post_breakout_volume_persistence_score < config.offensive_volume_distribution_low_persistence_score
    weak_volume = signal.volume_price_score < config.offensive_volume_distribution_low_volume_price_score
    weak_flow = (
        not _signal_capital_flow_confirmed(signal, min_score=58.0)
        and signal.capital_flow_confirmation_score < config.offensive_volume_distribution_low_flow_score
    )
    weak_force = (
        signal.force_ratio < config.offensive_volume_distribution_low_force_ratio
        and signal.force_weighted_score < config.offensive_volume_distribution_low_force_score
    )
    absorbed_pullback = (
        signal.vwap_support_score >= config.offensive_volume_distribution_absorption_vwap_score and signal.low_volume_pullback_score >= 78.0
    )
    if absorbed_pullback and not (weak_vwap and weak_persistence):
        return False
    return (
        (weak_vwap and weak_persistence)
        or (weak_vwap and weak_flow)
        or (weak_volume and weak_flow)
        or (weak_force and (weak_vwap or weak_persistence or weak_volume))
    )


def _stop_wait_soft_exit_confirmed_signal(
    *,
    action: str,
    signal: BacktestSignal,
    config: DividendTBacktestConfig,
    active_profit_pct: float,
) -> bool:
    pressure_confirmed = (
        signal.sell_pressure_score >= config.attack_exit_sell_pressure_score
        or signal.down_probability_1d >= config.attack_exit_down_probability
        or signal.down_probability_3d >= config.attack_exit_down_probability
    )
    if action == "WAIT_DAILY_WEAK":
        return pressure_confirmed or active_profit_pct <= -config.offensive_stop_hold_loss_pct

    support_broken = _exit_support_broken_signal(signal, config)
    probability_exit = (
        signal.down_probability_1d >= config.attack_exit_down_probability
        or signal.down_probability_3d >= config.attack_exit_down_probability
    )
    structure_warning = signal.chan_sell_point_type in {"sell1", "sell2"} or signal.chan_structure_type == "weakening"
    market_break = signal.market_regime_state == "DEFENSIVE" and signal.trend_state == "DOWNTREND"
    loss_needs_exit = active_profit_pct <= -config.offensive_stop_hold_loss_pct

    if market_break and (pressure_confirmed or support_broken or loss_needs_exit):
        return True
    if structure_warning and (pressure_confirmed or support_broken):
        return True
    if probability_exit and (support_broken or loss_needs_exit):
        return True
    if signal.sell_pressure_score >= config.attack_exit_sell_pressure_score and support_broken:
        return True
    return loss_needs_exit and (pressure_confirmed or support_broken)


def _stop_wait_false_break_deescalation_signal(
    *,
    action: str,
    signal: BacktestSignal,
    config: DividendTBacktestConfig,
    active_profit_pct: float,
) -> bool:
    if action != "STOP_T_WAIT":
        return False
    hard_probability = (
        signal.down_probability_1d >= config.attack_hard_exit_down_probability
        or signal.down_probability_3d >= config.attack_hard_exit_down_probability
    )
    hard_pressure = signal.sell_pressure_score >= config.attack_hard_exit_sell_pressure_score
    if hard_probability or hard_pressure:
        return False

    structure_break = signal.chan_sell_point_type == "sell3" or signal.chan_structure_type == "breakdown"
    pressure_confirmed = (
        signal.sell_pressure_score >= config.attack_exit_sell_pressure_score
        or signal.down_probability_1d >= config.attack_exit_down_probability
        or signal.down_probability_3d >= config.attack_exit_down_probability
    )
    mild_sell_pressure = signal.sell_pressure_score < min(config.attack_exit_sell_pressure_score - 20.0, 58.0)
    absorbed_pullback = signal.low_volume_pullback_score >= 63.0
    if not mild_sell_pressure or not absorbed_pullback:
        return False

    mild_probability = signal.down_probability_1d < min(config.attack_exit_down_probability, 0.56) and signal.down_probability_3d < min(
        config.attack_exit_down_probability, 0.56
    )
    hard_loss = active_profit_pct <= -max(config.beta_hold_hard_stop_loss_pct, config.offensive_stop_hold_loss_pct * 2.0)
    if hard_loss and not structure_break and not pressure_confirmed and mild_probability:
        return True

    probability_only_confirmation = (
        pressure_confirmed
        and signal.sell_pressure_score < 55.0
        and signal.down_probability_1d < min(config.attack_exit_down_probability + 0.012, 0.612)
        and signal.down_probability_3d < min(config.attack_exit_down_probability, 0.60)
    )
    return structure_break and probability_only_confirmation and active_profit_pct > -config.offensive_stop_hold_loss_pct


def _stop_wait_exit_fraction(
    *,
    action: str,
    signal: BacktestSignal,
    config: DividendTBacktestConfig,
    active_profit_pct: float,
    active_peak_profit_pct: float,
) -> float | None:
    if action not in {"STOP_T_WAIT", "WAIT_DAILY_WEAK"}:
        return None
    if not config.offensive_hold_extension_enabled:
        return None
    hard_probability = (
        signal.down_probability_1d >= config.attack_hard_exit_down_probability
        or signal.down_probability_3d >= config.attack_hard_exit_down_probability
    )
    hard_pressure = signal.sell_pressure_score >= config.attack_hard_exit_sell_pressure_score
    structure_break = signal.chan_sell_point_type == "sell3" or signal.chan_structure_type == "breakdown"
    pressure_confirmed = (
        signal.sell_pressure_score >= config.attack_exit_sell_pressure_score
        or signal.down_probability_1d >= config.attack_exit_down_probability
        or signal.down_probability_3d >= config.attack_exit_down_probability
    )
    hard_loss = active_profit_pct <= -max(config.beta_hold_hard_stop_loss_pct, config.offensive_stop_hold_loss_pct * 2.0)
    hard_market_break = (
        signal.market_regime_state == "DEFENSIVE"
        and signal.trend_state == "DOWNTREND"
        and active_profit_pct <= -(config.offensive_stop_hold_loss_pct * 1.8)
        and pressure_confirmed
    )
    if _stop_wait_false_break_deescalation_signal(
        action=action,
        signal=signal,
        config=config,
        active_profit_pct=active_profit_pct,
    ):
        return min(config.offensive_soft_stop_sell_fraction, config.beta_hold_soft_stop_sell_fraction)
    if (
        hard_loss
        or hard_probability
        or hard_pressure
        or hard_market_break
        or (signal.probability_state == "DOWN_RISK" and pressure_confirmed)
        or (structure_break and (pressure_confirmed or active_profit_pct < -config.offensive_stop_hold_loss_pct))
    ):
        return 1.0

    if _offensive_risk_on_continuation_signal(signal, config) and active_profit_pct >= -(config.offensive_stop_hold_loss_pct * 1.6):
        return 0.0
    if _sell_point_continuation_hold_signal(
        action=action,
        signal=signal,
        config=config,
        active_profit_pct=active_profit_pct,
        active_peak_profit_pct=active_peak_profit_pct,
    ):
        return 0.0
    if _offensive_soft_stop_extension_signal(signal, config) and active_profit_pct >= -(config.offensive_stop_hold_loss_pct * 1.6):
        if active_profit_pct >= -config.offensive_stop_hold_loss_pct:
            return 0.0
        if not _stop_wait_soft_exit_confirmed_signal(
            action=action,
            signal=signal,
            config=config,
            active_profit_pct=active_profit_pct,
        ):
            return 0.0
        return config.offensive_soft_stop_sell_fraction
    if active_profit_pct >= -(config.offensive_stop_hold_loss_pct * 2.0):
        if _stop_wait_soft_exit_confirmed_signal(
            action=action,
            signal=signal,
            config=config,
            active_profit_pct=active_profit_pct,
        ):
            return config.offensive_soft_stop_sell_fraction
        return 0.0
    return 1.0


def _offensive_exit_sell_fraction(
    *,
    action: str,
    signal: BacktestSignal,
    config: DividendTBacktestConfig,
    attack_state: str,
    active_profit_pct: float,
    active_peak_profit_pct: float,
) -> float:
    if attack_state == ATTACK_BETA_HOLD:
        if _beta_hold_hard_exit_signal(
            signal,
            config,
            active_profit_pct=active_profit_pct,
            active_peak_profit_pct=active_peak_profit_pct,
        ):
            return 1.0
        if _beta_hold_distribution_reduce_signal(
            signal,
            config,
            active_profit_pct=active_profit_pct,
            active_peak_profit_pct=active_peak_profit_pct,
        ):
            return config.beta_hold_distribution_sell_fraction
        trailing_fraction = _offensive_trailing_profit_sell_fraction(
            action=action,
            signal=signal,
            config=config,
            active_profit_pct=active_profit_pct,
            active_peak_profit_pct=active_peak_profit_pct,
            beta_hold=True,
        )
        if trailing_fraction is not None:
            return trailing_fraction
        if _sell_point_continuation_hold_signal(
            action=action,
            signal=signal,
            config=config,
            active_profit_pct=active_profit_pct,
            active_peak_profit_pct=active_peak_profit_pct,
        ):
            return 0.0
        if action == "SELL_T_TIMING":
            if _beta_hold_sustain_signal(signal, config):
                return 0.0
            if not _sell_timing_exit_confirmed_signal(
                signal=signal,
                config=config,
                active_profit_pct=active_profit_pct,
                active_peak_profit_pct=active_peak_profit_pct,
            ):
                return 0.0
            return config.beta_hold_soft_exit_sell_fraction
        if action in {"STOP_T_WAIT", "WAIT_DAILY_WEAK"}:
            if _stop_wait_observation_signal(
                signal=signal,
                config=config,
                active_profit_pct=active_profit_pct,
                active_peak_profit_pct=active_peak_profit_pct,
                beta_hold=True,
            ):
                return 0.0
            if active_profit_pct >= -config.offensive_stop_hold_loss_pct and _beta_hold_sustain_signal(signal, config):
                return 0.0
            if active_profit_pct >= -config.beta_hold_hard_stop_loss_pct and _beta_hold_main_rise_core_floor_signal(signal, config):
                return 0.0
            if (
                active_profit_pct >= -config.beta_hold_hard_stop_loss_pct
                and not _beta_hold_core_floor_hard_break_signal(signal, config)
                and not _beta_hold_distribution_reduce_signal(
                    signal,
                    config,
                    active_profit_pct=active_profit_pct,
                    active_peak_profit_pct=active_peak_profit_pct,
                )
            ):
                return 0.0
            if active_profit_pct >= -config.beta_hold_hard_stop_loss_pct:
                return config.beta_hold_soft_stop_sell_fraction
            return 1.0
        return 0.0
    stop_wait_fraction = _stop_wait_exit_fraction(
        action=action,
        signal=signal,
        config=config,
        active_profit_pct=active_profit_pct,
        active_peak_profit_pct=active_peak_profit_pct,
    )
    if stop_wait_fraction is not None:
        return stop_wait_fraction
    if attack_state not in {ATTACK_WATCH, ATTACK_CONFIRMED, ATTACK_FULL}:
        if config.offensive_hold_extension_enabled and signal.market_environment_state == MARKET_RISK_ON:
            if action == "SELL_T_TIMING" and (
                _offensive_hold_extension_signal(signal, config) or _trend_follow_hold_signal(signal, config)
            ):
                return 0.0
            if action in {"STOP_T_WAIT", "WAIT_DAILY_WEAK"} and _stop_wait_observation_signal(
                signal=signal,
                config=config,
                active_profit_pct=active_profit_pct,
                active_peak_profit_pct=active_peak_profit_pct,
            ):
                return 0.0
            if action in {"STOP_T_WAIT", "WAIT_DAILY_WEAK"} and _offensive_soft_stop_extension_signal(signal, config):
                if active_profit_pct >= -config.offensive_stop_hold_loss_pct:
                    return 0.0
                if active_profit_pct >= -(config.offensive_stop_hold_loss_pct * 1.6):
                    return config.offensive_soft_stop_sell_fraction
        if _sell_point_continuation_hold_signal(
            action=action,
            signal=signal,
            config=config,
            active_profit_pct=active_profit_pct,
            active_peak_profit_pct=active_peak_profit_pct,
        ):
            return 0.0
        if action == "SELL_T_TIMING" and not _sell_timing_exit_confirmed_signal(
            signal=signal,
            config=config,
            active_profit_pct=active_profit_pct,
            active_peak_profit_pct=active_peak_profit_pct,
        ):
            return 0.0
        return 1.0
    if not config.offensive_hold_extension_enabled:
        return 1.0
    hard_technical_exit = (
        signal.market_regime_state == "DEFENSIVE"
        or signal.probability_state == "DOWN_RISK"
        or signal.chan_sell_point_type == "sell3"
        or signal.chan_structure_type == "breakdown"
        or signal.sell_pressure_score >= config.attack_hard_exit_sell_pressure_score
        or signal.down_probability_1d >= config.attack_hard_exit_down_probability
        or signal.down_probability_3d >= config.attack_hard_exit_down_probability
    )
    if hard_technical_exit:
        return 1.0
    if _offensive_volume_distribution_hard_exit_signal(
        signal,
        config,
        active_profit_pct=active_profit_pct,
        active_peak_profit_pct=active_peak_profit_pct,
    ):
        return config.offensive_volume_distribution_hard_sell_fraction
    if _offensive_volume_distribution_reduce_signal(
        signal,
        config,
        active_profit_pct=active_profit_pct,
        active_peak_profit_pct=active_peak_profit_pct,
    ):
        if active_profit_pct < -config.offensive_stop_hold_loss_pct:
            return config.offensive_volume_distribution_hard_sell_fraction
        return config.offensive_volume_distribution_sell_fraction
    trailing_fraction = _offensive_trailing_profit_sell_fraction(
        action=action,
        signal=signal,
        config=config,
        active_profit_pct=active_profit_pct,
        active_peak_profit_pct=active_peak_profit_pct,
    )
    if trailing_fraction is not None:
        return trailing_fraction
    if _offensive_risk_on_continuation_signal(signal, config):
        if action == "SELL_T_TIMING":
            return 0.0
        if action in {"STOP_T_WAIT", "WAIT_DAILY_WEAK"} and active_profit_pct >= -(config.offensive_stop_hold_loss_pct * 1.25):
            return 0.0
    if _sell_point_continuation_hold_signal(
        action=action,
        signal=signal,
        config=config,
        active_profit_pct=active_profit_pct,
        active_peak_profit_pct=active_peak_profit_pct,
    ):
        return 0.0
    if action == "SELL_T_TIMING":
        if _sell_timing_defer_signal(
            signal=signal,
            config=config,
            active_profit_pct=active_profit_pct,
        ):
            return 0.0
        if _offensive_hold_extension_signal(signal, config):
            return 0.0
        if not _sell_timing_exit_confirmed_signal(
            signal=signal,
            config=config,
            active_profit_pct=active_profit_pct,
            active_peak_profit_pct=active_peak_profit_pct,
        ):
            return 0.0
        return config.offensive_soft_exit_sell_fraction
    if action in {"STOP_T_WAIT", "WAIT_DAILY_WEAK"}:
        if _stop_wait_observation_signal(
            signal=signal,
            config=config,
            active_profit_pct=active_profit_pct,
            active_peak_profit_pct=active_peak_profit_pct,
        ):
            return 0.0
        if _offensive_soft_stop_extension_signal(signal, config) and active_profit_pct >= -config.offensive_stop_hold_loss_pct:
            return 0.0
        if active_profit_pct >= -(config.offensive_stop_hold_loss_pct * 1.6):
            return config.offensive_soft_stop_sell_fraction
        return 1.0
    return 1.0


def _sell_timing_exit_confirmed_signal(
    *,
    signal: BacktestSignal,
    config: DividendTBacktestConfig,
    active_profit_pct: float,
    active_peak_profit_pct: float,
) -> bool:
    if signal.probability_state == "DOWN_RISK" or signal.chan_sell_point_type == "sell3" or signal.chan_structure_type == "breakdown":
        return True
    if (
        signal.sell_pressure_score >= config.attack_hard_exit_sell_pressure_score
        or signal.down_probability_1d >= config.attack_hard_exit_down_probability
        or signal.down_probability_3d >= config.attack_hard_exit_down_probability
    ):
        return True

    pressure_confirmed = (
        signal.sell_pressure_score >= config.attack_exit_sell_pressure_score
        or signal.down_probability_1d >= config.attack_exit_down_probability
        or signal.down_probability_3d >= config.attack_exit_down_probability
    )
    support_broken = _exit_support_broken_signal(signal, config)
    continuation_quality = _sell_point_continuation_quality_score(signal, config)
    weak_continuation = continuation_quality < max(0.30, config.sell_point_continuation_quality_score - 0.16)
    market_break = signal.market_regime_state == "DEFENSIVE" and signal.trend_state != "UPTREND"
    structure_warning = signal.chan_sell_point_type in {"sell1", "sell2"} or signal.chan_structure_type == "weakening"
    distribution_exit = _offensive_volume_distribution_reduce_signal(
        signal,
        config,
        active_profit_pct=active_profit_pct,
        active_peak_profit_pct=active_peak_profit_pct,
    )

    if distribution_exit and (support_broken or pressure_confirmed or weak_continuation):
        return True
    if market_break and (pressure_confirmed or support_broken):
        return True
    if structure_warning and (support_broken or pressure_confirmed):
        return True
    if active_profit_pct < 0.0 and pressure_confirmed:
        return True
    return pressure_confirmed and support_broken and weak_continuation


def _sell_timing_defer_signal(
    *,
    signal: BacktestSignal,
    config: DividendTBacktestConfig,
    active_profit_pct: float,
) -> bool:
    if not config.offensive_hold_extension_enabled:
        return False
    if signal.probability_state == "DOWN_RISK" or signal.chan_sell_point_type == "sell3" or signal.chan_structure_type == "breakdown":
        return False
    pressure_confirmed = (
        signal.sell_pressure_score >= config.attack_exit_sell_pressure_score
        or signal.down_probability_1d >= config.attack_exit_down_probability
        or signal.down_probability_3d >= config.attack_exit_down_probability
    )
    if pressure_confirmed and active_profit_pct < 0.0:
        return False
    continuation_quality = _sell_point_continuation_quality_score(signal, config)
    required = max(0.38, config.sell_point_continuation_quality_score - 0.12)
    constructive = signal.market_regime_state in {"BREAKOUT_ATTACK", "STRONG_TREND", "TREND_WATCH"} and (
        signal.trend_state == "UPTREND"
        or signal.breakout_score >= 78.0
        or signal.vwap_support_score >= 64.0
        or signal.post_breakout_volume_persistence_score >= 64.0
    )
    risk_mild = (
        signal.sell_pressure_score < config.attack_exit_sell_pressure_score
        and signal.down_probability_1d < config.attack_exit_down_probability
        and signal.down_probability_3d < config.attack_hard_exit_down_probability
    )
    return constructive and risk_mild and active_profit_pct >= -config.offensive_stop_hold_loss_pct and continuation_quality >= required


def _signal_capital_flow_confirmed(signal: BacktestSignal, *, min_score: float = 62.0) -> bool:
    if signal.capital_flow_confirmation_state == "CONFIRMED_INFLOW":
        return True
    if signal.capital_flow_source_type == "REAL_MONEY_FLOW":
        return signal.capital_flow_confirmation_score >= max(58.0, min_score - 4.0)
    return signal.capital_flow_confirmation_score >= min_score and signal.capital_flow_confidence >= 0.50


def _attack_rank(attack_state: str) -> int:
    return {
        ATTACK_INACTIVE: 0,
        ATTACK_WATCH: 1,
        ATTACK_CONFIRMED: 2,
        ATTACK_FULL: 3,
        ATTACK_BETA_HOLD: 4,
    }.get(attack_state, 0)


def _attack_position_floor_pct(attack_state: str, config: DividendTBacktestConfig) -> float:
    if attack_state == ATTACK_BETA_HOLD:
        return min(config.beta_hold_target_position_pct, config.max_signal_position_pct)
    if attack_state == ATTACK_FULL:
        return config.attack_full_position_pct
    if attack_state == ATTACK_CONFIRMED:
        return config.attack_confirm_position_pct
    if attack_state == ATTACK_WATCH:
        return config.attack_watch_position_pct
    return config.initial_base_position_pct


def _offensive_trend_add_signal(signal: BacktestSignal, config: DividendTBacktestConfig) -> bool:
    if signal.action not in {"BUY_T_TIMING", "BREAKOUT_BUY_TIMING"}:
        return False
    if signal.market_regime_state not in {"BREAKOUT_ATTACK", "STRONG_TREND"}:
        return False
    if _offensive_volume_distribution_reduce_signal(signal, config):
        return False
    if signal.probability_state == "DOWN_RISK" or signal.chan_sell_point_type in {"sell1", "sell2", "sell3"}:
        return False
    trend_confirmed = (
        signal.breakout_confirmed
        or signal.breakout_score >= config.attack_confirm_min_breakout_score
        or (signal.chan_buy_point_type == "buy3" and signal.chan_score >= 76.0)
        or (
            signal.volume_price_score >= 72.0
            and (signal.volume_breakout_score >= 70.0 or signal.post_breakout_volume_persistence_score >= 70.0)
            and signal.high_volume_stall_score < 72.0
        )
    )
    return (
        trend_confirmed
        and signal.buy_signal_strength >= config.attack_confirm_min_buy_strength
        and (
            _signal_capital_flow_confirmed(signal, min_score=62.0)
            or signal.post_breakout_volume_persistence_score >= 70.0
            or signal.vwap_support_score >= 70.0
        )
        and signal.sell_pressure_score < config.attack_exit_sell_pressure_score
        and signal.down_probability_1d < config.attack_exit_down_probability
        and signal.down_probability_3d < config.attack_hard_exit_down_probability
    )


def _offensive_full_add_signal(signal: BacktestSignal, config: DividendTBacktestConfig) -> bool:
    return (
        _offensive_trend_add_signal(signal, config)
        and signal.buy_signal_strength >= 82.0
        and (
            signal.breakout_score >= 92.0
            or signal.chan_score >= 82.0
            or (signal.volume_price_score >= 78.0 and signal.post_breakout_volume_persistence_score >= 74.0)
        )
        and signal.sell_pressure_score < 64.0
        and signal.down_probability_1d < 0.56
    )


def _breakout_direct_buy_allows_signal(
    signal: BacktestSignal,
    config: DividendTBacktestConfig,
    *,
    attack_state: str,
) -> bool:
    if signal.action != "BREAKOUT_BUY_TIMING":
        return True
    probe_enabled = config.breakout_direct_buy_probe_target_pct > 0.0
    if not config.enable_breakout_direct_buy and not probe_enabled:
        return False
    if attack_state == ATTACK_BETA_HOLD and config.suppress_beta_hold_breakout_direct_buy:
        return False
    if config.breakout_direct_buy_requires_risk_on_confirmation and not _risk_on_target_add_confirmation_signal(signal, config):
        return False
    strict_breakout_filter_enabled = (
        config.min_breakout_buy_quality_score > config.min_buy_point_quality_score
        or config.min_breakout_buy_main_rise_quality_score > config.min_main_rise_buy_quality_score
    )
    if not strict_breakout_filter_enabled:
        return True
    if _buy_point_quality_score(signal, config) < config.min_breakout_buy_quality_score:
        return False
    if _main_rise_buy_quality_score(signal, config) < config.min_breakout_buy_main_rise_quality_score:
        return False
    if not (signal.breakout_confirmed or signal.breakout_score >= 88.0):
        return False
    if signal.vwap_support_score < 68.0:
        return False
    volume_confirmed = signal.volume_breakout_score >= 68.0 and signal.post_breakout_volume_persistence_score >= 68.0
    if not volume_confirmed:
        return False
    if not (_signal_capital_flow_confirmed(signal, min_score=62.0) or signal.force_weighted_score >= 56.0):
        return False
    if signal.sell_pressure_score >= min(config.attack_exit_sell_pressure_score, 76.0):
        return False
    if signal.down_probability_1d >= min(config.attack_exit_down_probability, 0.60):
        return False
    if signal.down_probability_3d >= min(config.attack_hard_exit_down_probability, 0.66):
        return False
    if _offensive_volume_distribution_blocks_entry_signal(signal, config):
        return False
    return True


def _signal_t_trade_cap(signal: BacktestSignal, config: DividendTBacktestConfig, *, attack_state: str = ATTACK_INACTIVE) -> float:
    if signal.market_regime_state == "DEFENSIVE" or signal.chan_sell_point_type in {"sell1", "sell2", "sell3"}:
        return 0.0
    if signal.action in {"BUY_T_TIMING", "BREAKOUT_BUY_TIMING"}:
        if not _buy_point_quality_allows_entry(signal, config, min_score=config.min_buy_point_quality_score):
            return 0.0
        if signal.action == "BREAKOUT_BUY_TIMING" and not _breakout_direct_buy_allows_signal(
            signal,
            config,
            attack_state=attack_state,
        ):
            return 0.0
        breakout_direct_cap_limit = config.max_signal_position_pct
        if signal.action == "BREAKOUT_BUY_TIMING" and config.breakout_direct_buy_probe_target_pct > 0.0:
            breakout_direct_cap_limit = config.breakout_direct_buy_probe_target_pct
        strength_cap = _signal_strength_position_cap_floor(signal, config, attack_state=attack_state)
        if _offensive_full_add_signal(signal, config):
            return _signal_filtered_cap(
                signal, min(config.attack_full_position_pct, config.max_signal_position_pct, breakout_direct_cap_limit)
            )
        if _offensive_trend_add_signal(signal, config):
            cap = max(config.offensive_trend_add_floor_pct, config.attack_confirm_position_pct, strength_cap)
            return _signal_filtered_cap(signal, min(cap, config.max_signal_position_pct, breakout_direct_cap_limit))
        attack_cap = _attack_position_floor_pct(attack_state, config)
        if attack_state in {ATTACK_CONFIRMED, ATTACK_FULL}:
            return _signal_filtered_cap(
                signal, min(max(attack_cap, strength_cap), config.max_signal_position_pct, breakout_direct_cap_limit)
            )
        if signal.action == "BREAKOUT_BUY_TIMING":
            breakout_cap = 0.30
            if signal.chan_buy_point_type == "buy3" and signal.chan_score >= 76.0:
                breakout_cap = 0.55
            if signal.breakout_score >= 78.0 and signal.market_regime_state in {"BREAKOUT_ATTACK", "STRONG_TREND"}:
                breakout_cap = 0.50
            if signal.volume_breakout_score >= 74.0 and signal.vwap_support_score >= 66.0:
                breakout_cap = max(breakout_cap, 0.56)
            if signal.post_breakout_volume_persistence_score >= 76.0 and signal.high_volume_stall_score < 68.0:
                breakout_cap = max(breakout_cap, 0.62)
            if signal.breakout_score >= 88.0 and signal.buy_signal_strength >= 76.0 and signal.sell_pressure_score < 70.0:
                breakout_cap = 0.65
            if (
                _signal_capital_flow_confirmed(signal, min_score=62.0)
                and signal.breakout_score >= 86.0
                and signal.buy_signal_strength >= 68.0
                and signal.sell_pressure_score < 78.0
                and signal.down_probability_1d < 0.62
            ):
                breakout_cap = max(breakout_cap, 0.85 + config.confirmed_flow_position_bonus_pct)
            if (
                signal.breakout_score >= 92.0
                and signal.buy_signal_strength >= 84.0
                and signal.up_probability_1d >= 0.54
                and signal.down_probability_1d < 0.55
                and signal.sell_pressure_score < 64.0
            ):
                breakout_cap = 1.00
            direct_cap = max(breakout_cap, strength_cap)
            if config.breakout_direct_buy_probe_target_pct > 0.0:
                direct_cap = min(direct_cap, config.breakout_direct_buy_probe_target_pct)
            return _signal_filtered_cap(signal, min(direct_cap, config.max_signal_position_pct))
        if signal.market_regime_state == "STRONG_TREND":
            cap = config.strong_trend_signal_position_pct
            if _signal_capital_flow_confirmed(signal, min_score=62.0):
                cap = min(config.max_signal_position_pct, cap + config.confirmed_flow_position_bonus_pct)
            if signal.volume_price_score >= 72.0 and signal.vwap_support_score >= 66.0:
                cap = min(config.max_signal_position_pct, cap + 0.10)
            return _signal_filtered_cap(signal, min(max(cap, strength_cap), config.max_signal_position_pct))
        if signal.market_regime_state == "TREND_WATCH":
            cap = config.trend_watch_signal_position_pct
            if signal.chan_buy_point_type == "buy3" and signal.chan_score >= 76.0:
                cap = min(config.max_signal_position_pct, cap + 0.12)
            if _signal_capital_flow_confirmed(signal, min_score=64.0):
                cap = min(config.max_signal_position_pct, cap + config.confirmed_flow_position_bonus_pct)
            if signal.volume_price_score >= 70.0 and signal.post_breakout_volume_persistence_score >= 68.0:
                cap = min(config.max_signal_position_pct, cap + 0.08)
            return _signal_filtered_cap(signal, min(max(cap, strength_cap), config.max_signal_position_pct))
        return _signal_filtered_cap(signal, min(max(config.range_signal_position_pct, strength_cap), config.max_signal_position_pct))
    signal_cap = signal.max_total_position_pct if signal.max_total_position_pct > 0 else signal.t_trade_limit_pct
    if signal_cap <= 0:
        signal_cap = config.default_buy_total_cap_pct
    return round(clamp(min(signal_cap, config.default_buy_total_cap_pct), 0.0, config.default_buy_total_cap_pct), 4)


def _signal_filtered_cap(signal: BacktestSignal, cap: float) -> float:
    if signal.market_environment_state not in {MARKET_CAUTION, MARKET_NEUTRAL, MARKET_RISK_OFF}:
        return round(clamp(cap, 0.0, 1.0), 4)
    signal_cap = signal.max_total_position_pct if signal.max_total_position_pct > 0 else cap
    return round(clamp(min(cap, signal_cap), 0.0, 1.0), 4)


def _base_rebalance_buy_quality_allows(signal: BacktestSignal, config: DividendTBacktestConfig) -> bool:
    if signal.market_regime_state == "DEFENSIVE":
        return False
    if signal.probability_state == "DOWN_RISK" or signal.chan_sell_point_type in {"sell1", "sell2", "sell3"}:
        return False
    if signal.chan_structure_type == "breakdown":
        return False
    if signal.sell_pressure_score >= min(config.attack_exit_sell_pressure_score, 76.0):
        return False
    if signal.down_probability_1d >= min(config.attack_exit_down_probability, 0.60):
        return False
    score = _buy_point_quality_score(signal, config)
    if score >= config.min_base_rebalance_buy_quality_score:
        return True
    return (
        signal.market_regime_state in {"BREAKOUT_ATTACK", "STRONG_TREND"}
        and signal.trend_state == "UPTREND"
        and _non_force_position_confirmation_count(signal) >= 2
        and score >= config.min_base_rebalance_buy_quality_score - 0.06
    )


def _base_rebalance_sell_quality_holds(signal: BacktestSignal, config: DividendTBacktestConfig) -> bool:
    if signal.probability_state == "DOWN_RISK" or signal.chan_sell_point_type == "sell3" or signal.chan_structure_type == "breakdown":
        return False
    if signal.sell_pressure_score >= config.attack_hard_exit_sell_pressure_score:
        return False
    if (
        signal.down_probability_1d >= config.attack_hard_exit_down_probability
        or signal.down_probability_3d >= config.attack_hard_exit_down_probability
    ):
        return False
    if signal.market_regime_state != "DEFENSIVE":
        return False
    constructive = (
        signal.trend_state == "UPTREND"
        or signal.breakout_score >= 82.0
        or (signal.chan_buy_point_type == "buy3" and signal.chan_score >= 72.0)
        or signal.vwap_support_score >= 68.0
        or signal.post_breakout_volume_persistence_score >= 68.0
    )
    support = (
        _signal_capital_flow_confirmed(signal, min_score=58.0)
        or signal.force_weighted_score >= 52.0
        or signal.force_ratio >= 0.88
        or signal.vwap_support_score >= 68.0
        or signal.post_breakout_volume_persistence_score >= 68.0
    )
    risk_mild = (
        signal.sell_pressure_score < config.attack_exit_sell_pressure_score
        and signal.down_probability_1d < config.attack_exit_down_probability
        and signal.down_probability_3d < config.attack_hard_exit_down_probability
    )
    return constructive and support and risk_mild


def _buy_point_quality_allows_entry(signal: BacktestSignal, config: DividendTBacktestConfig, *, min_score: float) -> bool:
    if signal.probability_state == "DOWN_RISK" or signal.chan_sell_point_type in {"sell1", "sell2", "sell3"}:
        return False
    if signal.chan_structure_type == "breakdown":
        return False
    if signal.sell_pressure_score >= min(config.attack_hard_exit_sell_pressure_score, 86.0):
        return False
    if (
        signal.down_probability_1d >= config.attack_hard_exit_down_probability
        or signal.down_probability_3d >= config.attack_hard_exit_down_probability
    ):
        return False
    if _offensive_volume_distribution_blocks_entry_signal(signal, config):
        return False
    if not _buy_volume_price_window_filter_allows(signal, config):
        return False
    score = _buy_point_quality_score(signal, config)
    main_rise_score = _main_rise_buy_quality_score(signal, config)
    if main_rise_score < config.min_main_rise_buy_quality_score:
        return False
    if score >= min_score:
        return True
    strong_breakout = (
        signal.action == "BREAKOUT_BUY_TIMING"
        and (signal.breakout_confirmed or signal.breakout_score >= 92.0)
        and signal.buy_signal_strength >= config.attack_confirm_min_buy_strength
        and signal.sell_pressure_score < config.attack_exit_sell_pressure_score
        and signal.down_probability_1d < config.attack_exit_down_probability
    )
    strong_force_follow = (
        signal.action == "BUY_T_TIMING"
        and signal.market_regime_state in {"BREAKOUT_ATTACK", "STRONG_TREND"}
        and signal.trend_state == "UPTREND"
        and signal.buy_signal_strength >= max(config.min_buy_signal_strength + 18.0, 76.0)
        and (signal.force_ratio >= 1.18 or signal.force_weighted_score >= 68.0)
        and signal.sell_pressure_score < 56.0
        and signal.down_probability_1d < 0.56
    )
    return (
        (strong_breakout or strong_force_follow)
        and score >= min_score - 0.08
        and main_rise_score >= config.min_main_rise_buy_quality_score - 0.04
    )


def _buy_point_quality_score(signal: BacktestSignal, config: DividendTBacktestConfig) -> float:
    strength = _buy_strength_score(signal, config)
    breakout = clamp((signal.breakout_score - 68.0) / 28.0, 0.0, 1.0)
    if signal.breakout_confirmed:
        breakout = max(breakout, 0.86)
    chan = clamp((signal.chan_score - 66.0) / 24.0, 0.0, 1.0) if signal.chan_buy_point_type == "buy3" else 0.0
    flow = (
        1.0
        if _signal_capital_flow_confirmed(signal, min_score=62.0)
        else clamp(
            (0.55 * signal.capital_flow_score + 0.45 * signal.capital_flow_confirmation_score - 50.0) / 36.0,
            0.0,
            1.0,
        )
    )
    volume = _risk_on_volume_price_quality(signal)
    force = max(
        clamp((signal.force_ratio - 0.82) / 0.58, 0.0, 1.0),
        clamp((signal.force_weighted_score - 44.0) / 32.0, 0.0, 1.0),
    )
    probability = clamp(
        0.55 * clamp((signal.up_probability_1d - 0.50) / 0.12, 0.0, 1.0)
        + 0.35 * clamp((signal.up_probability_3d - 0.50) / 0.12, 0.0, 1.0)
        - 0.40 * clamp((signal.down_probability_1d - 0.54) / 0.14, 0.0, 1.0),
        0.0,
        1.0,
    )
    trend = 0.0
    if signal.market_regime_state in {"BREAKOUT_ATTACK", "STRONG_TREND"} and signal.trend_state == "UPTREND":
        trend = 1.0
    elif signal.market_regime_state == "TREND_WATCH" and (signal.trend_state == "UPTREND" or signal.breakout_score >= 82.0):
        trend = 0.70
    elif signal.trend_state == "UPTREND":
        trend = 0.45
    confirmations = min(_non_force_position_confirmation_count(signal) / 4.0, 1.0)
    score = 0.22 * strength + 0.15 * breakout + 0.10 * chan + 0.16 * flow + 0.16 * volume + 0.08 * force + 0.07 * probability + 0.06 * trend
    score += 0.08 * confirmations
    score += 0.08 * (_buy_volume_price_window_quality_score(signal, config) - 0.50)
    if signal.action == "BREAKOUT_BUY_TIMING":
        score += 0.03
    if signal.market_environment_state == MARKET_RISK_ON:
        score += 0.03
    if signal.sell_pressure_score >= 76.0:
        score -= 0.16
    elif signal.sell_pressure_score >= 68.0:
        score -= 0.08
    if signal.down_probability_1d >= 0.58 or signal.down_probability_3d >= 0.60:
        score -= 0.14
    if _offensive_volume_distribution_reduce_signal(signal, config):
        score -= 0.14
    elif _offensive_volume_distribution_soft_signal(signal, config):
        score -= 0.05
    return round(clamp(score, 0.0, 1.0), 4)


def _main_rise_buy_quality_score(signal: BacktestSignal, config: DividendTBacktestConfig) -> float:
    trend = 0.0
    if signal.market_regime_state in {"BREAKOUT_ATTACK", "STRONG_TREND"} and signal.trend_state == "UPTREND":
        trend = 1.0
    elif signal.market_regime_state == "TREND_WATCH" and (signal.trend_state == "UPTREND" or signal.breakout_score >= 84.0):
        trend = 0.68
    breakout = clamp((signal.breakout_score - 74.0) / 22.0, 0.0, 1.0)
    if signal.breakout_confirmed:
        breakout = max(breakout, 0.90)
    volume = max(
        clamp((signal.volume_breakout_score - 58.0) / 28.0, 0.0, 1.0),
        clamp((signal.post_breakout_volume_persistence_score - 58.0) / 28.0, 0.0, 1.0),
        0.70 * clamp((signal.volume_price_score - 58.0) / 30.0, 0.0, 1.0),
    )
    vwap = clamp((signal.vwap_support_score - 58.0) / 28.0, 0.0, 1.0)
    flow = (
        1.0
        if _signal_capital_flow_confirmed(signal, min_score=64.0)
        else clamp(
            (signal.capital_flow_confirmation_score - 52.0) / 30.0,
            0.0,
            1.0,
        )
    )
    force = max(
        clamp((signal.force_ratio - 0.82) / 0.58, 0.0, 1.0),
        clamp((signal.force_weighted_score - 46.0) / 30.0, 0.0, 1.0),
    )
    elasticity = max(
        clamp((signal.buy_signal_strength - 66.0) / 22.0, 0.0, 1.0),
        clamp((signal.attention_score - 56.0) / 30.0, 0.0, 1.0),
        0.65 * force + 0.35 * volume,
    )
    probability = clamp(
        0.58 * clamp((signal.up_probability_1d - 0.50) / 0.12, 0.0, 1.0)
        + 0.32 * clamp((signal.up_probability_3d - 0.50) / 0.12, 0.0, 1.0)
        - 0.45 * clamp((signal.down_probability_1d - 0.54) / 0.14, 0.0, 1.0),
        0.0,
        1.0,
    )
    confirmations = min(_non_force_position_confirmation_count(signal) / 4.0, 1.0)
    score = (
        0.16 * trend + 0.18 * breakout + 0.16 * volume + 0.12 * vwap + 0.14 * flow + 0.10 * force + 0.08 * elasticity + 0.06 * probability
    )
    score += 0.08 * confirmations
    score += 0.10 * (_buy_volume_price_window_quality_score(signal, config) - 0.50)
    if signal.action == "BREAKOUT_BUY_TIMING":
        score += 0.03
    if signal.chan_buy_point_type == "buy3" and signal.chan_score >= 76.0:
        score += 0.04
    if signal.market_environment_state == MARKET_RISK_ON:
        score += 0.03
    low_elasticity = signal.force_ratio < 0.86 and signal.force_weighted_score < 52.0 and signal.attention_score < 58.0
    low_volume = (
        signal.volume_price_score < 60.0 and signal.volume_breakout_score < 58.0 and signal.post_breakout_volume_persistence_score < 58.0
    )
    if low_elasticity:
        score -= 0.14
    if low_volume:
        score -= 0.16
    if signal.market_regime_state not in {"BREAKOUT_ATTACK", "STRONG_TREND", "TREND_WATCH"}:
        score -= 0.12
    if signal.sell_pressure_score >= 76.0:
        score -= 0.16
    elif signal.sell_pressure_score >= 68.0:
        score -= 0.08
    if signal.down_probability_1d >= 0.58 or signal.down_probability_3d >= 0.60:
        score -= 0.14
    if _offensive_volume_distribution_reduce_signal(signal, config):
        score -= 0.12
    elif _offensive_volume_distribution_soft_signal(signal, config):
        score -= 0.05
    return round(clamp(score, 0.0, 1.0), 4)


def _buy_volume_price_window_filter_allows(signal: BacktestSignal, config: DividendTBacktestConfig) -> bool:
    if not config.enable_buy_volume_price_window_filter:
        return True
    if signal.action not in {"BUY_T_TIMING", "BREAKOUT_BUY_TIMING"}:
        return True
    if _buy_volume_price_window_bypass_signal(signal, config):
        return True
    quality = _buy_volume_price_window_quality_score(signal, config)
    if quality < config.buy_volume_price_filter_min_quality_score:
        return False

    short_state = signal.pretrade_volume_price_state_12
    mid_state = signal.pretrade_volume_price_state_24
    weak_contract = (
        mid_state == "flat_volume_contract"
        and short_state in {"flat_volume_contract", "neutral_volume_price", "price_down_volume_down"}
        and signal.pretrade_price_return_pct_24 < config.buy_volume_price_filter_min_return_pct
        and signal.pretrade_volume_ratio_to_prev_24 <= config.buy_volume_price_filter_max_contract_ratio
    )
    if weak_contract:
        return False
    distribution_volume = mid_state == "price_down_volume_up" or (
        short_state == "price_down_volume_up" and signal.pretrade_price_return_pct_12 <= -config.buy_volume_price_filter_min_return_pct
    )
    if distribution_volume and (signal.sell_pressure_score >= 64.0 or signal.down_probability_1d >= 0.56):
        return False
    return True


def _buy_volume_price_window_bypass_signal(signal: BacktestSignal, config: DividendTBacktestConfig) -> bool:
    high_quality_breakout_like = (
        (signal.breakout_confirmed or signal.breakout_score >= 92.0)
        and signal.vwap_support_score >= 76.0
        and signal.volume_price_score >= 78.0
        and signal.volume_breakout_score >= 74.0
        and signal.post_breakout_volume_persistence_score >= 76.0
        and _signal_capital_flow_confirmed(signal, min_score=70.0)
        and signal.sell_pressure_score < 64.0
        and signal.down_probability_1d < 0.56
    )
    main_rise_rotation = (
        signal.pretrade_volume_price_state_24 == "price_up_volume_down"
        and signal.pretrade_price_return_pct_24 >= config.buy_volume_price_filter_min_return_pct * 2.0
        and signal.vwap_support_score >= 66.0
        and (
            signal.post_breakout_volume_persistence_score >= 66.0
            or _signal_capital_flow_confirmed(signal, min_score=62.0)
            or signal.volume_breakout_score >= 70.0
        )
        and signal.sell_pressure_score < min(config.attack_exit_sell_pressure_score, 76.0)
    )
    return high_quality_breakout_like or main_rise_rotation


def _buy_volume_price_window_quality_score(signal: BacktestSignal, config: DividendTBacktestConfig) -> float:
    if not config.enable_buy_volume_price_window_filter:
        return 0.50
    short = _volume_price_window_state_score(
        signal.pretrade_volume_price_state_12,
        price_return=signal.pretrade_price_return_pct_12,
        volume_ratio=signal.pretrade_volume_ratio_to_prev_12,
        config=config,
    )
    mid = _volume_price_window_state_score(
        signal.pretrade_volume_price_state_24,
        price_return=signal.pretrade_price_return_pct_24,
        volume_ratio=signal.pretrade_volume_ratio_to_prev_24,
        config=config,
    )
    support = max(
        clamp((signal.vwap_support_score - 58.0) / 26.0, 0.0, 1.0),
        clamp((signal.post_breakout_volume_persistence_score - 58.0) / 26.0, 0.0, 1.0),
        0.65 * clamp((signal.volume_breakout_score - 58.0) / 30.0, 0.0, 1.0),
    )
    score = 0.35 * short + 0.45 * mid + 0.20 * support
    return round(clamp(score, 0.0, 1.0), 4)


def _volume_price_window_state_score(
    state: str,
    *,
    price_return: float,
    volume_ratio: float,
    config: DividendTBacktestConfig,
) -> float:
    if state == "price_up_volume_up":
        return 1.00
    if state == "price_up_volume_down":
        if (
            price_return >= config.buy_volume_price_filter_min_return_pct * 2.0
            and volume_ratio <= config.buy_volume_price_filter_max_contract_ratio
        ):
            return 0.82
        return 0.66
    if state == "flat_volume_expand":
        return 0.56
    if state == "neutral_volume_price":
        return 0.50
    if state == "flat_volume_contract":
        return 0.18 if price_return < config.buy_volume_price_filter_min_return_pct else 0.32
    if state == "price_down_volume_down":
        return 0.28
    if state == "price_down_volume_up":
        return 0.10
    return 0.50


def _buy_quality_adjusted_position_target(target: float, *, quality_score: float, config: DividendTBacktestConfig) -> float:
    if quality_score < config.min_buy_point_quality_score + 0.08:
        return min(target, config.initial_base_position_pct + max(config.min_t_trade_pct, 0.21))
    if quality_score < config.min_buy_point_quality_score + 0.18:
        return min(target, 0.55)
    return target


def _main_rise_adjusted_position_target(target: float, *, main_rise_score: float, config: DividendTBacktestConfig) -> float:
    if main_rise_score < config.min_main_rise_buy_quality_score + 0.08:
        return min(target, config.initial_base_position_pct + max(config.min_t_trade_pct, 0.18))
    if main_rise_score < config.min_main_rise_buy_quality_score + 0.18:
        return min(target, 0.50)
    return target


def _signal_target_position_pct(signal: BacktestSignal, config: DividendTBacktestConfig, *, attack_state: str = ATTACK_INACTIVE) -> float:
    if signal.buy_signal_strength < config.min_buy_signal_strength:
        return 0.0
    if signal.chan_sell_point_type in {"sell1", "sell2", "sell3"} or signal.chan_structure_type == "breakdown":
        return 0.0
    quality_score = _buy_point_quality_score(signal, config)
    main_rise_score = _main_rise_buy_quality_score(signal, config)
    if not _buy_point_quality_allows_entry(signal, config, min_score=config.min_buy_point_quality_score):
        return 0.0
    cap = _signal_t_trade_cap(signal, config, attack_state=attack_state)
    if cap <= 0:
        return 0.0
    signal_score = _position_signal_score(signal, config, attack_state=attack_state)
    layered_floor = _layered_position_floor_pct(signal, config, attack_state=attack_state)
    if _full_position_signal(signal, config, attack_state=attack_state):
        signal_score = 1.0
    active_target = config.initial_base_position_pct + (cap - config.initial_base_position_pct) * signal_score
    target = max(config.initial_base_position_pct + config.min_t_trade_pct, active_target, layered_floor)
    target = _buy_quality_adjusted_position_target(target, quality_score=quality_score, config=config)
    target = _main_rise_adjusted_position_target(target, main_rise_score=main_rise_score, config=config)
    return round(clamp(target, config.initial_base_position_pct, min(config.max_signal_position_pct, cap)), 4)


def _next_core_position_floor_pct(
    *,
    signal: BacktestSignal,
    config: DividendTBacktestConfig,
    attack_state: str,
    current_floor_pct: float,
    active_profit_pct: float,
) -> float:
    if not config.enable_core_position_floor:
        return 0.0
    step = max(0.01, config.risk_on_core_floor_ramp_step_pct)
    if _core_floor_hard_exit_signal(signal, config, active_profit_pct=active_profit_pct):
        if (
            attack_state == ATTACK_BETA_HOLD
            and active_profit_pct > -config.beta_hold_hard_stop_loss_pct
            and _beta_hold_main_rise_core_floor_signal(signal, config)
        ):
            return round(max(current_floor_pct, config.beta_hold_main_rise_core_floor_pct), 4)
        return max(0.0, round(current_floor_pct - step * 2.0, 4))
    target = _risk_on_core_floor_target_pct(signal, config, attack_state=attack_state)
    if target <= 0.0:
        if current_floor_pct > 0.0 and _core_floor_sustain_signal(signal, config, attack_state=attack_state):
            return round(current_floor_pct, 4)
        return max(0.0, round(current_floor_pct - step, 4))
    if target > current_floor_pct:
        return round(min(target, current_floor_pct + step), 4)
    if _core_floor_sustain_signal(signal, config, attack_state=attack_state):
        return round(max(current_floor_pct, target), 4)
    return round(max(target, current_floor_pct - step), 4)


def _risk_on_core_floor_target_pct(signal: BacktestSignal, config: DividendTBacktestConfig, *, attack_state: str) -> float:
    if attack_state == ATTACK_BETA_HOLD and _beta_hold_main_rise_core_floor_signal(signal, config):
        return round(
            clamp(
                max(config.beta_hold_main_rise_core_floor_pct, config.risk_on_core_floor_l3_pct),
                config.initial_base_position_pct,
                config.max_signal_position_pct,
            ),
            4,
        )
    if signal.market_environment_state != MARKET_RISK_ON and not _individual_stock_risk_on_signal(signal):
        return 0.0
    if signal.market_regime_state not in {"BREAKOUT_ATTACK", "STRONG_TREND", "TREND_WATCH"}:
        return 0.0
    if signal.action in {"STOP_T_WAIT", "WAIT_DAILY_WEAK", "WAIT_MARKET_CAUTION", "WAIT_LATE_SESSION", "WAIT_STALE_DATA"}:
        return 0.0
    if signal.probability_state == "DOWN_RISK" or signal.chan_sell_point_type in {"sell2", "sell3"}:
        return 0.0
    if signal.chan_structure_type == "breakdown":
        return 0.0
    if signal.sell_pressure_score >= config.attack_hard_exit_sell_pressure_score:
        return 0.0
    if signal.down_probability_1d >= config.attack_hard_exit_down_probability:
        return 0.0
    if _offensive_volume_distribution_blocks_entry_signal(signal, config):
        return 0.0

    confirmations = _non_force_position_confirmation_count(signal)
    if attack_state == ATTACK_BETA_HOLD or confirmations >= 4:
        target = config.risk_on_core_floor_l3_pct
    elif attack_state in {ATTACK_FULL, ATTACK_CONFIRMED} or confirmations >= 3:
        target = config.risk_on_core_floor_l2_pct
    elif confirmations >= config.risk_on_position_target_min_confirmations:
        target = config.risk_on_core_floor_l1_pct
    else:
        return 0.0

    if signal.market_regime_state == "TREND_WATCH" and confirmations < 3:
        target = min(target, config.risk_on_core_floor_l1_pct)
    if signal.sell_pressure_score >= 72.0 or signal.down_probability_1d >= 0.58 or signal.down_probability_3d >= 0.60:
        target = min(target, config.risk_on_core_floor_l1_pct)
    return round(clamp(target, config.initial_base_position_pct, config.max_signal_position_pct), 4)


def _core_floor_sustain_signal(signal: BacktestSignal, config: DividendTBacktestConfig, *, attack_state: str) -> bool:
    if attack_state == ATTACK_BETA_HOLD and _beta_hold_sustain_signal(signal, config):
        return True
    if attack_state in {ATTACK_CONFIRMED, ATTACK_FULL} and _attack_sustain_signal(signal, config):
        return True
    return (
        signal.market_regime_state in {"BREAKOUT_ATTACK", "STRONG_TREND", "TREND_WATCH"}
        and signal.trend_state == "UPTREND"
        and signal.sell_pressure_score < config.attack_exit_sell_pressure_score
        and signal.down_probability_1d < config.attack_exit_down_probability
        and _non_force_position_confirmation_count(signal) >= 2
    )


def _risk_on_position_target_pct(
    signal: BacktestSignal,
    config: DividendTBacktestConfig,
    *,
    attack_state: str,
    current_position_pct: float,
) -> float:
    if not config.enable_risk_on_position_target_engine:
        return 0.0
    stock_trend_risk_on = _individual_stock_risk_on_signal(signal) or _beta_hold_entry_signal(signal, config)
    if signal.market_environment_state != MARKET_RISK_ON and not stock_trend_risk_on:
        return 0.0
    if signal.action in {
        "SELL_T_TIMING",
        "STOP_T_WAIT",
        "WAIT_DAILY_WEAK",
        "WAIT_MARKET_CAUTION",
        "WAIT_LATE_SESSION",
        "WAIT_CONFIRMATION",
        "WAIT_STALE_DATA",
        "WAIT_BETA_HOLD",
    }:
        return 0.0
    if signal.market_regime_state not in {"BREAKOUT_ATTACK", "STRONG_TREND", "TREND_WATCH"}:
        return 0.0
    if signal.probability_state == "DOWN_RISK" or signal.chan_sell_point_type in {"sell1", "sell2", "sell3"}:
        return 0.0
    if signal.chan_structure_type == "breakdown":
        return 0.0
    if signal.buy_signal_strength < config.risk_on_position_target_min_strength:
        return 0.0
    beta_hold_core_add = attack_state == ATTACK_BETA_HOLD and _beta_hold_main_rise_core_floor_signal(signal, config)
    portfolio_main_rise_target = _portfolio_main_rise_position_target_signal(signal, config, attack_state=attack_state)
    target_add_confirmed = _risk_on_target_add_confirmation_signal(signal, config)
    if not target_add_confirmed and not beta_hold_core_add and not portfolio_main_rise_target:
        return 0.0

    non_force_confirmations = _non_force_position_confirmation_count(signal)
    if non_force_confirmations < config.risk_on_position_target_min_confirmations:
        return 0.0
    volume_quality = _risk_on_volume_price_quality(signal)
    if volume_quality < 0.35:
        return 0.0
    if signal.sell_pressure_score >= config.attack_exit_sell_pressure_score:
        return 0.0
    if signal.down_probability_1d >= config.attack_exit_down_probability:
        return 0.0
    if signal.down_probability_3d >= config.attack_hard_exit_down_probability:
        return 0.0
    if _offensive_volume_distribution_blocks_entry_signal(signal, config):
        return 0.0
    if not _risk_on_staged_add_allows_signal(signal, config, current_position_pct=current_position_pct, attack_state=attack_state):
        return 0.0

    target_action = "BREAKOUT_BUY_TIMING" if signal.breakout_confirmed or signal.breakout_score >= 88.0 else "BUY_T_TIMING"
    target_signal = replace(signal, action=target_action)
    if not beta_hold_core_add and not _buy_point_quality_allows_entry(
        target_signal, config, min_score=config.min_risk_on_add_quality_score
    ):
        return 0.0
    model_target = _signal_target_position_pct(target_signal, config, attack_state=attack_state)
    if attack_state == ATTACK_BETA_HOLD and beta_hold_core_add:
        confirmation_target = max(config.beta_hold_main_rise_core_floor_pct, config.risk_on_core_floor_l3_pct)
        if _high_quality_breakout_add_signal(signal, config):
            confirmation_target = max(confirmation_target, config.risk_on_high_quality_breakout_upgrade_target_pct)
    elif attack_state == ATTACK_BETA_HOLD and non_force_confirmations >= 3:
        confirmation_target = max(config.beta_hold_target_position_pct, config.risk_on_core_floor_l3_pct)
    elif attack_state == ATTACK_BETA_HOLD and non_force_confirmations >= 2:
        confirmation_target = max(config.offensive_trend_add_floor_pct, config.risk_on_core_floor_l3_pct)
    elif non_force_confirmations >= 4:
        confirmation_target = max(0.95, config.risk_on_core_floor_l3_pct)
    elif non_force_confirmations >= 3:
        confirmation_target = max(0.75, config.risk_on_core_floor_l2_pct)
    else:
        confirmation_target = max(0.55, config.risk_on_core_floor_l1_pct)
    if volume_quality >= 0.80:
        confirmation_target += 0.08
    elif volume_quality >= 0.65:
        confirmation_target += 0.04
    confirmation_target = max(confirmation_target, config.risk_on_target_add_min_target_pct)
    confirmation_target += config.risk_on_target_add_bonus_pct
    if _high_quality_breakout_add_signal(signal, config):
        confirmation_target = max(confirmation_target, config.risk_on_high_quality_breakout_upgrade_target_pct)
    if portfolio_main_rise_target:
        confirmation_target = max(confirmation_target, config.portfolio_main_rise_position_target_pct)
    if attack_state == ATTACK_FULL:
        confirmation_target = max(confirmation_target, config.attack_full_position_pct)
    elif attack_state == ATTACK_CONFIRMED:
        confirmation_target = max(confirmation_target, config.attack_confirm_position_pct)
    elif attack_state == ATTACK_WATCH:
        confirmation_target = max(confirmation_target, config.attack_watch_position_pct)
    if signal.market_regime_state == "TREND_WATCH" and non_force_confirmations < 3:
        confirmation_target = min(confirmation_target, 0.68)
    target = max(model_target, confirmation_target)

    if attack_state == ATTACK_BETA_HOLD and _beta_hold_sustain_signal(signal, config):
        if signal.sell_pressure_score >= 82.0:
            target = min(target, 0.70)
    elif signal.sell_pressure_score >= 72.0:
        target = min(target, 0.45)
    elif signal.sell_pressure_score >= 68.0:
        target = min(target, 0.62)
    if attack_state == ATTACK_BETA_HOLD and (signal.down_probability_1d >= 0.64 or signal.down_probability_3d >= 0.66):
        target = min(target, 0.70)
    elif signal.down_probability_1d >= 0.58 or signal.down_probability_3d >= 0.60:
        target = min(target, 0.45)
    if attack_state == ATTACK_BETA_HOLD:
        if _beta_hold_distribution_reduce_signal(
            signal,
            config,
            active_profit_pct=0.0,
            active_peak_profit_pct=config.offensive_volume_distribution_min_peak_profit_pct,
        ):
            target = min(target, 0.82)
    elif _offensive_volume_distribution_reduce_signal(signal, config):
        target = min(target, 0.62)

    target = _risk_on_staged_position_target_pct(
        target,
        signal,
        config,
        current_position_pct=current_position_pct,
        attack_state=attack_state,
    )
    if target - current_position_pct < config.risk_on_position_target_min_gap_pct:
        return 0.0
    return target


def _risk_on_staged_position_target_pct(
    target: float,
    signal: BacktestSignal,
    config: DividendTBacktestConfig,
    *,
    current_position_pct: float,
    attack_state: str,
) -> float:
    staged_cap = _risk_on_position_stage_cap_pct(
        signal,
        current_position_pct=current_position_pct,
        config=config,
        attack_state=attack_state,
    )
    return round(clamp(min(target, staged_cap), config.initial_base_position_pct, config.max_signal_position_pct), 4)


def _risk_on_position_stage_cap_pct(
    signal: BacktestSignal,
    *,
    current_position_pct: float,
    config: DividendTBacktestConfig,
    attack_state: str,
) -> float:
    if _portfolio_main_rise_position_target_signal(signal, config, attack_state=attack_state):
        portfolio_cap = min(config.portfolio_main_rise_position_target_pct, config.max_signal_position_pct)
        if current_position_pct < portfolio_cap:
            return max(current_position_pct, portfolio_cap)
    if attack_state == ATTACK_BETA_HOLD and _beta_hold_main_rise_core_floor_signal(signal, config):
        floor = min(max(config.beta_hold_main_rise_core_floor_pct, config.risk_on_core_floor_l3_pct), config.max_signal_position_pct)
        if current_position_pct < floor:
            return max(current_position_pct, floor)
    if current_position_pct <= config.initial_base_position_pct + config.min_t_trade_pct:
        return config.risk_on_first_add_cap_pct
    if current_position_pct < 0.30:
        return config.risk_on_low_position_add_cap_pct
    if current_position_pct < 0.70:
        return config.risk_on_mid_position_add_cap_pct
    if _risk_on_full_add_confirmation_signal(signal, config):
        return config.max_signal_position_pct
    if _risk_on_high_position_reinforcement_signal(signal, config, attack_state=attack_state):
        return max(current_position_pct, min(config.risk_on_high_position_reinforce_cap_pct, config.max_signal_position_pct))
    return current_position_pct


def _risk_on_position_stage_label(
    signal: BacktestSignal,
    *,
    current_position_pct: float,
    config: DividendTBacktestConfig,
    attack_state: str,
) -> str:
    if _portfolio_main_rise_position_target_signal(signal, config, attack_state=attack_state):
        return f"组合盈利扩散主升≤{config.portfolio_main_rise_position_target_pct:.0%}"
    if current_position_pct <= config.initial_base_position_pct + config.min_t_trade_pct:
        return f"首买/低仓≤{config.risk_on_first_add_cap_pct:.0%}"
    if current_position_pct < 0.30:
        return f"低仓≤{config.risk_on_low_position_add_cap_pct:.0%}"
    if current_position_pct < 0.70:
        return f"中仓≤{config.risk_on_mid_position_add_cap_pct:.0%}"
    if _risk_on_full_add_confirmation_signal(signal, config):
        return "高仓极强确认可满仓"
    if _risk_on_high_position_reinforcement_signal(signal, config, attack_state=attack_state):
        return f"高仓核心强化≤{config.risk_on_high_position_reinforce_cap_pct:.0%}"
    return "高仓等待极强确认"


def _risk_on_staged_add_allows_signal(
    signal: BacktestSignal,
    config: DividendTBacktestConfig,
    *,
    current_position_pct: float,
    attack_state: str,
) -> bool:
    if _portfolio_main_rise_position_target_signal(signal, config, attack_state=attack_state):
        return current_position_pct < min(config.portfolio_main_rise_position_target_pct, config.max_signal_position_pct)
    if (
        attack_state == ATTACK_BETA_HOLD
        and _beta_hold_main_rise_core_floor_signal(signal, config)
        and current_position_pct
        < min(max(config.beta_hold_main_rise_core_floor_pct, config.risk_on_core_floor_l3_pct), config.max_signal_position_pct)
    ):
        return True
    if current_position_pct < 0.30:
        return True
    if current_position_pct >= 0.70:
        return _risk_on_full_add_confirmation_signal(signal, config) or _risk_on_high_position_reinforcement_signal(
            signal,
            config,
            attack_state=attack_state,
        )
    return _risk_on_secondary_add_confirmation_signal(signal, config)


def _portfolio_main_rise_position_target_signal(
    signal: BacktestSignal,
    config: DividendTBacktestConfig,
    *,
    attack_state: str,
) -> bool:
    if not config.enable_portfolio_main_rise_position_target:
        return False
    if config.portfolio_main_rise_position_target_pct <= config.risk_on_mid_position_add_cap_pct:
        return False
    if signal.market_environment_state != MARKET_RISK_ON:
        return False
    if signal.market_model_state_score < config.portfolio_main_rise_min_model_state_score:
        return False
    profit_diffusion = (
        signal.model_holding_win_rate >= config.portfolio_main_rise_min_holding_win_rate
        and signal.model_holding_profit_spread >= config.portfolio_main_rise_min_profit_spread
        and signal.model_new_buy_success_rate >= config.portfolio_main_rise_min_new_buy_success_rate
    )
    strong_profit_diffusion = (
        signal.model_holding_profit_spread >= max(config.portfolio_main_rise_min_profit_spread + 0.08, 0.70)
        and signal.model_holding_win_rate >= config.portfolio_main_rise_min_holding_win_rate - 0.04
    )
    if not (profit_diffusion or strong_profit_diffusion):
        return False
    if signal.market_regime_state not in {"BREAKOUT_ATTACK", "STRONG_TREND", "TREND_WATCH"}:
        return False
    if signal.probability_state == "DOWN_RISK" or signal.chan_sell_point_type in {"sell2", "sell3"}:
        return False
    if signal.chan_structure_type == "breakdown":
        return False
    if signal.sell_pressure_score >= config.attack_exit_sell_pressure_score:
        return False
    if signal.down_probability_1d >= config.attack_exit_down_probability:
        return False
    if signal.down_probability_3d >= config.attack_hard_exit_down_probability:
        return False
    if _offensive_volume_distribution_blocks_entry_signal(signal, config):
        return False
    if not _buy_volume_price_window_filter_allows(replace(signal, action="BUY_T_TIMING"), config):
        return False

    beta_hold_core = attack_state == ATTACK_BETA_HOLD and _beta_hold_main_rise_core_floor_signal(signal, config)
    stock_risk_on = _individual_stock_risk_on_signal(signal)
    sustained_main_rise = (
        _non_force_position_confirmation_count(signal) >= 3
        and (
            signal.trend_state == "UPTREND"
            or signal.breakout_confirmed
            or signal.breakout_score >= 86.0
            or (signal.chan_buy_point_type == "buy3" and signal.chan_score >= 74.0)
            or signal.post_breakout_volume_persistence_score >= 72.0
        )
        and (
            _signal_capital_flow_confirmed(signal, min_score=60.0)
            or signal.vwap_support_score >= 68.0
            or signal.post_breakout_volume_persistence_score >= 68.0
        )
    )
    return beta_hold_core or stock_risk_on or sustained_main_rise


def _runtime_breakout_alpha_score(signal: BacktestSignal) -> float:
    flow_confirmed = _signal_capital_flow_confirmed(signal, min_score=66.0)
    score = (
        0.22 * clamp((signal.breakout_score - 78.0) / 18.0, 0.0, 1.0)
        + 0.16 * clamp((signal.vwap_support_score - 62.0) / 20.0, 0.0, 1.0)
        + 0.16 * clamp((signal.volume_price_score - 62.0) / 22.0, 0.0, 1.0)
        + 0.14 * clamp((signal.post_breakout_volume_persistence_score - 62.0) / 22.0, 0.0, 1.0)
        + 0.14 * clamp((signal.capital_flow_confirmation_score - 58.0) / 24.0, 0.0, 1.0)
        + 0.10 * clamp((signal.force_weighted_score - 48.0) / 24.0, 0.0, 1.0)
        + 0.08 * clamp((70.0 - signal.sell_pressure_score) / 25.0, 0.0, 1.0)
    )
    if signal.breakout_confirmed:
        score += 0.05
    if signal.chan_buy_point_type == "buy3" and signal.chan_score >= 76.0:
        score += 0.03
    if flow_confirmed:
        score += 0.02
    if _breakout_stall_pressure_signal(signal) and not (
        signal.vwap_support_score >= 76.0 and signal.post_breakout_volume_persistence_score >= 76.0 and flow_confirmed
    ):
        score -= 0.08
    return round(clamp(score, 0.0, 1.0), 4)


def _breakout_stall_pressure_signal(signal: BacktestSignal) -> bool:
    return signal.high_volume_stall_score >= 78.0 or signal.price_up_volume_down_score >= 82.0


def _high_quality_breakout_add_signal(signal: BacktestSignal, config: DividendTBacktestConfig) -> bool:
    strong_volume = (
        signal.volume_price_score >= 78.0 and signal.volume_breakout_score >= 74.0 and signal.post_breakout_volume_persistence_score >= 76.0
    )
    strong_flow = (
        signal.capital_flow_confirmation_state == "CONFIRMED_INFLOW"
        and signal.capital_flow_confirmation_score >= 72.0
        and signal.capital_flow_confidence >= 0.50
    )
    pressure_clean = signal.sell_pressure_score < 64.0 and signal.down_probability_1d < 0.56 and signal.down_probability_3d < 0.58
    return (
        _runtime_breakout_alpha_score(signal) >= 0.90
        and (signal.breakout_confirmed or signal.breakout_score >= 92.0)
        and signal.vwap_support_score >= 76.0
        and strong_volume
        and strong_flow
        and pressure_clean
        and not _breakout_stall_pressure_signal(signal)
        and _main_rise_buy_quality_score(signal, config) >= config.risk_on_full_add_min_main_rise_quality_score
    )


def _qualified_breakout_hold_signal(signal: BacktestSignal, config: DividendTBacktestConfig) -> bool:
    return (
        _runtime_breakout_alpha_score(signal) >= 0.62
        and (signal.breakout_confirmed or signal.breakout_score >= 88.0)
        and signal.vwap_support_score >= 70.0
        and signal.volume_price_score >= 70.0
        and signal.volume_breakout_score >= 68.0
        and signal.post_breakout_volume_persistence_score >= 70.0
        and _signal_capital_flow_confirmed(signal, min_score=66.0)
        and signal.sell_pressure_score < min(config.attack_exit_sell_pressure_score, 76.0)
        and signal.down_probability_1d < min(config.attack_exit_down_probability, 0.60)
        and signal.down_probability_3d < min(config.attack_hard_exit_down_probability, 0.66)
    )


def _risk_on_secondary_add_confirmation_signal(signal: BacktestSignal, config: DividendTBacktestConfig) -> bool:
    if signal.trend_state == "EXHAUSTION" or signal.intraday_state == "LATE_SESSION":
        return False
    min_confirmations = max(config.risk_on_secondary_add_min_confirmations, config.risk_on_position_target_min_confirmations)
    if _beta_hold_sustain_signal(signal, config):
        min_confirmations = min(min_confirmations, config.risk_on_beta_hold_secondary_min_confirmations)
    return (
        _buy_point_quality_score(signal, config) >= config.min_risk_on_add_quality_score + config.risk_on_secondary_add_quality_buffer
        and _main_rise_buy_quality_score(signal, config)
        >= config.min_risk_on_add_main_rise_quality_score + config.risk_on_secondary_add_main_rise_quality_buffer
        and _non_force_position_confirmation_count(signal) >= min_confirmations
        and _high_quality_breakout_add_signal(signal, config)
        and signal.vwap_support_score >= config.risk_on_secondary_add_min_vwap_score
        and signal.volume_price_score >= config.risk_on_secondary_add_min_volume_price_score
        and signal.volume_breakout_score >= config.risk_on_secondary_add_min_volume_breakout_score
        and signal.post_breakout_volume_persistence_score >= config.risk_on_secondary_add_min_volume_persistence_score
        and _signal_capital_flow_confirmed(signal, min_score=config.risk_on_secondary_add_min_flow_score)
        and signal.sell_pressure_score < config.risk_on_secondary_add_max_sell_pressure_score
        and signal.down_probability_1d < config.risk_on_secondary_add_max_down_probability_1d
        and signal.down_probability_3d < config.risk_on_secondary_add_max_down_probability_3d
    )


def _risk_on_high_position_reinforcement_signal(
    signal: BacktestSignal,
    config: DividendTBacktestConfig,
    *,
    attack_state: str,
) -> bool:
    if attack_state != ATTACK_BETA_HOLD:
        return False
    if not config.enable_risk_on_high_position_reinforcement:
        return False
    if config.risk_on_high_position_reinforce_cap_pct <= 0:
        return False
    return _risk_on_secondary_add_confirmation_signal(signal, config)


def _risk_on_full_add_confirmation_signal(signal: BacktestSignal, config: DividendTBacktestConfig) -> bool:
    return (
        _high_quality_breakout_add_signal(signal, config)
        and _buy_point_quality_score(signal, config) >= config.risk_on_full_add_min_quality_score
        and _main_rise_buy_quality_score(signal, config) >= config.risk_on_full_add_min_main_rise_quality_score
        and _non_force_position_confirmation_count(signal) >= 4
        and signal.vwap_support_score >= 76.0
        and signal.volume_breakout_score >= 74.0
        and signal.post_breakout_volume_persistence_score >= 76.0
        and _signal_capital_flow_confirmed(signal, min_score=72.0)
        and signal.sell_pressure_score < 64.0
        and signal.down_probability_1d < 0.56
        and signal.down_probability_3d < 0.58
    )


def _risk_on_target_add_confirmation_signal(signal: BacktestSignal, config: DividendTBacktestConfig) -> bool:
    breakout_confirmed = signal.breakout_confirmed or signal.breakout_score >= 88.0
    vwap_confirmed = signal.vwap_support_score >= 70.0
    volume_confirmed = (
        signal.volume_price_score >= 70.0 and signal.volume_breakout_score >= 68.0 and signal.post_breakout_volume_persistence_score >= 70.0
    )
    flow_confirmed = _signal_capital_flow_confirmed(signal, min_score=66.0)
    main_rise_confirmed = _main_rise_buy_quality_score(signal, config) >= config.min_risk_on_add_main_rise_quality_score
    pressure_clean = (
        signal.sell_pressure_score < min(config.attack_exit_sell_pressure_score, 76.0)
        and signal.down_probability_1d < min(config.attack_exit_down_probability, 0.60)
        and signal.down_probability_3d < min(config.attack_hard_exit_down_probability, 0.66)
    )
    return breakout_confirmed and vwap_confirmed and volume_confirmed and flow_confirmed and main_rise_confirmed and pressure_clean


def _buy_t_failure_cooldown_blocks_signal(
    signal: BacktestSignal,
    config: DividendTBacktestConfig,
    *,
    bars_remaining: int,
) -> bool:
    if bars_remaining <= 0 or config.buy_t_failure_cooldown_bars <= 0:
        return False
    if signal.action != "BUY_T_TIMING":
        return False
    return not _buy_t_cooldown_bypass_signal(signal, config)


def _buy_t_cooldown_bypass_signal(signal: BacktestSignal, config: DividendTBacktestConfig) -> bool:
    return (
        _main_rise_buy_quality_score(signal, config) >= config.min_main_rise_buy_quality_score + 0.22
        and signal.market_regime_state in {"BREAKOUT_ATTACK", "STRONG_TREND"}
        and signal.trend_state == "UPTREND"
        and (signal.breakout_confirmed or signal.breakout_score >= 88.0)
        and signal.vwap_support_score >= 72.0
        and signal.post_breakout_volume_persistence_score >= 72.0
        and _signal_capital_flow_confirmed(signal, min_score=66.0)
        and signal.sell_pressure_score < min(config.attack_exit_sell_pressure_score, 76.0)
        and signal.down_probability_1d < min(config.attack_exit_down_probability, 0.60)
    )


def _buy_t_failure_cooldown_trigger_trade(trade: DividendTTrade) -> bool:
    return (
        trade.side == "STOP_T"
        and trade.action in {"STOP_T_WAIT", "WAIT_DAILY_WEAK"}
        and trade.realized_pnl is not None
        and trade.realized_pnl <= 0.0
    )


def _breakout_follow_through_cooldown_blocks_signal(
    signal: BacktestSignal,
    config: DividendTBacktestConfig,
    *,
    bars_remaining: int,
    current_position_shares: int,
) -> bool:
    if bars_remaining <= 0 or config.breakout_follow_through_failure_cooldown_bars <= 0:
        return False
    if current_position_shares <= 0:
        return False
    if signal.action != "BREAKOUT_BUY_TIMING":
        return False
    return not _risk_on_target_add_confirmation_signal(signal, config)


def _breakout_follow_through_confirmed(
    data: Any,
    *,
    buy_index: int,
    buy_price: float,
    buy_high: float,
    config: DividendTBacktestConfig,
) -> bool:
    if config.breakout_follow_through_bars <= 0:
        return True
    start = buy_index + 1
    end = start + config.breakout_follow_through_bars
    if start >= len(data):
        return False
    future = data.iloc[start:end]
    if future.empty:
        return False
    future_high = _safe_series_max(future, "high", fallback_col="close")
    high_reference = max(float(buy_price), float(buy_high), 0.0)
    new_high_confirmed = high_reference > 0 and future_high >= high_reference * (1.0 + config.breakout_follow_through_min_high_return_pct)
    if not new_high_confirmed:
        return False

    lookback_start = max(0, buy_index - max(10, config.breakout_follow_through_bars * 2))
    lookback = data.iloc[lookback_start:buy_index]
    future_volume = _safe_series_mean(future, "volume", fallback_col="amount")
    lookback_volume = _safe_series_mean(lookback, "volume", fallback_col="amount")
    if lookback_volume <= 0.0:
        return future_volume > 0.0
    return future_volume >= lookback_volume * config.breakout_follow_through_volume_ratio


def _risk_on_add_follow_through_cooldown_blocks_target(
    *,
    bars_remaining: int,
    config: DividendTBacktestConfig,
) -> bool:
    return bars_remaining > 0 and config.risk_on_add_follow_through_failure_cooldown_bars > 0


def _risk_on_add_follow_through_confirmed(
    data: Any,
    *,
    buy_index: int,
    buy_price: float,
    buy_high: float,
    config: DividendTBacktestConfig,
) -> bool:
    if config.risk_on_add_follow_through_bars <= 0:
        return True
    start = buy_index + 1
    end = start + config.risk_on_add_follow_through_bars
    if start >= len(data):
        return False
    future = data.iloc[start:end]
    if future.empty:
        return False

    high_reference = max(float(buy_price), float(buy_high), 0.0)
    future_high = _safe_series_max(future, "high", fallback_col="close")
    if high_reference <= 0 or future_high < high_reference * (1.0 + config.risk_on_add_follow_through_min_high_return_pct):
        return False

    lookback_start = max(0, buy_index - max(10, config.risk_on_add_follow_through_bars * 2))
    lookback = data.iloc[lookback_start:buy_index]
    future_volume = _safe_series_mean(future, "volume", fallback_col="amount")
    lookback_volume = _safe_series_mean(lookback, "volume", fallback_col="amount")
    if lookback_volume > 0.0 and future_volume < lookback_volume * config.risk_on_add_follow_through_volume_ratio:
        return False

    return _future_vwap_support_holds(
        future,
        buy_price=float(buy_price),
        tolerance_pct=config.risk_on_add_follow_through_vwap_tolerance_pct,
    )


def _future_vwap_support_holds(future: Any, *, buy_price: float, tolerance_pct: float) -> bool:
    closes = _safe_series_values(future, "close")
    if not closes or buy_price <= 0.0:
        return False
    vwaps = _bar_vwap_values(future)
    tolerance = max(0.0, float(tolerance_pct))
    hard_close_floor = buy_price * (1.0 - max(0.018, tolerance * 2.0))
    if min(closes) < hard_close_floor:
        return False
    if not vwaps:
        return True
    checks = [close >= vwap * (1.0 - tolerance) for close, vwap in zip(closes, vwaps, strict=False) if vwap > 0.0]
    if not checks:
        return True
    return sum(1 for passed in checks if passed) / len(checks) >= 0.70


def _bar_vwap_values(frame: Any) -> list[float]:
    closes = _safe_series_values(frame, "close")
    if "amount" not in frame or "volume" not in frame:
        return closes
    amounts = _safe_series_values(frame, "amount")
    volumes = _safe_series_values(frame, "volume")
    values: list[float] = []
    for index, close in enumerate(closes):
        amount = amounts[index] if index < len(amounts) else 0.0
        volume = volumes[index] if index < len(volumes) else 0.0
        values.append(amount / volume if amount > 0.0 and volume > 0.0 else close)
    return values


def _with_pretrade_volume_price_context(
    signal: BacktestSignal,
    history: Any,
    config: DividendTBacktestConfig,
) -> BacktestSignal:
    short_features = _pretrade_volume_price_window_features(
        history,
        lookback_bars=config.buy_volume_price_short_lookback_bars,
        min_return_pct=config.buy_volume_price_filter_min_return_pct,
        max_volume_ratio=config.buy_volume_price_filter_max_contract_ratio,
    )
    mid_features = _pretrade_volume_price_window_features(
        history,
        lookback_bars=config.buy_volume_price_mid_lookback_bars,
        min_return_pct=max(config.buy_volume_price_filter_min_return_pct * 1.5, 0.006),
        max_volume_ratio=config.buy_volume_price_filter_max_contract_ratio,
    )
    features = _pretrade_volume_price_window_features(
        history,
        lookback_bars=config.volume_price_continuation_lookback_bars,
        min_return_pct=config.volume_price_continuation_min_return_pct,
        max_volume_ratio=config.volume_price_continuation_max_volume_ratio,
    )
    buy_point_subtype = _signal_buy_point_subtype(
        signal,
        pretrade_volume_price_state=str(features["volume_price_state"]),
    )
    return replace(
        signal,
        buy_point_subtype=buy_point_subtype,
        pretrade_volume_price_state_12=str(short_features["volume_price_state"]),
        pretrade_price_return_pct_12=float(short_features["price_return_pct"]),
        pretrade_volume_ratio_to_prev_12=float(short_features["volume_ratio_to_prev"]),
        pretrade_volume_price_state_24=str(mid_features["volume_price_state"]),
        pretrade_price_return_pct_24=float(mid_features["price_return_pct"]),
        pretrade_volume_ratio_to_prev_24=float(mid_features["volume_ratio_to_prev"]),
        pretrade_volume_price_state=str(features["volume_price_state"]),
        pretrade_volume_price_lookback_bars=int(features["actual_bars"]),
        pretrade_price_return_pct=float(features["price_return_pct"]),
        pretrade_volume_ratio_to_prev=float(features["volume_ratio_to_prev"]),
    )


def _with_buy_point_subtype(signal: BacktestSignal) -> BacktestSignal:
    return replace(signal, buy_point_subtype=_signal_buy_point_subtype(signal))


def _signal_buy_point_subtype(
    signal: BacktestSignal,
    *,
    pretrade_volume_price_state: str | None = None,
) -> str:
    del pretrade_volume_price_state
    if signal.buy_point_subtype != "none":
        return signal.buy_point_subtype
    return classify_buy_point_subtype(signal.primary_setup_code)


def _pretrade_volume_price_window_features(
    history: Any,
    *,
    lookback_bars: int,
    min_return_pct: float,
    max_volume_ratio: float,
) -> dict[str, float | int | str]:
    if history is None or lookback_bars <= 0 or len(history) < max(8, lookback_bars // 2):
        return {
            "volume_price_state": "UNKNOWN",
            "actual_bars": 0 if history is None else len(history),
            "price_return_pct": 0.0,
            "volume_ratio_to_prev": 1.0,
        }
    window = history.tail(lookback_bars)
    closes = _safe_series_values(window, "close")
    volumes = _safe_series_values(window, "volume")
    if len(closes) < 8 or len(volumes) < 8 or closes[0] <= 0:
        return {
            "volume_price_state": "UNKNOWN",
            "actual_bars": len(window),
            "price_return_pct": 0.0,
            "volume_ratio_to_prev": 1.0,
        }

    price_return = closes[-1] / closes[0] - 1.0
    recent_span = max(4, min(12, len(volumes) // 3))
    recent_volume = sum(volumes[-recent_span:]) / recent_span
    previous = volumes[:-recent_span]
    previous_volume = sum(previous) / len(previous) if previous else recent_volume
    volume_ratio = recent_volume / previous_volume if previous_volume > 0.0 else 1.0

    price_up = price_return >= min_return_pct
    price_down = price_return <= -min_return_pct
    volume_down = volume_ratio <= max_volume_ratio
    volume_up = volume_ratio >= max(1.05, 2.0 - max_volume_ratio)
    if price_up and volume_down:
        state = "price_up_volume_down"
    elif price_up and volume_up:
        state = "price_up_volume_up"
    elif price_down and volume_up:
        state = "price_down_volume_up"
    elif price_down and volume_down:
        state = "price_down_volume_down"
    elif volume_down:
        state = "flat_volume_contract"
    elif volume_up:
        state = "flat_volume_expand"
    else:
        state = "neutral_volume_price"
    return {
        "volume_price_state": state,
        "actual_bars": len(window),
        "price_return_pct": round(price_return, 6),
        "volume_ratio_to_prev": round(volume_ratio, 6),
    }


def _late_stage_stall_entry_blocks(
    history: Any | None,
    *,
    execution: Any,
    signal: BacktestSignal,
    config: DividendTBacktestConfig,
) -> bool:
    if not config.late_stage_stall_entry_filter_enabled or history is None or len(history) < 8:
        return False
    if _risk_on_full_add_confirmation_signal(signal, config):
        return False
    entry_price = _row_float(execution, "open")
    if entry_price <= 0.0:
        return False
    recent = history.tail(max(8, config.late_stage_recent_high_lookback_bars))
    recent_high = _safe_series_max(recent, "high", fallback_col="close")
    if recent_high <= 0.0 or entry_price < recent_high * (1.0 - config.late_stage_near_high_pct):
        return False

    stall_count = _late_stage_consecutive_stall_bars(history, config)
    last_bar = history.iloc[-1]
    last_structure = _bar_structure(last_bar)
    weak_last_bar = last_structure["range_pct"] >= config.late_stage_min_range_pct and (
        last_structure["upper_shadow_ratio"] >= config.late_stage_max_upper_shadow_ratio
        or last_structure["body_progress_ratio"] <= config.late_stage_min_body_progress_ratio
    )
    distribution_signal = (
        signal.high_volume_stall_score >= config.offensive_volume_stall_reduce_score
        or signal.price_up_volume_down_score >= config.offensive_price_up_volume_down_reduce_score
        or signal.sell_pressure_score >= 68.0
    )
    if not distribution_signal:
        return False
    if _late_stage_pullback_quality_supports_entry(signal, config):
        return False
    return weak_last_bar or stall_count >= config.late_stage_max_stall_bars


def _late_stage_pullback_quality_supports_entry(signal: BacktestSignal, config: DividendTBacktestConfig) -> bool:
    return (
        signal.low_volume_pullback_score >= 74.0
        and signal.vwap_support_score >= 70.0
        and signal.post_breakout_volume_persistence_score >= 70.0
        and signal.high_volume_stall_score < config.offensive_volume_distribution_hard_stall_score
        and signal.sell_pressure_score < 70.0
    )


def _late_stage_consecutive_stall_bars(history: Any, config: DividendTBacktestConfig) -> int:
    window = history.tail(max(2, config.late_stage_stall_lookback_bars))
    recent_high = _safe_series_max(history.tail(max(8, config.late_stage_recent_high_lookback_bars)), "high", fallback_col="close")
    if recent_high <= 0.0:
        return 0
    count = 0
    for _, row in reversed(list(window.iterrows())):
        structure = _bar_structure(row)
        close = _row_float(row, "close")
        near_high = close >= recent_high * (1.0 - config.late_stage_near_high_pct * 1.5)
        stalled = (
            near_high
            and structure["range_pct"] >= config.late_stage_min_range_pct
            and (
                structure["upper_shadow_ratio"] >= config.late_stage_max_upper_shadow_ratio
                or structure["body_progress_ratio"] <= config.late_stage_min_body_progress_ratio
            )
        )
        if not stalled:
            break
        count += 1
    return count


def _bar_structure(row: Any) -> dict[str, float]:
    open_price = _row_float(row, "open")
    high = _row_float(row, "high")
    low = _row_float(row, "low")
    close = _row_float(row, "close")
    price_range = max(high - low, 0.0)
    if price_range <= 0.0 or close <= 0.0:
        return {"range_pct": 0.0, "upper_shadow_ratio": 0.0, "body_progress_ratio": 1.0}
    upper_shadow = max(high - max(open_price, close), 0.0)
    body = abs(close - open_price)
    return {
        "range_pct": price_range / close,
        "upper_shadow_ratio": upper_shadow / price_range,
        "body_progress_ratio": body / price_range,
    }


def _row_float(row: Any, column: str, default: float = 0.0) -> float:
    try:
        value = row[column]
    except (KeyError, TypeError):
        return default
    return float(value) if _is_finite_number(value) else default


def _safe_series_values(frame: Any, column: str) -> list[float]:
    if frame.empty or column not in frame:
        return []
    return [float(value) for value in frame[column] if _is_finite_number(value)]


def _safe_series_max(frame: Any, column: str, *, fallback_col: str) -> float:
    selected = frame[column] if column in frame else frame[fallback_col]
    values = [float(value) for value in selected if _is_finite_number(value)]
    return max(values) if values else 0.0


def _safe_series_mean(frame: Any, column: str, *, fallback_col: str) -> float:
    if frame.empty:
        return 0.0
    selected = frame[column] if column in frame else frame[fallback_col]
    values = [float(value) for value in selected if _is_finite_number(value)]
    return sum(values) / len(values) if values else 0.0


def _is_finite_number(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _candidate_entry_confirm_signal(signal: BacktestSignal, config: DividendTBacktestConfig) -> bool:
    if not config.enable_candidate_entry:
        return False
    if signal.action in {
        "SELL_T_TIMING",
        "STOP_T_WAIT",
        "WAIT_DAILY_WEAK",
        "WAIT_MARKET_CAUTION",
        "WAIT_LATE_SESSION",
        "WAIT_CONFIRMATION",
        "WAIT_STALE_DATA",
    }:
        return False
    if signal.market_regime_state not in {"BREAKOUT_ATTACK", "STRONG_TREND", "TREND_WATCH"}:
        return False
    if signal.probability_state == "DOWN_RISK" or signal.chan_sell_point_type in {"sell1", "sell2", "sell3"}:
        return False
    if signal.chan_structure_type == "breakdown":
        return False
    if signal.buy_signal_strength < config.candidate_entry_confirm_min_strength:
        return False
    if signal.sell_pressure_score >= config.attack_exit_sell_pressure_score:
        return False
    if signal.down_probability_1d >= config.attack_exit_down_probability:
        return False
    if signal.down_probability_3d >= config.attack_hard_exit_down_probability:
        return False
    if _offensive_volume_distribution_blocks_entry_signal(signal, config):
        return False
    if config.candidate_entry_confirm_requires_follow_through and not _candidate_entry_confirm_follow_through_signal(signal, config):
        return False

    strong_trend = signal.market_regime_state in {"BREAKOUT_ATTACK", "STRONG_TREND"} and (
        signal.trend_state == "UPTREND" or signal.breakout_score >= 84.0
    )
    if not strong_trend and signal.action not in {"BUY_T_TIMING", "BREAKOUT_BUY_TIMING", "WAIT_STRONG_TREND", "WATCH_BREAKOUT_NEXT_DAY"}:
        return False
    confirmations = _non_force_position_confirmation_count(signal)
    target_action = "BREAKOUT_BUY_TIMING" if signal.breakout_confirmed or signal.breakout_score >= 88.0 else "BUY_T_TIMING"
    target_signal = replace(signal, action=target_action)
    return confirmations >= config.candidate_entry_confirm_min_confirmations and _buy_point_quality_allows_entry(
        target_signal,
        config,
        min_score=config.min_risk_on_add_quality_score,
    )


def _candidate_entry_confirm_target_pct(config: DividendTBacktestConfig) -> float:
    return round(
        clamp(
            min(config.candidate_entry_confirm_target_pct, config.candidate_entry_confirm_probe_target_pct),
            config.initial_base_position_pct,
            config.max_signal_position_pct,
        ),
        4,
    )


def _candidate_entry_confirm_follow_through_signal(signal: BacktestSignal, config: DividendTBacktestConfig) -> bool:
    if config.candidate_entry_confirm_market_passthrough and (
        signal.market_environment_state == MARKET_RISK_ON or _individual_stock_risk_on_signal(signal)
    ):
        return True
    breakout_continuation = (
        (signal.breakout_confirmed or signal.breakout_score >= 88.0)
        and signal.vwap_support_score >= 70.0
        and signal.post_breakout_volume_persistence_score >= 70.0
        and signal.volume_breakout_score >= 68.0
        and _signal_capital_flow_confirmed(signal, min_score=64.0)
        and signal.sell_pressure_score < min(config.attack_exit_sell_pressure_score, 76.0)
        and signal.down_probability_1d < min(config.attack_exit_down_probability, 0.60)
        and signal.down_probability_3d < min(config.attack_hard_exit_down_probability, 0.66)
    )
    return breakout_continuation


def _candidate_entry_hold_blocks_exit(
    *,
    signal: BacktestSignal,
    config: DividendTBacktestConfig,
    bars_remaining: int,
    active_profit_pct: float,
) -> bool:
    if not config.enable_candidate_entry or config.candidate_entry_min_hold_bars <= 0:
        return False
    if bars_remaining <= 0:
        return False
    return not _candidate_entry_hard_exit_signal(signal, config, active_profit_pct=active_profit_pct)


def _candidate_entry_hard_exit_signal(
    signal: BacktestSignal,
    config: DividendTBacktestConfig,
    *,
    active_profit_pct: float,
) -> bool:
    if active_profit_pct <= -config.candidate_entry_hard_stop_loss_pct:
        return True
    if signal.sell_pressure_score >= config.attack_hard_exit_sell_pressure_score:
        return True
    if signal.down_probability_1d >= config.attack_hard_exit_down_probability:
        return True
    if signal.down_probability_3d >= config.attack_hard_exit_down_probability:
        return True
    risk_confirmed = (
        active_profit_pct < 0.0
        or signal.sell_pressure_score >= config.attack_exit_sell_pressure_score
        or signal.down_probability_1d >= config.attack_exit_down_probability
        or signal.down_probability_3d >= config.attack_exit_down_probability
    )
    if signal.chan_structure_type == "breakdown" and risk_confirmed:
        return True
    if signal.chan_sell_point_type == "sell3" and risk_confirmed:
        return True
    return (
        signal.market_regime_state == "DEFENSIVE"
        and signal.trend_state == "DOWNTREND"
        and signal.probability_state == "DOWN_RISK"
        and risk_confirmed
    )


def _kelly_target_trade_pct(signal: BacktestSignal, config: DividendTBacktestConfig) -> float:
    return _signal_target_position_pct(signal, config)


def _layered_position_floor_pct(signal: BacktestSignal, config: DividendTBacktestConfig, *, attack_state: str = ATTACK_INACTIVE) -> float:
    if signal.action not in {"BUY_T_TIMING", "BREAKOUT_BUY_TIMING"}:
        return config.initial_base_position_pct
    if (
        signal.probability_state == "DOWN_RISK"
        or signal.sell_pressure_score >= 86.0
        or signal.chan_sell_point_type in {"sell1", "sell2", "sell3"}
    ):
        return config.initial_base_position_pct + config.min_t_trade_pct
    attack_floor = _attack_position_floor_pct(attack_state, config)
    flow_floor_bonus = 0.12 if _signal_capital_flow_confirmed(signal, min_score=62.0) else 0.0
    volume_floor_bonus = 0.0
    if signal.volume_breakout_score >= 74.0 and signal.vwap_support_score >= 66.0:
        volume_floor_bonus += 0.08
    if signal.post_breakout_volume_persistence_score >= 74.0:
        volume_floor_bonus += 0.06
    if signal.low_volume_pullback_score >= 74.0 and signal.sell_pressure_score < 72.0:
        volume_floor_bonus += 0.04
    if signal.high_volume_stall_score >= 74.0 or signal.price_up_volume_down_score >= 80.0:
        volume_floor_bonus = min(volume_floor_bonus, 0.02)
    if _offensive_full_add_signal(signal, config):
        return round(
            min(
                config.offensive_full_add_floor_pct,
                _signal_t_trade_cap(signal, config, attack_state=attack_state),
                config.max_signal_position_pct,
            ),
            4,
        )
    if _offensive_trend_add_signal(signal, config):
        return round(
            min(
                config.offensive_trend_add_floor_pct,
                _signal_t_trade_cap(signal, config, attack_state=attack_state),
                config.max_signal_position_pct,
            ),
            4,
        )
    if signal.action == "BREAKOUT_BUY_TIMING":
        if signal.buy_signal_strength >= 86.0 and signal.breakout_score >= 92.0 and signal.sell_pressure_score < 64.0:
            floor = 0.60
        elif signal.buy_signal_strength >= 80.0 and signal.breakout_score >= 88.0:
            floor = 0.45
        elif signal.buy_signal_strength >= 76.0:
            floor = 0.32
        elif signal.buy_signal_strength >= config.min_buy_signal_strength:
            floor = 0.20
        else:
            floor = config.initial_base_position_pct + config.min_t_trade_pct
        floor = min(0.78, floor + flow_floor_bonus + volume_floor_bonus)
        floor = max(floor, attack_floor)
    else:
        if signal.chan_buy_point_type == "buy3" and signal.chan_score >= 80.0:
            floor = 0.42
        elif signal.buy_signal_strength >= 86.0 and signal.market_regime_state == "STRONG_TREND":
            floor = 0.60
        elif signal.buy_signal_strength >= 80.0:
            floor = 0.45 if signal.market_regime_state in {"STRONG_TREND", "TREND_WATCH"} else 0.35
        elif signal.buy_signal_strength >= 72.0:
            floor = 0.28
        elif signal.buy_signal_strength >= config.min_buy_signal_strength:
            floor = 0.18
        else:
            floor = config.initial_base_position_pct + config.min_t_trade_pct
        floor = min(0.72, floor + flow_floor_bonus + volume_floor_bonus)
    if signal.down_probability_1d >= 0.57:
        floor = min(floor, 0.20)
    elif signal.sell_pressure_score >= 76.0:
        floor = min(floor, 0.28)
    return round(min(floor, _signal_t_trade_cap(signal, config, attack_state=attack_state), config.max_signal_position_pct), 4)


def _signal_strength_position_cap_floor(signal: BacktestSignal, config: DividendTBacktestConfig, *, attack_state: str) -> float:
    if signal.buy_signal_strength < config.min_buy_signal_strength:
        return 0.0
    if signal.probability_state == "DOWN_RISK" or signal.sell_pressure_score >= 86.0:
        return config.initial_base_position_pct + config.min_t_trade_pct
    if _full_position_signal(signal, config, attack_state=attack_state):
        return config.max_signal_position_pct

    strength = _buy_strength_score(signal, config)
    confirmation_count = _position_confirmation_count(signal)
    non_force_confirmations = _non_force_position_confirmation_count(signal)
    base_cap = config.range_signal_position_pct + (config.max_signal_position_pct - config.range_signal_position_pct) * (strength**1.15)
    if signal.market_regime_state in {"BREAKOUT_ATTACK", "STRONG_TREND"}:
        base_cap = max(base_cap, config.strong_trend_signal_position_pct)
    elif signal.market_regime_state == "TREND_WATCH":
        base_cap = max(base_cap, config.trend_watch_signal_position_pct)

    confirmation_bonus = min(0.24, confirmation_count * 0.08)
    if signal.market_environment_state == MARKET_RISK_ON:
        confirmation_bonus += 0.06
    if signal.action == "BREAKOUT_BUY_TIMING" and signal.breakout_confirmed:
        confirmation_bonus += 0.08
    if signal.chan_buy_point_type == "buy3" and signal.chan_score >= 78.0:
        confirmation_bonus += 0.06
    if _signal_capital_flow_confirmed(signal, min_score=62.0):
        confirmation_bonus += 0.06
    if _volume_price_confirmed(signal):
        confirmation_bonus += 0.06
    if non_force_confirmations >= 3:
        confirmation_bonus += 0.10
    elif non_force_confirmations >= 2:
        confirmation_bonus += 0.06

    cap = base_cap + confirmation_bonus
    if signal.sell_pressure_score >= 76.0:
        cap = min(cap, 0.35)
    elif signal.sell_pressure_score >= 68.0:
        cap = min(cap, 0.62)
    if signal.down_probability_1d >= 0.58 or signal.down_probability_3d >= 0.60:
        cap = min(cap, 0.35)
    if _offensive_volume_distribution_reduce_signal(signal, config):
        cap = min(cap, 0.45)
    return round(clamp(cap, config.initial_base_position_pct + config.min_t_trade_pct, config.max_signal_position_pct), 4)


def _position_signal_score(signal: BacktestSignal, config: DividendTBacktestConfig, *, attack_state: str) -> float:
    strength = _buy_strength_score(signal, config)
    breakout = clamp((signal.breakout_score - 68.0) / 28.0, 0.0, 1.0)
    if signal.breakout_confirmed:
        breakout = max(breakout, 0.82)
    chan = clamp((signal.chan_score - 66.0) / 24.0, 0.0, 1.0) if signal.chan_buy_point_type == "buy3" else 0.0
    flow = clamp((0.55 * signal.capital_flow_score + 0.45 * signal.capital_flow_confirmation_score - 55.0) / 35.0, 0.0, 1.0)
    if _signal_capital_flow_confirmed(signal, min_score=62.0):
        flow = max(flow, 0.75)
    volume = _volume_price_score(signal)
    force = clamp(
        0.55 * clamp((signal.force_ratio - 0.85) / 0.65, 0.0, 1.0) + 0.45 * clamp((signal.force_weighted_score - 45.0) / 35.0, 0.0, 1.0),
        0.0,
        1.0,
    )
    probability = clamp(
        0.55 * clamp((signal.up_probability_1d - 0.50) / 0.12, 0.0, 1.0)
        + 0.45 * clamp((signal.up_probability_3d - 0.50) / 0.12, 0.0, 1.0)
        - 0.35 * clamp((signal.down_probability_1d - 0.54) / 0.16, 0.0, 1.0),
        0.0,
        1.0,
    )
    kelly_reference = clamp(signal.kelly_fraction * config.kelly_fraction_scale / 0.22, 0.0, 1.0)
    score = (
        0.34 * strength
        + 0.16 * breakout
        + 0.12 * chan
        + 0.14 * flow
        + 0.16 * volume
        + 0.04 * force
        + 0.03 * probability
        + 0.01 * kelly_reference
    )
    non_force_confirmations = _non_force_position_confirmation_count(signal)
    if non_force_confirmations >= 3:
        score += 0.10
    elif non_force_confirmations >= 2:
        score += 0.06
    if signal.action == "BREAKOUT_BUY_TIMING":
        score += 0.04
    if attack_state == ATTACK_CONFIRMED:
        score += 0.08
    elif attack_state == ATTACK_FULL:
        score += 0.16
    if signal.market_environment_state == MARKET_RISK_ON:
        score += 0.05
    if signal.market_regime_state in {"BREAKOUT_ATTACK", "STRONG_TREND"}:
        score += 0.04
    if _offensive_volume_distribution_reduce_signal(signal, config):
        score -= 0.12
    elif _offensive_volume_distribution_soft_signal(signal, config):
        score -= 0.04
    if signal.sell_pressure_score >= 72.0:
        score -= 0.16
    if signal.down_probability_1d >= 0.58:
        score -= 0.16
    return round(clamp(score, 0.0, 1.0), 4)


def _full_position_signal(signal: BacktestSignal, config: DividendTBacktestConfig, *, attack_state: str) -> bool:
    if signal.probability_state == "DOWN_RISK" or signal.chan_sell_point_type in {"sell1", "sell2", "sell3"}:
        return False
    if _offensive_volume_distribution_reduce_signal(signal, config):
        return False
    if signal.sell_pressure_score >= min(config.attack_exit_sell_pressure_score, 76.0):
        return False
    if signal.down_probability_1d >= min(config.attack_exit_down_probability, 0.60):
        return False
    if _offensive_full_add_signal(signal, config):
        return True
    confirmations = _position_confirmation_count(signal)
    non_force_confirmations = _non_force_position_confirmation_count(signal)
    if attack_state == ATTACK_BETA_HOLD and non_force_confirmations >= 2 and signal.buy_signal_strength >= config.beta_hold_min_strength:
        return True
    if attack_state == ATTACK_FULL and confirmations >= 1 and signal.buy_signal_strength >= config.attack_confirm_min_buy_strength:
        return True
    if (
        signal.market_environment_state == MARKET_RISK_ON
        and signal.buy_signal_strength >= 84.0
        and non_force_confirmations >= 3
        and signal.market_regime_state in {"BREAKOUT_ATTACK", "STRONG_TREND"}
        and signal.sell_pressure_score < 68.0
        and signal.down_probability_1d < 0.58
    ):
        return True
    return (
        signal.buy_signal_strength >= 90.0
        and confirmations >= 2
        and signal.market_regime_state in {"BREAKOUT_ATTACK", "STRONG_TREND"}
        and signal.sell_pressure_score < 64.0
        and signal.down_probability_1d < 0.56
    )


def _position_confirmation_count(signal: BacktestSignal) -> int:
    confirmations = _non_force_position_confirmation_count(signal)
    if signal.force_ratio >= 1.18 or signal.force_weighted_score >= 68.0:
        confirmations += 1
    return confirmations


def _non_force_position_confirmation_count(signal: BacktestSignal) -> int:
    confirmations = 0
    if signal.breakout_confirmed or signal.breakout_score >= 88.0:
        confirmations += 1
    if signal.chan_buy_point_type == "buy3" and signal.chan_score >= 76.0:
        confirmations += 1
    if _signal_capital_flow_confirmed(signal, min_score=62.0):
        confirmations += 1
    if _volume_price_confirmed(signal):
        confirmations += 1
    return confirmations


def _volume_price_confirmed(signal: BacktestSignal) -> bool:
    return (
        signal.volume_price_score >= 72.0
        and (
            signal.volume_breakout_score >= 70.0
            or signal.post_breakout_volume_persistence_score >= 70.0
            or signal.vwap_support_score >= 70.0
            or signal.low_volume_pullback_score >= 74.0
        )
        and (signal.high_volume_stall_score < 72.0 or _offensive_volume_distribution_absorbed(signal, DividendTBacktestConfig()))
    )


def _volume_price_score(signal: BacktestSignal) -> float:
    return clamp(
        0.30 * clamp((signal.volume_price_score - 55.0) / 35.0, 0.0, 1.0)
        + 0.22 * clamp((signal.volume_breakout_score - 58.0) / 34.0, 0.0, 1.0)
        + 0.18 * clamp((signal.post_breakout_volume_persistence_score - 58.0) / 34.0, 0.0, 1.0)
        + 0.18 * clamp((signal.vwap_support_score - 58.0) / 34.0, 0.0, 1.0)
        + 0.12 * clamp((signal.low_volume_pullback_score - 60.0) / 30.0, 0.0, 1.0),
        0.0,
        1.0,
    )


def _risk_on_volume_price_quality(signal: BacktestSignal) -> float:
    constructive = _volume_price_score(signal)
    if _volume_price_confirmed(signal):
        constructive = max(constructive, 0.72)
    if signal.post_breakout_volume_persistence_score >= 72.0:
        constructive += 0.08
    if signal.vwap_support_score >= 70.0:
        constructive += 0.06
    if signal.low_volume_pullback_score >= 74.0 and signal.sell_pressure_score < 72.0:
        constructive += 0.05
    if signal.volume_breakout_score >= 76.0:
        constructive += 0.06
    default_config = DividendTBacktestConfig()
    strong_trend_override = _strong_trend_volume_distribution_override_signal(signal, default_config)
    if strong_trend_override:
        constructive += 0.06
    elif _offensive_volume_distribution_reduce_signal(signal, default_config):
        constructive -= 0.14
    elif _offensive_volume_distribution_soft_signal(signal, default_config):
        constructive -= 0.05
    if (
        not strong_trend_override
        and signal.price_up_volume_down_score >= 78.0
        and not _offensive_volume_distribution_absorbed(signal, default_config)
        and not _price_up_volume_down_main_rise_continuation_signal(signal, default_config)
    ):
        constructive -= 0.10
    return round(clamp(constructive, 0.0, 1.0), 4)


def _buy_strength_score(signal: BacktestSignal, config: DividendTBacktestConfig) -> float:
    denominator = max(100.0 - config.min_buy_signal_strength, 1.0)
    return clamp((signal.buy_signal_strength - config.min_buy_signal_strength) / denominator, 0.0, 1.0)


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _safe_cache_part(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"_", "-"} else "_" for char in value.strip().lower())
    return cleaned or "profile"


def _trade(
    timestamp: str,
    action: str,
    side: str,
    shares: int,
    price: float,
    cash: float,
    base_shares: int,
    t_shares: int,
    close: float,
    reason: str,
    realized_pnl: float | None,
    *,
    execution_setup_code: str | None = None,
    sizing_trace: DecisionTrace | None = None,
    risk_enforcement: RiskEnforcement = RiskEnforcement.NONE,
) -> DividendTTrade:
    return DividendTTrade(
        timestamp=timestamp,
        action=action,
        side=side,
        shares=shares,
        price=round(price, 3),
        cash_after=round(cash, 2),
        equity_after=round(_mark_to_market(cash, base_shares, t_shares, close), 2),
        reason=reason,
        realized_pnl=round(realized_pnl, 2) if realized_pnl is not None else None,
        execution_setup_code=execution_setup_code,
        risk_enforcement=risk_enforcement.value,
        original_suggested_trade_pct=sizing_trace.original_suggested_trade_pct if sizing_trace else None,
        macd_sizing_multiplier=sizing_trace.macd_sizing_multiplier if sizing_trace else 1.0,
        adjusted_suggested_trade_pct=sizing_trace.adjusted_suggested_trade_pct if sizing_trace else None,
        macd_sizing_applied=sizing_trace.macd_sizing_applied if sizing_trace else False,
        macd_sizing_owner=sizing_trace.macd_sizing_owner if sizing_trace else None,
    )


def _validate_config(config: DividendTBacktestConfig) -> None:
    if config.initial_cash <= 0:
        raise ValueError("initial_cash must be positive")
    if config.t_position_mode not in T_POSITION_MODES:
        raise ValueError(f"t_position_mode must be one of {sorted(T_POSITION_MODES)}")
    if not MIN_BASE_POSITION_PCT <= config.initial_base_position_pct <= MAX_BASE_POSITION_PCT:
        raise ValueError("initial_base_position_pct must be in [0.05, 0.10]")
    if config.strategy_mode not in {"balanced", "defensive", "offensive", "dynamic"}:
        raise ValueError("strategy_mode must be one of: balanced, defensive, offensive, dynamic")
    if not 0 <= config.min_buy_point_quality_score <= 1:
        raise ValueError("min_buy_point_quality_score must be in [0, 1]")
    if not 0 <= config.min_main_rise_buy_quality_score <= 1:
        raise ValueError("min_main_rise_buy_quality_score must be in [0, 1]")
    if not 0 <= config.min_breakout_buy_quality_score <= 1:
        raise ValueError("min_breakout_buy_quality_score must be in [0, 1]")
    if not 0 <= config.min_breakout_buy_main_rise_quality_score <= 1:
        raise ValueError("min_breakout_buy_main_rise_quality_score must be in [0, 1]")
    if not 0 <= config.min_base_rebalance_buy_quality_score <= 1:
        raise ValueError("min_base_rebalance_buy_quality_score must be in [0, 1]")
    if not 0 <= config.min_risk_on_add_quality_score <= 1:
        raise ValueError("min_risk_on_add_quality_score must be in [0, 1]")
    if not 0 <= config.min_risk_on_add_main_rise_quality_score <= 1:
        raise ValueError("min_risk_on_add_main_rise_quality_score must be in [0, 1]")
    if not 0 <= config.sell_point_continuation_quality_score <= 1:
        raise ValueError("sell_point_continuation_quality_score must be in [0, 1]")
    if config.enable_market_filter and not config.market_filter_name.strip():
        raise ValueError("market_filter_name is required when enable_market_filter=True")
    if config.stock_risk_on_hold_bars < 0:
        raise ValueError("stock_risk_on_hold_bars must be non-negative")
    if config.stock_risk_on_sustain_bars < 0:
        raise ValueError("stock_risk_on_sustain_bars must be non-negative")
    if config.stock_risk_on_sustain_bars > config.stock_risk_on_hold_bars:
        raise ValueError("stock_risk_on_sustain_bars must be <= stock_risk_on_hold_bars")
    if not 0 <= config.market_risk_off_passthrough_cap_pct <= config.max_signal_position_pct:
        raise ValueError("market_risk_off_passthrough_cap_pct must be in [0, max_signal_position_pct]")
    if config.risk_on_continuation_min_confirmations < 1:
        raise ValueError("risk_on_continuation_min_confirmations must be positive")
    if not 0 <= config.risk_on_continuation_min_strength <= 100:
        raise ValueError("risk_on_continuation_min_strength must be in [0, 100]")
    if config.risk_on_position_target_min_confirmations < 1:
        raise ValueError("risk_on_position_target_min_confirmations must be positive")
    if not 0 <= config.risk_on_position_target_min_strength <= 100:
        raise ValueError("risk_on_position_target_min_strength must be in [0, 100]")
    if not 0 <= config.risk_on_position_target_min_gap_pct <= 1:
        raise ValueError("risk_on_position_target_min_gap_pct must be in [0, 1]")
    if not config.initial_base_position_pct <= config.risk_on_target_add_min_target_pct <= config.max_signal_position_pct:
        raise ValueError("risk_on_target_add_min_target_pct must be in [initial_base_position_pct, max_signal_position_pct]")
    if not 0 <= config.risk_on_target_add_bonus_pct <= 1:
        raise ValueError("risk_on_target_add_bonus_pct must be in [0, 1]")
    if (
        not config.initial_base_position_pct
        <= config.risk_on_first_add_cap_pct
        <= config.risk_on_low_position_add_cap_pct
        <= config.risk_on_mid_position_add_cap_pct
        <= config.max_signal_position_pct
    ):
        raise ValueError("risk_on staged caps must satisfy base <= first <= low <= mid <= max_signal_position_pct")
    if not config.risk_on_mid_position_add_cap_pct <= config.risk_on_high_position_reinforce_cap_pct <= config.max_signal_position_pct:
        raise ValueError("risk_on_high_position_reinforce_cap_pct must be in [risk_on_mid_position_add_cap_pct, max_signal_position_pct]")
    if not 0 <= config.risk_on_full_add_min_quality_score <= 1:
        raise ValueError("risk_on_full_add_min_quality_score must be in [0, 1]")
    if not 0 <= config.risk_on_full_add_min_main_rise_quality_score <= 1:
        raise ValueError("risk_on_full_add_min_main_rise_quality_score must be in [0, 1]")
    if (
        not config.risk_on_mid_position_add_cap_pct
        <= config.risk_on_high_quality_breakout_upgrade_target_pct
        <= config.max_signal_position_pct
    ):
        raise ValueError(
            "risk_on_high_quality_breakout_upgrade_target_pct must be in [risk_on_mid_position_add_cap_pct, max_signal_position_pct]"
        )
    if not 0 <= config.risk_on_secondary_add_quality_buffer <= 1:
        raise ValueError("risk_on_secondary_add_quality_buffer must be in [0, 1]")
    if not 0 <= config.risk_on_secondary_add_main_rise_quality_buffer <= 1:
        raise ValueError("risk_on_secondary_add_main_rise_quality_buffer must be in [0, 1]")
    for name, score in {
        "risk_on_secondary_add_min_vwap_score": config.risk_on_secondary_add_min_vwap_score,
        "risk_on_secondary_add_min_volume_price_score": config.risk_on_secondary_add_min_volume_price_score,
        "risk_on_secondary_add_min_volume_breakout_score": config.risk_on_secondary_add_min_volume_breakout_score,
        "risk_on_secondary_add_min_volume_persistence_score": config.risk_on_secondary_add_min_volume_persistence_score,
        "risk_on_secondary_add_min_flow_score": config.risk_on_secondary_add_min_flow_score,
        "risk_on_secondary_add_max_sell_pressure_score": config.risk_on_secondary_add_max_sell_pressure_score,
    }.items():
        if not 0 <= score <= 100:
            raise ValueError(f"{name} must be in [0, 100]")
    if not 0 <= config.risk_on_secondary_add_max_down_probability_1d <= 1:
        raise ValueError("risk_on_secondary_add_max_down_probability_1d must be in [0, 1]")
    if not 0 <= config.risk_on_secondary_add_max_down_probability_3d <= 1:
        raise ValueError("risk_on_secondary_add_max_down_probability_3d must be in [0, 1]")
    if config.risk_on_secondary_add_min_confirmations < 1:
        raise ValueError("risk_on_secondary_add_min_confirmations must be positive")
    if config.risk_on_beta_hold_secondary_min_confirmations < 1:
        raise ValueError("risk_on_beta_hold_secondary_min_confirmations must be positive")
    if config.risk_on_add_follow_through_bars < 0:
        raise ValueError("risk_on_add_follow_through_bars must be non-negative")
    if not 0 <= config.risk_on_add_follow_through_min_high_return_pct <= 1:
        raise ValueError("risk_on_add_follow_through_min_high_return_pct must be in [0, 1]")
    if config.risk_on_add_follow_through_volume_ratio < 0:
        raise ValueError("risk_on_add_follow_through_volume_ratio must be non-negative")
    if not 0 <= config.risk_on_add_follow_through_vwap_tolerance_pct <= 1:
        raise ValueError("risk_on_add_follow_through_vwap_tolerance_pct must be in [0, 1]")
    if config.risk_on_add_follow_through_failure_cooldown_bars < 0:
        raise ValueError("risk_on_add_follow_through_failure_cooldown_bars must be non-negative")
    if config.late_stage_recent_high_lookback_bars < 2:
        raise ValueError("late_stage_recent_high_lookback_bars must be >= 2")
    if config.late_stage_stall_lookback_bars < 1:
        raise ValueError("late_stage_stall_lookback_bars must be positive")
    if config.late_stage_max_stall_bars < 1:
        raise ValueError("late_stage_max_stall_bars must be positive")
    if not 0 <= config.late_stage_near_high_pct <= 1:
        raise ValueError("late_stage_near_high_pct must be in [0, 1]")
    if not 0 <= config.late_stage_max_upper_shadow_ratio <= 1:
        raise ValueError("late_stage_max_upper_shadow_ratio must be in [0, 1]")
    if not 0 <= config.late_stage_min_body_progress_ratio <= 1:
        raise ValueError("late_stage_min_body_progress_ratio must be in [0, 1]")
    if not 0 <= config.late_stage_min_range_pct <= 1:
        raise ValueError("late_stage_min_range_pct must be in [0, 1]")
    if (
        not config.initial_base_position_pct
        <= config.risk_on_core_floor_l1_pct
        <= config.risk_on_core_floor_l2_pct
        <= config.risk_on_core_floor_l3_pct
        <= config.max_signal_position_pct
    ):
        raise ValueError("risk_on_core_floor levels must satisfy base <= l1 <= l2 <= l3 <= max_signal_position_pct")
    if not 0 < config.risk_on_core_floor_ramp_step_pct <= 1:
        raise ValueError("risk_on_core_floor_ramp_step_pct must be in (0, 1]")
    if config.volume_price_continuation_lookback_bars < 8:
        raise ValueError("volume_price_continuation_lookback_bars must be >= 8")
    if not 0 <= config.volume_price_continuation_min_return_pct <= 1:
        raise ValueError("volume_price_continuation_min_return_pct must be in [0, 1]")
    if config.volume_price_continuation_max_volume_ratio <= 0:
        raise ValueError("volume_price_continuation_max_volume_ratio must be positive")
    if config.buy_volume_price_short_lookback_bars < 4:
        raise ValueError("buy_volume_price_short_lookback_bars must be >= 4")
    if config.buy_volume_price_mid_lookback_bars < config.buy_volume_price_short_lookback_bars:
        raise ValueError("buy_volume_price_mid_lookback_bars must be >= buy_volume_price_short_lookback_bars")
    if not 0 <= config.buy_volume_price_filter_min_return_pct <= 1:
        raise ValueError("buy_volume_price_filter_min_return_pct must be in [0, 1]")
    if config.buy_volume_price_filter_max_contract_ratio <= 0:
        raise ValueError("buy_volume_price_filter_max_contract_ratio must be positive")
    if not 0 <= config.buy_volume_price_filter_min_quality_score <= 1:
        raise ValueError("buy_volume_price_filter_min_quality_score must be in [0, 1]")
    if not config.risk_on_mid_position_add_cap_pct <= config.portfolio_main_rise_position_target_pct <= config.max_signal_position_pct:
        raise ValueError("portfolio_main_rise_position_target_pct must be in [risk_on_mid_position_add_cap_pct, max_signal_position_pct]")
    if not 0 <= config.portfolio_main_rise_min_model_state_score <= 100:
        raise ValueError("portfolio_main_rise_min_model_state_score must be in [0, 100]")
    for name, value in {
        "portfolio_main_rise_min_holding_win_rate": config.portfolio_main_rise_min_holding_win_rate,
        "portfolio_main_rise_min_profit_spread": config.portfolio_main_rise_min_profit_spread,
        "portfolio_main_rise_min_new_buy_success_rate": config.portfolio_main_rise_min_new_buy_success_rate,
    }.items():
        if not 0 <= value <= 1:
            raise ValueError(f"{name} must be in [0, 1]")
    if config.beta_hold_exit_confirm_bars < 1:
        raise ValueError("beta_hold_exit_confirm_bars must be positive")
    if config.beta_hold_soft_exit_confirm_bars < 1:
        raise ValueError("beta_hold_soft_exit_confirm_bars must be positive")
    if config.beta_hold_distribution_confirm_bars < 1:
        raise ValueError("beta_hold_distribution_confirm_bars must be positive")
    if config.attack_exit_confirm_bars < 1:
        raise ValueError("attack_exit_confirm_bars must be positive")
    if config.attack_distribution_confirm_bars < 1:
        raise ValueError("attack_distribution_confirm_bars must be positive")
    if not 0 <= config.candidate_entry_start_target_pct <= config.candidate_entry_confirm_target_pct <= config.max_signal_position_pct:
        raise ValueError("candidate entry targets must satisfy 0 <= start <= confirm <= max_signal")
    if config.candidate_entry_start_max_bars < 0:
        raise ValueError("candidate_entry_start_max_bars must be non-negative")
    if not 0 <= config.candidate_entry_start_min_market_cap_pct <= config.candidate_entry_start_target_pct:
        raise ValueError("candidate_entry_start_min_market_cap_pct must be in [0, candidate_entry_start_target_pct]")
    if not 0 <= config.candidate_entry_confirm_min_strength <= 100:
        raise ValueError("candidate_entry_confirm_min_strength must be in [0, 100]")
    if config.candidate_entry_confirm_min_confirmations < 1:
        raise ValueError("candidate_entry_confirm_min_confirmations must be positive")
    if not config.initial_base_position_pct <= config.candidate_entry_confirm_probe_target_pct <= config.max_signal_position_pct:
        raise ValueError("candidate_entry_confirm_probe_target_pct must be in [initial_base_position_pct, max_signal_position_pct]")
    if config.candidate_entry_min_hold_bars < 0:
        raise ValueError("candidate_entry_min_hold_bars must be non-negative")
    if not 0 <= config.candidate_entry_hard_stop_loss_pct <= 1:
        raise ValueError("candidate_entry_hard_stop_loss_pct must be in [0, 1]")
    if config.breakout_follow_through_bars < 0:
        raise ValueError("breakout_follow_through_bars must be non-negative")
    if not 0 <= config.breakout_follow_through_min_high_return_pct <= 1:
        raise ValueError("breakout_follow_through_min_high_return_pct must be in [0, 1]")
    if config.breakout_follow_through_volume_ratio < 0:
        raise ValueError("breakout_follow_through_volume_ratio must be non-negative")
    if config.breakout_follow_through_failure_cooldown_bars < 0:
        raise ValueError("breakout_follow_through_failure_cooldown_bars must be non-negative")
    if not 0 <= config.breakout_direct_buy_probe_target_pct <= config.max_signal_position_pct:
        raise ValueError("breakout_direct_buy_probe_target_pct must be in [0, max_signal_position_pct]")
    if not 0 < config.t_trade_pct <= 1.00:
        raise ValueError("t_trade_pct is a legacy default buy total-position cap and must be in (0, 1.00]")
    if config.t_trade_pct < config.initial_base_position_pct:
        raise ValueError("t_trade_pct legacy total-position cap must be >= initial_base_position_pct")
    if not 0 <= config.min_t_trade_pct <= config.t_trade_pct:
        raise ValueError("min_t_trade_pct must be in [0, t_trade_pct]")
    if not MIN_BASE_POSITION_PCT <= config.strong_trend_base_position_pct <= MAX_BASE_POSITION_PCT:
        raise ValueError("strong_trend_base_position_pct must be in [0.05, 0.10]")
    if not MAX_BASE_POSITION_PCT <= config.max_signal_position_pct <= 1.00:
        raise ValueError("max_signal_position_pct must be in [0.10, 1.00]")
    config.default_position_budget.validate(label="default buy position budget")
    if config.initial_base_position_pct + config.min_t_trade_pct > config.default_buy_total_cap_pct:
        raise ValueError("default buy total-position cap must cover initial_base_position_pct + min_t_trade_pct")
    if (
        not 0
        < config.range_signal_position_pct
        <= config.trend_watch_signal_position_pct
        <= config.strong_trend_signal_position_pct
        <= config.max_signal_position_pct
    ):
        raise ValueError("regime signal position caps must satisfy 0 < range <= trend_watch <= strong_trend <= max_signal")
    if (
        not 0
        < config.attack_watch_position_pct
        <= config.attack_confirm_position_pct
        <= config.attack_full_position_pct
        <= config.max_signal_position_pct
    ):
        raise ValueError("attack position caps must satisfy 0 < watch <= confirm <= full <= max_signal")
    if not 0 <= config.attack_watch_min_breakout_score <= config.attack_confirm_min_breakout_score <= 100:
        raise ValueError("attack breakout scores must satisfy 0 <= watch <= confirm <= 100")
    if not 0 <= config.attack_confirm_min_buy_strength <= 100:
        raise ValueError("attack_confirm_min_buy_strength must be in [0, 100]")
    if config.attack_full_confirm_signals <= 0:
        raise ValueError("attack_full_confirm_signals must be positive")
    if config.attack_min_hold_bars < 0:
        raise ValueError("attack_min_hold_bars must be non-negative")
    if config.trend_follow_min_hold_bars < config.attack_min_hold_bars:
        raise ValueError("trend_follow_min_hold_bars must be >= attack_min_hold_bars")
    if not 0 <= config.beta_hold_target_position_pct <= config.max_signal_position_pct:
        raise ValueError("beta_hold_target_position_pct must be in [0, max_signal_position_pct]")
    if config.beta_hold_min_confirmations < 1:
        raise ValueError("beta_hold_min_confirmations must be positive")
    if not 0 <= config.beta_hold_min_strength <= 100:
        raise ValueError("beta_hold_min_strength must be in [0, 100]")
    if config.beta_hold_min_bars < 0:
        raise ValueError("beta_hold_min_bars must be non-negative")
    if not 0 <= config.beta_hold_hard_stop_loss_pct <= 1:
        raise ValueError("beta_hold_hard_stop_loss_pct must be in [0, 1]")
    if (
        not 0
        <= config.beta_hold_soft_exit_sell_fraction
        <= config.beta_hold_soft_stop_sell_fraction
        <= config.beta_hold_distribution_sell_fraction
        <= 1.0
    ):
        raise ValueError("beta hold sell fractions must satisfy 0 <= soft_exit <= soft_stop <= distribution <= 1")
    if config.beta_hold_trailing_pullback_multiplier < 1.0:
        raise ValueError("beta_hold_trailing_pullback_multiplier must be >= 1")
    if (
        not 0
        <= config.beta_hold_trailing_light_sell_fraction
        <= config.beta_hold_trailing_mid_sell_fraction
        <= config.beta_hold_trailing_hard_sell_fraction
        <= 1.0
    ):
        raise ValueError("beta hold trailing sell fractions must satisfy 0 <= light <= mid <= hard <= 1")
    if not 0 <= config.attack_exit_sell_pressure_score <= 100:
        raise ValueError("attack_exit_sell_pressure_score must be in [0, 100]")
    if not 0 <= config.attack_exit_force_ratio <= 2:
        raise ValueError("attack_exit_force_ratio must be in [0, 2]")
    if not 0 <= config.attack_exit_down_probability <= 1:
        raise ValueError("attack_exit_down_probability must be in [0, 1]")
    if not config.attack_exit_sell_pressure_score <= config.attack_hard_exit_sell_pressure_score <= 100:
        raise ValueError("attack_hard_exit_sell_pressure_score must be in [attack_exit_sell_pressure_score, 100]")
    if not config.attack_exit_down_probability <= config.attack_hard_exit_down_probability <= 1:
        raise ValueError("attack_hard_exit_down_probability must be in [attack_exit_down_probability, 1]")
    if not 0 <= config.offensive_soft_exit_sell_fraction <= 1.0:
        raise ValueError("offensive_soft_exit_sell_fraction must be in [0, 1]")
    if not 0 <= config.offensive_soft_stop_sell_fraction <= 1.0:
        raise ValueError("offensive_soft_stop_sell_fraction must be in [0, 1]")
    if not 0 <= config.offensive_stop_hold_loss_pct <= 0.20:
        raise ValueError("offensive_stop_hold_loss_pct must be in [0, 0.20]")
    if not 0 <= config.offensive_trend_add_floor_pct <= config.offensive_full_add_floor_pct <= config.max_signal_position_pct:
        raise ValueError("offensive add floors must satisfy 0 <= trend <= full <= max_signal")
    if (
        not 0
        <= config.offensive_trailing_profit_trigger_pct
        <= config.offensive_trailing_profit_mid_pct
        <= config.offensive_trailing_profit_high_pct
        <= 1.0
    ):
        raise ValueError("offensive trailing profit thresholds must satisfy 0 <= trigger <= mid <= high <= 1")
    if (
        not 0
        <= config.offensive_trailing_pullback_pct
        <= config.offensive_trailing_pullback_mid_pct
        <= config.offensive_trailing_pullback_high_pct
        <= 0.50
    ):
        raise ValueError("offensive trailing pullbacks must satisfy 0 <= base <= mid <= high <= 0.50")
    if (
        not 0
        <= config.offensive_trailing_light_sell_fraction
        <= config.offensive_trailing_mid_sell_fraction
        <= config.offensive_trailing_hard_sell_fraction
        <= 1.0
    ):
        raise ValueError("offensive trailing sell fractions must satisfy 0 <= light <= mid <= hard <= 1")
    if config.offensive_beta_trend_pullback_multiplier < 1.0:
        raise ValueError("offensive_beta_trend_pullback_multiplier must be >= 1")
    if not 0 <= config.offensive_volume_stall_reduce_score <= config.offensive_volume_distribution_hard_stall_score <= 100:
        raise ValueError("offensive volume stall thresholds must satisfy 0 <= reduce <= hard <= 100")
    if not 0 <= config.offensive_price_up_volume_down_reduce_score <= config.offensive_volume_distribution_hard_up_down_score <= 100:
        raise ValueError("offensive price-up-volume-down thresholds must satisfy 0 <= reduce <= hard <= 100")
    if not 0 <= config.offensive_volume_distribution_min_profit_pct <= config.offensive_volume_distribution_min_peak_profit_pct <= 1.0:
        raise ValueError("offensive volume distribution profit thresholds must satisfy 0 <= current <= peak <= 1")
    if not 0 <= config.offensive_volume_distribution_absorption_vwap_score <= 100:
        raise ValueError("offensive_volume_distribution_absorption_vwap_score must be in [0, 100]")
    if not 0 <= config.offensive_volume_distribution_absorption_persistence_score <= 100:
        raise ValueError("offensive_volume_distribution_absorption_persistence_score must be in [0, 100]")
    if config.offensive_volume_distribution_continuation_min_confirmations < 1:
        raise ValueError("offensive_volume_distribution_continuation_min_confirmations must be positive")
    if config.offensive_volume_distribution_reduce_pressure_count < 1:
        raise ValueError("offensive_volume_distribution_reduce_pressure_count must be positive")
    if not 0 <= config.offensive_volume_distribution_low_vwap_score <= 100:
        raise ValueError("offensive_volume_distribution_low_vwap_score must be in [0, 100]")
    if not 0 <= config.offensive_volume_distribution_low_persistence_score <= 100:
        raise ValueError("offensive_volume_distribution_low_persistence_score must be in [0, 100]")
    if not 0 <= config.offensive_volume_distribution_low_flow_score <= 100:
        raise ValueError("offensive_volume_distribution_low_flow_score must be in [0, 100]")
    if not 0 <= config.offensive_volume_distribution_low_force_ratio <= 2:
        raise ValueError("offensive_volume_distribution_low_force_ratio must be in [0, 2]")
    if not 0 <= config.offensive_volume_distribution_low_force_score <= 100:
        raise ValueError("offensive_volume_distribution_low_force_score must be in [0, 100]")
    if not 0 <= config.offensive_volume_distribution_low_volume_price_score <= 100:
        raise ValueError("offensive_volume_distribution_low_volume_price_score must be in [0, 100]")
    if not 0 <= config.offensive_volume_distribution_sell_fraction <= config.offensive_volume_distribution_hard_sell_fraction <= 1.0:
        raise ValueError("offensive volume distribution sell fractions must satisfy 0 <= reduce <= hard <= 1")
    if not 0 <= config.fallback_kelly_fraction <= 0.10:
        raise ValueError("fallback_kelly_fraction must be in [0, 0.10]")
    if not 0 <= config.confirmed_flow_position_bonus_pct <= 0.30:
        raise ValueError("confirmed_flow_position_bonus_pct must be in [0, 0.30]")
    if not 0 < config.base_rebalance_threshold_pct <= 0.10:
        raise ValueError("base_rebalance_threshold_pct must be in (0, 0.10]")
    if not 0 < config.base_rebalance_step_pct <= MAX_BASE_POSITION_PCT:
        raise ValueError("base_rebalance_step_pct must be in (0, 0.10]")
    if config.base_rebalance_cooldown_bars < 0:
        raise ValueError("base_rebalance_cooldown_bars must be non-negative")
    if config.buy_t_failure_cooldown_bars < 0:
        raise ValueError("buy_t_failure_cooldown_bars must be non-negative")
    if config.strong_trend_confirm_signals <= 0:
        raise ValueError("strong_trend_confirm_signals must be positive")
    if config.trend_exit_confirm_signals <= 0:
        raise ValueError("trend_exit_confirm_signals must be positive")
    if config.defensive_confirm_signals <= 0:
        raise ValueError("defensive_confirm_signals must be positive")
    if not 0 < config.kelly_fraction_scale <= 1:
        raise ValueError("kelly_fraction_scale must be in (0, 1]")
    if not 0 <= config.min_buy_signal_strength <= 100:
        raise ValueError("min_buy_signal_strength must be in [0, 100]")
    if config.min_lot <= 0:
        raise ValueError("min_lot must be positive")
    if config.max_history_bars < config.min_lookback_bars:
        raise ValueError("max_history_bars must be greater than or equal to min_lookback_bars")
    if config.signal_step_bars <= 0:
        raise ValueError("signal_step_bars must be positive")
    if config.signal_cache_save_every <= 0:
        raise ValueError("signal_cache_save_every must be positive")
    if not 0 <= config.profit_protect_trigger_pct <= 0.20:
        raise ValueError("profit_protect_trigger_pct must be in [0, 0.20]")
    if not 0 < config.profit_protect_sell_fraction <= 1.0:
        raise ValueError("profit_protect_sell_fraction must be in (0, 1]")
    if config.limit_price_tolerance_bps < 0:
        raise ValueError("limit_price_tolerance_bps must be non-negative")


def _mark_to_market(cash: float, base_shares: int, t_shares: int, close: float) -> float:
    return cash + (base_shares + t_shares) * close


def _buy_price(price: float, config: DividendTBacktestConfig) -> float:
    return price * (1.0 + config.slippage_bps / 10_000.0)


def _sell_price(price: float, config: DividendTBacktestConfig) -> float:
    return price * (1.0 - config.slippage_bps / 10_000.0)


def _buy_cost(price: float, shares: int, config: DividendTBacktestConfig) -> float:
    return price * shares * (1.0 + config.commission_rate)


def _buy_cost_per_share(price: float, config: DividendTBacktestConfig) -> float:
    return price * (1.0 + config.commission_rate)


def _sell_proceeds(price: float, shares: int, config: DividendTBacktestConfig) -> float:
    return price * shares * (1.0 - config.commission_rate - config.stamp_duty_rate)


def _floor_lot(shares: float, lot_size: int) -> int:
    return int(shares // lot_size) * lot_size


def _annualized_return(total_return: float, periods: int, periods_per_year: int) -> float:
    if periods <= 0 or total_return <= -1.0:
        return float("nan")
    return (1.0 + total_return) ** (periods_per_year / periods) - 1.0


def _max_drawdown(equity_values: list[float]) -> float:
    if not equity_values:
        return 0.0
    peak = equity_values[0]
    worst = 0.0
    for equity in equity_values:
        peak = max(peak, equity)
        worst = min(worst, equity / peak - 1.0)
    return worst


def _fmt_pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2%}"


def _fmt_money(value: float | None) -> str:
    return "n/a" if value is None else f"{value:,.2f}"
