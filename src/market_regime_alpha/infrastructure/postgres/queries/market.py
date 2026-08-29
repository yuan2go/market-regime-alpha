"""Stable PostgreSQL Market/PIT query adapter exports."""

from __future__ import annotations

from uuid import UUID

from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.postgres.queries._market_actions import (
    _CorporateActionQueries,
)
from market_regime_alpha.infrastructure.postgres.queries._market_bars import (
    _BarSessionQueries,
)
from market_regime_alpha.infrastructure.postgres.queries._market_facts import (
    _InstrumentFactQueries,
)
from market_regime_alpha.infrastructure.postgres.queries._market_gaps import (
    _GapQueries,
)
from market_regime_alpha.infrastructure.postgres.queries._market_reference import (
    _ReferenceQueries,
)


class PostgresMarketQueries(
    _BarSessionQueries,
    _ReferenceQueries,
    _InstrumentFactQueries,
    _CorporateActionQueries,
    _GapQueries,
):
    """Generic exact/as-of queries bound to one owner ProviderProduct."""


class PostgresMarketQueryProvider:
    """Explicit query composition boundary bound to one ProviderProduct."""

    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool

    def for_provider_product(
        self,
        provider_product_id: UUID,
    ) -> PostgresMarketQueries:
        return PostgresMarketQueries(
            self._pool,
            provider_product_id=provider_product_id,
        )


__all__ = ["PostgresMarketQueries", "PostgresMarketQueryProvider"]
