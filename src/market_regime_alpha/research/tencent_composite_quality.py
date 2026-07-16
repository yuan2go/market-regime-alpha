"""Session preparation and fail-closed quality gates for Tencent composite data."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, time
from typing import Iterable
from zoneinfo import ZoneInfo

from market_regime_alpha.research.tencent_composite_contracts import (
    CompositeBar,
    CompositeDispositionCode,
    CompositeMergeResult,
    CompositeQualityFinding,
    CompositeQualityReport,
    CompositeSymbolDisposition,
    PreparedCompositeData,
    PreparedCompositeSession,
)


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
REFERENCE_CUTOFF = time(14, 50)
MINIMUM_BARS_PER_SESSION = 46


class TencentCompositeQualityGateError(RuntimeError):
    """Raised when the bounded 20-symbol run cannot satisfy its declared gate."""

    def __init__(self, message: str, quality: CompositeQualityReport) -> None:
        self.quality = quality
        super().__init__(message)


def prepare_composite_data(
    merged: CompositeMergeResult,
    *,
    requested_symbols: tuple[str, ...],
    decision_count: int = 60,
    warmup_sessions: int = 21,
    minimum_accepted_symbols: int = 16,
    minimum_bars_per_session: int = MINIMUM_BARS_PER_SESSION,
) -> PreparedCompositeData:
    """Aggregate complete sessions and enforce symbol/common-date coverage."""

    if not requested_symbols or len(requested_symbols) != len(set(requested_symbols)):
        raise ValueError("requested_symbols must be non-empty and unique")
    for label, value in (
        ("decision_count", decision_count),
        ("warmup_sessions", warmup_sessions),
        ("minimum_accepted_symbols", minimum_accepted_symbols),
        ("minimum_bars_per_session", minimum_bars_per_session),
    ):
        if value <= 0:
            raise ValueError(f"{label} must be positive")
    if minimum_accepted_symbols > len(requested_symbols):
        raise ValueError("minimum_accepted_symbols must not exceed requested symbol count")

    required_sessions = warmup_sessions + decision_count + 1
    sessions_by_symbol, findings_by_symbol = _group_complete_sessions(
        merged.bars,
        requested_symbols=requested_symbols,
        minimum_bars_per_session=minimum_bars_per_session,
    )
    _add_conflict_findings(merged, findings_by_symbol)

    accepted = tuple(
        sorted(
            symbol
            for symbol in requested_symbols
            if len(sessions_by_symbol.get(symbol, {})) >= required_sessions
        )
    )
    common_dates = _common_dates(sessions_by_symbol, accepted)
    dispositions = tuple(
        _disposition(
            symbol=symbol,
            complete_session_count=len(sessions_by_symbol.get(symbol, {})),
            required_sessions=required_sessions,
            warmup_sessions=warmup_sessions,
            findings=tuple(findings_by_symbol.get(symbol, ())),
        )
        for symbol in requested_symbols
    )
    quality = CompositeQualityReport(
        requested_symbols=requested_symbols,
        accepted_symbols=accepted,
        dispositions=dispositions,
        common_session_dates=common_dates,
        required_session_count=required_sessions,
        minimum_accepted_symbols=minimum_accepted_symbols,
    )
    if len(accepted) < minimum_accepted_symbols:
        raise TencentCompositeQualityGateError(
            f"accepted symbols {len(accepted)} < {minimum_accepted_symbols}",
            quality,
        )
    if len(common_dates) < required_sessions:
        raise TencentCompositeQualityGateError(
            f"common complete sessions {len(common_dates)} < {required_sessions}",
            quality,
        )

    selected_dates = common_dates[-required_sessions:]
    sessions = tuple(
        sessions_by_symbol[symbol][session_date]
        for session_date in selected_dates
        for symbol in accepted
    )
    return PreparedCompositeData(
        accepted_symbols=accepted,
        common_session_dates=selected_dates,
        sessions=sessions,
        quality=quality,
        limitations=(
            "CURRENT_WATCHLIST_BACKFILL_BIAS",
            "tencent-composite-1455-one-full-5m-lag-v1",
        ),
    )


def _group_complete_sessions(
    bars: tuple[CompositeBar, ...],
    *,
    requested_symbols: tuple[str, ...],
    minimum_bars_per_session: int,
) -> tuple[
    dict[str, dict[date, PreparedCompositeSession]],
    dict[str, list[CompositeQualityFinding]],
]:
    requested = set(requested_symbols)
    grouped: dict[tuple[str, date], list[CompositeBar]] = defaultdict(list)
    for bar in bars:
        if bar.symbol not in requested:
            continue
        session_date = bar.timestamp.astimezone(SHANGHAI_TZ).date()
        grouped[(bar.symbol, session_date)].append(bar)

    sessions_by_symbol: dict[str, dict[date, PreparedCompositeSession]] = defaultdict(dict)
    findings_by_symbol: dict[str, list[CompositeQualityFinding]] = defaultdict(list)
    for (symbol, session_date), session_bars in sorted(grouped.items()):
        prepared = _prepare_session(
            symbol,
            session_date,
            tuple(session_bars),
            minimum_bars_per_session=minimum_bars_per_session,
        )
        if prepared is None:
            findings_by_symbol[symbol].append(
                CompositeQualityFinding(
                    code="INCOMPLETE_SESSION",
                    message=f"{session_date.isoformat()} lacks required bars or a completed <=14:50 reference",
                    critical=False,
                )
            )
            continue
        sessions_by_symbol[symbol][session_date] = prepared

    for symbol in requested_symbols:
        if symbol not in grouped_symbols(grouped):
            findings_by_symbol[symbol].append(
                CompositeQualityFinding(
                    code="NO_SOURCE_ROWS",
                    message="no normalized source rows were acquired",
                    critical=True,
                )
            )
    return dict(sessions_by_symbol), dict(findings_by_symbol)


def grouped_symbols(grouped: dict[tuple[str, date], list[CompositeBar]]) -> set[str]:
    return {symbol for symbol, _ in grouped}


def _prepare_session(
    symbol: str,
    session_date: date,
    bars: tuple[CompositeBar, ...],
    *,
    minimum_bars_per_session: int,
) -> PreparedCompositeSession | None:
    ordered = tuple(sorted(bars, key=lambda bar: bar.timestamp))
    if len(ordered) < minimum_bars_per_session:
        return None
    reference_candidates = [
        bar
        for bar in ordered
        if bar.timestamp.astimezone(SHANGHAI_TZ).time().replace(tzinfo=None) <= REFERENCE_CUTOFF
    ]
    if not reference_candidates:
        return None
    reference = reference_candidates[-1]
    return PreparedCompositeSession(
        symbol=symbol,
        session_date=session_date,
        open=ordered[0].open,
        high=max(bar.high for bar in ordered),
        low=min(bar.low for bar in ordered),
        close=ordered[-1].close,
        amount=sum(bar.amount for bar in ordered),
        reference_price=reference.close,
        reference_timestamp=reference.timestamp,
        source_kinds=tuple(sorted({bar.source for bar in ordered}, key=lambda item: item.value)),
    )


def _add_conflict_findings(
    merged: CompositeMergeResult,
    findings_by_symbol: dict[str, list[CompositeQualityFinding]],
) -> None:
    for conflict in merged.conflicts:
        symbol, timestamp = conflict.key
        findings_by_symbol[symbol].append(
            CompositeQualityFinding(
                code="SOURCE_CONFLICT_RESOLVED_BY_PRECEDENCE",
                message=(
                    f"{timestamp.isoformat()} selected {conflict.selected.source.value} "
                    f"over {conflict.rejected.source.value}"
                ),
                critical=False,
            )
        )


def _disposition(
    *,
    symbol: str,
    complete_session_count: int,
    required_sessions: int,
    warmup_sessions: int,
    findings: tuple[CompositeQualityFinding, ...],
) -> CompositeSymbolDisposition:
    if complete_session_count >= required_sessions:
        code = CompositeDispositionCode.ACCEPTED
    elif any(finding.code == "NO_SOURCE_ROWS" for finding in findings):
        code = CompositeDispositionCode.REJECTED_FETCH_FAILURE
    elif complete_session_count < warmup_sessions:
        code = CompositeDispositionCode.REJECTED_INSUFFICIENT_WARMUP
    else:
        code = CompositeDispositionCode.REJECTED_INSUFFICIENT_DECISION_DATES
    return CompositeSymbolDisposition(
        symbol=symbol,
        code=code,
        complete_session_count=complete_session_count,
        findings=findings,
    )


def _common_dates(
    sessions_by_symbol: dict[str, dict[date, PreparedCompositeSession]],
    accepted_symbols: tuple[str, ...],
) -> tuple[date, ...]:
    if not accepted_symbols:
        return ()
    date_sets: Iterable[set[date]] = (
        set(sessions_by_symbol[symbol]) for symbol in accepted_symbols
    )
    iterator = iter(date_sets)
    common = next(iterator)
    for dates in iterator:
        common.intersection_update(dates)
    return tuple(sorted(common))
