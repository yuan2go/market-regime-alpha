"""Stable identity primitives for project-wide V2 contracts.

These types deliberately validate only identity hygiene. They do not impose a prefix
scheme because existing and future registries may use different naming conventions.
"""

from __future__ import annotations

from dataclasses import dataclass


def _validate_identity_value(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("identity value must be a string")
    if not value:
        raise ValueError("identity value must not be empty")
    if value != value.strip():
        raise ValueError("identity value must not contain leading or trailing whitespace")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError("identity value must not contain control characters")
    return value


@dataclass(frozen=True, slots=True)
class StableId:
    """An immutable, non-empty project identity value."""

    value: str

    def __post_init__(self) -> None:
        _validate_identity_value(self.value)

    def __str__(self) -> str:
        return self.value

    @classmethod
    def parse(cls, value: str) -> "StableId":
        return cls(value)


@dataclass(frozen=True, slots=True)
class ArtifactId(StableId):
    """Identity of an artifact such as a manifest or evidence package."""


@dataclass(frozen=True, slots=True)
class ProviderId(StableId):
    """Identity of a data provider or internal data-producing system."""


@dataclass(frozen=True, slots=True)
class DatasetId(StableId):
    """Identity of a controlled dataset."""


@dataclass(frozen=True, slots=True)
class UniverseId(StableId):
    """Identity of a reproducible universe definition or materialization."""


@dataclass(frozen=True, slots=True)
class FeatureDefinitionId(StableId):
    """Identity of a versioned feature definition."""


@dataclass(frozen=True, slots=True)
class FeatureMaterializationId(StableId):
    """Identity of concrete feature values under identified inputs."""


@dataclass(frozen=True, slots=True)
class TargetId(StableId):
    """Identity of a versioned research target contract."""


@dataclass(frozen=True, slots=True)
class ModelId(StableId):
    """Identity of a model or model artifact contract."""


@dataclass(frozen=True, slots=True)
class StrategyId(StableId):
    """Identity of a versioned strategy definition."""


@dataclass(frozen=True, slots=True)
class ExperimentId(StableId):
    """Identity of an experiment run or experiment configuration."""
