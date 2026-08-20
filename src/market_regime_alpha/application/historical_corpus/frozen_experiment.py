"""Typed owners for the frozen Phase E3 longitudinal methodology.

Changing a feature, threshold, Target, cost, capacity, or evaluation choice
produces a different content-addressed owner and Experiment Definition.  The
module intentionally freezes only the currently consumed Historical policy;
it is not a second feature or Strategy implementation.
"""

from __future__ import annotations

from datetime import UTC, datetime, time
from decimal import Decimal

from market_regime_alpha.application.research_evaluation.targets import (
    OutcomeTargetProtocol,
    TargetDefinition,
)
from market_regime_alpha.application.historical_corpus.golden_loop import (
    GoldenLoopScoringContract,
)
from market_regime_alpha.application.research_validation.common import (
    ENGINEERING_LIMITATIONS,
    ValidationArtifactReference,
)
from market_regime_alpha.application.research_validation.formal_protocol import (
    HyperparameterDomain,
    ResearchExperimentDefinition,
    SearchBudget,
)
from market_regime_alpha.application.research_validation.historical_economics import (
    HistoricalStrategyEconomicsPolicySet,
)
from market_regime_alpha.application.research_validation.liquidity_capacity import (
    CapacityParameter,
    CapacityValueProvenance,
    LiquidityCapacityProtocol,
)
from market_regime_alpha.application.strategy_shadow.economics import (
    StrategyEconomicsPolicy,
    StrategyEntryKind,
    StrategyExitKind,
)
from market_regime_alpha.application.strategy_shadow.portfolio import (
    ShadowParameterProvenance,
)
from market_regime_alpha.features.technical.catalog import canonical_technical_feature_set
from market_regime_alpha.features.spine import FeatureSetConfiguration


PHASE_E3_DECISION_LOCAL_TIME = time(14, 55)
PHASE_E3_TIMEZONE = "Asia/Shanghai"
_FEATURE_EFFECTIVE_FROM = datetime(1990, 1, 1, tzinfo=UTC)


def create_phase_e3_feature_configuration() -> FeatureSetConfiguration:
    return canonical_technical_feature_set(effective_from=_FEATURE_EFFECTIVE_FROM)


def create_phase_e3_strategy_economics_policy_set(
    *,
    target_protocol: OutcomeTargetProtocol,
    created_at: datetime,
) -> HistoricalStrategyEconomicsPolicySet:
    policies = tuple(
        _strategy_policy(target, created_at) for target in target_protocol.targets
    )
    return HistoricalStrategyEconomicsPolicySet.create(
        policy_set_version="phase-e3-unchanged-phase-e2-economics-v1",
        target_protocol_reference=ValidationArtifactReference(
            "OUTCOME_TARGET_PROTOCOL",
            target_protocol.protocol_id,
            target_protocol.protocol_hash,
        ),
        strategy_policies=policies,
        capacity_protocol=_capacity_protocol(created_at),
        created_at=created_at,
        limitations=tuple(
            sorted(
                {
                    *ENGINEERING_LIMITATIONS,
                    "COST_AND_FILLABILITY_ENGINEERING_ASSUMPTIONS",
                    "NOT_EMPIRICALLY_CALIBRATED",
                }
            )
        ),
    )


def create_phase_e3_historical_experiment(
    target_protocol: OutcomeTargetProtocol,
    *,
    locked_at: datetime,
) -> ResearchExperimentDefinition:
    """Create the sole unchanged Phase E2 methodology admitted by Phase E3."""

    feature_owner = create_phase_e3_feature_configuration()
    economics_owner = create_phase_e3_strategy_economics_policy_set(
        target_protocol=target_protocol,
        created_at=locked_at,
    )
    return ResearchExperimentDefinition.create(
        research_question=(
            "Does the unchanged Phase E alpha chain retain incremental ranking "
            "and executable economic value across longitudinal CSI300 history?"
        ),
        hypothesis=(
            "No Alpha layer is presumed valuable; positive, negative, "
            "inconclusive and not-estimable results are retained."
        ),
        decision_time_policy="FROZEN_14_55_ASIA_SHANGHAI",
        target_references=tuple(
            ValidationArtifactReference(
                "OUTCOME_TARGET",
                item.target_id,
                item.target_hash,
            )
            for item in target_protocol.targets
        ),
        feature_reference=ValidationArtifactReference(
            "FEATURE_SET_CONFIGURATION",
            feature_owner.feature_set_id,
            feature_owner.content_hash,
        ),
        feature_version=feature_owner.feature_set_version,
        allowed_model_families=("CANONICAL_HISTORICAL_FORECAST",),
        hyperparameter_space=(
            HyperparameterDomain("frozen_configuration", ("phase-e2-v1",)),
        ),
        search_budget=SearchBudget(1, 1),
        primary_hypothesis_ids=(
            "LONGITUDINAL:ABLATION_INCREMENTAL_LIFT:V1",
            "LONGITUDINAL:STRATEGY_NET_RETURN:V1",
        ),
        secondary_hypothesis_ids=(
            "LONGITUDINAL:FORECAST_ESTIMABILITY:V1",
            "LONGITUDINAL:SIGNAL_ACTIVE_COVERAGE:V1",
        ),
        multiple_testing_family_id="PHASE_E3_LONGITUDINAL_CHAIN_V1",
        stopping_rule="EXHAUST_FROZEN_SIX_MONTH_CORPUS",
        train_validation_policy="EXPANDING_PRIOR_SESSIONS_EXPLORATORY_ONLY",
        purge_embargo_policy="T_PLUS_1_OUTCOME_AVAILABLE_AFTER_NEXT_SESSION_ONLY",
        oos_unlock_policy="FORMAL_OOS_LOCKED_CLOSED",
        randomness_algorithm="DETERMINISTIC_CANONICAL_KERNELS",
        random_seeds=(20260813,),
        cost_policy_reference=economics_owner.reference,
        schema_version="research-experiment-definition/v2",
    )


def create_golden_loop_v2_historical_experiment(
    target_protocol: OutcomeTargetProtocol,
    *,
    locked_at: datetime,
) -> ResearchExperimentDefinition:
    """Freeze the V2 correctness change without tuning Phase E3 inputs."""

    v1 = create_phase_e3_historical_experiment(
        target_protocol,
        locked_at=locked_at,
    )
    scoring = GoldenLoopScoringContract.create_v2()
    return ResearchExperimentDefinition.create(
        research_question=v1.research_question,
        hypothesis=v1.hypothesis,
        decision_time_policy=v1.decision_time_policy,
        target_references=v1.target_references,
        feature_reference=v1.feature_reference,
        feature_version=v1.feature_version,
        allowed_model_families=v1.allowed_model_families,
        hyperparameter_space=(
            *v1.hyperparameter_space,
            HyperparameterDomain(
                "canonical_evidence_wiring",
                ("MULTI_STRATEGY_PORTFOLIO_OUTCOME_V2",),
            ),
            HyperparameterDomain(
                "missing_policy",
                (scoring.missing_policy,),
            ),
            HyperparameterDomain(
                "scoring_contract_hash",
                (scoring.contract_hash,),
            ),
            HyperparameterDomain(
                "selection_policy",
                (scoring.selection_policy,),
            ),
        ),
        search_budget=v1.search_budget,
        primary_hypothesis_ids=(
            "GOLDEN_LOOP_V2:ABLATION_INCREMENTAL_LIFT",
            "GOLDEN_LOOP_V2:CANONICAL_STRATEGY_NET_RETURN",
        ),
        secondary_hypothesis_ids=(
            "GOLDEN_LOOP_V2:CONSTANT_FACTOR_NEUTRALITY",
            "GOLDEN_LOOP_V2:FORECAST_ESTIMABILITY",
            "GOLDEN_LOOP_V2:SIGNAL_ACTIVE_COVERAGE",
            "GOLDEN_LOOP_V2:SYMBOL_EXCHANGE_BIAS",
        ),
        multiple_testing_family_id="WP_GOLDEN_LOOP_01_CORRECTNESS_V2",
        stopping_rule=v1.stopping_rule,
        train_validation_policy=v1.train_validation_policy,
        purge_embargo_policy=v1.purge_embargo_policy,
        oos_unlock_policy=v1.oos_unlock_policy,
        randomness_algorithm=v1.randomness_algorithm,
        random_seeds=v1.random_seeds,
        cost_policy_reference=v1.cost_policy_reference,
        schema_version=v1.schema_version,
    )


def verify_phase_e3_historical_experiment(
    definition: ResearchExperimentDefinition,
    *,
    target_protocol: OutcomeTargetProtocol,
    feature_owner: FeatureSetConfiguration,
    economics_owner: HistoricalStrategyEconomicsPolicySet,
    decision_local_time: time,
    timezone_name: str,
    configuration_references: tuple[ValidationArtifactReference, ...],
) -> None:
    """Fail closed unless owner reload proves the exact frozen methodology."""

    expected = create_phase_e3_historical_experiment(
        target_protocol,
        locked_at=economics_owner.created_at,
    )
    if definition != expected:
        raise ValueError(
            "Longitudinal Historical Experiment diverges from the frozen Phase E3 methodology"
        )
    if feature_owner != create_phase_e3_feature_configuration():
        raise ValueError("Longitudinal Historical Feature owner diverged")
    if economics_owner != create_phase_e3_strategy_economics_policy_set(
        target_protocol=target_protocol,
        created_at=economics_owner.created_at,
    ):
        raise ValueError("Longitudinal Historical Economics owner diverged")
    if (
        decision_local_time != PHASE_E3_DECISION_LOCAL_TIME
        or timezone_name != PHASE_E3_TIMEZONE
    ):
        raise ValueError("Longitudinal Historical DecisionTime policy diverged")
    required = {
        definition.feature_reference,
        definition.cost_policy_reference,
    }
    if not required.issubset(set(configuration_references)):
        raise ValueError(
            "Longitudinal Historical command omits frozen feature or cost bindings"
        )


def verify_golden_loop_v2_historical_experiment(
    definition: ResearchExperimentDefinition,
    *,
    target_protocol: OutcomeTargetProtocol,
    feature_owner: FeatureSetConfiguration,
    economics_owner: HistoricalStrategyEconomicsPolicySet,
    decision_local_time: time,
    timezone_name: str,
    configuration_references: tuple[ValidationArtifactReference, ...],
) -> None:
    """Fail closed unless the exact Golden Loop V2 correction is bound."""

    expected = create_golden_loop_v2_historical_experiment(
        target_protocol,
        locked_at=economics_owner.created_at,
    )
    if definition != expected:
        raise ValueError(
            "Historical Experiment diverges from the frozen Golden Loop V2 methodology"
        )
    if feature_owner != create_phase_e3_feature_configuration():
        raise ValueError("Golden Loop V2 Historical Feature owner diverged")
    if economics_owner != create_phase_e3_strategy_economics_policy_set(
        target_protocol=target_protocol,
        created_at=economics_owner.created_at,
    ):
        raise ValueError("Golden Loop V2 Historical Economics owner diverged")
    if (
        decision_local_time != PHASE_E3_DECISION_LOCAL_TIME
        or timezone_name != PHASE_E3_TIMEZONE
    ):
        raise ValueError("Golden Loop V2 Historical DecisionTime policy diverged")
    required = {
        definition.feature_reference,
        definition.cost_policy_reference,
    }
    if not required.issubset(set(configuration_references)):
        raise ValueError(
            "Golden Loop V2 command omits frozen feature or cost bindings"
        )


def _strategy_policy(
    target: TargetDefinition,
    created_at: datetime,
) -> StrategyEconomicsPolicy:
    return StrategyEconomicsPolicy.create(
        policy_version=f"phase-e-{target.checkpoint.value}-engineering-cost-v1",
        prediction_target=target,
        entry_kind=StrategyEntryKind.FROZEN_DECISION_REFERENCE,
        exit_kind=StrategyExitKind.FIXED_TIME,
        fixed_exit_checkpoint=target.checkpoint,
        barrier_id=None,
        forecast_raw_score_threshold=None,
        lot_size=100,
        t_plus_one=True,
        parameters={
            "commission_bps": (
                Decimal("3"),
                ShadowParameterProvenance.ENGINEERING_ASSUMPTION,
            ),
            "stamp_duty_bps": (
                Decimal("5"),
                ShadowParameterProvenance.ENGINEERING_ASSUMPTION,
            ),
            "spread_slippage_bps": (
                Decimal("5"),
                ShadowParameterProvenance.ENGINEERING_ASSUMPTION,
            ),
        },
        created_at=created_at,
    )


def _capacity_protocol(created_at: datetime) -> LiquidityCapacityProtocol:
    return LiquidityCapacityProtocol.create(
        protocol_version="phase-e-capacity-engineering-v1",
        parameters=tuple(
            CapacityParameter(
                name,
                value,
                CapacityValueProvenance.ENGINEERING_ASSUMPTION,
            )
            for name, value in (
                ("impact_coefficient_bps", Decimal("8")),
                ("participation_rate", Decimal("0.1")),
                ("slippage_bps", Decimal("5")),
            )
        ),
        created_at=created_at,
    )


__all__ = [
    "HistoricalStrategyEconomicsPolicySet",
    "PHASE_E3_DECISION_LOCAL_TIME",
    "PHASE_E3_TIMEZONE",
    "create_phase_e3_feature_configuration",
    "create_golden_loop_v2_historical_experiment",
    "create_phase_e3_historical_experiment",
    "create_phase_e3_strategy_economics_policy_set",
    "verify_phase_e3_historical_experiment",
    "verify_golden_loop_v2_historical_experiment",
]
