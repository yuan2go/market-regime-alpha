"""Crash-atomic publisher and strict Reader for Market Data Dataset packages."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Callable, Mapping

from market_regime_alpha.evidence.canonical import canonical_hash, canonical_json
from market_regime_alpha.market_data.adjustment import PriceAdjustmentPolicy
from market_regime_alpha.market_data.contracts import CanonicalMarketBar, Timeframe
from market_regime_alpha.market_data.dataset import (
    MarketDataDatasetArtifact,
    MarketDataPartition,
)


FailureInjector = Callable[[str], None]


@dataclass(frozen=True, slots=True)
class VerifiedMarketDataDataset:
    root: Path
    artifact: MarketDataDatasetArtifact
    bars: tuple[CanonicalMarketBar, ...]
    checksums_hash: str

    def bars_for(
        self,
        *,
        symbol: str,
        timeframe: Timeframe,
    ) -> tuple[CanonicalMarketBar, ...]:
        return tuple(
            item
            for item in self.bars
            if item.symbol == symbol and item.timeframe is timeframe
        )


def publish_market_data_dataset(
    *,
    root: Path,
    artifact: MarketDataDatasetArtifact,
    failure_injector: FailureInjector | None = None,
    encoding_version: str = "market-data-package-encoding-v2",
) -> Path:
    if encoding_version == "market-data-package-encoding-v2":
        from market_regime_alpha.market_data.encoding_v2 import (
            publish_market_data_dataset_v2,
        )

        return publish_market_data_dataset_v2(
            root=root,
            artifact=artifact,
            failure_injector=failure_injector,
        )
    if encoding_version != "market-data-package-json-v1":
        raise ValueError("unsupported Market Data physical encoding")
    return _publish_market_data_dataset_json_v1(
        root=root,
        artifact=artifact,
        failure_injector=failure_injector,
    )


def _publish_market_data_dataset_json_v1(
    *,
    root: Path,
    artifact: MarketDataDatasetArtifact,
    failure_injector: FailureInjector | None = None,
) -> Path:
    artifact.verify_identity()
    root.mkdir(parents=True, exist_ok=True)
    final = root / str(artifact.dataset_id)
    if final.exists():
        existing = load_verified_market_data_dataset(final)
        if existing.artifact.to_canonical_dict() != artifact.to_canonical_dict():
            raise FileExistsError(f"conflicting Market Data Dataset exists: {final}")
        return final
    stage = Path(tempfile.mkdtemp(prefix=f".{final.name}.", dir=root))
    installed = False
    try:
        _write_json(stage / "artifact.json", artifact.to_canonical_dict())
        _write_json(
            stage / "adjustment-policy.json",
            artifact.adjustment_policy.to_canonical_dict(),
        )
        for partition in artifact.partitions:
            _write_json(stage / partition.relative_path, partition.to_canonical_dict())
        expected_files = {
            "artifact.json",
            "adjustment-policy.json",
            *(item.relative_path for item in artifact.partitions),
        }
        _write_json(
            stage / "SHA256SUMS.json",
            {name: _file_hash(stage / name) for name in sorted(expected_files)},
        )
        _fsync_tree_directories(stage)
        _load_verified_market_data_dataset(stage, enforce_directory_identity=False)
        if failure_injector is not None:
            failure_injector("AFTER_STAGING_VALIDATED")
        os.replace(stage, final)
        installed = True
        _fsync_directory(root)
        if failure_injector is not None:
            failure_injector("AFTER_ATOMIC_INSTALL")
        return final
    finally:
        if not installed and stage.exists():
            shutil.rmtree(stage)


def load_verified_market_data_dataset(
    path: Path,
    *,
    symbols: tuple[str, ...] | None = None,
    timeframes: tuple[Timeframe, ...] | None = None,
) -> VerifiedMarketDataDataset:
    if (path / "encoding.json").is_file():
        from market_regime_alpha.market_data.encoding_v2 import (
            load_verified_market_data_dataset_v2,
        )

        verified = load_verified_market_data_dataset_v2(path)
    else:
        verified = _load_verified_market_data_dataset(
            path, enforce_directory_identity=True
        )
    selected_symbols = set(symbols) if symbols is not None else None
    selected_timeframes = set(timeframes) if timeframes is not None else None
    selected = tuple(
        item
        for item in verified.bars
        if (selected_symbols is None or item.symbol in selected_symbols)
        and (selected_timeframes is None or item.timeframe in selected_timeframes)
    )
    return VerifiedMarketDataDataset(
        root=verified.root,
        artifact=verified.artifact,
        bars=selected,
        checksums_hash=verified.checksums_hash,
    )


def replay_market_data_dataset(path: Path) -> VerifiedMarketDataDataset:
    verified = load_verified_market_data_dataset(path)
    original = verified.artifact
    replayed = MarketDataDatasetArtifact.create(
        decision_time=original.decision_time,
        created_at=original.created_at,
        bars=tuple(original.iter_bars()),
        expected_symbols=original.coverage.expected_symbols,
        expected_timeframes=original.coverage.expected_timeframes,
        adjustment_policy=original.adjustment_policy,
        source_manifest_references=original.source_manifest_references,
        data_eligibility=original.data_eligibility,
        formal_pit_status=original.formal_pit_status,
        limitations=original.limitations,
    )
    if replayed.to_canonical_dict() != original.to_canonical_dict():
        raise ValueError("Market Data Dataset replay differs from stored Artifact")
    return verified


def migrate_market_data_package_v1_to_v2(
    *, source_path: Path, target_root: Path
) -> Path:
    """Re-encode one verified JSON V1 package without changing logical identity."""

    if (source_path / "encoding.json").exists():
        raise ValueError("Market Data migration source must use JSON V1 encoding")
    verified = _load_verified_market_data_dataset(
        source_path, enforce_directory_identity=True
    )
    from market_regime_alpha.market_data.encoding_v2 import (
        publish_market_data_dataset_v2,
    )

    migrated = publish_market_data_dataset_v2(
        root=target_root, artifact=verified.artifact
    )
    reloaded = load_verified_market_data_dataset(migrated)
    if reloaded.artifact.to_canonical_dict() != verified.artifact.to_canonical_dict():
        raise ValueError("Market Data V1 to V2 migration changed logical identity")
    return migrated


def _load_verified_market_data_dataset(
    path: Path,
    *,
    enforce_directory_identity: bool,
) -> VerifiedMarketDataDataset:
    root = path.resolve()
    if not root.is_dir():
        raise ValueError("Market Data Dataset package path is not a directory")
    actual_files = {
        item.relative_to(root).as_posix() for item in root.rglob("*") if item.is_file()
    }
    if "SHA256SUMS.json" not in actual_files:
        raise ValueError("Market Data Dataset exact file set mismatch")
    checksums = _read_object(root / "SHA256SUMS.json")
    if any(not isinstance(key, str) or not isinstance(value, str) for key, value in checksums.items()):
        raise ValueError("Market Data Dataset checksum index mismatch")
    expected_files = set(checksums) | {"SHA256SUMS.json"}
    if actual_files != expected_files:
        raise ValueError("Market Data Dataset exact file set mismatch")
    for name, expected_hash in checksums.items():
        if _file_hash(root / name) != expected_hash:
            raise ValueError(f"Market Data Dataset checksum mismatch: {name}")
    raw_policy = _read_object(root / "adjustment-policy.json")
    policy = PriceAdjustmentPolicy.from_canonical_dict(raw_policy)
    raw_artifact = _read_object(root / "artifact.json")
    raw_refs = raw_artifact.get("partitions")
    if not isinstance(raw_refs, list) or any(
        not isinstance(item, dict) or not isinstance(item.get("relative_path"), str)
        for item in raw_refs
    ):
        raise ValueError("Market Data Dataset partition index mismatch")
    partitions = tuple(
        MarketDataPartition.from_canonical_dict(
            _read_object(root / str(item["relative_path"]))
        )
        for item in raw_refs
    )
    artifact = MarketDataDatasetArtifact.from_canonical_dict(
        raw_artifact,
        partitions=partitions,
        adjustment_policy=policy,
    )
    expected_index = {
        "artifact.json",
        "adjustment-policy.json",
        *(item.relative_path for item in artifact.partitions),
    }
    if set(checksums) != expected_index:
        raise ValueError("Market Data Dataset checksum index mismatch")
    if enforce_directory_identity and root.name != str(artifact.dataset_id):
        raise ValueError("Market Data Dataset directory identity mismatch")
    bars = tuple(artifact.iter_bars())
    return VerifiedMarketDataDataset(
        root=root,
        artifact=artifact,
        bars=bars,
        checksums_hash=canonical_hash(dict(sorted(checksums.items()))),
    )


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (canonical_json(payload) + "\n").encode("utf-8")
    with path.open("xb") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())


def _read_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid Market Data Dataset JSON: {path.name}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Market Data Dataset JSON must be an object: {path.name}")
    return payload


def _file_hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_tree_directories(root: Path) -> None:
    directories = sorted(
        (item for item in root.rglob("*") if item.is_dir()),
        key=lambda item: len(item.parts),
        reverse=True,
    )
    for directory in directories:
        _fsync_directory(directory)
    _fsync_directory(root)
