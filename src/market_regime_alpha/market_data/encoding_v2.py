"""Columnar Market Data Package Encoding V2.

Physical Parquet checksums are deliberately separate from the canonical logical
Dataset and Bar hashes.  JSON V1 remains readable in :mod:`artifacts`.
"""

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
from market_regime_alpha.market_data.artifacts import VerifiedMarketDataDataset
from market_regime_alpha.market_data.contracts import CanonicalMarketBar, Timeframe
from market_regime_alpha.market_data.dataset import (
    MarketDataDatasetArtifact,
    MarketDataPartition,
)


MARKET_DATA_PACKAGE_ENCODING_V2 = "market-data-package-encoding-v2"
MARKET_DATA_PARQUET_SCHEMA_V2 = "canonical-market-bar-parquet-v2"
FailureInjector = Callable[[str], None]


@dataclass(frozen=True, slots=True)
class MarketDataSelectionV2:
    root: Path
    dataset_id: str
    dataset_hash: str
    bars: tuple[CanonicalMarketBar, ...]
    selected_partition_count: int
    physical_checksums_hash: str


def publish_market_data_dataset_v2(
    *,
    root: Path,
    artifact: MarketDataDatasetArtifact,
    failure_injector: FailureInjector | None = None,
) -> Path:
    import pyarrow as pa
    import pyarrow.parquet as pq

    artifact.verify_identity()
    root.mkdir(parents=True, exist_ok=True)
    final = root / str(artifact.dataset_id)
    if final.exists():
        existing = load_verified_market_data_dataset_v2(final)
        if existing.artifact.to_canonical_dict() != artifact.to_canonical_dict():
            raise FileExistsError(f"conflicting Market Data Encoding V2 exists: {final}")
        return final
    stage = Path(tempfile.mkdtemp(prefix=f".{final.name}.", dir=root))
    installed = False
    try:
        _write_json(stage / "artifact.json", artifact.to_canonical_dict())
        _write_json(
            stage / "adjustment-policy.json",
            artifact.adjustment_policy.to_canonical_dict(),
        )
        entries: list[dict[str, Any]] = []
        for partition in artifact.partitions:
            relative_path = (
                f"partitions/{partition.symbol}/{partition.timeframe.value}/"
                f"{partition.first_market_date.isoformat()}_"
                f"{partition.last_market_date.isoformat()}.parquet"
            )
            target = stage / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            table = pa.table(
                {
                    "schema_version": [MARKET_DATA_PARQUET_SCHEMA_V2]
                    * partition.bar_count,
                    "symbol": [partition.symbol] * partition.bar_count,
                    "timeframe": [partition.timeframe.value] * partition.bar_count,
                    "market_date": [
                        item.market_date.isoformat() for item in partition.bars
                    ],
                    "event_start": [
                        item.event_start.isoformat() for item in partition.bars
                    ],
                    "bar_id": [str(item.bar_id) for item in partition.bars],
                    "bar_hash": [item.content_hash for item in partition.bars],
                    "bar_json": [
                        canonical_json(item.to_canonical_dict())
                        for item in partition.bars
                    ],
                }
            )
            pq.write_table(
                table,
                target,
                compression="zstd",
                compression_level=9,
                use_dictionary=True,
                write_statistics=True,
            )
            entries.append(
                {
                    **partition.reference_dict(),
                    "physical_path": relative_path,
                    "physical_format": "PARQUET",
                    "physical_schema": MARKET_DATA_PARQUET_SCHEMA_V2,
                    "physical_checksum": _file_hash(target),
                }
            )
        _write_json(
            stage / "encoding.json",
            {
                "encoding_version": MARKET_DATA_PACKAGE_ENCODING_V2,
                "logical_dataset_id": str(artifact.dataset_id),
                "logical_dataset_hash": artifact.content_hash,
                "logical_hash_basis": "CANONICAL_LOGICAL_PAYLOAD",
                "physical_hash_basis": "FILE_SHA256",
            },
        )
        _write_json(stage / "partition-index.json", {"partitions": entries})
        physical_files = {
            item.relative_to(stage).as_posix()
            for item in stage.rglob("*")
            if item.is_file()
        }
        _write_json(
            stage / "SHA256SUMS.json",
            {name: _file_hash(stage / name) for name in sorted(physical_files)},
        )
        _fsync_tree(stage)
        _load_verified_market_data_dataset_v2(
            stage, enforce_directory_identity=False
        )
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


def load_verified_market_data_dataset_v2(path: Path) -> VerifiedMarketDataDataset:
    return _load_verified_market_data_dataset_v2(
        path, enforce_directory_identity=True
    )


def _load_verified_market_data_dataset_v2(
    path: Path, *, enforce_directory_identity: bool
) -> VerifiedMarketDataDataset:
    root, checksums, artifact_payload, policy, entries = _read_package_index(path)
    for name, expected in checksums.items():
        if _file_hash(root / name) != expected:
            raise ValueError(f"Market Data Encoding V2 checksum mismatch: {name}")
    partitions = tuple(_read_partition(root=root, entry=item) for item in entries)
    artifact = MarketDataDatasetArtifact.from_canonical_dict(
        artifact_payload,
        partitions=partitions,
        adjustment_policy=policy,
    )
    encoding = _read_object(root / "encoding.json")
    if (
        encoding.get("logical_dataset_id") != str(artifact.dataset_id)
        or encoding.get("logical_dataset_hash") != artifact.content_hash
    ):
        raise ValueError("Market Data Encoding V2 logical identity mismatch")
    if enforce_directory_identity and root.name != str(artifact.dataset_id):
        raise ValueError("Market Data Encoding V2 directory identity mismatch")
    return VerifiedMarketDataDataset(
        root=root,
        artifact=artifact,
        bars=tuple(artifact.iter_bars()),
        checksums_hash=canonical_hash(dict(sorted(checksums.items()))),
    )


def read_market_data_selection_v2(
    path: Path,
    *,
    symbols: tuple[str, ...] | None = None,
    timeframes: tuple[Timeframe, ...] | None = None,
) -> MarketDataSelectionV2:
    """Read only matching Parquet partitions without decoding the full Dataset."""

    root, checksums, artifact_payload, _policy, entries = _read_package_index(path)
    selected_symbols = set(symbols) if symbols is not None else None
    selected_timeframes = set(timeframes) if timeframes is not None else None
    selected_entries = tuple(
        item
        for item in entries
        if (
            selected_symbols is None or str(item["symbol"]) in selected_symbols
        )
        and (
            selected_timeframes is None
            or Timeframe(str(item["timeframe"])) in selected_timeframes
        )
    )
    bars: list[CanonicalMarketBar] = []
    verified_names = {
        "artifact.json",
        "adjustment-policy.json",
        "encoding.json",
        "partition-index.json",
    }
    verified_names.update(str(item["physical_path"]) for item in selected_entries)
    for name in verified_names:
        expected = checksums.get(name)
        if expected is None or _file_hash(root / name) != expected:
            raise ValueError(f"Market Data Encoding V2 checksum mismatch: {name}")
    for entry in selected_entries:
        bars.extend(_read_partition(root=root, entry=entry).bars)
    encoding = _read_object(root / "encoding.json")
    if (
        encoding.get("logical_dataset_id") != artifact_payload.get("dataset_id")
        or encoding.get("logical_dataset_hash") != artifact_payload.get("content_hash")
    ):
        raise ValueError("Market Data Encoding V2 logical identity mismatch")
    return MarketDataSelectionV2(
        root=root,
        dataset_id=str(artifact_payload["dataset_id"]),
        dataset_hash=str(artifact_payload["content_hash"]),
        bars=tuple(bars),
        selected_partition_count=len(selected_entries),
        physical_checksums_hash=canonical_hash(
            {name: checksums[name] for name in sorted(verified_names)}
        ),
    )


def _read_package_index(
    path: Path,
) -> tuple[
    Path,
    dict[str, str],
    dict[str, Any],
    PriceAdjustmentPolicy,
    tuple[dict[str, Any], ...],
]:
    root = path.resolve()
    if not root.is_dir():
        raise ValueError("Market Data Encoding V2 path is not a directory")
    actual = {
        item.relative_to(root).as_posix()
        for item in root.rglob("*")
        if item.is_file()
    }
    checksums_raw = _read_object(root / "SHA256SUMS.json")
    if any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in checksums_raw.items()
    ):
        raise ValueError("Market Data Encoding V2 checksum index mismatch")
    checksums = {str(key): str(value) for key, value in checksums_raw.items()}
    if actual != set(checksums) | {"SHA256SUMS.json"}:
        raise ValueError("Market Data Encoding V2 exact file set mismatch")
    encoding = _read_object(root / "encoding.json")
    if encoding.get("encoding_version") != MARKET_DATA_PACKAGE_ENCODING_V2:
        raise ValueError("unsupported Market Data package encoding")
    index = _read_object(root / "partition-index.json")
    raw_entries = index.get("partitions")
    if not isinstance(raw_entries, list) or any(
        not isinstance(item, dict) for item in raw_entries
    ):
        raise ValueError("Market Data Encoding V2 partition index mismatch")
    entries = tuple(dict(item) for item in raw_entries)
    if tuple(
        (str(item.get("symbol")), str(item.get("timeframe"))) for item in entries
    ) != tuple(
        sorted(
            set(
                (str(item.get("symbol")), str(item.get("timeframe")))
                for item in entries
            )
        )
    ):
        raise ValueError("Market Data Encoding V2 partition scope mismatch")
    expected_physical = {str(item.get("physical_path")) for item in entries}
    if not expected_physical.issubset(checksums):
        raise ValueError("Market Data Encoding V2 partition file missing")
    return (
        root,
        checksums,
        _read_object(root / "artifact.json"),
        PriceAdjustmentPolicy.from_canonical_dict(
            _read_object(root / "adjustment-policy.json")
        ),
        entries,
    )


def _read_partition(*, root: Path, entry: Mapping[str, Any]) -> MarketDataPartition:
    import pyarrow.parquet as pq

    physical_path = str(entry.get("physical_path"))
    table = pq.read_table(root / physical_path, columns=["bar_json"])
    bars = tuple(
        CanonicalMarketBar.from_canonical_dict(_json_object(value))
        for value in table.column("bar_json").to_pylist()
    )
    partition = MarketDataPartition.create(
        symbol=str(entry["symbol"]),
        timeframe=Timeframe(str(entry["timeframe"])),
        bars=bars,
    )
    expected_projection = {
        key: entry[key]
        for key in (
            "partition_id",
            "content_hash",
            "symbol",
            "timeframe",
            "first_market_date",
            "last_market_date",
            "bar_count",
            "relative_path",
        )
    }
    if partition.reference_dict() != expected_projection:
        raise ValueError("Market Data Encoding V2 partition projection mismatch")
    return partition


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (canonical_json(payload) + "\n").encode()
    with path.open("xb") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())


def _read_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid Market Data Encoding V2 JSON: {path.name}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Market Data Encoding V2 JSON must be an object")
    return payload


def _json_object(value: object) -> dict[str, Any]:
    if not isinstance(value, str):
        raise ValueError("Market Data Encoding V2 bar payload is invalid")
    payload = json.loads(value)
    if not isinstance(payload, dict):
        raise ValueError("Market Data Encoding V2 bar payload is invalid")
    return payload


def _file_hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_tree(root: Path) -> None:
    for directory in sorted(
        (item for item in root.rglob("*") if item.is_dir()),
        key=lambda item: len(item.parts),
        reverse=True,
    ):
        _fsync_directory(directory)
    _fsync_directory(root)


__all__ = [
    "MARKET_DATA_PACKAGE_ENCODING_V2",
    "MarketDataSelectionV2",
    "load_verified_market_data_dataset_v2",
    "publish_market_data_dataset_v2",
    "read_market_data_selection_v2",
]
