from __future__ import annotations

import json
from datetime import UTC, date, datetime
from uuid import uuid4

import pytest

from market_regime_alpha.infrastructure.providers.baostock_archive import (
    BaoStockArchiveQuery,
    BaoStockArchiveQueryKind,
)
from market_regime_alpha.infrastructure.providers.baostock_archive_normalizer import (
    BaoStockArchiveNormalizer,
    a_share_instrument_id,
    a_share_session_id,
)
from market_regime_alpha.market.domain import (
    BarTimeframe,
    CaptureStatus,
    GapKind,
    GapReasonCode,
    PriceBasis,
    ProviderCapture,
    SourceAvailabilityStatus,
    TemporalEnvelope,
)
from market_regime_alpha.shared.identity import ContentHash
from market_regime_alpha.shared.time import DecisionTime, KnownTime


def _capture() -> ProviderCapture:
    observed = datetime(2026, 9, 3, 9, tzinfo=UTC)
    return ProviderCapture(
        capture_id=uuid4(),
        provider_product_id=uuid4(),
        capture_key="wp17p:normalize:test",
        request_hash=ContentHash("1" * 64),
        status=CaptureStatus.CAPTURED,
        temporal=TemporalEnvelope(
            provider_time=None,
            source_availability_status=SourceAvailabilityStatus.UNKNOWN,
            source_available_at=None,
            capture_started_at=observed,
            capture_completed_at=observed,
            known_at=KnownTime(observed),
            decision_visible_at=DecisionTime(observed),
        ),
        artifact_id=uuid4(),
        error_code=None,
        limitation_code="HISTORICAL_AVAILABILITY_AND_FINALITY_UNKNOWN",
        payload_encoding="UTF-8",
    )


def _payload(query: BaoStockArchiveQuery, fields: list[str], rows: list[list[str]]) -> bytes:
    return (
        json.dumps(
            {
                "error_code": "0",
                "error_message": "success",
                "fields": fields,
                "query": json.loads(query.resource),
                "rows": rows,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode()


def test_trade_calendar_builds_explicit_sse_and_szse_sessions_only_for_open_days() -> None:
    capture = _capture()
    query = BaoStockArchiveQuery(
        kind=BaoStockArchiveQueryKind.TRADE_DATES,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 5),
    )
    batch = BaoStockArchiveNormalizer().normalize(
        capture,
        _payload(
            query,
            ["calendar_date", "is_trading_day"],
            [["2026-01-01", "0"], ["2026-01-05", "1"]],
        ),
    )

    assert [(item.exchange, item.session_date) for item in batch.trading_sessions] == [
        ("XSHG", date(2026, 1, 5)),
        ("XSHE", date(2026, 1, 5)),
    ]
    assert batch.trading_sessions[0].session_id == a_share_session_id("XSHG", date(2026, 1, 5))


def test_security_master_builds_stable_instrument_and_identifier() -> None:
    capture = _capture()
    query = BaoStockArchiveQuery(kind=BaoStockArchiveQueryKind.STOCK_BASIC, code="sh.600000")
    batch = BaoStockArchiveNormalizer().normalize(
        capture,
        _payload(
            query,
            ["code", "code_name", "ipoDate", "outDate", "type", "status"],
            [["sh.600000", "浦发银行", "1999-11-10", "", "1", "1"]],
        ),
    )

    assert batch.instruments[0].instrument_id == a_share_instrument_id("sh.600000")
    assert batch.instruments[0].canonical_code == "600000.XSHG"
    assert batch.instrument_identifiers[0].identifier_value == "sh.600000"
    assert batch.instrument_identifiers[0].effective_from == datetime(1999, 11, 10, tzinfo=UTC)


def test_five_minute_raw_bar_preserves_exact_grid_and_decimal_values() -> None:
    capture = _capture()
    query = BaoStockArchiveQuery(
        kind=BaoStockArchiveQueryKind.HISTORY_5M_RAW,
        code="sh.600000",
        start_date=date(2026, 1, 5),
        end_date=date(2026, 1, 5),
    )
    fields = ["date", "time", "code", "open", "high", "low", "close", "volume", "amount", "adjustflag"]
    batch = BaoStockArchiveNormalizer().normalize(
        capture,
        _payload(
            query,
            fields,
            [["2026-01-05", "20260105093500000", "sh.600000", "10.00", "10.20", "9.90", "10.10", "100", "1010", "3"]],
        ),
    )

    bar = batch.bars[0]
    assert bar.instrument_id == a_share_instrument_id("sh.600000")
    assert bar.session_id == a_share_session_id("XSHG", date(2026, 1, 5))
    assert bar.timeframe is BarTimeframe.MINUTE_5
    assert bar.price_basis is PriceBasis.RAW_UNADJUSTED
    assert bar.event_start == datetime(2026, 1, 5, 1, 30, tzinfo=UTC)
    assert bar.event_end == datetime(2026, 1, 5, 1, 35, tzinfo=UTC)
    assert str(bar.close.amount) == "10.1000000000"


def test_blank_ohlc_is_an_explicit_placeholder_gap_not_a_silent_drop() -> None:
    capture = _capture()
    query = BaoStockArchiveQuery(
        kind=BaoStockArchiveQueryKind.HISTORY_DAILY_RAW,
        code="sz.000001",
        start_date=date(2026, 1, 5),
        end_date=date(2026, 1, 5),
    )
    fields = [
        "date",
        "code",
        "open",
        "high",
        "low",
        "close",
        "preclose",
        "volume",
        "amount",
        "adjustflag",
        "turn",
        "tradestatus",
        "pctChg",
        "isST",
    ]
    batch = BaoStockArchiveNormalizer().normalize(
        capture,
        _payload(query, fields, [["2026-01-05", "sz.000001", "", "", "", "", "", "", "", "3", "", "0", "", "0"]]),
    )

    assert not batch.bars
    assert batch.gaps[0].gap_kind is GapKind.PLACEHOLDER
    assert batch.gaps[0].reason_code is GapReasonCode.NULL_OHLC_PLACEHOLDER


def test_payload_query_mismatch_and_non_raw_adjustflag_fail_closed() -> None:
    capture = _capture()
    query = BaoStockArchiveQuery(kind=BaoStockArchiveQueryKind.STOCK_BASIC, code="sh.600000")
    other = BaoStockArchiveQuery(kind=BaoStockArchiveQueryKind.STOCK_BASIC, code="sh.600001")
    normalizer = BaoStockArchiveNormalizer(expected_query=query)

    with pytest.raises(ValueError, match="query identity"):
        normalizer.normalize(capture, _payload(other, ["code"], [["sh.600001"]]))

    history = BaoStockArchiveQuery(
        kind=BaoStockArchiveQueryKind.HISTORY_5M_RAW,
        code="sh.600000",
        start_date=date(2026, 1, 5),
        end_date=date(2026, 1, 5),
    )
    fields = ["date", "time", "code", "open", "high", "low", "close", "volume", "amount", "adjustflag"]
    with pytest.raises(ValueError, match="RAW_UNADJUSTED"):
        BaoStockArchiveNormalizer().normalize(
            capture,
            _payload(history, fields, [["2026-01-05", "20260105093500000", "sh.600000", "1", "1", "1", "1", "1", "1", "2"]]),
        )
