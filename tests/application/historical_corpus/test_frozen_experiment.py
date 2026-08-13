from __future__ import annotations

from dataclasses import fields
from datetime import time

import pytest

from market_regime_alpha.application.historical_corpus.frozen_experiment import (
    create_phase_e3_historical_experiment,
    verify_phase_e3_historical_experiment,
)
from market_regime_alpha.application.research_evaluation.targets import (
    exploratory_five_minute_multi_horizon_protocol,
)
from market_regime_alpha.application.research_validation.formal_protocol import (
    ResearchExperimentDefinition,
)


def test_phase_e3_experiment_accepts_only_exact_frozen_methodology() -> None:
    target = exploratory_five_minute_multi_horizon_protocol()
    experiment = create_phase_e3_historical_experiment(target)
    configuration = (
        experiment.feature_reference,
        experiment.cost_policy_reference,
    )

    verify_phase_e3_historical_experiment(
        experiment,
        target_protocol=target,
        decision_local_time=time(14, 55),
        timezone_name="Asia/Shanghai",
        configuration_references=configuration,
    )

    values = {
        item.name: getattr(experiment, item.name)
        for item in fields(experiment)
        if item.name not in {"definition_id", "definition_hash", "schema_version"}
    }
    values["feature_version"] = "after-the-fact-tuning"
    changed = ResearchExperimentDefinition.create(**values)
    with pytest.raises(ValueError, match="frozen Phase E3 methodology"):
        verify_phase_e3_historical_experiment(
            changed,
            target_protocol=target,
            decision_local_time=time(14, 55),
            timezone_name="Asia/Shanghai",
            configuration_references=(
                changed.feature_reference,
                changed.cost_policy_reference,
            ),
        )


def test_phase_e3_experiment_requires_command_level_feature_and_cost_bindings() -> None:
    target = exploratory_five_minute_multi_horizon_protocol()
    experiment = create_phase_e3_historical_experiment(target)

    with pytest.raises(ValueError, match="omits frozen feature or cost"):
        verify_phase_e3_historical_experiment(
            experiment,
            target_protocol=target,
            decision_local_time=time(14, 55),
            timezone_name="Asia/Shanghai",
            configuration_references=(experiment.feature_reference,),
        )
