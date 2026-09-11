"""Narrow explicit calendar observations; the historical archive v2 stays frozen."""

from dataclasses import dataclass
from datetime import date, timedelta
import json
from uuid import uuid5

from market_regime_alpha.infrastructure.providers.baostock_archive import BaoStockArchiveQuery, BaoStockArchiveQueryKind
from market_regime_alpha.infrastructure.providers.baostock_archive_normalizer import _session
from market_regime_alpha.market.domain import GapFactKind, GapKind, GapReasonCode, NormalizationBatch, ProviderCapture, SourceGap
from market_regime_alpha.market.ports import NormalizerContract
from market_regime_alpha.shared.hashing import canonical_json_sha256

CALENDAR_HORIZON_DAYS = 120


@dataclass(frozen=True, slots=True)
class CalendarObservation:
    query: BaoStockArchiveQuery
    open_dates: tuple[date, ...]
    missing_dates: tuple[date, ...]


def decode_calendar_response(content: bytes, expected_query: BaoStockArchiveQuery | None = None) -> CalendarObservation:
    """Authenticate the exact bounded request; absence never means a holiday."""
    value = json.loads(content)
    if (not isinstance(value, dict) or set(value) != {"error_code", "error_message", "fields", "query", "rows"}
            or value["error_code"] != "0" or not isinstance(value["error_message"], str)
            or value["fields"] != ["calendar_date", "is_trading_day"] or not isinstance(value["rows"], list)):
        raise ValueError("CALENDAR_RESPONSE_SHAPE_INVALID")
    query = BaoStockArchiveQuery.from_resource(json.dumps(value["query"], sort_keys=True, separators=(",", ":")))
    if (query.kind is not BaoStockArchiveQueryKind.TRADE_DATES or query.start_date is None or query.end_date is None
            or query.code is not None or not 1 <= (query.end_date - query.start_date).days + 1 <= CALENDAR_HORIZON_DAYS
            or expected_query is not None and query != expected_query):
        raise ValueError("CALENDAR_REQUEST_IDENTITY_INVALID")
    observed: dict[date, str] = {}
    for row in value["rows"]:
        if not isinstance(row, list) or len(row) != 2 or any(not isinstance(item, str) for item in row) or row[1] not in {"0", "1"}:
            raise ValueError("CALENDAR_ROW_INVALID")
        day = date.fromisoformat(row[0])
        if day.isoformat() != row[0] or day in observed or not query.start_date <= day <= query.end_date:
            raise ValueError("CALENDAR_DATE_DUPLICATE_OR_OUTSIDE_REQUEST")
        observed[day] = row[1]
    expected = tuple(query.start_date + timedelta(days=index) for index in range((query.end_date - query.start_date).days + 1))
    return CalendarObservation(query, tuple(day for day in expected if observed.get(day) == "1"), tuple(day for day in expected if day not in observed))


class BaoStockCalendarNormalizer:
    contract = NormalizerContract(
        implementation="market.baostock_calendar",
        version="1",
        implementation_sha256=canonical_json_sha256({
            "version": 1, "query": "TRADE_DATES", "exchange": "XSHG", "maximum_civil_days": CALENDAR_HORIZON_DAYS,
            "status": ["0", "1"], "missing": "TRADING_SESSION_SOURCE_GAP", "dates": "UNIQUE_EXACT_REQUEST_RANGE",
        }),
    )

    def __init__(self, expected_query: BaoStockArchiveQuery) -> None:
        self._expected_query = expected_query

    def normalize(self, capture: ProviderCapture, content: bytes) -> NormalizationBatch:
        observation = decode_calendar_response(content, self._expected_query)
        sessions = tuple(_session("XSHG", day, capture.capture_id) for day in observation.open_dates)
        gaps = tuple(SourceGap(
            gap_id=uuid5(capture.capture_id, "calendar:XSHG:" + day.isoformat()),
            provider_product_id=capture.provider_product_id, capture_id=capture.capture_id,
            instrument_id=None, session_id=None, gap_kind=GapKind.MISSING,
            reason_code=GapReasonCode.EXPECTED_OBSERVATION_MISSING, fact_kind=GapFactKind.TRADING_SESSION,
            instrument_fact_kind=None, timeframe=None, price_basis=None, event_start=None, event_end=None,
            detail="Provider response omitted this requested civil date; open/closed status is unknown.",
            exchange="XSHG", session_date=day,
        ) for day in observation.missing_dates)
        if not sessions and not gaps:
            raise ValueError("CALENDAR_NO_OPEN_SESSIONS")
        return NormalizationBatch(capture.capture_id, capture.provider_product_id, trading_sessions=sessions, gaps=gaps)
