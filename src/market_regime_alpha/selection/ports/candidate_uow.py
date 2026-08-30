"""Independent narrow Candidate unit-of-work contract."""

from types import TracebackType
from typing import Protocol, Self

from market_regime_alpha.runtime.ports import (
    AuditRepository,
    CommandReceiptRepository,
    RuntimeCommandFinalization,
)
from market_regime_alpha.selection.ports.candidate_artifacts import (
    CandidateArtifactRepository,
)
from market_regime_alpha.selection.ports.candidate_repository import (
    CandidateRepository,
)
from market_regime_alpha.selection.ports.research_inputs import (
    CandidateResearchDependencyQueries,
)


class CandidateUnitOfWork(Protocol):
    @property
    def candidates(self) -> CandidateRepository: ...

    @property
    def research_dependencies(self) -> CandidateResearchDependencyQueries: ...

    @property
    def candidate_artifacts(self) -> CandidateArtifactRepository: ...

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


class CandidateUnitOfWorkProvider(Protocol):
    def __call__(
        self,
        *,
        read_only: bool = False,
    ) -> CandidateUnitOfWork: ...


__all__ = ["CandidateUnitOfWork", "CandidateUnitOfWorkProvider"]
