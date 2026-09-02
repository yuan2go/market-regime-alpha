"""Deterministic, transparent ridge estimator for the WP-17P challenger."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_EVEN
import json
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


def _decimal(value: np.float64) -> Decimal:
    result = Decimal(format(float(value), ".17g")).quantize(
        _QUANTUM,
        rounding=ROUND_HALF_EVEN,
    )
    return Decimal(0).quantize(_QUANTUM) if result == 0 else result


__all__ = [
    "DeterministicRidgeArtifact",
    "LinearTrainingRow",
    "fit_deterministic_ridge",
    "predict_deterministic_ridge",
]
