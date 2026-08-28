"""Artifact publication, verification, orphan quarantine, and explicit GC commands."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
import re
from uuid import UUID, uuid4

from market_regime_alpha.runtime.application.service import (
    ActorType,
    CommandContext,
)
from market_regime_alpha.runtime.errors import ArtifactByteStoreError, ArtifactIntegrityError
from market_regime_alpha.runtime.ports import (
    ArtifactByteStore,
    ArtifactRecord,
    ArtifactVerificationRecord,
    ByteVerification,
    ReceiptRecord,
    RuntimeUnitOfWork,
    RuntimeUnitOfWorkProvider,
)
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.identity import ContentHash
from market_regime_alpha.shared.time import require_utc


_CODE = re.compile(r"^[A-Z][A-Z0-9_]{0,99}$")


@dataclass(frozen=True, slots=True)
class ArtifactGcScan:
    scan_id: UUID
    observed: tuple[str, ...]
    quarantined: tuple[str, ...]
    protected: tuple[str, ...]


class ArtifactApplication:
    """Coordinate bytes outside and canonical metadata inside short UoWs."""

    def __init__(
        self,
        byte_store: ArtifactByteStore,
        uow_provider: RuntimeUnitOfWorkProvider,
    ) -> None:
        self._byte_store = byte_store
        self._uow_provider = uow_provider

    def publish(
        self,
        content: bytes,
        *,
        media_type: str,
        context: CommandContext,
        expected_sha256: str | None = None,
        retention_until: datetime | None = None,
        pin_reason_code: str | None = None,
    ) -> ArtifactRecord:
        if pin_reason_code is not None and not _CODE.fullmatch(pin_reason_code):
            raise ValueError("pin_reason_code has an invalid format")
        if retention_until is not None:
            retention_until = require_utc(
                retention_until,
                field="retention_until",
            )
        published = self._byte_store.publish_bytes(
            content,
            media_type=media_type,
            expected_sha256=expected_sha256,
        )
        verification = self._byte_store.verify(
            published.content_sha256,
            expected_size=published.size_bytes,
        )
        if verification.result != "VERIFIED":
            raise ArtifactIntegrityError("bytes did not verify before database binding")
        request_hash = canonical_json_sha256(
            {
                "published": published,
                "retention_until": retention_until,
                "pin_reason_code": pin_reason_code,
            }
        )
        with self._uow_provider() as uow:
            receipt = uow.receipts.start(
                receipt_id=uuid4(),
                command_kind="REGISTER_ARTIFACT",
                scope_id=published.content_sha256,
                idempotency_key=context.idempotency_key,
                request_hash=request_hash,
            )
            if not receipt.is_new:
                if receipt.result_aggregate_id is None:
                    raise ArtifactIntegrityError("artifact receipt has no result identity")
                return replace(
                    uow.artifacts.get(UUID(receipt.result_aggregate_id)),
                    replayed=True,
                )
            artifact = uow.artifacts.register(
                artifact_id=uuid4(),
                published=published,
                retention_until=retention_until,
                pin_reason_code=pin_reason_code,
            )
            uow.artifacts.record_verification(
                verification_id=uuid4(),
                receipt_id=receipt.receipt_id,
                artifact=artifact,
                verifier_id="artifact-publisher",
                policy="PUBLISH_READ_AFTER_WRITE",
                verification=verification,
            )
            artifact = uow.artifacts.get(artifact.artifact_id)
            result_hash = _artifact_result_hash(artifact)
            uow.receipts.succeed(
                receipt_id=receipt.receipt_id,
                aggregate_kind="ARTIFACT",
                aggregate_id=str(artifact.artifact_id),
                aggregate_version=1,
                result_hash=result_hash,
            )
            _append_artifact_audit(
                uow,
                receipt=receipt,
                context=context,
                aggregate_id=str(artifact.artifact_id),
                action="REGISTER_ARTIFACT",
                before_version=None,
                after_version=1,
            )
            uow.commit()
            return artifact

    def verify(
        self,
        artifact_id: UUID,
        *,
        verifier_id: str,
        context: CommandContext,
    ) -> ArtifactVerificationRecord:
        if not verifier_id:
            raise ValueError("verifier_id is required")
        request_hash = canonical_json_sha256(
            {
                "artifact_id": artifact_id,
                "verifier_id": verifier_id,
                "policy": "AUTHORITATIVE_READ",
            }
        )
        # Exact command replay is resolved before byte I/O. A genuinely new physical
        # observation must use a new caller-owned idempotency key.
        with self._uow_provider() as preflight_uow:
            receipt = preflight_uow.receipts.start(
                receipt_id=uuid4(),
                command_kind="VERIFY_ARTIFACT",
                scope_id=str(artifact_id),
                idempotency_key=context.idempotency_key,
                request_hash=request_hash,
            )
            if not receipt.is_new:
                return _verified_observation_or_raise(
                    preflight_uow.artifacts.verification_for_receipt(
                        receipt.receipt_id
                    )
                )
            artifact = preflight_uow.artifacts.get(artifact_id)
            _validate_verifiable_artifact(artifact, self._byte_store)

        verification_exception: ArtifactByteStoreError | None = None
        try:
            byte_result = self._byte_store.verify(
                artifact.content_sha256,
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
        with self._uow_provider() as uow:
            receipt = uow.receipts.start(
                receipt_id=uuid4(),
                command_kind="VERIFY_ARTIFACT",
                scope_id=str(artifact_id),
                idempotency_key=context.idempotency_key,
                request_hash=request_hash,
            )
            if not receipt.is_new:
                return _verified_observation_or_raise(
                    uow.artifacts.verification_for_receipt(receipt.receipt_id)
                )
            current_artifact = uow.artifacts.get(artifact_id)
            _validate_verifiable_artifact(current_artifact, self._byte_store)
            if current_artifact != artifact:
                raise ArtifactIntegrityError(
                    "Artifact metadata changed during physical verification"
                )
            record = uow.artifacts.record_verification(
                verification_id=uuid4(),
                receipt_id=receipt.receipt_id,
                artifact=current_artifact,
                verifier_id=verifier_id,
                policy="AUTHORITATIVE_READ",
                verification=byte_result,
            )
            result_hash = canonical_json_sha256(record)
            uow.receipts.succeed(
                receipt_id=receipt.receipt_id,
                aggregate_kind="ARTIFACT_VERIFICATION",
                aggregate_id=str(record.verification_id),
                aggregate_version=1,
                result_hash=result_hash,
            )
            _append_artifact_audit(
                uow,
                receipt=receipt,
                context=context,
                aggregate_id=str(artifact_id),
                action="VERIFY_ARTIFACT",
                before_version=None,
                after_version=1,
            )
            uow.commit()
        return _verified_observation_or_raise(record, cause=verification_exception)

    def scan_orphans(
        self,
        *,
        scan_id: UUID,
        grace: timedelta,
        actor_id: str,
    ) -> ArtifactGcScan:
        if grace < timedelta(0):
            raise ValueError("GC grace cannot be negative")
        if not actor_id:
            raise ValueError("actor_id is required")
        physical_objects = self._byte_store.list_objects()
        object_hashes = {item.content_sha256 for item in physical_objects}
        quarantined_hashes = set(self._byte_store.list_quarantined_hashes())
        observed: list[str] = []
        quarantined: list[str] = []
        protected: list[str] = []

        for content_sha256 in sorted(object_hashes | quarantined_hashes):
            with self._uow_provider() as status_uow:
                status = status_uow.artifacts.gc_status(content_sha256)
            if status.state == "DELETED":
                if content_sha256 in object_hashes:
                    self._byte_store.quarantine(content_sha256)
                if self._byte_store.is_quarantined(content_sha256):
                    self._byte_store.delete_quarantined(content_sha256)
                with self._uow_provider() as audit_uow:
                    audit_uow.audit.append(
                        audit_event_id=uuid4(),
                        receipt_id=None,
                        actor_type="SYSTEM",
                        actor_id=actor_id,
                        aggregate_kind="ARTIFACT",
                        aggregate_id=content_sha256,
                        action="RECONCILE_DELETED_ARTIFACT_BYTES",
                        reason_code="DELETED_TOMBSTONE_RECONCILIATION",
                        before_version=None,
                        after_version=None,
                    )
                    audit_uow.commit()
                continue
            if status.referenced or status.pinned:
                if status.state == "OBSERVED":
                    self._clear_candidate(
                        content_sha256,
                        scan_id=scan_id,
                        actor_id=actor_id,
                    )
                protected.append(content_sha256)
                continue
            if status.state is None or status.state == "CLEARED":
                if content_sha256 in quarantined_hashes:
                    raise ArtifactIntegrityError(
                        "quarantined bytes have no PostgreSQL GC candidate"
                    )
                if self._observe_candidate(
                    content_sha256,
                    scan_id=scan_id,
                    grace=grace,
                    actor_id=actor_id,
                ):
                    observed.append(content_sha256)
                else:
                    protected.append(content_sha256)
                continue
            if status.state == "OBSERVED" and status.due:
                operation_token = uuid4()
                self._begin_quarantine(
                    content_sha256,
                    operation_token,
                    scan_id=scan_id,
                    actor_id=actor_id,
                )
                self._byte_store.quarantine(content_sha256)
                self._finish_quarantine(
                    content_sha256,
                    operation_token,
                    scan_id=scan_id,
                    actor_id=actor_id,
                )
                quarantined.append(content_sha256)
            elif status.state == "QUARANTINE_PENDING":
                if status.operation_token is None:
                    raise ArtifactIntegrityError("pending quarantine has no operation token")
                if not self._byte_store.is_quarantined(content_sha256):
                    self._byte_store.quarantine(content_sha256)
                self._finish_quarantine(
                    content_sha256,
                    status.operation_token,
                    scan_id=scan_id,
                    actor_id=actor_id,
                )
                quarantined.append(content_sha256)
        return ArtifactGcScan(
            scan_id=scan_id,
            observed=tuple(observed),
            quarantined=tuple(quarantined),
            protected=tuple(protected),
        )

    def delete_quarantined(
        self,
        content_sha256: str,
        *,
        context: CommandContext,
    ) -> None:
        ContentHash(content_sha256)
        with self._uow_provider() as status_uow:
            status = status_uow.artifacts.gc_status(content_sha256)
        if status.state == "DELETED":
            return
        if status.referenced or status.pinned:
            raise ArtifactIntegrityError(
                "referenced or pinned Artifact cannot be explicitly deleted"
            )
        operation_token = status.operation_token or uuid4()
        if status.state == "QUARANTINED":
            request_hash = canonical_json_sha256(
                {"content_sha256": content_sha256, "phase": "BEGIN_DELETE"}
            )
            with self._uow_provider() as uow:
                receipt = uow.receipts.start(
                    receipt_id=uuid4(),
                    command_kind="BEGIN_ARTIFACT_DELETE",
                    scope_id=content_sha256,
                    idempotency_key=f"{context.idempotency_key}:begin",
                    request_hash=request_hash,
                )
                if receipt.is_new:
                    uow.artifacts.begin_delete(content_sha256, operation_token)
                    uow.receipts.succeed(
                        receipt_id=receipt.receipt_id,
                        aggregate_kind="ARTIFACT_GC_CANDIDATE",
                        aggregate_id=content_sha256,
                        aggregate_version=3,
                        result_hash=canonical_json_sha256(
                            {"content_sha256": content_sha256, "state": "DELETE_PENDING"}
                        ),
                    )
                    _append_artifact_audit(
                        uow,
                        receipt=receipt,
                        context=context,
                        aggregate_id=content_sha256,
                        action="BEGIN_ARTIFACT_DELETE",
                        before_version=2,
                        after_version=3,
                    )
                    uow.commit()
        elif status.state != "DELETE_PENDING":
            raise ArtifactIntegrityError("artifact is not quarantined for explicit deletion")

        if self._byte_store.is_quarantined(content_sha256):
            self._byte_store.delete_quarantined(content_sha256)
        final_hash = canonical_json_sha256(
            {"content_sha256": content_sha256, "phase": "FINISH_DELETE"}
        )
        with self._uow_provider() as uow:
            receipt = uow.receipts.start(
                receipt_id=uuid4(),
                command_kind="FINISH_ARTIFACT_DELETE",
                scope_id=content_sha256,
                idempotency_key=f"{context.idempotency_key}:finish",
                request_hash=final_hash,
            )
            if receipt.is_new:
                uow.artifacts.finish_delete(
                    content_sha256,
                    operation_token,
                    verification_id=uuid4(),
                    receipt_id=receipt.receipt_id,
                    verifier_id=context.actor_id,
                )
                uow.receipts.succeed(
                    receipt_id=receipt.receipt_id,
                    aggregate_kind="ARTIFACT_GC_CANDIDATE",
                    aggregate_id=content_sha256,
                    aggregate_version=4,
                    result_hash=canonical_json_sha256(
                        {"content_sha256": content_sha256, "state": "DELETED"}
                    ),
                )
                _append_artifact_audit(
                    uow,
                    receipt=receipt,
                    context=context,
                    aggregate_id=content_sha256,
                    action="DELETE_ARTIFACT_BYTES",
                    before_version=3,
                    after_version=4,
                )
                uow.commit()

    def _observe_candidate(
        self,
        content_sha256: str,
        *,
        scan_id: UUID,
        grace: timedelta,
        actor_id: str,
    ) -> bool:
        context = _scanner_context(
            f"gc-observe:{scan_id}", actor_id, "ARTIFACT_ORPHAN_FIRST_SEEN"
        )
        request_hash = canonical_json_sha256(
            {"content_sha256": content_sha256, "scan_id": scan_id, "grace": grace}
        )
        with self._uow_provider() as uow:
            receipt = uow.receipts.start(
                receipt_id=uuid4(),
                command_kind="OBSERVE_ARTIFACT_ORPHAN",
                scope_id=content_sha256,
                idempotency_key=context.idempotency_key,
                request_hash=request_hash,
            )
            if not receipt.is_new:
                status = uow.artifacts.gc_status(content_sha256)
                return (
                    not status.referenced
                    and not status.pinned
                    and status.state == "OBSERVED"
                )
            observed = uow.artifacts.observe_gc_candidate(
                content_sha256=content_sha256,
                grace=grace,
            )
            if not observed:
                return False
            _finish_gc_command(
                uow,
                receipt,
                context,
                content_sha256=content_sha256,
                state="OBSERVED",
                action="OBSERVE_ARTIFACT_ORPHAN",
                version=1,
            )
            return True

    def _begin_quarantine(
        self,
        content_sha256: str,
        operation_token: UUID,
        *,
        scan_id: UUID,
        actor_id: str,
    ) -> None:
        context = _scanner_context(
            f"gc-quarantine-begin:{scan_id}", actor_id, "ARTIFACT_ORPHAN_SECOND_SEEN"
        )
        with self._uow_provider() as uow:
            receipt = uow.receipts.start(
                receipt_id=uuid4(),
                command_kind="BEGIN_ARTIFACT_QUARANTINE",
                scope_id=content_sha256,
                idempotency_key=context.idempotency_key,
                request_hash=canonical_json_sha256(
                    {"content_sha256": content_sha256, "operation_token": operation_token}
                ),
            )
            if not receipt.is_new:
                return
            uow.artifacts.begin_quarantine(content_sha256, operation_token)
            _finish_gc_command(
                uow,
                receipt,
                context,
                content_sha256=content_sha256,
                state="QUARANTINE_PENDING",
                action="BEGIN_ARTIFACT_QUARANTINE",
                version=2,
            )

    def _clear_candidate(
        self,
        content_sha256: str,
        *,
        scan_id: UUID,
        actor_id: str,
    ) -> None:
        context = _scanner_context(
            f"gc-clear:{scan_id}", actor_id, "ARTIFACT_BECAME_PROTECTED"
        )
        with self._uow_provider() as uow:
            receipt = uow.receipts.start(
                receipt_id=uuid4(),
                command_kind="CLEAR_ARTIFACT_GC_CANDIDATE",
                scope_id=content_sha256,
                idempotency_key=context.idempotency_key,
                request_hash=canonical_json_sha256(
                    {"content_sha256": content_sha256, "state": "CLEARED"}
                ),
            )
            if not receipt.is_new:
                return
            uow.artifacts.clear_gc_candidate(
                content_sha256=content_sha256,
                operator_id=actor_id,
                reason_code=context.reason_code,
            )
            _finish_gc_command(
                uow,
                receipt,
                context,
                content_sha256=content_sha256,
                state="CLEARED",
                action="CLEAR_ARTIFACT_GC_CANDIDATE",
                version=2,
            )

    def _finish_quarantine(
        self,
        content_sha256: str,
        operation_token: UUID,
        *,
        scan_id: UUID,
        actor_id: str,
    ) -> None:
        context = _scanner_context(
            f"gc-quarantine-finish:{scan_id}", actor_id, "ARTIFACT_QUARANTINED"
        )
        with self._uow_provider() as uow:
            receipt = uow.receipts.start(
                receipt_id=uuid4(),
                command_kind="FINISH_ARTIFACT_QUARANTINE",
                scope_id=content_sha256,
                idempotency_key=context.idempotency_key,
                request_hash=canonical_json_sha256(
                    {"content_sha256": content_sha256, "operation_token": operation_token}
                ),
            )
            if not receipt.is_new:
                return
            uow.artifacts.finish_quarantine(content_sha256, operation_token)
            _finish_gc_command(
                uow,
                receipt,
                context,
                content_sha256=content_sha256,
                state="QUARANTINED",
                action="FINISH_ARTIFACT_QUARANTINE",
                version=3,
            )


def _scanner_context(key: str, actor_id: str, reason_code: str) -> CommandContext:
    return CommandContext(
        idempotency_key=key,
        actor_type=ActorType.SYSTEM,
        actor_id=actor_id,
        reason_code=reason_code,
    )


def _validate_verifiable_artifact(
    artifact: ArtifactRecord,
    byte_store: ArtifactByteStore,
) -> None:
    expected_locator = byte_store.canonical_locator(artifact.content_sha256)
    if artifact.locator != expected_locator:
        raise ArtifactIntegrityError(
            "Artifact locator does not match its content-addressed identity"
        )
    if artifact.integrity_state in {"QUARANTINED", "DELETED"}:
        raise ArtifactIntegrityError(
            f"{artifact.integrity_state} Artifact cannot be verified as available"
        )


def _verified_observation_or_raise(
    record: ArtifactVerificationRecord,
    *,
    cause: ArtifactByteStoreError | None = None,
) -> ArtifactVerificationRecord:
    if record.result == "VERIFIED":
        return record
    error = ArtifactIntegrityError(
        "ARTIFACT_INTEGRITY_FAILED: "
        f"Artifact {record.artifact_id} verification result is {record.result}"
    )
    if cause is not None:
        raise error from cause
    raise error


def _finish_gc_command(
    uow: RuntimeUnitOfWork,
    receipt: ReceiptRecord,
    context: CommandContext,
    *,
    content_sha256: str,
    state: str,
    action: str,
    version: int,
) -> None:
    result_hash = canonical_json_sha256(
        {"content_sha256": content_sha256, "state": state}
    )
    uow.receipts.succeed(
        receipt_id=receipt.receipt_id,
        aggregate_kind="ARTIFACT_GC_CANDIDATE",
        aggregate_id=content_sha256,
        aggregate_version=version,
        result_hash=result_hash,
    )
    _append_artifact_audit(
        uow,
        receipt=receipt,
        context=context,
        aggregate_id=content_sha256,
        action=action,
        before_version=version - 1 if version > 1 else None,
        after_version=version,
    )
    uow.commit()


def _append_artifact_audit(
    uow: RuntimeUnitOfWork,
    *,
    receipt: ReceiptRecord,
    context: CommandContext,
    aggregate_id: str,
    action: str,
    before_version: int | None,
    after_version: int | None,
) -> None:
    uow.audit.append(
        audit_event_id=uuid4(),
        receipt_id=receipt.receipt_id,
        actor_type=context.actor_type.value,
        actor_id=context.actor_id,
        aggregate_kind="ARTIFACT",
        aggregate_id=aggregate_id,
        action=action,
        reason_code=context.reason_code,
        before_version=before_version,
        after_version=after_version,
    )


def _artifact_result_hash(artifact: ArtifactRecord) -> str:
    return canonical_json_sha256(
        {
            "artifact_id": artifact.artifact_id,
            "content_sha256": artifact.content_sha256,
            "size_bytes": artifact.size_bytes,
            "media_type": artifact.media_type,
            "locator": artifact.locator,
        }
    )


__all__ = ["ArtifactApplication", "ArtifactGcScan"]
