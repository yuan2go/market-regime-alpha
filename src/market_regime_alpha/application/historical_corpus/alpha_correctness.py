"""Independent correctness checks over Historical normalized source bars.

This module is a checker, not a Feature, Target, Runtime or Evidence authority.
It deliberately recomputes the three WP-ALPHA-RESEARCH-01 intraday values and
the T+1 10:30 target without reading their persisted numerical outputs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal, ROUND_HALF_EVEN
from enum import Enum
from typing import Final
from zoneinfo import ZoneInfo

from market_regime_alpha.application.historical_corpus.contracts import (
    HistoricalNormalizedBar,
)
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.market_data import Timeframe


_SHANGHAI: Final[ZoneInfo] = ZoneInfo("Asia/Shanghai")
_SCALE: Final[Decimal] = Decimal("0.000000000001")
_SUPPORTED_FACTORS: Final[frozenset[str]] = frozenset(
    {
        "intraday_return_to_decision_time",
        "price_vs_vwap_return",
        "vwap_slope",
    }
)


class AlphaCorrectnessStatus(str, Enum):
    CORRECTNESS_SUPPORTED = "CORRECTNESS_SUPPORTED"
    CORRECTNESS_FAILED = "CORRECTNESS_FAILED"
    PARTIALLY_REPRODUCED = "PARTIALLY_REPRODUCED"
    PHYSICAL_REPRODUCTION_NOT_ESTABLISHED = (
        "PHYSICAL_REPRODUCTION_NOT_ESTABLISHED"
    )


@dataclass(frozen=True, slots=True)
class PersistedFeatureObservation:
    factor_id: str
    value: Decimal
    source_bar_ids: tuple[str, ...]
    source_bar_hashes: tuple[str, ...]
    source_lineage_hash: str
    event_start: datetime
    event_end: datetime

    @classmethod
    def create(
        cls,
        *,
        factor_id: str,
        value: Decimal,
        source_bars: tuple[HistoricalNormalizedBar, ...],
    ) -> PersistedFeatureObservation:
        ordered = _ordered_bars(source_bars)
        if factor_id not in _SUPPORTED_FACTORS:
            raise ValueError("unsupported independent intraday factor")
        if not ordered:
            raise ValueError("persisted Feature observation requires source bars")
        ids, hashes, lineage = _source_lineage(ordered)
        return cls(
            factor_id=factor_id,
            value=value,
            source_bar_ids=ids,
            source_bar_hashes=hashes,
            source_lineage_hash=lineage,
            event_start=ordered[0].event_start,
            event_end=ordered[-1].event_end,
        )


@dataclass(frozen=True, slots=True)
class FeatureCorrectnessComparison:
    factor_id: str
    persisted_value: Decimal
    recomputed_value: Decimal
    source_bar_ids: tuple[str, ...]
    source_bar_hashes: tuple[str, ...]
    source_lineage_hash: str
    event_start: datetime
    event_end: datetime
    decision_time: datetime
    discrepancies: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FeatureReproductionResult:
    session: date
    symbol: str
    decision_time: datetime
    status: AlphaCorrectnessStatus
    physical_source_available: bool
    comparisons: tuple[FeatureCorrectnessComparison, ...]
    discrepancies: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PersistedTargetObservation:
    decision_reference_price: Decimal
    target_price: Decimal
    target_return: Decimal
    decision_source_ids: tuple[str, ...]
    decision_source_hashes: tuple[str, ...]
    target_source_ids: tuple[str, ...]
    target_source_hashes: tuple[str, ...]
    target_session: date
    target_event_end: datetime

    @classmethod
    def create(
        cls,
        *,
        decision_reference_price: Decimal,
        target_price: Decimal,
        target_return: Decimal,
        decision_source_bars: tuple[HistoricalNormalizedBar, ...],
        target_source_bars: tuple[HistoricalNormalizedBar, ...],
        target_session: date,
    ) -> PersistedTargetObservation:
        decision = _ordered_bars(decision_source_bars)
        target = _ordered_bars(target_source_bars)
        if not decision or not target:
            raise ValueError("persisted Target observation requires source bars")
        expected = target_price / decision_reference_price - Decimal("1")
        if target_return != expected:
            raise ValueError("persisted Target return disagrees with its prices")
        decision_ids, decision_hashes, _ = _source_lineage(decision)
        target_ids, target_hashes, _ = _source_lineage(target)
        if set(decision_ids).intersection(target_ids):
            raise ValueError("Feature/Decision and Target lineage must be disjoint")
        return cls(
            decision_reference_price=decision_reference_price,
            target_price=target_price,
            target_return=target_return,
            decision_source_ids=decision_ids,
            decision_source_hashes=decision_hashes,
            target_source_ids=target_ids,
            target_source_hashes=target_hashes,
            target_session=target_session,
            target_event_end=target[-1].event_end,
        )


@dataclass(frozen=True, slots=True)
class TargetReproductionResult:
    symbol: str
    decision_time: datetime
    target_session: date
    target_event_end: datetime
    decision_reference_price: Decimal
    target_price: Decimal
    target_return: Decimal
    decision_source_ids: tuple[str, ...]
    target_source_ids: tuple[str, ...]
    status: AlphaCorrectnessStatus
    physical_source_available: bool
    discrepancies: tuple[str, ...]


def reproduce_intraday_features(
    *,
    session: date,
    symbol: str,
    decision_time: datetime,
    source_bars: tuple[HistoricalNormalizedBar, ...],
    persisted: tuple[PersistedFeatureObservation, ...],
    physical_source_available: bool,
) -> FeatureReproductionResult:
    """Recompute frozen intraday factors directly from bounded normalized bars."""

    _require_aware("decision_time", decision_time)
    decision_session = decision_time.astimezone(_SHANGHAI).date()
    if session != decision_session:
        raise ValueError("Feature session must equal DecisionTime session")
    persisted_ids = tuple(item.factor_id for item in persisted)
    if persisted_ids != tuple(sorted(set(persisted_ids))):
        raise ValueError("persisted Feature observations must be unique and sorted")
    selected = _ordered_bars(
        tuple(
            item
            for item in source_bars
            if item.symbol == symbol
            and item.market_date == session
            and item.timeframe is Timeframe.MINUTE_5
            and item.event_end <= decision_time
        )
    )
    if not selected:
        return FeatureReproductionResult(
            session=session,
            symbol=symbol,
            decision_time=decision_time,
            status=AlphaCorrectnessStatus.PARTIALLY_REPRODUCED,
            physical_source_available=physical_source_available,
            comparisons=(),
            discrepancies=("DECISION_TIME_SOURCE_BARS_MISSING",),
        )
    if any(item.event_end > decision_time for item in selected):
        raise ValueError("Feature source event_end exceeds DecisionTime")
    recomputed = _intraday_values(selected)
    comparisons: list[FeatureCorrectnessComparison] = []
    all_discrepancies: list[str] = []
    for observation in persisted:
        value, factor_bars = recomputed[observation.factor_id]
        ids, hashes, lineage = _source_lineage(factor_bars)
        discrepancies: list[str] = []
        if observation.value != value:
            discrepancies.append(f"VALUE_MISMATCH:{observation.factor_id}")
        if (
            observation.source_bar_ids != ids
            or observation.source_bar_hashes != hashes
            or observation.source_lineage_hash != lineage
        ):
            discrepancies.append(f"SOURCE_LINEAGE_MISMATCH:{observation.factor_id}")
        if (
            observation.event_start != factor_bars[0].event_start
            or observation.event_end != factor_bars[-1].event_end
        ):
            discrepancies.append(f"EVENT_INTERVAL_MISMATCH:{observation.factor_id}")
        comparison = FeatureCorrectnessComparison(
            factor_id=observation.factor_id,
            persisted_value=observation.value,
            recomputed_value=value,
            source_bar_ids=ids,
            source_bar_hashes=hashes,
            source_lineage_hash=lineage,
            event_start=factor_bars[0].event_start,
            event_end=factor_bars[-1].event_end,
            decision_time=decision_time,
            discrepancies=tuple(discrepancies),
        )
        comparisons.append(comparison)
        all_discrepancies.extend(discrepancies)
    status = _correctness_status(
        discrepancies=tuple(all_discrepancies),
        physical_source_available=physical_source_available,
        complete=bool(persisted),
    )
    return FeatureReproductionResult(
        session=session,
        symbol=symbol,
        decision_time=decision_time,
        status=status,
        physical_source_available=physical_source_available,
        comparisons=tuple(comparisons),
        discrepancies=tuple(all_discrepancies),
    )


def reproduce_t_plus_one_1030_target(
    *,
    symbol: str,
    decision_time: datetime,
    next_session: date,
    source_bars: tuple[HistoricalNormalizedBar, ...],
    persisted: PersistedTargetObservation | None,
    physical_source_available: bool,
) -> TargetReproductionResult:
    """Independently reconstruct the frozen Decision reference and T+1 10:30 return."""

    _require_aware("decision_time", decision_time)
    decision_session = decision_time.astimezone(_SHANGHAI).date()
    if next_session <= decision_session:
        raise ValueError("Target must use a later trading session")
    decision_bars = _ordered_bars(
        tuple(
            item
            for item in source_bars
            if item.symbol == symbol
            and item.market_date == decision_session
            and item.timeframe is Timeframe.MINUTE_5
            and item.event_end <= decision_time
        )
    )
    if not decision_bars:
        raise ValueError("Decision reference bar is unavailable")
    if decision_bars[-1].event_end != decision_time:
        raise ValueError("Decision reference checkpoint is incomplete")
    checkpoint = datetime.combine(next_session, time(10, 30), _SHANGHAI).astimezone(
        decision_time.tzinfo
    )
    target_bars = _ordered_bars(
        tuple(
            item
            for item in source_bars
            if item.symbol == symbol
            and item.market_date == next_session
            and item.timeframe is Timeframe.MINUTE_5
            and time(9, 30)
            <= item.event_start.astimezone(_SHANGHAI).time().replace(tzinfo=None)
            and item.event_end <= checkpoint
        )
    )
    target_start = datetime.combine(
        next_session, time(9, 30), _SHANGHAI
    ).astimezone(decision_time.tzinfo)
    if (
        not target_bars
        or target_bars[0].event_start != target_start
        or target_bars[-1].event_end != checkpoint
    ):
        raise ValueError("T+1 10:30 checkpoint is incomplete")
    if any(left.event_end != right.event_start for left, right in zip(target_bars, target_bars[1:], strict=False)):
        raise ValueError("T+1 checkpoint bars are not contiguous")
    decision_source = (decision_bars[-1],)
    decision_ids, decision_hashes, _ = _source_lineage(decision_source)
    target_ids, target_hashes, _ = _source_lineage(target_bars)
    if set(decision_ids).intersection(target_ids):
        raise ValueError("Feature/Decision and Target lineage must be disjoint")
    decision_price = decision_bars[-1].close
    target_price = target_bars[-1].close
    if decision_price is None or target_price is None or decision_price <= 0:
        raise ValueError("Target reproduction requires positive source prices")
    target_return = target_price / decision_price - Decimal("1")
    discrepancies: list[str] = []
    if persisted is not None:
        if (
            persisted.decision_reference_price != decision_price
            or persisted.target_price != target_price
            or persisted.target_return != target_return
        ):
            discrepancies.append("TARGET_VALUE_MISMATCH")
        if (
            persisted.decision_source_ids != decision_ids
            or persisted.decision_source_hashes != decision_hashes
            or persisted.target_source_ids != target_ids
            or persisted.target_source_hashes != target_hashes
        ):
            discrepancies.append("TARGET_SOURCE_LINEAGE_MISMATCH")
        if (
            persisted.target_session != next_session
            or persisted.target_event_end != checkpoint
        ):
            discrepancies.append("TARGET_TEMPORAL_BOUNDARY_MISMATCH")
    status = _correctness_status(
        discrepancies=tuple(discrepancies),
        physical_source_available=physical_source_available,
        complete=persisted is not None,
    )
    return TargetReproductionResult(
        symbol=symbol,
        decision_time=decision_time,
        target_session=next_session,
        target_event_end=checkpoint,
        decision_reference_price=decision_price,
        target_price=target_price,
        target_return=target_return,
        decision_source_ids=decision_ids,
        target_source_ids=target_ids,
        status=status,
        physical_source_available=physical_source_available,
        discrepancies=tuple(discrepancies),
    )


def _intraday_values(
    bars: tuple[HistoricalNormalizedBar, ...],
) -> dict[str, tuple[Decimal, tuple[HistoricalNormalizedBar, ...]]]:
    if any(item.close is None or item.open is None for item in bars):
        raise ValueError("intraday correctness bars require complete prices")
    first, latest = bars[0], bars[-1]
    assert first.open is not None and latest.close is not None
    if first.open <= 0:
        raise ValueError("intraday first open must be positive")
    total_volume = sum((item.volume for item in bars), Decimal("0"))
    if total_volume <= 0 or any(item.amount is None for item in bars):
        raise ValueError("VWAP correctness bars require positive volume and amount")
    total_amount = sum(
        (item.amount for item in bars if item.amount is not None), Decimal("0")
    )
    vwap = total_amount / total_volume
    split = max(1, len(bars) // 2)
    first_bars = bars[:split]
    first_volume = sum((item.volume for item in first_bars), Decimal("0"))
    first_amount = sum(
        (item.amount for item in first_bars if item.amount is not None), Decimal("0")
    )
    if first_volume <= 0 or first_amount <= 0:
        raise ValueError("VWAP slope correctness window is unavailable")
    first_vwap = first_amount / first_volume
    return {
        "intraday_return_to_decision_time": (
            _quantize(latest.close / first.open - Decimal("1")),
            (first, latest) if first is not latest else (first,),
        ),
        "price_vs_vwap_return": (
            _quantize(latest.close / vwap - Decimal("1")),
            bars,
        ),
        "vwap_slope": (
            _quantize(vwap / first_vwap - Decimal("1")),
            bars,
        ),
    }


def _source_lineage(
    bars: tuple[HistoricalNormalizedBar, ...],
) -> tuple[tuple[str, ...], tuple[str, ...], str]:
    ids = tuple(str(item.bar_id) for item in bars)
    hashes = tuple(item.content_hash for item in bars)
    lineage = canonical_hash(
        {
            "normalized_source_bars": [
                {"bar_id": bar_id, "bar_hash": bar_hash}
                for bar_id, bar_hash in zip(ids, hashes, strict=True)
            ]
        }
    )
    return ids, hashes, lineage


def _ordered_bars(
    bars: tuple[HistoricalNormalizedBar, ...],
) -> tuple[HistoricalNormalizedBar, ...]:
    ordered = tuple(
        sorted(bars, key=lambda item: (item.event_start, item.event_end, str(item.bar_id)))
    )
    ids = tuple(str(item.bar_id) for item in ordered)
    if len(ids) != len(set(ids)):
        raise ValueError("correctness source bars must be unique")
    return ordered


def _correctness_status(
    *,
    discrepancies: tuple[str, ...],
    physical_source_available: bool,
    complete: bool,
) -> AlphaCorrectnessStatus:
    if discrepancies:
        return AlphaCorrectnessStatus.CORRECTNESS_FAILED
    if not complete:
        return AlphaCorrectnessStatus.PARTIALLY_REPRODUCED
    if not physical_source_available:
        return AlphaCorrectnessStatus.PHYSICAL_REPRODUCTION_NOT_ESTABLISHED
    return AlphaCorrectnessStatus.CORRECTNESS_SUPPORTED


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(_SCALE, rounding=ROUND_HALF_EVEN)


def _require_aware(label: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")


__all__ = [
    "AlphaCorrectnessStatus",
    "FeatureCorrectnessComparison",
    "FeatureReproductionResult",
    "PersistedFeatureObservation",
    "PersistedTargetObservation",
    "TargetReproductionResult",
    "reproduce_intraday_features",
    "reproduce_t_plus_one_1030_target",
]
