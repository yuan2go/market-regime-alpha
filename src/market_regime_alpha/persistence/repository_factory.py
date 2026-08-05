"""PostgreSQL-default repository composition with explicit SQLite compatibility."""

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
from market_regime_alpha.application.canonical_lifecycle.sqlite_repository import (
    SQLiteLifecycleRunRepository,
)
from market_regime_alpha.application.controlled_operation.longitudinal_index import (
    LongitudinalOperationalIndex,
    SQLiteLongitudinalOperationalIndex,
)
from market_regime_alpha.application.controlled_operation.postgres_journal import (
    PostgresDecisionTimeOperationJournal,
)
from market_regime_alpha.application.controlled_operation.postgres_longitudinal_index import (
    PostgresLongitudinalOperationalIndex,
)
from market_regime_alpha.application.controlled_operation.sqlite_journal import (
    DEFAULT_CONTROLLED_OPERATION_LEASE,
    SQLiteDecisionTimeOperationJournal,
)
from market_regime_alpha.application.daily_loop.postgres_repository import (
    PostgresDailyRunRepository,
)
from market_regime_alpha.application.daily_loop.sqlite_repository import (
    SQLiteDailyRunRepository,
)
from market_regime_alpha.application.operational_research.postgres_composite_repository import (
    PostgresCompositeOperationalRepository,
)
from market_regime_alpha.application.operational_research.sqlite_composite_repository import (
    SQLiteCompositeOperationalRepository,
)
from market_regime_alpha.application.trading_lifecycle.postgres_risk_reduction import (
    PostgresRiskReductionManualIntentRepository,
)
from market_regime_alpha.application.trading_lifecycle.sqlite_risk_reduction import (
    SQLiteRiskReductionManualIntentRepository,
)
from market_regime_alpha.decision.postgres_repository import (
    PostgresDecisionLifecycleRepository,
)
from market_regime_alpha.decision.sqlite_repository import (
    SQLiteDecisionLifecycleRepository,
)
from market_regime_alpha.execution.postgres_repository import (
    PostgresManualExecutionRepository,
    PostgresTraceableManualExecutionRepository,
)
from market_regime_alpha.execution.sqlite_repository import (
    SQLiteManualExecutionRepository,
)
from market_regime_alpha.execution.sqlite_traceability import (
    SQLiteTraceableManualExecutionRepository,
)
from market_regime_alpha.features.materialization_run import (
    DEFAULT_FEATURE_TASK_LEASE,
    SQLiteFeatureMaterializationRunRepository,
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
    DatabaseBackend,
    DatabaseSettings,
)
from market_regime_alpha.portfolio.postgres_repository import (
    PostgresCompleteAccountPortfolioRiskRepository,
    PostgresPortfolioDecisionRepository,
    PostgresRiskRouteRepository,
)
from market_regime_alpha.portfolio.sqlite_account_authority import (
    SQLiteCompleteAccountPortfolioRiskRepository,
)
from market_regime_alpha.portfolio.sqlite_repository import (
    SQLitePortfolioDecisionRepository,
)
from market_regime_alpha.portfolio.sqlite_risk_routes import (
    SQLiteRiskRouteRepository,
)
from market_regime_alpha.position.postgres_thesis_health import (
    PostgresThesisHealthRepository,
)
from market_regime_alpha.position.sqlite_thesis_health import (
    SQLiteThesisHealthRepository,
)
from market_regime_alpha.platform.postgres_governance import (
    PostgresExperimentGovernanceRepository,
    PostgresModelRegistryRepository,
)
from market_regime_alpha.platform.sqlite_governance import (
    SQLiteExperimentGovernanceRepository,
    SQLiteModelRegistryRepository,
)


Clock = Callable[[], datetime]


@dataclass(frozen=True, slots=True)
class DatabaseBinding:
    backend: DatabaseBackend
    locator: str


class DatabaseBindingError(ValueError):
    """Raised when a persisted runtime selects a different authority."""


class RepositoryFactory:
    """Own backend resources and construct repositories for one authority."""

    def __init__(
        self,
        settings: DatabaseSettings,
        *,
        postgres_factory: PostgresConnectionFactory | None = None,
    ) -> None:
        if not isinstance(settings, DatabaseSettings):
            raise TypeError("settings must be DatabaseSettings")
        self.settings = settings
        if (
            postgres_factory is not None
            and settings.backend is not DatabaseBackend.POSTGRES
        ):
            raise ValueError("PostgreSQL factory cannot back SQLite settings")
        self._owns_postgres = postgres_factory is None
        self._postgres = postgres_factory
        if self._postgres is None and settings.backend is DatabaseBackend.POSTGRES:
            self._postgres = PostgresConnectionFactory(settings)

    @property
    def binding(self) -> DatabaseBinding:
        if self.settings.backend is DatabaseBackend.POSTGRES:
            locator = _postgres_binding_locator(
                self.settings.require_database_url(),
                application_schema=self.postgres_factory.application_schema,
            )
        else:
            locator = str(self.settings.require_sqlite_path())
        return DatabaseBinding(self.settings.backend, locator)

    @property
    def postgres_factory(self) -> PostgresConnectionFactory:
        if self._postgres is None:
            raise ValueError("PostgreSQL factory requested for SQLite compatibility")
        return self._postgres

    def daily(self):
        if self._postgres is not None:
            return PostgresDailyRunRepository(self._postgres)
        return SQLiteDailyRunRepository(self.settings.require_sqlite_path())

    def decision(self):
        if self._postgres is not None:
            return PostgresDecisionLifecycleRepository(self._postgres)
        return SQLiteDecisionLifecycleRepository(self.settings.require_sqlite_path())

    def portfolio(self):
        if self._postgres is not None:
            return PostgresPortfolioDecisionRepository(self._postgres)
        return SQLitePortfolioDecisionRepository(self.settings.require_sqlite_path())

    def complete_account_portfolio(self):
        if self._postgres is not None:
            return PostgresCompleteAccountPortfolioRiskRepository(self._postgres)
        return SQLiteCompleteAccountPortfolioRiskRepository(
            self.settings.require_sqlite_path()
        )

    def risk_route(self):
        if self._postgres is not None:
            return PostgresRiskRouteRepository(self._postgres)
        return SQLiteRiskRouteRepository(self.settings.require_sqlite_path())

    def manual_execution(self):
        if self._postgres is not None:
            return PostgresManualExecutionRepository(self._postgres)
        return SQLiteManualExecutionRepository(self.settings.require_sqlite_path())

    def traceable_execution(self):
        if self._postgres is not None:
            return PostgresTraceableManualExecutionRepository(self._postgres)
        return SQLiteTraceableManualExecutionRepository(
            self.settings.require_sqlite_path()
        )

    def risk_reduction_manual_intent(self):
        if self._postgres is not None:
            return PostgresRiskReductionManualIntentRepository(self._postgres)
        return SQLiteRiskReductionManualIntentRepository(
            self.settings.require_sqlite_path()
        )

    def thesis_health(self):
        if self._postgres is not None:
            return PostgresThesisHealthRepository(self._postgres)
        return SQLiteThesisHealthRepository(self.settings.require_sqlite_path())

    def composite(self):
        if self._postgres is not None:
            return PostgresCompositeOperationalRepository(self._postgres)
        return SQLiteCompositeOperationalRepository(
            self.settings.require_sqlite_path()
        )

    def model_registry(self):
        if self._postgres is not None:
            return PostgresModelRegistryRepository(self._postgres)
        return SQLiteModelRegistryRepository(self.settings.require_sqlite_path())

    def experiment_governance(self):
        if self._postgres is not None:
            return PostgresExperimentGovernanceRepository(self._postgres)
        return SQLiteExperimentGovernanceRepository(
            self.settings.require_sqlite_path()
        )

    def lifecycle(self, *, read_only: bool = False) -> LifecycleRunRepository:
        if self._postgres is not None:
            return PostgresLifecycleRunRepository(
                self._postgres,
                read_only=read_only,
            )
        return SQLiteLifecycleRunRepository(
            self.settings.require_sqlite_path(),
            read_only=read_only,
        )

    def feature_materialization(
        self,
        *,
        clock: Clock,
        lease_duration: timedelta = DEFAULT_FEATURE_TASK_LEASE,
    ):
        if self._postgres is not None:
            return PostgresFeatureMaterializationRunRepository(
                self._postgres,
                clock=clock,
                lease_duration=lease_duration,
            )
        return SQLiteFeatureMaterializationRunRepository(
            self.settings.require_sqlite_path(),
            clock=clock,
            lease_duration=lease_duration,
        )

    def feature_materialization_for_path(
        self,
        path: Path,
        clock: Clock | None,
        lease_duration: timedelta,
    ):
        resolved_clock = clock or _utc_now
        if self._postgres is not None:
            return PostgresFeatureMaterializationRunRepository(
                self._postgres,
                clock=resolved_clock,
                lease_duration=lease_duration,
            )
        return SQLiteFeatureMaterializationRunRepository(
            path,
            clock=resolved_clock,
            lease_duration=lease_duration,
        )

    def controlled_operation(
        self,
        *,
        clock: Clock,
        lease_duration: timedelta = DEFAULT_CONTROLLED_OPERATION_LEASE,
    ):
        if self._postgres is not None:
            return PostgresDecisionTimeOperationJournal(
                self._postgres,
                clock=clock,
                lease_duration=lease_duration,
            )
        return SQLiteDecisionTimeOperationJournal(
            self.settings.require_sqlite_path(),
            clock=clock,
            lease_duration=lease_duration,
        )

    def longitudinal(self, *, clock: Clock) -> LongitudinalOperationalIndex:
        if self._postgres is not None:
            return PostgresLongitudinalOperationalIndex(
                self._postgres,
                clock=clock,
            )
        return SQLiteLongitudinalOperationalIndex(
            self.settings.require_sqlite_path(),
            clock=clock,
        )

    def controlled_canonical_repository(
        self,
        path: Path,
        read_only: bool,
    ) -> LifecycleRunRepository:
        if self._postgres is not None:
            return PostgresLifecycleRunRepository(
                self._postgres,
                read_only=read_only,
            )
        return SQLiteLifecycleRunRepository(path, read_only=read_only)

    def bind_runtime(self, scope_type: str, scope_id: str) -> DatabaseBinding:
        """Persist one immutable PostgreSQL run-to-authority binding.

        SQLite compatibility is already physically path-bound: selecting another
        file cannot retrieve the run. PostgreSQL needs an explicit row because
        multiple authorities can share the same connection interface.
        """

        _validate_runtime_binding_key(scope_type, scope_id)
        binding = self.binding
        if self._postgres is None:
            return binding
        PostgresMigrator().apply_all(self._postgres)
        with self._postgres.connection() as connection:
            connection.execute(
                """
                INSERT INTO runtime_database_bindings(
                    scope_type, scope_id, backend, locator, created_at
                ) VALUES (%s, %s, %s, %s, now())
                ON CONFLICT (scope_type, scope_id) DO NOTHING
                """,
                (scope_type, scope_id, binding.backend.value, binding.locator),
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
        if self._postgres is None:
            return binding
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
        if self._postgres is not None and self._owns_postgres:
            self._postgres.close()

    def __enter__(self) -> RepositoryFactory:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def add_database_arguments(
    parser: argparse.ArgumentParser,
    *,
    legacy_sqlite_flag: str | None = None,
) -> None:
    parser.add_argument("--database-url")
    parser.add_argument("--sqlite-database", type=Path)
    if legacy_sqlite_flag is not None:
        parser.add_argument(
            legacy_sqlite_flag,
            dest="legacy_sqlite_database",
            type=Path,
            help=argparse.SUPPRESS,
        )


def settings_from_namespace(
    args: argparse.Namespace,
    *,
    dotenv_path: Path = Path(".env"),
) -> DatabaseSettings:
    sqlite_path = getattr(args, "sqlite_database", None)
    legacy_path = getattr(args, "legacy_sqlite_database", None)
    if sqlite_path is not None and legacy_path is not None:
        raise ValueError("select only one explicit SQLite compatibility path")
    selected_path = sqlite_path if sqlite_path is not None else legacy_path
    environment = dict(os.environ)
    if DATABASE_URL_ENV not in environment:
        value = _read_dotenv_value(dotenv_path, DATABASE_URL_ENV)
        if value is not None:
            environment[DATABASE_URL_ENV] = value
    return DatabaseSettings.from_sources(
        database_url=getattr(args, "database_url", None),
        sqlite_path=selected_path,
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
    userinfo = f"{username}:***@" if parts.password is not None else (
        f"{username}@" if username else ""
    )
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
    }:
        raise ValueError("unsupported runtime database binding scope")
    if not isinstance(scope_id, str) or not scope_id.strip():
        raise ValueError("runtime database binding scope ID must be non-empty")


def _assert_database_binding(
    expected: DatabaseBinding,
    stored_backend: str,
    stored_locator: str,
) -> None:
    if (
        stored_backend != expected.backend.value
        or stored_locator != expected.locator
    ):
        raise DatabaseBindingError(
            "runtime database authority does not match the stored binding"
        )


__all__ = [
    "DatabaseBinding",
    "DatabaseBindingError",
    "RepositoryFactory",
    "add_database_arguments",
    "settings_from_namespace",
]
