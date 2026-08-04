"""Signal-observation contract with no execution or order semantics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Protocol, runtime_checkable

from market_regime_alpha.core.identity import ArtifactId, ModelId
from market_regime_alpha.evidence.canonical import (
    require_sha256,
    require_text,
    require_unique_text,
)


class SignalMeaning(str, Enum):
    ENTRY_CONFIRMATION = "ENTRY_CONFIRMATION"
    TREND_CONTINUATION = "TREND_CONTINUATION"
    REVERSAL_WARNING = "REVERSAL_WARNING"
    SELL_PRESSURE = "SELL_PRESSURE"
    OVERHEAT = "OVERHEAT"
    VOLUME_CONFIRMATION = "VOLUME_CONFIRMATION"


def _require_aware_time(value: datetime) -> None:
    if not isinstance(value, datetime):
        raise TypeError("as_of_time must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("as_of_time must be timezone-aware")


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


@dataclass(frozen=True, slots=True)
class SignalModelRequest:
    as_of_time: datetime
    configuration_id: ArtifactId
    configuration_hash: str
    input_artifact_ids: tuple[ArtifactId, ...]
    input_hashes: tuple[str, ...]
    inputs: tuple[object, ...]
    configuration: object

    def __post_init__(self) -> None:
        if not isinstance(self.configuration_id, ArtifactId):
            raise TypeError("configuration_id must be an ArtifactId")
        _require_aware_time(self.as_of_time)
        require_sha256("configuration_hash", self.configuration_hash)
        _require_input_references(self.input_artifact_ids, self.input_hashes)
        if not isinstance(self.inputs, tuple):
            raise TypeError("inputs must be an immutable tuple")


@dataclass(frozen=True, slots=True)
class SignalModelResult:
    model_id: ModelId
    model_version: str
    configuration_id: ArtifactId
    configuration_hash: str
    input_artifact_ids: tuple[ArtifactId, ...]
    input_hashes: tuple[str, ...]
    as_of_time: datetime
    state: SignalMeaning
    score: Decimal | None
    reason_codes: tuple[str, ...]
    limitations: tuple[str, ...]
    validation_status: str

    def __post_init__(self) -> None:
        if not isinstance(self.model_id, ModelId):
            raise TypeError("model_id must be a ModelId")
        if not isinstance(self.configuration_id, ArtifactId):
            raise TypeError("configuration_id must be an ArtifactId")
        require_text("model_version", self.model_version)
        require_sha256("configuration_hash", self.configuration_hash)
        _require_input_references(self.input_artifact_ids, self.input_hashes)
        _require_aware_time(self.as_of_time)
        if not isinstance(self.state, SignalMeaning):
            raise TypeError("state must be a SignalMeaning")
        _require_score(self.score)
        _require_sorted_unique_text("reason_code", self.reason_codes)
        _require_sorted_unique_text("limitation", self.limitations)
        require_text("validation_status", self.validation_status)


@runtime_checkable
class SignalModel(Protocol):
    model_id: ModelId
    model_version: str
    supported_meanings: tuple[SignalMeaning, ...]

    def run(self, request: SignalModelRequest) -> SignalModelResult: ...


__all__ = ["SignalMeaning", "SignalModel", "SignalModelRequest", "SignalModelResult"]

