"""Authenticated runtime identity, permissions and impersonation refusal."""

from contextlib import contextmanager
from uuid import uuid4

import psycopg
from psycopg import sql
import pytest

from market_regime_alpha.infrastructure.postgres.schema import SchemaManager
from tests.contracts.conftest import target_database_url  # noqa: F401


@contextmanager
def runtime_login(database_url):
    role = "runtime_test_" + uuid4().hex
    password = uuid4().hex
    with psycopg.connect(database_url) as admin:
        admin.execute(sql.SQL("REVOKE TEMP ON DATABASE {} FROM PUBLIC").format(sql.Identifier(admin.info.dbname)))
        admin.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(sql.Identifier(role), sql.Literal(password)))
        admin.execute(sql.SQL("GRANT USAGE ON SCHEMA mra TO {}").format(sql.Identifier(role)))
        admin.execute(sql.SQL("GRANT EXECUTE ON FUNCTION pg_catalog.pg_control_system() TO {}").format(sql.Identifier(role)))
        admin.execute(sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA mra TO {}").format(sql.Identifier(role)))
        for table in ("runtime_attempt", "runtime_run", "runtime_step", "command_receipt", "artifact"):
            admin.execute(sql.SQL("GRANT INSERT, UPDATE ON mra.{} TO {}").format(sql.Identifier(table), sql.Identifier(role)))
        from tests.contracts.test_daily_runtime_permissions_postgres import REFERENCE_LOCKS

        for table, column in REFERENCE_LOCKS.items():
            admin.execute(
                sql.SQL("GRANT UPDATE({}) ON mra.{} TO {}").format(sql.Identifier(column), sql.Identifier(table), sql.Identifier(role))
            )
        for table in (
            "decision_run_research_qualification_roster",
            "decision_run_research_qualification_member",
            "research_partition_outcome_access",
            "evaluation_observation",
        ):
            admin.execute(sql.SQL("GRANT INSERT, UPDATE ON mra.{} TO {}").format(sql.Identifier(table), sql.Identifier(role)))
    try:
        with psycopg.connect(database_url, user=role, password=password, autocommit=True) as connection:
            yield role, connection
    finally:
        with psycopg.connect(database_url) as admin:
            admin.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
            admin.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))


@pytest.mark.parametrize(
    "privilege",
    [
        "UPDATE ON mra.runtime_attempt",
        "UPDATE(provider_product_id) ON mra.provider_product",
        "UPDATE(universe_revision_id) ON mra.exploratory_retrospective_universe_revision",
        "INSERT ON mra.decision_run_research_qualification_roster",
    ],
)
def test_principal_is_authenticated_and_lost_write_privilege_refuses_without_facts(target_database_url, privilege):  # noqa: F811
    from market_regime_alpha.interfaces.deployment_profile import inspect_runtime_principal

    SchemaManager(target_database_url).bootstrap()
    with runtime_login(target_database_url) as (role, connection):
        first = inspect_runtime_principal(connection)
        assert first["name"] == role
        assert first["oid"] > 0
        assert connection.execute("SELECT count(*) FROM mra.command_receipt").fetchone() == (0,)
        with psycopg.connect(target_database_url) as admin:
            admin.execute(sql.SQL("REVOKE {} FROM {}").format(sql.SQL(privilege), sql.Identifier(role)))
        with pytest.raises(ValueError, match="RUNTIME_PRINCIPAL_PRIVILEGES"):
            inspect_runtime_principal(connection)
        assert connection.execute("SELECT count(*) FROM mra.command_receipt").fetchone() == (0,)


def test_superuser_and_set_role_cannot_impersonate_runtime_login(target_database_url):  # noqa: F811
    from market_regime_alpha.interfaces.deployment_profile import inspect_runtime_principal

    SchemaManager(target_database_url).bootstrap()
    with psycopg.connect(target_database_url, autocommit=True) as admin:
        with pytest.raises(ValueError, match="RUNTIME_PRINCIPAL_PRIVILEGES"):
            inspect_runtime_principal(admin)
        with runtime_login(target_database_url) as (role, _):
            admin.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(role)))
            try:
                with pytest.raises(ValueError, match="RUNTIME_PRINCIPAL_IMPERSONATION"):
                    inspect_runtime_principal(admin)
            finally:
                admin.execute("RESET ROLE")
        assert admin.execute("SELECT count(*) FROM mra.audit_event").fetchone() == (0,)


@pytest.mark.parametrize(
    "grant",
    [
        "DELETE ON mra.runtime_attempt",
        "TRUNCATE ON mra.artifact",
        "UPDATE ON mra.model_version",
        "INSERT(model_version_id) ON mra.model_version",
        "REFERENCES ON mra.forecast",
        "TRIGGER ON mra.data_capture",
        "UPDATE(model_id) ON mra.model_version",
    ],
)
def test_dangerous_extra_grant_is_refused_with_old_identity(target_database_url, grant):  # noqa: F811
    from market_regime_alpha.interfaces.deployment_profile import inspect_runtime_principal

    SchemaManager(target_database_url).bootstrap()
    with runtime_login(target_database_url) as (role, connection):
        identity = inspect_runtime_principal(connection)
        with psycopg.connect(target_database_url) as admin:
            admin.execute(sql.SQL("GRANT {} TO {}").format(sql.SQL(grant), sql.Identifier(role)))
        assert connection.execute("SELECT oid FROM pg_roles WHERE rolname=session_user").fetchone()[0] == identity["oid"]
        with pytest.raises(ValueError, match="RUNTIME_PRINCIPAL_PRIVILEGES"):
            inspect_runtime_principal(connection)
        assert connection.execute("SELECT count(*) FROM mra.audit_event").fetchone() == (0,)


@pytest.mark.parametrize("change", ["sequence", "function", "membership", "schema", "grant_option"])
def test_runtime_refuses_non_table_privilege_escalation(target_database_url, change):  # noqa: F811
    from market_regime_alpha.interfaces.deployment_profile import inspect_runtime_principal

    SchemaManager(target_database_url).bootstrap()
    with runtime_login(target_database_url) as (role, connection):
        inspect_runtime_principal(connection)
        with psycopg.connect(target_database_url) as admin:
            if change == "sequence":
                admin.execute("CREATE SEQUENCE mra.privilege_probe")
                admin.execute(sql.SQL("GRANT USAGE ON SEQUENCE mra.privilege_probe TO {}").format(sql.Identifier(role)))
            elif change == "function":
                admin.execute("CREATE FUNCTION mra.privilege_probe() RETURNS integer LANGUAGE sql SECURITY DEFINER AS 'SELECT 1'")
            elif change == "membership":
                admin.execute(sql.SQL("GRANT pg_read_all_data TO {}").format(sql.Identifier(role)))
            elif change == "schema":
                admin.execute(sql.SQL("GRANT CREATE ON SCHEMA public TO {}").format(sql.Identifier(role)))
            else:
                admin.execute(sql.SQL("GRANT INSERT ON mra.artifact TO {} WITH GRANT OPTION").format(sql.Identifier(role)))
        with pytest.raises(ValueError, match="RUNTIME_PRINCIPAL_PRIVILEGES"):
            inspect_runtime_principal(connection)
        assert connection.execute("SELECT count(*) FROM mra.command_receipt").fetchone() == (0,)
