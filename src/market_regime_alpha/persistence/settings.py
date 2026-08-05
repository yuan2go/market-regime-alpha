"""Fail-closed database settings with credential-safe rendering."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
import os
from pathlib import Path
from urllib.parse import SplitResult, urlsplit, urlunsplit


DATABASE_URL_ENV = "MARKET_REGIME_ALPHA_DATABASE_URL"
POSTGRES_SCHEMES = frozenset({"postgres", "postgresql"})


class DatabaseConfigurationError(ValueError):
    """Raised when database authority selection is absent or ambiguous."""


class DatabaseBackend(str, Enum):
    POSTGRES = "postgres"
    SQLITE = "sqlite"


@dataclass(frozen=True, repr=False)
class DatabaseSettings:
    """Exactly one PostgreSQL or explicit SQLite authority selection."""

    backend: DatabaseBackend
    database_url: str | None = field(default=None, repr=False)
    sqlite_path: Path | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.backend, DatabaseBackend):
            raise TypeError("backend must be a DatabaseBackend")
        selected = int(self.database_url is not None) + int(
            self.sqlite_path is not None
        )
        if selected != 1:
            raise DatabaseConfigurationError(
                "select exactly one database authority"
            )
        if self.backend is DatabaseBackend.POSTGRES:
            if self.database_url is None or self.sqlite_path is not None:
                raise DatabaseConfigurationError(
                    "PostgreSQL backend requires only a PostgreSQL URL"
                )
            _validate_postgres_url(self.database_url)
        else:
            if self.sqlite_path is None or self.database_url is not None:
                raise DatabaseConfigurationError(
                    "SQLite compatibility requires only a SQLite path"
                )
            object.__setattr__(self, "sqlite_path", self.sqlite_path.resolve())

    @classmethod
    def from_sources(
        cls,
        *,
        database_url: str | None,
        sqlite_path: str | Path | None,
        environ: Mapping[str, str] | None = None,
    ) -> DatabaseSettings:
        environment = os.environ if environ is None else environ
        explicit_url = _optional_text(database_url)
        selected_path = Path(sqlite_path) if sqlite_path is not None else None
        if explicit_url is not None and selected_path is not None:
            raise DatabaseConfigurationError(
                "select exactly one database authority; PostgreSQL and SQLite "
                "were both supplied"
            )
        if selected_path is not None:
            return cls(
                backend=DatabaseBackend.SQLITE,
                sqlite_path=selected_path,
            )
        selected_url = explicit_url or _optional_text(
            environment.get(DATABASE_URL_ENV)
        )
        if selected_url is None:
            raise DatabaseConfigurationError(
                "PostgreSQL configuration is required through --database-url "
                f"or {DATABASE_URL_ENV}; SQLite is explicit compatibility only"
            )
        return cls(
            backend=DatabaseBackend.POSTGRES,
            database_url=selected_url,
        )

    def require_database_url(self) -> str:
        if self.backend is not DatabaseBackend.POSTGRES:
            raise DatabaseConfigurationError(
                "PostgreSQL URL requested from SQLite settings"
            )
        assert self.database_url is not None
        return self.database_url

    def require_sqlite_path(self) -> Path:
        if self.backend is not DatabaseBackend.SQLITE:
            raise DatabaseConfigurationError(
                "SQLite path requested from PostgreSQL settings"
            )
        assert self.sqlite_path is not None
        return self.sqlite_path

    def __repr__(self) -> str:
        if self.database_url is not None:
            authority = redact_database_url(self.database_url)
        else:
            authority = str(self.sqlite_path)
        return (
            "DatabaseSettings("
            f"backend={self.backend.value!r}, authority={authority!r})"
        )


def redact_database_url(value: str) -> str:
    """Return a useful PostgreSQL locator without exposing its credential."""

    if not isinstance(value, str):
        raise TypeError("database URL must be a string")
    try:
        parts = urlsplit(value)
    except ValueError:
        return "<invalid-database-url>"
    if "@" not in parts.netloc:
        return urlunsplit(parts)
    userinfo, hostinfo = parts.netloc.rsplit("@", 1)
    username = userinfo.split(":", 1)[0]
    redacted_netloc = f"{username}:***@{hostinfo}"
    return urlunsplit(
        SplitResult(
            scheme=parts.scheme,
            netloc=redacted_netloc,
            path=parts.path,
            query=parts.query,
            fragment=parts.fragment,
        )
    )


def _validate_postgres_url(value: str) -> None:
    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError as exc:
        raise DatabaseConfigurationError("invalid PostgreSQL URL") from exc
    if parts.scheme not in POSTGRES_SCHEMES:
        raise DatabaseConfigurationError(
            "database authority must be a PostgreSQL URL"
        )
    if not parts.hostname or not parts.path.strip("/"):
        raise DatabaseConfigurationError(
            "PostgreSQL URL must include a host and database name"
        )
    if port is not None and not (1 <= port <= 65535):
        raise DatabaseConfigurationError("invalid PostgreSQL URL port")


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("database URL must be a string or None")
    normalized = value.strip()
    return normalized or None
