"""PostgreSQL-only repository composition."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta
import os
from pathlib import Path
from typing import Callable
from urllib.parse import SplitResult, urlsplit, urlunsplit

from market_regime_alpha.application.canonical_lifecycle.postgres_repository import (
    PostgresLifecycleRunRepository,
)
from market_regime_alpha.application.canonical_lifecycle.repositories import (
    LifecycleRunRepository,
)
from market_regime_alpha.application.controlled_operation.longitudinal_index import (
    LongitudinalOperationalIndex,
)
from market_regime_alpha.application.controlled_operation.postgres_journal import (
    DEFAULT_CONTROLLED_OPERATION_LEASE,
    PostgresDecisionTimeOperationJournal,
)
from market_regime_alpha.application.controlled_operation.postgres_longitudinal_index import (
    PostgresLongitudinalOperationalIndex,
)
from market_regime_alpha.application.continuous_research.postgres_journal import (
    DEFAULT_CONTINUOUS_TICK_LEASE,
    PostgresContinuousResearchJournal,
)
from market_regime_alpha.application.daily_loop.postgres_repository import (
    PostgresDailyRunRepository,
)
from market_regime_alpha.application.decision_system.postgres_repository import (
    PostgresDecisionSystemRepository,
)
from market_regime_alpha.application.operational_research.postgres_composite_repository import (
    PostgresCompositeOperationalRepository,
)
from market_regime_alpha.application.trading_lifecycle.postgres_risk_reduction import (
    PostgresRiskReductionManualIntentRepository,
)
from market_regime_alpha.data.pit_artifact_authority import (
    PITArtifactAuthorityResolver,
)
from market_regime_alpha.data.pit_authority import ProviderQualificationPolicy
from market_regime_alpha.data.postgres_pit_authority import PostgresPITAuthority
from market_regime_alpha.decision.postgres_repository import (
    PostgresDecisionLifecycleRepository,
)
from market_regime_alpha.execution.postgres_repository import (
    PostgresManualExecutionRepository,
    PostgresTraceableManualExecutionRepository,
)
from market_regime_alpha.features.materialization_run import (
    DEFAULT_FEATURE_TASK_LEASE,
)
from market_regime_alpha.features.postgres_materialization_run import (
    PostgresFeatureMaterializationRunRepository,
)
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.postgres.migrator import PostgresMigrator
from market_regime_alpha.persistence.settings import (
    DATABASE_URL_ENV,
    DatabaseSettings,
)
from market_regime_alpha.portfolio.postgres_repository import (
    PostgresCompleteAccountPortfolioRiskRepository,
    PostgresPortfolioDecisionRepository,
    PostgresRiskRouteRepository,
)
from market_regime_alpha.position.postgres_thesis_health import (
    PostgresThesisHealthRepository,
)
from market_regime_alpha.platform.postgres_governance import (
    PostgresExperimentGovernanceRepository,
)
from market_regime_alpha.platform.postgres_runtime_governance import (
    PostgresModelGovernanceRepository,
)


Clock = Callable[[], datetime]


@dataclass(frozen=True, slots=True)
class DatabaseBinding:
    locator: str


class DatabaseBindingError(ValueError):
    """Raised when a persisted runtime selects a different authority."""


class RepositoryFactory:
    """Own PostgreSQL resources and construct native bounded repositories."""

    def __init__(
        self,
        settings: DatabaseSettings,
        *,
        postgres_factory: PostgresConnectionFactory | None = None,
    ) -> None:
        if not isinstance(settings, DatabaseSettings):
            raise TypeError("settings must be DatabaseSettings")
        self.settings = settings
        self._owns_postgres = postgres_factory is None
        self._postgres = postgres_factory or PostgresConnectionFactory(
            settings,
            application_schema=settings.application_schema,
        )

    @property
    def binding(self) -> DatabaseBinding:
        locator = _postgres_binding_locator(
            self.settings.require_database_url(),
            application_schema=self.postgres_factory.application_schema,
        )
        return DatabaseBinding(locator)

    @property
    def postgres_factory(self) -> PostgresConnectionFactory:
        return self._postgres

    def daily(self):
        return PostgresDailyRunRepository(self._postgres)

    def decision_system(self, *, clock: Clock | None = None):
        return PostgresDecisionSystemRepository(
            self._postgres,
            clock=clock or _utc_now,
        )

    def state_system(self, *, clock: Clock | None = None):
        from market_regime_alpha.application.state_system.postgres_repository import (
            PostgresStateSystemRepository,
        )

        return PostgresStateSystemRepository(
            self._postgres,
            clock=clock or _utc_now,
        )

    def multi_strategy(self):
        from market_regime_alpha.strategies.postgres_repository import (
            PostgresMultiStrategyRepository,
        )

        return PostgresMultiStrategyRepository(self._postgres)

    def strategy_shadow(self):
        from market_regime_alpha.application.strategy_shadow.postgres_repository import (
            PostgresStrategyShadowRepository,
        )

        return PostgresStrategyShadowRepository(self._postgres)

    def decision(self):
        return PostgresDecisionLifecycleRepository(self._postgres)

    def portfolio(self):
        return PostgresPortfolioDecisionRepository(self._postgres)

    def complete_account_portfolio(self):
        return PostgresCompleteAccountPortfolioRiskRepository(self._postgres)

    def risk_route(self):
        return PostgresRiskRouteRepository(self._postgres)

    def manual_execution(self):
        return PostgresManualExecutionRepository(self._postgres)

    def traceable_execution(self):
        return PostgresTraceableManualExecutionRepository(self._postgres)

    def risk_reduction_manual_intent(self):
        return PostgresRiskReductionManualIntentRepository(self._postgres)

    def thesis_health(self):
        return PostgresThesisHealthRepository(self._postgres)

    def composite(self):
        return PostgresCompositeOperationalRepository(self._postgres)

    def model_registry(self):
        return PostgresModelGovernanceRepository(self._postgres)

    def model_governance(self):
        return PostgresModelGovernanceRepository(self._postgres)

    def runtime_scope(self):
        from market_regime_alpha.universe.postgres_runtime_scope import (
            PostgresRuntimeScopeRepository,
        )

        return PostgresRuntimeScopeRepository(self._postgres)

    def shadow_performance(self):
        from market_regime_alpha.application.strategy_shadow.postgres_performance import (
            PostgresPortfolioPerformanceRepository,
        )

        return PostgresPortfolioPerformanceRepository(self._postgres)

    def shadow_observations(self):
        from market_regime_alpha.application.strategy_shadow.postgres_observations import (
            PostgresShadowObservationRepository,
        )

        return PostgresShadowObservationRepository(self._postgres)

    def research_models(self):
        from market_regime_alpha.application.research_validation.postgres_research_model import (
            PostgresResearchModelRepository,
        )

        return PostgresResearchModelRepository(self._postgres)

    def formal_execution(self):
        from market_regime_alpha.application.research_validation.postgres_formal_execution import (
            PostgresFormalExecutionRepository,
        )

        return PostgresFormalExecutionRepository(self._postgres)

    def pit_authority(
        self,
        *,
        clock: Clock | None = None,
        artifact_resolver: PITArtifactAuthorityResolver | None = None,
        provider_policy: ProviderQualificationPolicy | None = None,
    ):
        return PostgresPITAuthority(
            self._postgres,
            clock=clock,
            artifact_resolver=artifact_resolver,
            provider_policy=provider_policy,
        )

    def experiment_governance(self):
        return PostgresExperimentGovernanceRepository(self._postgres)

    def free_data_blocked(self):
        from market_regime_alpha.application.free_data_operation.postgres_blocked import (
            PostgresFreeDataBlockedRepository,
        )

        return PostgresFreeDataBlockedRepository(self._postgres)

    def lifecycle(self, *, read_only: bool = False) -> LifecycleRunRepository:
        return PostgresLifecycleRunRepository(
            self._postgres,
            read_only=read_only,
        )

    def feature_materialization(
        self,
        *,
        clock: Clock,
        lease_duration: timedelta = DEFAULT_FEATURE_TASK_LEASE,
    ):
        return PostgresFeatureMaterializationRunRepository(
            self._postgres,
            clock=clock,
            lease_duration=lease_duration,
        )

    def feature_materialization_for_path(
        self,
        clock: Clock | None,
        lease_duration: timedelta,
    ):
        resolved_clock = clock or _utc_now
        return PostgresFeatureMaterializationRunRepository(
            self._postgres,
            clock=resolved_clock,
            lease_duration=lease_duration,
        )

    def controlled_operation(
        self,
        *,
        clock: Clock,
        lease_duration: timedelta = DEFAULT_CONTROLLED_OPERATION_LEASE,
    ):
        return PostgresDecisionTimeOperationJournal(
            self._postgres,
            clock=clock,
            lease_duration=lease_duration,
        )

    def continuous_research(
        self,
        *,
        clock: Clock,
        lease_duration: timedelta = DEFAULT_CONTINUOUS_TICK_LEASE,
    ) -> PostgresContinuousResearchJournal:
        return PostgresContinuousResearchJournal(
            self._postgres,
            clock=clock,
            lease_duration=lease_duration,
        )

    def historical_research(
        self,
        *,
        clock: Clock,
        lease_duration: timedelta,
    ):
        from market_regime_alpha.application.historical_research.postgres_journal import (
            PostgresHistoricalResearchJournal,
        )

        return PostgresHistoricalResearchJournal(
            self._postgres,
            clock=clock,
            lease_duration=lease_duration,
        )

    def longitudinal(self, *, clock: Clock) -> LongitudinalOperationalIndex:
        return PostgresLongitudinalOperationalIndex(
            self._postgres,
            clock=clock,
        )

    def controlled_canonical_repository(
        self,
        read_only: bool,
    ) -> LifecycleRunRepository:
        return PostgresLifecycleRunRepository(
            self._postgres,
            read_only=read_only,
        )

    def bind_runtime(self, scope_type: str, scope_id: str) -> DatabaseBinding:
        """Persist one immutable PostgreSQL run-to-authority binding.

        Multiple schemas can share one connection interface, so the binding is
        persisted explicitly without credentials.
        """

        _validate_runtime_binding_key(scope_type, scope_id)
        binding = self.binding
        PostgresMigrator().apply_all(self._postgres)
        with self._postgres.connection() as connection:
            connection.execute(
                """
                INSERT INTO runtime_database_bindings(
                    scope_type, scope_id, backend, locator, created_at
                ) VALUES (%s, %s, %s, %s, now())
                ON CONFLICT (scope_type, scope_id) DO NOTHING
                """,
                (scope_type, scope_id, "postgres", binding.locator),
            )
            row = connection.execute(
                """
                SELECT backend, locator
                FROM runtime_database_bindings
                WHERE scope_type = %s AND scope_id = %s
                """,
                (scope_type, scope_id),
            ).fetchone()
        if row is None:
            raise DatabaseBindingError("runtime database binding was not durable")
        _assert_database_binding(binding, str(row[0]), str(row[1]))
        return binding

    def assert_runtime_binding(
        self,
        scope_type: str,
        scope_id: str,
    ) -> DatabaseBinding:
        """Reject a PostgreSQL resume/replay against another stored authority."""

        _validate_runtime_binding_key(scope_type, scope_id)
        binding = self.binding
        PostgresMigrator().apply_all(self._postgres)
        with self._postgres.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT backend, locator
                FROM runtime_database_bindings
                WHERE scope_type = %s AND scope_id = %s
                """,
                (scope_type, scope_id),
            ).fetchone()
        if row is None:
            raise DatabaseBindingError("runtime database binding is missing")
        _assert_database_binding(binding, str(row[0]), str(row[1]))
        return binding

    def close(self) -> None:
        if self._owns_postgres:
            self._postgres.close()

    def __enter__(self) -> RepositoryFactory:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def add_database_arguments(
    parser: argparse.ArgumentParser,
) -> None:
    parser.allow_abbrev = False
    parser.add_argument("--database-url")
    parser.add_argument("--database-schema")


def settings_from_namespace(
    args: argparse.Namespace,
    *,
    dotenv_path: Path = Path(".env"),
) -> DatabaseSettings:
    environment = dict(os.environ)
    if DATABASE_URL_ENV not in environment:
        value = _read_dotenv_value(dotenv_path, DATABASE_URL_ENV)
        if value is not None:
            environment[DATABASE_URL_ENV] = value
    return DatabaseSettings.from_sources(
        database_url=getattr(args, "database_url", None),
        application_schema=getattr(args, "database_schema", None),
        environ=environment,
    )


def _read_dotenv_value(path: Path, name: str) -> str | None:
    if not path.is_file():
        return None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() == name:
            normalized = value.strip().strip('"').strip("'")
            return normalized or None
    return None


def _utc_now() -> datetime:
    from datetime import timezone

    return datetime.now(timezone.utc)


def _postgres_binding_locator(
    database_url: str,
    *,
    application_schema: str,
) -> str:
    """Build a stable credential-free locator for persisted run bindings."""

    parts = urlsplit(database_url)
    username = parts.username or ""
    userinfo = f"{username}:***@" if parts.password is not None else (f"{username}@" if username else "")
    hostname = parts.hostname or ""
    rendered_host = f"[{hostname}]" if ":" in hostname else hostname
    hostinfo = f"{rendered_host}:{parts.port}" if parts.port is not None else rendered_host
    return urlunsplit(
        SplitResult(
            scheme=parts.scheme,
            netloc=f"{userinfo}{hostinfo}",
            path=parts.path,
            query=f"schema={application_schema}",
            fragment="",
        )
    )


def _validate_runtime_binding_key(scope_type: str, scope_id: str) -> None:
    if scope_type not in {
        "CANONICAL_LIFECYCLE",
        "CONTROLLED_OPERATION",
        "DAILY_LOOP",
        "FREE_DATA_OPERATION",
        "CONTINUOUS_RESEARCH",
    }:
        raise ValueError("unsupported runtime database binding scope")
    if not isinstance(scope_id, str) or not scope_id.strip():
        raise ValueError("runtime database binding scope ID must be non-empty")


def _assert_database_binding(
    expected: DatabaseBinding,
    stored_backend: str,
    stored_locator: str,
) -> None:
    if stored_backend != "postgres" or stored_locator != expected.locator:
        raise DatabaseBindingError("runtime database authority does not match the stored binding")


__all__ = [
    "DatabaseBinding",
    "DatabaseBindingError",
    "RepositoryFactory",
    "add_database_arguments",
    "settings_from_namespace",
]
