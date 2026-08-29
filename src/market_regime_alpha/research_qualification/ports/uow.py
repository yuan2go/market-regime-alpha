"""Independent narrow Research Definition unit-of-work contract."""

from types import TracebackType
from typing import Protocol, Self

from market_regime_alpha.research_qualification.ports.artifacts import (
    ResearchArtifactRepository,
)
from market_regime_alpha.research_qualification.ports.repository import (
    ResearchDefinitionRepository,
)
from market_regime_alpha.research_qualification.ports.sources import (
    ResearchSourceQueries,
)
from market_regime_alpha.runtime.ports import (
    AuditRepository,
    CommandReceiptRepository,
    RuntimeCommandFinalization,
)


class ResearchUnitOfWork(Protocol):
    @property
    def research_definitions(self) -> ResearchDefinitionRepository: ...

    @property
    def research_artifacts(self) -> ResearchArtifactRepository: ...

    @property
    def source_queries(self) -> ResearchSourceQueries: ...

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


class ResearchUnitOfWorkProvider(Protocol):
    def __call__(self) -> ResearchUnitOfWork: ...


__all__ = ["ResearchUnitOfWork", "ResearchUnitOfWorkProvider"]
