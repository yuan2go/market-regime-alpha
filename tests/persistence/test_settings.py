from __future__ import annotations

from pathlib import Path

import pytest

from market_regime_alpha.persistence.settings import (
    DatabaseBackend,
    DatabaseConfigurationError,
    DatabaseSettings,
    redact_database_url,
)


POSTGRES_URL = (
    "postgresql://market_regime_alpha:s%40cret@127.0.0.1:5432/"
    "market_regime_alpha"
)


def test_default_backend_requires_postgres_url() -> None:
    with pytest.raises(
        DatabaseConfigurationError,
        match="PostgreSQL configuration",
    ):
        DatabaseSettings.from_sources(
            database_url=None,
            sqlite_path=None,
            environ={},
        )


def test_environment_selects_postgres_by_default() -> None:
    settings = DatabaseSettings.from_sources(
        database_url=None,
        sqlite_path=None,
        environ={"MARKET_REGIME_ALPHA_DATABASE_URL": POSTGRES_URL},
    )

    assert settings.backend is DatabaseBackend.POSTGRES
    assert settings.require_database_url() == POSTGRES_URL
    assert settings.sqlite_path is None


def test_explicit_database_url_precedes_environment() -> None:
    explicit = POSTGRES_URL.replace("127.0.0.1", "localhost")

    settings = DatabaseSettings.from_sources(
        database_url=explicit,
        sqlite_path=None,
        environ={"MARKET_REGIME_ALPHA_DATABASE_URL": POSTGRES_URL},
    )

    assert settings.require_database_url() == explicit


def test_explicit_sqlite_path_selects_compatibility_backend(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "compatibility.sqlite3"

    settings = DatabaseSettings.from_sources(
        database_url=None,
        sqlite_path=sqlite_path,
        environ={},
    )

    assert settings.backend is DatabaseBackend.SQLITE
    assert settings.require_sqlite_path() == sqlite_path.resolve()
    assert settings.database_url is None


def test_explicit_sqlite_path_overrides_environment_default(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "compatibility.sqlite3"

    settings = DatabaseSettings.from_sources(
        database_url=None,
        sqlite_path=sqlite_path,
        environ={"MARKET_REGIME_ALPHA_DATABASE_URL": POSTGRES_URL},
    )

    assert settings.backend is DatabaseBackend.SQLITE
    assert settings.require_sqlite_path() == sqlite_path.resolve()


def test_postgres_and_sqlite_cannot_be_selected_together(tmp_path: Path) -> None:
    with pytest.raises(
        DatabaseConfigurationError,
        match="exactly one database authority",
    ):
        DatabaseSettings.from_sources(
            database_url=POSTGRES_URL,
            sqlite_path=tmp_path / "compatibility.sqlite3",
            environ={},
        )


@pytest.mark.parametrize(
    "value",
    [
        "sqlite:///tmp/runtime.sqlite3",
        "http://127.0.0.1/database",
        "postgresql://127.0.0.1",
    ],
)
def test_invalid_postgres_url_fails_closed(value: str) -> None:
    with pytest.raises(DatabaseConfigurationError, match="PostgreSQL URL"):
        DatabaseSettings.from_sources(
            database_url=value,
            sqlite_path=None,
            environ={},
        )


def test_redaction_never_exposes_password() -> None:
    redacted = redact_database_url(POSTGRES_URL)

    assert "s%40cret" not in redacted
    assert "s@cret" not in redacted
    assert "market_regime_alpha:***@" in redacted
    assert redacted.endswith("/market_regime_alpha")


def test_settings_repr_redacts_database_password() -> None:
    settings = DatabaseSettings.from_sources(
        database_url=POSTGRES_URL,
        sqlite_path=None,
        environ={},
    )

    rendered = repr(settings)
    assert "s%40cret" not in rendered
    assert "s@cret" not in rendered
    assert "***" in rendered
