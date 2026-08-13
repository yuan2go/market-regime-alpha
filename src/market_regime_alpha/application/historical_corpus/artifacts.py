"""Crash-atomic columnar packages for Phase E historical data owners."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
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
    HistoricalArtifactKind,
    HistoricalCorpusCoverage,
    HistoricalDataOwner,
    HistoricalDataPartition,
    HistoricalNormalizedBar,
    HistoricalRawRequest,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash, canonical_json
from market_regime_alpha.market_data.contracts import Timeframe, parse_utc_second


HISTORICAL_PACKAGE_ENCODING = "historical-columnar-package/v1"
HISTORICAL_PARQUET_SCHEMA = "historical-columnar-record/v1"
FailureInjector = Callable[[str], None]


@dataclass(frozen=True, slots=True)
class VerifiedHistoricalPackage:
    root: Path
    owner: HistoricalDataOwner
    physical_hash: str
    checksums: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class HistoricalPartitionDescriptor:
    partition_id: ArtifactId
    content_hash: str
    artifact_kind: HistoricalArtifactKind
    timeframe: Timeframe
    first_market_date: date
    last_market_date: date
    symbol_bucket: int
    bucket_count: int
    row_count: int
    symbol_count: int
    relative_path: str
    schema_version: str | None

    @classmethod
    def from_reference_dict(cls, payload: Mapping[str, Any]) -> HistoricalPartitionDescriptor:
        return cls(
            partition_id=ArtifactId(str(payload["partition_id"])),
            content_hash=str(payload["content_hash"]),
            artifact_kind=HistoricalArtifactKind(str(payload["artifact_kind"])),
            timeframe=Timeframe(str(payload["timeframe"])),
            first_market_date=date.fromisoformat(str(payload["first_market_date"])),
            last_market_date=date.fromisoformat(str(payload["last_market_date"])),
            symbol_bucket=int(payload["symbol_bucket"]),
            bucket_count=int(payload["bucket_count"]),
            row_count=int(payload["row_count"]),
            symbol_count=int(payload["symbol_count"]),
            relative_path=str(payload["relative_path"]),
            schema_version=(None if "schema_version" not in payload else str(payload["schema_version"])),
        )

    def __post_init__(self) -> None:
        if self.first_market_date > self.last_market_date:
            raise ValueError("Historical partition descriptor date range is reversed")
        if not 0 <= self.symbol_bucket < self.bucket_count:
            raise ValueError("Historical partition descriptor bucket is invalid")
        if self.row_count <= 0 or self.symbol_count <= 0:
            raise ValueError("Historical partition descriptor counts must be positive")
        if not self.relative_path.endswith(".parquet") or ".." in self.relative_path:
            raise ValueError("Historical partition descriptor path is invalid")

    def reference_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "partition_id": str(self.partition_id),
            "content_hash": self.content_hash,
            "artifact_kind": self.artifact_kind.value,
            "timeframe": self.timeframe.value,
            "first_market_date": self.first_market_date.isoformat(),
            "last_market_date": self.last_market_date.isoformat(),
            "symbol_bucket": self.symbol_bucket,
            "bucket_count": self.bucket_count,
            "row_count": self.row_count,
            "symbol_count": self.symbol_count,
            "relative_path": self.relative_path,
        }
        if self.schema_version is not None:
            result["schema_version"] = self.schema_version
        return result


@dataclass(frozen=True, slots=True)
class HistoricalPackageIndex:
    root: Path
    reference: ValidationArtifactReference
    artifact_kind: HistoricalArtifactKind
    provider_id: str
    normalization_version: str | None
    parent_reference: ValidationArtifactReference | None
    first_market_date: date
    last_market_date: date
    bucket_count: int
    retrieved_at: datetime
    created_at: datetime
    coverage: HistoricalCorpusCoverage
    limitations: tuple[str, ...]
    partitions: tuple[HistoricalPartitionDescriptor, ...]
    manifest: Mapping[str, Any]
    physical_hash: str
    checksums: tuple[tuple[str, str], ...]

    @property
    def partition_count(self) -> int:
        return len(self.partitions)

    @property
    def owner_id(self) -> ArtifactId:
        return self.reference.artifact_id

    @property
    def content_hash(self) -> str:
        return self.reference.content_hash


@dataclass(frozen=True, slots=True)
class HistoricalPartitionScan:
    records: tuple[HistoricalRawRequest | HistoricalNormalizedBar, ...]
    verified_bytes: int
    arrow_batch_count: int
    maximum_batch_row_count: int
    projected_columns: tuple[str, ...]


def publish_historical_package(
    *,
    artifact_root: Path,
    owner: HistoricalDataOwner,
    failure_injector: FailureInjector | None = None,
) -> Path:
    """Validate, hash and atomically publish one immutable owner package."""

    owner.verify_identity()
    family = artifact_root.resolve() / "historical-corpus" / owner.artifact_kind.value.lower()
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
        physical_files = tuple(sorted(item.relative_to(stage).as_posix() for item in stage.rglob("*") if item.is_file()))
        _write_json(
            stage / "SHA256SUMS.json",
            {name: _file_hash(stage / name) for name in physical_files},
        )
        _fsync_tree(stage)
        verified = _load_verified_historical_package(stage, enforce_directory_identity=False)
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


def load_historical_package_index(path: Path) -> HistoricalPackageIndex:
    """Verify immutable package metadata without decoding Parquet records."""

    root = path.resolve()
    if not root.is_dir():
        raise ValueError("Historical package path is not a directory")
    checksums_payload = _read_object(root / "SHA256SUMS.json")
    checksums = {str(name): str(digest) for name, digest in checksums_payload.items()}
    if len(checksums) != len(checksums_payload) or any(
        not isinstance(name, str) or not isinstance(digest, str) for name, digest in checksums_payload.items()
    ):
        raise ValueError("Historical checksum manifest is invalid")
    actual_files = {item.relative_to(root).as_posix() for item in root.rglob("*") if item.is_file()}
    if actual_files != {*checksums, "SHA256SUMS.json"}:
        raise ValueError("Historical package exact file set mismatch")
    for name in ("manifest.json", "encoding.json"):
        expected = checksums.get(name)
        if expected is None or _file_hash(root / name) != expected:
            raise ValueError(f"Historical package checksum mismatch: {name}")
    encoding = _read_object(root / "encoding.json")
    if encoding.get("encoding_version") != HISTORICAL_PACKAGE_ENCODING:
        raise ValueError("unsupported Historical package encoding")
    manifest = _read_object(root / "manifest.json")
    raw_refs = manifest.get("partitions")
    if not isinstance(raw_refs, list) or any(not isinstance(item, Mapping) for item in raw_refs):
        raise ValueError("Historical partition manifest is invalid")
    semantic_payload = {key: value for key, value in manifest.items() if key not in {"owner_id", "content_hash"}}
    content_hash = str(manifest.get("content_hash"))
    owner_id = str(manifest.get("owner_id"))
    if canonical_hash(semantic_payload) != content_hash:
        raise ValueError("Historical data owner hash mismatch")
    if owner_id != f"historical-data-owner-{content_hash[7:31]}":
        raise ValueError("Historical data owner identity mismatch")
    if (
        encoding.get("logical_owner_id") != owner_id
        or encoding.get("logical_owner_hash") != content_hash
        or encoding.get("parquet_schema") != HISTORICAL_PARQUET_SCHEMA
    ):
        raise ValueError("Historical package logical identity mismatch")
    if root.name != owner_id:
        raise ValueError("Historical package directory identity mismatch")
    partitions = tuple(HistoricalPartitionDescriptor.from_reference_dict(item) for item in raw_refs)
    if not partitions:
        raise ValueError("Historical package index requires partitions")
    if len({str(item.partition_id) for item in partitions}) != len(partitions):
        raise ValueError("Historical package partition identities are not unique")
    artifact_kind = HistoricalArtifactKind(str(manifest["artifact_kind"]))
    bucket_count = int(manifest["bucket_count"])
    if any(item.artifact_kind is not artifact_kind or item.bucket_count != bucket_count for item in partitions):
        raise ValueError("Historical package partition contract mismatch")
    expected_files = {
        "manifest.json",
        "encoding.json",
        *(item.relative_path for item in partitions),
    }
    if set(checksums) != expected_files:
        raise ValueError("Historical checksum coverage mismatch")
    parent_payload = manifest.get("parent_reference")
    parent_reference = None if parent_payload is None else ValidationArtifactReference.from_canonical_dict(parent_payload)
    ordered_checksums = tuple(sorted(checksums.items()))
    return HistoricalPackageIndex(
        root=root,
        reference=ValidationArtifactReference(artifact_kind.value, ArtifactId(owner_id), content_hash),
        artifact_kind=artifact_kind,
        provider_id=str(manifest["provider_id"]),
        normalization_version=(None if manifest.get("normalization_version") is None else str(manifest["normalization_version"])),
        parent_reference=parent_reference,
        first_market_date=date.fromisoformat(str(manifest["first_market_date"])),
        last_market_date=date.fromisoformat(str(manifest["last_market_date"])),
        bucket_count=bucket_count,
        retrieved_at=parse_utc_second("retrieved_at", manifest["retrieved_at"]),
        created_at=parse_utc_second("created_at", manifest["created_at"]),
        coverage=HistoricalCorpusCoverage.from_canonical_dict(manifest["coverage"]),
        limitations=tuple(str(item) for item in manifest["limitations"]),
        partitions=partitions,
        manifest=manifest,
        physical_hash=canonical_hash(dict(ordered_checksums)),
        checksums=ordered_checksums,
    )


def scan_historical_package(
    *,
    package: HistoricalPackageIndex,
    partitions: tuple[HistoricalPartitionDescriptor, ...],
    timeframes: tuple[Timeframe, ...],
    first_market_date: date,
    last_market_date: date,
    symbols: tuple[str, ...] | None,
    max_rows: int,
    batch_size: int,
) -> HistoricalPartitionScan:
    """Checksum and scan selected immutable partitions in bounded Arrow batches."""

    import pyarrow.dataset as ds

    checksum_by_path = dict(package.checksums)
    descriptor_by_id = {str(item.partition_id): item for item in partitions}
    paths: list[Path] = []
    verified_bytes = 0
    for item in partitions:
        candidate = (package.root / item.relative_path).resolve()
        if package.root not in candidate.parents:
            raise ValueError("Historical partition path escapes package")
        expected = checksum_by_path.get(item.relative_path)
        if expected is None or _file_hash(candidate) != expected:
            raise ValueError(f"Historical package checksum mismatch: {item.relative_path}")
        paths.append(candidate)
        verified_bytes += candidate.stat().st_size
    projected_columns = tuple(
        sorted(
            {
                "logical_record_schema",
                "market_date",
                "partition_hash",
                "partition_id",
                "record_json",
                "symbol",
                "timeframe",
            }
        )
    )
    if not paths:
        return HistoricalPartitionScan((), 0, 0, 0, projected_columns)
    expression = (
        ds.field("timeframe").isin([item.value for item in timeframes])
        & (ds.field("market_date") >= first_market_date.isoformat())
        & (ds.field("market_date") <= last_market_date.isoformat())
    )
    if symbols is not None:
        expression = expression & ds.field("symbol").isin(list(symbols))
    scanner = ds.dataset(paths, format="parquet").scanner(
        columns=list(projected_columns),
        filter=expression,
        batch_size=batch_size,
        use_threads=True,
    )
    records: list[HistoricalRawRequest | HistoricalNormalizedBar] = []
    batch_count = 0
    maximum_batch = 0
    for batch in scanner.to_batches():
        batch_count += 1
        maximum_batch = max(maximum_batch, batch.num_rows)
        if len(records) + batch.num_rows > max_rows:
            raise ValueError("Historical selective read exceeds max_rows; narrow the query")
        columns = {name: batch.column(batch.schema.get_field_index(name)).to_pylist() for name in projected_columns}
        for row_index in range(batch.num_rows):
            row = {name: values[row_index] for name, values in columns.items()}
            descriptor = descriptor_by_id.get(str(row["partition_id"]))
            if descriptor is None or row["partition_hash"] != descriptor.content_hash:
                raise ValueError("Historical Parquet partition identity mismatch")
            records.append(_decode_record(row))
    records.sort(key=_record_sort_key)
    record_ids = tuple(str(_record_id(item)) for item in records)
    if len(set(record_ids)) != len(record_ids):
        raise ValueError("Historical selective read returned duplicate records")
    return HistoricalPartitionScan(
        records=tuple(records),
        verified_bytes=verified_bytes,
        arrow_batch_count=batch_count,
        maximum_batch_row_count=maximum_batch,
        projected_columns=projected_columns,
    )


def _load_verified_historical_package(
    path: Path,
    *,
    enforce_directory_identity: bool,
) -> VerifiedHistoricalPackage:
    root = path.resolve()
    if not root.is_dir():
        raise ValueError("Historical package path is not a directory")
    checksums_payload = _read_object(root / "SHA256SUMS.json")
    if any(not isinstance(name, str) or not isinstance(digest, str) for name, digest in checksums_payload.items()):
        raise ValueError("Historical checksum manifest is invalid")
    checksums = {str(name): str(digest) for name, digest in checksums_payload.items()}
    actual_files = {item.relative_to(root).as_posix() for item in root.rglob("*") if item.is_file()}
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
    partitions = tuple(_read_partition(root=root, reference=item) for item in raw_refs)
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
        records.append(_decode_record(row))
    partition = HistoricalDataPartition.from_reference_dict(
        reference,
        records=tuple(records),
    )
    if any(row["partition_id"] != str(partition.partition_id) or row["partition_hash"] != partition.content_hash for row in rows):
        raise ValueError("Historical Parquet partition identity mismatch")
    return partition


def _record_id(item: HistoricalRawRequest | HistoricalNormalizedBar) -> ArtifactId:
    return item.request_id if isinstance(item, HistoricalRawRequest) else item.bar_id


def _record_date(item: HistoricalRawRequest | HistoricalNormalizedBar) -> date:
    return item.start_date if isinstance(item, HistoricalRawRequest) else item.market_date


def _event_start(item: HistoricalRawRequest | HistoricalNormalizedBar) -> str | None:
    return None if isinstance(item, HistoricalRawRequest) else item.event_start.isoformat()


def _decode_record(row: Mapping[str, Any]) -> HistoricalRawRequest | HistoricalNormalizedBar:
    if "physical_schema" in row and row["physical_schema"] != HISTORICAL_PARQUET_SCHEMA:
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
    expected_projection = {
        "record_id": str(_record_id(record)),
        "record_hash": record.content_hash,
        "symbol": record.symbol,
        "timeframe": record.timeframe.value,
        "market_date": _record_date(record).isoformat(),
        "retrieved_at": record.retrieved_at.isoformat(),
        "event_start": _event_start(record),
    }
    if any(name in row and row[name] != expected for name, expected in expected_projection.items()):
        raise ValueError("Historical Parquet row projection mismatch")
    return record


def _record_sort_key(
    item: HistoricalRawRequest | HistoricalNormalizedBar,
) -> tuple[object, ...]:
    if isinstance(item, HistoricalRawRequest):
        return (item.start_date, item.symbol, str(item.request_id))
    return (item.market_date, item.symbol, item.event_start, str(item.bar_id))


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
    "HistoricalPackageIndex",
    "HistoricalPartitionDescriptor",
    "HistoricalPartitionScan",
    "VerifiedHistoricalPackage",
    "load_historical_package_index",
    "load_verified_historical_package",
    "publish_historical_package",
    "scan_historical_package",
]
