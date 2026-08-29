"""Stable PostgreSQL Market/PIT write adapter export."""

from market_regime_alpha.infrastructure.postgres.repositories._market_normalization_repository import (
    _MarketNormalizationRepository,
)


class PostgresMarketRepository(_MarketNormalizationRepository):
    """Aggregate writes only; transaction ownership belongs to Market UoW."""


__all__ = ["PostgresMarketRepository"]
