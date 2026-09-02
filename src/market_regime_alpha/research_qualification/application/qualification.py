"""Freeze Qualification Policies and derive complete floor Decisions."""

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
from market_regime_alpha.research_qualification.domain.qualification import (
    ResearchQualificationDecisionPlan,
    ResearchQualificationPolicyPlan,
)
from market_regime_alpha.research_qualification.ports.qualification_uow import (
    QualificationUnitOfWork,
    QualificationUnitOfWorkProvider,
    ResearchQualificationDecisionRecord,
    ResearchQualificationPolicyRecord,
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
class QualificationMutationResult:
    aggregate_kind: str
    aggregate_id: UUID
    aggregate_version: int
    decision_status: str | None
    floor_count: int
    receipt_id: UUID
    result_hash: str
    replayed: bool


class QualificationCommands:
    def __init__(
        self,
        uow_provider: QualificationUnitOfWorkProvider,
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
    def register_policy(
        self,
        plan: ResearchQualificationPolicyPlan,
        context: CommandContext,
        *,
        runtime_claim: AttemptClaim | None = None,
    ) -> QualificationMutationResult:
        request_hash = canonical_json_sha256(plan)
        with terminal_failure_boundary(
            self._failure_recorder,
            operation="REGISTER_RESEARCH_QUALIFICATION_POLICY",
            scope_id=plan.policy_code,
            request_hash=request_hash,
            error_class="COMMAND",
            error_code="REGISTER_RESEARCH_QUALIFICATION_POLICY_REJECTED",
            context=context,
            runtime_claim=runtime_claim,
        ):
            with self._uow_provider() as uow:
                if runtime_claim is not None:
                    uow.runtime_finalization.lock_live(runtime_claim)
                receipt = uow.receipts.start(
                    receipt_id=self._id_factory(),
                    command_kind="REGISTER_RESEARCH_QUALIFICATION_POLICY",
                    scope_id=plan.policy_code,
                    idempotency_key=context.idempotency_key,
                    request_hash=request_hash,
                )
                if not receipt.is_new:
                    return self._replay_policy(uow, receipt, runtime_claim)
                uow.qualifications.lock_policy_identity(plan.policy_code)
                uow.artifacts.require_exact(plan.code_artifact, lock=True)
                uow.artifacts.require_exact(plan.config_artifact, lock=True)
                record = uow.qualifications.register_policy(
                    plan,
                    request_identity=context.idempotency_key,
                    request_sha256=request_hash,
                )
                result_hash = canonical_json_sha256(record)
                self._finish(
                    uow,
                    receipt_id=receipt.receipt_id,
                    aggregate_kind="RESEARCH_QUALIFICATION_POLICY",
                    aggregate_id=record.research_qualification_policy_id,
                    aggregate_version=record.version,
                    result_hash=result_hash,
                    action="RESEARCH_QUALIFICATION_POLICY_REGISTERED",
                    context=context,
                    runtime_claim=runtime_claim,
                )
                uow.commit()
                return self._policy_result(
                    record,
                    receipt_id=receipt.receipt_id,
                    result_hash=result_hash,
                    replayed=False,
                )

    @retry_transient_transaction
    @replay_concurrent_success
    def decide(
        self,
        plan: ResearchQualificationDecisionPlan,
        context: CommandContext,
        *,
        runtime_claim: AttemptClaim | None = None,
    ) -> QualificationMutationResult:
        request_hash = canonical_json_sha256(plan)
        with terminal_failure_boundary(
            self._failure_recorder,
            operation="DECIDE_RESEARCH_QUALIFICATION",
            scope_id=plan.decision_code,
            request_hash=request_hash,
            error_class="COMMAND",
            error_code="DECIDE_RESEARCH_QUALIFICATION_REJECTED",
            context=context,
            runtime_claim=runtime_claim,
        ):
            with self._uow_provider() as uow:
                if runtime_claim is not None:
                    uow.runtime_finalization.lock_live(runtime_claim)
                receipt = uow.receipts.start(
                    receipt_id=self._id_factory(),
                    command_kind="DECIDE_RESEARCH_QUALIFICATION",
                    scope_id=plan.decision_code,
                    idempotency_key=context.idempotency_key,
                    request_hash=request_hash,
                )
                if not receipt.is_new:
                    return self._replay_decision(uow, receipt, runtime_claim)
                uow.qualifications.lock_decision_identity(plan.decision_code)
                uow.artifacts.require_exact(plan.code_artifact, lock=True)
                uow.artifacts.require_exact(plan.config_artifact, lock=True)
                record = uow.qualifications.decide(
                    plan,
                    request_identity=context.idempotency_key,
                    request_sha256=request_hash,
                )
                result_hash = canonical_json_sha256(record)
                self._finish(
                    uow,
                    receipt_id=receipt.receipt_id,
                    aggregate_kind="RESEARCH_QUALIFICATION_DECISION",
                    aggregate_id=record.research_qualification_decision_id,
                    aggregate_version=record.revision,
                    result_hash=result_hash,
                    action="RESEARCH_QUALIFICATION_DECIDED",
                    context=context,
                    runtime_claim=runtime_claim,
                )
                uow.commit()
                return self._decision_result(
                    record,
                    receipt_id=receipt.receipt_id,
                    result_hash=result_hash,
                    replayed=False,
                )

    def _finish(
        self,
        uow: QualificationUnitOfWork,
        *,
        receipt_id: UUID,
        aggregate_kind: str,
        aggregate_id: UUID,
        aggregate_version: int,
        result_hash: str,
        action: str,
        context: CommandContext,
        runtime_claim: AttemptClaim | None,
    ) -> None:
        uow.receipts.succeed(
            receipt_id=receipt_id,
            aggregate_kind=aggregate_kind,
            aggregate_id=str(aggregate_id),
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
            aggregate_id=str(aggregate_id),
            action=action,
            reason_code=context.reason_code,
            before_version=None,
            after_version=aggregate_version,
            runtime_claim=runtime_claim,
        )
        if runtime_claim is not None:
            uow.runtime_finalization.succeed(
                runtime_claim,
                receipt_id=receipt_id,
                result_hash=result_hash,
            )

    def _replay_policy(
        self,
        uow: QualificationUnitOfWork,
        receipt: ReceiptRecord,
        runtime_claim: AttemptClaim | None,
    ) -> QualificationMutationResult:
        ensure_replay_succeeded(receipt)
        if (
            receipt.result_aggregate_kind != "RESEARCH_QUALIFICATION_POLICY"
            or receipt.result_aggregate_id is None
            or receipt.result_hash is None
        ):
            raise ArtifactIntegrityError("Qualification Policy receipt is incomplete")
        policy_id = UUID(receipt.result_aggregate_id)
        record = uow.qualifications.policy_record(policy_id, lock=False)
        if canonical_json_sha256(record) != receipt.result_hash:
            raise ArtifactIntegrityError(
                "Qualification Policy receipt and Authority differ"
            )
        self._replay_runtime(uow, receipt, runtime_claim)
        return self._policy_result(
            record,
            receipt_id=receipt.receipt_id,
            result_hash=receipt.result_hash,
            replayed=True,
        )

    def _replay_decision(
        self,
        uow: QualificationUnitOfWork,
        receipt: ReceiptRecord,
        runtime_claim: AttemptClaim | None,
    ) -> QualificationMutationResult:
        ensure_replay_succeeded(receipt)
        if (
            receipt.result_aggregate_kind != "RESEARCH_QUALIFICATION_DECISION"
            or receipt.result_aggregate_id is None
            or receipt.result_hash is None
        ):
            raise ArtifactIntegrityError("Qualification Decision receipt is incomplete")
        decision_id = UUID(receipt.result_aggregate_id)
        record = uow.qualifications.decision_record(decision_id, lock=False)
        if canonical_json_sha256(record) != receipt.result_hash:
            raise ArtifactIntegrityError(
                "Qualification Decision receipt and Authority differ"
            )
        self._replay_runtime(uow, receipt, runtime_claim)
        return self._decision_result(
            record,
            receipt_id=receipt.receipt_id,
            result_hash=receipt.result_hash,
            replayed=True,
        )

    @staticmethod
    def _replay_runtime(
        uow: QualificationUnitOfWork,
        receipt: ReceiptRecord,
        runtime_claim: AttemptClaim | None,
    ) -> None:
        if runtime_claim is not None:
            assert receipt.result_hash is not None
            uow.runtime_finalization.succeed(
                runtime_claim,
                receipt_id=receipt.receipt_id,
                result_hash=receipt.result_hash,
            )
            uow.commit()

    @staticmethod
    def _policy_result(
        record: ResearchQualificationPolicyRecord,
        *,
        receipt_id: UUID,
        result_hash: str,
        replayed: bool,
    ) -> QualificationMutationResult:
        return QualificationMutationResult(
            aggregate_kind="RESEARCH_QUALIFICATION_POLICY",
            aggregate_id=record.research_qualification_policy_id,
            aggregate_version=record.version,
            decision_status=None,
            floor_count=record.floor_count,
            receipt_id=receipt_id,
            result_hash=result_hash,
            replayed=replayed,
        )

    @staticmethod
    def _decision_result(
        record: ResearchQualificationDecisionRecord,
        *,
        receipt_id: UUID,
        result_hash: str,
        replayed: bool,
    ) -> QualificationMutationResult:
        return QualificationMutationResult(
            aggregate_kind="RESEARCH_QUALIFICATION_DECISION",
            aggregate_id=record.research_qualification_decision_id,
            aggregate_version=record.revision,
            decision_status=record.decision_status,
            floor_count=record.floor_count,
            receipt_id=receipt_id,
            result_hash=result_hash,
            replayed=replayed,
        )


__all__ = ["QualificationCommands", "QualificationMutationResult"]
