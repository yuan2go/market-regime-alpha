"""Leak-free exact-14:50 auxiliary-watchlist Context evidence for MR-2B."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
from enum import Enum
import math
from typing import Iterable, TypedDict, cast
from zoneinfo import ZoneInfo

from market_regime_alpha.research.mr2b_excess import WatchlistDirection
from market_regime_alpha.research.prr_artifact_schemas import canonical_identity_hash
from market_regime_alpha.research.tencent_composite_contracts import CompositeBar


MR2B_CONTEXT_SCHEMA_VERSION = "mr-2b-auxiliary-watchlist-context-v2"
MR2B_CONTEXT_SYMBOL_EVIDENCE_SCHEMA_VERSION = (
    "mr-2b-auxiliary-watchlist-context-symbol-evidence-v1"
)
MR2B_CONTEXT_DEFINITION_ID = "mr2b-accepted-watchlist-exact-1450-context-v2"
MR2B_CONTEXT_GRID_DEFINITION_ID = "a-share-5m-end-labeled-grid-to-1450-v1"
MR2B_CONTEXT_COVERAGE_POLICY_ID = "full-accepted-watchlist-coverage-required-v1"
MR2B_DIRECTION_LABEL_POLICY_ID = "mr2b-direction-sign-epsilon-1e-12-v1"
_SHANGHAI = ZoneInfo("Asia/Shanghai")


def _inclusive_times(start: time, end: time) -> tuple[time, ...]:
    anchor = date(2000, 1, 1)
    current = datetime.combine(anchor, start)
    finish = datetime.combine(anchor, end)
    output: list[time] = []
    while current <= finish:
        output.append(current.time())
        current += timedelta(minutes=5)
    return tuple(output)


CONTEXT_GRID = (
    *_inclusive_times(time(9, 35), time(11, 30)),
    *_inclusive_times(time(13, 5), time(14, 50)),
)


class ContextDataStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class ContextMissingReason(str, Enum):
    EXACT_1450_ENDPOINT_MISSING = "EXACT_1450_ENDPOINT_MISSING"
    INCOMPLETE_CUTOFF_GRID = "INCOMPLETE_CUTOFF_GRID"
    PRIOR_SESSION_INCOMPLETE_CUTOFF_GRID = "PRIOR_SESSION_INCOMPLETE_CUTOFF_GRID"
    PRIOR_SESSION_CLOSE_MISSING = "PRIOR_SESSION_CLOSE_MISSING"


class _SymbolEvidencePayload(TypedDict):
    symbol: str
    current_grid_count: int
    prior_grid_count: int
    has_exact_1450: bool
    has_prior_exact_1450: bool
    has_prior_close_1500: bool
    close_1450: float | None
    prior_close_1500: float | None
    return_to_1450: float | None
    intraday_high_to_1450: float | None
    intraday_low_to_1450: float | None
    intraday_range_to_1450: float | None
    amount_to_1450: float | None
    prior_amount_same_cutoff: float | None
    evidence_status: ContextDataStatus
    missing_reason: ContextMissingReason | None


@dataclass(frozen=True, slots=True)
class AuxiliaryWatchlistContextSymbolEvidence:
    dataset_id: str
    decision_date: date
    symbol: str
    current_grid_count: int
    prior_grid_count: int
    has_exact_1450: bool
    has_prior_exact_1450: bool
    has_prior_close_1500: bool
    close_1450: float | None
    prior_close_1500: float | None
    return_to_1450: float | None
    intraday_high_to_1450: float | None
    intraday_low_to_1450: float | None
    intraday_range_to_1450: float | None
    amount_to_1450: float | None
    prior_amount_same_cutoff: float | None
    evidence_status: ContextDataStatus
    missing_reason: ContextMissingReason | None
    context_id: str
    watchlist_id: str
    data_eligibility: str = "EXPLORATORY"
    schema_version: str = MR2B_CONTEXT_SYMBOL_EVIDENCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != MR2B_CONTEXT_SYMBOL_EVIDENCE_SCHEMA_VERSION:
            raise ValueError("unsupported symbol Context evidence schema")
        if self.data_eligibility != "EXPLORATORY":
            raise ValueError("symbol Context evidence authority must remain EXPLORATORY")
        if not self.dataset_id or not self.symbol or not self.context_id or not self.watchlist_id:
            raise ValueError("symbol Context evidence identities must be non-empty")
        if not 0 <= self.current_grid_count <= len(CONTEXT_GRID):
            raise ValueError("current grid count is invalid")
        if not 0 <= self.prior_grid_count <= len(CONTEXT_GRID):
            raise ValueError("prior grid count is invalid")
        metrics = (
            self.close_1450,
            self.prior_close_1500,
            self.return_to_1450,
            self.intraday_high_to_1450,
            self.intraday_low_to_1450,
            self.intraday_range_to_1450,
            self.amount_to_1450,
            self.prior_amount_same_cutoff,
        )
        if self.evidence_status is ContextDataStatus.AVAILABLE:
            if self.missing_reason is not None or not all(
                (self.has_exact_1450, self.has_prior_exact_1450, self.has_prior_close_1500)
            ):
                raise ValueError("available symbol Context evidence requires complete endpoints")
            if self.current_grid_count != len(CONTEXT_GRID) or self.prior_grid_count != len(
                CONTEXT_GRID
            ):
                raise ValueError("available symbol Context evidence requires complete grids")
            if any(value is None or not math.isfinite(value) for value in metrics):
                raise ValueError("available symbol Context evidence metrics must be finite")
        elif self.missing_reason is None:
            raise ValueError("unavailable symbol Context evidence requires a missing reason")


@dataclass(frozen=True, slots=True)
class AuxiliaryWatchlistContextEvidence:
    contexts: tuple[AuxiliaryWatchlistContext, ...]
    symbol_evidence: tuple[AuxiliaryWatchlistContextSymbolEvidence, ...]


@dataclass(frozen=True, slots=True)
class AuxiliaryWatchlistContext:
    decision_date: date
    decision_time: datetime
    cutoff_time: datetime
    dataset_id: str
    watchlist_id: str
    context_id: str
    expected_symbol_count: int
    available_symbol_count: int
    coverage: float
    expected_bar_count_per_symbol: int
    available_bar_count_per_symbol: int
    grid_status: str
    data_status: ContextDataStatus
    missing_reason: ContextMissingReason | None
    watchlist_direction_return: float | None
    watchlist_direction: WatchlistDirection | None
    watchlist_breadth_at_cutoff: float | None
    watchlist_intraday_range_to_cutoff: float | None
    watchlist_amount_to_cutoff: float | None
    prior_watchlist_amount_same_cutoff: float | None
    watchlist_amount_change_same_cutoff: float | None
    definition_id: str = MR2B_CONTEXT_DEFINITION_ID
    grid_definition_id: str = MR2B_CONTEXT_GRID_DEFINITION_ID
    data_eligibility: str = "EXPLORATORY"
    schema_version: str = MR2B_CONTEXT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != MR2B_CONTEXT_SCHEMA_VERSION:
            raise ValueError("unsupported auxiliary-watchlist Context schema")
        if self.definition_id != MR2B_CONTEXT_DEFINITION_ID:
            raise ValueError("unsupported auxiliary-watchlist Context definition")
        if self.grid_definition_id != MR2B_CONTEXT_GRID_DEFINITION_ID:
            raise ValueError("unsupported auxiliary-watchlist grid definition")
        if self.data_eligibility != "EXPLORATORY":
            raise ValueError("auxiliary-watchlist Context authority must remain EXPLORATORY")
        if self.decision_time.tzinfo is None or self.cutoff_time.tzinfo is None:
            raise ValueError("Context times must be timezone-aware")
        if self.cutoff_time.time() != time(14, 50) or self.decision_time.time() != time(14, 55):
            raise ValueError("Context requires exact 14:50 cutoff and 14:55 Decision Time")
        if self.expected_bar_count_per_symbol != 46:
            raise ValueError("Context grid must contain exactly 46 bars")
        if not 0.0 <= self.coverage <= 1.0:
            raise ValueError("Context coverage must be within [0, 1]")
        if self.data_status is ContextDataStatus.AVAILABLE:
            if self.missing_reason is not None or self.watchlist_direction is None:
                raise ValueError("available Context must have metrics and no missing reason")
            if self.available_symbol_count != self.expected_symbol_count or self.coverage != 1.0:
                raise ValueError("available Context requires full accepted-watchlist coverage")
            values = (
                self.watchlist_direction_return,
                self.watchlist_breadth_at_cutoff,
                self.watchlist_intraday_range_to_cutoff,
                self.watchlist_amount_to_cutoff,
                self.prior_watchlist_amount_same_cutoff,
                self.watchlist_amount_change_same_cutoff,
            )
            if any(value is None or not math.isfinite(value) for value in values):
                raise ValueError("available Context metrics must be finite")


def build_auxiliary_watchlist_context(
    *,
    dataset_id: str,
    accepted_symbols: Iterable[str],
    session_dates: Iterable[date],
    bars: Iterable[CompositeBar],
    decision_dates: Iterable[date],
) -> tuple[AuxiliaryWatchlistContext, ...]:
    """Compatibility projection of the complete Context evidence bundle."""

    return build_auxiliary_watchlist_context_evidence(
        dataset_id=dataset_id,
        accepted_symbols=accepted_symbols,
        session_dates=session_dates,
        bars=bars,
        decision_dates=decision_dates,
    ).contexts


def build_auxiliary_watchlist_context_evidence(
    *,
    dataset_id: str,
    accepted_symbols: Iterable[str],
    session_dates: Iterable[date],
    bars: Iterable[CompositeBar],
    decision_dates: Iterable[date],
) -> AuxiliaryWatchlistContextEvidence:
    """Construct exact-cutoff daily Context plus auditable per-symbol evidence."""

    if not isinstance(dataset_id, str) or not dataset_id.strip():
        raise ValueError("dataset_id must be non-empty")
    symbols = tuple(sorted(accepted_symbols))
    if not symbols or len(symbols) != len(set(symbols)):
        raise ValueError("accepted symbols must be non-empty and unique")
    calendar = tuple(session_dates)
    decisions = tuple(decision_dates)
    if calendar != tuple(sorted(calendar)) or len(calendar) != len(set(calendar)):
        raise ValueError("session dates must be chronological and unique")
    if decisions != tuple(sorted(decisions)) or len(decisions) != len(set(decisions)):
        raise ValueError("Decision Dates must be chronological and unique")
    if any(day not in calendar or calendar.index(day) == 0 for day in decisions):
        raise ValueError("each Decision Date requires a previous identified session")
    bar_rows = tuple(bars)
    keys = tuple((bar.symbol, bar.timestamp) for bar in bar_rows)
    if len(keys) != len(set(keys)):
        raise ValueError("Context bar symbol/timestamp keys must be unique")
    indexed = {(bar.symbol, bar.timestamp.date(), _local_time(bar)): bar for bar in bar_rows}
    watchlist_id = canonical_identity_hash(
        {"definition": "accepted-watchlist-symbols-v1", "dataset_id": dataset_id, "symbols": symbols}
    )
    contexts: list[AuxiliaryWatchlistContext] = []
    evidence: list[AuxiliaryWatchlistContextSymbolEvidence] = []
    for day in decisions:
        previous_day = calendar[calendar.index(day) - 1]
        payloads = tuple(
            _symbol_evidence_payload(
                symbol=symbol,
                decision_day=day,
                previous_day=previous_day,
                bars=indexed,
            )
            for symbol in symbols
        )
        context = _context_from_symbol_payloads(
            dataset_id=dataset_id,
            watchlist_id=watchlist_id,
            decision_day=day,
            payloads=payloads,
        )
        contexts.append(context)
        evidence.extend(
            AuxiliaryWatchlistContextSymbolEvidence(
                dataset_id=dataset_id,
                decision_date=day,
                context_id=context.context_id,
                watchlist_id=watchlist_id,
                **payload,
            )
            for payload in payloads
        )
    return AuxiliaryWatchlistContextEvidence(
        contexts=tuple(contexts),
        symbol_evidence=tuple(evidence),
    )


def _symbol_evidence_payload(
    *,
    symbol: str,
    decision_day: date,
    previous_day: date,
    bars: dict[tuple[str, date, time], CompositeBar],
) -> _SymbolEvidencePayload:
    current = tuple(bars.get((symbol, decision_day, endpoint)) for endpoint in CONTEXT_GRID)
    previous = tuple(bars.get((symbol, previous_day, endpoint)) for endpoint in CONTEXT_GRID)
    prior_close_bar = bars.get((symbol, previous_day, time(15, 0)))
    current_count = sum(item is not None for item in current)
    prior_count = sum(item is not None for item in previous)
    common = {
        "symbol": symbol,
        "current_grid_count": current_count,
        "prior_grid_count": prior_count,
        "has_exact_1450": current[-1] is not None,
        "has_prior_exact_1450": previous[-1] is not None,
        "has_prior_close_1500": prior_close_bar is not None,
        "close_1450": None,
        "prior_close_1500": None,
        "return_to_1450": None,
        "intraday_high_to_1450": None,
        "intraday_low_to_1450": None,
        "intraday_range_to_1450": None,
        "amount_to_1450": None,
        "prior_amount_same_cutoff": None,
        "evidence_status": ContextDataStatus.UNAVAILABLE,
    }
    if current[-1] is None:
        return cast(
            _SymbolEvidencePayload,
            {**common, "missing_reason": ContextMissingReason.EXACT_1450_ENDPOINT_MISSING},
        )
    if any(item is None for item in current):
        return cast(
            _SymbolEvidencePayload,
            {**common, "missing_reason": ContextMissingReason.INCOMPLETE_CUTOFF_GRID},
        )
    if any(item is None for item in previous):
        return cast(
            _SymbolEvidencePayload,
            {
                **common,
                "missing_reason": ContextMissingReason.PRIOR_SESSION_INCOMPLETE_CUTOFF_GRID,
            },
        )
    if prior_close_bar is None:
        return cast(
            _SymbolEvidencePayload,
            {**common, "missing_reason": ContextMissingReason.PRIOR_SESSION_CLOSE_MISSING},
        )
    current_complete = tuple(item for item in current if item is not None)
    previous_complete = tuple(item for item in previous if item is not None)
    close_1450 = current_complete[-1].close
    prior_close = prior_close_bar.close
    high = max(item.high for item in current_complete)
    low = min(item.low for item in current_complete)
    prior_amount = sum(item.amount for item in previous_complete)
    if close_1450 <= 0.0 or prior_close <= 0.0 or prior_amount <= 0.0:
        raise ValueError("Context price and previous-session same-cutoff amount must be positive")
    return cast(
        _SymbolEvidencePayload,
        {
            **common,
            "close_1450": close_1450,
            "prior_close_1500": prior_close,
            "return_to_1450": close_1450 / prior_close - 1.0,
            "intraday_high_to_1450": high,
            "intraday_low_to_1450": low,
            "intraday_range_to_1450": (high - low) / close_1450,
            "amount_to_1450": sum(item.amount for item in current_complete),
            "prior_amount_same_cutoff": prior_amount,
            "evidence_status": ContextDataStatus.AVAILABLE,
            "missing_reason": None,
        },
    )


def _context_from_symbol_payloads(
    *,
    dataset_id: str,
    watchlist_id: str,
    decision_day: date,
    payloads: tuple[_SymbolEvidencePayload, ...],
) -> AuxiliaryWatchlistContext:
    expected = len(payloads)
    available_rows = tuple(
        row for row in payloads if row["evidence_status"] is ContextDataStatus.AVAILABLE
    )
    available = len(available_rows)
    common = {
        "decision_date": decision_day,
        "decision_time": datetime.combine(decision_day, time(14, 55), tzinfo=_SHANGHAI),
        "cutoff_time": datetime.combine(decision_day, time(14, 50), tzinfo=_SHANGHAI),
        "dataset_id": dataset_id,
        "watchlist_id": watchlist_id,
        "expected_symbol_count": expected,
        "available_symbol_count": available,
        "coverage": available / expected,
        "expected_bar_count_per_symbol": len(CONTEXT_GRID),
        "available_bar_count_per_symbol": min(row["current_grid_count"] for row in payloads),
    }
    if available != expected:
        reason = next(
            row["missing_reason"] for row in payloads if row["missing_reason"] is not None
        )
        return _identified_context(
            **common,
            grid_status="INCOMPLETE",
            data_status=ContextDataStatus.UNAVAILABLE,
            missing_reason=reason,
            symbol_payloads=payloads,
        )
    symbol_returns = tuple(cast(float, row["return_to_1450"]) for row in available_rows)
    ranges = tuple(cast(float, row["intraday_range_to_1450"]) for row in available_rows)
    current_amount = sum(cast(float, row["amount_to_1450"]) for row in available_rows)
    previous_amount = sum(
        cast(float, row["prior_amount_same_cutoff"]) for row in available_rows
    )
    direction_return = sum(symbol_returns) / expected
    direction = (
        WatchlistDirection.UP
        if direction_return > 1e-12
        else WatchlistDirection.DOWN
        if direction_return < -1e-12
        else WatchlistDirection.FLAT
    )
    return _identified_context(
        **common,
        grid_status="COMPLETE",
        data_status=ContextDataStatus.AVAILABLE,
        missing_reason=None,
        watchlist_direction_return=direction_return,
        watchlist_direction=direction,
        watchlist_breadth_at_cutoff=sum(value > 0.0 for value in symbol_returns) / expected,
        watchlist_intraday_range_to_cutoff=sum(ranges) / expected,
        watchlist_amount_to_cutoff=current_amount,
        prior_watchlist_amount_same_cutoff=previous_amount,
        watchlist_amount_change_same_cutoff=current_amount / previous_amount - 1.0,
        symbol_payloads=payloads,
    )


def _identified_context(**values: object) -> AuxiliaryWatchlistContext:
    symbol_payloads = cast(
        tuple[_SymbolEvidencePayload, ...], values.pop("symbol_payloads", ())
    )
    metrics = {
        "watchlist_direction_return": None,
        "watchlist_direction": None,
        "watchlist_breadth_at_cutoff": None,
        "watchlist_intraday_range_to_cutoff": None,
        "watchlist_amount_to_cutoff": None,
        "prior_watchlist_amount_same_cutoff": None,
        "watchlist_amount_change_same_cutoff": None,
        **values,
    }
    identity_values = {
        key: (value.value if isinstance(value, Enum) else value.isoformat() if isinstance(value, (date, datetime)) else value)
        for key, value in metrics.items()
        if key != "context_id"
    }
    context_id = canonical_identity_hash(
        {
            "schema_version": MR2B_CONTEXT_SCHEMA_VERSION,
            "definition_id": MR2B_CONTEXT_DEFINITION_ID,
            "grid_definition_id": MR2B_CONTEXT_GRID_DEFINITION_ID,
            "coverage_policy_id": MR2B_CONTEXT_COVERAGE_POLICY_ID,
            "direction_label_policy_id": MR2B_DIRECTION_LABEL_POLICY_ID,
            "evidence": identity_values,
            "symbol_evidence": [
                _canonical_symbol_payload(payload) for payload in symbol_payloads
            ],
        }
    )
    return AuxiliaryWatchlistContext(context_id=context_id, **metrics)  # type: ignore[arg-type]


def context_record(context: AuxiliaryWatchlistContext) -> dict[str, object]:
    """Return a stable Parquet-ready record."""

    row = asdict(context)
    for key, value in tuple(row.items()):
        if isinstance(value, Enum):
            row[key] = value.value
        elif isinstance(value, (date, datetime)):
            row[key] = value.isoformat()
    return row


def context_symbol_evidence_record(
    evidence: AuxiliaryWatchlistContextSymbolEvidence,
) -> dict[str, object]:
    row = asdict(evidence)
    for key, value in tuple(row.items()):
        if isinstance(value, Enum):
            row[key] = value.value
        elif isinstance(value, (date, datetime)):
            row[key] = value.isoformat()
    return row


def validate_context_reconstruction(
    context: AuxiliaryWatchlistContext,
    evidence: Iterable[AuxiliaryWatchlistContextSymbolEvidence],
) -> None:
    """Fail closed unless the daily Context exactly projects its symbol evidence."""

    rows = tuple(sorted(evidence, key=lambda item: item.symbol))
    if not rows or len(rows) != len({item.symbol for item in rows}):
        raise ValueError("Context symbol evidence must be non-empty and unique")
    if any(
        item.dataset_id != context.dataset_id
        or item.decision_date != context.decision_date
        or item.context_id != context.context_id
        or item.watchlist_id != context.watchlist_id
        for item in rows
    ):
        raise ValueError("Context symbol evidence identity mismatch")
    payloads = tuple(_symbol_payload_from_evidence(item) for item in rows)
    expected = _context_from_symbol_payloads(
        dataset_id=context.dataset_id,
        watchlist_id=context.watchlist_id,
        decision_day=context.decision_date,
        payloads=payloads,
    )
    if context_record(expected) != context_record(context):
        raise ValueError("daily Context cannot be reconstructed from symbol evidence")


def _symbol_payload_from_evidence(
    evidence: AuxiliaryWatchlistContextSymbolEvidence,
) -> _SymbolEvidencePayload:
    row = asdict(evidence)
    for key in (
        "schema_version",
        "dataset_id",
        "decision_date",
        "context_id",
        "watchlist_id",
        "data_eligibility",
    ):
        row.pop(key)
    row["evidence_status"] = evidence.evidence_status
    row["missing_reason"] = evidence.missing_reason
    return cast(_SymbolEvidencePayload, row)


def _canonical_symbol_payload(payload: _SymbolEvidencePayload) -> dict[str, object]:
    return {
        key: value.value if isinstance(value, Enum) else value
        for key, value in sorted(payload.items())
    }


def _local_time(bar: CompositeBar) -> time:
    return bar.timestamp.astimezone(_SHANGHAI).time().replace(tzinfo=None)
