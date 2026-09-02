"""Market-owned commands for purpose-specific Provider qualification."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
from uuid import UUID

from market_regime_alpha.market.domain import (
    ProviderFinalityObservation,
    ProviderQualificationProtocol,
)
from market_regime_alpha.market.ports import (
    ProviderQualificationDecisionRecord,
    ProviderQualificationProtocolRecord,
    ProviderQualificationUnitOfWork,
    ProviderQualificationUnitOfWorkProvider,
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
class ProviderProtocolRegistrationResult:
    provider_qualification_protocol_id: UUID
    revision: int
    requirement_count: int
    requirement_roster_sha256: str
    content_sha256: str
    receipt_id: UUID
    result_hash: str
    replayed: bool


@dataclass(frozen=True, slots=True)
class ProviderFinalityObservationResult:
    provider_finality_observation_id: UUID
    capture_id: UUID
    observation_ordinal: int
    receipt_id: UUID
    result_hash: str
    replayed: bool


@dataclass(frozen=True, slots=True)
class ProviderQualificationCompletionResult:
    provider_qualification_decision_id: UUID
    decision_status: str
    evidence_class: str
    capture_count: int
    capture_roster_sha256: str
    requirement_result_count: int
    requirement_result_roster_sha256: str
    reason_code: str
    content_sha256: str
    receipt_id: UUID
    result_hash: str
    replayed: bool


class ProviderQualificationCommands:
    def __init__(
        self,
        uow_provider: ProviderQualificationUnitOfWorkProvider,
        *,
        id_factory: Callable[[], UUID],
    ) -> None:
        self._uow_provider = uow_provider
        self._id_factory = id_factory

    def register_protocol(
        self,
        protocol: ProviderQualificationProtocol,
        context: CommandContext,
        *,
        runtime_claim: AttemptClaim | None = None,
    ) -> ProviderProtocolRegistrationResult:
        request_hash = canonical_json_sha256(protocol)
        with self._uow_provider() as uow:
            if runtime_claim is not None:
                uow.runtime_finalization.lock_live(runtime_claim)
            receipt = uow.receipts.start(
                receipt_id=self._id_factory(),
                command_kind="REGISTER_PROVIDER_QUALIFICATION_PROTOCOL",
                scope_id=protocol.protocol_code,
                idempotency_key=context.idempotency_key,
                request_hash=request_hash,
            )
            if not receipt.is_new:
                _ensure_succeeded(receipt)
                if receipt.result_aggregate_id is None or receipt.result_hash is None:
                    raise ArtifactIntegrityError("Provider Protocol replay receipt is incomplete")
                record = uow.provider_qualifications.protocol_record(
                    UUID(receipt.result_aggregate_id), lock=False
                )
                result = _protocol_result(record, receipt.receipt_id, receipt.result_hash, True)
                if runtime_claim is not None:
                    uow.runtime_finalization.succeed(
                        runtime_claim, receipt_id=receipt.receipt_id,
                        result_hash=receipt.result_hash,
                    )
                    uow.commit()
                return result
            record = uow.provider_qualifications.insert_protocol(
                protocol,
                request_identity=context.idempotency_key,
                request_sha256=request_hash,
            )
            if not uow.provider_qualifications.reconcile_protocol(record.provider_qualification_protocol_id):
                raise ArtifactIntegrityError("Provider qualification Protocol does not reconcile")
            result_hash = canonical_json_sha256(record)
            self._finish(
                uow, receipt_id=receipt.receipt_id,
                aggregate_kind="PROVIDER_QUALIFICATION_PROTOCOL",
                aggregate_id=str(record.provider_qualification_protocol_id),
                aggregate_version=record.revision, result_hash=result_hash,
                action="REGISTER_PROVIDER_QUALIFICATION_PROTOCOL",
                context=context, runtime_claim=runtime_claim,
            )
            uow.commit()
            return _protocol_result(record, receipt.receipt_id, result_hash, False)

    def record_finality_observation(
        self,
        observation: ProviderFinalityObservation,
        context: CommandContext,
        *,
        runtime_claim: AttemptClaim | None = None,
    ) -> ProviderFinalityObservationResult:
        request_hash = canonical_json_sha256(observation)
        with self._uow_provider() as uow:
            if runtime_claim is not None:
                uow.runtime_finalization.lock_live(runtime_claim)
            receipt = uow.receipts.start(
                receipt_id=self._id_factory(),
                command_kind="RECORD_PROVIDER_FINALITY_OBSERVATION",
                scope_id=str(observation.capture_id),
                idempotency_key=context.idempotency_key,
                request_hash=request_hash,
            )
            if not receipt.is_new:
                _ensure_succeeded(receipt)
                if receipt.result_aggregate_id is None or receipt.result_hash is None:
                    raise ArtifactIntegrityError("Provider finality replay receipt is incomplete")
                return ProviderFinalityObservationResult(
                    provider_finality_observation_id=UUID(receipt.result_aggregate_id),
                    capture_id=observation.capture_id,
                    observation_ordinal=receipt.result_aggregate_version or 0,
                    receipt_id=receipt.receipt_id,
                    result_hash=receipt.result_hash,
                    replayed=True,
                )
            version = uow.provider_qualifications.insert_finality_observation(observation)
            result_hash = canonical_json_sha256(observation)
            self._finish(
                uow, receipt_id=receipt.receipt_id,
                aggregate_kind="PROVIDER_FINALITY_OBSERVATION",
                aggregate_id=str(observation.provider_finality_observation_id),
                aggregate_version=version, result_hash=result_hash,
                action="RECORD_PROVIDER_FINALITY_OBSERVATION",
                context=context, runtime_claim=runtime_claim,
            )
            uow.commit()
            return ProviderFinalityObservationResult(
                provider_finality_observation_id=observation.provider_finality_observation_id,
                capture_id=observation.capture_id,
                observation_ordinal=version,
                receipt_id=receipt.receipt_id,
                result_hash=result_hash,
                replayed=False,
            )

    def complete(
        self,
        *,
        provider_qualification_decision_id: UUID,
        decision_code: str,
        provider_qualification_protocol_id: UUID,
        context: CommandContext,
        runtime_claim: AttemptClaim | None = None,
    ) -> ProviderQualificationCompletionResult:
        request_hash = canonical_json_sha256(
            {
                "decision_code": decision_code,
                "provider_qualification_decision_id": provider_qualification_decision_id,
                "provider_qualification_protocol_id": provider_qualification_protocol_id,
            }
        )
        with self._uow_provider() as uow:
            if runtime_claim is not None:
                uow.runtime_finalization.lock_live(runtime_claim)
            receipt = uow.receipts.start(
                receipt_id=self._id_factory(),
                command_kind="COMPLETE_PROVIDER_QUALIFICATION",
                scope_id=str(provider_qualification_protocol_id),
                idempotency_key=context.idempotency_key,
                request_hash=request_hash,
            )
            if not receipt.is_new:
                _ensure_succeeded(receipt)
                if receipt.result_aggregate_id is None or receipt.result_hash is None:
                    raise ArtifactIntegrityError("Provider Decision replay receipt is incomplete")
                record = uow.provider_qualifications.decision_record(
                    UUID(receipt.result_aggregate_id), lock=False
                )
                result = _completion_result(record, receipt.receipt_id, receipt.result_hash, True)
                if runtime_claim is not None:
                    uow.runtime_finalization.succeed(
                        runtime_claim, receipt_id=receipt.receipt_id,
                        result_hash=receipt.result_hash,
                    )
                    uow.commit()
                return result
            record = uow.provider_qualifications.complete(
                provider_qualification_decision_id=provider_qualification_decision_id,
                decision_code=decision_code,
                provider_qualification_protocol_id=provider_qualification_protocol_id,
                request_identity=context.idempotency_key,
                request_sha256=request_hash,
            )
            if not uow.provider_qualifications.reconcile_decision(record.provider_qualification_decision_id):
                raise ArtifactIntegrityError("Provider qualification Decision does not reconcile")
            result_hash = canonical_json_sha256(record)
            self._finish(
                uow, receipt_id=receipt.receipt_id,
                aggregate_kind="PROVIDER_QUALIFICATION_DECISION",
                aggregate_id=str(record.provider_qualification_decision_id),
                aggregate_version=1, result_hash=result_hash,
                action="COMPLETE_PROVIDER_QUALIFICATION",
                context=context, runtime_claim=runtime_claim,
            )
            uow.commit()
            return _completion_result(record, receipt.receipt_id, result_hash, False)

    def _finish(
        self,
        uow: ProviderQualificationUnitOfWork,
        *,
        receipt_id: UUID,
        aggregate_kind: str,
        aggregate_id: str,
        aggregate_version: int,
        result_hash: str,
        action: str,
        context: CommandContext,
        runtime_claim: AttemptClaim | None,
    ) -> None:
        uow.receipts.succeed(
            receipt_id=receipt_id, aggregate_kind=aggregate_kind,
            aggregate_id=aggregate_id, aggregate_version=aggregate_version,
            result_hash=result_hash, runtime_claim=runtime_claim,
        )
        uow.audit.append(
            audit_event_id=self._id_factory(), receipt_id=receipt_id,
            actor_type=context.actor_type.value, actor_id=context.actor_id,
            aggregate_kind=aggregate_kind, aggregate_id=aggregate_id,
            action=action, reason_code=context.reason_code,
            before_version=None, after_version=aggregate_version,
            runtime_claim=runtime_claim,
        )
        if runtime_claim is not None:
            uow.runtime_finalization.succeed(
                runtime_claim, receipt_id=receipt_id, result_hash=result_hash
            )


def _ensure_succeeded(receipt: ReceiptRecord) -> None:
    if receipt.status in {"FAILED", "BLOCKED"}:
        raise CommandPreviouslyFailedError(receipt.error_code or "PROVIDER_QUALIFICATION_FAILED")
    if receipt.status != "SUCCEEDED":
        raise RuntimeStateConflictError("Provider qualification receipt is not terminal")


def _protocol_result(
    record: ProviderQualificationProtocolRecord,
    receipt_id: UUID,
    result_hash: str,
    replayed: bool,
) -> ProviderProtocolRegistrationResult:
    if canonical_json_sha256(record) != result_hash:
        raise ArtifactIntegrityError("Provider Protocol receipt differs from Authority")
    return ProviderProtocolRegistrationResult(
        provider_qualification_protocol_id=record.provider_qualification_protocol_id,
        revision=record.revision,
        requirement_count=record.requirement_count,
        requirement_roster_sha256=record.requirement_roster_sha256,
        content_sha256=record.content_sha256,
        receipt_id=receipt_id, result_hash=result_hash, replayed=replayed,
    )


def _completion_result(
    record: ProviderQualificationDecisionRecord,
    receipt_id: UUID,
    result_hash: str,
    replayed: bool,
) -> ProviderQualificationCompletionResult:
    if canonical_json_sha256(record) != result_hash:
        raise ArtifactIntegrityError("Provider Decision receipt differs from Authority")
    return ProviderQualificationCompletionResult(
        provider_qualification_decision_id=record.provider_qualification_decision_id,
        decision_status=record.decision_status,
        evidence_class=record.evidence_class,
        capture_count=record.capture_count,
        capture_roster_sha256=record.capture_roster_sha256,
        requirement_result_count=record.requirement_result_count,
        requirement_result_roster_sha256=record.requirement_result_roster_sha256,
        reason_code=record.reason_code,
        content_sha256=record.content_sha256,
        receipt_id=receipt_id, result_hash=result_hash, replayed=replayed,
    )


__all__ = [
    "ProviderFinalityObservationResult",
    "ProviderProtocolRegistrationResult",
    "ProviderQualificationCommands",
    "ProviderQualificationCompletionResult",
]
