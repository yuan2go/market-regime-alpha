from __future__ import annotations

from datetime import UTC, datetime
import json
from types import SimpleNamespace

from market_regime_alpha.application.research_evaluation.targets import (
    engineering_multi_horizon_protocol,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.application.research_validation.formal_forecast_computation import (
    RegularizedFormalForecastExecutor,
)
from market_regime_alpha.application.research_validation.formal_protocol import (
    ForecastMeasureKind,
    ForecastMeasureStatus,
    HyperparameterDomain,
    ResearchExperimentDefinition,
    SearchBudget,
)
from market_regime_alpha.application.research_validation.research_model import (
    ResearchMeasureBinding,
    ResearchModelHeadKind,
    train_research_model,
)
from market_regime_alpha.data.pit_authority import PITFactKind
from tests.application.research_validation.test_research_model import (
    NOW,
    _reference,
    _request,
)
from tests.persistence.postgres.pit_fixture import pit_fact, required_facts


def test_owner_resolved_executor_uses_same_pure_kernel_and_never_invents_probability() -> None:
    targets = engineering_multi_horizon_protocol()
    target = targets.targets[0]
    target_reference = ValidationArtifactReference(
        "OUTCOME_TARGET", target.target_id, target.target_hash
    )
    feature_reference = _reference("FEATURE_DEFINITION_SET", "8")
    experiment = ResearchExperimentDefinition.create(
        research_question="Does the benchmark predict one frozen T+1 target?",
        hypothesis="Expected return and raw direction logit add information.",
        decision_time_policy="T_CLOSE_AVAILABLE",
        target_references=(target_reference,),
        feature_reference=feature_reference,
        feature_version="feature-set/v1",
        allowed_model_families=("deterministic-regularized-linear/v1",),
        hyperparameter_space=(HyperparameterDomain("ridge_penalty", ("0.1", "1")),),
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
    bindings = tuple(
        sorted(
            (
                ResearchMeasureBinding(
                    "expected_return",
                    target_reference,
                    ForecastMeasureKind.EXPECTED_RETURN,
                    ResearchModelHeadKind.CONTINUOUS_EXPECTATION,
                ),
                ResearchMeasureBinding(
                    "up_barrier",
                    target_reference,
                    ForecastMeasureKind.UPPER_BEFORE_LOWER_RAW_LOGIT,
                    ResearchModelHeadKind.LOGISTIC_RAW_LOGIT,
                ),
            ),
            key=lambda item: item.key,
        )
    )
    training = _request(
        experiment_definition=experiment,
        measure_bindings=bindings,
        feature_catalog_reference=feature_reference,
        target_protocol_reference=ValidationArtifactReference(
            "OUTCOME_TARGET_PROTOCOL", targets.protocol_id, targets.protocol_hash
        ),
    )
    artifact = train_research_model(training, trained_at=NOW)
    assert artifact.model_parameter_hash is not None
    decision_time = datetime(2026, 8, 8, 6, 45, tzinfo=UTC)
    required = next(
        item
        for item in required_facts()
        if item.fact_kind is PITFactKind.FEATURE_MATERIALIZATION
    )
    fact = pit_fact(
        required,
        value_json=json.dumps(
            {
                "schema_version": "forecast-feature-vector/v1",
                "symbol": "600000.SH",
                "decision_time": decision_time.isoformat(),
                "features": {"momentum": "1", "value": "7"},
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
    )
    context = SimpleNamespace(
        research_model_artifact=artifact,
        research_model_training_request=training,
        protocol=SimpleNamespace(
            experiment_definition=experiment,
            feature_reference=feature_reference,
        ),
        target_protocol=targets,
        model_lineage=SimpleNamespace(
            model_parameter_hash=artifact.model_parameter_hash,
            definition_hash=training.model_definition_reference.content_hash,
            code_revision=training.code_revision,
            code_hash=training.code_hash,
        ),
        configuration_reference=training.configuration_reference,
        selected_fact_payloads=(fact.to_canonical_dict(),),
        symbol="600000.SH",
        decision_time=decision_time,
    )
    executor = RegularizedFormalForecastExecutor()

    assert executor.supports(context)
    estimates = executor.compute(context)
    predicted = estimates[0]
    assert predicted.measure(ForecastMeasureKind.EXPECTED_RETURN).status is ForecastMeasureStatus.AVAILABLE
    assert predicted.measure(ForecastMeasureKind.UPPER_BEFORE_LOWER_RAW_LOGIT).status is ForecastMeasureStatus.AVAILABLE
    assert predicted.measure(ForecastMeasureKind.UPPER_BEFORE_LOWER_PROBABILITY).status is ForecastMeasureStatus.NOT_ESTIMABLE
