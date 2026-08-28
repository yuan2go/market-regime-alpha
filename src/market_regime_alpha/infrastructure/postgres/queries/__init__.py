"""Target PostgreSQL read adapters."""

from market_regime_alpha.infrastructure.postgres.queries.market import (
    PostgresMarketQueries,
    PostgresMarketQueryProvider,
)

__all__ = ["PostgresMarketQueries", "PostgresMarketQueryProvider"]
