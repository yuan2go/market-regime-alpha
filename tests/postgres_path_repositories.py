"""Path-keyed PostgreSQL schema isolation for legacy-shaped test setup only.

The supplied path is an opaque test-scope key. No file database is created or read.
Every returned repository is a native PostgreSQL repository.
"""

from __future__ import annotations

import atexit
from collections import OrderedDict
from contextlib import contextmanager
from datetime import datetime, timedelta
import os
from pathlib import Path
import re
from threading import Lock
from typing import Any, Callable, Iterable, Iterator, TypeVar
from uuid import uuid4

import psycopg
from psycopg import sql

from market_regime_alpha.application.canonical_lifecycle.postgres_repository import (
    PostgresLifecycleRunRepository as _Lifecycle,
)
from market_regime_alpha.application.controlled_operation.postgres_journal import (
    ControlledOperationClaimRejected,
    ControlledOperationConflict,
    PostgresDecisionTimeOperationJournal as _Controlled,
)
from market_regime_alpha.application.controlled_operation.postgres_longitudinal_index import (
    PostgresLongitudinalOperationalIndex as _Longitudinal,
)
from market_regime_alpha.application.daily_loop.postgres_repository import (
    PostgresDailyRunRepository as _Daily,
)
from market_regime_alpha.application.operational_research.postgres_composite_repository import (
    PostgresCompositeOperationalRepository as _Composite,
)
from market_regime_alpha.application.state_system.postgres_repository import (
    PostgresStateSystemRepository as _State,
)
from market_regime_alpha.application.trading_lifecycle.postgres_risk_reduction import (
    PostgresRiskReductionManualIntentRepository as _RiskReduction,
)
from market_regime_alpha.decision.postgres_repository import (
    PostgresDecisionLifecycleRepository as _Decision,
)
from market_regime_alpha.execution.postgres_manual_repository import (
    PostgresManualExecutionRepository as _ManualExecution,
    insert_manual_trade_event,
    load_manual_trade_projection,
    restore_manual_execution_json,
    serialize_manual_execution_json,
)
from market_regime_alpha.execution.postgres_traceability import (
    PostgresTraceableManualExecutionRepository as _TraceableExecution,
)
from market_regime_alpha.features.postgres_materialization_run import (
    PostgresFeatureMaterializationRunRepository as _Feature,
)
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.repository_factory import RepositoryFactory
from market_regime_alpha.persistence.settings import DatabaseSettings
from market_regime_alpha.platform.postgres_governance import (
    PostgresExperimentGovernanceRepository as _Experiment,
    PostgresModelRegistryRepository as _Model,
)
from market_regime_alpha.portfolio.postgres_account_authority import (
    PostgresCompleteAccountPortfolioRiskRepository as _CompleteAccount,
)
from market_regime_alpha.portfolio.postgres_decision_repository import (
    PostgresPortfolioDecisionRepository as _Portfolio,
)
from market_regime_alpha.portfolio.postgres_risk_routes import (
    PostgresRiskRouteRepository as _RiskRoute,
)
from market_regime_alpha.position.postgres_thesis_health import (
    PostgresThesisHealthRepository as _ThesisHealth,
)


_DATABASE_URL_ENV = "MARKET_REGIME_ALPHA_TEST_DATABASE_URL"
_SCHEMA = re.compile(r"^test_path_[0-9a-f]{32}$")
_LOCK = Lock()
_MAX_CACHED_FACTORIES = 8
_SCHEMAS: dict[str, str] = {}
_FACTORIES: OrderedDict[str, PostgresConnectionFactory] = OrderedDict()
_RepositoryT = TypeVar("_RepositoryT")


def _factory(path: str | Path) -> PostgresConnectionFactory:
    key = str(Path(path).resolve())
    with _LOCK:
        existing = _FACTORIES.get(key)
        if existing is not None:
            _FACTORIES.move_to_end(key)
            return existing
        database_url = os.getenv(_DATABASE_URL_ENV)
        if not database_url:
            raise RuntimeError(
                f"{_DATABASE_URL_ENV} is required; PostgreSQL tests never skip"
            )
        schema = _SCHEMAS.get(key)
        if schema is None:
            schema = f"test_path_{uuid4().hex}"
            with psycopg.connect(database_url, autocommit=True) as connection:
                connection.execute(
                    sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema))
                )
            _SCHEMAS[key] = schema
        factory = PostgresConnectionFactory(
            DatabaseSettings.from_sources(database_url=database_url, environ={}),
            min_size=0,
            max_size=4,
            application_schema=schema,
        )
        _FACTORIES[key] = factory
        if len(_FACTORIES) > _MAX_CACHED_FACTORIES:
            _, expired = _FACTORIES.popitem(last=False)
            expired.close()
        return factory


def _cleanup() -> None:
    with _LOCK:
        factories = tuple(_FACTORIES.values())
        _FACTORIES.clear()
        schemas = tuple(_SCHEMAS.values())
        _SCHEMAS.clear()
    database_url = os.getenv(_DATABASE_URL_ENV)
    for factory in factories:
        factory.close()
    for schema in schemas:
        if database_url and _SCHEMA.fullmatch(schema):
            with psycopg.connect(database_url, autocommit=True) as connection:
                connection.execute(
                    sql.SQL("DROP SCHEMA {} CASCADE").format(
                        sql.Identifier(schema)
                    )
                )


atexit.register(_cleanup)


def _bind_test_scope(
    repository: _RepositoryT,
    path: str | Path,
) -> _RepositoryT:
    """Expose the opaque scope key for restart/corruption tests only."""

    setattr(repository, "path", Path(path))
    return repository


@contextmanager
def postgres_connection(
    path: str | Path,
    *,
    read_only: bool = False,
) -> Iterator[psycopg.Connection[Any]]:
    """Open a native psycopg connection in the path-keyed isolated schema."""

    with _factory(path).connection(read_only=read_only) as connection:
        yield connection


def postgres_factory(path: str | Path) -> PostgresConnectionFactory:
    """Return the native factory for an isolated test scope."""

    return _factory(path)


def postgres_cli_arguments(path: str | Path) -> list[str]:
    """Render explicit CLI authority arguments for one isolated schema."""

    database_url = os.getenv(_DATABASE_URL_ENV)
    if not database_url:
        raise RuntimeError(
            f"{_DATABASE_URL_ENV} is required; PostgreSQL tests never skip"
        )
    return [
        "--database-url",
        database_url,
        "--database-schema",
        _factory(path).application_schema,
    ]


def bind_postgres_runtime(
    path: str | Path,
    *,
    scope_type: str,
    scope_id: str,
) -> None:
    """Persist the same runtime binding that a PostgreSQL composition root owns."""

    database_url = os.getenv(_DATABASE_URL_ENV)
    if not database_url:
        raise RuntimeError(
            f"{_DATABASE_URL_ENV} is required; PostgreSQL tests never skip"
        )
    factory = _factory(path)
    RepositoryFactory(
        DatabaseSettings.from_sources(
            database_url=database_url,
            application_schema=factory.application_schema,
            environ={},
        ),
        postgres_factory=factory,
    ).bind_runtime(scope_type, scope_id)


def controlled_runner_dependencies(
    path: str | Path,
    *,
    clock: Callable[[], datetime],
) -> dict[str, object]:
    """Compose one-schema PostgreSQL dependencies for Controlled Runtime tests."""

    return {
        "longitudinal_index": PostgresLongitudinalOperationalIndex(
            path,
            clock=clock,
        ),
        "canonical_repository_factory": lambda read_only: (
            PostgresLifecycleRunRepository(path, read_only=read_only)
        ),
        "feature_repository_factory": lambda repository_clock, lease: (
            PostgresFeatureMaterializationRunRepository(
                path,
                clock=repository_clock or clock,
                lease_duration=lease,
            )
        ),
    }


def feature_repository_factory(
    path: str | Path,
    *,
    fallback_clock: Callable[[], datetime],
) -> Callable[[Callable[[], datetime] | None, timedelta], _Feature]:
    """Build native PostgreSQL Feature repositories in one isolated schema."""

    return lambda clock, lease: PostgresFeatureMaterializationRunRepository(
        path,
        clock=clock or fallback_clock,
        lease_duration=lease,
    )


class PostgresLifecycleRunRepository:
    def __new__(cls, path: str | Path, **kwargs: object) -> _Lifecycle:
        return _bind_test_scope(_Lifecycle(_factory(path), **kwargs), path)


class PostgresDecisionTimeOperationJournal:
    def __new__(cls, path: str | Path, **kwargs: object) -> _Controlled:
        return _bind_test_scope(_Controlled(_factory(path), **kwargs), path)


class PostgresLongitudinalOperationalIndex:
    def __new__(cls, path: str | Path, **kwargs: object) -> _Longitudinal:
        return _bind_test_scope(_Longitudinal(_factory(path), **kwargs), path)

    @classmethod
    def rebuild(
        cls,
        *,
        path: Path,
        packages: Iterable[tuple[Path, str]],
        clock: Callable[[], datetime],
    ) -> _Longitudinal:
        return _bind_test_scope(
            _Longitudinal.rebuild(
                factory=_factory(path),
                packages=packages,
                clock=clock,
            ),
            path,
        )


class PostgresDailyRunRepository:
    def __new__(cls, path: str | Path, **kwargs: object) -> _Daily:
        return _bind_test_scope(_Daily(_factory(path), **kwargs), path)


class PostgresCompositeOperationalRepository:
    def __new__(cls, path: str | Path, **kwargs: object) -> _Composite:
        return _bind_test_scope(_Composite(_factory(path), **kwargs), path)


class PostgresStateSystemRepository:
    def __new__(cls, path: str | Path, **kwargs: object) -> _State:
        return _bind_test_scope(_State(_factory(path), **kwargs), path)


class PostgresRiskReductionManualIntentRepository:
    def __new__(cls, path: str | Path, **kwargs: object) -> _RiskReduction:
        return _bind_test_scope(_RiskReduction(_factory(path), **kwargs), path)


class PostgresDecisionLifecycleRepository:
    def __new__(cls, path: str | Path, **kwargs: object) -> _Decision:
        return _bind_test_scope(_Decision(_factory(path), **kwargs), path)


class PostgresManualExecutionRepository:
    def __new__(cls, path: str | Path, **kwargs: object) -> _ManualExecution:
        return _bind_test_scope(_ManualExecution(_factory(path), **kwargs), path)


class PostgresTraceableManualExecutionRepository:
    def __new__(cls, path: str | Path, **kwargs: object) -> _TraceableExecution:
        return _bind_test_scope(_TraceableExecution(_factory(path), **kwargs), path)


class PostgresFeatureMaterializationRunRepository:
    def __new__(cls, path: str | Path, **kwargs: object) -> _Feature:
        return _bind_test_scope(_Feature(_factory(path), **kwargs), path)


class PostgresExperimentGovernanceRepository:
    def __new__(cls, path: str | Path, **kwargs: object) -> _Experiment:
        return _bind_test_scope(_Experiment(_factory(path), **kwargs), path)


class PostgresModelRegistryRepository:
    def __new__(cls, path: str | Path, **kwargs: object) -> _Model:
        return _bind_test_scope(_Model(_factory(path), **kwargs), path)


class PostgresCompleteAccountPortfolioRiskRepository:
    def __new__(cls, path: str | Path, **kwargs: object) -> _CompleteAccount:
        return _bind_test_scope(_CompleteAccount(_factory(path), **kwargs), path)


class PostgresPortfolioDecisionRepository:
    def __new__(cls, path: str | Path, **kwargs: object) -> _Portfolio:
        return _bind_test_scope(_Portfolio(_factory(path), **kwargs), path)


class PostgresRiskRouteRepository:
    def __new__(cls, path: str | Path, **kwargs: object) -> _RiskRoute:
        return _bind_test_scope(_RiskRoute(_factory(path), **kwargs), path)


class PostgresThesisHealthRepository:
    def __new__(cls, path: str | Path, **kwargs: object) -> _ThesisHealth:
        return _bind_test_scope(_ThesisHealth(_factory(path), **kwargs), path)


__all__ = [
    "ControlledOperationClaimRejected",
    "ControlledOperationConflict",
    "PostgresCompleteAccountPortfolioRiskRepository",
    "PostgresCompositeOperationalRepository",
    "PostgresDailyRunRepository",
    "PostgresDecisionLifecycleRepository",
    "PostgresDecisionTimeOperationJournal",
    "PostgresExperimentGovernanceRepository",
    "PostgresFeatureMaterializationRunRepository",
    "PostgresLifecycleRunRepository",
    "PostgresLongitudinalOperationalIndex",
    "PostgresManualExecutionRepository",
    "PostgresModelRegistryRepository",
    "PostgresPortfolioDecisionRepository",
    "PostgresRiskReductionManualIntentRepository",
    "PostgresRiskRouteRepository",
    "PostgresStateSystemRepository",
    "PostgresThesisHealthRepository",
    "PostgresTraceableManualExecutionRepository",
    "insert_manual_trade_event",
    "bind_postgres_runtime",
    "controlled_runner_dependencies",
    "feature_repository_factory",
    "load_manual_trade_projection",
    "postgres_connection",
    "postgres_cli_arguments",
    "postgres_factory",
    "restore_manual_execution_json",
    "serialize_manual_execution_json",
]
