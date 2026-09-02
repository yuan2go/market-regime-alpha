"""Narrow complete Signal and Forecast Authority ports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from market_regime_alpha.decision_support.domain import (
    ForecastAuthority,
    PreparedInferenceInputs,
    SignalAuthority,
)
from market_regime_alpha.runtime.ports import (
    AttemptClaim,
    AuditRepository,
    CommandReceiptRepository,
    RuntimeCommandFinalization,
)


@dataclass(frozen=True, slots=True)
class InferenceRecord:
    decision_run_id: UUID
    strategy_version_id: UUID
    signal_group_id: UUID
    forecast_group_id: UUID
    signal_count: int
    forecast_count: int
    context_binding_count: int
    estimate_count: int
    signal_content_sha256: str
    forecast_content_sha256: str
    request_identity: str
    request_sha256: str
    recorded_at: datetime
    receipt_id: UUID


@dataclass(frozen=True, slots=True)
class InferenceReconciliation:
    signal_group_id: UUID
    forecast_group_id: UUID
    signal_count: int
    context_binding_count: int
    forecast_count: int
    estimate_count: int
    matched: bool


class InferenceInputPreparationProvider(Protocol):
    def prepare(
        self,
        decision_run_id: UUID,
        strategy_version_id: UUID,
    ) -> PreparedInferenceInputs: ...


class InferenceQueryProvider(Protocol):
    def find_request(
        self,
        decision_run_id: UUID,
        strategy_version_id: UUID,
        request_identity: str,
    ) -> InferenceRecord | None: ...


class InferenceDependencyRepository(Protocol):
    def lock_and_revalidate(self, prepared: PreparedInferenceInputs) -> None: ...


class InferenceRepository(Protocol):
    def lock_identity(
        self,
        decision_run_id: UUID,
        strategy_version_id: UUID,
    ) -> None: ...

    def authoritative_recorded_at(self) -> datetime: ...

    def insert(
        self,
        signal: SignalAuthority,
        forecast: ForecastAuthority,
    ) -> InferenceRecord: ...

    def record(
        self,
        signal_group_id: UUID,
        forecast_group_id: UUID,
        *,
        lock: bool,
    ) -> InferenceRecord: ...

    def forecast_group_for_signal(
        self,
        signal_group_id: UUID,
        *,
        lock: bool,
    ) -> UUID: ...

    def reconcile(
        self,
        signal_group_id: UUID,
        forecast_group_id: UUID,
        *,
        lock: bool,
    ) -> InferenceReconciliation: ...


class InferenceRuntimeFinalization(RuntimeCommandFinalization, Protocol):
    def lock_live_for_step(
        self,
        claim: AttemptClaim,
        *,
        expected_step_kind: str,
    ) -> None: ...


class InferenceUnitOfWork(Protocol):
    @property
    def inference(self) -> InferenceRepository: ...

    @property
    def dependencies(self) -> InferenceDependencyRepository: ...

    @property
    def receipts(self) -> CommandReceiptRepository: ...

    @property
    def audit(self) -> AuditRepository: ...

    @property
    def runtime_finalization(self) -> InferenceRuntimeFinalization: ...

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    def commit(self) -> None: ...


class InferenceUnitOfWorkProvider(Protocol):
    def __call__(self) -> InferenceUnitOfWork: ...


__all__ = [
    "InferenceDependencyRepository",
    "InferenceInputPreparationProvider",
    "InferenceQueryProvider",
    "InferenceReconciliation",
    "InferenceRecord",
    "InferenceRepository",
    "InferenceRuntimeFinalization",
    "InferenceUnitOfWork",
    "InferenceUnitOfWorkProvider",
]
