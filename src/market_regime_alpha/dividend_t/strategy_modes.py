"""Named strategy profiles for dividend-T backtests."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from market_regime_alpha.dividend_t.backtest import DividendTBacktestConfig


STRATEGY_MODES = ("balanced", "defensive", "offensive", "dynamic")
STATIC_STRATEGY_MODES = ("balanced", "defensive", "offensive")


def apply_strategy_mode(config: "DividendTBacktestConfig", mode: str) -> "DividendTBacktestConfig":
    """Return a config adjusted for a named defensive/offensive profile."""

    normalized = mode.strip().lower()
    if normalized in {"balanced", "dynamic"}:
        return replace(config, strategy_mode=normalized)
    if normalized == "defensive":
        return replace(
            config,
            strategy_mode=normalized,
            t_trade_pct=min(config.t_trade_pct, 0.45),
            max_signal_position_pct=min(config.max_signal_position_pct, 0.45),
            strong_trend_signal_position_pct=min(config.strong_trend_signal_position_pct, 0.35),
            trend_watch_signal_position_pct=min(config.trend_watch_signal_position_pct, 0.25),
            range_signal_position_pct=min(config.range_signal_position_pct, 0.16),
            enable_attack_state_machine=False,
            attack_watch_position_pct=min(config.attack_watch_position_pct, 0.18),
            attack_confirm_position_pct=min(config.attack_confirm_position_pct, 0.30),
            attack_full_position_pct=min(config.attack_full_position_pct, 0.45),
            min_buy_signal_strength=max(config.min_buy_signal_strength, 72.0),
            attack_confirm_min_breakout_score=max(config.attack_confirm_min_breakout_score, 94.0),
            attack_confirm_min_buy_strength=max(config.attack_confirm_min_buy_strength, 76.0),
            kelly_fraction_scale=min(config.kelly_fraction_scale, 0.45),
            confirmed_flow_position_bonus_pct=min(config.confirmed_flow_position_bonus_pct, 0.06),
            profit_protect_trigger_pct=min(config.profit_protect_trigger_pct, 0.008),
        )
    if normalized == "offensive":
        return replace(
            config,
            strategy_mode=normalized,
            t_trade_pct=max(config.t_trade_pct, 1.00),
            max_signal_position_pct=max(config.max_signal_position_pct, 1.00),
            strong_trend_signal_position_pct=max(config.strong_trend_signal_position_pct, 0.95),
            trend_watch_signal_position_pct=max(config.trend_watch_signal_position_pct, 0.65),
            range_signal_position_pct=max(config.range_signal_position_pct, 0.40),
            enable_attack_state_machine=True,
            attack_watch_position_pct=max(config.attack_watch_position_pct, 0.45),
            attack_confirm_position_pct=max(config.attack_confirm_position_pct, 0.85),
            attack_full_position_pct=max(config.attack_full_position_pct, 1.00),
            enable_beta_hold_state=True,
            beta_hold_target_position_pct=max(config.beta_hold_target_position_pct, 1.00),
            beta_hold_min_bars=max(config.beta_hold_min_bars, 720),
            beta_hold_soft_exit_sell_fraction=min(config.beta_hold_soft_exit_sell_fraction, 0.06),
            beta_hold_soft_stop_sell_fraction=min(config.beta_hold_soft_stop_sell_fraction, 0.16),
            beta_hold_distribution_sell_fraction=min(config.beta_hold_distribution_sell_fraction, 0.20),
            beta_hold_trailing_pullback_multiplier=max(config.beta_hold_trailing_pullback_multiplier, 3.00),
            min_buy_signal_strength=min(config.min_buy_signal_strength, 62.0),
            min_main_rise_buy_quality_score=max(config.min_main_rise_buy_quality_score, 0.48),
            min_risk_on_add_main_rise_quality_score=max(config.min_risk_on_add_main_rise_quality_score, 0.60),
            buy_t_failure_cooldown_bars=max(config.buy_t_failure_cooldown_bars, 96),
            attack_confirm_min_breakout_score=min(config.attack_confirm_min_breakout_score, 88.0),
            attack_confirm_min_buy_strength=min(config.attack_confirm_min_buy_strength, 66.0),
            attack_min_hold_bars=max(config.attack_min_hold_bars, 12),
            trend_follow_min_hold_bars=max(config.trend_follow_min_hold_bars, 48),
            attack_exit_sell_pressure_score=max(config.attack_exit_sell_pressure_score, 82.0),
            attack_exit_down_probability=max(config.attack_exit_down_probability, 0.64),
            attack_hard_exit_sell_pressure_score=max(config.attack_hard_exit_sell_pressure_score, 92.0),
            attack_hard_exit_down_probability=max(config.attack_hard_exit_down_probability, 0.72),
            kelly_fraction_scale=max(config.kelly_fraction_scale, 0.80),
            confirmed_flow_position_bonus_pct=max(config.confirmed_flow_position_bonus_pct, 0.25),
            profit_protect_trigger_pct=max(config.profit_protect_trigger_pct, 0.055),
            profit_protect_sell_fraction=min(config.profit_protect_sell_fraction, 0.22),
            offensive_soft_exit_sell_fraction=min(config.offensive_soft_exit_sell_fraction, 0.22),
            offensive_soft_stop_sell_fraction=min(config.offensive_soft_stop_sell_fraction, 0.38),
            offensive_stop_hold_loss_pct=max(config.offensive_stop_hold_loss_pct, 0.045),
            offensive_trend_add_floor_pct=max(config.offensive_trend_add_floor_pct, 0.88),
            offensive_full_add_floor_pct=max(config.offensive_full_add_floor_pct, 0.98),
            offensive_trailing_profit_enabled=True,
            offensive_trailing_profit_trigger_pct=max(config.offensive_trailing_profit_trigger_pct, 0.06),
            offensive_trailing_profit_mid_pct=max(config.offensive_trailing_profit_mid_pct, 0.13),
            offensive_trailing_profit_high_pct=max(config.offensive_trailing_profit_high_pct, 0.22),
            offensive_trailing_pullback_pct=max(config.offensive_trailing_pullback_pct, 0.03),
            offensive_trailing_pullback_mid_pct=max(config.offensive_trailing_pullback_mid_pct, 0.055),
            offensive_trailing_pullback_high_pct=max(config.offensive_trailing_pullback_high_pct, 0.09),
            offensive_trailing_light_sell_fraction=min(config.offensive_trailing_light_sell_fraction, 0.16),
            offensive_trailing_mid_sell_fraction=min(config.offensive_trailing_mid_sell_fraction, 0.30),
            offensive_trailing_hard_sell_fraction=min(config.offensive_trailing_hard_sell_fraction, 0.50),
        )
    raise ValueError(f"unknown strategy mode: {mode}")
