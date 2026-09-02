from __future__ import annotations

import json
from datetime import UTC, date, datetime, time
from uuid import uuid4
from zoneinfo import ZoneInfo

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
    SecurityStatus,
    SourceAvailabilityStatus,
    TemporalEnvelope,
)
from market_regime_alpha.market.ports import (
    ArchiveTradingSession,
    MarketBarRevisionHead,
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


def test_daily_bar_preserves_session_security_and_st_status() -> None:
    capture = _capture()
    query = BaoStockArchiveQuery(
        kind=BaoStockArchiveQueryKind.HISTORY_DAILY_RAW,
        code="sh.600000",
        start_date=date(2026, 1, 5),
        end_date=date(2026, 1, 5),
    )
    fields = [
        "date", "code", "open", "high", "low", "close", "preclose",
        "volume", "amount", "adjustflag", "turn", "tradestatus", "pctChg",
        "isST",
    ]

    batch = BaoStockArchiveNormalizer().normalize(
        capture,
        _payload(
            query,
            fields,
            [["2026-01-05", "sh.600000", "10", "11", "9", "10", "10", "1", "10", "3", "1", "1", "0", "0"]],
        ),
    )

    assert batch.security_status_facts[0].status is SecurityStatus.ACTIVE
    assert batch.lifecycle_status_facts[0].status.value == "NORMAL"
    assert not batch.gaps


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


def test_empty_single_session_history_becomes_typed_gap() -> None:
    capture = _capture()
    query = BaoStockArchiveQuery(
        kind=BaoStockArchiveQueryKind.HISTORY_5M_RAW,
        code="sh.600000",
        start_date=date(2026, 1, 5),
        end_date=date(2026, 1, 5),
    )
    fields = [
        "date", "time", "code", "open", "high", "low", "close",
        "volume", "amount", "adjustflag",
    ]

    batch = BaoStockArchiveNormalizer().normalize(
        capture,
        _payload(query, fields, []),
    )

    assert not batch.bars
    assert batch.gaps[0].gap_kind is GapKind.MISSING
    assert batch.gaps[0].reason_code is GapReasonCode.NO_ROWS_RETURNED
    assert batch.gaps[0].session_id == a_share_session_id("XSHG", date(2026, 1, 5))


def test_csi300_snapshot_preserves_exact_asof_membership_lineage() -> None:
    capture = _capture()
    query = BaoStockArchiveQuery(
        kind=BaoStockArchiveQueryKind.CSI300_MEMBERS,
        start_date=date(2026, 9, 3),
        end_date=date(2026, 9, 3),
    )

    batch = BaoStockArchiveNormalizer(expected_query=query).normalize(
        capture,
        _payload(
            query,
            ["updateDate", "code", "code_name"],
            [
                ["2026-08-31", "sh.600000", "浦发银行"],
                ["2026-08-31", "sz.000001", "平安银行"],
            ],
        ),
    )

    assert batch.classifications[0].classification_scheme == "INDEX_MEMBERSHIP"
    assert batch.classifications[0].classification_code == "CSI300"
    assert len(batch.classification_memberships) == 2
    assert all(
        item.classification_id == batch.classifications[0].classification_id
        for item in batch.classification_memberships
    )
    assert {
        item.instrument_id for item in batch.classification_memberships
    } == {
        a_share_instrument_id("sh.600000"),
        a_share_instrument_id("sz.000001"),
    }


def test_csi300_snapshot_rejects_wrong_date_and_duplicate_member() -> None:
    capture = _capture()
    query = BaoStockArchiveQuery(
        kind=BaoStockArchiveQueryKind.CSI300_MEMBERS,
        start_date=date(2026, 9, 3),
        end_date=date(2026, 9, 3),
    )
    fields = ["updateDate", "code", "code_name"]
    with pytest.raises(ValueError, match="after the frozen"):
        BaoStockArchiveNormalizer().normalize(
            capture,
            _payload(query, fields, [["2026-09-04", "sh.600000", "浦发银行"]]),
        )
    row = ["2026-08-31", "sh.600000", "浦发银行"]
    with pytest.raises(ValueError, match="duplicate member"):
        BaoStockArchiveNormalizer().normalize(
            capture,
            _payload(query, fields, [row, row]),
        )


class _RevisionLineage:
    def __init__(self, head: MarketBarRevisionHead | None) -> None:
        self.head = head

    def market_bar_head(self, **kwargs):
        return self.head


class _Sessions:
    def sessions(self, *, exchange, start_date, end_date):
        shanghai = ZoneInfo("Asia/Shanghai")

        def at(session_date, value):
            return datetime.combine(session_date, value, tzinfo=shanghai).astimezone(UTC)

        return tuple(
            ArchiveTradingSession(
                session_id=a_share_session_id(exchange, session_date),
                exchange=exchange,
                session_date=session_date,
                open_at=at(session_date, time(9, 30)),
                break_start_at=at(session_date, time(11, 30)),
                break_end_at=at(session_date, time(13, 0)),
                close_at=at(session_date, time(15, 0)),
            )
            for session_date in (date(2026, 1, 5), date(2026, 1, 6))
        )


def test_multi_session_bar_slice_expands_complete_calendar_grid() -> None:
    capture = _capture()
    query = BaoStockArchiveQuery(
        kind=BaoStockArchiveQueryKind.HISTORY_5M_RAW,
        code="sh.600000",
        start_date=date(2026, 1, 5),
        end_date=date(2026, 1, 6),
    )
    fields = [
        "date", "time", "code", "open", "high", "low", "close",
        "volume", "amount", "adjustflag",
    ]

    batch = BaoStockArchiveNormalizer(trading_sessions=_Sessions()).normalize(
        capture,
        _payload(
            query,
            fields,
            [["2026-01-05", "20260105093500000", "sh.600000", "10", "10", "10", "10", "1", "10", "3"]],
        ),
    )

    assert len(batch.bars) == 1
    assert len(batch.gaps) == 95
    assert all(
        item.reason_code is GapReasonCode.EXPECTED_OBSERVATION_MISSING
        for item in batch.gaps
    )
    assert sum(
        item.session_id == a_share_session_id("XSHG", date(2026, 1, 6))
        for item in batch.gaps
    ) == 48


def test_repeated_observation_appends_exact_market_revision_lineage() -> None:
    capture = _capture()
    query = BaoStockArchiveQuery(
        kind=BaoStockArchiveQueryKind.HISTORY_5M_RAW,
        code="sh.600000",
        start_date=date(2026, 1, 5),
        end_date=date(2026, 1, 5),
    )
    fields = [
        "date", "time", "code", "open", "high", "low", "close",
        "volume", "amount", "adjustflag",
    ]
    predecessor = uuid4()

    batch = BaoStockArchiveNormalizer(
        revision_lineage=_RevisionLineage(
            MarketBarRevisionHead(predecessor, 3)
        )
    ).normalize(
        capture,
        _payload(
            query,
            fields,
            [["2026-01-05", "20260105093500000", "sh.600000", "10", "10", "10", "10", "1", "10", "3"]],
        ),
    )

    assert batch.bars[0].revision == 4
    assert batch.bars[0].supersedes_revision_id == predecessor


def test_duplicate_bar_in_one_payload_fails_closed() -> None:
    capture = _capture()
    query = BaoStockArchiveQuery(
        kind=BaoStockArchiveQueryKind.HISTORY_5M_RAW,
        code="sh.600000",
        start_date=date(2026, 1, 5),
        end_date=date(2026, 1, 5),
    )
    fields = [
        "date", "time", "code", "open", "high", "low", "close",
        "volume", "amount", "adjustflag",
    ]
    row = ["2026-01-05", "20260105093500000", "sh.600000", "10", "10", "10", "10", "1", "10", "3"]

    with pytest.raises(ValueError, match="duplicate bar"):
        BaoStockArchiveNormalizer().normalize(
            capture,
            _payload(query, fields, [row, row]),
        )
