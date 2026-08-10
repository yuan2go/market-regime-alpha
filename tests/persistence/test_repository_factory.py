from __future__ import annotations

import os
from datetime import datetime, timezone
from urllib.parse import urlsplit

import pytest

from market_regime_alpha.application.canonical_lifecycle.postgres_repository import (
    PostgresLifecycleRunRepository,
)
from market_regime_alpha.application.continuous_research.postgres_journal import (
    PostgresContinuousResearchJournal,
)
from market_regime_alpha.decision.postgres_repository import (
    PostgresDecisionLifecycleRepository,
)
from market_regime_alpha.persistence.repository_factory import (
    DatabaseBindingError,
    RepositoryFactory,
)
from market_regime_alpha.persistence.settings import (
    DatabaseSettings,
)
from market_regime_alpha.platform.postgres_governance import (
    PostgresExperimentGovernanceRepository,
    PostgresModelRegistryRepository,
)
from tests.persistence.postgres.conftest import (
    TEST_DATABASE_URL_ENV,
    postgres_factory,
)


def _assert_credential_free_locator(
    *, locator: str, configured: DatabaseSettings, schema: str
) -> None:
    source = urlsplit(configured.require_database_url())
    rendered = urlsplit(locator)

    assert rendered.username == source.username
    assert rendered.password == ("***" if source.password is not None else None)
    assert rendered.hostname == source.hostname
    assert rendered.port == source.port
    assert rendered.path == source.path
    assert rendered.query == f"schema={schema}"


def test_repository_factory_builds_postgres_authorities_on_one_pool(
    postgres_factory,
) -> None:
    configured = DatabaseSettings.from_sources(
        database_url=os.environ[TEST_DATABASE_URL_ENV],
        environ={},
    )
    with RepositoryFactory(
        configured, postgres_factory=postgres_factory
    ) as repositories:
        decision = repositories.decision()
        lifecycle = repositories.lifecycle()
        model_registry = repositories.model_registry()
        experiment_governance = repositories.experiment_governance()
        continuous = repositories.continuous_research(
            clock=lambda: datetime(2026, 8, 6, tzinfo=timezone.utc)
        )
        binding = repositories.binding

    assert isinstance(decision, PostgresDecisionLifecycleRepository)
    assert isinstance(lifecycle, PostgresLifecycleRunRepository)
    assert isinstance(model_registry, PostgresModelRegistryRepository)
    assert isinstance(
        experiment_governance,
        PostgresExperimentGovernanceRepository,
    )
    assert isinstance(continuous, PostgresContinuousResearchJournal)
    _assert_credential_free_locator(
        locator=binding.locator,
        configured=configured,
        schema=postgres_factory.application_schema,
    )


def test_postgres_runtime_binding_is_immutable_idempotent_and_credential_free(
    postgres_factory,
) -> None:
    configured = DatabaseSettings.from_sources(
        database_url=os.environ[TEST_DATABASE_URL_ENV],
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
    _assert_credential_free_locator(
        locator=first.locator,
        configured=configured,
        schema=postgres_factory.application_schema,
    )
    with postgres_factory.connection(read_only=True) as connection:
        row = connection.execute(
            "SELECT backend, locator FROM runtime_database_bindings"
        ).fetchone()
    assert row == ("postgres", first.locator)


def test_postgres_continuous_runtime_binding_is_supported(
    postgres_factory,
) -> None:
    configured = DatabaseSettings.from_sources(
        database_url=os.environ[TEST_DATABASE_URL_ENV],
        environ={},
    )
    repositories = RepositoryFactory(configured, postgres_factory=postgres_factory)

    first = repositories.bind_runtime("CONTINUOUS_RESEARCH", "continuous-run-1")
    second = repositories.assert_runtime_binding(
        "CONTINUOUS_RESEARCH", "continuous-run-1"
    )

    assert first == second


def test_postgres_runtime_binding_rejects_authority_mismatch(
    postgres_factory,
) -> None:
    configured = DatabaseSettings.from_sources(
        database_url=os.environ[TEST_DATABASE_URL_ENV],
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
