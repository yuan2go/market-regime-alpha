from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from market_regime_alpha.application.research_evaluation.targets import (
    OutcomeCheckpoint,
    OutcomeTargetProtocol,
    engineering_multi_horizon_protocol,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.application.research_validation.formal_evaluation import (
    EvaluationPartition,
    EvaluationWindow,
    FormalEvaluationProtocol,
    MultipleTestingErrorRate,
    MultipleTestingMethod,
    benchmark_evaluation_hypotheses,
)
from market_regime_alpha.application.research_validation.formal_protocol import (
    FormalResearchProtocol,
    HyperparameterDomain,
    OutcomeTargetForecastStatus,
    ResearchExperimentDefinition,
    SearchBudget,
    build_outcome_target_bound_forecast,
    not_estimable_target_forecast,
)
from market_regime_alpha.core.identity import ArtifactId, DatasetId
from market_regime_alpha.data.trading_calendar import (
    TradingSession,
    build_trading_calendar_artifact,
)
from market_regime_alpha.evidence.canonical import canonical_hash


NOW = datetime(2026, 8, 11, 8, tzinfo=UTC)


def _reference(kind: str, name: str) -> ValidationArtifactReference:
    return ValidationArtifactReference(
        kind,
        ArtifactId(name),
        canonical_hash({"kind": kind, "name": name}),
    )


def _calendar():
    sessions = tuple(
        TradingSession(
            trade_date=date(2026, 1, day),
            session_close=datetime(2026, 1, day, 7, tzinfo=UTC),
        )
        for day in range(5, 31)
    )
    return build_trading_calendar_artifact(
        source_dataset_id=DatasetId("calendar-source"),
        market="XSHG-XSHE",
        calendar_version="frozen-c0-v1",
        timezone_name="Asia/Shanghai",
        sessions=sessions,
    )


def _evaluation(targets: OutcomeTargetProtocol) -> FormalEvaluationProtocol:
    return FormalEvaluationProtocol.create(
        protocol_version="formal-c0-v1",
        target_protocol=targets,
        windows=(
            EvaluationWindow("train", EvaluationPartition.TRAIN, date(2026, 1, 5), date(2026, 1, 12), 1),
            EvaluationWindow("validation", EvaluationPartition.VALIDATION, date(2026, 1, 13), date(2026, 1, 20), 1),
            EvaluationWindow("locked-oos", EvaluationPartition.LOCKED_OOS, date(2026, 1, 21), date(2026, 1, 30), 1),
        ),
        bootstrap_iterations=100,
        bootstrap_block_sessions=2,
        confidence_level=Decimal("0.95"),
        multiple_testing_method=MultipleTestingMethod.BENJAMINI_HOCHBERG,
        multiple_testing_error_rate=MultipleTestingErrorRate.FDR,
        hypothesis_specs=benchmark_evaluation_hypotheses(),
        hypothesis_family_id="C0-FROZEN-FAMILY-V1",
        top_k=5,
        locked_at=NOW,
    )


def _formal_protocol(*, cost_name: str = "cost-v1") -> FormalResearchProtocol:
    targets = engineering_multi_horizon_protocol()
    evaluation = _evaluation(targets)
    feature = _reference("FEATURE_DEFINITION_SET", "features-v1")
    cost = _reference("SHADOW_PORTFOLIO_POLICY", cost_name)
    experiment = ResearchExperimentDefinition.create(
        research_question="Do frozen price/volume features add T+1 ranking information?",
        hypothesis="The primary RankIC and spread effects exceed their frozen nulls.",
        decision_time_policy="FROZEN_DECISION_TIME",
        target_references=tuple(
            ValidationArtifactReference("OUTCOME_TARGET", item.target_id, item.target_hash)
            for item in targets.targets
        ),
        feature_reference=feature,
        feature_version="price-volume-baseline-v1",
        allowed_model_families=("REGULARIZED_LINEAR",),
        hyperparameter_space=(
            HyperparameterDomain("l2_penalty", ("0", "0.1", "1")),
        ),
        search_budget=SearchBudget(max_model_fits=3, max_wall_clock_seconds=300),
        primary_hypothesis_ids=("BASELINE:RANK_IC:V1", "BASELINE:SPREAD:V1"),
        secondary_hypothesis_ids=("BASELINE:IC:V1",),
        multiple_testing_family_id=evaluation.hypothesis_family_id,
        stopping_rule="EXHAUST_FROZEN_SEARCH_BUDGET",
        train_validation_policy="PURGED_WALK_FORWARD_NO_LOCKED_OOS",
        purge_embargo_policy="EVALUATION_PROTOCOL_DERIVED",
        oos_unlock_policy="ONE_TIME_AFTER_MODEL_SELECTION_FREEZE",
        randomness_algorithm="SHA256_DERIVED_PCG64",
        random_seeds=(20260812,),
        cost_policy_reference=cost,
    )
    return FormalResearchProtocol.create(
        protocol_version="phase-c0-v1",
        target_protocol=targets,
        trading_calendar=_calendar(),
        evaluation_protocol=evaluation,
        experiment_definition=experiment,
        universe_reference=_reference("UNIVERSE", "universe-v1"),
        dataset_reference=_reference("MARKET_DATA_DATASET", "dataset-v1"),
        historical_sample_dataset_reference=_reference(
            "HISTORICAL_SAMPLE_DATASET", "sample-dataset-v1"
        ),
        feature_reference=feature,
        factor_reference=_reference("FACTOR_CATALOG", "factors-v1"),
        model_reference=_reference("MODEL_VERSION_LINEAGE", "model-v1"),
        threshold_policy_reference=_reference("THRESHOLD_POLICY", "threshold-v1"),
        formal_oos_qualification_policy_reference=_reference(
            "FORMAL_OOS_QUALIFICATION_POLICY", "formal-oos-v1"
        ),
        cost_policy_reference=cost,
        calibration_policy_reference=_reference("CALIBRATION_POLICY", "calibration-v1"),
        strategy_policy_reference=_reference("STRATEGY_SHADOW_POLICY", "strategy-v1"),
        entry_holding_exit_qualification_policy_reference=_reference(
            "ENTRY_HOLDING_EXIT_QUALIFICATION_POLICY", "entry-exit-v1"
        ),
        locked_at=NOW,
    )


def test_formal_protocol_freezes_every_result_affecting_component() -> None:
    protocol = _formal_protocol()
    changed_cost = _formal_protocol(cost_name="cost-v2")

    assert protocol.protocol_hash != changed_cost.protocol_hash
    assert protocol.trading_calendar_reference.content_hash == _calendar().content_hash
    assert protocol.frozen_trading_dates[0] == date(2026, 1, 5)
    assert protocol.frozen_trading_dates[-1] == date(2026, 1, 30)
    assert len(protocol.target_references) == len(engineering_multi_horizon_protocol().targets)
    assert protocol.locked_oos_reuse_policy == "NEVER_REUSE_FOR_SELECTION_OR_TUNING"
    assert protocol.experiment_definition is not None
    assert str(protocol.experiment_definition.definition_id).startswith(
        "research-experiment-definition:"
    )
    assert protocol.experiment_definition.search_budget.max_model_fits == 3
    assert FormalResearchProtocol.from_canonical_dict(
        protocol.to_canonical_dict()
    ) == protocol


def test_experiment_definition_rejects_after_the_fact_mutation() -> None:
    definition = _formal_protocol().experiment_definition
    assert definition is not None

    with pytest.raises(ValueError, match="hash"):
        replace(definition, stopping_rule="STOP_AFTER_FAVOURABLE_OOS")


def test_formal_protocol_rejects_calendar_or_target_lineage_mismatch() -> None:
    targets = engineering_multi_horizon_protocol()
    evaluation = _evaluation(targets)
    wrong_targets = OutcomeTargetProtocol.create(
        protocol_version="different-targets",
        timezone_name=targets.timezone_name,
        session_offset=targets.session_offset,
        targets=targets.targets,
        limitations=targets.limitations,
    )
    values = dict(
        protocol_version="phase-c0-v1",
        experiment_definition=_formal_protocol().experiment_definition,
        trading_calendar=_calendar(),
        evaluation_protocol=evaluation,
        universe_reference=_reference("UNIVERSE", "universe-v1"),
        dataset_reference=_reference("DATASET", "dataset-v1"),
        historical_sample_dataset_reference=_reference(
            "HISTORICAL_SAMPLE_DATASET", "sample-dataset-v1"
        ),
        feature_reference=_reference("FEATURE_DEFINITION_SET", "features-v1"),
        factor_reference=_reference("FACTOR_CATALOG", "factors-v1"),
        model_reference=_reference("MODEL_VERSION_LINEAGE", "model-v1"),
        threshold_policy_reference=_reference("THRESHOLD_POLICY", "threshold-v1"),
        formal_oos_qualification_policy_reference=_reference(
            "FORMAL_OOS_QUALIFICATION_POLICY", "formal-oos-v1"
        ),
        cost_policy_reference=_reference("SHADOW_PORTFOLIO_POLICY", "cost-v1"),
        calibration_policy_reference=_reference("CALIBRATION_POLICY", "calibration-v1"),
        strategy_policy_reference=_reference("STRATEGY_SHADOW_POLICY", "strategy-v1"),
        entry_holding_exit_qualification_policy_reference=_reference(
            "ENTRY_HOLDING_EXIT_QUALIFICATION_POLICY", "entry-exit-v1"
        ),
        locked_at=NOW,
    )
    with pytest.raises(ValueError, match="Target Protocol"):
        FormalResearchProtocol.create(target_protocol=wrong_targets, **values)

    outside = FormalEvaluationProtocol.create(
        protocol_version="outside-calendar",
        target_protocol=targets,
        windows=(
            EvaluationWindow("train", EvaluationPartition.TRAIN, date(2025, 12, 1), date(2025, 12, 5), 1),
            EvaluationWindow("validation", EvaluationPartition.VALIDATION, date(2026, 1, 13), date(2026, 1, 20), 1),
            EvaluationWindow("locked-oos", EvaluationPartition.LOCKED_OOS, date(2026, 1, 21), date(2026, 1, 30), 1),
        ),
        bootstrap_iterations=100,
        confidence_level=Decimal("0.95"),
        multiple_testing_method=MultipleTestingMethod.BONFERRONI,
        multiple_testing_error_rate=MultipleTestingErrorRate.FWER,
        hypothesis_specs=benchmark_evaluation_hypotheses(),
        locked_at=NOW,
    )
    with pytest.raises(ValueError, match="Frozen Trading Calendar"):
        FormalResearchProtocol.create(
            target_protocol=targets,
            **{**values, "evaluation_protocol": outside},
        )

    late_evaluation = FormalEvaluationProtocol.create(
        protocol_version="late-evaluation-lock",
        target_protocol=targets,
        windows=evaluation.windows,
        bootstrap_iterations=100,
        confidence_level=Decimal("0.95"),
        multiple_testing_method=MultipleTestingMethod.BONFERRONI,
        multiple_testing_error_rate=MultipleTestingErrorRate.FWER,
        hypothesis_specs=benchmark_evaluation_hypotheses(),
        locked_at=NOW + timedelta(seconds=1),
    )
    with pytest.raises(ValueError, match="locked before"):
        FormalResearchProtocol.create(
            target_protocol=targets,
            **{**values, "evaluation_protocol": late_evaluation},
        )


def test_multi_target_forecast_binds_every_outcome_target_exactly() -> None:
    protocol = engineering_multi_horizon_protocol()
    estimates = tuple(
        not_estimable_target_forecast(
            target_id=target.target_id,
            target_hash=target.target_hash,
            barrier_ids=tuple(item.barrier_id for item in target.barriers),
            reason_codes=("QUALIFIED_HISTORICAL_SAMPLE_MISSING",),
        )
        for target in protocol.targets
    )
    forecast = build_outcome_target_bound_forecast(
        target_protocol=protocol,
        symbol="000001.SZ",
        decision_time=NOW,
        estimates=estimates,
        source_references=(_reference("FROZEN_DECISION", "decision-v1"),),
        model_reference=_reference("MODEL_VERSION_LINEAGE", "model-v1"),
        created_at=NOW,
    )

    assert len(forecast.estimates) == len(OutcomeCheckpoint)
    assert all(item.status is OutcomeTargetForecastStatus.NOT_ESTIMABLE for item in forecast.estimates)
    assert forecast.calibrated is False
    assert forecast.production_authorized is False

    with pytest.raises(ValueError, match="exactly every Outcome Target"):
        build_outcome_target_bound_forecast(
            target_protocol=protocol,
            symbol="000001.SZ",
            decision_time=NOW,
            estimates=estimates[:-1],
            source_references=(_reference("FROZEN_DECISION", "decision-v1"),),
            model_reference=_reference("MODEL_VERSION_LINEAGE", "model-v1"),
            created_at=NOW,
        )

    forged = (
        not_estimable_target_forecast(
            target_id=estimates[0].target_id,
            target_hash=canonical_hash({"forged": True}),
            barrier_ids=tuple(item.barrier_id for item in protocol.targets[0].barriers),
            reason_codes=("QUALIFIED_HISTORICAL_SAMPLE_MISSING",),
        ),
        *estimates[1:],
    )
    with pytest.raises(ValueError, match="identity"):
        build_outcome_target_bound_forecast(
            target_protocol=protocol,
            symbol="000001.SZ",
            decision_time=NOW,
            estimates=forged,
            source_references=(_reference("FROZEN_DECISION", "decision-v1"),),
            model_reference=_reference("MODEL_VERSION_LINEAGE", "model-v1"),
            created_at=NOW,
        )
