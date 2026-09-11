"""Full daily owner commands authenticate as a restricted login; fixture setup stays separate."""

from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from uuid import uuid4
import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.interfaces.daily_research import DailyResearchOperations
from tests.contracts.research_qualification.test_daily_vertical_postgres import (
    test_completed_model_is_consumed_without_backtest_and_publication_is_replayable as vertical,
    _isolated_calendar_handoff,  # noqa: F401
)

from market_regime_alpha.infrastructure.postgres.runtime_privileges import WRITE_TABLES, REFERENCE_LOCKS, inspect_runtime_principal


def test_restricted_runtime_login_completes_prediction_maturity_recovery_and_replay(
    target_database_url, tmp_path, monkeypatch, record_property
):
    role = "daily_runtime_" + uuid4().hex
    password = uuid4().hex
    active = ContextVar("restricted_daily_command", default=False)
    with psycopg.connect(target_database_url) as admin:
        admin.execute(sql.SQL("REVOKE TEMP ON DATABASE {} FROM PUBLIC").format(sql.Identifier(admin.info.dbname)))
        admin.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(sql.Identifier(role), sql.Literal(password)))
    runtime_pool = TargetPostgresPool(make_conninfo(target_database_url, user=role, password=password))
    original_connection = TargetPostgresPool.connection
    initialized = False

    @contextmanager
    def restricted_connection(pool, *, read_only=False):
        nonlocal initialized
        if active.get() and pool is not runtime_pool:
            if not initialized:
                with psycopg.connect(target_database_url) as admin:
                    admin.execute(sql.SQL("GRANT USAGE ON SCHEMA mra TO {}").format(sql.Identifier(role)))
                    admin.execute(sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA mra TO {}").format(sql.Identifier(role)))
                    admin.execute(sql.SQL("GRANT EXECUTE ON FUNCTION pg_catalog.pg_control_system() TO {}").format(sql.Identifier(role)))
                    for table in WRITE_TABLES:
                        admin.execute(sql.SQL("GRANT INSERT, UPDATE ON mra.{} TO {}").format(sql.Identifier(table), sql.Identifier(role)))
                    for table, column in REFERENCE_LOCKS.items():
                        admin.execute(
                            sql.SQL("GRANT UPDATE({}) ON mra.{} TO {}").format(
                                sql.Identifier(column), sql.Identifier(table), sql.Identifier(role)
                            )
                        )
                with original_connection(runtime_pool, read_only=True) as checked:
                    assert inspect_runtime_principal(checked)["name"] == role
                initialized = True
            with original_connection(runtime_pool, read_only=read_only) as connection:
                assert connection.info.user == role
                yield connection
        else:
            with original_connection(pool, read_only=read_only) as connection:
                yield connection

    def wrap(function):
        @wraps(function)
        def under_login(*args, **kwargs):
            token = active.set(True)
            try:
                return function(*args, **kwargs)
            finally:
                active.reset(token)

        return under_login

    try:
        with monkeypatch.context() as patch:
            patch.setattr(TargetPostgresPool, "connection", restricted_connection)
            for name in (
                "execute",
                "execute_step",
                "settle_and_evaluate",
                "_execute_outcome_step",
                "abstain",
                "report",
                "replay",
                "replay_completed_cycle",
                "record_research_disposition",
            ):
                patch.setattr(DailyResearchOperations, name, wrap(getattr(DailyResearchOperations, name)))
            vertical(target_database_url, tmp_path, False, True, patch, record_property)
        with original_connection(runtime_pool, read_only=True) as c:
            assert c.execute(
                "SELECT has_table_privilege('mra.model_version','INSERT'),has_table_privilege('mra.schema_migrations','INSERT'),has_table_privilege('mra.provider_qualification_decision','INSERT')"
            ).fetchone() == (False, False, False)
    finally:
        runtime_pool.close()
        with psycopg.connect(target_database_url) as admin:
            admin.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
            admin.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))
