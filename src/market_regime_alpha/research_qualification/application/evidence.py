"""Record immutable Evaluation-bound Research Evidence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, cast
from uuid import UUID

from market_regime_alpha.research_qualification.application._command_support import (
    replay_concurrent_success,
    retry_transient_transaction,
    terminal_failure_boundary,
)
from market_regime_alpha.research_qualification.application._results import (
    ensure_replay_succeeded,
)
from market_regime_alpha.research_qualification.domain.evidence import EvidenceItemPlan
from market_regime_alpha.research_qualification.ports.evidence_uow import (
    EvidenceUnitOfWork,
    EvidenceUnitOfWorkProvider,
)
from market_regime_alpha.runtime.application import (
    CommandContext,
    RuntimeCommandFailureRecorder,
)
from market_regime_alpha.runtime.errors import ArtifactIntegrityError
from market_regime_alpha.runtime.ports import (
    AttemptClaim,
    CommandFailureUnitOfWorkProvider,
    ReceiptRecord,
)
from market_regime_alpha.shared.hashing import canonical_json_sha256


@dataclass(frozen=True, slots=True)
class EvidenceMutationResult:
    aggregate_kind: str
    aggregate_id: UUID
    receipt_id: UUID
    result_hash: str
    replayed: bool


class EvidenceCommands:
    def __init__(
        self,
        uow_provider: EvidenceUnitOfWorkProvider,
        *,
        id_factory: Callable[[], UUID],
    ) -> None:
        self._uow_provider = uow_provider
        self._id_factory = id_factory
        self._failure_recorder = RuntimeCommandFailureRecorder(
            cast(CommandFailureUnitOfWorkProvider, uow_provider),
            id_factory=id_factory,
        )

    @retry_transient_transaction
    @replay_concurrent_success
    def record(
        self,
        plan: EvidenceItemPlan,
        context: CommandContext,
        *,
        runtime_claim: AttemptClaim | None = None,
    ) -> EvidenceMutationResult:
        request_hash = canonical_json_sha256(plan)
        scope_id = f"{plan.evaluation_run_id}:{plan.evidence_code}"
        with terminal_failure_boundary(
            self._failure_recorder,
            operation="RECORD_RESEARCH_EVIDENCE",
            scope_id=scope_id,
            request_hash=request_hash,
            error_class="COMMAND",
            error_code="RECORD_RESEARCH_EVIDENCE_REJECTED",
            context=context,
            runtime_claim=runtime_claim,
        ):
            return self._record_once(
                plan,
                context,
                request_hash=request_hash,
                scope_id=scope_id,
                runtime_claim=runtime_claim,
            )

    def _record_once(
        self,
        plan: EvidenceItemPlan,
        context: CommandContext,
        *,
        request_hash: str,
        scope_id: str,
        runtime_claim: AttemptClaim | None,
    ) -> EvidenceMutationResult:
        with self._uow_provider() as uow:
            if runtime_claim is not None:
                uow.runtime_finalization.lock_live(runtime_claim)
            receipt = uow.receipts.start(
                receipt_id=self._id_factory(),
                command_kind="RECORD_RESEARCH_EVIDENCE",
                scope_id=scope_id,
                idempotency_key=context.idempotency_key,
                request_hash=request_hash,
            )
            if not receipt.is_new:
                return self._replay(uow, receipt, runtime_claim)
            uow.evidence.lock_identity(plan.evaluation_run_id, plan.evidence_code)
            uow.artifacts.require_exact(plan.evidence_artifact, lock=True)
            uow.artifacts.require_exact(plan.code_artifact, lock=True)
            uow.artifacts.require_exact(plan.config_artifact, lock=True)
            record = uow.evidence.record(
                plan,
                request_identity=context.idempotency_key,
                request_sha256=request_hash,
            )
            result_hash = canonical_json_sha256(record)
            self._finish(
                uow,
                receipt.receipt_id,
                record.evidence_item_id,
                result_hash,
                context,
                runtime_claim,
            )
            uow.commit()
            return EvidenceMutationResult(
                "EVIDENCE_ITEM",
                record.evidence_item_id,
                receipt.receipt_id,
                result_hash,
                False,
            )

    def _finish(
        self,
        uow: EvidenceUnitOfWork,
        receipt_id: UUID,
        evidence_item_id: UUID,
        result_hash: str,
        context: CommandContext,
        runtime_claim: AttemptClaim | None,
    ) -> None:
        uow.receipts.succeed(
            receipt_id=receipt_id,
            aggregate_kind="EVIDENCE_ITEM",
            aggregate_id=str(evidence_item_id),
            aggregate_version=1,
            result_hash=result_hash,
            runtime_claim=runtime_claim,
        )
        uow.audit.append(
            audit_event_id=self._id_factory(),
            receipt_id=receipt_id,
            actor_type=context.actor_type.value,
            actor_id=context.actor_id,
            aggregate_kind="EVIDENCE_ITEM",
            aggregate_id=str(evidence_item_id),
            action="RESEARCH_EVIDENCE_RECORDED",
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

    def _replay(
        self,
        uow: EvidenceUnitOfWork,
        receipt: ReceiptRecord,
        runtime_claim: AttemptClaim | None,
    ) -> EvidenceMutationResult:
        ensure_replay_succeeded(receipt)
        if (
            receipt.result_aggregate_kind != "EVIDENCE_ITEM"
            or receipt.result_aggregate_id is None
            or receipt.result_hash is None
        ):
            raise ArtifactIntegrityError("Evidence receipt is incomplete")
        evidence_item_id = UUID(receipt.result_aggregate_id)
        record = uow.evidence.item_record(evidence_item_id, lock=False)
        if canonical_json_sha256(record) != receipt.result_hash:
            raise ArtifactIntegrityError("Evidence receipt and Authority differ")
        if runtime_claim is not None:
            uow.runtime_finalization.succeed(
                runtime_claim,
                receipt_id=receipt.receipt_id,
                result_hash=receipt.result_hash,
            )
            uow.commit()
        return EvidenceMutationResult(
            "EVIDENCE_ITEM",
            evidence_item_id,
            receipt.receipt_id,
            receipt.result_hash,
            True,
        )


__all__ = ["EvidenceCommands", "EvidenceMutationResult"]
