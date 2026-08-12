"""Crash-atomic columnar packages for Phase E historical data owners."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Callable, Mapping

from market_regime_alpha.application.historical_corpus.contracts import (
    HISTORICAL_NORMALIZED_BAR_SCHEMA,
    HISTORICAL_RAW_REQUEST_SCHEMA,
    HistoricalDataOwner,
    HistoricalDataPartition,
    HistoricalNormalizedBar,
    HistoricalRawRequest,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash, canonical_json


HISTORICAL_PACKAGE_ENCODING = "historical-columnar-package/v1"
HISTORICAL_PARQUET_SCHEMA = "historical-columnar-record/v1"
FailureInjector = Callable[[str], None]


@dataclass(frozen=True, slots=True)
class VerifiedHistoricalPackage:
    root: Path
    owner: HistoricalDataOwner
    physical_hash: str
    checksums: tuple[tuple[str, str], ...]


def publish_historical_package(
    *,
    artifact_root: Path,
    owner: HistoricalDataOwner,
    failure_injector: FailureInjector | None = None,
) -> Path:
    """Validate, hash and atomically publish one immutable owner package."""

    owner.verify_identity()
    family = (
        artifact_root.resolve()
        / "historical-corpus"
        / owner.artifact_kind.value.lower()
    )
    family.mkdir(parents=True, exist_ok=True)
    final = family / str(owner.owner_id)
    if final.exists():
        existing = load_verified_historical_package(final)
        if existing.owner != owner:
            raise FileExistsError("conflicting Historical package identity exists")
        return final
    stage = Path(tempfile.mkdtemp(prefix=f".{owner.owner_id}.", dir=family))
    installed = False
    try:
        _write_json(stage / "manifest.json", owner.to_canonical_dict())
        _write_json(
            stage / "encoding.json",
            {
                "encoding_version": HISTORICAL_PACKAGE_ENCODING,
                "logical_owner_id": str(owner.owner_id),
                "logical_owner_hash": owner.content_hash,
                "logical_hash_basis": "CANONICAL_OWNER_AND_PARTITION_PAYLOADS",
                "physical_hash_basis": "FILE_SHA256",
                "parquet_schema": HISTORICAL_PARQUET_SCHEMA,
            },
        )
        for partition in owner.partitions:
            _write_partition(stage / partition.relative_path, partition)
        physical_files = tuple(
            sorted(
                item.relative_to(stage).as_posix()
                for item in stage.rglob("*")
                if item.is_file()
            )
        )
        _write_json(
            stage / "SHA256SUMS.json",
            {name: _file_hash(stage / name) for name in physical_files},
        )
        _fsync_tree(stage)
        verified = _load_verified_historical_package(
            stage, enforce_directory_identity=False
        )
        if verified.owner != owner:
            raise ValueError("staged Historical package semantic mismatch")
        if failure_injector is not None:
            failure_injector("AFTER_STAGING_VALIDATED")
        os.replace(stage, final)
        installed = True
        _fsync_directory(family)
        if failure_injector is not None:
            failure_injector("AFTER_ATOMIC_PUBLISH")
        return final
    finally:
        if not installed and stage.exists():
            shutil.rmtree(stage)


def load_verified_historical_package(path: Path) -> VerifiedHistoricalPackage:
    return _load_verified_historical_package(path, enforce_directory_identity=True)


def _load_verified_historical_package(
    path: Path,
    *,
    enforce_directory_identity: bool,
) -> VerifiedHistoricalPackage:
    root = path.resolve()
    if not root.is_dir():
        raise ValueError("Historical package path is not a directory")
    checksums_payload = _read_object(root / "SHA256SUMS.json")
    if any(
        not isinstance(name, str) or not isinstance(digest, str)
        for name, digest in checksums_payload.items()
    ):
        raise ValueError("Historical checksum manifest is invalid")
    checksums = {str(name): str(digest) for name, digest in checksums_payload.items()}
    actual_files = {
        item.relative_to(root).as_posix()
        for item in root.rglob("*")
        if item.is_file()
    }
    if actual_files != {*checksums, "SHA256SUMS.json"}:
        raise ValueError("Historical package exact file set mismatch")
    for name, digest in checksums.items():
        if _file_hash(root / name) != digest:
            raise ValueError(f"Historical package checksum mismatch: {name}")
    encoding = _read_object(root / "encoding.json")
    if encoding.get("encoding_version") != HISTORICAL_PACKAGE_ENCODING:
        raise ValueError("unsupported Historical package encoding")
    manifest = _read_object(root / "manifest.json")
    raw_refs = manifest.get("partitions")
    if not isinstance(raw_refs, list) or any(not isinstance(item, Mapping) for item in raw_refs):
        raise ValueError("Historical partition manifest is invalid")
    partitions = tuple(
        _read_partition(root=root, reference=item) for item in raw_refs
    )
    owner = HistoricalDataOwner.from_canonical_dict(manifest, partitions=partitions)
    if (
        encoding.get("logical_owner_id") != str(owner.owner_id)
        or encoding.get("logical_owner_hash") != owner.content_hash
        or encoding.get("parquet_schema") != HISTORICAL_PARQUET_SCHEMA
    ):
        raise ValueError("Historical package logical identity mismatch")
    if enforce_directory_identity and root.name != str(owner.owner_id):
        raise ValueError("Historical package directory identity mismatch")
    expected_files = {
        "manifest.json",
        "encoding.json",
        *(item.relative_path for item in owner.partitions),
    }
    if set(checksums) != expected_files:
        raise ValueError("Historical checksum coverage mismatch")
    ordered = tuple(sorted(checksums.items()))
    return VerifiedHistoricalPackage(
        root=root,
        owner=owner,
        physical_hash=canonical_hash(dict(ordered)),
        checksums=ordered,
    )


def _write_partition(path: Path, partition: HistoricalDataPartition) -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq

    path.parent.mkdir(parents=True, exist_ok=True)
    records = partition.records
    table = pa.table(
        {
            "physical_schema": [HISTORICAL_PARQUET_SCHEMA] * len(records),
            "logical_record_schema": [item.schema_version for item in records],
            "partition_id": [str(partition.partition_id)] * len(records),
            "partition_hash": [partition.content_hash] * len(records),
            "record_id": [str(_record_id(item)) for item in records],
            "record_hash": [item.content_hash for item in records],
            "symbol": [item.symbol for item in records],
            "timeframe": [item.timeframe.value for item in records],
            "market_date": [_record_date(item).isoformat() for item in records],
            "event_start": [_event_start(item) for item in records],
            "retrieved_at": [item.retrieved_at.isoformat() for item in records],
            "record_json": [canonical_json(item.to_canonical_dict()) for item in records],
        }
    )
    pq.write_table(
        table,
        path,
        compression="zstd",
        compression_level=9,
        use_dictionary=True,
        write_statistics=True,
        row_group_size=65_536,
    )


def _read_partition(
    *,
    root: Path,
    reference: Mapping[str, Any],
) -> HistoricalDataPartition:
    import pyarrow.parquet as pq

    relative = str(reference.get("relative_path"))
    candidate = (root / relative).resolve()
    if root not in candidate.parents:
        raise ValueError("Historical partition path escapes package")
    table = pq.read_table(candidate)
    expected_columns = {
        "physical_schema",
        "logical_record_schema",
        "partition_id",
        "partition_hash",
        "record_id",
        "record_hash",
        "symbol",
        "timeframe",
        "market_date",
        "event_start",
        "retrieved_at",
        "record_json",
    }
    if set(table.column_names) != expected_columns:
        raise ValueError("Historical Parquet columns mismatch")
    rows = table.to_pylist()
    if not rows:
        raise ValueError("Historical Parquet partition is empty")
    records = []
    for row in rows:
        if row["physical_schema"] != HISTORICAL_PARQUET_SCHEMA:
            raise ValueError("Historical Parquet row schema mismatch")
        payload = json.loads(str(row["record_json"]))
        schema = str(row["logical_record_schema"])
        record: HistoricalRawRequest | HistoricalNormalizedBar
        if schema == HISTORICAL_RAW_REQUEST_SCHEMA:
            record = HistoricalRawRequest.from_canonical_dict(payload)
        elif schema == HISTORICAL_NORMALIZED_BAR_SCHEMA:
            record = HistoricalNormalizedBar.from_canonical_dict(payload)
        else:
            raise ValueError("unsupported Historical logical record schema")
        if (
            str(_record_id(record)) != row["record_id"]
            or record.content_hash != row["record_hash"]
            or record.symbol != row["symbol"]
            or record.timeframe.value != row["timeframe"]
            or _record_date(record).isoformat() != row["market_date"]
            or record.retrieved_at.isoformat() != row["retrieved_at"]
            or _event_start(record) != row["event_start"]
        ):
            raise ValueError("Historical Parquet row projection mismatch")
        records.append(record)
    partition = HistoricalDataPartition.from_reference_dict(
        reference,
        records=tuple(records),
    )
    if any(
        row["partition_id"] != str(partition.partition_id)
        or row["partition_hash"] != partition.content_hash
        for row in rows
    ):
        raise ValueError("Historical Parquet partition identity mismatch")
    return partition


def _record_id(item: HistoricalRawRequest | HistoricalNormalizedBar) -> ArtifactId:
    return item.request_id if isinstance(item, HistoricalRawRequest) else item.bar_id


def _record_date(item: HistoricalRawRequest | HistoricalNormalizedBar) -> date:
    return item.start_date if isinstance(item, HistoricalRawRequest) else item.market_date


def _event_start(item: HistoricalRawRequest | HistoricalNormalizedBar) -> str | None:
    return None if isinstance(item, HistoricalRawRequest) else item.event_start.isoformat()


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(canonical_json(payload))
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _read_object(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Historical package JSON object required: {path.name}")
    return payload


def _file_hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _fsync_tree(root: Path) -> None:
    directories = sorted(
        (item for item in root.rglob("*") if item.is_dir()),
        key=lambda item: len(item.parts),
        reverse=True,
    )
    for directory in (*directories, root):
        _fsync_directory(directory)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


__all__ = [
    "HISTORICAL_PACKAGE_ENCODING",
    "VerifiedHistoricalPackage",
    "load_verified_historical_package",
    "publish_historical_package",
]
