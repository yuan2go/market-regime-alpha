"""Actual PostgreSQL cancellation/loss cleanup; disposable scope only."""

import pytest

from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.interfaces.operation_observation import observe_health


@pytest.mark.parametrize("read_only", [False, True])
def test_closed_connection_cleanup_preserves_original_failure_and_pool_capacity(target_database_url, read_only):
    pool = TargetPostgresPool(target_database_url, min_size=0, max_size=1)
    original = RuntimeError("original owner failure")
    try:
        with pytest.raises(RuntimeError) as raised:
            with pool.connection(read_only=read_only) as connection:
                connection.close()
                raise original
        assert raised.value is original
        with pool.connection(read_only=True) as connection:
            assert connection.execute("SELECT 42").fetchone() == (42,)
    finally:
        pool.close()


def test_cancelled_health_rolls_back_and_keeps_previously_committed_result(target_database_url):
    pool = TargetPostgresPool(target_database_url, min_size=0, max_size=1)
    try:
        with pool.connection() as connection:
            connection.execute("CREATE TEMP TABLE committed_result(value integer)")
            connection.execute("INSERT INTO committed_result VALUES (42)")
            connection.commit()
        def health():
            with pool.connection(read_only=True) as connection:
                connection.execute("SET LOCAL statement_timeout='10ms'")
                connection.execute("SELECT pg_sleep(0.1)")
            return {"state": "UNREACHABLE"}
        result = observe_health(health)
        assert result["state"] == "HEALTH_QUERY_FAILED"
        assert result["error_type"] == "QueryCanceled"
        assert result["sqlstate"] == "57014"
        with pool.connection(read_only=True) as connection:
            assert connection.execute("SELECT value FROM committed_result").fetchone() == (42,)
            assert connection.execute("SELECT current_setting('transaction_read_only')").fetchone() == ("on",)
    finally:
        pool.close()


@pytest.mark.parametrize("read_only", [False, True])
def test_rollback_failure_preserves_owner_error_and_replaces_connection(target_database_url, monkeypatch, read_only):
    pool = TargetPostgresPool(target_database_url, min_size=0, max_size=1)
    original = RuntimeError("original transaction failure")
    def failed_rollback():
        raise OSError("connection lost during rollback")
    try:
        with pytest.raises(RuntimeError) as raised:
            with pool.connection(read_only=read_only) as connection:
                connection.execute("SELECT 1")
                monkeypatch.setattr(connection, "rollback", failed_rollback)
                raise original
        assert raised.value is original
        assert connection.closed
        assert any("cleanup failed: OSError" in note for note in original.__notes__)
        with pool.connection(read_only=True) as replacement:
            assert replacement.execute("SELECT 42").fetchone() == (42,)
    finally:
        pool.close()
