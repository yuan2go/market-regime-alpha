"""Market-owned commands for immutable archive roots and work rosters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from typing import Callable
from uuid import UUID

from market_regime_alpha.market.domain import (
    ArchiveCaptureObservation,
    ArchiveLane,
    ArchiveSealDisposition,
    ArchiveSliceStatus,
    BarTimeframe,
    MarketArchive,
    MarketArchiveSeal,
    MarketArchiveSlice,
    PriceBasis,
)
from market_regime_alpha.market.ports.archive import (
    ArchiveUnitOfWork,
    ArchiveUnitOfWorkProvider,
)
from market_regime_alpha.runtime.application import CommandContext
from market_regime_alpha.runtime.errors import (
    ArtifactIntegrityError,
    CommandPreviouslyFailedError,
    RuntimeStateConflictError,
)
from market_regime_alpha.runtime.ports import AttemptClaim, ReceiptRecord
from market_regime_alpha.shared.hashing import canonical_json_sha256


@dataclass(frozen=True, slots=True)
class ArchiveSlicePlan:
    market_archive_slice_id: UUID
    ordinal: int
    scope_key: str
    event_window_start: datetime
    event_window_end: datetime
    request_sha256: str
    expected_fact_kind: str


@dataclass(frozen=True, slots=True)
class StartMarketArchiveRequest:
    market_archive_id: UUID
    archive_code: str
    lane: ArchiveLane
    provider_product_id: UUID
    exchange_code: str
    timeframe: BarTimeframe
    price_basis: PriceBasis
    instrument_scope: str
    instrument_scope_sha256: str
    event_window_start: datetime
    event_window_end: datetime
    reserved_free_bytes: int
    maximum_archive_bytes: int
    maximum_slice_bytes: int
    code_artifact_id: UUID
    config_artifact_id: UUID
    provenance_sha256: str
    slices: tuple[ArchiveSlicePlan, ...]

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,99}", self.archive_code):
            raise ValueError("archive_code has an invalid format")
        if not self.slices:
            raise ValueError("archive slice plan must be non-empty")
        if tuple(item.ordinal for item in self.slices) != tuple(range(1, len(self.slices) + 1)):
            raise ValueError("archive slice plan ordinals must be contiguous")


@dataclass(frozen=True, slots=True)
class MarketArchiveResult:
    market_archive_id: UUID
    archive_start_at: datetime
    slice_count: int
    slice_roster_sha256: str
    content_sha256: str
    receipt_id: UUID
    result_hash: str
    replayed: bool


@dataclass(frozen=True, slots=True)
class RecordArchiveCaptureObservationRequest:
    market_archive_id: UUID
    market_archive_slice_id: UUID
    capture_id: UUID
    schedule_slot: str
    requested_at: datetime
    normalized_revision_count: int
    normalized_revision_roster_sha256: str


@dataclass(frozen=True, slots=True)
class ArchiveCaptureObservationResult:
    market_archive_capture_observation_id: UUID
    market_archive_id: UUID
    market_archive_slice_id: UUID
    capture_id: UUID
    observation_ordinal: int
    relation: str
    timeliness: str
    content_sha256: str
    receipt_id: UUID
    result_hash: str
    replayed: bool


@dataclass(frozen=True, slots=True)
class ArchiveSliceGapResult:
    market_archive_slice_gap_id: UUID
    market_archive_id: UUID
    market_archive_slice_id: UUID
    gap_id: UUID
    terminal_status: str
    content_sha256: str
    receipt_id: UUID
    result_hash: str
    replayed: bool


@dataclass(frozen=True, slots=True)
class ArchiveSealResult:
    market_archive_seal_id: UUID
    market_archive_id: UUID
    sealed_at: datetime
    knowledge_cutoff: datetime
    disposition: str
    capture_count: int
    gap_count: int
    content_sha256: str
    receipt_id: UUID
    result_hash: str
    replayed: bool


class ArchiveCommands:
    def __init__(
        self,
        uow_provider: ArchiveUnitOfWorkProvider,
        *,
        id_factory: Callable[[], UUID],
    ) -> None:
        self._uow_provider = uow_provider
        self._id_factory = id_factory

    def start(
        self,
        request: StartMarketArchiveRequest,
        context: CommandContext,
        *,
        runtime_claim: AttemptClaim | None = None,
    ) -> MarketArchiveResult:
        request_hash = canonical_json_sha256(request)
        with self._uow_provider() as uow:
            if runtime_claim is not None:
                uow.runtime_finalization.lock_live(runtime_claim)
            receipt = uow.receipts.start(
                receipt_id=self._id_factory(),
                command_kind="START_MARKET_ARCHIVE",
                scope_id=request.archive_code,
                idempotency_key=context.idempotency_key,
                request_hash=request_hash,
            )
            if not receipt.is_new:
                _ensure_succeeded(receipt)
                if receipt.result_aggregate_id is None or receipt.result_hash is None:
                    raise ArtifactIntegrityError("Market archive replay receipt is incomplete")
                archive = uow.archives.get_archive(UUID(receipt.result_aggregate_id))
                result = _result(archive, receipt, replayed=True)
                if result.result_hash != receipt.result_hash:
                    raise ArtifactIntegrityError("Market archive replay differs from Authority")
                if runtime_claim is not None:
                    uow.runtime_finalization.succeed(
                        runtime_claim,
                        receipt_id=receipt.receipt_id,
                        result_hash=receipt.result_hash,
                    )
                    uow.commit()
                return result
            archive_start_at = uow.archives.database_now()
            slices = tuple(
                MarketArchiveSlice(
                    market_archive_slice_id=item.market_archive_slice_id,
                    market_archive_id=request.market_archive_id,
                    ordinal=item.ordinal,
                    scope_key=item.scope_key,
                    event_window_start=item.event_window_start,
                    event_window_end=item.event_window_end,
                    request_sha256=item.request_sha256,
                    expected_fact_kind=item.expected_fact_kind,
                    status=ArchiveSliceStatus.PLANNED,
                )
                for item in request.slices
            )
            archive = MarketArchive(
                market_archive_id=request.market_archive_id,
                lane=request.lane,
                provider_product_id=request.provider_product_id,
                exchange_code=request.exchange_code,
                timeframe=request.timeframe,
                price_basis=request.price_basis,
                instrument_scope=request.instrument_scope,
                instrument_scope_sha256=request.instrument_scope_sha256,
                event_window_start=request.event_window_start,
                event_window_end=request.event_window_end,
                archive_start_at=archive_start_at,
                reserved_free_bytes=request.reserved_free_bytes,
                maximum_archive_bytes=request.maximum_archive_bytes,
                maximum_slice_bytes=request.maximum_slice_bytes,
                code_artifact_id=request.code_artifact_id,
                config_artifact_id=request.config_artifact_id,
                provenance_sha256=request.provenance_sha256,
                slices=slices,
            )
            uow.archives.insert_archive(
                archive,
                archive_code=request.archive_code,
                request_identity=context.idempotency_key,
                request_sha256=request_hash,
            )
            result_hash = _archive_result_hash(archive)
            uow.receipts.succeed(
                receipt_id=receipt.receipt_id,
                aggregate_kind="MARKET_ARCHIVE",
                aggregate_id=str(archive.market_archive_id),
                aggregate_version=1,
                result_hash=result_hash,
                runtime_claim=runtime_claim,
            )
            uow.audit.append(
                audit_event_id=self._id_factory(),
                receipt_id=receipt.receipt_id,
                actor_type=context.actor_type.value,
                actor_id=context.actor_id,
                aggregate_kind="MARKET_ARCHIVE",
                aggregate_id=str(archive.market_archive_id),
                action="START_MARKET_ARCHIVE",
                reason_code=context.reason_code,
                before_version=None,
                after_version=1,
                runtime_claim=runtime_claim,
            )
            if runtime_claim is not None:
                uow.runtime_finalization.succeed(
                    runtime_claim,
                    receipt_id=receipt.receipt_id,
                    result_hash=result_hash,
                )
            uow.commit()
            return _result(archive, receipt, replayed=False, result_hash=result_hash)

    def record_capture_observation(
        self,
        request: RecordArchiveCaptureObservationRequest,
        context: CommandContext,
        *,
        runtime_claim: AttemptClaim | None = None,
    ) -> ArchiveCaptureObservationResult:
        request_hash = canonical_json_sha256(request)
        with self._uow_provider() as uow:
            if runtime_claim is not None:
                uow.runtime_finalization.lock_live(runtime_claim)
            receipt = uow.receipts.start(
                receipt_id=self._id_factory(),
                command_kind="RECORD_ARCHIVE_CAPTURE_OBSERVATION",
                scope_id=str(request.market_archive_slice_id),
                idempotency_key=context.idempotency_key,
                request_hash=request_hash,
            )
            if not receipt.is_new:
                _ensure_succeeded(receipt)
                if receipt.result_aggregate_id is None or receipt.result_hash is None:
                    raise ArtifactIntegrityError("Archive observation replay receipt is incomplete")
                observation = uow.archives.get_capture_observation(
                    UUID(receipt.result_aggregate_id)
                )
                result = _observation_result(
                    observation,
                    receipt,
                    result_hash=receipt.result_hash,
                    replayed=True,
                )
                if canonical_json_sha256(observation) != receipt.result_hash:
                    raise ArtifactIntegrityError("Archive observation replay differs from Authority")
                if runtime_claim is not None:
                    uow.runtime_finalization.succeed(
                        runtime_claim,
                        receipt_id=receipt.receipt_id,
                        result_hash=receipt.result_hash,
                    )
                    uow.commit()
                return result
            observation = uow.archives.record_capture_observation(
                observation_id=self._id_factory(),
                market_archive_id=request.market_archive_id,
                market_archive_slice_id=request.market_archive_slice_id,
                capture_id=request.capture_id,
                schedule_slot=request.schedule_slot,
                requested_at=request.requested_at,
                normalized_revision_count=request.normalized_revision_count,
                normalized_revision_roster_sha256=request.normalized_revision_roster_sha256,
            )
            result_hash = canonical_json_sha256(observation)
            self._finish(
                uow,
                receipt_id=receipt.receipt_id,
                aggregate_kind="MARKET_ARCHIVE_CAPTURE_OBSERVATION",
                aggregate_id=str(observation.market_archive_capture_observation_id),
                action="RECORD_ARCHIVE_CAPTURE_OBSERVATION",
                result_hash=result_hash,
                context=context,
                runtime_claim=runtime_claim,
            )
            uow.commit()
            return _observation_result(
                observation,
                receipt,
                result_hash=result_hash,
                replayed=False,
            )

    def record_slice_gap(
        self,
        *,
        market_archive_id: UUID,
        market_archive_slice_id: UUID,
        gap_id: UUID,
        terminal_status: str,
        context: CommandContext,
        runtime_claim: AttemptClaim | None = None,
    ) -> ArchiveSliceGapResult:
        request = {
            "gap_id": gap_id,
            "market_archive_id": market_archive_id,
            "market_archive_slice_id": market_archive_slice_id,
            "terminal_status": terminal_status,
        }
        request_hash = canonical_json_sha256(request)
        with self._uow_provider() as uow:
            if runtime_claim is not None:
                uow.runtime_finalization.lock_live(runtime_claim)
            receipt = uow.receipts.start(
                receipt_id=self._id_factory(),
                command_kind="RECORD_ARCHIVE_SLICE_GAP",
                scope_id=str(market_archive_slice_id),
                idempotency_key=context.idempotency_key,
                request_hash=request_hash,
            )
            if not receipt.is_new:
                _ensure_succeeded(receipt)
                if receipt.result_aggregate_id is None or receipt.result_hash is None:
                    raise ArtifactIntegrityError("Archive gap replay receipt is incomplete")
                record = uow.archives.get_slice_gap(UUID(receipt.result_aggregate_id))
                if canonical_json_sha256(record) != receipt.result_hash:
                    raise ArtifactIntegrityError("Archive gap replay differs from Authority")
                return ArchiveSliceGapResult(
                    market_archive_slice_gap_id=record.market_archive_slice_gap_id,
                    market_archive_id=record.market_archive_id,
                    market_archive_slice_id=record.market_archive_slice_id,
                    gap_id=record.gap_id,
                    terminal_status=record.terminal_status,
                    content_sha256=record.content_sha256,
                    receipt_id=receipt.receipt_id,
                    result_hash=receipt.result_hash,
                    replayed=True,
                )
            record = uow.archives.record_slice_gap(
                binding_id=self._id_factory(),
                market_archive_id=market_archive_id,
                market_archive_slice_id=market_archive_slice_id,
                gap_id=gap_id,
                terminal_status=terminal_status,
            )
            result_hash = canonical_json_sha256(record)
            self._finish(
                uow,
                receipt_id=receipt.receipt_id,
                aggregate_kind="MARKET_ARCHIVE_SLICE_GAP",
                aggregate_id=str(record.market_archive_slice_gap_id),
                action="RECORD_ARCHIVE_SLICE_GAP",
                result_hash=result_hash,
                context=context,
                runtime_claim=runtime_claim,
            )
            uow.commit()
            return ArchiveSliceGapResult(
                market_archive_slice_gap_id=record.market_archive_slice_gap_id,
                market_archive_id=record.market_archive_id,
                market_archive_slice_id=record.market_archive_slice_id,
                gap_id=record.gap_id,
                terminal_status=record.terminal_status,
                content_sha256=record.content_sha256,
                receipt_id=receipt.receipt_id,
                result_hash=result_hash,
                replayed=False,
            )

    def seal_retrospective(
        self,
        *,
        market_archive_id: UUID,
        disposition: ArchiveSealDisposition,
        context: CommandContext,
        runtime_claim: AttemptClaim | None = None,
    ) -> ArchiveSealResult:
        request_hash = canonical_json_sha256(
            {"disposition": disposition, "market_archive_id": market_archive_id}
        )
        with self._uow_provider() as uow:
            if runtime_claim is not None:
                uow.runtime_finalization.lock_live(runtime_claim)
            receipt = uow.receipts.start(
                receipt_id=self._id_factory(),
                command_kind="SEAL_RETROSPECTIVE_ARCHIVE",
                scope_id=str(market_archive_id),
                idempotency_key=context.idempotency_key,
                request_hash=request_hash,
            )
            if not receipt.is_new:
                _ensure_succeeded(receipt)
                if receipt.result_aggregate_id is None or receipt.result_hash is None:
                    raise ArtifactIntegrityError("Archive seal replay receipt is incomplete")
                seal = uow.archives.get_seal(UUID(receipt.result_aggregate_id))
                if canonical_json_sha256(seal) != receipt.result_hash:
                    raise ArtifactIntegrityError("Archive seal replay differs from Authority")
                return _seal_result(
                    seal,
                    receipt,
                    result_hash=receipt.result_hash,
                    replayed=True,
                )
            seal = uow.archives.seal_retrospective(
                seal_id=self._id_factory(),
                market_archive_id=market_archive_id,
                disposition=disposition,
            )
            result_hash = canonical_json_sha256(seal)
            self._finish(
                uow,
                receipt_id=receipt.receipt_id,
                aggregate_kind="MARKET_ARCHIVE_SEAL",
                aggregate_id=str(seal.market_archive_seal_id),
                action="SEAL_RETROSPECTIVE_ARCHIVE",
                result_hash=result_hash,
                context=context,
                runtime_claim=runtime_claim,
            )
            uow.commit()
            return _seal_result(
                seal,
                receipt,
                result_hash=result_hash,
                replayed=False,
            )

    def _finish(
        self,
        uow: ArchiveUnitOfWork,
        *,
        receipt_id: UUID,
        aggregate_kind: str,
        aggregate_id: str,
        action: str,
        result_hash: str,
        context: CommandContext,
        runtime_claim: AttemptClaim | None,
    ) -> None:
        uow.receipts.succeed(
            receipt_id=receipt_id,
            aggregate_kind=aggregate_kind,
            aggregate_id=aggregate_id,
            aggregate_version=1,
            result_hash=result_hash,
            runtime_claim=runtime_claim,
        )
        uow.audit.append(
            audit_event_id=self._id_factory(),
            receipt_id=receipt_id,
            actor_type=context.actor_type.value,
            actor_id=context.actor_id,
            aggregate_kind=aggregate_kind,
            aggregate_id=aggregate_id,
            action=action,
            reason_code=context.reason_code,
            before_version=None,
            after_version=1,
            runtime_claim=runtime_claim,
        )
        if runtime_claim is not None:
            uow.runtime_finalization.succeed(
                runtime_claim,
                receipt_id=receipt_id,
                result_hash=result_hash,
            )


def _archive_result_hash(archive: MarketArchive) -> str:
    return canonical_json_sha256(
        {
            "archive_start_at": archive.archive_start_at,
            "content_sha256": str(archive.content_sha256),
            "market_archive_id": archive.market_archive_id,
            "slice_count": archive.slice_count,
            "slice_roster_sha256": str(archive.slice_roster_sha256),
        }
    )


def _result(
    archive: MarketArchive,
    receipt: ReceiptRecord,
    *,
    replayed: bool,
    result_hash: str | None = None,
) -> MarketArchiveResult:
    actual_hash = result_hash or _archive_result_hash(archive)
    return MarketArchiveResult(
        market_archive_id=archive.market_archive_id,
        archive_start_at=archive.archive_start_at,
        slice_count=archive.slice_count,
        slice_roster_sha256=str(archive.slice_roster_sha256),
        content_sha256=str(archive.content_sha256),
        receipt_id=receipt.receipt_id,
        result_hash=actual_hash,
        replayed=replayed,
    )


def _observation_result(
    observation: ArchiveCaptureObservation,
    receipt: ReceiptRecord,
    *,
    result_hash: str,
    replayed: bool,
) -> ArchiveCaptureObservationResult:
    return ArchiveCaptureObservationResult(
        market_archive_capture_observation_id=observation.market_archive_capture_observation_id,
        market_archive_id=observation.market_archive_id,
        market_archive_slice_id=observation.market_archive_slice_id,
        capture_id=observation.capture_id,
        observation_ordinal=observation.observation_ordinal,
        relation=observation.relation.value,
        timeliness=observation.timeliness.value,
        content_sha256=str(observation.content_sha256),
        receipt_id=receipt.receipt_id,
        result_hash=result_hash,
        replayed=replayed,
    )


def _seal_result(
    seal: MarketArchiveSeal,
    receipt: ReceiptRecord,
    *,
    result_hash: str,
    replayed: bool,
) -> ArchiveSealResult:
    return ArchiveSealResult(
        market_archive_seal_id=seal.market_archive_seal_id,
        market_archive_id=seal.market_archive_id,
        sealed_at=seal.sealed_at,
        knowledge_cutoff=seal.knowledge_cutoff,
        disposition=seal.disposition.value,
        capture_count=seal.capture_count,
        gap_count=seal.gap_count,
        content_sha256=str(seal.content_sha256),
        receipt_id=receipt.receipt_id,
        result_hash=result_hash,
        replayed=replayed,
    )


def _ensure_succeeded(receipt: ReceiptRecord) -> None:
    if receipt.status in {"FAILED", "BLOCKED"}:
        raise CommandPreviouslyFailedError(receipt.error_code or "START_MARKET_ARCHIVE_FAILED")
    if receipt.status != "SUCCEEDED":
        raise RuntimeStateConflictError("Market archive receipt is not terminal")


__all__ = [
    "ArchiveCaptureObservationResult",
    "ArchiveCommands",
    "ArchiveSealResult",
    "ArchiveSlicePlan",
    "ArchiveSliceGapResult",
    "MarketArchiveResult",
    "RecordArchiveCaptureObservationRequest",
    "StartMarketArchiveRequest",
]
