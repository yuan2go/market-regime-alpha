"""Conservative Xuntou P0 native-export adapter for R5 rehearsal evidence.

The adapter translates an identified JSON-compatible export into existing canonical contracts. It
does not import XtQuant, call a provider runtime, infer historical PIT authority, or grant more than
REHEARSAL data eligibility.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from enum import Enum
from hashlib import sha256
import json
import math
from pathlib import Path
import re
from statistics import median
from typing import NoReturn
from zoneinfo import ZoneInfo

from market_regime_alpha.core.identity import ArtifactId, DatasetId, ProviderId
from market_regime_alpha.core.time import (
    AsOfTime,
    AvailabilityTime,
    DecisionTime,
    RetrievedAt,
)
from market_regime_alpha.data.contracts import ProviderReference, SourceArtifactReference
from market_regime_alpha.data.rehearsal import (
    RehearsalDailyBar,
    RehearsalDecisionSnapshot,
    RehearsalNextSessionBar,
)
from market_regime_alpha.data.trading_calendar import (
    TradingCalendarArtifact,
    TradingSession,
    build_trading_calendar_artifact,
)
from market_regime_alpha.research.provider_rehearsal_market_artifact import (
    ProviderRehearsalMarketArtifact,
    build_provider_rehearsal_market_artifact,
)
from market_regime_alpha.universe.artifacts import (
    HistoricalPITUniverseArtifact,
    HistoricalUniverseMembershipRecord,
    build_historical_pit_universe_artifact,
)
from market_regime_alpha.universe.eligibility_policy import (
    DecisionBuyabilityStatus,
    RawTradingEligibilityObservation,
)


XUNTOU_P0_NATIVE_BUNDLE_SCHEMA_VERSION = "xuntou-p0-native-bundle-v1"
XUNTOU_P0_MAPPING_CONTRACT_VERSION = "xuntou-p0-native-field-mapping-v1"
XUNTOU_P0_PROVIDER_ID = ProviderId("xuntou-thinktrader-xtquant-p0-v1")
XUNTOU_P0_PRODUCT = "ThinkTrader/XtQuant normalized native export"

XUNTOU_SYMBOL_NORMALIZATION_VERSION = "XUNTOU_SYMBOL_NORMALIZATION_V1"
XUNTOU_CALENDAR_CLOSE_CONVENTION = (
    "A_SHARE_STANDARD_SESSION_CLOSE_1500_ASIA_SHANGHAI_V1"
)
XUNTOU_DECISION_SNAPSHOT_CONVENTION = "XUNTOU_1455_REFERENCE_PRICE_CONVENTION_V1"
XUNTOU_AVAILABILITY_CONVENTION = "XUNTOU_EXPLICIT_EXPORT_AVAILABILITY_V1"
XUNTOU_BAR_FINALITY_CONVENTION = "XUNTOU_EXPLICIT_EXPORT_FINALITY_V1"
XUNTOU_PRICE_ADJUSTMENT_BASIS = "XUNTOU_DIVIDEND_TYPE_NONE_RAW_V1"
XUNTOU_LIQUIDITY_MEASURE_ID = "MEDIAN_AMOUNT_PREVIOUS_20_FINAL_SESSIONS_CNY_V1"
XUNTOU_UNIVERSE_EFFECTIVE_TIME_CONVENTION = (
    "XUNTOU_EXPLICIT_DATE_MEMBERSHIP_UNVERIFIED_PIT_V1"
)
XUNTOU_BUYABILITY_CONVENTION = "XUNTOU_DECISION_BUYABILITY_EVIDENCE_V1"
XUNTOU_RETRIEVAL_CONVENTION = "XUNTOU_NORMALIZED_NATIVE_EXPORT_SHA256_V1"
XUNTOU_RAW_ELIGIBILITY_CONVENTION = "XUNTOU_RAW_ELIGIBILITY_MATERIALIZATION_V1"

_TIMEZONE_NAME = "Asia/Shanghai"
_ZONE = ZoneInfo(_TIMEZONE_NAME)
_SYMBOL_PATTERN = re.compile(r"^[0-9]{6}\.(?:SH|SZ|BJ)$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_OPEN_DATE_SENTINELS = {
    "19700101",
    "19700102",
    "19700103",
    "19700104",
    "19700105",
    "19700106",
}

_REQUIRED_CONVENTIONS = {
    "symbol_normalization": XUNTOU_SYMBOL_NORMALIZATION_VERSION,
    "calendar_close": XUNTOU_CALENDAR_CLOSE_CONVENTION,
    "decision_snapshot": XUNTOU_DECISION_SNAPSHOT_CONVENTION,
    "availability": XUNTOU_AVAILABILITY_CONVENTION,
    "bar_finality": XUNTOU_BAR_FINALITY_CONVENTION,
    "price_adjustment_basis": XUNTOU_PRICE_ADJUSTMENT_BASIS,
    "liquidity": XUNTOU_LIQUIDITY_MEASURE_ID,
    "universe_effective_time": XUNTOU_UNIVERSE_EFFECTIVE_TIME_CONVENTION,
    "buyability": XUNTOU_BUYABILITY_CONVENTION,
}

_BASE_LIMITATIONS = (
    "CURRENT_MEMBERSHIP_BACKFILL_BIAS",
    "XUNTOU_HISTORICAL_PIT_UNVERIFIED",
    "XUNTOU_1M_BAR_LABEL_SEMANTICS_UNVERIFIED",
    "XUNTOU_EXPORT_AVAILABILITY_ASSERTION_UNVERIFIED",
    "XUNTOU_LIMIT_REGIME_IDENTITY_UNVERIFIED",
    "XUNTOU_RUNTIME_EXTRACTION_NOT_EXECUTED",
)


class XuntouP0EvidenceClassification(str, Enum):
    """Required P0 mapping confidence classes."""

    DIRECT_NATIVE = "DIRECT_NATIVE"
    DERIVED_FROM_NATIVE = "DERIVED_FROM_NATIVE"
    REQUIRES_STATE_MATERIALIZATION = "REQUIRES_STATE_MATERIALIZATION"
    CURRENT_ONLY_NOT_HISTORICAL_PIT = "CURRENT_ONLY_NOT_HISTORICAL_PIT"
    UNVERIFIED = "UNVERIFIED"
    UNAVAILABLE_IN_P0 = "UNAVAILABLE_IN_P0"


class XuntouProviderAdapterErrorCode(str, Enum):
    """Stable semantic failure codes for the Xuntou P0 boundary."""

    REQUIRED_SECTION_MISSING = "XUNTOU_REQUIRED_SECTION_MISSING"
    FIELD_UNSUPPORTED = "XUNTOU_FIELD_UNSUPPORTED"
    TIMEZONE_REQUIRED = "XUNTOU_TIMEZONE_REQUIRED"
    DECISION_SNAPSHOT_AMBIGUOUS = "XUNTOU_DECISION_SNAPSHOT_AMBIGUOUS"
    HISTORICAL_PIT_UNVERIFIED = "XUNTOU_HISTORICAL_PIT_UNVERIFIED"
    INSTRUMENT_TYPE_UNSUPPORTED = "XUNTOU_INSTRUMENT_TYPE_UNSUPPORTED"
    NATIVE_SCHEMA_UNSUPPORTED = "XUNTOU_NATIVE_SCHEMA_UNSUPPORTED"
    CONTENT_HASH_MISMATCH = "XUNTOU_CONTENT_HASH_MISMATCH"
    INVALID_NATIVE_VALUE = "XUNTOU_INVALID_NATIVE_VALUE"
    NEXT_SESSION_EVIDENCE_MISSING = "XUNTOU_NEXT_SESSION_EVIDENCE_MISSING"


class XuntouProviderAdapterError(ValueError):
    """A provider-boundary error with a stable machine-readable code."""

    def __init__(self, code: XuntouProviderAdapterErrorCode, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code.value}: {detail}")


@dataclass(frozen=True, slots=True)
class _NativeBar:
    symbol: str
    observed_at: datetime
    session_date: date
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float
    pre_close: float | None
    suspend_flag: int | None
    available_at: datetime
    finalized: bool
    buyability_evidence_complete: bool


@dataclass(frozen=True, slots=True)
class _SecurityEvidence:
    listing_date: date | None
    available_at: datetime | None


@dataclass(frozen=True, slots=True)
class _StEvidence:
    lookup_complete: bool
    available_at: datetime
    periods: tuple[tuple[date, date], ...]


@dataclass(frozen=True, slots=True)
class _LimitEvidence:
    symbol: str
    session_date: date
    limit_up_price: float | None
    limit_down_price: float | None
    limit_regime: str | None
    available_at: datetime


def load_xuntou_p0_native_bundle(path: str | Path) -> ProviderRehearsalMarketArtifact:
    """Load one JSON export, hash its exact bytes, and adapt it without importing XtQuant."""

    source_path = Path(path)
    raw_bytes = source_path.read_bytes()
    content_hash = sha256(raw_bytes).hexdigest()
    try:
        payload = json.loads(raw_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise XuntouProviderAdapterError(
            XuntouProviderAdapterErrorCode.NATIVE_SCHEMA_UNSUPPORTED,
            "bundle must be UTF-8 JSON",
        ) from exc
    if not isinstance(payload, Mapping):
        _raise(
            XuntouProviderAdapterErrorCode.NATIVE_SCHEMA_UNSUPPORTED,
            "bundle root must be an object",
        )
    return adapt_xuntou_p0_native_mapping(
        payload,
        computed_content_hash=content_hash,
        default_locator=str(source_path),
    )


def adapt_xuntou_p0_native_mapping(
    payload: Mapping[str, object],
    *,
    computed_content_hash: str | None = None,
    default_locator: str | None = None,
) -> ProviderRehearsalMarketArtifact:
    """Translate a normalized Xuntou P0 export into existing REHEARSAL contracts.

    In-memory callers must declare a SHA-256 in ``source_artifact.content_hash``. File callers use
    :func:`load_xuntou_p0_native_bundle`, which computes the hash from the exact file bytes.
    Historical PIT correctness is deliberately fixed to ``False`` for this P0 contract.
    """

    schema_version = _required_string(payload, "schema_version", "bundle")
    if schema_version != XUNTOU_P0_NATIVE_BUNDLE_SCHEMA_VERSION:
        _raise(
            XuntouProviderAdapterErrorCode.NATIVE_SCHEMA_UNSUPPORTED,
            f"unsupported schema_version {schema_version!r}",
        )

    source = _required_mapping(payload, "source_artifact", "bundle")
    content_hash = _resolve_content_hash(source, computed_content_hash)
    retrieved_at = RetrievedAt(_parse_aware_datetime(source.get("retrieved_at"), "retrieved_at"))
    locator_value = source.get("locator") or default_locator
    if not isinstance(locator_value, str) or not locator_value.strip():
        _raise(
            XuntouProviderAdapterErrorCode.REQUIRED_SECTION_MISSING,
            "source_artifact.locator is required",
        )
    locator = locator_value.strip()

    conventions = _required_mapping(payload, "conventions", "bundle")
    _validate_conventions(conventions)

    provider_reference = ProviderReference(
        provider_id=XUNTOU_P0_PROVIDER_ID,
        product=XUNTOU_P0_PRODUCT,
        contract_version=XUNTOU_P0_MAPPING_CONTRACT_VERSION,
    )
    source_artifact = SourceArtifactReference(
        artifact_id=ArtifactId(f"xuntou-p0-source-{content_hash[:24]}"),
        provider_id=XUNTOU_P0_PROVIDER_ID,
        retrieved_at=retrieved_at,
        content_hash=content_hash,
        locator=locator,
    )

    securities = _parse_securities(_required_sequence(payload, "securities", "bundle"))
    accepted_symbols = frozenset(securities)
    if not accepted_symbols:
        _raise(
            XuntouProviderAdapterErrorCode.INSTRUMENT_TYPE_UNSUPPORTED,
            "bundle contains no explicitly classified A-share stocks",
        )

    calendar = _build_calendar(
        _required_mapping(payload, "calendar", "bundle"),
        content_hash=content_hash,
    )
    universe = _build_universe(
        _required_mapping(payload, "universe", "bundle"),
        accepted_symbols=accepted_symbols,
        content_hash=content_hash,
    )

    daily_native = _parse_bars(
        _required_sequence(payload, "daily_bars", "bundle"),
        accepted_symbols=accepted_symbols,
        section="daily_bars",
        intraday=False,
    )
    minute_native = _parse_bars(
        _required_sequence(payload, "minute_bars", "bundle"),
        accepted_symbols=accepted_symbols,
        section="minute_bars",
        intraday=True,
    )
    decision_times = _parse_decision_times(
        _required_sequence(payload, "decision_times", "bundle")
    )
    st_by_symbol = _parse_st_history(
        _optional_sequence(payload, "st_history"), accepted_symbols=accepted_symbols
    )
    limits_by_key = _parse_limit_prices(
        _optional_sequence(payload, "limit_prices"), accepted_symbols=accepted_symbols
    )

    daily_bars = tuple(
        RehearsalDailyBar(
            symbol=bar.symbol,
            session_date=bar.session_date,
            close=bar.close,
            amount=bar.amount,
            available_at=AvailabilityTime(bar.available_at),
            finalized=bar.finalized,
        )
        for bar in daily_native
    )
    if not daily_bars:
        _raise(
            XuntouProviderAdapterErrorCode.REQUIRED_SECTION_MISSING,
            "no accepted finalized daily bars remain after instrument filtering",
        )

    positive_members_by_date = _positive_members_by_date(universe)
    selected_minutes: dict[tuple[datetime, str], _NativeBar] = {}
    decision_snapshots: list[RehearsalDecisionSnapshot] = []
    for decision_time in decision_times:
        members = positive_members_by_date.get(decision_time.astimezone(_ZONE).date(), frozenset())
        for symbol in sorted(members):
            selected = _select_decision_bar(
                minute_native,
                symbol=symbol,
                decision_time=decision_time,
            )
            if selected is None:
                continue
            selected_minutes[(decision_time, symbol)] = selected
            decision_snapshots.append(
                RehearsalDecisionSnapshot(
                    symbol=symbol,
                    decision_time=DecisionTime(decision_time),
                    reference_price=selected.close,
                    available_at=AvailabilityTime(selected.available_at),
                )
            )
    if not decision_snapshots:
        _raise(
            XuntouProviderAdapterErrorCode.DECISION_SNAPSHOT_AMBIGUOUS,
            "no completed minute close was explicitly available by any Decision Time",
        )

    raw_eligibility = _build_raw_eligibility(
        selected_minutes=selected_minutes,
        securities=securities,
        daily_bars=daily_native,
        st_by_symbol=st_by_symbol,
        limits_by_key=limits_by_key,
    )
    if not raw_eligibility:
        _raise(
            XuntouProviderAdapterErrorCode.REQUIRED_SECTION_MISSING,
            "no raw eligibility observations could be materialized",
        )

    next_session_bars = _build_next_session_bars(
        decision_snapshots=tuple(decision_snapshots),
        daily_native=daily_native,
        trading_calendar=calendar,
    )
    if not next_session_bars:
        _raise(
            XuntouProviderAdapterErrorCode.NEXT_SESSION_EVIDENCE_MISSING,
            "no finalized next-session OHLC matched a calendar-resolved next session",
        )

    limitations = list(_BASE_LIMITATIONS)
    limitations.extend(_parse_limitations(_optional_sequence(payload, "limitations")))
    if not st_by_symbol:
        limitations.append("XUNTOU_HISTORICAL_ST_EVIDENCE_NOT_PRESENT")
    if not limits_by_key:
        limitations.append("XUNTOU_HISTORICAL_LIMIT_PRICE_EVIDENCE_NOT_PRESENT")

    return build_provider_rehearsal_market_artifact(
        provider_references=(provider_reference,),
        source_artifacts=(source_artifact,),
        retrieval_convention=XUNTOU_RETRIEVAL_CONVENTION,
        market_availability_convention=XUNTOU_AVAILABILITY_CONVENTION,
        raw_eligibility_evidence_convention=(
            f"{XUNTOU_RAW_ELIGIBILITY_CONVENTION};{XUNTOU_BUYABILITY_CONVENTION};"
            f"{XUNTOU_LIQUIDITY_MEASURE_ID}"
        ),
        bar_finality_convention=XUNTOU_BAR_FINALITY_CONVENTION,
        price_adjustment_basis=XUNTOU_PRICE_ADJUSTMENT_BASIS,
        trading_calendar=calendar,
        universe_artifact=universe,
        daily_bars=daily_bars,
        decision_snapshots=tuple(decision_snapshots),
        next_session_bars=next_session_bars,
        raw_eligibility_observations=raw_eligibility,
        pit_correct_for_scope=False,
        limitations=tuple(sorted(set(limitations))),
    )


def _build_calendar(
    section: Mapping[str, object], *, content_hash: str
) -> TradingCalendarArtifact:
    market = _required_string(section, "market", "calendar")
    raw_dates = _required_sequence(section, "trade_dates", "calendar")
    trade_dates = tuple(
        sorted({_parse_native_date(item, "calendar.trade_dates") for item in raw_dates})
    )
    if not trade_dates:
        _raise(
            XuntouProviderAdapterErrorCode.REQUIRED_SECTION_MISSING,
            "calendar.trade_dates must not be empty",
        )
    sessions = tuple(
        TradingSession(
            trade_date=trade_date,
            session_close=datetime.combine(trade_date, time(15, 0), tzinfo=_ZONE),
        )
        for trade_date in trade_dates
    )
    return build_trading_calendar_artifact(
        source_dataset_id=DatasetId(f"xuntou-calendar-source-{content_hash[:24]}"),
        market=market,
        calendar_version=(
            f"{XUNTOU_P0_MAPPING_CONTRACT_VERSION};{XUNTOU_CALENDAR_CLOSE_CONVENTION}"
        ),
        timezone_name=_TIMEZONE_NAME,
        sessions=sessions,
    )


def _build_universe(
    section: Mapping[str, object],
    *,
    accepted_symbols: frozenset[str],
    content_hash: str,
) -> HistoricalPITUniverseArtifact:
    pit_status = _required_string(section, "historical_pit_status", "universe")
    if pit_status not in {
        XuntouP0EvidenceClassification.CURRENT_ONLY_NOT_HISTORICAL_PIT.value,
        XuntouP0EvidenceClassification.UNVERIFIED.value,
    }:
        _raise(
            XuntouProviderAdapterErrorCode.HISTORICAL_PIT_UNVERIFIED,
            "P0 accepts only CURRENT_ONLY_NOT_HISTORICAL_PIT or UNVERIFIED universe status",
        )
    records: list[HistoricalUniverseMembershipRecord] = []
    for index, item in enumerate(_required_sequence(section, "records", "universe")):
        row = _as_mapping(item, f"universe.records[{index}]")
        symbol = _parse_symbol(row.get("stock_code"), f"universe.records[{index}].stock_code")
        if symbol not in accepted_symbols:
            continue
        is_member = row.get("is_member")
        if not isinstance(is_member, bool):
            _raise(
                XuntouProviderAdapterErrorCode.INVALID_NATIVE_VALUE,
                f"universe.records[{index}].is_member must be boolean",
            )
        records.append(
            HistoricalUniverseMembershipRecord(
                as_of_date=_parse_native_date(
                    row.get("as_of_date"), f"universe.records[{index}].as_of_date"
                ),
                symbol=symbol,
                is_member=is_member,
            )
        )
    if not records:
        _raise(
            XuntouProviderAdapterErrorCode.REQUIRED_SECTION_MISSING,
            "no A-share universe membership records remain after filtering",
        )
    return build_historical_pit_universe_artifact(
        source_dataset_id=DatasetId(f"xuntou-universe-source-{content_hash[:24]}"),
        method_version=(
            f"{XUNTOU_P0_MAPPING_CONTRACT_VERSION};{XUNTOU_SYMBOL_NORMALIZATION_VERSION}"
        ),
        timezone_name=_TIMEZONE_NAME,
        effective_time_convention=XUNTOU_UNIVERSE_EFFECTIVE_TIME_CONVENTION,
        records=tuple(records),
    )


def _parse_securities(items: Sequence[object]) -> dict[str, _SecurityEvidence]:
    securities: dict[str, _SecurityEvidence] = {}
    for index, item in enumerate(items):
        row = _as_mapping(item, f"securities[{index}]")
        symbol = _parse_symbol(row.get("stock_code"), f"securities[{index}].stock_code")
        instrument_type = _required_string(row, "instrument_type", f"securities[{index}]")
        if instrument_type != "A_SHARE_STOCK":
            continue
        if symbol in securities:
            _raise(
                XuntouProviderAdapterErrorCode.INVALID_NATIVE_VALUE,
                f"duplicate security {symbol}",
            )
        available_raw = row.get("available_at")
        available_at = (
            None
            if available_raw is None
            else _parse_aware_datetime(available_raw, f"securities[{index}].available_at")
        )
        securities[symbol] = _SecurityEvidence(
            listing_date=_parse_open_date(row.get("OpenDate")),
            available_at=available_at,
        )
    return securities


def _parse_bars(
    items: Sequence[object],
    *,
    accepted_symbols: frozenset[str],
    section: str,
    intraday: bool,
) -> tuple[_NativeBar, ...]:
    bars: list[_NativeBar] = []
    seen: set[tuple[str, datetime]] = set()
    for index, item in enumerate(items):
        row = _as_mapping(item, f"{section}[{index}]")
        symbol = _parse_symbol(row.get("stock_code"), f"{section}[{index}].stock_code")
        if symbol not in accepted_symbols:
            continue
        observed_at = (
            _parse_aware_datetime(row.get("time"), f"{section}[{index}].time")
            if intraday
            else _native_date_as_datetime(row.get("time"), f"{section}[{index}].time")
        )
        key = (symbol, observed_at)
        if key in seen:
            _raise(
                XuntouProviderAdapterErrorCode.INVALID_NATIVE_VALUE,
                f"duplicate {section} key {symbol} {observed_at.isoformat()}",
            )
        seen.add(key)
        finalized = row.get("finalized")
        if finalized is not True:
            _raise(
                XuntouProviderAdapterErrorCode.INVALID_NATIVE_VALUE,
                f"{section}[{index}] must be explicitly finalized",
            )
        open_price = _positive_float(row.get("open"), f"{section}[{index}].open")
        high_price = _positive_float(row.get("high"), f"{section}[{index}].high")
        low_price = _positive_float(row.get("low"), f"{section}[{index}].low")
        close_price = _positive_float(row.get("close"), f"{section}[{index}].close")
        if (
            not low_price <= open_price <= high_price
            or not low_price <= close_price <= high_price
        ):
            _raise(
                XuntouProviderAdapterErrorCode.INVALID_NATIVE_VALUE,
                f"{section}[{index}] requires low <= open/close <= high",
            )
        bars.append(
            _NativeBar(
                symbol=symbol,
                observed_at=observed_at,
                session_date=observed_at.astimezone(_ZONE).date(),
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
                volume=_non_negative_float(
                    row.get("volume"), f"{section}[{index}].volume"
                ),
                amount=_non_negative_float(
                    row.get("amount"), f"{section}[{index}].amount"
                ),
                pre_close=_optional_positive_float(
                    row.get("preClose"), f"{section}[{index}].preClose"
                ),
                suspend_flag=_parse_suspend_flag(
                    row.get("suspendFlag"), f"{section}[{index}].suspendFlag"
                ),
                available_at=_parse_aware_datetime(
                    row.get("available_at"), f"{section}[{index}].available_at"
                ),
                finalized=True,
                buyability_evidence_complete=_optional_bool(
                    row.get("buyability_evidence_complete"),
                    f"{section}[{index}].buyability_evidence_complete",
                    default=False,
                ),
            )
        )
    return tuple(sorted(bars, key=lambda bar: (bar.observed_at, bar.symbol)))


def _parse_decision_times(items: Sequence[object]) -> tuple[datetime, ...]:
    values: list[datetime] = []
    for index, item in enumerate(items):
        value = item.get("decision_time") if isinstance(item, Mapping) else item
        parsed = _parse_aware_datetime(value, f"decision_times[{index}]")
        local = parsed.astimezone(_ZONE)
        if local.time().replace(tzinfo=None) != time(14, 55):
            _raise(
                XuntouProviderAdapterErrorCode.INVALID_NATIVE_VALUE,
                f"decision_times[{index}] must be 14:55:00 Asia/Shanghai",
            )
        values.append(parsed)
    if not values:
        _raise(
            XuntouProviderAdapterErrorCode.REQUIRED_SECTION_MISSING,
            "decision_times must not be empty",
        )
    if len(values) != len(set(values)):
        _raise(
            XuntouProviderAdapterErrorCode.INVALID_NATIVE_VALUE,
            "decision_times must be unique",
        )
    return tuple(sorted(values))


def _parse_st_history(
    items: Sequence[object], *, accepted_symbols: frozenset[str]
) -> dict[str, _StEvidence]:
    output: dict[str, _StEvidence] = {}
    for index, item in enumerate(items):
        row = _as_mapping(item, f"st_history[{index}]")
        symbol = _parse_symbol(row.get("stock_code"), f"st_history[{index}].stock_code")
        if symbol not in accepted_symbols:
            continue
        if symbol in output:
            _raise(
                XuntouProviderAdapterErrorCode.INVALID_NATIVE_VALUE,
                f"duplicate ST history for {symbol}",
            )
        lookup_complete = row.get("lookup_complete")
        if not isinstance(lookup_complete, bool):
            _raise(
                XuntouProviderAdapterErrorCode.INVALID_NATIVE_VALUE,
                f"st_history[{index}].lookup_complete must be boolean",
            )
        periods_mapping = _required_mapping(row, "periods", f"st_history[{index}]")
        periods: list[tuple[date, date]] = []
        for label in ("ST", "*ST", "PT"):
            raw_periods = periods_mapping.get(label, ())
            if not isinstance(raw_periods, Sequence) or isinstance(raw_periods, (str, bytes)):
                _raise(
                    XuntouProviderAdapterErrorCode.INVALID_NATIVE_VALUE,
                    f"st_history[{index}].periods[{label!r}] must be a sequence",
                )
            for period_index, period in enumerate(raw_periods):
                if (
                    not isinstance(period, Sequence)
                    or isinstance(period, (str, bytes))
                    or len(period) != 2
                ):
                    _raise(
                        XuntouProviderAdapterErrorCode.INVALID_NATIVE_VALUE,
                        f"ST period {label}[{period_index}] must contain start and end",
                    )
                start = _parse_native_date(period[0], f"ST {label}[{period_index}] start")
                end = _parse_native_date(period[1], f"ST {label}[{period_index}] end")
                if end < start:
                    _raise(
                        XuntouProviderAdapterErrorCode.INVALID_NATIVE_VALUE,
                        f"ST period {label}[{period_index}] ends before it starts",
                    )
                periods.append((start, end))
        output[symbol] = _StEvidence(
            lookup_complete=lookup_complete,
            available_at=_parse_aware_datetime(
                row.get("available_at"), f"st_history[{index}].available_at"
            ),
            periods=tuple(periods),
        )
    return output


def _parse_limit_prices(
    items: Sequence[object], *, accepted_symbols: frozenset[str]
) -> dict[tuple[date, str], _LimitEvidence]:
    output: dict[tuple[date, str], _LimitEvidence] = {}
    for index, item in enumerate(items):
        row = _as_mapping(item, f"limit_prices[{index}]")
        symbol = _parse_symbol(row.get("stock_code"), f"limit_prices[{index}].stock_code")
        if symbol not in accepted_symbols:
            continue
        session_date = _parse_native_date(row.get("time"), f"limit_prices[{index}].time")
        key = (session_date, symbol)
        if key in output:
            _raise(
                XuntouProviderAdapterErrorCode.INVALID_NATIVE_VALUE,
                f"duplicate limit price for {symbol} on {session_date}",
            )
        regime = row.get("limit_regime")
        if regime is not None and (not isinstance(regime, str) or not regime.strip()):
            _raise(
                XuntouProviderAdapterErrorCode.INVALID_NATIVE_VALUE,
                f"limit_prices[{index}].limit_regime must be a non-empty string or null",
            )
        output[key] = _LimitEvidence(
            symbol=symbol,
            session_date=session_date,
            limit_up_price=_optional_positive_float(
                row.get("涨停价"), f"limit_prices[{index}].涨停价"
            ),
            limit_down_price=_optional_positive_float(
                row.get("跌停价"), f"limit_prices[{index}].跌停价"
            ),
            limit_regime=regime.strip() if isinstance(regime, str) else None,
            available_at=_parse_aware_datetime(
                row.get("available_at"), f"limit_prices[{index}].available_at"
            ),
        )
    return output


def _positive_members_by_date(
    universe: HistoricalPITUniverseArtifact,
) -> dict[date, frozenset[str]]:
    return {
        snapshot.as_of.value.astimezone(_ZONE).date(): frozenset(
            record.symbol for record in snapshot.records if record.is_member
        )
        for snapshot in universe.snapshots
    }


def _select_decision_bar(
    minute_bars: tuple[_NativeBar, ...], *, symbol: str, decision_time: datetime
) -> _NativeBar | None:
    local_date = decision_time.astimezone(_ZONE).date()
    eligible = tuple(
        bar
        for bar in minute_bars
        if bar.symbol == symbol
        and bar.session_date == local_date
        and bar.observed_at <= decision_time
        and bar.available_at <= decision_time
        and bar.finalized
    )
    if not eligible:
        return None
    return max(eligible, key=lambda bar: (bar.observed_at, bar.available_at))


def _build_raw_eligibility(
    *,
    selected_minutes: Mapping[tuple[datetime, str], _NativeBar],
    securities: Mapping[str, _SecurityEvidence],
    daily_bars: tuple[_NativeBar, ...],
    st_by_symbol: Mapping[str, _StEvidence],
    limits_by_key: Mapping[tuple[date, str], _LimitEvidence],
) -> tuple[RawTradingEligibilityObservation, ...]:
    observations: list[RawTradingEligibilityObservation] = []
    for (decision_time, symbol), minute in sorted(selected_minutes.items()):
        decision_date = decision_time.astimezone(_ZONE).date()
        evidence_times = [minute.available_at]

        security = securities[symbol]
        listing_age: int | None = None
        if (
            security.listing_date is not None
            and security.available_at is not None
            and security.available_at <= decision_time
        ):
            listing_age = (decision_date - security.listing_date).days
            if listing_age < 0:
                listing_age = None
            else:
                evidence_times.append(security.available_at)

        st_value: bool | None = None
        st_evidence = st_by_symbol.get(symbol)
        if st_evidence is not None and st_evidence.available_at <= decision_time:
            evidence_times.append(st_evidence.available_at)
            if st_evidence.lookup_complete:
                st_value = any(start <= decision_date <= end for start, end in st_evidence.periods)

        limit = limits_by_key.get((decision_date, symbol))
        if limit is not None and limit.available_at <= decision_time:
            evidence_times.append(limit.available_at)
        else:
            limit = None

        liquidity_value, liquidity_evidence_times = _liquidity_at_decision(
            daily_bars,
            symbol=symbol,
            decision_time=decision_time,
        )
        evidence_times.extend(liquidity_evidence_times)

        is_suspended = _suspension_from_flag(minute.suspend_flag)
        limit_up = limit.limit_up_price if limit is not None else None
        limit_down = limit.limit_down_price if limit is not None else None
        limit_regime = limit.limit_regime if limit is not None else None
        buyability = _materialize_buyability(
            is_suspended=is_suspended,
            reference_price=minute.close,
            limit_up_price=limit_up,
            limit_down_price=limit_down,
            limit_regime=limit_regime,
            evidence_complete=minute.buyability_evidence_complete,
        )
        available_at = max(evidence_times)
        if available_at > decision_time:
            _raise(
                XuntouProviderAdapterErrorCode.TIMEZONE_REQUIRED,
                f"eligibility evidence for {symbol} is not available by Decision Time",
            )
        observations.append(
            RawTradingEligibilityObservation(
                as_of=AsOfTime(decision_time),
                available_at=AvailabilityTime(available_at),
                symbol=symbol,
                is_suspended=is_suspended,
                is_st=st_value,
                prev_close=minute.pre_close,
                limit_up_price=limit_up,
                limit_down_price=limit_down,
                limit_regime=limit_regime,
                listing_age_calendar_days=listing_age,
                liquidity_value=liquidity_value,
                liquidity_measure_id=(
                    XUNTOU_LIQUIDITY_MEASURE_ID if liquidity_value is not None else None
                ),
                decision_buyability=buyability,
            )
        )
    return tuple(observations)


def _liquidity_at_decision(
    daily_bars: tuple[_NativeBar, ...], *, symbol: str, decision_time: datetime
) -> tuple[float | None, tuple[datetime, ...]]:
    decision_date = decision_time.astimezone(_ZONE).date()
    eligible = sorted(
        (
            bar
            for bar in daily_bars
            if bar.symbol == symbol
            and bar.session_date < decision_date
            and bar.finalized
            and bar.available_at <= decision_time
        ),
        key=lambda bar: bar.session_date,
    )
    if len(eligible) < 20:
        return None, ()
    window = eligible[-20:]
    value = float(median(bar.amount for bar in window))
    if value <= 0.0:
        return None, ()
    return value, tuple(bar.available_at for bar in window)


def _materialize_buyability(
    *,
    is_suspended: bool | None,
    reference_price: float,
    limit_up_price: float | None,
    limit_down_price: float | None,
    limit_regime: str | None,
    evidence_complete: bool,
) -> DecisionBuyabilityStatus:
    if is_suspended is True:
        return DecisionBuyabilityStatus.NOT_BUYABLE
    if limit_up_price is not None and reference_price >= limit_up_price:
        return DecisionBuyabilityStatus.NOT_BUYABLE
    if (
        evidence_complete
        and is_suspended is False
        and limit_up_price is not None
        and limit_down_price is not None
        and limit_regime is not None
    ):
        return DecisionBuyabilityStatus.BUYABLE
    return DecisionBuyabilityStatus.UNKNOWN


def _build_next_session_bars(
    *,
    decision_snapshots: tuple[RehearsalDecisionSnapshot, ...],
    daily_native: tuple[_NativeBar, ...],
    trading_calendar: TradingCalendarArtifact,
) -> tuple[RehearsalNextSessionBar, ...]:
    daily_by_key = {(bar.session_date, bar.symbol): bar for bar in daily_native}
    output: dict[tuple[date, str], RehearsalNextSessionBar] = {}
    for snapshot in decision_snapshots:
        try:
            next_date = trading_calendar.resolve_next_session_date(snapshot.decision_time)
        except LookupError:
            continue
        native = daily_by_key.get((next_date, snapshot.symbol))
        if native is None or not native.finalized:
            continue
        if native.available_at <= snapshot.decision_time.value:
            _raise(
                XuntouProviderAdapterErrorCode.INVALID_NATIVE_VALUE,
                f"next-session bar for {snapshot.symbol} is available before its Decision Time",
            )
        output[(next_date, snapshot.symbol)] = RehearsalNextSessionBar(
            symbol=snapshot.symbol,
            session_date=next_date,
            open=native.open,
            high=native.high,
            low=native.low,
            close=native.close,
            available_at=AvailabilityTime(native.available_at),
        )
    return tuple(output[key] for key in sorted(output))


def _resolve_content_hash(
    source: Mapping[str, object], computed_content_hash: str | None
) -> str:
    declared = source.get("content_hash")
    if computed_content_hash is not None:
        if not _SHA256_PATTERN.fullmatch(computed_content_hash):
            _raise(
                XuntouProviderAdapterErrorCode.INVALID_NATIVE_VALUE,
                "computed content hash is not lowercase SHA-256",
            )
        if declared is not None and declared != computed_content_hash:
            _raise(
                XuntouProviderAdapterErrorCode.CONTENT_HASH_MISMATCH,
                "declared content hash differs from exact file-byte SHA-256",
            )
        return computed_content_hash
    if not isinstance(declared, str) or not _SHA256_PATTERN.fullmatch(declared):
        _raise(
            XuntouProviderAdapterErrorCode.REQUIRED_SECTION_MISSING,
            "in-memory source_artifact.content_hash must be lowercase SHA-256",
        )
    return declared


def _validate_conventions(conventions: Mapping[str, object]) -> None:
    for key, expected in _REQUIRED_CONVENTIONS.items():
        actual = conventions.get(key)
        if actual != expected:
            _raise(
                XuntouProviderAdapterErrorCode.FIELD_UNSUPPORTED,
                f"conventions.{key} must equal {expected!r}, got {actual!r}",
            )


def _parse_limitations(items: Sequence[object]) -> tuple[str, ...]:
    output: list[str] = []
    for index, item in enumerate(items):
        if not isinstance(item, str) or not item.strip() or item != item.strip():
            _raise(
                XuntouProviderAdapterErrorCode.INVALID_NATIVE_VALUE,
                f"limitations[{index}] must be a non-empty trimmed string",
            )
        output.append(item)
    return tuple(output)


def _parse_open_date(value: object) -> date | None:
    if value is None:
        return None
    text = str(value)
    if text in _OPEN_DATE_SENTINELS or text in {"0", "99999999"}:
        return None
    try:
        return datetime.strptime(text, "%Y%m%d").date()
    except ValueError:
        return None


def _parse_native_date(value: object, label: str) -> date:
    if isinstance(value, bool):
        _raise(XuntouProviderAdapterErrorCode.INVALID_NATIVE_VALUE, f"{label} is invalid")
    if isinstance(value, int):
        try:
            return datetime.fromtimestamp(value / 1000.0, tz=timezone.utc).astimezone(_ZONE).date()
        except (OverflowError, OSError, ValueError) as exc:
            raise XuntouProviderAdapterError(
                XuntouProviderAdapterErrorCode.INVALID_NATIVE_VALUE,
                f"{label} is not a valid millisecond timestamp",
            ) from exc
    if isinstance(value, str):
        text = value.strip()
        for pattern in ("%Y%m%d", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, pattern).date()
            except ValueError:
                continue
    _raise(
        XuntouProviderAdapterErrorCode.INVALID_NATIVE_VALUE,
        f"{label} must be YYYYMMDD, YYYY-MM-DD, or native millisecond time",
    )


def _native_date_as_datetime(value: object, label: str) -> datetime:
    trade_date = _parse_native_date(value, label)
    return datetime.combine(trade_date, time.min, tzinfo=_ZONE)


def _parse_aware_datetime(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        _raise(
            XuntouProviderAdapterErrorCode.TIMEZONE_REQUIRED,
            f"{label} must be a timezone-aware ISO-8601 string",
        )
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise XuntouProviderAdapterError(
            XuntouProviderAdapterErrorCode.TIMEZONE_REQUIRED,
            f"{label} must be a timezone-aware ISO-8601 string",
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        _raise(
            XuntouProviderAdapterErrorCode.TIMEZONE_REQUIRED,
            f"{label} must include an explicit UTC offset",
        )
    return parsed


def _parse_symbol(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SYMBOL_PATTERN.fullmatch(value):
        _raise(
            XuntouProviderAdapterErrorCode.INVALID_NATIVE_VALUE,
            f"{label} must match six-digit code plus .SH, .SZ, or .BJ",
        )
    return value


def _parse_suspend_flag(value: object, label: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value not in {-1, 0, 1}:
        _raise(
            XuntouProviderAdapterErrorCode.INVALID_NATIVE_VALUE,
            f"{label} must be -1, 0, 1, or null",
        )
    return int(value)


def _suspension_from_flag(value: int | None) -> bool | None:
    if value == 1:
        return True
    if value in {-1, 0}:
        return False
    return None


def _positive_float(value: object, label: str) -> float:
    parsed = _finite_float(value, label)
    if parsed <= 0.0:
        _raise(
            XuntouProviderAdapterErrorCode.INVALID_NATIVE_VALUE,
            f"{label} must be positive",
        )
    return parsed


def _non_negative_float(value: object, label: str) -> float:
    parsed = _finite_float(value, label)
    if parsed < 0.0:
        _raise(
            XuntouProviderAdapterErrorCode.INVALID_NATIVE_VALUE,
            f"{label} must be non-negative",
        )
    return parsed


def _optional_positive_float(value: object, label: str) -> float | None:
    if value is None or value == 0:
        return None
    return _positive_float(value, label)


def _finite_float(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        _raise(XuntouProviderAdapterErrorCode.INVALID_NATIVE_VALUE, f"{label} must be numeric")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise XuntouProviderAdapterError(
            XuntouProviderAdapterErrorCode.INVALID_NATIVE_VALUE,
            f"{label} must be numeric",
        ) from exc
    if not math.isfinite(parsed):
        _raise(
            XuntouProviderAdapterErrorCode.INVALID_NATIVE_VALUE,
            f"{label} must be finite",
        )
    return parsed


def _optional_bool(value: object, label: str, *, default: bool) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        _raise(
            XuntouProviderAdapterErrorCode.INVALID_NATIVE_VALUE,
            f"{label} must be boolean",
        )
    return value


def _required_mapping(
    mapping: Mapping[str, object], key: str, section: str
) -> Mapping[str, object]:
    if key not in mapping:
        _raise(
            XuntouProviderAdapterErrorCode.REQUIRED_SECTION_MISSING,
            f"{section}.{key} is required",
        )
    return _as_mapping(mapping[key], f"{section}.{key}")


def _as_mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        _raise(
            XuntouProviderAdapterErrorCode.NATIVE_SCHEMA_UNSUPPORTED,
            f"{label} must be an object",
        )
    return value


def _required_sequence(
    mapping: Mapping[str, object], key: str, section: str
) -> Sequence[object]:
    if key not in mapping:
        _raise(
            XuntouProviderAdapterErrorCode.REQUIRED_SECTION_MISSING,
            f"{section}.{key} is required",
        )
    return _as_sequence(mapping[key], f"{section}.{key}")


def _optional_sequence(mapping: Mapping[str, object], key: str) -> Sequence[object]:
    value = mapping.get(key, ())
    return _as_sequence(value, key)


def _as_sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        _raise(
            XuntouProviderAdapterErrorCode.NATIVE_SCHEMA_UNSUPPORTED,
            f"{label} must be an array",
        )
    return value


def _required_string(mapping: Mapping[str, object], key: str, section: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        _raise(
            XuntouProviderAdapterErrorCode.REQUIRED_SECTION_MISSING,
            f"{section}.{key} must be a non-empty trimmed string",
        )
    return value


def _raise(code: XuntouProviderAdapterErrorCode, detail: str) -> NoReturn:
    raise XuntouProviderAdapterError(code, detail)
