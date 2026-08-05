from __future__ import annotations

from datetime import datetime
import sqlite3

import pytest

from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.postgres.dbapi import (
    PostgresDBAPIConnection,
    compile_qmark_sql,
)


def test_qmark_compiler_ignores_literals_identifiers_and_comments() -> None:
    source = "SELECT ?, '?', \"?\" -- ?\n, ? /* ? */"

    assert compile_qmark_sql(source) == "SELECT %s, '?', \"?\" -- ?\n, %s /* ? */"


def test_rows_support_name_position_and_keys(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    with postgres_factory.connection() as raw:
        connection = PostgresDBAPIConnection(raw)
        row = connection.execute(
            "SELECT ?::text AS alpha, ?::bigint AS beta",
            ("value", 7),
        ).fetchone()

    assert row is not None
    assert row[0] == "value"
    assert row["alpha"] == "value"
    assert row[1] == 7
    assert row.keys() == ["alpha", "beta"]
    assert tuple(row) == ("value", 7)


def test_begin_immediate_and_executemany_are_supported(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    with postgres_factory.connection() as raw:
        connection = PostgresDBAPIConnection(raw)
        connection.execute("CREATE TABLE dbapi_items(id bigint PRIMARY KEY, value text)")
        connection.commit()
        connection.execute("BEGIN IMMEDIATE")
        connection.executemany(
            "INSERT INTO dbapi_items(id, value) VALUES (?, ?)",
            ((1, "one"), (2, "two")),
        )
        connection.commit()
        rows = connection.execute(
            "SELECT id, value FROM dbapi_items ORDER BY id"
        ).fetchall()

    assert [(row["id"], row["value"]) for row in rows] == [
        (1, "one"),
        (2, "two"),
    ]


def test_postgres_integrity_error_maps_to_repository_compatibility_error(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    with postgres_factory.connection() as raw:
        connection = PostgresDBAPIConnection(raw)
        connection.execute("CREATE TABLE dbapi_unique(id bigint PRIMARY KEY)")
        connection.commit()
        connection.execute("INSERT INTO dbapi_unique(id) VALUES (?)", (1,))
        connection.commit()

        with pytest.raises(sqlite3.IntegrityError, match="duplicate key"):
            connection.execute("INSERT INTO dbapi_unique(id) VALUES (?)", (1,))
        connection.rollback()


def test_timestamptz_rows_compare_by_instant_but_remain_text_shaped(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    with postgres_factory.connection() as raw:
        connection = PostgresDBAPIConnection(raw)
        row = connection.execute(
            "SELECT ?::timestamptz AS observed_at",
            ("2026-08-05T10:00:00+08:00",),
        ).fetchone()

    assert row is not None
    assert row["observed_at"] == "2026-08-05T10:00:00+08:00"
    assert datetime.fromisoformat(str(row["observed_at"])) == datetime.fromisoformat(
        "2026-08-05T02:00:00+00:00"
    )
