from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from market_regime_alpha.decision_support.domain import (
    DecisionArtifactBinding,
    ForecastCalibrationStatus,
    ForecastStatus,
    OpportunityStatus,
    PortfolioAllocationMethod,
    PortfolioLineStatus,
    PortfolioPolicyPlan,
    PortfolioProposalStatus,
    PreparedOpportunityContext,
    PreparedOpportunityInput,
    PreparedOpportunityInputs,
    PreparedPortfolioInputs,
    PreparedPortfolioOpportunity,
    PreparedRiskInputs,
    PreparedRiskLine,
    RiskAuthorityScope,
    RiskDecisionStatus,
    RiskMissingAction,
    RiskOperator,
    RiskPolicyPlan,
    RiskRulePlan,
    RiskRuleResult,
    RiskRuleScope,
    RiskSeverity,
    RiskSubject,
    SignalStatus,
    ThesisConditionKind,
    ThesisConditionOperator,
    ThesisConditionPlan,
    ThesisConditionSource,
    ThesisMissingAction,
    ThesisPlan,
    build_opportunity_authority,
    build_portfolio_proposal,
    build_risk_decision,
)
from tests.refoundation.decision_support.test_decision_domain import _uuid


RECORDED_AT = datetime(2026, 9, 1, 7, 5, tzinfo=UTC)


def _artifact(suffix: int, character: str) -> DecisionArtifactBinding:
    return DecisionArtifactBinding(
        artifact_id=_uuid(suffix),
        content_sha256=character * 64,
        size_bytes=100,
    )


def _prepared_opportunities() -> PreparedOpportunityInputs:
    contexts = (
        PreparedOpportunityContext(
            signal_context_binding_id=_uuid(4010),
            strategy_context_requirement_id=_uuid(4011),
            context_assessment_id=_uuid(4012),
            context_kind="MARKET_REGIME",
            content_sha256="1" * 64,
        ),
    )
    common = {
        "signal_content_sha256": "2" * 64,
        "candidate_id": _uuid(4020),
        "instrument_id": _uuid(4021),
        "commitment_content_sha256": "3" * 64,
        "target_definition_id": _uuid(4022),
        "target_definition_sha256": "4" * 64,
        "contexts": contexts,
    }
    return PreparedOpportunityInputs(
        decision_run_id=_uuid(4000),
        strategy_version_id=_uuid(4001),
        strategy_version_sha256="5" * 64,
        signal_group_id=_uuid(4002),
        signal_content_sha256="6" * 64,
        forecast_group_id=_uuid(4003),
        forecast_content_sha256="7" * 64,
        forecast_recorded_at=RECORDED_AT,
        items=(
            PreparedOpportunityInput(
                forecast_id=_uuid(4030),
                forecast_ordinal=1,
                forecast_content_sha256="8" * 64,
                forecast_status=ForecastStatus.AVAILABLE,
                calibration_status=ForecastCalibrationStatus.UNCALIBRATED,
                signal_id=_uuid(4031),
                signal_status=SignalStatus.PRESENT,
                commitment_id=_uuid(4032),
                **common,
            ),
            PreparedOpportunityInput(
                forecast_id=_uuid(4040),
                forecast_ordinal=2,
                forecast_content_sha256="9" * 64,
                forecast_status=ForecastStatus.NOT_APPLICABLE,
                calibration_status=ForecastCalibrationStatus.NOT_APPLICABLE,
                signal_id=_uuid(4041),
                signal_status=SignalStatus.WAIT,
                commitment_id=_uuid(4042),
                **{**common, "candidate_id": _uuid(4043), "instrument_id": _uuid(4044)},
            ),
        ),
    )


def test_opportunity_preserves_complete_actionable_and_wait_roster() -> None:
    prepared = _prepared_opportunities()
    authority = build_opportunity_authority(
        opportunity_set_id=_uuid(4100),
        prepared=prepared,
        request_identity="opportunity-1",
        request_sha256="a" * 64,
        command_receipt_id=_uuid(4101),
        recorded_at=RECORDED_AT,
        opportunity_id_factory=lambda item: _uuid(4110 + item.forecast_ordinal),
        context_id_factory=lambda item, context: _uuid(4120 + item.forecast_ordinal),
    )

    assert tuple(item.status for item in authority.opportunities) == (
        OpportunityStatus.ACTIONABLE,
        OpportunityStatus.WAIT,
    )
    assert authority.context_count == 2
    assert not hasattr(authority.opportunities[0], "quantity")
    assert not hasattr(authority.opportunities[0], "risk_decision_id")


def test_thesis_requires_complete_typed_falsifiable_conditions() -> None:
    thesis_id = _uuid(4200)
    condition = ThesisConditionPlan(
        thesis_condition_id=_uuid(4201),
        thesis_id=thesis_id,
        ordinal=1,
        condition_code="invalidate_on_regime_break",
        kind=ThesisConditionKind.INVALIDATE,
        source=ThesisConditionSource.CONTEXT,
        operator=ThesisConditionOperator.EQUALS,
        decimal_threshold=None,
        text_threshold="NEGATIVE",
        value_unit="CONTEXT_STATE",
        missing_action=ThesisMissingAction.INVALIDATE,
        invalidates=True,
    )
    plan = ThesisPlan(
        thesis_id=thesis_id,
        opportunity_id=_uuid(4202),
        opportunity_content_sha256="b" * 64,
        revision=1,
        supersedes_thesis_id=None,
        claim="The setup remains valid while the declared regime is not negative.",
        conditions=(condition,),
        code_artifact=_artifact(4203, "c"),
        config_artifact=_artifact(4204, "d"),
        provenance_sha256="e" * 64,
    )

    assert len(plan.condition_roster_sha256) == 64
    with pytest.raises(ValueError, match="non-empty"):
        replace(plan, conditions=())
    with pytest.raises(ValueError, match="must invalidate"):
        replace(condition, invalidates=False)


def _portfolio_policy() -> PortfolioPolicyPlan:
    return PortfolioPolicyPlan(
        portfolio_policy_id=_uuid(4300),
        policy_code="equal_weight_research",
        version=1,
        supersedes_policy_id=None,
        allocation_method=PortfolioAllocationMethod.EQUAL_WEIGHT_ACTIONABLE,
        minimum_estimable_count=1,
        maximum_line_count=2,
        maximum_single_weight=Decimal("0.60"),
        maximum_gross_weight=Decimal("1.00"),
        maximum_net_weight=Decimal("1.00"),
        minimum_cash_weight=Decimal("0.00"),
        maximum_turnover=Decimal("1.00"),
        decimal_places=4,
        code_artifact=_artifact(4301, "1"),
        config_artifact=_artifact(4302, "2"),
        provenance_sha256="3" * 64,
    )


def _portfolio_inputs() -> PreparedPortfolioInputs:
    return PreparedPortfolioInputs(
        decision_run_id=_uuid(4310),
        strategy_version_id=_uuid(4311),
        opportunity_set_id=_uuid(4312),
        opportunity_set_sha256="4" * 64,
        opportunity_set_recorded_at=RECORDED_AT,
        opportunities=(
            PreparedPortfolioOpportunity(
                opportunity_id=_uuid(4320), ordinal=1,
                candidate_id=_uuid(4321), instrument_id=_uuid(4322),
                target_definition_id=_uuid(4323),
                status=OpportunityStatus.ACTIONABLE, content_sha256="5" * 64,
            ),
            PreparedPortfolioOpportunity(
                opportunity_id=_uuid(4330), ordinal=2,
                candidate_id=_uuid(4331), instrument_id=_uuid(4332),
                target_definition_id=_uuid(4333),
                status=OpportunityStatus.WAIT, content_sha256="6" * 64,
            ),
        ),
    )


def test_portfolio_keeps_every_opportunity_and_decimal_totals() -> None:
    authority = build_portfolio_proposal(
        portfolio_proposal_id=_uuid(4340),
        prepared=_portfolio_inputs(),
        policy=_portfolio_policy(),
        request_identity="portfolio-1",
        request_sha256="7" * 64,
        command_receipt_id=_uuid(4341),
        recorded_at=RECORDED_AT,
        line_id_factory=lambda item: _uuid(4350 + item.ordinal),
    )

    assert authority.status is PortfolioProposalStatus.PROPOSED
    assert tuple(item.status for item in authority.lines) == (
        PortfolioLineStatus.INCLUDED,
        PortfolioLineStatus.EXCLUDED,
    )
    assert authority.gross_weight == authority.net_weight == Decimal("0.6000")
    assert authority.cash_weight == Decimal("0.4000")


def _risk_policy() -> RiskPolicyPlan:
    policy_id = _uuid(4400)
    return RiskPolicyPlan(
        risk_policy_id=policy_id,
        policy_code="research_risk_baseline",
        version=1,
        supersedes_policy_id=None,
        authority_scope=RiskAuthorityScope.DECISION_SUPPORT_ONLY,
        rules=(
            RiskRulePlan(
                risk_rule_id=_uuid(4401), risk_policy_id=policy_id, ordinal=1,
                rule_code="gross_weight_cap", scope=RiskRuleScope.GLOBAL,
                subject=RiskSubject.GROSS_WEIGHT, operator=RiskOperator.AT_MOST,
                decimal_threshold=Decimal("0.50"), integer_threshold=None,
                text_threshold=None, boolean_threshold=None, value_unit="WEIGHT",
                severity=RiskSeverity.REJECT, missing_action=RiskMissingAction.FAIL,
            ),
            RiskRulePlan(
                risk_rule_id=_uuid(4402), risk_policy_id=policy_id, ordinal=2,
                rule_code="single_weight_cap", scope=RiskRuleScope.LINE,
                subject=RiskSubject.SINGLE_LINE_WEIGHT,
                operator=RiskOperator.AT_MOST,
                decimal_threshold=Decimal("0.70"), integer_threshold=None,
                text_threshold=None, boolean_threshold=None, value_unit="WEIGHT",
                severity=RiskSeverity.REJECT, missing_action=RiskMissingAction.FAIL,
            ),
        ),
        code_artifact=_artifact(4403, "8"),
        config_artifact=_artifact(4404, "9"),
        provenance_sha256="a" * 64,
    )


def test_risk_evaluates_every_global_and_line_input_without_authorizing_execution() -> None:
    portfolio = build_portfolio_proposal(
        portfolio_proposal_id=_uuid(4410), prepared=_portfolio_inputs(),
        policy=_portfolio_policy(), request_identity="portfolio-risk",
        request_sha256="b" * 64, command_receipt_id=_uuid(4411),
        recorded_at=RECORDED_AT, line_id_factory=lambda item: _uuid(4420 + item.ordinal),
    )
    prepared = PreparedRiskInputs(
        portfolio_proposal_id=portfolio.portfolio_proposal_id,
        proposal_content_sha256=portfolio.content_sha256,
        proposal_status=portfolio.status,
        line_count=len(portfolio.lines),
        included_count=portfolio.included_count,
        not_estimable_count=portfolio.not_estimable_count,
        gross_weight=portfolio.gross_weight,
        net_weight=portfolio.net_weight,
        cash_weight=portfolio.cash_weight,
        qualification_count=0,
        lines=tuple(PreparedRiskLine(
            portfolio_line_id=item.portfolio_line_id,
            ordinal=item.ordinal, status=item.status,
            proposed_weight=item.proposed_weight,
            content_sha256=item.content_sha256,
        ) for item in portfolio.lines),
    )
    authority = build_risk_decision(
        risk_decision_id=_uuid(4430), prepared=prepared, policy=_risk_policy(),
        request_identity="risk-1", request_sha256="c" * 64,
        command_receipt_id=_uuid(4431), decided_at=RECORDED_AT,
        reason_id_factory=lambda rule, line: _uuid(
            4440 + rule.ordinal * 10 + (line.ordinal if line else 0)
        ),
    )

    assert authority.status is RiskDecisionStatus.REJECTED
    assert len(authority.reasons) == 3  # one global + one per complete line
    assert tuple(item.result for item in authority.reasons) == (
        RiskRuleResult.FAIL,
        RiskRuleResult.PASS,
        RiskRuleResult.PASS,
    )
    assert authority.policy.authority_scope is RiskAuthorityScope.DECISION_SUPPORT_ONLY
    assert not hasattr(authority, "execution_authorized")
