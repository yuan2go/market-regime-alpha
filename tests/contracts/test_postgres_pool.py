from __future__ import annotations

import psycopg
import pytest

from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool


def test_successful_read_only_checks_preserve_prepared_statement_reuse(target_database_url):
    pool = TargetPostgresPool(target_database_url, min_size=1, max_size=1)
    try:
        for value in range(8):
            with pool.connection(read_only=True) as connection:
                assert connection.execute("SHOW transaction_read_only").fetchone() == ("on",)
                assert connection.execute(
                    "SELECT %s::integer + 1", (value,), prepare=True,
                ).fetchone() == (value + 1,)
        with pool.connection(read_only=True) as connection:
            assert connection.execute(
                "SELECT count(*) FROM pg_prepared_statements WHERE statement = %s",
                ("SELECT $1::integer + 1",),
            ).fetchone() == (1,)
    finally:
        pool.close()


def test_read_only_failure_and_uncommitted_writes_still_roll_back(target_database_url):
    with psycopg.connect(target_database_url, autocommit=True) as connection:
        connection.execute("CREATE SCHEMA mra")
        connection.execute("CREATE TABLE mra.pool_probe (value integer)")
    pool = TargetPostgresPool(target_database_url, min_size=1, max_size=1)
    try:
        with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
            with pool.connection(read_only=True) as connection:
                connection.execute("INSERT INTO mra.pool_probe VALUES (1)")
        with pool.connection() as connection:
            connection.execute("INSERT INTO mra.pool_probe VALUES (2)")
        with pool.connection(read_only=True) as connection:
            assert connection.execute("SELECT * FROM mra.pool_probe").fetchall() == []
        with pool.connection() as connection:
            connection.execute("INSERT INTO mra.pool_probe VALUES (3)")
            connection.commit()
        with pytest.raises(RuntimeError, match="reader interrupted"):
            with pool.connection(read_only=True) as connection:
                connection.execute("SET LOCAL application_name = 'interrupted-reader'")
                raise RuntimeError("reader interrupted")
        with pool.connection(read_only=True) as connection:
            assert connection.execute("SELECT * FROM mra.pool_probe").fetchall() == [(3,)]
            assert connection.execute("SHOW application_name").fetchone() == (
                "market-regime-alpha-refoundation",
            )
    finally:
        pool.close()
