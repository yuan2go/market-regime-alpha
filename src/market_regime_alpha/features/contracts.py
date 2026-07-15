"""Canonical feature definition, materialization, and registry contracts.

A Feature Definition is not one materialized dataset. Missing values are not neutral
values. Registration does not promote a feature into a Predictive Factor.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from market_regime_alpha.core.identity import (
    DatasetId,
    FeatureDefinitionId,
    FeatureMaterializationId,
    UniverseId,
)
from market_regime_alpha.core.status import InputAvailabilityStatus
from market_regime_alpha.core.time import AsOfTime


def _require_non_empty(label: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{label} must be a non-empty trimmed string")


@dataclass(frozen=True, slots=True)
class FeatureDefinition:
    """Versioned semantic and computational identity of a feature."""

    feature_id: FeatureDefinitionId
    name: str
    semantic_family: str
    source_information_families: tuple[str, ...]
    representation_method: str
    value_type: str = "float"
    parameters: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        for label, value in (
            ("name", self.name),
            ("semantic_family", self.semantic_family),
            ("representation_method", self.representation_method),
            ("value_type", self.value_type),
        ):
            _require_non_empty(label, value)
        if not self.source_information_families:
            raise ValueError("source_information_families must not be empty")
        if len(self.source_information_families) != len(set(self.source_information_families)):
            raise ValueError("source_information_families must be unique")
        parameter_keys = [key for key, _ in self.parameters]
        if len(parameter_keys) != len(set(parameter_keys)):
            raise ValueError("feature parameters must have unique keys")


@dataclass(frozen=True, slots=True)
class FeatureObservation:
    """One symbol-level feature observation with explicit availability semantics."""

    symbol: str
    status: InputAvailabilityStatus
    value: Any | None

    def __post_init__(self) -> None:
        if not isinstance(self.symbol, str) or not self.symbol.strip() or self.symbol != self.symbol.strip():
            raise ValueError("symbol must be a non-empty trimmed string")
        if self.status is InputAvailabilityStatus.AVAILABLE and self.value is None:
            raise ValueError("AVAILABLE feature observation requires a value")
        if self.status is not InputAvailabilityStatus.AVAILABLE and self.value is not None:
            raise ValueError("unavailable feature observation must not carry a usable value")


@dataclass(frozen=True, slots=True)
class FeatureMaterialization:
    """Concrete feature values under identified data, universe, code, and config."""

    materialization_id: FeatureMaterializationId
    definition_id: FeatureDefinitionId
    dataset_id: DatasetId
    universe_id: UniverseId
    as_of: AsOfTime
    code_revision: str
    config_hash: str
    observations: tuple[FeatureObservation, ...]

    def __post_init__(self) -> None:
        _require_non_empty("code_revision", self.code_revision)
        _require_non_empty("config_hash", self.config_hash)
        symbols = [observation.symbol for observation in self.observations]
        if len(symbols) != len(set(symbols)):
            raise ValueError("feature observations must have unique symbols")

    @property
    def available_symbols(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                observation.symbol
                for observation in self.observations
                if observation.status is InputAvailabilityStatus.AVAILABLE
            )
        )


class FeatureRegistry:
    """Minimal in-memory authority for registered Feature Definitions.

    Persistence is intentionally unspecified. The first implementation exists to freeze
    identity and conflict semantics required by Candidate research.
    """

    def __init__(self) -> None:
        self._definitions: dict[FeatureDefinitionId, FeatureDefinition] = {}

    def register(self, definition: FeatureDefinition) -> FeatureDefinition:
        existing = self._definitions.get(definition.feature_id)
        if existing is not None and existing != definition:
            raise ValueError(f"feature identity conflict: {definition.feature_id}")
        self._definitions[definition.feature_id] = definition
        return definition

    def get(self, feature_id: FeatureDefinitionId) -> FeatureDefinition:
        try:
            return self._definitions[feature_id]
        except KeyError as exc:
            raise KeyError(str(feature_id)) from exc

    def __len__(self) -> int:
        return len(self._definitions)
