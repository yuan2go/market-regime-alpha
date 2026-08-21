"""Frozen baseline and regularized conditional Forecast research capability."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from statistics import pstdev
from typing import Any, Mapping

from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_datetime, canonical_hash
from market_regime_alpha.forecasting.regularized_linear import (
    RegularizedMultiTargetModel,
    RegularizedPrediction,
    TrainingMatrix,
    fit_regularized_multi_target,
)


@dataclass(frozen=True, slots=True)
class ConditionalForecastConfig:
    configuration_id: ArtifactId
    configuration_hash: str
    feature_names: tuple[str, ...]
    continuous_targets: tuple[str, ...]
    barrier_targets: tuple[str, ...]
    train_validation_policy: str
    penalties: tuple[Decimal, ...]
    hyperparameter_search_budget: int
    random_seed: int
    minimum_training_samples: int
    cost_assumption: Decimal
    schema_version: str = "conditional-forecast-config/v1"

    def __post_init__(self) -> None:
        if self.feature_names != tuple(sorted(set(self.feature_names))):
            raise ValueError("Conditional Forecast features must be unique and sorted")
        if self.continuous_targets != tuple(sorted(set(self.continuous_targets))):
            raise ValueError("Conditional Forecast continuous targets must be unique and sorted")
        if self.barrier_targets != tuple(sorted(set(self.barrier_targets))):
            raise ValueError("Conditional Forecast barrier targets must be unique and sorted")
        if set(self.continuous_targets) != {"mae", "mfe", "t_plus_1_return"}:
            raise ValueError("Conditional Forecast requires T+1 return, MFE and MAE")
        if set(self.barrier_targets) != {"lower_barrier", "upper_barrier"}:
            raise ValueError("Conditional Forecast requires upper/lower path barriers")
        if self.train_validation_policy != "CHRONOLOGICAL_75_25":
            raise ValueError("unsupported Conditional Forecast split")
        if self.penalties != tuple(sorted(set(self.penalties))) or any(item <= 0 for item in self.penalties):
            raise ValueError("Conditional Forecast penalties must be positive and frozen")
        if self.hyperparameter_search_budget != len(self.penalties):
            raise ValueError("hyperparameter budget must equal the frozen search space")
        if self.minimum_training_samples <= 0:
            raise ValueError("minimum training samples must be positive")
        if not Decimal("0") <= self.cost_assumption < Decimal("1"):
            raise ValueError("Conditional Forecast cost assumption is invalid")
        if canonical_hash(self.identity_payload()) != self.configuration_hash:
            raise ValueError("Conditional Forecast configuration hash mismatch")

    @classmethod
    def create(
        cls,
        *,
        feature_names: tuple[str, ...],
        continuous_targets: tuple[str, ...],
        barrier_targets: tuple[str, ...],
        train_validation_policy: str,
        penalties: tuple[Decimal, ...],
        hyperparameter_search_budget: int,
        random_seed: int,
        minimum_training_samples: int,
        cost_assumption: Decimal,
    ) -> ConditionalForecastConfig:
        features = tuple(sorted(set(feature_names)))
        continuous = tuple(sorted(set(continuous_targets)))
        barriers = tuple(sorted(set(barrier_targets)))
        frozen_penalties = tuple(sorted(set(penalties)))
        values = {
            "schema_version": "conditional-forecast-config/v1",
            "feature_names": list(features),
            "continuous_targets": list(continuous),
            "barrier_targets": list(barriers),
            "train_validation_policy": train_validation_policy,
            "penalties": [str(item) for item in frozen_penalties],
            "hyperparameter_search_budget": hyperparameter_search_budget,
            "random_seed": random_seed,
            "minimum_training_samples": minimum_training_samples,
            "cost_assumption": str(cost_assumption),
        }
        digest = canonical_hash(values)
        return cls(
            ArtifactId(f"conditional-forecast-config:{digest[7:]}"),
            digest,
            features,
            continuous,
            barriers,
            train_validation_policy,
            frozen_penalties,
            hyperparameter_search_budget,
            random_seed,
            minimum_training_samples,
            cost_assumption,
        )

    @property
    def reference(self) -> ValidationArtifactReference:
        return ValidationArtifactReference(
            "CONDITIONAL_FORECAST_CONFIG",
            self.configuration_id,
            self.configuration_hash,
        )

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "feature_names": list(self.feature_names),
            "continuous_targets": list(self.continuous_targets),
            "barrier_targets": list(self.barrier_targets),
            "train_validation_policy": self.train_validation_policy,
            "penalties": [str(item) for item in self.penalties],
            "hyperparameter_search_budget": self.hyperparameter_search_budget,
            "random_seed": self.random_seed,
            "minimum_training_samples": self.minimum_training_samples,
            "cost_assumption": str(self.cost_assumption),
        }


@dataclass(frozen=True, slots=True)
class ConditionalForecastSample:
    sample_id: str
    sample_decision_time: datetime
    target_available_at: datetime
    features: Mapping[str, Decimal | None]
    continuous_targets: Mapping[str, Decimal]
    barrier_targets: Mapping[str, bool]

    def __post_init__(self) -> None:
        if not self.sample_id.strip():
            raise ValueError("Conditional Forecast sample must be identified")
        canonical_datetime(self.sample_decision_time)
        canonical_datetime(self.target_available_at)
        if self.target_available_at <= self.sample_decision_time:
            raise ValueError("Forecast target availability must follow its DecisionTime")


@dataclass(frozen=True, slots=True)
class BaselineConditionalPrediction:
    continuous: Mapping[str, Decimal]
    raw_barrier_frequencies: Mapping[str, Decimal]
    barrier_scores_are_probabilities: bool = False


@dataclass(frozen=True, slots=True)
class ConditionalModelComparison:
    baseline_validation_mae: Decimal
    regularized_validation_mae: Decimal
    selected_model: str
    selected_penalty: Decimal


@dataclass(frozen=True, slots=True)
class ConditionalForecastResult:
    result_id: ArtifactId
    result_hash: str
    configuration_reference: ValidationArtifactReference
    model_reference: ValidationArtifactReference | None
    status: str
    admitted_sample_count: int
    future_excluded_sample_count: int
    training_sample_count: int
    validation_sample_count: int
    baseline_prediction: BaselineConditionalPrediction | None
    regularized_prediction: RegularizedPrediction | None
    model_comparison: ConditionalModelComparison | None
    prediction_uncertainty: Decimal | None
    calibration_status: str
    limitations: tuple[str, ...]


def fit_conditional_forecast(
    config: ConditionalForecastConfig,
    *,
    samples: tuple[ConditionalForecastSample, ...],
    prediction_time: datetime,
    inference_features: Mapping[str, Decimal | None],
) -> ConditionalForecastResult:
    """Fit only samples whose realized targets were available at prediction time."""

    canonical_datetime(prediction_time)
    if set(inference_features) != set(config.feature_names):
        raise ValueError("Conditional Forecast inference features drifted")
    ordered = tuple(sorted(samples, key=lambda item: (item.sample_decision_time, item.sample_id)))
    ids = tuple(item.sample_id for item in ordered)
    if len(ids) != len(set(ids)):
        raise ValueError("Conditional Forecast samples must be unique")
    for item in ordered:
        if set(item.features) != set(config.feature_names):
            raise ValueError("Conditional Forecast sample feature set drifted")
        if set(item.continuous_targets) != set(config.continuous_targets):
            raise ValueError("Conditional Forecast continuous Target set drifted")
        if set(item.barrier_targets) != set(config.barrier_targets):
            raise ValueError("Conditional Forecast barrier Target set drifted")
    admitted = tuple(
        item
        for item in ordered
        if item.sample_decision_time < prediction_time
        and item.target_available_at <= prediction_time
    )
    excluded_count = len(ordered) - len(admitted)
    limitations = (
        "CALIBRATED_FALSE",
        "FORMAL_OOS_FALSE",
        "PRODUCTION_QUALIFIED_FALSE",
        "RAW_BARRIER_SCORES_NOT_PROBABILITIES",
        "RESEARCH_ONLY",
    )
    if len(admitted) < config.minimum_training_samples:
        return _insufficient(config, len(admitted), excluded_count, limitations)

    split = max(1, int(Decimal(len(admitted)) * Decimal("0.75")))
    split = min(split, len(admitted) - 1)
    training = admitted[:split]
    validation = admitted[split:]
    if len(training) < 2 or not validation:
        return _insufficient(config, len(admitted), excluded_count, limitations)
    matrix = _matrix(config, training)
    baseline = _baseline(config, training)
    baseline_mae = _baseline_mae(baseline, validation)
    candidates: list[tuple[Decimal, Decimal, RegularizedMultiTargetModel]] = []
    for penalty in config.penalties:
        try:
            model = fit_regularized_multi_target(matrix, penalty=penalty)
        except ValueError:
            continue
        error = _regularized_mae(model, validation)
        candidates.append((error, penalty, model))
    if not candidates:
        return _insufficient(config, len(admitted), excluded_count, limitations)
    regularized_mae, selected_penalty, model = min(candidates, key=lambda item: (item[0], item[1]))
    prediction = model.predict(inference_features)
    comparison = ConditionalModelComparison(
        baseline_mae,
        regularized_mae,
        "REGULARIZED_LINEAR" if regularized_mae <= baseline_mae else "EMPIRICAL_BASELINE",
        selected_penalty,
    )
    residuals = tuple(
        item.continuous_targets["t_plus_1_return"]
        - model.predict(item.features).continuous["t_plus_1_return"]
        for item in validation
    )
    uncertainty = Decimal(str(pstdev(float(item) for item in residuals))) if len(residuals) > 1 else abs(residuals[0])
    model_payload = {
        "configuration_reference": config.reference.to_canonical_dict(),
        "selected_penalty": str(selected_penalty),
        "model": model.to_canonical_dict(),
        "training_sample_ids": [item.sample_id for item in training],
        "validation_sample_ids": [item.sample_id for item in validation],
        "fit_available_at": canonical_datetime(prediction_time),
    }
    model_hash = canonical_hash(model_payload)
    model_reference = ValidationArtifactReference(
        "CONDITIONAL_FORECAST_MODEL",
        ArtifactId(f"conditional-forecast-model:{model_hash[7:]}"),
        model_hash,
    )
    values = {
        "configuration_reference": config.reference.to_canonical_dict(),
        "model_reference": model_reference.to_canonical_dict(),
        "status": "AVAILABLE_FOR_RESEARCH",
        "admitted_sample_count": len(admitted),
        "future_excluded_sample_count": excluded_count,
        "training_sample_count": len(training),
        "validation_sample_count": len(validation),
        "baseline_prediction": _baseline_payload(baseline),
        "regularized_prediction": _regularized_payload(prediction),
        "model_comparison": _comparison_payload(comparison),
        "prediction_uncertainty": str(uncertainty),
        "calibration_status": "NOT_CALIBRATED",
        "limitations": list(limitations),
    }
    digest = canonical_hash(values)
    return ConditionalForecastResult(
        ArtifactId(f"conditional-forecast-result:{digest[7:]}"),
        digest,
        config.reference,
        model_reference,
        "AVAILABLE_FOR_RESEARCH",
        len(admitted),
        excluded_count,
        len(training),
        len(validation),
        baseline,
        prediction,
        comparison,
        uncertainty,
        "NOT_CALIBRATED",
        limitations,
    )


def _insufficient(
    config: ConditionalForecastConfig,
    admitted: int,
    excluded: int,
    limitations: tuple[str, ...],
) -> ConditionalForecastResult:
    values = {
        "configuration_reference": config.reference.to_canonical_dict(),
        "model_reference": None,
        "status": "DATA_INSUFFICIENT",
        "admitted_sample_count": admitted,
        "future_excluded_sample_count": excluded,
        "training_sample_count": 0,
        "validation_sample_count": 0,
        "baseline_prediction": None,
        "regularized_prediction": None,
        "model_comparison": None,
        "prediction_uncertainty": None,
        "calibration_status": "NOT_CALIBRATED",
        "limitations": list(limitations),
    }
    digest = canonical_hash(values)
    return ConditionalForecastResult(
        ArtifactId(f"conditional-forecast-result:{digest[7:]}"),
        digest,
        config.reference,
        None,
        "DATA_INSUFFICIENT",
        admitted,
        excluded,
        0,
        0,
        None,
        None,
        None,
        None,
        "NOT_CALIBRATED",
        limitations,
    )


def _matrix(
    config: ConditionalForecastConfig,
    samples: tuple[ConditionalForecastSample, ...],
) -> TrainingMatrix:
    return TrainingMatrix.create(
        feature_names=config.feature_names,
        rows=tuple(item.features for item in samples),
        continuous_targets={
            target: tuple(item.continuous_targets[target] for item in samples)
            for target in config.continuous_targets
        },
        barrier_targets={
            target: tuple(item.barrier_targets[target] for item in samples)
            for target in config.barrier_targets
        },
    )


def _baseline(
    config: ConditionalForecastConfig,
    samples: tuple[ConditionalForecastSample, ...],
) -> BaselineConditionalPrediction:
    return BaselineConditionalPrediction(
        continuous={
            target: sum((item.continuous_targets[target] for item in samples), Decimal("0")) / Decimal(len(samples))
            for target in config.continuous_targets
        },
        raw_barrier_frequencies={
            target: Decimal(sum(item.barrier_targets[target] for item in samples)) / Decimal(len(samples))
            for target in config.barrier_targets
        },
    )


def _baseline_mae(
    prediction: BaselineConditionalPrediction,
    samples: tuple[ConditionalForecastSample, ...],
) -> Decimal:
    errors = tuple(
        abs(item.continuous_targets[target] - prediction.continuous[target])
        for item in samples
        for target in prediction.continuous
    )
    return sum(errors, Decimal("0")) / Decimal(len(errors))


def _regularized_mae(
    model: RegularizedMultiTargetModel,
    samples: tuple[ConditionalForecastSample, ...],
) -> Decimal:
    errors = tuple(
        abs(item.continuous_targets[target] - prediction.continuous[target])
        for item in samples
        for prediction in (model.predict(item.features),)
        for target in prediction.continuous
    )
    return sum(errors, Decimal("0")) / Decimal(len(errors))


def _baseline_payload(value: BaselineConditionalPrediction) -> dict[str, Any]:
    return {
        "continuous": {key: str(item) for key, item in sorted(value.continuous.items())},
        "raw_barrier_frequencies": {
            key: str(item) for key, item in sorted(value.raw_barrier_frequencies.items())
        },
        "barrier_scores_are_probabilities": value.barrier_scores_are_probabilities,
    }


def _regularized_payload(value: RegularizedPrediction) -> dict[str, Any]:
    return {
        "continuous": {key: str(item) for key, item in sorted(value.continuous.items())},
        "raw_barrier_logits": {
            key: str(item) for key, item in sorted(value.raw_barrier_logits.items())
        },
        "barrier_scores_are_probabilities": value.barrier_scores_are_probabilities,
    }


def _comparison_payload(value: ConditionalModelComparison) -> dict[str, str]:
    return {
        "baseline_validation_mae": str(value.baseline_validation_mae),
        "regularized_validation_mae": str(value.regularized_validation_mae),
        "selected_model": value.selected_model,
        "selected_penalty": str(value.selected_penalty),
    }


__all__ = [
    "BaselineConditionalPrediction",
    "ConditionalForecastConfig",
    "ConditionalForecastResult",
    "ConditionalForecastSample",
    "ConditionalModelComparison",
    "fit_conditional_forecast",
]
