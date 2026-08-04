from __future__ import annotations

from market_regime_alpha.migration.legacy.adapters.technical_observables import (
    LegacyTechnicalFamily,
    LegacyTechnicalObservableAdapter,
    LegacyTechnicalResultState,
)
from tests.features.test_materialization_runner_v2 import _daily_bars, _minute_bars


def test_adapter_invokes_real_legacy_sma_ema_macd_and_volume_logic() -> None:
    bars = _daily_bars()
    adapter = LegacyTechnicalObservableAdapter()

    moving_average = adapter.compute(
        family=LegacyTechnicalFamily.MOVING_AVERAGE, bars=bars
    )
    ema = adapter.compute(family=LegacyTechnicalFamily.EMA, bars=bars)
    macd = adapter.compute(family=LegacyTechnicalFamily.MACD, bars=bars)
    volume = adapter.compute(family=LegacyTechnicalFamily.VOLUME_RATIO, bars=bars)

    assert all(
        item.state is LegacyTechnicalResultState.AVAILABLE
        for item in (moving_average, ema, macd, volume)
    )
    assert set(moving_average.values) == {"sma_5", "sma_10", "sma_20", "sma_60"}
    assert set(ema.values) == {
        "ema_5",
        "ema_10",
        "ema_12",
        "ema_20",
        "ema_26",
        "ema_60",
    }
    assert set(macd.values) >= {"dif", "dea", "histogram"}
    assert set(volume.values) == {"volume_ratio_20_including_current"}
    assert "LEGACY_PANDAS_FLOAT_SEMANTICS" in moving_average.limitations
    assert "LEGACY_RECURSIVE_FLOAT_SEMANTICS" in ema.limitations
    assert "LEGACY_INCLUDES_CURRENT_OBSERVATION" in volume.limitations


def test_amount_structure_without_real_legacy_equivalent_is_not_comparable() -> None:
    result = LegacyTechnicalObservableAdapter().compute(
        family=LegacyTechnicalFamily.AMOUNT_STRUCTURE,
        bars=_daily_bars(),
    )

    assert result.state is LegacyTechnicalResultState.NOT_COMPARABLE
    assert result.values == {}
    assert result.reason_codes == ("LEGACY_AMOUNT_STRUCTURE_NOT_IMPLEMENTED",)


def test_legacy_adapter_rejects_non_daily_and_missing_real_volume() -> None:
    adapter = LegacyTechnicalObservableAdapter()
    result = adapter.compute(
        family=LegacyTechnicalFamily.MOVING_AVERAGE,
        bars=_minute_bars(),
    )
    assert result.state is LegacyTechnicalResultState.NOT_COMPARABLE
    assert result.reason_codes == ("LEGACY_DAILY_TIMEFRAME_ONLY",)
