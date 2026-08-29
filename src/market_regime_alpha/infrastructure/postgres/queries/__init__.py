"""Target PostgreSQL read adapters."""

from market_regime_alpha.infrastructure.postgres.queries.market import (
    PostgresMarketQueries,
    PostgresMarketQueryProvider,
)
from market_regime_alpha.infrastructure.postgres.queries.selection_market import (
    PostgresSelectionMarketQueries,
)

__all__ = [
    "PostgresMarketQueries",
    "PostgresMarketQueryProvider",
    "PostgresSelectionMarketQueries",
]
