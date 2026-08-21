from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from market_regime_alpha.application.continuous_research.journal import (
    RuntimeArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.strategies.opportunity import (
    PreStrategyRiskState,
    PreStrategySymbolRiskDecision,
)


NOW = datetime(2026, 8, 21, 6, 55, tzinfo=UTC)


def _ref(kind: str, name: str) -> RuntimeArtifactReference:
    return RuntimeArtifactReference(
        kind,
        ArtifactId(name),
        canonical_hash({"kind": kind, "name": name}),
    )


def _risk_state() -> PreStrategyRiskState:
    return PreStrategyRiskState.create(
        account_scope="research-account",
        candidate_reference=_ref("CANDIDATE_SET", "candidates"),
        decision_time=NOW,
        available_at=NOW,
        account_state_reference=_ref("ACCOUNT_STATE", "account"),
        position_state_references=(_ref("POSITION_BOOK", "positions"),),
        liquidity_constraint_references=(
            _ref("LIQUIDITY_CONSTRAINT_SET", "liquidity"),
        ),
        position_constraint_references=(),
        risk_limit_references=(_ref("RISK_LIMIT_SET", "limits"),),
        trading_restriction_references=(),
        symbol_decisions=(
            PreStrategySymbolRiskDecision("000001.SZ", True, ()),
            PreStrategySymbolRiskDecision(
                "000002.SZ", False, ("SYMBOL_EXPOSURE_LIMIT",)
            ),
        ),
        limitations=("RESEARCH_ONLY",),
    )


def test_pre_strategy_risk_state_is_content_addressed_and_round_trips() -> None:
    state = _risk_state()

    assert state.reference.reference_kind == "PRE_STRATEGY_RISK_STATE"
    assert PreStrategyRiskState.from_canonical_dict(state.to_canonical_dict()) == state
    assert state.decision_for("000002.SZ").allows_action is False


def test_pre_strategy_risk_state_rejects_future_and_post_portfolio_facts() -> None:
    state = _risk_state()
    values = {
        name: getattr(state, name)
        for name in (
            "account_scope",
            "candidate_reference",
            "decision_time",
            "available_at",
            "account_state_reference",
            "position_state_references",
            "liquidity_constraint_references",
            "position_constraint_references",
            "risk_limit_references",
            "trading_restriction_references",
            "symbol_decisions",
            "limitations",
        )
    }

    with pytest.raises(ValueError, match="unavailable at DecisionTime"):
        PreStrategyRiskState.create(
            **(values | {"available_at": NOW + timedelta(seconds=1)})
        )
    with pytest.raises(ValueError, match="post-Portfolio facts"):
        PreStrategyRiskState.create(
            **(
                values
                | {
                    "account_state_reference": _ref(
                        "COMPLETE_ACCOUNT_RISK_DECISION", "complete-risk"
                    )
                }
            )
        )
