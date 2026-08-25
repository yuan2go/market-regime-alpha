from __future__ import annotations

from pathlib import Path

import pytest

from market_regime_alpha.application.historical_corpus.artifacts import (
    load_historical_package_index,
)
from market_regime_alpha.application.historical_corpus.contracts import (
    HistoricalArtifactKind,
)
from market_regime_alpha.application.historical_corpus.staged_package import (
    HistoricalOwnerMetadata,
    StagedHistoricalPackageWriter,
)
from tests.application.historical_corpus.support import raw_owner


def _metadata():
    owner = raw_owner()
    return HistoricalOwnerMetadata(
        provider_id=owner.provider_id,
        normalization_version=owner.normalization_version,
        parent_reference=owner.parent_reference,
        created_at=owner.created_at,
        retrieved_at=owner.retrieved_at,
        coverage=owner.coverage,
        limitations=owner.limitations,
    )


def test_staged_writer_releases_partition_records_and_replays_exact_index(
    tmp_path: Path,
) -> None:
    owner = raw_owner()
    writer = StagedHistoricalPackageWriter(
        artifact_root=tmp_path,
        artifact_kind=HistoricalArtifactKind.RAW_PROVIDER_ARCHIVE,
        bucket_count=owner.bucket_count,
    )

    descriptor = writer.add_partition(owner.partitions[0])

    assert descriptor.row_count == 1
    assert writer.decoded_record_count == 0
    first = writer.finalize(_metadata())
    replayed = load_historical_package_index(first.root)
    assert replayed.reference == owner.reference
    assert replayed.reference == first.reference
    assert replayed.physical_hash == first.physical_hash
    assert replayed.partitions == (descriptor,)


def test_staged_writer_never_publishes_partial_package(tmp_path: Path) -> None:
    owner = raw_owner()

    def fail(stage: str) -> None:
        if stage == "AFTER_STAGING_VALIDATED":
            raise RuntimeError(stage)

    writer = StagedHistoricalPackageWriter(
        artifact_root=tmp_path,
        artifact_kind=HistoricalArtifactKind.RAW_PROVIDER_ARCHIVE,
        bucket_count=owner.bucket_count,
        failure_injector=fail,
    )
    writer.add_partition(owner.partitions[0])

    with pytest.raises(RuntimeError, match="AFTER_STAGING_VALIDATED"):
        writer.finalize(_metadata())

    family = tmp_path / "historical-corpus" / "raw_provider_archive"
    assert not tuple(family.glob("historical-data-owner-*"))
    assert not tuple(family.glob(".*"))


def test_staged_writer_rejects_duplicate_partition_key(tmp_path: Path) -> None:
    owner = raw_owner()
    writer = StagedHistoricalPackageWriter(
        artifact_root=tmp_path,
        artifact_kind=HistoricalArtifactKind.RAW_PROVIDER_ARCHIVE,
        bucket_count=owner.bucket_count,
    )
    writer.add_partition(owner.partitions[0])

    with pytest.raises(ValueError, match="duplicate partition"):
        writer.add_partition(owner.partitions[0])
