from __future__ import annotations

import pytest

from market_regime_alpha.persistence.settings import (
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
            environ={},
        )


def test_environment_selects_postgres_by_default() -> None:
    settings = DatabaseSettings.from_sources(
        database_url=None,
        environ={"MARKET_REGIME_ALPHA_DATABASE_URL": POSTGRES_URL},
    )

    assert settings.require_database_url() == POSTGRES_URL


def test_explicit_database_url_precedes_environment() -> None:
    explicit = POSTGRES_URL.replace("127.0.0.1", "localhost")

    settings = DatabaseSettings.from_sources(
        database_url=explicit,
        environ={"MARKET_REGIME_ALPHA_DATABASE_URL": POSTGRES_URL},
    )

    assert settings.require_database_url() == explicit


@pytest.mark.parametrize(
    "value",
    [
        "postgresql:///tmp/runtime.postgres-scope",
        "http://127.0.0.1/database",
        "postgresql://127.0.0.1",
    ],
)
def test_invalid_postgres_url_fails_closed(value: str) -> None:
    with pytest.raises(DatabaseConfigurationError, match="PostgreSQL URL"):
        DatabaseSettings.from_sources(
            database_url=value,
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
        environ={},
    )

    rendered = repr(settings)
    assert "s%40cret" not in rendered
    assert "s@cret" not in rendered
    assert "***" in rendered


def test_settings_exposes_no_sqlite_backend_or_path() -> None:
    settings = DatabaseSettings.from_sources(
        database_url=POSTGRES_URL,
        environ={},
    )

    assert not hasattr(settings, "backend")
    assert not hasattr(settings, "sqlite_path")
    assert not hasattr(settings, "require_sqlite_path")
