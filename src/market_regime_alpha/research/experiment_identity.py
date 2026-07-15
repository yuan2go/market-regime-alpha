"""Project-wide experiment identity contract.

The contract generalizes the identity discipline proven useful in Legacy MACD research
without importing Legacy strategy semantics or creating a second experiment ontology.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, ClassVar

from market_regime_alpha.core.identity import (
    DatasetId,
    ExperimentId,
    FeatureDefinitionId,
    FeatureMaterializationId,
    ModelId,
    StrategyId,
    TargetId,
    UniverseId,
)


def _require_non_empty(label: str, value: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    if not value or value != value.strip():
        raise ValueError(f"{label} must be a non-empty trimmed string")


def _require_unique(label: str, values: tuple[object, ...]) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must not contain duplicate values")


def _validate_semantic_refs(values: tuple[tuple[str, str], ...]) -> None:
    keys: list[str] = []
    for key, value in values:
        _require_non_empty("semantic reference key", key)
        _require_non_empty(f"semantic reference {key!r}", value)
        keys.append(key)
    if len(keys) != len(set(keys)):
        raise ValueError("semantic_refs must not contain duplicate keys")


@dataclass(frozen=True, slots=True)
class ExperimentIdentity:
    """Immutable identity of result-affecting experiment semantics.

    The initial kernel intentionally stays small. Additional result-affecting semantics
    can be carried through ``semantic_refs`` until a dedicated canonical contract is
    justified. Reference order is preserved because order may itself be meaningful.
    """

    SCHEMA_VERSION: ClassVar[str] = "experiment-identity-v1"

    code_revision: str
    dataset_id: DatasetId
    config_hash: str
    universe_id: UniverseId | None = None
    target_id: TargetId | None = None
    feature_definition_ids: tuple[FeatureDefinitionId, ...] = ()
    feature_materialization_ids: tuple[FeatureMaterializationId, ...] = ()
    model_id: ModelId | None = None
    strategy_id: StrategyId | None = None
    parent_experiment_ids: tuple[ExperimentId, ...] = ()
    execution_assumption_ref: str | None = None
    environment_ref: str | None = None
    semantic_refs: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        _require_non_empty("code_revision", self.code_revision)
        _require_non_empty("config_hash", self.config_hash)
        _require_unique("feature_definition_ids", self.feature_definition_ids)
        _require_unique("feature_materialization_ids", self.feature_materialization_ids)
        _require_unique("parent_experiment_ids", self.parent_experiment_ids)
        if self.execution_assumption_ref is not None:
            _require_non_empty("execution_assumption_ref", self.execution_assumption_ref)
        if self.environment_ref is not None:
            _require_non_empty("environment_ref", self.environment_ref)
        _validate_semantic_refs(self.semantic_refs)

    def canonical_payload(self) -> dict[str, Any]:
        """Return the canonical JSON-serializable identity payload."""

        return {
            "schema_version": self.SCHEMA_VERSION,
            "code_revision": self.code_revision,
            "dataset_id": str(self.dataset_id),
            "config_hash": self.config_hash,
            "universe_id": str(self.universe_id) if self.universe_id is not None else None,
            "target_id": str(self.target_id) if self.target_id is not None else None,
            "feature_definition_ids": [str(value) for value in self.feature_definition_ids],
            "feature_materialization_ids": [str(value) for value in self.feature_materialization_ids],
            "model_id": str(self.model_id) if self.model_id is not None else None,
            "strategy_id": str(self.strategy_id) if self.strategy_id is not None else None,
            "parent_experiment_ids": [str(value) for value in self.parent_experiment_ids],
            "execution_assumption_ref": self.execution_assumption_ref,
            "environment_ref": self.environment_ref,
            "semantic_refs": [[key, value] for key, value in sorted(self.semantic_refs)],
        }

    def to_canonical_json(self) -> str:
        """Serialize identity deterministically for hashing and artifact references."""

        return json.dumps(
            self.canonical_payload(),
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )

    @property
    def identity_hash(self) -> str:
        """SHA-256 hash of the canonical experiment identity payload."""

        return sha256(self.to_canonical_json().encode("utf-8")).hexdigest()

    @property
    def experiment_id(self) -> ExperimentId:
        """Content-derived experiment ID for the initial V2 kernel."""

        return ExperimentId(f"exp-{self.identity_hash[:24]}")
