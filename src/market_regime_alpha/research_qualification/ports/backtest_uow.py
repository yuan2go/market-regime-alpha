"""Application-facing UoW contract for current Backtest predeclaration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from market_regime_alpha.research_qualification.domain.backtest import (
    BacktestSpecification,
)
from market_regime_alpha.research_qualification.domain.backtest_execution import (
    BacktestEvaluationExecution,
    BacktestModelLineage,
    BacktestRuntimeBinding,
)
from market_regime_alpha.research_qualification.domain.backtest_report import (
    BacktestReportArtifactBinding,
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
class BacktestSpecificationRecord:
    exploratory_backtest_run_id: UUID
    generation: int
    specification_sha256: str
    definition_sha256: str
    arm_count: int
    fold_count: int
    distinct_trading_session_count: int
    fold_session_binding_count: int
    registered_at: datetime


class BacktestRepository(Protocol):
    def lock_identity(self, run_code: str, generation: int) -> None: ...

    def predeclare(
        self,
        specification: BacktestSpecification,
        *,
        request_identity: str,
        request_sha256: str,
    ) -> BacktestSpecificationRecord: ...

    def record(self, exploratory_backtest_run_id: UUID, *, lock: bool) -> BacktestSpecificationRecord: ...

    def bind_runtime(self, binding: BacktestRuntimeBinding) -> BacktestRuntimeBinding: ...

    def bind_evaluation(self, binding: BacktestEvaluationExecution) -> BacktestEvaluationExecution: ...

    def bind_model_lineage(self, binding: BacktestModelLineage) -> BacktestModelLineage: ...

    def bind_report(self, binding: BacktestReportArtifactBinding) -> BacktestReportArtifactBinding: ...


class BacktestUnitOfWork(Protocol):
    @property
    def backtests(self) -> BacktestRepository: ...

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


class BacktestUnitOfWorkProvider(Protocol):
    def __call__(self) -> BacktestUnitOfWork: ...


__all__ = [
    "BacktestRepository",
    "BacktestSpecificationRecord",
    "BacktestUnitOfWork",
    "BacktestUnitOfWorkProvider",
]
