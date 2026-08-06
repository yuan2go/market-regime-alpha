"""Fail-closed database settings with credential-safe rendering."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import os
from urllib.parse import SplitResult, urlsplit, urlunsplit


DATABASE_URL_ENV = "MARKET_REGIME_ALPHA_DATABASE_URL"
POSTGRES_SCHEMES = frozenset({"postgres", "postgresql"})


class DatabaseConfigurationError(ValueError):
    """Raised when database authority selection is absent or ambiguous."""


@dataclass(frozen=True, repr=False)
class DatabaseSettings:
    """The only supported database authority: one PostgreSQL URL."""

    database_url: str = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.database_url, str):
            raise TypeError("database_url must be a string")
        _validate_postgres_url(self.database_url)

    @classmethod
    def from_sources(
        cls,
        *,
        database_url: str | None,
        environ: Mapping[str, str] | None = None,
    ) -> DatabaseSettings:
        environment = os.environ if environ is None else environ
        explicit_url = _optional_text(database_url)
        selected_url = explicit_url or _optional_text(
            environment.get(DATABASE_URL_ENV)
        )
        if selected_url is None:
            raise DatabaseConfigurationError(
                "PostgreSQL configuration is required through --database-url "
                f"or {DATABASE_URL_ENV}"
            )
        return cls(database_url=selected_url)

    def require_database_url(self) -> str:
        return self.database_url

    def __repr__(self) -> str:
        authority = redact_database_url(self.database_url)
        return f"DatabaseSettings(authority={authority!r})"


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
