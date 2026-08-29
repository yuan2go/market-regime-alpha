"""Explicit Market/PIT commands over a narrow bounded transaction."""

from __future__ import annotations

from uuid import UUID

from market_regime_alpha.market.ports import (
    MarketNormalizer,
)
from market_regime_alpha.runtime.application import CommandContext
from market_regime_alpha.runtime.errors import (
    ArtifactByteStoreError,
    ArtifactIntegrityError,
    CommandInProgressError,
    IdempotencyKeyReusedError,
    RuntimeStateConflictError,
)
from market_regime_alpha.runtime.ports import (
    ArtifactRecord,
    AttemptClaim,
    ByteVerification,
)
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.identity import ContentHash

from market_regime_alpha.market.application._support import (
    _ConcurrentCommandSucceeded,
    _MarketCommandSupport,
    _SourceArtifactVerificationFailure,
    _ensure_replay_succeeded,
    _replay_concurrent_success,
    _replayed_mutation,
    _required_result_hash,
)
from market_regime_alpha.market.application.results import MarketMutationResult


class _NormalizationCommands(_MarketCommandSupport):
    @_replay_concurrent_success
    def normalize(
        self, capture_id: UUID, normalizer: MarketNormalizer, context: CommandContext, *, runtime_claim: AttemptClaim | None = None
    ) -> MarketMutationResult:
        """Verify/read bytes and normalize outside; bind facts and fence atomically."""
        contract = normalizer.contract
        request_hash = canonical_json_sha256({"capture_id": capture_id, "normalizer_contract": contract})
        with self._terminal_failure_boundary(
            operation="NORMALIZE_MARKET_PIT",
            scope_id=str(capture_id),
            request_hash=request_hash,
            error_class="COMMAND",
            error_code="NORMALIZE_COMMAND_REJECTED",
            context=context,
            runtime_claim=runtime_claim,
        ):
            replay = self._normalize_replay_before_io(capture_id, request_hash=request_hash, context=context, runtime_claim=runtime_claim)
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
        verifier_id = f"market-normalizer:{contract.implementation}:{contract.version}"
        self._verify_source_artifact(
            source.artifact,
            verifier_id=verifier_id,
            context=context,
            runtime_claim=runtime_claim,
            command_scope_id=str(capture_id),
            command_request_hash=request_hash,
        )
        try:
            content = self._byte_store.read_bytes(ContentHash(source.artifact.content_sha256), expected_size=source.artifact.size_bytes)
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
                raise ValueError("Normalizer returned evidence for a different ProviderProduct")
        with (
            self._terminal_failure_boundary(
                operation="NORMALIZE_MARKET_PIT",
                scope_id=str(capture_id),
                request_hash=request_hash,
                error_class="DATA_INTEGRITY",
                error_code="NORMALIZATION_BINDING_REJECTED",
                context=context,
                runtime_claim=runtime_claim,
            ),
            self._uow_provider() as uow,
        ):
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
                replay = _replayed_mutation(receipt, decision_visible_at=uow.market.normalization_decision_visible_at(capture_id))
                if runtime_claim is not None:
                    uow.runtime_finalization.succeed(runtime_claim, receipt_id=receipt.receipt_id, result_hash=replay.result_hash)
                    uow.commit()
                return replay
            decision_visible_at = uow.market.insert_normalization(
                batch,
                expected_artifact_sha256=ContentHash(source.artifact.content_sha256),
                expected_artifact_size=source.artifact.size_bytes,
            )
            result_hash = canonical_json_sha256({"normalization": batch, "decision_visible_at": decision_visible_at})
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
                uow.runtime_finalization.succeed(runtime_claim, receipt_id=receipt.receipt_id, result_hash=result_hash)
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
        self, capture_id: UUID, *, request_hash: str, context: CommandContext, runtime_claim: AttemptClaim | None
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
            replay = _replayed_mutation(receipt, decision_visible_at=uow.market.normalization_decision_visible_at(capture_id))
            if runtime_claim is not None:
                uow.runtime_finalization.succeed(runtime_claim, receipt_id=receipt.receipt_id, result_hash=replay.result_hash)
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
            byte_result = self._byte_store.verify(ContentHash(artifact.content_sha256), expected_size=artifact.size_bytes)
        except ArtifactByteStoreError as exc:
            verification_exception = exc
            byte_result = ByteVerification(result="INTEGRITY_ERROR", observed_exists=False, observed_size_bytes=None, observed_sha256=None)
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
        idempotency_collision: CommandInProgressError | IdempotencyKeyReusedError | None = None
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
                        uow.receipts.fail(receipt_id=command_receipt.receipt_id, error_code=failure_code, runtime_claim=runtime_claim)
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
                            uow.runtime_finalization.succeed(runtime_claim, receipt_id=command_receipt.receipt_id, result_hash=result_hash)
                        concurrent_success = True
                    elif command_receipt.status != "FAILED":
                        raise RuntimeStateConflictError("cannot record Artifact failure over a non-failed command")
                    if runtime_claim is not None and (not concurrent_success):
                        uow.runtime_finalization.fail(
                            runtime_claim, receipt_id=command_receipt.receipt_id, error_class="DATA_INTEGRITY", error_code=failure_code
                        )
            uow.commit()
        if idempotency_collision is not None:
            raise idempotency_collision
        if concurrent_success:
            raise _ConcurrentCommandSucceeded(runtime_finalized=runtime_claim is not None)
        if failure_code is not None:
            message = (
                "Capture source bytes could not be read after verification"
                if forced_failure_code is not None
                else f"Capture source Artifact failed authoritative verification: {byte_result.result}"
            )
            if verification_exception is not None:
                raise _SourceArtifactVerificationFailure(message) from verification_exception
            raise _SourceArtifactVerificationFailure(message)
