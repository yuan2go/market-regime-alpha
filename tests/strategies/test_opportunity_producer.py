from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from market_regime_alpha.application.continuous_research.journal import (
    RuntimeArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.strategies.opportunity import (
    PreStrategyMarketFact,
    PreStrategyPositionFact,
    PreStrategyRiskFacts,
    build_pre_strategy_risk_state,
)
from tests.strategies.test_multi_strategy_runtime import NOW, _candidate_set


def _reference(kind: str, name: str) -> RuntimeArtifactReference:
    return RuntimeArtifactReference(
        kind,
        ArtifactId(name),
        canonical_hash({"kind": kind, "name": name}),
    )


def test_pre_strategy_risk_is_computed_from_exact_owner_facts() -> None:
    candidates = _candidate_set()
    facts = PreStrategyRiskFacts(
        account_scope="research-account",
        account_state_reference=_reference(
            "MANUAL_ACCOUNT_OBSERVATION", "account-observation"
        ),
        reconciliation_reference=_reference(
            "ACCOUNT_RECONCILIATION", "reconciliation"
        ),
        market_state_reference=_reference("DYNAMIC_STOCK_POOL", "pool"),
        risk_limit_reference=_reference(
            "DECISION_RISK_CONFIGURATION", "risk-limits"
        ),
        decision_time=NOW,
        available_at=NOW,
        total_equity=Decimal("1000"),
        available_cash=Decimal("300"),
        positions=(
            PreStrategyPositionFact(
                "000002.SZ", 100, 0, Decimal("300")
            ),
        ),
        market_facts=(
            PreStrategyMarketFact(
                "000001.SZ", True, Decimal("0.80"), False, False
            ),
            PreStrategyMarketFact(
                "000002.SZ", True, Decimal("0.90"), False, False
            ),
        ),
        maximum_single_symbol_weight=Decimal("0.20"),
        maximum_theme_weight=Decimal("0.50"),
        theme_exposures=(("theme-test", Decimal("0.30")),),
        theme_exposure_complete=True,
        minimum_liquidity=Decimal("0.50"),
        daily_loss_limit=None,
    )

    state = build_pre_strategy_risk_state(candidates=candidates, facts=facts)

    assert state.decision_for("000001.SZ").allows_action is True
    assert state.decision_for("000002.SZ").reason_codes == (
        "POSITION_AVAILABLE_QUANTITY_ZERO",
        "SINGLE_SYMBOL_EXPOSURE_LIMIT",
    )
    assert state.account_state_reference == facts.account_state_reference
    assert state.position_state_references == (facts.account_state_reference,)
    assert state.risk_limit_references == (facts.risk_limit_reference,)
    assert state.trading_restriction_references == (facts.market_state_reference,)
    assert {item.symbol for item in state.symbol_decisions} == {
        "000001.SZ",
        "000002.SZ",
    }


def test_pre_strategy_risk_fails_closed_when_theme_or_market_facts_are_unknown() -> None:
    candidates = _candidate_set()
    baseline = PreStrategyRiskFacts(
        account_scope="research-account",
        account_state_reference=_reference("MANUAL_ACCOUNT_OBSERVATION", "account"),
        reconciliation_reference=_reference("ACCOUNT_RECONCILIATION", "reconciliation"),
        market_state_reference=_reference("DYNAMIC_STOCK_POOL", "pool"),
        risk_limit_reference=_reference("DECISION_RISK_CONFIGURATION", "risk"),
        decision_time=NOW,
        available_at=NOW,
        total_equity=Decimal("1000"),
        available_cash=Decimal("500"),
        positions=(),
        market_facts=(
            PreStrategyMarketFact("000001.SZ", True, None, None, None),
            PreStrategyMarketFact("000002.SZ", True, Decimal("0.9"), False, False),
        ),
        maximum_single_symbol_weight=Decimal("0.20"),
        maximum_theme_weight=Decimal("0.20"),
        theme_exposures=(),
        theme_exposure_complete=False,
        minimum_liquidity=Decimal("0.50"),
        daily_loss_limit=None,
    )

    state = build_pre_strategy_risk_state(candidates=candidates, facts=baseline)

    assert state.decision_for("000001.SZ").reason_codes == (
        "LIQUIDITY_EVIDENCE_UNAVAILABLE",
        "ST_STATUS_EVIDENCE_UNAVAILABLE",
        "SUSPENSION_STATUS_EVIDENCE_UNAVAILABLE",
        "THEME_EXPOSURE_EVIDENCE_UNAVAILABLE",
    )
    assert "THEME_EXPOSURE_LIMIT" in build_pre_strategy_risk_state(
        candidates=candidates,
        facts=replace(
            baseline,
            theme_exposures=(("theme-test", Decimal("0.30")),),
            theme_exposure_complete=True,
        ),
    ).decision_for("000002.SZ").reason_codes
