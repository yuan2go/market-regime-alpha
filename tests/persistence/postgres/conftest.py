from __future__ import annotations

from collections.abc import Iterator
import os
import re
import uuid

import psycopg
from psycopg import sql
import pytest

from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.settings import DatabaseSettings


TEST_DATABASE_URL_ENV = "MARKET_REGIME_ALPHA_TEST_DATABASE_URL"
_TEST_SCHEMA = re.compile(r"^test_mra_[0-9a-f]{32}$")


@pytest.fixture
def postgres_factory() -> Iterator[PostgresConnectionFactory]:
    database_url = os.getenv(TEST_DATABASE_URL_ENV)
    if not database_url:
        raise RuntimeError(
            f"{TEST_DATABASE_URL_ENV} is required; PostgreSQL tests never skip"
        )
    schema = f"test_mra_{uuid.uuid4().hex}"
    assert _TEST_SCHEMA.fullmatch(schema)
    with psycopg.connect(database_url, autocommit=True) as connection:
        connection.execute(
            sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema))
        )
    settings = DatabaseSettings.from_sources(
        database_url=database_url,
        environ={},
    )
    factory = PostgresConnectionFactory(
        settings,
        min_size=0,
        max_size=8,
        application_schema=schema,
    )
    try:
        yield factory
    finally:
        factory.close()
        if not _TEST_SCHEMA.fullmatch(schema):
            raise RuntimeError("refusing to drop unresolved test schema")
        with psycopg.connect(database_url, autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(
                    sql.Identifier(schema)
                )
            )
