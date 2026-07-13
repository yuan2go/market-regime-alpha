"""Reproducible MACD calculation and immutable v1 data contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import Any, Sequence, cast


MACD_CONTRACT_VERSION = "macd-data-v1"
MACD_ALGORITHM_VERSION = "macd-v1"
BAR_CONTRACT_VERSION = "closed-bars-a-share-v1"
PRICE_ADJUSTMENT_VERSION = "point-in-time-adjust-v1"
DATA_QUALITY_RULE_VERSION = "macd-data-quality-v1"


class BarInterval(str, Enum):
    DAY_1 = "1d"
    MINUTE_5 = "5m"


class MACDCross(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NONE = "NONE"


class MACDZeroAxis(str, Enum):
    ABOVE = "ABOVE"
    BELOW = "BELOW"
    STRADDLING = "STRADDLING"


class MACDHistogramTrend(str, Enum):
    EXPANDING = "EXPANDING"
    CONTRACTING = "CONTRACTING"
    FLAT = "FLAT"


class MACDDataReason(str, Enum):
    READY = "READY"
    INSUFFICIENT_BARS = "INSUFFICIENT_BARS"
    INVALID_CLOSE = "INVALID_CLOSE"
    EXPECTED_BAR_MISSING = "EXPECTED_BAR_MISSING"
    PRICE_ADJUSTMENT_UNAVAILABLE = "PRICE_ADJUSTMENT_UNAVAILABLE"


class MACDPriceField(str, Enum):
    CLOSE = "close"


class PriceAdjustmentMode(str, Enum):
    POINT_IN_TIME_ADJUSTED = "POINT_IN_TIME_ADJUSTED"


class HistogramToleranceMode(str, Enum):
    ABSOLUTE = "ABSOLUTE"


class MACDConfigError(ValueError):
    """Raised when a MACD configuration violates the v1 contract."""


@dataclass(frozen=True)
class MACDConfig:
    bar_interval: BarInterval
    fast_period: int = 12
    slow_period: int = 26
    signal_period: int = 9
    cross_lookback_bars: int = 3
    closed_bars_only: bool = True
    price_field: MACDPriceField = MACDPriceField.CLOSE
    price_adjustment_mode: PriceAdjustmentMode = PriceAdjustmentMode.POINT_IN_TIME_ADJUSTED
    histogram_tolerance_mode: HistogramToleranceMode = HistogramToleranceMode.ABSOLUTE
    histogram_flat_tolerance: float = 0.0
    algorithm_version: str = MACD_ALGORITHM_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.bar_interval, BarInterval):
            raise MACDConfigError("bar_interval must be 1d or 5m")

        for name in ("fast_period", "slow_period", "signal_period", "cross_lookback_bars"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise MACDConfigError(f"{name} must be a positive integer")

        if self.fast_period >= self.slow_period:
            raise MACDConfigError("fast_period must be less than slow_period")
        if not isinstance(self.closed_bars_only, bool) or not self.closed_bars_only:
            raise MACDConfigError("formal MACD requires closed_bars_only=True")
        if not isinstance(self.price_field, MACDPriceField):
            raise MACDConfigError("price_field must be a MACDPriceField")
        if not isinstance(self.price_adjustment_mode, PriceAdjustmentMode):
            raise MACDConfigError("price_adjustment_mode must be a PriceAdjustmentMode")
        if not isinstance(self.histogram_tolerance_mode, HistogramToleranceMode):
            raise MACDConfigError("histogram_tolerance_mode must be a HistogramToleranceMode")
        tolerance = self.histogram_flat_tolerance
        if isinstance(tolerance, bool) or not isinstance(tolerance, (int, float)) or not math.isfinite(tolerance) or tolerance < 0:
            raise MACDConfigError("histogram_flat_tolerance must be finite and non-negative")
        if not isinstance(self.algorithm_version, str) or not self.algorithm_version.strip():
            raise MACDConfigError("algorithm_version must be non-empty")


@dataclass(frozen=True)
class MACDScoreBreakdown:
    histogram_sign_component: float = 0.0
    zero_axis_component: float = 0.0
    cross_component: float = 0.0
    histogram_trend_component: float = 0.0
    raw_macd_score: float = 50.0
    clamped_macd_score: float = 50.0

    def __post_init__(self) -> None:
        values = (
            self.histogram_sign_component,
            self.zero_axis_component,
            self.cross_component,
            self.histogram_trend_component,
            self.raw_macd_score,
            self.clamped_macd_score,
        )
        if any(not math.isfinite(value) for value in values):
            raise ValueError("MACD score breakdown values must be finite")
        if not 0.0 <= self.clamped_macd_score <= 100.0:
            raise ValueError("clamped MACD score must be in [0, 100]")


@dataclass(frozen=True)
class MACDResult:
    config: MACDConfig
    dif: float | None
    dea: float | None
    histogram: float | None
    histogram_delta: float | None
    histogram_trend: MACDHistogramTrend
    cross: MACDCross
    cross_age: int | None
    zero_axis: MACDZeroAxis
    data_ready: bool
    data_reason: MACDDataReason
    score: float
    score_breakdown: MACDScoreBreakdown
    provisional: bool = False
    last_closed_bar_time: str | None = None
    bar_contract_version: str = BAR_CONTRACT_VERSION
    price_adjustment_version: str = PRICE_ADJUSTMENT_VERSION
    data_quality_rule_version: str = DATA_QUALITY_RULE_VERSION

    def __post_init__(self) -> None:
        self._validate_types()
        if self.data_ready:
            self._validate_ready()
        else:
            self._validate_unready()
        self._validate_cross()

    def _validate_types(self) -> None:
        if not isinstance(self.config, MACDConfig):
            raise ValueError("MACD result requires a MACDConfig")
        if not isinstance(self.data_ready, bool) or not isinstance(self.provisional, bool):
            raise ValueError("MACD readiness and provisional flags must be boolean")
        if not isinstance(self.histogram_trend, MACDHistogramTrend):
            raise ValueError("invalid histogram trend")
        if not isinstance(self.cross, MACDCross):
            raise ValueError("invalid MACD cross")
        if not isinstance(self.zero_axis, MACDZeroAxis):
            raise ValueError("invalid MACD zero axis")
        if not isinstance(self.data_reason, MACDDataReason):
            raise ValueError("invalid MACD data reason")
        if any(
            not isinstance(value, str) or not value.strip()
            for value in (self.bar_contract_version, self.price_adjustment_version, self.data_quality_rule_version)
        ):
            raise ValueError("MACD result versions must be non-empty")

    def _validate_ready(self) -> None:
        if self.data_reason is not MACDDataReason.READY:
            raise ValueError("ready MACD requires READY reason and raw values")
        if self.dif is None or self.dea is None or self.histogram is None:
            raise ValueError("ready MACD requires READY reason and raw values")
        raw_values = (self.dif, self.dea, self.histogram)
        if any(not math.isfinite(value) for value in raw_values):
            raise ValueError("ready MACD raw values must be finite")
        if self.histogram_delta is not None and not math.isfinite(self.histogram_delta):
            raise ValueError("MACD histogram delta must be finite when present")
        if not math.isfinite(self.score) or not 0.0 <= self.score <= 100.0:
            raise ValueError("macd score must be in [0, 100]")
        if self.score != self.score_breakdown.clamped_macd_score:
            raise ValueError("score must match score breakdown")
        if self.zero_axis is not _zero_axis(self.dif, self.dea):
            raise ValueError("zero-axis enum must match unrounded DIF and DEA")

    def _validate_unready(self) -> None:
        if self.data_reason is MACDDataReason.READY:
            raise ValueError("unready MACD cannot use READY reason")
        if self.score != 50.0 or self.cross is not MACDCross.NONE or self.cross_age is not None:
            raise ValueError("unready MACD must use neutral score and cross")
        if any(value is not None for value in (self.dif, self.dea, self.histogram, self.histogram_delta)):
            raise ValueError("unready MACD raw values must be None")
        if self.histogram_trend is not MACDHistogramTrend.FLAT or self.zero_axis is not MACDZeroAxis.STRADDLING:
            raise ValueError("unready MACD must use neutral trend and zero axis")
        if self.score_breakdown != MACDScoreBreakdown():
            raise ValueError("unready MACD must use neutral score breakdown")

    def _validate_cross(self) -> None:
        if self.cross is MACDCross.NONE:
            if self.cross_age is not None:
                raise ValueError("NONE cross cannot have an age")
            return
        if isinstance(self.cross_age, bool) or not isinstance(self.cross_age, int):
            raise ValueError("cross age must lie inside lookback window")
        if not 0 <= self.cross_age < self.config.cross_lookback_bars:
            raise ValueError("cross age must lie inside lookback window")


def ema_recursive(values: Sequence[float], period: int) -> tuple[float, ...]:
    """Return the EMA defined by seed-first, adjust=False recursion."""

    if not values:
        raise ValueError("ema_recursive requires at least one value")
    if isinstance(period, bool) or not isinstance(period, int) or period <= 0:
        raise ValueError("EMA period must be a positive integer")

    numeric_values = tuple(float(value) for value in values)
    if any(not math.isfinite(value) for value in numeric_values):
        raise ValueError("EMA values must be finite")

    alpha = 2.0 / (period + 1.0)
    output = [numeric_values[0]]
    for value in numeric_values[1:]:
        output.append(alpha * value + (1.0 - alpha) * output[-1])
    return tuple(output)


def macd_series(
    values: Sequence[float],
    *,
    fast_period: int,
    slow_period: int,
    signal_period: int,
) -> tuple[tuple[float, ...], tuple[float, ...], tuple[float, ...]]:
    """Calculate full-precision DIF, DEA, and doubled histogram series."""

    if not values:
        raise ValueError("macd_series requires at least one value")
    for period in (fast_period, slow_period, signal_period):
        if isinstance(period, bool) or not isinstance(period, int) or period <= 0:
            raise ValueError("MACD series periods must be positive integers")
    if fast_period >= slow_period:
        raise ValueError("fast_period must be less than slow_period")

    fast = ema_recursive(values, fast_period)
    slow = ema_recursive(values, slow_period)
    dif = tuple(left - right for left, right in zip(fast, slow, strict=True))
    dea = ema_recursive(dif, signal_period)
    histogram = tuple(2.0 * (left - right) for left, right in zip(dif, dea, strict=True))
    return dif, dea, histogram


def neutral_macd_result(config: MACDConfig, reason: MACDDataReason) -> MACDResult:
    """Build the only valid unready/neutral MACD state."""

    if not isinstance(reason, MACDDataReason):
        raise ValueError("neutral MACD reason must be a MACDDataReason")
    if reason is MACDDataReason.READY:
        raise ValueError("neutral MACD reason cannot be READY")
    return MACDResult(
        config=config,
        dif=None,
        dea=None,
        histogram=None,
        histogram_delta=None,
        histogram_trend=MACDHistogramTrend.FLAT,
        cross=MACDCross.NONE,
        cross_age=None,
        zero_axis=MACDZeroAxis.STRADDLING,
        data_ready=False,
        data_reason=reason,
        score=50.0,
        score_breakdown=MACDScoreBreakdown(),
    )


def _coerce_closes(values: Sequence[object]) -> tuple[float, ...] | None:
    output: list[float] = []
    for value in values:
        if isinstance(value, bool):
            return None
        try:
            close = float(cast(Any, value))
        except (OverflowError, TypeError, ValueError):
            return None
        if not math.isfinite(close) or close <= 0.0:
            return None
        output.append(close)
    return tuple(output)


def _zero_axis(dif: float, dea: float) -> MACDZeroAxis:
    if dif > 0.0 and dea > 0.0:
        return MACDZeroAxis.ABOVE
    if dif < 0.0 and dea < 0.0:
        return MACDZeroAxis.BELOW
    return MACDZeroAxis.STRADDLING


def _histogram_trend(previous: float, current: float, tolerance: float) -> MACDHistogramTrend:
    if not math.isfinite(previous) or not math.isfinite(current):
        raise ValueError("histogram values must be finite")
    if not math.isfinite(tolerance) or tolerance < 0.0:
        raise ValueError("histogram tolerance must be finite and non-negative")
    if abs(current) > abs(previous) + tolerance:
        return MACDHistogramTrend.EXPANDING
    if abs(current) < abs(previous) - tolerance:
        return MACDHistogramTrend.CONTRACTING
    return MACDHistogramTrend.FLAT


def _cross_at(dif_series: Sequence[float], dea_series: Sequence[float], index: int) -> MACDCross:
    if dif_series[index] > dea_series[index] and dif_series[index - 1] <= dea_series[index - 1]:
        return MACDCross.BULLISH
    if dif_series[index] < dea_series[index] and dif_series[index - 1] >= dea_series[index - 1]:
        return MACDCross.BEARISH
    return MACDCross.NONE


def _most_recent_true_cross(
    dif_series: Sequence[float],
    dea_series: Sequence[float],
    first_ready_index: int,
    lookback: int,
) -> tuple[MACDCross, int | None]:
    if len(dif_series) != len(dea_series):
        raise ValueError("DIF and DEA series must have equal lengths")
    if isinstance(lookback, bool) or not isinstance(lookback, int) or lookback <= 0:
        raise ValueError("cross lookback must be a positive integer")
    if isinstance(first_ready_index, bool) or not isinstance(first_ready_index, int) or first_ready_index < 0:
        raise ValueError("first ready index must be a non-negative integer")
    if len(dif_series) <= first_ready_index + 1:
        return MACDCross.NONE, None

    latest = len(dif_series) - 1
    for age in range(lookback):
        index = latest - age
        if index <= first_ready_index:
            break
        cross = _cross_at(dif_series, dea_series, index)
        if cross is not MACDCross.NONE:
            return cross, age
    return MACDCross.NONE, None


def _score_macd(
    histogram: float,
    zero_axis: MACDZeroAxis,
    cross: MACDCross,
    cross_age: int | None,
    trend: MACDHistogramTrend,
    lookback: int,
) -> MACDScoreBreakdown:
    if not math.isfinite(histogram):
        raise ValueError("histogram must be finite")
    if isinstance(lookback, bool) or not isinstance(lookback, int) or lookback <= 0:
        raise ValueError("score lookback must be a positive integer")
    if cross is MACDCross.NONE and cross_age is not None:
        raise ValueError("NONE cross cannot have an age")
    if cross is not MACDCross.NONE:
        if isinstance(cross_age, bool) or not isinstance(cross_age, int) or not 0 <= cross_age < lookback:
            raise ValueError("cross age must lie inside lookback window")

    sign_component = 15.0 if histogram > 0.0 else -15.0 if histogram < 0.0 else 0.0
    axis_component = 15.0 if zero_axis is MACDZeroAxis.ABOVE else -15.0 if zero_axis is MACDZeroAxis.BELOW else 0.0
    bonus = 0.0 if cross_age is None else 15.0 * (lookback - cross_age) / lookback
    cross_component = bonus if cross is MACDCross.BULLISH else -bonus if cross is MACDCross.BEARISH else 0.0

    trend_component = 0.0
    if trend is MACDHistogramTrend.EXPANDING:
        trend_component = 5.0 if histogram > 0.0 else -5.0 if histogram < 0.0 else 0.0
    elif trend is MACDHistogramTrend.CONTRACTING:
        trend_component = -5.0 if histogram > 0.0 else 5.0 if histogram < 0.0 else 0.0

    raw = 50.0 + sign_component + axis_component + cross_component + trend_component
    clamped = max(0.0, min(100.0, raw))
    return MACDScoreBreakdown(
        histogram_sign_component=sign_component,
        zero_axis_component=axis_component,
        cross_component=cross_component,
        histogram_trend_component=trend_component,
        raw_macd_score=raw,
        clamped_macd_score=clamped,
    )


def calculate_macd(closes: Sequence[object], config: MACDConfig) -> MACDResult:
    """Calculate a formal MACD result from the complete supplied close history."""

    values = _coerce_closes(closes)
    if values is None:
        return neutral_macd_result(config, MACDDataReason.INVALID_CLOSE)

    minimum_required_bars = config.slow_period + config.signal_period - 1
    if len(values) < minimum_required_bars:
        return neutral_macd_result(config, MACDDataReason.INSUFFICIENT_BARS)

    dif_series, dea_series, histogram_series = macd_series(
        values,
        fast_period=config.fast_period,
        slow_period=config.slow_period,
        signal_period=config.signal_period,
    )
    first_ready_index = minimum_required_bars - 1
    latest_index = len(values) - 1
    dif = dif_series[latest_index]
    dea = dea_series[latest_index]
    histogram = histogram_series[latest_index]
    zero_axis = _zero_axis(dif, dea)

    if latest_index == first_ready_index:
        histogram_delta = None
        histogram_trend = MACDHistogramTrend.FLAT
        cross = MACDCross.NONE
        cross_age = None
    else:
        previous_histogram = histogram_series[latest_index - 1]
        histogram_delta = histogram - previous_histogram
        histogram_trend = _histogram_trend(previous_histogram, histogram, config.histogram_flat_tolerance)
        cross, cross_age = _most_recent_true_cross(
            dif_series,
            dea_series,
            first_ready_index,
            config.cross_lookback_bars,
        )

    score_breakdown = _score_macd(
        histogram,
        zero_axis,
        cross,
        cross_age,
        histogram_trend,
        config.cross_lookback_bars,
    )
    return MACDResult(
        config=config,
        dif=dif,
        dea=dea,
        histogram=histogram,
        histogram_delta=histogram_delta,
        histogram_trend=histogram_trend,
        cross=cross,
        cross_age=cross_age,
        zero_axis=zero_axis,
        data_ready=True,
        data_reason=MACDDataReason.READY,
        score=score_breakdown.clamped_macd_score,
        score_breakdown=score_breakdown,
    )
