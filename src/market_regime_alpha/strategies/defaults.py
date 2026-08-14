"""The two canonical exploratory Strategy registrations for the current platform."""

from __future__ import annotations

from decimal import Decimal
from typing import Mapping

from market_regime_alpha.application.continuous_research.journal import (
    RuntimeArtifactReference,
)
from market_regime_alpha.application.research_evaluation.targets import (
    engineering_multi_horizon_protocol,
)
from market_regime_alpha.core.identity import ArtifactId, StrategyId
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.strategies.contracts import (
    PortfolioWeightingMethod,
    StrategyContract,
    StrategyFamily,
    StrategyRegistry,
    StrategyVersion,
)
from market_regime_alpha.strategies.entry.contracts import (
    EntryBarrierSpec,
    build_entry_path_target_contract,
)


def canonical_exploratory_strategy_registry() -> StrategyRegistry:
    code_reference = _reference(
        "STRATEGY_POLICY_CODE",
        "multi-strategy-policy-kernel-v1",
        {
            "overnight_policy": "overnight-state-v1",
            "swing_policy": "swing-state-v1",
        },
    )
    universe_reference = _reference(
        "STRATEGY_UNIVERSE_POLICY",
        "canonical-a-share-candidate-universe-v1",
        {
            "scope": "UPSTREAM_CANONICAL_CANDIDATE_SET",
            "strategy_override": False,
        },
    )
    configuration_reference = _reference(
        "STRATEGY_CONFIGURATION",
        "canonical-multi-strategy-configuration-v1",
        {
            "candidate_policy": "candidate-explicit-gates-v1",
            "overnight_policy": "overnight-state-v1",
            "swing_policy": "swing-state-v1",
            "decision_time": "14:55:00+08:00",
            "portfolio": "bounded-score-weight-v1",
        },
    )
    cost_reference = _reference(
        "COST_MODEL",
        "engineering-cost-not-estimable-v1",
        {
            "status": "NOT_ESTIMABLE",
            "purpose": "portfolio sensitivity only",
        },
    )
    overnight_protocol = engineering_multi_horizon_protocol()
    overnight_target = RuntimeArtifactReference(
        "OUTCOME_TARGET_PROTOCOL",
        overnight_protocol.protocol_id,
        overnight_protocol.protocol_hash,
    )
    swing_targets = tuple(_swing_target_reference(horizon) for horizon in (3, 5, 10))
    limitations = (
        "ALPHA_NOT_ESTABLISHED",
        "CALIBRATED_FALSE",
        "FORMAL_OOS_FALSE",
        "PIT_INCOMPLETE",
        "PRODUCTION_AUTHORIZED_FALSE",
    )
    decision_time = "14:55:00+08:00"
    overnight = StrategyContract.create(
        strategy_id=StrategyId("overnight-canonical"),
        family=StrategyFamily.OVERNIGHT,
        semantic_version="1.0.0-exploratory",
        objective="Late-session opportunity with explicit next-session realization.",
        universe_reference=universe_reference,
        target_references=(overnight_target,),
        decision_times=(decision_time,),
        horizon_sessions=(1,),
        candidate_policy_version="candidate-explicit-gates-v1",
        action_policy_version="overnight-state-v1",
        portfolio_weighting=PortfolioWeightingMethod.SCORE,
        top_k=3,
        strategy_budget=Decimal("0.25"),
        cost_model_reference=cost_reference,
        evaluation_protocol_reference=_reference(
            "EVALUATION_PROTOCOL",
            "overnight-evaluation-v1",
            {"metrics": ["rank_ic", "spread", "mfe", "mae", "net_economics"]},
        ),
        code_reference=code_reference,
        configuration_reference=configuration_reference,
        parameters=(("minimum_entry_score", "0"),),
        limitations=limitations,
    )
    swing = StrategyContract.create(
        strategy_id=StrategyId("swing-state-canonical"),
        family=StrategyFamily.SWING_STATE,
        semantic_version="1.0.0-exploratory",
        objective="Multi-session state transitions across Entry, Hold, Add, Reduce, and Exit.",
        universe_reference=universe_reference,
        target_references=swing_targets,
        decision_times=(decision_time,),
        horizon_sessions=(3, 5, 10),
        candidate_policy_version="candidate-explicit-gates-v1",
        action_policy_version="swing-state-v1",
        portfolio_weighting=PortfolioWeightingMethod.SCORE,
        top_k=5,
        strategy_budget=Decimal("0.25"),
        cost_model_reference=cost_reference,
        evaluation_protocol_reference=_reference(
            "EVALUATION_PROTOCOL",
            "swing-evaluation-v1",
            {
                "metrics": [
                    "rank_ic_decay",
                    "mfe",
                    "mae",
                    "target_before_stop",
                    "post_exit_opportunity_loss",
                    "avoided_drawdown",
                ]
            },
        ),
        code_reference=code_reference,
        configuration_reference=configuration_reference,
        parameters=(
            ("add_return", "0.03"),
            ("max_add_count", "1"),
            ("minimum_entry_score", "0"),
            ("reduce_drawdown", "0.04"),
            ("stop_loss", "0.08"),
        ),
        limitations=limitations,
    )
    contracts = (overnight, swing)
    return StrategyRegistry.create(
        contracts=contracts,
        versions=tuple(StrategyVersion.activate(item) for item in contracts),
    )


def _swing_target_reference(horizon: int) -> RuntimeArtifactReference:
    target = build_entry_path_target_contract(
        EntryBarrierSpec(
            upper_return=0.02,
            lower_return=-0.02,
            horizon_sessions=horizon,
            price_adjustment_basis="RAW_UNADJUSTED_RESEARCH_ONLY",
        )
    )
    payload = {
        "target_id": str(target.target_id),
        "name": target.name,
        "upper_return": target.spec.upper_return,
        "lower_return": target.spec.lower_return,
        "horizon_sessions": target.spec.horizon_sessions,
        "price_adjustment_basis": target.spec.price_adjustment_basis,
        "target_start_convention": target.spec.target_start_convention,
        "reference_price_convention": target.spec.reference_price_convention,
        "path_ordering_convention": target.spec.path_ordering_convention,
        "schema_version": target.spec.schema_version,
    }
    return RuntimeArtifactReference(
        "ENTRY_PATH_TARGET",
        ArtifactId(str(target.target_id)),
        canonical_hash(payload),
    )


def _reference(
    reference_kind: str,
    identifier: str,
    payload: Mapping[str, object],
) -> RuntimeArtifactReference:
    digest = canonical_hash(payload)
    return RuntimeArtifactReference(
        reference_kind,
        ArtifactId(f"{identifier}:{digest[7:]}"),
        digest,
    )


__all__ = ["canonical_exploratory_strategy_registry"]
