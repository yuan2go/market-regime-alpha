"""Resumable archive slice orchestration over canonical Market commands."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID

from market_regime_alpha.market.application.archive import (
    ArchiveCommands,
    RecordArchiveCaptureObservationRequest,
)
from market_regime_alpha.market.domain import CaptureStatus
from market_regime_alpha.market.ports import (
    CaptureRequest,
    MarketDatabaseClock,
    MarketNormalizer,
    MarketProvider,
)
from market_regime_alpha.market.ports.archive_operations import (
    ArchiveOperationsReadPort,
    ArchiveResourceInspector,
)
from market_regime_alpha.runtime.application import CommandContext
from market_regime_alpha.runtime.ports import AttemptClaim
from market_regime_alpha.shared.hashing import canonical_json_sha256


class _MarketCommands(Protocol):
    def capture(
        self,
        request: CaptureRequest,
        provider: MarketProvider,
        context: CommandContext,
        *,
        runtime_claim: AttemptClaim | None = None,
    ) -> Any: ...

    def normalize(
        self,
        capture_id: UUID,
        normalizer: MarketNormalizer,
        context: CommandContext,
        *,
        runtime_claim: AttemptClaim | None = None,
    ) -> Any: ...


class ArchiveSliceExecutionStatus(StrEnum):
    CAPTURED = "CAPTURED"
    GAP_RECORDED = "GAP_RECORDED"
    RESOURCE_LIMIT = "RESOURCE_LIMIT"
    ALREADY_TERMINAL = "ALREADY_TERMINAL"


@dataclass(frozen=True, slots=True)
class ArchiveSliceExecutionRequest:
    market_archive_id: UUID
    market_archive_slice_id: UUID
    capture_request: CaptureRequest
    schedule_slot: str


@dataclass(frozen=True, slots=True)
class ArchiveSliceExecutionResult:
    market_archive_id: UUID
    market_archive_slice_id: UUID
    status: ArchiveSliceExecutionStatus
    capture_id: UUID | None
    source_gap_id: UUID | None


class MarketArchiveOperations:
    def __init__(
        self,
        market: _MarketCommands,
        archives: ArchiveCommands,
        read_port: ArchiveOperationsReadPort,
        resources: ArchiveResourceInspector,
        database_clock: MarketDatabaseClock,
    ) -> None:
        self._market = market
        self._archives = archives
        self._read_port = read_port
        self._resources = resources
        self._database_clock = database_clock

    def execute_slice(
        self,
        request: ArchiveSliceExecutionRequest,
        *,
        provider: MarketProvider,
        normalizer: MarketNormalizer,
        context: CommandContext,
        runtime_claim: AttemptClaim | None = None,
    ) -> ArchiveSliceExecutionResult:
        contract = self._read_port.load_slice_contract(
            request.market_archive_id,
            request.market_archive_slice_id,
        )
        if contract.market_archive_id != request.market_archive_id or contract.market_archive_slice_id != request.market_archive_slice_id:
            raise ValueError("archive read port returned a different slice identity")
        if contract.provider_product_id != request.capture_request.provider_product_id:
            raise ValueError("Capture ProviderProduct differs from the frozen archive")
        if contract.request_sha256 != canonical_json_sha256(request.capture_request):
            raise ValueError("CaptureRequest differs from the frozen slice request")
        if contract.terminal_status is not None:
            return ArchiveSliceExecutionResult(
                market_archive_id=request.market_archive_id,
                market_archive_slice_id=request.market_archive_slice_id,
                status=ArchiveSliceExecutionStatus.ALREADY_TERMINAL,
                capture_id=None,
                source_gap_id=None,
            )
        available = self._resources.available_bytes()
        if available < contract.required_free_bytes:
            self._archives.record_resource_stop(
                market_archive_id=request.market_archive_id,
                market_archive_slice_id=request.market_archive_slice_id,
                observed_free_bytes=available,
                context=_child_context(context, "resource-stop"),
                runtime_claim=runtime_claim,
            )
            return ArchiveSliceExecutionResult(
                market_archive_id=request.market_archive_id,
                market_archive_slice_id=request.market_archive_slice_id,
                status=ArchiveSliceExecutionStatus.RESOURCE_LIMIT,
                capture_id=None,
                source_gap_id=None,
            )
        requested_at = self._database_clock.now()
        captured = self._market.capture(
            request.capture_request,
            provider,
            _child_context(context, "capture"),
            runtime_claim=runtime_claim,
        )
        capture_id = captured.capture.capture_id
        if captured.capture.status is CaptureStatus.PROVIDER_FAILURE:
            disposition = self._read_port.capture_disposition(capture_id)
            if disposition.status is not CaptureStatus.PROVIDER_FAILURE or len(disposition.source_gap_ids) != 1:
                raise ValueError("Provider failure Capture requires one exact SourceGap")
            gap_id = disposition.source_gap_ids[0]
            self._archives.record_slice_gap(
                market_archive_id=request.market_archive_id,
                market_archive_slice_id=request.market_archive_slice_id,
                gap_id=gap_id,
                terminal_status="GAP_RECORDED",
                context=_child_context(context, "gap"),
                runtime_claim=runtime_claim,
            )
            return ArchiveSliceExecutionResult(
                market_archive_id=request.market_archive_id,
                market_archive_slice_id=request.market_archive_slice_id,
                status=ArchiveSliceExecutionStatus.GAP_RECORDED,
                capture_id=capture_id,
                source_gap_id=gap_id,
            )
        self._market.normalize(
            capture_id,
            normalizer,
            _child_context(context, "normalize"),
            runtime_claim=runtime_claim,
        )
        self._archives.record_capture_observation(
            RecordArchiveCaptureObservationRequest(
                market_archive_id=request.market_archive_id,
                market_archive_slice_id=request.market_archive_slice_id,
                capture_id=capture_id,
                schedule_slot=request.schedule_slot,
                requested_at=requested_at,
            ),
            _child_context(context, "observe"),
            runtime_claim=runtime_claim,
        )
        return ArchiveSliceExecutionResult(
            market_archive_id=request.market_archive_id,
            market_archive_slice_id=request.market_archive_slice_id,
            status=ArchiveSliceExecutionStatus.CAPTURED,
            capture_id=capture_id,
            source_gap_id=None,
        )


def _child_context(parent: CommandContext, suffix: str) -> CommandContext:
    return CommandContext(
        idempotency_key=f"{parent.idempotency_key}:{suffix}",
        actor_type=parent.actor_type,
        actor_id=parent.actor_id,
        reason_code=parent.reason_code,
    )


__all__ = [
    "ArchiveSliceExecutionRequest",
    "ArchiveSliceExecutionResult",
    "ArchiveSliceExecutionStatus",
    "MarketArchiveOperations",
]
