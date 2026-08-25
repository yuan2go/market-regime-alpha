"""Bounded staged publication for the canonical Historical Corpus authority."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any

from market_regime_alpha.application.historical_corpus.artifacts import (
    FailureInjector,
    HISTORICAL_PACKAGE_ENCODING,
    HISTORICAL_PARQUET_SCHEMA,
    HistoricalPackageIndex,
    HistoricalPartitionDescriptor,
    _file_hash,
    _fsync_directory,
    _fsync_tree,
    _write_json,
    _write_partition,
    load_historical_package_index,
)
from market_regime_alpha.application.historical_corpus.contracts import (
    HISTORICAL_AVAILABILITY_BASIS,
    HISTORICAL_EVIDENCE_LIMITATIONS,
    HISTORICAL_OWNER_SCHEMA,
    HistoricalArtifactKind,
    HistoricalCorpusCoverage,
    HistoricalDataPartition,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
)


@dataclass(frozen=True, slots=True)
class HistoricalOwnerMetadata:
    """Small owner metadata retained while decoded partitions are released."""

    provider_id: str
    normalization_version: str | None
    parent_reference: ValidationArtifactReference | None
    created_at: datetime
    retrieved_at: datetime
    coverage: HistoricalCorpusCoverage
    limitations: tuple[str, ...]


class StagedHistoricalPackageWriter:
    """Write one verified logical partition at a time, then freeze one owner."""

    def __init__(
        self,
        *,
        artifact_root: Path,
        artifact_kind: HistoricalArtifactKind,
        bucket_count: int,
        failure_injector: FailureInjector | None = None,
    ) -> None:
        if artifact_kind is HistoricalArtifactKind.RESEARCH_MATERIALIZATION:
            raise ValueError("research materialization does not use data partitions")
        if bucket_count <= 0:
            raise ValueError("Historical staged package bucket_count must be positive")
        self._artifact_kind = artifact_kind
        self._bucket_count = bucket_count
        self._failure_injector = failure_injector
        self._family = (
            artifact_root.resolve()
            / "historical-corpus"
            / artifact_kind.value.lower()
        )
        self._family.mkdir(parents=True, exist_ok=True)
        self._stage = Path(
            tempfile.mkdtemp(prefix=".historical-staged.", dir=self._family)
        )
        self._descriptors: list[HistoricalPartitionDescriptor] = []
        self._keys: set[tuple[str, object, int]] = set()
        self._finalized = False

    @property
    def decoded_record_count(self) -> int:
        """The writer retains descriptors, never decoded records."""

        return 0

    def add_partition(
        self,
        partition: HistoricalDataPartition,
    ) -> HistoricalPartitionDescriptor:
        if self._finalized:
            raise ValueError("Historical staged package is already finalized")
        if (
            partition.artifact_kind is not self._artifact_kind
            or partition.bucket_count != self._bucket_count
        ):
            raise ValueError("Historical staged partition contract mismatch")
        key = (
            partition.timeframe.value,
            partition.first_market_date,
            partition.symbol_bucket,
        )
        if key in self._keys:
            raise ValueError("Historical staged package duplicate partition key")
        partition.verify_identity()
        _write_partition(self._stage / partition.relative_path, partition)
        descriptor = HistoricalPartitionDescriptor.from_reference_dict(
            partition.reference_dict()
        )
        self._keys.add(key)
        self._descriptors.append(descriptor)
        return descriptor

    def finalize(self, metadata: HistoricalOwnerMetadata) -> HistoricalPackageIndex:
        if self._finalized:
            raise ValueError("Historical staged package is already finalized")
        if not self._descriptors:
            raise ValueError("Historical staged package requires partitions")
        descriptors = tuple(
            sorted(
                self._descriptors,
                key=lambda item: (
                    item.timeframe.value,
                    item.first_market_date,
                    item.symbol_bucket,
                ),
            )
        )
        manifest = _owner_manifest(
            artifact_kind=self._artifact_kind,
            bucket_count=self._bucket_count,
            partitions=descriptors,
            metadata=metadata,
        )
        owner_id = str(manifest["owner_id"])
        content_hash = str(manifest["content_hash"])
        final = self._family / owner_id
        installed = False
        try:
            _write_json(self._stage / "manifest.json", manifest)
            _write_json(
                self._stage / "encoding.json",
                {
                    "encoding_version": HISTORICAL_PACKAGE_ENCODING,
                    "logical_owner_id": owner_id,
                    "logical_owner_hash": content_hash,
                    "logical_hash_basis": "CANONICAL_OWNER_AND_PARTITION_PAYLOADS",
                    "physical_hash_basis": "FILE_SHA256",
                    "parquet_schema": HISTORICAL_PARQUET_SCHEMA,
                },
            )
            physical_files = tuple(
                sorted(
                    item.relative_to(self._stage).as_posix()
                    for item in self._stage.rglob("*")
                    if item.is_file()
                )
            )
            _write_json(
                self._stage / "SHA256SUMS.json",
                {name: _file_hash(self._stage / name) for name in physical_files},
            )
            _fsync_tree(self._stage)
            staged = load_historical_package_index(
                self._stage,
                enforce_directory_identity=False,
            )
            if staged.reference != ValidationArtifactReference(
                self._artifact_kind.value,
                ArtifactId(owner_id),
                content_hash,
            ):
                raise ValueError("staged Historical package semantic mismatch")
            if self._failure_injector is not None:
                self._failure_injector("AFTER_STAGING_VALIDATED")
            if final.exists():
                existing = load_historical_package_index(final)
                if (
                    existing.reference != staged.reference
                    or dict(existing.manifest) != dict(staged.manifest)
                    or existing.checksums != staged.checksums
                ):
                    raise FileExistsError(
                        "conflicting Historical package identity exists"
                    )
                shutil.rmtree(self._stage)
                installed = True
                self._finalized = True
                return existing
            os.replace(self._stage, final)
            installed = True
            self._finalized = True
            _fsync_directory(self._family)
            if self._failure_injector is not None:
                self._failure_injector("AFTER_ATOMIC_PUBLISH")
            return load_historical_package_index(final)
        finally:
            if not installed and self._stage.exists():
                shutil.rmtree(self._stage)


def _owner_manifest(
    *,
    artifact_kind: HistoricalArtifactKind,
    bucket_count: int,
    partitions: tuple[HistoricalPartitionDescriptor, ...],
    metadata: HistoricalOwnerMetadata,
) -> dict[str, Any]:
    if metadata.created_at < metadata.retrieved_at:
        raise ValueError("Historical owner predates provider retrieval")
    if artifact_kind is HistoricalArtifactKind.RAW_PROVIDER_ARCHIVE:
        if (
            metadata.parent_reference is not None
            or metadata.normalization_version is not None
        ):
            raise ValueError("Raw archive cannot have a parent or normalization version")
    elif (
        metadata.parent_reference is None
        or metadata.parent_reference.artifact_kind != "RAW_PROVIDER_ARCHIVE"
        or metadata.normalization_version is None
    ):
        raise ValueError("Normalized Dataset requires exact Raw parent and version")
    limitations = tuple(
        sorted(set(metadata.limitations) | set(HISTORICAL_EVIDENCE_LIMITATIONS))
    )
    semantic: dict[str, Any] = {
        "schema_version": HISTORICAL_OWNER_SCHEMA,
        "artifact_kind": artifact_kind.value,
        "provider_id": metadata.provider_id,
        "normalization_version": metadata.normalization_version,
        "parent_reference": (
            None
            if metadata.parent_reference is None
            else metadata.parent_reference.to_canonical_dict()
        ),
        "created_at": canonical_datetime(metadata.created_at),
        "retrieved_at": canonical_datetime(metadata.retrieved_at),
        "first_market_date": min(
            item.first_market_date for item in partitions
        ).isoformat(),
        "last_market_date": max(
            item.last_market_date for item in partitions
        ).isoformat(),
        "bucket_count": bucket_count,
        "partitions": [item.reference_dict() for item in partitions],
        "coverage": metadata.coverage.to_canonical_dict(),
        "availability_basis": HISTORICAL_AVAILABILITY_BASIS,
        "data_eligibility": "EXPLORATORY",
        "formal_pit_status": "PIT_INCOMPLETE",
        "limitations": list(limitations),
    }
    digest = canonical_hash(semantic)
    return {
        "owner_id": f"historical-data-owner-{digest[7:31]}",
        "content_hash": digest,
        **semantic,
    }


__all__ = [
    "HistoricalOwnerMetadata",
    "StagedHistoricalPackageWriter",
]
