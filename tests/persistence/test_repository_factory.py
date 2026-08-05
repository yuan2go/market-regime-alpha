from __future__ import annotations

import os
from pathlib import Path

import pytest

from market_regime_alpha.application.canonical_lifecycle.postgres_repository import (
    PostgresLifecycleRunRepository,
)
from market_regime_alpha.application.canonical_lifecycle.sqlite_repository import (
    SQLiteLifecycleRunRepository,
)
from market_regime_alpha.decision.postgres_repository import (
    PostgresDecisionLifecycleRepository,
)
from market_regime_alpha.decision.sqlite_repository import (
    SQLiteDecisionLifecycleRepository,
)
from market_regime_alpha.persistence.repository_factory import (
    DatabaseBindingError,
    RepositoryFactory,
)
from market_regime_alpha.persistence.settings import (
    DatabaseBackend,
    DatabaseSettings,
)
from tests.persistence.postgres.conftest import (
    TEST_DATABASE_URL_ENV,
    postgres_factory,
)


def test_repository_factory_builds_postgres_authorities_on_one_pool(
    postgres_factory,
) -> None:
    configured = DatabaseSettings.from_sources(
        database_url=os.environ[TEST_DATABASE_URL_ENV],
        sqlite_path=None,
        environ={},
    )
    with RepositoryFactory(
        configured, postgres_factory=postgres_factory
    ) as repositories:
        decision = repositories.decision()
        lifecycle = repositories.lifecycle()
        binding = repositories.binding

    assert isinstance(decision, PostgresDecisionLifecycleRepository)
    assert isinstance(lifecycle, PostgresLifecycleRunRepository)
    assert binding.backend is DatabaseBackend.POSTGRES
    assert "***" in binding.locator
    assert configured.require_database_url() not in binding.locator


def test_repository_factory_keeps_sqlite_explicit_and_path_bound(
    tmp_path: Path,
) -> None:
    path = tmp_path / "compatibility.sqlite3"
    settings = DatabaseSettings.from_sources(
        database_url=None,
        sqlite_path=path,
        environ={},
    )
    with RepositoryFactory(settings) as repositories:
        decision = repositories.decision()
        lifecycle = repositories.lifecycle()

    assert isinstance(decision, SQLiteDecisionLifecycleRepository)
    assert isinstance(lifecycle, SQLiteLifecycleRunRepository)
    assert repositories.binding.backend is DatabaseBackend.SQLITE
    assert repositories.binding.locator == str(path.resolve())


def test_postgres_runtime_binding_is_immutable_idempotent_and_credential_free(
    postgres_factory,
) -> None:
    configured = DatabaseSettings.from_sources(
        database_url=os.environ[TEST_DATABASE_URL_ENV],
        sqlite_path=None,
        environ={},
    )
    repositories = RepositoryFactory(
        configured,
        postgres_factory=postgres_factory,
    )
    repositories.lifecycle()

    first = repositories.bind_runtime("CANONICAL_LIFECYCLE", "run-1")
    second = repositories.bind_runtime("CANONICAL_LIFECYCLE", "run-1")
    asserted = repositories.assert_runtime_binding(
        "CANONICAL_LIFECYCLE",
        "run-1",
    )

    assert first == second == asserted
    assert first.locator == repositories.binding.locator
    assert configured.require_database_url() not in first.locator
    with postgres_factory.connection(read_only=True) as connection:
        row = connection.execute(
            "SELECT backend, locator FROM runtime_database_bindings"
        ).fetchone()
    assert row == (first.backend.value, first.locator)


def test_postgres_runtime_binding_rejects_authority_mismatch(
    postgres_factory,
) -> None:
    configured = DatabaseSettings.from_sources(
        database_url=os.environ[TEST_DATABASE_URL_ENV],
        sqlite_path=None,
        environ={},
    )
    repositories = RepositoryFactory(
        configured,
        postgres_factory=postgres_factory,
    )
    repositories.lifecycle()
    with postgres_factory.connection() as connection:
        connection.execute(
            """
            INSERT INTO runtime_database_bindings(
                scope_type, scope_id, backend, locator, created_at
            ) VALUES (%s, %s, %s, %s, now())
            """,
            (
                "CONTROLLED_OPERATION",
                "run-mismatch",
                "postgres",
                "postgresql://other:***@127.0.0.1/other?schema=other",
            ),
        )

    with pytest.raises(DatabaseBindingError, match="does not match"):
        repositories.assert_runtime_binding(
            "CONTROLLED_OPERATION",
            "run-mismatch",
        )


__all__ = ["postgres_factory"]
