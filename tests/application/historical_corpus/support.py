from __future__ import annotations

from calendar import monthrange
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from market_regime_alpha.application.historical_corpus.contracts import (
    HistoricalArtifactKind,
    HistoricalCorpusCoverage,
    HistoricalDataOwner,
    HistoricalListingStatus,
    HistoricalNormalizedBar,
    HistoricalRawRequest,
    HistoricalTradingStatus,
    build_partitions,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.market_data.contracts import Timeframe


RETRIEVED_AT = datetime(2026, 8, 12, 2, 0, tzinfo=UTC)
CREATED_AT = datetime(2026, 8, 12, 2, 1, tzinfo=UTC)


def raw_request(
    *,
    symbol: str = "600000.SH",
    timeframe: Timeframe = Timeframe.DAILY,
    year: int = 2023,
    month: int = 1,
) -> HistoricalRawRequest:
    fields = (
        "date",
        "code",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
        "adjustflag",
        "tradestatus",
        "isST",
    )
    row = (
        f"{year}-{month:02d}-03",
        "sh.600000",
        "10",
        "10.5",
        "9.8",
        "10.2",
        "100000",
        "1020000",
        "3",
        "1",
        "0",
    )
    return HistoricalRawRequest.create(
        provider_id="BAOSTOCK",
        product="query_history_k_data_plus",
        symbol=symbol,
        timeframe=timeframe,
        start_date=(
            date(year, 1, 1)
            if timeframe is Timeframe.DAILY
            else date(year, month, 1)
        ),
        end_date=(
            date(year, 12, 31)
            if timeframe is Timeframe.DAILY
            else date(year, month, monthrange(year, month)[1])
        ),
        request_parameters=(
            ("adjustflag", "3"),
            ("frequency", "d" if timeframe is Timeframe.DAILY else "5"),
        ),
        requested_at=RETRIEVED_AT - timedelta(seconds=1),
        retrieved_at=RETRIEVED_AT,
        fields=fields,
        rows=(row,),
        limitations=(
            "BAOSTOCK_LIBRARY_RESULT_REENCODED_NOT_TRANSPORT_BYTES",
            "PUBLIC_DATA_EXPLORATORY_ONLY",
        ),
    )


def raw_owner(*, request: HistoricalRawRequest | None = None) -> HistoricalDataOwner:
    request = request or raw_request()
    partitions = build_partitions(
        artifact_kind=HistoricalArtifactKind.RAW_PROVIDER_ARCHIVE,
        records=(request,),
        bucket_count=4,
    )
    return HistoricalDataOwner.create(
        artifact_kind=HistoricalArtifactKind.RAW_PROVIDER_ARCHIVE,
        provider_id="BAOSTOCK",
        normalization_version=None,
        parent_reference=None,
        created_at=CREATED_AT,
        retrieved_at=RETRIEVED_AT,
        first_market_date=partitions[0].first_market_date,
        last_market_date=partitions[-1].last_market_date,
        bucket_count=4,
        partitions=partitions,
        coverage=HistoricalCorpusCoverage(
            expected_symbols=(request.symbol,),
            observed_symbols=(request.symbol,),
            expected_request_count=1,
            successful_request_count=1,
            source_row_count=1,
            normalized_row_count=0,
            missing_field_counts=(),
            failure_counts=(),
        ),
        limitations=(),
    )


def normalized_owner(raw: HistoricalDataOwner) -> HistoricalDataOwner:
    request = raw.partitions[0].records[0]
    assert isinstance(request, HistoricalRawRequest)
    bar = HistoricalNormalizedBar.create(
        symbol=request.symbol,
        timeframe=Timeframe.DAILY,
        market_date=date(2023, 1, 3),
        event_start=datetime(2023, 1, 3, 6, 59, 59, tzinfo=UTC),
        event_end=datetime(2023, 1, 3, 7, 0, tzinfo=UTC),
        retrieved_at=request.retrieved_at,
        open=Decimal("10"),
        high=Decimal("10.5"),
        low=Decimal("9.8"),
        close=Decimal("10.2"),
        volume=Decimal("100000"),
        amount=Decimal("1020000"),
        adjustment_basis="BAOSTOCK_ADJUSTFLAG_3_RAW",
        trading_status=HistoricalTradingStatus.TRADING,
        st_status=False,
        listing_status=HistoricalListingStatus.UNKNOWN,
        raw_request_reference=ValidationArtifactReference(
            "RAW_PROVIDER_REQUEST", request.request_id, request.content_hash
        ),
        raw_row_number=1,
        missing_fields=("LISTING_STATUS",),
        limitations=("HISTORICAL_LISTING_STATUS_NOT_PROVIDED",),
    )
    partitions = build_partitions(
        artifact_kind=HistoricalArtifactKind.NORMALIZED_DATASET,
        records=(bar,),
        bucket_count=4,
    )
    return HistoricalDataOwner.create(
        artifact_kind=HistoricalArtifactKind.NORMALIZED_DATASET,
        provider_id="BAOSTOCK",
        normalization_version="baostock-historical-normalization/v1",
        parent_reference=raw.reference,
        created_at=CREATED_AT,
        retrieved_at=RETRIEVED_AT,
        first_market_date=partitions[0].first_market_date,
        last_market_date=partitions[-1].last_market_date,
        bucket_count=4,
        partitions=partitions,
        coverage=HistoricalCorpusCoverage(
            expected_symbols=(request.symbol,),
            observed_symbols=(request.symbol,),
            expected_request_count=1,
            successful_request_count=1,
            source_row_count=1,
            normalized_row_count=1,
            missing_field_counts=(("LISTING_STATUS", 1),),
            failure_counts=(),
        ),
        limitations=("HISTORICAL_LISTING_STATUS_NOT_PROVIDED",),
    )
