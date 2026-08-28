"""Explicit Market/PIT commands over a narrow bounded transaction."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Callable
from uuid import UUID, uuid4

from market_regime_alpha.market.domain import (
    CaptureStatus,
    GapKind,
    NormalizationBatch,
    Provider,
    ProviderCapture,
    ProviderProduct,
    SourceAvailabilityStatus,
    SourceGap,
    TemporalEnvelope,
)
from market_regime_alpha.market.ports import (
    CaptureRequest,
    MarketArtifactByteStore,
    MarketNormalizer,
    MarketProvider,
    MarketProviderError,
    MarketUnitOfWork,
    MarketUnitOfWorkProvider,
)
from market_regime_alpha.runtime.application import CommandContext
from market_regime_alpha.runtime.errors import ArtifactIntegrityError
from market_regime_alpha.runtime.ports import ArtifactRecord, AttemptClaim
from market_regime_alpha.shared.hashing import canonical_json_sha256


@dataclass(frozen=True, slots=True)
class MarketMutationResult:
    aggregate_kind: str
    aggregate_id: str
    aggregate_version: int
    result_hash: str
    receipt_id: UUID
    replayed: bool


@dataclass(frozen=True, slots=True)
class CaptureMutationResult:
    capture: ProviderCapture
    artifact: ArtifactRecord | None
    result_hash: str
    receipt_id: UUID
    replayed: bool


class MarketApplication:
    """Provider and Artifact I/O outside; canonical mutation inside one short UoW."""

    def __init__(
        self,
        byte_store: MarketArtifactByteStore,
        uow_provider: MarketUnitOfWorkProvider,
        *,
        clock: Callable[[], datetime] | None = None,
        id_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self._byte_store = byte_store
        self._uow_provider = uow_provider
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._id_factory = id_factory

    def register_provider(
        self,
        provider: Provider,
        context: CommandContext,
    ) -> MarketMutationResult:
        request_hash = canonical_json_sha256(provider)
        result_hash = canonical_json_sha256(
            {"provider_id": provider.provider_id, "version": 1}
        )
        with self._uow_provider() as uow:
            receipt = uow.receipts.start(
                receipt_id=self._id_factory(),
                command_kind="REGISTER_MARKET_PROVIDER",
                scope_id=provider.provider_code,
                idempotency_key=context.idempotency_key,
                request_hash=request_hash,
            )
            if not receipt.is_new:
                return _replayed_mutation(receipt)
            version = uow.market.register_provider(provider)
            self._finish_mutation(
                uow,
                receipt_id=receipt.receipt_id,
                aggregate_kind="MARKET_PROVIDER",
                aggregate_id=str(provider.provider_id),
                aggregate_version=version,
                result_hash=result_hash,
                action="REGISTER_MARKET_PROVIDER",
                context=context,
            )
            uow.commit()
            return MarketMutationResult(
                aggregate_kind="MARKET_PROVIDER",
                aggregate_id=str(provider.provider_id),
                aggregate_version=version,
                result_hash=result_hash,
                receipt_id=receipt.receipt_id,
                replayed=False,
            )

    def register_provider_product(
        self,
        product: ProviderProduct,
        context: CommandContext,
    ) -> MarketMutationResult:
        request_hash = canonical_json_sha256(product)
        result_hash = canonical_json_sha256(
            {
                "provider_product_id": product.provider_product_id,
                "revision": product.revision,
            }
        )
        with self._uow_provider() as uow:
            receipt = uow.receipts.start(
                receipt_id=self._id_factory(),
                command_kind="REGISTER_PROVIDER_PRODUCT",
                scope_id=f"{product.provider_id}:{product.product_code}",
                idempotency_key=context.idempotency_key,
                request_hash=request_hash,
            )
            if not receipt.is_new:
                return _replayed_mutation(receipt)
            version = uow.market.register_provider_product(product)
            self._finish_mutation(
                uow,
                receipt_id=receipt.receipt_id,
                aggregate_kind="PROVIDER_PRODUCT",
                aggregate_id=str(product.provider_product_id),
                aggregate_version=version,
                result_hash=result_hash,
                action="REGISTER_PROVIDER_PRODUCT",
                context=context,
            )
            uow.commit()
            return MarketMutationResult(
                aggregate_kind="PROVIDER_PRODUCT",
                aggregate_id=str(product.provider_product_id),
                aggregate_version=version,
                result_hash=result_hash,
                receipt_id=receipt.receipt_id,
                replayed=False,
            )

    def capture(
        self,
        request: CaptureRequest,
        provider: MarketProvider,
        context: CommandContext,
        *,
        runtime_claim: AttemptClaim | None = None,
    ) -> CaptureMutationResult:
        """Perform observational Provider/CAS I/O before opening the write transaction."""

        request_hash = canonical_json_sha256(request)
        started_at = self._clock()
        try:
            response = provider.capture(request)
        except MarketProviderError as exc:
            completed_at = self._clock()
            temporal = TemporalEnvelope(
                provider_time=None,
                source_availability_status=SourceAvailabilityStatus.UNKNOWN,
                source_available_at=None,
                capture_started_at=started_at,
                capture_completed_at=completed_at,
                known_at=completed_at,
                decision_visible_at=completed_at,
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
            return self._record_capture_failure(
                failure,
                context=context,
                runtime_claim=runtime_claim,
            )
        completed_at = self._clock()
        temporal = TemporalEnvelope(
            provider_time=response.provider_time,
            source_availability_status=response.source_availability_status,
            source_available_at=response.source_available_at,
            capture_started_at=started_at,
            capture_completed_at=completed_at,
            known_at=completed_at,
            decision_visible_at=completed_at,
        )
        published = self._byte_store.publish_bytes(
            response.content,
            media_type=response.media_type,
        )
        verification = self._byte_store.verify(
            published.content_sha256,
            expected_size=published.size_bytes,
        )
        if verification.result != "VERIFIED":
            raise ArtifactIntegrityError("Provider bytes failed verification before binding")

        with self._uow_provider() as uow:
            receipt = uow.receipts.start(
                receipt_id=self._id_factory(),
                command_kind="CAPTURE_MARKET_DATA",
                scope_id=str(request.provider_product_id),
                idempotency_key=context.idempotency_key,
                request_hash=request_hash,
            )
            if not receipt.is_new:
                if receipt.result_aggregate_id is None:
                    raise ArtifactIntegrityError("Capture receipt has no Capture identity")
                source = uow.market.capture_source(
                    UUID(receipt.result_aggregate_id),
                    lock=False,
                )
                return CaptureMutationResult(
                    capture=source.capture,
                    artifact=replace(source.artifact, replayed=True)
                    if source.artifact is not None
                    else None,
                    result_hash=_required_result_hash(receipt.result_hash),
                    receipt_id=receipt.receipt_id,
                    replayed=True,
                )
            artifact = uow.artifacts.register(
                artifact_id=self._id_factory(),
                published=published,
                retention_until=None,
                pin_reason_code=None,
            )
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
            capture = uow.market.insert_capture(capture, published)
            version = 1
            result_hash = canonical_json_sha256(
                {
                    "capture": capture,
                    "artifact_hash": artifact.content_sha256,
                    "artifact_size": artifact.size_bytes,
                }
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
                uow.runtime_finalization.succeed(
                    runtime_claim,
                    receipt_id=receipt.receipt_id,
                    result_hash=result_hash,
                )
            uow.commit()
            return CaptureMutationResult(
                capture=capture,
                artifact=artifact,
                result_hash=result_hash,
                receipt_id=receipt.receipt_id,
                replayed=False,
            )

    def normalize(
        self,
        capture_id: UUID,
        normalizer: MarketNormalizer,
        context: CommandContext,
        *,
        runtime_claim: AttemptClaim | None = None,
    ) -> MarketMutationResult:
        """Verify/read bytes and normalize outside; bind facts and fence atomically."""

        with self._uow_provider() as lookup_uow:
            source = lookup_uow.market.capture_source(capture_id, lock=False)
        if source.artifact is None or source.artifact.integrity_state != "AVAILABLE":
            raise ArtifactIntegrityError("Capture has no AVAILABLE source Artifact")
        content = self._byte_store.read_bytes(
            source.artifact.content_sha256,
            expected_size=source.artifact.size_bytes,
        )
        batch = normalizer.normalize(source.capture, content)
        if batch.source_capture_id != capture_id:
            raise ValueError("Normalizer returned evidence for a different Capture")
        request_hash = canonical_json_sha256(
            {
                "capture_id": capture_id,
                "capture_artifact_hash": source.artifact.content_sha256,
                "normalization": batch,
            }
        )
        result_hash = canonical_json_sha256(batch)

        with self._uow_provider() as uow:
            receipt = uow.receipts.start(
                receipt_id=self._id_factory(),
                command_kind="NORMALIZE_MARKET_PIT",
                scope_id=str(capture_id),
                idempotency_key=context.idempotency_key,
                request_hash=request_hash,
            )
            if not receipt.is_new:
                return _replayed_mutation(receipt)
            locked = uow.market.lock_capture_source(capture_id)
            if (
                locked.artifact is None
                or locked.artifact.content_sha256 != source.artifact.content_sha256
                or locked.artifact.size_bytes != source.artifact.size_bytes
            ):
                raise ArtifactIntegrityError("Capture source changed during normalization")
            self._insert_batch(uow, batch)
            self._finish_mutation(
                uow,
                receipt_id=receipt.receipt_id,
                aggregate_kind="MARKET_NORMALIZATION",
                aggregate_id=str(capture_id),
                aggregate_version=1,
                result_hash=result_hash,
                action="NORMALIZE_MARKET_PIT",
                context=context,
                runtime_claim=runtime_claim,
            )
            if runtime_claim is not None:
                uow.runtime_finalization.succeed(
                    runtime_claim,
                    receipt_id=receipt.receipt_id,
                    result_hash=result_hash,
                )
            uow.commit()
            return MarketMutationResult(
                aggregate_kind="MARKET_NORMALIZATION",
                aggregate_id=str(capture_id),
                aggregate_version=1,
                result_hash=result_hash,
                receipt_id=receipt.receipt_id,
                replayed=False,
            )

    def _record_capture_failure(
        self,
        capture: ProviderCapture,
        *,
        context: CommandContext,
        runtime_claim: AttemptClaim | None,
    ) -> CaptureMutationResult:
        with self._uow_provider() as uow:
            receipt = uow.receipts.start(
                receipt_id=self._id_factory(),
                command_kind="CAPTURE_MARKET_DATA",
                scope_id=str(capture.provider_product_id),
                idempotency_key=context.idempotency_key,
                request_hash=capture.request_hash,
            )
            if not receipt.is_new:
                if receipt.result_aggregate_id is None:
                    raise ArtifactIntegrityError("Capture receipt has no Capture identity")
                replay = uow.market.capture_source(
                    UUID(receipt.result_aggregate_id), lock=False
                )
                return CaptureMutationResult(
                    capture=replay.capture,
                    artifact=replay.artifact,
                    result_hash=_required_result_hash(receipt.result_hash),
                    receipt_id=receipt.receipt_id,
                    replayed=True,
                )
            capture = uow.market.insert_capture(capture, None)
            version = 1
            gap = SourceGap(
                gap_id=self._id_factory(),
                provider_product_id=capture.provider_product_id,
                capture_id=capture.capture_id,
                instrument_id=None,
                session_id=None,
                gap_kind=GapKind.PROVIDER_FAILURE,
                reason_code=capture.error_code or "PROVIDER_FAILURE",
                fact_kind="DATA_CAPTURE",
                timeframe=None,
                adjustment_basis=None,
                event_start=None,
                event_end=None,
                detail="Provider failure recorded without inventing Market facts",
            )
            uow.market.insert_source_gap(gap)
            result_hash = canonical_json_sha256(
                {"capture": capture, "gap_id": gap.gap_id}
            )
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
                capture=capture,
                artifact=None,
                result_hash=result_hash,
                receipt_id=receipt.receipt_id,
                replayed=False,
            )

    @staticmethod
    def _insert_batch(uow: MarketUnitOfWork, batch: NormalizationBatch) -> None:
        for instrument in batch.instruments:
            uow.market.insert_instrument(instrument)
        for identifier in batch.instrument_identifiers:
            uow.market.insert_instrument_identifier(identifier)
        for session in batch.trading_sessions:
            uow.market.insert_trading_session(session)
        for classification in batch.classifications:
            uow.market.insert_classification(classification)
        for membership in batch.classification_memberships:
            uow.market.insert_classification_membership(membership)
        for bar in batch.bars:
            uow.market.insert_bar_revision(bar)
        for instrument_fact in batch.instrument_facts:
            uow.market.insert_instrument_fact_revision(instrument_fact)
        for security_fact in batch.security_status_facts:
            uow.market.insert_security_status_revision(security_fact)
        for action in batch.corporate_actions:
            uow.market.insert_corporate_action(action)
        for gap in batch.gaps:
            uow.market.insert_source_gap(gap)

    def _finish_mutation(
        self,
        uow: MarketUnitOfWork,
        *,
        receipt_id: UUID,
        aggregate_kind: str,
        aggregate_id: str,
        aggregate_version: int,
        result_hash: str,
        action: str,
        context: CommandContext,
        runtime_claim: AttemptClaim | None = None,
    ) -> None:
        uow.receipts.succeed(
            receipt_id=receipt_id,
            aggregate_kind=aggregate_kind,
            aggregate_id=aggregate_id,
            aggregate_version=aggregate_version,
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
            after_version=aggregate_version,
            runtime_claim=runtime_claim,
        )


def _required_result_hash(value: str | None) -> str:
    if value is None:
        raise ArtifactIntegrityError("terminal receipt has no result hash")
    return value


def _replayed_mutation(receipt) -> MarketMutationResult:
    if (
        receipt.result_aggregate_kind is None
        or receipt.result_aggregate_id is None
        or receipt.result_aggregate_version is None
        or receipt.result_hash is None
    ):
        raise ArtifactIntegrityError("terminal receipt has no complete result")
    return MarketMutationResult(
        aggregate_kind=receipt.result_aggregate_kind,
        aggregate_id=receipt.result_aggregate_id,
        aggregate_version=receipt.result_aggregate_version,
        result_hash=receipt.result_hash,
        receipt_id=receipt.receipt_id,
        replayed=True,
    )


__all__ = [
    "CaptureMutationResult",
    "MarketApplication",
    "MarketMutationResult",
]
