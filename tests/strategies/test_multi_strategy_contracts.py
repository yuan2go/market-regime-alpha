from __future__ import annotations

from dataclasses import fields
from decimal import Decimal

from market_regime_alpha.core.identity import ArtifactId, StrategyId
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.application.continuous_research.journal import (
    RuntimeArtifactReference,
)
from market_regime_alpha.strategies.contracts import (
    CanonicalStrategyAction,
    PortfolioWeightingMethod,
    StrategyContract,
    StrategyFamily,
    StrategyVersion,
)


def _reference(kind: str, name: str) -> RuntimeArtifactReference:
    digest = canonical_hash({"kind": kind, "name": name})
    return RuntimeArtifactReference(kind, ArtifactId(f"{name}:{digest[7:]}"), digest)


def _contract(**changes: object) -> StrategyContract:
    values: dict[str, object] = {
        "strategy_id": StrategyId("overnight-canonical"),
        "family": StrategyFamily.OVERNIGHT,
        "semantic_version": "1.0.0",
        "objective": "Late-session opportunity with explicit next-session realization.",
        "universe_reference": _reference("UNIVERSE_POLICY", "full-a-research"),
        "target_references": (_reference("OUTCOME_TARGET_PROTOCOL", "t-plus-one"),),
        "decision_times": ("14:55:00+08:00",),
        "horizon_sessions": (1,),
        "candidate_policy_version": "candidate-pass-through-v1",
        "action_policy_version": "overnight-state-v1",
        "portfolio_weighting": PortfolioWeightingMethod.EQUAL,
        "top_k": 3,
        "strategy_budget": Decimal("0.30"),
        "cost_model_reference": _reference("COST_MODEL", "engineering-cost"),
        "evaluation_protocol_reference": _reference(
            "EVALUATION_PROTOCOL", "overnight-evaluation"
        ),
        "code_reference": _reference("CODE_IDENTITY", "code-sha"),
        "configuration_reference": _reference("CONFIGURATION", "overnight-config"),
        "parameters": (("minimum_entry_score", "0"),),
        "limitations": (
            "CALIBRATED_FALSE",
            "FORMAL_OOS_FALSE",
            "PIT_INCOMPLETE",
            "PRODUCTION_AUTHORIZED_FALSE",
        ),
    }
    values.update(changes)
    return StrategyContract.create(**values)  # type: ignore[arg-type]


def test_strategy_contract_identity_covers_result_affecting_semantics() -> None:
    baseline = _contract()

    assert baseline == _contract()
    assert baseline.contract_id != _contract(top_k=5).contract_id
    assert baseline.contract_id != _contract(
        parameters=(("minimum_entry_score", "0.55"),)
    ).contract_id
    assert baseline.contract_id != _contract(
        target_references=(_reference("OUTCOME_TARGET_PROTOCOL", "swing-5"),)
    ).contract_id
    assert baseline.contract_id != _contract(
        cost_model_reference=_reference("COST_MODEL", "cost-v2")
    ).contract_id
    assert baseline.contract_id != _contract(
        code_reference=_reference("CODE_IDENTITY", "another-code-sha")
    ).contract_id


def test_strategy_version_is_scoped_to_exact_contract() -> None:
    first = StrategyVersion.activate(_contract())
    second = StrategyVersion.activate(_contract())
    changed = StrategyVersion.activate(_contract(top_k=5))

    assert first == second
    assert first.version_id != changed.version_id
    assert first.contract_reference.artifact_id == _contract().contract_id
    assert first.production_authorized is False


def test_canonical_actions_keep_no_action_and_hold_distinct() -> None:
    assert CanonicalStrategyAction.NO_ACTION is not CanonicalStrategyAction.HOLD
    assert tuple(item.value for item in CanonicalStrategyAction) == (
        "NO_ACTION",
        "ENTER",
        "HOLD",
        "ADD",
        "REDUCE",
        "ROTATE",
        "EXIT",
    )


def test_strategy_contract_and_version_do_not_own_physical_position() -> None:
    prohibited = {"physical_position", "fill", "order", "broker_order"}

    assert prohibited.isdisjoint({item.name for item in fields(StrategyContract)})
    assert prohibited.isdisjoint({item.name for item in fields(StrategyVersion)})
