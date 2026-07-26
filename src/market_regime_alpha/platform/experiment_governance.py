"""Frozen experiment protocols, research budgets, and validation-access governance."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
from typing import Any, ClassVar

from market_regime_alpha.core.identity import (
    DatasetId,
    ExperimentId,
    FeatureDefinitionId,
    ModelId,
    TargetId,
    UniverseId,
)
from market_regime_alpha.platform.contracts import EvaluationProtocolId, ResearchHypothesisId


def _require_non_empty(label: str, value: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    if not value or value != value.strip():
        raise ValueError(f"{label} must be a non-empty trimmed string")


def _require_unique(label: str, values: tuple[object, ...]) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must not contain duplicate values")


class PrimaryChangeDimension(str, Enum):
    BASELINE_CREATION = "BASELINE_CREATION"
    FEATURE_SET = "FEATURE_SET"
    FEATURE_DEFINITION = "FEATURE_DEFINITION"
    MODEL_FORM = "MODEL_FORM"
    PARAMETER_SET = "PARAMETER_SET"
    TARGET = "TARGET"
    UNIVERSE = "UNIVERSE"
    ENTRY_POLICY = "ENTRY_POLICY"
    EXIT_POLICY = "EXIT_POLICY"
    PORTFOLIO_POLICY = "PORTFOLIO_POLICY"
    COST_MODEL = "COST_MODEL"


@dataclass(frozen=True, slots=True)
class ResearchHypothesis:
    hypothesis_id: ResearchHypothesisId
    statement: str
    rationale: str
    expected_result: str
    counter_evidence: tuple[str, ...]
    invalidation_condition: str

    def __post_init__(self) -> None:
        for label, value in (
            ("statement", self.statement),
            ("rationale", self.rationale),
            ("expected_result", self.expected_result),
            ("invalidation_condition", self.invalidation_condition),
        ):
            _require_non_empty(label, value)
        _require_unique("counter_evidence", self.counter_evidence)


@dataclass(frozen=True, slots=True)
class ExperimentBudget:
    max_parameter_variants: int = 3
    max_targets: int = 1
    max_validation_accesses: int = 1
    max_sealed_test_accesses: int = 1

    def __post_init__(self) -> None:
        for label, value in (
            ("max_parameter_variants", self.max_parameter_variants),
            ("max_targets", self.max_targets),
            ("max_validation_accesses", self.max_validation_accesses),
            ("max_sealed_test_accesses", self.max_sealed_test_accesses),
        ):
            if value <= 0:
                raise ValueError(f"{label} must be positive")


@dataclass(frozen=True, slots=True)
class FrozenExperimentProtocol:
    """Content-addressed protocol frozen before evaluation access."""

    SCHEMA_VERSION: ClassVar[str] = "frozen-experiment-protocol-v1"

    hypothesis: ResearchHypothesis
    model_id: ModelId
    parent_model_id: ModelId | None
    dataset_id: DatasetId
    universe_id: UniverseId
    target_ids: tuple[TargetId, ...]
    evaluation_protocol_id: EvaluationProtocolId
    feature_ids: tuple[FeatureDefinitionId, ...]
    parameter_variants: tuple[tuple[tuple[str, str], ...], ...]
    primary_change: PrimaryChangeDimension
    comparison_model_ids: tuple[ModelId, ...]
    sample_split_ref: str
    cost_model_ref: str
    code_revision: str
    environment_ref: str
    budget: ExperimentBudget = ExperimentBudget()

    def __post_init__(self) -> None:
        for label, value in (
            ("sample_split_ref", self.sample_split_ref),
            ("cost_model_ref", self.cost_model_ref),
            ("code_revision", self.code_revision),
            ("environment_ref", self.environment_ref),
        ):
            _require_non_empty(label, value)
        if not isinstance(self.primary_change, PrimaryChangeDimension):
            raise TypeError("primary_change must be a PrimaryChangeDimension")
        _require_unique("target_ids", self.target_ids)
        _require_unique("feature_ids", self.feature_ids)
        _require_unique("comparison_model_ids", self.comparison_model_ids)
        if not self.target_ids:
            raise ValueError("target_ids must not be empty")
        if len(self.target_ids) > self.budget.max_targets:
            raise ValueError("target count exceeds experiment budget")
        if not self.feature_ids:
            raise ValueError("feature_ids must not be empty")
        if not self.comparison_model_ids:
            raise ValueError("comparison_model_ids must not be empty")
        if len(self.parameter_variants) > self.budget.max_parameter_variants:
            raise ValueError("parameter variant count exceeds experiment budget")
        for variant in self.parameter_variants:
            keys = [key for key, _ in variant]
            if len(keys) != len(set(keys)):
                raise ValueError("parameter variant keys must be unique")
            for key, value in variant:
                _require_non_empty("parameter key", key)
                _require_non_empty(f"parameter {key!r}", value)
        if self.primary_change is not PrimaryChangeDimension.BASELINE_CREATION and self.parent_model_id is None:
            raise ValueError("challenger experiment requires parent_model_id")
        if self.parent_model_id == self.model_id:
            raise ValueError("model cannot be its own parent")

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "hypothesis": {
                "hypothesis_id": str(self.hypothesis.hypothesis_id),
                "statement": self.hypothesis.statement,
                "rationale": self.hypothesis.rationale,
                "expected_result": self.hypothesis.expected_result,
                "counter_evidence": list(self.hypothesis.counter_evidence),
                "invalidation_condition": self.hypothesis.invalidation_condition,
            },
            "model_id": str(self.model_id),
            "parent_model_id": str(self.parent_model_id) if self.parent_model_id else None,
            "dataset_id": str(self.dataset_id),
            "universe_id": str(self.universe_id),
            "target_ids": [str(item) for item in self.target_ids],
            "evaluation_protocol_id": str(self.evaluation_protocol_id),
            "feature_ids": [str(item) for item in self.feature_ids],
            "parameter_variants": [
                [[key, value] for key, value in sorted(variant)]
                for variant in self.parameter_variants
            ],
            "primary_change": self.primary_change.value,
            "comparison_model_ids": [str(item) for item in self.comparison_model_ids],
            "sample_split_ref": self.sample_split_ref,
            "cost_model_ref": self.cost_model_ref,
            "code_revision": self.code_revision,
            "environment_ref": self.environment_ref,
            "budget": {
                "max_parameter_variants": self.budget.max_parameter_variants,
                "max_targets": self.budget.max_targets,
                "max_validation_accesses": self.budget.max_validation_accesses,
                "max_sealed_test_accesses": self.budget.max_sealed_test_accesses,
            },
        }

    @property
    def protocol_hash(self) -> str:
        canonical = json.dumps(self.canonical_payload(), ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        return sha256(canonical.encode("utf-8")).hexdigest()

    @property
    def experiment_id(self) -> ExperimentId:
        return ExperimentId(f"platform-exp-{self.protocol_hash[:24]}")


@dataclass(frozen=True, slots=True)
class ExperimentAccessRecord:
    experiment_id: ExperimentId
    validation_access_count: int = 0
    sealed_test_access_count: int = 0


class ExperimentGovernance:
    """In-memory authority for frozen protocols and scarce evaluation access."""

    def __init__(self) -> None:
        self._protocols: dict[ExperimentId, FrozenExperimentProtocol] = {}
        self._access: dict[ExperimentId, ExperimentAccessRecord] = {}

    def register(self, protocol: FrozenExperimentProtocol) -> ExperimentId:
        experiment_id = protocol.experiment_id
        existing = self._protocols.get(experiment_id)
        if existing is not None and existing != protocol:
            raise ValueError(f"experiment identity conflict: {experiment_id}")
        self._protocols[experiment_id] = protocol
        self._access.setdefault(experiment_id, ExperimentAccessRecord(experiment_id))
        return experiment_id

    def get(self, experiment_id: ExperimentId) -> FrozenExperimentProtocol:
        try:
            return self._protocols[experiment_id]
        except KeyError as exc:
            raise KeyError(str(experiment_id)) from exc

    def access_record(self, experiment_id: ExperimentId) -> ExperimentAccessRecord:
        try:
            return self._access[experiment_id]
        except KeyError as exc:
            raise KeyError(str(experiment_id)) from exc

    def record_validation_access(self, experiment_id: ExperimentId) -> ExperimentAccessRecord:
        protocol = self.get(experiment_id)
        record = self.access_record(experiment_id)
        if record.validation_access_count >= protocol.budget.max_validation_accesses:
            raise ValueError("validation access budget exhausted")
        updated = ExperimentAccessRecord(
            experiment_id=experiment_id,
            validation_access_count=record.validation_access_count + 1,
            sealed_test_access_count=record.sealed_test_access_count,
        )
        self._access[experiment_id] = updated
        return updated

    def record_sealed_test_access(self, experiment_id: ExperimentId) -> ExperimentAccessRecord:
        protocol = self.get(experiment_id)
        record = self.access_record(experiment_id)
        if record.sealed_test_access_count >= protocol.budget.max_sealed_test_accesses:
            raise ValueError("sealed-test access budget exhausted")
        updated = ExperimentAccessRecord(
            experiment_id=experiment_id,
            validation_access_count=record.validation_access_count,
            sealed_test_access_count=record.sealed_test_access_count + 1,
        )
        self._access[experiment_id] = updated
        return updated
