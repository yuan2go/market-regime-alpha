from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from datetime import date

import pytest

from market_regime_alpha.application.historical_corpus.artifacts import (
    load_verified_historical_package,
    publish_historical_package,
)
from market_regime_alpha.application.historical_corpus.postgres_repository import (
    HistoricalCorpusIntegrityError,
    HistoricalCorpusOwnerNotFound,
    PostgresHistoricalCorpusRepository,
)
from market_regime_alpha.application.historical_corpus.selective_read import (
    HistoricalReadQuery,
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
    repository = PostgresHistoricalCorpusRepository(
        postgres_factory, artifact_root=tmp_path
    )
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


def test_normalized_owner_requires_exact_registered_raw_parent(
    postgres_factory: PostgresConnectionFactory,
    tmp_path: Path,
) -> None:
    repository = PostgresHistoricalCorpusRepository(
        postgres_factory, artifact_root=tmp_path
    )
    raw = raw_owner()
    normalized = normalized_owner(raw)
    package_path = publish_historical_package(
        artifact_root=tmp_path, owner=normalized
    )

    with pytest.raises(HistoricalCorpusIntegrityError, match="parent"):
        repository.register(load_verified_historical_package(package_path))

    repository.publish_and_register(raw)
    registered = repository.publish_and_register(normalized)
    assert repository.load(normalized.reference) == registered


def test_concurrent_registration_is_idempotent(
    postgres_factory: PostgresConnectionFactory,
    tmp_path: Path,
) -> None:
    repository = PostgresHistoricalCorpusRepository(
        postgres_factory, artifact_root=tmp_path
    )
    raw = raw_owner()
    package = load_verified_historical_package(
        publish_historical_package(artifact_root=tmp_path, owner=raw)
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        tuple(executor.map(lambda _: repository.register(package), range(2)))

    assert repository.load(raw.reference).owner == raw


def test_registered_package_corruption_fails_closed(
    postgres_factory: PostgresConnectionFactory,
    tmp_path: Path,
) -> None:
    repository = PostgresHistoricalCorpusRepository(
        postgres_factory, artifact_root=tmp_path
    )
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
    repository = PostgresHistoricalCorpusRepository(
        postgres_factory, artifact_root=tmp_path
    )
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

    full_records = tuple(
        record
        for partition in repository.load(normalized.reference).owner.partitions
        for record in partition.records
    )
    assert result.records == full_records
    assert result.metrics.candidate_partition_count == 1
    assert result.metrics.verified_partition_count == 1
    assert result.metrics.returned_row_count == 1
    assert result.metrics.maximum_batch_row_count <= 10
    assert "record_json" in result.metrics.projected_columns


def test_selective_read_rejects_unbounded_or_corrupt_slice(
    postgres_factory: PostgresConnectionFactory,
    tmp_path: Path,
) -> None:
    repository = PostgresHistoricalCorpusRepository(
        postgres_factory, artifact_root=tmp_path
    )
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
