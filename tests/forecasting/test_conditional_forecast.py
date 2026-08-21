from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest

from market_regime_alpha.application.research_validation.research_model import (
    RegularizedLinearForecastExecutor,
    ResearchInferenceRequest,
    ResearchModelInferenceReceipt,
    ResearchModelTrainingRequest,
    ResearchTrainingSample,
    TimedResearchFeature,
    TimedResearchTarget,
    WalkForwardFold,
    train_research_model,
)
from market_regime_alpha.forecasting.conditional import (
    ConditionalForecastConfig,
    ConditionalForecastResult,
    fit_conditional_forecast,
)
from tests.application.research_validation.test_research_model import (
    NOW,
    _request as _base_request,
)
from tests.forecasting.test_path_forecast import _build as _build_path_baseline
from tests.forecasting.test_path_forecast import _sample as _path_sample


def _baseline():
    return _build_path_baseline((_path_sample(1), _path_sample(2)))


def _request() -> ResearchModelTrainingRequest:
    base = _base_request()
    samples = tuple(
        ResearchTrainingSample.create(
            symbol=sample.symbol,
            trading_date=sample.trading_date,
            decision_time=sample.decision_time,
            features=sample.features,
            targets=(
                TimedResearchTarget(
                    "lower_barrier",
                    sample.trading_date.day % 2 == 0,
                    sample.decision_time + timedelta(days=1),
                    sample.targets[0].source_reference,
                    "labels.lower_barrier",
                ),
                TimedResearchTarget(
                    "mae",
                    -Decimal(sample.trading_date.day) / Decimal("100"),
                    sample.decision_time + timedelta(days=1),
                    sample.targets[0].source_reference,
                    "labels.mae",
                ),
                TimedResearchTarget(
                    "mfe",
                    Decimal(sample.trading_date.day) / Decimal("100"),
                    sample.decision_time + timedelta(days=1),
                    sample.targets[0].source_reference,
                    "labels.mfe",
                ),
                TimedResearchTarget(
                    "t_plus_1_return",
                    Decimal(sample.trading_date.day - 3) / Decimal("100"),
                    sample.decision_time + timedelta(days=1),
                    sample.targets[0].source_reference,
                    "labels.t_plus_1_return",
                ),
                TimedResearchTarget(
                    "upper_barrier",
                    sample.trading_date.day % 2 == 1,
                    sample.decision_time + timedelta(days=1),
                    sample.targets[0].source_reference,
                    "labels.upper_barrier",
                ),
            ),
        )
        for sample in base.samples
    )
    by_day = {item.trading_date.day: item.sample_id for item in samples}
    folds = (
        WalkForwardFold(
            "fold-01",
            tuple(sorted((by_day[1], by_day[2]), key=str)),
            tuple(sorted((by_day[4], by_day[5]), key=str)),
            1,
            2,
        ),
        WalkForwardFold(
            "fold-02",
            tuple(sorted((by_day[1], by_day[2], by_day[4], by_day[5]), key=str)),
            (by_day[7],),
            1,
            2,
        ),
    )
    return ResearchModelTrainingRequest.create(
        model_definition_reference=base.model_definition_reference,
        configuration_reference=base.configuration_reference,
        feature_catalog_reference=base.feature_catalog_reference,
        target_protocol_reference=base.target_protocol_reference,
        dataset_references=base.dataset_references,
        locked_oos_reference=base.locked_oos_reference,
        locked_oos_sample_ids=base.locked_oos_sample_ids,
        oos_start_date=base.oos_start_date,
        session_sequence=base.session_sequence,
        samples=samples,
        folds=folds,
        feature_names=base.feature_names,
        continuous_target_names=("mae", "mfe", "t_plus_1_return"),
        barrier_target_names=("lower_barrier", "upper_barrier"),
        penalty_candidates=base.penalty_candidates,
        fold_seed=base.fold_seed,
        code_revision=base.code_revision,
        code_hash=base.code_hash,
        requested_at=base.requested_at,
    )


def _config(minimum: int = 2) -> ConditionalForecastConfig:
    request = _request()
    baseline = _baseline()
    return ConditionalForecastConfig.create(
        feature_names=request.feature_names,
        continuous_targets=request.continuous_target_names,
        barrier_targets=request.barrier_target_names,
        train_validation_policy="OWNER_WALK_FORWARD_PURGED",
        penalties=request.penalty_candidates,
        hyperparameter_search_budget=len(request.penalty_candidates),
        random_seed=request.fold_seed,
        minimum_training_samples=minimum,
        cost_assumption=Decimal("0.001"),
        baseline_target_id=str(baseline.forecast.target_id),
        baseline_horizon=baseline.forecast.forecast_horizon,
    )


def _owners(request: ResearchModelTrainingRequest | None = None):
    request = _request() if request is None else request
    trained_at = max(
        NOW,
        request.requested_at,
        *(target.available_at for sample in request.samples for target in sample.targets),
    )
    artifact = train_research_model(request, trained_at=trained_at)
    baseline = _baseline()
    decision_time = baseline.forecast.envelope.decision_time.value
    source = request.samples[0].features[0].source_reference
    features = tuple(
        TimedResearchFeature(
            name,
            Decimal("1"),
            decision_time - timedelta(minutes=5),
            decision_time - timedelta(minutes=1),
            source,
            f"inference.{name}",
        )
        for name in request.feature_names
    )
    inference = ResearchInferenceRequest(
        symbol=baseline.forecast.symbol,
        decision_time=decision_time,
        features=features,
        model_definition_hash=request.model_definition_reference.content_hash,
        configuration_hash=request.configuration_reference.content_hash,
        code_revision=request.code_revision,
        code_hash=request.code_hash,
    )
    result = RegularizedLinearForecastExecutor(
        artifact=artifact,
        request=request,
    ).execute(inference)
    receipt = ResearchModelInferenceReceipt.create(
        model_reference=artifact_reference(artifact),
        request=inference,
        result=result,
        executed_at=max(trained_at, decision_time),
    )
    return request, artifact, receipt, baseline


def _request_with_fold_target_leakage() -> ResearchModelTrainingRequest:
    base = _request()
    original = base.samples[0]
    leaked = ResearchTrainingSample.create(
        symbol=original.symbol,
        trading_date=original.trading_date,
        decision_time=original.decision_time,
        features=original.features,
        targets=tuple(
            replace(target, available_at=original.decision_time + timedelta(days=30))
            for target in original.targets
        ),
    )
    remapped = {original.sample_id: leaked.sample_id}
    samples = (leaked, *base.samples[1:])
    folds = tuple(
        WalkForwardFold(
            fold.fold_name,
            tuple(
                sorted(
                    (remapped.get(item, item) for item in fold.train_sample_ids),
                    key=str,
                )
            ),
            tuple(
                sorted(
                    (remapped.get(item, item) for item in fold.validation_sample_ids),
                    key=str,
                )
            ),
            fold.purge_sessions,
            fold.embargo_sessions,
        )
        for fold in base.folds
    )
    return ResearchModelTrainingRequest.create(
        model_definition_reference=base.model_definition_reference,
        configuration_reference=base.configuration_reference,
        feature_catalog_reference=base.feature_catalog_reference,
        target_protocol_reference=base.target_protocol_reference,
        dataset_references=base.dataset_references,
        locked_oos_reference=base.locked_oos_reference,
        locked_oos_sample_ids=base.locked_oos_sample_ids,
        oos_start_date=base.oos_start_date,
        session_sequence=base.session_sequence,
        samples=samples,
        folds=folds,
        feature_names=base.feature_names,
        continuous_target_names=base.continuous_target_names,
        barrier_target_names=base.barrier_target_names,
        penalty_candidates=base.penalty_candidates,
        fold_seed=base.fold_seed,
        code_revision=base.code_revision,
        code_hash=base.code_hash,
        requested_at=base.requested_at + timedelta(days=31),
    )


def artifact_reference(artifact):
    from market_regime_alpha.application.research_validation.common import (
        ValidationArtifactReference,
    )

    return ValidationArtifactReference(
        "RESEARCH_MODEL_ARTIFACT", artifact.artifact_id, artifact.artifact_hash
    )


def test_minimum_sample_behavior_is_fail_closed() -> None:
    request, artifact, receipt, baseline = _owners()
    result = fit_conditional_forecast(
        _config(minimum=3),
        training_request=request,
        research_model=artifact,
        inference_receipt=receipt,
        baseline_forecast=baseline,
    )

    assert result.status == "DATA_INSUFFICIENT"
    assert result.model_reference is None
    assert result.training_sample_bindings
    assert result.validation_sample_bindings
    assert result.training_sample_count == len(result.training_sample_bindings)
    assert result.validation_sample_count == len(result.validation_sample_bindings)
    assert result.calibration_status == "NOT_CALIBRATED"


def test_owner_model_and_as_of_baseline_are_compared_without_probability_claim() -> None:
    request, artifact, receipt, baseline = _owners()
    configuration = _config()
    result = fit_conditional_forecast(
        configuration,
        training_request=request,
        research_model=artifact,
        inference_receipt=receipt,
        baseline_forecast=baseline,
    )

    assert result.status == "AVAILABLE_FOR_RESEARCH"
    assert result.model_comparison is not None
    assert result.model_reference is not None
    assert result.inference_reference is not None
    assert result.selected_expected_return is not None
    assert result.prediction_uncertainty is not None
    assert result.calibration_status == "NOT_CALIBRATED"
    if result.model_comparison.selected_model == "REGULARIZED_RESEARCH_MODEL":
        assert result.raw_barrier_scores
        assert "RAW_BARRIER_SCORES_NOT_PROBABILITIES" in result.limitations
    else:
        assert result.raw_barrier_scores == ()
        assert "EMPIRICAL_BASELINE_HAS_NO_BARRIER_PROBABILITY" in result.limitations
    assert ConditionalForecastResult.from_canonical_dict(
        result.to_canonical_dict()
    ) == result
    assert ConditionalForecastConfig.from_canonical_dict(
        configuration.to_canonical_dict()
    ) == configuration


def test_fold_target_must_be_available_before_validation_decision() -> None:
    request = _request_with_fold_target_leakage()
    request, artifact, receipt, baseline = _owners(request)

    with pytest.raises(ValueError, match="unavailable at validation DecisionTime"):
        fit_conditional_forecast(
            _config(),
            training_request=request,
            research_model=artifact,
            inference_receipt=receipt,
            baseline_forecast=baseline,
        )
