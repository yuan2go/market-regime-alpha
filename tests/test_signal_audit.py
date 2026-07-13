from __future__ import annotations

import pandas as pd
import pytest

from market_regime_alpha.dividend_t.signal_audit import (
    audit_report,
    calibration_report,
    label_candidate_outcomes,
    local_threshold_sensitivity,
    sell_side_gap_report,
)


def test_labels_use_next_executable_open_and_keep_buy_sell_taxonomies_separate() -> None:
    bars = pd.DataFrame(
        [
            {"symbol": "600000.SH", "timestamp": "2026-01-05 10:00:00", "open": 10.0, "high": 10.2, "low": 9.8, "close": 10.0, "suspended": False, "at_limit_up": False, "at_limit_down": False},
            {"symbol": "600000.SH", "timestamp": "2026-01-05 10:05:00", "open": 10.1, "high": 10.5, "low": 10.0, "close": 10.4, "suspended": False, "at_limit_up": False, "at_limit_down": False},
            {"symbol": "600000.SH", "timestamp": "2026-01-05 10:10:00", "open": 10.4, "high": 10.6, "low": 10.2, "close": 10.5, "suspended": False, "at_limit_up": False, "at_limit_down": False},
            {"symbol": "600000.SH", "timestamp": "2026-01-05 10:15:00", "open": 10.5, "high": 10.6, "low": 10.1, "close": 10.2, "suspended": False, "at_limit_up": False, "at_limit_down": False},
        ]
    )
    candidates = pd.DataFrame(
        [
            {"symbol": "600000.SH", "timestamp": "2026-01-05 10:00:00", "action": "BUY_T", "primary_setup_code": "pullback_low_buy", "signal_intent": "MEAN_REVERSION_T", "market_regime": "RANGE", "industry": "bank", "up_probability": 0.70, "stop_price": 9.7},
            {"symbol": "600000.SH", "timestamp": "2026-01-05 10:00:00", "action": "SELL_T", "primary_setup_code": "pressure_sell_t", "signal_intent": "MEAN_REVERSION_T", "market_regime": "RANGE", "industry": "bank", "up_probability": 0.40, "stop_price": None},
        ]
    )

    labels = label_candidate_outcomes(candidates, bars, intraday_horizons=(1, 2), daily_horizons=())

    assert list(labels["entry_time"]) == ["2026-01-05 10:05:00", "2026-01-05 10:05:00"]
    assert labels.loc[0, "entry_price"] == pytest.approx(10.1)
    assert labels.loc[0, "gross_return_bar_1"] == pytest.approx((10.5 / 10.1) - 1.0)
    assert labels.loc[1, "label_taxonomy"] == "HIGH_SELL_T"
    assert labels.loc[0, "label_taxonomy"] == "BUY_ENTRY"
    assert labels.loc[0, "mfe"] > 0.0 and labels.loc[0, "mae"] <= 0.0
    assert labels.loc[0, "cost_adjusted_return_bar_1"] < labels.loc[0, "gross_return_bar_1"]


def test_calibration_and_threshold_sensitivity_are_stratified_and_deterministic() -> None:
    labels = pd.DataFrame(
        [
            {"up_probability": 0.9, "success": 1, "market_regime": "BULL", "symbol_type": "ETF", "force_buy_edge": 72.0, "net_return": 0.03},
            {"up_probability": 0.8, "success": 1, "market_regime": "BULL", "symbol_type": "ETF", "force_buy_edge": 68.0, "net_return": 0.02},
            {"up_probability": 0.2, "success": 0, "market_regime": "RANGE", "symbol_type": "A_SHARE", "force_buy_edge": 52.0, "net_return": -0.01},
            {"up_probability": 0.1, "success": 0, "market_regime": "RANGE", "symbol_type": "A_SHARE", "force_buy_edge": 48.0, "net_return": -0.02},
        ]
    )

    calibration = calibration_report(labels, probability_column="up_probability", outcome_column="success", bins=2)
    assert calibration["brier_score"] == pytest.approx(0.025)
    assert calibration["log_loss"] > 0.0
    assert set(calibration["by_stratum"]) == {"market_regime", "symbol_type"}

    sensitivity = local_threshold_sensitivity(
        labels,
        feature="force_buy_edge",
        thresholds=(50.0, 60.0, 70.0),
        return_column="net_return",
    )
    assert list(sensitivity["threshold"]) == [50.0, 60.0, 70.0]
    assert list(sensitivity["selected_count"]) == [3, 2, 1]


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
