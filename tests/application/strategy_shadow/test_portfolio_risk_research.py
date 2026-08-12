from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.application.strategy_shadow.portfolio_risk_research import (
    MembershipEvidenceStatus,
    PortfolioRiskCandidate,
    PortfolioRiskMode,
    PortfolioRiskResearchPolicy,
    construct_risk_constrained_portfolio,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash


NOW = datetime(2026, 8, 12, tzinfo=UTC)


def _candidate(
    symbol: str,
    score: str,
    theme: str,
    industry: str,
    cluster: str,
    *,
    membership: MembershipEvidenceStatus = MembershipEvidenceStatus.EXPLORATORY,
) -> PortfolioRiskCandidate:
    return PortfolioRiskCandidate(
        symbol=symbol,
        score=Decimal(score),
        volatility=Decimal("0.2"),
        adv20=Decimal("10000000"),
        theme=theme,
        industry=industry,
        correlation_cluster=cluster,
        membership_evidence=membership,
    )


def _policy() -> PortfolioRiskResearchPolicy:
    return PortfolioRiskResearchPolicy.create(
        policy_version="portfolio-risk-research-v1",
        single_name_max_weight=Decimal("0.25"),
        theme_max_weight=Decimal("0.35"),
        industry_max_weight=Decimal("0.40"),
        correlation_cluster_max_weight=Decimal("0.35"),
        minimum_adv20=Decimal("1000000"),
        maximum_participation_rate=Decimal("0.10"),
        volatility_budget=Decimal("0.20"),
        cash_reserve=Decimal("0.10"),
        drawdown_reduction_threshold=Decimal("-0.10"),
        drawdown_exposure_multiplier=Decimal("0.50"),
        created_at=NOW,
    )


def _reference() -> ValidationArtifactReference:
    return ValidationArtifactReference(
        "SHADOW_PORTFOLIO_POLICY",
        ArtifactId("shadow-policy"),
        canonical_hash({"policy": 1}),
    )


def test_portfolio_risk_constraints_bound_concentration_capacity_and_drawdown() -> None:
    result = construct_risk_constrained_portfolio(
        policy=_policy(),
        source_policy_reference=_reference(),
        candidates=(
            _candidate("000001.SZ", "4", "T1", "I1", "C1"),
            _candidate("000002.SZ", "3", "T1", "I1", "C1"),
            _candidate("000003.SZ", "2", "T2", "I2", "C2"),
            _candidate("000004.SZ", "1", "T3", "I3", "C3"),
        ),
        portfolio_nav=Decimal("10000000"),
        current_drawdown=Decimal("-0.12"),
        mode=PortfolioRiskMode.EXPLORATORY,
        constructed_at=NOW,
    )

    weights = {item.symbol: item.weight for item in result.allocations}
    assert all(weight <= Decimal("0.25") for weight in weights.values())
    assert result.invested_weight <= Decimal("0.45")
    assert result.cash_weight >= Decimal("0.55")
    assert result.portfolio_adv_capacity == Decimal("4000000.00")
    assert result.formal_membership_qualified is False
    assert "DRAWDOWN_EXPOSURE_REDUCED" in result.reason_codes


def test_formal_portfolio_risk_fails_closed_without_pit_membership() -> None:
    with pytest.raises(ValueError, match="PIT-qualified membership"):
        construct_risk_constrained_portfolio(
            policy=_policy(),
            source_policy_reference=_reference(),
            candidates=(
                _candidate("000001.SZ", "1", "T1", "I1", "C1"),
            ),
            portfolio_nav=Decimal("1000000"),
            current_drawdown=Decimal("0"),
            mode=PortfolioRiskMode.FORMAL,
            constructed_at=NOW,
        )
