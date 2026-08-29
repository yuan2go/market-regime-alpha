"""Explicit Market/PIT commands over a narrow bounded transaction."""

from __future__ import annotations

from dataclasses import replace
from uuid import UUID

from market_regime_alpha.market.domain import (
    CaptureStatus,
    GapFactKind,
    GapKind,
    GapReasonCode,
    ProviderCapture,
    SourceAvailabilityStatus,
    SourceGap,
    TemporalEnvelope,
)
from market_regime_alpha.market.ports import (
    CaptureRequest,
    MarketProvider,
    MarketProviderError,
    MarketUnitOfWork,
)
from market_regime_alpha.runtime.application import CommandContext
from market_regime_alpha.runtime.errors import (
    ArtifactByteStoreError,
    ArtifactIntegrityError,
)
from market_regime_alpha.runtime.ports import (
    AttemptClaim,
)
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.identity import ContentHash
from market_regime_alpha.shared.time import DecisionTime, KnownTime

from market_regime_alpha.market.application._support import (
    _MarketCommandSupport,
    _ensure_replay_succeeded,
    _replay_concurrent_success,
    _required_result_hash,
)
from market_regime_alpha.market.application.results import CaptureMutationResult


class _CaptureCommands(_MarketCommandSupport):
    @_replay_concurrent_success
    def capture(
        self, request: CaptureRequest, provider: MarketProvider, context: CommandContext, *, runtime_claim: AttemptClaim | None = None
    ) -> CaptureMutationResult:
        """Perform observational Provider/CAS I/O before opening the write transaction."""
        request_hash = ContentHash(canonical_json_sha256(request))
        with self._terminal_failure_boundary(
            operation="CAPTURE_MARKET_DATA",
            scope_id=str(request.provider_product_id),
            request_hash=request_hash.value,
            error_class="COMMAND",
            error_code="CAPTURE_COMMAND_REJECTED",
            context=context,
            runtime_claim=runtime_claim,
        ):
            replay = self._capture_replay_before_io(request, request_hash=request_hash, context=context, runtime_claim=runtime_claim)
        if replay is not None:
            return replay
        started_at = self._database_clock.now()
        try:
            with self._terminal_failure_boundary(
                operation="CAPTURE_MARKET_DATA",
                scope_id=str(request.provider_product_id),
                request_hash=request_hash.value,
                error_class="PROVIDER",
                error_code="PROVIDER_RESPONSE_REJECTED",
                context=context,
                runtime_claim=runtime_claim,
            ):
                response = provider.capture(request)
        except MarketProviderError as exc:
            completed_at = self._database_clock.now()
            with self._terminal_failure_boundary(
                operation="CAPTURE_MARKET_DATA",
                scope_id=str(request.provider_product_id),
                request_hash=request_hash.value,
                error_class="DATA_INTEGRITY",
                error_code="CAPTURE_FAILURE_BINDING_REJECTED",
                context=context,
                runtime_claim=runtime_claim,
            ):
                temporal = TemporalEnvelope(
                    provider_time=None,
                    source_availability_status=SourceAvailabilityStatus.UNKNOWN,
                    source_available_at=None,
                    capture_started_at=started_at,
                    capture_completed_at=completed_at,
                    known_at=KnownTime(completed_at),
                    decision_visible_at=DecisionTime(completed_at),
                )
                failure = ProviderCapture(
                    capture_id=self._id_factory(),
                    provider_product_id=request.provider_product_id,
                    capture_key=request.capture_key,
                    request_hash=request_hash,
                    status=CaptureStatus.PROVIDER_FAILURE,
                    temporal=temporal,
                    artifact_id=None,
                    error_code=exc.code,
                    limitation_code=None,
                    payload_encoding=None,
                )
                return self._record_capture_failure(failure, context=context, runtime_claim=runtime_claim)
        completed_at = self._database_clock.now()
        with self._terminal_failure_boundary(
            operation="CAPTURE_MARKET_DATA",
            scope_id=str(request.provider_product_id),
            request_hash=request_hash.value,
            error_class="PROVIDER",
            error_code="PROVIDER_RESPONSE_REJECTED",
            context=context,
            runtime_claim=runtime_claim,
        ):
            temporal = TemporalEnvelope(
                provider_time=response.provider_time,
                source_availability_status=response.source_availability_status,
                source_available_at=response.source_available_at,
                capture_started_at=started_at,
                capture_completed_at=completed_at,
                known_at=KnownTime(completed_at),
                decision_visible_at=DecisionTime(completed_at),
            )
        try:
            published = self._byte_store.publish_bytes(response.content, media_type=response.media_type)
            verification = self._byte_store.verify(ContentHash(published.content_sha256), expected_size=published.size_bytes)
            if verification.result != "VERIFIED":
                self._record_capture_artifact_failure(
                    request,
                    request_hash=request_hash,
                    error_code=f"ARTIFACT_{verification.result}",
                    context=context,
                    runtime_claim=runtime_claim,
                )
                raise ArtifactIntegrityError("Provider bytes failed verification before binding")
        except (ArtifactByteStoreError, ValueError) as exc:
            self._record_capture_artifact_failure(
                request, request_hash=request_hash, error_code="ARTIFACT_PUBLISH_FAILED", context=context, runtime_claim=runtime_claim
            )
            raise ArtifactIntegrityError("Provider bytes could not establish a safe Artifact identity") from exc
        with (
            self._terminal_failure_boundary(
                operation="CAPTURE_MARKET_DATA",
                scope_id=str(request.provider_product_id),
                request_hash=request_hash.value,
                error_class="DATA_INTEGRITY",
                error_code="CAPTURE_BINDING_REJECTED",
                context=context,
                runtime_claim=runtime_claim,
            ),
            self._uow_provider() as uow,
        ):
            if runtime_claim is not None:
                uow.runtime_finalization.lock_live(runtime_claim)
            receipt = uow.receipts.start(
                receipt_id=self._id_factory(),
                command_kind="CAPTURE_MARKET_DATA",
                scope_id=str(request.provider_product_id),
                idempotency_key=context.idempotency_key,
                request_hash=request_hash.value,
            )
            if not receipt.is_new:
                _ensure_replay_succeeded(receipt)
                if receipt.result_aggregate_id is None:
                    raise ArtifactIntegrityError("Capture receipt has no Capture identity")
                source = uow.market.capture_source(UUID(receipt.result_aggregate_id), lock=False)
                result_hash = _required_result_hash(receipt.result_hash)
                self._finalize_capture_replay(
                    uow, capture=source.capture, receipt_id=receipt.receipt_id, result_hash=result_hash, runtime_claim=runtime_claim
                )
                return CaptureMutationResult(
                    capture=source.capture,
                    artifact=replace(source.artifact, replayed=True) if source.artifact is not None else None,
                    result_hash=result_hash,
                    receipt_id=receipt.receipt_id,
                    replayed=True,
                )
            artifact = uow.artifacts.register(
                artifact_id=self._id_factory(), published=published, retention_until=None, pin_reason_code=None
            )
            uow.artifacts.record_verification(
                verification_id=self._id_factory(),
                receipt_id=receipt.receipt_id,
                artifact=artifact,
                verifier_id=f"market-provider-product:{request.provider_product_id}",
                policy="CAPTURE_PUBLISH_READ_AFTER_WRITE",
                verification=verification,
            )
            artifact = uow.artifacts.get(artifact.artifact_id)
            capture = ProviderCapture(
                capture_id=self._id_factory(),
                provider_product_id=request.provider_product_id,
                capture_key=request.capture_key,
                request_hash=request_hash,
                status=CaptureStatus.CAPTURED,
                temporal=temporal,
                artifact_id=artifact.artifact_id,
                error_code=None,
                limitation_code=response.limitation_code,
                payload_encoding=response.payload_encoding,
            )
            capture = uow.market.record_capture(capture, published)
            version = 1
            result_hash = canonical_json_sha256(
                {"capture": capture, "artifact_hash": artifact.content_sha256, "artifact_size": artifact.size_bytes}
            )
            self._finish_mutation(
                uow,
                receipt_id=receipt.receipt_id,
                aggregate_kind="DATA_CAPTURE",
                aggregate_id=str(capture.capture_id),
                aggregate_version=version,
                result_hash=result_hash,
                action="CAPTURE_MARKET_DATA",
                context=context,
                runtime_claim=runtime_claim,
            )
            if runtime_claim is not None:
                uow.runtime_finalization.succeed(runtime_claim, receipt_id=receipt.receipt_id, result_hash=result_hash)
            uow.commit()
            return CaptureMutationResult(
                capture=capture, artifact=artifact, result_hash=result_hash, receipt_id=receipt.receipt_id, replayed=False
            )

    def _capture_replay_before_io(
        self, request: CaptureRequest, *, request_hash: ContentHash, context: CommandContext, runtime_claim: AttemptClaim | None
    ) -> CaptureMutationResult | None:
        """Return an exact committed replay without repeating Provider byte I/O."""
        with self._uow_provider() as uow:
            if runtime_claim is not None:
                uow.runtime_finalization.lock_live(runtime_claim)
            receipt = uow.receipts.start(
                receipt_id=self._id_factory(),
                command_kind="CAPTURE_MARKET_DATA",
                scope_id=str(request.provider_product_id),
                idempotency_key=context.idempotency_key,
                request_hash=request_hash.value,
            )
            if receipt.is_new:
                return None
            _ensure_replay_succeeded(receipt)
            if receipt.result_aggregate_id is None:
                raise ArtifactIntegrityError("Capture receipt has no Capture identity")
            source = uow.market.capture_source(UUID(receipt.result_aggregate_id), lock=False)
            result_hash = _required_result_hash(receipt.result_hash)
            self._finalize_capture_replay(
                uow, capture=source.capture, receipt_id=receipt.receipt_id, result_hash=result_hash, runtime_claim=runtime_claim
            )
            return CaptureMutationResult(
                capture=source.capture,
                artifact=replace(source.artifact, replayed=True) if source.artifact is not None else None,
                result_hash=result_hash,
                receipt_id=receipt.receipt_id,
                replayed=True,
            )

    def _record_capture_artifact_failure(
        self,
        request: CaptureRequest,
        *,
        request_hash: ContentHash,
        error_code: str,
        context: CommandContext,
        runtime_claim: AttemptClaim | None,
    ) -> None:
        """Persist the failed CAPTURE command without inventing a Capture."""
        self._record_command_failure(
            operation="CAPTURE_MARKET_DATA",
            scope_id=str(request.provider_product_id),
            request_hash=request_hash.value,
            error_class="DATA_INTEGRITY",
            error_code=error_code,
            context=context,
            runtime_claim=runtime_claim,
        )

    def _record_capture_failure(
        self, capture: ProviderCapture, *, context: CommandContext, runtime_claim: AttemptClaim | None
    ) -> CaptureMutationResult:
        with self._uow_provider() as uow:
            if runtime_claim is not None:
                uow.runtime_finalization.lock_live(runtime_claim)
            receipt = uow.receipts.start(
                receipt_id=self._id_factory(),
                command_kind="CAPTURE_MARKET_DATA",
                scope_id=str(capture.provider_product_id),
                idempotency_key=context.idempotency_key,
                request_hash=capture.request_hash.value,
            )
            if not receipt.is_new:
                _ensure_replay_succeeded(receipt)
                if receipt.result_aggregate_id is None:
                    raise ArtifactIntegrityError("Capture receipt has no Capture identity")
                replay = uow.market.capture_source(UUID(receipt.result_aggregate_id), lock=False)
                result_hash = _required_result_hash(receipt.result_hash)
                self._finalize_capture_replay(
                    uow, capture=replay.capture, receipt_id=receipt.receipt_id, result_hash=result_hash, runtime_claim=runtime_claim
                )
                return CaptureMutationResult(
                    capture=replay.capture, artifact=replay.artifact, result_hash=result_hash, receipt_id=receipt.receipt_id, replayed=True
                )
            gap = SourceGap(
                gap_id=self._id_factory(),
                provider_product_id=capture.provider_product_id,
                capture_id=capture.capture_id,
                instrument_id=None,
                session_id=None,
                gap_kind=GapKind.PROVIDER_FAILURE,
                reason_code=GapReasonCode.PROVIDER_FAILURE,
                fact_kind=GapFactKind.DATA_CAPTURE,
                instrument_fact_kind=None,
                timeframe=None,
                price_basis=None,
                event_start=None,
                event_end=None,
                detail="Provider failure recorded without inventing Market facts",
            )
            capture, _ = uow.market.record_capture_failure(capture, gap)
            version = 1
            result_hash = canonical_json_sha256({"capture": capture, "gap_id": gap.gap_id})
            self._finish_mutation(
                uow,
                receipt_id=receipt.receipt_id,
                aggregate_kind="DATA_CAPTURE",
                aggregate_id=str(capture.capture_id),
                aggregate_version=version,
                result_hash=result_hash,
                action="CAPTURE_MARKET_DATA_FAILED",
                context=context,
                runtime_claim=runtime_claim,
            )
            if runtime_claim is not None:
                uow.runtime_finalization.fail(
                    runtime_claim,
                    receipt_id=receipt.receipt_id,
                    error_class="PROVIDER",
                    error_code=capture.error_code or "PROVIDER_FAILURE",
                )
            uow.commit()
            return CaptureMutationResult(
                capture=capture, artifact=None, result_hash=result_hash, receipt_id=receipt.receipt_id, replayed=False
            )

    def _finalize_capture_replay(
        self, uow: MarketUnitOfWork, *, capture: ProviderCapture, receipt_id: UUID, result_hash: str, runtime_claim: AttemptClaim | None
    ) -> None:
        if runtime_claim is None:
            return
        if capture.status is CaptureStatus.CAPTURED:
            uow.runtime_finalization.succeed(runtime_claim, receipt_id=receipt_id, result_hash=result_hash)
        else:
            uow.runtime_finalization.fail(
                runtime_claim, receipt_id=receipt_id, error_class="PROVIDER", error_code=capture.error_code or "PROVIDER_FAILURE"
            )
        uow.commit()
