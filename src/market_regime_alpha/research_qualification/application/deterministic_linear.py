"""Deterministic, transparent ridge estimator used by its concrete adapter."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_EVEN
import json
from typing import Any
from uuid import UUID

import numpy as np

from market_regime_alpha.research_qualification.domain.research_models import (
    LinearTrainingRow,
)
from market_regime_alpha.shared.hashing import canonical_json_sha256, sha256_bytes


_QUANTUM = Decimal("0.000000000001")


@dataclass(frozen=True, slots=True)
class DeterministicRidgeArtifact:
    content: bytes
    content_sha256: str
    sample_roster_sha256: str
    feature_definition_ids: tuple[UUID, ...]
    feature_means: tuple[Decimal, ...]
    feature_scales: tuple[Decimal, ...]
    intercept: Decimal
    coefficients: tuple[Decimal, ...]
    alpha: Decimal
    seed: int


def fit_deterministic_ridge(
    rows: tuple[LinearTrainingRow, ...],
    *,
    feature_definition_ids: tuple[UUID, ...],
    alpha: Decimal,
    seed: int,
) -> DeterministicRidgeArtifact:
    """Fit a fixed ridge formulation and emit canonical content-addressed bytes."""

    if len(rows) < 2:
        raise ValueError("deterministic ridge requires at least two samples")
    if not feature_definition_ids or len(set(feature_definition_ids)) != len(
        feature_definition_ids
    ):
        raise ValueError("feature_definition_ids must be non-empty and unique")
    if alpha < 0 or not alpha.is_finite():
        raise ValueError("alpha must be finite and non-negative")
    if isinstance(seed, bool) or seed < 0:
        raise ValueError("seed must be non-negative")
    ordered = tuple(sorted(rows, key=lambda item: str(item.model_training_sample_id)))
    if len({item.model_training_sample_id for item in ordered}) != len(ordered):
        raise ValueError("training sample identities must be unique")
    width = len(feature_definition_ids)
    if any(len(item.features) != width for item in ordered):
        raise ValueError("training row feature width does not match feature roster")
    if any(
        not value.is_finite()
        for item in ordered
        for value in (*item.features, item.target)
    ):
        raise ValueError("training matrix values must be finite")

    matrix = np.asarray(
        [[float(value) for value in item.features] for item in ordered],
        dtype=np.float64,
    )
    target = np.asarray([float(item.target) for item in ordered], dtype=np.float64)
    means = matrix.mean(axis=0, dtype=np.float64)
    scales = matrix.std(axis=0, dtype=np.float64)
    scales = np.where(scales == 0.0, 1.0, scales)
    normalized = (matrix - means) / scales
    design = np.column_stack((np.ones(len(ordered), dtype=np.float64), normalized))
    penalty = np.eye(width + 1, dtype=np.float64) * float(alpha)
    penalty[0, 0] = 0.0
    parameters = np.linalg.solve(design.T @ design + penalty, design.T @ target)
    if not np.isfinite(parameters).all():
        raise ValueError("deterministic ridge produced non-finite parameters")

    decimal_means = tuple(_decimal(value) for value in means)
    decimal_scales = tuple(_decimal(value) for value in scales)
    intercept = _decimal(parameters[0])
    coefficients = tuple(_decimal(value) for value in parameters[1:])
    sample_roster_sha256 = canonical_json_sha256(
        tuple(
            {
                "features": item.features,
                "model_training_sample_id": item.model_training_sample_id,
                "target": item.target,
            }
            for item in ordered
        )
    )
    payload = {
        "algorithm": "deterministic_ridge_v1",
        "alpha": format(alpha, "f"),
        "coefficients": [format(item, "f") for item in coefficients],
        "feature_definition_ids": [str(item) for item in feature_definition_ids],
        "feature_means": [format(item, "f") for item in decimal_means],
        "feature_scales": [format(item, "f") for item in decimal_scales],
        "intercept": format(intercept, "f"),
        "sample_roster_sha256": sample_roster_sha256,
        "schema": "mra-deterministic-ridge-model-v1",
        "seed": seed,
    }
    content = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return DeterministicRidgeArtifact(
        content=content,
        content_sha256=sha256_bytes(content),
        sample_roster_sha256=sample_roster_sha256,
        feature_definition_ids=feature_definition_ids,
        feature_means=decimal_means,
        feature_scales=decimal_scales,
        intercept=intercept,
        coefficients=coefficients,
        alpha=alpha,
        seed=seed,
    )


def predict_deterministic_ridge(
    model: DeterministicRidgeArtifact,
    features: tuple[Decimal, ...],
) -> Decimal:
    if len(features) != len(model.coefficients):
        raise ValueError("inference feature width does not match ModelVersion")
    if any(not item.is_finite() for item in features):
        raise ValueError("inference features must be finite")
    value = model.intercept
    for raw, mean, scale, coefficient in zip(
        features,
        model.feature_means,
        model.feature_scales,
        model.coefficients,
        strict=True,
    ):
        value += ((raw - mean) / scale) * coefficient
    return value.quantize(_QUANTUM, rounding=ROUND_HALF_EVEN)


def load_deterministic_ridge_artifact(
    content: bytes,
) -> DeterministicRidgeArtifact:
    """Parse only the exact fitted-model wire contract; ambiguity fails closed."""

    try:
        payload = json.loads(
            content.decode("utf-8"),
            parse_float=Decimal,
            parse_int=Decimal,
            parse_constant=_raise_invalid_number,
            object_pairs_hook=_closed_object,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("fitted ModelVersion Artifact is not canonical JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("fitted ModelVersion Artifact must be an object")
    expected = {
        "algorithm",
        "alpha",
        "coefficients",
        "feature_definition_ids",
        "feature_means",
        "feature_scales",
        "intercept",
        "sample_roster_sha256",
        "schema",
        "seed",
    }
    if set(payload) != expected:
        raise ValueError("fitted ModelVersion Artifact must contain exact fields")
    if payload["schema"] != "mra-deterministic-ridge-model-v1":
        raise ValueError("fitted ModelVersion Artifact schema is unsupported")
    if payload["algorithm"] != "deterministic_ridge_v1":
        raise ValueError("fitted ModelVersion Artifact algorithm is unsupported")
    feature_ids = _uuid_array(payload["feature_definition_ids"])
    means = _decimal_array(payload["feature_means"], "feature_means")
    scales = _decimal_array(payload["feature_scales"], "feature_scales")
    coefficients = _decimal_array(payload["coefficients"], "coefficients")
    if not feature_ids or not (
        len(feature_ids) == len(means) == len(scales) == len(coefficients)
    ):
        raise ValueError("fitted ModelVersion feature roster is incomplete")
    if len(set(feature_ids)) != len(feature_ids):
        raise ValueError("fitted ModelVersion feature roster contains duplicates")
    if any(value <= 0 for value in scales):
        raise ValueError("fitted ModelVersion feature scales must be positive")
    alpha = _decimal_scalar(payload["alpha"], "alpha")
    intercept = _decimal_scalar(payload["intercept"], "intercept")
    if alpha < 0:
        raise ValueError("fitted ModelVersion alpha must be non-negative")
    seed = payload["seed"]
    if not isinstance(seed, Decimal) or seed != seed.to_integral_value() or seed < 0:
        raise ValueError("fitted ModelVersion seed must be a non-negative integer")
    sample_hash = payload["sample_roster_sha256"]
    if not isinstance(sample_hash, str) or len(sample_hash) != 64 or any(
        char not in "0123456789abcdef" for char in sample_hash
    ):
        raise ValueError("fitted ModelVersion sample roster hash is invalid")
    return DeterministicRidgeArtifact(
        content=content,
        content_sha256=sha256_bytes(content),
        sample_roster_sha256=sample_hash,
        feature_definition_ids=feature_ids,
        feature_means=means,
        feature_scales=scales,
        intercept=intercept,
        coefficients=coefficients,
        alpha=alpha,
        seed=int(seed),
    )


def _decimal(value: np.float64) -> Decimal:
    result = Decimal(format(float(value), ".17g")).quantize(
        _QUANTUM,
        rounding=ROUND_HALF_EVEN,
    )
    return Decimal(0).quantize(_QUANTUM) if result == 0 else result


def _closed_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"fitted ModelVersion Artifact contains duplicate field {key}")
        result[key] = value
    return result


def _raise_invalid_number(value: str) -> None:
    raise ValueError(f"fitted ModelVersion Artifact contains invalid number {value}")


def _uuid_array(value: object) -> tuple[UUID, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError("fitted ModelVersion feature identities are invalid")
    try:
        return tuple(UUID(item) for item in value)
    except ValueError as exc:
        raise ValueError("fitted ModelVersion feature identity is invalid") from exc


def _decimal_array(value: object, field: str) -> tuple[Decimal, ...]:
    if not isinstance(value, list):
        raise ValueError(f"fitted ModelVersion {field} must be an array")
    return tuple(_decimal_scalar(item, field) for item in value)


def _decimal_scalar(value: object, field: str) -> Decimal:
    if not isinstance(value, (str, Decimal)) or isinstance(value, bool):
        raise ValueError(f"fitted ModelVersion {field} must contain decimals")
    try:
        result = Decimal(value)
    except Exception as exc:
        raise ValueError(f"fitted ModelVersion {field} contains an invalid decimal") from exc
    if not result.is_finite():
        raise ValueError(f"fitted ModelVersion {field} must be finite")
    return result


__all__ = [
    "DeterministicRidgeArtifact",
    "LinearTrainingRow",
    "fit_deterministic_ridge",
    "load_deterministic_ridge_artifact",
    "predict_deterministic_ridge",
]
