"""Synthetic request-time checks; no Provider or research qualification."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest

from market_regime_alpha.infrastructure.providers.baostock_acquisition_readiness import (
    ACQUISITION_READINESS_V1, BaoStockProspectiveAcquisitionNormalizer, preopen_empty_5m_readiness,
)
from market_regime_alpha.infrastructure.providers.baostock_archive import BaoStockArchiveQuery, BaoStockArchiveQueryKind
from market_regime_alpha.infrastructure.providers.baostock_archive_normalizer import BaoStockArchiveNormalizer, BaoStockProspectiveNormalizer
from market_regime_alpha.market.domain import NormalizationBatch, TemporalEnvelope, SourceAvailabilityStatus
from market_regime_alpha.shared.time import KnownTime, DecisionTime
from tests.contracts.market.test_baostock_archive_normalizer import _capture, _payload, _Sessions

FIELDS = ["date", "time", "code", "open", "high", "low", "close", "volume", "amount", "adjustflag"]
QUERY = BaoStockArchiveQuery(BaoStockArchiveQueryKind.HISTORY_5M_RAW, date(2026, 1, 5), date(2026, 1, 6), "sh.600000")


def capture_at(start, response=None):
    response = response or start
    return replace(_capture(), temporal=TemporalEnvelope(provider_time=None, source_availability_status=SourceAvailabilityStatus.UNKNOWN,
        source_available_at=None, capture_started_at=start, capture_completed_at=response,
        known_at=KnownTime(response), decision_visible_at=DecisionTime(response)))


@pytest.mark.parametrize("start,response", [(datetime(2026, 1, 5, 1, 1, tzinfo=UTC), None),
    (datetime(2026, 1, 5, 1, 34, tzinfo=UTC), datetime(2026, 1, 5, 1, 36, tzinfo=UTC))])
def test_actual_empty_response_before_any_mature_interval_is_capture_only(start, response):
    capture = capture_at(start, response)
    content = _payload(QUERY, FIELDS, [])
    readiness = preopen_empty_5m_readiness(capture, content, QUERY, _Sessions())
    assert readiness.state == "NO_MATURE_INTERVAL"
    assert readiness.capture_id == capture.capture_id and readiness.expected_interval_count == 96
    assert readiness.first_mature_at == datetime(2026, 1, 5, 1, 35, tzinfo=UTC)
    assert readiness.policy == ACQUISITION_READINESS_V1
    assert preopen_empty_5m_readiness(capture, content, QUERY, _Sessions()) == readiness
    normalizer = BaoStockProspectiveAcquisitionNormalizer(expected_query=QUERY, trading_sessions=_Sessions())
    assert normalizer.acquisition_readiness(capture, content) == readiness
    assert normalizer.contract == BaoStockProspectiveNormalizer.contract
    # Frozen historical behavior remains reproducible; an empty Batch is not legalized.
    with pytest.raises(ValueError, match="normalization must record"):
        BaoStockProspectiveNormalizer(trading_sessions=_Sessions()).normalize(capture, content)
    with pytest.raises(ValueError, match="normalization must record"):
        NormalizationBatch(capture.capture_id, capture.provider_product_id)
    assert len(BaoStockArchiveNormalizer(trading_sessions=_Sessions()).normalize(capture, content).gaps) == 96


def test_mature_empty_response_still_normalizes_exact_source_gaps():
    capture = capture_at(datetime(2026, 1, 5, 1, 35, tzinfo=UTC))
    content = _payload(QUERY, FIELDS, [])
    normalizer = BaoStockProspectiveAcquisitionNormalizer(expected_query=QUERY, trading_sessions=_Sessions())
    assert normalizer.acquisition_readiness(capture, content) is None
    batch = normalizer.normalize(capture, content)
    assert len(batch.gaps) == 1 and batch.gaps[0].event_end == capture.temporal.capture_started_at
    assert batch.gaps[0].reason_code.value == "NO_ROWS_RETURNED"


@pytest.mark.parametrize("mutate", [
    lambda b: b.replace(b'"error_message":"success"', b'"error_message":"unknown"'),
    lambda b: b.replace(b'"rows":[]', b'"rows":[],"rows":[]'),
    lambda b: b.replace(b'"kind":"HISTORY_5M_RAW"', b'"kind":"HISTORY_DAILY_RAW"'),
    lambda b: b.replace(b'"amount",', b''),
    lambda b: b.replace(b'"error_code":"0"', b'"error_code":"1"'),
])
def test_empty_readiness_rejects_malformed_or_changed_source(mutate):
    with pytest.raises(ValueError):
        preopen_empty_5m_readiness(capture_at(datetime(2026, 1, 5, 1, 1, tzinfo=UTC)),
                                 mutate(_payload(QUERY, FIELDS, [])), QUERY, _Sessions())


def test_nonempty_corrupt_rows_still_reach_normalizer_rejection():
    capture = capture_at(datetime(2026, 1, 5, 1, 1, tzinfo=UTC))
    malformed = _payload(QUERY, FIELDS, [["corrupt"]])
    normalizer = BaoStockProspectiveAcquisitionNormalizer(expected_query=QUERY, trading_sessions=_Sessions())
    assert normalizer.acquisition_readiness(capture, malformed) is None
    with pytest.raises(ValueError, match="malformed"):
        normalizer.normalize(capture, malformed)


def test_readiness_cannot_assume_missing_or_corrupted_calendar():
    capture = capture_at(datetime(2026, 1, 5, 1, 1, tzinfo=UTC))
    content = _payload(QUERY, FIELDS, [])
    with pytest.raises(ValueError, match="canonical trading Sessions"):
        preopen_empty_5m_readiness(capture, content, QUERY, SimpleNamespace(sessions=lambda **_: ()))
    one = _Sessions().sessions(exchange="XSHG", start_date=QUERY.start_date, end_date=QUERY.end_date)[0]
    with pytest.raises(ValueError, match="CALENDAR_IDENTITY"):
        preopen_empty_5m_readiness(capture, content, QUERY, SimpleNamespace(sessions=lambda **_: (replace(one, close_at=one.open_at-timedelta(minutes=1)),)))
