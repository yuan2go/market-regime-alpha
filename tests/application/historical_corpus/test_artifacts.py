from __future__ import annotations

from pathlib import Path

import pytest

from market_regime_alpha.application.historical_corpus.artifacts import (
    load_verified_historical_package,
    publish_historical_package,
)
from market_regime_alpha.application.historical_corpus.contracts import (
    HISTORICAL_EVIDENCE_LIMITATIONS,
)
from tests.application.historical_corpus.support import raw_owner


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
    assert "year=2023" in parquet[0].as_posix()
    assert "600000.SH" not in parquet[0].as_posix()
    assert replayed.physical_hash.startswith("sha256:")


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
