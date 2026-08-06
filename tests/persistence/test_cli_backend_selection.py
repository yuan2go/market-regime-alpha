from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from market_regime_alpha.persistence.repository_factory import (
    add_database_arguments,
    settings_from_namespace,
)
from market_regime_alpha.persistence.settings import (
    DATABASE_URL_ENV,
    DatabaseConfigurationError,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    add_database_arguments(parser)
    return parser


def test_cli_selection_defaults_to_dotenv_postgres_and_allows_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(DATABASE_URL_ENV, raising=False)
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        f"{DATABASE_URL_ENV}=postgresql://app:secret@127.0.0.1:5432/app\n",
        encoding="utf-8",
    )
    default = settings_from_namespace(_parser().parse_args([]), dotenv_path=dotenv)
    explicit = settings_from_namespace(
        _parser().parse_args(
            ["--database-url", "postgresql://other:pw@db.example/authority"]
        ),
        dotenv_path=dotenv,
    )

    assert default.require_database_url().endswith("127.0.0.1:5432/app")
    assert explicit.require_database_url() == (
        "postgresql://other:pw@db.example/authority"
    )


def test_cli_selection_requires_postgres_and_rejects_sqlite_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(DATABASE_URL_ENV, raising=False)
    missing = _parser().parse_args([])
    with pytest.raises(DatabaseConfigurationError, match="PostgreSQL configuration"):
        settings_from_namespace(missing, dotenv_path=tmp_path / "missing.env")

    for arguments in (
        ["--sqlite-database", str(tmp_path / "compatibility.postgres-scope")],
        ["--database", str(tmp_path / "compatibility.postgres-scope")],
    ):
        with pytest.raises(SystemExit):
            _parser().parse_args(arguments)

    sqlite_url = _parser().parse_args(
        ["--database-url", "postgresql:///tmp/compatibility.postgres-scope"]
    )
    with pytest.raises(DatabaseConfigurationError, match="PostgreSQL URL"):
        settings_from_namespace(
            sqlite_url,
            dotenv_path=tmp_path / "missing.env",
        )
