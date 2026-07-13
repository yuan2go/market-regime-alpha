from __future__ import annotations

import pandas as pd
import pytest

from market_regime_alpha.dividend_t.backtest import DividendTBacktestConfig
from market_regime_alpha.dividend_t.signal_audit import (
    CalibrationRequirements,
    DailyHorizonMode,
    ThresholdComparison,
    audit_report,
    calibration_report,
    label_candidate_outcomes,
    local_threshold_neighborhood,
    local_threshold_sensitivity,
    sell_side_gap_report,
)


def test_labels_use_next_executable_open_and_keep_buy_sell_taxonomies_separate() -> None:
    bars = pd.DataFrame(
        [
            {
                "symbol": "600000.SH",
                "timestamp": "2026-01-05 10:00:00",
                "open": 10.0,
                "high": 10.2,
                "low": 9.8,
                "close": 10.0,
                "volume": 1000,
                "prev_close": 10.0,
            },
            {
                "symbol": "600000.SH",
                "timestamp": "2026-01-05 10:05:00",
                "open": 10.1,
                "high": 10.5,
                "low": 10.0,
                "close": 10.4,
                "volume": 1000,
                "prev_close": 10.0,
            },
            {
                "symbol": "600000.SH",
                "timestamp": "2026-01-05 10:10:00",
                "open": 10.4,
                "high": 10.6,
                "low": 10.2,
                "close": 10.5,
                "volume": 1000,
                "prev_close": 10.0,
            },
            {
                "symbol": "600000.SH",
                "timestamp": "2026-01-05 10:15:00",
                "open": 10.5,
                "high": 10.6,
                "low": 10.1,
                "close": 10.2,
                "volume": 1000,
                "prev_close": 10.0,
            },
        ]
    )
    candidates = pd.DataFrame(
        [
            {
                "symbol": "600000.SH",
                "timestamp": "2026-01-05 10:00:00",
                "action": "BUY_T",
                "primary_setup_code": "pullback_low_buy",
                "signal_intent": "MEAN_REVERSION_T",
                "market_regime": "RANGE",
                "industry": "bank",
                "up_probability_bar_1": 0.70,
                "stop_price": 9.7,
                "equity_before": 10000,
                "cash": 10000,
                "suggested_trade_pct": 0.2,
            },
            {
                "symbol": "600000.SH",
                "timestamp": "2026-01-05 10:00:00",
                "action": "SELL_T",
                "primary_setup_code": "pressure_sell_t",
                "signal_intent": "MEAN_REVERSION_T",
                "market_regime": "RANGE",
                "industry": "bank",
                "up_probability_bar_1": 0.40,
                "stop_price": None,
                "equity_before": 10000,
                "cash": 0,
                "suggested_trade_pct": 0.2,
                "t_shares": 300,
                "sellable_qty": 300,
                "buyback_target_price": 10.0,
            },
        ]
    )

    labels = label_candidate_outcomes(candidates, bars, intraday_horizons=(1, 2), daily_horizons=())

    assert list(labels["entry_time"]) == ["2026-01-05 10:05:00", "2026-01-05 10:05:00"]
    assert labels.loc[0, "execution_price"] == pytest.approx(10.10202)
    assert labels.loc[0, "execution_quantity"] == 100
    assert labels.loc[0, "execution_constraint_version"] == "a-share-execution-v1"
    assert labels.loc[0, "gross_return_bar_1"] == pytest.approx((10.5 / 10.10202) - 1.0)
    assert labels.loc[1, "label_taxonomy"] == "HIGH_SELL_T"
    assert labels.loc[0, "label_taxonomy"] == "BUY_ENTRY"
    assert labels.loc[0, "mfe_bar_1"] > 0.0 and labels.loc[0, "mae_bar_1"] <= 0.0
    assert labels.loc[0, "cost_adjusted_return_bar_1"] < labels.loc[0, "gross_return_bar_1"]


def test_calibration_and_threshold_sensitivity_are_stratified_and_deterministic() -> None:
    labels = pd.DataFrame(
        [
            {
                "up_probability_bar_6": 0.9,
                "success_bar_6": 1,
                "market_regime": "BULL",
                "symbol_type": "ETF",
                "force_buy_edge": 72.0,
                "net_return": 0.03,
            },
            {
                "up_probability_bar_6": 0.8,
                "success_bar_6": 1,
                "market_regime": "BULL",
                "symbol_type": "ETF",
                "force_buy_edge": 68.0,
                "net_return": 0.02,
            },
            {
                "up_probability_bar_6": 0.2,
                "success_bar_6": 0,
                "market_regime": "RANGE",
                "symbol_type": "A_SHARE",
                "force_buy_edge": 52.0,
                "net_return": -0.01,
            },
            {
                "up_probability_bar_6": 0.1,
                "success_bar_6": 0,
                "market_regime": "RANGE",
                "symbol_type": "A_SHARE",
                "force_buy_edge": 48.0,
                "net_return": -0.02,
            },
        ]
    )

    calibration = calibration_report(labels, horizon="bar_6", bins=2)
    assert calibration["brier_score"] == pytest.approx(0.025)
    assert calibration["log_loss"] > 0.0
    assert set(calibration["by_stratum"]) == {"market_regime", "symbol_type"}

    sensitivity = local_threshold_sensitivity(
        labels,
        feature="force_buy_edge",
        thresholds=(50.0, 60.0, 70.0),
        return_column="net_return",
        comparison=ThresholdComparison.GREATER_EQUAL,
    )
    assert list(sensitivity["threshold"]) == [50.0, 60.0, 70.0]
    assert list(sensitivity["selected_count"]) == [3, 2, 1]


def test_calibration_low_sample_output_is_display_only_and_local_grid_reports_stability() -> None:
    labels = pd.DataFrame(
        [
            {"up_probability_bar_6": 0.8, "success_bar_6": 1, "market_regime": "BULL", "force_buy_edge": 60.0, "net_return": 0.01},
            {"up_probability_bar_6": 0.2, "success_bar_6": 0, "market_regime": "BULL", "force_buy_edge": 61.0, "net_return": 0.02},
        ]
    )

    calibration = calibration_report(
        labels,
        horizon="bar_6",
        requirements=CalibrationRequirements(minimum_calibration_samples=10, minimum_samples_per_bin=3, minimum_samples_per_stratum=5),
    )
    neighborhood = local_threshold_neighborhood(
        labels,
        feature="force_buy_edge",
        baseline=60.0,
        perturbations=(-1.0, 0.0, 1.0),
        return_column="net_return",
    )

    assert calibration["valid_for_inference"] is False
    assert calibration["display_only_reason"] == "MINIMUM_CALIBRATION_SAMPLES"
    assert all("valid_for_inference" in item for item in calibration["reliability_curve"])
    assert set(neighborhood["threshold"]) == {59.0, 60.0, 61.0}
    assert "neighborhood_stability" in neighborhood.columns


def test_daily_horizon_uses_explicit_trading_calendar_and_each_horizon_has_own_path_metrics() -> None:
    bars = pd.DataFrame(
        [
            {"symbol": "510300.SH", "timestamp": "2026-01-05 14:55", "open": 4.0, "high": 4.0, "low": 4.0, "close": 4.0, "volume": 1000},
            {"symbol": "510300.SH", "timestamp": "2026-01-06 09:35", "open": 4.1, "high": 4.3, "low": 4.05, "close": 4.2, "volume": 1000},
            {"symbol": "510300.SH", "timestamp": "2026-01-08 09:35", "open": 4.2, "high": 4.21, "low": 3.9, "close": 4.0, "volume": 1000},
        ]
    )
    calendar = pd.DataFrame(
        {
            "trade_date": ["2026-01-05", "2026-01-06", "2026-01-08"],
            "session_close": ["2026-01-05 14:55", "2026-01-06 09:35", "2026-01-08 09:35"],
        }
    )
    candidates = pd.DataFrame(
        [
            {
                "symbol": "510300.SH",
                "timestamp": "2026-01-05 14:55",
                "action": "BUY_T",
                "primary_setup_code": "pullback_low_buy",
                "signal_intent": "MEAN_REVERSION_T",
                "equity_before": 10000,
                "cash": 10000,
                "suggested_trade_pct": 0.2,
            }
        ]
    )

    labels = label_candidate_outcomes(candidates, bars, intraday_horizons=(1, 2), daily_horizons=(1, 2), trading_calendar=calendar)

    assert labels.loc[0, "horizon_end_time_day_1"] == "2026-01-08 09:35:00"
    assert labels.loc[0, "horizon_end_time_day_2"] is None
    assert labels.loc[0, "horizon_reason_day_2"] == "HORIZON_OUT_OF_RANGE"
    assert labels.loc[0, "mfe_bar_1"] != labels.loc[0, "mfe_bar_2"]
    assert labels.loc[0, "stop_triggered_day_1"] is None


def test_daily_horizon_distinguishes_market_and_symbol_tradable_days_and_requires_session_close() -> None:
    bars = pd.DataFrame(
        [
            {
                "symbol": "600000.SH",
                "timestamp": "2026-01-05 14:55",
                "open": 10.0,
                "high": 10.0,
                "low": 10.0,
                "close": 10.0,
                "volume": 1000,
            },
            {
                "symbol": "600000.SH",
                "timestamp": "2026-01-05 14:50",
                "open": 10.0,
                "high": 10.0,
                "low": 10.0,
                "close": 10.0,
                "volume": 1000,
            },
            {
                "symbol": "600000.SH",
                "timestamp": "2026-01-07 14:55",
                "open": 10.1,
                "high": 10.2,
                "low": 10.0,
                "close": 10.1,
                "volume": 1000,
            },
        ]
    )
    calendar = pd.DataFrame(
        {
            "trade_date": ["2026-01-05", "2026-01-06", "2026-01-07"],
            "session_close": ["2026-01-05 14:55", "2026-01-06 14:55", "2026-01-07 14:55"],
        }
    )
    candidates = pd.DataFrame(
        [
            {
                "symbol": "600000.SH",
                "timestamp": "2026-01-05 14:50",
                "action": "BUY_T",
                "primary_setup_code": "pullback_low_buy",
                "signal_intent": "MEAN_REVERSION_T",
                "equity_before": 10000,
                "cash": 10000,
                "suggested_trade_pct": 0.2,
            }
        ]
    )

    market = label_candidate_outcomes(candidates, bars, intraday_horizons=(), daily_horizons=(1,), trading_calendar=calendar)
    tradable = label_candidate_outcomes(
        candidates,
        bars,
        intraday_horizons=(),
        daily_horizons=(1,),
        trading_calendar=calendar,
        daily_horizon_mode=DailyHorizonMode.SYMBOL_TRADABLE_DAY,
    )

    assert market.loc[0, "horizon_reason_day_1"] == "HORIZON_BAR_MISSING"
    assert tradable.loc[0, "horizon_end_time_day_1"] == "2026-01-07 14:55:00"


def test_sell_labels_separate_directional_decline_from_completed_t_cycle() -> None:
    bars = pd.DataFrame(
        [
            {
                "symbol": "600000.SH",
                "timestamp": "2026-01-05 10:00",
                "open": 10.0,
                "high": 10.0,
                "low": 10.0,
                "close": 10.0,
                "volume": 1000,
            },
            {"symbol": "600000.SH", "timestamp": "2026-01-05 10:05", "open": 10.0, "high": 10.1, "low": 9.9, "close": 10.0, "volume": 1000},
            {"symbol": "600000.SH", "timestamp": "2026-01-05 10:10", "open": 9.8, "high": 9.9, "low": 9.7, "close": 9.8, "volume": 1000},
        ]
    )
    candidates = pd.DataFrame(
        [
            {
                "symbol": "600000.SH",
                "timestamp": "2026-01-05 10:00",
                "action": "SELL_T",
                "primary_setup_code": "pressure_sell_t",
                "signal_intent": "MEAN_REVERSION_T",
                "equity_before": 10000,
                "cash": 0,
                "suggested_trade_pct": 0.2,
                "t_shares": 300,
                "sellable_qty": 300,
                "buyback_target_price": 9.9,
            }
        ]
    )

    labels = label_candidate_outcomes(
        candidates, bars, intraday_horizons=(1,), daily_horizons=(), execution_config=DividendTBacktestConfig(enable_t_sell=True)
    )

    assert labels.loc[0, "directional_decline_label_bar_1"] == 1
    assert labels.loc[0, "completed_t_cycle_label"] == 1
    assert labels.loc[0, "buyback_execution_quantity"] == labels.loc[0, "execution_quantity"]
    assert labels.loc[0, "buyback_expiry_bars"] == 24
    assert labels.loc[0, "buyback_holding_bars"] == 1
    assert labels.loc[0, "buyback_fill_ratio"] == 1.0
    assert labels.loc[0, "completed_t_cycle_net_pnl"] > 0.0


def test_buyback_cycle_expires_instead_of_scanning_the_rest_of_the_dataset() -> None:
    bars = pd.DataFrame(
        [
            {
                "symbol": "600000.SH",
                "timestamp": "2026-01-05 10:00",
                "open": 10.0,
                "high": 10.0,
                "low": 10.0,
                "close": 10.0,
                "volume": 1000,
            },
            {
                "symbol": "600000.SH",
                "timestamp": "2026-01-05 10:05",
                "open": 10.0,
                "high": 10.1,
                "low": 9.95,
                "close": 10.0,
                "volume": 1000,
            },
            {"symbol": "600000.SH", "timestamp": "2026-01-05 10:10", "open": 9.7, "high": 9.8, "low": 9.7, "close": 9.7, "volume": 1000},
            {"symbol": "600000.SH", "timestamp": "2026-01-05 10:15", "open": 9.5, "high": 9.6, "low": 9.4, "close": 9.5, "volume": 1000},
        ]
    )
    candidate = pd.DataFrame(
        [
            {
                "symbol": "600000.SH",
                "timestamp": "2026-01-05 10:00",
                "action": "SELL_T",
                "primary_setup_code": "pressure_sell_t",
                "signal_intent": "MEAN_REVERSION_T",
                "equity_before": 10000,
                "cash": 0,
                "suggested_trade_pct": 0.2,
                "t_shares": 300,
                "sellable_qty": 300,
                "buyback_target_price": 9.6,
                "buyback_expiry_bars": 1,
            }
        ]
    )

    labels = label_candidate_outcomes(
        candidate, bars, intraday_horizons=(), daily_horizons=(), execution_config=DividendTBacktestConfig(enable_t_sell=True)
    )

    assert labels.loc[0, "completed_t_cycle_label"] is None
    assert labels.loc[0, "completed_t_cycle_reason"] == "BUYBACK_EXPIRED_BARS"


def test_reference_series_must_match_candidate_identity_and_timestamp_exactly() -> None:
    bars = pd.DataFrame(
        [
            {"symbol": "510300.SH", "timestamp": "2026-01-05 10:00", "open": 4.0, "high": 4.0, "low": 4.0, "close": 4.0, "volume": 1000},
            {"symbol": "510300.SH", "timestamp": "2026-01-05 10:05", "open": 4.1, "high": 4.2, "low": 4.1, "close": 4.2, "volume": 1000},
            {"symbol": "510300.SH", "timestamp": "2026-01-05 10:10", "open": 4.2, "high": 4.2, "low": 4.1, "close": 4.1, "volume": 1000},
        ]
    )
    candidates = pd.DataFrame(
        [
            {
                "symbol": "510300.SH",
                "timestamp": "2026-01-05 10:00",
                "action": "BUY_T",
                "primary_setup_code": "pullback_low_buy",
                "signal_intent": "MEAN_REVERSION_T",
                "benchmark_symbol": "000300.SH",
                "industry_id": "ETF",
                "industry_as_of": "2026-01-05",
                "equity_before": 10000,
                "cash": 10000,
                "suggested_trade_pct": 0.2,
            }
        ]
    )
    benchmark = pd.DataFrame([{"symbol": "000300.SH", "timestamp": "2026-01-05 10:00", "close": 4000.0}])

    labels = label_candidate_outcomes(candidates, bars, intraday_horizons=(1,), daily_horizons=(), benchmark_bars=benchmark)

    assert labels.loc[0, "benchmark_excess_return_bar_1"] is None
    assert labels.loc[0, "benchmark_reference_reason_bar_1"] == "REFERENCE_TIMESTAMP_MISSING"


def test_label_execution_uses_t1_and_skips_temporary_market_blocks() -> None:
    bars = pd.DataFrame(
        [
            {
                "symbol": "600000.SH",
                "timestamp": "2026-01-05 10:00",
                "open": 10.0,
                "high": 10.0,
                "low": 10.0,
                "close": 10.0,
                "volume": 1000,
                "prev_close": 10.0,
            },
            {
                "symbol": "600000.SH",
                "timestamp": "2026-01-05 10:05",
                "open": 11.0,
                "high": 11.0,
                "low": 11.0,
                "close": 11.0,
                "volume": 1000,
                "prev_close": 10.0,
            },
            {
                "symbol": "600000.SH",
                "timestamp": "2026-01-05 10:10",
                "open": 10.2,
                "high": 10.3,
                "low": 10.1,
                "close": 10.2,
                "volume": 1000,
                "prev_close": 10.0,
            },
        ]
    )
    candidates = pd.DataFrame(
        [
            {
                "symbol": "600000.SH",
                "timestamp": "2026-01-05 10:00",
                "action": "BUY_T",
                "primary_setup_code": "pullback_low_buy",
                "signal_intent": "MEAN_REVERSION_T",
                "equity_before": 10000,
                "cash": 10000,
                "suggested_trade_pct": 0.2,
            },
            {
                "symbol": "600000.SH",
                "timestamp": "2026-01-05 10:00",
                "action": "SELL_T",
                "primary_setup_code": "pressure_sell_t",
                "signal_intent": "MEAN_REVERSION_T",
                "equity_before": 10000,
                "cash": 0,
                "suggested_trade_pct": 0.2,
                "t_shares": 100,
                "t_locked_shares": 100,
                "sellable_qty": 0,
            },
        ]
    )

    labels = label_candidate_outcomes(candidates, bars, intraday_horizons=(), daily_horizons=())

    assert labels.loc[0, "execution_time"] == "2026-01-05 10:10:00"  # 10:05 is limit-up, so it is skipped
    assert not bool(labels.loc[1, "actual_executable"])
    assert labels.loc[1, "execution_block_reason"] == "T1_LOCK"


def test_threshold_contract_supports_direction_and_rejects_strategy_parameter_filtering() -> None:
    labels = pd.DataFrame({"sell_pressure": [50.0, 60.0, 70.0], "net_return": [0.1, 0.0, -0.1]})

    less_equal = local_threshold_sensitivity(
        labels, feature="sell_pressure", thresholds=(55.0, 65.0), return_column="net_return", comparison=ThresholdComparison.LESS_EQUAL
    )
    between = local_threshold_sensitivity(
        labels, feature="sell_pressure", thresholds=((55.0, 65.0),), return_column="net_return", comparison=ThresholdComparison.BETWEEN
    )

    assert list(less_equal["selected_count"]) == [1, 2]
    assert between.loc[0, "selected_count"] == 1
    with pytest.raises(ValueError, match="FULL_EXPERIMENT"):
        local_threshold_sensitivity(
            labels.assign(macd_score_weight=0.15), feature="macd_score_weight", thresholds=(0.0, 0.15), return_column="net_return"
        )


def test_sell_side_gap_report_does_not_merge_sell_t_and_stop_t_hit_rates() -> None:
    labels = pd.DataFrame(
        [
            {"action": "SELL_T", "label_taxonomy": "HIGH_SELL_T", "success": 1},
            {"action": "STOP_T", "label_taxonomy": "RISK_EXIT", "success": 0, "max_adverse_excursion": -0.12},
        ]
    )

    report = sell_side_gap_report(labels)

    assert report["ordinary_sell_t"]["count"] == 1
    assert report["hard_risk_exit"]["count"] == 1
    assert "directional_hit_rate" not in report["hard_risk_exit"]


def test_audit_report_includes_required_research_strata_when_available() -> None:
    labels = pd.DataFrame(
        [
            {
                "symbol": "510300.SH",
                "primary_setup_code": "trend_follow",
                "signal_intent": "TREND_FOLLOWING",
                "market_regime": "BULL",
                "industry": "ETF",
                "volatility_bucket": "LOW",
                "trend_state": "UPTREND",
                "holding_period_bucket": "DAY_1",
                "label_taxonomy": "BUY_ENTRY",
            }
        ]
    )

    report = audit_report(labels)

    assert report["by_volatility_bucket"] == {"LOW": 1}
    assert report["by_trend_state"] == {"UPTREND": 1}
    assert report["by_holding_period"] == {"DAY_1": 1}
