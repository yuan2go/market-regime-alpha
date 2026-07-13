from __future__ import annotations

from dataclasses import replace

import pandas as pd
import pytest

from market_regime_alpha.dividend_t.macd import (
    BAR_CONTRACT_VERSION,
    DATA_QUALITY_RULE_VERSION,
    MACD_ALGORITHM_VERSION,
    MACD_CONTRACT_VERSION,
    PRICE_ADJUSTMENT_VERSION,
    BarInterval,
    HistogramToleranceMode,
    MACDConfig,
    MACDConfigError,
    MACDCross,
    MACDDataReason,
    MACDHistogramTrend,
    MACDPriceField,
    MACDResult,
    MACDScoreBreakdown,
    MACDZeroAxis,
    PriceAdjustmentMode,
    _histogram_trend,
    _most_recent_true_cross,
    _score_macd,
    _zero_axis,
    calculate_macd,
    ema_recursive,
    macd_series,
    neutral_macd_result,
)


def rising_closes(count: int) -> list[float]:
    return [10.0 + index * 0.07 for index in range(count)]


def test_contract_versions_and_default_config_are_explicit() -> None:
    config = MACDConfig(bar_interval=BarInterval.DAY_1)

    assert MACD_CONTRACT_VERSION == "macd-data-v1"
    assert MACD_ALGORITHM_VERSION == "macd-v1"
    assert BAR_CONTRACT_VERSION == "closed-bars-a-share-v1"
    assert PRICE_ADJUSTMENT_VERSION == "point-in-time-adjust-v1"
    assert DATA_QUALITY_RULE_VERSION == "macd-data-quality-v1"
    assert config.closed_bars_only is True
    assert config.price_field is MACDPriceField.CLOSE
    assert config.price_adjustment_mode is PriceAdjustmentMode.POINT_IN_TIME_ADJUSTED
    assert config.histogram_tolerance_mode is HistogramToleranceMode.ABSOLUTE
    assert config.histogram_flat_tolerance == 0.0


@pytest.mark.parametrize(
    ("field", "bad"),
    [
        ("fast_period", True),
        ("fast_period", 0),
        ("slow_period", -1),
        ("signal_period", 1.5),
        ("cross_lookback_bars", False),
    ],
)
def test_macd_rejects_invalid_integer_config(field: str, bad: object) -> None:
    with pytest.raises(MACDConfigError, match=f"{field} must be a positive integer"):
        MACDConfig(bar_interval=BarInterval.DAY_1, **{field: bad})


@pytest.mark.parametrize(
    "overrides",
    [
        {"fast_period": 26},
        {"closed_bars_only": False},
        {"bar_interval": "1d"},
        {"price_field": "close"},
        {"price_adjustment_mode": "POINT_IN_TIME_ADJUSTED"},
        {"histogram_tolerance_mode": "ABSOLUTE"},
        {"histogram_flat_tolerance": -0.01},
        {"histogram_flat_tolerance": float("inf")},
        {"histogram_flat_tolerance": "0.0"},
        {"algorithm_version": ""},
        {"algorithm_version": "   "},
    ],
)
def test_macd_rejects_invalid_nonperiod_config(overrides: dict[str, object]) -> None:
    kwargs: dict[str, object] = {"bar_interval": BarInterval.DAY_1, **overrides}
    with pytest.raises(MACDConfigError):
        MACDConfig(**kwargs)


@pytest.mark.parametrize("bad", [None, float("nan"), float("inf"), float("-inf"), 0.0, -1.0, "bad", True])
def test_any_invalid_historical_close_invalidates_result(bad: object) -> None:
    closes: list[object] = rising_closes(40)
    closes[2] = bad

    result = calculate_macd(closes, MACDConfig(bar_interval=BarInterval.DAY_1))

    assert result.data_ready is False
    assert result.data_reason is MACDDataReason.INVALID_CLOSE
    assert result.dif is None
    assert result.dea is None
    assert result.histogram is None
    assert result.histogram_delta is None
    assert result.histogram_trend is MACDHistogramTrend.FLAT
    assert result.cross is MACDCross.NONE
    assert result.cross_age is None
    assert result.zero_axis is MACDZeroAxis.STRADDLING
    assert result.score == 50.0
    assert result.score_breakdown == MACDScoreBreakdown()


def test_warmup_boundary_33_34_35() -> None:
    config = MACDConfig(bar_interval=BarInterval.DAY_1)

    at_33 = calculate_macd(rising_closes(33), config)
    at_34 = calculate_macd(rising_closes(34), config)
    at_35 = calculate_macd(rising_closes(35), config)

    assert at_33.data_reason is MACDDataReason.INSUFFICIENT_BARS
    assert at_33.dif is None and at_33.dea is None and at_33.histogram is None
    assert at_34.data_ready is True
    assert at_34.data_reason is MACDDataReason.READY
    assert at_34.dif is not None and at_34.dea is not None and at_34.histogram is not None
    assert at_34.zero_axis is MACDZeroAxis.ABOVE
    assert at_34.histogram_delta is None
    assert at_34.histogram_trend is MACDHistogramTrend.FLAT
    assert at_34.cross is MACDCross.NONE
    assert at_34.cross_age is None
    assert at_34.score_breakdown.cross_component == 0.0
    assert at_34.score_breakdown.histogram_trend_component == 0.0
    assert at_35.data_ready is True
    assert at_35.histogram_delta is not None


def test_first_ready_bar_does_not_recognize_pre_warmup_cross() -> None:
    config = MACDConfig(bar_interval=BarInterval.DAY_1)
    closes = [10.0] * 30 + [8.0, 8.5, 9.0, 9.5]

    result = calculate_macd(closes, config)

    assert result.data_ready is True
    assert result.cross is MACDCross.NONE
    assert result.cross_age is None
    assert result.histogram_delta is None


def test_recursive_ema_matches_fixed_recurrence() -> None:
    values = (10.0, 11.0, 13.0)

    assert ema_recursive(values, 3) == pytest.approx((10.0, 10.5, 11.75), rel=0.0, abs=1e-15)


def test_recursive_ema_matches_pandas_adjust_false() -> None:
    closes = rising_closes(50)
    expected = tuple(pd.Series(closes).ewm(span=12, adjust=False).mean())

    actual = ema_recursive(closes, 12)

    assert actual == pytest.approx(expected, rel=1e-12, abs=1e-12)


def test_macd_series_matches_pandas_adjust_false() -> None:
    closes = rising_closes(50)
    pandas_values = pd.Series(closes)
    expected_dif = pandas_values.ewm(span=12, adjust=False).mean() - pandas_values.ewm(span=26, adjust=False).mean()
    expected_dea = expected_dif.ewm(span=9, adjust=False).mean()
    expected_histogram = 2.0 * (expected_dif - expected_dea)

    dif, dea, histogram = macd_series(closes, fast_period=12, slow_period=26, signal_period=9)

    assert dif == pytest.approx(tuple(expected_dif), rel=1e-12, abs=1e-12)
    assert dea == pytest.approx(tuple(expected_dea), rel=1e-12, abs=1e-12)
    assert histogram == pytest.approx(tuple(expected_histogram), rel=1e-12, abs=1e-12)


def test_fixed_close_sequence_matches_golden_macd_values() -> None:
    result = calculate_macd(rising_closes(40), MACDConfig(bar_interval=BarInterval.DAY_1))

    assert result.dif == pytest.approx(0.44707091223128437, rel=0.0, abs=1e-14)
    assert result.dea == pytest.approx(0.4280189018433426, rel=0.0, abs=1e-14)
    assert result.histogram == pytest.approx(0.038104020775883485, rel=0.0, abs=1e-14)


def test_repeated_calculation_is_reproducible() -> None:
    config = MACDConfig(bar_interval=BarInterval.MINUTE_5)
    closes = rising_closes(80)

    assert calculate_macd(closes, config) == calculate_macd(closes, config)


def test_histogram_trend_uses_absolute_magnitude_and_absolute_tolerance() -> None:
    assert _histogram_trend(-0.10, -0.13, 0.01) is MACDHistogramTrend.EXPANDING
    assert _histogram_trend(0.13, 0.10, 0.01) is MACDHistogramTrend.CONTRACTING
    assert _histogram_trend(-0.10, -0.105, 0.01) is MACDHistogramTrend.FLAT
    assert _histogram_trend(0.10, 0.11, 0.01) is MACDHistogramTrend.FLAT


def test_zero_axis_uses_strict_unrounded_values() -> None:
    assert _zero_axis(1e-15, 2e-15) is MACDZeroAxis.ABOVE
    assert _zero_axis(-1e-15, -2e-15) is MACDZeroAxis.BELOW
    assert _zero_axis(0.0, 1.0) is MACDZeroAxis.STRADDLING
    assert _zero_axis(-1.0, 0.0) is MACDZeroAxis.STRADDLING


def test_cross_age_increments_without_refresh_and_expires() -> None:
    dif = (-1.0, 1.0, 1.2, 1.3, 1.4)
    dea = (0.0,) * len(dif)

    observed = [_most_recent_true_cross(dif[:end], dea[:end], 0, 3) for end in range(2, 6)]

    assert observed == [
        (MACDCross.BULLISH, 0),
        (MACDCross.BULLISH, 1),
        (MACDCross.BULLISH, 2),
        (MACDCross.NONE, None),
    ]


def test_cross_window_edges_and_most_recent_direction() -> None:
    dea = (0.0,) * 6

    assert _most_recent_true_cross((-1.0, -1.0, 1.0), dea[:3], 0, 3) == (MACDCross.BULLISH, 0)
    assert _most_recent_true_cross((-1.0, -1.0, 1.0, 1.0, 1.0), dea[:5], 0, 3) == (MACDCross.BULLISH, 2)
    assert _most_recent_true_cross((-1.0, -1.0, 1.0, 1.0, 1.0, 1.0), dea, 0, 3) == (MACDCross.NONE, None)
    assert _most_recent_true_cross((-1.0, 1.0, 1.0, -1.0, -1.0), dea[:5], 0, 4) == (MACDCross.BEARISH, 1)


def test_cross_requires_a_real_strict_transition_but_allows_previous_equality() -> None:
    dea = (0.0, 0.0, 0.0)

    assert _most_recent_true_cross((0.0, 1.0), dea[:2], 0, 3) == (MACDCross.BULLISH, 0)
    assert _most_recent_true_cross((0.0, -1.0), dea[:2], 0, 3) == (MACDCross.BEARISH, 0)
    assert _most_recent_true_cross((1.0, 1.0, 1.0), dea, 0, 3) == (MACDCross.NONE, None)


def test_zero_histogram_and_neutral_states_score_exactly_50() -> None:
    breakdown = _score_macd(0.0, MACDZeroAxis.STRADDLING, MACDCross.NONE, None, MACDHistogramTrend.FLAT, 3)

    assert breakdown == MACDScoreBreakdown(raw_macd_score=50.0, clamped_macd_score=50.0)


def test_score_breakdown_reports_each_bullish_component() -> None:
    breakdown = _score_macd(0.2, MACDZeroAxis.ABOVE, MACDCross.BULLISH, 1, MACDHistogramTrend.EXPANDING, 3)

    assert breakdown == MACDScoreBreakdown(
        histogram_sign_component=15.0,
        zero_axis_component=15.0,
        cross_component=10.0,
        histogram_trend_component=5.0,
        raw_macd_score=95.0,
        clamped_macd_score=95.0,
    )


def test_score_clamps_extreme_component_total() -> None:
    bullish = _score_macd(0.2, MACDZeroAxis.ABOVE, MACDCross.BULLISH, 0, MACDHistogramTrend.EXPANDING, 1)
    bearish = _score_macd(-0.2, MACDZeroAxis.BELOW, MACDCross.BEARISH, 0, MACDHistogramTrend.EXPANDING, 1)

    assert bullish.raw_macd_score == 100.0
    assert bullish.clamped_macd_score == 100.0
    assert bearish.raw_macd_score == 0.0
    assert bearish.clamped_macd_score == 0.0


def test_display_rounding_is_downstream_of_cross_and_score() -> None:
    result = calculate_macd(rising_closes(40), MACDConfig(bar_interval=BarInterval.DAY_1))
    display_payload = {
        "dif": round(float(result.dif), 4),
        "dea": round(float(result.dea), 4),
        "histogram": round(float(result.histogram), 4),
        "score": round(result.score, 1),
    }

    assert display_payload["dif"] != result.dif
    assert result.cross is MACDCross.NONE
    assert result.score == result.score_breakdown.clamped_macd_score


def test_neutral_result_rejects_ready_reason() -> None:
    with pytest.raises(ValueError, match="neutral MACD reason cannot be READY"):
        neutral_macd_result(MACDConfig(bar_interval=BarInterval.DAY_1), MACDDataReason.READY)


def test_result_invariants_reject_inconsistent_cross_age() -> None:
    ready = calculate_macd(rising_closes(40), MACDConfig(bar_interval=BarInterval.DAY_1))

    with pytest.raises(ValueError, match="NONE cross cannot have an age"):
        replace(ready, cross_age=0)


def test_result_invariants_reject_inconsistent_score_breakdown() -> None:
    ready = calculate_macd(rising_closes(40), MACDConfig(bar_interval=BarInterval.DAY_1))

    with pytest.raises(ValueError, match="score must match score breakdown"):
        replace(ready, score=ready.score - 1.0)


def test_result_metadata_defaults_are_versioned_and_formal() -> None:
    result: MACDResult = calculate_macd(rising_closes(40), MACDConfig(bar_interval=BarInterval.DAY_1))

    assert result.provisional is False
    assert result.last_closed_bar_time is None
    assert result.bar_contract_version == BAR_CONTRACT_VERSION
    assert result.price_adjustment_version == PRICE_ADJUSTMENT_VERSION
    assert result.data_quality_rule_version == DATA_QUALITY_RULE_VERSION
