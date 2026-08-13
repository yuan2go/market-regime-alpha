"""Deterministic regularized linear research model primitives.

The barrier head is trained with logistic loss but emits only its raw logit.
Calibration belongs to the Formal evidence track and cannot be inferred here.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from math import exp
from typing import Any, Mapping


FeatureRow = Mapping[str, Decimal | None]


@dataclass(frozen=True, slots=True)
class TrainingMatrix:
    feature_names: tuple[str, ...]
    rows: tuple[FeatureRow, ...]
    continuous_targets: Mapping[str, tuple[Decimal, ...]]
    barrier_targets: Mapping[str, tuple[bool, ...]]

    @classmethod
    def create(
        cls,
        *,
        feature_names: tuple[str, ...],
        rows: tuple[FeatureRow, ...],
        continuous_targets: Mapping[str, tuple[Decimal, ...]],
        barrier_targets: Mapping[str, tuple[bool, ...]],
    ) -> TrainingMatrix:
        ordered_names = tuple(sorted(set(feature_names)))
        if not ordered_names or not rows:
            raise ValueError("training matrix requires features and rows")
        if any(set(row) != set(ordered_names) for row in rows):
            raise ValueError("training rows must contain the exact frozen features")
        row_count = len(rows)
        if any(len(values) != row_count for values in continuous_targets.values()):
            raise ValueError("continuous target cardinality mismatch")
        if any(len(values) != row_count for values in barrier_targets.values()):
            raise ValueError("barrier target cardinality mismatch")
        if not continuous_targets and not barrier_targets:
            raise ValueError("training matrix requires at least one target")
        return cls(
            feature_names=ordered_names,
            rows=rows,
            continuous_targets={
                name: tuple(continuous_targets[name])
                for name in sorted(continuous_targets)
            },
            barrier_targets={
                name: tuple(barrier_targets[name])
                for name in sorted(barrier_targets)
            },
        )


@dataclass(frozen=True, slots=True)
class RobustPreprocessingState:
    feature_names: tuple[str, ...]
    medians: tuple[Decimal, ...]
    scales: tuple[Decimal, ...]

    @property
    def transformed_feature_names(self) -> tuple[str, ...]:
        return (*self.feature_names, *(f"missing::{name}" for name in self.feature_names))

    def transform(self, row: FeatureRow) -> tuple[Decimal, ...]:
        if set(row) != set(self.feature_names):
            raise ValueError("inference row does not match frozen feature set")
        normalized: list[Decimal] = []
        missing: list[Decimal] = []
        for name, median, scale in zip(
            self.feature_names, self.medians, self.scales, strict=True
        ):
            value = row[name]
            normalized.append(
                Decimal("0") if value is None else (value - median) / scale
            )
            missing.append(Decimal("1") if value is None else Decimal("0"))
        return (*normalized, *missing)

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "feature_names": list(self.feature_names),
            "medians": [str(item) for item in self.medians],
            "scales": [str(item) for item in self.scales],
            "transformed_feature_names": list(self.transformed_feature_names),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> RobustPreprocessingState:
        feature_names = tuple(str(item) for item in _array(payload["feature_names"]))
        state = cls(
            feature_names=feature_names,
            medians=tuple(Decimal(str(item)) for item in _array(payload["medians"])),
            scales=tuple(Decimal(str(item)) for item in _array(payload["scales"])),
        )
        if tuple(str(item) for item in _array(payload["transformed_feature_names"])) != state.transformed_feature_names:
            raise ValueError("preprocessing transformed feature projection mismatch")
        return state


@dataclass(frozen=True, slots=True)
class RegularizedHead:
    target_name: str
    head_kind: str
    intercept: Decimal
    coefficients: tuple[Decimal, ...]

    def score(self, transformed: tuple[Decimal, ...]) -> Decimal:
        if len(transformed) != len(self.coefficients):
            raise ValueError("transformed feature cardinality mismatch")
        return self.intercept + sum(
            (coefficient * value for coefficient, value in zip(
                self.coefficients, transformed, strict=True
            )),
            Decimal("0"),
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "target_name": self.target_name,
            "head_kind": self.head_kind,
            "intercept": str(self.intercept),
            "coefficients": [str(item) for item in self.coefficients],
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> RegularizedHead:
        return cls(
            target_name=str(payload["target_name"]),
            head_kind=str(payload["head_kind"]),
            intercept=Decimal(str(payload["intercept"])),
            coefficients=tuple(
                Decimal(str(item)) for item in _array(payload["coefficients"])
            ),
        )


@dataclass(frozen=True, slots=True)
class RegularizedPrediction:
    continuous: Mapping[str, Decimal]
    raw_barrier_logits: Mapping[str, Decimal]
    barrier_scores_are_probabilities: bool = False


@dataclass(frozen=True, slots=True)
class RegularizedMultiTargetModel:
    preprocessing: RobustPreprocessingState
    continuous_heads: tuple[RegularizedHead, ...]
    barrier_heads: tuple[RegularizedHead, ...]
    penalty: Decimal
    implementation: str = "deterministic-regularized-linear/v1"

    @property
    def feature_names(self) -> tuple[str, ...]:
        return self.preprocessing.feature_names

    @property
    def transformed_feature_names(self) -> tuple[str, ...]:
        return self.preprocessing.transformed_feature_names

    def predict(self, row: FeatureRow) -> RegularizedPrediction:
        transformed = self.preprocessing.transform(row)
        return RegularizedPrediction(
            continuous={
                head.target_name: head.score(transformed)
                for head in self.continuous_heads
            },
            raw_barrier_logits={
                head.target_name: head.score(transformed)
                for head in self.barrier_heads
            },
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "implementation": self.implementation,
            "penalty": str(self.penalty),
            "preprocessing": self.preprocessing.to_canonical_dict(),
            "continuous_heads": [
                item.to_canonical_dict() for item in self.continuous_heads
            ],
            "barrier_heads": [
                item.to_canonical_dict() for item in self.barrier_heads
            ],
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> RegularizedMultiTargetModel:
        preprocessing = RobustPreprocessingState.from_canonical_dict(
            _mapping(payload["preprocessing"])
        )
        model = cls(
            preprocessing=preprocessing,
            continuous_heads=tuple(
                RegularizedHead.from_canonical_dict(_mapping(item))
                for item in _array(payload["continuous_heads"])
            ),
            barrier_heads=tuple(
                RegularizedHead.from_canonical_dict(_mapping(item))
                for item in _array(payload["barrier_heads"])
            ),
            penalty=Decimal(str(payload["penalty"])),
            implementation=str(payload["implementation"]),
        )
        width = len(preprocessing.transformed_feature_names)
        if any(
            len(item.coefficients) != width
            for item in (*model.continuous_heads, *model.barrier_heads)
        ):
            raise ValueError("model head coefficient projection mismatch")
        return model


def fit_regularized_multi_target(
    matrix: TrainingMatrix,
    *,
    penalty: Decimal,
    logistic_iterations: int = 64,
) -> RegularizedMultiTargetModel:
    if not penalty.is_finite() or penalty <= 0:
        raise ValueError("regularization penalty must be positive and finite")
    preprocessing = _fit_preprocessing(matrix.feature_names, matrix.rows)
    transformed = tuple(preprocessing.transform(row) for row in matrix.rows)
    design = tuple((Decimal("1"), *row) for row in transformed)
    continuous = []
    for name, continuous_values in matrix.continuous_targets.items():
        if len(set(continuous_values)) < 2:
            raise ValueError(f"degenerate continuous target: {name}")
        weights = _ridge(design, continuous_values, penalty)
        continuous.append(
            RegularizedHead(name, "RIDGE", weights[0], weights[1:])
        )
    barriers = []
    for name, barrier_values in matrix.barrier_targets.items():
        if len(set(barrier_values)) < 2:
            raise ValueError(f"degenerate barrier target: {name}")
        weights = _logistic_score(
            design,
            tuple(Decimal(int(value)) for value in barrier_values),
            penalty,
            iterations=logistic_iterations,
        )
        barriers.append(
            RegularizedHead(name, "LOGISTIC_RAW_LOGIT", weights[0], weights[1:])
        )
    return RegularizedMultiTargetModel(
        preprocessing=preprocessing,
        continuous_heads=tuple(continuous),
        barrier_heads=tuple(barriers),
        penalty=penalty,
    )


def fit_regularized_continuous_statistics(
    *,
    preprocessing: RobustPreprocessingState,
    target_name: str,
    normal_matrix: tuple[tuple[Decimal, ...], ...],
    rhs: tuple[Decimal, ...],
    distinct_target_count: int,
    penalty: Decimal,
) -> RegularizedMultiTargetModel:
    """Fit the same Ridge head from bounded, incrementally built statistics."""

    if not target_name.strip():
        raise ValueError("continuous statistics require a target name")
    if not penalty.is_finite() or penalty <= 0:
        raise ValueError("regularization penalty must be positive and finite")
    width = len(preprocessing.transformed_feature_names) + 1
    if (
        len(normal_matrix) != width
        or any(len(row) != width for row in normal_matrix)
        or len(rhs) != width
    ):
        raise ValueError("continuous sufficient-statistic dimensions mismatch")
    if any(
        normal_matrix[left][right] != normal_matrix[right][left]
        for left in range(width)
        for right in range(width)
    ):
        raise ValueError("continuous normal matrix must be symmetric")
    if distinct_target_count < 2:
        raise ValueError(f"degenerate continuous target: {target_name}")
    normal = [list(row) for row in normal_matrix]
    for index in range(1, width):
        normal[index][index] += penalty
    weights = _solve(normal, list(rhs))
    return RegularizedMultiTargetModel(
        preprocessing=preprocessing,
        continuous_heads=(
            RegularizedHead(target_name, "RIDGE", weights[0], weights[1:]),
        ),
        barrier_heads=(),
        penalty=penalty,
    )


def _fit_preprocessing(
    feature_names: tuple[str, ...], rows: tuple[FeatureRow, ...]
) -> RobustPreprocessingState:
    medians = []
    scales = []
    for name in feature_names:
        values: list[Decimal] = []
        for row in rows:
            value = row[name]
            if value is not None:
                values.append(value)
        values.sort()
        if not values:
            medians.append(Decimal("0"))
            scales.append(Decimal("1"))
            continue
        median = _quantile(values, Decimal("0.5"))
        q1 = _quantile(values, Decimal("0.25"))
        q3 = _quantile(values, Decimal("0.75"))
        scale = q3 - q1
        medians.append(median)
        scales.append(Decimal("1") if scale == 0 else scale)
    return RobustPreprocessingState(feature_names, tuple(medians), tuple(scales))


def _quantile(values: list[Decimal], probability: Decimal) -> Decimal:
    if len(values) == 1:
        return values[0]
    position = probability * Decimal(len(values) - 1)
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    fraction = position - Decimal(lower)
    return values[lower] * (Decimal("1") - fraction) + values[upper] * fraction


def _ridge(
    design: tuple[tuple[Decimal, ...], ...],
    targets: tuple[Decimal, ...],
    penalty: Decimal,
) -> tuple[Decimal, ...]:
    width = len(design[0])
    normal = [
        [sum((row[i] * row[j] for row in design), Decimal("0")) for j in range(width)]
        for i in range(width)
    ]
    for index in range(1, width):
        normal[index][index] += penalty
    rhs = [
        sum((row[index] * target for row, target in zip(design, targets, strict=True)), Decimal("0"))
        for index in range(width)
    ]
    return _solve(normal, rhs)


def _logistic_score(
    design: tuple[tuple[Decimal, ...], ...],
    targets: tuple[Decimal, ...],
    penalty: Decimal,
    *,
    iterations: int,
) -> tuple[Decimal, ...]:
    width = len(design[0])
    weights = tuple(Decimal("0") for _ in range(width))
    for _ in range(iterations):
        probabilities = tuple(
            _sigmoid(sum((x * weight for x, weight in zip(row, weights, strict=True)), Decimal("0")))
            for row in design
        )
        hessian = [
            [
                sum(
                    (
                        row[i] * row[j] * probability * (Decimal("1") - probability)
                        for row, probability in zip(design, probabilities, strict=True)
                    ),
                    Decimal("0"),
                )
                for j in range(width)
            ]
            for i in range(width)
        ]
        gradient = [
            sum(
                (
                    row[index] * (target - probability)
                    for row, target, probability in zip(
                        design, targets, probabilities, strict=True
                    )
                ),
                Decimal("0"),
            )
            for index in range(width)
        ]
        for index in range(1, width):
            hessian[index][index] += penalty
            gradient[index] -= penalty * weights[index]
        delta = _solve(hessian, gradient)
        weights = tuple(
            weight + change for weight, change in zip(weights, delta, strict=True)
        )
        if max(abs(item) for item in delta) <= Decimal("1e-20"):
            break
    return weights


def _sigmoid(value: Decimal) -> Decimal:
    bounded = max(Decimal("-40"), min(Decimal("40"), value))
    return Decimal(str(1 / (1 + exp(-float(bounded)))))


def _solve(matrix: list[list[Decimal]], rhs: list[Decimal]) -> tuple[Decimal, ...]:
    size = len(rhs)
    augmented = [matrix[index][:] + [rhs[index]] for index in range(size)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        if augmented[pivot][column] == 0:
            raise ValueError("regularized system is singular")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        divisor = augmented[column][column]
        augmented[column] = [item / divisor for item in augmented[column]]
        for row in range(size):
            if row == column:
                continue
            multiplier = augmented[row][column]
            if multiplier == 0:
                continue
            augmented[row] = [
                left - multiplier * right
                for left, right in zip(augmented[row], augmented[column], strict=True)
            ]
    return tuple(row[-1] for row in augmented)


def _array(value: object) -> list[object]:
    if not isinstance(value, list):
        raise ValueError("expected array")
    return value


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("expected object")
    return value


__all__ = [
    "RegularizedHead",
    "RegularizedMultiTargetModel",
    "RegularizedPrediction",
    "RobustPreprocessingState",
    "TrainingMatrix",
    "fit_regularized_continuous_statistics",
    "fit_regularized_multi_target",
]
