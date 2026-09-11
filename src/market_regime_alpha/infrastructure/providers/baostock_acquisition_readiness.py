"""V1 readiness for an actual empty observation before any 5-minute interval ends.

This adds no normalization result. The retained V2/V3 normalizers and their
historical contract bytes continue to own all facts and typed SourceGaps.
"""

from hashlib import sha256
import json
from typing import Any

from market_regime_alpha.infrastructure.providers.baostock_archive import BaoStockArchiveQuery, BaoStockArchiveQueryKind
from market_regime_alpha.infrastructure.providers.baostock_archive_normalizer import BaoStockProspectiveNormalizer, _parse_code
from market_regime_alpha.market.domain import CaptureStatus, ProviderCapture
from market_regime_alpha.market.ports import ArchiveTradingSessionReadPort, NormalizerContract
from market_regime_alpha.market.ports.acquisition_readiness import ArchiveAcquisitionReadiness
from market_regime_alpha.shared.hashing import canonical_json_sha256


ACQUISITION_READINESS_V1 = NormalizerContract(
    implementation="market.baostock_prospective_acquisition_readiness", version="1",
    implementation_sha256=canonical_json_sha256({
        "version": 1, "query": "HISTORY_5M_RAW", "response": "EXACT_SUCCESS_EMPTY_ROWS",
        "calendar": "CANONICAL_EXACT_EXCHANGE_SESSIONS", "condition": "ALL_INTERVAL_ENDS_AFTER_CAPTURE_STARTED_AT",
        "result": "NO_MATURE_INTERVAL; CAPTURE_ONLY; NO_NORMALIZATION_OR_SOURCE_GAP",
        "retained_normalizer": str(BaoStockProspectiveNormalizer.contract.implementation_sha256),
    }),
)
_FIELDS = ["date", "time", "code", "open", "high", "low", "close", "volume", "amount", "adjustflag"]


def _unique_object(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result = dict(items)
    if len(result) != len(items):
        raise ValueError("ACQUISITION_RESPONSE_DUPLICATE_JSON_KEY")
    return result


def preopen_empty_5m_readiness(capture: ProviderCapture, content: bytes, expected_query: BaoStockArchiveQuery,
                             trading_sessions: ArchiveTradingSessionReadPort) -> ArchiveAcquisitionReadiness | None:
    """Reconstruct the narrow readiness proof from the original Capture bytes."""
    if expected_query.kind is not BaoStockArchiveQueryKind.HISTORY_5M_RAW:
        return None
    value = json.loads(content, object_pairs_hook=_unique_object)
    if not isinstance(value, dict):
        raise ValueError("ACQUISITION_RESPONSE_SHAPE_INVALID")
    # Nonempty or malformed observations still pass through the normal owner;
    # only the exact successful empty envelope may bypass normalization.
    if value.get("rows") != []:
        return None
    expected = {"error_code": "0", "error_message": "success", "fields": _FIELDS,
                "query": json.loads(expected_query.resource), "rows": []}
    if value != expected or capture.status is not CaptureStatus.CAPTURED:
        raise ValueError("ACQUISITION_EMPTY_RESPONSE_IDENTITY_INVALID")
    if trading_sessions is None:
        raise ValueError("ACQUISITION_REQUIRES_CANONICAL_CALENDAR")
    normalizer = BaoStockProspectiveNormalizer(expected_query=expected_query, trading_sessions=trading_sessions)
    assert expected_query.code is not None
    exchange, _ = _parse_code(expected_query.code)
    assert expected_query.start_date is not None and expected_query.end_date is not None
    sessions = normalizer._expected_sessions(exchange=exchange, start_date=expected_query.start_date,
        end_date=expected_query.end_date, capture_id=capture.capture_id)
    if (len({item.session_id for item in sessions}) != len(sessions)
            or len({item.session_date for item in sessions}) != len(sessions)
            or any(item.exchange != exchange or not expected_query.start_date <= item.session_date <= expected_query.end_date
                   or not item.open_at < item.break_start_at < item.break_end_at < item.close_at for item in sessions)):
        raise ValueError("ACQUISITION_CANONICAL_CALENDAR_IDENTITY_INVALID")
    intervals = tuple(interval for session in sessions for interval in normalizer._expected_intervals(session, is_daily=False))
    if not intervals or any(start >= end for start, end in intervals):
        raise ValueError("ACQUISITION_CANONICAL_INTERVALS_INVALID")
    first_mature = min(end for _, end in intervals)
    if first_mature <= capture.temporal.capture_started_at:
        return None
    return ArchiveAcquisitionReadiness(capture.capture_id, "NO_MATURE_INTERVAL", ACQUISITION_READINESS_V1,
        sha256(content).hexdigest(), capture.temporal.capture_started_at, first_mature, len(intervals),
        tuple(item.session_id.value for item in sessions))


class BaoStockProspectiveAcquisitionNormalizer(BaoStockProspectiveNormalizer):
    """Retain V3 normalization; advertise the separate opt-in readiness policy."""

    def acquisition_readiness(self, capture: ProviderCapture, content: bytes) -> ArchiveAcquisitionReadiness | None:
        if self._expected_query is None or self._trading_sessions is None:
            raise ValueError("ACQUISITION_REQUIRES_FROZEN_QUERY_AND_CANONICAL_CALENDAR")
        return preopen_empty_5m_readiness(capture, content, self._expected_query, self._trading_sessions)
