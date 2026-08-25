from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from market_regime_alpha.application.historical_corpus.artifacts import (
    load_historical_package_index,
    load_verified_historical_package,
    publish_historical_package,
)
from market_regime_alpha.application.historical_corpus.postgres_repository import (
    HistoricalCorpusIntegrityError,
    HistoricalCorpusOwnerNotFound,
    PostgresHistoricalCorpusRepository,
)
from market_regime_alpha.application.historical_corpus.contracts import (
    HistoricalArtifactKind,
    HistoricalCorpusCoverage,
    HistoricalDataOwner,
    HistoricalListingStatus,
    HistoricalNormalizedBar,
    HistoricalTradingStatus,
    build_partitions,
)
from market_regime_alpha.application.historical_corpus.selective_read import (
    HistoricalReadQuery,
)
from market_regime_alpha.application.historical_corpus.staged_package import (
    HistoricalOwnerMetadata,
    StagedHistoricalPackageWriter,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.market_data.contracts import Timeframe
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from tests.application.historical_corpus.support import normalized_owner, raw_owner


def test_owner_registration_reloads_exact_locator_and_hash(
    postgres_factory: PostgresConnectionFactory,
    tmp_path: Path,
) -> None:
    repository = PostgresHistoricalCorpusRepository(postgres_factory, artifact_root=tmp_path)
    raw = raw_owner()
    verified = repository.publish_and_register(raw)

    assert repository.load(raw.reference) == verified
    with pytest.raises(HistoricalCorpusOwnerNotFound):
        repository.load(
            ValidationArtifactReference(
                raw.artifact_kind.value,
                raw.owner_id,
                canonical_hash({"wrong": True}),
            )
        )


def test_descriptor_index_registration_reloads_without_decoding_whole_owner(
    postgres_factory: PostgresConnectionFactory,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = raw_owner()
    writer = StagedHistoricalPackageWriter(
        artifact_root=tmp_path,
        artifact_kind=owner.artifact_kind,
        bucket_count=owner.bucket_count,
    )
    writer.add_partition(owner.partitions[0])
    index = writer.finalize(
        HistoricalOwnerMetadata(
            provider_id=owner.provider_id,
            normalization_version=owner.normalization_version,
            parent_reference=owner.parent_reference,
            created_at=owner.created_at,
            retrieved_at=owner.retrieved_at,
            coverage=owner.coverage,
            limitations=owner.limitations,
        )
    )
    repository = PostgresHistoricalCorpusRepository(
        postgres_factory,
        artifact_root=tmp_path,
    )
    monkeypatch.setattr(
        "market_regime_alpha.application.historical_corpus.artifacts._read_partition",
        lambda **_: (_ for _ in ()).throw(AssertionError("partition decoded")),
    )

    registered = repository.register_index(index)

    assert registered == load_historical_package_index(index.root)
    assert registered.reference == owner.reference


def test_normalized_owner_requires_exact_registered_raw_parent(
    postgres_factory: PostgresConnectionFactory,
    tmp_path: Path,
) -> None:
    repository = PostgresHistoricalCorpusRepository(postgres_factory, artifact_root=tmp_path)
    raw = raw_owner()
    normalized = normalized_owner(raw)
    package_path = publish_historical_package(artifact_root=tmp_path, owner=normalized)

    with pytest.raises(HistoricalCorpusIntegrityError, match="parent"):
        repository.register(load_verified_historical_package(package_path))

    repository.publish_and_register(raw)
    registered = repository.publish_and_register(normalized)
    assert repository.load(normalized.reference) == registered


def test_concurrent_registration_is_idempotent(
    postgres_factory: PostgresConnectionFactory,
    tmp_path: Path,
) -> None:
    repository = PostgresHistoricalCorpusRepository(postgres_factory, artifact_root=tmp_path)
    raw = raw_owner()
    package = load_verified_historical_package(publish_historical_package(artifact_root=tmp_path, owner=raw))

    with ThreadPoolExecutor(max_workers=2) as executor:
        tuple(executor.map(lambda _: repository.register(package), range(2)))

    assert repository.load(raw.reference).owner == raw


def test_registered_package_corruption_fails_closed(
    postgres_factory: PostgresConnectionFactory,
    tmp_path: Path,
) -> None:
    repository = PostgresHistoricalCorpusRepository(postgres_factory, artifact_root=tmp_path)
    raw = raw_owner()
    registered = repository.publish_and_register(raw)
    parquet = next(registered.root.rglob("*.parquet"))
    with parquet.open("ab") as handle:
        handle.write(b"corruption")

    with pytest.raises(ValueError, match="checksum mismatch"):
        repository.load(raw.reference)


def test_selective_read_matches_full_owner_and_records_pushdown_metrics(
    postgres_factory: PostgresConnectionFactory,
    tmp_path: Path,
) -> None:
    repository = PostgresHistoricalCorpusRepository(postgres_factory, artifact_root=tmp_path)
    raw = raw_owner()
    normalized = normalized_owner(raw)
    repository.publish_and_register(raw)
    repository.publish_and_register(normalized)

    result = repository.read(
        HistoricalReadQuery.create(
            reference=normalized.reference,
            timeframes=(Timeframe.DAILY,),
            first_market_date=date(2023, 1, 3),
            last_market_date=date(2023, 1, 3),
            symbols=("600000.SH",),
            max_rows=10,
        )
    )

    full_records = tuple(record for partition in repository.load(normalized.reference).owner.partitions for record in partition.records)
    assert result.records == full_records
    assert result.metrics.candidate_partition_count == 1
    assert result.metrics.verified_partition_count == 1
    assert result.metrics.returned_row_count == 1
    assert result.metrics.maximum_batch_row_count <= 10
    assert result.metrics.projected_columns == (
        "logical_record_schema",
        "market_date",
        "partition_hash",
        "partition_id",
        "record_json",
        "symbol",
        "timeframe",
    )


def test_selective_read_matches_full_filter_across_date_and_symbol_partitions(
    postgres_factory: PostgresConnectionFactory,
    tmp_path: Path,
) -> None:
    repository = PostgresHistoricalCorpusRepository(postgres_factory, artifact_root=tmp_path)
    raw = raw_owner()
    repository.publish_and_register(raw)
    normalized = _multi_partition_normalized_owner(raw)
    repository.publish_and_register(normalized)

    result = repository.read(
        HistoricalReadQuery.create(
            reference=normalized.reference,
            timeframes=(Timeframe.DAILY,),
            first_market_date=date(2023, 1, 4),
            last_market_date=date(2024, 1, 3),
            symbols=("000001.SZ", "600000.SH"),
            max_rows=10,
            batch_size=2,
        )
    )
    full = repository.load(normalized.reference).owner
    expected = tuple(
        item
        for partition in full.partitions
        for item in partition.records
        if item.timeframe is Timeframe.DAILY
        and date(2023, 1, 4) <= item.market_date <= date(2024, 1, 3)
        and item.symbol in {"000001.SZ", "600000.SH"}
    )

    assert result.records == tuple(
        sorted(
            expected,
            key=lambda item: (
                item.market_date,
                item.symbol,
                item.event_start,
                str(item.bar_id),
            ),
        )
    )
    assert result.metrics.candidate_partition_count >= 2
    assert result.metrics.arrow_batch_count >= 2
    assert result.metrics.maximum_batch_row_count <= 2


def test_selective_read_rejects_unbounded_or_corrupt_slice(
    postgres_factory: PostgresConnectionFactory,
    tmp_path: Path,
) -> None:
    repository = PostgresHistoricalCorpusRepository(postgres_factory, artifact_root=tmp_path)
    raw = raw_owner()
    normalized = normalized_owner(raw)
    repository.publish_and_register(raw)
    registered = repository.publish_and_register(normalized)

    with pytest.raises(ValueError, match="max_rows"):
        HistoricalReadQuery.create(
            reference=normalized.reference,
            timeframes=(Timeframe.DAILY,),
            first_market_date=date(2023, 1, 1),
            last_market_date=date(2023, 1, 31),
            symbols=None,
            max_rows=0,
        )

    parquet = next(registered.root.rglob("*.parquet"))
    with parquet.open("ab") as handle:
        handle.write(b"corruption")
    with pytest.raises(ValueError, match="checksum mismatch"):
        repository.read(
            HistoricalReadQuery.create(
                reference=normalized.reference,
                timeframes=(Timeframe.DAILY,),
                first_market_date=date(2023, 1, 1),
                last_market_date=date(2023, 1, 31),
                symbols=None,
                max_rows=10,
            )
        )


def _multi_partition_normalized_owner(
    raw: HistoricalDataOwner,
) -> HistoricalDataOwner:
    raw_request = raw.partitions[0].records[0]
    raw_reference = ValidationArtifactReference("RAW_PROVIDER_REQUEST", raw_request.request_id, raw_request.content_hash)
    inputs = (
        ("600000.SH", Timeframe.DAILY, date(2023, 1, 3), 1),
        ("000001.SZ", Timeframe.DAILY, date(2023, 1, 4), 2),
        ("600000.SH", Timeframe.DAILY, date(2024, 1, 3), 3),
        ("000001.SZ", Timeframe.MINUTE_5, date(2024, 1, 3), 4),
    )
    bars = tuple(
        HistoricalNormalizedBar.create(
            symbol=symbol,
            timeframe=timeframe,
            market_date=market_date,
            event_start=datetime.combine(market_date, datetime.min.time(), tzinfo=UTC),
            event_end=datetime.combine(market_date, datetime.min.time(), tzinfo=UTC)
            + timedelta(minutes=5 if timeframe is Timeframe.MINUTE_5 else 900),
            retrieved_at=raw.retrieved_at,
            open=Decimal("10"),
            high=Decimal("10.5"),
            low=Decimal("9.5"),
            close=Decimal("10.2"),
            volume=Decimal("100000"),
            amount=Decimal("1020000"),
            adjustment_basis="BAOSTOCK_ADJUSTFLAG_3_RAW",
            trading_status=HistoricalTradingStatus.TRADING,
            st_status=False,
            listing_status=HistoricalListingStatus.UNKNOWN,
            raw_request_reference=raw_reference,
            raw_row_number=row_number,
            missing_fields=("LISTING_STATUS",),
            limitations=("HISTORICAL_LISTING_STATUS_NOT_PROVIDED",),
        )
        for symbol, timeframe, market_date, row_number in inputs
    )
    partitions = build_partitions(
        artifact_kind=HistoricalArtifactKind.NORMALIZED_DATASET,
        records=bars,
        bucket_count=4,
    )
    return HistoricalDataOwner.create(
        artifact_kind=HistoricalArtifactKind.NORMALIZED_DATASET,
        provider_id="BAOSTOCK",
        normalization_version="baostock-historical-normalization/v1",
        parent_reference=raw.reference,
        created_at=raw.created_at,
        retrieved_at=raw.retrieved_at,
        first_market_date=min(item.market_date for item in bars),
        last_market_date=max(item.market_date for item in bars),
        bucket_count=4,
        partitions=partitions,
        coverage=HistoricalCorpusCoverage(
            expected_symbols=("000001.SZ", "600000.SH"),
            observed_symbols=("000001.SZ", "600000.SH"),
            expected_request_count=4,
            successful_request_count=4,
            source_row_count=4,
            normalized_row_count=4,
            missing_field_counts=(("LISTING_STATUS", 4),),
            failure_counts=(),
        ),
        limitations=("HISTORICAL_LISTING_STATUS_NOT_PROVIDED",),
    )
