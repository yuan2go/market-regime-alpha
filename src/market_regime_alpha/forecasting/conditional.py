"""Conditional Forecast selection over canonical Research Model owners.

This module does not train or persist a second model. It compares the
PostgreSQL-owned Research Model against as-of empirical Path Forecasts using
the frozen walk-forward folds, then emits one research selection artifact.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from statistics import pstdev
from typing import Any, Mapping

from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.application.research_validation.research_model import (
    ResearchForecastStatus,
    ResearchModelArtifact,
    ResearchModelInferenceReceipt,
    ResearchModelStatus,
    ResearchModelTrainingRequest,
    ResearchTrainingSample,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    require_sha256,
)
from market_regime_alpha.forecasting.contracts import PathForecastStatus
from market_regime_alpha.forecasting.path import PathForecastArtifact
from market_regime_alpha.forecasting.regularized_linear import (
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
    minimum_validation_samples: int
    expected_return_target: str
    baseline_target_id: str
    baseline_horizon: str
    cost_assumption: Decimal
    schema_version: str = "conditional-forecast-config/v2"

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
        if self.expected_return_target != "t_plus_1_return":
            raise ValueError("Conditional Forecast expected-return Target is frozen")
        if not self.baseline_target_id.strip() or not self.baseline_horizon.strip():
            raise ValueError("Conditional Forecast baseline Target must be frozen")
        if self.train_validation_policy != "OWNER_WALK_FORWARD_PURGED":
            raise ValueError("unsupported Conditional Forecast split")
        if self.penalties != tuple(sorted(set(self.penalties))) or any(
            item <= 0 for item in self.penalties
        ):
            raise ValueError("Conditional Forecast penalties must be positive and frozen")
        if self.hyperparameter_search_budget != len(self.penalties):
            raise ValueError("hyperparameter budget must equal the frozen search space")
        if self.minimum_training_samples <= 0 or self.minimum_validation_samples <= 0:
            raise ValueError("Conditional Forecast sample floors must be positive")
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
        minimum_validation_samples: int = 1,
        expected_return_target: str = "t_plus_1_return",
        baseline_target_id: str,
        baseline_horizon: str,
    ) -> ConditionalForecastConfig:
        features = tuple(sorted(set(feature_names)))
        continuous = tuple(sorted(set(continuous_targets)))
        barriers = tuple(sorted(set(barrier_targets)))
        frozen_penalties = tuple(sorted(set(penalties)))
        values = {
            "schema_version": "conditional-forecast-config/v2",
            "feature_names": list(features),
            "continuous_targets": list(continuous),
            "barrier_targets": list(barriers),
            "train_validation_policy": train_validation_policy,
            "penalties": [str(item) for item in frozen_penalties],
            "hyperparameter_search_budget": hyperparameter_search_budget,
            "random_seed": random_seed,
            "minimum_training_samples": minimum_training_samples,
            "minimum_validation_samples": minimum_validation_samples,
            "expected_return_target": expected_return_target,
            "baseline_target_id": baseline_target_id,
            "baseline_horizon": baseline_horizon,
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
            minimum_validation_samples,
            expected_return_target,
            baseline_target_id,
            baseline_horizon,
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
            "minimum_validation_samples": self.minimum_validation_samples,
            "expected_return_target": self.expected_return_target,
            "baseline_target_id": self.baseline_target_id,
            "baseline_horizon": self.baseline_horizon,
            "cost_assumption": str(self.cost_assumption),
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "configuration_id": str(self.configuration_id),
            "configuration_hash": self.configuration_hash,
            **self.identity_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> ConditionalForecastConfig:
        return cls(
            configuration_id=ArtifactId(str(payload["configuration_id"])),
            configuration_hash=str(payload["configuration_hash"]),
            feature_names=tuple(str(item) for item in _sequence(payload["feature_names"])),
            continuous_targets=tuple(
                str(item) for item in _sequence(payload["continuous_targets"])
            ),
            barrier_targets=tuple(
                str(item) for item in _sequence(payload["barrier_targets"])
            ),
            train_validation_policy=str(payload["train_validation_policy"]),
            penalties=tuple(
                Decimal(str(item)) for item in _sequence(payload["penalties"])
            ),
            hyperparameter_search_budget=int(payload["hyperparameter_search_budget"]),
            random_seed=int(payload["random_seed"]),
            minimum_training_samples=int(payload["minimum_training_samples"]),
            minimum_validation_samples=int(payload["minimum_validation_samples"]),
            expected_return_target=str(payload["expected_return_target"]),
            baseline_target_id=str(payload["baseline_target_id"]),
            baseline_horizon=str(payload["baseline_horizon"]),
            cost_assumption=Decimal(str(payload["cost_assumption"])),
            schema_version=str(payload["schema_version"]),
        )


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
    training_request_reference: ValidationArtifactReference
    model_reference: ValidationArtifactReference | None
    inference_reference: ValidationArtifactReference | None
    baseline_reference: ValidationArtifactReference
    training_sample_bindings: tuple[tuple[str, str], ...]
    validation_sample_bindings: tuple[tuple[str, str], ...]
    fit_available_at: datetime | None
    status: str
    training_sample_count: int
    validation_sample_count: int
    model_comparison: ConditionalModelComparison | None
    selected_expected_return: Decimal | None
    prediction_uncertainty: Decimal | None
    raw_barrier_scores: tuple[tuple[str, Decimal], ...]
    calibration_status: str
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        require_sha256("Conditional Forecast result hash", self.result_hash)
        for _sample_id, sample_hash in (
            *self.training_sample_bindings,
            *self.validation_sample_bindings,
        ):
            require_sha256("Conditional Forecast sample hash", sample_hash)
        if self.training_sample_bindings != tuple(
            sorted(set(self.training_sample_bindings))
        ) or self.validation_sample_bindings != tuple(
            sorted(set(self.validation_sample_bindings))
        ):
            raise ValueError("Conditional Forecast sample bindings must be unique and sorted")
        if self.status == "AVAILABLE_FOR_RESEARCH" and (
            self.model_reference is None
            or self.inference_reference is None
            or self.fit_available_at is None
            or self.model_comparison is None
            or self.selected_expected_return is None
        ):
            raise ValueError("available Conditional Forecast owner bindings are incomplete")
        if self.status == "AVAILABLE_FOR_RESEARCH" and (
            len(self.training_sample_bindings) != self.training_sample_count
            or len(self.validation_sample_bindings) != self.validation_sample_count
            or self.model_reference
            not in {self.baseline_reference, self.inference_model_reference}
        ):
            raise ValueError("available Conditional Forecast population/model binding drifted")
        if self.status == "DATA_INSUFFICIENT" and any(
            item is not None
            for item in (
                self.model_reference,
                self.inference_reference,
                self.fit_available_at,
                self.model_comparison,
                self.selected_expected_return,
            )
        ):
            raise ValueError("insufficient Conditional Forecast cannot expose model lineage")
        if self.calibration_status != "NOT_CALIBRATED":
            raise ValueError("Conditional Forecast has no calibration authority")
        digest = canonical_hash(self.identity_payload())
        if digest != self.result_hash or self.result_id != ArtifactId(
            f"conditional-forecast-result:{digest[7:]}"
        ):
            raise ValueError("Conditional Forecast result identity mismatch")

    @property
    def inference_model_reference(self) -> ValidationArtifactReference | None:
        return (
            self.model_reference
            if self.model_reference is not None
            and self.model_reference.artifact_kind == "RESEARCH_MODEL_ARTIFACT"
            else None
        )

    @property
    def reference(self) -> ValidationArtifactReference:
        return ValidationArtifactReference(
            "CONDITIONAL_FORECAST_RESULT", self.result_id, self.result_hash
        )

    def identity_payload(self) -> dict[str, Any]:
        return {
            "configuration_reference": self.configuration_reference.to_canonical_dict(),
            "training_request_reference": self.training_request_reference.to_canonical_dict(),
            "model_reference": _reference_payload(self.model_reference),
            "inference_reference": _reference_payload(self.inference_reference),
            "baseline_reference": self.baseline_reference.to_canonical_dict(),
            "training_sample_bindings": [list(item) for item in self.training_sample_bindings],
            "validation_sample_bindings": [list(item) for item in self.validation_sample_bindings],
            "fit_available_at": (
                None if self.fit_available_at is None else canonical_datetime(self.fit_available_at)
            ),
            "status": self.status,
            "training_sample_count": self.training_sample_count,
            "validation_sample_count": self.validation_sample_count,
            "model_comparison": (
                None if self.model_comparison is None else _comparison_payload(self.model_comparison)
            ),
            "selected_expected_return": (
                None if self.selected_expected_return is None else str(self.selected_expected_return)
            ),
            "prediction_uncertainty": (
                None if self.prediction_uncertainty is None else str(self.prediction_uncertainty)
            ),
            "raw_barrier_scores": [
                [name, str(value)] for name, value in self.raw_barrier_scores
            ],
            "calibration_status": self.calibration_status,
            "limitations": list(self.limitations),
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "result_id": str(self.result_id),
            "result_hash": self.result_hash,
            **self.identity_payload(),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> ConditionalForecastResult:
        raw_comparison = payload.get("model_comparison")
        return cls(
            ArtifactId(str(payload["result_id"])),
            str(payload["result_hash"]),
            _reference(payload["configuration_reference"]),
            _reference(payload["training_request_reference"]),
            _optional_reference(payload.get("model_reference")),
            _optional_reference(payload.get("inference_reference")),
            _reference(payload["baseline_reference"]),
            _bindings(payload["training_sample_bindings"]),
            _bindings(payload["validation_sample_bindings"]),
            (
                None
                if payload.get("fit_available_at") is None
                else datetime.fromisoformat(str(payload["fit_available_at"]))
            ),
            str(payload["status"]),
            int(payload["training_sample_count"]),
            int(payload["validation_sample_count"]),
            (
                None
                if raw_comparison is None
                else _comparison_from_payload(_mapping(raw_comparison))
            ),
            _optional_decimal(payload.get("selected_expected_return")),
            _optional_decimal(payload.get("prediction_uncertainty")),
            tuple(
                (str(item[0]), Decimal(str(item[1])))
                for item in _sequence(payload["raw_barrier_scores"])
            ),
            str(payload["calibration_status"]),
            tuple(str(item) for item in _sequence(payload["limitations"])),
        )


def fit_conditional_forecast(
    config: ConditionalForecastConfig,
    *,
    training_request: ResearchModelTrainingRequest,
    research_model: ResearchModelArtifact,
    inference_receipt: ResearchModelInferenceReceipt,
    baseline_forecast: PathForecastArtifact,
) -> ConditionalForecastResult:
    """Compare existing owners; training remains solely Research Model authority."""

    baseline_forecast.forecast.envelope.verify_payload(
        baseline_forecast.forecast.artifact_payload()
    )
    baseline_reference = ValidationArtifactReference(
        "PATH_FORECAST",
        baseline_forecast.artifact_id,
        baseline_forecast.forecast.envelope.content_hash,
    )
    _verify_baseline_target(config, baseline_forecast)
    request_reference = ValidationArtifactReference(
        "RESEARCH_MODEL_TRAINING_REQUEST",
        training_request.request_id,
        training_request.request_hash,
    )
    expected_model_reference = ValidationArtifactReference(
        "RESEARCH_MODEL_ARTIFACT",
        research_model.artifact_id,
        research_model.artifact_hash,
    )
    if research_model.request_reference != request_reference:
        raise ValueError("Conditional Forecast Research Model Request owner drifted")
    if inference_receipt.model_reference != expected_model_reference:
        raise ValueError("Conditional Forecast inference Model owner drifted")
    if (
        inference_receipt.result.symbol != baseline_forecast.forecast.symbol
        or inference_receipt.result.decision_time
        != baseline_forecast.forecast.envelope.decision_time.value
    ):
        raise ValueError("Conditional Forecast baseline/inference Decision binding drifted")
    if tuple(training_request.feature_names) != config.feature_names:
        raise ValueError("Conditional Forecast Feature set drifted from Model Request")
    if tuple(training_request.continuous_target_names) != config.continuous_targets:
        raise ValueError("Conditional Forecast continuous Target set drifted")
    if tuple(training_request.barrier_target_names) != config.barrier_targets:
        raise ValueError("Conditional Forecast barrier Target set drifted")
    if training_request.penalty_candidates != config.penalties:
        raise ValueError("Conditional Forecast search space drifted from Model Request")
    if training_request.fold_seed != config.random_seed:
        raise ValueError("Conditional Forecast randomness drifted from Model Request")
    validation_ids = {
        sample_id for fold in training_request.folds for sample_id in fold.validation_sample_ids
    }
    training_ids = {
        sample_id for fold in training_request.folds for sample_id in fold.train_sample_ids
    }
    sample_by_id = {sample.sample_id: sample for sample in training_request.samples}
    training_bindings = tuple(
        sorted((str(item), sample_by_id[item].sample_hash) for item in training_ids)
    )
    validation_bindings = tuple(
        sorted((str(item), sample_by_id[item].sample_hash) for item in validation_ids)
    )
    minimum_ok = (
        len(training_ids) >= config.minimum_training_samples
        and len(validation_ids) >= config.minimum_validation_samples
        and all(
            len(fold.train_sample_ids) >= config.minimum_training_samples
            for fold in training_request.folds
        )
    )
    owners_available = (
        research_model.status is ResearchModelStatus.AVAILABLE
        and inference_receipt.result.status is ResearchForecastStatus.AVAILABLE
        and baseline_forecast.forecast.forecast_status
        is PathForecastStatus.AVAILABLE_FOR_RESEARCH
        and research_model.selected_penalty is not None
    )
    if not minimum_ok or not owners_available:
        return _insufficient(
            config,
            request_reference,
            baseline_reference,
            training_bindings=training_bindings,
            validation_bindings=validation_bindings,
        )
    assert research_model.selected_penalty is not None
    baseline_errors: list[Decimal] = []
    baseline_residuals: list[Decimal] = []
    regularized_errors: list[Decimal] = []
    regularized_residuals: list[Decimal] = []
    for fold in training_request.folds:
        training = tuple(sample_by_id[item] for item in fold.train_sample_ids)
        validation = tuple(sample_by_id[item] for item in fold.validation_sample_ids)
        first_validation_decision = min(item.decision_time for item in validation)
        if any(
            target.available_at > first_validation_decision
            for sample in training
            for target in sample.targets
        ):
            raise ValueError(
                "Conditional Forecast fold uses a Target unavailable at validation DecisionTime"
            )
        model = fit_regularized_multi_target(
            _matrix(training_request, training),
            penalty=research_model.selected_penalty,
        )
        baseline_value = _median(
            tuple(
                _continuous_targets(item)[config.expected_return_target]
                for item in training
            )
        )
        for sample_id in fold.validation_sample_ids:
            sample = sample_by_id[sample_id]
            actual = _continuous_targets(sample)[config.expected_return_target]
            model_value = model.predict(_features(sample)).continuous[
                config.expected_return_target
            ]
            baseline_errors.append(abs(actual - baseline_value))
            baseline_residuals.append(actual - baseline_value)
            regularized_errors.append(abs(actual - model_value))
            regularized_residuals.append(actual - model_value)
    baseline_mae = _mean(tuple(baseline_errors))
    regularized_mae = _mean(tuple(regularized_errors))
    selected_model = (
        "REGULARIZED_RESEARCH_MODEL"
        if regularized_mae <= baseline_mae
        else "EMPIRICAL_PATH_BASELINE"
    )
    estimates = dict(inference_receipt.result.continuous_estimates)
    expected_return = (
        estimates.get(config.expected_return_target)
        if selected_model == "REGULARIZED_RESEARCH_MODEL"
        else _baseline_expected_return(baseline_forecast)
    )
    if expected_return is None:
        return _insufficient(
            config,
            request_reference,
            baseline_reference,
            training_bindings=training_bindings,
            validation_bindings=validation_bindings,
        )
    comparison = ConditionalModelComparison(
        baseline_mae,
        regularized_mae,
        selected_model,
        research_model.selected_penalty,
    )
    selected_residuals = (
        regularized_residuals
        if selected_model == "REGULARIZED_RESEARCH_MODEL"
        else baseline_residuals
    )
    uncertainty = (
        abs(selected_residuals[0])
        if len(selected_residuals) == 1
        else Decimal(str(pstdev(float(item) for item in selected_residuals)))
    )
    model_reference = (
        expected_model_reference
        if selected_model == "REGULARIZED_RESEARCH_MODEL"
        else baseline_reference
    )
    inference_reference = ValidationArtifactReference(
        "RESEARCH_MODEL_INFERENCE_RECEIPT",
        inference_receipt.receipt_id,
        inference_receipt.receipt_hash,
    )
    selected_barrier_scores = (
        tuple(inference_receipt.result.raw_barrier_logits)
        if selected_model == "REGULARIZED_RESEARCH_MODEL"
        else ()
    )
    limitations = (
        "CALIBRATED_FALSE",
        *(
            ("RAW_BARRIER_SCORES_NOT_PROBABILITIES",)
            if selected_barrier_scores
            else ("EMPIRICAL_BASELINE_HAS_NO_BARRIER_PROBABILITY",)
        ),
        "FORMAL_MODEL_QUALIFIED_FALSE",
        "FORMAL_OOS_FALSE",
        "NO_PRODUCTION_AUTHORITY",
        "RESEARCH_ONLY",
    )
    values = _result_payload(
        config.reference,
        request_reference,
        model_reference,
        inference_reference,
        baseline_reference,
        training_bindings,
        validation_bindings,
        inference_receipt.executed_at,
        "AVAILABLE_FOR_RESEARCH",
        len(training_ids),
        len(validation_ids),
        comparison,
        expected_return,
        uncertainty,
        selected_barrier_scores,
        limitations,
    )
    digest = canonical_hash(values)
    return ConditionalForecastResult(
        ArtifactId(f"conditional-forecast-result:{digest[7:]}"),
        digest,
        config.reference,
        request_reference,
        model_reference,
        inference_reference,
        baseline_reference,
        training_bindings,
        validation_bindings,
        inference_receipt.executed_at,
        "AVAILABLE_FOR_RESEARCH",
        len(training_ids),
        len(validation_ids),
        comparison,
        expected_return,
        uncertainty,
        selected_barrier_scores,
        "NOT_CALIBRATED",
        limitations,
    )


def _insufficient(
    config: ConditionalForecastConfig,
    request_reference: ValidationArtifactReference,
    baseline_reference: ValidationArtifactReference,
    *,
    training_bindings: tuple[tuple[str, str], ...],
    validation_bindings: tuple[tuple[str, str], ...],
) -> ConditionalForecastResult:
    limitations = (
        "CALIBRATED_FALSE",
        "DATA_INSUFFICIENT",
        "FORMAL_OOS_FALSE",
        "NO_PRODUCTION_AUTHORITY",
        "RESEARCH_ONLY",
    )
    values = _result_payload(
        config.reference,
        request_reference,
        None,
        None,
        baseline_reference,
        training_bindings,
        validation_bindings,
        None,
        "DATA_INSUFFICIENT",
        len(training_bindings),
        len(validation_bindings),
        None,
        None,
        None,
        (),
        limitations,
    )
    digest = canonical_hash(values)
    return ConditionalForecastResult(
        ArtifactId(f"conditional-forecast-result:{digest[7:]}"),
        digest,
        config.reference,
        request_reference,
        None,
        None,
        baseline_reference,
        training_bindings,
        validation_bindings,
        None,
        "DATA_INSUFFICIENT",
        len(training_bindings),
        len(validation_bindings),
        None,
        None,
        None,
        (),
        "NOT_CALIBRATED",
        limitations,
    )


def _matrix(
    request: ResearchModelTrainingRequest,
    samples: tuple[ResearchTrainingSample, ...],
) -> TrainingMatrix:
    return TrainingMatrix.create(
        feature_names=request.feature_names,
        rows=tuple(_features(item) for item in samples),
        continuous_targets={
            name: tuple(_continuous_targets(item)[name] for item in samples)
            for name in request.continuous_target_names
        },
        barrier_targets={
            name: tuple(_barrier_targets(item)[name] for item in samples)
            for name in request.barrier_target_names
        },
    )


def _features(sample: ResearchTrainingSample) -> dict[str, Decimal | None]:
    return {item.name: item.value for item in sample.features}


def _continuous_targets(sample: ResearchTrainingSample) -> dict[str, Decimal]:
    return {
        item.name: item.value
        for item in sample.targets
        if isinstance(item.value, Decimal)
    }


def _barrier_targets(sample: ResearchTrainingSample) -> dict[str, bool]:
    return {
        item.name: item.value
        for item in sample.targets
        if isinstance(item.value, bool)
    }


def _verify_baseline_target(
    config: ConditionalForecastConfig,
    baseline: PathForecastArtifact,
) -> None:
    if (
        str(baseline.forecast.target_id) != config.baseline_target_id
        or baseline.forecast.forecast_horizon != config.baseline_horizon
    ):
        raise ValueError("Conditional Forecast Path baseline Target drifted")


def _baseline_expected_return(baseline: PathForecastArtifact) -> Decimal | None:
    return next(
        (
            Decimal(str(item.return_value))
            for item in baseline.forecast.return_quantiles
            if Decimal(str(item.probability)) == Decimal("0.5")
        ),
        None,
    )


def _result_payload(
    configuration_reference: ValidationArtifactReference,
    training_request_reference: ValidationArtifactReference,
    model_reference: ValidationArtifactReference | None,
    inference_reference: ValidationArtifactReference | None,
    baseline_reference: ValidationArtifactReference,
    training_sample_bindings: tuple[tuple[str, str], ...],
    validation_sample_bindings: tuple[tuple[str, str], ...],
    fit_available_at: datetime | None,
    status: str,
    training_sample_count: int,
    validation_sample_count: int,
    model_comparison: ConditionalModelComparison | None,
    selected_expected_return: Decimal | None,
    prediction_uncertainty: Decimal | None,
    raw_barrier_scores: tuple[tuple[str, Decimal], ...],
    limitations: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "configuration_reference": configuration_reference.to_canonical_dict(),
        "training_request_reference": training_request_reference.to_canonical_dict(),
        "model_reference": _reference_payload(model_reference),
        "inference_reference": _reference_payload(inference_reference),
        "baseline_reference": baseline_reference.to_canonical_dict(),
        "training_sample_bindings": [list(item) for item in training_sample_bindings],
        "validation_sample_bindings": [list(item) for item in validation_sample_bindings],
        "fit_available_at": (
            None if fit_available_at is None else canonical_datetime(fit_available_at)
        ),
        "status": status,
        "training_sample_count": training_sample_count,
        "validation_sample_count": validation_sample_count,
        "model_comparison": (
            None if model_comparison is None else _comparison_payload(model_comparison)
        ),
        "selected_expected_return": (
            None if selected_expected_return is None else str(selected_expected_return)
        ),
        "prediction_uncertainty": (
            None if prediction_uncertainty is None else str(prediction_uncertainty)
        ),
        "raw_barrier_scores": [
            [name, str(value)] for name, value in raw_barrier_scores
        ],
        "calibration_status": "NOT_CALIBRATED",
        "limitations": list(limitations),
    }


def _comparison_payload(value: ConditionalModelComparison) -> dict[str, str]:
    return {
        "baseline_validation_mae": str(value.baseline_validation_mae),
        "regularized_validation_mae": str(value.regularized_validation_mae),
        "selected_model": value.selected_model,
        "selected_penalty": str(value.selected_penalty),
    }


def _comparison_from_payload(value: Mapping[str, Any]) -> ConditionalModelComparison:
    return ConditionalModelComparison(
        Decimal(str(value["baseline_validation_mae"])),
        Decimal(str(value["regularized_validation_mae"])),
        str(value["selected_model"]),
        Decimal(str(value["selected_penalty"])),
    )


def _reference_payload(
    value: ValidationArtifactReference | None,
) -> dict[str, Any] | None:
    return None if value is None else value.to_canonical_dict()


def _reference(value: object) -> ValidationArtifactReference:
    return ValidationArtifactReference.from_canonical_dict(_mapping(value))


def _optional_reference(value: object) -> ValidationArtifactReference | None:
    return None if value is None else _reference(value)


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("Conditional Forecast payload must be an object")
    return value


def _sequence(value: object) -> tuple[Any, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError("Conditional Forecast payload must be an array")
    return tuple(value)


def _bindings(value: object) -> tuple[tuple[str, str], ...]:
    return tuple((str(item[0]), str(item[1])) for item in _sequence(value))


def _optional_decimal(value: object) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _mean(values: tuple[Decimal, ...]) -> Decimal:
    if not values:
        raise ValueError("Conditional Forecast comparison population is empty")
    return sum(values, Decimal("0")) / Decimal(len(values))


def _median(values: tuple[Decimal, ...]) -> Decimal:
    if not values:
        raise ValueError("Conditional Forecast baseline population is empty")
    ordered = tuple(sorted(values))
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / Decimal("2")


__all__ = [
    "ConditionalForecastConfig",
    "ConditionalForecastResult",
    "ConditionalModelComparison",
    "fit_conditional_forecast",
]
