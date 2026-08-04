"""Lossy, research-only adapters over existing Dividend-T indicator code.

This is the only place where the canonical technical migration calls Legacy.
Actual OHLCV values are preserved; no close-derived OHLC or zero-volume frame is
constructed.  Results are comparison evidence and can never become Signal input.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping, TypeAlias

from market_regime_alpha.market_data import CanonicalMarketBar, Timeframe


LegacyScalar: TypeAlias = Decimal | str


class LegacyTechnicalFamily(str, Enum):
    MOVING_AVERAGE = "MOVING_AVERAGE"
    EMA = "EMA"
    MACD = "MACD"
    VOLUME_RATIO = "VOLUME_RATIO"
    AMOUNT_STRUCTURE = "AMOUNT_STRUCTURE"


class LegacyTechnicalResultState(str, Enum):
    AVAILABLE = "AVAILABLE"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"
    NOT_COMPARABLE = "NOT_COMPARABLE"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class LegacyTechnicalValue:
    output_id: str
    value: LegacyScalar

    def __post_init__(self) -> None:
        if not self.output_id or self.output_id != self.output_id.strip():
            raise ValueError("Legacy technical output_id must be trimmed")
        if isinstance(self.value, Decimal) and not self.value.is_finite():
            raise ValueError("Legacy technical Decimal must be finite")
        if isinstance(self.value, str) and (
            not self.value or self.value != self.value.strip()
        ):
            raise ValueError("Legacy technical text value must be trimmed")


@dataclass(frozen=True, slots=True)
class LegacyTechnicalResult:
    family: LegacyTechnicalFamily
    state: LegacyTechnicalResultState
    observations: tuple[LegacyTechnicalValue, ...]
    reason_codes: tuple[str, ...]
    limitations: tuple[str, ...]
    exception_type: str | None = None
    exception_message: str | None = None

    def __post_init__(self) -> None:
        keys = tuple(item.output_id for item in self.observations)
        if keys != tuple(sorted(keys)) or len(keys) != len(set(keys)):
            raise ValueError("Legacy technical outputs must be sorted and unique")
        if self.reason_codes != tuple(sorted(set(self.reason_codes))):
            raise ValueError("Legacy technical reasons must be sorted and unique")
        if self.limitations != tuple(sorted(set(self.limitations))):
            raise ValueError("Legacy technical limitations must be sorted and unique")
        if (self.exception_type is None) != (self.exception_message is None):
            raise ValueError("Legacy technical exception fields must be paired")
        if self.state is LegacyTechnicalResultState.AVAILABLE and not self.observations:
            raise ValueError("available Legacy result requires observations")
        if self.state is not LegacyTechnicalResultState.AVAILABLE and self.observations:
            raise ValueError("non-available Legacy result cannot expose observations")

    @property
    def values(self) -> dict[str, LegacyScalar]:
        return {item.output_id: item.value for item in self.observations}


class LegacyTechnicalObservableAdapter:
    """Call exact Legacy helpers without publishing canonical state."""

    model_version = "dividend-t-baseline-2026-08-04"

    def compute(
        self,
        *,
        family: LegacyTechnicalFamily,
        bars: tuple[CanonicalMarketBar, ...],
    ) -> LegacyTechnicalResult:
        if not isinstance(family, LegacyTechnicalFamily):
            raise TypeError("family must be LegacyTechnicalFamily")
        if not isinstance(bars, tuple) or any(
            not isinstance(item, CanonicalMarketBar) for item in bars
        ):
            raise TypeError("bars must contain CanonicalMarketBar values")
        if family is LegacyTechnicalFamily.AMOUNT_STRUCTURE:
            return _not_comparable(
                family,
                "LEGACY_AMOUNT_STRUCTURE_NOT_IMPLEMENTED",
                ("NO_EQUIVALENT_LEGACY_AUTHORITY",),
            )
        if not bars:
            return _insufficient(family, "LEGACY_BARS_EMPTY")
        if any(item.timeframe is not Timeframe.DAILY for item in bars):
            return _not_comparable(
                family, "LEGACY_DAILY_TIMEFRAME_ONLY", ("NO_RESAMPLING_PERFORMED",)
            )
        symbols = {item.symbol for item in bars}
        if len(symbols) != 1:
            return _not_comparable(
                family, "LEGACY_SINGLE_SYMBOL_REQUIRED", ("NO_CROSS_SYMBOL_MIXING",)
            )
        ordered = tuple(sorted(bars, key=lambda item: item.event_end))
        if len({item.event_end for item in ordered}) != len(ordered):
            return _not_comparable(
                family, "LEGACY_DUPLICATE_EVENT_TIME", ("DUPLICATE_INPUT_REJECTED",)
            )
        for bar in ordered:
            bar.verify_identity()
        try:
            if family is LegacyTechnicalFamily.MOVING_AVERAGE:
                return self._moving_average(ordered)
            if family is LegacyTechnicalFamily.EMA:
                return self._ema(ordered)
            if family is LegacyTechnicalFamily.MACD:
                return self._macd(ordered)
            if family is LegacyTechnicalFamily.VOLUME_RATIO:
                return self._volume_ratio(ordered)
        except Exception as exc:
            return LegacyTechnicalResult(
                family=family,
                state=LegacyTechnicalResultState.FAILED,
                observations=(),
                reason_codes=("LEGACY_EXCEPTION_EXPOSED",),
                limitations=_limitations("LEGACY_COMPUTATION_FAILED"),
                exception_type=type(exc).__name__,
                exception_message=str(exc) or repr(exc),
            )
        raise AssertionError("unhandled Legacy technical family")

    def _moving_average(
        self, bars: tuple[CanonicalMarketBar, ...]
    ) -> LegacyTechnicalResult:
        if len(bars) < 60:
            return _insufficient(
                LegacyTechnicalFamily.MOVING_AVERAGE, "LEGACY_WINDOW_NOT_READY"
            )
        from market_regime_alpha.dividend_t import indicators

        frame = indicators.add_daily_indicators(_frame(bars), atr_window=14)
        latest = frame.iloc[-1]
        values = {
            f"sma_{period}": _decimal(latest[f"ma{period}"])
            for period in (5, 10, 20, 60)
        }
        return _available(
            LegacyTechnicalFamily.MOVING_AVERAGE,
            values,
            ("LEGACY_PANDAS_FLOAT_SEMANTICS", "LEGACY_ROLLING_STRICT_WINDOW"),
        )

    def _ema(
        self, bars: tuple[CanonicalMarketBar, ...]
    ) -> LegacyTechnicalResult:
        from market_regime_alpha.dividend_t.macd import ema_recursive

        closes = tuple(float(item.close) for item in bars)
        values = {
            f"ema_{period}": _decimal(ema_recursive(closes, period)[-1])
            for period in (5, 10, 12, 20, 26, 60)
        }
        return _available(
            LegacyTechnicalFamily.EMA,
            values,
            (
                "LEGACY_FIRST_OBSERVATION_EMA_SEED",
                "LEGACY_RECURSIVE_FLOAT_SEMANTICS",
            ),
        )

    def _macd(
        self, bars: tuple[CanonicalMarketBar, ...]
    ) -> LegacyTechnicalResult:
        from market_regime_alpha.dividend_t.macd import (
            BarInterval,
            MACDConfig,
            calculate_macd,
        )

        result = calculate_macd(
            tuple(item.close for item in bars),
            MACDConfig(
                bar_interval=BarInterval.DAY_1,
                fast_period=12,
                slow_period=26,
                signal_period=9,
                cross_lookback_bars=3,
            ),
        )
        if not result.data_ready:
            return _insufficient(
                LegacyTechnicalFamily.MACD,
                f"LEGACY_MACD_{result.data_reason.value}",
            )
        assert result.dif is not None
        assert result.dea is not None
        assert result.histogram is not None
        values: dict[str, LegacyScalar] = {
            "cross": result.cross.value,
            "dea": _decimal(result.dea),
            "dif": _decimal(result.dif),
            "histogram": _decimal(result.histogram),
            "histogram_trend": result.histogram_trend.value,
            "zero_axis": result.zero_axis.value,
        }
        return _available(
            LegacyTechnicalFamily.MACD,
            values,
            (
                "LEGACY_DOUBLED_HISTOGRAM",
                "LEGACY_FIRST_OBSERVATION_EMA_SEED",
                "LEGACY_RECURSIVE_FLOAT_SEMANTICS",
            ),
        )

    def _volume_ratio(
        self, bars: tuple[CanonicalMarketBar, ...]
    ) -> LegacyTechnicalResult:
        if len(bars) < 20:
            return _insufficient(
                LegacyTechnicalFamily.VOLUME_RATIO, "LEGACY_WINDOW_NOT_READY"
            )
        if any(item.volume is None for item in bars):
            return _insufficient(
                LegacyTechnicalFamily.VOLUME_RATIO, "LEGACY_REAL_VOLUME_UNAVAILABLE"
            )
        from market_regime_alpha.dividend_t import indicators

        frame = indicators.add_daily_indicators(_frame(bars), atr_window=14)
        latest = frame.iloc[-1]
        mean = _decimal(latest["volume_ma20"])
        current = bars[-1].volume
        assert current is not None
        if mean == 0:
            return _insufficient(
                LegacyTechnicalFamily.VOLUME_RATIO,
                "LEGACY_VOLUME_DENOMINATOR_ZERO",
            )
        return _available(
            LegacyTechnicalFamily.VOLUME_RATIO,
            {"volume_ratio_20_including_current": current / mean},
            (
                "LEGACY_INCLUDES_CURRENT_OBSERVATION",
                "LEGACY_PANDAS_FLOAT_SEMANTICS",
            ),
        )


def _frame(bars: tuple[CanonicalMarketBar, ...]) -> Any:
    import pandas as pd

    return pd.DataFrame(
        (
            {
                "timestamp": item.event_end,
                "open": float(item.open),
                "high": float(item.high),
                "low": float(item.low),
                "close": float(item.close),
                "volume": float(item.volume) if item.volume is not None else None,
                "amount": float(item.amount) if item.amount is not None else None,
                "turnover_rate": (
                    float(item.turnover_rate)
                    if item.turnover_rate is not None
                    else None
                ),
            }
            for item in bars
        )
    )


def _decimal(value: object) -> Decimal:
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("Legacy technical output is not finite")
    return result


def _available(
    family: LegacyTechnicalFamily,
    values: Mapping[str, LegacyScalar],
    extra_limitations: tuple[str, ...],
) -> LegacyTechnicalResult:
    return LegacyTechnicalResult(
        family=family,
        state=LegacyTechnicalResultState.AVAILABLE,
        observations=tuple(
            LegacyTechnicalValue(output_id=key, value=value)
            for key, value in sorted(values.items())
        ),
        reason_codes=("LEGACY_COMPUTED_FOR_DIFFERENTIAL_ONLY",),
        limitations=_limitations(*extra_limitations),
    )


def _insufficient(
    family: LegacyTechnicalFamily, reason: str
) -> LegacyTechnicalResult:
    return LegacyTechnicalResult(
        family=family,
        state=LegacyTechnicalResultState.DATA_INSUFFICIENT,
        observations=(),
        reason_codes=(reason,),
        limitations=_limitations("LEGACY_DATA_INSUFFICIENT"),
    )


def _not_comparable(
    family: LegacyTechnicalFamily,
    reason: str,
    extra_limitations: tuple[str, ...],
) -> LegacyTechnicalResult:
    return LegacyTechnicalResult(
        family=family,
        state=LegacyTechnicalResultState.NOT_COMPARABLE,
        observations=(),
        reason_codes=(reason,),
        limitations=_limitations(*extra_limitations),
    )


def _limitations(*values: str) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                *values,
                "LEGACY_LOSSY_COMPARISON_ONLY",
                "NO_CANONICAL_REPOSITORY_MUTATION",
                "NO_SIGNAL_AUTHORITY",
                "NO_TRADING_AUTHORITY",
                "RESEARCH_ONLY",
            }
        )
    )


__all__ = [
    "LegacyTechnicalFamily",
    "LegacyTechnicalObservableAdapter",
    "LegacyTechnicalResult",
    "LegacyTechnicalResultState",
    "LegacyTechnicalValue",
]
