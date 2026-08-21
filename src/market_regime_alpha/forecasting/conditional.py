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
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    require_sha256,
)
from market_regime_alpha.forecasting.regularized_linear import (
    RegularizedMultiTargetModel,
    RegularizedPrediction,
    TrainingMatrix,
    fit_regularized_multi_target,
)
from market_regime_alpha.forecasting.path import PathForecastArtifact
from market_regime_alpha.forecasting.contracts import PathForecastStatus


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
    candidate_reference: ValidationArtifactReference
    signal_reference: ValidationArtifactReference
    context_reference: ValidationArtifactReference
    target_reference: ValidationArtifactReference

    def __post_init__(self) -> None:
        if not self.sample_id.strip():
            raise ValueError("Conditional Forecast sample must be identified")
        canonical_datetime(self.sample_decision_time)
        canonical_datetime(self.target_available_at)
        if self.target_available_at <= self.sample_decision_time:
            raise ValueError("Forecast target availability must follow its DecisionTime")
        if self.candidate_reference.artifact_kind != "CANDIDATE_SET":
            raise ValueError("Conditional Forecast sample requires Candidate owner lineage")
        if self.signal_reference.artifact_kind not in {
            "SIGNAL_SNAPSHOT",
            "CANONICAL_SIGNAL_SNAPSHOT",
            "HISTORICAL_SIGNAL",
        }:
            raise ValueError("Conditional Forecast sample requires Signal owner lineage")
        if self.context_reference.artifact_kind not in {
            "CONTEXT_CONDITIONAL_EVALUATION",
            "HISTORICAL_CONTEXT",
        }:
            raise ValueError("Conditional Forecast sample requires Context owner lineage")
        if self.target_reference.artifact_kind not in {
            "OUTCOME_TARGET",
            "HISTORICAL_OUTCOME_TARGET",
        }:
            raise ValueError("Conditional Forecast sample requires Target owner lineage")
        if any(
            value is not None and not value.is_finite()
            for value in self.features.values()
        ) or any(not value.is_finite() for value in self.continuous_targets.values()):
            raise ValueError("Conditional Forecast sample values must be finite")

    @property
    def sample_hash(self) -> str:
        return canonical_hash(
            {
                "sample_id": self.sample_id,
                "sample_decision_time": canonical_datetime(self.sample_decision_time),
                "target_available_at": canonical_datetime(self.target_available_at),
                "features": {
                    key: None if value is None else str(value)
                    for key, value in sorted(self.features.items())
                },
                "continuous_targets": {
                    key: str(value)
                    for key, value in sorted(self.continuous_targets.items())
                },
                "barrier_targets": dict(sorted(self.barrier_targets.items())),
                "candidate_reference": self.candidate_reference.to_canonical_dict(),
                "signal_reference": self.signal_reference.to_canonical_dict(),
                "context_reference": self.context_reference.to_canonical_dict(),
                "target_reference": self.target_reference.to_canonical_dict(),
            }
        )


@dataclass(frozen=True, slots=True)
class BaselineConditionalPrediction:
    forecast_reference: ValidationArtifactReference
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
    regularized_model_reference: ValidationArtifactReference | None
    baseline_reference: ValidationArtifactReference
    regularized_model: RegularizedMultiTargetModel | None
    training_sample_ids: tuple[str, ...]
    validation_sample_ids: tuple[str, ...]
    training_sample_bindings: tuple[tuple[str, str], ...]
    validation_sample_bindings: tuple[tuple[str, str], ...]
    fit_available_at: datetime | None
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

    def __post_init__(self) -> None:
        require_sha256("result_hash", self.result_hash)
        if self.training_sample_ids != tuple(item[0] for item in self.training_sample_bindings):
            raise ValueError("Conditional Forecast training lineage projection mismatch")
        if self.validation_sample_ids != tuple(item[0] for item in self.validation_sample_bindings):
            raise ValueError("Conditional Forecast validation lineage projection mismatch")
        all_ids = (*self.training_sample_ids, *self.validation_sample_ids)
        if len(all_ids) != len(set(all_ids)):
            raise ValueError("Conditional Forecast sample lineage must be disjoint")
        for _sample_id, sample_hash in (
            *self.training_sample_bindings,
            *self.validation_sample_bindings,
        ):
            require_sha256("Conditional Forecast sample hash", sample_hash)
        if canonical_hash(self.identity_payload()) != self.result_hash:
            raise ValueError("Conditional Forecast result hash mismatch")
        if str(self.result_id) != f"conditional-forecast-result:{self.result_hash[7:]}":
            raise ValueError("Conditional Forecast result identity mismatch")
        if self.regularized_model is not None:
            if (
                self.regularized_model_reference is None
                or self.model_comparison is None
                or self.fit_available_at is None
            ):
                raise ValueError("Conditional Forecast model lineage is incomplete")
            if canonical_hash(self.regularized_model_payload()) != self.regularized_model_reference.content_hash:
                raise ValueError("Conditional Forecast model reference is not reconstructible")
        if self.status == "AVAILABLE_FOR_RESEARCH" and (
            self.model_reference is None
            or self.baseline_prediction is None
            or self.regularized_prediction is None
        ):
            raise ValueError("available Conditional Forecast result is incomplete")
        if self.status == "DATA_INSUFFICIENT" and (
            self.model_reference is not None
            or self.training_sample_bindings
            or self.validation_sample_bindings
            or self.fit_available_at is not None
        ):
            raise ValueError("insufficient Conditional Forecast cannot expose fitted lineage")

    @property
    def reference(self) -> ValidationArtifactReference:
        return ValidationArtifactReference(
            "CONDITIONAL_FORECAST_RESULT", self.result_id, self.result_hash
        )

    def regularized_model_payload(self) -> dict[str, Any]:
        if self.regularized_model is None or self.model_comparison is None or self.fit_available_at is None:
            raise ValueError("Conditional Forecast regularized model is unavailable")
        return {
            "configuration_reference": self.configuration_reference.to_canonical_dict(),
            "selected_penalty": str(self.model_comparison.selected_penalty),
            "model": self.regularized_model.to_canonical_dict(),
            "training_sample_bindings": [list(item) for item in self.training_sample_bindings],
            "validation_sample_bindings": [list(item) for item in self.validation_sample_bindings],
            "fit_available_at": canonical_datetime(self.fit_available_at),
        }

    def identity_payload(self) -> dict[str, Any]:
        return {
            "configuration_reference": self.configuration_reference.to_canonical_dict(),
            "model_reference": (
                None if self.model_reference is None else self.model_reference.to_canonical_dict()
            ),
            "regularized_model_reference": (
                None
                if self.regularized_model_reference is None
                else self.regularized_model_reference.to_canonical_dict()
            ),
            "baseline_reference": self.baseline_reference.to_canonical_dict(),
            "regularized_model": (
                None if self.regularized_model is None else self.regularized_model.to_canonical_dict()
            ),
            "training_sample_ids": list(self.training_sample_ids),
            "validation_sample_ids": list(self.validation_sample_ids),
            "training_sample_bindings": [
                list(item) for item in self.training_sample_bindings
            ],
            "validation_sample_bindings": [
                list(item) for item in self.validation_sample_bindings
            ],
            "fit_available_at": (
                None
                if self.fit_available_at is None
                else canonical_datetime(self.fit_available_at)
            ),
            "status": self.status,
            "admitted_sample_count": self.admitted_sample_count,
            "future_excluded_sample_count": self.future_excluded_sample_count,
            "training_sample_count": self.training_sample_count,
            "validation_sample_count": self.validation_sample_count,
            "baseline_prediction": (
                None if self.baseline_prediction is None else _baseline_payload(self.baseline_prediction)
            ),
            "regularized_prediction": (
                None if self.regularized_prediction is None else _regularized_payload(self.regularized_prediction)
            ),
            "model_comparison": (
                None if self.model_comparison is None else _comparison_payload(self.model_comparison)
            ),
            "prediction_uncertainty": (
                None if self.prediction_uncertainty is None else str(self.prediction_uncertainty)
            ),
            "calibration_status": self.calibration_status,
            "limitations": list(self.limitations),
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "result_id": str(self.result_id),
            "result_hash": self.result_hash,
            "configuration_reference": self.configuration_reference.to_canonical_dict(),
            "model_reference": (
                None
                if self.model_reference is None
                else self.model_reference.to_canonical_dict()
            ),
            "regularized_model_reference": (
                None
                if self.regularized_model_reference is None
                else self.regularized_model_reference.to_canonical_dict()
            ),
            "baseline_reference": self.baseline_reference.to_canonical_dict(),
            "regularized_model": (
                None
                if self.regularized_model is None
                else self.regularized_model.to_canonical_dict()
            ),
            "training_sample_ids": list(self.training_sample_ids),
            "validation_sample_ids": list(self.validation_sample_ids),
            "training_sample_bindings": [list(item) for item in self.training_sample_bindings],
            "validation_sample_bindings": [list(item) for item in self.validation_sample_bindings],
            "fit_available_at": (
                None
                if self.fit_available_at is None
                else canonical_datetime(self.fit_available_at)
            ),
            "status": self.status,
            "admitted_sample_count": self.admitted_sample_count,
            "future_excluded_sample_count": self.future_excluded_sample_count,
            "training_sample_count": self.training_sample_count,
            "validation_sample_count": self.validation_sample_count,
            "baseline_prediction": (
                None
                if self.baseline_prediction is None
                else _baseline_payload(self.baseline_prediction)
            ),
            "regularized_prediction": (
                None
                if self.regularized_prediction is None
                else _regularized_payload(self.regularized_prediction)
            ),
            "model_comparison": (
                None
                if self.model_comparison is None
                else _comparison_payload(self.model_comparison)
            ),
            "prediction_uncertainty": (
                None
                if self.prediction_uncertainty is None
                else str(self.prediction_uncertainty)
            ),
            "calibration_status": self.calibration_status,
            "limitations": list(self.limitations),
        }


def fit_conditional_forecast(
    config: ConditionalForecastConfig,
    *,
    samples: tuple[ConditionalForecastSample, ...],
    prediction_time: datetime,
    inference_features: Mapping[str, Decimal | None],
    baseline_forecast: PathForecastArtifact,
) -> ConditionalForecastResult:
    """Fit only samples whose realized targets were available at prediction time."""

    canonical_datetime(prediction_time)
    baseline_forecast.forecast.envelope.verify_payload(
        baseline_forecast.forecast.artifact_payload()
    )
    if (
        baseline_forecast.forecast.forecast_status
        is not PathForecastStatus.AVAILABLE_FOR_RESEARCH
        or baseline_forecast.forecast.envelope.decision_time.value > prediction_time
    ):
        raise ValueError("Conditional Forecast requires an available empirical PathForecast baseline")
    baseline_reference = ValidationArtifactReference(
        "PATH_FORECAST",
        baseline_forecast.artifact_id,
        baseline_forecast.forecast.envelope.content_hash,
    )
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
        return _insufficient(
            config, baseline_reference, len(admitted), excluded_count, limitations
        )

    decision_times = tuple(sorted({item.sample_decision_time for item in admitted}))
    if len(decision_times) < 2:
        return _insufficient(
            config, baseline_reference, len(admitted), excluded_count, limitations
        )
    time_split = max(1, int(Decimal(len(decision_times)) * Decimal("0.75")))
    time_split = min(time_split, len(decision_times) - 1)
    validation_start = decision_times[time_split]
    training = tuple(
        item for item in admitted if item.sample_decision_time < validation_start
    )
    validation = tuple(
        item for item in admitted if item.sample_decision_time >= validation_start
    )
    if len(training) < config.minimum_training_samples or not validation:
        return _insufficient(
            config, baseline_reference, len(admitted), excluded_count, limitations
        )
    matrix = _matrix(config, training)
    baseline = _baseline_from_path_forecast(config, baseline_forecast)
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
        return _insufficient(
            config, baseline_reference, len(admitted), excluded_count, limitations
        )
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
    training_bindings = tuple((item.sample_id, item.sample_hash) for item in training)
    validation_bindings = tuple((item.sample_id, item.sample_hash) for item in validation)
    model_payload = {
        "configuration_reference": config.reference.to_canonical_dict(),
        "selected_penalty": str(selected_penalty),
        "model": model.to_canonical_dict(),
        "training_sample_bindings": [list(item) for item in training_bindings],
        "validation_sample_bindings": [list(item) for item in validation_bindings],
        "fit_available_at": canonical_datetime(prediction_time),
    }
    model_hash = canonical_hash(model_payload)
    regularized_model_reference = ValidationArtifactReference(
        "CONDITIONAL_FORECAST_MODEL",
        ArtifactId(f"conditional-forecast-model:{model_hash[7:]}"),
        model_hash,
    )
    selected_model_reference = (
        regularized_model_reference
        if comparison.selected_model == "REGULARIZED_LINEAR"
        else baseline_reference
    )
    values = {
        "configuration_reference": config.reference.to_canonical_dict(),
        "model_reference": selected_model_reference.to_canonical_dict(),
        "regularized_model_reference": regularized_model_reference.to_canonical_dict(),
        "baseline_reference": baseline_reference.to_canonical_dict(),
        "regularized_model": model.to_canonical_dict(),
        "training_sample_ids": [item.sample_id for item in training],
        "validation_sample_ids": [item.sample_id for item in validation],
        "training_sample_bindings": [list(item) for item in training_bindings],
        "validation_sample_bindings": [list(item) for item in validation_bindings],
        "fit_available_at": canonical_datetime(prediction_time),
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
        selected_model_reference,
        regularized_model_reference,
        baseline_reference,
        model,
        tuple(item.sample_id for item in training),
        tuple(item.sample_id for item in validation),
        training_bindings,
        validation_bindings,
        prediction_time,
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
    baseline_reference: ValidationArtifactReference,
    admitted: int,
    excluded: int,
    limitations: tuple[str, ...],
) -> ConditionalForecastResult:
    values = {
        "configuration_reference": config.reference.to_canonical_dict(),
        "model_reference": None,
        "regularized_model_reference": None,
        "baseline_reference": baseline_reference.to_canonical_dict(),
        "regularized_model": None,
        "training_sample_ids": [],
        "validation_sample_ids": [],
        "training_sample_bindings": [],
        "validation_sample_bindings": [],
        "fit_available_at": None,
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
        None,
        baseline_reference,
        None,
        (),
        (),
        (),
        (),
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


def _baseline_from_path_forecast(
    config: ConditionalForecastConfig,
    artifact: PathForecastArtifact,
) -> BaselineConditionalPrediction:
    forecast = artifact.forecast
    median = next(
        (
            item.return_value
            for item in forecast.return_quantiles
            if item.probability == 0.5
        ),
        None,
    )
    if median is None or forecast.expected_mfe is None or forecast.expected_mae is None:
        raise ValueError("empirical PathForecast baseline lacks required path estimates")
    available_samples = tuple(
        item
        for item in artifact.samples
        if item.realized_mfe is not None and item.realized_mae is not None
    )
    if not available_samples:
        raise ValueError("empirical PathForecast baseline lacks resolved path samples")
    return BaselineConditionalPrediction(
        forecast_reference=ValidationArtifactReference(
            "PATH_FORECAST",
            artifact.artifact_id,
            forecast.envelope.content_hash,
        ),
        continuous={
            "mae": Decimal(str(forecast.expected_mae)),
            "mfe": Decimal(str(forecast.expected_mfe)),
            "t_plus_1_return": Decimal(str(median)),
        },
        raw_barrier_frequencies={
            "lower_barrier": Decimal(
                sum(
                    item.realized_mae <= forecast.lower_barrier_return
                    for item in available_samples
                    if item.realized_mae is not None
                )
            )
            / Decimal(len(available_samples)),
            "upper_barrier": Decimal(
                sum(
                    item.realized_mfe >= forecast.upper_barrier_return
                    for item in available_samples
                    if item.realized_mfe is not None
                )
            )
            / Decimal(len(available_samples)),
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
        "forecast_reference": value.forecast_reference.to_canonical_dict(),
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
