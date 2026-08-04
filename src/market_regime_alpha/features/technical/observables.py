"""Pure Decimal reference implementations of canonical technical observables."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from enum import Enum
from typing import Callable, TypeAlias
from zoneinfo import ZoneInfo

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import require_sha256, require_text
from market_regime_alpha.features.spine import FeatureConfiguration
from market_regime_alpha.features.technical.catalog import (
    CAPITAL_VOLUME_FEATURE_ID,
    MACD_DECIMAL_OUTPUTS,
    MACD_FEATURE_ID,
    MACD_TEXT_OUTPUTS,
    MOVING_AVERAGE_DECIMAL_OUTPUTS,
    MOVING_AVERAGE_FEATURE_ID,
    MOVING_AVERAGE_TEXT_OUTPUTS,
    OVERHEAT_FEATURE_ID,
    OVERHEAT_OUTPUTS,
    PRICE_ACTION_FEATURE_ID,
    PRICE_ACTION_OUTPUTS,
    VOLUME_DECIMAL_OUTPUTS,
    VOLUME_TEXT_OUTPUTS,
    VWAP_DECIMAL_OUTPUTS,
    VWAP_FEATURE_ID,
    VWAP_TEXT_OUTPUTS,
)
from market_regime_alpha.market_data import CanonicalMarketBar, Timeframe, TradingStatus
from market_regime_alpha.market_data.contracts import require_utc_second


FeatureScalar: TypeAlias = Decimal | int | str
_SHANGHAI = ZoneInfo("Asia/Shanghai")


class FeatureValueState(str, Enum):
    AVAILABLE = "AVAILABLE"
    MISSING = "MISSING"


@dataclass(frozen=True, slots=True)
class TechnicalFeatureValue:
    output_id: str
    state: FeatureValueState
    value: FeatureScalar | None
    available_at: datetime
    source_bar_ids: tuple[ArtifactId, ...]
    source_bar_hashes: tuple[str, ...]
    missing_reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        require_text("output_id", self.output_id)
        require_utc_second("available_at", self.available_at)
        if len(self.source_bar_ids) != len(self.source_bar_hashes):
            raise ValueError("source bar identities and hashes must align")
        if len(self.source_bar_ids) != len(set(self.source_bar_ids)):
            raise ValueError("source bar identities must be unique")
        for item_hash in self.source_bar_hashes:
            require_sha256("source_bar_hash", item_hash)
        if self.missing_reason_codes != tuple(sorted(set(self.missing_reason_codes))):
            raise ValueError("missing reason codes must be unique and sorted")
        if self.state is FeatureValueState.AVAILABLE:
            if self.value is None or self.missing_reason_codes:
                raise ValueError("AVAILABLE feature value cannot be missing")
        elif self.value is not None or not self.missing_reason_codes:
            raise ValueError("MISSING feature value requires reasons and no value")


@dataclass(frozen=True, slots=True)
class TechnicalFeatureComputation:
    feature_id: str
    symbol: str
    timeframe: Timeframe
    available_at: datetime
    configuration_id: ArtifactId
    configuration_hash: str
    values: tuple[TechnicalFeatureValue, ...]
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        require_text("feature_id", self.feature_id)
        require_text("symbol", self.symbol)
        require_utc_second("available_at", self.available_at)
        require_sha256("configuration_hash", self.configuration_hash)
        output_ids = tuple(item.output_id for item in self.values)
        if not output_ids or output_ids != tuple(sorted(set(output_ids))):
            raise ValueError("computed feature outputs must be non-empty, unique, and sorted")
        if self.limitations != tuple(sorted(set(self.limitations))):
            raise ValueError("limitations must be unique and sorted")


def compute_technical_feature(
    *,
    feature_id: str,
    bars: tuple[CanonicalMarketBar, ...],
    configuration: FeatureConfiguration,
    decision_time: datetime,
) -> TechnicalFeatureComputation:
    configuration.verify_identity()
    require_utc_second("decision_time", decision_time)
    if configuration.feature_id != feature_id:
        raise ValueError("Feature Configuration does not match requested feature")
    if configuration.effective_from > decision_time:
        raise ValueError("Feature Configuration is not effective at DecisionTime")
    ordered = _validate_bars(bars=bars, decision_time=decision_time)
    dispatch: dict[
        str,
        Callable[
            [tuple[CanonicalMarketBar, ...], FeatureConfiguration, datetime],
            TechnicalFeatureComputation,
        ],
    ] = {
        PRICE_ACTION_FEATURE_ID: _compute_price_action,
        MOVING_AVERAGE_FEATURE_ID: _compute_moving_average,
        MACD_FEATURE_ID: _compute_macd,
        CAPITAL_VOLUME_FEATURE_ID: _compute_volume,
        VWAP_FEATURE_ID: _compute_vwap,
        OVERHEAT_FEATURE_ID: _compute_overheat,
    }
    try:
        computer = dispatch[feature_id]
    except KeyError as exc:
        raise ValueError(f"unsupported technical feature: {feature_id}") from exc
    with localcontext() as context:
        context.prec = 50
        context.rounding = ROUND_HALF_EVEN
        return computer(ordered, configuration, decision_time)


def _compute_price_action(
    bars: tuple[CanonicalMarketBar, ...],
    configuration: FeatureConfiguration,
    decision_time: datetime,
) -> TechnicalFeatureComputation:
    output_ids = PRICE_ACTION_OUTPUTS
    unsupported = _unsupported_or_suspended(
        feature_id=PRICE_ACTION_FEATURE_ID,
        bars=bars,
        configuration=configuration,
        supported={Timeframe.DAILY, Timeframe.MINUTE_5},
        output_ids=output_ids,
    )
    if unsupported is not None:
        return unsupported
    scale = _scale(configuration)
    latest = bars[-1]
    values: list[TechnicalFeatureValue] = []
    for window in (1, 3, 5, 10):
        output_id = f"return_{window}"
        if len(bars) <= window:
            values.append(_missing(output_id, bars, "WINDOW_NOT_READY"))
        else:
            values.append(
                _available(
                    output_id,
                    _q(latest.close / bars[-window - 1].close - Decimal("1"), scale),
                    (bars[-window - 1], latest),
                )
            )
    decision_date = decision_time.astimezone(_SHANGHAI).date()
    if latest.market_date != decision_date:
        values.append(
            _missing(
                "intraday_return_to_decision_time",
                (latest,),
                "DECISION_SESSION_DATA_NOT_AVAILABLE",
            )
        )
    else:
        values.append(
            _available(
                "intraday_return_to_decision_time",
                _q(latest.close / latest.open - Decimal("1"), scale),
                (latest,),
            )
        )
    if latest.previous_close is None:
        values.extend(
            (
                _missing("gap_return", (latest,), "FIELD_UNAVAILABLE_PREVIOUS_CLOSE"),
                _missing("high_low_range", (latest,), "FIELD_UNAVAILABLE_PREVIOUS_CLOSE"),
            )
        )
    else:
        values.extend(
            (
                _available(
                    "gap_return",
                    _q(latest.open / latest.previous_close - Decimal("1"), scale),
                    (latest,),
                ),
                _available(
                    "high_low_range",
                    _q((latest.high - latest.low) / latest.previous_close, scale),
                    (latest,),
                ),
            )
        )
    price_range = latest.high - latest.low
    if price_range == 0:
        values.append(_missing("close_location_value", (latest,), "ZERO_PRICE_RANGE"))
    else:
        close_location = (
            (latest.close - latest.low) - (latest.high - latest.close)
        ) / price_range
        values.append(
            _available("close_location_value", _q(close_location, scale), (latest,))
        )
    return _result(PRICE_ACTION_FEATURE_ID, bars, configuration, values)


def _compute_moving_average(
    bars: tuple[CanonicalMarketBar, ...],
    configuration: FeatureConfiguration,
    decision_time: datetime,
) -> TechnicalFeatureComputation:
    del decision_time
    output_ids = (*MOVING_AVERAGE_DECIMAL_OUTPUTS, *MOVING_AVERAGE_TEXT_OUTPUTS)
    unsupported = _unsupported_or_suspended(
        feature_id=MOVING_AVERAGE_FEATURE_ID,
        bars=bars,
        configuration=configuration,
        supported={Timeframe.DAILY},
        output_ids=output_ids,
    )
    if unsupported is not None:
        return unsupported
    parameters = _parameters(
        configuration,
        {"ema_periods", "ema_seed", "output_scale", "rounding", "sma_periods"},
    )
    if parameters["ema_seed"] != "FIRST_OBSERVATION_RECURSIVE":
        raise ValueError("unsupported EMA initialization policy")
    scale = int(parameters["output_scale"])
    closes = tuple(item.close for item in bars)
    values: list[TechnicalFeatureValue] = []
    sma_series: dict[int, tuple[Decimal | None, ...]] = {}
    for period in (5, 10, 20, 60):
        series = _sma_series(closes, period)
        sma_series[period] = series
        values.append(
            _series_value(f"sma_{period}", series, bars, period, scale)
        )
    ema_series: dict[int, tuple[Decimal, ...]] = {}
    for period in (5, 10, 12, 20, 26, 60):
        series = _ema_series(closes, period)
        ema_series[period] = series
        if len(bars) < period:
            values.append(_missing(f"ema_{period}", bars, "WINDOW_NOT_READY"))
        else:
            values.append(_available(f"ema_{period}", _q(series[-1], scale), bars))
    for period in (5, 10, 20):
        current = sma_series[period][-1]
        if current is None:
            values.append(
                _missing(f"price_vs_sma{period}_return", bars, "WINDOW_NOT_READY")
            )
        else:
            values.append(
                _available(
                    f"price_vs_sma{period}_return",
                    _q(closes[-1] / current - Decimal("1"), scale),
                    bars[-period:],
                )
            )
    if len(bars) < 20:
        values.append(_missing("price_vs_ema20_return", bars, "WINDOW_NOT_READY"))
    else:
        values.append(
            _available(
                "price_vs_ema20_return",
                _q(closes[-1] / ema_series[20][-1] - Decimal("1"), scale),
                bars,
            )
        )
    for period in (5, 20, 60):
        current = sma_series[period][-1]
        previous = sma_series[period][-2] if len(bars) >= 2 else None
        if current is None or previous is None:
            values.append(_missing(f"ma_slope_{period}", bars, "WINDOW_NOT_READY"))
        else:
            values.append(
                _available(
                    f"ma_slope_{period}",
                    _q(current / previous - Decimal("1"), scale),
                    bars[-period - 1 :],
                )
            )
    current_smas = tuple(sma_series[period][-1] for period in (5, 10, 20, 60))
    if any(item is None for item in current_smas):
        values.append(_missing("ma_alignment", bars, "WINDOW_NOT_READY"))
    else:
        sma5, sma10, sma20, sma60 = current_smas
        assert sma5 is not None and sma10 is not None and sma20 is not None and sma60 is not None
        alignment = (
            "BULLISH"
            if sma5 > sma10 > sma20 > sma60
            else "BEARISH"
            if sma5 < sma10 < sma20 < sma60
            else "MIXED"
        )
        values.append(_available("ma_alignment", alignment, bars[-60:]))
    if len(bars) < 21:
        values.append(_missing("short_ma_cross_state", bars, "WINDOW_NOT_READY"))
    else:
        short_now = sma_series[5][-1]
        long_now = sma_series[20][-1]
        short_before = sma_series[5][-2]
        long_before = sma_series[20][-2]
        assert None not in {short_now, long_now, short_before, long_before}
        cross = (
            "CROSS_UP"
            if short_before <= long_before and short_now > long_now  # type: ignore[operator]
            else "CROSS_DOWN"
            if short_before >= long_before and short_now < long_now  # type: ignore[operator]
            else "NONE"
        )
        values.append(_available("short_ma_cross_state", cross, bars[-21:]))
    _append_distance(
        values,
        output_id="distance_sma5_sma20",
        first=sma_series[5][-1],
        second=sma_series[20][-1],
        bars=bars,
        scale=scale,
    )
    if len(bars) < 26:
        values.append(_missing("distance_ema12_ema26", bars, "WINDOW_NOT_READY"))
    else:
        values.append(
            _available(
                "distance_ema12_ema26",
                _q(ema_series[12][-1] / ema_series[26][-1] - Decimal("1"), scale),
                bars,
            )
        )
    return _result(MOVING_AVERAGE_FEATURE_ID, bars, configuration, values)


def _compute_macd(
    bars: tuple[CanonicalMarketBar, ...],
    configuration: FeatureConfiguration,
    decision_time: datetime,
) -> TechnicalFeatureComputation:
    del decision_time
    output_ids = (
        *MACD_DECIMAL_OUTPUTS,
        "histogram_consecutive_direction",
        *MACD_TEXT_OUTPUTS,
    )
    unsupported = _unsupported_or_suspended(
        feature_id=MACD_FEATURE_ID,
        bars=bars,
        configuration=configuration,
        supported={Timeframe.DAILY},
        output_ids=output_ids,
    )
    if unsupported is not None:
        return unsupported
    parameters = _parameters(
        configuration,
        {
            "divergence_lookback",
            "ema_seed",
            "fast_period",
            "histogram_multiplier",
            "output_scale",
            "rounding",
            "signal_period",
            "slow_period",
            "warmup_observations",
        },
    )
    if parameters["ema_seed"] != "FIRST_OBSERVATION_RECURSIVE":
        raise ValueError("unsupported MACD EMA initialization policy")
    warmup = int(parameters["warmup_observations"])
    if len(bars) < warmup:
        return _all_missing(
            MACD_FEATURE_ID, bars, configuration, output_ids, "WINDOW_NOT_READY"
        )
    fast = int(parameters["fast_period"])
    slow = int(parameters["slow_period"])
    signal = int(parameters["signal_period"])
    multiplier = Decimal(parameters["histogram_multiplier"])
    scale = int(parameters["output_scale"])
    closes = tuple(item.close for item in bars)
    fast_ema = _ema_series(closes, fast)
    slow_ema = _ema_series(closes, slow)
    dif = tuple(first - second for first, second in zip(fast_ema, slow_ema, strict=True))
    dea = _ema_series(dif, signal)
    histogram = tuple(multiplier * (first - second) for first, second in zip(dif, dea, strict=True))
    values: list[TechnicalFeatureValue] = [
        _available("dif", _q(dif[-1], scale), bars),
        _available("dea", _q(dea[-1], scale), bars),
        _available("histogram", _q(histogram[-1], scale), bars),
        _available("dif_slope", _q(dif[-1] - dif[-2], scale), bars),
        _available("dea_slope", _q(dea[-1] - dea[-2], scale), bars),
    ]
    cross = (
        "GOLDEN_CROSS"
        if dif[-2] <= dea[-2] and dif[-1] > dea[-1]
        else "DEATH_CROSS"
        if dif[-2] >= dea[-2] and dif[-1] < dea[-1]
        else "NONE"
    )
    values.append(_available("cross_state", cross, bars))
    zero_axis = (
        "ABOVE_ZERO"
        if dif[-1] > 0 and dea[-1] > 0
        else "BELOW_ZERO"
        if dif[-1] < 0 and dea[-1] < 0
        else "CROSSING_ZERO"
    )
    values.append(_available("zero_axis_state", zero_axis, bars))
    expansion = (
        "EXPANDING"
        if abs(histogram[-1]) > abs(histogram[-2])
        else "CONTRACTING"
        if abs(histogram[-1]) < abs(histogram[-2])
        else "FLAT"
    )
    values.append(_available("histogram_expansion_state", expansion, bars))
    values.append(
        _available(
            "histogram_consecutive_direction",
            _consecutive_direction(histogram),
            bars,
        )
    )
    lookback = int(parameters["divergence_lookback"])
    if len(bars) <= lookback:
        values.append(_missing("divergence_candidate", bars, "WINDOW_NOT_READY"))
    else:
        prior_closes = closes[-lookback - 1 : -1]
        prior_dif = dif[-lookback - 1 : -1]
        divergence = (
            "BEARISH_CANDIDATE"
            if closes[-1] > max(prior_closes) and dif[-1] < max(prior_dif)
            else "BULLISH_CANDIDATE"
            if closes[-1] < min(prior_closes) and dif[-1] > min(prior_dif)
            else "NONE"
        )
        values.append(_available("divergence_candidate", divergence, bars[-lookback - 1 :]))
    return _result(MACD_FEATURE_ID, bars, configuration, values)


def _compute_volume(
    bars: tuple[CanonicalMarketBar, ...],
    configuration: FeatureConfiguration,
    decision_time: datetime,
) -> TechnicalFeatureComputation:
    del decision_time
    output_ids = (
        *VOLUME_DECIMAL_OUTPUTS,
        "volume_persistence",
        *VOLUME_TEXT_OUTPUTS,
    )
    unsupported = _unsupported_or_suspended(
        feature_id=CAPITAL_VOLUME_FEATURE_ID,
        bars=bars,
        configuration=configuration,
        supported={Timeframe.DAILY},
        output_ids=output_ids,
    )
    if unsupported is not None:
        return unsupported
    parameters = _parameters(
        configuration,
        {
            "abnormal_ratio_threshold",
            "breakout_ratio_threshold",
            "output_scale",
            "ratio_denominator",
            "ratio_windows",
            "rounding",
        },
    )
    if parameters["ratio_denominator"] != "PRIOR_COMPLETED_SESSIONS_EXCLUDING_CURRENT":
        raise ValueError("unsupported volume ratio denominator")
    scale = int(parameters["output_scale"])
    values: list[TechnicalFeatureValue] = []
    for window in (5, 10, 20):
        values.append(
            _ratio_value(
                output_id=f"volume_ratio_{window}",
                bars=bars,
                window=window,
                getter=lambda item: item.volume,
                missing_reason="FIELD_UNAVAILABLE_VOLUME",
                scale=scale,
            )
        )
        values.append(
            _ratio_value(
                output_id=f"amount_ratio_{window}",
                bars=bars,
                window=window,
                getter=lambda item: item.amount,
                missing_reason="FIELD_UNAVAILABLE_AMOUNT",
                scale=scale,
            )
        )
    values.append(
        _percentile_value(
            output_id="volume_percentile_20",
            bars=bars,
            getter=lambda item: item.volume,
            missing_reason="FIELD_UNAVAILABLE_VOLUME",
            scale=scale,
        )
    )
    values.append(
        _percentile_value(
            output_id="amount_percentile_20",
            bars=bars,
            getter=lambda item: item.amount,
            missing_reason="FIELD_UNAVAILABLE_AMOUNT",
            scale=scale,
        )
    )
    if len(bars) < 2 or bars[-2].volume == 0:
        values.extend(
            (
                _missing("volume_expansion", bars, "ZERO_OR_MISSING_PRIOR_VOLUME"),
                _missing("volume_contraction", bars, "ZERO_OR_MISSING_PRIOR_VOLUME"),
                _missing(
                    "price_volume_direction_agreement", bars, "WINDOW_NOT_READY"
                ),
            )
        )
    else:
        volume_change = bars[-1].volume / bars[-2].volume - Decimal("1")
        values.append(
            _available(
                "volume_expansion", _q(max(volume_change, Decimal("0")), scale), bars[-2:]
            )
        )
        contraction = (
            bars[-2].volume / bars[-1].volume - Decimal("1")
            if bars[-1].volume > 0
            else None
        )
        if contraction is None:
            values.append(_missing("volume_contraction", bars[-2:], "ZERO_CURRENT_VOLUME"))
        else:
            values.append(
                _available(
                    "volume_contraction",
                    _q(max(contraction, Decimal("0")), scale),
                    bars[-2:],
                )
            )
        price_change = bars[-1].close / bars[-2].close - Decimal("1")
        agreement = (
            "AGREE"
            if (price_change > 0 and volume_change > 0)
            or (price_change < 0 and volume_change < 0)
            else "NEUTRAL"
            if price_change == 0 or volume_change == 0
            else "DIVERGE"
        )
        values.append(
            _available("price_volume_direction_agreement", agreement, bars[-2:])
        )
    volume_ratio_20 = next(item for item in values if item.output_id == "volume_ratio_20")
    if len(bars) < 21 or volume_ratio_20.value is None:
        values.append(_missing("breakout_volume_confirmation", bars, "WINDOW_NOT_READY"))
    else:
        threshold = Decimal(parameters["breakout_ratio_threshold"])
        confirmed = (
            bars[-1].close > max(item.high for item in bars[-21:-1])
            and isinstance(volume_ratio_20.value, Decimal)
            and volume_ratio_20.value >= threshold
        )
        values.append(
            _available(
                "breakout_volume_confirmation",
                "CONFIRMED" if confirmed else "NOT_CONFIRMED",
                bars[-21:],
            )
        )
    volume_ratio_5 = next(item for item in values if item.output_id == "volume_ratio_5")
    if not isinstance(volume_ratio_5.value, Decimal):
        values.append(_missing("abnormal_volume_state", bars, "WINDOW_NOT_READY"))
    else:
        values.append(
            _available(
                "abnormal_volume_state",
                (
                    "ABNORMAL"
                    if volume_ratio_5.value >= Decimal(parameters["abnormal_ratio_threshold"])
                    else "NORMAL"
                ),
                bars[-6:],
            )
        )
    if len(bars) < 2 or bars[-1].turnover_rate is None or bars[-2].turnover_rate is None:
        values.append(_missing("turnover_expansion", bars[-2:], "FIELD_UNAVAILABLE_TURNOVER_RATE"))
    elif bars[-2].turnover_rate == 0:
        values.append(_missing("turnover_expansion", bars[-2:], "ZERO_PRIOR_TURNOVER_RATE"))
    else:
        values.append(
            _available(
                "turnover_expansion",
                _q(bars[-1].turnover_rate / bars[-2].turnover_rate - Decimal("1"), scale),
                bars[-2:],
            )
        )
    values.append(_available("volume_persistence", _volume_persistence(bars), bars))
    return _result(CAPITAL_VOLUME_FEATURE_ID, bars, configuration, values)


def _compute_vwap(
    bars: tuple[CanonicalMarketBar, ...],
    configuration: FeatureConfiguration,
    decision_time: datetime,
) -> TechnicalFeatureComputation:
    del decision_time
    output_ids = (*VWAP_DECIMAL_OUTPUTS, *VWAP_TEXT_OUTPUTS)
    unsupported = _unsupported_or_suspended(
        feature_id=VWAP_FEATURE_ID,
        bars=bars,
        configuration=configuration,
        supported={
            Timeframe.MINUTE_1,
            Timeframe.MINUTE_5,
            Timeframe.MINUTE_15,
            Timeframe.MINUTE_30,
            Timeframe.MINUTE_60,
        },
        output_ids=output_ids,
    )
    if unsupported is not None:
        return unsupported
    parameters = _parameters(
        configuration, {"output_scale", "rounding", "session_policy"}
    )
    if parameters["session_policy"] != "A_SHARE_REGULAR_SESSION_OBSERVED_BARS_ONLY":
        raise ValueError("unsupported VWAP session policy")
    scale = int(parameters["output_scale"])
    latest_date = bars[-1].market_date
    session_bars = tuple(item for item in bars if item.market_date == latest_date)
    if any(not _is_regular_session_bar(item) for item in session_bars):
        return _all_missing(
            VWAP_FEATURE_ID,
            session_bars,
            configuration,
            output_ids,
            "SESSION_BAR_OUTSIDE_POLICY",
        )
    if any(item.amount is None for item in session_bars):
        return _all_missing(
            VWAP_FEATURE_ID,
            session_bars,
            configuration,
            output_ids,
            "FIELD_UNAVAILABLE_AMOUNT",
        )
    cumulative_volume = sum((item.volume for item in session_bars), Decimal("0"))
    if cumulative_volume == 0:
        return _all_missing(
            VWAP_FEATURE_ID,
            session_bars,
            configuration,
            output_ids,
            "ZERO_CUMULATIVE_VOLUME",
        )
    cumulative_amount = sum(
        (item.amount for item in session_bars if item.amount is not None), Decimal("0")
    )
    vwap = cumulative_amount / cumulative_volume
    values: list[TechnicalFeatureValue] = [
        _available("session_vwap", _q(vwap, scale), session_bars),
        _available(
            "price_vs_vwap_return",
            _q(session_bars[-1].close / vwap - Decimal("1"), scale),
            session_bars,
        ),
        _available(
            "distance_from_vwap",
            _q(abs(session_bars[-1].close / vwap - Decimal("1")), scale),
            session_bars,
        ),
    ]
    split = max(1, len(session_bars) // 2)
    first_bars = session_bars[:split]
    first_volume = sum((item.volume for item in first_bars), Decimal("0"))
    if first_volume == 0:
        values.append(_missing("vwap_slope", first_bars, "ZERO_CUMULATIVE_VOLUME"))
    else:
        first_amount = sum(
            (item.amount for item in first_bars if item.amount is not None), Decimal("0")
        )
        first_vwap = first_amount / first_volume
        values.append(
            _available(
                "vwap_slope", _q(vwap / first_vwap - Decimal("1"), scale), session_bars
            )
        )
    if len(session_bars) < 2:
        values.append(_missing("price_crossing_vwap", session_bars, "WINDOW_NOT_READY"))
    else:
        prior_bars = session_bars[:-1]
        prior_volume = sum((item.volume for item in prior_bars), Decimal("0"))
        prior_amount = sum(
            (item.amount for item in prior_bars if item.amount is not None), Decimal("0")
        )
        if prior_volume == 0:
            values.append(
                _missing("price_crossing_vwap", prior_bars, "ZERO_CUMULATIVE_VOLUME")
            )
        else:
            prior_vwap = prior_amount / prior_volume
            prior_side = session_bars[-2].close - prior_vwap
            current_side = session_bars[-1].close - vwap
            crossing = (
                "CROSS_UP"
                if prior_side <= 0 < current_side
                else "CROSS_DOWN"
                if prior_side >= 0 > current_side
                else "NONE"
            )
            values.append(_available("price_crossing_vwap", crossing, session_bars))
    return _result(VWAP_FEATURE_ID, session_bars, configuration, values)


def _compute_overheat(
    bars: tuple[CanonicalMarketBar, ...],
    configuration: FeatureConfiguration,
    decision_time: datetime,
) -> TechnicalFeatureComputation:
    del decision_time
    output_ids = ("consecutive_up_sessions", *OVERHEAT_OUTPUTS)
    unsupported = _unsupported_or_suspended(
        feature_id=OVERHEAT_FEATURE_ID,
        bars=bars,
        configuration=configuration,
        supported={Timeframe.DAILY},
        output_ids=output_ids,
    )
    if unsupported is not None:
        return unsupported
    parameters = _parameters(
        configuration,
        {
            "output_scale",
            "range_window",
            "rolling_high_window",
            "rounding",
            "short_return_window",
            "volume_window",
        },
    )
    scale = int(parameters["output_scale"])
    short = int(parameters["short_return_window"])
    high_window = int(parameters["rolling_high_window"])
    range_window = int(parameters["range_window"])
    volume_window = int(parameters["volume_window"])
    values: list[TechnicalFeatureValue] = []
    if len(bars) <= short:
        values.append(_missing("short_return", bars, "WINDOW_NOT_READY"))
    else:
        values.append(
            _available(
                "short_return",
                _q(bars[-1].close / bars[-short - 1].close - Decimal("1"), scale),
                bars[-short - 1 :],
            )
        )
    for period in (5, 10):
        sma = _sma_series(tuple(item.close for item in bars), period)[-1]
        if sma is None:
            values.append(_missing(f"price_vs_sma{period}", bars, "WINDOW_NOT_READY"))
        else:
            values.append(
                _available(
                    f"price_vs_sma{period}",
                    _q(bars[-1].close / sma - Decimal("1"), scale),
                    bars[-period:],
                )
            )
    if len(bars) <= range_window:
        values.append(_missing("range_expansion", bars, "WINDOW_NOT_READY"))
    else:
        current_range = bars[-1].high - bars[-1].low
        prior_ranges = tuple(
            item.high - item.low for item in bars[-range_window - 1 : -1]
        )
        average_range = sum(prior_ranges, Decimal("0")) / Decimal(range_window)
        if average_range == 0:
            values.append(_missing("range_expansion", bars, "ZERO_PRIOR_RANGE"))
        else:
            values.append(
                _available(
                    "range_expansion",
                    _q(current_range / average_range - Decimal("1"), scale),
                    bars[-range_window - 1 :],
                )
            )
    if bars[-1].previous_close is None:
        values.append(_missing("gap_extension", bars[-1:], "FIELD_UNAVAILABLE_PREVIOUS_CLOSE"))
    else:
        values.append(
            _available(
                "gap_extension",
                _q(bars[-1].open / bars[-1].previous_close - Decimal("1"), scale),
                bars[-1:],
            )
        )
    values.append(_available("consecutive_up_sessions", _consecutive_up(bars), bars))
    if len(bars) < high_window:
        values.append(_missing("distance_from_rolling_high", bars, "WINDOW_NOT_READY"))
    else:
        rolling_high = max(item.high for item in bars[-high_window:])
        values.append(
            _available(
                "distance_from_rolling_high",
                _q(bars[-1].close / rolling_high - Decimal("1"), scale),
                bars[-high_window:],
            )
        )
    short_value = next(item for item in values if item.output_id == "short_return")
    volume_ratio = _ratio_value(
        output_id="internal_volume_ratio",
        bars=bars,
        window=volume_window,
        getter=lambda item: item.volume,
        missing_reason="FIELD_UNAVAILABLE_VOLUME",
        scale=scale,
    )
    if not isinstance(short_value.value, Decimal) or not isinstance(
        volume_ratio.value, Decimal
    ):
        values.append(
            _missing("volume_price_overextension", bars, "DEPENDENCY_NOT_AVAILABLE")
        )
    else:
        values.append(
            _available(
                "volume_price_overextension",
                _q(short_value.value * volume_ratio.value, scale),
                bars[-max(short + 1, volume_window + 1) :],
            )
        )
    return _result(OVERHEAT_FEATURE_ID, bars, configuration, values)


def _validate_bars(
    *, bars: tuple[CanonicalMarketBar, ...], decision_time: datetime
) -> tuple[CanonicalMarketBar, ...]:
    if not bars:
        raise ValueError("technical feature computation requires market bars")
    for bar in bars:
        bar.verify_identity()
        if bar.available_at > decision_time:
            raise ValueError("technical feature input became available after DecisionTime")
    ordered = tuple(sorted(bars, key=lambda item: (item.event_start, str(item.bar_id))))
    if ordered != bars:
        raise ValueError("technical feature bars must be deterministically sorted")
    first = bars[0]
    if any(
        item.symbol != first.symbol or item.timeframe is not first.timeframe
        for item in bars
    ):
        raise ValueError("technical feature bars must share symbol and timeframe")
    keys = tuple(item.event_start for item in bars)
    if len(keys) != len(set(keys)):
        raise ValueError("technical feature bars contain duplicate event times")
    return bars


def _unsupported_or_suspended(
    *,
    feature_id: str,
    bars: tuple[CanonicalMarketBar, ...],
    configuration: FeatureConfiguration,
    supported: set[Timeframe],
    output_ids: tuple[str, ...],
) -> TechnicalFeatureComputation | None:
    if bars[-1].timeframe not in supported:
        return _all_missing(
            feature_id, bars, configuration, output_ids, "TIMEFRAME_UNSUPPORTED"
        )
    if bars[-1].trading_status is TradingStatus.SUSPENDED:
        return _all_missing(
            feature_id, bars, configuration, output_ids, "CURRENT_BAR_SUSPENDED"
        )
    return None


def _all_missing(
    feature_id: str,
    bars: tuple[CanonicalMarketBar, ...],
    configuration: FeatureConfiguration,
    output_ids: tuple[str, ...],
    reason: str,
) -> TechnicalFeatureComputation:
    return _result(
        feature_id,
        bars,
        configuration,
        [_missing(output_id, bars, reason) for output_id in output_ids],
    )


def _result(
    feature_id: str,
    bars: tuple[CanonicalMarketBar, ...],
    configuration: FeatureConfiguration,
    values: list[TechnicalFeatureValue],
) -> TechnicalFeatureComputation:
    limitations = {
        "MODEL_ASSUMPTION",
        "NOT_EMPIRICALLY_VALIDATED",
        "RESEARCH_ONLY",
        "TRADING_AUTHORITY_NOT_GRANTED",
    }
    if bars[-1].trading_status is TradingStatus.UNKNOWN:
        limitations.add("CURRENT_TRADING_STATUS_UNKNOWN")
    return TechnicalFeatureComputation(
        feature_id=feature_id,
        symbol=bars[-1].symbol,
        timeframe=bars[-1].timeframe,
        available_at=bars[-1].available_at,
        configuration_id=configuration.configuration_id,
        configuration_hash=configuration.configuration_hash,
        values=tuple(sorted(values, key=lambda item: item.output_id)),
        limitations=tuple(sorted(limitations)),
    )


def _available(
    output_id: str,
    value: FeatureScalar,
    bars: tuple[CanonicalMarketBar, ...],
) -> TechnicalFeatureValue:
    return TechnicalFeatureValue(
        output_id=output_id,
        state=FeatureValueState.AVAILABLE,
        value=value,
        available_at=bars[-1].available_at,
        source_bar_ids=tuple(item.bar_id for item in bars),
        source_bar_hashes=tuple(item.content_hash for item in bars),
        missing_reason_codes=(),
    )


def _missing(
    output_id: str,
    bars: tuple[CanonicalMarketBar, ...],
    *reasons: str,
) -> TechnicalFeatureValue:
    return TechnicalFeatureValue(
        output_id=output_id,
        state=FeatureValueState.MISSING,
        value=None,
        available_at=bars[-1].available_at,
        source_bar_ids=tuple(item.bar_id for item in bars),
        source_bar_hashes=tuple(item.content_hash for item in bars),
        missing_reason_codes=tuple(sorted(reasons)),
    )


def _parameters(
    configuration: FeatureConfiguration, expected: set[str]
) -> dict[str, str]:
    parameters = configuration.parameter_map()
    if set(parameters) != expected:
        raise ValueError("Feature Configuration parameter fields mismatch")
    if parameters.get("rounding") != "ROUND_HALF_EVEN":
        raise ValueError("unsupported Feature rounding policy")
    return parameters


def _scale(configuration: FeatureConfiguration) -> int:
    parameters = configuration.parameter_map()
    if parameters.get("rounding") != "ROUND_HALF_EVEN":
        raise ValueError("unsupported Feature rounding policy")
    try:
        scale = int(parameters["output_scale"])
    except (KeyError, ValueError) as exc:
        raise ValueError("Feature output scale is invalid") from exc
    if scale < 0 or scale > 18:
        raise ValueError("Feature output scale is out of range")
    return scale


def _q(value: Decimal, scale: int) -> Decimal:
    quantum = Decimal(1).scaleb(-scale)
    quantized = value.quantize(quantum, rounding=ROUND_HALF_EVEN)
    return quantized.normalize() if quantized != 0 else Decimal("0")


def _sma_series(values: tuple[Decimal, ...], period: int) -> tuple[Decimal | None, ...]:
    result: list[Decimal | None] = []
    rolling = Decimal("0")
    for index, value in enumerate(values):
        rolling += value
        if index >= period:
            rolling -= values[index - period]
        result.append(rolling / Decimal(period) if index + 1 >= period else None)
    return tuple(result)


def _ema_series(values: tuple[Decimal, ...], period: int) -> tuple[Decimal, ...]:
    alpha = Decimal("2") / Decimal(period + 1)
    result = [values[0]]
    for value in values[1:]:
        result.append(alpha * value + (Decimal("1") - alpha) * result[-1])
    return tuple(result)


def _series_value(
    output_id: str,
    series: tuple[Decimal | None, ...],
    bars: tuple[CanonicalMarketBar, ...],
    period: int,
    scale: int,
) -> TechnicalFeatureValue:
    current = series[-1]
    if current is None:
        return _missing(output_id, bars, "WINDOW_NOT_READY")
    return _available(output_id, _q(current, scale), bars[-period:])


def _append_distance(
    values: list[TechnicalFeatureValue],
    *,
    output_id: str,
    first: Decimal | None,
    second: Decimal | None,
    bars: tuple[CanonicalMarketBar, ...],
    scale: int,
) -> None:
    if first is None or second is None:
        values.append(_missing(output_id, bars, "WINDOW_NOT_READY"))
    else:
        values.append(
            _available(output_id, _q(first / second - Decimal("1"), scale), bars)
        )


def _ratio_value(
    *,
    output_id: str,
    bars: tuple[CanonicalMarketBar, ...],
    window: int,
    getter: Callable[[CanonicalMarketBar], Decimal | None],
    missing_reason: str,
    scale: int,
) -> TechnicalFeatureValue:
    if len(bars) <= window:
        return _missing(output_id, bars, "WINDOW_NOT_READY")
    relevant = bars[-window - 1 :]
    current = getter(relevant[-1])
    prior = tuple(getter(item) for item in relevant[:-1])
    if current is None or any(item is None for item in prior):
        return _missing(output_id, relevant, missing_reason)
    prior_values = tuple(item for item in prior if item is not None)
    denominator = sum(prior_values, Decimal("0")) / Decimal(window)
    if denominator == 0:
        return _missing(output_id, relevant, "ZERO_RATIO_DENOMINATOR")
    return _available(output_id, _q(current / denominator, scale), relevant)


def _percentile_value(
    *,
    output_id: str,
    bars: tuple[CanonicalMarketBar, ...],
    getter: Callable[[CanonicalMarketBar], Decimal | None],
    missing_reason: str,
    scale: int,
) -> TechnicalFeatureValue:
    window = 20
    if len(bars) < window:
        return _missing(output_id, bars, "WINDOW_NOT_READY")
    relevant = bars[-window:]
    raw = tuple(getter(item) for item in relevant)
    if any(item is None for item in raw):
        return _missing(output_id, relevant, missing_reason)
    values = tuple(item for item in raw if item is not None)
    percentile = Decimal(sum(item <= values[-1] for item in values)) / Decimal(window)
    return _available(output_id, _q(percentile, scale), relevant)


def _consecutive_direction(values: tuple[Decimal, ...]) -> int:
    if len(values) < 2 or values[-1] == values[-2]:
        return 0
    direction = 1 if values[-1] > values[-2] else -1
    count = 1
    for index in range(len(values) - 2, 0, -1):
        difference = values[index] - values[index - 1]
        if difference == 0 or (difference > 0) != (direction > 0):
            break
        count += 1
    return direction * count


def _volume_persistence(bars: tuple[CanonicalMarketBar, ...]) -> int:
    if len(bars) < 2 or bars[-1].volume == bars[-2].volume:
        return 0
    direction = 1 if bars[-1].volume > bars[-2].volume else -1
    count = 1
    for index in range(len(bars) - 2, 0, -1):
        difference = bars[index].volume - bars[index - 1].volume
        if difference == 0 or (difference > 0) != (direction > 0):
            break
        count += 1
    return direction * count


def _consecutive_up(bars: tuple[CanonicalMarketBar, ...]) -> int:
    count = 0
    for item in reversed(bars):
        if item.previous_close is None or item.close <= item.previous_close:
            break
        count += 1
    return count


def _is_regular_session_bar(bar: CanonicalMarketBar) -> bool:
    local_start = bar.event_start.astimezone(_SHANGHAI).time()
    local_end = bar.event_end.astimezone(_SHANGHAI).time()
    morning = time(9, 30) <= local_start < local_end <= time(11, 30)
    afternoon = time(13, 0) <= local_start < local_end <= time(15, 0)
    return morning or afternoon
