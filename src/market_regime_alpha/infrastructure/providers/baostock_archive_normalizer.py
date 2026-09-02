"""Deterministic normalization for exact BaoStock archive envelopes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
import json
from uuid import NAMESPACE_URL, UUID, uuid5
from zoneinfo import ZoneInfo

from market_regime_alpha.infrastructure.providers.baostock_archive import (
    BaoStockArchiveQuery,
    BaoStockArchiveQueryKind,
)
from market_regime_alpha.market.domain import (
    BarTimeframe,
    GapFactKind,
    GapKind,
    GapReasonCode,
    Instrument,
    InstrumentIdentifier,
    InstrumentType,
    MarketBarRevision,
    NormalizationBatch,
    PriceBasis,
    ProviderCapture,
    SourceGap,
    TradingSession,
)
from market_regime_alpha.market.ports import NormalizerContract
from market_regime_alpha.market.ports.revision_lineage import (
    MarketRevisionLineageReadPort,
)
from market_regime_alpha.shared.financial import Money, Quantity, QuantityUnit
from market_regime_alpha.shared.identity import InstrumentId, TradingSessionId

_SHANGHAI = ZoneInfo("Asia/Shanghai")


def a_share_instrument_id(code: str) -> InstrumentId:
    exchange, digits = _parse_code(code)
    return InstrumentId(uuid5(NAMESPACE_URL, f"mra:instrument:{exchange}:{digits}"))


def a_share_session_id(exchange: str, session_date: date) -> TradingSessionId:
    if exchange not in {"XSHG", "XSHE"}:
        raise ValueError("unsupported A-share exchange")
    return TradingSessionId(uuid5(NAMESPACE_URL, f"mra:trading-session:{exchange}:{session_date.isoformat()}"))


def _parse_code(code: str) -> tuple[str, str]:
    if len(code) != 9 or code[2] != "." or not code[3:].isdigit():
        raise ValueError("BaoStock security code has an invalid format")
    exchange = {"sh": "XSHG", "sz": "XSHE"}.get(code[:2])
    if exchange is None:
        raise ValueError("BaoStock security code is outside the A-share pilot exchanges")
    return exchange, code[3:]


def _session(exchange: str, session_date: date, capture_id: UUID) -> TradingSession:
    def at(value: time) -> datetime:
        return datetime.combine(session_date, value, tzinfo=_SHANGHAI).astimezone(UTC)

    return TradingSession(
        session_id=a_share_session_id(exchange, session_date),
        exchange=exchange,
        session_date=session_date,
        timezone_name="Asia/Shanghai",
        open_at=at(time(9, 30)),
        break_start_at=at(time(11, 30)),
        break_end_at=at(time(13, 0)),
        close_at=at(time(15, 0)),
        decision_reference_at=at(time(14, 55)),
        source_capture_id=capture_id,
    )


@dataclass(frozen=True, slots=True)
class _Envelope:
    query: BaoStockArchiveQuery
    fields: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]


class BaoStockArchiveNormalizer:
    contract = NormalizerContract(
        implementation="market.baostock_archive",
        version="1",
        implementation_sha256="de8d3e7c5dc51a946580c6be27eea56bff53282769fc291175048c68db14821d",
    )

    def __init__(
        self,
        expected_query: BaoStockArchiveQuery | None = None,
        revision_lineage: MarketRevisionLineageReadPort | None = None,
    ) -> None:
        self._expected_query = expected_query
        self._revision_lineage = revision_lineage

    def normalize(self, capture: ProviderCapture, content: bytes) -> NormalizationBatch:
        envelope = self._decode(content)
        if self._expected_query is not None and envelope.query != self._expected_query:
            raise ValueError("BaoStock payload query identity differs from the frozen request")
        if envelope.query.kind is BaoStockArchiveQueryKind.TRADE_DATES:
            return self._normalize_calendar(capture, envelope)
        if envelope.query.kind is BaoStockArchiveQueryKind.STOCK_BASIC:
            return self._normalize_security_master(capture, envelope)
        if envelope.query.kind in {
            BaoStockArchiveQueryKind.HISTORY_DAILY_RAW,
            BaoStockArchiveQueryKind.HISTORY_5M_RAW,
        }:
            return self._normalize_bars(capture, envelope)
        raise ValueError("BaoStock archive query kind has no canonical normalizer")

    def _decode(self, content: bytes) -> _Envelope:
        try:
            payload = json.loads(content)
            if not isinstance(payload, dict) or set(payload) != {
                "error_code",
                "error_message",
                "fields",
                "query",
                "rows",
            }:
                raise ValueError("payload has an unexpected field roster")
            if payload["error_code"] != "0":
                raise ValueError("successful Capture contains a Provider error")
            fields = tuple(str(item) for item in payload["fields"])
            if not fields or len(fields) != len(set(fields)):
                raise ValueError("payload field roster is empty or duplicated")
            rows = tuple(tuple(str(value) for value in row) for row in payload["rows"])
            if any(len(row) != len(fields) for row in rows):
                raise ValueError("payload row width differs from its field roster")
            query_resource = json.dumps(payload["query"], allow_nan=False, separators=(",", ":"), sort_keys=True)
            query = BaoStockArchiveQuery.from_resource(query_resource)
        except (TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("BaoStock archive payload is malformed") from exc
        return _Envelope(query=query, fields=fields, rows=rows)

    def _normalize_calendar(self, capture: ProviderCapture, envelope: _Envelope) -> NormalizationBatch:
        required = ("calendar_date", "is_trading_day")
        rows = self._row_dicts(envelope, required)
        sessions = tuple(
            _session(exchange, date.fromisoformat(row["calendar_date"]), capture.capture_id)
            for row in rows
            if row["is_trading_day"] == "1"
            for exchange in ("XSHG", "XSHE")
        )
        if not sessions:
            raise ValueError("trade-calendar normalization produced no open Session evidence")
        return NormalizationBatch(
            source_capture_id=capture.capture_id,
            source_provider_product_id=capture.provider_product_id,
            trading_sessions=sessions,
        )

    def _normalize_security_master(self, capture: ProviderCapture, envelope: _Envelope) -> NormalizationBatch:
        required = ("code", "code_name", "ipoDate", "outDate", "type", "status")
        rows = self._row_dicts(envelope, required)
        instruments: list[Instrument] = []
        identifiers: list[InstrumentIdentifier] = []
        for row in rows:
            exchange, digits = _parse_code(row["code"])
            if row["type"] != "1":
                raise ValueError("security-master row is not an A-share equity")
            instrument_id = a_share_instrument_id(row["code"])
            instruments.append(
                Instrument(
                    instrument_id=instrument_id,
                    canonical_code=f"{digits}.{exchange}",
                    exchange=exchange,
                    instrument_type=InstrumentType.EQUITY,
                    currency="CNY",
                    source_capture_id=capture.capture_id,
                )
            )
            if row["ipoDate"]:
                effective_from = datetime.combine(date.fromisoformat(row["ipoDate"]), time(), tzinfo=UTC)
                effective_to = (
                    datetime.combine(date.fromisoformat(row["outDate"]), time(), tzinfo=UTC) if row["outDate"] else None
                )
                identifiers.append(
                    InstrumentIdentifier(
                        instrument_identifier_id=uuid5(
                            NAMESPACE_URL,
                            f"mra:instrument-identifier:BAOSTOCK:{row['code']}:{row['ipoDate']}",
                        ),
                        instrument_id=instrument_id,
                        identifier_scheme="BAOSTOCK",
                        identifier_value=row["code"],
                        effective_from=effective_from,
                        effective_to=effective_to,
                        revision=1,
                        supersedes_identifier_id=None,
                        source_capture_id=capture.capture_id,
                    )
                )
        if not instruments:
            query = envelope.query
            assert query.code is not None
            gap = SourceGap(
                gap_id=uuid5(NAMESPACE_URL, f"mra:gap:{capture.capture_id}:instrument:{query.code}"),
                provider_product_id=capture.provider_product_id,
                capture_id=capture.capture_id,
                instrument_id=None,
                session_id=None,
                gap_kind=GapKind.MISSING,
                reason_code=GapReasonCode.NO_ROWS_RETURNED,
                fact_kind=GapFactKind.INSTRUMENT,
                instrument_fact_kind=None,
                timeframe=None,
                price_basis=None,
                event_start=None,
                event_end=None,
                detail="BaoStock returned no security-master row for the exact code",
                instrument_code=self._canonical_code(query.code),
            )
            return NormalizationBatch(
                source_capture_id=capture.capture_id,
                source_provider_product_id=capture.provider_product_id,
                gaps=(gap,),
            )
        return NormalizationBatch(
            source_capture_id=capture.capture_id,
            source_provider_product_id=capture.provider_product_id,
            instruments=tuple(instruments),
            instrument_identifiers=tuple(identifiers),
        )

    def _normalize_bars(self, capture: ProviderCapture, envelope: _Envelope) -> NormalizationBatch:
        is_daily = envelope.query.kind is BaoStockArchiveQueryKind.HISTORY_DAILY_RAW
        required = (
            ("date", "code", "open", "high", "low", "close", "volume", "amount", "adjustflag")
            if is_daily
            else ("date", "time", "code", "open", "high", "low", "close", "volume", "amount", "adjustflag")
        )
        rows = self._row_dicts(envelope, required)
        bars: list[MarketBarRevision] = []
        gaps: list[SourceGap] = []
        observed_keys: set[tuple[str, BarTimeframe, datetime]] = set()
        for row in rows:
            if row["adjustflag"] != "3":
                raise ValueError("archive bar must preserve RAW_UNADJUSTED price basis")
            query_code = envelope.query.code
            if query_code is None or row["code"] != query_code:
                raise ValueError("bar row code differs from the frozen query")
            exchange, _ = _parse_code(row["code"])
            session_date = date.fromisoformat(row["date"])
            session = _session(exchange, session_date, capture.capture_id)
            if is_daily:
                event_start, event_end = session.open_at, session.close_at
                timeframe = BarTimeframe.DAILY
            else:
                event_end = datetime.strptime(row["time"], "%Y%m%d%H%M%S%f").replace(tzinfo=_SHANGHAI).astimezone(UTC)
                event_start = event_end - timedelta(minutes=5)
                timeframe = BarTimeframe.MINUTE_5
            observation_key = (row["code"], timeframe, event_start)
            if observation_key in observed_keys:
                raise ValueError("BaoStock payload contains a duplicate bar observation")
            observed_keys.add(observation_key)
            gap = self._bar_gap_if_needed(capture, row, session.session_id, timeframe, event_start, event_end)
            if gap is not None:
                gaps.append(gap)
                continue
            try:
                open_value, high_value, low_value, close_value = (
                    Money(Decimal(row[field]), "CNY") for field in ("open", "high", "low", "close")
                )
                volume = Quantity(Decimal(row["volume"]), QuantityUnit.SHARES)
                turnover = Money(Decimal(row["amount"]), "CNY") if row["amount"] else None
                head = (
                    self._revision_lineage.market_bar_head(
                        provider_product_id=capture.provider_product_id,
                        instrument_id=a_share_instrument_id(row["code"]),
                        session_id=session.session_id,
                        timeframe=timeframe,
                        price_basis=PriceBasis.RAW_UNADJUSTED,
                        event_start=event_start,
                        event_end=event_end,
                    )
                    if self._revision_lineage is not None
                    else None
                )
                revision = 1 if head is None else head.revision + 1
                supersedes = None if head is None else head.bar_revision_id
                bar = MarketBarRevision(
                    bar_revision_id=uuid5(
                        NAMESPACE_URL,
                        f"mra:bar:{capture.provider_product_id}:{capture.capture_id}:{row['code']}:{timeframe.value}:{event_start.isoformat()}",
                    ),
                    provider_product_id=capture.provider_product_id,
                    capture_id=capture.capture_id,
                    instrument_id=a_share_instrument_id(row["code"]),
                    session_id=session.session_id,
                    timeframe=timeframe,
                    price_basis=PriceBasis.RAW_UNADJUSTED,
                    event_start=event_start,
                    event_end=event_end,
                    revision=revision,
                    supersedes_revision_id=supersedes,
                    open=open_value,
                    high=high_value,
                    low=low_value,
                    close=close_value,
                    volume=volume,
                    turnover=turnover,
                )
            except (InvalidOperation, TypeError, ValueError):
                gaps.append(
                    self._bar_gap(
                        capture,
                        row["code"],
                        session.session_id,
                        timeframe,
                        event_start,
                        event_end,
                        GapKind.INVALID_OHLC,
                        GapReasonCode.INVALID_OHLC,
                    )
                )
            else:
                bars.append(bar)
        if not rows:
            query = envelope.query
            assert query.code is not None
            assert query.start_date is not None and query.end_date is not None
            if query.start_date != query.end_date:
                raise ValueError(
                    "multi-session history absence cannot be assigned to one exact Session"
                )
            exchange, _ = _parse_code(query.code)
            session = _session(exchange, query.start_date, capture.capture_id)
            timeframe = (
                BarTimeframe.DAILY
                if is_daily
                else BarTimeframe.MINUTE_5
            )
            gaps.append(
                self._bar_gap(
                    capture,
                    query.code,
                    session.session_id,
                    timeframe,
                    session.open_at,
                    session.close_at,
                    GapKind.MISSING,
                    GapReasonCode.NO_ROWS_RETURNED,
                )
            )
        return NormalizationBatch(
            source_capture_id=capture.capture_id,
            source_provider_product_id=capture.provider_product_id,
            bars=tuple(bars),
            gaps=tuple(gaps),
        )

    def _bar_gap_if_needed(
        self,
        capture: ProviderCapture,
        row: dict[str, str],
        session_id: TradingSessionId,
        timeframe: BarTimeframe,
        event_start: datetime,
        event_end: datetime,
    ) -> SourceGap | None:
        values = tuple(row[field] for field in ("open", "high", "low", "close"))
        if all(values):
            return None
        return self._bar_gap(
            capture,
            row["code"],
            session_id,
            timeframe,
            event_start,
            event_end,
            GapKind.PLACEHOLDER,
            GapReasonCode.NULL_OHLC_PLACEHOLDER,
        )

    def _bar_gap(
        self,
        capture: ProviderCapture,
        code: str,
        session_id: TradingSessionId,
        timeframe: BarTimeframe,
        event_start: datetime,
        event_end: datetime,
        gap_kind: GapKind,
        reason_code: GapReasonCode,
    ) -> SourceGap:
        return SourceGap(
            gap_id=uuid5(
                NAMESPACE_URL,
                f"mra:gap:{capture.capture_id}:{code}:{timeframe.value}:{event_start.isoformat()}",
            ),
            provider_product_id=capture.provider_product_id,
            capture_id=capture.capture_id,
            instrument_id=a_share_instrument_id(code),
            session_id=session_id,
            gap_kind=gap_kind,
            reason_code=reason_code,
            fact_kind=GapFactKind.MARKET_BAR,
            instrument_fact_kind=None,
            timeframe=timeframe,
            price_basis=PriceBasis.RAW_UNADJUSTED,
            event_start=event_start,
            event_end=event_end,
            detail="BaoStock row cannot establish a legal canonical raw bar",
        )

    @staticmethod
    def _row_dicts(envelope: _Envelope, required: tuple[str, ...]) -> tuple[dict[str, str], ...]:
        missing = set(required) - set(envelope.fields)
        if missing:
            raise ValueError(f"BaoStock payload is missing required fields: {sorted(missing)}")
        return tuple(dict(zip(envelope.fields, row, strict=True)) for row in envelope.rows)

    @staticmethod
    def _canonical_code(code: str) -> str:
        exchange, digits = _parse_code(code)
        return f"{digits}.{exchange}"


__all__ = [
    "BaoStockArchiveNormalizer",
    "a_share_instrument_id",
    "a_share_session_id",
]
