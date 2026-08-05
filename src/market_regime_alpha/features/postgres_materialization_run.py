"""PostgreSQL Feature Materialization run authority."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta
import json
import sqlite3
from typing import Callable, Iterator, cast

from market_regime_alpha.features.materialization_run import (
    ClaimedFeatureMaterializationTask,
    DEFAULT_FEATURE_TASK_LEASE,
    FeatureMaterializationTaskStatus,
    SQLiteFeatureMaterializationRunRepository,
)
from market_regime_alpha.features.v2_contracts import FeatureMaterializationReceipt
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.postgres.dbapi import (
    PostgresDBAPIConnection,
)
from market_regime_alpha.persistence.postgres.migrator import PostgresMigrator
from market_regime_alpha.persistence.postgres.schema import (
    verify_postgres_authority_schema,
)


Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    from datetime import timezone

    return datetime.now(timezone.utc)


class PostgresFeatureMaterializationRunRepository(SQLiteFeatureMaterializationRunRepository):
    """Feature run/task leases backed by PostgreSQL fencing constraints."""

    def __init__(
        self,
        factory: PostgresConnectionFactory,
        *,
        clock: Clock = _utc_now,
        lease_duration: timedelta = DEFAULT_FEATURE_TASK_LEASE,
    ) -> None:
        if not isinstance(factory, PostgresConnectionFactory):
            raise TypeError("factory must be a PostgresConnectionFactory")
        if not callable(clock):
            raise TypeError("clock must be callable")
        if not isinstance(lease_duration, timedelta) or lease_duration <= timedelta(0):
            raise ValueError("lease_duration must be positive")
        self._postgres_factory = factory
        self._clock = clock
        self._lease_duration = lease_duration
        PostgresMigrator().apply_all(factory)
        with factory.connection(read_only=True) as connection:
            verify_postgres_authority_schema(connection)

    def _connect(self) -> sqlite3.Connection:
        bridge = PostgresDBAPIConnection.acquire(self._postgres_factory)
        return cast(sqlite3.Connection, bridge)

    def claim_batch(
        self,
        *,
        run_id: int,
        limit: int,
        stale_after: timedelta | None = None,
    ) -> tuple[ClaimedFeatureMaterializationTask, ...]:
        """Claim distinct PostgreSQL queue rows without blocking other workers."""

        if isinstance(limit, bool) or not 1 <= limit <= 256:
            raise ValueError("claim batch limit must be between one and 256")
        if stale_after is not None and stale_after <= timedelta(0):
            raise ValueError("stale_after must be positive")
        with self._postgres_immediate() as connection:
            self._recover_expired(
                connection,
                run_id=run_id,
                stale_after=stale_after,
            )
            rows = tuple(
                connection.execute(
                    "SELECT task_key, symbol, feature_id, timeframe, version, "
                    "claim_epoch FROM feature_materialization_task "
                    "WHERE run_id = ? AND status IN (?, ?) "
                    "ORDER BY task_key LIMIT ? FOR UPDATE SKIP LOCKED",
                    (
                        run_id,
                        FeatureMaterializationTaskStatus.PENDING.value,
                        FeatureMaterializationTaskStatus.FAILED.value,
                        limit,
                    ),
                )
            )
            return tuple(self._claim_row(connection, run_id=run_id, row=row) for row in rows)

    @contextmanager
    def _postgres_immediate(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("BEGIN")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def receipts(self) -> tuple[FeatureMaterializationReceipt, ...]:
        """Return immutable child receipts for network-free replay lookup."""

        with self._connect() as connection:
            rows = connection.execute("SELECT receipt_json FROM feature_materialization_receipt ORDER BY run_id")
            receipts = []
            for row in rows:
                payload = json.loads(str(row["receipt_json"]))
                if not isinstance(payload, dict):
                    raise ValueError("stored Feature materialization receipt is invalid")
                receipts.append(FeatureMaterializationReceipt.from_canonical_dict(payload))
            return tuple(receipts)


__all__ = ["PostgresFeatureMaterializationRunRepository"]
