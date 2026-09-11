"""Resumable archive slice orchestration over canonical Market commands."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from typing import Any, Protocol
from uuid import UUID

from market_regime_alpha.market.application.archive import (
    ArchiveCommands,
    RecordArchiveCaptureObservationRequest,
)
from market_regime_alpha.market.domain import ArchiveLane, CaptureStatus
from market_regime_alpha.market.ports import (
    CaptureRequest,
    MarketDatabaseClock,
    MarketArtifactByteStore,
    MarketNormalizer,
    MarketProvider,
)
from market_regime_alpha.market.ports.acquisition_readiness import ArchiveAcquisitionReadiness, ArchiveAcquisitionReadinessClassifier
from market_regime_alpha.market.ports.archive_operations import (
    ArchiveOperationsReadPort,
    ArchiveResourceInspector,
)
from market_regime_alpha.runtime.application import CommandContext
from market_regime_alpha.runtime.errors import ArtifactIntegrityError, RuntimeStateConflictError
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
        complete_runtime_attempt: bool = True,
    ) -> Any: ...

    def normalize(
        self,
        capture_id: UUID,
        normalizer: MarketNormalizer,
        context: CommandContext,
        *,
        runtime_claim: AttemptClaim | None = None,
        complete_runtime_attempt: bool = True,
    ) -> Any: ...


class ArchiveSliceExecutionStatus(StrEnum):
    NOT_DUE = "NOT_DUE"
    CAPTURED = "CAPTURED"
    NO_MATURE_INTERVAL = "NO_MATURE_INTERVAL"
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
    acquisition_readiness: ArchiveAcquisitionReadiness | None = None


class MarketArchiveOperations:
    def __init__(
        self,
        market: _MarketCommands,
        archives: ArchiveCommands,
        read_port: ArchiveOperationsReadPort,
        resources: ArchiveResourceInspector,
        database_clock: MarketDatabaseClock,
        *,
        byte_store: MarketArtifactByteStore | None = None,
    ) -> None:
        self._market = market
        self._archives = archives
        self._read_port = read_port
        self._resources = resources
        self._database_clock = database_clock
        self._byte_store = byte_store

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
        requested_at = self._database_clock.now()
        if (
            contract.lane is ArchiveLane.PROSPECTIVE_CONTEMPORANEOUS
            and requested_at < contract.event_window_start
        ):
            return ArchiveSliceExecutionResult(
                market_archive_id=request.market_archive_id,
                market_archive_slice_id=request.market_archive_slice_id,
                status=ArchiveSliceExecutionStatus.NOT_DUE,
                capture_id=None,
                source_gap_id=None,
            )
        if (
            contract.lane is ArchiveLane.PROSPECTIVE_CONTEMPORANEOUS
            and runtime_claim is None
        ):
            raise RuntimeStateConflictError(
                "prospective archive effects require a Runtime claim"
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
        captured = self._market.capture(
            request.capture_request,
            provider,
            _child_context(context, "capture"),
            runtime_claim=runtime_claim,
            complete_runtime_attempt=False,
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
        if contract.lane is ArchiveLane.PROSPECTIVE_CONTEMPORANEOUS and isinstance(normalizer, ArchiveAcquisitionReadinessClassifier):
            if self._byte_store is None or captured.artifact is None or captured.artifact.artifact_id != captured.capture.artifact_id:
                raise ArtifactIntegrityError("ACQUISITION_CAPTURE_ARTIFACT_UNAVAILABLE")
            content = self._byte_store.read_bytes(captured.artifact.content_sha256, expected_size=captured.artifact.size_bytes)
            if len(content) != captured.artifact.size_bytes or sha256(content).hexdigest() != str(captured.artifact.content_sha256):
                raise ArtifactIntegrityError("ACQUISITION_CAPTURE_ARTIFACT_CHANGED")
            readiness = normalizer.acquisition_readiness(captured.capture, content)
            if readiness is not None:
                if (readiness.state != "NO_MATURE_INTERVAL" or readiness.capture_id != capture_id
                        or readiness.source_sha256 != sha256(content).hexdigest()
                        or readiness.requested_at != captured.capture.temporal.capture_started_at
                        or readiness.first_mature_at <= readiness.requested_at or readiness.expected_interval_count < 1):
                    raise ArtifactIntegrityError("ACQUISITION_READINESS_CAPTURE_IDENTITY_CHANGED")
                # Replay the exact successful Capture receipt to close its fence.
                # This cannot invoke the Provider again or claim normalization.
                completed = self._market.capture(request.capture_request, provider, _child_context(context, "capture"),
                    runtime_claim=runtime_claim, complete_runtime_attempt=True)
                if completed.capture != captured.capture or completed.result_hash != captured.result_hash or not completed.replayed:
                    raise ArtifactIntegrityError("ACQUISITION_CAPTURE_COMPLETION_DIFFERS")
                return ArchiveSliceExecutionResult(request.market_archive_id, request.market_archive_slice_id,
                    ArchiveSliceExecutionStatus.NO_MATURE_INTERVAL, capture_id, None, readiness)
        self._market.normalize(
            capture_id,
            normalizer,
            _child_context(context, "normalize"),
            runtime_claim=runtime_claim,
            complete_runtime_attempt=False,
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
