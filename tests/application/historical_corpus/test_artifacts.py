from __future__ import annotations

from pathlib import Path

import pytest

from market_regime_alpha.application.historical_corpus.artifacts import (
    load_historical_package_index,
    load_verified_historical_package,
    publish_historical_package,
    scan_historical_package,
)
from market_regime_alpha.application.historical_corpus.contracts import (
    HISTORICAL_EVIDENCE_LIMITATIONS,
    HistoricalArtifactKind,
    HistoricalCorpusCoverage,
    HistoricalDataOwner,
    build_partitions,
)
from market_regime_alpha.market_data.contracts import Timeframe
from tests.application.historical_corpus.support import (
    CREATED_AT,
    RETRIEVED_AT,
    raw_owner,
    raw_request,
)


def test_raw_package_is_columnar_content_addressed_and_replayable(
    tmp_path: Path,
) -> None:
    owner = raw_owner()

    path = publish_historical_package(artifact_root=tmp_path, owner=owner)
    replayed = load_verified_historical_package(path)

    assert replayed.owner == owner
    assert replayed.owner.data_eligibility == "EXPLORATORY"
    assert replayed.owner.formal_pit_status == "PIT_INCOMPLETE"
    assert set(HISTORICAL_EVIDENCE_LIMITATIONS).issubset(owner.limitations)
    parquet = tuple(path.rglob("*.parquet"))
    assert len(parquet) == 1
    assert "raw/timeframe=daily/year=2023" in parquet[0].as_posix()
    assert "600000.SH" not in parquet[0].as_posix()
    assert replayed.physical_hash.startswith("sha256:")


def test_raw_daily_and_minute_partitions_cannot_overwrite_each_other(
    tmp_path: Path,
) -> None:
    requests = (
        raw_request(timeframe=Timeframe.DAILY),
        raw_request(timeframe=Timeframe.MINUTE_5),
    )
    partitions = build_partitions(
        artifact_kind=HistoricalArtifactKind.RAW_PROVIDER_ARCHIVE,
        records=requests,
        bucket_count=4,
    )
    owner = HistoricalDataOwner.create(
        artifact_kind=HistoricalArtifactKind.RAW_PROVIDER_ARCHIVE,
        provider_id="BAOSTOCK",
        normalization_version=None,
        parent_reference=None,
        created_at=CREATED_AT,
        retrieved_at=RETRIEVED_AT,
        first_market_date=min(item.first_market_date for item in partitions),
        last_market_date=max(item.last_market_date for item in partitions),
        bucket_count=4,
        partitions=partitions,
        coverage=HistoricalCorpusCoverage(
            expected_symbols=("600000.SH",),
            observed_symbols=("600000.SH",),
            expected_request_count=2,
            successful_request_count=2,
            source_row_count=2,
            normalized_row_count=0,
            missing_field_counts=(),
            failure_counts=(),
        ),
        limitations=(),
    )

    path = publish_historical_package(artifact_root=tmp_path, owner=owner)
    replayed = load_verified_historical_package(path)

    assert replayed.owner == owner
    parquet_paths = {item.relative_to(path).as_posix() for item in path.rglob("*.parquet")}
    assert len(parquet_paths) == 2
    assert any("timeframe=daily" in item for item in parquet_paths)
    assert any("timeframe=minute_5" in item for item in parquet_paths)


def test_raw_intraday_month_partitions_have_unique_immutable_paths(
    tmp_path: Path,
) -> None:
    requests = (
        raw_request(timeframe=Timeframe.MINUTE_5, month=1),
        raw_request(timeframe=Timeframe.MINUTE_5, month=2),
    )
    partitions = build_partitions(
        artifact_kind=HistoricalArtifactKind.RAW_PROVIDER_ARCHIVE,
        records=requests,
        bucket_count=4,
    )
    owner = HistoricalDataOwner.create(
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
            expected_symbols=("600000.SH",),
            observed_symbols=("600000.SH",),
            expected_request_count=2,
            successful_request_count=2,
            source_row_count=2,
            normalized_row_count=0,
            missing_field_counts=(),
            failure_counts=(),
        ),
        limitations=(),
    )

    path = publish_historical_package(artifact_root=tmp_path, owner=owner)
    paths = tuple(
        sorted(item.relative_to(path).as_posix() for item in path.rglob("*.parquet"))
    )

    assert load_verified_historical_package(path).owner == owner
    assert len(paths) == 2
    assert "/month=01/" in paths[0]
    assert "/month=02/" in paths[1]


def test_atomic_publish_is_recoverable_after_registration_gap(tmp_path: Path) -> None:
    owner = raw_owner()

    def fail(point: str) -> None:
        if point == "AFTER_ATOMIC_PUBLISH":
            raise RuntimeError("simulated process interruption")

    with pytest.raises(RuntimeError, match="simulated"):
        publish_historical_package(
            artifact_root=tmp_path,
            owner=owner,
            failure_injector=fail,
        )

    recovered = publish_historical_package(artifact_root=tmp_path, owner=owner)
    assert load_verified_historical_package(recovered).owner == owner


def test_package_corruption_is_detected_without_fallback(tmp_path: Path) -> None:
    owner = raw_owner()
    path = publish_historical_package(artifact_root=tmp_path, owner=owner)
    parquet = next(path.rglob("*.parquet"))

    with parquet.open("ab") as handle:
        handle.write(b"corruption")

    with pytest.raises(ValueError, match="checksum mismatch"):
        load_verified_historical_package(path)


def test_unexpected_file_is_rejected(tmp_path: Path) -> None:
    owner = raw_owner()
    path = publish_historical_package(artifact_root=tmp_path, owner=owner)
    (path / "latest.json").touch()

    with pytest.raises(ValueError, match="exact file set"):
        load_verified_historical_package(path)


def test_package_index_verifies_identity_without_decoding_partitions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = raw_owner()
    path = publish_historical_package(artifact_root=tmp_path, owner=owner)

    monkeypatch.setattr(
        "market_regime_alpha.application.historical_corpus.artifacts._read_partition",
        lambda **_: (_ for _ in ()).throw(AssertionError("partition decoded")),
    )

    index = load_historical_package_index(path)

    assert index.reference == owner.reference
    assert index.coverage == owner.coverage
    assert index.partition_count == len(owner.partitions)
    assert index.physical_hash.startswith("sha256:")


def test_repeated_immutable_partition_scan_reuses_verified_file_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = raw_owner()
    path = publish_historical_package(artifact_root=tmp_path, owner=owner)
    index = load_historical_package_index(path)
    hash_calls = 0

    from market_regime_alpha.application.historical_corpus import artifacts

    artifacts._hash_file_with_signature.cache_clear()
    original = artifacts._hash_file_contents

    def count_hashes(candidate: Path) -> str:
        nonlocal hash_calls
        hash_calls += 1
        return original(candidate)

    monkeypatch.setattr(artifacts, "_hash_file_contents", count_hashes)
    for _ in range(2):
        scan_historical_package(
            package=index,
            partitions=index.partitions,
            timeframes=(Timeframe.DAILY,),
            first_market_date=index.first_market_date,
            last_market_date=index.last_market_date,
            symbols=None,
            max_rows=10,
            batch_size=10,
        )

    assert hash_calls == 1

    parquet = next(path.rglob("*.parquet"))
    with parquet.open("ab") as handle:
        handle.write(b"corruption-after-cached-verification")
    with pytest.raises(ValueError, match="checksum mismatch"):
        scan_historical_package(
            package=index,
            partitions=index.partitions,
            timeframes=(Timeframe.DAILY,),
            first_market_date=index.first_market_date,
            last_market_date=index.last_market_date,
            symbols=None,
            max_rows=10,
            batch_size=10,
        )
    assert hash_calls == 2
