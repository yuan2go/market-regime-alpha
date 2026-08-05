"""Narrow DB-API compatibility surface for proven SQLite repository logic."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from datetime import date, datetime
import sqlite3
from typing import Any, overload

import psycopg


class _InstantIsoString(str):
    """A text-shaped timestamp whose equality follows timestamptz semantics."""

    def __new__(cls, value: datetime) -> _InstantIsoString:
        return super().__new__(cls, value.isoformat())

    def __eq__(self, other: object) -> bool:
        if isinstance(other, str):
            try:
                return _parse_iso_instant(self) == _parse_iso_instant(other)
            except ValueError:
                pass
        return super().__eq__(other)

    def __ne__(self, other: object) -> bool:
        return not self == other

    __hash__ = str.__hash__


class PostgresRow:
    """Immutable row with the name and positional access used by sqlite3.Row."""

    def __init__(self, columns: Sequence[str], values: Sequence[Any]) -> None:
        if len(columns) != len(values):
            raise ValueError("row column/value cardinality mismatch")
        self._columns = tuple(columns)
        self._values = tuple(_sqlite_compatible_value(value) for value in values)
        self._positions = {name: index for index, name in enumerate(self._columns)}
        if len(self._positions) != len(self._columns):
            raise ValueError("duplicate result column names are unsupported")

    @overload
    def __getitem__(self, key: str) -> Any: ...

    @overload
    def __getitem__(self, key: int) -> Any: ...

    def __getitem__(self, key: str | int) -> Any:
        if isinstance(key, int):
            return self._values[key]
        return self._values[self._positions[key]]

    def __iter__(self) -> Iterator[Any]:
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._columns)

    def keys(self) -> list[str]:
        return list(self._columns)


class PostgresDBAPICursor:
    def __init__(self, cursor: psycopg.Cursor[tuple[Any, ...]]) -> None:
        self._cursor = cursor

    @property
    def rowcount(self) -> int:
        return self._cursor.rowcount

    @property
    def lastrowid(self) -> int | None:
        return None

    def fetchone(self) -> PostgresRow | None:
        row = self._cursor.fetchone()
        if row is None:
            return None
        return PostgresRow(self._columns(), row)

    def fetchall(self) -> list[PostgresRow]:
        columns = self._columns()
        return [PostgresRow(columns, row) for row in self._cursor.fetchall()]

    def _columns(self) -> tuple[str, ...]:
        description = self._cursor.description
        if description is None:
            return ()
        return tuple(item.name for item in description)


class PostgresDBAPIConnection:
    """Translate only qmark parameters and SQLite transaction initiation."""

    def __init__(self, connection: psycopg.Connection[tuple[Any, ...]]) -> None:
        self._connection = connection

    def execute(
        self,
        statement: str,
        parameters: Sequence[Any] | None = None,
    ) -> PostgresDBAPICursor:
        normalized = statement.strip().rstrip(";")
        if normalized.upper() == "BEGIN IMMEDIATE":
            normalized = "BEGIN"
        if normalized.upper().startswith("PRAGMA"):
            raise ValueError("SQLite PRAGMA is not available in PostgreSQL")
        compiled = compile_qmark_sql(normalized)
        try:
            cursor = self._connection.execute(
                compiled,
                tuple(parameters or ()),
                prepare=False,
            )
        except (psycopg.IntegrityError, psycopg.errors.RaiseException) as exc:
            raise sqlite3.IntegrityError(str(exc)) from exc
        return PostgresDBAPICursor(cursor)

    def executemany(
        self,
        statement: str,
        parameter_rows: Iterable[Sequence[Any]],
    ) -> PostgresDBAPICursor:
        compiled = compile_qmark_sql(statement.strip().rstrip(";"))
        try:
            cursor = self._connection.cursor()
            cursor.executemany(compiled, parameter_rows)
        except (psycopg.IntegrityError, psycopg.errors.RaiseException) as exc:
            raise sqlite3.IntegrityError(str(exc)) from exc
        return PostgresDBAPICursor(cursor)

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()


def compile_qmark_sql(statement: str) -> str:
    """Compile qmark placeholders without rewriting quoted/comment text."""

    if not isinstance(statement, str):
        raise TypeError("SQL statement must be a string")
    output: list[str] = []
    index = 0
    state = "plain"
    while index < len(statement):
        char = statement[index]
        following = statement[index + 1] if index + 1 < len(statement) else ""
        if state == "plain":
            if char == "'":
                state = "single"
            elif char == '"':
                state = "double"
            elif char == "-" and following == "-":
                state = "line_comment"
                output.append(char)
                index += 1
                char = following
            elif char == "/" and following == "*":
                state = "block_comment"
                output.append(char)
                index += 1
                char = following
            elif char == "?":
                output.append("%s")
                index += 1
                continue
        elif state == "single":
            if char == "'":
                if following == "'":
                    output.extend((char, following))
                    index += 2
                    continue
                state = "plain"
        elif state == "double":
            if char == '"':
                if following == '"':
                    output.extend((char, following))
                    index += 2
                    continue
                state = "plain"
        elif state == "line_comment":
            if char == "\n":
                state = "plain"
        elif state == "block_comment" and char == "*" and following == "/":
            output.extend((char, following))
            index += 2
            state = "plain"
            continue
        output.append(char)
        index += 1
    return "".join(output)


def _sqlite_compatible_value(value: Any) -> Any:
    """Preserve the value shapes consumed by existing domain restorers."""

    if isinstance(value, datetime):
        return _InstantIsoString(value)
    if isinstance(value, date):
        return value.isoformat()
    return value


def _parse_iso_instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
