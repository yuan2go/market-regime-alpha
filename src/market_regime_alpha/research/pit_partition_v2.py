"""Immutable Validation partition specification, seal, and first-open receipt."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
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


@dataclass(frozen=True, slots=True)
class PartitionOpenReceipt:
    schema_version: str
    partition_id: str
    opened_at: datetime
    run_id: str
    reader_implementation_identity: str
    partition_hash: str


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
