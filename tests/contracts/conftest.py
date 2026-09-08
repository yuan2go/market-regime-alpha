from __future__ import annotations

from collections.abc import Iterator
import os
import time

import psycopg
import pytest


TEST_DATABASE_URL_ENV = "MARKET_REGIME_ALPHA_TEST_DATABASE_URL"
_CONNECTION_DRAIN_TIMEOUT_SECONDS = 5.0


def _wait_for_client_connections_to_drain(database_url: str) -> None:
    deadline = time.monotonic() + _CONNECTION_DRAIN_TIMEOUT_SECONDS
    while True:
        with psycopg.connect(database_url, autocommit=True) as connection:
            rows = connection.execute(
                """
                SELECT pid
                FROM pg_stat_activity
                WHERE datname = current_database()
                  AND pid <> pg_backend_pid()
                  AND backend_type = 'client backend'
                ORDER BY pid
                """
            ).fetchall()
        if not rows:
            return
        if time.monotonic() >= deadline:
            raise RuntimeError(
                "disposable PostgreSQL test connections did not drain; "
                f"remaining pids={[int(row[0]) for row in rows]}"
            )
        time.sleep(0.02)


@pytest.fixture
def target_database_url() -> Iterator[str]:
    database_url = os.getenv(TEST_DATABASE_URL_ENV)
    if not database_url:
        raise RuntimeError(
            f"{TEST_DATABASE_URL_ENV} is required; Foundation PostgreSQL tests never skip"
        )

    def clean() -> None:
        with psycopg.connect(database_url, autocommit=True) as connection:
            connection.execute("DROP SCHEMA IF EXISTS mra CASCADE")
            connection.execute("DROP TABLE IF EXISTS public.continuous_research_run")
            connection.execute("DROP TABLE IF EXISTS public.unexpected_probe")
        _wait_for_client_connections_to_drain(database_url)

    clean()
    try:
        yield database_url
    finally:
        clean()
