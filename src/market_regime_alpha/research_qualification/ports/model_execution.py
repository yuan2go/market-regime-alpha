"""Narrow infrastructure contracts for explicitly composed Model families."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
import re
from typing import Protocol
from uuid import UUID

from market_regime_alpha.research_qualification.domain.research_models import (
    LinearTrainingRow,
)
from market_regime_alpha.shared.identity import ContentHash


_PARAMETER = re.compile(r"^[a-z][a-z0-9_]{0,99}$")


class ModelScalarType(StrEnum):
    DECIMAL = "DECIMAL"
    INTEGER = "INTEGER"
    BOOLEAN = "BOOLEAN"
    TEXT = "TEXT"


@dataclass(frozen=True, slots=True)
class ModelScalarParameter:
    parameter_code: str
    value_type: ModelScalarType
    decimal_value: Decimal | None = None
    integer_value: int | None = None
    boolean_value: bool | None = None
    text_value: str | None = None

    def __post_init__(self) -> None:
        if not _PARAMETER.fullmatch(self.parameter_code):
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


@dataclass(frozen=True, slots=True)
class FrozenModelTrainingInput:
    algorithm_code: str
    algorithm_version: str
    implementation_sha256: ContentHash | str
    feature_definition_ids: tuple[UUID, ...]
    hyperparameters: tuple[ModelScalarParameter, ...]
    seed: int
    rows: tuple[LinearTrainingRow, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "implementation_sha256", ContentHash(str(self.implementation_sha256))
        )
        if not self.feature_definition_ids or len(set(self.feature_definition_ids)) != len(
            self.feature_definition_ids
        ):
            raise ValueError("Model training Feature roster must be non-empty and unique")
        if len({item.parameter_code for item in self.hyperparameters}) != len(
            self.hyperparameters
        ):
            raise ValueError("Model training parameter roster contains duplicates")
        if isinstance(self.seed, bool) or self.seed < 0:
            raise ValueError("Model training seed must be non-negative")


@dataclass(frozen=True, slots=True)
class FittedModelPayload:
    content: bytes
    content_sha256: ContentHash | str
    coefficient_count: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "content_sha256", ContentHash(str(self.content_sha256))
        )
        if isinstance(self.coefficient_count, bool) or self.coefficient_count < 1:
            raise ValueError("fitted Model coefficient_count must be positive")


@dataclass(frozen=True, slots=True)
class FrozenModelVersionPayload:
    algorithm_code: str
    algorithm_version: str
    implementation_sha256: ContentHash | str
    fitted_content: bytes
    fitted_content_sha256: ContentHash | str
    feature_definition_ids: tuple[UUID, ...]
    hyperparameters: tuple[ModelScalarParameter, ...]
    seed: int
    coefficient_count: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "implementation_sha256", ContentHash(str(self.implementation_sha256))
        )
        object.__setattr__(
            self, "fitted_content_sha256", ContentHash(str(self.fitted_content_sha256))
        )
        if not self.feature_definition_ids or len(set(self.feature_definition_ids)) != len(
            self.feature_definition_ids
        ):
            raise ValueError("ModelVersion Feature roster must be non-empty and unique")
        if len({item.parameter_code for item in self.hyperparameters}) != len(
            self.hyperparameters
        ):
            raise ValueError("ModelVersion parameter roster contains duplicates")
        if isinstance(self.seed, bool) or self.seed < 0:
            raise ValueError("ModelVersion seed must be non-negative")
        if isinstance(self.coefficient_count, bool) or self.coefficient_count < 1:
            raise ValueError("ModelVersion coefficient_count must be positive")


@dataclass(frozen=True, slots=True)
class ModelPredictionRow:
    row_id: UUID
    features: tuple[Decimal, ...]


@dataclass(frozen=True, slots=True)
class ModelPredictionBatch:
    rows: tuple[ModelPredictionRow, ...]

    def __post_init__(self) -> None:
        if not self.rows or len({item.row_id for item in self.rows}) != len(self.rows):
            raise ValueError("Model prediction rows must be non-empty and unique")


@dataclass(frozen=True, slots=True)
class ModelPrediction:
    row_id: UUID
    point_estimate: Decimal


class ModelTrainer(Protocol):
    def fit(self, training: FrozenModelTrainingInput) -> FittedModelPayload: ...


class ModelPredictor(Protocol):
    def predict(
        self,
        model: FrozenModelVersionPayload,
        batch: ModelPredictionBatch,
    ) -> tuple[ModelPrediction, ...]: ...


__all__ = [
    "FittedModelPayload",
    "FrozenModelTrainingInput",
    "FrozenModelVersionPayload",
    "ModelPrediction",
    "ModelPredictionBatch",
    "ModelPredictionRow",
    "ModelPredictor",
    "ModelScalarParameter",
    "ModelScalarType",
    "ModelTrainer",
]
