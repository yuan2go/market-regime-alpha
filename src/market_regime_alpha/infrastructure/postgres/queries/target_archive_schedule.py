"""Exact registered Target schedule projection for Market archive planning."""

from __future__ import annotations

from uuid import UUID

from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.market.domain import TargetArchiveCheckpoint
from market_regime_alpha.market.ports.target_archive_schedule import TargetArchiveContract
from market_regime_alpha.runtime.errors import RuntimeNotFoundError


class PostgresTargetArchiveScheduleReadPort:
    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool

    def exact_contract(self, target_definition_id: UUID) -> TargetArchiveContract:
        with self._pool.connection(read_only=True) as connection:
            root = connection.execute(
                """
                SELECT version, content_sha256, checkpoint_count
                FROM mra.target_definition
                WHERE target_definition_id = %s
                  AND registration_status = 'REGISTERED'
                """,
                (target_definition_id,),
            ).fetchone()
            if root is None:
                raise RuntimeNotFoundError(
                    f"registered TargetDefinition {target_definition_id} does not exist"
                )
            rows = connection.execute(
                """
                SELECT target_checkpoint_id, ordinal, checkpoint_role,
                       session_offset, local_time, timezone_name
                FROM mra.target_checkpoint
                WHERE target_definition_id = %s
                ORDER BY ordinal, target_checkpoint_id
                """,
                (target_definition_id,),
            ).fetchall()
        checkpoints = tuple(
            TargetArchiveCheckpoint(
                target_checkpoint_id=UUID(str(row[0])),
                ordinal=int(row[1]),
                checkpoint_role=str(row[2]),
                session_offset=int(row[3]),
                local_time=row[4],
                timezone_name=str(row[5]),
            )
            for row in rows
        )
        if len(checkpoints) != int(root[2]):
            raise RuntimeError("Target checkpoint roster is incomplete")
        return TargetArchiveContract(
            target_definition_id=target_definition_id,
            version=int(root[0]),
            content_sha256=str(root[1]),
            checkpoints=checkpoints,
        )


__all__ = ["PostgresTargetArchiveScheduleReadPort"]
