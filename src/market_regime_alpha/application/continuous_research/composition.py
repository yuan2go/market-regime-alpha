"""Thin adapters to existing FreeData and research service boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Protocol

from market_regime_alpha.application.continuous_research.journal import (
    ContinuousChildKind,
)
from market_regime_alpha.application.continuous_research.ports import (
    ChildExecutionRequest,
    ChildExecutionResult,
    ProviderAcquisitionRequest,
    ProviderAcquisitionResult,
)
from market_regime_alpha.application.free_data_operation.contracts import (
    FreeDataPreparationRequest,
)
from market_regime_alpha.application.free_data_operation.service import (
    FreeDataOperationPreparation,
    FreeDataOperationService,
)


@dataclass(frozen=True, slots=True)
class FreeDataPreparationInvocation:
    request: FreeDataPreparationRequest
    runtime_configuration_path: Path
    idempotency_key: str


FreeDataInvocationBuilder = Callable[
    [ProviderAcquisitionRequest], FreeDataPreparationInvocation
]
FreeDataPreparationTranslator = Callable[
    [FreeDataOperationPreparation], ProviderAcquisitionResult
]


class FreeDataPreparationProviderAdapter:
    """Delegate acquisition/preparation to the existing FreeData composite service."""

    def __init__(
        self,
        *,
        service: FreeDataOperationService,
        invocation_builder: FreeDataInvocationBuilder,
        translator: FreeDataPreparationTranslator,
    ) -> None:
        if not isinstance(service, FreeDataOperationService):
            raise TypeError("service must be FreeDataOperationService")
        self._service = service
        self._invocation_builder = invocation_builder
        self._translator = translator

    def acquire(
        self, request: ProviderAcquisitionRequest
    ) -> ProviderAcquisitionResult:
        invocation = self._invocation_builder(request)
        if invocation.request.command_hash != request.request_hash:
            raise ValueError("FreeData invocation does not bind the provider request")
        preparation = self._service.prepare(
            request=invocation.request,
            runtime_configuration_path=invocation.runtime_configuration_path,
            idempotency_key=invocation.idempotency_key,
        )
        result = self._translator(preparation)
        if not isinstance(result, ProviderAcquisitionResult):
            raise TypeError("FreeData translator must return ProviderAcquisitionResult")
        return result


class ExistingChildServiceDelegate(Protocol):
    child_kind: ContinuousChildKind

    def lookup(
        self, request: ChildExecutionRequest
    ) -> ChildExecutionResult | None: ...

    def execute(self, request: ChildExecutionRequest) -> ChildExecutionResult: ...


class ExistingResearchServiceComposition:
    """Call existing Dataset/Feature/Controlled/Canonical owners exactly once."""

    def __init__(
        self, *, delegates: Mapping[ContinuousChildKind, ExistingChildServiceDelegate]
    ) -> None:
        expected = set(ContinuousChildKind)
        if set(delegates) != expected:
            raise ValueError("composition requires every existing child service")
        for kind, delegate in delegates.items():
            if delegate.child_kind is not kind:
                raise ValueError("child service delegate kind mismatch")
        self._delegates = dict(delegates)

    def lookup_children(
        self, request: ChildExecutionRequest
    ) -> tuple[ChildExecutionResult, ...] | None:
        results: list[ChildExecutionResult] = []
        for kind in sorted(ContinuousChildKind, key=lambda item: item.value):
            result = self._delegates[kind].lookup(request)
            if result is None:
                return None
            _require_kind(kind, result)
            results.append(result)
        return tuple(results)

    def execute_children(
        self, request: ChildExecutionRequest
    ) -> tuple[ChildExecutionResult, ...]:
        results: list[ChildExecutionResult] = []
        for kind in sorted(ContinuousChildKind, key=lambda item: item.value):
            delegate = self._delegates[kind]
            result = delegate.lookup(request)
            if result is None:
                result = delegate.execute(request)
            _require_kind(kind, result)
            results.append(result)
        return tuple(results)


def _require_kind(
    expected: ContinuousChildKind, result: ChildExecutionResult
) -> None:
    if result.child_kind is not expected:
        raise ValueError("existing child service returned a different kind")


__all__ = [
    "ExistingChildServiceDelegate",
    "ExistingResearchServiceComposition",
    "FreeDataPreparationInvocation",
    "FreeDataPreparationProviderAdapter",
]
