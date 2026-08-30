"""Independent narrow Target registration unit-of-work contract."""

from types import TracebackType
from typing import Protocol, Self

from market_regime_alpha.research_qualification.ports.target_artifacts import (
    TargetArtifactRepository,
)
from market_regime_alpha.research_qualification.ports.target_repository import (
    TargetDefinitionRepository,
)
from market_regime_alpha.runtime.ports import (
    AuditRepository,
    CommandReceiptRepository,
    RuntimeCommandFinalization,
)


class TargetUnitOfWork(Protocol):
    @property
    def target_definitions(self) -> TargetDefinitionRepository: ...

    @property
    def target_artifacts(self) -> TargetArtifactRepository: ...

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


class TargetUnitOfWorkProvider(Protocol):
    def __call__(self) -> TargetUnitOfWork: ...


__all__ = ["TargetUnitOfWork", "TargetUnitOfWorkProvider"]
