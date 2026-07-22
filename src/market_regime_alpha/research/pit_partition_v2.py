"""Immutable Validation partition specification, seal, and first-open receipt."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from hashlib import sha256
import json
from pathlib import Path
import shutil
from typing import Any, Iterable

from market_regime_alpha.research.prr_artifact_schemas import canonical_identity_hash


@dataclass(frozen=True, slots=True)
class ValidationPartitionSpecification:
    schema_version: str
    partition_id: str
    provider_id: str
    date_selection_rule_id: str
    requested_start_date: date | None
    requested_end_date: date | None
    minimum_decision_dates: int
    exclusion_policy_id: str
    protocol_id: str
    model_spec_hash: str
    created_at: datetime
    status: str

    def __post_init__(self) -> None:
        if self.schema_version != "pit-validation-partition-specification-v1":
            raise ValueError("partition specification schema mismatch")
        if self.provider_id != "XUNTOU":
            raise ValueError("partition provider must be Xuntou")
        if self.requested_start_date is None or self.requested_end_date is None:
            raise ValueError("PARTITION_SPEC_REQUIRED")
        if self.requested_start_date > self.requested_end_date:
            raise ValueError("partition date range is invalid")
        if self.status != "SPECIFIED_NOT_OPENED":
            raise ValueError("new partition specification must remain unopened")

    def to_canonical_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["requested_start_date"] = self.requested_start_date.isoformat() if self.requested_start_date else None
        payload["requested_end_date"] = self.requested_end_date.isoformat() if self.requested_end_date else None
        payload["created_at"] = self.created_at.isoformat()
        return payload

    @property
    def specification_hash(self) -> str:
        return canonical_identity_hash(self.to_canonical_dict())


@dataclass(frozen=True, slots=True)
class PartitionSealArtifact:
    schema_version: str
    partition_id: str
    specification_hash: str
    included_sessions: tuple[date, ...]
    excluded_sessions: tuple[tuple[date, str], ...]
    calendar_identity: str
    provider_source_hashes: tuple[str, ...]
    universe_identity: str
    protocol_id: str
    model_spec_hash: str
    sealed_at: datetime
    first_opened_at: None
    partition_content_hash: str

    def __post_init__(self) -> None:
        if self.schema_version != "pit-validation-partition-seal-v1":
            raise ValueError("partition seal schema mismatch")
        if self.first_opened_at is not None:
            raise ValueError("immutable partition seal must remain unopened")
        if not self.partition_content_hash.startswith("sha256:"):
            raise ValueError("partition content hash is invalid")


@dataclass(frozen=True, slots=True)
class PartitionOpenReceipt:
    schema_version: str
    partition_id: str
    opened_at: datetime
    run_id: str
    reader_implementation_identity: str
    partition_hash: str

    def __post_init__(self) -> None:
        if self.schema_version != "pit-validation-partition-open-receipt-v1":
            raise ValueError("partition open receipt schema mismatch")
        if not self.partition_id or not self.run_id:
            raise ValueError("partition open receipt identity is incomplete")
        if not self.reader_implementation_identity.startswith("sha256:"):
            raise ValueError("partition reader implementation identity is invalid")
        if not self.partition_hash.startswith("sha256:"):
            raise ValueError("partition open receipt hash is invalid")


def seal_validation_partition(
    specification: ValidationPartitionSpecification,
    *,
    included_sessions: Iterable[date],
    excluded_sessions: Iterable[tuple[date, str]],
    development_sessions: Iterable[date],
    calendar_identity: str,
    provider_source_hashes: tuple[str, ...],
    universe_identity: str,
    sealed_at: datetime,
    existing_partition_ids: frozenset[str] = frozenset(),
) -> PartitionSealArtifact:
    if specification.partition_id in existing_partition_ids:
        raise ValueError("sealed Validation partition cannot be resealed")
    included = tuple(sorted(included_sessions))
    excluded = tuple(sorted(excluded_sessions))
    if len(included) != len(set(included)) or set(included) & set(development_sessions):
        raise ValueError("Validation partition sessions overlap or repeat development evidence")
    requested_start = specification.requested_start_date
    requested_end = specification.requested_end_date
    assert requested_start is not None and requested_end is not None
    if any(value < requested_start or value > requested_end for value in included):
        raise ValueError("Validation partition session falls outside the frozen date range")
    excluded_dates = tuple(value for value, reason in excluded if reason)
    if len(excluded_dates) != len(excluded) or len(excluded_dates) != len(set(excluded_dates)):
        raise ValueError("Validation partition exclusions must be unique and explained")
    if set(included) & set(excluded_dates):
        raise ValueError("Validation partition session cannot be included and excluded")
    if len(included) < specification.minimum_decision_dates:
        raise ValueError("Validation partition has insufficient Decision Dates")
    if not calendar_identity or not universe_identity or not provider_source_hashes:
        raise ValueError("Validation partition source identity is incomplete")
    if any(not value.startswith("sha256:") for value in provider_source_hashes):
        raise ValueError("Validation partition source hash is invalid")
    payload = {
        "schema_version": "pit-validation-partition-seal-v1",
        "partition_id": specification.partition_id,
        "specification_hash": specification.specification_hash,
        "included_sessions": [value.isoformat() for value in included],
        "excluded_sessions": [[value.isoformat(), reason] for value, reason in excluded],
        "calendar_identity": calendar_identity,
        "provider_source_hashes": list(provider_source_hashes),
        "universe_identity": universe_identity,
        "protocol_id": specification.protocol_id,
        "model_spec_hash": specification.model_spec_hash,
    }
    return PartitionSealArtifact(
        "pit-validation-partition-seal-v1",
        specification.partition_id,
        specification.specification_hash,
        included,
        excluded,
        calendar_identity,
        provider_source_hashes,
        universe_identity,
        specification.protocol_id,
        specification.model_spec_hash,
        sealed_at,
        None,
        canonical_identity_hash(payload),
    )


def open_partition(
    seal: PartitionSealArtifact,
    *,
    opened_at: datetime,
    run_id: str,
    reader_implementation_identity: str,
) -> PartitionOpenReceipt:
    return PartitionOpenReceipt(
        "pit-validation-partition-open-receipt-v1",
        seal.partition_id,
        opened_at,
        run_id,
        reader_implementation_identity,
        seal.partition_content_hash,
    )


PARTITION_GOVERNANCE_DIRECTORY = ".pit-validation-partitions"


def persist_partition_seal(
    *,
    output_root: Path,
    specification: ValidationPartitionSpecification,
    seal: PartitionSealArtifact,
) -> Path:
    """Persist a seal before model access so a failed run cannot reseal it."""

    _validate_partition_component(specification.partition_id)
    _verify_seal_binding(specification, seal)
    parent = output_root / PARTITION_GOVERNANCE_DIRECTORY
    final = parent / specification.partition_id
    stage = parent / f".{specification.partition_id}.staging"
    if final.exists() or stage.exists():
        raise ValueError("sealed Validation partition cannot be resealed")
    parent.mkdir(parents=True, exist_ok=True)
    stage.mkdir()
    try:
        specification_path = stage / "partition_specification.json"
        seal_path = stage / "partition_seal.json"
        _write_json(specification_path, specification.to_canonical_dict())
        _write_json(seal_path, asdict(seal))
        _write_json(
            stage / "SHA256SUMS.json",
            {
                specification_path.name: _content_hash(specification_path),
                seal_path.name: _content_hash(seal_path),
            },
        )
        stage.rename(final)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return final


def open_persisted_partition(
    *,
    output_root: Path,
    seal: PartitionSealArtifact,
    opened_at: datetime,
    run_id: str,
    reader_implementation_identity: str,
) -> PartitionOpenReceipt:
    """Write the sole first-open receipt with exclusive-create semantics."""

    _validate_partition_component(seal.partition_id)
    root = output_root / PARTITION_GOVERNANCE_DIRECTORY / seal.partition_id
    _verify_persisted_seal(root, seal)
    receipt = open_partition(
        seal,
        opened_at=opened_at,
        run_id=run_id,
        reader_implementation_identity=reader_implementation_identity,
    )
    path = root / "partition_open_receipt.json"
    try:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(receipt), sort_keys=True, indent=2, default=str))
            handle.write("\n")
    except FileExistsError as exc:
        raise ValueError("Validation partition has already been opened") from exc
    return receipt


def _verify_seal_binding(
    specification: ValidationPartitionSpecification,
    seal: PartitionSealArtifact,
) -> None:
    if (
        seal.partition_id != specification.partition_id
        or seal.specification_hash != specification.specification_hash
        or seal.protocol_id != specification.protocol_id
        or seal.model_spec_hash != specification.model_spec_hash
    ):
        raise ValueError("Validation partition seal does not bind its specification")


def _verify_persisted_seal(root: Path, seal: PartitionSealArtifact) -> None:
    expected_files = {
        "partition_specification.json",
        "partition_seal.json",
        "SHA256SUMS.json",
    }
    if not root.is_dir():
        raise ValueError("persisted Validation partition seal is missing")
    files = {item.name for item in root.iterdir() if item.is_file()}
    if files not in (expected_files, expected_files | {"partition_open_receipt.json"}):
        raise ValueError("persisted Validation partition file set mismatch")
    checksums = json.loads((root / "SHA256SUMS.json").read_text(encoding="utf-8"))
    if checksums != {
        name: _content_hash(root / name)
        for name in ("partition_specification.json", "partition_seal.json")
    }:
        raise ValueError("persisted Validation partition checksum mismatch")
    persisted = json.loads((root / "partition_seal.json").read_text(encoding="utf-8"))
    expected = json.loads(json.dumps(asdict(seal), sort_keys=True, default=str))
    if persisted != expected:
        raise ValueError("persisted Validation partition seal mismatch")


def _validate_partition_component(value: str) -> None:
    if not value or value in {".", ".."} or Path(value).name != value:
        raise ValueError("partition_id is not a safe path component")


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, sort_keys=True, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def _content_hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"
