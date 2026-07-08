from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtesting.run_top1000_screened_portfolio_backtest import (  # noqa: E402
    CAPTURE_BIAS_RULE_IDS,
    CaptureBiasRuleConstraints,
    CurvePayload,
    RANK_RULE_COLUMNS,
    _breakout_alpha_features,
    _build_return_leakage_attribution,
    _build_train_features,
    _curve_points_with_risk_matched,
    _evaluate_trade_quality,
    _market_filter_start_date,
    _portfolio_metrics,
    _portfolio_weights,
    _position_stats,
    _select_rule_for_window,
    _sell_event_forward_metrics,
    _sell_event_type,
    _summarize_buy_event_study_by,
    _summarize_sell_event_study_by,
    _summarize_volume_price_window_study,
    _trade_type,
    _volume_price_window_features,
)


def test_rank_tier_portfolio_weighting_overweights_top_ranked_symbols() -> None:
    symbols = [f"{index:06d}.SH" for index in range(1, 32)]
    terminal_values = {symbol: 1.0 for symbol in symbols}
    terminal_values[symbols[0]] = 1.20
    terminal_values[symbols[-1]] = 0.80
    curve_map = {
        symbol: CurvePayload(
            symbol=symbol,
            status="ok",
            points=(
                ("2026-01-01 09:35:00", 1.0, 1.0),
                ("2026-01-01 09:40:00", terminal_values[symbol], terminal_values[symbol]),
            ),
        )
        for symbol in symbols
    }

    equal = _portfolio_metrics(curve_map, symbols, weighting="equal")
    rank_tier = _portfolio_metrics(curve_map, symbols, weighting="rank-tier")
    weights = _portfolio_weights(symbols, weighting="rank-tier")

    assert weights[symbols[0]] > weights[symbols[-1]]
    assert abs(equal["strategy_return"]) < 1e-9
    assert rank_tier["strategy_return"] > 0


def test_lifecycle_rank_columns_are_available_for_rule_search() -> None:
    assert RANK_RULE_COLUMNS["beta_hold_share_rank"] == "beta_hold_share_rank"
    assert RANK_RULE_COLUMNS["full_position_share_rank"] == "full_position_share_rank"
    assert RANK_RULE_COLUMNS["hold_lifecycle_rank"] == "hold_lifecycle_rank"
    assert "beta_hold_share_rank" in CAPTURE_BIAS_RULE_IDS
    assert "full_position_share_rank" in CAPTURE_BIAS_RULE_IDS
    assert "hold_lifecycle_rank" in CAPTURE_BIAS_RULE_IDS


def test_curve_points_and_portfolio_metrics_include_risk_matched_hold() -> None:
    points = [
        SimpleNamespace(timestamp="2026-01-01 09:35:00", equity=1000.0, close=10.0, base_shares=10, t_shares=40),
        SimpleNamespace(timestamp="2026-01-01 09:40:00", equity=1010.0, close=11.0, base_shares=10, t_shares=40),
        SimpleNamespace(timestamp="2026-01-01 09:45:00", equity=1005.0, close=10.5, base_shares=10, t_shares=20),
    ]

    curve_points = _curve_points_with_risk_matched(points, initial_cash=1000.0, first_open=10.0)
    metrics = _portfolio_metrics(
        {
            "600000.SH": CurvePayload(
                symbol="600000.SH",
                status="ok",
                points=curve_points,
            )
        },
        ["600000.SH"],
    )

    assert len(curve_points[0]) == 4
    assert abs(metrics["benchmark_return"] - 0.05) < 1e-9
    assert metrics["risk_matched_benchmark_return"] > 0.0
    assert metrics["risk_matched_benchmark_return"] < metrics["benchmark_return"]


def test_market_filter_start_date_uses_nonnegative_lookback() -> None:
    assert _market_filter_start_date(date(2026, 6, 28), lookback_days=120) == date(2026, 2, 28)
    assert _market_filter_start_date(date(2026, 6, 28), lookback_days=-10) == date(2026, 6, 28)


def test_force_rule_selection_prefers_requested_top_n() -> None:
    rules = pd.DataFrame(
        [
            {"rule_id": "strong_beta_score_rank", "top_n": 50, "train_objective": 1.0},
            {"rule_id": "risk_on_position_capture_rank", "top_n": 50, "train_objective": 0.8},
            {"rule_id": "risk_on_position_capture_rank", "top_n": 100, "train_objective": 0.7},
        ]
    )

    selected = _select_rule_for_window(rules, force_rule_id="risk_on_position_capture_rank", preferred_top_n=100)

    assert selected["rule_id"] == "risk_on_position_capture_rank"
    assert selected["top_n"] == 100


def test_capture_bias_rule_selection_prefers_main_rise_capture_over_stable_beta() -> None:
    rules = pd.DataFrame(
        [
            {
                "rule_id": "strong_beta_score_rank",
                "top_n": 100,
                "train_objective": 2.5,
                "train_avg_trend_capture_return": 0.03,
                "train_avg_upside_capture": 0.35,
                "train_positive_rate": 0.45,
                "train_avg_position_pct": 0.50,
                "train_avg_capture_shortfall": 0.12,
                "train_avg_max_drawdown": -0.12,
                "train_avg_stop_per_trade": 1.2,
                "train_avg_early_exit_per_trade": 2.5,
            },
            {
                "rule_id": "main_rise_capture_bias_score_rank",
                "top_n": 100,
                "train_objective": 1.0,
                "train_avg_trend_capture_return": 0.10,
                "train_avg_upside_capture": 0.72,
                "train_avg_main_rise_capture_bias_score": 0.88,
                "train_avg_risk_on_after_10d_position": 0.72,
                "train_positive_rate": 0.60,
                "train_avg_position_pct": 0.68,
                "train_avg_capture_shortfall": 0.04,
                "train_avg_max_drawdown": -0.08,
                "train_avg_stop_per_trade": 0.6,
                "train_avg_early_exit_per_trade": 0.9,
                "train_avg_distribution_risk_density": 8.0,
            },
            {
                "rule_id": "trend_capture_rank",
                "top_n": 100,
                "train_objective": 1.4,
                "train_avg_trend_capture_return": 0.14,
                "train_avg_upside_capture": 0.80,
                "train_avg_main_rise_capture_bias_score": 0.45,
                "train_avg_risk_on_after_10d_position": 0.60,
                "train_positive_rate": 0.62,
                "train_avg_position_pct": 0.65,
                "train_avg_capture_shortfall": 0.05,
                "train_avg_max_drawdown": -0.10,
                "train_avg_stop_per_trade": 0.9,
                "train_avg_early_exit_per_trade": 1.5,
                "train_avg_distribution_risk_density": 10.0,
            },
            {
                "rule_id": "beta_hold_capture_score_rank",
                "top_n": 100,
                "train_objective": 2.0,
                "train_avg_trend_capture_return": 0.08,
                "train_avg_upside_capture": 0.62,
                "train_avg_main_rise_capture_bias_score": 0.52,
                "train_avg_risk_on_after_10d_position": 0.66,
                "train_positive_rate": 0.68,
                "train_avg_position_pct": 0.70,
                "train_avg_capture_shortfall": 0.06,
                "train_avg_max_drawdown": -0.06,
                "train_avg_stop_per_trade": 0.5,
                "train_avg_early_exit_per_trade": 0.7,
                "train_avg_distribution_risk_density": 9.0,
            },
        ]
    )

    selected = _select_rule_for_window(
        rules,
        force_rule_id=None,
        preferred_top_n=100,
        selection_mode="capture-bias",
    )

    assert selected["rule_id"] == "main_rise_capture_bias_score_rank"


def test_capture_bias_rule_selection_respects_strict_rule_pool() -> None:
    rules = pd.DataFrame(
        [
            {
                "rule_id": "trend_capture_rank",
                "top_n": 100,
                "train_objective": 2.5,
                "train_avg_trend_capture_return": 0.20,
                "train_avg_upside_capture": 1.10,
                "train_positive_rate": 0.75,
                "train_avg_position_pct": 0.82,
                "train_avg_capture_shortfall": 0.02,
                "train_avg_max_drawdown": -0.06,
                "train_avg_stop_per_trade": 0.4,
                "train_avg_early_exit_per_trade": 0.5,
            },
            {
                "rule_id": "main_rise_capture_bias_score_rank",
                "top_n": 100,
                "train_objective": 1.0,
                "train_avg_trend_capture_return": 0.10,
                "train_avg_upside_capture": 0.72,
                "train_avg_main_rise_capture_bias_score": 0.88,
                "train_avg_risk_on_after_10d_position": 0.72,
                "train_positive_rate": 0.60,
                "train_avg_position_pct": 0.68,
                "train_avg_capture_shortfall": 0.04,
                "train_avg_max_drawdown": -0.08,
                "train_avg_stop_per_trade": 0.6,
                "train_avg_early_exit_per_trade": 0.9,
                "train_avg_distribution_risk_density": 8.0,
            },
        ]
    )

    selected = _select_rule_for_window(
        rules,
        force_rule_id=None,
        preferred_top_n=100,
        selection_mode="capture-bias",
        capture_bias_rule_ids=frozenset({"main_rise_capture_bias_score_rank"}),
    )

    assert selected["rule_id"] == "main_rise_capture_bias_score_rank"


def test_capture_bias_rule_selection_fails_when_constraints_remove_all_candidates() -> None:
    rules = pd.DataFrame(
        [
            {
                "rule_id": "main_rise_capture_bias_score_rank",
                "top_n": 100,
                "train_objective": 1.0,
                "train_avg_trend_capture_return": 0.10,
                "train_avg_upside_capture": 0.72,
                "train_positive_rate": 0.60,
                "train_avg_position_pct": 0.68,
                "train_avg_capture_shortfall": 0.04,
                "train_avg_max_drawdown": -0.08,
                "train_avg_stop_per_trade": 0.6,
                "train_avg_early_exit_per_trade": 0.9,
            },
        ]
    )

    with pytest.raises(ValueError, match="constraints removed all candidate rules"):
        _select_rule_for_window(
            rules,
            force_rule_id=None,
            preferred_top_n=100,
            selection_mode="capture-bias",
            capture_bias_constraints=CaptureBiasRuleConstraints(min_positive_rate=0.95),
        )


def test_build_train_features_scores_divergence_capture_and_soft_stop_flying_risk() -> None:
    train = pd.DataFrame(
        [
            {
                "symbol": "600001.SH",
                "status": "ok",
                "total_return": 0.12,
                "benchmark_return": 0.16,
                "excess_return": -0.04,
                "max_drawdown": -0.06,
                "trade_count": 10,
                "win_rate": 0.62,
                "buy_signal_count": 10,
                "breakout_signal_count": 5,
                "risk_on_target_add_count": 4,
                "sell_signal_count": 2,
                "stop_signal_count": 1,
                "offensive_mode_count": 80,
                "risk_on_share": 0.80,
                "beta_hold_share": 0.42,
                "risk_on_after_3d_avg_position_pct": 0.74,
                "risk_on_after_5d_avg_position_pct": 0.78,
                "risk_on_after_10d_avg_position_pct": 0.82,
                "strong_confirm_to_exit_avg_bars": 320,
                "beta_hold_episode_avg_bars": 300,
                "avg_total_position_pct": 0.76,
                "max_total_position_pct_realized": 0.96,
                "buy3_count": 4,
                "breakout_confirmed_count": 4,
                "confirmed_flow_count": 5,
                "volume_price_score_avg": 78,
                "volume_breakout_count": 5,
                "vwap_support_count": 5,
                "post_breakout_volume_persistence_count": 5,
                "high_volume_stall_count": 4,
                "price_up_volume_down_count": 4,
                "rows": 1000,
            },
            {
                "symbol": "600002.SH",
                "status": "ok",
                "total_return": 0.02,
                "benchmark_return": 0.20,
                "excess_return": -0.18,
                "max_drawdown": -0.10,
                "trade_count": 10,
                "win_rate": 0.42,
                "buy_signal_count": 12,
                "breakout_signal_count": 5,
                "risk_on_target_add_count": 3,
                "sell_signal_count": 18,
                "stop_signal_count": 8,
                "offensive_mode_count": 60,
                "risk_on_share": 0.80,
                "beta_hold_share": 0.06,
                "risk_on_after_3d_avg_position_pct": 0.24,
                "risk_on_after_5d_avg_position_pct": 0.22,
                "risk_on_after_10d_avg_position_pct": 0.20,
                "strong_confirm_to_exit_avg_bars": 36,
                "beta_hold_episode_avg_bars": 28,
                "avg_total_position_pct": 0.22,
                "max_total_position_pct_realized": 0.45,
                "buy3_count": 3,
                "breakout_confirmed_count": 3,
                "confirmed_flow_count": 3,
                "volume_price_score_avg": 70,
                "volume_breakout_count": 3,
                "vwap_support_count": 2,
                "post_breakout_volume_persistence_count": 2,
                "high_volume_stall_count": 4,
                "price_up_volume_down_count": 4,
                "rows": 1000,
            },
        ]
    )

    features = _build_train_features(train).set_index("symbol")

    assert "volume_divergence_capture" in features.columns
    assert "volume_price_continuation_capture" in features.columns
    assert "risk_on_position_underbuilt" in features.columns
    assert "soft_stop_flying_rate" in features.columns
    assert features.loc["600001.SH", "volume_divergence_capture"] > features.loc["600002.SH", "volume_divergence_capture"]
    assert features.loc["600001.SH", "volume_price_continuation_capture"] > features.loc["600002.SH", "volume_price_continuation_capture"]
    assert features.loc["600001.SH", "risk_on_position_underbuilt"] < features.loc["600002.SH", "risk_on_position_underbuilt"]
    assert features.loc["600001.SH", "soft_stop_flying_rate"] < features.loc["600002.SH", "soft_stop_flying_rate"]
    assert (
        features.loc["600001.SH", "main_rise_capture_resilience_score"]
        > features.loc["600002.SH", "main_rise_capture_resilience_score"]
    )


def test_capture_bias_rule_selection_penalizes_soft_stop_flying_risk() -> None:
    common = {
        "top_n": 100,
        "train_objective": 1.0,
        "train_avg_trend_capture_return": 0.10,
        "train_avg_upside_capture": 0.70,
        "train_avg_main_rise_capture_bias_score": 0.72,
        "train_avg_main_rise_capture_resilience_score": 0.72,
        "train_avg_risk_on_after_10d_position": 0.70,
        "train_positive_rate": 0.58,
        "train_avg_position_pct": 0.68,
        "train_avg_capture_shortfall": 0.05,
        "train_avg_max_drawdown": -0.08,
        "train_avg_stop_per_trade": 0.7,
        "train_avg_early_exit_per_trade": 1.0,
        "train_avg_distribution_risk_density": 8.0,
    }
    rules = pd.DataFrame(
        [
            {
                **common,
                "rule_id": "main_rise_capture_bias_score_rank",
                "train_avg_volume_divergence_capture": 0.78,
                "train_avg_soft_stop_flying_rate": 0.12,
            },
            {
                **common,
                "rule_id": "main_rise_capture_resilience_score_rank",
                "train_avg_volume_divergence_capture": 0.40,
                "train_avg_soft_stop_flying_rate": 0.58,
            },
        ]
    )

    selected = _select_rule_for_window(
        rules,
        force_rule_id=None,
        preferred_top_n=100,
        selection_mode="capture-bias",
    )

    assert selected["rule_id"] == "main_rise_capture_bias_score_rank"


def test_trade_quality_marks_buy_accurate_when_target_precedes_stop() -> None:
    bars = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01 09:30:00", periods=4, freq="5min"),
            "high": [10.0, 10.1, 10.4, 10.5],
            "low": [10.0, 9.95, 10.2, 10.3],
            "close": [10.0, 10.05, 10.35, 10.4],
        }
    )

    quality = _evaluate_trade_quality(
        timestamp="2026-01-01 09:30:00",
        side="BUY_T",
        price=10.0,
        bars=bars,
        horizon_bars=3,
        buy_up_threshold_pct=0.03,
        stop_loss_threshold_pct=0.02,
        sell_drawdown_threshold_pct=0.03,
        sell_fly_threshold_pct=0.03,
    )

    assert quality["buy_accurate"] is True
    assert quality["buy_target_hit_bar"] == 2
    assert quality["stop_loss_hit_bar"] is None


def test_trade_quality_marks_buy_inaccurate_when_stop_precedes_target() -> None:
    bars = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01 09:30:00", periods=4, freq="5min"),
            "high": [10.0, 10.1, 10.4, 10.5],
            "low": [10.0, 9.7, 10.2, 10.3],
            "close": [10.0, 9.8, 10.35, 10.4],
        }
    )

    quality = _evaluate_trade_quality(
        timestamp="2026-01-01 09:30:00",
        side="BUY_T",
        price=10.0,
        bars=bars,
        horizon_bars=3,
        buy_up_threshold_pct=0.03,
        stop_loss_threshold_pct=0.02,
        sell_drawdown_threshold_pct=0.03,
        sell_fly_threshold_pct=0.03,
    )

    assert quality["buy_accurate"] is False
    assert quality["stop_loss_hit_bar"] == 1
    assert quality["buy_target_hit_bar"] == 2


def test_trade_quality_marks_sell_accuracy_and_flying_independently() -> None:
    bars = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01 09:30:00", periods=4, freq="5min"),
            "high": [10.0, 10.1, 10.35, 10.2],
            "low": [10.0, 9.6, 10.1, 9.8],
            "close": [10.0, 9.8, 10.2, 9.9],
        }
    )

    quality = _evaluate_trade_quality(
        timestamp="2026-01-01 09:30:00",
        side="SELL_T",
        price=10.0,
        bars=bars,
        horizon_bars=3,
        buy_up_threshold_pct=0.03,
        stop_loss_threshold_pct=0.02,
        sell_drawdown_threshold_pct=0.03,
        sell_fly_threshold_pct=0.03,
    )

    assert quality["sell_accurate"] is True
    assert quality["sell_flying"] is True
    assert quality["sell_drawdown_hit_bar"] == 1
    assert quality["sell_fly_hit_bar"] == 2


def test_trade_quality_classifies_rebalance_outside_timing_accuracy() -> None:
    assert _trade_type("BUY_BASE_TREND") == "rebalance"
    assert _trade_type("SELL_BASE_REGIME") == "rebalance"
    assert _trade_type("BUY_CANDIDATE_START") == "candidate_start"
    assert _trade_type("BUY_RISK_ON_TARGET") == "buy"
    assert _trade_type("STOP_T") == "sell_exit"


def test_sell_event_metrics_marks_valid_when_drawdown_precedes_rally() -> None:
    future = pd.DataFrame(
        {
            "high": [10.1, 10.4, 10.2],
            "low": [9.6, 10.0, 9.9],
            "close": [9.8, 10.3, 10.0],
        }
    )

    metrics = _sell_event_forward_metrics(
        price=10.0,
        future=future,
        drawdown_threshold_pct=0.03,
        rally_threshold_pct=0.03,
    )

    assert metrics["risk_avoided"] is True
    assert metrics["sell_valid"] is True
    assert metrics["sell_flying"] is True
    assert metrics["sell_drawdown_hit_bar"] == 1
    assert metrics["sell_rally_hit_bar"] == 2


def test_sell_event_metrics_marks_invalid_when_rally_precedes_drawdown() -> None:
    future = pd.DataFrame(
        {
            "high": [10.4, 10.1, 10.0],
            "low": [10.0, 9.6, 9.9],
            "close": [10.3, 9.8, 10.0],
        }
    )

    metrics = _sell_event_forward_metrics(
        price=10.0,
        future=future,
        drawdown_threshold_pct=0.03,
        rally_threshold_pct=0.03,
    )

    assert metrics["risk_avoided"] is False
    assert metrics["sell_valid"] is False
    assert metrics["sell_flying"] is True
    assert metrics["sell_rally_hit_bar"] == 1
    assert metrics["sell_drawdown_hit_bar"] == 2


def test_sell_event_type_prioritizes_explicit_stop_reason_over_beta_state() -> None:
    assert (
        _sell_event_type(
            action="STOP_T_WAIT",
            side="STOP_T",
            reason="offensive 软止损只降主动仓 50%，等待趋势确认",
            attack_state="BETA_HOLD",
        )
        == "soft_stop"
    )
    assert (
        _sell_event_type(
            action="WAIT_DAILY_WEAK",
            side="STOP_T",
            reason="T 仓止损/失效卖出",
            attack_state="BETA_HOLD",
        )
        == "hard_stop"
    )
    assert (
        _sell_event_type(
            action="REDUCE_ATTACK_POSITION",
            side="SELL_ATTACK_REDUCE",
            reason="进攻状态 BETA_HOLD -> INACTIVE，主动仓位降到 10%",
            attack_state="BETA_HOLD",
        )
        == "beta_hold_exit"
    )


def test_sell_event_summary_recommends_disabling_repeated_invalid_sell_reason() -> None:
    sell_events = pd.DataFrame(
        [
            {
                "rank": 1,
                "horizon_bars": 40,
                "sell_event_type": "soft_stop",
                "future_bar_count": 40,
                "end_return_pct": 0.01,
                "max_missed_upside_pct": 0.04,
                "max_avoided_drawdown_pct": 0.01,
                "sell_valid": False,
                "sell_flying": True,
                "risk_avoided": False,
            }
            for _ in range(12)
        ]
    )

    summary = _summarize_sell_event_study_by(sell_events, top_n_values=[100], group_col="sell_event_type")

    assert len(summary) == 1
    row = summary.iloc[0]
    assert row["sell_event_type"] == "soft_stop"
    assert row["sell_event_decision"] == "delete_or_disable"


def test_breakout_alpha_features_classify_high_quality_breakout() -> None:
    point = SimpleNamespace(
        breakout_score=96.0,
        breakout_confirmed=True,
        breakout_state="BREAKOUT_CONFIRMED",
        volume_price_score=84.0,
        volume_breakout_score=82.0,
        post_breakout_volume_persistence_score=80.0,
        vwap_support_score=82.0,
        capital_flow_confirmation_score=84.0,
        capital_flow_confirmation_state="CONFIRMED_INFLOW",
        capital_flow_confidence=0.82,
        force_weighted_score=76.0,
        sell_pressure_score=48.0,
        down_probability_1d=0.48,
        down_probability_3d=0.50,
        high_volume_stall_score=40.0,
        price_up_volume_down_score=42.0,
        buy_signal_strength=88.0,
        chan_score=82.0,
        chan_buy_point_type="buy3",
    )

    features = _breakout_alpha_features(point)

    assert features["breakout_alpha_tier"] == "high_quality_breakout"
    assert features["breakout_confirmation_count"] >= 6
    assert features["breakout_flow_confirmed"]


def test_buy_event_summary_groups_breakout_alpha_tiers() -> None:
    events = pd.DataFrame(
        [
            {
                "rank": 1,
                "horizon_bars": 10,
                "breakout_alpha_tier": "high_quality_breakout",
                "end_return_pct": 0.02,
                "max_favorable_return_pct": 0.04,
                "max_adverse_return_pct": -0.01,
                "target_1pct_hit_bar": 2,
                "target_2pct_hit_bar": 5,
                "target_3pct_hit_bar": 8,
                "drawdown_3pct_hit_bar": None,
                "drawdown_5pct_hit_bar": None,
                "future_bar_count": 10,
            },
            {
                "rank": 2,
                "horizon_bars": 10,
                "breakout_alpha_tier": "weak_follow_breakout",
                "end_return_pct": -0.015,
                "max_favorable_return_pct": 0.006,
                "max_adverse_return_pct": -0.035,
                "target_1pct_hit_bar": None,
                "target_2pct_hit_bar": None,
                "target_3pct_hit_bar": None,
                "drawdown_3pct_hit_bar": 4,
                "drawdown_5pct_hit_bar": None,
                "future_bar_count": 10,
            },
        ]
    )

    summary = _summarize_buy_event_study_by(events, top_n_values=[100], group_col="breakout_alpha_tier")

    tiers = set(summary["breakout_alpha_tier"])
    assert tiers == {"high_quality_breakout", "weak_follow_breakout"}
    high_quality = summary[summary["breakout_alpha_tier"] == "high_quality_breakout"].iloc[0]
    assert high_quality["avg_end_return_pct"] == 0.02
    assert high_quality["win_rate"] == 1.0


def test_volume_price_window_features_use_only_pre_trade_bars() -> None:
    timestamps = pd.date_range("2026-01-01 09:30:00", periods=9, freq="5min")
    bars = pd.DataFrame(
        {
            "timestamp": timestamps.astype(str),
            "open": [10.0, 10.1, 10.2, 10.3, 10.4, 10.6, 10.8, 11.0, 8.0],
            "high": [10.1, 10.2, 10.3, 10.4, 10.5, 10.7, 10.9, 11.1, 8.1],
            "low": [9.9, 10.0, 10.1, 10.2, 10.3, 10.5, 10.7, 10.9, 7.9],
            "close": [10.0, 10.1, 10.2, 10.3, 10.4, 10.6, 10.8, 11.0, 8.0],
            "volume": [100, 100, 100, 100, 200, 230, 260, 290, 1],
        }
    )

    features = _volume_price_window_features(timestamp=str(timestamps[-1]), bars=bars, lookback_bars=4)

    assert features["lookback_bar_count"] == 4
    assert features["price_trend_bucket"] == "strong_up"
    assert features["volume_price_state"] == "price_up_volume_up"
    assert features["volume_ratio_to_prev"] > 1.0


def test_volume_price_window_summary_separates_buy_and_sell_value() -> None:
    study = pd.DataFrame(
        [
            {
                "rank": 1,
                "event_side": "buy",
                "horizon_bars": 20,
                "lookback_bars": 48,
                "volume_price_state": "price_up_volume_up",
                "price_return_pct": 0.02,
                "price_sma_gap_pct": 0.01,
                "price_efficiency": 0.5,
                "price_volatility_pct": 0.01,
                "volume_signal_pct": 0.4,
                "volume_ratio_to_prev": 0.4,
                "price_volume_corr": 0.2,
                "up_bar_share": 0.7,
                "end_return_pct": 0.03,
                "max_favorable_return_pct": 0.05,
                "max_adverse_return_pct": -0.01,
                "target_2pct_hit_bar": 5,
                "drawdown_3pct_hit_bar": None,
            },
            {
                "rank": 2,
                "event_side": "sell_exit",
                "horizon_bars": 20,
                "lookback_bars": 48,
                "volume_price_state": "price_down_volume_up",
                "price_return_pct": -0.02,
                "price_sma_gap_pct": -0.01,
                "price_efficiency": 0.4,
                "price_volatility_pct": 0.012,
                "volume_signal_pct": 0.5,
                "volume_ratio_to_prev": 0.5,
                "price_volume_corr": -0.2,
                "up_bar_share": 0.3,
                "end_return_pct": -0.02,
                "sell_valid": True,
                "sell_flying": False,
                "risk_avoided": True,
                "max_missed_upside_pct": 0.005,
                "max_avoided_drawdown_pct": 0.04,
            },
        ]
    )

    summary = _summarize_volume_price_window_study(study, top_n_values=[100])

    assert set(summary["event_side"]) == {"buy", "sell_exit"}
    buy = summary[summary["event_side"] == "buy"].iloc[0]
    sell = summary[summary["event_side"] == "sell_exit"].iloc[0]
    assert buy["avg_end_return_pct"] == 0.03
    assert buy["target_2pct_rate"] == 1.0
    assert sell["sell_valid_rate"] == 1.0
    assert sell["risk_avoided_rate"] == 1.0


def test_return_leakage_attribution_flags_risk_on_position_underbuilt() -> None:
    valid = pd.DataFrame(
        [
            {
                "window_id": "w1",
                "valid_start": "2025-01-01",
                "valid_end": "2025-02-01",
                "symbol": "600000.SH",
                "name": "浦发银行",
                "industry": "银行",
                "status": "ok",
                "total_return": 0.02,
                "benchmark_return": 0.30,
                "buy_signal_count": 4,
                "breakout_signal_count": 1,
                "sell_signal_count": 1,
                "stop_signal_count": 0,
                "risk_on_share": 0.72,
                "avg_total_position_pct": 0.10,
                "max_total_position_pct_realized": 0.22,
                "avg_active_position_pct": 0.02,
                "max_active_position_pct": 0.08,
                "buy3_count": 1,
                "breakout_confirmed_count": 1,
                "confirmed_flow_count": 1,
                "confirmed_flow_share": 0.20,
                "avg_force_ratio": 0.84,
                "avg_buy_force_ratio": 0.62,
                "force_suppression_count": 4,
                "force_suppression_share": 0.80,
                "volume_price_score_avg": 74.0,
                "volume_breakout_count": 2,
                "low_volume_pullback_count": 0,
                "high_volume_stall_count": 0,
                "price_up_volume_down_count": 0,
                "vwap_support_count": 3,
                "post_breakout_volume_persistence_count": 2,
                "rows": 240,
            }
        ]
    )
    ranked = pd.DataFrame([{"window_id": "w1", "symbol": "600000.SH", "rank": 12, "screen_score": 0.66}])

    attribution = _build_return_leakage_attribution(valid, ranked)

    assert len(attribution) == 1
    row = attribution.iloc[0]
    assert row["primary_leak_reason"] == "risk_on_position_underbuilt"
    assert row["is_risk_on"]
    assert row["has_buy3_or_breakout"]
    assert row["has_funding_confirmation"]
    assert not row["force_ratio_suppressed"]
    assert row["force_ratio_raw_suppressed"]
    assert row["non_force_confirmation_count"] == 4
    assert row["avg_total_position_pct"] == 0.10
    assert row["max_total_position_pct_realized"] == 0.22


def test_return_leakage_attribution_keeps_force_suppression_when_unconfirmed() -> None:
    valid = pd.DataFrame(
        [
            {
                "window_id": "w1",
                "valid_start": "2025-01-01",
                "valid_end": "2025-02-01",
                "symbol": "600000.SH",
                "name": "浦发银行",
                "industry": "银行",
                "status": "ok",
                "total_return": 0.02,
                "benchmark_return": 0.20,
                "buy_signal_count": 3,
                "breakout_signal_count": 0,
                "sell_signal_count": 1,
                "stop_signal_count": 0,
                "risk_on_share": 0.50,
                "avg_total_position_pct": 0.10,
                "max_total_position_pct_realized": 0.22,
                "avg_active_position_pct": 0.02,
                "max_active_position_pct": 0.08,
                "buy3_count": 1,
                "breakout_confirmed_count": 0,
                "confirmed_flow_count": 0,
                "confirmed_flow_share": 0.0,
                "avg_force_ratio": 0.84,
                "avg_buy_force_ratio": 0.62,
                "force_suppression_count": 3,
                "force_suppression_share": 0.80,
                "volume_price_score_avg": 56.0,
                "volume_breakout_count": 0,
                "low_volume_pullback_count": 0,
                "high_volume_stall_count": 0,
                "price_up_volume_down_count": 0,
                "vwap_support_count": 0,
                "post_breakout_volume_persistence_count": 0,
                "rows": 240,
            }
        ]
    )
    ranked = pd.DataFrame([{"window_id": "w1", "symbol": "600000.SH", "rank": 12, "screen_score": 0.66}])

    attribution = _build_return_leakage_attribution(valid, ranked)

    row = attribution.iloc[0]
    assert row["primary_leak_reason"] == "force_ratio_position_suppressed"
    assert row["force_ratio_suppressed"]
    assert row["non_force_confirmation_count"] == 1


def test_return_leakage_attribution_splits_volume_price_secondary_reason() -> None:
    valid = pd.DataFrame(
        [
            {
                "window_id": "w1",
                "valid_start": "2025-01-01",
                "valid_end": "2025-02-01",
                "symbol": "600000.SH",
                "name": "浦发银行",
                "industry": "银行",
                "status": "ok",
                "total_return": 0.02,
                "benchmark_return": 0.25,
                "buy_signal_count": 3,
                "breakout_signal_count": 1,
                "risk_on_target_add_count": 2,
                "sell_signal_count": 1,
                "stop_signal_count": 0,
                "risk_on_share": 0.60,
                "avg_total_position_pct": 0.24,
                "max_total_position_pct_realized": 0.82,
                "avg_active_position_pct": 0.10,
                "max_active_position_pct": 0.60,
                "buy3_count": 1,
                "breakout_confirmed_count": 1,
                "confirmed_flow_count": 1,
                "confirmed_flow_share": 0.20,
                "avg_force_ratio": 1.05,
                "avg_buy_force_ratio": 1.02,
                "force_suppression_count": 0,
                "force_suppression_share": 0.0,
                "volume_price_score_avg": 76.0,
                "volume_breakout_count": 1,
                "low_volume_pullback_count": 0,
                "high_volume_stall_count": 3,
                "price_up_volume_down_count": 2,
                "vwap_support_count": 0,
                "post_breakout_volume_persistence_count": 0,
                "rows": 240,
            }
        ]
    )
    ranked = pd.DataFrame([{"window_id": "w1", "symbol": "600000.SH", "rank": 5, "screen_score": 0.70}])

    attribution = _build_return_leakage_attribution(valid, ranked)

    row = attribution.iloc[0]
    assert row["primary_leak_reason"] == "volume_price_distribution_or_weak_follow"
    assert row["volume_price_secondary_reason"] == "stall_and_price_up_volume_down"
    assert row["risk_on_target_add_count"] == 2
    assert "目标补仓=2" in row["attribution_note"]


def test_train_features_rewards_target_add_density_for_beta_hold_capture() -> None:
    train = pd.DataFrame(
        [
            {
                "symbol": "600000.SH",
                "status": "ok",
                "total_return": 0.08,
                "benchmark_return": 0.10,
                "excess_return": -0.02,
                "max_drawdown": -0.03,
                "trade_count": 8,
                "completed_trades": 4,
                "win_rate": 0.50,
                "buy_signal_count": 3,
                "breakout_signal_count": 1,
                "breakout_watch_count": 0,
                "risk_on_target_add_count": 6,
                "sell_signal_count": 1,
                "stop_signal_count": 1,
                "defensive_mode_count": 20,
                "balanced_mode_count": 20,
                "offensive_mode_count": 60,
                "rows": 1000,
            },
            {
                "symbol": "600001.SH",
                "status": "ok",
                "total_return": 0.08,
                "benchmark_return": 0.10,
                "excess_return": -0.02,
                "max_drawdown": -0.03,
                "trade_count": 8,
                "completed_trades": 4,
                "win_rate": 0.50,
                "buy_signal_count": 3,
                "breakout_signal_count": 1,
                "breakout_watch_count": 0,
                "risk_on_target_add_count": 0,
                "sell_signal_count": 1,
                "stop_signal_count": 1,
                "defensive_mode_count": 20,
                "balanced_mode_count": 20,
                "offensive_mode_count": 60,
                "rows": 1000,
            },
        ]
    )

    features = _build_train_features(train).set_index("symbol")

    assert features.loc["600000.SH", "target_add_density"] > features.loc["600001.SH", "target_add_density"]
    assert features.loc["600000.SH", "target_add_rank"] > features.loc["600001.SH", "target_add_rank"]
    assert features.loc["600000.SH", "beta_hold_capture_score"] > features.loc["600001.SH", "beta_hold_capture_score"]
    assert features.loc["600000.SH", "screen_score"] > features.loc["600001.SH", "screen_score"]


def test_position_stats_tracks_beta_hold_lifecycle() -> None:
    points = [
        SimpleNamespace(
            equity=1000.0,
            close=10.0,
            base_shares=10,
            t_shares=t_shares,
            market_environment_state=market_state,
            attack_state=attack_state,
        )
        for t_shares, market_state, attack_state in [
            (20, "NEUTRAL", "INACTIVE"),
            (70, "RISK_ON", "BETA_HOLD"),
            (90, "RISK_ON", "BETA_HOLD"),
            (80, "RISK_ON", "FULL_ATTACK"),
            (30, "NEUTRAL", "INACTIVE"),
        ]
    ]

    stats = _position_stats(points)

    assert stats["beta_hold_entry_count"] == 1
    assert stats["beta_hold_bar_count"] == 2
    assert stats["full_position_bar_count"] == 1
    assert stats["strong_confirm_episode_count"] == 1
    assert stats["strong_confirm_to_exit_avg_bars"] == 3.0
    assert stats["risk_on_after_1d_avg_position_pct"] == 0.775
