"""Historical path-sample registry, immutable dataset, Reader and replay."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Protocol

from market_regime_alpha.application.research_validation.common import (
    ENGINEERING_LIMITATIONS,
    ValidationArtifactReference,
    content_identity,
    timestamp,
)
from market_regime_alpha.core.identity import ArtifactId, TargetId
from market_regime_alpha.core.time import DecisionTime
from market_regime_alpha.evidence.canonical import canonical_hash, require_sha256, require_text
from market_regime_alpha.forecasting.path import PathForecastSample


class HistoricalSampleQualification(str, Enum):
    UNQUALIFIED = "UNQUALIFIED"
    PIT_ELIGIBLE = "PIT_ELIGIBLE"
    OOS_ELIGIBLE = "OOS_ELIGIBLE"
    QUALIFIED = "QUALIFIED"


@dataclass(frozen=True, slots=True)
class HistoricalPathSampleRecord:
    record_id: ArtifactId
    record_hash: str
    sample: PathForecastSample
    target_reference: ValidationArtifactReference
    outcome_reference: ValidationArtifactReference
    pit_lineage: tuple[ValidationArtifactReference, ...]
    qualification: HistoricalSampleQualification
    registered_at: datetime
    reason_codes: tuple[str, ...]
    schema_version: str = "historical-path-sample-record/v1"

    def __post_init__(self) -> None:
        require_sha256("record_hash", self.record_hash)
        if self.sample.target_id != TargetId(str(self.target_reference.artifact_id)):
            raise ValueError("Historical sample target binding mismatch")
        if self.qualification is not HistoricalSampleQualification.UNQUALIFIED and not self.pit_lineage:
            raise ValueError("eligible Historical sample requires PIT lineage")
        if self.reason_codes != tuple(sorted(set(self.reason_codes))):
            raise ValueError("Historical sample reasons must be unique and sorted")
        if canonical_hash(self.identity_payload()) != self.record_hash:
            raise ValueError("Historical sample record hash mismatch")

    @classmethod
    def register_unqualified(
        cls,
        *,
        sample: PathForecastSample,
        target_reference: ValidationArtifactReference,
        outcome_reference: ValidationArtifactReference,
        pit_lineage: tuple[ValidationArtifactReference, ...],
        registered_at: datetime,
        reason_codes: tuple[str, ...] = ("REAL_FORMAL_PIT_NOT_ESTABLISHED",),
    ) -> HistoricalPathSampleRecord:
        values = _record_payload(
            sample,
            target_reference,
            outcome_reference,
            tuple(sorted(set(pit_lineage), key=_reference_key)),
            HistoricalSampleQualification.UNQUALIFIED,
            registered_at,
            tuple(sorted(set(reason_codes))),
        )
        record_id, digest = content_identity("historical-path-sample", values)
        return cls(
            record_id,
            digest,
            sample,
            target_reference,
            outcome_reference,
            tuple(sorted(set(pit_lineage), key=_reference_key)),
            HistoricalSampleQualification.UNQUALIFIED,
            registered_at,
            tuple(sorted(set(reason_codes))),
        )

    def identity_payload(self) -> dict[str, Any]:
        return _record_payload(
            self.sample,
            self.target_reference,
            self.outcome_reference,
            self.pit_lineage,
            self.qualification,
            self.registered_at,
            self.reason_codes,
        )


@dataclass(frozen=True, slots=True)
class HistoricalSampleDataset:
    dataset_id: ArtifactId
    dataset_hash: str
    registry_version: str
    target_reference: ValidationArtifactReference
    records: tuple[HistoricalPathSampleRecord, ...]
    available_at: datetime
    qualification: HistoricalSampleQualification
    limitations: tuple[str, ...]
    schema_version: str = "historical-sample-dataset/v1"

    def __post_init__(self) -> None:
        require_sha256("dataset_hash", self.dataset_hash)
        require_text("registry_version", self.registry_version)
        keys = tuple((item.sample.sample_decision_time.value, str(item.record_id)) for item in self.records)
        if not self.records or keys != tuple(sorted(set(keys))):
            raise ValueError("Historical Sample Dataset records must be non-empty, unique and sorted")
        if any(item.target_reference != self.target_reference for item in self.records):
            raise ValueError("Historical Sample Dataset target binding mismatch")
        ceiling = min((item.qualification for item in self.records), key=_qualification_rank)
        if self.qualification is not ceiling:
            raise ValueError("Historical Sample Dataset qualification exceeds member evidence")
        if canonical_hash(self.identity_payload()) != self.dataset_hash:
            raise ValueError("Historical Sample Dataset hash mismatch")

    @classmethod
    def create(
        cls,
        *,
        registry_version: str,
        target_reference: ValidationArtifactReference,
        records: tuple[HistoricalPathSampleRecord, ...],
        available_at: datetime,
    ) -> HistoricalSampleDataset:
        if not records:
            raise ValueError("Historical Sample Dataset requires records")
        ordered = tuple(sorted(records, key=lambda item: (item.sample.sample_decision_time.value, str(item.record_id))))
        qualification = min((item.qualification for item in ordered), key=_qualification_rank)
        limitations = tuple(
            sorted({*ENGINEERING_LIMITATIONS, "NO_SAMPLES_FABRICATED_FROM_CURRENT_SIGNAL", f"SAMPLE_QUALIFICATION_{qualification.value}"})
        )
        values = _dataset_payload(registry_version, target_reference, ordered, available_at, qualification, limitations)
        dataset_id, digest = content_identity("historical-sample-dataset", values)
        return cls(dataset_id, digest, registry_version, target_reference, ordered, available_at, qualification, limitations)

    def identity_payload(self) -> dict[str, Any]:
        return _dataset_payload(
            self.registry_version, self.target_reference, self.records, self.available_at, self.qualification, self.limitations
        )


def advance_sample_qualification(
    *,
    record: HistoricalPathSampleRecord,
    qualification: HistoricalSampleQualification,
    authority_evidence: ValidationArtifactReference,
    registered_at: datetime,
) -> HistoricalPathSampleRecord:
    """Monotonic qualification; current Signal can never act as evidence."""
    if _qualification_rank(qualification) <= _qualification_rank(record.qualification):
        raise ValueError("Historical sample qualification must advance monotonically")
    pit_lineage = tuple(sorted({*record.pit_lineage, authority_evidence}, key=_reference_key))
    reasons = (f"QUALIFICATION_ADVANCED_TO_{qualification.value}",)
    values = _record_payload(
        record.sample,
        record.target_reference,
        record.outcome_reference,
        pit_lineage,
        qualification,
        registered_at,
        reasons,
    )
    record_id, digest = content_identity("historical-path-sample", values)
    return HistoricalPathSampleRecord(
        record_id,
        digest,
        record.sample,
        record.target_reference,
        record.outcome_reference,
        pit_lineage,
        qualification,
        registered_at,
        reasons,
    )


class HistoricalSampleRegistryReader(Protocol):
    def read_for_forecast(
        self,
        *,
        symbol: str,
        target_id: TargetId,
        decision_time: DecisionTime,
    ) -> HistoricalSampleDataset | None: ...


class InMemoryHistoricalSampleRegistry:
    """Reference registry semantics; PostgreSQL adapter supplies durable authority."""

    def __init__(self) -> None:
        self._datasets: dict[tuple[str, str], HistoricalSampleDataset] = {}

    def register(self, dataset: HistoricalSampleDataset) -> None:
        key = (str(dataset.target_reference.artifact_id), dataset.registry_version)
        existing = self._datasets.get(key)
        if existing is not None and existing != dataset:
            raise ValueError("Historical Sample Registry identity conflict")
        self._datasets[key] = dataset

    def read_for_forecast(
        self,
        *,
        symbol: str,
        target_id: TargetId,
        decision_time: DecisionTime,
    ) -> HistoricalSampleDataset | None:
        matches = [
            dataset
            for (stored_target, _version), dataset in self._datasets.items()
            if stored_target == str(target_id)
            and dataset.available_at <= decision_time.value
            and any(item.sample.symbol == symbol for item in dataset.records)
        ]
        if not matches:
            return None
        return max(matches, key=lambda item: (item.available_at, item.registry_version))

    def load_available_samples(
        self,
        *,
        symbol: str,
        target_id: object,
        decision_time: DecisionTime,
    ) -> tuple[tuple[PathForecastSample, ...], str, tuple[str, ...]]:
        dataset = self.read_for_forecast(
            symbol=symbol,
            target_id=TargetId(str(target_id)),
            decision_time=decision_time,
        )
        if dataset is None:
            return (), HistoricalSampleQualification.UNQUALIFIED.value, ("HISTORICAL_SAMPLE_DATASET_NOT_AVAILABLE",)
        samples = tuple(
            item.sample
            for item in dataset.records
            if item.sample.symbol == symbol and item.sample.available_at.value <= decision_time.value
        )
        reasons = ("HISTORICAL_SAMPLE_DATASET_LOADED",) if samples else ("HISTORICAL_SAMPLES_NOT_AVAILABLE_AT_DECISION_TIME",)
        return samples, dataset.qualification.value, reasons


def replay_historical_sample_dataset(dataset: HistoricalSampleDataset) -> HistoricalSampleDataset:
    replayed = HistoricalSampleDataset.create(
        registry_version=dataset.registry_version,
        target_reference=dataset.target_reference,
        records=dataset.records,
        available_at=dataset.available_at,
    )
    if replayed != dataset:
        raise ValueError("Historical Sample Dataset replay diverged")
    return replayed


def _record_payload(
    sample: PathForecastSample,
    target: ValidationArtifactReference,
    outcome: ValidationArtifactReference,
    pit: tuple[ValidationArtifactReference, ...],
    qualification: HistoricalSampleQualification,
    registered_at: datetime,
    reasons: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "schema_version": "historical-path-sample-record/v1",
        "sample": sample.to_canonical_dict(),
        "target_reference": target.to_canonical_dict(),
        "outcome_reference": outcome.to_canonical_dict(),
        "pit_lineage": [item.to_canonical_dict() for item in pit],
        "qualification": qualification.value,
        "registered_at": timestamp(registered_at),
        "reason_codes": list(reasons),
    }


def _dataset_payload(
    registry_version: str,
    target: ValidationArtifactReference,
    records: tuple[HistoricalPathSampleRecord, ...],
    available_at: datetime,
    qualification: HistoricalSampleQualification,
    limitations: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "schema_version": "historical-sample-dataset/v1",
        "registry_version": registry_version,
        "target_reference": target.to_canonical_dict(),
        "records": [{"record_id": str(item.record_id), "record_hash": item.record_hash, **item.identity_payload()} for item in records],
        "available_at": timestamp(available_at),
        "qualification": qualification.value,
        "limitations": list(limitations),
    }


def _reference_key(item: ValidationArtifactReference) -> tuple[str, str, str]:
    return item.artifact_kind, str(item.artifact_id), item.content_hash


def _qualification_rank(item: HistoricalSampleQualification) -> int:
    return {
        HistoricalSampleQualification.UNQUALIFIED: 0,
        HistoricalSampleQualification.PIT_ELIGIBLE: 1,
        HistoricalSampleQualification.OOS_ELIGIBLE: 2,
        HistoricalSampleQualification.QUALIFIED: 3,
    }[item]
