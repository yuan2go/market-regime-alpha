"""Market-owned commands for purpose-specific Provider qualification."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, TypeVar, cast
from uuid import UUID

from market_regime_alpha.market.domain import (
    ProviderFinalityObservation,
    ProviderQualificationProtocol,
)
from market_regime_alpha.market.errors import (
    MarketCommitOutcomeUnknownError,
    MarketRetryableTransactionError,
    MarketTransactionRetryExhaustedError,
)
from market_regime_alpha.market.ports import (
    ProviderQualificationDecisionRecord,
    ProviderQualificationProtocolRecord,
    ProviderQualificationRepository,
    ProviderQualificationUnitOfWork,
    ProviderQualificationUnitOfWorkProvider,
    QualifiedHistoricalVisibilityRecord,
)
from market_regime_alpha.runtime.application import (
    CommandContext,
    CommandFailureDescriptor,
    ConcurrentCommandSucceeded,
    RuntimeCommandFailureRecorder,
)
from market_regime_alpha.runtime.errors import (
    ArtifactIntegrityError,
    CommandInProgressError,
    CommandPreviouslyFailedError,
    IdempotencyKeyReusedError,
    RuntimeNotFoundError,
    RuntimeStateConflictError,
    StaleFenceError,
)
from market_regime_alpha.runtime.ports import (
    AttemptClaim,
    CommandFailureUnitOfWorkProvider,
    ReceiptRecord,
)
from market_regime_alpha.shared.hashing import canonical_json_sha256


_ProviderResult = TypeVar("_ProviderResult")


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


@dataclass(frozen=True, slots=True)
class QualifiedHistoricalVisibilityResult:
    qualified_visibility_id: UUID
    source_kind: str
    source_identity: UUID
    provider_qualification_decision_id: UUID
    qualified_decision_visible_at: datetime
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
        self._failure_recorder = RuntimeCommandFailureRecorder(
            cast(CommandFailureUnitOfWorkProvider, uow_provider),
            id_factory=id_factory,
        )

    def register_protocol(
        self,
        protocol: ProviderQualificationProtocol,
        context: CommandContext,
        *,
        runtime_claim: AttemptClaim | None = None,
    ) -> ProviderProtocolRegistrationResult:
        request_hash = canonical_json_sha256(protocol)
        return self._execute(
            operation=lambda: self._register_protocol_once(
                protocol, context, request_hash=request_hash,
                runtime_claim=runtime_claim,
            ),
            probe=lambda: self._probe_protocol(protocol, context, request_hash),
            descriptor=self._descriptor(
                operation="REGISTER_PROVIDER_QUALIFICATION_PROTOCOL",
                scope_id=protocol.protocol_code,
                request_hash=request_hash,
                error_code="REGISTER_PROVIDER_QUALIFICATION_PROTOCOL_REJECTED",
            ),
            context=context,
            runtime_claim=runtime_claim,
        )

    def _register_protocol_once(
        self,
        protocol: ProviderQualificationProtocol,
        context: CommandContext,
        *,
        request_hash: str,
        runtime_claim: AttemptClaim | None,
    ) -> ProviderProtocolRegistrationResult:
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
        return self._execute(
            operation=lambda: self._record_finality_observation_once(
                observation, context, request_hash=request_hash,
                runtime_claim=runtime_claim,
            ),
            probe=lambda: self._probe_finality(observation, context, request_hash),
            descriptor=self._descriptor(
                operation="RECORD_PROVIDER_FINALITY_OBSERVATION",
                scope_id=str(observation.capture_id),
                request_hash=request_hash,
                error_code="RECORD_PROVIDER_FINALITY_OBSERVATION_REJECTED",
            ),
            context=context,
            runtime_claim=runtime_claim,
        )

    def _record_finality_observation_once(
        self,
        observation: ProviderFinalityObservation,
        context: CommandContext,
        *,
        request_hash: str,
        runtime_claim: AttemptClaim | None,
    ) -> ProviderFinalityObservationResult:
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
        return self._execute(
            operation=lambda: self._complete_once(
                provider_qualification_decision_id=provider_qualification_decision_id,
                decision_code=decision_code,
                provider_qualification_protocol_id=provider_qualification_protocol_id,
                context=context,
                request_hash=request_hash,
                runtime_claim=runtime_claim,
            ),
            probe=lambda: self._probe_decision(
                provider_qualification_protocol_id, context, request_hash
            ),
            descriptor=self._descriptor(
                operation="COMPLETE_PROVIDER_QUALIFICATION",
                scope_id=str(provider_qualification_protocol_id),
                request_hash=request_hash,
                error_code="COMPLETE_PROVIDER_QUALIFICATION_REJECTED",
            ),
            context=context,
            runtime_claim=runtime_claim,
        )

    def _complete_once(
        self,
        *,
        provider_qualification_decision_id: UUID,
        decision_code: str,
        provider_qualification_protocol_id: UUID,
        context: CommandContext,
        request_hash: str,
        runtime_claim: AttemptClaim | None,
    ) -> ProviderQualificationCompletionResult:
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

    def admit_market_bar_visibility(
        self, *, provider_qualification_decision_id: UUID,
        bar_revision_id: UUID, context: CommandContext,
        runtime_claim: AttemptClaim | None = None,
    ) -> QualifiedHistoricalVisibilityResult:
        return self._admit_visibility(
            provider_qualification_decision_id=provider_qualification_decision_id,
            source_kind="MARKET_BAR_REVISION", source_identity=bar_revision_id,
            context=context, runtime_claim=runtime_claim,
            mutation=lambda repository, visibility_id: repository.admit_market_bar_visibility(
                visibility_id, provider_qualification_decision_id, bar_revision_id
            ),
        )

    def admit_instrument_fact_visibility(
        self, *, provider_qualification_decision_id: UUID,
        fact_revision_id: UUID, context: CommandContext,
        runtime_claim: AttemptClaim | None = None,
    ) -> QualifiedHistoricalVisibilityResult:
        return self._admit_visibility(
            provider_qualification_decision_id=provider_qualification_decision_id,
            source_kind="INSTRUMENT_FACT_REVISION", source_identity=fact_revision_id,
            context=context, runtime_claim=runtime_claim,
            mutation=lambda repository, visibility_id: repository.admit_instrument_fact_visibility(
                visibility_id, provider_qualification_decision_id, fact_revision_id
            ),
        )

    def admit_classification_membership_visibility(
        self, *, provider_qualification_decision_id: UUID,
        membership_revision_id: UUID, context: CommandContext,
        runtime_claim: AttemptClaim | None = None,
    ) -> QualifiedHistoricalVisibilityResult:
        return self._admit_visibility(
            provider_qualification_decision_id=provider_qualification_decision_id,
            source_kind="CLASSIFICATION_MEMBERSHIP_REVISION",
            source_identity=membership_revision_id,
            context=context, runtime_claim=runtime_claim,
            mutation=lambda repository, visibility_id: repository.admit_classification_membership_visibility(
                visibility_id, provider_qualification_decision_id,
                membership_revision_id,
            ),
        )

    def admit_trading_session_visibility(
        self, *, provider_qualification_decision_id: UUID,
        session_id: UUID, context: CommandContext,
        runtime_claim: AttemptClaim | None = None,
    ) -> QualifiedHistoricalVisibilityResult:
        return self._admit_visibility(
            provider_qualification_decision_id=provider_qualification_decision_id,
            source_kind="TRADING_SESSION", source_identity=session_id,
            context=context, runtime_claim=runtime_claim,
            mutation=lambda repository, visibility_id: repository.admit_trading_session_visibility(
                visibility_id, provider_qualification_decision_id, session_id
            ),
        )

    def admit_source_gap_visibility(
        self, *, provider_qualification_decision_id: UUID,
        gap_id: UUID, context: CommandContext,
        runtime_claim: AttemptClaim | None = None,
    ) -> QualifiedHistoricalVisibilityResult:
        return self._admit_visibility(
            provider_qualification_decision_id=provider_qualification_decision_id,
            source_kind="SOURCE_GAP", source_identity=gap_id,
            context=context, runtime_claim=runtime_claim,
            mutation=lambda repository, visibility_id: repository.admit_source_gap_visibility(
                visibility_id, provider_qualification_decision_id, gap_id
            ),
        )

    def _admit_visibility(
        self, *, provider_qualification_decision_id: UUID,
        source_kind: str, source_identity: UUID, context: CommandContext,
        runtime_claim: AttemptClaim | None,
        mutation: Callable[
            [ProviderQualificationRepository, UUID],
            QualifiedHistoricalVisibilityRecord,
        ],
    ) -> QualifiedHistoricalVisibilityResult:
        request_hash = canonical_json_sha256({
            "provider_qualification_decision_id": provider_qualification_decision_id,
            "source_identity": source_identity, "source_kind": source_kind,
        })
        return self._execute(
            operation=lambda: self._admit_visibility_once(
                provider_qualification_decision_id=provider_qualification_decision_id,
                source_kind=source_kind,
                source_identity=source_identity,
                context=context,
                runtime_claim=runtime_claim,
                mutation=mutation,
                request_hash=request_hash,
            ),
            probe=lambda: self._probe_visibility(
                provider_qualification_decision_id,
                source_kind,
                context,
                request_hash,
            ),
            descriptor=self._descriptor(
                operation=f"ADMIT_QUALIFIED_{source_kind}",
                scope_id=str(provider_qualification_decision_id),
                request_hash=request_hash,
                error_code=f"ADMIT_QUALIFIED_{source_kind}_REJECTED",
            ),
            context=context,
            runtime_claim=runtime_claim,
        )

    def _admit_visibility_once(
        self,
        *,
        provider_qualification_decision_id: UUID,
        source_kind: str,
        source_identity: UUID,
        context: CommandContext,
        runtime_claim: AttemptClaim | None,
        mutation: Callable[
            [ProviderQualificationRepository, UUID],
            QualifiedHistoricalVisibilityRecord,
        ],
        request_hash: str,
    ) -> QualifiedHistoricalVisibilityResult:
        with self._uow_provider() as uow:
            if runtime_claim is not None:
                uow.runtime_finalization.lock_live(runtime_claim)
            receipt = uow.receipts.start(
                receipt_id=self._id_factory(),
                command_kind=f"ADMIT_QUALIFIED_{source_kind}",
                scope_id=str(provider_qualification_decision_id),
                idempotency_key=context.idempotency_key,
                request_hash=request_hash,
            )
            if not receipt.is_new:
                _ensure_succeeded(receipt)
                if receipt.result_aggregate_id is None or receipt.result_hash is None:
                    raise ArtifactIntegrityError("qualified visibility replay is incomplete")
                record = uow.provider_qualifications.visibility_record(
                    UUID(receipt.result_aggregate_id), source_kind=source_kind
                )
                if canonical_json_sha256(record) != receipt.result_hash:
                    raise ArtifactIntegrityError("qualified visibility replay differs")
                if runtime_claim is not None:
                    uow.runtime_finalization.succeed(
                        runtime_claim, receipt_id=receipt.receipt_id,
                        result_hash=receipt.result_hash,
                    )
                    uow.commit()
                return QualifiedHistoricalVisibilityResult(
                    record.qualified_visibility_id, record.source_kind,
                    record.source_identity, record.provider_qualification_decision_id,
                    record.qualified_decision_visible_at, receipt.receipt_id,
                    receipt.result_hash, True,
                )
            record = mutation(uow.provider_qualifications, self._id_factory())
            result_hash = canonical_json_sha256(record)
            self._finish(
                uow, receipt_id=receipt.receipt_id,
                aggregate_kind="QUALIFIED_HISTORICAL_VISIBILITY",
                aggregate_id=str(record.qualified_visibility_id),
                aggregate_version=1, result_hash=result_hash,
                action=f"ADMIT_QUALIFIED_{source_kind}", context=context,
                runtime_claim=runtime_claim,
            )
            uow.commit()
            return QualifiedHistoricalVisibilityResult(
                record.qualified_visibility_id, record.source_kind,
                record.source_identity, record.provider_qualification_decision_id,
                record.qualified_decision_visible_at, receipt.receipt_id,
                result_hash, False,
            )

    def _probe_protocol(
        self,
        protocol: ProviderQualificationProtocol,
        context: CommandContext,
        request_hash: str,
    ) -> ProviderProtocolRegistrationResult | None:
        with self._uow_provider() as uow:
            receipt = uow.provider_qualifications.protocol_request_receipt(
                protocol.protocol_code, context.idempotency_key
            )
            if receipt is None:
                return None
            _require_exact_recovery_receipt(receipt, request_hash)
            if receipt.result_aggregate_id is None or receipt.result_hash is None:
                raise ArtifactIntegrityError("Provider Protocol recovery receipt is incomplete")
            record = uow.provider_qualifications.protocol_record(
                UUID(receipt.result_aggregate_id), lock=False
            )
            return _protocol_result(record, receipt.receipt_id, receipt.result_hash, True)

    def _probe_finality(
        self,
        observation: ProviderFinalityObservation,
        context: CommandContext,
        request_hash: str,
    ) -> ProviderFinalityObservationResult | None:
        with self._uow_provider() as uow:
            receipt = uow.provider_qualifications.finality_request_receipt(
                observation.capture_id, context.idempotency_key
            )
            if receipt is None:
                return None
            _require_exact_recovery_receipt(receipt, request_hash)
            if receipt.result_aggregate_id is None or receipt.result_hash is None:
                raise ArtifactIntegrityError("Provider finality recovery receipt is incomplete")
            if receipt.result_hash != canonical_json_sha256(observation):
                raise ArtifactIntegrityError("Provider finality recovery differs")
            return ProviderFinalityObservationResult(
                provider_finality_observation_id=UUID(receipt.result_aggregate_id),
                capture_id=observation.capture_id,
                observation_ordinal=receipt.result_aggregate_version or 0,
                receipt_id=receipt.receipt_id,
                result_hash=receipt.result_hash,
                replayed=True,
            )

    def _probe_decision(
        self,
        provider_qualification_protocol_id: UUID,
        context: CommandContext,
        request_hash: str,
    ) -> ProviderQualificationCompletionResult | None:
        with self._uow_provider() as uow:
            receipt = uow.provider_qualifications.decision_request_receipt(
                provider_qualification_protocol_id, context.idempotency_key
            )
            if receipt is None:
                return None
            _require_exact_recovery_receipt(receipt, request_hash)
            if receipt.result_aggregate_id is None or receipt.result_hash is None:
                raise ArtifactIntegrityError("Provider Decision recovery receipt is incomplete")
            record = uow.provider_qualifications.decision_record(
                UUID(receipt.result_aggregate_id), lock=False
            )
            return _completion_result(record, receipt.receipt_id, receipt.result_hash, True)

    def _probe_visibility(
        self,
        provider_qualification_decision_id: UUID,
        source_kind: str,
        context: CommandContext,
        request_hash: str,
    ) -> QualifiedHistoricalVisibilityResult | None:
        with self._uow_provider() as uow:
            receipt = uow.provider_qualifications.visibility_request_receipt(
                provider_qualification_decision_id,
                source_kind,
                context.idempotency_key,
            )
            if receipt is None:
                return None
            _require_exact_recovery_receipt(receipt, request_hash)
            if receipt.result_aggregate_id is None or receipt.result_hash is None:
                raise ArtifactIntegrityError("qualified visibility recovery receipt is incomplete")
            record = uow.provider_qualifications.visibility_record(
                UUID(receipt.result_aggregate_id), source_kind=source_kind
            )
            if canonical_json_sha256(record) != receipt.result_hash:
                raise ArtifactIntegrityError("qualified visibility recovery differs")
            return QualifiedHistoricalVisibilityResult(
                record.qualified_visibility_id,
                record.source_kind,
                record.source_identity,
                record.provider_qualification_decision_id,
                record.qualified_decision_visible_at,
                receipt.receipt_id,
                receipt.result_hash,
                True,
            )

    def _execute(
        self,
        *,
        operation: Callable[[], _ProviderResult],
        probe: Callable[[], _ProviderResult | None],
        descriptor: CommandFailureDescriptor,
        context: CommandContext,
        runtime_claim: AttemptClaim | None,
    ) -> _ProviderResult:
        for attempt in range(3):
            try:
                return operation()
            except (MarketRetryableTransactionError, MarketCommitOutcomeUnknownError) as exc:
                existing = probe()
                if existing is not None:
                    return existing
                if attempt == 2:
                    if isinstance(exc, MarketRetryableTransactionError):
                        raise MarketTransactionRetryExhaustedError(
                            "Provider qualification transaction retries exhausted"
                        ) from exc
                    raise
            except StaleFenceError:
                raise
            except ConcurrentCommandSucceeded:
                existing = probe()
                if existing is None:
                    raise ArtifactIntegrityError(
                        "concurrent Provider command reported success without Authority"
                    )
                return existing
            except (CommandInProgressError, IdempotencyKeyReusedError) as exc:
                self._failure_recorder.record_idempotency_rejection(
                    descriptor,
                    rejection_code=exc.code,
                    context=context,
                    runtime_claim=runtime_claim,
                )
                raise
            except (
                ArtifactIntegrityError,
                CommandPreviouslyFailedError,
                RuntimeNotFoundError,
                RuntimeStateConflictError,
                ValueError,
            ):
                try:
                    self._failure_recorder.record(
                        descriptor,
                        context=context,
                        runtime_claim=runtime_claim,
                    )
                except ConcurrentCommandSucceeded:
                    existing = probe()
                    if existing is not None:
                        return existing
                    raise
                raise
        raise AssertionError("Provider qualification retry loop did not terminate")

    @staticmethod
    def _descriptor(
        *,
        operation: str,
        scope_id: str,
        request_hash: str,
        error_code: str,
    ) -> CommandFailureDescriptor:
        return CommandFailureDescriptor(
            command_kind=operation,
            scope_id=scope_id,
            request_hash=request_hash,
            error_class="COMMAND",
            error_code=error_code,
            aggregate_kind="MARKET_COMMAND",
            failure_action="MARKET_COMMAND_FAILED",
            rejection_command_kind="MARKET_COMMAND_REJECTION",
            rejection_action="MARKET_COMMAND_REJECTED",
            rejection_key_prefix="market-command-rejection",
        )

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


def _require_exact_recovery_receipt(
    receipt: ReceiptRecord, request_hash: str
) -> None:
    if receipt.request_hash != request_hash:
        raise IdempotencyKeyReusedError(
            "Provider qualification recovery inputs differ"
        )
    _ensure_succeeded(receipt)


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
    "QualifiedHistoricalVisibilityResult",
]
