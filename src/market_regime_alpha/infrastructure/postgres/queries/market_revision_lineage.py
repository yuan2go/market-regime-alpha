"""Read-only exact Market revision heads for archive normalization planning."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.market.domain.vocabulary import BarTimeframe, PriceBasis
from market_regime_alpha.market.ports.revision_lineage import MarketBarRevisionHead
from market_regime_alpha.shared.identity import InstrumentId, TradingSessionId


class PostgresMarketRevisionLineageReadPort:
    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool

    def market_bar_head(
        self,
        *,
        provider_product_id: UUID,
        instrument_id: InstrumentId,
        session_id: TradingSessionId,
        timeframe: BarTimeframe,
        price_basis: PriceBasis,
        event_start: datetime,
        event_end: datetime,
    ) -> MarketBarRevisionHead | None:
        with self._pool.connection(read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT candidate.bar_revision_id, candidate.revision
                FROM mra.market_bar_revision AS candidate
                WHERE candidate.provider_product_id = %s
                  AND candidate.instrument_id = %s
                  AND candidate.session_id = %s
                  AND candidate.timeframe = %s
                  AND candidate.price_basis = %s
                  AND candidate.event_start = %s
                  AND candidate.event_end = %s
                  AND NOT EXISTS (
                      SELECT 1
                      FROM mra.market_bar_revision AS successor
                      WHERE successor.supersedes_revision_id =
                            candidate.bar_revision_id
                  )
                """,
                (
                    provider_product_id,
                    instrument_id.value,
                    session_id.value,
                    timeframe.value,
                    price_basis.value,
                    event_start,
                    event_end,
                ),
            ).fetchall()
        if len(rows) > 1:
            raise ValueError("Market bar revision lineage has multiple leaves")
        if not rows:
            return None
        return MarketBarRevisionHead(
            bar_revision_id=UUID(str(rows[0][0])),
            revision=int(rows[0][1]),
        )


__all__ = ["PostgresMarketRevisionLineageReadPort"]
