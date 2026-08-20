from __future__ import annotations

from dataclasses import fields
from datetime import UTC, datetime, time

import pytest

from market_regime_alpha.application.historical_corpus.frozen_experiment import (
    create_golden_loop_v2_historical_experiment,
    create_phase_e3_feature_configuration,
    create_phase_e3_historical_experiment,
    create_phase_e3_strategy_economics_policy_set,
    verify_golden_loop_v2_historical_experiment,
    verify_phase_e3_historical_experiment,
)
from market_regime_alpha.application.historical_corpus.golden_loop import (
    GoldenLoopScoringContract,
)
from market_regime_alpha.application.research_evaluation.targets import (
    exploratory_five_minute_multi_horizon_protocol,
)
from market_regime_alpha.application.research_validation.formal_protocol import (
    ResearchExperimentDefinition,
)
from market_regime_alpha.application.research_validation.historical_economics import (
    HistoricalStrategyEconomicsPolicySet,
)


LOCKED_AT = datetime(2026, 8, 13, 8, 0, tzinfo=UTC)


def test_phase_e3_experiment_accepts_only_exact_frozen_methodology() -> None:
    target = exploratory_five_minute_multi_horizon_protocol()
    experiment = create_phase_e3_historical_experiment(target, locked_at=LOCKED_AT)
    feature = create_phase_e3_feature_configuration()
    economics = create_phase_e3_strategy_economics_policy_set(
        target_protocol=target,
        created_at=LOCKED_AT,
    )
    configuration = (
        experiment.feature_reference,
        experiment.cost_policy_reference,
    )

    assert HistoricalStrategyEconomicsPolicySet.from_canonical_dict(
        economics.to_canonical_dict()
    ) == economics

    verify_phase_e3_historical_experiment(
        experiment,
        target_protocol=target,
        feature_owner=feature,
        economics_owner=economics,
        decision_local_time=time(14, 55),
        timezone_name="Asia/Shanghai",
        configuration_references=configuration,
    )

    values = {
        item.name: getattr(experiment, item.name)
        for item in fields(experiment)
        if item.name not in {"definition_id", "definition_hash"}
    }
    values["feature_version"] = "after-the-fact-tuning"
    changed = ResearchExperimentDefinition.create(**values)
    with pytest.raises(ValueError, match="frozen Phase E3 methodology"):
        verify_phase_e3_historical_experiment(
            changed,
            target_protocol=target,
            feature_owner=feature,
            economics_owner=economics,
            decision_local_time=time(14, 55),
            timezone_name="Asia/Shanghai",
            configuration_references=(
                changed.feature_reference,
                changed.cost_policy_reference,
            ),
        )


def test_phase_e3_experiment_requires_command_level_feature_and_cost_bindings() -> None:
    target = exploratory_five_minute_multi_horizon_protocol()
    experiment = create_phase_e3_historical_experiment(target, locked_at=LOCKED_AT)

    with pytest.raises(ValueError, match="omits frozen feature or cost"):
        verify_phase_e3_historical_experiment(
            experiment,
            target_protocol=target,
            feature_owner=create_phase_e3_feature_configuration(),
            economics_owner=create_phase_e3_strategy_economics_policy_set(
                target_protocol=target,
                created_at=LOCKED_AT,
            ),
            decision_local_time=time(14, 55),
            timezone_name="Asia/Shanghai",
            configuration_references=(experiment.feature_reference,),
        )


def test_golden_loop_v2_changes_only_research_correctness_identity() -> None:
    target = exploratory_five_minute_multi_horizon_protocol()
    v1 = create_phase_e3_historical_experiment(target, locked_at=LOCKED_AT)
    v2 = create_golden_loop_v2_historical_experiment(target, locked_at=LOCKED_AT)

    assert v2.definition_hash != v1.definition_hash
    assert v2.target_references == v1.target_references
    assert v2.feature_reference == v1.feature_reference
    assert v2.feature_version == v1.feature_version
    assert v2.cost_policy_reference == v1.cost_policy_reference
    assert v2.decision_time_policy == v1.decision_time_policy
    assert v2.allowed_model_families == v1.allowed_model_families
    assert v2.search_budget == v1.search_budget
    assert v2.train_validation_policy == v1.train_validation_policy
    assert v2.purge_embargo_policy == v1.purge_embargo_policy
    assert v2.oos_unlock_policy == v1.oos_unlock_policy
    assert v2.random_seeds == v1.random_seeds
    assert GoldenLoopScoringContract.create_v2().contract_hash in {
        value
        for domain in v2.hyperparameter_space
        if domain.parameter_name == "scoring_contract_hash"
        for value in domain.allowed_values
    }

    verify_golden_loop_v2_historical_experiment(
        v2,
        target_protocol=target,
        feature_owner=create_phase_e3_feature_configuration(),
        economics_owner=create_phase_e3_strategy_economics_policy_set(
            target_protocol=target,
            created_at=LOCKED_AT,
        ),
        decision_local_time=time(14, 55),
        timezone_name="Asia/Shanghai",
        configuration_references=(
            v2.feature_reference,
            v2.cost_policy_reference,
        ),
    )
