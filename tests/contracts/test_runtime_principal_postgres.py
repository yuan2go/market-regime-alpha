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
    role = 'runtime_test_' + uuid4().hex
    password = uuid4().hex
    with psycopg.connect(database_url) as admin:
        admin.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {}').format(sql.Identifier(role), sql.Literal(password)))
        admin.execute(sql.SQL('GRANT USAGE ON SCHEMA mra TO {}').format(sql.Identifier(role)))
        admin.execute(sql.SQL('GRANT SELECT ON ALL TABLES IN SCHEMA mra TO {}').format(sql.Identifier(role)))
        for table in ('runtime_attempt', 'runtime_run', 'runtime_step', 'command_receipt', 'artifact'):
            admin.execute(sql.SQL('GRANT INSERT, UPDATE ON mra.{} TO {}').format(sql.Identifier(table), sql.Identifier(role)))
    try:
        with psycopg.connect(database_url, user=role, password=password, autocommit=True) as connection:
            yield role, connection
    finally:
        with psycopg.connect(database_url) as admin:
            admin.execute(sql.SQL('DROP OWNED BY {}').format(sql.Identifier(role)))
            admin.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(role)))


def test_principal_is_authenticated_and_lost_write_privilege_refuses_without_facts(target_database_url):  # noqa: F811
    from market_regime_alpha.interfaces.deployment_profile import inspect_runtime_principal

    SchemaManager(target_database_url).bootstrap()
    with runtime_login(target_database_url) as (role, connection):
        first = inspect_runtime_principal(connection)
        assert first['name'] == role
        assert first['oid'] > 0
        assert connection.execute('SELECT count(*) FROM mra.command_receipt').fetchone() == (0,)
        with psycopg.connect(target_database_url) as admin:
            admin.execute(sql.SQL('REVOKE UPDATE ON mra.runtime_attempt FROM {}').format(sql.Identifier(role)))
        with pytest.raises(ValueError, match='RUNTIME_PRINCIPAL_PRIVILEGES'):
            inspect_runtime_principal(connection)
        assert connection.execute('SELECT count(*) FROM mra.command_receipt').fetchone() == (0,)


def test_superuser_and_set_role_cannot_impersonate_runtime_login(target_database_url):  # noqa: F811
    from market_regime_alpha.interfaces.deployment_profile import inspect_runtime_principal

    SchemaManager(target_database_url).bootstrap()
    with psycopg.connect(target_database_url, autocommit=True) as admin:
        with pytest.raises(ValueError, match='RUNTIME_PRINCIPAL_PRIVILEGES'):
            inspect_runtime_principal(admin)
        with runtime_login(target_database_url) as (role, _):
            admin.execute(sql.SQL('SET ROLE {}').format(sql.Identifier(role)))
            try:
                with pytest.raises(ValueError, match='RUNTIME_PRINCIPAL_IMPERSONATION'):
                    inspect_runtime_principal(admin)
            finally:
                admin.execute('RESET ROLE')
        assert admin.execute('SELECT count(*) FROM mra.audit_event').fetchone() == (0,)
