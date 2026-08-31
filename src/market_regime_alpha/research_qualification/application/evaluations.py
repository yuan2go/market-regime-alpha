"""Evaluation Protocol, Run, controlled acquisition, and completion commands."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, cast
from uuid import UUID

from market_regime_alpha.research_qualification.application._results import ensure_replay_succeeded
from market_regime_alpha.research_qualification.application._command_support import replay_concurrent_success, retry_postgres_transient, terminal_failure_boundary
from market_regime_alpha.research_qualification.domain.evaluation import EvaluationProtocolPlan, EvaluationRunPlan
from market_regime_alpha.research_qualification.ports.evaluation_inputs import OutcomeAcquisitionResult
from market_regime_alpha.research_qualification.ports.evaluation_uow import (
    EvaluationCompletionResult,
    EvaluationUnitOfWork,
    EvaluationUnitOfWorkProvider,
)
from market_regime_alpha.runtime.application import CommandContext, RuntimeCommandFailureRecorder
from market_regime_alpha.runtime.errors import ArtifactIntegrityError
from market_regime_alpha.runtime.ports import AttemptClaim, CommandFailureUnitOfWorkProvider, ReceiptRecord
from market_regime_alpha.shared.hashing import canonical_json_sha256


@dataclass(frozen=True, slots=True)
class EvaluationMutationResult:
    aggregate_kind: str
    evaluation_run_id: UUID | None
    evaluation_protocol_id: UUID | None
    count: int
    roster_sha256: str
    receipt_id: UUID
    replayed: bool


class EvaluationCommands:
    def __init__(self, uow_provider: EvaluationUnitOfWorkProvider, *, id_factory: Callable[[], UUID]) -> None:
        self._uow_provider = uow_provider
        self._id_factory = id_factory
        self._failure_recorder = RuntimeCommandFailureRecorder(
            cast(CommandFailureUnitOfWorkProvider, uow_provider), id_factory=id_factory
        )

    @retry_postgres_transient
    @replay_concurrent_success
    def register_protocol(self, plan: EvaluationProtocolPlan, context: CommandContext, *, runtime_claim: AttemptClaim | None = None) -> EvaluationMutationResult:
        request_hash = canonical_json_sha256(plan)
        with terminal_failure_boundary(
            self._failure_recorder,
            operation="REGISTER_EVALUATION_PROTOCOL",
            scope_id=plan.protocol_code,
            request_hash=request_hash,
            error_class="COMMAND",
            error_code="REGISTER_EVALUATION_PROTOCOL_REJECTED",
            context=context,
            runtime_claim=runtime_claim,
        ):
            return self._register_protocol_once(plan, context, runtime_claim=runtime_claim)

    def _register_protocol_once(self, plan: EvaluationProtocolPlan, context: CommandContext, *, runtime_claim: AttemptClaim | None) -> EvaluationMutationResult:
        request_hash = canonical_json_sha256(plan)
        with self._uow_provider() as uow:
            receipt = self._start(uow, "REGISTER_EVALUATION_PROTOCOL", plan.protocol_code, request_hash, context, runtime_claim)
            if not receipt.is_new:
                ensure_replay_succeeded(receipt)
                protocol_id = _receipt_id(receipt, "EVALUATION_PROTOCOL")
                record = uow.evaluations.protocol_record(protocol_id, lock=False)
                _require_result_hash(receipt, canonical_json_sha256(record))
                result = EvaluationMutationResult("EVALUATION_PROTOCOL", None, protocol_id, record.metric_count, record.metric_roster_sha256, receipt.receipt_id, True)
                self._finish_replay(uow, receipt, runtime_claim)
                return result
            uow.evaluations.lock_protocol_identity(plan.protocol_code)
            uow.artifacts.require_exact(plan.code_artifact, lock=True)
            uow.artifacts.require_exact(plan.config_artifact, lock=True)
            record = uow.evaluations.register_protocol(plan, request_identity=context.idempotency_key, request_sha256=request_hash)
            result_hash = canonical_json_sha256(record)
            self._finish(uow, receipt, "EVALUATION_PROTOCOL", record.evaluation_protocol_id, 1, result_hash, context, runtime_claim)
            uow.commit()
            return EvaluationMutationResult("EVALUATION_PROTOCOL", None, record.evaluation_protocol_id, record.metric_count, record.metric_roster_sha256, receipt.receipt_id, False)

    @retry_postgres_transient
    @replay_concurrent_success
    def open_run(self, plan: EvaluationRunPlan, context: CommandContext, *, runtime_claim: AttemptClaim | None = None) -> EvaluationMutationResult:
        request_hash = canonical_json_sha256(plan)
        with terminal_failure_boundary(
            self._failure_recorder,
            operation="OPEN_EVALUATION_RUN",
            scope_id=str(plan.experiment_run_id),
            request_hash=request_hash,
            error_class="COMMAND",
            error_code="OPEN_EVALUATION_RUN_REJECTED",
            context=context,
            runtime_claim=runtime_claim,
        ):
            return self._open_run_once(plan, context, runtime_claim=runtime_claim)

    def _open_run_once(self, plan: EvaluationRunPlan, context: CommandContext, *, runtime_claim: AttemptClaim | None) -> EvaluationMutationResult:
        request_hash = canonical_json_sha256(plan)
        with self._uow_provider() as uow:
            receipt = self._start(uow, "OPEN_EVALUATION_RUN", str(plan.experiment_run_id), request_hash, context, runtime_claim)
            if not receipt.is_new:
                ensure_replay_succeeded(receipt)
                run_id = _receipt_id(receipt, "EVALUATION_RUN")
                record = uow.evaluations.run_record(run_id, lock=False)
                _require_result_hash(receipt, canonical_json_sha256(record))
                self._finish_replay(uow, receipt, runtime_claim)
                return EvaluationMutationResult("EVALUATION_RUN", run_id, None, 0, canonical_json_sha256(record), receipt.receipt_id, True)
            record = uow.evaluations.open_run(plan, request_sha256=request_hash)
            result_hash = canonical_json_sha256(record)
            self._finish(uow, receipt, "EVALUATION_RUN", record.evaluation_run_id, 1, result_hash, context, runtime_claim)
            uow.commit()
            return EvaluationMutationResult("EVALUATION_RUN", record.evaluation_run_id, None, 0, result_hash, receipt.receipt_id, False)

    @retry_postgres_transient
    @replay_concurrent_success
    def acquire_outcome_inputs(self, evaluation_run_id: UUID, context: CommandContext, *, runtime_claim: AttemptClaim | None = None) -> EvaluationMutationResult:
        request_hash = canonical_json_sha256({"evaluation_run_id": evaluation_run_id})
        with terminal_failure_boundary(
            self._failure_recorder,
            operation="ACQUIRE_OUTCOME_INPUTS",
            scope_id=str(evaluation_run_id),
            request_hash=request_hash,
            error_class="COMMAND",
            error_code="ACQUIRE_OUTCOME_INPUTS_REJECTED",
            context=context,
            runtime_claim=runtime_claim,
        ):
            return self._acquire_once(evaluation_run_id, context, runtime_claim=runtime_claim)

    def _acquire_once(self, evaluation_run_id: UUID, context: CommandContext, *, runtime_claim: AttemptClaim | None) -> EvaluationMutationResult:
        request_hash = canonical_json_sha256({"evaluation_run_id": evaluation_run_id})
        with self._uow_provider() as uow:
            receipt = self._start(uow, "ACQUIRE_OUTCOME_INPUTS", str(evaluation_run_id), request_hash, context, runtime_claim)
            if not receipt.is_new:
                ensure_replay_succeeded(receipt)
                _receipt_id(receipt, "EVALUATION_RUN")
                acquired = uow.outcome_acquisition.acquire(evaluation_run_id)
                _require_result_hash(receipt, canonical_json_sha256(acquired))
                self._finish_replay(uow, receipt, runtime_claim)
                return _acquisition_result(acquired, receipt.receipt_id, True)
            acquired = uow.outcome_acquisition.acquire(evaluation_run_id)
            result_hash = canonical_json_sha256(acquired)
            self._finish(uow, receipt, "EVALUATION_RUN", evaluation_run_id, 2, result_hash, context, runtime_claim)
            # No Outcome value crosses this boundary. Only counts/identities survive commit.
            uow.commit()
            return _acquisition_result(acquired, receipt.receipt_id, False)

    @retry_postgres_transient
    @replay_concurrent_success
    def complete(self, evaluation_run_id: UUID, context: CommandContext, *, runtime_claim: AttemptClaim | None = None) -> EvaluationMutationResult:
        request_hash = canonical_json_sha256({"evaluation_run_id": evaluation_run_id})
        with terminal_failure_boundary(
            self._failure_recorder,
            operation="COMPLETE_EVALUATION_RUN",
            scope_id=str(evaluation_run_id),
            request_hash=request_hash,
            error_class="COMMAND",
            error_code="COMPLETE_EVALUATION_RUN_REJECTED",
            context=context,
            runtime_claim=runtime_claim,
        ):
            return self._complete_once(evaluation_run_id, context, runtime_claim=runtime_claim)

    def _complete_once(self, evaluation_run_id: UUID, context: CommandContext, *, runtime_claim: AttemptClaim | None) -> EvaluationMutationResult:
        request_hash = canonical_json_sha256({"evaluation_run_id": evaluation_run_id})
        with self._uow_provider() as uow:
            receipt = self._start(uow, "COMPLETE_EVALUATION_RUN", str(evaluation_run_id), request_hash, context, runtime_claim)
            if not receipt.is_new:
                ensure_replay_succeeded(receipt)
                _receipt_id(receipt, "EVALUATION_RUN")
                completed = uow.evaluations.complete(evaluation_run_id)
                _require_result_hash(receipt, canonical_json_sha256(completed))
                self._finish_replay(uow, receipt, runtime_claim)
                return _completion_result(completed, receipt.receipt_id, True)
            completed = uow.evaluations.complete(evaluation_run_id)
            result_hash = canonical_json_sha256(completed)
            self._finish(uow, receipt, "EVALUATION_RUN", evaluation_run_id, 3, result_hash, context, runtime_claim)
            uow.commit()
            return _completion_result(completed, receipt.receipt_id, False)

    def _start(self, uow: EvaluationUnitOfWork, kind: str, scope: str, request_hash: str, context: CommandContext, claim: AttemptClaim | None) -> ReceiptRecord:
        if claim is not None:
            uow.runtime_finalization.lock_live(claim)
        return uow.receipts.start(receipt_id=self._id_factory(), command_kind=kind, scope_id=scope, idempotency_key=context.idempotency_key, request_hash=request_hash)

    def _finish(self, uow: EvaluationUnitOfWork, receipt: ReceiptRecord, kind: str, aggregate_id: UUID, version: int, result_hash: str, context: CommandContext, claim: AttemptClaim | None) -> None:
        uow.receipts.succeed(receipt_id=receipt.receipt_id, aggregate_kind=kind, aggregate_id=str(aggregate_id), aggregate_version=version, result_hash=result_hash, runtime_claim=claim)
        uow.audit.append(audit_event_id=self._id_factory(), receipt_id=receipt.receipt_id, actor_type=context.actor_type.value, actor_id=context.actor_id, aggregate_kind=kind, aggregate_id=str(aggregate_id), action=f"{kind}_MUTATED", reason_code=context.reason_code, before_version=version - 1 if version > 1 else None, after_version=version, runtime_claim=claim)
        if claim is not None:
            uow.runtime_finalization.succeed(claim, receipt_id=receipt.receipt_id, result_hash=result_hash)

    @staticmethod
    def _finish_replay(uow: EvaluationUnitOfWork, receipt: ReceiptRecord, claim: AttemptClaim | None) -> None:
        if claim is not None:
            assert receipt.result_hash is not None
            uow.runtime_finalization.succeed(claim, receipt_id=receipt.receipt_id, result_hash=receipt.result_hash)
            uow.commit()


def _receipt_id(receipt: ReceiptRecord, expected_kind: str) -> UUID:
    if receipt.result_aggregate_kind != expected_kind or receipt.result_aggregate_id is None:
        raise ArtifactIntegrityError("Evaluation receipt is incomplete")
    return UUID(receipt.result_aggregate_id)


def _require_result_hash(receipt: ReceiptRecord, actual: str) -> None:
    if receipt.result_hash != actual:
        raise ArtifactIntegrityError("Evaluation receipt and Authority differ")


def _acquisition_result(result: OutcomeAcquisitionResult, receipt_id: UUID, replayed: bool) -> EvaluationMutationResult:
    return EvaluationMutationResult("EVALUATION_RUN", result.evaluation_run_id, None, result.observation_count, result.input_roster_sha256, receipt_id, replayed)


def _completion_result(result: EvaluationCompletionResult, receipt_id: UUID, replayed: bool) -> EvaluationMutationResult:
    return EvaluationMutationResult("EVALUATION_RUN", result.evaluation_run_id, None, result.metric_count, result.metric_roster_sha256, receipt_id, replayed)


__all__ = ["EvaluationCommands", "EvaluationMutationResult"]
