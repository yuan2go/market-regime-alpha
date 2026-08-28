"""Explicit Market/PIT commands over a narrow bounded transaction."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, replace
from functools import wraps
from typing import Callable, Iterator, ParamSpec, TypeVar
from uuid import UUID, uuid4

from market_regime_alpha.market.domain import (
    CaptureStatus,
    GapFactKind,
    GapKind,
    GapReasonCode,
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
    MarketDatabaseClock,
    MarketNormalizer,
    MarketProvider,
    MarketProviderError,
    MarketUnitOfWork,
    MarketUnitOfWorkProvider,
)
from market_regime_alpha.runtime.application import CommandContext
from market_regime_alpha.runtime.errors import (
    ArtifactByteStoreError,
    ArtifactIntegrityError,
    CommandInProgressError,
    CommandPreviouslyFailedError,
    IdempotencyKeyReusedError,
    RuntimeNotFoundError,
    RuntimeStateConflictError,
    StaleFenceError,
)
from market_regime_alpha.runtime.ports import (
    ArtifactRecord,
    AttemptClaim,
    ByteVerification,
    ReceiptRecord,
)
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.identity import ContentHash
from market_regime_alpha.shared.time import DecisionTime, KnownTime


@dataclass(frozen=True, slots=True)
class MarketMutationResult:
    aggregate_kind: str
    aggregate_id: str
    aggregate_version: int
    result_hash: str
    receipt_id: UUID
    replayed: bool
    decision_visible_at: DecisionTime | None = None


@dataclass(frozen=True, slots=True)
class CaptureMutationResult:
    capture: ProviderCapture
    artifact: ArtifactRecord | None
    result_hash: str
    receipt_id: UUID
    replayed: bool


class _SourceArtifactVerificationFailure(ArtifactIntegrityError):
    """The verification observation and original command failure are durable."""


class _ConcurrentCommandSucceeded(RuntimeError):
    """A concurrent exact command committed while this worker was outside SQL."""

    def __init__(self, *, runtime_finalized: bool = False) -> None:
        super().__init__("concurrent exact command already succeeded")
        self.runtime_finalized = runtime_finalized


_P = ParamSpec("_P")
_R = TypeVar("_R")


def _replay_concurrent_success(command: Callable[_P, _R]) -> Callable[_P, _R]:
    """Resolve a post-preflight race through the canonical replay path."""

    @wraps(command)
    def wrapped(*args: _P.args, **kwargs: _P.kwargs) -> _R:
        try:
            return command(*args, **kwargs)
        except _ConcurrentCommandSucceeded as resolution:
            if resolution.runtime_finalized:
                replay_kwargs = dict(kwargs)
                replay_kwargs["runtime_claim"] = None
                return command(*args, **replay_kwargs)  # type: ignore[arg-type]
            return command(*args, **kwargs)

    return wrapped


class MarketApplication:
    """Provider and Artifact I/O outside; canonical mutation inside one short UoW."""

    def __init__(
        self,
        byte_store: MarketArtifactByteStore,
        uow_provider: MarketUnitOfWorkProvider,
        database_clock: MarketDatabaseClock,
        *,
        id_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self._byte_store = byte_store
        self._uow_provider = uow_provider
        self._database_clock = database_clock
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

    @_replay_concurrent_success
    def capture(
        self,
        request: CaptureRequest,
        provider: MarketProvider,
        context: CommandContext,
        *,
        runtime_claim: AttemptClaim | None = None,
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
            replay = self._capture_replay_before_io(
                request,
                request_hash=request_hash,
                context=context,
                runtime_claim=runtime_claim,
            )
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
                return self._record_capture_failure(
                    failure,
                    context=context,
                    runtime_claim=runtime_claim,
                )
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
            published = self._byte_store.publish_bytes(
                response.content,
                media_type=response.media_type,
            )
            verification = self._byte_store.verify(
                ContentHash(published.content_sha256),
                expected_size=published.size_bytes,
            )
            if verification.result != "VERIFIED":
                self._record_capture_artifact_failure(
                    request,
                    request_hash=request_hash,
                    error_code=f"ARTIFACT_{verification.result}",
                    context=context,
                    runtime_claim=runtime_claim,
                )
                raise ArtifactIntegrityError(
                    "Provider bytes failed verification before binding"
                )
        except (ArtifactByteStoreError, ValueError) as exc:
            self._record_capture_artifact_failure(
                request,
                request_hash=request_hash,
                error_code="ARTIFACT_PUBLISH_FAILED",
                context=context,
                runtime_claim=runtime_claim,
            )
            raise ArtifactIntegrityError(
                "Provider bytes could not establish a safe Artifact identity"
            ) from exc

        with self._terminal_failure_boundary(
            operation="CAPTURE_MARKET_DATA",
            scope_id=str(request.provider_product_id),
            request_hash=request_hash.value,
            error_class="DATA_INTEGRITY",
            error_code="CAPTURE_BINDING_REJECTED",
            context=context,
            runtime_claim=runtime_claim,
        ), self._uow_provider() as uow:
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
                source = uow.market.capture_source(
                    UUID(receipt.result_aggregate_id),
                    lock=False,
                )
                result_hash = _required_result_hash(receipt.result_hash)
                self._finalize_capture_replay(
                    uow,
                    capture=source.capture,
                    receipt_id=receipt.receipt_id,
                    result_hash=result_hash,
                    runtime_claim=runtime_claim,
                )
                return CaptureMutationResult(
                    capture=source.capture,
                    artifact=replace(source.artifact, replayed=True)
                    if source.artifact is not None
                    else None,
                    result_hash=result_hash,
                    receipt_id=receipt.receipt_id,
                    replayed=True,
                )
            artifact = uow.artifacts.register(
                artifact_id=self._id_factory(),
                published=published,
                retention_until=None,
                pin_reason_code=None,
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

    def _capture_replay_before_io(
        self,
        request: CaptureRequest,
        *,
        request_hash: ContentHash,
        context: CommandContext,
        runtime_claim: AttemptClaim | None,
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
            source = uow.market.capture_source(
                UUID(receipt.result_aggregate_id),
                lock=False,
            )
            result_hash = _required_result_hash(receipt.result_hash)
            self._finalize_capture_replay(
                uow,
                capture=source.capture,
                receipt_id=receipt.receipt_id,
                result_hash=result_hash,
                runtime_claim=runtime_claim,
            )
            return CaptureMutationResult(
                capture=source.capture,
                artifact=(
                    replace(source.artifact, replayed=True)
                    if source.artifact is not None
                    else None
                ),
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

    @contextmanager
    def _terminal_failure_boundary(
        self,
        *,
        operation: str,
        scope_id: str,
        request_hash: str,
        error_class: str,
        error_code: str,
        context: CommandContext,
        runtime_claim: AttemptClaim | None,
    ) -> Iterator[None]:
        """Classify deterministic command rejection without weakening fencing."""

        try:
            yield
        except StaleFenceError:
            raise
        except (CommandInProgressError, IdempotencyKeyReusedError) as exc:
            self._record_idempotency_rejection(
                operation=operation,
                scope_id=scope_id,
                rejected_request_hash=request_hash,
                rejection_code=exc.code,
                context=context,
                runtime_claim=runtime_claim,
            )
            raise
        except (
            ArtifactByteStoreError,
            ArtifactIntegrityError,
            CommandPreviouslyFailedError,
            RuntimeNotFoundError,
            RuntimeStateConflictError,
            ValueError,
        ):
            self._record_command_failure(
                operation=operation,
                scope_id=scope_id,
                request_hash=request_hash,
                error_class=error_class,
                error_code=error_code,
                context=context,
                runtime_claim=runtime_claim,
            )
            raise

    def _record_command_failure(
        self,
        *,
        operation: str,
        scope_id: str,
        request_hash: str,
        error_class: str,
        error_code: str,
        context: CommandContext,
        runtime_claim: AttemptClaim | None,
    ) -> None:
        """Commit the original command's FAILED receipt after business rollback."""

        try:
            with self._uow_provider() as uow:
                # A stale worker must not be able to record or finalize this failure.
                if runtime_claim is not None:
                    uow.runtime_finalization.lock_live(runtime_claim)
                receipt = uow.receipts.start(
                    receipt_id=self._id_factory(),
                    command_kind=operation,
                    scope_id=scope_id,
                    idempotency_key=context.idempotency_key,
                    request_hash=request_hash,
                )
                if receipt.is_new:
                    uow.receipts.fail(
                        receipt_id=receipt.receipt_id,
                        error_code=error_code,
                        runtime_claim=runtime_claim,
                    )
                    uow.audit.append(
                        audit_event_id=self._id_factory(),
                        receipt_id=receipt.receipt_id,
                        actor_type=context.actor_type.value,
                        actor_id=context.actor_id,
                        aggregate_kind="MARKET_COMMAND",
                        aggregate_id=f"{operation}:{scope_id}",
                        action="MARKET_COMMAND_FAILED",
                        reason_code=error_code,
                        before_version=None,
                        after_version=None,
                        runtime_claim=runtime_claim,
                    )
                elif receipt.status == "SUCCEEDED":
                    raise _ConcurrentCommandSucceeded()
                elif receipt.status != "FAILED":
                    raise RuntimeStateConflictError(
                        "cannot replace a non-failed terminal command receipt"
                    )
                if runtime_claim is not None:
                    terminal_error_code = (
                        error_code
                        if receipt.is_new
                        else receipt.error_code or error_code
                    )
                    uow.runtime_finalization.fail(
                        runtime_claim,
                        receipt_id=receipt.receipt_id,
                        error_class=error_class,
                        error_code=terminal_error_code,
                    )
                uow.commit()
        except (CommandInProgressError, IdempotencyKeyReusedError) as exc:
            self._record_idempotency_rejection(
                operation=operation,
                scope_id=scope_id,
                rejected_request_hash=request_hash,
                rejection_code=exc.code,
                context=context,
                runtime_claim=runtime_claim,
            )
            raise

    def _record_idempotency_rejection(
        self,
        *,
        operation: str,
        scope_id: str,
        rejected_request_hash: str,
        rejection_code: str,
        context: CommandContext,
        runtime_claim: AttemptClaim | None,
    ) -> None:
        """Terminalize a fenced Attempt without taking over another command key."""

        if runtime_claim is None:
            return
        with self._uow_provider() as uow:
            uow.runtime_finalization.lock_live(runtime_claim)
            self._append_idempotency_rejection(
                uow,
                operation=operation,
                scope_id=scope_id,
                rejected_request_hash=rejected_request_hash,
                rejection_code=rejection_code,
                context=context,
                runtime_claim=runtime_claim,
            )
            uow.commit()

    def _append_idempotency_rejection(
        self,
        uow: MarketUnitOfWork,
        *,
        operation: str,
        scope_id: str,
        rejected_request_hash: str,
        rejection_code: str,
        context: CommandContext,
        runtime_claim: AttemptClaim,
    ) -> None:
        """Append a rejection after the caller has locked the live Runtime claim."""

        rejection_scope = str(runtime_claim.attempt_id)
        rejection_key = f"market-command-rejection:{runtime_claim.attempt_id}"
        rejection_hash = canonical_json_sha256(
            {
                "operation": operation,
                "scope_id": scope_id,
                "idempotency_key": context.idempotency_key,
                "rejected_request_hash": rejected_request_hash,
                "rejection_code": rejection_code,
                "attempt_id": runtime_claim.attempt_id,
                "fence_token": runtime_claim.fence_token,
            }
        )
        receipt = uow.receipts.start(
            receipt_id=self._id_factory(),
            command_kind="MARKET_COMMAND_REJECTION",
            scope_id=rejection_scope,
            idempotency_key=rejection_key,
            request_hash=rejection_hash,
        )
        if receipt.is_new:
            uow.receipts.fail(
                receipt_id=receipt.receipt_id,
                error_code=rejection_code,
                runtime_claim=runtime_claim,
            )
            uow.audit.append(
                audit_event_id=self._id_factory(),
                receipt_id=receipt.receipt_id,
                actor_type=context.actor_type.value,
                actor_id=context.actor_id,
                aggregate_kind="MARKET_COMMAND",
                aggregate_id=f"{operation}:{scope_id}",
                action="MARKET_COMMAND_REJECTED",
                reason_code=rejection_code,
                before_version=None,
                after_version=None,
                runtime_claim=runtime_claim,
            )
        elif receipt.status != "FAILED":
            raise RuntimeStateConflictError(
                "idempotency rejection incident is not terminal FAILED"
            )
        uow.runtime_finalization.fail(
            runtime_claim,
            receipt_id=receipt.receipt_id,
            error_class="COMMAND",
            error_code=rejection_code,
        )

    @_replay_concurrent_success
    def normalize(
        self,
        capture_id: UUID,
        normalizer: MarketNormalizer,
        context: CommandContext,
        *,
        runtime_claim: AttemptClaim | None = None,
    ) -> MarketMutationResult:
        """Verify/read bytes and normalize outside; bind facts and fence atomically."""

        contract = normalizer.contract
        request_hash = canonical_json_sha256(
            {
                "capture_id": capture_id,
                "normalizer_contract": contract,
            }
        )
        with self._terminal_failure_boundary(
            operation="NORMALIZE_MARKET_PIT",
            scope_id=str(capture_id),
            request_hash=request_hash,
            error_class="COMMAND",
            error_code="NORMALIZE_COMMAND_REJECTED",
            context=context,
            runtime_claim=runtime_claim,
        ):
            replay = self._normalize_replay_before_io(
                capture_id,
                request_hash=request_hash,
                context=context,
                runtime_claim=runtime_claim,
            )
        if replay is not None:
            return replay
        with self._terminal_failure_boundary(
            operation="NORMALIZE_MARKET_PIT",
            scope_id=str(capture_id),
            request_hash=request_hash,
            error_class="DATA_INTEGRITY",
            error_code="CAPTURE_SOURCE_INVALID",
            context=context,
            runtime_claim=runtime_claim,
        ):
            with self._uow_provider() as lookup_uow:
                source = lookup_uow.market.capture_source(capture_id, lock=False)
            if source.artifact is None:
                raise ArtifactIntegrityError("Capture has no source Artifact")
        verifier_id = (
            f"market-normalizer:{contract.implementation}:{contract.version}"
        )
        self._verify_source_artifact(
            source.artifact,
            verifier_id=verifier_id,
            context=context,
            runtime_claim=runtime_claim,
            command_scope_id=str(capture_id),
            command_request_hash=request_hash,
        )
        try:
            content = self._byte_store.read_bytes(
                ContentHash(source.artifact.content_sha256),
                expected_size=source.artifact.size_bytes,
            )
        except ArtifactByteStoreError as exc:
            self._verify_source_artifact(
                source.artifact,
                verifier_id=verifier_id,
                context=context,
                runtime_claim=runtime_claim,
                command_scope_id=str(capture_id),
                command_request_hash=request_hash,
                forced_failure_code="ARTIFACT_READ_FAILED",
            )
            raise AssertionError("forced Artifact read failure must raise") from exc
        with self._terminal_failure_boundary(
            operation="NORMALIZE_MARKET_PIT",
            scope_id=str(capture_id),
            request_hash=request_hash,
            error_class="DOMAIN",
            error_code="NORMALIZER_OUTPUT_REJECTED",
            context=context,
            runtime_claim=runtime_claim,
        ):
            batch = normalizer.normalize(source.capture, content)
            if batch.source_capture_id != capture_id:
                raise ValueError("Normalizer returned evidence for a different Capture")
            if batch.source_provider_product_id != source.capture.provider_product_id:
                raise ValueError(
                    "Normalizer returned evidence for a different ProviderProduct"
                )
        with self._terminal_failure_boundary(
            operation="NORMALIZE_MARKET_PIT",
            scope_id=str(capture_id),
            request_hash=request_hash,
            error_class="DATA_INTEGRITY",
            error_code="NORMALIZATION_BINDING_REJECTED",
            context=context,
            runtime_claim=runtime_claim,
        ), self._uow_provider() as uow:
            if runtime_claim is not None:
                uow.runtime_finalization.lock_live(runtime_claim)
            receipt = uow.receipts.start(
                receipt_id=self._id_factory(),
                command_kind="NORMALIZE_MARKET_PIT",
                scope_id=str(capture_id),
                idempotency_key=context.idempotency_key,
                request_hash=request_hash,
            )
            if not receipt.is_new:
                _ensure_replay_succeeded(receipt)
                replay = _replayed_mutation(
                    receipt,
                    decision_visible_at=uow.market.normalization_decision_visible_at(
                        capture_id
                    ),
                )
                if runtime_claim is not None:
                    uow.runtime_finalization.succeed(
                        runtime_claim,
                        receipt_id=receipt.receipt_id,
                        result_hash=replay.result_hash,
                    )
                    uow.commit()
                return replay
            decision_visible_at = uow.market.insert_normalization(
                batch,
                expected_artifact_sha256=ContentHash(
                    source.artifact.content_sha256
                ),
                expected_artifact_size=source.artifact.size_bytes,
            )
            result_hash = canonical_json_sha256(
                {
                    "normalization": batch,
                    "decision_visible_at": decision_visible_at,
                }
            )
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
                decision_visible_at=decision_visible_at,
            )

    def _normalize_replay_before_io(
        self,
        capture_id: UUID,
        *,
        request_hash: str,
        context: CommandContext,
        runtime_claim: AttemptClaim | None,
    ) -> MarketMutationResult | None:
        """Resolve an exact committed normalization before Artifact/normalizer I/O."""

        with self._uow_provider() as uow:
            if runtime_claim is not None:
                uow.runtime_finalization.lock_live(runtime_claim)
            receipt = uow.receipts.start(
                receipt_id=self._id_factory(),
                command_kind="NORMALIZE_MARKET_PIT",
                scope_id=str(capture_id),
                idempotency_key=context.idempotency_key,
                request_hash=request_hash,
            )
            if receipt.is_new:
                return None
            _ensure_replay_succeeded(receipt)
            replay = _replayed_mutation(
                receipt,
                decision_visible_at=uow.market.normalization_decision_visible_at(
                    capture_id
                ),
            )
            if runtime_claim is not None:
                uow.runtime_finalization.succeed(
                    runtime_claim,
                    receipt_id=receipt.receipt_id,
                    result_hash=replay.result_hash,
                )
                uow.commit()
            return replay

    def _verify_source_artifact(
        self,
        artifact: ArtifactRecord,
        *,
        verifier_id: str,
        context: CommandContext,
        runtime_claim: AttemptClaim | None,
        command_scope_id: str,
        command_request_hash: str,
        forced_failure_code: str | None = None,
    ) -> None:
        """Persist verification and terminal command failure in one short UoW."""

        verification_exception: ArtifactByteStoreError | None = None
        try:
            byte_result = self._byte_store.verify(
                ContentHash(artifact.content_sha256),
                expected_size=artifact.size_bytes,
            )
        except ArtifactByteStoreError as exc:
            verification_exception = exc
            byte_result = ByteVerification(
                result="INTEGRITY_ERROR",
                observed_exists=False,
                observed_size_bytes=None,
                observed_sha256=None,
            )
        failure_code = forced_failure_code
        if byte_result.result != "VERIFIED" and failure_code is None:
            failure_code = "ARTIFACT_INTEGRITY_FAILED"
        verification_id = self._id_factory()
        receipt_id = self._id_factory()
        verification_key = f"market-source-verify:{self._id_factory()}"
        request_hash = canonical_json_sha256(
            {
                "artifact_id": artifact.artifact_id,
                "content_sha256": artifact.content_sha256,
                "expected_size": artifact.size_bytes,
                "verifier_id": verifier_id,
                "policy": "MARKET_NORMALIZATION_SOURCE_READ",
                "observation": byte_result,
            }
        )
        concurrent_success = False
        idempotency_collision: CommandInProgressError | IdempotencyKeyReusedError | None = (
            None
        )
        with self._uow_provider() as uow:
            if runtime_claim is not None:
                uow.runtime_finalization.lock_live(runtime_claim)
            current_artifact = uow.artifacts.get(artifact.artifact_id)
            receipt = uow.receipts.start(
                receipt_id=receipt_id,
                command_kind="VERIFY_MARKET_SOURCE_ARTIFACT",
                scope_id=str(artifact.artifact_id),
                idempotency_key=verification_key,
                request_hash=request_hash,
            )
            record = uow.artifacts.record_verification(
                verification_id=verification_id,
                receipt_id=receipt.receipt_id,
                artifact=current_artifact,
                verifier_id=verifier_id,
                policy="MARKET_NORMALIZATION_SOURCE_READ",
                verification=byte_result,
            )
            result_hash = canonical_json_sha256(record)
            uow.receipts.succeed(
                receipt_id=receipt.receipt_id,
                aggregate_kind="ARTIFACT_VERIFICATION",
                aggregate_id=str(record.verification_id),
                aggregate_version=1,
                result_hash=result_hash,
                runtime_claim=runtime_claim,
            )
            uow.audit.append(
                audit_event_id=self._id_factory(),
                receipt_id=receipt.receipt_id,
                actor_type=context.actor_type.value,
                actor_id=context.actor_id,
                aggregate_kind="ARTIFACT",
                aggregate_id=str(artifact.artifact_id),
                action="VERIFY_MARKET_SOURCE_ARTIFACT",
                reason_code=context.reason_code,
                before_version=None,
                after_version=1,
                runtime_claim=runtime_claim,
            )
            if failure_code is not None:
                try:
                    command_receipt = uow.receipts.start(
                        receipt_id=self._id_factory(),
                        command_kind="NORMALIZE_MARKET_PIT",
                        scope_id=command_scope_id,
                        idempotency_key=context.idempotency_key,
                        request_hash=command_request_hash,
                    )
                except (CommandInProgressError, IdempotencyKeyReusedError) as exc:
                    if runtime_claim is not None:
                        self._append_idempotency_rejection(
                            uow,
                            operation="NORMALIZE_MARKET_PIT",
                            scope_id=command_scope_id,
                            rejected_request_hash=command_request_hash,
                            rejection_code=exc.code,
                            context=context,
                            runtime_claim=runtime_claim,
                        )
                    idempotency_collision = exc
                else:
                    if command_receipt.is_new:
                        uow.receipts.fail(
                            receipt_id=command_receipt.receipt_id,
                            error_code=failure_code,
                            runtime_claim=runtime_claim,
                        )
                        uow.audit.append(
                            audit_event_id=self._id_factory(),
                            receipt_id=command_receipt.receipt_id,
                            actor_type=context.actor_type.value,
                            actor_id=context.actor_id,
                            aggregate_kind="MARKET_COMMAND",
                            aggregate_id=f"NORMALIZE_MARKET_PIT:{command_scope_id}",
                            action="MARKET_COMMAND_FAILED",
                            reason_code=failure_code,
                            before_version=None,
                            after_version=None,
                            runtime_claim=runtime_claim,
                        )
                    elif command_receipt.status == "SUCCEEDED":
                        result_hash = _required_result_hash(command_receipt.result_hash)
                        if runtime_claim is not None:
                            uow.runtime_finalization.succeed(
                                runtime_claim,
                                receipt_id=command_receipt.receipt_id,
                                result_hash=result_hash,
                            )
                        concurrent_success = True
                    elif command_receipt.status != "FAILED":
                        raise RuntimeStateConflictError(
                            "cannot record Artifact failure over a non-failed command"
                        )
                    if runtime_claim is not None and not concurrent_success:
                        uow.runtime_finalization.fail(
                            runtime_claim,
                            receipt_id=command_receipt.receipt_id,
                            error_class="DATA_INTEGRITY",
                            error_code=failure_code,
                        )
            uow.commit()
        if idempotency_collision is not None:
            raise idempotency_collision
        if concurrent_success:
            raise _ConcurrentCommandSucceeded(
                runtime_finalized=runtime_claim is not None
            )
        if failure_code is not None:
            message = (
                "Capture source bytes could not be read after verification"
                if forced_failure_code is not None
                else "Capture source Artifact failed authoritative verification: "
                f"{byte_result.result}"
            )
            if verification_exception is not None:
                raise _SourceArtifactVerificationFailure(message) from verification_exception
            raise _SourceArtifactVerificationFailure(message)

    def _record_capture_failure(
        self,
        capture: ProviderCapture,
        *,
        context: CommandContext,
        runtime_claim: AttemptClaim | None,
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
                replay = uow.market.capture_source(
                    UUID(receipt.result_aggregate_id), lock=False
                )
                result_hash = _required_result_hash(receipt.result_hash)
                self._finalize_capture_replay(
                    uow,
                    capture=replay.capture,
                    receipt_id=receipt.receipt_id,
                    result_hash=result_hash,
                    runtime_claim=runtime_claim,
                )
                return CaptureMutationResult(
                    capture=replay.capture,
                    artifact=replay.artifact,
                    result_hash=result_hash,
                    receipt_id=receipt.receipt_id,
                    replayed=True,
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

    def _finalize_capture_replay(
        self,
        uow: MarketUnitOfWork,
        *,
        capture: ProviderCapture,
        receipt_id: UUID,
        result_hash: str,
        runtime_claim: AttemptClaim | None,
    ) -> None:
        if runtime_claim is None:
            return
        if capture.status is CaptureStatus.CAPTURED:
            uow.runtime_finalization.succeed(
                runtime_claim,
                receipt_id=receipt_id,
                result_hash=result_hash,
            )
        else:
            uow.runtime_finalization.fail(
                runtime_claim,
                receipt_id=receipt_id,
                error_class="PROVIDER",
                error_code=capture.error_code or "PROVIDER_FAILURE",
            )
        uow.commit()

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


def _ensure_replay_succeeded(receipt: ReceiptRecord) -> None:
    if receipt.status in {"FAILED", "BLOCKED"}:
        raise CommandPreviouslyFailedError(
            receipt.error_code or "COMMAND_FAILED_WITHOUT_ERROR_CODE"
        )
    if receipt.status != "SUCCEEDED":
        raise RuntimeStateConflictError(
            f"receipt {receipt.receipt_id} is not a replayable terminal result"
        )


def _replayed_mutation(
    receipt,
    *,
    decision_visible_at: DecisionTime | None = None,
) -> MarketMutationResult:
    _ensure_replay_succeeded(receipt)
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
        decision_visible_at=decision_visible_at,
    )


__all__ = [
    "CaptureMutationResult",
    "MarketApplication",
    "MarketMutationResult",
]
