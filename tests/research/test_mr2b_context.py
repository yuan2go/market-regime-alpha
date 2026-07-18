from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.research.mr2b_context import (
    CONTEXT_GRID,
    ContextDataStatus,
    ContextMissingReason,
    build_auxiliary_watchlist_context,
    build_auxiliary_watchlist_context_evidence,
    validate_context_reconstruction,
)
from market_regime_alpha.research.tencent_composite_contracts import (
    CompositeBar,
    CompositeSourceKind,
)


SHANGHAI = ZoneInfo("Asia/Shanghai")
PREVIOUS = date(2026, 1, 5)
DECISION = date(2026, 1, 6)
SYMBOLS = ("000001.SZ", "000002.SZ")


def _bar(symbol: str, day: date, endpoint: time, *, value: float, amount: float) -> CompositeBar:
    return CompositeBar(
        symbol=symbol,
        timestamp=datetime.combine(day, endpoint, tzinfo=SHANGHAI),
        open=value,
        high=value * 1.001,
        low=value * 0.999,
        close=value,
        volume=100.0,
        amount=amount,
        source=CompositeSourceKind.LOCAL,
    )


def _complete_bars(*, post_cutoff_multiplier: float = 1.0) -> tuple[CompositeBar, ...]:
    rows: list[CompositeBar] = []
    for symbol_index, symbol in enumerate(SYMBOLS):
        prior = 10.0 + symbol_index
        current = prior * 1.01
        for endpoint in CONTEXT_GRID:
            rows.append(_bar(symbol, PREVIOUS, endpoint, value=prior, amount=100.0))
            rows.append(_bar(symbol, DECISION, endpoint, value=current, amount=110.0))
        rows.append(_bar(symbol, PREVIOUS, time(15, 0), value=prior, amount=50.0))
        rows.append(
            _bar(
                symbol,
                DECISION,
                time(14, 55),
                value=current * post_cutoff_multiplier,
                amount=1_000_000.0 * post_cutoff_multiplier,
            )
        )
        rows.append(
            _bar(
                symbol,
                DECISION,
                time(15, 0),
                value=current * post_cutoff_multiplier,
                amount=2_000_000.0 * post_cutoff_multiplier,
            )
        )
    return tuple(rows)


def _build(bars: tuple[CompositeBar, ...]):
    return build_auxiliary_watchlist_context(
        dataset_id="prr-dataset-test",
        accepted_symbols=SYMBOLS,
        session_dates=(PREVIOUS, DECISION),
        bars=bars,
        decision_dates=(DECISION,),
    )[0]


def test_context_requires_exact_1450_endpoint() -> None:
    bars = tuple(
        bar
        for bar in _complete_bars()
        if not (bar.timestamp.date() == DECISION and bar.timestamp.time() == time(14, 50))
    )

    context = _build(bars)

    assert context.data_status is ContextDataStatus.UNAVAILABLE
    assert context.missing_reason is ContextMissingReason.EXACT_1450_ENDPOINT_MISSING


def test_context_ignores_post_cutoff_bars() -> None:
    ordinary = _build(_complete_bars(post_cutoff_multiplier=1.0))
    extreme = _build(_complete_bars(post_cutoff_multiplier=100.0))

    assert ordinary == extreme


def test_context_requires_canonical_46_bar_grid_without_lunch_break() -> None:
    assert len(CONTEXT_GRID) == 46
    assert CONTEXT_GRID[0] == time(9, 35)
    assert CONTEXT_GRID[-1] == time(14, 50)
    assert time(11, 35) not in CONTEXT_GRID
    assert time(13, 0) not in CONTEXT_GRID
    missing = tuple(
        bar
        for bar in _complete_bars()
        if not (
            bar.symbol == SYMBOLS[0]
            and bar.timestamp.date() == DECISION
            and bar.timestamp.time() == time(10, 5)
        )
    )

    context = _build(missing)

    assert context.data_status is ContextDataStatus.UNAVAILABLE
    assert context.missing_reason is ContextMissingReason.INCOMPLETE_CUTOFF_GRID


def test_amount_change_uses_previous_session_same_cutoff() -> None:
    context = _build(_complete_bars())

    assert context.watchlist_amount_to_cutoff == 2 * 46 * 110.0
    assert context.prior_watchlist_amount_same_cutoff == 2 * 46 * 100.0
    assert context.watchlist_amount_change_same_cutoff == pytest.approx(0.1)


def test_future_dates_do_not_change_historical_context_identity() -> None:
    later = date(2026, 1, 7)
    future = tuple(
        _bar(symbol, later, endpoint, value=999.0, amount=999_999.0)
        for symbol in SYMBOLS
        for endpoint in CONTEXT_GRID
    )

    original = _build(_complete_bars())
    with_future = _build((*_complete_bars(), *future))

    assert original == with_future
    assert original.dataset_id == "prr-dataset-test"
    assert original.expected_bar_count_per_symbol == 46


def test_symbol_evidence_reconstructs_available_daily_context() -> None:
    bundle = build_auxiliary_watchlist_context_evidence(
        dataset_id="prr-dataset-test",
        accepted_symbols=SYMBOLS,
        session_dates=(PREVIOUS, DECISION),
        bars=_complete_bars(),
        decision_dates=(DECISION,),
    )

    assert len(bundle.symbol_evidence) == len(SYMBOLS)
    assert all(row.evidence_status is ContextDataStatus.AVAILABLE for row in bundle.symbol_evidence)
    validate_context_reconstruction(bundle.contexts[0], bundle.symbol_evidence)


def test_symbol_evidence_preserves_per_symbol_missing_reason() -> None:
    bars = tuple(
        bar
        for bar in _complete_bars()
        if not (
            bar.symbol == SYMBOLS[0]
            and bar.timestamp.date() == DECISION
            and bar.timestamp.time() == time(10, 5)
        )
    )
    bundle = build_auxiliary_watchlist_context_evidence(
        dataset_id="prr-dataset-test",
        accepted_symbols=SYMBOLS,
        session_dates=(PREVIOUS, DECISION),
        bars=bars,
        decision_dates=(DECISION,),
    )

    missing = next(row for row in bundle.symbol_evidence if row.symbol == SYMBOLS[0])
    assert missing.missing_reason is ContextMissingReason.INCOMPLETE_CUTOFF_GRID
    validate_context_reconstruction(bundle.contexts[0], bundle.symbol_evidence)
