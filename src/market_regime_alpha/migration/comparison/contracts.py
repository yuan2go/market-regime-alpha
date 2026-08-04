"""Immutable contracts for policy-driven Legacy/canonical comparisons."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any

from market_regime_alpha.core.identity import ArtifactId, DatasetId, ModelId
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    require_sha256,
    require_text,
    require_unique_text,
)


COMPARISON_POLICY_SCHEMA = "model-comparison-policy-v1"
MODEL_COMPARISON_REPORT_SCHEMA = "model-comparison-report-v1"


class DifferenceClassification(str, Enum):
    EXACT_MATCH = "EXACT_MATCH"
    NUMERIC_TOLERANCE = "NUMERIC_TOLERANCE"
    EXPECTED_SEMANTIC_CHANGE = "EXPECTED_SEMANTIC_CHANGE"
    LEGACY_DEFECT_FIXED = "LEGACY_DEFECT_FIXED"
    CANONICAL_REGRESSION = "CANONICAL_REGRESSION"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    NOT_COMPARABLE = "NOT_COMPARABLE"


def _require_canonical_time(label: str, value: datetime) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{label} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    if value.microsecond != 0:
        raise ValueError(f"{label} must have whole-second precision")


def _require_sorted_unique_text(label: str, values: tuple[str, ...]) -> None:
    if not isinstance(values, tuple):
        raise TypeError(f"{label} values must be a tuple")
    require_unique_text(label, values)
    if values != tuple(sorted(values)):
        raise ValueError(f"{label} values must be sorted")


def _require_path(path: str) -> None:
    require_text("comparison path", path)
    if "*" in path:
        raise ValueError("comparison paths must be field-specific; wildcards are forbidden")


@dataclass(frozen=True, slots=True)
class NumericTolerance:
    path: str
    absolute_tolerance: Decimal

    def __post_init__(self) -> None:
        _require_path(self.path)
        if (
            not isinstance(self.absolute_tolerance, Decimal)
            or not self.absolute_tolerance.is_finite()
            or self.absolute_tolerance < Decimal("0")
        ):
            raise ValueError("absolute_tolerance must be finite and non-negative")

    def to_canonical_dict(self) -> dict[str, str]:
        return {
            "path": self.path,
            "absolute_tolerance": str(self.absolute_tolerance),
        }


@dataclass(frozen=True, slots=True)
class ExpectedSemanticChange:
    rule_id: str
    path: str
    legacy_value: str | None
    canonical_value: str | None

    def __post_init__(self) -> None:
        require_text("semantic rule_id", self.rule_id)
        _require_path(self.path)

    def to_canonical_dict(self) -> dict[str, str | None]:
        return {
            "rule_id": self.rule_id,
            "path": self.path,
            "legacy_value": self.legacy_value,
            "canonical_value": self.canonical_value,
        }


@dataclass(frozen=True, slots=True)
class CanonicalInvariant:
    invariant_id: str
    path: str
    independently_expected_value: str | None

    def __post_init__(self) -> None:
        require_text("invariant_id", self.invariant_id)
        _require_path(self.path)

    def to_canonical_dict(self) -> dict[str, str | None]:
        return {
            "invariant_id": self.invariant_id,
            "path": self.path,
            "independently_expected_value": self.independently_expected_value,
        }


@dataclass(frozen=True, slots=True)
class LegacyDefectExpectation:
    defect_id: str
    path: str
    legacy_value: str | None
    independently_expected_canonical_value: str | None

    def __post_init__(self) -> None:
        require_text("defect_id", self.defect_id)
        _require_path(self.path)

    def to_canonical_dict(self) -> dict[str, str | None]:
        return {
            "defect_id": self.defect_id,
            "path": self.path,
            "legacy_value": self.legacy_value,
            "independently_expected_canonical_value": (
                self.independently_expected_canonical_value
            ),
        }


@dataclass(frozen=True, slots=True)
class ComparisonPolicy:
    policy_id: ArtifactId
    policy_hash: str
    policy_version: str
    exact_fields: tuple[str, ...]
    numeric_tolerances: tuple[NumericTolerance, ...]
    expected_semantic_changes: tuple[ExpectedSemanticChange, ...]
    canonical_invariants: tuple[CanonicalInvariant, ...]
    legacy_defect_expectations: tuple[LegacyDefectExpectation, ...]
    expected_insufficient_reason_codes: tuple[str, ...]
    expected_not_comparable_reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.policy_id, ArtifactId):
            raise TypeError("policy_id must be an ArtifactId")
        require_sha256("policy_hash", self.policy_hash)
        require_text("policy_version", self.policy_version)
        _require_sorted_unique_text("exact field", self.exact_fields)
        for path in self.exact_fields:
            _require_path(path)
        _require_sorted_rules(
            "numeric tolerance", self.numeric_tolerances, lambda item: item.path
        )
        _require_sorted_rules(
            "semantic change",
            self.expected_semantic_changes,
            lambda item: item.path,
        )
        _require_sorted_rules(
            "canonical invariant",
            self.canonical_invariants,
            lambda item: f"{item.path}:{item.invariant_id}",
        )
        _require_sorted_rules(
            "Legacy defect",
            self.legacy_defect_expectations,
            lambda item: f"{item.path}:{item.defect_id}",
        )
        exact_paths = set(self.exact_fields)
        overlapping_paths = exact_paths.intersection(
            {
                *[item.path for item in self.numeric_tolerances],
                *[item.path for item in self.expected_semantic_changes],
                *[item.path for item in self.legacy_defect_expectations],
            }
        )
        if overlapping_paths:
            raise ValueError(
                "exact_fields cannot overlap tolerance, semantic-change, or "
                f"Legacy-defect rules: {sorted(overlapping_paths)}"
            )
        _require_sorted_unique_text(
            "expected insufficient reason_code",
            self.expected_insufficient_reason_codes,
        )
        _require_sorted_unique_text(
            "expected not-comparable reason_code",
            self.expected_not_comparable_reason_codes,
        )
        expected_hash = canonical_hash(self.semantic_payload())
        if self.policy_hash != expected_hash:
            raise ValueError("Comparison Policy hash mismatch")
        expected_id = f"comparison-policy-{expected_hash.split(':', 1)[1][:24]}"
        if str(self.policy_id) != expected_id:
            raise ValueError("Comparison Policy identity mismatch")

    @classmethod
    def create(
        cls,
        *,
        policy_version: str,
        exact_fields: tuple[str, ...] = (),
        numeric_tolerances: tuple[NumericTolerance, ...] = (),
        expected_semantic_changes: tuple[ExpectedSemanticChange, ...] = (),
        canonical_invariants: tuple[CanonicalInvariant, ...] = (),
        legacy_defect_expectations: tuple[LegacyDefectExpectation, ...] = (),
        expected_insufficient_reason_codes: tuple[str, ...] = (),
        expected_not_comparable_reason_codes: tuple[str, ...] = (),
    ) -> ComparisonPolicy:
        sorted_exact_fields = tuple(sorted(exact_fields))
        sorted_numeric_tolerances = tuple(
            sorted(numeric_tolerances, key=lambda item: item.path)
        )
        sorted_semantic_changes = tuple(
            sorted(expected_semantic_changes, key=lambda item: item.path)
        )
        sorted_invariants = tuple(
            sorted(
                canonical_invariants,
                key=lambda item: (item.path, item.invariant_id),
            )
        )
        sorted_defects = tuple(
            sorted(
                legacy_defect_expectations,
                key=lambda item: (item.path, item.defect_id),
            )
        )
        sorted_insufficient_reasons = tuple(
            sorted(expected_insufficient_reason_codes)
        )
        sorted_not_comparable_reasons = tuple(
            sorted(expected_not_comparable_reason_codes)
        )
        payload = _policy_payload(
            policy_version=policy_version,
            exact_fields=sorted_exact_fields,
            numeric_tolerances=sorted_numeric_tolerances,
            expected_semantic_changes=sorted_semantic_changes,
            canonical_invariants=sorted_invariants,
            legacy_defect_expectations=sorted_defects,
            expected_insufficient_reason_codes=sorted_insufficient_reasons,
            expected_not_comparable_reason_codes=sorted_not_comparable_reasons,
        )
        policy_hash = canonical_hash(payload)
        return cls(
            policy_id=ArtifactId(
                f"comparison-policy-{policy_hash.split(':', 1)[1][:24]}"
            ),
            policy_hash=policy_hash,
            policy_version=policy_version,
            exact_fields=sorted_exact_fields,
            numeric_tolerances=sorted_numeric_tolerances,
            expected_semantic_changes=sorted_semantic_changes,
            canonical_invariants=sorted_invariants,
            legacy_defect_expectations=sorted_defects,
            expected_insufficient_reason_codes=sorted_insufficient_reasons,
            expected_not_comparable_reason_codes=sorted_not_comparable_reasons,
        )

    def semantic_payload(self) -> dict[str, Any]:
        return _policy_payload(
            policy_version=self.policy_version,
            exact_fields=self.exact_fields,
            numeric_tolerances=self.numeric_tolerances,
            expected_semantic_changes=self.expected_semantic_changes,
            canonical_invariants=self.canonical_invariants,
            legacy_defect_expectations=self.legacy_defect_expectations,
            expected_insufficient_reason_codes=self.expected_insufficient_reason_codes,
            expected_not_comparable_reason_codes=(
                self.expected_not_comparable_reason_codes
            ),
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "policy_id": str(self.policy_id),
            "policy_hash": self.policy_hash,
            **self.semantic_payload(),
        }


def _require_sorted_rules(
    label: str, values: tuple[object, ...], key: Any
) -> None:
    if not isinstance(values, tuple):
        raise TypeError(f"{label} rules must be a tuple")
    keys = tuple(key(item) for item in values)
    if keys != tuple(sorted(keys)) or len(keys) != len(set(keys)):
        raise ValueError(f"{label} rules must be sorted and unique")


def _policy_payload(
    *,
    policy_version: str,
    exact_fields: tuple[str, ...],
    numeric_tolerances: tuple[NumericTolerance, ...],
    expected_semantic_changes: tuple[ExpectedSemanticChange, ...],
    canonical_invariants: tuple[CanonicalInvariant, ...],
    legacy_defect_expectations: tuple[LegacyDefectExpectation, ...],
    expected_insufficient_reason_codes: tuple[str, ...],
    expected_not_comparable_reason_codes: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "schema_version": COMPARISON_POLICY_SCHEMA,
        "policy_version": policy_version,
        "exact_fields": list(exact_fields),
        "numeric_tolerances": [
            item.to_canonical_dict() for item in numeric_tolerances
        ],
        "expected_semantic_changes": [
            item.to_canonical_dict() for item in expected_semantic_changes
        ],
        "canonical_invariants": [
            item.to_canonical_dict() for item in canonical_invariants
        ],
        "legacy_defect_expectations": [
            item.to_canonical_dict() for item in legacy_defect_expectations
        ],
        "expected_insufficient_reason_codes": list(
            expected_insufficient_reason_codes
        ),
        "expected_not_comparable_reason_codes": list(
            expected_not_comparable_reason_codes
        ),
    }


@dataclass(frozen=True, slots=True)
class ComparisonObservation:
    key: str
    value: Decimal | None
    missing_reason: str | None

    def __post_init__(self) -> None:
        require_text("observation key", self.key)
        if self.value is not None and (
            not isinstance(self.value, Decimal) or not self.value.is_finite()
        ):
            raise ValueError("comparison value must be a finite Decimal")
        if self.missing_reason is not None:
            require_text("missing_reason", self.missing_reason)
        if (self.value is None) == (self.missing_reason is None):
            raise ValueError("comparison observation requires a value or missing_reason")

    def to_canonical_dict(self) -> dict[str, str | None]:
        return {
            "key": self.key,
            "value": str(self.value) if self.value is not None else None,
            "missing_reason": self.missing_reason,
        }


@dataclass(frozen=True, slots=True)
class ModelComparisonOutput:
    model_id: ModelId
    model_version: str
    state: str
    score: Decimal | None
    observations: tuple[ComparisonObservation, ...]
    reason_codes: tuple[str, ...]
    limitations: tuple[str, ...]
    exception_type: str | None = None
    exception_message: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.model_id, ModelId):
            raise TypeError("model_id must be a ModelId")
        require_text("model_version", self.model_version)
        require_text("state", self.state)
        if self.score is not None and (
            not isinstance(self.score, Decimal) or not self.score.is_finite()
        ):
            raise ValueError("comparison score must be a finite Decimal")
        if not isinstance(self.observations, tuple) or any(
            not isinstance(item, ComparisonObservation) for item in self.observations
        ):
            raise TypeError("observations must contain ComparisonObservation values")
        keys = tuple(item.key for item in self.observations)
        if keys != tuple(sorted(keys)) or len(keys) != len(set(keys)):
            raise ValueError("comparison observation keys must be sorted and unique")
        _require_sorted_unique_text("reason_code", self.reason_codes)
        _require_sorted_unique_text("limitation", self.limitations)
        if (self.exception_type is None) != (self.exception_message is None):
            raise ValueError("comparison exception type and message must be paired")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "model_id": str(self.model_id),
            "model_version": self.model_version,
            "state": self.state,
            "score": str(self.score) if self.score is not None else None,
            "observations": [item.to_canonical_dict() for item in self.observations],
            "reason_codes": list(self.reason_codes),
            "limitations": list(self.limitations),
            "exception_type": self.exception_type,
            "exception_message": self.exception_message,
        }


@dataclass(frozen=True, slots=True)
class FieldDifference:
    path: str
    legacy_value: str | None
    canonical_value: str | None

    def __post_init__(self) -> None:
        _require_path(self.path)

    def to_canonical_dict(self) -> dict[str, str | None]:
        return {
            "path": self.path,
            "legacy_value": self.legacy_value,
            "canonical_value": self.canonical_value,
        }


@dataclass(frozen=True, slots=True)
class NumericDifference:
    path: str
    legacy_value: Decimal
    canonical_value: Decimal
    absolute_difference: Decimal
    tolerance: Decimal | None
    within_tolerance: bool

    def __post_init__(self) -> None:
        _require_path(self.path)
        for label, value in (
            ("legacy_value", self.legacy_value),
            ("canonical_value", self.canonical_value),
            ("absolute_difference", self.absolute_difference),
        ):
            if not isinstance(value, Decimal) or not value.is_finite():
                raise ValueError(f"{label} must be a finite Decimal")
        if self.absolute_difference < Decimal("0"):
            raise ValueError("absolute_difference must be non-negative")
        if self.tolerance is not None and (
            not isinstance(self.tolerance, Decimal)
            or not self.tolerance.is_finite()
            or self.tolerance < Decimal("0")
        ):
            raise ValueError("tolerance must be finite and non-negative")

    def to_canonical_dict(self) -> dict[str, str | bool | None]:
        return {
            "path": self.path,
            "legacy_value": str(self.legacy_value),
            "canonical_value": str(self.canonical_value),
            "absolute_difference": str(self.absolute_difference),
            "tolerance": str(self.tolerance) if self.tolerance is not None else None,
            "within_tolerance": self.within_tolerance,
        }


@dataclass(frozen=True, slots=True)
class SemanticDifference:
    rule_id: str
    difference_kind: str
    path: str
    legacy_value: str | None
    canonical_value: str | None

    def __post_init__(self) -> None:
        require_text("rule_id", self.rule_id)
        require_text("difference_kind", self.difference_kind)
        _require_path(self.path)

    def to_canonical_dict(self) -> dict[str, str | None]:
        return {
            "rule_id": self.rule_id,
            "difference_kind": self.difference_kind,
            "path": self.path,
            "legacy_value": self.legacy_value,
            "canonical_value": self.canonical_value,
        }


@dataclass(frozen=True, slots=True)
class ModelComparisonReport:
    comparison_id: ArtifactId
    report_hash: str
    policy_id: ArtifactId
    policy_hash: str
    legacy_model_id: ModelId
    legacy_model_version: str
    canonical_model_id: ModelId
    canonical_model_version: str
    dataset_id: DatasetId
    as_of_time: datetime
    input_hash: str
    legacy_output: ModelComparisonOutput
    canonical_output: ModelComparisonOutput
    field_differences: tuple[FieldDifference, ...]
    numeric_differences: tuple[NumericDifference, ...]
    semantic_differences: tuple[SemanticDifference, ...]
    difference_classification: DifferenceClassification
    expected_difference: bool
    unexpected_difference: bool
    created_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.comparison_id, ArtifactId):
            raise TypeError("comparison_id must be an ArtifactId")
        if not isinstance(self.policy_id, ArtifactId):
            raise TypeError("policy_id must be an ArtifactId")
        if not isinstance(self.legacy_model_id, ModelId) or not isinstance(
            self.canonical_model_id, ModelId
        ):
            raise TypeError("comparison model identities must be ModelId values")
        if not isinstance(self.dataset_id, DatasetId):
            raise TypeError("dataset_id must be a DatasetId")
        require_sha256("report_hash", self.report_hash)
        require_sha256("policy_hash", self.policy_hash)
        require_sha256("input_hash", self.input_hash)
        require_text("legacy_model_version", self.legacy_model_version)
        require_text("canonical_model_version", self.canonical_model_version)
        _require_canonical_time("as_of_time", self.as_of_time)
        _require_canonical_time("created_at", self.created_at)
        if self.created_at < self.as_of_time:
            raise ValueError("created_at cannot precede as_of_time")
        if not isinstance(self.difference_classification, DifferenceClassification):
            raise TypeError("difference_classification must be a DifferenceClassification")
        _require_difference_order(self.field_differences)
        _require_difference_order(self.numeric_differences)
        _require_difference_order(
            self.semantic_differences,
            key=lambda item: f"{item.path}:{item.rule_id}",
        )

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "schema_version": MODEL_COMPARISON_REPORT_SCHEMA,
            "policy_id": str(self.policy_id),
            "policy_hash": self.policy_hash,
            "legacy_model_id": str(self.legacy_model_id),
            "legacy_model_version": self.legacy_model_version,
            "canonical_model_id": str(self.canonical_model_id),
            "canonical_model_version": self.canonical_model_version,
            "dataset_id": str(self.dataset_id),
            "as_of_time": canonical_datetime(self.as_of_time),
            "input_hash": self.input_hash,
            "legacy_output": self.legacy_output.to_canonical_dict(),
            "canonical_output": self.canonical_output.to_canonical_dict(),
            "field_differences": [
                item.to_canonical_dict() for item in self.field_differences
            ],
            "numeric_differences": [
                item.to_canonical_dict() for item in self.numeric_differences
            ],
            "semantic_differences": [
                item.to_canonical_dict() for item in self.semantic_differences
            ],
            "difference_classification": self.difference_classification.value,
            "expected_difference": self.expected_difference,
            "unexpected_difference": self.unexpected_difference,
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "comparison_id": str(self.comparison_id),
            "report_hash": self.report_hash,
            "created_at": canonical_datetime(self.created_at),
            **self.semantic_payload(),
        }

    def verify_content_identity(self) -> None:
        expected_hash = canonical_hash(self.semantic_payload())
        if self.report_hash != expected_hash:
            raise ValueError("Model Comparison report hash mismatch")
        expected_id = f"model-comparison-{expected_hash.split(':', 1)[1][:24]}"
        if str(self.comparison_id) != expected_id:
            raise ValueError("Model Comparison identity mismatch")


def bind_model_comparison_report(report: ModelComparisonReport) -> ModelComparisonReport:
    report_hash = canonical_hash(report.semantic_payload())
    bound = replace(
        report,
        comparison_id=ArtifactId(
            f"model-comparison-{report_hash.split(':', 1)[1][:24]}"
        ),
        report_hash=report_hash,
    )
    bound.verify_content_identity()
    return bound


def _require_difference_order(values: tuple[Any, ...], key: Any = None) -> None:
    if not isinstance(values, tuple):
        raise TypeError("differences must be immutable tuples")
    key_function = key or (lambda item: item.path)
    keys = tuple(key_function(item) for item in values)
    if keys != tuple(sorted(keys)) or len(keys) != len(set(keys)):
        raise ValueError("differences must be sorted and unique")


def decimal_from_string(value: object, label: str) -> Decimal:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a Decimal string")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"{label} must be a Decimal string") from exc
    if not result.is_finite():
        raise ValueError(f"{label} must be finite")
    return result


__all__ = [
    "COMPARISON_POLICY_SCHEMA",
    "MODEL_COMPARISON_REPORT_SCHEMA",
    "CanonicalInvariant",
    "ComparisonObservation",
    "ComparisonPolicy",
    "DifferenceClassification",
    "ExpectedSemanticChange",
    "FieldDifference",
    "LegacyDefectExpectation",
    "ModelComparisonOutput",
    "ModelComparisonReport",
    "NumericDifference",
    "NumericTolerance",
    "SemanticDifference",
    "bind_model_comparison_report",
    "decimal_from_string",
]
