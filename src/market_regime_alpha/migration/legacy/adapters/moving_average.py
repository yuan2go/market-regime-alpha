"""Isolated adapter for the Legacy Dividend-T moving-average calculation.

Only the existing ``add_daily_indicators`` function performs the Legacy
calculation.  This adapter converts exact canonical inputs, exposes lossy float
semantics and never receives a Repository or any trading capability.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, cast

from market_regime_alpha.core.identity import ModelId
from market_regime_alpha.core.status import InputAvailabilityStatus
from market_regime_alpha.features.technical.moving_average import (
    MovingAverageConfiguration,
    NormalizedCloseBar,
)
from market_regime_alpha.migration.legacy.normalization.market_data import (
    LegacyFeatureObservation,
    LegacyFeatureResult,
    LegacyFeatureResultState,
    NormalizedFeatureDataset,
)


LEGACY_MOVING_AVERAGE_MODEL_ID = ModelId(
    "legacy.dividend-t.add-daily-indicators.moving-average"
)
LEGACY_MOVING_AVERAGE_SUPPORTED_WINDOWS = frozenset({5, 10, 20, 60})
_BASE_LIMITATIONS = (
    "LEGACY_FLOAT_CALCULATION",
    "LEGACY_HELPER_UNUSED_OHLCV_DERIVED_FROM_CLOSE",
    "NO_STATIC_DATA_FALLBACK",
    "NO_TRADING_AUTHORITY",
    "RESEARCH_ONLY",
)


class LegacyMovingAverageAdapter:
    """Normalize, invoke and label one Legacy moving-average calculation."""

    legacy_model_id = LEGACY_MOVING_AVERAGE_MODEL_ID
    legacy_model_version = "dividend-t-baseline-2026-08-04"

    def compute(self, dataset: object) -> LegacyFeatureResult:
        if not isinstance(dataset, NormalizedFeatureDataset):
            raise TypeError("dataset must be a NormalizedFeatureDataset")
        configuration = dataset.configuration
        if not isinstance(configuration, MovingAverageConfiguration):
            return self._not_comparable("LEGACY_CONFIGURATION_NOT_SUPPORTED")
        if configuration.window not in LEGACY_MOVING_AVERAGE_SUPPORTED_WINDOWS:
            return self._not_comparable("LEGACY_WINDOW_NOT_SUPPORTED")
        if dataset.data_availability is not InputAvailabilityStatus.AVAILABLE:
            return LegacyFeatureResult(
                model_id=self.legacy_model_id,
                model_version=self.legacy_model_version,
                state=LegacyFeatureResultState.DATA_INSUFFICIENT,
                score=None,
                observations=(),
                reason_codes=(f"INPUT_DATA_{dataset.data_availability.value}",),
                limitations=tuple(sorted(_BASE_LIMITATIONS)),
            )

        try:
            frame = _to_legacy_daily_frame(dataset)
            # Importing through the module preserves one patchable and auditable
            # call edge to the existing Legacy implementation.
            from market_regime_alpha.dividend_t import indicators

            enriched = indicators.add_daily_indicators(frame, atr_window=14)
            observations = _normalize_legacy_observations(
                enriched=enriched,
                window=configuration.window,
            )
        except Exception as exc:
            return LegacyFeatureResult.failed(
                model_id=self.legacy_model_id,
                model_version=self.legacy_model_version,
                exception=exc,
                limitations=tuple(sorted((*_BASE_LIMITATIONS, "LEGACY_EXCEPTION_EXPOSED"))),
            )

        score = observations[-1].value if observations else None
        reasons: tuple[str, ...]
        if not observations:
            state = LegacyFeatureResultState.DATA_INSUFFICIENT
            reasons = ("NO_OBSERVATIONS",)
        elif score is None:
            state = LegacyFeatureResultState.DATA_INSUFFICIENT
            reasons = ("WINDOW_NOT_READY",)
        else:
            state = LegacyFeatureResultState.AVAILABLE
            reasons = (
                ("FEATURE_COMPUTED", "WINDOW_NOT_READY")
                if any(item.value is None for item in observations)
                else ("FEATURE_COMPUTED",)
            )
        return LegacyFeatureResult(
            model_id=self.legacy_model_id,
            model_version=self.legacy_model_version,
            state=state,
            score=score,
            observations=observations,
            reason_codes=reasons,
            limitations=tuple(sorted(_BASE_LIMITATIONS)),
        )

    def _not_comparable(self, reason_code: str) -> LegacyFeatureResult:
        return LegacyFeatureResult(
            model_id=self.legacy_model_id,
            model_version=self.legacy_model_version,
            state=LegacyFeatureResultState.NOT_COMPARABLE,
            score=None,
            observations=(),
            reason_codes=(reason_code,),
            limitations=tuple(
                sorted((*_BASE_LIMITATIONS, "LEGACY_SUPPORTED_WINDOWS_5_10_20_60_ONLY"))
            ),
        )


def _to_legacy_daily_frame(dataset: NormalizedFeatureDataset) -> Any:
    import pandas as pd

    if any(not isinstance(item, NormalizedCloseBar) for item in dataset.normalized_data):
        raise TypeError("Legacy moving-average input must contain NormalizedCloseBar values")
    bars = cast(tuple[NormalizedCloseBar, ...], dataset.normalized_data)
    rows = []
    for bar in bars:
        close = float(bar.close)
        rows.append(
            {
                "timestamp": bar.market_date.isoformat(),
                "open": close,
                "high": close,
                "low": close,
                "close": close,
                "volume": 0.0,
            }
        )
    frame = pd.DataFrame(
        rows,
        columns=("timestamp", "open", "high", "low", "close", "volume"),
    )
    frame["timestamp"] = pd.to_datetime(frame["timestamp"])
    return frame


def _normalize_legacy_observations(
    *,
    enriched: Any,
    window: int,
) -> tuple[LegacyFeatureObservation, ...]:
    import pandas as pd

    column = f"ma{window}"
    required = {"timestamp", column}
    columns = set(getattr(enriched, "columns", ()))
    if not required.issubset(columns):
        raise ValueError(f"Legacy output missing required columns: {sorted(required - columns)}")

    observations: list[LegacyFeatureObservation] = []
    for _, row in enriched.iterrows():
        timestamp = pd.Timestamp(row["timestamp"])
        raw_value = row[column]
        if pd.isna(raw_value):
            value = None
            missing_reason = "WINDOW_NOT_READY"
        else:
            value = Decimal(str(raw_value))
            if not value.is_finite():
                raise ValueError("Legacy moving-average output must be finite")
            missing_reason = None
        market_date = timestamp.date()
        observations.append(
            LegacyFeatureObservation(
                key=market_date.isoformat(),
                market_date=market_date,
                value=value,
                missing_reason=missing_reason,
            )
        )
    return tuple(observations)


__all__ = [
    "LEGACY_MOVING_AVERAGE_MODEL_ID",
    "LEGACY_MOVING_AVERAGE_SUPPORTED_WINDOWS",
    "LegacyMovingAverageAdapter",
]
