"""Narrow UoW contract for exploratory backtest predeclaration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from market_regime_alpha.research_qualification.domain.exploratory_backtest import (
    ExploratoryBacktestRunPlan,
)
from market_regime_alpha.research_qualification.ports.target_artifacts import (
    TargetArtifactRepository,
)
from market_regime_alpha.runtime.ports import (
    AuditRepository,
    CommandReceiptRepository,
    RuntimeCommandFinalization,
)


@dataclass(frozen=True, slots=True)
class ExploratoryBacktestRecord:
    exploratory_backtest_run_id: UUID
    generation: int
    feature_count: int
    feature_roster_sha256: str
    arm_count: int
    arm_roster_sha256: str
    fold_count: int
    fold_roster_sha256: str
    session_count: int
    cost_count: int
    cost_roster_sha256: str
    definition_sha256: str
    registered_at: datetime


class ExploratoryBacktestRepository(Protocol):
    def lock_identity(self, run_code: str, generation: int) -> None: ...

    def register(
        self,
        plan: ExploratoryBacktestRunPlan,
        *,
        request_identity: str,
        request_sha256: str,
    ) -> ExploratoryBacktestRecord: ...

    def record(
        self, exploratory_backtest_run_id: UUID, *, lock: bool
    ) -> ExploratoryBacktestRecord: ...


class ExploratoryBacktestUnitOfWork(Protocol):
    @property
    def exploratory_backtests(self) -> ExploratoryBacktestRepository: ...

    @property
    def artifacts(self) -> TargetArtifactRepository: ...

    @property
    def receipts(self) -> CommandReceiptRepository: ...

    @property
    def audit(self) -> AuditRepository: ...

    @property
    def runtime_finalization(self) -> RuntimeCommandFinalization: ...

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    def commit(self) -> None: ...


class ExploratoryBacktestUnitOfWorkProvider(Protocol):
    def __call__(self) -> ExploratoryBacktestUnitOfWork: ...


__all__ = [
    "ExploratoryBacktestRecord",
    "ExploratoryBacktestRepository",
    "ExploratoryBacktestUnitOfWork",
    "ExploratoryBacktestUnitOfWorkProvider",
]
