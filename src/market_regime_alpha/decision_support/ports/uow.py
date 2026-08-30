"""Independent short Decision Support transaction contract."""

from types import TracebackType
from typing import Protocol, Self

from market_regime_alpha.decision_support.ports.preparation import (
    DecisionDependencyRepository,
)
from market_regime_alpha.decision_support.ports.repository import (
    DecisionRunRepository,
)
from market_regime_alpha.runtime.ports import (
    AttemptClaim,
    AuditRepository,
    CommandReceiptRepository,
    RuntimeCommandFinalization,
)


class DecisionRuntimeCommandFinalization(RuntimeCommandFinalization, Protocol):
    def lock_live_for_step(
        self,
        claim: AttemptClaim,
        *,
        expected_step_kind: str,
    ) -> None: ...


class DecisionSupportUnitOfWork(Protocol):
    @property
    def decision_runs(self) -> DecisionRunRepository: ...

    @property
    def dependencies(self) -> DecisionDependencyRepository: ...

    @property
    def receipts(self) -> CommandReceiptRepository: ...

    @property
    def audit(self) -> AuditRepository: ...

    @property
    def runtime_finalization(self) -> DecisionRuntimeCommandFinalization: ...

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    def commit(self) -> None: ...


class DecisionSupportUnitOfWorkProvider(Protocol):
    def __call__(self) -> DecisionSupportUnitOfWork: ...


__all__ = [
    "DecisionRuntimeCommandFinalization",
    "DecisionSupportUnitOfWork",
    "DecisionSupportUnitOfWorkProvider",
]
