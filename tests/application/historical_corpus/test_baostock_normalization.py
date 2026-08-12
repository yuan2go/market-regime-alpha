from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime

import pytest

from market_regime_alpha.application.historical_corpus.baostock_archive import (
    BAOSTOCK_HISTORICAL_PROVIDER_ID,
    BaoStockHistoricalArchiveClient,
)
from market_regime_alpha.application.historical_corpus.contracts import (
    HistoricalArtifactKind,
    HistoricalRawRequest,
    HistoricalTradingStatus,
    build_partitions,
)
from market_regime_alpha.application.historical_corpus.normalization import (
    HistoricalNormalizationError,
    normalize_baostock_archive,
)
from market_regime_alpha.market_data.contracts import Timeframe
from tests.application.historical_corpus.support import raw_owner, raw_request


@dataclass
class _Response:
    fields: list[str]
    rows: list[list[str]]
    error_code: str = "0"
    error_msg: str = ""
    index: int = -1

    def next(self) -> bool:
        self.index += 1
        return self.index < len(self.rows)

    def get_row_data(self) -> list[str]:
        return self.rows[self.index]


class _FakeBaoStock:
    def __init__(self) -> None:
        self.queries: list[dict[str, str]] = []

    def login(self, **_: str) -> _Response:
        return _Response([], [])

    def logout(self) -> _Response:
        return _Response([], [])

    def query_history_k_data_plus(
        self,
        code: str,
        fields: str,
        **parameters: str,
    ) -> _Response:
        self.queries.append({"code": code, "fields": fields, **parameters})
        names = fields.split(",")
        if parameters["frequency"] == "d":
            values = {
                "date": f"{parameters['start_date'][:4]}-01-03",
                "code": code,
                "open": "10",
                "high": "10.5",
                "low": "9.8",
                "close": "10.2",
                "volume": "100000",
                "amount": "1020000",
                "adjustflag": "3",
                "tradestatus": "1",
                "isST": "0",
            }
        else:
            values = {
                "date": f"{parameters['start_date'][:4]}-01-03",
                "time": f"{parameters['start_date'][:4]}0103093500000",
                "code": code,
                "open": "10",
                "high": "10.2",
                "low": "9.9",
                "close": "10.1",
                "volume": "1000",
                "amount": "10100",
                "adjustflag": "3",
            }
        return _Response(names, [[values[name] for name in names]])


def test_acquisition_splits_requests_by_year_and_preserves_true_retrieval() -> None:
    provider = _FakeBaoStock()
    retrieved_at = datetime(2026, 8, 12, 3, 0, tzinfo=UTC)
    owner = BaoStockHistoricalArchiveClient(
        clock=lambda: retrieved_at,
        baostock_module=provider,
    ).acquire(
        symbols=("600000.SH",),
        start_date=date(2023, 1, 1),
        end_date=date(2024, 12, 31),
        timeframes=(Timeframe.DAILY, Timeframe.MINUTE_5),
        bucket_count=4,
    )

    assert owner.artifact_kind is HistoricalArtifactKind.RAW_PROVIDER_ARCHIVE
    assert owner.provider_id == BAOSTOCK_HISTORICAL_PROVIDER_ID
    assert owner.retrieved_at == retrieved_at
    assert owner.coverage.expected_request_count == 4
    assert owner.coverage.source_row_count == 4
    assert len(provider.queries) == 4
    requests = tuple(
        record for partition in owner.partitions for record in partition.records
    )
    assert all(isinstance(item, HistoricalRawRequest) for item in requests)
    assert all(item.retrieved_at == retrieved_at for item in requests)
    assert all(
        "BAOSTOCK_LIBRARY_RESULT_REENCODED_NOT_TRANSPORT_BYTES"
        in item.limitations
        for item in requests
        if isinstance(item, HistoricalRawRequest)
    )


def test_normalization_preserves_retrieval_clock_and_missingness() -> None:
    provider = _FakeBaoStock()
    retrieved_at = datetime(2026, 8, 12, 3, 0, tzinfo=UTC)
    raw = BaoStockHistoricalArchiveClient(
        clock=lambda: retrieved_at,
        baostock_module=provider,
    ).acquire(
        symbols=("600000.SH",),
        start_date=date(2023, 1, 1),
        end_date=date(2023, 12, 31),
        bucket_count=4,
    )

    normalized = normalize_baostock_archive(raw)
    bars = tuple(
        record for partition in normalized.partitions for record in partition.records
    )

    assert normalized.parent_reference == raw.reference
    assert normalized.created_at == raw.created_at
    assert normalized.coverage.normalized_row_count == 2
    assert all(item.retrieved_at == retrieved_at for item in bars)
    daily = next(item for item in bars if item.timeframe is Timeframe.DAILY)
    minute = next(item for item in bars if item.timeframe is Timeframe.MINUTE_5)
    assert daily.event_end == datetime(2023, 1, 3, 7, 0, tzinfo=UTC)
    assert minute.event_end == datetime(2023, 1, 3, 1, 35, tzinfo=UTC)
    assert daily.trading_status is HistoricalTradingStatus.TRADING
    assert daily.st_status is False
    assert minute.st_status is None
    assert ("ST_STATUS", 1) in normalized.coverage.missing_field_counts
    assert ("LISTING_STATUS", 2) in normalized.coverage.missing_field_counts


def test_suspension_is_not_silently_price_filled() -> None:
    request = HistoricalRawRequest.create(
        provider_id=BAOSTOCK_HISTORICAL_PROVIDER_ID,
        product="query_history_k_data_plus:d:adjustflag=3",
        symbol="600000.SH",
        timeframe=Timeframe.DAILY,
        start_date=date(2023, 1, 1),
        end_date=date(2023, 12, 31),
        request_parameters=(("frequency", "d"),),
        requested_at=datetime(2026, 8, 12, 2, 0, tzinfo=UTC),
        retrieved_at=datetime(2026, 8, 12, 2, 0, tzinfo=UTC),
        fields=(
            "date", "code", "open", "high", "low", "close", "volume",
            "amount", "adjustflag", "tradestatus", "isST",
        ),
        rows=((
            "2023-01-03", "sh.600000", "", "", "", "", "0", "0",
            "3", "0", "0",
        ),),
    )
    raw = raw_owner(request=request)
    # Test support uses a legacy provider id; bind the same immutable payload to
    # the BaoStock product identity required by the normalizer.
    raw = type(raw).create(
        artifact_kind=raw.artifact_kind,
        provider_id=BAOSTOCK_HISTORICAL_PROVIDER_ID,
        normalization_version=None,
        parent_reference=None,
        created_at=raw.created_at,
        retrieved_at=raw.retrieved_at,
        first_market_date=raw.first_market_date,
        last_market_date=raw.last_market_date,
        bucket_count=raw.bucket_count,
        partitions=raw.partitions,
        coverage=raw.coverage,
        limitations=raw.limitations,
    )

    normalized = normalize_baostock_archive(raw)
    bar = normalized.partitions[0].records[0]

    assert bar.trading_status is HistoricalTradingStatus.SUSPENDED
    assert (bar.open, bar.high, bar.low, bar.close) == (None, None, None, None)
    assert "OHLC" in bar.missing_fields


def test_duplicate_event_facts_fail_normalization() -> None:
    first = raw_request()
    duplicate = HistoricalRawRequest.create(
        provider_id=first.provider_id,
        product=first.product,
        symbol=first.symbol,
        timeframe=first.timeframe,
        start_date=first.start_date,
        end_date=first.end_date,
        request_parameters=(*first.request_parameters, ("retry", "1")),
        requested_at=first.requested_at,
        retrieved_at=first.retrieved_at,
        fields=first.fields,
        rows=first.rows,
        limitations=first.limitations,
    )
    partitions = build_partitions(
        artifact_kind=HistoricalArtifactKind.RAW_PROVIDER_ARCHIVE,
        records=(first, duplicate),
        bucket_count=4,
    )
    template = raw_owner(request=first)
    raw = type(template).create(
        artifact_kind=template.artifact_kind,
        provider_id=BAOSTOCK_HISTORICAL_PROVIDER_ID,
        normalization_version=None,
        parent_reference=None,
        created_at=template.created_at,
        retrieved_at=template.retrieved_at,
        first_market_date=partitions[0].first_market_date,
        last_market_date=partitions[-1].last_market_date,
        bucket_count=4,
        partitions=partitions,
        coverage=template.coverage,
        limitations=template.limitations,
    )

    with pytest.raises(HistoricalNormalizationError, match="duplicate"):
        normalize_baostock_archive(raw)
