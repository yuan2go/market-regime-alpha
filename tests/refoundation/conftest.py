from __future__ import annotations

from collections.abc import Iterator
import os

import psycopg
import pytest


TEST_DATABASE_URL_ENV = "MARKET_REGIME_ALPHA_TEST_DATABASE_URL"


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

    clean()
    try:
        yield database_url
    finally:
        clean()
