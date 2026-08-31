"""Narrow short transaction owned by the Outcome bounded context."""

from types import TracebackType
from typing import Protocol, Self

from market_regime_alpha.outcome.ports.preparation import (
    OutcomeDependencyRepository,
)
from market_regime_alpha.outcome.ports.repository import OutcomeRepository
from market_regime_alpha.runtime.ports import (
    AttemptClaim,
    AuditRepository,
    CommandReceiptRepository,
    RuntimeCommandFinalization,
)


class OutcomeRuntimeFinalization(RuntimeCommandFinalization, Protocol):
    def lock_live_for_step(
        self,
        claim: AttemptClaim,
        *,
        expected_step_kind: str,
    ) -> None: ...


class OutcomeUnitOfWork(Protocol):
    @property
    def outcomes(self) -> OutcomeRepository: ...

    @property
    def dependencies(self) -> OutcomeDependencyRepository: ...

    @property
    def receipts(self) -> CommandReceiptRepository: ...

    @property
    def audit(self) -> AuditRepository: ...

    @property
    def runtime_finalization(self) -> OutcomeRuntimeFinalization: ...

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    def commit(self) -> None: ...


class OutcomeUnitOfWorkProvider(Protocol):
    def __call__(self) -> OutcomeUnitOfWork: ...


__all__ = [
    "OutcomeRuntimeFinalization",
    "OutcomeUnitOfWork",
    "OutcomeUnitOfWorkProvider",
]
