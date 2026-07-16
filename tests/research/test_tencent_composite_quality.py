from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.research.tencent_composite_contracts import (
    CompositeBar,
    CompositeDispositionCode,
    CompositeMergeResult,
    CompositeSourceKind,
)
from market_regime_alpha.research.tencent_composite_quality import (
    TencentCompositeQualityGateError,
    prepare_composite_data,
)


TZ = ZoneInfo("Asia/Shanghai")


def _symbols(count: int = 20) -> tuple[str, ...]:
    return tuple(f"{index + 1:06d}.SZ" for index in range(count))


def _session_bars(symbol: str, day: date, *, include_reference: bool = True) -> tuple[CompositeBar, ...]:
    rows = [
        (datetime(day.year, day.month, day.day, 9, 35, tzinfo=TZ), 10.0),
    ]
    if include_reference:
        rows.append((datetime(day.year, day.month, day.day, 14, 50, tzinfo=TZ), 10.2))
    return tuple(
        CompositeBar(
            symbol=symbol,
            timestamp=timestamp,
            open=close,
            high=close,
            low=close,
            close=close,
            volume=100.0,
            amount=close * 100.0,
            source=CompositeSourceKind.LOCAL,
        )
        for timestamp, close in rows
    )


def _merge_result(*, symbol_count: int, session_count: int, shifted_symbol: str | None = None) -> CompositeMergeResult:
    start = date(2026, 1, 1)
    bars = []
    for symbol in _symbols(symbol_count):
        shift = 1 if symbol == shifted_symbol else 0
        for index in range(session_count):
            bars.extend(_session_bars(symbol, start + timedelta(days=index + shift)))
    return CompositeMergeResult(
        bars=tuple(sorted(bars, key=lambda bar: (bar.timestamp, bar.symbol))),
        conflicts=(),
    )


def test_session_reference_uses_latest_row_no_later_than_1450() -> None:
    prepared = prepare_composite_data(
        _merge_result(symbol_count=16, session_count=82),
        requested_symbols=_symbols(20),
        decision_count=60,
        warmup_sessions=21,
        minimum_accepted_symbols=16,
        minimum_bars_per_session=2,
    )

    session = prepared.session_for("000001.SZ", prepared.common_session_dates[-2])
    assert session.reference_timestamp.strftime("%H:%M") == "14:50"
    assert session.reference_price == pytest.approx(10.2)
    assert prepared.quality.success is True
    assert len(prepared.quality.accepted_symbols) == 16
    assert len(prepared.common_session_dates) == 82


def test_quality_gate_fails_below_sixteen_symbols_and_retains_all_dispositions() -> None:
    with pytest.raises(TencentCompositeQualityGateError, match="accepted symbols 15 < 16") as captured:
        prepare_composite_data(
            _merge_result(symbol_count=15, session_count=82),
            requested_symbols=_symbols(20),
            decision_count=60,
            warmup_sessions=21,
            minimum_accepted_symbols=16,
            minimum_bars_per_session=2,
        )

    quality = captured.value.quality
    assert len(quality.dispositions) == 20
    assert len(quality.accepted_symbols) == 15
    assert quality.success is False


def test_quality_gate_requires_eighty_two_common_complete_sessions() -> None:
    symbols = _symbols(16)
    with pytest.raises(TencentCompositeQualityGateError, match="common complete sessions 81 < 82"):
        prepare_composite_data(
            _merge_result(symbol_count=16, session_count=82, shifted_symbol=symbols[-1]),
            requested_symbols=symbols,
            decision_count=60,
            warmup_sessions=21,
            minimum_accepted_symbols=16,
            minimum_bars_per_session=2,
        )


def test_missing_reference_bar_rejects_symbol_as_history_gap() -> None:
    symbols = _symbols(16)
    start = date(2026, 1, 1)
    bars = []
    for symbol in symbols:
        for index in range(82):
            bars.extend(
                _session_bars(
                    symbol,
                    start + timedelta(days=index),
                    include_reference=not (symbol == symbols[-1] and index == 40),
                )
            )
    merged = CompositeMergeResult(
        bars=tuple(sorted(bars, key=lambda bar: (bar.timestamp, bar.symbol))),
        conflicts=(),
    )

    with pytest.raises(TencentCompositeQualityGateError) as captured:
        prepare_composite_data(
            merged,
            requested_symbols=symbols,
            decision_count=60,
            warmup_sessions=21,
            minimum_accepted_symbols=16,
            minimum_bars_per_session=2,
        )

    rejected = next(item for item in captured.value.quality.dispositions if item.symbol == symbols[-1])
    assert rejected.code is CompositeDispositionCode.REJECTED_INSUFFICIENT_DECISION_DATES
    assert any(finding.code == "INCOMPLETE_SESSION" for finding in rejected.findings)
