"""Owner-resolved Portfolio Shadow performance application service."""

from __future__ import annotations

from datetime import datetime

from market_regime_alpha.application.strategy_shadow.performance import (
    PerformancePolicy,
    PortfolioPerformanceReport,
    build_portfolio_performance_report,
)
from market_regime_alpha.application.strategy_shadow.postgres_performance import (
    PostgresPortfolioPerformanceRepository,
)
from market_regime_alpha.application.strategy_shadow.postgres_portfolio import (
    PostgresShadowPortfolioRepository,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)


class PortfolioPerformanceOperator:
    def __init__(
        self,
        factory: PostgresConnectionFactory,
        *,
        apply_migrations: bool = False,
    ) -> None:
        self._portfolio = PostgresShadowPortfolioRepository(
            factory,
            apply_migrations=apply_migrations,
        )
        self._performance = PostgresPortfolioPerformanceRepository(
            factory,
            apply_migrations=False,
        )

    def build(
        self,
        *,
        portfolio_id: ArtifactId,
        policy: PerformancePolicy,
        generated_at: datetime,
    ) -> PortfolioPerformanceReport:
        _portfolio_policy, portfolio = self._portfolio.get_portfolio(portfolio_id)
        states = self._portfolio.replay(portfolio_id)
        report = build_portfolio_performance_report(
            portfolio=portfolio,
            states=states,
            policy=policy,
            generated_at=generated_at,
        )
        return self._performance.publish(policy=policy, report=report)

    def report(self, report_id: ArtifactId) -> PortfolioPerformanceReport:
        return self._performance.get(report_id)

    def replay(self, report_id: ArtifactId) -> PortfolioPerformanceReport:
        stored = self._performance.get(report_id)
        policy = self._performance.get_policy(stored.policy_reference.artifact_id)
        _portfolio_policy, portfolio = self._portfolio.get_portfolio(
            stored.portfolio_reference.artifact_id
        )
        all_states = self._portfolio.replay(portfolio.portfolio_id)
        states = tuple(
            item
            for item in all_states
            if stored.start_date <= item.trading_date <= stored.end_date
        )
        rebuilt = build_portfolio_performance_report(
            portfolio=portfolio,
            states=states,
            policy=policy,
            generated_at=stored.generated_at,
        )
        if rebuilt != stored:
            raise ValueError("Portfolio performance replay mismatch")
        return stored


__all__ = ["PortfolioPerformanceOperator"]
