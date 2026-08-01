from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from market_regime_alpha.core.identity import (
    ArtifactId,
    FillId,
    ManualTradeId,
    OpportunityId,
    PortfolioDecisionId,
    ThesisId,
)
from market_regime_alpha.decision import (
    DecisionEvidenceReference,
    InvalidationCondition,
    InvalidationKind,
    ThesisState,
    TradingThesis,
)
from market_regime_alpha.decision.thesis import TRADING_THESIS_SCHEMA
from market_regime_alpha.execution import Fill, FillKind, TradeSide
from market_regime_alpha.execution.manual import FILL_SCHEMA
from market_regime_alpha.portfolio import (
    RISK_BUDGET_SCHEMA,
    IndependentRiskService,
    PortfolioAccountSnapshot,
    PortfolioDecision,
    PortfolioDecisionState,
    PortfolioOutputMode,
    RiskBudget,
    TargetPosition,
)
from market_regime_alpha.portfolio.lifecycle import PORTFOLIO_DECISION_SCHEMA
from market_regime_alpha.position import (
    POSITION_LIFECYCLE_CONFIG_SCHEMA,
    ExitAssessmentModel,
    HoldingAssessmentModel,
    PositionLifecycleAction,
    PositionLifecycleConfig,
    PositionProjector,
    ThesisHealth,
    ThesisHealthObservation,
)


TZ = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 7, 20, 14, 55, tzinfo=TZ)
SYMBOL = "000001.SZ"


def _reference(name: str = "holding-evidence") -> DecisionEvidenceReference:
    return DecisionEvidenceReference(
        artifact_type="SUPPLEMENTAL_RESEARCH_EVIDENCE",
        artifact_id=ArtifactId(name),
        content_hash="sha256:" + "7" * 64,
        status="VERIFIED_EXPLORATORY",
    )


def _thesis(*, state: ThesisState = ThesisState.APPROVED) -> TradingThesis:
    version = 0 if state is ThesisState.APPROVED else 1
    return TradingThesis(
        schema_version=TRADING_THESIS_SCHEMA,
        thesis_id=ThesisId("thesis-holding-test"),
        opportunity_id=OpportunityId("opportunity-holding-test"),
        source_opportunity_version=0,
        symbol=SYMBOL,
        supporting_evidence=(_reference("supporting-evidence"),),
        invalidation_conditions=(
            InvalidationCondition(
                condition_id="price-floor",
                kind=InvalidationKind.PRICE,
                description="synthetic fixture condition",
                reason_code="SYNTHETIC_PRICE_INVALIDATION",
            ),
        ),
        time_invalidation=NOW + timedelta(days=5),
        state=state,
        version=version,
        approved_by="approver-a",
        approval_reason="synthetic fixture",
        created_at=NOW - timedelta(days=1),
        updated_at=NOW - timedelta(days=1) if version == 0 else NOW,
        last_actor="approver-a",
        last_reason="synthetic fixture",
    )


def _fill() -> Fill:
    return Fill(
        schema_version=FILL_SCHEMA,
        fill_id=FillId("fill-holding-entry"),
        manual_trade_id=ManualTradeId("manual-holding-entry"),
        account_id="account-a",
        symbol=SYMBOL,
        side=TradeSide.BUY,
        quantity=100,
        price=10.0,
        fees=0.0,
        occurred_at=NOW - timedelta(hours=1),
        recorded_at=NOW - timedelta(minutes=59),
        actor="human-a",
        reason="synthetic entry",
        external_fill_id="external-holding-entry",
        fill_kind=FillKind.EXECUTION,
        correction_of_fill_id=None,
    )


def _position():
    return PositionProjector().project(
        account_id="account-a",
        symbol=SYMBOL,
        fills=(_fill(),),
        as_of=NOW - timedelta(minutes=1),
    )


def _config() -> PositionLifecycleConfig:
    return PositionLifecycleConfig.create(
        profile_id="synthetic_holding_exit_profile_v1",
        add_minimum_return=0.05,
        weakening_return_threshold=-0.03,
        exit_return_threshold=-0.08,
        enable_add_assessment=True,
        market_scope="A_SHARE",
        allowed_side="LONG_ONLY",
        schema_version=POSITION_LIFECYCLE_CONFIG_SCHEMA,
    )


def _observation(
    *,
    price: float = 10.1,
    signal: bool | None = True,
    theme: bool | None = True,
    capital: bool | None = True,
    triggered: tuple[str, ...] = (),
) -> ThesisHealthObservation:
    missing = (
        ("SYNTHETIC_SIGNAL_MISSING",)
        if signal is None
        else ()
    )
    return ThesisHealthObservation(
        symbol=SYMBOL,
        market_price=price,
        observed_at=NOW - timedelta(seconds=2),
        availability_time=NOW - timedelta(seconds=1),
        signal_support=signal,
        theme_support=theme,
        capital_support=capital,
        triggered_condition_ids=triggered,
        evidence=_reference(),
        missing_reason_codes=missing,
    )


def _add_authority(thesis: TradingThesis, current: int = 100):
    budget = RiskBudget.create(
        profile_id="test_risk_profile_v1",
        maximum_gross_exposure=1.0,
        single_symbol_limit=1.0,
        theme_limit=1.0,
        liquidity_max_participation=1.0,
        minimum_cash_reserve=0.0,
        maximum_loss_budget=1.0,
        t_plus_one_enforced=True,
        risk_service_timeout_seconds=2.0,
        market_scope="A_SHARE",
        allowed_side="LONG_ONLY",
        schema_version=RISK_BUDGET_SCHEMA,
    )
    target = TargetPosition(
        thesis_id=thesis.thesis_id,
        symbol=SYMBOL,
        theme_id="theme-bank",
        current_quantity=current,
        available_quantity=current,
        target_quantity=200,
        trade_quantity=200 - current,
        reference_price=10.6,
        average_daily_trade_value=1_000_000.0,
        loss_per_share=1.0,
    )
    portfolio = PortfolioDecision(
        schema_version=PORTFOLIO_DECISION_SCHEMA,
        decision_id=PortfolioDecisionId("portfolio-add-risk-test"),
        mode=PortfolioOutputMode.MANUAL_CONFIRMATION,
        state=PortfolioDecisionState.PROPOSED_FOR_RISK,
        risk_budget_id=budget.configuration_id,
        risk_budget_hash=budget.configuration_hash,
        risk_budget=budget,
        account_snapshot=PortfolioAccountSnapshot(
            net_asset_value=100_000.0,
            available_cash=90_000.0,
            observed_at=NOW - timedelta(seconds=2),
            source_reference="synthetic-account",
        ),
        target_positions=(target,),
        thesis_ids=(thesis.thesis_id,),
        version=0,
        actor="portfolio-a",
        reason="synthetic ADD reevaluation",
        created_at=NOW,
        reason_codes=("PORTFOLIO_PROPOSED_FOR_INDEPENDENT_RISK",),
    )
    risk = IndependentRiskService().assess(
        portfolio,
        actor="risk-a",
        reason="synthetic ADD reevaluation",
        started_at=NOW,
        completed_at=NOW + timedelta(seconds=1),
    )
    return portfolio, risk


def test_holding_and_exit_are_independent_roles() -> None:
    thesis = _thesis()
    position = _position()
    holding = HoldingAssessmentModel().assess(
        thesis,
        position,
        _observation(),
        _config(),
        assessed_at=NOW,
        actor="reviewer-a",
        reason="synthetic healthy review",
    )
    exit_assessment = ExitAssessmentModel().assess(
        thesis,
        position,
        _observation(),
        _config(),
        assessed_at=NOW,
        actor="reviewer-a",
        reason="synthetic healthy review",
    )
    assert holding.action is PositionLifecycleAction.HOLD
    assert exit_assessment.action is PositionLifecycleAction.WAIT
    assert holding.thesis_health is ThesisHealth.HEALTHY


def test_add_fails_closed_without_fresh_risk_and_succeeds_with_recomputation() -> None:
    thesis = _thesis()
    position = _position()
    observation = _observation(price=10.6)
    model = HoldingAssessmentModel()
    waiting = model.assess(
        thesis,
        position,
        observation,
        _config(),
        assessed_at=NOW,
        actor="reviewer-a",
        reason="synthetic add review",
    )
    assert waiting.action is PositionLifecycleAction.WAIT
    assert waiting.reason_codes == ("ADD_RISK_AUTHORITY_MISSING",)

    portfolio, risk = _add_authority(thesis)
    not_yet_completed = model.assess(
        thesis,
        position,
        observation,
        _config(),
        assessed_at=NOW,
        actor="reviewer-a",
        reason="synthetic add review",
        add_portfolio=portfolio,
        add_risk=risk,
    )
    assert not_yet_completed.action is PositionLifecycleAction.WAIT
    assert not_yet_completed.reason_codes == (
        "ADD_RISK_AUTHORITY_NOT_FRESH_FOR_POSITION",
    )

    approved = model.assess(
        thesis,
        position,
        observation,
        _config(),
        assessed_at=NOW + timedelta(seconds=2),
        actor="reviewer-a",
        reason="synthetic add review",
        add_portfolio=portfolio,
        add_risk=risk,
    )
    assert approved.action is PositionLifecycleAction.ADD
    assert approved.add_risk_decision_id == risk.risk_decision_id

    forged = replace(risk, reason_codes=("FORGED_APPROVAL",))
    rejected = model.assess(
        thesis,
        position,
        observation,
        _config(),
        assessed_at=NOW + timedelta(seconds=2),
        actor="reviewer-a",
        reason="synthetic add review",
        add_portfolio=portfolio,
        add_risk=forged,
    )
    assert rejected.action is PositionLifecycleAction.WAIT
    assert rejected.reason_codes == ("ADD_RISK_RECOMPUTATION_MISMATCH",)


def test_invalidated_thesis_never_adds_and_exit_requires_new_risk_cycle() -> None:
    thesis = _thesis()
    position = _position()
    observation = _observation(price=11.0, triggered=("price-floor",))
    portfolio, risk = _add_authority(thesis)
    holding = HoldingAssessmentModel().assess(
        thesis,
        position,
        observation,
        _config(),
        assessed_at=NOW + timedelta(seconds=2),
        actor="reviewer-a",
        reason="synthetic invalidation",
        add_portfolio=portfolio,
        add_risk=risk,
    )
    exit_assessment = ExitAssessmentModel().assess(
        thesis,
        position,
        observation,
        _config(),
        assessed_at=NOW + timedelta(seconds=2),
        actor="reviewer-a",
        reason="synthetic invalidation",
    )
    assert holding.action is PositionLifecycleAction.WAIT
    assert holding.thesis_health is ThesisHealth.INVALIDATED
    assert exit_assessment.action is PositionLifecycleAction.EXIT
    assert exit_assessment.requires_portfolio_risk


def test_weakening_reduce_and_missing_data_are_explicit() -> None:
    thesis = _thesis()
    position = _position()
    reduced = ExitAssessmentModel().assess(
        thesis,
        position,
        _observation(price=9.6, theme=False),
        _config(),
        assessed_at=NOW,
        actor="reviewer-a",
        reason="synthetic weakening",
    )
    insufficient = HoldingAssessmentModel().assess(
        thesis,
        position,
        _observation(signal=None),
        _config(),
        assessed_at=NOW,
        actor="reviewer-a",
        reason="synthetic missingness",
    )
    stopped = ExitAssessmentModel().assess(
        thesis,
        position,
        _observation(price=9.0),
        _config(),
        assessed_at=NOW,
        actor="reviewer-a",
        reason="synthetic price exit",
    )
    assert reduced.action is PositionLifecycleAction.REDUCE
    assert insufficient.action is PositionLifecycleAction.DATA_INSUFFICIENT
    assert stopped.action is PositionLifecycleAction.EXIT
