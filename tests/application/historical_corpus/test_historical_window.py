from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from market_regime_alpha.application.historical_corpus.historical_window import (
    HistoricalDatasetWindowIndex,
    HistoricalWindowReader,
    _CachedDailyMonth,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash


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
    reads: list[tuple[int, int]] = []

    def sparse_month(
        _reference: ValidationArtifactReference,
        year: int,
        month: int,
        _symbols: tuple[str, ...],
    ) -> _CachedDailyMonth:
        reads.append((year, month))
        return _CachedDailyMonth(records=(), daily_dates=(), read_lineage={})

    reader._daily_month = sparse_month  # type: ignore[method-assign]  # noqa: SLF001
    records, dates = reader._daily_window(  # noqa: SLF001
        reference,
        date(2025, 7, 14),
        symbols=("688999.SH",),
    )

    assert records == ()
    assert dates == ()
    assert reads == [
        (2025, 7),
        (2025, 6),
        (2025, 5),
        (2025, 4),
        (2025, 3),
        (2025, 2),
        (2025, 1),
    ]
