from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from market_regime_alpha.research_qualification.domain.alpha_diagnosis import (
    AlphaFunnelDiagnosisInputs,
    AlphaLossStage,
    FunnelRate,
    diagnose_alpha_loss,
)


def _estimable() -> AlphaFunnelDiagnosisInputs:
    return AlphaFunnelDiagnosisInputs(
        dataset=FunnelRate(32, 32),
        feature=FunnelRate(96, 96),
        candidate_score=FunnelRate(32, 32),
        candidate_selected=FunnelRate(8, 32),
        candidate_rank_ic=Decimal("0.05"),
        context_pass=FunnelRate(8, 8),
        signal_current=FunnelRate(8, 32),
        signal_observational=FunnelRate(8, 32),
        forecast=FunnelRate(8, 32),
        opportunity=FunnelRate(8, 32),
        portfolio_exposed=FunnelRate(8, 32),
        risk_rejected=FunnelRate(0, 8),
        assumed_cost_net_return=Decimal("0.01"),
    )


def test_context_is_diagnosed_only_when_observational_arm_restores_signal() -> None:
    inputs = replace(
        _estimable(),
        context_pass=FunnelRate(0, 8),
        signal_current=FunnelRate(0, 32),
    )

    assert diagnose_alpha_loss(inputs) is AlphaLossStage.CONTEXT


def test_zero_exposure_is_portfolio_not_zero_return_economics() -> None:
    inputs = replace(
        _estimable(),
        portfolio_exposed=FunnelRate(0, 32),
        assumed_cost_net_return=None,
    )

    assert diagnose_alpha_loss(inputs) is AlphaLossStage.PORTFOLIO


def test_missing_candidate_rank_ic_stops_before_downstream_layers() -> None:
    inputs = replace(
        _estimable(),
        candidate_rank_ic=None,
        context_pass=FunnelRate(0, 8),
        signal_current=FunnelRate(0, 32),
    )

    assert diagnose_alpha_loss(inputs) is AlphaLossStage.CANDIDATE
