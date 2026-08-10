from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.application.strategy_shadow.portfolio import (
    PortfolioWeightingMethod,
    ShadowParameterProvenance,
    ShadowPortfolioMarketObservation,
    ShadowPortfolioPolicy,
    ShadowPortfolioTradeSession,
    ShadowTradeSide,
    build_shadow_portfolio,
    run_shadow_portfolio_day,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.market_data import PriceLimitState, TradingStatus


NOW = datetime(2026, 8, 10, 6, 0, tzinfo=UTC)


def _reference(kind: str, name: str) -> ValidationArtifactReference:
    return ValidationArtifactReference(
        kind,
        ArtifactId(name),
        canonical_hash({"name": name}),
    )


def _policy(*, top_k: int = 3) -> ShadowPortfolioPolicy:
    return ShadowPortfolioPolicy.create(
        policy_version="phase-b-portfolio-v1",
        top_k=top_k,
        weighting_method=PortfolioWeightingMethod.EQUAL_WEIGHT,
        lot_size=100,
        t_plus_one=True,
        parameters={
            "commission_bps": (
                Decimal("2"),
                ShadowParameterProvenance.ENGINEERING_ASSUMPTION,
            ),
            "slippage_bps": (
                Decimal("5"),
                ShadowParameterProvenance.ENGINEERING_ASSUMPTION,
            ),
            "impact_bps": (
                Decimal("3"),
                ShadowParameterProvenance.ENGINEERING_ASSUMPTION,
            ),
            "exit_cost_bps": (
                Decimal("2"),
                ShadowParameterProvenance.ENGINEERING_ASSUMPTION,
            ),
            "max_participation_rate": (
                Decimal("0.10"),
                ShadowParameterProvenance.ENGINEERING_ASSUMPTION,
            ),
        },
        created_at=NOW,
    )


def _observation(
    symbol: str,
    score: str,
    price: str,
    *,
    trading_status: TradingStatus = TradingStatus.TRADING,
    limit_state: PriceLimitState = PriceLimitState.NORMAL,
    observed_at: datetime = NOW,
) -> ShadowPortfolioMarketObservation:
    return ShadowPortfolioMarketObservation(
        symbol=symbol,
        score=Decimal(score),
        risk_weight=None,
        risk_weight_provenance=None,
        reference_price=Decimal(price),
        mark_price=Decimal(price),
        average_daily_amount=Decimal("10000000"),
        trading_status=trading_status,
        price_limit_state=limit_state,
        trade_session=ShadowPortfolioTradeSession.CONTINUOUS_PM,
        value_provenance=tuple(
            (name, ShadowParameterProvenance.OBSERVED_FACT)
            for name in (
                "average_daily_amount",
                "mark_price",
                "price_limit_state",
                "reference_price",
                "trade_session",
                "trading_status",
            )
        ),
        observed_at=observed_at,
        source_references=(
            _reference("CANDIDATE_SET", f"candidate-{symbol}"),
            _reference("MARKET_DATA", f"market-{symbol}-{observed_at.date()}"),
        ),
        reason_codes=(),
    )


def test_portfolio_shadow_builds_cash_fill_position_nav_and_attribution() -> None:
    policy = _policy()
    portfolio = build_shadow_portfolio(
        policy=policy,
        research_reference=_reference("RESEARCH_PANEL_V2", "panel"),
        candidate_reference=_reference("CANDIDATE_SET", "candidates"),
        initial_cash=Decimal("300000"),
        created_at=NOW,
    )

    state = run_shadow_portfolio_day(
        portfolio=portfolio,
        policy=policy,
        trading_date=date(2026, 8, 10),
        observations=(
            _observation("000001.SZ", "0.9", "10"),
            _observation("000002.SZ", "0.8", "20"),
            _observation("000003.SZ", "0.7", "30"),
        ),
        previous=None,
        recorded_at=NOW,
    )

    assert len(state.positions) == 3
    assert all(item.quantity % Decimal("100") == 0 for item in state.positions)
    assert {item.side for item in state.order_intents} == {ShadowTradeSide.BUY}
    assert state.cash >= 0
    assert state.nav > 0
    assert state.gross_exposure > 0
    assert state.turnover > 0
    assert len(state.attribution) == 3
    assert "NOT_REAL_FILL" in state.limitations
    assert "NOT_REAL_POSITION" in state.limitations
    assert "ENGINEERING_ASSUMPTION" in state.limitations
    assert ShadowPortfolioPolicy.from_canonical_dict(
        policy.to_canonical_dict()
    ) == policy
    assert type(portfolio).from_canonical_dict(
        portfolio.to_canonical_dict()
    ) == portfolio
    assert type(state).from_canonical_dict(state.to_canonical_dict()) == state


def test_portfolio_shadow_fails_closed_for_limit_up_unknown_and_capacity() -> None:
    policy = _policy()
    portfolio = build_shadow_portfolio(
        policy=policy,
        research_reference=_reference("RESEARCH_PANEL_V2", "panel-blocked"),
        candidate_reference=_reference("CANDIDATE_SET", "candidates-blocked"),
        initial_cash=Decimal("300000"),
        created_at=NOW,
    )
    observations = (
        _observation(
            "000001.SZ",
            "0.9",
            "10",
            limit_state=PriceLimitState.LIMIT_UP,
        ),
        _observation(
            "000002.SZ",
            "0.8",
            "20",
            trading_status=TradingStatus.UNKNOWN,
        ),
        ShadowPortfolioMarketObservation(
            **{
                **_observation("000003.SZ", "0.7", "30").to_init_dict(),
                "average_daily_amount": None,
                "value_provenance": tuple(
                    item
                    for item in _observation(
                        "000003.SZ", "0.7", "30"
                    ).value_provenance
                    if item[0] != "average_daily_amount"
                ),
                "reason_codes": ("ADV_MISSING",),
            }
        ),
    )

    state = run_shadow_portfolio_day(
        portfolio=portfolio,
        policy=policy,
        trading_date=date(2026, 8, 10),
        observations=observations,
        previous=None,
        recorded_at=NOW,
    )

    assert state.positions == ()
    assert {item.status.value for item in state.fills} == {"UNFILLED"}
    reasons = {reason for item in state.order_intents for reason in item.reason_codes}
    assert {"BUY_LIMIT_UP", "TRADING_STATUS_UNKNOWN", "CAPACITY_EVIDENCE_MISSING"}.issubset(reasons)


def test_portfolio_shadow_t_plus_one_and_limit_down_keep_shadow_position() -> None:
    policy = _policy(top_k=1)
    portfolio = build_shadow_portfolio(
        policy=policy,
        research_reference=_reference("RESEARCH_PANEL_V2", "panel-exit"),
        candidate_reference=_reference("CANDIDATE_SET", "candidates-exit"),
        initial_cash=Decimal("100000"),
        created_at=NOW,
    )
    first = run_shadow_portfolio_day(
        portfolio=portfolio,
        policy=policy,
        trading_date=date(2026, 8, 10),
        observations=(_observation("000001.SZ", "0.9", "10"),),
        previous=None,
        recorded_at=NOW,
    )
    next_time = NOW + timedelta(days=1)
    second = run_shadow_portfolio_day(
        portfolio=portfolio,
        policy=policy,
        trading_date=date(2026, 8, 11),
        observations=(
            _observation(
                "000001.SZ",
                "0.1",
                "9",
                limit_state=PriceLimitState.LIMIT_DOWN,
                observed_at=next_time,
            ),
            _observation("000002.SZ", "0.9", "20", observed_at=next_time),
        ),
        previous=first,
        recorded_at=next_time,
    )

    assert {item.symbol for item in second.positions} == {"000001.SZ"}
    sell = next(item for item in second.order_intents if item.side is ShadowTradeSide.SELL)
    assert sell.reason_codes == ("SELL_LIMIT_DOWN",)
    assert next(item for item in second.fills if item.intent_id == sell.intent_id).status.value == "UNFILLED"
    buy = next(item for item in second.order_intents if item.side is ShadowTradeSide.BUY)
    assert buy.requested_quantity > 0
    assert "ZERO_EXECUTABLE_LOT" in buy.reason_codes
    assert next(item for item in second.fills if item.intent_id == buy.intent_id).status.value == "UNFILLED"


def test_portfolio_policy_rejects_missing_cost_provenance() -> None:
    parameters = {
        "commission_bps": (
            Decimal("2"),
            ShadowParameterProvenance.ENGINEERING_ASSUMPTION,
        )
    }
    with pytest.raises(ValueError, match="exact cost/capacity parameter set"):
        ShadowPortfolioPolicy.create(
            policy_version="invalid",
            top_k=1,
            weighting_method=PortfolioWeightingMethod.EQUAL_WEIGHT,
            lot_size=100,
            t_plus_one=True,
            parameters=parameters,
            created_at=NOW,
        )


def test_portfolio_shadow_capacity_creates_explicit_partial_shadow_fill() -> None:
    policy = _policy(top_k=1)
    portfolio = build_shadow_portfolio(
        policy=policy,
        research_reference=_reference("RESEARCH_PANEL_V2", "panel-partial"),
        candidate_reference=_reference("CANDIDATE_SET", "candidate-partial"),
        initial_cash=Decimal("1000000"),
        created_at=NOW,
    )
    observation = replace(
        _observation("000001.SZ", "0.9", "10"),
        average_daily_amount=Decimal("1000000"),
    )

    state = run_shadow_portfolio_day(
        portfolio=portfolio,
        policy=policy,
        trading_date=date(2026, 8, 10),
        observations=(observation,),
        previous=None,
        recorded_at=NOW,
    )

    assert state.order_intents[0].requested_quantity == Decimal("100000")
    assert state.fills[0].status.value == "PARTIAL"
    assert state.fills[0].filled_quantity == Decimal("10000")
