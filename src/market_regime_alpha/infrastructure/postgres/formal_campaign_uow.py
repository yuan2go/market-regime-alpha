"""One short PostgreSQL transaction for FormalResearchCampaign Authority."""

from __future__ import annotations

from contextlib import AbstractContextManager
from types import TracebackType
from typing import Any

import psycopg

from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.postgres.repositories.formal_campaigns import (
    PostgresFormalCampaignRepository,
)
from market_regime_alpha.infrastructure.postgres.repositories.runtime import (
    PostgresAuditRepository,
    PostgresCommandReceiptRepository,
)
from market_regime_alpha.infrastructure.postgres.repositories.target_artifacts import (
    PostgresTargetArtifactRepository,
)
from market_regime_alpha.infrastructure.postgres.research_transaction import (
    classify_research_postgres_error,
    commit_research_transaction,
)
from market_regime_alpha.infrastructure.postgres.runtime_finalization import (
    PostgresRuntimeCommandFinalization,
)
from market_regime_alpha.research_qualification.ports.formal_campaign_uow import (
    FormalCampaignUnitOfWork,
)


class PostgresFormalCampaignUnitOfWork:
    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool
        self._scope: AbstractContextManager[psycopg.Connection[Any]] | None = None
        self._connection: psycopg.Connection[Any] | None = None
        self._used = False
        self._committed = False

    def __enter__(self) -> PostgresFormalCampaignUnitOfWork:
        if self._used:
            raise RuntimeError("FormalCampaign UoW cannot be nested or reused")
        self._used = True
        self._scope = self._pool.connection()
        self._connection = self._scope.__enter__()
        return self

    def _active(self) -> psycopg.Connection[Any]:
        if self._connection is None:
            raise RuntimeError("FormalCampaign UoW is not active")
        return self._connection

    @property
    def campaigns(self) -> PostgresFormalCampaignRepository:
        return PostgresFormalCampaignRepository(self._active())

    @property
    def artifacts(self) -> PostgresTargetArtifactRepository:
        return PostgresTargetArtifactRepository(self._active())

    @property
    def receipts(self) -> PostgresCommandReceiptRepository:
        return PostgresCommandReceiptRepository(self._active())

    @property
    def audit(self) -> PostgresAuditRepository:
        return PostgresAuditRepository(self._active())

    @property
    def runtime_finalization(self) -> PostgresRuntimeCommandFinalization:
        return PostgresRuntimeCommandFinalization(self._active())

    def commit(self) -> None:
        commit_research_transaction(self._active())
        self._committed = True

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        replacement = classify_research_postgres_error(
            exception, owner="FormalResearchCampaign"
        )
        if self._connection is not None and not self._committed:
            try:
                self._connection.rollback()
            except psycopg.Error:
                if exception is None:
                    raise
        if self._scope is not None:
            self._scope.__exit__(exception_type, exception, traceback)
        self._connection = None
        self._scope = None
        if replacement is not None:
            raise replacement from exception


class PostgresFormalCampaignUnitOfWorkProvider:
    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool

    def __call__(self) -> FormalCampaignUnitOfWork:
        return PostgresFormalCampaignUnitOfWork(self._pool)


__all__ = [
    "PostgresFormalCampaignUnitOfWork",
    "PostgresFormalCampaignUnitOfWorkProvider",
]
