from __future__ import annotations

from pathlib import Path

import pytest

from scripts.bootstrap_postgres import (
    BootstrapConflictError,
    PostgresBootstrapConfiguration,
    RoleInspection,
    build_application_database_url,
    render_dry_run,
    upsert_env_database_url,
    validate_existing_role,
)


def test_application_url_percent_encodes_generated_password() -> None:
    value = build_application_database_url(
        host="127.0.0.1",
        port=5432,
        password="generated @:/?#[] password",
    )

    assert value.startswith("postgresql://market_regime_alpha:")
    assert "generated @:/?#[] password" not in value
    assert value.endswith("@127.0.0.1:5432/market_regime_alpha")


def test_env_upsert_preserves_unrelated_keys_and_replaces_database_url(
    tmp_path: Path,
) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "TUSHARE_TOKEN=preserve-me\n"
        "MARKET_REGIME_ALPHA_DATABASE_URL=postgresql://old\n",
        encoding="utf-8",
    )

    upsert_env_database_url(env_path, "postgresql://new")

    assert env_path.read_text(encoding="utf-8") == (
        "TUSHARE_TOKEN=preserve-me\n"
        "MARKET_REGIME_ALPHA_DATABASE_URL=postgresql://new\n"
    )


def test_env_upsert_rejects_duplicate_database_keys(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "MARKET_REGIME_ALPHA_DATABASE_URL=postgresql://one\n"
        "MARKET_REGIME_ALPHA_DATABASE_URL=postgresql://two\n",
        encoding="utf-8",
    )

    with pytest.raises(BootstrapConflictError, match="duplicate"):
        upsert_env_database_url(env_path, "postgresql://new")


def test_conflicting_privileged_role_fails_closed() -> None:
    role = RoleInspection(
        name="market_regime_alpha",
        can_login=True,
        is_superuser=True,
        can_create_database=False,
        can_create_role=False,
        can_replicate=False,
    )

    with pytest.raises(BootstrapConflictError, match="unsafe attributes"):
        validate_existing_role(role)


def test_expected_existing_role_is_accepted() -> None:
    role = RoleInspection(
        name="market_regime_alpha",
        can_login=True,
        is_superuser=False,
        can_create_database=False,
        can_create_role=False,
        can_replicate=False,
    )

    validate_existing_role(role)


def test_dry_run_contains_no_password_or_admin_url() -> None:
    configuration = PostgresBootstrapConfiguration(
        admin_database_url=(
            "postgresql://admin_user:admin-secret-example@127.0.0.1:5432/admin_db"
        ),
        env_path=Path(".env"),
    )

    rendered = render_dry_run(configuration)

    assert "admin_user:admin-secret-example" not in rendered
    assert "password" not in rendered.lower()
    assert "market_regime_alpha" in rendered
    assert "127.0.0.1:5432" in rendered
