"""Typed Research Definition command results and replay reconstruction."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from market_regime_alpha.research_qualification.ports import (
    DatasetRecord,
    ResearchUnitOfWork,
)
from market_regime_alpha.runtime.errors import (
    ArtifactIntegrityError,
    CommandPreviouslyFailedError,
    RuntimeStateConflictError,
)
from market_regime_alpha.runtime.ports import ReceiptRecord
from market_regime_alpha.shared.hashing import canonical_json_sha256


@dataclass(frozen=True, slots=True)
class ResearchMutationResult:
    aggregate_kind: str
    aggregate_id: str
    aggregate_version: int
    result_hash: str
    receipt_id: UUID
    replayed: bool


@dataclass(frozen=True, slots=True)
class DatasetRegistrationResult:
    aggregate_kind: str
    aggregate_id: str
    aggregate_version: int
    result_hash: str
    receipt_id: UUID
    replayed: bool
    row_count: int
    feature_count: int
    source_count: int
    cell_count: int
    available_cell_count: int
    missing_cell_count: int
    unknown_cell_count: int
    stale_cell_count: int
    conflict_cell_count: int


def replayed_mutation_result(receipt: ReceiptRecord) -> ResearchMutationResult:
    ensure_replay_succeeded(receipt)
    if (
        receipt.result_aggregate_kind is None
        or receipt.result_aggregate_id is None
        or receipt.result_aggregate_version is None
        or receipt.result_hash is None
    ):
        raise ArtifactIntegrityError("terminal receipt has no complete result")
    return ResearchMutationResult(
        aggregate_kind=receipt.result_aggregate_kind,
        aggregate_id=receipt.result_aggregate_id,
        aggregate_version=receipt.result_aggregate_version,
        result_hash=receipt.result_hash,
        receipt_id=receipt.receipt_id,
        replayed=True,
    )


def replayed_dataset_result(
    uow: ResearchUnitOfWork,
    receipt: ReceiptRecord,
) -> DatasetRegistrationResult:
    ensure_replay_succeeded(receipt)
    if (
        receipt.result_aggregate_kind != "DATASET"
        or receipt.result_aggregate_id is None
        or receipt.result_aggregate_version is None
        or receipt.result_hash is None
    ):
        raise ArtifactIntegrityError("Dataset receipt has no complete result")
    try:
        dataset_id = UUID(receipt.result_aggregate_id)
    except ValueError as exc:
        raise ArtifactIntegrityError(
            "Dataset receipt result identity is invalid"
        ) from exc
    record = uow.research_definitions.dataset_record(dataset_id, lock=False)
    expected_result_hash = dataset_result_hash(record)
    if (
        record.version != receipt.result_aggregate_version
        or expected_result_hash != receipt.result_hash
    ):
        raise ArtifactIntegrityError(
            "Dataset receipt and Authority do not reconcile"
        )
    return dataset_result(
        record,
        receipt_id=receipt.receipt_id,
        result_hash=expected_result_hash,
        replayed=True,
    )


def dataset_result_hash(record: DatasetRecord) -> str:
    return canonical_json_sha256(record)


def dataset_result(
    record: DatasetRecord,
    *,
    receipt_id: UUID,
    result_hash: str,
    replayed: bool,
) -> DatasetRegistrationResult:
    return DatasetRegistrationResult(
        aggregate_kind="DATASET",
        aggregate_id=str(record.dataset_id),
        aggregate_version=record.version,
        result_hash=result_hash,
        receipt_id=receipt_id,
        replayed=replayed,
        row_count=record.row_count,
        feature_count=record.feature_count,
        source_count=record.source_count,
        cell_count=record.cell_count,
        available_cell_count=record.available_cell_count,
        missing_cell_count=record.missing_cell_count,
        unknown_cell_count=record.unknown_cell_count,
        stale_cell_count=record.stale_cell_count,
        conflict_cell_count=record.conflict_cell_count,
    )


def ensure_replay_succeeded(receipt: ReceiptRecord) -> None:
    if receipt.status in {"FAILED", "BLOCKED"}:
        raise CommandPreviouslyFailedError(
            receipt.error_code or "COMMAND_FAILED_WITHOUT_ERROR_CODE"
        )
    if receipt.status != "SUCCEEDED":
        raise RuntimeStateConflictError(
            f"receipt {receipt.receipt_id} is not a replayable terminal result"
        )


__all__ = [
    "DatasetRegistrationResult",
    "ResearchMutationResult",
    "dataset_result",
    "dataset_result_hash",
    "replayed_dataset_result",
    "replayed_mutation_result",
]
