"""Consistent, credential-free operational inventory from canonical rows."""

from __future__ import annotations

from typing import Any

import psycopg
from psycopg.rows import dict_row

from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool


def read_evidence_snapshot(connection: psycopg.Connection[Any]) -> dict[str, Any]:
    with connection.cursor(row_factory=dict_row) as cursor:
        database = cursor.execute("""
            SELECT current_database() AS name, oid::bigint AS oid,
                   pg_get_userbyid(datdba) AS owner,
                   (pg_control_system()).system_identifier::text AS cluster_identity,
                   current_setting('server_version') AS server_version
            FROM pg_database WHERE datname = current_database()
        """).fetchone()
        schema = cursor.execute("""
            SELECT epoch_name AS epoch, release_state, baseline_checksum,
                   catalog_checksum, seed_checksum, reference_vocabulary_checksum
            FROM mra.schema_epoch
        """).fetchone()
        artifacts = cursor.execute("""
            SELECT artifact_id::text, content_sha256, size_bytes, locator
            FROM mra.artifact ORDER BY artifact_id
        """).fetchall()
        archives = cursor.execute("""
            SELECT market_archive_id::text, archive_code, lane, evidence_class,
                   content_sha256, archive_start_at::text
            FROM mra.market_archive ORDER BY market_archive_id
        """).fetchall()
        generations = cursor.execute("""
            SELECT market_archive_id::text, series_code, generation,
                   predecessor_market_archive_id::text, decision_session_id::text,
                   content_sha256, registered_at::text
            FROM mra.prospective_archive_generation ORDER BY series_code, generation
        """).fetchall()
        state = cursor.execute("""
            SELECT clock_timestamp()::text AS observed_at,
                   (SELECT count(*) FROM mra.runtime_attempt
                    WHERE state IN ('CLAIMED', 'RUNNING')) AS active_attempts,
                   (SELECT count(*) FROM mra.prospective_archive_planning_gap) AS planning_gaps,
                   (SELECT max(verified_at)::text FROM mra.artifact_verification) AS latest_authority_artifact_verification_at
        """).fetchone()
        backtests = cursor.execute(
            "SELECT exploratory_backtest_run_id::text FROM mra.exploratory_backtest_run ORDER BY exploratory_backtest_run_id"
        ).fetchall()
    assert database is not None and schema is not None and state is not None
    return {
        "database": database,
        "schema": schema,
        "artifacts": artifacts,
        "backtests": backtests,
        "archives": archives,
        "prospective_generations": generations,
        **state,
    }


class PostgresEvidenceSnapshotPort:
    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool

    def snapshot(self) -> dict[str, Any]:
        with self._pool.connection(read_only=True) as connection:
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            return read_evidence_snapshot(connection)


def read_service_restart_state(connection: psycopg.Connection[Any]) -> dict[str, Any]:
    """Inspect current fences/effects without recovering or reopening any Run."""
    with connection.transaction():
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        with connection.cursor(row_factory=dict_row) as cursor:
            observed = cursor.execute("SELECT clock_timestamp() AS observed_at").fetchone()
            attempts = cursor.execute("""
                SELECT attempt.attempt_id, attempt.state, attempt.fence_token,
                       attempt.lease_until, attempt.lease_until > statement_timestamp() AS lease_live,
                       step.step_id, step.run_id, step.state AS step_state,
                       step.current_fence, step.current_attempt_id, step.external_effect_class,
                       run.state AS run_state, run.code_sha, run.config_hash
                FROM mra.runtime_attempt attempt
                JOIN mra.runtime_step step USING(step_id)
                JOIN mra.runtime_run run USING(run_id)
                WHERE attempt.state IN ('CLAIMED','RUNNING','RECONCILIATION_REQUIRED')
                ORDER BY attempt.attempt_id
            """).fetchall()
            waiting = cursor.execute("""
                SELECT run.run_id, run.state AS run_state, run.code_sha, run.config_hash,
                       step.step_id, step.state AS step_state, step.current_fence,
                       step.current_attempt_id, step.external_effect_class,
                       step.terminal_reason_code
                FROM mra.runtime_run run
                LEFT JOIN mra.runtime_step step USING(run_id)
                WHERE run.state='WAITING' OR step.state='WAITING'
                ORDER BY run.run_id, step.ordinal
            """).fetchall()
            terminals = cursor.execute("""
                SELECT state, count(*) AS count FROM mra.runtime_attempt
                WHERE state IN ('SUCCEEDED','FAILED_TERMINAL','FAILED_RETRYABLE','ABANDONED')
                GROUP BY state ORDER BY state
            """).fetchall()
    assert observed is not None
    return {**observed, "unresolved_attempts": attempts, "waiting_work": waiting,
            "historical_attempt_counts": terminals, "business_writes": 0}
