"""Session lock and short read-only SQL for the prospective process guard."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterator, cast

import psycopg
from psycopg.rows import dict_row

from market_regime_alpha.infrastructure.postgres.queries.evidence import read_evidence_snapshot


class PostgresProspectiveOperationSession:
    def __init__(self, connection: psycopg.Connection[Any]) -> None:
        self.connection = connection

    def snapshot(self) -> dict[str, Any]:
        with self.connection.transaction():
            self.connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            return read_evidence_snapshot(self.connection)

    def require_supervisor_lock(self, series_code: str) -> None:
        if self.connection.closed:
            raise ValueError("OPERATION_SUPERVISOR_CONNECTION_LOST")
        try:
            row = self.connection.execute(
                """WITH intent AS (SELECT hashtextextended(%s,0) AS key)
                   SELECT EXISTS (SELECT 1 FROM pg_locks, intent
                     WHERE pid=pg_backend_pid() AND locktype='advisory' AND granted
                       AND classid::bigint=((intent.key >> 32) & 4294967295)
                       AND objid::bigint=(intent.key & 4294967295) AND objsubid=1)""",
                ("operator:prospective-series:" + series_code,),
            ).fetchone()
        except psycopg.Error as exc:
            raise ValueError("OPERATION_SUPERVISOR_CONNECTION_LOST") from exc
        if row != (True,):
            raise ValueError("OPERATION_SUPERVISOR_LOCK_LOST")

    def has_conflicting_attempts(self, series_code: str) -> bool:
        row = self.connection.execute(
            """SELECT count(*) FROM mra.runtime_attempt AS attempt
               JOIN mra.runtime_step AS step USING (step_id)
               JOIN mra.runtime_run AS run ON run.run_id=step.run_id
               WHERE attempt.state IN ('CLAIMED','RUNNING')
                 AND (attempt.lease_until > clock_timestamp() OR NOT EXISTS (
                   SELECT 1 FROM mra.prospective_archive_generation AS generation
                   WHERE generation.series_code=%s
                     AND run.fire_key LIKE 'archive:' || generation.market_archive_id::text || ':%%'
                 ))""", (series_code,),
        ).fetchone()
        return row is None or bool(row[0])

    def clock(self) -> datetime:
        row = self.connection.execute("SELECT clock_timestamp()").fetchone()
        if row is None:
            raise ValueError("OPERATION_DATABASE_CLOCK_UNAVAILABLE")
        return cast(datetime, row[0])

    def generations(self, series_code: str) -> list[dict[str, Any]]:
        with self.connection.transaction(), self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute("SET TRANSACTION READ ONLY")
            return cursor.execute(
                "SELECT * FROM mra.prospective_archive_generation WHERE series_code=%s ORDER BY generation",
                (series_code,),
            ).fetchall()


@contextmanager
def prospective_operation_session(
    database_url: str, *, database_name: str, database_oid: int,
    cluster_identity: str, series_code: str,
) -> Iterator[PostgresProspectiveOperationSession]:
    """Bind one advisory lock to one session without spanning a transaction."""
    with psycopg.connect(database_url, autocommit=True,
                         application_name="mra-prospective-supervisor") as connection:
        row = connection.execute(
            "SELECT current_database(), oid::bigint, (pg_control_system()).system_identifier::text "
            "FROM pg_database WHERE datname=current_database()",
        ).fetchone()
        if row != (database_name, database_oid, cluster_identity):
            raise ValueError("OPERATION_DATABASE_IDENTITY_MISMATCH")
        key = "operator:prospective-series:" + series_code
        locked = connection.execute("SELECT pg_try_advisory_lock(hashtextextended(%s,0))", (key,)).fetchone()
        if locked != (True,):
            raise ValueError("OPERATION_DUPLICATE_SUPERVISOR")
        try:
            yield PostgresProspectiveOperationSession(connection)
        finally:
            if not connection.closed:
                connection.execute("SELECT pg_advisory_unlock(hashtextextended(%s,0))", (key,))
