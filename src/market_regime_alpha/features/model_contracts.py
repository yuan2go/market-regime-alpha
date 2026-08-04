"""Pure feature-computation boundary for incremental model migration.

This module deliberately defines a feature role only.  It grants no Signal,
Decision, execution, Repository, or Broker capability.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol, runtime_checkable

from market_regime_alpha.core.identity import (
    ArtifactId,
    DatasetId,
    FeatureDefinitionId,
    ModelId,
)
from market_regime_alpha.core.status import InputAvailabilityStatus
from market_regime_alpha.evidence.canonical import require_sha256, require_text, require_unique_text


def _require_aware_time(label: str, value: datetime) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{label} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")


def _require_input_references(
    input_artifact_ids: tuple[ArtifactId, ...], input_hashes: tuple[str, ...]
) -> None:
    if not isinstance(input_artifact_ids, tuple) or not isinstance(
        input_hashes, tuple
    ):
        raise TypeError("input Artifact identities and hashes must be tuples")
    if len(input_artifact_ids) != len(input_hashes):
        raise ValueError("input Artifact identities and hashes must align")
    if any(not isinstance(item, ArtifactId) for item in input_artifact_ids):
        raise TypeError("input_artifact_ids must contain ArtifactId values")
    if len(input_artifact_ids) != len(set(input_artifact_ids)):
        raise ValueError("input Artifact identities must be unique")
    if input_artifact_ids != tuple(sorted(input_artifact_ids, key=str)):
        raise ValueError("input Artifact identities must be sorted")
    for value in input_hashes:
        require_sha256("input_hash", value)


def _require_sorted_unique_text(label: str, values: tuple[str, ...]) -> None:
    if not isinstance(values, tuple):
        raise TypeError(f"{label} values must be a tuple")
    require_unique_text(label, values)
    if values != tuple(sorted(values)):
        raise ValueError(f"{label} values must be sorted")


def _require_score(score: Decimal | None) -> None:
    if score is None:
        return
    if not isinstance(score, Decimal):
        raise TypeError("score must be a Decimal or None")
    if not score.is_finite():
        raise ValueError("score must be finite")


def _require_configuration_parameters(
    values: tuple[tuple[str, str], ...],
) -> None:
    if not isinstance(values, tuple) or any(
        not isinstance(item, tuple) or len(item) != 2 for item in values
    ):
        raise TypeError("configuration_parameters must be name/value tuples")
    names: list[str] = []
    for name, value in values:
        require_text("configuration parameter name", name)
        require_text("configuration parameter value", value)
        names.append(name)
    if len(names) != len(set(names)):
        raise ValueError("configuration parameter names must be unique")
    if tuple(names) != tuple(sorted(names)):
        raise ValueError("configuration parameters must be sorted")


@dataclass(frozen=True, slots=True)
class FeatureComputationRequest:
    """All explicit inputs needed for a deterministic feature calculation."""

    dataset_id: DatasetId
    as_of_time: datetime
    created_at: datetime
    data_availability: InputAvailabilityStatus
    configuration_id: ArtifactId
    configuration_version: str
    configuration_hash: str
    input_artifact_ids: tuple[ArtifactId, ...]
    input_hashes: tuple[str, ...]
    normalized_data: tuple[object, ...]
    configuration: object

    def __post_init__(self) -> None:
        if not isinstance(self.dataset_id, DatasetId):
            raise TypeError("dataset_id must be a DatasetId")
        if not isinstance(self.configuration_id, ArtifactId):
            raise TypeError("configuration_id must be an ArtifactId")
        _require_aware_time("as_of_time", self.as_of_time)
        _require_aware_time("created_at", self.created_at)
        if self.created_at < self.as_of_time:
            raise ValueError("created_at cannot precede as_of_time")
        if not isinstance(self.data_availability, InputAvailabilityStatus):
            raise TypeError("data_availability must be an InputAvailabilityStatus")
        require_text("configuration_version", self.configuration_version)
        require_sha256("configuration_hash", self.configuration_hash)
        _require_input_references(self.input_artifact_ids, self.input_hashes)
        if not isinstance(self.normalized_data, tuple):
            raise TypeError("normalized_data must be an immutable tuple")


@dataclass(frozen=True, slots=True)
class FeatureArtifact:
    """Immutable, traceable output of one ``FeatureComputer`` invocation."""

    artifact_id: ArtifactId
    content_hash: str
    feature_id: FeatureDefinitionId
    dataset_id: DatasetId
    model_id: ModelId
    model_version: str
    configuration_id: ArtifactId
    configuration_version: str
    configuration_hash: str
    input_artifact_ids: tuple[ArtifactId, ...]
    input_hashes: tuple[str, ...]
    as_of_time: datetime
    created_at: datetime
    data_availability: InputAvailabilityStatus
    state: str
    score: Decimal | None
    reason_codes: tuple[str, ...]
    limitations: tuple[str, ...]
    validation_status: str
    observations: tuple[object, ...]
    configuration_parameters: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.artifact_id, ArtifactId):
            raise TypeError("artifact_id must be an ArtifactId")
        if not isinstance(self.feature_id, FeatureDefinitionId):
            raise TypeError("feature_id must be a FeatureDefinitionId")
        if not isinstance(self.dataset_id, DatasetId):
            raise TypeError("dataset_id must be a DatasetId")
        if not isinstance(self.model_id, ModelId):
            raise TypeError("model_id must be a ModelId")
        if not isinstance(self.configuration_id, ArtifactId):
            raise TypeError("configuration_id must be an ArtifactId")
        require_sha256("content_hash", self.content_hash)
        require_text("model_version", self.model_version)
        require_text("configuration_version", self.configuration_version)
        require_sha256("configuration_hash", self.configuration_hash)
        _require_input_references(self.input_artifact_ids, self.input_hashes)
        _require_aware_time("as_of_time", self.as_of_time)
        _require_aware_time("created_at", self.created_at)
        if self.created_at < self.as_of_time:
            raise ValueError("created_at cannot precede as_of_time")
        if not isinstance(self.data_availability, InputAvailabilityStatus):
            raise TypeError("data_availability must be an InputAvailabilityStatus")
        require_text("state", self.state)
        _require_score(self.score)
        _require_sorted_unique_text("reason_code", self.reason_codes)
        _require_sorted_unique_text("limitation", self.limitations)
        require_text("validation_status", self.validation_status)
        if not isinstance(self.observations, tuple):
            raise TypeError("observations must be an immutable tuple")
        _require_configuration_parameters(self.configuration_parameters)

    def semantic_payload(self) -> dict[str, Any]:
        """Return the exact payload bound by ``content_hash`` and ``artifact_id``."""

        from market_regime_alpha.features.artifact import feature_artifact_payload

        return feature_artifact_payload(self)

    def to_canonical_dict(self) -> dict[str, Any]:
        from market_regime_alpha.features.artifact import feature_artifact_to_dict

        return feature_artifact_to_dict(self)

    def verify_content_identity(self) -> None:
        from market_regime_alpha.features.artifact import verify_feature_artifact_identity

        verify_feature_artifact_identity(self)


@runtime_checkable
class FeatureComputer(Protocol):
    """Side-effect-free observable computation, never a trading action."""

    feature_id: FeatureDefinitionId
    model_version: str

    def compute(self, request: FeatureComputationRequest) -> FeatureArtifact: ...


__all__ = [
    "FeatureArtifact",
    "FeatureComputationRequest",
    "FeatureComputer",
]
