from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, getcontext

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.features.technical.catalog import (
    CAPITAL_VOLUME_FEATURE_ID,
    INTRADAY_PRICE_ACTION_FEATURE_ID,
    MACD_FEATURE_ID,
    MOVING_AVERAGE_FEATURE_ID,
    OVERHEAT_FEATURE_ID,
    PRICE_ACTION_FEATURE_ID,
    VWAP_FEATURE_ID,
    canonical_technical_feature_set,
)
from market_regime_alpha.features.technical.observables import (
    FeatureValueState,
    compute_technical_feature,
)
from market_regime_alpha.market_data import (
    AdjustmentMode,
    AssetType,
    CanonicalMarketBar,
    Exchange,
    PriceLimitState,
    Timeframe,
    TradingStatus,
    VolumeUnit,
)


UTC = timezone.utc
EFFECTIVE_FROM = datetime(2026, 1, 1, tzinfo=UTC)
SOURCE_HASH = "sha256:" + "1" * 64


def _daily_bars(
    count: int,
    *,
    start_date: date = date(2026, 1, 1),
    amount_missing_at: int | None = None,
    suspended_at: int | None = None,
) -> tuple[CanonicalMarketBar, ...]:
    bars: list[CanonicalMarketBar] = []
    for index in range(count):
        market_date = start_date + timedelta(days=index)
        close = Decimal("10") + Decimal(index) / Decimal("10")
        previous = (
            None
            if index == 0
            else Decimal("10") + Decimal(index - 1) / Decimal("10")
        )
        event_start = datetime.combine(
            market_date, datetime.min.time(), tzinfo=UTC
        ) + timedelta(hours=1, minutes=30)
        event_end = event_start + timedelta(hours=5, minutes=30)
        bars.append(
            CanonicalMarketBar.create(
                symbol="600000.SH",
                exchange=Exchange.SH,
                asset_type=AssetType.A_SHARE,
                timeframe=Timeframe.DAILY,
                market_date=market_date,
                event_start=event_start,
                event_end=event_end,
                available_at=event_end,
                open=close - Decimal("0.05"),
                high=close + Decimal("0.2"),
                low=close - Decimal("0.2"),
                close=close,
                previous_close=previous,
                volume=Decimal(100000 + index * 1000),
                volume_unit=VolumeUnit.SHARES,
                amount=(
                    None
                    if amount_missing_at == index
                    else close * Decimal(100000 + index * 1000)
                ),
                turnover_rate=Decimal("0.01") + Decimal(index) / Decimal("10000"),
                adjustment_mode=AdjustmentMode.RAW,
                adjustment_factor=Decimal("1"),
                trading_status=(
                    TradingStatus.SUSPENDED
                    if suspended_at == index
                    else TradingStatus.TRADING
                ),
                price_limit_state=PriceLimitState.NORMAL,
                source_artifact_id=ArtifactId(f"source-{index}"),
                source_content_hash=SOURCE_HASH,
            )
        )
    return tuple(bars)


def _minute_bars() -> tuple[CanonicalMarketBar, ...]:
    market_date = date(2026, 8, 4)
    starts = (
        datetime(2026, 8, 4, 1, 30, tzinfo=UTC),
        datetime(2026, 8, 4, 1, 35, tzinfo=UTC),
        datetime(2026, 8, 4, 1, 40, tzinfo=UTC),
    )
    closes = (Decimal("10"), Decimal("11"), Decimal("12"))
    volumes = (Decimal("100"), Decimal("200"), Decimal("300"))
    amounts = (Decimal("1000"), Decimal("2200"), Decimal("3600"))
    return tuple(
        CanonicalMarketBar.create(
            symbol="600000.SH",
            exchange=Exchange.SH,
            asset_type=AssetType.A_SHARE,
            timeframe=Timeframe.MINUTE_5,
            market_date=market_date,
            event_start=start,
            event_end=start + timedelta(minutes=5),
            available_at=start + timedelta(minutes=5),
            open=close,
            high=close,
            low=close,
            close=close,
            previous_close=(closes[index - 1] if index else Decimal("9.9")),
            volume=volumes[index],
            volume_unit=VolumeUnit.SHARES,
            amount=amounts[index],
            turnover_rate=None,
            adjustment_mode=AdjustmentMode.RAW,
            adjustment_factor=Decimal("1"),
            trading_status=TradingStatus.TRADING,
            price_limit_state=PriceLimitState.NORMAL,
            source_artifact_id=ArtifactId(f"minute-source-{index}"),
            source_content_hash=SOURCE_HASH,
        )
        for index, (start, close) in enumerate(zip(starts, closes, strict=True))
    )


def _config(feature_id: str):
    feature_set = canonical_technical_feature_set(effective_from=EFFECTIVE_FROM)
    return next(
        item for item in feature_set.configurations if item.feature_id == feature_id
    )


def _values(
    feature_id: str,
    bars: tuple[CanonicalMarketBar, ...],
    *,
    decision_time: datetime = datetime(2026, 8, 4, 2, 30, tzinfo=UTC),
):
    computation = compute_technical_feature(
        feature_id=feature_id,
        bars=bars,
        configuration=_config(feature_id),
        decision_time=decision_time,
    )
    return {item.output_id: item for item in computation.values}


def test_price_action_returns_and_ranges_use_explicit_endpoints() -> None:
    bars = _daily_bars(11)
    values = _values(PRICE_ACTION_FEATURE_ID, bars)

    assert values["return_1"].value == Decimal("0.009174311927")
    assert values["return_10"].value == Decimal("0.1")
    assert values["gap_return"].value == Decimal("0.004587155963")
    assert values["high_low_range"].value == Decimal("0.036697247706")
    assert values["close_location_value"].value == Decimal("0")
    assert "intraday_return_to_decision_time" not in values


def test_current_session_minute_evidence_uses_session_open_not_last_bar_open() -> None:
    values = _values(
        INTRADAY_PRICE_ACTION_FEATURE_ID,
        _minute_bars(),
    )

    assert values["intraday_return_to_decision_time"].value == Decimal("0.2")
def test_moving_average_family_has_strict_windows_cross_and_alignment() -> None:
    bars = _daily_bars(61)
    values = _values(MOVING_AVERAGE_FEATURE_ID, bars)

    assert values["sma_5"].value == Decimal("15.8")
    assert values["sma_60"].value == Decimal("13.05")
    assert values["price_vs_sma20_return"].value == Decimal("0.063122923588")
    assert values["ma_alignment"].value == "BULLISH"
    assert values["short_ma_cross_state"].value == "NONE"


def test_ema_and_macd_match_independent_decimal_reference() -> None:
    bars = _daily_bars(70)
    ma_values = _values(MOVING_AVERAGE_FEATURE_ID, bars)
    macd_values = _values(MACD_FEATURE_ID, bars)
    closes = [item.close for item in bars]

    def ema(values: list[Decimal], period: int) -> list[Decimal]:
        alpha = Decimal("2") / Decimal(period + 1)
        result = [values[0]]
        for value in values[1:]:
            result.append(alpha * value + (Decimal("1") - alpha) * result[-1])
        return result

    ema12 = ema(closes, 12)
    ema26 = ema(closes, 26)
    dif = [fast - slow for fast, slow in zip(ema12, ema26, strict=True)]
    dea = ema(dif, 9)
    expected_histogram = Decimal("2") * (dif[-1] - dea[-1])

    assert ma_values["ema_12"].value == _q(ema12[-1])
    assert ma_values["ema_26"].value == _q(ema26[-1])
    assert macd_values["dif"].value == _q(dif[-1])
    assert macd_values["dea"].value == _q(dea[-1])
    assert macd_values["histogram"].value == _q(expected_histogram)
    assert macd_values["zero_axis_state"].value == "ABOVE_ZERO"


def test_macd_warmup_is_explicit_and_does_not_emit_partial_number() -> None:
    values = _values(MACD_FEATURE_ID, _daily_bars(20))

    assert all(item.state is FeatureValueState.MISSING for item in values.values())
    assert all(item.value is None for item in values.values())
    assert all("WINDOW_NOT_READY" in item.missing_reason_codes for item in values.values())


def test_volume_amount_and_turnover_missingness_is_per_output() -> None:
    values = _values(
        CAPITAL_VOLUME_FEATURE_ID,
        _daily_bars(25, amount_missing_at=24),
    )

    assert values["volume_ratio_5"].state is FeatureValueState.AVAILABLE
    assert values["amount_ratio_5"].state is FeatureValueState.MISSING
    assert values["amount_ratio_5"].missing_reason_codes == ("FIELD_UNAVAILABLE_AMOUNT",)
    assert values["amount_expansion"].missing_reason_codes == (
        "FIELD_UNAVAILABLE_AMOUNT",
    )
    assert values["amount_contraction"].missing_reason_codes == (
        "FIELD_UNAVAILABLE_AMOUNT",
    )
    assert values["turnover_expansion"].state is FeatureValueState.AVAILABLE
    assert values["turnover_persistence"].state is FeatureValueState.AVAILABLE


def test_vwap_uses_real_amount_and_volume_and_rejects_daily_approximation() -> None:
    minute_values = _values(VWAP_FEATURE_ID, _minute_bars())
    daily_values = _values(VWAP_FEATURE_ID, _daily_bars(5))

    assert minute_values["session_vwap"].value == Decimal("11.333333333333")
    assert minute_values["price_vs_vwap_return"].value == Decimal("0.058823529412")
    assert all(item.state is FeatureValueState.MISSING for item in daily_values.values())
    assert all(
        item.missing_reason_codes == ("TIMEFRAME_UNSUPPORTED",)
        for item in daily_values.values()
    )


def test_zero_volume_vwap_is_missing_not_close_fallback() -> None:
    bar = _minute_bars()[0]
    zero = CanonicalMarketBar.create(
        symbol=bar.symbol,
        exchange=bar.exchange,
        asset_type=bar.asset_type,
        timeframe=bar.timeframe,
        market_date=bar.market_date,
        event_start=bar.event_start,
        event_end=bar.event_end,
        available_at=bar.available_at,
        open=bar.open,
        high=bar.high,
        low=bar.low,
        close=bar.close,
        previous_close=bar.previous_close,
        volume=Decimal("0"),
        volume_unit=bar.volume_unit,
        amount=Decimal("0"),
        turnover_rate=None,
        adjustment_mode=bar.adjustment_mode,
        adjustment_factor=bar.adjustment_factor,
        trading_status=bar.trading_status,
        price_limit_state=bar.price_limit_state,
        source_artifact_id=bar.source_artifact_id,
        source_content_hash=bar.source_content_hash,
    )
    values = _values(VWAP_FEATURE_ID, (zero,))

    assert values["session_vwap"].state is FeatureValueState.MISSING
    assert values["session_vwap"].missing_reason_codes == ("ZERO_CUMULATIVE_VOLUME",)


def _with_volume_unit(
    bar: CanonicalMarketBar, unit: VolumeUnit
) -> CanonicalMarketBar:
    return CanonicalMarketBar.create(
        symbol=bar.symbol,
        exchange=bar.exchange,
        asset_type=bar.asset_type,
        timeframe=bar.timeframe,
        market_date=bar.market_date,
        event_start=bar.event_start,
        event_end=bar.event_end,
        available_at=bar.available_at,
        open=bar.open,
        high=bar.high,
        low=bar.low,
        close=bar.close,
        previous_close=bar.previous_close,
        volume=bar.volume,
        volume_unit=unit,
        amount=bar.amount,
        turnover_rate=bar.turnover_rate,
        adjustment_mode=bar.adjustment_mode,
        adjustment_factor=bar.adjustment_factor,
        adjustment_factor_id=bar.adjustment_factor_id,
        adjustment_factor_hash=bar.adjustment_factor_hash,
        trading_status=bar.trading_status,
        price_limit_state=bar.price_limit_state,
        source_artifact_id=bar.source_artifact_id,
        source_content_hash=bar.source_content_hash,
    )


def test_vwap_rejects_lots_and_mixed_volume_units() -> None:
    shares = _minute_bars()
    all_lots = tuple(_with_volume_unit(item, VolumeUnit.LOTS) for item in shares)
    mixed = (shares[0], _with_volume_unit(shares[1], VolumeUnit.LOTS), shares[2])

    for bars in (all_lots, mixed):
        values = _values(VWAP_FEATURE_ID, bars)
        assert all(item.state is FeatureValueState.MISSING for item in values.values())
        assert all(
            item.missing_reason_codes == ("VOLUME_UNIT_NOT_CANONICAL_SHARES",)
            for item in values.values()
        )


def test_vwap_zero_amount_with_positive_volume_is_explicitly_missing() -> None:
    bar = _minute_bars()[0]
    zero_amount = CanonicalMarketBar.create(
        symbol=bar.symbol,
        exchange=bar.exchange,
        asset_type=bar.asset_type,
        timeframe=bar.timeframe,
        market_date=bar.market_date,
        event_start=bar.event_start,
        event_end=bar.event_end,
        available_at=bar.available_at,
        open=bar.open,
        high=bar.high,
        low=bar.low,
        close=bar.close,
        previous_close=bar.previous_close,
        volume=bar.volume,
        volume_unit=bar.volume_unit,
        amount=Decimal("0"),
        turnover_rate=None,
        adjustment_mode=bar.adjustment_mode,
        adjustment_factor=bar.adjustment_factor,
        trading_status=bar.trading_status,
        price_limit_state=bar.price_limit_state,
        source_artifact_id=bar.source_artifact_id,
        source_content_hash=bar.source_content_hash,
    )
    values = _values(VWAP_FEATURE_ID, (zero_amount,))
    assert values["session_vwap"].missing_reason_codes == (
        "ZERO_CUMULATIVE_AMOUNT",
    )


def test_overheat_is_observable_only_and_decimal_context_independent() -> None:
    bars = _daily_bars(25)
    original_precision = getcontext().prec
    try:
        getcontext().prec = 6
        low_precision = _values(OVERHEAT_FEATURE_ID, bars)
        getcontext().prec = 50
        high_precision = _values(OVERHEAT_FEATURE_ID, bars)
    finally:
        getcontext().prec = original_precision

    assert low_precision == high_precision
    assert low_precision["short_return"].state is FeatureValueState.AVAILABLE
    assert not any(
        output_id in {"BUY", "SELL", "ENTER", "REDUCE", "EXIT"}
        for output_id in low_precision
    )


def test_suspended_current_bar_fails_closed_without_zero_imputation() -> None:
    values = _values(PRICE_ACTION_FEATURE_ID, _daily_bars(11, suspended_at=10))

    assert all(item.state is FeatureValueState.MISSING for item in values.values())
    assert all(item.value is None for item in values.values())
    assert all(
        item.missing_reason_codes == ("CURRENT_BAR_SUSPENDED",)
        for item in values.values()
    )


def _q(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.000000000001")).normalize()
