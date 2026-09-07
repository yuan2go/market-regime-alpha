"""Bounded, read-only PostgreSQL observations; never a root-cause verdict."""

from __future__ import annotations

from hashlib import sha256
from time import perf_counter
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.postgres.queries.backtest_execution import (
    _FOLD_METRIC_STATES_SQL,
    _RUNTIME_BINDINGS_SQL,
)
from market_regime_alpha.infrastructure.postgres.queries.outcome_verification import _OUTCOME_INSPECTION_SQL


_IDENTITY_SQL = """
    SELECT current_database() AS name, oid::bigint AS oid,
           pg_get_userbyid(datdba) AS owner,
           (pg_control_system()).system_identifier::text AS cluster_identity,
           current_setting('server_version') AS server_version
    FROM pg_database WHERE datname = current_database()
"""
_RUN_SCOPE_SQL = """
    SELECT root.exploratory_backtest_run_id::text,
           root.code_content_sha256, root.config_artifact_id::text,
           root.config_content_sha256, root.current_specification_sha256,
           (SELECT count(*) FROM mra.backtest_runtime_binding b
            WHERE b.exploratory_backtest_run_id=root.exploratory_backtest_run_id) AS runtime_binding_count,
           (SELECT count(*) FROM mra.exploratory_backtest_dataset d
            WHERE d.exploratory_backtest_run_id=root.exploratory_backtest_run_id) AS dataset_count,
           (SELECT count(*) FROM mra.backtest_evaluation_execution e
            WHERE e.exploratory_backtest_run_id=root.exploratory_backtest_run_id) AS evaluation_count
    FROM mra.exploratory_backtest_run root WHERE exploratory_backtest_run_id=%s
"""


def _snapshot(cursor: Any) -> dict[str, Any]:
    """Counters have database/cluster scope, never per-query attribution."""
    observed = cursor.execute("SELECT clock_timestamp()::text AS observed_at, pg_backend_pid() AS backend_pid").fetchone()
    settings = cursor.execute("""
        SELECT name, setting, unit FROM pg_settings
        WHERE name = ANY(%s) ORDER BY name
    """, ([
        "server_version", "shared_buffers", "work_mem", "effective_cache_size",
        "max_connections", "track_io_timing", "track_wal_io_timing",
        "track_activity_query_size", "default_statistics_target",
        "random_page_cost", "seq_page_cost", "jit", "fsync", "synchronous_commit",
        "full_page_writes",
    ],)).fetchall()
    session = cursor.execute("""
        SELECT current_setting('statement_timeout') AS statement_timeout,
               current_setting('lock_timeout') AS lock_timeout,
               current_setting('transaction_read_only') AS transaction_read_only
    """).fetchone()
    database = cursor.execute("""
        SELECT to_jsonb(s) AS value FROM pg_stat_database s
        WHERE datname=current_database()
    """).fetchone()
    io = cursor.execute("SELECT to_jsonb(s) AS value FROM pg_stat_io s ORDER BY backend_type, object, context").fetchall()
    activity = cursor.execute("""
        SELECT pid, backend_type, state, wait_event_type, wait_event,
               extract(epoch FROM clock_timestamp()-backend_start)::float8 AS connection_seconds,
               extract(epoch FROM clock_timestamp()-xact_start)::float8 AS transaction_seconds,
               extract(epoch FROM clock_timestamp()-query_start)::float8 AS query_seconds,
               pg_blocking_pids(pid) AS blocking_pids, query_id,
               md5(query) AS query_fingerprint, pid=pg_backend_pid() AS diagnostic_connection
        FROM pg_stat_activity WHERE datname=current_database() ORDER BY pid
    """).fetchall()
    cluster_activity = cursor.execute("""
        SELECT datname, backend_type, state, wait_event_type, wait_event, count(*) AS count
        FROM pg_stat_activity GROUP BY datname, backend_type, state, wait_event_type, wait_event
        ORDER BY datname, backend_type, state, wait_event_type, wait_event
    """).fetchall()
    locks = cursor.execute("""
        SELECT locktype, mode, granted, count(*) AS count
        FROM pg_locks WHERE database=(SELECT oid FROM pg_database WHERE datname=current_database())
        GROUP BY locktype, mode, granted ORDER BY locktype, mode, granted
    """).fetchall()
    tables = cursor.execute("""
        SELECT s.relname, s.n_live_tup, s.n_dead_tup,
               s.seq_scan, s.seq_tup_read, s.idx_scan, s.idx_tup_fetch,
               s.last_analyze::text, s.last_autoanalyze::text,
               io.heap_blks_read, io.heap_blks_hit, io.idx_blks_read, io.idx_blks_hit,
               pg_table_size(s.relid) AS table_bytes,
               pg_indexes_size(s.relid) AS index_bytes
        FROM pg_stat_user_tables s JOIN pg_statio_user_tables io USING(relid)
        WHERE s.schemaname='mra' AND s.relname = ANY(%s)
        ORDER BY s.relname
    """, ([
        "exploratory_backtest_run", "backtest_runtime_binding", "runtime_run", "runtime_step",
        "runtime_attempt", "market_target_outcome_revision", "market_target_outcome_source",
        "market_target_outcome_metric", "evaluation_run", "evaluation_observation",
        "evaluation_metric", "evaluation_backtest_arm_source", "decision_target_commitment",
    ],)).fetchall()
    assert observed is not None and session is not None and database is not None
    return {
        **observed, "settings": {**{r["name"]: r["setting"] for r in settings}, **session},
        "setting_units": {r["name"]: r["unit"] for r in settings},
        "database_statistics": database["value"], "cluster_io_statistics": [r["value"] for r in io],
        "activity": activity, "cluster_activity": cluster_activity, "locks": locks, "table_statistics": tables,
    }


class PostgresOperationalDiagnostics:
    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool

    def inspect(
        self, run_id: UUID, *, expected_database_name: str,
        expected_database_oid: int, expected_cluster_identity: str,
        repetitions: int = 2,
    ) -> dict[str, Any]:
        if type(repetitions) is not int or not 1 <= repetitions <= 3:
            raise ValueError("diagnostic repetitions must be an integer from 1 to 3")
        started = perf_counter()
        with self._pool.connection(read_only=True) as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                identity = cursor.execute(_IDENTITY_SQL).fetchone()
                if identity is None or (
                    identity["name"], identity["oid"], identity["cluster_identity"]
                ) != (expected_database_name, expected_database_oid, expected_cluster_identity):
                    raise ValueError("diagnostic database identity differs from exact operator intent")
                scope_before = cursor.execute(_RUN_SCOPE_SQL, (run_id,)).fetchone()
                if scope_before is None:
                    raise ValueError("diagnostic Backtest run does not exist in the explicit database scope")
                schema = cursor.execute("""
                    SELECT epoch_name, release_state, baseline_checksum, catalog_checksum,
                           seed_checksum, reference_vocabulary_checksum FROM mra.schema_epoch
                """).fetchone()
                before = _snapshot(cursor)
                bindings = [r["backtest_runtime_binding_id"] for r in cursor.execute("""
                    SELECT backtest_runtime_binding_id FROM mra.backtest_runtime_binding
                    WHERE exploratory_backtest_run_id=%s ORDER BY backtest_runtime_binding_id LIMIT 8
                """, (run_id,)).fetchall()]
                outcomes = [r["market_target_outcome_revision_id"] for r in cursor.execute("""
                    SELECT o.market_target_outcome_revision_id FROM mra.market_target_outcome_revision o
                    JOIN mra.decision_target_commitment c USING(commitment_id)
                    JOIN mra.exploratory_retrospective_decision_run d USING(decision_run_id)
                    WHERE d.exploratory_backtest_run_id=%s
                    ORDER BY o.market_target_outcome_revision_id LIMIT 8
                """, (run_id,)).fetchall()]
        queries: list[dict[str, Any]] = []
        for repetition in range(1, repetitions + 1):
            for name, source, statement, params, available in (
                ("fold_metric_states", "backtest_execution.py", _FOLD_METRIC_STATES_SQL, (run_id,), True),
                ("runtime_binding_batch", "backtest_execution.py", _RUNTIME_BINDINGS_SQL, (run_id, bindings), bool(bindings)),
                ("outcome_owner_batch", "outcome_verification.py", _OUTCOME_INSPECTION_SQL, (outcomes,), bool(outcomes)),
            ):
                item: dict[str, Any] = {
                    "query_name": name, "repetition": repetition, "source_file": "infrastructure/postgres/queries/" + source,
                    "sql": statement, "statement_sha256": sha256(statement.encode()).hexdigest(),
                    "parameters": [[str(value) for value in p] if isinstance(p, list) else str(p) for p in params],
                    "status": "NO_BOUND_INPUTS", "plan": None,
                }
                if available:
                    measured = perf_counter()
                    try:
                        with self._pool.connection(read_only=True) as connection:
                            item["backend_pid"] = connection.info.backend_pid
                            row = connection.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + statement, params).fetchone()
                            assert row is not None
                            item.update(status="MEASURED", plan=row[0][0])
                    except psycopg.Error as exc:
                        # The pool rolls back this read transaction. No blind retry;
                        # a subsequent declared repetition is a distinct observation.
                        item.update(status="FAILED", error_type=type(exc).__name__, sqlstate=exc.sqlstate)
                    item["elapsed_seconds"] = perf_counter() - measured
                queries.append(item)
        with self._pool.connection(read_only=True) as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                if cursor.execute(_IDENTITY_SQL).fetchone() != identity:
                    raise ValueError("diagnostic database identity changed during observation")
                after = _snapshot(cursor)
                scope_after = cursor.execute(_RUN_SCOPE_SQL, (run_id,)).fetchone()
        return {
            "database": identity, "schema": schema, "root_cause": "UNPROVEN",
            "authority": "NON_AUTHORITATIVE_OPERATIONAL_DIAGNOSTIC", "owner_reconciliation": "NOT_PERFORMED",
            "read_only": True, "backtest_run_id": str(run_id),
            "status": "INCOMPLETE" if any(q["status"] == "FAILED" for q in queries) else "OBSERVED",
            "run_scope_before": scope_before, "run_scope_after": scope_after,
            "run_scope_changed": scope_before != scope_after, "before": before, "after": after,
            "queries": queries, "elapsed_seconds": perf_counter() - started,
            "limits": [
                "FIRST_LEXICAL_EIGHT_BINDINGS_AND_OUTCOMES_ONLY",
                "READ_ONLY_TRANSACTIONS_WITH_EXISTING_POOL_TIMEOUTS",
                "NO_CACHE_RESET_OR_COLD_CACHE_CLAIM",
                "DATABASE_AND_CLUSTER_COUNTERS_INCLUDE_OTHER_CONNECTIONS",
                "NO_HISTORICAL_LOCK_OR_IO_ATTRIBUTION",
                "QUERY_FINGERPRINTS_ONLY_FOR_OTHER_SESSIONS",
                "NO_BUSINESS_RECONCILIATION_OR_RUN_SUCCESS_ADMISSION",
            ],
        }
