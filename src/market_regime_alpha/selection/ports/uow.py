"""Independent narrow Selection unit-of-work contract."""

from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from market_regime_alpha.runtime.ports import (
    AttemptClaim,
    AuditRepository,
    CommandReceiptRepository,
)
from market_regime_alpha.selection.ports.market import SelectionMarketQueries
from market_regime_alpha.selection.ports.repository import SelectionRepository


class SelectionRuntimeFinalization(Protocol):
    def lock_live(self, claim: AttemptClaim) -> None: ...

    def succeed(
        self,
        claim: AttemptClaim,
        *,
        receipt_id: UUID,
        result_hash: str,
    ) -> tuple[int, int]: ...


class SelectionUnitOfWork(Protocol):
    @property
    def selection(self) -> SelectionRepository: ...

    @property
    def market_queries(self) -> SelectionMarketQueries: ...

    @property
    def receipts(self) -> CommandReceiptRepository: ...

    @property
    def audit(self) -> AuditRepository: ...

    @property
    def runtime_finalization(self) -> SelectionRuntimeFinalization: ...

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    def commit(self) -> None: ...


class SelectionUnitOfWorkProvider(Protocol):
    def __call__(self) -> SelectionUnitOfWork: ...


__all__ = [
    "SelectionRuntimeFinalization",
    "SelectionUnitOfWork",
    "SelectionUnitOfWorkProvider",
]
