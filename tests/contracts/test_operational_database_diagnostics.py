from __future__ import annotations

from uuid import uuid4

import pytest
import psycopg

from market_regime_alpha.bootstrap import TargetSettings, bootstrap_application, bootstrap_database
from market_regime_alpha.infrastructure.postgres.operational_diagnostics import PostgresOperationalDiagnostics
from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.postgres.backtest_uow import PostgresBacktestUnitOfWorkProvider
from market_regime_alpha.infrastructure.postgres.evidence_backup import _table_hashes
from market_regime_alpha.research_qualification.application.backtests import BacktestApplication
from tests.contracts.research_qualification import test_backtest_postgres as backtests


@pytest.fixture
def backtest_stack(target_database_url, tmp_path, request):
    return backtests.backtest_stack.__wrapped__(target_database_url, tmp_path, request)


@pytest.mark.parametrize("changed", ("name", "oid", "cluster_identity"))
def test_diagnostics_refuses_wrong_exact_scope_before_campaign_reads(target_database_url, tmp_path, changed):
    settings = TargetSettings(target_database_url, tmp_path / "artifacts")
    bootstrap_database(settings)
    with bootstrap_application(settings) as app:
        identity = app.evidence.inventory()["database"]
    identity[changed] = identity[changed] + 1 if changed == "oid" else "wrong-scope"
    pool = TargetPostgresPool(target_database_url, min_size=0, max_size=1)
    try:
        with pytest.raises(ValueError, match="database identity"):
            PostgresOperationalDiagnostics(pool).inspect(
                uuid4(), expected_database_name=identity["name"],
                expected_database_oid=identity["oid"],
                expected_cluster_identity=identity["cluster_identity"],
            )
    finally:
        pool.close()


def test_diagnostics_measures_owner_sql_without_writes_or_success_attribution(backtest_stack):
    stack = backtest_stack
    specification = backtests._current_specification(stack)
    BacktestApplication(PostgresBacktestUnitOfWorkProvider(stack.pool), id_factory=uuid4).predeclare(
        specification, backtests._legacy._context("diagnostic-predeclare")
    )
    with stack.pool.connection(read_only=True) as connection:
        before = _table_hashes(connection)
        identity = connection.execute("SELECT current_database(), oid, (pg_control_system()).system_identifier::text FROM pg_database WHERE datname=current_database()").fetchone()
    result = PostgresOperationalDiagnostics(stack.pool).inspect(
        specification.exploratory_backtest_run_id,
        expected_database_name=identity[0], expected_database_oid=identity[1],
        expected_cluster_identity=identity[2], repetitions=2,
    )
    assert result["root_cause"] == "UNPROVEN"
    assert result["owner_reconciliation"] == "NOT_PERFORMED"
    assert result["read_only"] is True
    assert result["status"] == "OBSERVED"
    assert result["backtest_run_id"] == str(specification.exploratory_backtest_run_id)
    assert result["run_scope_before"] == result["run_scope_after"]
    plans = result["queries"]
    assert len(plans) == 6
    for item in plans:
        assert item["source_file"].startswith("infrastructure/postgres/queries/")
        assert item["sql"] and len(item["statement_sha256"]) == 64
        if item["query_name"] == "fold_metric_states":
            assert item["status"] == "MEASURED"
            assert item["plan"]["Plan"]["Actual Rows"] == 0
        else:
            assert item["status"] == "NO_BOUND_INPUTS"
            assert item["plan"] is None
    for phase in ("before", "after"):
        assert result[phase]["settings"]["statement_timeout"] == "30s"
        assert result[phase]["settings"]["transaction_read_only"] == "on"
        assert result[phase]["setting_units"]["shared_buffers"] == "8kB"
        assert result[phase]["cluster_activity"]
        assert result[phase]["activity"]
        assert result[phase]["database_statistics"]["temp_bytes"] >= 0
        assert result[phase]["table_statistics"]
    with stack.pool.connection(read_only=True) as connection:
        assert _table_hashes(connection) == before


@pytest.mark.parametrize("repetitions", (0, 4, True, 1.5))
def test_diagnostics_rejects_unbounded_or_non_integer_repetition_before_connecting(repetitions):
    pool = TargetPostgresPool("postgresql://invalid.invalid/db", min_size=0, max_size=1)
    try:
        with pytest.raises(ValueError, match="repetitions"):
            PostgresOperationalDiagnostics(pool).inspect(
                uuid4(), expected_database_name="scope", expected_database_oid=1,
                expected_cluster_identity="1", repetitions=repetitions,
            )
    finally:
        pool.close()


def test_unknown_run_does_not_become_an_empty_success(target_database_url, tmp_path):
    settings = TargetSettings(target_database_url, tmp_path / "artifacts")
    bootstrap_database(settings)
    with bootstrap_application(settings) as app:
        identity = app.evidence.inventory()["database"]
    pool = TargetPostgresPool(target_database_url, min_size=0, max_size=1)
    try:
        with pytest.raises(ValueError, match="run does not exist"):
            PostgresOperationalDiagnostics(pool).inspect(
                uuid4(), expected_database_name=identity["name"], expected_database_oid=identity["oid"],
                expected_cluster_identity=identity["cluster_identity"],
            )
    finally:
        pool.close()


def test_cancelled_read_is_recorded_without_timeout_change_or_blind_retry(backtest_stack, monkeypatch):
    stack = backtest_stack
    specification = backtests._current_specification(stack)
    BacktestApplication(PostgresBacktestUnitOfWorkProvider(stack.pool), id_factory=uuid4).predeclare(
        specification, backtests._legacy._context("diagnostic-cancel-predeclare")
    )
    with stack.pool.connection(read_only=True) as connection:
        before = _table_hashes(connection)
        identity = connection.execute("SELECT current_database(), oid, (pg_control_system()).system_identifier::text FROM pg_database WHERE datname=current_database()").fetchone()
    original = psycopg.Cursor.execute
    calls = []

    def cancel_first(cursor, query, params=None, *args, **kwargs):
        if str(query).startswith("EXPLAIN "):
            calls.append(query)
            if len(calls) == 1:
                raise psycopg.errors.QueryCanceled("injected diagnostic read cancellation")
        return original(cursor, query, params, *args, **kwargs)

    monkeypatch.setattr(psycopg.Cursor, "execute", cancel_first)
    result = PostgresOperationalDiagnostics(stack.pool).inspect(
        specification.exploratory_backtest_run_id,
        expected_database_name=identity[0], expected_database_oid=identity[1],
        expected_cluster_identity=identity[2], repetitions=2,
    )
    assert result["status"] == "INCOMPLETE"
    assert result["root_cause"] == "UNPROVEN"
    assert len(calls) == 2
    assert result["queries"][0]["status"] == "FAILED"
    assert result["queries"][0]["sqlstate"] == "57014"
    assert result["queries"][0]["plan"] is None
    assert result["queries"][3]["status"] == "MEASURED"
    assert result["after"]["settings"]["statement_timeout"] == "30s"
    with stack.pool.connection(read_only=True) as connection:
        assert _table_hashes(connection) == before
