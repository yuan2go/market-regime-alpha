from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from types import SimpleNamespace

from market_regime_alpha.application.historical_corpus.historical_window import (
    HistoricalDatasetWindowIndex,
    HistoricalWindowReader,
)
from market_regime_alpha.application.historical_corpus.contracts import (
    HistoricalListingStatus,
    HistoricalNormalizedBar,
    HistoricalTradingStatus,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.market_data.contracts import Timeframe


def test_sparse_symbol_daily_window_never_scans_before_declared_bound() -> None:
    reference = ValidationArtifactReference(
        "HISTORICAL_NORMALIZED_DATASET",
        ArtifactId("sparse-daily-owner"),
        canonical_hash({"sparse": "daily"}),
    )
    reader = HistoricalWindowReader(
        object(),  # type: ignore[arg-type]
        maximum_daily_rows=10_000,
        maximum_minute_session_rows=10_000,
        minute_session_cache_size=4,
        maximum_daily_lookback_calendar_days=180,
    )
    reader._indexes[reference] = HistoricalDatasetWindowIndex(  # noqa: SLF001
        package=SimpleNamespace(  # type: ignore[arg-type]
            first_market_date=date(2020, 1, 1),
            last_market_date=date(2025, 7, 14),
        )
    )
    queries = []

    class Metrics:
        @staticmethod
        def to_canonical_dict() -> dict[str, object]:
            return {}

    def sparse_read(query, *, record_lineage):
        assert record_lineage is False
        queries.append(query)
        return SimpleNamespace(
            query=query,
            package=SimpleNamespace(reference=reference, checksums=()),
            partitions=(),
            records=(),
            metrics=Metrics(),
        )

    reader._read_normalized = sparse_read  # type: ignore[method-assign]  # noqa: SLF001
    records, dates = reader._daily_window(  # noqa: SLF001
        reference,
        datetime(2025, 7, 14, 6, 55, tzinfo=UTC),
        symbols=("688999.SH",),
    )
    repeated = reader._daily_window(  # noqa: SLF001
        reference,
        datetime(2025, 7, 14, 6, 55, tzinfo=UTC),
        symbols=("688999.SH",),
    )

    assert records == ()
    assert dates == ()
    assert repeated == (records, dates)
    assert len(queries) == 1
    assert queries[0].first_market_date == date(2025, 1, 16)
    assert queries[0].last_market_date == date(2025, 7, 14)


def test_daily_window_caps_only_bars_available_at_decision_time() -> None:
    reference = ValidationArtifactReference(
        "NORMALIZED_DATASET",
        ArtifactId("decision-daily-owner"),
        canonical_hash({"decision": "daily"}),
    )
    decision_time = datetime(2025, 7, 14, 6, 55, tzinfo=UTC)
    start = date(2025, 5, 14)
    records = tuple(
        _daily_bar(
            market_date=start + timedelta(days=index),
            row_number=index + 1,
        )
        for index in range(62)
    )
    assert records[-1].market_date == decision_time.date()
    assert records[-1].event_end > decision_time
    reader = HistoricalWindowReader(
        object(),  # type: ignore[arg-type]
        maximum_daily_rows=10_000,
        maximum_minute_session_rows=10_000,
        minute_session_cache_size=4,
    )
    reader._indexes[reference] = HistoricalDatasetWindowIndex(  # noqa: SLF001
        package=SimpleNamespace(  # type: ignore[arg-type]
            first_market_date=start,
            last_market_date=decision_time.date(),
        )
    )

    class Metrics:
        @staticmethod
        def to_canonical_dict() -> dict[str, object]:
            return {}

    def read(query, *, record_lineage):
        assert record_lineage is False
        return SimpleNamespace(
            query=query,
            package=SimpleNamespace(reference=reference, checksums=()),
            partitions=(),
            records=records,
            metrics=Metrics(),
        )

    reader._read_normalized = read  # type: ignore[method-assign]  # noqa: SLF001

    available, daily_dates = reader._daily_window(  # noqa: SLF001
        reference,
        decision_time,
        symbols=("600000.SH",),
    )

    assert len(available) == 61
    assert all(item.event_end <= decision_time for item in available)
    assert decision_time.date() not in daily_dates


def _daily_bar(
    *,
    market_date: date,
    row_number: int,
) -> HistoricalNormalizedBar:
    event_start = datetime.combine(market_date, time(1, 30), tzinfo=UTC)
    return HistoricalNormalizedBar.create(
        symbol="600000.SH",
        timeframe=Timeframe.DAILY,
        market_date=market_date,
        event_start=event_start,
        event_end=event_start + timedelta(hours=5, minutes=30),
        retrieved_at=datetime(2026, 1, 1, tzinfo=UTC),
        open=Decimal("10"),
        high=Decimal("10.5"),
        low=Decimal("9.5"),
        close=Decimal("10.1"),
        volume=Decimal("100000"),
        amount=Decimal("1010000"),
        adjustment_basis="RAW_UNADJUSTED",
        trading_status=HistoricalTradingStatus.TRADING,
        st_status=False,
        listing_status=HistoricalListingStatus.UNKNOWN,
        raw_request_reference=ValidationArtifactReference(
            "RAW_PROVIDER_REQUEST",
            ArtifactId("raw-decision-daily-owner"),
            canonical_hash({"raw": "decision-daily"}),
        ),
        raw_row_number=row_number,
        missing_fields=("LISTING_STATUS",),
        limitations=("PIT_INCOMPLETE",),
    )
