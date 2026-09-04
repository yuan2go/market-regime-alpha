"""Minimal immutable Model and training lineage for exploratory research."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
import re
from uuid import UUID

from market_regime_alpha.research_qualification.domain.model import ArtifactBinding
from market_regime_alpha.shared.financial import bounded_decimal
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.identity import ContentHash


_CODE = re.compile(r"^[a-z][a-z0-9_-]{0,99}$")
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_REASON = re.compile(r"^[A-Z][A-Z0-9_]{0,99}$")


class ModelTrainingSampleState(StrEnum):
    ESTIMABLE = "ESTIMABLE"
    NOT_ESTIMABLE = "NOT_ESTIMABLE"


class ModelScalarType(StrEnum):
    DECIMAL = "DECIMAL"
    INTEGER = "INTEGER"
    BOOLEAN = "BOOLEAN"
    TEXT = "TEXT"


@dataclass(frozen=True, slots=True)
class ModelScalarParameter:
    ordinal: int
    parameter_code: str
    value_type: ModelScalarType
    decimal_value: Decimal | None = None
    integer_value: int | None = None
    boolean_value: bool | None = None
    text_value: str | None = None
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        if isinstance(self.ordinal, bool) or self.ordinal < 1:
            raise ValueError("Model parameter ordinal must be positive")
        if not _CODE.fullmatch(self.parameter_code):
            raise ValueError("Model parameter_code is invalid")
        values = (
            self.decimal_value,
            self.integer_value,
            self.boolean_value,
            self.text_value,
        )
        if sum(value is not None for value in values) != 1:
            raise ValueError("Model parameter requires exactly one typed value")
        expected = {
            ModelScalarType.DECIMAL: self.decimal_value,
            ModelScalarType.INTEGER: self.integer_value,
            ModelScalarType.BOOLEAN: self.boolean_value,
            ModelScalarType.TEXT: self.text_value,
        }[self.value_type]
        if expected is None:
            raise ValueError("Model parameter value does not match value_type")
        if self.decimal_value is not None and not self.decimal_value.is_finite():
            raise ValueError("Model decimal parameter must be finite")
        if isinstance(self.integer_value, bool):
            raise TypeError("Model integer parameter cannot be bool")
        if self.text_value is not None and not self.text_value:
            raise ValueError("Model text parameter cannot be empty")
        decimal_value = (
            None
            if self.decimal_value is None
            else bounded_decimal(
                self.decimal_value,
                field="model scalar parameter",
                precision=48,
                scale=18,
            )
        )
        object.__setattr__(self, "decimal_value", decimal_value)
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(
                canonical_json_sha256(
                    {
                        "boolean_value": self.boolean_value,
                        "decimal_value": decimal_value,
                        "integer_value": self.integer_value,
                        "ordinal": self.ordinal,
                        "parameter_code": self.parameter_code,
                        "text_value": self.text_value,
                        "value_type": self.value_type,
                    }
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class ModelDependencyVersion:
    ordinal: int
    package_name: str
    package_version: str
    distribution_sha256: ContentHash | str
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        if isinstance(self.ordinal, bool) or self.ordinal < 1:
            raise ValueError("Model dependency ordinal must be positive")
        if not _CODE.fullmatch(self.package_name):
            raise ValueError("Model dependency package_name is invalid")
        if not _VERSION.fullmatch(self.package_version):
            raise ValueError("Model dependency package_version is invalid")
        distribution_hash = ContentHash(str(self.distribution_sha256))
        object.__setattr__(self, "distribution_sha256", distribution_hash)
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(
                canonical_json_sha256(
                    {
                        "distribution_sha256": str(distribution_hash),
                        "ordinal": self.ordinal,
                        "package_name": self.package_name,
                        "package_version": self.package_version,
                    }
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class ModelExecutionEnvironment:
    python_implementation: str
    python_version: str
    runtime_code: str
    runtime_version: str
    uv_lock_sha256: ContentHash | str
    dependencies: tuple[ModelDependencyVersion, ...]
    dependency_roster_sha256: ContentHash = field(init=False)
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        if not _CODE.fullmatch(self.python_implementation):
            raise ValueError("Python implementation code is invalid")
        if not _VERSION.fullmatch(self.python_version):
            raise ValueError("Python version is invalid")
        if not _CODE.fullmatch(self.runtime_code):
            raise ValueError("runtime code is invalid")
        if not _VERSION.fullmatch(self.runtime_version):
            raise ValueError("runtime version is invalid")
        if not self.dependencies:
            raise ValueError("Model dependency roster must be non-empty")
        if tuple(item.ordinal for item in self.dependencies) != tuple(range(1, len(self.dependencies) + 1)) or len(
            {item.package_name for item in self.dependencies}
        ) != len(self.dependencies):
            raise ValueError("Model dependency roster must be ordered and unique")
        lock_hash = ContentHash(str(self.uv_lock_sha256))
        roster_hash = ContentHash(
            canonical_json_sha256(
                tuple(
                    {
                        "content_sha256": str(item.content_sha256),
                        "ordinal": item.ordinal,
                        "package_name": item.package_name,
                    }
                    for item in self.dependencies
                )
            )
        )
        object.__setattr__(self, "uv_lock_sha256", lock_hash)
        object.__setattr__(self, "dependency_roster_sha256", roster_hash)
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(
                canonical_json_sha256(
                    {
                        "dependency_roster_sha256": str(roster_hash),
                        "python_implementation": self.python_implementation,
                        "python_version": self.python_version,
                        "runtime_code": self.runtime_code,
                        "runtime_version": self.runtime_version,
                        "uv_lock_sha256": str(lock_hash),
                    }
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class ModelTrainingReproducibility:
    model_training_run_id: UUID
    training_knowledge_cutoff: datetime
    implementation_sha256: ContentHash | str
    environment: ModelExecutionEnvironment
    hyperparameters: tuple[ModelScalarParameter, ...]
    hyperparameter_roster_sha256: ContentHash = field(init=False)
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        if self.training_knowledge_cutoff.tzinfo is None:
            raise ValueError("training knowledge cutoff must be timezone-aware")
        knowledge_cutoff = self.training_knowledge_cutoff.astimezone(UTC)
        if tuple(item.ordinal for item in self.hyperparameters) != tuple(range(1, len(self.hyperparameters) + 1)) or len(
            {item.parameter_code for item in self.hyperparameters}
        ) != len(self.hyperparameters):
            raise ValueError("Model hyperparameter roster must be ordered and unique")
        implementation_hash = ContentHash(str(self.implementation_sha256))
        roster_hash = ContentHash(
            canonical_json_sha256(
                tuple(
                    {
                        "content_sha256": str(item.content_sha256),
                        "ordinal": item.ordinal,
                        "parameter_code": item.parameter_code,
                    }
                    for item in self.hyperparameters
                )
            )
        )
        object.__setattr__(self, "implementation_sha256", implementation_hash)
        object.__setattr__(self, "training_knowledge_cutoff", knowledge_cutoff)
        object.__setattr__(self, "hyperparameter_roster_sha256", roster_hash)
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(
                canonical_json_sha256(
                    {
                        "environment_sha256": str(self.environment.content_sha256),
                        "hyperparameter_roster_sha256": str(roster_hash),
                        "implementation_sha256": str(implementation_hash),
                        "model_training_run_id": self.model_training_run_id,
                        "training_knowledge_cutoff": knowledge_cutoff,
                    }
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class LinearTrainingRow:
    model_training_sample_id: UUID
    features: tuple[Decimal, ...]
    target: Decimal


@dataclass(frozen=True, slots=True)
class ResearchModelPlan:
    """Stable family identity; versions remain optional children."""

    model_id: UUID
    model_code: str
    target_definition_id: UUID
    target_version: int
    target_definition_sha256: ContentHash | str
    feature_definitions: tuple[tuple[UUID, ContentHash | str], ...]
    code_artifact: ArtifactBinding
    config_artifact: ArtifactBinding
    provenance_sha256: ContentHash | str
    feature_count: int = field(init=False)
    feature_roster_sha256: ContentHash = field(init=False)
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        if not _CODE.fullmatch(self.model_code):
            raise ValueError("model_code has an invalid format")
        if isinstance(self.target_version, bool) or self.target_version < 1:
            raise ValueError("target_version must be positive")
        if not self.feature_definitions:
            raise ValueError("Model feature roster must be non-empty")
        normalized = tuple((identity, ContentHash(str(content_hash))) for identity, content_hash in self.feature_definitions)
        if len({item[0] for item in normalized}) != len(normalized):
            raise ValueError("Model feature roster must be unique and ordered")
        target_hash = ContentHash(str(self.target_definition_sha256))
        provenance_hash = ContentHash(str(self.provenance_sha256))
        roster_hash = ContentHash(
            canonical_json_sha256(
                tuple(
                    {
                        "feature_definition_id": identity,
                        "feature_definition_sha256": str(content_hash),
                        "ordinal": ordinal,
                    }
                    for ordinal, (identity, content_hash) in enumerate(normalized, start=1)
                )
            )
        )
        object.__setattr__(self, "feature_definitions", normalized)
        object.__setattr__(self, "target_definition_sha256", target_hash)
        object.__setattr__(self, "provenance_sha256", provenance_hash)
        object.__setattr__(self, "feature_count", len(normalized))
        object.__setattr__(self, "feature_roster_sha256", roster_hash)
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(
                canonical_json_sha256(
                    {
                        "code_artifact": self.code_artifact,
                        "config_artifact": self.config_artifact,
                        "feature_roster_sha256": roster_hash,
                        "model_code": self.model_code,
                        "provenance_sha256": provenance_hash,
                        "target_definition_id": self.target_definition_id,
                        "target_definition_sha256": target_hash,
                        "target_version": self.target_version,
                    }
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class ModelTrainingSamplePlan:
    """One member of the complete DB-derived FIT Evaluation roster."""

    model_training_sample_id: UUID
    ordinal: int
    evaluation_observation_id: UUID
    evaluation_metric_observation_id: UUID
    research_partition_member_id: UUID
    commitment_id: UUID
    decision_run_id: UUID
    candidate_id: UUID
    instrument_id: UUID
    dataset_id: UUID
    dataset_manifest_artifact: ArtifactBinding
    market_target_outcome_revision_id: UUID
    source_outcome_metric_id: UUID
    evaluation_input_state: str
    state: ModelTrainingSampleState
    reason_code: str
    target_value: Decimal | None
    feature_vector_sha256: ContentHash | str | None
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        if isinstance(self.ordinal, bool) or self.ordinal < 1:
            raise ValueError("ModelTrainingSample ordinal must be positive")
        if not isinstance(self.state, ModelTrainingSampleState):
            raise TypeError("state must be ModelTrainingSampleState")
        if not _REASON.fullmatch(self.reason_code):
            raise ValueError("reason_code has an invalid format")
        if self.evaluation_input_state not in {
            "INCLUDED",
            "EXCLUDED",
            "NOT_ESTIMABLE",
        }:
            raise ValueError("evaluation_input_state is invalid")
        vector_hash = None if self.feature_vector_sha256 is None else ContentHash(str(self.feature_vector_sha256))
        target_value = self.target_value
        if self.state is ModelTrainingSampleState.ESTIMABLE:
            if self.evaluation_input_state != "INCLUDED":
                raise ValueError("ESTIMABLE sample requires INCLUDED Evaluation input")
            if target_value is None or vector_hash is None:
                raise ValueError("ESTIMABLE sample requires target and feature values")
            target_value = bounded_decimal(
                target_value,
                field="target_value",
                precision=48,
                scale=18,
            )
        elif target_value is not None or vector_hash is not None:
            raise ValueError("NOT_ESTIMABLE sample cannot contain target or feature values")
        object.__setattr__(self, "target_value", target_value)
        object.__setattr__(self, "feature_vector_sha256", vector_hash)
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(
                canonical_json_sha256(
                    {
                        "candidate_id": self.candidate_id,
                        "commitment_id": self.commitment_id,
                        "dataset_id": self.dataset_id,
                        "dataset_manifest_artifact": self.dataset_manifest_artifact,
                        "decision_run_id": self.decision_run_id,
                        "evaluation_metric_observation_id": self.evaluation_metric_observation_id,
                        "evaluation_input_state": self.evaluation_input_state,
                        "evaluation_observation_id": self.evaluation_observation_id,
                        "feature_vector_sha256": vector_hash,
                        "instrument_id": self.instrument_id,
                        "market_target_outcome_revision_id": self.market_target_outcome_revision_id,
                        "ordinal": self.ordinal,
                        "reason_code": self.reason_code,
                        "research_partition_member_id": self.research_partition_member_id,
                        "source_outcome_metric_id": self.source_outcome_metric_id,
                        "state": self.state,
                        "target_value": target_value,
                    }
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class ModelTrainingRunPlan:
    model_training_run_id: UUID
    model_id: UUID
    evaluation_run_id: UUID
    evaluation_protocol_metric_id: UUID
    exploratory_backtest_run_id: UUID
    exploratory_backtest_arm_id: UUID
    exploratory_backtest_fold_id: UUID
    algorithm_code: str
    algorithm_version: str
    algorithm_sha256: ContentHash | str
    # Retained only to reproduce historical deterministic-ridge rows/hashes.
    # Current model-family semantics live in the typed hyperparameter closure.
    ridge_alpha: Decimal | None
    random_seed: int
    training_input_artifact: ArtifactBinding
    code_artifact: ArtifactBinding
    config_artifact: ArtifactBinding
    provenance_sha256: ContentHash | str
    samples: tuple[ModelTrainingSamplePlan, ...]
    sample_count: int = field(init=False)
    estimable_count: int = field(init=False)
    sample_roster_sha256: ContentHash = field(init=False)
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        if not _CODE.fullmatch(self.algorithm_code):
            raise ValueError("algorithm_code has an invalid format")
        if not _VERSION.fullmatch(self.algorithm_version):
            raise ValueError("algorithm_version has an invalid format")
        if self.algorithm_code == "deterministic_ridge" and self.ridge_alpha is None:
            raise ValueError("historical deterministic_ridge contract requires ridge_alpha")
        alpha = (
            bounded_decimal(
                self.ridge_alpha,
                field="ridge_alpha",
                precision=24,
                scale=12,
            )
            if self.ridge_alpha is not None
            else None
        )
        if alpha is not None and alpha < 0:
            raise ValueError("ridge_alpha must be non-negative")
        if isinstance(self.random_seed, bool) or self.random_seed < 0:
            raise ValueError("random_seed must be non-negative")
        if not self.samples:
            raise ValueError("ModelTrainingRun sample roster must be non-empty")
        if tuple(item.ordinal for item in self.samples) != tuple(range(1, len(self.samples) + 1)):
            raise ValueError("ModelTrainingRun sample ordinals must be contiguous")
        if len({item.evaluation_observation_id for item in self.samples}) != len(self.samples):
            raise ValueError("ModelTrainingRun samples must be unique")
        estimable_count = sum(item.state is ModelTrainingSampleState.ESTIMABLE for item in self.samples)
        if estimable_count < 2:
            raise ValueError("ModelTrainingRun requires at least two estimable samples")
        algorithm_hash = ContentHash(str(self.algorithm_sha256))
        provenance_hash = ContentHash(str(self.provenance_sha256))
        roster_hash = ContentHash(
            canonical_json_sha256(
                tuple(
                    {
                        "content_sha256": str(item.content_sha256),
                        "model_training_sample_id": item.model_training_sample_id,
                        "ordinal": item.ordinal,
                    }
                    for item in self.samples
                )
            )
        )
        object.__setattr__(self, "ridge_alpha", alpha)
        object.__setattr__(self, "algorithm_sha256", algorithm_hash)
        object.__setattr__(self, "provenance_sha256", provenance_hash)
        object.__setattr__(self, "sample_count", len(self.samples))
        object.__setattr__(self, "estimable_count", estimable_count)
        object.__setattr__(self, "sample_roster_sha256", roster_hash)
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(
                canonical_json_sha256(
                    {
                        "algorithm_code": self.algorithm_code,
                        "algorithm_sha256": algorithm_hash,
                        "algorithm_version": self.algorithm_version,
                        "code_artifact": self.code_artifact,
                        "config_artifact": self.config_artifact,
                        "estimable_count": estimable_count,
                        "evaluation_protocol_metric_id": self.evaluation_protocol_metric_id,
                        "evaluation_run_id": self.evaluation_run_id,
                        "exploratory_backtest_arm_id": self.exploratory_backtest_arm_id,
                        "exploratory_backtest_fold_id": self.exploratory_backtest_fold_id,
                        "exploratory_backtest_run_id": self.exploratory_backtest_run_id,
                        "model_id": self.model_id,
                        "provenance_sha256": provenance_hash,
                        "random_seed": self.random_seed,
                        "ridge_alpha": alpha,
                        "sample_roster_sha256": roster_hash,
                        "training_input_artifact": self.training_input_artifact,
                    }
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class ReproducibleModelTrainingRunPlan:
    """Registration envelope; not a second ModelTrainingRun identity."""

    training_run: ModelTrainingRunPlan
    reproducibility: ModelTrainingReproducibility
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        if (
            self.reproducibility.model_training_run_id != self.training_run.model_training_run_id
            or self.reproducibility.implementation_sha256 != self.training_run.algorithm_sha256
        ):
            raise ValueError("Model reproducibility closure differs from training identity")
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(
                canonical_json_sha256(
                    {
                        "model_training_run_sha256": str(self.training_run.content_sha256),
                        "reproducibility_sha256": str(self.reproducibility.content_sha256),
                    }
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class ModelVersionPlan:
    model_version_id: UUID
    model_id: UUID
    version: int
    model_training_run_id: UUID
    training_input_artifact: ArtifactBinding
    fitted_model_artifact: ArtifactBinding
    coefficient_count: int
    fitted_model_sha256: ContentHash | str
    code_artifact: ArtifactBinding
    config_artifact: ArtifactBinding
    provenance_sha256: ContentHash | str
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        if isinstance(self.version, bool) or self.version < 1:
            raise ValueError("ModelVersion version must be positive")
        if isinstance(self.coefficient_count, bool) or self.coefficient_count < 1:
            raise ValueError("coefficient_count must be positive")
        fitted_hash = ContentHash(str(self.fitted_model_sha256))
        if fitted_hash != self.fitted_model_artifact.content_sha256:
            raise ValueError("fitted_model_sha256 must equal exact Artifact bytes")
        provenance_hash = ContentHash(str(self.provenance_sha256))
        object.__setattr__(self, "fitted_model_sha256", fitted_hash)
        object.__setattr__(self, "provenance_sha256", provenance_hash)
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(
                canonical_json_sha256(
                    {
                        "code_artifact": self.code_artifact,
                        "coefficient_count": self.coefficient_count,
                        "config_artifact": self.config_artifact,
                        "fitted_model_artifact": self.fitted_model_artifact,
                        "model_id": self.model_id,
                        "model_training_run_id": self.model_training_run_id,
                        "provenance_sha256": provenance_hash,
                        "training_input_artifact": self.training_input_artifact,
                        "version": self.version,
                    }
                )
            ),
        )


__all__ = [
    "LinearTrainingRow",
    "ModelDependencyVersion",
    "ModelExecutionEnvironment",
    "ModelScalarParameter",
    "ModelScalarType",
    "ModelTrainingReproducibility",
    "ModelTrainingRunPlan",
    "ModelTrainingSamplePlan",
    "ModelTrainingSampleState",
    "ModelVersionPlan",
    "ResearchModelPlan",
    "ReproducibleModelTrainingRunPlan",
]
