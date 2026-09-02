"""Narrow immutable Strategy Authority ports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from market_regime_alpha.decision_support.domain import (
    DecisionArtifactBinding,
    StrategyVersionPlan,
)
from market_regime_alpha.runtime.ports import (
    ArtifactRecord,
    AuditRepository,
    CommandReceiptRepository,
)


@dataclass(frozen=True, slots=True)
class StrategyVersionRecord:
    strategy_id: UUID
    strategy_version_id: UUID
    version: int
    context_requirement_count: int
    forecast_rule_count: int
    content_sha256: str
    request_identity: str
    request_sha256: str
    frozen_at: datetime
    receipt_id: UUID


@dataclass(frozen=True, slots=True)
class StrategyReconciliation:
    strategy_version_id: UUID
    context_requirement_count: int
    signal_rule_count: int
    forecast_rule_count: int
    context_requirement_roster_sha256: str
    forecast_rule_roster_sha256: str
    matched: bool


class StrategyQueryProvider(Protocol):
    def find_request(
        self,
        strategy_id: UUID,
        request_identity: str,
    ) -> StrategyVersionRecord | None: ...


class StrategyArtifactRepository(Protocol):
    def require_exact(
        self,
        binding: DecisionArtifactBinding,
        *,
        lock: bool,
    ) -> ArtifactRecord: ...


class StrategyRepository(Protocol):
    def lock_identity(self, strategy_id: UUID) -> None: ...

    def register(
        self,
        plan: StrategyVersionPlan,
        *,
        request_identity: str,
        request_sha256: str,
    ) -> StrategyVersionRecord: ...

    def record(
        self,
        strategy_version_id: UUID,
        *,
        lock: bool,
    ) -> StrategyVersionRecord: ...

    def reconcile(
        self,
        strategy_version_id: UUID,
        *,
        lock: bool,
    ) -> StrategyReconciliation: ...


class StrategyUnitOfWork(Protocol):
    @property
    def strategies(self) -> StrategyRepository: ...

    @property
    def artifacts(self) -> StrategyArtifactRepository: ...

    @property
    def receipts(self) -> CommandReceiptRepository: ...

    @property
    def audit(self) -> AuditRepository: ...

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    def commit(self) -> None: ...


class StrategyUnitOfWorkProvider(Protocol):
    def __call__(self) -> StrategyUnitOfWork: ...


__all__ = [
    "StrategyArtifactRepository",
    "StrategyQueryProvider",
    "StrategyReconciliation",
    "StrategyRepository",
    "StrategyUnitOfWork",
    "StrategyUnitOfWorkProvider",
    "StrategyVersionRecord",
]
