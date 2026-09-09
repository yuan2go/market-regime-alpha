"""Retained account persistence cannot race a canonical database reservation."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from market_regime_alpha.interfaces.prospective_operation_guard import operational_session
from market_regime_alpha.persistence.postgres.connection import PostgresConnectionFactory
from market_regime_alpha.persistence.settings import DatabaseSettings
from market_regime_alpha.bootstrap import bootstrap_application
from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.runtime.application import ActorType, CommandContext
from tests.contracts.market.test_prospective_operation_guard_postgres import guarded_scope  # noqa: F401


def test_retained_writer_refuses_supervised_scope_but_read_only_inspection_remains_available(request):
    settings, _, config = request.getfixturevalue("guarded_scope")
    legacy = DatabaseSettings.from_sources(database_url=settings.database_url, environ={})
    with PostgresConnectionFactory(legacy, application_schema="public") as factory:
        with operational_session(settings, config):
            with pytest.raises(ValueError, match="RETAINED_WRITER_ADMISSION_CONFLICT"):
                with factory.connection() as connection:
                    connection.execute("CREATE TEMP TABLE forbidden_writer (id integer)")
            with factory.connection(read_only=True) as connection:
                assert connection.execute("SELECT to_regclass('pg_temp.forbidden_writer')").fetchone() == (None,)
                assert connection.execute("SHOW transaction_read_only").fetchone() == ("on",)


def test_inflight_retained_transaction_and_new_supervisor_share_atomic_admission(request):
    settings, _, config = request.getfixturevalue("guarded_scope")
    legacy = DatabaseSettings.from_sources(database_url=settings.database_url, environ={})
    attempting, acquired = Event(), Event()
    def supervise():
        attempting.set()
        with operational_session(settings, config):
            acquired.set()
    with PostgresConnectionFactory(legacy, application_schema="public") as factory, ThreadPoolExecutor(1) as executor:
        with factory.connection() as connection:
            connection.execute("SELECT 1")
            # Nested retained reads/writes share admission; they must not deadlock
            # on a global exclusive lock before their existing scoped locks.
            with factory.connection() as nested:
                assert nested.execute("SELECT 2").fetchone() == (2,)
            future = executor.submit(supervise)
            assert attempting.wait(2)
            assert not acquired.wait(.15)
        future.result(timeout=5)
    assert acquired.is_set()


def test_canonical_non_attempt_writer_respects_reservation_and_supervision_loss(request):
    settings, _, config = request.getfixturevalue("guarded_scope")
    with bootstrap_application(settings) as app, ThreadPoolExecutor(1) as executor:
        def publish(key):
            return app.artifacts.publish(key.encode(), media_type="text/plain",
                context=CommandContext(key, ActorType.OPERATOR, "admission-test", "TEST"))
        with operational_session(settings, config) as guard:
            before = app.evidence.inventory()["artifact_count"]
            with pytest.raises(ValueError, match="CANONICAL_WRITER_ADMISSION_CONFLICT"):
                executor.submit(publish, "foreign-writer").result(timeout=5)
            assert app.evidence.inventory()["artifact_count"] == before
            # The authentic owner may publish; after losing its reservation no
            # further command can start, even when it has no Runtime Attempt.
            publish("own-writer")
            guard.connection.close()
            with pytest.raises(ValueError, match="SUPERVISOR_CONNECTION_LOST"):
                publish("lost-supervision")


def test_inflight_canonical_transaction_prevents_supervisor_reservation(request):
    settings, _, config = request.getfixturevalue("guarded_scope")
    pool = TargetPostgresPool(settings.database_url)
    def supervise():
        with operational_session(settings, config):
            return True
    try:
        with ThreadPoolExecutor(1) as executor:
            with pool.connection() as connection:
                connection.execute("SELECT 1")
                with pytest.raises(ValueError, match="DUPLICATE_SUPERVISOR"):
                    executor.submit(supervise).result(timeout=5)
            assert executor.submit(supervise).result(timeout=5)
    finally:
        pool.close()
