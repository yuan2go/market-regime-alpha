"""PostgreSQL Portfolio/Risk authority adapters."""

from market_regime_alpha.persistence.postgres.adapter import (
    PostgresRepositoryAdapter,
)
from market_regime_alpha.portfolio.sqlite_account_authority import (
    SQLiteCompleteAccountPortfolioRiskRepository,
)
from market_regime_alpha.portfolio.sqlite_repository import (
    SQLitePortfolioDecisionRepository,
)
from market_regime_alpha.portfolio.sqlite_risk_routes import (
    SQLiteRiskRouteRepository,
)


class PostgresPortfolioDecisionRepository(
    PostgresRepositoryAdapter,
    SQLitePortfolioDecisionRepository,
):
    """PostgreSQL implementation of PortfolioDecisionRepository."""


class PostgresCompleteAccountPortfolioRiskRepository(
    PostgresRepositoryAdapter,
    SQLiteCompleteAccountPortfolioRiskRepository,
):
    """PostgreSQL implementation of complete-account Portfolio/Risk."""


class PostgresRiskRouteRepository(
    PostgresRepositoryAdapter,
    SQLiteRiskRouteRepository,
):
    """PostgreSQL implementation of RiskRouteRepository."""


__all__ = [
    "PostgresCompleteAccountPortfolioRiskRepository",
    "PostgresPortfolioDecisionRepository",
    "PostgresRiskRouteRepository",
]
