# Intent-Aware MACD Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add reproducible interval-aware MACD features, explicit SignalIntent candidates, asymmetric policy, auditable sizing, and leakage-safe experiments while leaving the production runtime on the legacy baseline profile.

**Architecture:** A pure `macd.py` module calculates and scores MACD; `macd_bars.py` owns finalized-bar, interval, calendar, and point-in-time price preparation. Signal generators emit structured candidates with one primary setup and intent, while a shared policy consumes those fields and applies at most one sizing multiplier. API, snapshots, caches, and backtests record effective configuration and immutable traces; production configuration remains `score_weight=0` and `conflict_gate_enabled=False` through Stage 7.

**Tech Stack:** Python 3.12, dataclasses and enums, pandas 2.2+, FastAPI/Pydantic, pytest, Ruff, mypy, JSON/CSV/Parquet backtest artifacts.

## Global Constraints

- Follow `docs/superpowers/specs/2026-07-13-macd-signal-intent-design.md` as the normative specification.
- Formal decisions use `closed_bars_only=True`; provisional bars are UI preview only.
- Supported v1 intervals are exactly `1d` and `5m`.
- Formal MACD uses `price_field=close`, `price_adjustment_mode=POINT_IN_TIME_ADJUSTED`, and `histogram_tolerance_mode=ABSOLUTE`.
- `histogram_flat_tolerance=0.0` is the strict default; a non-zero absolute value is configured for one effective symbol/interval profile and is never silently reused across the whole universe.
- EMA is recursive with `alpha=2/(period+1)`, seed equal to the first close, and pandas compatibility `adjust=False`.
- The 33/34/35 boundary is fixed: unavailable at 33, current values only at 34, adjacent-bar features from 35.
- Signal generation assigns equal v1 `candidate_setup_code`/`primary_setup_code`, `candidate_signal_intent`, and current-bar confirmations exactly once.
- `RISK_REDUCTION` is never blocked or resized; `BASE_ACCUMULATION` is not gated in v1.
- Each pipeline has one MACD sizing owner; duplicate multiplier application is an error.
- Default production profile remains baseline: `score_weight=0`, `conflict_gate_enabled=False`.
- Stage 5 must not enable production gating.
- Stage 7 creates reports only; changing production defaults requires a separate reviewed decision.
- Every task uses TDD, ends with focused tests, and produces its own commit.
- Use `uv run --extra dev` for pytest, Ruff, and mypy in this repository.

---

## File Responsibility Map

### New files

- `src/market_regime_alpha/dividend_t/macd.py`: MACD enums, config, result, recursive calculation, true-cross scan, bullish-strength breakdown.
- `src/market_regime_alpha/dividend_t/macd_bars.py`: finalized-bar selection, A-share interval/session validation, missing-bar diagnostics, point-in-time adjustment input contract.
- `src/market_regime_alpha/dividend_t/signal_intent.py`: setup and intent enums, confirmation sets, candidate contract, trace, profiles, asymmetric policy.
- `src/market_regime_alpha/dividend_t/macd_experiments.py`: canonical config/dataset hashes, four ablation profiles, immutable report metadata and paths.
- `tests/test_macd.py`: pure calculation and 33/34/35 tests.
- `tests/test_macd_bars.py`: closed-bar, calendar, gap, and adjustment tests.
- `tests/test_signal_intent.py`: mapping, current-bar confirmations, policy, sizing, and trace tests.
- `tests/test_macd_experiments.py`: cache/config hashes, immutable artifacts, and metric formulas.
- `backtesting/run_macd_ablation.py`: four-arm chronological/symbol-holdout runner and sealed final-test report entrypoint.

### Existing files with focused modifications

- `src/market_regime_alpha/dividend_t/models.py`: flat MACD fields and strategy DecisionTrace.
- `src/market_regime_alpha/dividend_t/indicators.py`: consume prepared bars and shared MACD result.
- `src/market_regime_alpha/dividend_t/scoring.py`: `[0,100]` normalization, legacy/new technical scores, normalized MACD weight.
- `src/market_regime_alpha/dividend_t/strategy.py`: structured simplified candidates and one policy call.
- `src/market_regime_alpha/dividend_t/chan.py`: optional shared series primitive without changing Chan-normalized semantics.
- `src/market_regime_alpha/dividend_t/cosco_timing_types.py`: structured candidate, layered trace, and metadata fields.
- `src/market_regime_alpha/dividend_t/cosco_timing_manual.py`: assign primary setup, intent, and confirmations at each winning branch.
- `src/market_regime_alpha/dividend_t/cosco_timing.py`: preserve raw/quality/MACD/freshness stages and separate 5m config.
- `src/market_regime_alpha/dividend_t/buy_point_quality.py`: map reporting subtype from primary setup instead of re-inferring intent.
- `src/market_regime_alpha/dividend_t/backtest.py`: cache identity, research diagnostics, one sizing owner, counterfactual ledger.
- `src/market_regime_alpha/dividend_t/trend_snapshot.py`: schema 2 and distinct daily/5m metadata.
- `src/market_regime_alpha/web/dividend_t_app.py`: additive enum/trace/metadata serialization and provisional preview separation.
- `backtesting/run_cosco_dividend_t_backtest.py`: explicit baseline/experiment profile selection.
- `backtesting/run_dividend_watchlist_backtest.py`: explicit baseline/experiment profile selection and report metadata.
- `tests/test_dividend_t_model.py`, `tests/test_cosco_timing.py`, `tests/test_dividend_t_backtest.py`, `tests/test_dividend_trend_snapshot.py`, `tests/test_dividend_t_app.py`, `tests/test_dividend_t_chan.py`: regression and integration coverage.
- `docs/Dividend-T-Platform.md`, `docs/Data-Spec.md`, `backtesting/README.md`: final user-facing contracts and commands.

## Old Logic Replacement Checkpoints

- Replace simplified-strategy inline signal selection with `select_simplified_candidate`; preserve the legacy final result under baseline.
- Replace `_manual_action`'s tuple return with `ManualCandidateDecision`; do not keep a second tuple path.
- Remove feature-boolean reclassification from `buy_point_quality.py` and `backtest.py`; reporting subtype consumes the generator-owned primary setup.
- Replace human-readable cache tags as cache identity with schema plus canonical hashes; tags remain labels only.
- Centralize MACD sizing at the simplified finalization boundary and the detailed target-delta boundary; delete any upstream or downstream duplicate multiplier.
- Replace Chan's local EMA/MACD primitive only after numeric parity; otherwise retain it and document the intentionally separate normalized input semantics.

---

### Task 1: Stage 1A — Pure MACD Contract and Recursive Calculation

**Files:**
- Create: `src/market_regime_alpha/dividend_t/macd.py`
- Create: `tests/test_macd.py`

**Interfaces:**
- Consumes: `Sequence[float | int | str | None]` closes and `MACDConfig`.
- Produces: `calculate_macd(closes: Sequence[object], config: MACDConfig) -> MACDResult`, `ema_recursive(values: Sequence[float], period: int) -> tuple[float, ...]`, and version constants.

- [ ] **Step 1: Write failing enum, configuration, invalid-close, and 33/34/35 tests**

```python
from dataclasses import replace

import pytest

from market_regime_alpha.dividend_t.macd import (
    BarInterval,
    MACDConfig,
    MACDConfigError,
    MACDCross,
    MACDDataReason,
    MACDHistogramTrend,
    MACDScoreBreakdown,
    MACDZeroAxis,
    _histogram_trend,
    _most_recent_true_cross,
    _score_macd,
    _zero_axis,
    calculate_macd,
    ema_recursive,
)


def rising_closes(count: int) -> list[float]:
    return [10.0 + index * 0.07 for index in range(count)]


def test_macd_rejects_bool_period() -> None:
    with pytest.raises(MACDConfigError, match="fast_period must be a positive integer"):
        MACDConfig(bar_interval=BarInterval.DAY_1, fast_period=True)


@pytest.mark.parametrize("bad", [None, float("nan"), float("inf"), 0.0, -1.0, "bad"])
def test_any_invalid_historical_close_invalidates_result(bad: object) -> None:
    closes: list[object] = rising_closes(40)
    closes[2] = bad
    result = calculate_macd(closes, MACDConfig(bar_interval=BarInterval.DAY_1))
    assert result.data_ready is False
    assert result.data_reason is MACDDataReason.INVALID_CLOSE
    assert result.dif is None
    assert result.score == 50.0


def test_warmup_boundary_33_34_35() -> None:
    config = MACDConfig(bar_interval=BarInterval.DAY_1)
    at_33 = calculate_macd(rising_closes(33), config)
    at_34 = calculate_macd(rising_closes(34), config)
    at_35 = calculate_macd(rising_closes(35), config)
    assert at_33.data_reason is MACDDataReason.INSUFFICIENT_BARS
    assert at_33.dif is None and at_33.dea is None and at_33.histogram is None
    assert at_34.data_ready is True
    assert at_34.histogram_delta is None
    assert at_34.histogram_trend is MACDHistogramTrend.FLAT
    assert at_34.cross is MACDCross.NONE
    assert at_34.score_breakdown.cross_component == 0.0
    assert at_34.score_breakdown.histogram_trend_component == 0.0
    assert at_35.data_ready is True
    assert at_35.histogram_delta is not None
```

- [ ] **Step 2: Run the tests and verify the module is absent**

Run: `uv run --extra dev pytest tests/test_macd.py -q`

Expected: collection fails with `ModuleNotFoundError: No module named 'market_regime_alpha.dividend_t.macd'`.

- [ ] **Step 3: Implement enums, validated config, immutable results, recursive EMA, and warm-up**

```python
# src/market_regime_alpha/dividend_t/macd.py
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import Sequence

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
    pass


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
        if not math.isfinite(self.histogram_flat_tolerance) or self.histogram_flat_tolerance < 0:
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
        if self.data_ready:
            if self.data_reason is not MACDDataReason.READY:
                raise ValueError("ready MACD requires READY reason and raw values")
            if self.dif is None or self.dea is None or self.histogram is None:
                raise ValueError("ready MACD requires READY reason and raw values")
            if any(not math.isfinite(value) for value in (self.dif, self.dea, self.histogram)):
                raise ValueError("ready MACD raw values must be finite")
            if not 0.0 <= self.score <= 100.0:
                raise ValueError("macd score must be in [0, 100]")
        else:
            if self.data_reason is MACDDataReason.READY:
                raise ValueError("unready MACD cannot use READY reason")
            if self.score != 50.0 or self.cross is not MACDCross.NONE or self.cross_age is not None:
                raise ValueError("unready MACD must use neutral score and cross")
            if any(value is not None for value in (self.dif, self.dea, self.histogram, self.histogram_delta)):
                raise ValueError("unready MACD raw values must be None")
            if self.histogram_trend is not MACDHistogramTrend.FLAT or self.zero_axis is not MACDZeroAxis.STRADDLING:
                raise ValueError("unready MACD must use neutral trend and zero axis")
        if self.cross is MACDCross.NONE and self.cross_age is not None:
            raise ValueError("NONE cross cannot have an age")
        if self.cross is not MACDCross.NONE:
            if self.cross_age is None or not 0 <= self.cross_age < self.config.cross_lookback_bars:
                raise ValueError("cross age must lie inside lookback window")
        if self.data_ready:
            assert self.dif is not None and self.dea is not None
            if self.zero_axis is not _zero_axis(self.dif, self.dea):
                raise ValueError("zero-axis enum must match unrounded DIF and DEA")


def ema_recursive(values: Sequence[float], period: int) -> tuple[float, ...]:
    if not values:
        raise ValueError("ema_recursive requires at least one value")
    if isinstance(period, bool) or not isinstance(period, int) or period <= 0:
        raise ValueError("EMA period must be a positive integer")
    alpha = 2.0 / (period + 1.0)
    output = [float(values[0])]
    for value in values[1:]:
        output.append(alpha * float(value) + (1.0 - alpha) * output[-1])
    return tuple(output)


def macd_series(
    values: Sequence[float],
    *,
    fast_period: int,
    slow_period: int,
    signal_period: int,
) -> tuple[tuple[float, ...], tuple[float, ...], tuple[float, ...]]:
    if not values:
        raise ValueError("macd_series requires at least one value")
    for period in (fast_period, slow_period, signal_period):
        if isinstance(period, bool) or not isinstance(period, int) or period <= 0:
            raise ValueError("MACD series periods must be positive integers")
    fast = ema_recursive(values, fast_period)
    slow = ema_recursive(values, slow_period)
    dif = tuple(left - right for left, right in zip(fast, slow, strict=True))
    dea = ema_recursive(dif, signal_period)
    histogram = tuple(2.0 * (left - right) for left, right in zip(dif, dea, strict=True))
    return dif, dea, histogram
```

Add these calculation helpers below the dataclasses:

```python
def neutral_macd_result(config: MACDConfig, reason: MACDDataReason) -> MACDResult:
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
        try:
            close = float(value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(close) or close <= 0.0:
            return None
        output.append(close)
    return tuple(output)


def calculate_macd(closes: Sequence[object], config: MACDConfig) -> MACDResult:
    values = _coerce_closes(closes)
    if values is None:
        return neutral_macd_result(config, MACDDataReason.INVALID_CLOSE)
    minimum = config.slow_period + config.signal_period - 1
    if len(values) < minimum:
        return neutral_macd_result(config, MACDDataReason.INSUFFICIENT_BARS)
    dif_series, dea_series, hist_series = macd_series(
        values,
        fast_period=config.fast_period,
        slow_period=config.slow_period,
        signal_period=config.signal_period,
    )
    first_ready_index = minimum - 1
    latest_index = len(values) - 1
    dif = dif_series[-1]
    dea = dea_series[-1]
    histogram = hist_series[-1]
    zero_axis = _zero_axis(dif, dea)
    if latest_index == first_ready_index:
        trend = MACDHistogramTrend.FLAT
        delta = None
        cross = MACDCross.NONE
        age = None
    else:
        delta = histogram - hist_series[-2]
        trend = _histogram_trend(hist_series[-2], histogram, config.histogram_flat_tolerance)
        cross, age = _most_recent_true_cross(dif_series, dea_series, first_ready_index, config.cross_lookback_bars)
    breakdown = _score_macd(histogram, zero_axis, cross, age, trend, config.cross_lookback_bars)
    return MACDResult(
        config=config,
        dif=dif,
        dea=dea,
        histogram=histogram,
        histogram_delta=delta,
        histogram_trend=trend,
        cross=cross,
        cross_age=age,
        zero_axis=zero_axis,
        data_ready=True,
        data_reason=MACDDataReason.READY,
        score=breakdown.clamped_macd_score,
        score_breakdown=breakdown,
    )
```

Add the state and score helpers:

```python
def _zero_axis(dif: float, dea: float) -> MACDZeroAxis:
    if dif > 0.0 and dea > 0.0:
        return MACDZeroAxis.ABOVE
    if dif < 0.0 and dea < 0.0:
        return MACDZeroAxis.BELOW
    return MACDZeroAxis.STRADDLING


def _histogram_trend(previous: float, current: float, tolerance: float) -> MACDHistogramTrend:
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
    dif_series: Sequence[float], dea_series: Sequence[float], first_ready_index: int, lookback: int
) -> tuple[MACDCross, int | None]:
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
    sign = 15.0 if histogram > 0.0 else -15.0 if histogram < 0.0 else 0.0
    axis = 15.0 if zero_axis is MACDZeroAxis.ABOVE else -15.0 if zero_axis is MACDZeroAxis.BELOW else 0.0
    bonus = 0.0 if cross_age is None else 15.0 * (lookback - cross_age) / lookback
    cross_component = bonus if cross is MACDCross.BULLISH else -bonus if cross is MACDCross.BEARISH else 0.0
    trend_component = 0.0
    if trend is MACDHistogramTrend.EXPANDING:
        trend_component = 5.0 if histogram > 0.0 else -5.0 if histogram < 0.0 else 0.0
    elif trend is MACDHistogramTrend.CONTRACTING:
        trend_component = -5.0 if histogram > 0.0 else 5.0 if histogram < 0.0 else 0.0
    raw = 50.0 + sign + axis + cross_component + trend_component
    return MACDScoreBreakdown(sign, axis, cross_component, trend_component, raw, max(0.0, min(100.0, raw)))
```

- [ ] **Step 4: Add golden, pandas-equivalence, true-cross age, expiry, and score-component tests**

```python
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


def test_histogram_trend_uses_absolute_magnitude_and_absolute_tolerance() -> None:
    assert _histogram_trend(-0.10, -0.13, 0.01) is MACDHistogramTrend.EXPANDING
    assert _histogram_trend(0.13, 0.10, 0.01) is MACDHistogramTrend.CONTRACTING
    assert _histogram_trend(-0.10, -0.105, 0.01) is MACDHistogramTrend.FLAT


def test_zero_axis_uses_strict_unrounded_values() -> None:
    assert _zero_axis(1e-15, 2e-15) is MACDZeroAxis.ABOVE
    assert _zero_axis(-1e-15, -2e-15) is MACDZeroAxis.BELOW
    assert _zero_axis(0.0, 1.0) is MACDZeroAxis.STRADDLING


def test_zero_histogram_and_neutral_states_score_exactly_50() -> None:
    breakdown = _score_macd(
        0.0,
        MACDZeroAxis.STRADDLING,
        MACDCross.NONE,
        None,
        MACDHistogramTrend.FLAT,
        3,
    )
    assert breakdown == MACDScoreBreakdown(raw_macd_score=50.0, clamped_macd_score=50.0)


def test_recursive_ema_matches_pandas_adjust_false() -> None:
    import pandas as pd

    closes = rising_closes(50)
    expected = tuple(pd.Series(closes).ewm(span=12, adjust=False).mean())
    actual = ema_recursive(closes, 12)
    assert actual == pytest.approx(expected, rel=1e-12, abs=1e-12)


def test_fixed_close_sequence_matches_golden_macd_values() -> None:
    result = calculate_macd(rising_closes(40), MACDConfig(bar_interval=BarInterval.DAY_1))
    assert result.dif == pytest.approx(0.44707091223128437, rel=0.0, abs=1e-14)
    assert result.dea == pytest.approx(0.4280189018433426, rel=0.0, abs=1e-14)
    assert result.histogram == pytest.approx(0.038104020775883485, rel=0.0, abs=1e-14)


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
```

The three literal values above are the golden fixture. Do not regenerate or round them through API serialization inside the tested implementation.

- [ ] **Step 5: Run focused tests and lint**

Run: `uv run --extra dev pytest tests/test_macd.py -q`

Expected: all `tests/test_macd.py` tests pass.

Run: `uv run --extra dev ruff check src/market_regime_alpha/dividend_t/macd.py tests/test_macd.py`

Expected: `All checks passed!`

- [ ] **Step 6: Commit Stage 1A**

```bash
git add src/market_regime_alpha/dividend_t/macd.py tests/test_macd.py
git commit -m "feat: add reproducible MACD calculation"
```

---

### Task 2: Stage 1B — Closed-Bar, Calendar, Gap, and Point-in-Time Price Preparation

**Files:**
- Create: `src/market_regime_alpha/dividend_t/macd_bars.py`
- Create: `tests/test_macd_bars.py`
- Modify: `src/market_regime_alpha/dividend_t/macd.py`

**Interfaces:**
- Consumes: pandas OHLCV frames, evaluation time, `MACDConfig`, corporate-action rows, expected-session and suspension callbacks.
- Produces: `prepare_macd_bars(...) -> PreparedMACDBars` and `calculate_macd_from_bars(...) -> MACDResult`.

- [ ] **Step 1: Write failing finalized-bar, lunch, missing-bar, and adjustment tests**

```python
import pandas as pd
import pytest

from market_regime_alpha.dividend_t.macd import BarInterval, MACDConfig, MACDDataReason
from market_regime_alpha.dividend_t.macd_bars import CorporateAction, expected_a_share_5m_closes, prepare_macd_bars


def test_unclosed_five_minute_bar_is_excluded() -> None:
    frame = pd.DataFrame(
        {
            "timestamp": ["2026-07-13 09:35:00", "2026-07-13 09:40:00"],
            "close": [10.0, 10.1],
            "bar_final": [True, False],
        }
    )
    prepared = prepare_macd_bars(
        frame,
        config=MACDConfig(bar_interval=BarInterval.MINUTE_5),
        evaluation_time=pd.Timestamp("2026-07-13 09:39:59"),
        corporate_actions=(),
        adjustment_data_complete=True,
        expected_bar_times=(pd.Timestamp("2026-07-13 09:35:00"),),
        suspension_times=frozenset(),
    )
    assert list(prepared.frame["timestamp"]) == [pd.Timestamp("2026-07-13 09:35:00")]
    assert prepared.provisional_excluded_count == 1


def test_expected_missing_bar_is_not_forward_filled() -> None:
    frame = pd.DataFrame({"timestamp": ["2026-07-13 09:35:00", "2026-07-13 09:45:00"], "close": [10.0, 10.2], "bar_final": [True, True]})
    prepared = prepare_macd_bars(
        frame,
        config=MACDConfig(bar_interval=BarInterval.MINUTE_5),
        evaluation_time=pd.Timestamp("2026-07-13 09:45:00"),
        corporate_actions=(),
        adjustment_data_complete=True,
        expected_bar_times=tuple(pd.to_datetime(["2026-07-13 09:35:00", "2026-07-13 09:40:00", "2026-07-13 09:45:00"])),
        suspension_times=frozenset(),
    )
    assert prepared.data_reason is MACDDataReason.EXPECTED_BAR_MISSING
    assert prepared.missing_bar_times == (pd.Timestamp("2026-07-13 09:40:00"),)
    assert len(prepared.frame) == 2


def test_point_in_time_split_adjustment_removes_false_jump() -> None:
    frame = pd.DataFrame({"timestamp": pd.to_datetime(["2026-07-10 15:00", "2026-07-13 15:00"]), "close": [20.0, 10.1], "bar_final": [True, True]})
    action = CorporateAction(effective_time=pd.Timestamp("2026-07-13 09:30"), share_factor=2.0, cash_per_share=0.0)
    prepared = prepare_macd_bars(
        frame,
        config=MACDConfig(bar_interval=BarInterval.DAY_1),
        evaluation_time=pd.Timestamp("2026-07-13 15:00"),
        corporate_actions=(action,),
        adjustment_data_complete=True,
        expected_bar_times=tuple(frame["timestamp"]),
        suspension_times=frozenset(),
    )
    assert list(prepared.adjusted_closes) == pytest.approx([10.0, 10.1])


def test_incomplete_corporate_action_source_blocks_formal_macd() -> None:
    frame = pd.DataFrame(
        {"timestamp": ["2026-07-13 15:00:00"], "close": [10.1], "bar_final": [True]}
    )
    prepared = prepare_macd_bars(
        frame,
        config=MACDConfig(bar_interval=BarInterval.DAY_1),
        evaluation_time=pd.Timestamp("2026-07-13 15:00:00"),
        corporate_actions=(),
        adjustment_data_complete=False,
        expected_bar_times=(pd.Timestamp("2026-07-13 15:00:00"),),
        suspension_times=frozenset(),
    )
    assert prepared.data_reason is MACDDataReason.PRICE_ADJUSTMENT_UNAVAILABLE
    assert prepared.adjusted_closes == ()
```

- [ ] **Step 2: Run and verify failure**

Run: `uv run --extra dev pytest tests/test_macd_bars.py -q`

Expected: collection fails because `macd_bars` is absent.

- [ ] **Step 3: Implement the focused preparation contracts**

```python
# src/market_regime_alpha/dividend_t/macd_bars.py
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Iterable

from market_regime_alpha.dividend_t.macd import MACDConfig, MACDDataReason, MACDResult, calculate_macd, neutral_macd_result


@dataclass(frozen=True)
class CorporateAction:
    effective_time: Any
    share_factor: float = 1.0
    cash_per_share: float = 0.0


@dataclass(frozen=True)
class PreparedMACDBars:
    frame: Any
    adjusted_closes: tuple[float, ...]
    data_reason: MACDDataReason
    missing_bar_times: tuple[Any, ...]
    provisional_excluded_count: int
    last_closed_bar_time: Any | None


def prepare_macd_bars(
    frame: Any,
    *,
    config: MACDConfig,
    evaluation_time: Any,
    corporate_actions: Iterable[CorporateAction],
    adjustment_data_complete: bool,
    expected_bar_times: tuple[Any, ...],
    suspension_times: frozenset[Any],
) -> PreparedMACDBars:
    import pandas as pd

    data = frame.copy()
    data["timestamp"] = pd.to_datetime(data["timestamp"])
    data = data.sort_values("timestamp").reset_index(drop=True)
    evaluation = pd.Timestamp(evaluation_time)
    final_mask = data.get("bar_final", pd.Series(True, index=data.index)).astype(bool)
    closed = data.loc[final_mask & (data["timestamp"] <= evaluation)].copy()
    expected_closed = tuple(pd.Timestamp(time) for time in expected_bar_times if pd.Timestamp(time) <= evaluation)
    missing = tuple(time for time in expected_closed if time not in set(closed["timestamp"]) and time not in suspension_times)
    reason = MACDDataReason.EXPECTED_BAR_MISSING if missing else MACDDataReason.READY
    try:
        if not adjustment_data_complete:
            raise PriceAdjustmentUnavailable("corporate-action source is incomplete")
        adjusted = _point_in_time_adjusted_closes(closed, tuple(corporate_actions), evaluation)
    except PriceAdjustmentUnavailable:
        adjusted = ()
        reason = MACDDataReason.PRICE_ADJUSTMENT_UNAVAILABLE
    return PreparedMACDBars(
        frame=closed,
        adjusted_closes=adjusted,
        data_reason=reason,
        missing_bar_times=missing,
        provisional_excluded_count=int((~final_mask | (data["timestamp"] > evaluation)).sum()),
        last_closed_bar_time=closed["timestamp"].iloc[-1] if len(closed) else None,
    )


def calculate_macd_from_bars(prepared: PreparedMACDBars, config: MACDConfig) -> MACDResult:
    if prepared.data_reason is not MACDDataReason.READY:
        result = neutral_macd_result(config, prepared.data_reason)
    else:
        result = calculate_macd(prepared.adjusted_closes, config)
    return replace(
        result,
        last_closed_bar_time=(str(prepared.last_closed_bar_time) if prepared.last_closed_bar_time is not None else None),
    )


def expected_a_share_5m_closes(day: Any) -> tuple[Any, ...]:
    import pandas as pd

    date = pd.Timestamp(day).normalize()
    morning = pd.date_range(date + pd.Timedelta(hours=9, minutes=35), date + pd.Timedelta(hours=11, minutes=30), freq="5min")
    afternoon = pd.date_range(date + pd.Timedelta(hours=13, minutes=5), date + pd.Timedelta(hours=15), freq="5min")
    return tuple((*morning, *afternoon))
```

Use one explicit adjustment exception and a deterministic prior-bar rebase. An action at `effective_time` transforms every earlier adjusted close as `(close - cash_per_share) / share_factor`; actions after `evaluation_time` are ignored. Multiple effective actions apply in ascending effective-time order:

```python
class PriceAdjustmentUnavailable(ValueError):
    pass


def _point_in_time_adjusted_closes(
    closed: Any,
    actions: tuple[CorporateAction, ...],
    evaluation_time: Any,
) -> tuple[float, ...]:
    import math
    import pandas as pd

    values = [float(value) for value in closed["close"]]
    timestamps = tuple(pd.to_datetime(closed["timestamp"]))
    for action in sorted(actions, key=lambda item: pd.Timestamp(item.effective_time)):
        effective = pd.Timestamp(action.effective_time)
        if effective > evaluation_time:
            continue
        if (
            not math.isfinite(float(action.share_factor))
            or action.share_factor <= 0.0
            or not math.isfinite(float(action.cash_per_share))
        ):
            raise PriceAdjustmentUnavailable("incomplete corporate action")
        for index, timestamp in enumerate(timestamps):
            if timestamp < effective:
                values[index] = (values[index] - action.cash_per_share) / action.share_factor
    if any(not math.isfinite(value) or value <= 0.0 for value in values):
        raise PriceAdjustmentUnavailable("adjusted close must be finite and positive")
    return tuple(values)
```

The `prepare_macd_bars` and `calculate_macd_from_bars` bodies above ensure an unavailable adjustment returns an empty adjusted series plus `PRICE_ADJUSTMENT_UNAVAILABLE`, and that no non-`READY` series reaches EMA evaluation.

- [ ] **Step 4: Add same-bar lookahead and session-boundary tests**

Add these concrete session tests:

```python
def test_a_share_session_has_no_lunch_placeholders() -> None:
    times = expected_a_share_5m_closes(pd.Timestamp("2026-07-13"))
    assert times[0].strftime("%H:%M") == "09:35"
    assert times[-1].strftime("%H:%M") == "15:00"
    assert all(not ("11:30" < item.strftime("%H:%M") < "13:05") for item in times)
    assert len(times) == 48


def test_verified_suspension_is_not_reported_as_gap() -> None:
    missing = pd.Timestamp("2026-07-13 10:00:00")
    expected = expected_a_share_5m_closes(pd.Timestamp("2026-07-13"))
    frame = pd.DataFrame(
        {
            "timestamp": [item for item in expected if item != missing],
            "close": [10.0] * (len(expected) - 1),
            "bar_final": [True] * (len(expected) - 1),
        }
    )
    prepared = prepare_macd_bars(
        frame,
        config=MACDConfig(bar_interval=BarInterval.MINUTE_5),
        evaluation_time=pd.Timestamp("2026-07-13 15:00:00"),
        corporate_actions=(),
        adjustment_data_complete=True,
        expected_bar_times=expected,
        suspension_times=frozenset({missing}),
    )
    assert prepared.data_reason is MACDDataReason.READY
    assert prepared.missing_bar_times == ()


def test_final_bar_requires_finalized_source_status() -> None:
    frame = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2026-07-13 14:55:00", "2026-07-13 15:00:00"]),
            "close": [10.0, 10.1],
            "bar_final": [True, False],
        }
    )
    prepared = prepare_macd_bars(
        frame,
        config=MACDConfig(bar_interval=BarInterval.MINUTE_5),
        evaluation_time=pd.Timestamp("2026-07-13 15:00:00"),
        corporate_actions=(),
        adjustment_data_complete=True,
        expected_bar_times=(pd.Timestamp("2026-07-13 14:55:00"),),
        suspension_times=frozenset(),
    )
    assert prepared.last_closed_bar_time < pd.Timestamp("2026-07-13 15:00:00")
    assert prepared.provisional_excluded_count == 1
```

- [ ] **Step 5: Run focused tests and lint**

Run: `uv run --extra dev pytest tests/test_macd.py tests/test_macd_bars.py -q`

Expected: both files pass.

Run: `uv run --extra dev ruff check src/market_regime_alpha/dividend_t/macd.py src/market_regime_alpha/dividend_t/macd_bars.py tests/test_macd.py tests/test_macd_bars.py`

Expected: `All checks passed!`

- [ ] **Step 6: Commit Stage 1B**

```bash
git add src/market_regime_alpha/dividend_t/macd.py src/market_regime_alpha/dividend_t/macd_bars.py tests/test_macd.py tests/test_macd_bars.py
git commit -m "feat: enforce closed-bar MACD inputs"
```

---

### Task 3: Stage 2 — Neutral Contracts, Technical Inputs, API Metadata, and Snapshot Schema 2

**Files:**
- Modify: `src/market_regime_alpha/dividend_t/models.py`
- Modify: `src/market_regime_alpha/dividend_t/indicators.py`
- Modify: `src/market_regime_alpha/dividend_t/trend_snapshot.py`
- Modify: `src/market_regime_alpha/web/dividend_t_app.py`
- Test: `tests/test_dividend_t_model.py`
- Test: `tests/test_dividend_trend_snapshot.py`
- Test: `tests/test_dividend_t_app.py`

**Interfaces:**
- Consumes: `MACDResult`, distinct daily and 5m `MACDConfig` instances.
- Produces: flat neutral-compatible `TechnicalInputs`, additive API fields, `schema_version=2`, and named `daily_macd_config`/`timing_5m_macd_config` metadata.

- [ ] **Step 1: Write failing neutral-default and schema tests**

```python
def test_technical_inputs_default_to_unavailable_neutral_macd() -> None:
    technical = TechnicalInputs(70, 70, 70, 70)
    assert technical.macd_dif is None
    assert technical.macd_data_ready is False
    assert technical.macd_score == 50.0
    assert technical.macd_cross is MACDCross.NONE


def test_snapshot_schema_2_records_separate_interval_configs() -> None:
    snapshot = build_dividend_trend_snapshot(provider=FakeProvider())
    assert snapshot["schema_version"] == 2
    assert snapshot["model_metadata"]["daily_macd_config"]["bar_interval"] == "1d"
    assert snapshot["model_metadata"]["timing_5m_macd_config"]["bar_interval"] == "5m"
```

- [ ] **Step 2: Run focused tests and verify missing fields fail**

Run: `uv run --extra dev pytest tests/test_dividend_t_model.py tests/test_dividend_trend_snapshot.py tests/test_dividend_t_app.py -q`

Expected: new assertions fail for absent MACD fields and schema 1.

- [ ] **Step 3: Add flat fields and one conversion helper**

```python
@dataclass(frozen=True)
class TechnicalInputs:
    position_quality: float
    volume_structure: float
    trend_quality: float
    intraday_support: float
    chan_score: float = 65.0
    trend_state: TrendState = TrendState.RANGE
    near_support: bool = False
    near_resistance: bool = False
    shrinking_pullback: bool = False
    volume_stalling: bool = False
    intraday_reversal: bool = False
    sector_healthy: bool = True
    chan_structure_type: str = "unknown"
    chan_trend_direction: str = "range"
    chan_divergence_type: str = "none"
    chan_buy_point_type: str = "none"
    chan_sell_point_type: str = "none"
    chan_pivot_low: float | None = None
    chan_pivot_high: float | None = None
    chan_invalid_price: float | None = None
    macd_dif: float | None = None
    macd_dea: float | None = None
    macd_histogram: float | None = None
    macd_histogram_delta: float | None = None
    macd_histogram_trend: MACDHistogramTrend = MACDHistogramTrend.FLAT
    macd_cross: MACDCross = MACDCross.NONE
    macd_cross_age: int | None = None
    macd_zero_axis: MACDZeroAxis = MACDZeroAxis.STRADDLING
    macd_data_ready: bool = False
    macd_data_reason: MACDDataReason = MACDDataReason.INSUFFICIENT_BARS
    macd_score: float = 50.0


def technical_macd_fields(result: MACDResult) -> dict[str, object]:
    if result.provisional:
        raise ValueError("provisional MACD cannot populate TechnicalInputs")
    return {
        "macd_dif": result.dif,
        "macd_dea": result.dea,
        "macd_histogram": result.histogram,
        "macd_histogram_delta": result.histogram_delta,
        "macd_histogram_trend": result.histogram_trend,
        "macd_cross": result.cross,
        "macd_cross_age": result.cross_age,
        "macd_zero_axis": result.zero_axis,
        "macd_data_ready": result.data_ready,
        "macd_data_reason": result.data_reason,
        "macd_score": result.score,
    }


def provisional_macd_payload(result: MACDResult) -> dict[str, object]:
    if not result.provisional:
        raise ValueError("preview payload requires provisional MACD")
    return {
        "provisional": True,
        "bar_interval": result.config.bar_interval.value,
        "dif": result.dif,
        "dea": result.dea,
        "histogram": result.histogram,
        "score": result.score,
    }


def validate_macd_consistency(technical: TechnicalInputs) -> None:
    raw = (technical.macd_dif, technical.macd_dea, technical.macd_histogram)
    if technical.macd_data_ready:
        if technical.macd_data_reason is not MACDDataReason.READY or any(value is None for value in raw):
            raise ValueError("ready MACD requires READY reason and DIF/DEA/Histogram")
        if not 0.0 <= technical.macd_score <= 100.0:
            raise ValueError("macd score must be in [0, 100]")
    else:
        if technical.macd_data_reason is MACDDataReason.READY:
            raise ValueError("unready MACD cannot use READY reason")
        if technical.macd_score != 50.0 or technical.macd_cross is not MACDCross.NONE or technical.macd_cross_age is not None:
            raise ValueError("unready MACD must use neutral score and cross")
        if any(value is not None for value in (*raw, technical.macd_histogram_delta)):
            raise ValueError("unready MACD raw fields must be None")
```

Call `validate_macd_consistency()` from the `TechnicalInputs` construction boundary. `infer_technical_inputs` accepts an explicit config and prepared formal result; it must not infer interval from timestamps.

- [ ] **Step 4: Add additive API and snapshot metadata**

Serialize enum values as strings and confirmation sets as sorted lists. Old `/api/evaluate` payloads without MACD fields construct the unavailable neutral state. If MACD values are supplied, require an explicit interval and consistency validation.

```python
def serialize_macd_config(config: MACDConfig) -> dict[str, object]:
    return {
        "bar_interval": config.bar_interval.value,
        "fast_period": config.fast_period,
        "slow_period": config.slow_period,
        "signal_period": config.signal_period,
        "cross_lookback_bars": config.cross_lookback_bars,
        "closed_bars_only": config.closed_bars_only,
        "price_field": config.price_field.value,
        "price_adjustment_mode": config.price_adjustment_mode.value,
        "histogram_tolerance_mode": config.histogram_tolerance_mode.value,
        "histogram_flat_tolerance": config.histogram_flat_tolerance,
        "algorithm_version": config.algorithm_version,
    }


def snapshot_macd_metadata(daily: MACDConfig, timing_5m: MACDConfig) -> dict[str, object]:
    if daily.bar_interval is not BarInterval.DAY_1 or timing_5m.bar_interval is not BarInterval.MINUTE_5:
        raise ValueError("snapshot MACD configs must be explicitly 1d and 5m")
    return {
        "macd_contract_version": MACD_CONTRACT_VERSION,
        "daily_macd_config": serialize_macd_config(daily),
        "timing_5m_macd_config": serialize_macd_config(timing_5m),
    }


def serialize_macd_result_metadata(result: MACDResult) -> dict[str, object]:
    return {
        "macd_contract_version": MACD_CONTRACT_VERSION,
        "macd_algorithm_version": result.config.algorithm_version,
        "bar_interval": result.config.bar_interval.value,
        "closed_bars_only": result.config.closed_bars_only,
        "price_field": result.config.price_field.value,
        "price_adjustment_mode": result.config.price_adjustment_mode.value,
        "histogram_tolerance_mode": result.config.histogram_tolerance_mode.value,
        "histogram_flat_tolerance": result.config.histogram_flat_tolerance,
        "provisional": result.provisional,
        "last_closed_bar_time": result.last_closed_bar_time,
        "bar_contract_version": result.bar_contract_version,
        "price_adjustment_version": result.price_adjustment_version,
        "data_quality_rule_version": result.data_quality_rule_version,
    }
```

In the Pydantic request model, a model-level validator calls `validate_macd_consistency(technical)`. If every MACD request field is absent, construct the neutral defaults; if any raw MACD value is present and `bar_interval` is absent, raise `ValueError("bar_interval is required with MACD values")`.

- [ ] **Step 5: Run regression tests and verify legacy decisions remain equal**

Run: `uv run --extra dev pytest tests/test_dividend_t_model.py tests/test_dividend_trend_snapshot.py tests/test_dividend_t_app.py -q`

Expected: all focused tests pass and pre-existing signal assertions remain unchanged.

Run: `uv run --extra dev ruff check src/market_regime_alpha/dividend_t/models.py src/market_regime_alpha/dividend_t/indicators.py src/market_regime_alpha/dividend_t/trend_snapshot.py src/market_regime_alpha/web/dividend_t_app.py tests/test_dividend_t_model.py tests/test_dividend_trend_snapshot.py tests/test_dividend_t_app.py`

Expected: `All checks passed!`

- [ ] **Step 6: Commit Stage 2**

```bash
git add src/market_regime_alpha/dividend_t/models.py src/market_regime_alpha/dividend_t/indicators.py src/market_regime_alpha/dividend_t/trend_snapshot.py src/market_regime_alpha/web/dividend_t_app.py tests/test_dividend_t_model.py tests/test_dividend_trend_snapshot.py tests/test_dividend_t_app.py
git commit -m "feat: expose neutral MACD model metadata"
```

---

### Task 4: Stage 3A — SignalIntent, Setup Mapping, Current-Bar Confirmations, and Candidate Trace

**Files:**
- Create: `src/market_regime_alpha/dividend_t/signal_intent.py`
- Create: `tests/test_signal_intent.py`
- Modify: `src/market_regime_alpha/dividend_t/models.py`
- Modify: `src/market_regime_alpha/dividend_t/strategy.py`
- Test: `tests/test_dividend_t_model.py`

**Interfaces:**
- Consumes: generator-owned `PrimarySetupCode`, current decision bar time, confirmation sets.
- Produces: `CandidateSignal`, `DecisionTrace`, `select_simplified_candidate(...)`, and `intent_for_setup(...)`.

- [ ] **Step 1: Write failing mapping, NONE restriction, and expired-confirmation tests**

```python
import pytest

from market_regime_alpha.dividend_t.signal_intent import (
    CandidateContractError,
    EntryConfirmation,
    PrimarySetupCode,
    SignalIntent,
    intent_for_setup,
    validate_candidate,
)


def test_primary_setup_uniquely_maps_to_intent() -> None:
    assert intent_for_setup(PrimarySetupCode.PULLBACK_LOW_BUY) is SignalIntent.MEAN_REVERSION_T
    assert intent_for_setup(PrimarySetupCode.THIRD_BUY_FOLLOW) is SignalIntent.TREND_FOLLOWING
    assert intent_for_setup(PrimarySetupCode.STRUCTURE_BREAK) is SignalIntent.RISK_REDUCTION
    assert intent_for_setup(PrimarySetupCode.BUILD_BASE) is SignalIntent.BASE_ACCUMULATION


def test_every_primary_setup_has_one_non_none_intent() -> None:
    assert set(SETUP_INTENT_MAP) == set(PrimarySetupCode)
    assert all(intent is not SignalIntent.NONE for intent in SETUP_INTENT_MAP.values())


def test_live_buy_candidate_cannot_use_none_intent() -> None:
    candidate = candidate_fixture(signal=Signal.BUY_T, intent=SignalIntent.NONE)
    with pytest.raises(CandidateContractError, match="UNKNOWN_SIGNAL_INTENT"):
        validate_candidate(candidate, strict=True)


def test_confirmation_must_belong_to_current_decision_bar() -> None:
    candidate = candidate_fixture(
        decision_bar_time="2026-07-13 10:05:00",
        confirmation_bar_time="2026-07-13 10:00:00",
        entry_confirmations=frozenset({EntryConfirmation.SUPPORT_HOLD}),
    )
    with pytest.raises(CandidateContractError, match="current decision bar"):
        validate_candidate(candidate, strict=True)


def test_primary_breakout_setup_wins_over_companion_pullback_flags() -> None:
    score = ScoreBreakdown(80, 4, 4, 4, 2, 80, 80, 80, 65)
    retreat = RetreatInputs(4, 4, 3, 2)
    technical = TechnicalInputs(
        80,
        80,
        80,
        80,
        chan_structure_type="breakout",
        near_support=True,
        shrinking_pullback=True,
    )
    candidate = select_simplified_candidate(
        score=score,
        retreat=retreat,
        technical=technical,
        position=PositionState(),
        decision_bar_time="2026-07-13 15:00:00",
    )
    assert candidate.primary_setup_code is PrimarySetupCode.BREAKOUT_CONFIRMED
    assert candidate.candidate_signal_intent is SignalIntent.TREND_FOLLOWING


def candidate_fixture(
    *,
    signal: Signal = Signal.BUY_T,
    intent: SignalIntent = SignalIntent.MEAN_REVERSION_T,
    decision_bar_time: str = "2026-07-13 10:05:00",
    confirmation_bar_time: str | None = None,
    entry_confirmations: frozenset[EntryConfirmation] = frozenset({EntryConfirmation.NONE}),
) -> CandidateSignal:
    return CandidateSignal(
        candidate_signal=signal,
        candidate_setup_code=PrimarySetupCode.PULLBACK_LOW_BUY,
        primary_setup_code=PrimarySetupCode.PULLBACK_LOW_BUY,
        candidate_signal_intent=intent,
        decision_bar_time=decision_bar_time,
        confirmation_bar_time=confirmation_bar_time or decision_bar_time,
        entry_confirmations=entry_confirmations,
        exit_confirmations=frozenset({ExitConfirmation.NONE}),
    )
```

- [ ] **Step 2: Run and verify module absence**

Run: `uv run --extra dev pytest tests/test_signal_intent.py -q`

Expected: collection fails because `signal_intent` is absent.

- [ ] **Step 3: Implement enums, mapping, candidate, and trace contracts**

```python
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import math

SIGNAL_INTENT_MAPPING_VERSION = "signal-intent-map-v1"
CONFIRMATION_RULE_VERSION = "confirmation-rules-v1"
MACD_POLICY_VERSION = "signal-intent-macd-v1"


class SignalIntent(str, Enum):
    NONE = "NONE"
    MEAN_REVERSION_T = "MEAN_REVERSION_T"
    TREND_FOLLOWING = "TREND_FOLLOWING"
    RISK_REDUCTION = "RISK_REDUCTION"
    BASE_ACCUMULATION = "BASE_ACCUMULATION"


class EntryConfirmation(str, Enum):
    NONE = "NONE"
    INTRADAY_REVERSAL = "INTRADAY_REVERSAL"
    CHAN_BUY_POINT = "CHAN_BUY_POINT"
    SUPPORT_HOLD = "SUPPORT_HOLD"
    VWAP_RECLAIM = "VWAP_RECLAIM"
    SELLING_PRESSURE_EXHAUSTION = "SELLING_PRESSURE_EXHAUSTION"


class ExitConfirmation(str, Enum):
    NONE = "NONE"
    VOLUME_STALLING = "VOLUME_STALLING"
    RESISTANCE_REJECTION = "RESISTANCE_REJECTION"
    CHAN_SELL_POINT = "CHAN_SELL_POINT"
    TOP_DIVERGENCE = "TOP_DIVERGENCE"
    MOMENTUM_EXHAUSTION = "MOMENTUM_EXHAUSTION"


class CandidateContractError(ValueError):
    pass


@dataclass(frozen=True)
class CandidateSignal:
    candidate_signal: Signal | None
    candidate_setup_code: PrimarySetupCode | None
    primary_setup_code: PrimarySetupCode | None
    candidate_signal_intent: SignalIntent
    decision_bar_time: str
    confirmation_bar_time: str
    entry_confirmations: frozenset[EntryConfirmation]
    exit_confirmations: frozenset[ExitConfirmation]
    candidate_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class DecisionTrace:
    candidate_signal: Signal | None
    candidate_signal_intent: SignalIntent
    candidate_setup_code: str | None
    primary_setup_code: str | None
    entry_confirmations: tuple[str, ...]
    exit_confirmations: tuple[str, ...]
    candidate_reasons: tuple[str, ...]
    final_signal: Signal
    macd_policy_applied: bool = False
    contract_trace_codes: tuple[str, ...] = ()
    signal_downgraded: bool = False
    downgrade_source: str | None = None
    downgrade_reason: str | None = None
    original_suggested_trade_pct: float | None = None
    sizing_multiplier: float = 1.0
    adjusted_suggested_trade_pct: float | None = None
    sizing_adjustment_source: str | None = None
    sizing_adjustment_applied: bool = False
```

Define every setup and its single mapping in one constant:

```python
class PrimarySetupCode(str, Enum):
    PULLBACK_LOW_BUY = "pullback_low_buy"
    VWAP_RECLAIM = "vwap_reclaim"
    INTRADAY_REVERSAL = "intraday_reversal"
    RANGE_LOW_BUY = "range_low_buy"
    PRESSURE_SELL_T = "pressure_sell_t"
    REVERSE_T_SELL = "reverse_t_sell"
    FORCE_REVERSAL_PROBE = "force_reversal_probe"
    TREND_FOLLOW = "trend_follow"
    TREND_PULLBACK_FOLLOW = "trend_pullback_follow"
    BREAKOUT_CONFIRMED = "breakout_confirmed"
    THIRD_BUY_FOLLOW = "third_buy_follow"
    STRONG_LAUNCH_FOLLOW = "strong_launch_follow"
    ATTENTION_FEEDBACK_FOLLOW = "attention_feedback_follow"
    CLEAR = "clear"
    REDUCE = "reduce"
    STOP_T = "stop_t"
    THIRD_SELL = "third_sell"
    STRUCTURE_BREAK = "structure_break"
    CHAN_SELL_RISK = "chan_sell_risk"
    TOP_DIVERGENCE_RISK = "top_divergence_risk"
    BUILD_BASE = "build_base"


SETUP_INTENT_MAP = {
    PrimarySetupCode.PULLBACK_LOW_BUY: SignalIntent.MEAN_REVERSION_T,
    PrimarySetupCode.VWAP_RECLAIM: SignalIntent.MEAN_REVERSION_T,
    PrimarySetupCode.INTRADAY_REVERSAL: SignalIntent.MEAN_REVERSION_T,
    PrimarySetupCode.RANGE_LOW_BUY: SignalIntent.MEAN_REVERSION_T,
    PrimarySetupCode.PRESSURE_SELL_T: SignalIntent.MEAN_REVERSION_T,
    PrimarySetupCode.REVERSE_T_SELL: SignalIntent.MEAN_REVERSION_T,
    PrimarySetupCode.FORCE_REVERSAL_PROBE: SignalIntent.MEAN_REVERSION_T,
    PrimarySetupCode.TREND_FOLLOW: SignalIntent.TREND_FOLLOWING,
    PrimarySetupCode.TREND_PULLBACK_FOLLOW: SignalIntent.TREND_FOLLOWING,
    PrimarySetupCode.BREAKOUT_CONFIRMED: SignalIntent.TREND_FOLLOWING,
    PrimarySetupCode.THIRD_BUY_FOLLOW: SignalIntent.TREND_FOLLOWING,
    PrimarySetupCode.STRONG_LAUNCH_FOLLOW: SignalIntent.TREND_FOLLOWING,
    PrimarySetupCode.ATTENTION_FEEDBACK_FOLLOW: SignalIntent.TREND_FOLLOWING,
    PrimarySetupCode.CLEAR: SignalIntent.RISK_REDUCTION,
    PrimarySetupCode.REDUCE: SignalIntent.RISK_REDUCTION,
    PrimarySetupCode.STOP_T: SignalIntent.RISK_REDUCTION,
    PrimarySetupCode.THIRD_SELL: SignalIntent.RISK_REDUCTION,
    PrimarySetupCode.STRUCTURE_BREAK: SignalIntent.RISK_REDUCTION,
    PrimarySetupCode.CHAN_SELL_RISK: SignalIntent.RISK_REDUCTION,
    PrimarySetupCode.TOP_DIVERGENCE_RISK: SignalIntent.RISK_REDUCTION,
    PrimarySetupCode.BUILD_BASE: SignalIntent.BASE_ACCUMULATION,
}


def intent_for_setup(setup: PrimarySetupCode) -> SignalIntent:
    return SETUP_INTENT_MAP[setup]


@dataclass(frozen=True)
class CandidateValidation:
    policy_applicable: bool
    trace_codes: tuple[str, ...] = ()


def validate_candidate(candidate: CandidateSignal, *, strict: bool) -> CandidateValidation:
    has_live_signal = candidate.candidate_signal is not None and candidate.candidate_signal is not Signal.HOLD
    errors: list[str] = []
    if has_live_signal and candidate.candidate_signal_intent is SignalIntent.NONE:
        errors.append("UNKNOWN_SIGNAL_INTENT")
    if has_live_signal and candidate.primary_setup_code is None:
        errors.append("UNKNOWN_PRIMARY_SETUP")
    if candidate.primary_setup_code is not None:
        mapped = intent_for_setup(candidate.primary_setup_code)
        if candidate.candidate_signal_intent is not mapped:
            errors.append("SETUP_INTENT_MISMATCH")
    if candidate.candidate_setup_code is not candidate.primary_setup_code:
        errors.append("candidate_setup_code must equal primary_setup_code in v1")
    confirmations = {*candidate.entry_confirmations, *candidate.exit_confirmations}
    has_real_confirmation = any(item.value != "NONE" for item in confirmations)
    if has_real_confirmation and candidate.confirmation_bar_time != candidate.decision_bar_time:
        errors.append("confirmation must belong to current decision bar")
    if EntryConfirmation.NONE in candidate.entry_confirmations and len(candidate.entry_confirmations) > 1:
        errors.append("NONE cannot accompany entry confirmations")
    if ExitConfirmation.NONE in candidate.exit_confirmations and len(candidate.exit_confirmations) > 1:
        errors.append("NONE cannot accompany exit confirmations")
    if errors and strict:
        raise CandidateContractError("; ".join(errors))
    return CandidateValidation(policy_applicable=not errors, trace_codes=tuple(errors))
```

`validate_candidate(candidate, strict=False)` returns `policy_applicable=False` plus `UNKNOWN_SIGNAL_INTENT` for an unknown legacy candidate; the caller copies `trace_codes` into DecisionTrace and preserves the unmodified candidate signal.

- [ ] **Step 4: Replace simplified boolean-only candidate generation without changing behavior**

Split candidate selection from final evaluation:

```python
def select_simplified_candidate(
    *, score: ScoreBreakdown, retreat: RetreatInputs, technical: TechnicalInputs, position: PositionState, decision_bar_time: str
) -> CandidateSignal:
    if score.F_score < 50:
        return candidate_for(Signal.CLEAR, PrimarySetupCode.CLEAR, technical, decision_bar_time)
    if score.F_score < 55:
        return candidate_for(Signal.REDUCE, PrimarySetupCode.REDUCE, technical, decision_bar_time)
    if _stop_t_reasons(score.F_score, technical, position):
        setup = PrimarySetupCode.STRUCTURE_BREAK if technical.chan_structure_type == "breakdown" else PrimarySetupCode.STOP_T
        return candidate_for(Signal.STOP_T, setup, technical, decision_bar_time)
    if _can_buy_t(score, retreat, technical):
        if technical.chan_buy_point_type == "buy3":
            setup = PrimarySetupCode.THIRD_BUY_FOLLOW
        elif technical.chan_structure_type == "breakout":
            setup = PrimarySetupCode.BREAKOUT_CONFIRMED
        elif technical.intraday_reversal:
            setup = PrimarySetupCode.INTRADAY_REVERSAL
        else:
            setup = PrimarySetupCode.PULLBACK_LOW_BUY
        return candidate_for(Signal.BUY_T, setup, technical, decision_bar_time)
    if _should_sell_t(retreat, technical):
        setup = PrimarySetupCode.TOP_DIVERGENCE_RISK if technical.chan_divergence_type == "top" else PrimarySetupCode.PRESSURE_SELL_T
        return candidate_for(Signal.SELL_T, setup, technical, decision_bar_time)
    if position.symbol_position_pct < min(base_position_limit(score.F_score), 0.20) and score.F_score >= 70:
        return candidate_for(Signal.BUILD_BASE, PrimarySetupCode.BUILD_BASE, technical, decision_bar_time)
    return no_candidate(decision_bar_time)
```

Define `candidate_for` and `no_candidate` in the same module so every live candidate receives intent during construction:

```python
def candidate_for(
    signal: Signal,
    setup: PrimarySetupCode,
    technical: TechnicalInputs,
    decision_bar_time: str,
) -> CandidateSignal:
    entry = current_entry_confirmations(technical)
    exit_ = current_exit_confirmations(technical)
    return CandidateSignal(
        candidate_signal=signal,
        candidate_setup_code=setup,
        primary_setup_code=setup,
        candidate_signal_intent=intent_for_setup(setup),
        decision_bar_time=decision_bar_time,
        confirmation_bar_time=decision_bar_time,
        entry_confirmations=entry or frozenset({EntryConfirmation.NONE}),
        exit_confirmations=exit_ or frozenset({ExitConfirmation.NONE}),
    )


def no_candidate(decision_bar_time: str) -> CandidateSignal:
    return CandidateSignal(
        candidate_signal=None,
        candidate_setup_code=None,
        primary_setup_code=None,
        candidate_signal_intent=SignalIntent.NONE,
        decision_bar_time=decision_bar_time,
        confirmation_bar_time=decision_bar_time,
        entry_confirmations=frozenset({EntryConfirmation.NONE}),
        exit_confirmations=frozenset({ExitConfirmation.NONE}),
    )
```

For the simplified path, use only confirmations its current technical snapshot can prove:

```python
def current_entry_confirmations(technical: TechnicalInputs) -> frozenset[EntryConfirmation]:
    values: set[EntryConfirmation] = set()
    if technical.intraday_reversal:
        values.add(EntryConfirmation.INTRADAY_REVERSAL)
    if technical.chan_buy_point_type in BUY_POINTS:
        values.add(EntryConfirmation.CHAN_BUY_POINT)
    if technical.near_support and (technical.shrinking_pullback or technical.intraday_reversal):
        values.add(EntryConfirmation.SUPPORT_HOLD)
    return frozenset(values)


def current_exit_confirmations(technical: TechnicalInputs) -> frozenset[ExitConfirmation]:
    values: set[ExitConfirmation] = set()
    if technical.volume_stalling:
        values.add(ExitConfirmation.VOLUME_STALLING)
    if technical.near_resistance and technical.volume_stalling:
        values.add(ExitConfirmation.RESISTANCE_REJECTION)
    if technical.chan_sell_point_type in SELL_POINTS:
        values.add(ExitConfirmation.CHAN_SELL_POINT)
    if technical.chan_divergence_type == "top":
        values.add(ExitConfirmation.TOP_DIVERGENCE)
    return frozenset(values)
```

Assign setup and intent in the winning branch. A third-buy/breakout branch remains trend following even if a pullback companion flag is true. Risk branches return risk intent. `BUILD_BASE` returns base accumulation. No-candidate HOLD uses `SignalIntent.NONE`.

- [ ] **Step 5: Run behavior-parity and contract tests**

Run: `uv run --extra dev pytest tests/test_signal_intent.py tests/test_dividend_t_model.py -q`

Expected: all tests pass; existing BUY_T, SELL_T, STOP_T, CLEAR, and BUILD_BASE outcomes remain unchanged under baseline.

- [ ] **Step 6: Commit Stage 3A**

```bash
git add src/market_regime_alpha/dividend_t/signal_intent.py src/market_regime_alpha/dividend_t/models.py src/market_regime_alpha/dividend_t/strategy.py tests/test_signal_intent.py tests/test_dividend_t_model.py
git commit -m "refactor: emit explicit signal intents"
```

---

### Task 5: Stage 3B — Structured 5-Minute Candidates and Removal of Duplicate Classification

**Files:**
- Modify: `src/market_regime_alpha/dividend_t/cosco_timing_types.py`
- Modify: `src/market_regime_alpha/dividend_t/cosco_timing_manual.py`
- Modify: `src/market_regime_alpha/dividend_t/cosco_timing.py`
- Modify: `src/market_regime_alpha/dividend_t/buy_point_quality.py`
- Modify: `src/market_regime_alpha/dividend_t/backtest.py`
- Test: `tests/test_cosco_timing.py`
- Test: `tests/test_buy_point_quality.py`
- Test: `tests/test_dividend_t_backtest.py`

**Interfaces:**
- Consumes: Task 4 candidate and setup enums.
- Produces: `ManualCandidateDecision`, immutable layered actions, copied setup/intent fields in `BacktestSignal`.

- [ ] **Step 1: Write failing tests for branch-owned setup and immutable layers**

```python
def test_breakout_branch_emits_trend_following_primary_setup() -> None:
    snapshot = CoscoTimingEngine().evaluate(_bars_for_breakout_buy())
    assert snapshot.decision_trace.primary_setup_code == "breakout_confirmed"
    assert snapshot.decision_trace.candidate_signal_intent == "TREND_FOLLOWING"
    assert snapshot.decision_trace.raw_candidate_action == "BREAKOUT_BUY_TIMING"
    assert snapshot.decision_trace.final_action == "WATCH_BREAKOUT_NEXT_DAY"


def test_backtest_copies_intent_without_reclassification() -> None:
    candidate = ManualCandidateDecision(
        action="BUY_T",
        candidate_signal=Signal.BUY_T,
        candidate_setup_code=PrimarySetupCode.PULLBACK_LOW_BUY,
        primary_setup_code=PrimarySetupCode.PULLBACK_LOW_BUY,
        signal_intent=SignalIntent.MEAN_REVERSION_T,
        decision_bar_time="2026-07-13 10:05:00",
        confirmation_bar_time="2026-07-13 10:05:00",
        entry_confirmations=frozenset({EntryConfirmation.SUPPORT_HOLD}),
        exit_confirmations=frozenset({ExitConfirmation.NONE}),
        reasons=(),
        warnings=(),
    )
    fields = candidate_trace_fields(candidate)
    assert fields["primary_setup_code"] == "pullback_low_buy"
    assert fields["signal_intent"] == "MEAN_REVERSION_T"
```

- [ ] **Step 2: Run and verify missing structured fields fail**

Run: `uv run --extra dev pytest tests/test_cosco_timing.py tests/test_buy_point_quality.py tests/test_dividend_t_backtest.py -q`

Expected: new trace/setup assertions fail.

- [ ] **Step 3: Replace `_manual_action` tuple with a structured return**

```python
@dataclass(frozen=True)
class ManualCandidateDecision:
    action: str
    candidate_signal: Signal | None
    candidate_setup_code: PrimarySetupCode | None
    primary_setup_code: PrimarySetupCode | None
    signal_intent: SignalIntent
    decision_bar_time: str
    confirmation_bar_time: str
    entry_confirmations: frozenset[EntryConfirmation]
    exit_confirmations: frozenset[ExitConfirmation]
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class TimingDecisionTrace:
    candidate_signal: Signal | None = None
    candidate_setup_code: str | None = None
    primary_setup_code: str | None = None
    candidate_signal_intent: SignalIntent = SignalIntent.NONE
    entry_confirmations: tuple[str, ...] = ()
    exit_confirmations: tuple[str, ...] = ()
    raw_candidate_action: str = "WAIT"
    quality_filtered_action: str = "WAIT"
    macd_filtered_action: str = "WAIT"
    freshness_filtered_action: str = "WAIT"
    final_action: str = "WAIT"
    final_signal: Signal = Signal.HOLD
    signal_downgraded: bool = False
    downgrade_source: str | None = None
    downgrade_reason: str | None = None
    original_suggested_trade_pct: float | None = None
    macd_sizing_multiplier: float = 1.0
    adjusted_suggested_trade_pct: float | None = None
    sizing_adjustment_source: str | None = None
    macd_sizing_applied: bool = False
    macd_policy_applied: bool = False
    macd_contract_version: str = MACD_CONTRACT_VERSION
    macd_algorithm_version: str = MACD_ALGORITHM_VERSION
    macd_policy_version: str = MACD_POLICY_VERSION
    signal_intent_mapping_version: str = SIGNAL_INTENT_MAPPING_VERSION
    confirmation_rule_version: str = CONFIRMATION_RULE_VERSION
```

Every return branch constructs this type directly. Wait-only branches use no primary setup and `NONE`. Risk branches use `RISK_REDUCTION`. Recompute confirmations from the current finalized bar only.

Use one constructor at each winning branch so action/setup competition remains inside `_manual_action`:

```python
def manual_candidate(
    action: str,
    candidate_signal: Signal | None,
    setup: PrimarySetupCode | None,
    *,
    decision_bar_time: str,
    entry_confirmations: frozenset[EntryConfirmation] = frozenset({EntryConfirmation.NONE}),
    exit_confirmations: frozenset[ExitConfirmation] = frozenset({ExitConfirmation.NONE}),
    reasons: tuple[str, ...] = (),
    warnings: tuple[str, ...] = (),
) -> ManualCandidateDecision:
    intent = SignalIntent.NONE if setup is None else intent_for_setup(setup)
    return ManualCandidateDecision(
        action=action,
        candidate_signal=candidate_signal,
        candidate_setup_code=setup,
        primary_setup_code=setup,
        signal_intent=intent,
        decision_bar_time=decision_bar_time,
        confirmation_bar_time=decision_bar_time,
        entry_confirmations=entry_confirmations,
        exit_confirmations=exit_confirmations,
        reasons=reasons,
        warnings=warnings,
    )
```

Copy those fields into snapshot/backtest types through one serialization helper; no consumer reclassifies them:

```python
def candidate_trace_fields(candidate: ManualCandidateDecision) -> dict[str, object]:
    return {
        "candidate_signal": candidate.candidate_signal.value if candidate.candidate_signal else None,
        "candidate_setup_code": candidate.candidate_setup_code.value if candidate.candidate_setup_code else None,
        "primary_setup_code": candidate.primary_setup_code.value if candidate.primary_setup_code else None,
        "signal_intent": candidate.signal_intent.value,
        "decision_bar_time": candidate.decision_bar_time,
        "confirmation_bar_time": candidate.confirmation_bar_time,
        "entry_confirmations": tuple(sorted(item.value for item in candidate.entry_confirmations)),
        "exit_confirmations": tuple(sorted(item.value for item in candidate.exit_confirmations)),
    }


def policy_candidate_from_manual(candidate: ManualCandidateDecision) -> CandidateSignal:
    return CandidateSignal(
        candidate_signal=candidate.candidate_signal,
        candidate_setup_code=candidate.candidate_setup_code,
        primary_setup_code=candidate.primary_setup_code,
        candidate_signal_intent=candidate.signal_intent,
        decision_bar_time=candidate.decision_bar_time,
        confirmation_bar_time=candidate.confirmation_bar_time,
        entry_confirmations=candidate.entry_confirmations,
        exit_confirmations=candidate.exit_confirmations,
        candidate_reasons=candidate.reasons,
    )
```

Every `_manual_action` winning branch passes both its detailed action and canonical signal explicitly—for example `manual_candidate("BREAKOUT_BUY_TIMING", Signal.BUY_T, PrimarySetupCode.BREAKOUT_CONFIRMED, decision_bar_time=str(final_bar_time))`. Wait-only branches pass `candidate_signal=None` and `setup=None`. The adapter above copies fields only; it never parses `action`.

- [ ] **Step 4: Preserve layered actions and derive reporting subtype from primary setup**

Record `raw_candidate_action`, `quality_filtered_action`, `macd_filtered_action`, `freshness_filtered_action`, and `final_action` without overwriting earlier fields. Change `classify_buy_point_subtype` to accept `primary_setup_code` and use a stable reporting map; remove backtest reclassification from feature booleans.

```python
BUY_POINT_SUBTYPE_BY_SETUP = {
    PrimarySetupCode.PULLBACK_LOW_BUY: "pullback",
    PrimarySetupCode.VWAP_RECLAIM: "vwap_reclaim",
    PrimarySetupCode.INTRADAY_REVERSAL: "reversal",
    PrimarySetupCode.RANGE_LOW_BUY: "range_low",
    PrimarySetupCode.TREND_FOLLOW: "trend_follow",
    PrimarySetupCode.TREND_PULLBACK_FOLLOW: "trend_pullback",
    PrimarySetupCode.BREAKOUT_CONFIRMED: "breakout",
    PrimarySetupCode.THIRD_BUY_FOLLOW: "third_buy",
    PrimarySetupCode.STRONG_LAUNCH_FOLLOW: "strong_launch",
    PrimarySetupCode.ATTENTION_FEEDBACK_FOLLOW: "attention_feedback",
}


def classify_buy_point_subtype(primary_setup_code: PrimarySetupCode | None) -> str | None:
    return BUY_POINT_SUBTYPE_BY_SETUP.get(primary_setup_code)
```

- [ ] **Step 5: Run focused regression tests and mypy**

Run: `uv run --extra dev pytest tests/test_cosco_timing.py tests/test_buy_point_quality.py tests/test_dividend_t_backtest.py -q`

Expected: all tests pass and existing final action assertions remain unchanged.

Run: `uv run --extra dev mypy`

Expected: `Success: no issues found`.

- [ ] **Step 6: Commit Stage 3B**

```bash
git add src/market_regime_alpha/dividend_t/cosco_timing_types.py src/market_regime_alpha/dividend_t/cosco_timing_manual.py src/market_regime_alpha/dividend_t/cosco_timing.py src/market_regime_alpha/dividend_t/buy_point_quality.py src/market_regime_alpha/dividend_t/backtest.py tests/test_cosco_timing.py tests/test_buy_point_quality.py tests/test_dividend_t_backtest.py
git commit -m "refactor: preserve timing candidate semantics"
```

---

### Task 6: Stage 4 — Normalized Technical Score and Dual-Use Diagnostics

**Files:**
- Modify: `src/market_regime_alpha/dividend_t/scoring.py`
- Modify: `src/market_regime_alpha/dividend_t/models.py`
- Modify: `src/market_regime_alpha/dividend_t/strategy.py`
- Modify: `src/market_regime_alpha/dividend_t/backtest.py`
- Test: `tests/test_dividend_t_model.py`
- Test: `tests/test_dividend_t_backtest.py`

**Interfaces:**
- Consumes: ready/unready MACD fields and `score_weight`.
- Produces: `TechnicalScoreDiagnostics`, legacy and weighted scores, pre-policy candidate counterfactuals.

- [ ] **Step 1: Write failing scale, weight, and dual-diagnostic tests**

```python
def test_all_neutral_technical_components_score_50() -> None:
    technical = TechnicalInputs(50, 50, 50, 50, chan_score=50, macd_data_ready=True, macd_score=50)
    diagnostics = technical_score_diagnostics(technical, macd_weight=0.15)
    assert diagnostics.technical_score_without_macd == 50.0
    assert diagnostics.technical_score_with_macd == 50.0


def test_zero_weight_is_digit_equal_to_legacy_score() -> None:
    technical = TechnicalInputs(82, 71, 66, 59, chan_score=74, macd_data_ready=True, macd_score=3)
    assert technical_score_diagnostics(technical, macd_weight=0).technical_score_with_macd == technical_score(technical)


def test_out_of_range_component_is_normalized_before_weighting() -> None:
    technical = TechnicalInputs(150, 0, 0, 0, chan_score=0, macd_data_ready=True, macd_score=100)
    diagnostics = technical_score_diagnostics(technical, macd_weight=0.15)
    assert 0.0 <= diagnostics.technical_score_with_macd <= 100.0


def test_score_and_policy_effect_flags_are_independent() -> None:
    candidate = no_candidate("2026-07-13 15:00:00")
    event = MACDDualUseDiagnostics(
        technical_score_without_macd=50.0,
        technical_score_with_macd=55.0,
        candidate_without_macd_score=candidate,
        candidate_with_macd_score=candidate,
        macd_score_changed_candidate=True,
        macd_policy_changed_candidate=False,
    )
    assert event.macd_score_changed_candidate is True
    assert event.macd_policy_changed_candidate is False
```

- [ ] **Step 2: Run and verify missing diagnostics fail**

Run: `uv run --extra dev pytest tests/test_dividend_t_model.py tests/test_dividend_t_backtest.py -q`

Expected: new diagnostic imports or attributes fail.

- [ ] **Step 3: Implement normalized scoring and exact legacy path**

```python
TECHNICAL_SCORE_VERSION = "technical-score-macd-v1"


LEGACY_TECHNICAL_WEIGHTS: tuple[tuple[str, float], ...] = (
    ("position_quality", 0.28),
    ("volume_structure", 0.20),
    ("trend_quality", 0.17),
    ("intraday_support", 0.15),
    ("chan_score", 0.20),
)


@dataclass(frozen=True)
class TechnicalScoreDiagnostics:
    technical_score_without_macd: float
    technical_score_with_macd: float
    effective_weights: tuple[tuple[str, float], ...]


def normalize_score(value: float) -> float:
    if not math.isfinite(float(value)):
        raise ValueError("technical score components must be finite")
    return clamp(float(value), 0.0, 100.0)


def technical_score(inputs: TechnicalInputs) -> float:
    return clamp(
        sum(normalize_score(getattr(inputs, name)) * weight for name, weight in LEGACY_TECHNICAL_WEIGHTS),
        0.0,
        100.0,
    )


def technical_score_diagnostics(inputs: TechnicalInputs, *, macd_weight: float) -> TechnicalScoreDiagnostics:
    if not math.isfinite(float(macd_weight)) or not 0.0 <= macd_weight <= 1.0:
        raise ValueError("macd_weight must be finite and in [0, 1]")
    legacy = technical_score(inputs)
    if not inputs.macd_data_ready or macd_weight == 0:
        return TechnicalScoreDiagnostics(legacy, legacy, LEGACY_TECHNICAL_WEIGHTS)
    scaled = tuple((name, weight * (1.0 - macd_weight)) for name, weight in LEGACY_TECHNICAL_WEIGHTS)
    weights = (*scaled, ("macd_score", macd_weight))
    weighted = sum(normalize_score(getattr(inputs, name)) * weight for name, weight in weights)
    if not math.isclose(sum(weight for _, weight in weights), 1.0, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError("technical score weights must sum to 1")
    return TechnicalScoreDiagnostics(legacy, clamp(weighted, 0.0, 100.0), weights)


def build_score_breakdown(
    fundamental: FundamentalInputs,
    retreat: RetreatInputs,
    technical: TechnicalInputs,
    *,
    macd_weight: float = 0.0,
) -> ScoreBreakdown:
    diagnostics = technical_score_diagnostics(technical, macd_weight=macd_weight)
    return _build_score_breakdown_with_t_score(
        fundamental,
        retreat,
        technical,
        t_score=diagnostics.technical_score_with_macd,
    )


def _build_score_breakdown_with_t_score(
    fundamental: FundamentalInputs,
    retreat: RetreatInputs,
    technical: TechnicalInputs,
    *,
    t_score: float,
) -> ScoreBreakdown:
    f_score = fundamental_score(fundamental)
    r_score, k_score = retreat_score(retreat)
    total_score = clamp(0.35 * f_score + 0.35 * r_score + 0.30 * t_score, 0.0, 100.0)
    return ScoreBreakdown(
        F_score=round(f_score, 2),
        G_score=round(normalize_score(retreat.market_attention * 20.0) / 20.0, 2),
        Z_score=round(normalize_score(retreat.upside_certainty * 20.0) / 20.0, 2),
        K_score=round(k_score, 2),
        S_score=round(normalize_score(retreat.sell_pressure * 20.0) / 20.0, 2),
        R_score=round(r_score, 2),
        T_score=round(t_score, 2),
        total_score=round(total_score, 2),
        C_score=round(normalize_score(technical.chan_score), 2),
    )
```

- [ ] **Step 4: Add research-only pure candidate comparison**

Run the same pure selector twice before policy and persist the result without mutating the production candidate:

```python
@dataclass(frozen=True)
class MACDDualUseDiagnostics:
    technical_score_without_macd: float
    technical_score_with_macd: float
    candidate_without_macd_score: CandidateSignal
    candidate_with_macd_score: CandidateSignal
    macd_score_changed_candidate: bool
    macd_policy_changed_candidate: bool = False


def compare_candidates_with_macd_score(
    selector: Callable[[ScoreBreakdown], CandidateSignal],
    *,
    fundamental: FundamentalInputs,
    retreat: RetreatInputs,
    technical: TechnicalInputs,
    macd_weight: float,
) -> MACDDualUseDiagnostics:
    diagnostics = technical_score_diagnostics(technical, macd_weight=macd_weight)
    without_score = _build_score_breakdown_with_t_score(
        fundamental,
        retreat,
        technical,
        t_score=diagnostics.technical_score_without_macd,
    )
    with_score = _build_score_breakdown_with_t_score(
        fundamental,
        retreat,
        technical,
        t_score=diagnostics.technical_score_with_macd,
    )
    without = selector(without_score)
    with_macd = selector(with_score)
    return MACDDualUseDiagnostics(
        technical_score_without_macd=diagnostics.technical_score_without_macd,
        technical_score_with_macd=diagnostics.technical_score_with_macd,
        candidate_without_macd_score=without,
        candidate_with_macd_score=with_macd,
        macd_score_changed_candidate=(without != with_macd),
    )
```

After policy, derive the second flag without mutating the frozen pre-policy record:

```python
def with_policy_effect(
    diagnostics: MACDDualUseDiagnostics,
    policy: PolicyDecision,
    *,
    weighted_original_pct: float,
) -> MACDDualUseDiagnostics:
    weighted_signal = diagnostics.candidate_with_macd_score.candidate_signal or Signal.HOLD
    changed = (
        policy.final_signal is not weighted_signal
        or policy.adjusted_suggested_trade_pct != weighted_original_pct
    )
    return replace(diagnostics, macd_policy_changed_candidate=changed)
```

Persist all six fields in `BacktestSignal`/research events; the baseline decision still uses the legacy selector result.

- [ ] **Step 5: Run focused tests and full scoring regression**

Run: `uv run --extra dev pytest tests/test_dividend_t_model.py tests/test_dividend_t_backtest.py -q`

Expected: all pass, including digit-equal zero-weight output.

- [ ] **Step 6: Commit Stage 4**

```bash
git add src/market_regime_alpha/dividend_t/scoring.py src/market_regime_alpha/dividend_t/models.py src/market_regime_alpha/dividend_t/strategy.py src/market_regime_alpha/dividend_t/backtest.py tests/test_dividend_t_model.py tests/test_dividend_t_backtest.py
git commit -m "feat: add experimental MACD technical score"
```

---

### Task 7: Stage 5A — Shared Asymmetric Policy and Simplified-Strategy Sizing Owner

**Files:**
- Modify: `src/market_regime_alpha/dividend_t/signal_intent.py`
- Modify: `src/market_regime_alpha/dividend_t/strategy.py`
- Test: `tests/test_signal_intent.py`
- Test: `tests/test_dividend_t_model.py`

**Interfaces:**
- Consumes: explicit candidate, MACD result fields, `MACDPolicyConfig`, original percentage.
- Produces: `apply_macd_policy(...) -> PolicyDecision` with one adjusted percentage and full trace.

- [ ] **Step 1: Write failing trend, mean-reversion, risk, base, and sizing tests**

```python
@pytest.mark.parametrize("axis", [MACDZeroAxis.BELOW, MACDZeroAxis.STRADDLING])
def test_trend_buy_bearish_cross_in_configured_axis_downgrades(axis: MACDZeroAxis) -> None:
    decision = apply_macd_policy(
        trend_buy_candidate(),
        ready_macd(cross=MACDCross.BEARISH, zero_axis=axis),
        experimental_macd_policy(),
        original_suggested_trade_pct=0.20,
    )
    assert decision.final_signal is Signal.HOLD
    assert decision.trace.downgrade_source == "MACD_CONFLICT"


def test_trend_buy_bearish_cross_above_is_not_blocked() -> None:
    decision = apply_macd_policy(
        trend_buy_candidate(),
        ready_macd(cross=MACDCross.BEARISH, zero_axis=MACDZeroAxis.ABOVE),
        experimental_macd_policy(),
        original_suggested_trade_pct=0.20,
    )
    assert decision.final_signal is Signal.BUY_T
    assert decision.adjusted_suggested_trade_pct == 0.20


def test_unready_macd_and_disabled_gate_preserve_candidate() -> None:
    candidate = trend_buy_candidate()
    unready = neutral_macd_result(MACDConfig(bar_interval=BarInterval.DAY_1), MACDDataReason.INSUFFICIENT_BARS)
    assert apply_macd_policy(candidate, unready, experimental_macd_policy(), original_suggested_trade_pct=0.20).final_signal is Signal.BUY_T
    assert apply_macd_policy(candidate, expanding_bearish_macd(), baseline_macd_policy(), original_suggested_trade_pct=0.20).final_signal is Signal.BUY_T


def test_compatible_unknown_intent_preserves_candidate_and_records_trace() -> None:
    unknown = replace(
        trend_buy_candidate(),
        candidate_setup_code=None,
        primary_setup_code=None,
        candidate_signal_intent=SignalIntent.NONE,
    )
    decision = apply_macd_policy(
        unknown,
        expanding_bearish_macd(),
        experimental_macd_policy(),
        original_suggested_trade_pct=0.20,
        strict_contracts=False,
    )
    assert decision.final_signal is Signal.BUY_T
    assert "UNKNOWN_SIGNAL_INTENT" in decision.trace.contract_trace_codes


def test_confirmed_mean_reversion_buy_resizes_once() -> None:
    candidate = mean_reversion_buy_candidate(confirmations={EntryConfirmation.SUPPORT_HOLD})
    decision = apply_macd_policy(candidate, expanding_bearish_macd(), experimental_macd_policy(), original_suggested_trade_pct=0.20)
    assert decision.final_signal is Signal.BUY_T
    assert decision.adjusted_suggested_trade_pct == 0.10
    assert decision.trace.original_suggested_trade_pct == 0.20
    with pytest.raises(CandidateContractError, match="DUPLICATE_SIZING_ADJUSTMENT"):
        apply_macd_policy(candidate, expanding_bearish_macd(), experimental_macd_policy(), original_suggested_trade_pct=0.20, prior_trace=decision.trace)


def test_compatible_duplicate_sizing_keeps_first_adjustment() -> None:
    candidate = mean_reversion_buy_candidate(confirmations={EntryConfirmation.SUPPORT_HOLD})
    first = apply_macd_policy(candidate, expanding_bearish_macd(), experimental_macd_policy(), original_suggested_trade_pct=0.20)
    second = apply_macd_policy(
        candidate,
        expanding_bearish_macd(),
        experimental_macd_policy(),
        original_suggested_trade_pct=0.20,
        prior_trace=first.trace,
        strict_contracts=False,
    )
    assert second.adjusted_suggested_trade_pct == 0.10
    assert "DUPLICATE_SIZING_ADJUSTMENT" in second.trace.contract_trace_codes


def test_unaccepted_mean_reversion_confirmation_does_not_release_trade() -> None:
    candidate = mean_reversion_buy_candidate(confirmations={EntryConfirmation.SELLING_PRESSURE_EXHAUSTION})
    decision = apply_macd_policy(candidate, expanding_bearish_macd(), experimental_macd_policy(), original_suggested_trade_pct=0.20)
    assert decision.final_signal is Signal.HOLD
    assert decision.trace.downgrade_source == "MACD_CONFIRMATION_REQUIRED"


def test_zero_multiplier_converts_signal_to_hold_and_preserves_original_size() -> None:
    candidate = mean_reversion_buy_candidate(confirmations={EntryConfirmation.SUPPORT_HOLD})
    config = replace(experimental_macd_policy(), mean_reversion_size_multiplier=0.0)
    decision = apply_macd_policy(candidate, expanding_bearish_macd(), config, original_suggested_trade_pct=0.20)
    assert decision.final_signal is Signal.HOLD
    assert decision.trace.original_suggested_trade_pct == 0.20
    assert decision.trace.downgrade_source == "MACD_SIZING_TO_ZERO"


def test_confirmed_mean_reversion_sell_resizes_against_expanding_bullish_macd() -> None:
    candidate = candidate_for_test(
        Signal.SELL_T,
        PrimarySetupCode.PRESSURE_SELL_T,
        exits=frozenset({ExitConfirmation.RESISTANCE_REJECTION}),
    )
    decision = apply_macd_policy(
        candidate,
        expanding_bullish_macd(),
        experimental_macd_policy(),
        original_suggested_trade_pct=0.20,
    )
    assert decision.final_signal is Signal.SELL_T
    assert decision.adjusted_suggested_trade_pct == 0.10


@pytest.mark.parametrize("signal", [Signal.CLEAR, Signal.REDUCE, Signal.STOP_T])
def test_risk_reduction_is_never_changed(signal: Signal) -> None:
    decision = apply_macd_policy(risk_candidate(signal), expanding_bullish_macd(), experimental_macd_policy(), original_suggested_trade_pct=0.20)
    assert decision.final_signal is signal
    assert decision.adjusted_suggested_trade_pct == 0.20


def test_base_accumulation_is_diagnosed_but_not_gated() -> None:
    decision = apply_macd_policy(base_candidate(), expanding_bearish_macd(), experimental_macd_policy(), original_suggested_trade_pct=0.05)
    assert decision.final_signal is Signal.BUILD_BASE
    assert decision.adjusted_suggested_trade_pct == 0.05


def candidate_for_test(
    signal: Signal,
    setup: PrimarySetupCode,
    *,
    entries: frozenset[EntryConfirmation] = frozenset({EntryConfirmation.NONE}),
    exits: frozenset[ExitConfirmation] = frozenset({ExitConfirmation.NONE}),
) -> CandidateSignal:
    return CandidateSignal(
        candidate_signal=signal,
        candidate_setup_code=setup,
        primary_setup_code=setup,
        candidate_signal_intent=intent_for_setup(setup),
        decision_bar_time="2026-07-13 15:00:00",
        confirmation_bar_time="2026-07-13 15:00:00",
        entry_confirmations=entries,
        exit_confirmations=exits,
    )


def trend_buy_candidate() -> CandidateSignal:
    return candidate_for_test(Signal.BUY_T, PrimarySetupCode.BREAKOUT_CONFIRMED)


def mean_reversion_buy_candidate(*, confirmations: set[EntryConfirmation]) -> CandidateSignal:
    return candidate_for_test(
        Signal.BUY_T,
        PrimarySetupCode.PULLBACK_LOW_BUY,
        entries=frozenset(confirmations),
    )


def risk_candidate(signal: Signal) -> CandidateSignal:
    setup = {
        Signal.CLEAR: PrimarySetupCode.CLEAR,
        Signal.REDUCE: PrimarySetupCode.REDUCE,
        Signal.STOP_T: PrimarySetupCode.STOP_T,
    }[signal]
    return candidate_for_test(signal, setup)


def base_candidate() -> CandidateSignal:
    return candidate_for_test(Signal.BUILD_BASE, PrimarySetupCode.BUILD_BASE)


def ready_macd(
    *,
    cross: MACDCross,
    zero_axis: MACDZeroAxis,
    histogram: float = -0.2,
    trend: MACDHistogramTrend = MACDHistogramTrend.EXPANDING,
) -> MACDResult:
    dif, dea = {
        MACDZeroAxis.ABOVE: (0.10, 0.05),
        MACDZeroAxis.BELOW: (-0.10, -0.05),
        MACDZeroAxis.STRADDLING: (0.10, -0.05),
    }[zero_axis]
    return MACDResult(
        config=MACDConfig(bar_interval=BarInterval.DAY_1),
        dif=dif,
        dea=dea,
        histogram=histogram,
        histogram_delta=-0.03,
        histogram_trend=trend,
        cross=cross,
        cross_age=0,
        zero_axis=zero_axis,
        data_ready=True,
        data_reason=MACDDataReason.READY,
        score=25.0,
        score_breakdown=MACDScoreBreakdown(raw_macd_score=25.0, clamped_macd_score=25.0),
    )


def expanding_bearish_macd() -> MACDResult:
    return ready_macd(cross=MACDCross.BEARISH, zero_axis=MACDZeroAxis.BELOW)


def expanding_bullish_macd() -> MACDResult:
    return ready_macd(
        cross=MACDCross.BULLISH,
        zero_axis=MACDZeroAxis.ABOVE,
        histogram=0.2,
    )
```

- [ ] **Step 2: Run and verify missing policy fails**

Run: `uv run --extra dev pytest tests/test_signal_intent.py tests/test_dividend_t_model.py -q`

Expected: new policy tests fail for missing functions.

- [ ] **Step 3: Implement validated profiles and shared policy**

```python
DEFAULT_ACCEPTED_ENTRY_CONFIRMATIONS = frozenset(
    {
        EntryConfirmation.INTRADAY_REVERSAL,
        EntryConfirmation.CHAN_BUY_POINT,
        EntryConfirmation.SUPPORT_HOLD,
        EntryConfirmation.VWAP_RECLAIM,
    }
)
DEFAULT_ACCEPTED_EXIT_CONFIRMATIONS = frozenset(
    {
        ExitConfirmation.VOLUME_STALLING,
        ExitConfirmation.RESISTANCE_REJECTION,
        ExitConfirmation.CHAN_SELL_POINT,
        ExitConfirmation.TOP_DIVERGENCE,
    }
)


@dataclass(frozen=True)
class MACDPolicyConfig:
    score_weight: float = 0.0
    conflict_gate_enabled: bool = False
    mean_reversion_size_multiplier: float = 0.5
    minimum_executable_trade_pct: float = 0.0
    trend_buy_block_bearish_cross: bool = True
    trend_buy_block_zero_axis_states: frozenset[MACDZeroAxis] = frozenset({MACDZeroAxis.BELOW, MACDZeroAxis.STRADDLING})
    mean_reversion_buy_accepted_confirmations: frozenset[EntryConfirmation] = DEFAULT_ACCEPTED_ENTRY_CONFIRMATIONS
    mean_reversion_sell_accepted_confirmations: frozenset[ExitConfirmation] = DEFAULT_ACCEPTED_EXIT_CONFIRMATIONS
    policy_version: str = MACD_POLICY_VERSION

    def __post_init__(self) -> None:
        for name in ("score_weight", "mean_reversion_size_multiplier", "minimum_executable_trade_pct"):
            value = float(getattr(self, name))
            if not math.isfinite(value) or not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be finite and in [0, 1]")
        for name in ("conflict_gate_enabled", "trend_buy_block_bearish_cross"):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be bool")
        if any(not isinstance(item, MACDZeroAxis) for item in self.trend_buy_block_zero_axis_states):
            raise ValueError("trend buy zero-axis states must be MACDZeroAxis values")
        if not self.mean_reversion_buy_accepted_confirmations or any(
            not isinstance(item, EntryConfirmation) or item is EntryConfirmation.NONE
            for item in self.mean_reversion_buy_accepted_confirmations
        ):
            raise ValueError("accepted entry confirmations must be non-empty and exclude NONE")
        if not self.mean_reversion_sell_accepted_confirmations or any(
            not isinstance(item, ExitConfirmation) or item is ExitConfirmation.NONE
            for item in self.mean_reversion_sell_accepted_confirmations
        ):
            raise ValueError("accepted exit confirmations must be non-empty and exclude NONE")
        if not self.policy_version.strip():
            raise ValueError("policy_version must be non-empty")


def baseline_macd_policy() -> MACDPolicyConfig:
    return MACDPolicyConfig(score_weight=0.0, conflict_gate_enabled=False)


def experimental_macd_policy() -> MACDPolicyConfig:
    return MACDPolicyConfig(score_weight=0.15, conflict_gate_enabled=True)
```

Add the policy result and branch implementation. Factor trace construction into `_policy_decision` so every return preserves the original candidate fields:

```python
@dataclass(frozen=True)
class PolicyDecision:
    final_signal: Signal
    adjusted_suggested_trade_pct: float
    trace: DecisionTrace


def apply_macd_policy(
    candidate: CandidateSignal,
    macd: MACDResult,
    config: MACDPolicyConfig,
    *,
    original_suggested_trade_pct: float,
    effective_minimum_trade_pct: float = 0.0,
    prior_trace: DecisionTrace | None = None,
    strict_contracts: bool = True,
) -> PolicyDecision:
    signal = candidate.candidate_signal or Signal.HOLD
    validation = validate_candidate(candidate, strict=strict_contracts)
    if not validation.policy_applicable:
        return _policy_decision(
            candidate,
            signal,
            original_suggested_trade_pct,
            original_suggested_trade_pct,
            1.0,
            contract_trace_codes=validation.trace_codes,
        )
    if prior_trace is not None and prior_trace.sizing_adjustment_applied:
        if strict_contracts:
            raise CandidateContractError("DUPLICATE_SIZING_ADJUSTMENT")
        return PolicyDecision(
            final_signal=prior_trace.final_signal,
            adjusted_suggested_trade_pct=prior_trace.adjusted_suggested_trade_pct or 0.0,
            trace=replace(
                prior_trace,
                contract_trace_codes=(*prior_trace.contract_trace_codes, "DUPLICATE_SIZING_ADJUSTMENT"),
            ),
        )
    if not macd.data_ready or not config.conflict_gate_enabled:
        return _policy_decision(candidate, signal, original_suggested_trade_pct, original_suggested_trade_pct, 1.0)
    if candidate.candidate_signal_intent in {SignalIntent.RISK_REDUCTION, SignalIntent.BASE_ACCUMULATION, SignalIntent.NONE}:
        return _policy_decision(candidate, signal, original_suggested_trade_pct, original_suggested_trade_pct, 1.0)
    trend_conflict = (
        candidate.candidate_signal_intent is SignalIntent.TREND_FOLLOWING
        and signal is Signal.BUY_T
        and config.trend_buy_block_bearish_cross
        and macd.cross is MACDCross.BEARISH
        and macd.zero_axis in config.trend_buy_block_zero_axis_states
    )
    if trend_conflict:
        return _policy_decision(
            candidate,
            Signal.HOLD,
            original_suggested_trade_pct,
            0.0,
            0.0,
            downgrade_source="MACD_CONFLICT",
            policy_applied=True,
        )
    if candidate.candidate_signal_intent is not SignalIntent.MEAN_REVERSION_T:
        return _policy_decision(
            candidate,
            signal,
            original_suggested_trade_pct,
            original_suggested_trade_pct,
            1.0,
            policy_applied=True,
        )
    opposing_buy = (
        signal is Signal.BUY_T
        and macd.cross is MACDCross.BEARISH
        and macd.zero_axis in {MACDZeroAxis.BELOW, MACDZeroAxis.STRADDLING}
        and macd.histogram is not None
        and macd.histogram < 0.0
        and macd.histogram_trend is MACDHistogramTrend.EXPANDING
    )
    opposing_sell = (
        signal is Signal.SELL_T
        and macd.cross is MACDCross.BULLISH
        and macd.zero_axis in {MACDZeroAxis.ABOVE, MACDZeroAxis.STRADDLING}
        and macd.histogram is not None
        and macd.histogram > 0.0
        and macd.histogram_trend is MACDHistogramTrend.EXPANDING
    )
    accepted = False
    if opposing_buy:
        accepted = bool(candidate.entry_confirmations & config.mean_reversion_buy_accepted_confirmations)
    elif opposing_sell:
        accepted = bool(candidate.exit_confirmations & config.mean_reversion_sell_accepted_confirmations)
    else:
        return _policy_decision(
            candidate,
            signal,
            original_suggested_trade_pct,
            original_suggested_trade_pct,
            1.0,
            policy_applied=True,
        )
    if not accepted:
        return _policy_decision(
            candidate,
            Signal.HOLD,
            original_suggested_trade_pct,
            0.0,
            0.0,
            downgrade_source="MACD_CONFIRMATION_REQUIRED",
            policy_applied=True,
        )
    adjusted = original_suggested_trade_pct * config.mean_reversion_size_multiplier
    minimum = max(config.minimum_executable_trade_pct, effective_minimum_trade_pct)
    if abs(adjusted) <= minimum:
        return _policy_decision(
            candidate,
            Signal.HOLD,
            original_suggested_trade_pct,
            0.0,
            config.mean_reversion_size_multiplier,
            downgrade_source="MACD_SIZING_TO_ZERO",
            policy_applied=True,
        )
    return _policy_decision(
        candidate,
        signal,
        original_suggested_trade_pct,
        adjusted,
        config.mean_reversion_size_multiplier,
        sizing_source="MACD_MEAN_REVERSION",
        policy_applied=True,
    )
```

Use this helper for every return:

```python
def _policy_decision(
    candidate: CandidateSignal,
    final_signal: Signal,
    original_pct: float,
    adjusted_pct: float,
    multiplier: float,
    *,
    downgrade_source: str | None = None,
    sizing_source: str | None = None,
    contract_trace_codes: tuple[str, ...] = (),
    policy_applied: bool = False,
) -> PolicyDecision:
    trace = DecisionTrace(
        candidate_signal=candidate.candidate_signal,
        candidate_signal_intent=candidate.candidate_signal_intent,
        candidate_setup_code=candidate.candidate_setup_code.value if candidate.candidate_setup_code else None,
        primary_setup_code=candidate.primary_setup_code.value if candidate.primary_setup_code else None,
        entry_confirmations=tuple(sorted(item.value for item in candidate.entry_confirmations)),
        exit_confirmations=tuple(sorted(item.value for item in candidate.exit_confirmations)),
        candidate_reasons=candidate.candidate_reasons,
        contract_trace_codes=contract_trace_codes,
        final_signal=final_signal,
        macd_policy_applied=policy_applied,
        signal_downgraded=final_signal is not (candidate.candidate_signal or Signal.HOLD),
        downgrade_source=downgrade_source,
        downgrade_reason=downgrade_source,
        original_suggested_trade_pct=original_pct,
        sizing_multiplier=multiplier,
        adjusted_suggested_trade_pct=adjusted_pct,
        sizing_adjustment_source=sizing_source,
        sizing_adjustment_applied=sizing_source is not None,
    )
    return PolicyDecision(final_signal, adjusted_pct, trace)
```

The test must assert that blocked and sizing-to-zero traces still retain the original percentage.

- [ ] **Step 4: Integrate one simplified-strategy policy call after candidate sizing**

Construct `OrderIntent` only after policy. Baseline profile is the default constructor argument. Preserve original/adjusted percentages in trace.

```python
def finalize_simplified_candidate(
    candidate: CandidateSignal,
    *,
    macd: MACDResult,
    original_suggested_trade_pct: float,
    policy_config: MACDPolicyConfig = MACDPolicyConfig(),
    effective_minimum_trade_pct: float = 0.0,
) -> PolicyDecision:
    decision = apply_macd_policy(
        candidate,
        macd,
        policy_config,
        original_suggested_trade_pct=original_suggested_trade_pct,
        effective_minimum_trade_pct=effective_minimum_trade_pct,
    )
    if decision.final_signal is Signal.HOLD:
        return decision
    # The caller constructs OrderIntent from decision.final_signal and
    # decision.adjusted_suggested_trade_pct only after this function returns.
    return decision
```

Replace every direct pre-policy `OrderIntent(...)` construction in `strategy.py` with this one finalization call and one post-policy constructor. The default `MACDPolicyConfig()` remains score weight zero and gate disabled.

- [ ] **Step 5: Run tests and verify production-default parity**

Run: `uv run --extra dev pytest tests/test_signal_intent.py tests/test_dividend_t_model.py tests/test_dividend_t_app.py -q`

Expected: all pass; app tests show unchanged default decisions.

- [ ] **Step 6: Commit Stage 5A without enabling production policy**

```bash
git add src/market_regime_alpha/dividend_t/signal_intent.py src/market_regime_alpha/dividend_t/strategy.py tests/test_signal_intent.py tests/test_dividend_t_model.py tests/test_dividend_t_app.py
git commit -m "feat: add intent-aware MACD policy"
```

---

### Task 8: Stage 5B — Detailed-Engine Policy Trace and Single Backtest Sizing Owner

**Files:**
- Modify: `src/market_regime_alpha/dividend_t/cosco_timing_types.py`
- Modify: `src/market_regime_alpha/dividend_t/cosco_timing.py`
- Modify: `src/market_regime_alpha/dividend_t/backtest.py`
- Modify: `backtesting/run_cosco_dividend_t_backtest.py`
- Modify: `backtesting/run_dividend_watchlist_backtest.py`
- Test: `tests/test_cosco_timing.py`
- Test: `tests/test_dividend_t_backtest.py`

**Interfaces:**
- Consumes: policy decision multiplier and detailed candidate trace.
- Produces: layered timing trace plus exactly one multiplier consumption in `_signal_target_position_pct` or a new focused target-delta helper.

- [ ] **Step 1: Write failing one-owner, minimum-lot, disabled-policy, and hard-stop tests**

```python
def test_backtest_consumes_macd_multiplier_once_at_target_delta() -> None:
    target = _macd_adjusted_target_delta_pct(
        signal_intent=SignalIntent.MEAN_REVERSION_T,
        macd_sizing_multiplier=0.5,
        macd_sizing_applied=False,
        original_delta_pct=0.20,
        effective_minimum_trade_pct=0.01,
    )
    assert target.adjusted_delta_pct == 0.10
    assert target.sizing_applied is True
    with pytest.raises(ValueError, match="DUPLICATE_SIZING_ADJUSTMENT"):
        _macd_adjusted_target_delta_pct(
            signal_intent=SignalIntent.MEAN_REVERSION_T,
            macd_sizing_multiplier=0.5,
            macd_sizing_applied=True,
            original_delta_pct=0.20,
            effective_minimum_trade_pct=0.01,
        )


def test_risk_reduction_target_delta_ignores_macd_multiplier() -> None:
    target = _macd_adjusted_target_delta_pct(
        signal_intent=SignalIntent.RISK_REDUCTION,
        macd_sizing_multiplier=0.0,
        macd_sizing_applied=False,
        original_delta_pct=-0.20,
        effective_minimum_trade_pct=0.01,
    )
    assert target.adjusted_delta_pct == -0.20
    assert target.sizing_applied is False


def test_execution_time_must_follow_candidate_bar_close() -> None:
    with pytest.raises(ValueError, match="same-bar execution is forbidden"):
        validate_execution_after_signal("2026-07-13 10:00:00", "2026-07-13 10:00:00")
    validate_execution_after_signal("2026-07-13 10:00:00", "2026-07-13 10:05:00")
```

- [ ] **Step 2: Run and verify missing sizing helper fails**

Run: `uv run --extra dev pytest tests/test_cosco_timing.py tests/test_dividend_t_backtest.py -q`

Expected: new helper/field assertions fail.

- [ ] **Step 3: Apply policy after quality filters and before freshness, without percentage math**

The advisory engine records the intended multiplier and `macd_filtered_action`. It sets exact percentages to `None` because it lacks account position. Multiplier zero may immediately produce HOLD; non-zero effective-minimum resolution waits for the position-aware backtest/execution boundary. Preserve layer ordering through one immutable helper:

```python
def record_macd_layer(trace: TimingDecisionTrace, policy: PolicyDecision) -> TimingDecisionTrace:
    action = trace.quality_filtered_action
    if policy.final_signal is Signal.HOLD and trace.candidate_signal not in {None, Signal.HOLD}:
        action = "WAIT_MACD_POLICY"
    return replace(
        trace,
        macd_filtered_action=action,
        final_signal=policy.final_signal,
        macd_sizing_multiplier=policy.trace.sizing_multiplier,
        macd_sizing_applied=False,
        macd_policy_applied=policy.trace.macd_policy_applied,
        downgrade_source=policy.trace.downgrade_source,
        downgrade_reason=policy.trace.downgrade_reason,
        sizing_adjustment_source=policy.trace.sizing_adjustment_source,
    )
```

Call it exactly once after `quality_filtered_action` is fixed and before freshness evaluation. Freshness may change only `freshness_filtered_action` and `final_action`; it must not rewrite the raw, quality, or MACD layer.

- [ ] **Step 4: Implement the one target-delta sizing owner**

```python
@dataclass(frozen=True)
class MACDAdjustedTarget:
    adjusted_delta_pct: float
    sizing_applied: bool
    downgrade_source: str | None


def validate_execution_after_signal(candidate_bar_close_time: str, execution_time: str) -> None:
    if pd.Timestamp(execution_time) <= pd.Timestamp(candidate_bar_close_time):
        raise ValueError("same-bar execution is forbidden")


def _macd_adjusted_target_delta_pct(
    *,
    signal_intent: SignalIntent,
    macd_sizing_multiplier: float,
    macd_sizing_applied: bool,
    original_delta_pct: float,
    effective_minimum_trade_pct: float,
) -> MACDAdjustedTarget:
    if signal_intent is not SignalIntent.MEAN_REVERSION_T or macd_sizing_multiplier == 1.0:
        return MACDAdjustedTarget(original_delta_pct, False, None)
    if macd_sizing_applied:
        raise ValueError("DUPLICATE_SIZING_ADJUSTMENT")
    adjusted = original_delta_pct * macd_sizing_multiplier
    if abs(adjusted) <= effective_minimum_trade_pct:
        return MACDAdjustedTarget(0.0, True, "MACD_SIZING_TO_ZERO")
    return MACDAdjustedTarget(adjusted, True, None)
```

Call this helper once after original target delta is known and before lot rounding. Execution constraints cap or block the adjusted amount but never multiply again.
Call `validate_execution_after_signal(signal.timestamp, str(execution["timestamp"]))` at the shared execution entry before reading execution-bar OHLCV, so real and counterfactual paths enforce the same strict ordering.

- [ ] **Step 5: Verify baseline CLI defaults and focused tests**

Run: `uv run --extra dev pytest tests/test_cosco_timing.py tests/test_dividend_t_backtest.py -q`

Expected: all pass.

Run: `PYTHONPATH=src uv run --extra dev python backtesting/run_cosco_dividend_t_backtest.py --help | rg "macd-profile"`

Expected: help lists `baseline`, `score-only`, `policy-only`, and `full`; default shown by parser code remains `baseline`.

- [ ] **Step 6: Commit Stage 5B without enabling production policy**

```bash
git add src/market_regime_alpha/dividend_t/cosco_timing_types.py src/market_regime_alpha/dividend_t/cosco_timing.py src/market_regime_alpha/dividend_t/backtest.py backtesting/run_cosco_dividend_t_backtest.py backtesting/run_dividend_watchlist_backtest.py tests/test_cosco_timing.py tests/test_dividend_t_backtest.py
git commit -m "feat: trace MACD policy in timing backtests"
```

---

### Task 9: Stage 6A — Canonical Cache Identity and Four Experiment Profiles

**Files:**
- Create: `src/market_regime_alpha/dividend_t/macd_experiments.py`
- Create: `tests/test_macd_experiments.py`
- Modify: `src/market_regime_alpha/dividend_t/backtest.py`
- Modify: `backtesting/run_cosco_dividend_t_backtest.py`
- Modify: `backtesting/run_dividend_watchlist_backtest.py`

**Interfaces:**
- Consumes: MACD config, policy config, interval/price/confirmation versions, execution config.
- Produces: `canonical_experiment_config`, `experiment_config_hash`, cache schema version, and four named profiles.

- [ ] **Step 1: Write failing cache sensitivity and canonical-set tests**

```python
def test_every_result_affecting_field_changes_experiment_hash() -> None:
    base = experiment_config_fixture()
    mutations = (
        replace(base, macd_contract_version="macd-data-v2"),
        replace(base, macd_algorithm_version="macd-v2"),
        replace(base, macd_policy_version="signal-intent-macd-v2"),
        replace(base, technical_score_version="technical-score-macd-v2"),
        replace(base, signal_intent_mapping_version="signal-intent-map-v2"),
        replace(base, confirmation_rule_version="confirmation-rules-v2"),
        replace(base, bar_contract_version="closed-bars-a-share-v2"),
        replace(base, price_adjustment_version="point-in-time-adjust-v2"),
        replace(base, data_quality_rule_version="macd-data-quality-v2"),
        replace(base, execution_config_hash="execution-v2"),
        replace(base, fast_period=10),
        replace(base, slow_period=30),
        replace(base, signal_period=7),
        replace(base, cross_lookback_bars=4),
        replace(base, bar_interval=BarInterval.DAY_1),
        replace(base, closed_bars_only=False),
        replace(base, histogram_flat_tolerance=0.001),
        replace(base, score_weight=0.15),
        replace(base, conflict_gate_enabled=True),
        replace(base, mean_reversion_size_multiplier=0.25),
        replace(base, minimum_executable_trade_pct=0.01),
        replace(base, trend_buy_block_bearish_cross=False),
        replace(base, trend_buy_block_zero_axis_states=frozenset({MACDZeroAxis.BELOW})),
        replace(base, mean_reversion_buy_accepted_confirmations=frozenset({EntryConfirmation.VWAP_RECLAIM})),
        replace(base, mean_reversion_sell_accepted_confirmations=frozenset({ExitConfirmation.VOLUME_STALLING})),
    )
    hashes = {experiment_config_hash(item) for item in (base, *mutations)}
    assert len(hashes) == len(mutations) + 1


def test_canonical_identity_contains_all_v2_cache_fields() -> None:
    payload = canonical_experiment_config(experiment_config_fixture())
    assert set(payload) == {
        "macd_contract_version",
        "macd_algorithm_version",
        "macd_policy_version",
        "technical_score_version",
        "signal_intent_mapping_version",
        "confirmation_rule_version",
        "bar_contract_version",
        "price_adjustment_version",
        "data_quality_rule_version",
        "execution_config_hash",
        "fast_period",
        "slow_period",
        "signal_period",
        "cross_lookback_bars",
        "histogram_flat_tolerance",
        "score_weight",
        "conflict_gate_enabled",
        "mean_reversion_size_multiplier",
        "minimum_executable_trade_pct",
        "trend_buy_block_bearish_cross",
        "trend_buy_block_zero_axis_states",
        "bar_interval",
        "closed_bars_only",
        "price_field",
        "price_adjustment_mode",
        "histogram_tolerance_mode",
        "mean_reversion_buy_accepted_confirmations",
        "mean_reversion_sell_accepted_confirmations",
    }


def test_set_order_does_not_change_hash() -> None:
    left = experiment_config_fixture(entry_confirmations=(EntryConfirmation.SUPPORT_HOLD, EntryConfirmation.VWAP_RECLAIM))
    right = experiment_config_fixture(entry_confirmations=(EntryConfirmation.VWAP_RECLAIM, EntryConfirmation.SUPPORT_HOLD))
    assert experiment_config_hash(left) == experiment_config_hash(right)


def experiment_config_fixture(
    *,
    entry_confirmations: tuple[EntryConfirmation, ...] = (EntryConfirmation.SUPPORT_HOLD,),
) -> MACDExperimentIdentity:
    return MACDExperimentIdentity(
        macd_contract_version="macd-data-v1",
        macd_algorithm_version="macd-v1",
        macd_policy_version="signal-intent-macd-v1",
        technical_score_version="technical-score-macd-v1",
        signal_intent_mapping_version="signal-intent-map-v1",
        confirmation_rule_version="confirmation-rules-v1",
        bar_contract_version="closed-bars-a-share-v1",
        price_adjustment_version="point-in-time-adjust-v1",
        data_quality_rule_version="macd-data-quality-v1",
        execution_config_hash="execution-v1",
        fast_period=12,
        slow_period=26,
        signal_period=9,
        cross_lookback_bars=3,
        histogram_flat_tolerance=0.0,
        score_weight=0.0,
        conflict_gate_enabled=False,
        mean_reversion_size_multiplier=0.5,
        minimum_executable_trade_pct=0.0,
        trend_buy_block_bearish_cross=True,
        trend_buy_block_zero_axis_states=frozenset({MACDZeroAxis.BELOW, MACDZeroAxis.STRADDLING}),
        bar_interval=BarInterval.MINUTE_5,
        closed_bars_only=True,
        price_field=MACDPriceField.CLOSE,
        price_adjustment_mode=PriceAdjustmentMode.POINT_IN_TIME_ADJUSTED,
        histogram_tolerance_mode=HistogramToleranceMode.ABSOLUTE,
        mean_reversion_buy_accepted_confirmations=frozenset(entry_confirmations),
        mean_reversion_sell_accepted_confirmations=frozenset({ExitConfirmation.RESISTANCE_REJECTION}),
    )
```

- [ ] **Step 2: Run and verify missing module fails**

Run: `uv run --extra dev pytest tests/test_macd_experiments.py -q`

Expected: collection fails because `macd_experiments` is absent.

- [ ] **Step 3: Implement canonical serialization and profiles**

```python
import hashlib
import json

MACD_CACHE_SCHEMA_VERSION = "macd-signal-cache-v2"


@dataclass(frozen=True)
class MACDExperimentIdentity:
    macd_contract_version: str
    macd_algorithm_version: str
    macd_policy_version: str
    technical_score_version: str
    signal_intent_mapping_version: str
    confirmation_rule_version: str
    bar_contract_version: str
    price_adjustment_version: str
    data_quality_rule_version: str
    execution_config_hash: str
    fast_period: int
    slow_period: int
    signal_period: int
    cross_lookback_bars: int
    histogram_flat_tolerance: float
    score_weight: float
    conflict_gate_enabled: bool
    mean_reversion_size_multiplier: float
    minimum_executable_trade_pct: float
    trend_buy_block_bearish_cross: bool
    trend_buy_block_zero_axis_states: frozenset[MACDZeroAxis]
    bar_interval: BarInterval
    closed_bars_only: bool
    price_field: MACDPriceField
    price_adjustment_mode: PriceAdjustmentMode
    histogram_tolerance_mode: HistogramToleranceMode
    mean_reversion_buy_accepted_confirmations: frozenset[EntryConfirmation]
    mean_reversion_sell_accepted_confirmations: frozenset[ExitConfirmation]


def canonical_experiment_config(identity: MACDExperimentIdentity) -> dict[str, object]:
    payload = asdict(identity)
    for key in (
        "trend_buy_block_zero_axis_states",
        "mean_reversion_buy_accepted_confirmations",
        "mean_reversion_sell_accepted_confirmations",
    ):
        payload[key] = sorted(item.value for item in getattr(identity, key))
    for key in ("bar_interval", "price_field", "price_adjustment_mode", "histogram_tolerance_mode"):
        payload[key] = getattr(identity, key).value
    payload["confirmation_rule_version"] = effective_confirmation_rule_version(
        identity.confirmation_rule_version,
        identity.mean_reversion_buy_accepted_confirmations,
        identity.mean_reversion_sell_accepted_confirmations,
    )
    return payload


def execution_config_hash(config: DividendTBacktestConfig) -> str:
    payload = asdict(config)
    for non_semantic in ("signal_cache_dir", "signal_cache_save_every", "signal_cache_tag"):
        payload.pop(non_semantic, None)
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()[:16]


def effective_confirmation_rule_version(
    base_version: str,
    entries: frozenset[EntryConfirmation],
    exits: frozenset[ExitConfirmation],
) -> str:
    accepted = {
        "entries": sorted(item.value for item in entries),
        "exits": sorted(item.value for item in exits),
        "validity": "current-decision-bar-only",
    }
    suffix = hashlib.sha256(canonical_json(accepted).encode("utf-8")).hexdigest()[:8]
    return f"{base_version}+{suffix}"


def canonical_json(payload: dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def experiment_config_hash(identity: MACDExperimentIdentity) -> str:
    payload = canonical_experiment_config(identity)
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()[:16]


def ablation_profiles() -> dict[str, MACDPolicyConfig]:
    return {
        "baseline": MACDPolicyConfig(score_weight=0.0, conflict_gate_enabled=False),
        "score-only": MACDPolicyConfig(score_weight=0.15, conflict_gate_enabled=False),
        "policy-only": MACDPolicyConfig(score_weight=0.0, conflict_gate_enabled=True),
        "full": MACDPolicyConfig(score_weight=0.15, conflict_gate_enabled=True),
    }
```

The dataclass above is the complete v2 cache identity. Adding any later result-affecting field requires adding it to this type, its sensitivity test, and `MACD_CACHE_SCHEMA_VERSION` review.

- [ ] **Step 4: Replace cache tag identity with schema plus canonical hash**

Retain human-readable tags only as labels. Cache file selection and validation use cache schema, dataset version, symbol, interval, and experiment hash. Reject old cache schema rather than reading it as current.

```python
def signal_cache_path(
    root: Path,
    *,
    dataset_version: str,
    symbol: str,
    identity: MACDExperimentIdentity,
) -> Path:
    config_hash = experiment_config_hash(identity)
    safe_symbol = symbol.replace(".", "_")
    return root / MACD_CACHE_SCHEMA_VERSION / dataset_version / identity.bar_interval.value / f"{safe_symbol}-{config_hash}.parquet"


def validate_cache_metadata(metadata: dict[str, object]) -> None:
    actual = metadata.get("cache_schema_version")
    if actual != MACD_CACHE_SCHEMA_VERSION:
        raise ValueError(f"unsupported cache schema: {actual!r}")
```

- [ ] **Step 5: Run cache and backtest regression tests**

Run: `uv run --extra dev pytest tests/test_macd_experiments.py tests/test_dividend_t_backtest.py -q`

Expected: all pass and each ablation profile has a distinct hash except intentionally identical canonical inputs.

- [ ] **Step 6: Commit Stage 6A**

```bash
git add src/market_regime_alpha/dividend_t/macd_experiments.py src/market_regime_alpha/dividend_t/backtest.py backtesting/run_cosco_dividend_t_backtest.py backtesting/run_dividend_watchlist_backtest.py tests/test_macd_experiments.py tests/test_dividend_t_backtest.py
git commit -m "feat: version MACD experiment caches"
```

---

### Task 10: Stage 6B — Counterfactual Ledger and Source-Separated Metrics

**Files:**
- Modify: `src/market_regime_alpha/dividend_t/backtest.py`
- Modify: `src/market_regime_alpha/dividend_t/macd_experiments.py`
- Modify: `backtesting/run_dividend_watchlist_backtest.py`
- Test: `tests/test_dividend_t_backtest.py`
- Test: `tests/test_macd_experiments.py`

**Interfaces:**
- Consumes: layered candidate trace, next-bar execution constraints, fees/slippage/T+1 rules.
- Produces: counterfactual event rows and `MACDGateMetrics` split by intent and score/policy effect source.

- [ ] **Step 1: Write failing metric and execution-parity tests**

```python
def test_net_block_benefit_subtracts_missed_profit() -> None:
    metrics = summarize_macd_gate_events(
        [
            gate_event_fixture(blocked=True, executable=True, counterfactual_net_pnl=-120.0),
            gate_event_fixture(blocked=True, executable=True, counterfactual_net_pnl=45.0),
            gate_event_fixture(blocked=True, executable=True, counterfactual_net_pnl=0.0),
        ]
    )
    assert metrics.avoided_loss_amount == 120.0
    assert metrics.missed_profit_amount == 45.0
    assert metrics.net_block_benefit == 75.0
    assert metrics.effective_block_rate == pytest.approx(1 / 3)
    assert metrics.wrong_block_rate == pytest.approx(1 / 3)


def test_blocked_counterfactual_uses_same_next_bar_constraints() -> None:
    candidate = gate_event_fixture(blocked=True, executable=False, counterfactual_net_pnl=None)
    blocked = evaluate_counterfactual(
        candidate,
        next_bar=object(),
        execution_resolver=lambda _event, _bar: ExecutionResolution(False, "LIMIT_UP", None, 0.0, 0.0),
    )
    assert blocked.executable is False
    assert blocked.block_reason == "LIMIT_UP"


def test_counterfactual_execution_resolver_receives_raw_not_adjusted_price() -> None:
    candidate = gate_event_fixture(blocked=True, executable=False, counterfactual_net_pnl=None)
    raw_next_bar = {"close": 10.10, "feature_adjusted_close": 5.05}

    def resolve(_event: CounterfactualEvent, bar: object) -> ExecutionResolution:
        assert isinstance(bar, dict)
        assert bar["close"] == 10.10
        return ExecutionResolution(True, None, float(bar["close"]), 0.01, 0.02)

    evaluated = evaluate_counterfactual(candidate, next_bar=raw_next_bar, execution_resolver=resolve)
    assert evaluated.reference_fill_price == 10.10
```

- [ ] **Step 2: Run and verify missing ledger functions fail**

Run: `uv run --extra dev pytest tests/test_macd_experiments.py tests/test_dividend_t_backtest.py -q`

Expected: new imports fail.

- [ ] **Step 3: Implement immutable candidate-time counterfactual events**

```python
@dataclass(frozen=True)
class CounterfactualEvent:
    symbol: str
    candidate_bar_close_time: str
    next_eligible_execution_time: str
    signal_intent: str
    candidate_setup_code: str
    primary_setup_code: str
    candidate_without_macd_score: str | None
    candidate_with_macd_score: str | None
    final_policy_action: str
    original_suggested_trade_pct: float
    adjusted_suggested_trade_pct: float
    macd_score_changed_candidate: bool
    macd_policy_changed_candidate: bool
    policy_eligible: bool
    policy_blocked: bool
    policy_resized: bool
    executable: bool
    block_reason: str | None
    reference_fill_price: float | None
    slippage_amount: float
    fee_amount: float
    counterfactual_net_pnl: float | None
    holding_period_bars: int | None


@dataclass(frozen=True)
class ExecutionResolution:
    executable: bool
    block_reason: str | None
    reference_fill_price: float | None
    slippage_amount: float
    fee_amount: float


def evaluate_counterfactual(
    event: CounterfactualEvent,
    *,
    next_bar: object,
    execution_resolver: Callable[[CounterfactualEvent, object], ExecutionResolution],
) -> CounterfactualEvent:
    resolved = execution_resolver(event, next_bar)
    return replace(
        event,
        executable=resolved.executable,
        block_reason=resolved.block_reason,
        reference_fill_price=resolved.reference_fill_price,
        slippage_amount=resolved.slippage_amount,
        fee_amount=resolved.fee_amount,
    )


def gate_event_fixture(
    *,
    blocked: bool,
    executable: bool,
    counterfactual_net_pnl: float | None,
) -> CounterfactualEvent:
    return CounterfactualEvent(
        symbol="601919.SH",
        candidate_bar_close_time="2026-07-13 10:00:00",
        next_eligible_execution_time="2026-07-13 10:05:00",
        signal_intent="TREND_FOLLOWING",
        candidate_setup_code="breakout_confirmed",
        primary_setup_code="breakout_confirmed",
        candidate_without_macd_score="BUY_T",
        candidate_with_macd_score="BUY_T",
        final_policy_action="HOLD" if blocked else "BUY_T",
        original_suggested_trade_pct=0.20,
        adjusted_suggested_trade_pct=0.0 if blocked else 0.20,
        macd_score_changed_candidate=False,
        macd_policy_changed_candidate=blocked,
        policy_eligible=True,
        policy_blocked=blocked,
        policy_resized=False,
        executable=executable,
        block_reason=None,
        reference_fill_price=10.0 if executable else None,
        slippage_amount=0.0,
        fee_amount=0.0,
        counterfactual_net_pnl=counterfactual_net_pnl,
        holding_period_bars=3 if counterfactual_net_pnl is not None else None,
    )
```

Construct this row at candidate time, but resolve execution and forward outcomes only in the offline evaluator. Reuse the same next-eligible-bar, limit-up/down, suspension, T+1, fill-price, fee, and slippage helpers as actual trades; require `next_eligible_execution_time > candidate_bar_close_time`. Do not create a looser counterfactual fill model.

- [ ] **Step 4: Implement metric formulas and mutually inspectable effect groups**

```python
@dataclass(frozen=True)
class MACDGateMetrics:
    block_rate: float
    resize_rate: float
    effective_block_rate: float
    wrong_block_rate: float
    avoided_loss_amount: float
    missed_profit_amount: float
    net_block_benefit: float
    zero_pnl_block_count: int
    coverage_change: float
    average_holding_period_change: float


def _rate(numerator: int, denominator: int) -> float:
    return 0.0 if denominator == 0 else numerator / denominator


def summarize_macd_gate_events(
    events: Sequence[CounterfactualEvent],
    *,
    baseline_coverage: float = 0.0,
    experiment_coverage: float = 0.0,
    baseline_average_holding_period: float = 0.0,
    experiment_average_holding_period: float = 0.0,
) -> MACDGateMetrics:
    eligible = [event for event in events if event.policy_eligible]
    blocked = [event for event in eligible if event.policy_blocked]
    resized = [event for event in eligible if event.policy_resized]
    executable = [event for event in blocked if event.executable and event.counterfactual_net_pnl is not None]
    losing = [event for event in executable if event.counterfactual_net_pnl < 0.0]
    winning = [event for event in executable if event.counterfactual_net_pnl > 0.0]
    zero = [event for event in executable if event.counterfactual_net_pnl == 0.0]
    avoided = sum(abs(float(event.counterfactual_net_pnl)) for event in losing)
    missed = sum(float(event.counterfactual_net_pnl) for event in winning)
    return MACDGateMetrics(
        block_rate=_rate(len(blocked), len(eligible)),
        resize_rate=_rate(len(resized), len(eligible)),
        effective_block_rate=_rate(len(losing), len(executable)),
        wrong_block_rate=_rate(len(winning), len(executable)),
        avoided_loss_amount=avoided,
        missed_profit_amount=missed,
        net_block_benefit=avoided - missed,
        zero_pnl_block_count=len(zero),
        coverage_change=experiment_coverage - baseline_coverage,
        average_holding_period_change=(experiment_average_holding_period - baseline_average_holding_period),
    )
```

Produce separate rows for `MEAN_REVERSION_T`, `TREND_FOLLOWING`, `RISK_REDUCTION`, and `BASE_ACCUMULATION`, plus score-suppressed, policy-blocked, policy-resized, both-layer, and unaffected groups. Exclude base accumulation from ordinary buy hit rates.

- [ ] **Step 5: Run focused tests and ensure no same-bar fills**

Run: `uv run --extra dev pytest tests/test_macd_experiments.py tests/test_dividend_t_backtest.py -q`

Expected: all pass, including timestamp assertions `execution_time > candidate_bar_close_time`.

- [ ] **Step 6: Commit Stage 6B**

```bash
git add src/market_regime_alpha/dividend_t/backtest.py src/market_regime_alpha/dividend_t/macd_experiments.py backtesting/run_dividend_watchlist_backtest.py tests/test_dividend_t_backtest.py tests/test_macd_experiments.py
git commit -m "feat: add MACD counterfactual metrics"
```

---

### Task 11: Stage 7 — Sealed Four-Arm Out-of-Sample Runner and Immutable Artifacts

**Files:**
- Create: `backtesting/run_macd_ablation.py`
- Modify: `src/market_regime_alpha/dividend_t/macd_experiments.py`
- Modify: `tests/test_macd_experiments.py`
- Modify: `backtesting/README.md`

**Interfaces:**
- Consumes: fixed dataset manifest, train/validation/test ranges, four profiles, backtest runner.
- Produces: an immutable hash-named directory with manifest, config, metrics, events, counterfactual ledger, and Markdown report.

- [ ] **Step 1: Write failing manifest, immutable-directory, and sealed-test tests**

```python
def test_final_artifact_directory_is_content_addressed_and_non_overwriting(tmp_path: Path) -> None:
    metadata = FinalRunMetadata(
        git_commit="f27e048",
        dataset_version="data123",
        experiment_config_hash="abc123",
        train_range=("2024-01-01", "2024-12-31"),
        validation_range=("2025-01-01", "2025-06-30"),
        test_range=("2025-07-01", "2025-12-31"),
        cache_schema_version="macd-signal-cache-v2",
        run_timestamp="20260713T120000+0800",
    )
    first = create_final_artifact_dir(tmp_path, metadata)
    assert first.name == "20260713T120000+0800-abc123-f27e048"
    with pytest.raises(FileExistsError):
        create_final_artifact_dir(tmp_path, metadata)


def test_dataset_version_changes_when_corporate_actions_change() -> None:
    manifest = DatasetManifest(
        bars_hash="bars",
        universe_hash="universe",
        corporate_action_hash="actions",
        trading_calendar_hash="calendar",
        suspension_hash="suspensions",
        source_metadata_hash="source",
    )
    first = dataset_version(manifest)
    changed = replace(manifest, corporate_action_hash="different")
    assert dataset_version(changed) != first
```

- [ ] **Step 2: Run and verify missing artifact helpers fail**

Run: `uv run --extra dev pytest tests/test_macd_experiments.py -q`

Expected: new helper imports fail.

- [ ] **Step 3: Implement final metadata and atomic non-overwriting directory creation**

```python
@dataclass(frozen=True)
class FinalRunMetadata:
    git_commit: str
    dataset_version: str
    experiment_config_hash: str
    train_range: tuple[str, str]
    validation_range: tuple[str, str]
    test_range: tuple[str, str]
    cache_schema_version: str
    run_timestamp: str


def create_final_artifact_dir(root: Path, metadata: FinalRunMetadata) -> Path:
    short_sha = metadata.git_commit[:7]
    path = root / f"{metadata.run_timestamp}-{metadata.experiment_config_hash}-{short_sha}"
    path.mkdir(parents=True, exist_ok=False)
    return path
```

Build `dataset_version` from one explicit manifest so every point-in-time input participates:

```python
@dataclass(frozen=True)
class DatasetManifest:
    bars_hash: str
    universe_hash: str
    corporate_action_hash: str
    trading_calendar_hash: str
    suspension_hash: str
    source_metadata_hash: str


def dataset_version(manifest: DatasetManifest) -> str:
    payload = asdict(manifest)
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()[:16]
```

- [ ] **Step 4: Implement the explicit four-arm runner**

The CLI requires explicit train, validation, and test dates. `--final-test` is required to read the test range and write under `reports/backtests/macd/final/`; without it, only train/validation reports are allowed. Execute all four profiles with the same dataset and execution assumptions, then write `manifest.json`, `config.json`, `metrics.csv`, `intent_metrics.csv`, `counterfactual_events.parquet`, and `report.md`.

```python
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--train-start", required=True)
    parser.add_argument("--train-end", required=True)
    parser.add_argument("--validation-start", required=True)
    parser.add_argument("--validation-end", required=True)
    parser.add_argument("--test-start")
    parser.add_argument("--test-end")
    parser.add_argument("--final-test", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def selected_ranges(args: argparse.Namespace) -> dict[str, tuple[str, str]]:
    ranges = {
        "train": (args.train_start, args.train_end),
        "validation": (args.validation_start, args.validation_end),
    }
    if args.final_test:
        if not args.test_start or not args.test_end:
            raise ValueError("--final-test requires --test-start and --test-end")
        ranges["test"] = (args.test_start, args.test_end)
    elif args.test_start or args.test_end:
        raise ValueError("test range is sealed unless --final-test is set")
    return ranges
```

`main()` loads the dataset once, builds one `DatasetManifest`, loops over `ablation_profiles()` without changing execution assumptions, and writes the six named files. It calls `create_final_artifact_dir()` only when `--final-test` is present; a dry run prints ranges and hashes and performs no writes.

- [ ] **Step 5: Run unit tests and a tiny synthetic smoke run**

Run: `uv run --extra dev pytest tests/test_macd_experiments.py -q`

Expected: all pass.

Run: `PYTHONPATH=src uv run --extra dev python backtesting/run_macd_ablation.py --data data/raw/dividend_t_5min_1y/601919.SH_5min.csv --train-start 2025-06-25 --train-end 2025-06-25 --validation-start 2025-06-26 --validation-end 2025-06-26 --dry-run`

Expected: prints four distinct experiment hashes, the fixed ranges, and `profile=baseline production_default=true`; it does not create a final-test directory.

- [ ] **Step 6: Commit Stage 7 report tooling without promoting production defaults**

```bash
git add backtesting/run_macd_ablation.py src/market_regime_alpha/dividend_t/macd_experiments.py tests/test_macd_experiments.py backtesting/README.md
git commit -m "feat: add sealed MACD ablation reports"
```

---

### Task 12: Final Documentation, Full Regression, and Implementation Handoff

**Files:**
- Modify: `docs/Dividend-T-Platform.md`
- Modify: `docs/Data-Spec.md`
- Modify: `backtesting/README.md`
- Modify: `src/market_regime_alpha/dividend_t/chan.py` only if Task 1 left local formula duplication and golden parity is proven
- Test: `tests/test_dividend_t_chan.py`
- Test: all tests

**Interfaces:**
- Consumes: all prior tasks.
- Produces: complete documented baseline behavior, experiment commands, and a fully verified implementation branch ready for specification review.

- [ ] **Step 1: Add a failing Chan parity test before deduplicating its formula**

```python
def legacy_chan_histogram(closes: pd.Series) -> pd.Series:
    dif = closes.ewm(span=12, adjust=False).mean() - closes.ewm(span=26, adjust=False).mean()
    dea = dif.ewm(span=9, adjust=False).mean()
    return (dif - dea) * 2.0


def test_shared_macd_series_preserves_chan_histogram() -> None:
    closes = pd.Series([10.0, 10.2, 10.1, 10.5, 10.3, 10.8, 10.6, 11.0] * 6)
    _, _, shared_histogram = macd_series(tuple(closes), fast_period=12, slow_period=26, signal_period=9)
    assert shared_histogram == pytest.approx(tuple(legacy_chan_histogram(closes)), rel=1e-12, abs=1e-12)
```

Run all pre-existing `tests/test_dividend_t_chan.py` assertions before and after replacing `_add_macd`; the new parity test fixes the duplicated numeric primitive, while the existing suite fixes structure, divergence, and score behavior.

- [ ] **Step 2: Replace only the duplicated EMA/MACD series primitive if parity holds**

Keep Chan calculation on the inclusion-normalized frame. Do not feed the main raw-bar MACD result into Chan divergence.

```python
def _add_macd(data: Any) -> Any:
    frame = data.copy()
    _, _, histogram = macd_series(
        tuple(float(value) for value in frame["close"]),
        fast_period=12,
        slow_period=26,
        signal_period=9,
    )
    frame["macd_hist"] = histogram
    return frame
```

- [ ] **Step 3: Update user-facing documentation with exact contracts and commands**

Add these concrete sections:

- `docs/Data-Spec.md`: “MACD data contract v1” with `1d`/`5m`, 33/34/35, finalized bars, point-in-time adjusted feature close versus raw execution price, gap reasons, enums, neutral defaults, and schema 2 metadata.
- `docs/Dividend-T-Platform.md`: “Signal intent and MACD research policy” with the complete setup map, current-bar-only confirmations, accepted confirmation sets, risk/base exemptions, one sizing owner, baseline defaults, and the statement that 15% plus gate conditions are unpromoted hypotheses.
- `backtesting/README.md`: “MACD four-arm ablation” with the exact dry-run command from Task 11, the four profile definitions, chronological/holdout split rules, immutable `reports/backtests/macd/final/<timestamp>-<config-hash>-<sha>/` layout, counterfactual assumptions, and the prohibition on tuning after reading the final test report.

Use these exact baseline statements in both platform and backtest documentation:

```markdown
生产默认 profile 为 `baseline`：`score_weight=0.0`、`conflict_gate_enabled=False`。
`score_weight=0.15` 与 MACD policy 均为待样本外验证的模型假设；Stage 7 只生成研究报告，不提升生产默认值。
正式决策只使用已收盘 K 线；未收盘数据仅可作为 `provisional=true` 的 UI 预览。
确认状态只对当前决策 K 线有效，且只有 policy 配置列出的确认类型可以放行均值回归候选。
```

- [ ] **Step 4: Run the full test suite**

Run: `uv run --extra dev pytest -q`

Expected: all tests pass.

- [ ] **Step 5: Run full static verification**

Run: `uv run --extra dev ruff check src tests scripts backtesting`

Expected: `All checks passed!`

Run: `uv run --extra dev mypy`

Expected: `Success: no issues found`.

- [ ] **Step 6: Verify baseline defaults and clean worktree scope**

Run: `rg -n "score_weight=0.0|conflict_gate_enabled=False|default=\"baseline\"" src backtesting`

Expected: baseline constructors and CLI defaults are present; no production default selects `full`.

Run: `git status --short`

Expected: only the documentation and any intentional final parity-test edits for this task are listed before commit.

- [ ] **Step 7: Commit final documentation and verification changes**

```bash
git add docs/Dividend-T-Platform.md docs/Data-Spec.md backtesting/README.md src/market_regime_alpha/dividend_t/chan.py tests/test_dividend_t_chan.py
git commit -m "docs: document intent-aware MACD research flow"
```

- [ ] **Step 8: Stop before production promotion**

Report the exact commits and verification commands. Do not change the default weight or enable policy. The next decision is whether to run the sealed Stage 7 report; production promotion is a later, separately reviewed change.

Use this handoff shape:

```text
Implemented commits: <ordered commit list>
Verification: <exact pytest, Ruff, mypy, and smoke commands with results>
Production defaults: baseline (score_weight=0.0, conflict_gate_enabled=False)
Stage 7 status: tooling ready; no production promotion performed
Next reviewed decision: run sealed final report, then separately decide whether to promote weight or policy
```
