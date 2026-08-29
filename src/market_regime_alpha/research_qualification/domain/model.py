"""Immutable Research Definition identities and calculation semantics."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from uuid import UUID

from market_regime_alpha.research_qualification.domain.vocabulary import (
    FeatureAvailabilityRule,
    FeatureIntervalUnit,
    FeatureMissingnessPolicy,
    FeatureSourceRequirement,
    FeatureValueType,
)
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.identity import ContentHash
from market_regime_alpha.shared.time import DecisionTime


_IDENTITY_CODE = re.compile(r"^[a-z][a-z0-9_-]{0,99}$")
_UNIT = re.compile(r"^[A-Z][A-Z0-9_]{0,31}$")
_ALGORITHM_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


@dataclass(frozen=True, slots=True)
class ArtifactBinding:
    artifact_id: UUID
    content_sha256: ContentHash | str
    size_bytes: int

    def __post_init__(self) -> None:
        content_hash = (
            self.content_sha256
            if isinstance(self.content_sha256, ContentHash)
            else ContentHash(self.content_sha256)
        )
        object.__setattr__(self, "content_sha256", content_hash)
        if isinstance(self.size_bytes, bool) or self.size_bytes < 0:
            raise ValueError("Artifact size_bytes must be non-negative")


@dataclass(frozen=True, slots=True)
class FeatureDefinition:
    feature_definition_id: UUID
    feature_code: str
    version: int
    value_type: FeatureValueType
    value_unit: str
    frequency_value: int
    frequency_unit: FeatureIntervalUnit
    window_value: int
    window_unit: FeatureIntervalUnit
    lookback_value: int
    lookback_unit: FeatureIntervalUnit
    source_requirements: tuple[FeatureSourceRequirement, ...]
    availability_rule: FeatureAvailabilityRule
    missingness_policy: FeatureMissingnessPolicy
    algorithm_code: str
    algorithm_version: str
    algorithm_sha256: ContentHash | str
    code_artifact: ArtifactBinding
    config_artifact: ArtifactBinding
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        if not _IDENTITY_CODE.fullmatch(self.feature_code):
            raise ValueError("feature_code has an invalid format")
        if isinstance(self.version, bool) or self.version < 1:
            raise ValueError("FeatureDefinition version must be positive")
        if not isinstance(self.value_type, FeatureValueType):
            raise TypeError("value_type must be FeatureValueType")
        if not _UNIT.fullmatch(self.value_unit):
            raise ValueError("value_unit has an invalid format")
        for field_name, interval_value, allow_zero in (
            ("frequency_value", self.frequency_value, False),
            ("window_value", self.window_value, False),
            ("lookback_value", self.lookback_value, True),
        ):
            if (
                isinstance(interval_value, bool)
                or interval_value < 0
                or (not allow_zero and interval_value == 0)
            ):
                qualifier = "non-negative" if allow_zero else "positive"
                raise ValueError(f"{field_name} must be {qualifier}")
        for field_name, interval_unit in (
            ("frequency_unit", self.frequency_unit),
            ("window_unit", self.window_unit),
            ("lookback_unit", self.lookback_unit),
        ):
            if not isinstance(interval_unit, FeatureIntervalUnit):
                raise TypeError(f"{field_name} must be FeatureIntervalUnit")
        if not self.source_requirements:
            raise ValueError("FeatureDefinition requires explicit sources")
        if any(
            not isinstance(item, FeatureSourceRequirement)
            for item in self.source_requirements
        ):
            raise TypeError(
                "source_requirements must contain FeatureSourceRequirement"
            )
        if self.source_requirements != tuple(
            sorted(set(self.source_requirements), key=lambda item: item.value)
        ):
            raise ValueError("source_requirements must be unique and sorted")
        if not isinstance(self.availability_rule, FeatureAvailabilityRule):
            raise TypeError("availability_rule must be FeatureAvailabilityRule")
        if not isinstance(self.missingness_policy, FeatureMissingnessPolicy):
            raise TypeError("missingness_policy must be FeatureMissingnessPolicy")
        if not _IDENTITY_CODE.fullmatch(self.algorithm_code):
            raise ValueError("algorithm_code has an invalid format")
        if not _ALGORITHM_VERSION.fullmatch(self.algorithm_version):
            raise ValueError("algorithm_version has an invalid format")
        algorithm_hash = (
            self.algorithm_sha256
            if isinstance(self.algorithm_sha256, ContentHash)
            else ContentHash(self.algorithm_sha256)
        )
        object.__setattr__(self, "algorithm_sha256", algorithm_hash)
        content_hash = canonical_json_sha256(
            {
                "algorithm_code": self.algorithm_code,
                "algorithm_sha256": algorithm_hash,
                "algorithm_version": self.algorithm_version,
                "availability_rule": self.availability_rule,
                "code_artifact": self.code_artifact,
                "config_artifact": self.config_artifact,
                "feature_code": self.feature_code,
                "frequency_unit": self.frequency_unit,
                "frequency_value": self.frequency_value,
                "lookback_unit": self.lookback_unit,
                "lookback_value": self.lookback_value,
                "missingness_policy": self.missingness_policy,
                "source_requirements": self.source_requirements,
                "value_type": self.value_type,
                "value_unit": self.value_unit,
                "version": self.version,
                "window_unit": self.window_unit,
                "window_value": self.window_value,
            }
        )
        object.__setattr__(self, "content_sha256", ContentHash(content_hash))


@dataclass(frozen=True, slots=True)
class DecisionInputDatasetDefinition:
    dataset_id: UUID
    dataset_code: str
    version: int
    decision_time: DecisionTime
    universe_revision_id: UUID
    eligibility_policy_id: UUID
    feature_definition_ids: tuple[UUID, ...]
    manifest_artifact: ArtifactBinding
    code_artifact: ArtifactBinding
    config_artifact: ArtifactBinding
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        if not _IDENTITY_CODE.fullmatch(self.dataset_code):
            raise ValueError("dataset_code has an invalid format")
        if isinstance(self.version, bool) or self.version < 1:
            raise ValueError("Dataset version must be positive")
        decision_time = (
            self.decision_time
            if isinstance(self.decision_time, DecisionTime)
            else DecisionTime(self.decision_time)
        )
        object.__setattr__(self, "decision_time", decision_time)
        if not self.feature_definition_ids:
            raise ValueError("Decision-input Dataset requires Feature definitions")
        if self.feature_definition_ids != tuple(
            sorted(set(self.feature_definition_ids), key=str)
        ):
            raise ValueError("feature_definition_ids must be unique and sorted")
        content_hash = canonical_json_sha256(
            {
                "code_artifact": self.code_artifact,
                "config_artifact": self.config_artifact,
                "dataset_code": self.dataset_code,
                "decision_time": decision_time,
                "eligibility_policy_id": self.eligibility_policy_id,
                "feature_definition_ids": self.feature_definition_ids,
                "manifest_artifact": self.manifest_artifact,
                "universe_revision_id": self.universe_revision_id,
                "version": self.version,
            }
        )
        object.__setattr__(self, "content_sha256", ContentHash(content_hash))


__all__ = [
    "ArtifactBinding",
    "DecisionInputDatasetDefinition",
    "FeatureDefinition",
]
