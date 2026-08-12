from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.application.research_validation.formal_protocol import (
    ForecastMeasureKind,
    HyperparameterDomain,
    ResearchExperimentDefinition,
    SearchBudget,
)
from market_regime_alpha.application.research_validation.research_model import (
    RegularizedLinearForecastExecutor,
    ResearchForecastStatus,
    ResearchInferenceRequest,
    ResearchMeasureBinding,
    ResearchModelHeadKind,
    ResearchModelStatus,
    ResearchModelTrainingRequest,
    ResearchTrainingSample,
    TimedResearchFeature,
    TimedResearchTarget,
    WalkForwardFold,
    train_research_model,
)
from market_regime_alpha.core.identity import ArtifactId


NOW = datetime(2026, 8, 11, 12, tzinfo=UTC)
SESSIONS = tuple(date(2026, 7, day) for day in range(1, 11))
SAMPLE_DAYS = (1, 2, 4, 5, 7)


def _reference(kind: str, suffix: str) -> ValidationArtifactReference:
    return ValidationArtifactReference(
        kind,
        ArtifactId(f"{kind.lower()}:{suffix}"),
        "sha256:" + suffix[0] * 64,
    )


def _sample(day: int) -> ResearchTrainingSample:
    decision = datetime(2026, 7, day, 6, 55, tzinfo=UTC)
    x = Decimal(day)
    source = _reference("PANEL_ENRICHMENT", format(day, "x"))
    outcome = _reference("TARGETED_OUTCOME", format(day + 8, "x"))
    return ResearchTrainingSample.create(
        symbol=f"00000{day}.SZ",
        trading_date=date(2026, 7, day),
        decision_time=decision,
        features=(
            TimedResearchFeature(
                "momentum",
                None if day == 4 else x - Decimal("3"),
                decision - timedelta(minutes=5),
                decision - timedelta(minutes=1),
                source,
                "exposures.momentum",
            ),
            TimedResearchFeature(
                "value",
                x,
                decision - timedelta(days=1),
                decision - timedelta(minutes=2),
                source,
                "exposures.value",
            ),
        ),
        targets=(
            TimedResearchTarget(
                "expected_return",
                x / Decimal("100"),
                decision + timedelta(days=1),
                outcome,
                "labels.return",
            ),
            TimedResearchTarget(
                "up_barrier",
                day % 2 == 0,
                decision + timedelta(days=1),
                outcome,
                "labels.up_barrier",
            ),
        ),
    )


def _request(**overrides) -> ResearchModelTrainingRequest:
    samples = tuple(_sample(day) for day in SAMPLE_DAYS)
    by_day = {item.trading_date.day: item.sample_id for item in samples}
    values = {
        "model_definition_reference": _reference("MODEL_DEFINITION", "a"),
        "configuration_reference": _reference("MODEL_CONFIGURATION", "b"),
        "feature_catalog_reference": _reference("FACTOR_RESEARCH_CATALOG", "c"),
        "target_protocol_reference": _reference("OUTCOME_TARGET_PROTOCOL", "d"),
        "dataset_references": (_reference("HISTORICAL_SAMPLE_DATASET", "e"),),
        "locked_oos_reference": _reference("LOCKED_OOS_PARTITION", "f"),
        "locked_oos_sample_ids": (ArtifactId("locked-oos:1"),),
        "oos_start_date": SESSIONS[-1],
        "session_sequence": SESSIONS,
        "samples": samples,
        "folds": (
            WalkForwardFold(
                "fold-01",
                tuple(sorted((by_day[1], by_day[2]), key=str)),
                tuple(sorted((by_day[4], by_day[5]), key=str)),
                purge_sessions=1,
                embargo_sessions=2,
            ),
            WalkForwardFold(
                "fold-02",
                tuple(sorted((by_day[1], by_day[2], by_day[4], by_day[5]), key=str)),
                (by_day[7],),
                purge_sessions=1,
                embargo_sessions=2,
            ),
        ),
        "feature_names": ("momentum", "value"),
        "continuous_target_names": ("expected_return",),
        "barrier_target_names": ("up_barrier",),
        "penalty_candidates": (Decimal("0.1"), Decimal("1")),
        "fold_seed": 17,
        "code_revision": "phase-d-test",
        "code_hash": "sha256:" + "9" * 64,
        "requested_at": NOW,
    }
    values.update(overrides)
    return ResearchModelTrainingRequest.create(**values)


def test_walk_forward_training_is_deterministic_replayable_and_exploratory() -> None:
    request = _request()

    first = train_research_model(request, trained_at=NOW)
    second = train_research_model(request, trained_at=NOW)

    assert first == second
    assert first.status is ResearchModelStatus.AVAILABLE
    assert first.research_model_available is True
    assert first.formal_model_qualified is False
    assert first.formal_oos is False
    assert first.calibrated is False
    assert first.model is not None
    assert first == first.from_canonical_dict(first.to_canonical_dict())
    assert request == request.from_canonical_dict(request.to_canonical_dict())


def test_partition_isolation_rejects_future_features_oos_overlap_and_bad_purge() -> None:
    request = _request()
    first = request.samples[0]
    future_feature = replace(
        first.features[0], available_at=first.decision_time + timedelta(seconds=1)
    )
    future_sample = ResearchTrainingSample.create(
        symbol=first.symbol,
        trading_date=first.trading_date,
        decision_time=first.decision_time,
        features=(future_feature, *first.features[1:]),
        targets=first.targets,
    )
    future_samples = (future_sample, *request.samples[1:])

    with pytest.raises(ValueError, match="Future feature rejected"):
        _request(samples=future_samples)
    with pytest.raises(ValueError, match="Locked OOS samples"):
        _request(locked_oos_sample_ids=(first.sample_id,))
    bad_fold = replace(request.folds[0], purge_sessions=2)
    with pytest.raises(ValueError, match="purge window"):
        _request(folds=(bad_fold, request.folds[1]))


def test_executor_requires_exact_lineage_and_emits_raw_logits_not_probabilities() -> None:
    request = _request()
    artifact = train_research_model(request, trained_at=NOW)
    executor = RegularizedLinearForecastExecutor(
        artifact=artifact,
        request=request,
    )
    sample = request.samples[-1]
    inference = ResearchInferenceRequest(
        symbol=sample.symbol,
        decision_time=sample.decision_time,
        features=sample.features,
        model_definition_hash=request.model_definition_reference.content_hash,
        configuration_hash=request.configuration_reference.content_hash,
        code_revision=request.code_revision,
        code_hash=request.code_hash,
    )

    available = executor.execute(inference)
    mismatched = executor.execute(
        replace(inference, configuration_hash="sha256:" + "0" * 64)
    )

    assert available.status is ResearchForecastStatus.AVAILABLE
    assert available.raw_barrier_logits
    assert available.barrier_scores_are_probabilities is False
    assert available.calibrated is False
    assert mismatched.status is ResearchForecastStatus.NOT_ESTIMABLE
    assert "MODEL_CONFIGURATION_HASH_MISMATCH" in mismatched.reason_codes


def test_injected_barrier_signal_is_discriminated_by_raw_logit() -> None:
    original = _request()
    samples = tuple(
        ResearchTrainingSample.create(
            symbol=sample.symbol,
            trading_date=sample.trading_date,
            decision_time=sample.decision_time,
            features=sample.features,
            targets=tuple(
                replace(
                    target,
                    value=(sample.trading_date.day >= 2),
                )
                if target.name == "up_barrier"
                else target
                for target in sample.targets
            ),
        )
        for sample in original.samples
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
            tuple(
                sorted(
                    (by_day[1], by_day[2], by_day[4], by_day[5]),
                    key=str,
                )
            ),
            (by_day[7],),
            1,
            2,
        ),
    )
    artifact = train_research_model(
        _request(samples=samples, folds=folds),
        trained_at=NOW,
    )

    assert artifact.model is not None
    lower = artifact.model.predict(
        {"momentum": Decimal("-2"), "value": Decimal("1")}
    ).raw_barrier_logits["up_barrier"]
    upper = artifact.model.predict(
        {"momentum": Decimal("4"), "value": Decimal("7")}
    ).raw_barrier_logits["up_barrier"]
    assert lower < Decimal("0") < upper
    assert upper > lower


def test_degenerate_targets_produce_a_preserved_terminal_negative_artifact() -> None:
    original = _request()
    samples = tuple(
        ResearchTrainingSample.create(
            symbol=sample.symbol,
            trading_date=sample.trading_date,
            decision_time=sample.decision_time,
            features=sample.features,
            targets=tuple(
                replace(
                    target,
                    value=(False if isinstance(target.value, bool) else Decimal("0")),
                )
                for target in sample.targets
            ),
        )
        for sample in original.samples
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
    request = _request(samples=samples, folds=folds)

    artifact = train_research_model(request, trained_at=NOW)

    assert artifact.status is ResearchModelStatus.NOT_ESTIMABLE
    assert artifact.research_model_available is False
    assert artifact.model is None
    assert artifact.reason_codes == ("NO_ESTIMABLE_HYPERPARAMETER_CANDIDATE",)
    assert all(
        item.status is ResearchModelStatus.NOT_ESTIMABLE
        for item in artifact.diagnostics
    )


def _v2_request(**overrides) -> ResearchModelTrainingRequest:
    target = _reference("OUTCOME_TARGET", "7")
    feature = _reference("FEATURE_DEFINITION_SET", "8")
    experiment = ResearchExperimentDefinition.create(
        research_question="Do price and volume features predict the frozen T+1 target?",
        hypothesis="The regularized benchmark has positive out-of-fold information.",
        decision_time_policy="T_CLOSE_AVAILABLE",
        target_references=(target,),
        feature_reference=feature,
        feature_version="feature-set/v1",
        allowed_model_families=("deterministic-regularized-linear/v1",),
        hyperparameter_space=(
            HyperparameterDomain("ridge_penalty", ("0.1", "1")),
        ),
        search_budget=SearchBudget(5, 60),
        primary_hypothesis_ids=("rank-ic",),
        secondary_hypothesis_ids=("spread",),
        multiple_testing_family_id="baseline-family/v1",
        stopping_rule="EXHAUST_FROZEN_GRID",
        train_validation_policy="EXPANDING_WALK_FORWARD",
        purge_embargo_policy="PURGE_1_EMBARGO_2",
        oos_unlock_policy="OWNER_CONTROLLED_SINGLE_CONSUMPTION",
        randomness_algorithm="NO_STOCHASTIC_OPTIMIZATION",
        random_seeds=(17,),
        cost_policy_reference=_reference("SHADOW_PORTFOLIO_POLICY", "9"),
    )
    bindings = (
        ResearchMeasureBinding(
            "expected_return",
            target,
            ForecastMeasureKind.EXPECTED_RETURN,
            ResearchModelHeadKind.CONTINUOUS_EXPECTATION,
        ),
        ResearchMeasureBinding(
            "up_barrier",
            target,
            ForecastMeasureKind.UPPER_BEFORE_LOWER_RAW_LOGIT,
            ResearchModelHeadKind.LOGISTIC_RAW_LOGIT,
        ),
    )

    return _request(
        experiment_definition=experiment,
        measure_bindings=bindings,
        feature_catalog_reference=feature,
        **overrides,
    )


def test_v2_training_request_binds_frozen_experiment_and_measure_semantics() -> None:
    request = _v2_request()

    assert request.schema_version == "research-model-training-request/v2"
    assert request == request.from_canonical_dict(request.to_canonical_dict())
    with pytest.raises(ValueError, match="hyperparameter space"):
        _v2_request(
            penalty_candidates=(Decimal("0.1"), Decimal("2")),
        )


def test_logistic_head_cannot_be_labeled_probability() -> None:
    with pytest.raises(ValueError, match="raw logit"):
        ResearchMeasureBinding(
            "direction",
            _reference("OUTCOME_TARGET", "7"),
            ForecastMeasureKind.RETURN_POSITIVE_PROBABILITY,
            ResearchModelHeadKind.LOGISTIC_RAW_LOGIT,
        )
