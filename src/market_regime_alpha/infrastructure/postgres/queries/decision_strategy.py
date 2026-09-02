"""Read-only exact Strategy request lookup."""

from __future__ import annotations

from uuid import UUID

from market_regime_alpha.decision_support.ports import StrategyVersionRecord
from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.postgres.repositories.decision_strategy import (
    _record,
    _record_row,
)


class PostgresStrategyQueryProvider:
    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool

    def find_request(
        self,
        strategy_id: UUID,
        request_identity: str,
    ) -> StrategyVersionRecord | None:
        with self._pool.connection(read_only=True) as connection:
            row = _record_row(
                connection,
                "version.strategy_id = %s AND version.request_identity = %s",
                (strategy_id, request_identity),
                lock=False,
            )
        return None if row is None else _record(row)


__all__ = ["PostgresStrategyQueryProvider"]
