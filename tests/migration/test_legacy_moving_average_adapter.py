from dataclasses import FrozenInstanceError
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pandas as pd
import pytest

from market_regime_alpha.core.identity import ArtifactId, DatasetId
from market_regime_alpha.core.status import InputAvailabilityStatus
from market_regime_alpha.features.technical.moving_average import (
    MovingAverageConfiguration,
    NormalizedCloseBar,
)
from market_regime_alpha.migration.legacy.adapters.moving_average import (
    LegacyMovingAverageAdapter,
)
from market_regime_alpha.migration.legacy.normalization.market_data import (
    LegacyFeatureResultState,
    NormalizedFeatureDataset,
)


AS_OF = datetime(2026, 8, 4, 7, 0, tzinfo=timezone.utc)
HASH_A = "sha256:" + "a" * 64


def bars(count: int = 5) -> tuple[NormalizedCloseBar, ...]:
    result: list[NormalizedCloseBar] = []
    for index in range(count):
        market_date = date(2026, 7, 30) + timedelta(days=index)
        result.append(
            NormalizedCloseBar(
            symbol="600000.SH",
            market_date=market_date,
            close=Decimal(str(10 + index)),
            available_at=datetime.combine(
                market_date, datetime.min.time(), tzinfo=timezone.utc
            ).replace(hour=7),
            )
        )
    return tuple(result)


def dataset(
    *,
    window: int = 5,
    values: tuple[NormalizedCloseBar, ...] | None = None,
    availability: InputAvailabilityStatus = InputAvailabilityStatus.AVAILABLE,
) -> NormalizedFeatureDataset:
    configuration = MovingAverageConfiguration.create(
        configuration_version="1.0.0",
        window=window,
    )
    return NormalizedFeatureDataset.create(
        dataset_id=DatasetId("legacy-ma-dataset"),
        as_of_time=AS_OF,
        data_availability=availability,
        configuration_id=configuration.configuration_id,
        configuration_version=configuration.configuration_version,
        configuration_hash=configuration.content_hash,
        configuration=configuration,
        input_artifact_ids=(ArtifactId("source-bars"),),
        input_hashes=(HASH_A,),
        normalized_data=bars() if values is None else values,
    )


def test_legacy_adapter_calls_existing_indicator_and_normalizes_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_add_daily_indicators(frame: pd.DataFrame, *, atr_window: int = 14) -> pd.DataFrame:
        captured["columns"] = tuple(frame.columns)
        captured["timestamp"] = tuple(frame["timestamp"].dt.date)
        captured["close"] = tuple(frame["close"])
        captured["atr_window"] = atr_window
        result = frame.copy()
        result["ma5"] = [float("nan"), float("nan"), float("nan"), float("nan"), 12.0]
        return result

    monkeypatch.setattr(
        "market_regime_alpha.dividend_t.indicators.add_daily_indicators",
        fake_add_daily_indicators,
    )

    result = LegacyMovingAverageAdapter().compute(dataset())

    assert captured == {
        "columns": ("timestamp", "open", "high", "low", "close", "volume"),
        "timestamp": tuple(item.market_date for item in bars()),
        "close": tuple(float(item.close) for item in bars()),
        "atr_window": 14,
    }
    assert result.state is LegacyFeatureResultState.AVAILABLE
    assert result.score == Decimal("12.0")
    assert tuple(item.value for item in result.observations) == (
        None,
        None,
        None,
        None,
        Decimal("12.0"),
    )
    assert tuple(item.missing_reason for item in result.observations) == (
        "WINDOW_NOT_READY",
        "WINDOW_NOT_READY",
        "WINDOW_NOT_READY",
        "WINDOW_NOT_READY",
        None,
    )
    assert "LEGACY_FLOAT_CALCULATION" in result.limitations
    assert "LEGACY_HELPER_UNUSED_OHLCV_DERIVED_FROM_CLOSE" in result.limitations


def test_legacy_adapter_rejects_unsupported_window_without_calling_legacy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("unsupported windows must not invoke Legacy")

    monkeypatch.setattr(
        "market_regime_alpha.dividend_t.indicators.add_daily_indicators", forbidden
    )

    result = LegacyMovingAverageAdapter().compute(dataset(window=3))

    assert result.state is LegacyFeatureResultState.NOT_COMPARABLE
    assert result.reason_codes == ("LEGACY_WINDOW_NOT_SUPPORTED",)
    assert "LEGACY_SUPPORTED_WINDOWS_5_10_20_60_ONLY" in result.limitations


def test_legacy_adapter_captures_exception_without_silent_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken(*args: object, **kwargs: object) -> object:
        raise ArithmeticError("legacy rolling calculation failed")

    monkeypatch.setattr(
        "market_regime_alpha.dividend_t.indicators.add_daily_indicators", broken
    )

    result = LegacyMovingAverageAdapter().compute(dataset())

    assert result.state is LegacyFeatureResultState.COMPUTATION_FAILED
    assert result.reason_codes == ("LEGACY_COMPUTATION_FAILED",)
    assert result.exception_type == "ArithmeticError"
    assert result.exception_message == "legacy rolling calculation failed"
    assert result.score is None
    assert result.observations == ()


def test_legacy_adapter_marks_unavailable_input_without_fallback() -> None:
    result = LegacyMovingAverageAdapter().compute(
        dataset(availability=InputAvailabilityStatus.MISSING)
    )

    assert result.state is LegacyFeatureResultState.DATA_INSUFFICIENT
    assert result.reason_codes == ("INPUT_DATA_MISSING",)
    assert "NO_STATIC_DATA_FALLBACK" in result.limitations


def test_normalized_dataset_is_content_addressed_and_immutable() -> None:
    first = dataset()
    second = dataset()

    assert first == second
    assert first.content_hash.startswith("sha256:")
    with pytest.raises(FrozenInstanceError):
        setattr(first, "content_hash", HASH_A)
