"""Normalized market-data boundary shared by canonical and Legacy feature runs.

The dataset owns only immutable, content-addressed inputs.  Conversion to a
Legacy pandas frame is intentionally kept in the Legacy adapter, where lossy
Decimal-to-float behavior can be labelled rather than silently promoted.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping

from market_regime_alpha.core.identity import ArtifactId, DatasetId, ModelId
from market_regime_alpha.core.status import InputAvailabilityStatus
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    require_sha256,
    require_text,
    require_unique_text,
)
from market_regime_alpha.features.model_contracts import FeatureComputationRequest


NORMALIZED_FEATURE_DATASET_SCHEMA = "normalized-feature-dataset-v1"


def _require_canonical_time(label: str, value: datetime) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{label} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    if value.microsecond != 0:
        raise ValueError(f"{label} must have whole-second precision")


def _require_sorted_unique_text(label: str, values: tuple[str, ...]) -> None:
    if not isinstance(values, tuple):
        raise TypeError(f"{label} values must be a tuple")
    require_unique_text(label, values)
    if values != tuple(sorted(values)):
        raise ValueError(f"{label} values must be sorted")


def _canonicalizable(value: object, label: str) -> Mapping[str, Any]:
    method = getattr(value, "to_canonical_dict", None)
    if method is None or not callable(method):
        raise TypeError(f"{label} must expose to_canonical_dict()")
    payload = method()
    if not isinstance(payload, Mapping) or any(
        not isinstance(key, str) for key in payload
    ):
        raise TypeError(f"{label} must canonicalize to an object")
    return payload


@dataclass(frozen=True, slots=True)
class NormalizedFeatureDataset:
    """One exact feature input shared by both implementations."""

    dataset_id: DatasetId
    content_hash: str
    as_of_time: datetime
    data_availability: InputAvailabilityStatus
    configuration_id: ArtifactId
    configuration_version: str
    configuration_hash: str
    configuration: object
    input_artifact_ids: tuple[ArtifactId, ...]
    input_hashes: tuple[str, ...]
    normalized_data: tuple[object, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.dataset_id, DatasetId):
            raise TypeError("dataset_id must be a DatasetId")
        if not isinstance(self.configuration_id, ArtifactId):
            raise TypeError("configuration_id must be an ArtifactId")
        require_sha256("content_hash", self.content_hash)
        _require_canonical_time("as_of_time", self.as_of_time)
        if not isinstance(self.data_availability, InputAvailabilityStatus):
            raise TypeError("data_availability must be an InputAvailabilityStatus")
        require_text("configuration_version", self.configuration_version)
        require_sha256("configuration_hash", self.configuration_hash)
        if not isinstance(self.input_artifact_ids, tuple) or not isinstance(
            self.input_hashes, tuple
        ):
            raise TypeError("input references must be immutable tuples")
        if len(self.input_artifact_ids) != len(self.input_hashes):
            raise ValueError("input Artifact identities and hashes must align")
        if any(not isinstance(item, ArtifactId) for item in self.input_artifact_ids):
            raise TypeError("input_artifact_ids must contain ArtifactId values")
        if self.input_artifact_ids != tuple(
            sorted(self.input_artifact_ids, key=str)
        ):
            raise ValueError("input Artifact identities must be sorted")
        if len(self.input_artifact_ids) != len(set(self.input_artifact_ids)):
            raise ValueError("input Artifact identities must be unique")
        for value in self.input_hashes:
            require_sha256("input_hash", value)
        if not isinstance(self.normalized_data, tuple):
            raise TypeError("normalized_data must be an immutable tuple")
        configuration = _canonicalizable(self.configuration, "configuration")
        if configuration.get("configuration_id") != str(self.configuration_id):
            raise ValueError("configuration identity mismatch")
        if configuration.get("content_hash") != self.configuration_hash:
            raise ValueError("configuration hash mismatch")
        expected = canonical_hash(self.semantic_payload())
        if self.content_hash != expected:
            raise ValueError("Normalized Feature Dataset hash mismatch")

    @classmethod
    def create(
        cls,
        *,
        dataset_id: DatasetId,
        as_of_time: datetime,
        data_availability: InputAvailabilityStatus,
        configuration_id: ArtifactId,
        configuration_version: str,
        configuration_hash: str,
        configuration: object,
        input_artifact_ids: tuple[ArtifactId, ...],
        input_hashes: tuple[str, ...],
        normalized_data: tuple[object, ...],
    ) -> NormalizedFeatureDataset:
        semantic = _dataset_payload(
            dataset_id=dataset_id,
            as_of_time=as_of_time,
            data_availability=data_availability,
            configuration_id=configuration_id,
            configuration_version=configuration_version,
            configuration_hash=configuration_hash,
            configuration=configuration,
            input_artifact_ids=input_artifact_ids,
            input_hashes=input_hashes,
            normalized_data=normalized_data,
        )
        return cls(
            dataset_id=dataset_id,
            content_hash=canonical_hash(semantic),
            as_of_time=as_of_time,
            data_availability=data_availability,
            configuration_id=configuration_id,
            configuration_version=configuration_version,
            configuration_hash=configuration_hash,
            configuration=configuration,
            input_artifact_ids=input_artifact_ids,
            input_hashes=input_hashes,
            normalized_data=normalized_data,
        )

    def semantic_payload(self) -> dict[str, Any]:
        return _dataset_payload(
            dataset_id=self.dataset_id,
            as_of_time=self.as_of_time,
            data_availability=self.data_availability,
            configuration_id=self.configuration_id,
            configuration_version=self.configuration_version,
            configuration_hash=self.configuration_hash,
            configuration=self.configuration,
            input_artifact_ids=self.input_artifact_ids,
            input_hashes=self.input_hashes,
            normalized_data=self.normalized_data,
        )

    def to_feature_request(self, *, created_at: datetime) -> FeatureComputationRequest:
        _require_canonical_time("created_at", created_at)
        return FeatureComputationRequest(
            dataset_id=self.dataset_id,
            as_of_time=self.as_of_time,
            created_at=created_at,
            data_availability=self.data_availability,
            configuration_id=self.configuration_id,
            configuration_version=self.configuration_version,
            configuration_hash=self.configuration_hash,
            input_artifact_ids=self.input_artifact_ids,
            input_hashes=self.input_hashes,
            normalized_data=self.normalized_data,
            configuration=self.configuration,
        )


def _dataset_payload(
    *,
    dataset_id: DatasetId,
    as_of_time: datetime,
    data_availability: InputAvailabilityStatus,
    configuration_id: ArtifactId,
    configuration_version: str,
    configuration_hash: str,
    configuration: object,
    input_artifact_ids: tuple[ArtifactId, ...],
    input_hashes: tuple[str, ...],
    normalized_data: tuple[object, ...],
) -> dict[str, Any]:
    return {
        "schema_version": NORMALIZED_FEATURE_DATASET_SCHEMA,
        "dataset_id": str(dataset_id),
        "as_of_time": canonical_datetime(as_of_time),
        "data_availability": data_availability.value,
        "configuration_id": str(configuration_id),
        "configuration_version": configuration_version,
        "configuration_hash": configuration_hash,
        "configuration": _canonicalizable(configuration, "configuration"),
        "input_artifact_ids": [str(item) for item in input_artifact_ids],
        "input_hashes": list(input_hashes),
        "normalized_data": [
            _canonicalizable(item, "normalized data item") for item in normalized_data
        ],
    }


class LegacyFeatureResultState(str, Enum):
    AVAILABLE = "AVAILABLE"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"
    NOT_COMPARABLE = "NOT_COMPARABLE"
    COMPUTATION_FAILED = "COMPUTATION_FAILED"


@dataclass(frozen=True, slots=True)
class LegacyFeatureObservation:
    key: str
    market_date: date
    value: Decimal | None
    missing_reason: str | None

    def __post_init__(self) -> None:
        require_text("observation key", self.key)
        if not isinstance(self.market_date, date) or isinstance(
            self.market_date, datetime
        ):
            raise TypeError("market_date must be a date")
        if self.value is not None and (
            not isinstance(self.value, Decimal) or not self.value.is_finite()
        ):
            raise ValueError("Legacy observation value must be a finite Decimal")
        if self.missing_reason is not None:
            require_text("missing_reason", self.missing_reason)
        if (self.value is None) == (self.missing_reason is None):
            raise ValueError("Legacy observation requires one value or missing_reason")

    def to_canonical_dict(self) -> dict[str, str | None]:
        return {
            "key": self.key,
            "market_date": self.market_date.isoformat(),
            "value": str(self.value) if self.value is not None else None,
            "missing_reason": self.missing_reason,
        }


@dataclass(frozen=True, slots=True)
class LegacyFeatureResult:
    model_id: ModelId
    model_version: str
    state: LegacyFeatureResultState
    score: Decimal | None
    observations: tuple[LegacyFeatureObservation, ...]
    reason_codes: tuple[str, ...]
    limitations: tuple[str, ...]
    exception_type: str | None = None
    exception_message: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.model_id, ModelId):
            raise TypeError("model_id must be a ModelId")
        require_text("model_version", self.model_version)
        if not isinstance(self.state, LegacyFeatureResultState):
            raise TypeError("state must be a LegacyFeatureResultState")
        if self.score is not None and (
            not isinstance(self.score, Decimal) or not self.score.is_finite()
        ):
            raise ValueError("Legacy score must be a finite Decimal")
        if not isinstance(self.observations, tuple) or any(
            not isinstance(item, LegacyFeatureObservation)
            for item in self.observations
        ):
            raise TypeError("observations must contain LegacyFeatureObservation values")
        keys = tuple(item.key for item in self.observations)
        if keys != tuple(sorted(keys)) or len(keys) != len(set(keys)):
            raise ValueError("Legacy observation keys must be sorted and unique")
        _require_sorted_unique_text("reason_code", self.reason_codes)
        _require_sorted_unique_text("limitation", self.limitations)
        if (self.exception_type is None) != (self.exception_message is None):
            raise ValueError("Legacy exception type and message must be paired")
        if self.exception_type is not None:
            require_text("exception_type", self.exception_type)
            require_text("exception_message", self.exception_message or "")
        if self.state is LegacyFeatureResultState.COMPUTATION_FAILED:
            if self.exception_type is None:
                raise ValueError("failed Legacy result requires exception details")
        elif self.exception_type is not None:
            raise ValueError("only failed Legacy results may contain an exception")

    @classmethod
    def failed(
        cls,
        *,
        model_id: ModelId,
        model_version: str,
        exception: Exception,
        limitations: tuple[str, ...] = (
            "LEGACY_EXCEPTION_EXPOSED",
            "NO_STATIC_DATA_FALLBACK",
            "NO_TRADING_AUTHORITY",
            "RESEARCH_ONLY",
        ),
    ) -> LegacyFeatureResult:
        return cls(
            model_id=model_id,
            model_version=model_version,
            state=LegacyFeatureResultState.COMPUTATION_FAILED,
            score=None,
            observations=(),
            reason_codes=("LEGACY_COMPUTATION_FAILED",),
            limitations=tuple(sorted(limitations)),
            exception_type=type(exception).__name__,
            exception_message=str(exception),
        )


__all__ = [
    "LegacyFeatureObservation",
    "LegacyFeatureResult",
    "LegacyFeatureResultState",
    "NORMALIZED_FEATURE_DATASET_SCHEMA",
    "NormalizedFeatureDataset",
]
