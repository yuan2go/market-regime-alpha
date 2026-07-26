"""Canonical Target and Evaluation protocols for model-comparison lanes."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
from typing import Any, ClassVar

from market_regime_alpha.core.identity import ModelId, TargetId, UniverseId
from market_regime_alpha.platform.contracts import EvaluationProtocolId, MetricId, ModelRole


def _require_non_empty(label: str, value: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    if not value or value != value.strip():
        raise ValueError(f"{label} must be a non-empty trimmed string")


def _require_unique(label: str, values: tuple[object, ...]) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must not contain duplicate values")


class TargetKind(str, Enum):
    RETURN = "RETURN"
    RELATIVE_RETURN = "RELATIVE_RETURN"
    MFE = "MFE"
    MAE = "MAE"
    PATH_EVENT = "PATH_EVENT"
    TIME_TO_EVENT = "TIME_TO_EVENT"


class PriceMark(str, Enum):
    DECISION_PRICE = "DECISION_PRICE"
    NEXT_OPEN = "NEXT_OPEN"
    NEXT_1030 = "NEXT_1030"
    NEXT_1445 = "NEXT_1445"
    NEXT_CLOSE = "NEXT_CLOSE"
    SESSION_HIGH = "SESSION_HIGH"
    SESSION_LOW = "SESSION_LOW"
    HORIZON_CLOSE = "HORIZON_CLOSE"


class ReturnBasis(str, Enum):
    ABSOLUTE = "ABSOLUTE"
    BENCHMARK_RELATIVE = "BENCHMARK_RELATIVE"
    UNIVERSE_RELATIVE = "UNIVERSE_RELATIVE"


class MissingTargetPolicy(str, Enum):
    EXCLUDE_WITH_REASON = "EXCLUDE_WITH_REASON"
    FAIL_SCOPE = "FAIL_SCOPE"
    RETAIN_AS_UNRESOLVED = "RETAIN_AS_UNRESOLVED"


class MetricDirection(str, Enum):
    HIGHER_IS_BETTER = "HIGHER_IS_BETTER"
    LOWER_IS_BETTER = "LOWER_IS_BETTER"
    TARGET_ZERO = "TARGET_ZERO"


@dataclass(frozen=True, slots=True)
class TargetProtocol:
    """Exact future-outcome semantics for one comparable model lane."""

    SCHEMA_VERSION: ClassVar[str] = "target-protocol-v1"

    target_id: TargetId
    name: str
    version: str
    kind: TargetKind
    decision_time_convention: str
    horizon: str
    start_mark: PriceMark
    end_mark: PriceMark
    return_basis: ReturnBasis
    availability_rule: str
    adjustment_rule: str
    missing_policy: MissingTargetPolicy
    universe_id: UniverseId
    benchmark_ref: str | None = None
    cost_adjusted: bool = False
    path_required: bool = False

    def __post_init__(self) -> None:
        for label, value in (
            ("name", self.name),
            ("version", self.version),
            ("decision_time_convention", self.decision_time_convention),
            ("horizon", self.horizon),
            ("availability_rule", self.availability_rule),
            ("adjustment_rule", self.adjustment_rule),
        ):
            _require_non_empty(label, value)
        if not isinstance(self.kind, TargetKind):
            raise TypeError("kind must be a TargetKind")
        if not isinstance(self.start_mark, PriceMark) or not isinstance(self.end_mark, PriceMark):
            raise TypeError("start_mark and end_mark must be PriceMark values")
        if not isinstance(self.return_basis, ReturnBasis):
            raise TypeError("return_basis must be a ReturnBasis")
        if not isinstance(self.missing_policy, MissingTargetPolicy):
            raise TypeError("missing_policy must be a MissingTargetPolicy")
        if self.return_basis is ReturnBasis.BENCHMARK_RELATIVE and self.benchmark_ref is None:
            raise ValueError("benchmark-relative Target requires benchmark_ref")
        if self.benchmark_ref is not None:
            _require_non_empty("benchmark_ref", self.benchmark_ref)
        if self.kind in (TargetKind.MFE, TargetKind.MAE, TargetKind.PATH_EVENT, TargetKind.TIME_TO_EVENT) and not self.path_required:
            raise ValueError("path-dependent Target kind requires path_required=True")

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "target_id": str(self.target_id),
            "name": self.name,
            "version": self.version,
            "kind": self.kind.value,
            "decision_time_convention": self.decision_time_convention,
            "horizon": self.horizon,
            "start_mark": self.start_mark.value,
            "end_mark": self.end_mark.value,
            "return_basis": self.return_basis.value,
            "availability_rule": self.availability_rule,
            "adjustment_rule": self.adjustment_rule,
            "missing_policy": self.missing_policy.value,
            "universe_id": str(self.universe_id),
            "benchmark_ref": self.benchmark_ref,
            "cost_adjusted": self.cost_adjusted,
            "path_required": self.path_required,
        }

    @property
    def protocol_hash(self) -> str:
        canonical = json.dumps(self.canonical_payload(), ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        return sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class MetricDefinition:
    metric_id: MetricId
    name: str
    version: str
    direction: MetricDirection
    formula_ref: str
    aggregation_scope: str
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for label, value in (
            ("name", self.name),
            ("version", self.version),
            ("formula_ref", self.formula_ref),
            ("aggregation_scope", self.aggregation_scope),
        ):
            _require_non_empty(label, value)
        if not isinstance(self.direction, MetricDirection):
            raise TypeError("direction must be a MetricDirection")
        _require_unique("limitations", self.limitations)


@dataclass(frozen=True, slots=True)
class EvaluationProtocol:
    """Frozen comparison protocol for one model role, Target, and Universe lane."""

    SCHEMA_VERSION: ClassVar[str] = "evaluation-protocol-v1"

    protocol_id: EvaluationProtocolId
    version: str
    model_role: ModelRole
    target_id: TargetId
    universe_id: UniverseId
    primary_metric_id: MetricId
    secondary_metric_ids: tuple[MetricId, ...]
    risk_metric_ids: tuple[MetricId, ...]
    robustness_metric_ids: tuple[MetricId, ...]
    top_k_values: tuple[int, ...]
    baseline_model_ids: tuple[ModelId, ...]
    cost_model_ref: str
    split_protocol_ref: str
    minimum_decision_dates: int
    minimum_symbol_coverage: float
    pass_conditions: tuple[str, ...]
    failure_conditions: tuple[str, ...]

    def __post_init__(self) -> None:
        for label, value in (
            ("version", self.version),
            ("cost_model_ref", self.cost_model_ref),
            ("split_protocol_ref", self.split_protocol_ref),
        ):
            _require_non_empty(label, value)
        if not isinstance(self.model_role, ModelRole):
            raise TypeError("model_role must be a ModelRole")
        _require_unique("secondary_metric_ids", self.secondary_metric_ids)
        _require_unique("risk_metric_ids", self.risk_metric_ids)
        _require_unique("robustness_metric_ids", self.robustness_metric_ids)
        _require_unique("top_k_values", self.top_k_values)
        _require_unique("baseline_model_ids", self.baseline_model_ids)
        if self.primary_metric_id in self.secondary_metric_ids + self.risk_metric_ids + self.robustness_metric_ids:
            raise ValueError("primary metric must not be duplicated in other metric groups")
        if not self.top_k_values or tuple(sorted(self.top_k_values)) != self.top_k_values:
            raise ValueError("top_k_values must be non-empty, unique, and sorted")
        if any(value <= 0 for value in self.top_k_values):
            raise ValueError("top_k_values must be positive")
        if not self.baseline_model_ids:
            raise ValueError("baseline_model_ids must not be empty")
        if self.minimum_decision_dates <= 0:
            raise ValueError("minimum_decision_dates must be positive")
        if not 0.0 <= self.minimum_symbol_coverage <= 1.0:
            raise ValueError("minimum_symbol_coverage must be in [0, 1]")
        if not self.pass_conditions or not self.failure_conditions:
            raise ValueError("pass_conditions and failure_conditions must not be empty")
        _require_unique("pass_conditions", self.pass_conditions)
        _require_unique("failure_conditions", self.failure_conditions)

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "protocol_id": str(self.protocol_id),
            "version": self.version,
            "model_role": self.model_role.value,
            "target_id": str(self.target_id),
            "universe_id": str(self.universe_id),
            "primary_metric_id": str(self.primary_metric_id),
            "secondary_metric_ids": [str(item) for item in self.secondary_metric_ids],
            "risk_metric_ids": [str(item) for item in self.risk_metric_ids],
            "robustness_metric_ids": [str(item) for item in self.robustness_metric_ids],
            "top_k_values": list(self.top_k_values),
            "baseline_model_ids": [str(item) for item in self.baseline_model_ids],
            "cost_model_ref": self.cost_model_ref,
            "split_protocol_ref": self.split_protocol_ref,
            "minimum_decision_dates": self.minimum_decision_dates,
            "minimum_symbol_coverage": self.minimum_symbol_coverage,
            "pass_conditions": list(self.pass_conditions),
            "failure_conditions": list(self.failure_conditions),
        }

    @property
    def protocol_hash(self) -> str:
        canonical = json.dumps(self.canonical_payload(), ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        return sha256(canonical.encode("utf-8")).hexdigest()
