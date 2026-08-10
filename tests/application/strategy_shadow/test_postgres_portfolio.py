from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from tests.persistence.postgres.conftest import postgres_factory as postgres_factory

from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.application.strategy_shadow.portfolio import (
    PortfolioWeightingMethod,
    ShadowParameterProvenance,
    ShadowPortfolioMarketObservation,
    ShadowPortfolioPolicy,
    ShadowPortfolioTradeSession,
    build_shadow_portfolio,
    run_shadow_portfolio_day,
)
from market_regime_alpha.application.strategy_shadow.postgres_portfolio import (
    PostgresShadowPortfolioRepository,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.market_data import PriceLimitState, TradingStatus
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)


NOW = datetime(2026, 8, 10, 6, 0, tzinfo=UTC)


def _reference(kind: str, name: str) -> ValidationArtifactReference:
    return ValidationArtifactReference(
        kind, ArtifactId(name), canonical_hash({"name": name})
    )


def _policy() -> ShadowPortfolioPolicy:
    provenance = ShadowParameterProvenance.ENGINEERING_ASSUMPTION
    return ShadowPortfolioPolicy.create(
        policy_version="postgres-portfolio-v1",
        top_k=1,
        weighting_method=PortfolioWeightingMethod.EQUAL_WEIGHT,
        lot_size=100,
        t_plus_one=True,
        parameters={
            "commission_bps": (Decimal("2"), provenance),
            "slippage_bps": (Decimal("5"), provenance),
            "impact_bps": (Decimal("3"), provenance),
            "exit_cost_bps": (Decimal("2"), provenance),
            "max_participation_rate": (Decimal("0.1"), provenance),
        },
        created_at=NOW,
    )


def _observation(day: int) -> ShadowPortfolioMarketObservation:
    observed_at = NOW + timedelta(days=day)
    return ShadowPortfolioMarketObservation(
        symbol="000001.SZ",
        score=Decimal("0.9"),
        risk_weight=None,
        risk_weight_provenance=None,
        reference_price=Decimal("10"),
        mark_price=Decimal("10"),
        average_daily_amount=Decimal("10000000"),
        trading_status=TradingStatus.TRADING,
        price_limit_state=PriceLimitState.NORMAL,
        trade_session=ShadowPortfolioTradeSession.CONTINUOUS_PM,
        observed_at=observed_at,
        source_references=(_reference("MARKET_DATA", f"market-{day}"),),
        reason_codes=(),
    )


def test_postgres_portfolio_shadow_is_idempotent_cas_and_replayable(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    repository = PostgresShadowPortfolioRepository(postgres_factory)
    policy = _policy()
    portfolio = build_shadow_portfolio(
        policy=policy,
        research_reference=_reference("RESEARCH_PANEL_V2", "panel"),
        candidate_reference=_reference("CANDIDATE_SET", "candidate"),
        initial_cash=Decimal("100000"),
        created_at=NOW,
    )
    assert repository.save_portfolio(policy=policy, portfolio=portfolio) == portfolio
    assert repository.save_portfolio(policy=policy, portfolio=portfolio) == portfolio

    first = run_shadow_portfolio_day(
        portfolio=portfolio,
        policy=policy,
        trading_date=date(2026, 8, 10),
        observations=(_observation(0),),
        previous=None,
        recorded_at=NOW,
    )
    assert repository.append_state(first, expected_previous_state_id=None) == first
    assert repository.append_state(first, expected_previous_state_id=None) == first

    second = run_shadow_portfolio_day(
        portfolio=portfolio,
        policy=policy,
        trading_date=date(2026, 8, 11),
        observations=(_observation(1),),
        previous=first,
        recorded_at=NOW + timedelta(days=1),
    )
    with pytest.raises(ValueError, match="CAS conflict"):
        repository.append_state(second, expected_previous_state_id=None)
    assert repository.append_state(
        second, expected_previous_state_id=first.state_id
    ) == second
    assert repository.latest_state(portfolio.portfolio_id) == second
    assert repository.replay(portfolio.portfolio_id) == (first, second)

    with postgres_factory.connection(read_only=True) as connection:
        row = connection.execute(
            """
            SELECT real_order_authority, real_fill_authority,
                   real_position_authority
            FROM strategy_shadow_portfolio WHERE portfolio_id = %s
            """,
            (str(portfolio.portfolio_id),),
        ).fetchone()
        day_rows = connection.execute(
            """
            SELECT real_trading_mutation FROM strategy_shadow_portfolio_day
            ORDER BY sequence
            """
        ).fetchall()
    assert row == (False, False, False)
    assert day_rows == [(False,), (False,)]
