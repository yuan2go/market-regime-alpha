"""Frozen Phase E3 methodology bound to the longitudinal Historical command.

The owner is deliberately narrow: changing any feature, threshold, target,
cost, or evaluation choice produces a different Experiment Definition and
requires a new explicitly coded experiment contract.
"""

from __future__ import annotations

from datetime import time
from typing import Any

from market_regime_alpha.application.research_evaluation.targets import (
    OutcomeTargetProtocol,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.application.research_validation.formal_protocol import (
    HyperparameterDomain,
    ResearchExperimentDefinition,
    SearchBudget,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash


PHASE_E3_DECISION_LOCAL_TIME = time(14, 55)
PHASE_E3_TIMEZONE = "Asia/Shanghai"


def phase_e3_feature_methodology_payload() -> dict[str, Any]:
    return {
        "schema_version": "phase-e3-canonical-feature-methodology/v1",
        "chain": [
            "PRICE",
            "VOLUME",
            "MARKET_REGIME",
            "ETF",
            "THEME",
            "CAPITAL",
            "DYNAMIC_POOL",
            "CANDIDATE",
            "SIGNAL",
            "FORECAST",
        ],
        "forecast_minimum_usable_samples": 20,
        "signal_threshold_policy": "UNCHANGED_FROM_PHASE_E2",
        "tuning_after_phase_e2": False,
    }


def phase_e3_strategy_economics_payload() -> dict[str, Any]:
    return {
        "schema_version": "phase-e3-strategy-economics-policy/v1",
        "commission_bps_each_side": "3",
        "stamp_duty_bps_sell": "5",
        "spread_slippage_bps_each_side": "5",
        "impact_coefficient_bps": "8",
        "participation_rate": "0.1",
        "commission_provenance": "ENGINEERING_ASSUMPTION",
        "stamp_duty_provenance": "ENGINEERING_ASSUMPTION",
        "slippage_provenance": "ENGINEERING_ASSUMPTION",
        "impact_provenance": "ENGINEERING_ASSUMPTION",
        "fillability_provenance": "ENGINEERING_ASSUMPTION",
        "capacity_provenance": "ENGINEERING_ASSUMPTION",
    }


def phase_e3_feature_reference() -> ValidationArtifactReference:
    payload = phase_e3_feature_methodology_payload()
    digest = canonical_hash(payload)
    return ValidationArtifactReference(
        "FEATURE_DEFINITION_SET",
        ArtifactId(f"phase-e3-feature-methodology:{digest[7:]}"),
        digest,
    )


def phase_e3_cost_policy_reference() -> ValidationArtifactReference:
    payload = phase_e3_strategy_economics_payload()
    digest = canonical_hash(payload)
    return ValidationArtifactReference(
        "SHADOW_PORTFOLIO_POLICY",
        ArtifactId(f"phase-e3-strategy-economics-policy:{digest[7:]}"),
        digest,
    )


def create_phase_e3_historical_experiment(
    target_protocol: OutcomeTargetProtocol,
) -> ResearchExperimentDefinition:
    """Create the sole unchanged Phase E2 methodology admitted by Phase E3."""

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
        feature_reference=phase_e3_feature_reference(),
        feature_version="phase-e3-unchanged-phase-e2-canonical-v1",
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
        cost_policy_reference=phase_e3_cost_policy_reference(),
    )


def verify_phase_e3_historical_experiment(
    definition: ResearchExperimentDefinition,
    *,
    target_protocol: OutcomeTargetProtocol,
    decision_local_time: time,
    timezone_name: str,
    configuration_references: tuple[ValidationArtifactReference, ...],
) -> None:
    """Fail closed unless the command binds the exact frozen methodology."""

    expected = create_phase_e3_historical_experiment(target_protocol)
    if definition != expected:
        raise ValueError(
            "Longitudinal Historical Experiment diverges from the frozen Phase E3 methodology"
        )
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


__all__ = [
    "PHASE_E3_DECISION_LOCAL_TIME",
    "PHASE_E3_TIMEZONE",
    "create_phase_e3_historical_experiment",
    "phase_e3_cost_policy_reference",
    "phase_e3_feature_methodology_payload",
    "phase_e3_feature_reference",
    "phase_e3_strategy_economics_payload",
    "verify_phase_e3_historical_experiment",
]
