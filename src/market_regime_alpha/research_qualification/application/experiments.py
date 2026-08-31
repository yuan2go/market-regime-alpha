"""Register Experiment declarations and open execution identities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, cast
from uuid import UUID

from market_regime_alpha.research_qualification.application._results import ensure_replay_succeeded
from market_regime_alpha.research_qualification.application._command_support import replay_concurrent_success, retry_transient_transaction, terminal_failure_boundary
from market_regime_alpha.research_qualification.domain.experiment import ExperimentDefinition, ExperimentPartitionBinding, ExperimentRunPlan
from market_regime_alpha.research_qualification.ports.experiment_uow import (
    ExperimentUnitOfWork,
    ExperimentUnitOfWorkProvider,
)
from market_regime_alpha.runtime.application import CommandContext, RuntimeCommandFailureRecorder
from market_regime_alpha.runtime.errors import ArtifactIntegrityError
from market_regime_alpha.runtime.ports import (
    AttemptClaim,
    CommandFailureUnitOfWorkProvider,
    ReceiptRecord,
)
from market_regime_alpha.shared.hashing import canonical_json_sha256


@dataclass(frozen=True, slots=True)
class ExperimentMutationResult:
    aggregate_kind: str
    aggregate_id: UUID
    receipt_id: UUID
    result_hash: str
    replayed: bool


class ExperimentCommands:
    def __init__(self, uow_provider: ExperimentUnitOfWorkProvider, *, id_factory: Callable[[], UUID]) -> None:
        self._uow_provider = uow_provider
        self._id_factory = id_factory
        self._failure_recorder = RuntimeCommandFailureRecorder(
            cast(CommandFailureUnitOfWorkProvider, uow_provider), id_factory=id_factory
        )

    @retry_transient_transaction
    @replay_concurrent_success
    def register(
        self,
        definition: ExperimentDefinition,
        binding: ExperimentPartitionBinding,
        context: CommandContext,
        *,
        runtime_claim: AttemptClaim | None = None,
    ) -> ExperimentMutationResult:
        request_hash = canonical_json_sha256((definition, binding))
        with terminal_failure_boundary(
            self._failure_recorder,
            operation="REGISTER_EXPERIMENT",
            scope_id=definition.experiment_code,
            request_hash=request_hash,
            error_class="COMMAND",
            error_code="REGISTER_EXPERIMENT_REJECTED",
            context=context,
            runtime_claim=runtime_claim,
        ):
            return self._register_once(
                definition, binding, context, runtime_claim=runtime_claim
            )

    def _register_once(
        self,
        definition: ExperimentDefinition,
        binding: ExperimentPartitionBinding,
        context: CommandContext,
        *,
        runtime_claim: AttemptClaim | None,
    ) -> ExperimentMutationResult:
        request_hash = canonical_json_sha256((definition, binding))
        with self._uow_provider() as uow:
            if runtime_claim is not None:
                uow.runtime_finalization.lock_live(runtime_claim)
            receipt = uow.receipts.start(
                receipt_id=self._id_factory(), command_kind="REGISTER_EXPERIMENT",
                scope_id=definition.experiment_code, idempotency_key=context.idempotency_key,
                request_hash=request_hash,
            )
            if not receipt.is_new:
                return self._replay(uow, receipt, "EXPERIMENT", runtime_claim)
            uow.experiments.lock_identity(definition.experiment_code)
            uow.artifacts.require_exact(definition.code_artifact, lock=True)
            uow.artifacts.require_exact(definition.config_artifact, lock=True)
            record = uow.experiments.register(
                definition, binding, request_identity=context.idempotency_key,
                request_sha256=request_hash,
            )
            result_hash = canonical_json_sha256(record)
            self._finish(uow, receipt.receipt_id, "EXPERIMENT", record.experiment_id, result_hash, context, runtime_claim)
            uow.commit()
            return ExperimentMutationResult("EXPERIMENT", record.experiment_id, receipt.receipt_id, result_hash, False)

    @retry_transient_transaction
    @replay_concurrent_success
    def open_run(
        self,
        plan: ExperimentRunPlan,
        context: CommandContext,
        *,
        runtime_claim: AttemptClaim | None = None,
    ) -> ExperimentMutationResult:
        request_hash = canonical_json_sha256(plan)
        with terminal_failure_boundary(
            self._failure_recorder,
            operation="OPEN_EXPERIMENT_RUN",
            scope_id=str(plan.experiment_id),
            request_hash=request_hash,
            error_class="COMMAND",
            error_code="OPEN_EXPERIMENT_RUN_REJECTED",
            context=context,
            runtime_claim=runtime_claim,
        ):
            return self._open_run_once(plan, context, runtime_claim=runtime_claim)

    def _open_run_once(
        self,
        plan: ExperimentRunPlan,
        context: CommandContext,
        *,
        runtime_claim: AttemptClaim | None,
    ) -> ExperimentMutationResult:
        request_hash = canonical_json_sha256(plan)
        with self._uow_provider() as uow:
            if runtime_claim is not None:
                uow.runtime_finalization.lock_live(runtime_claim)
            receipt = uow.receipts.start(
                receipt_id=self._id_factory(), command_kind="OPEN_EXPERIMENT_RUN",
                scope_id=str(plan.experiment_id), idempotency_key=context.idempotency_key,
                request_hash=request_hash,
            )
            if not receipt.is_new:
                return self._replay(uow, receipt, "EXPERIMENT_RUN", runtime_claim)
            record = uow.experiments.open_run(plan)
            result_hash = canonical_json_sha256(record)
            self._finish(uow, receipt.receipt_id, "EXPERIMENT_RUN", record.experiment_run_id, result_hash, context, runtime_claim)
            uow.commit()
            return ExperimentMutationResult("EXPERIMENT_RUN", record.experiment_run_id, receipt.receipt_id, result_hash, False)

    def _finish(self, uow: ExperimentUnitOfWork, receipt_id: UUID, kind: str, aggregate_id: UUID, result_hash: str, context: CommandContext, runtime_claim: AttemptClaim | None) -> None:
        uow.receipts.succeed(receipt_id=receipt_id, aggregate_kind=kind, aggregate_id=str(aggregate_id), aggregate_version=1, result_hash=result_hash, runtime_claim=runtime_claim)
        uow.audit.append(audit_event_id=self._id_factory(), receipt_id=receipt_id, actor_type=context.actor_type.value, actor_id=context.actor_id, aggregate_kind=kind, aggregate_id=str(aggregate_id), action=f"{kind}_REGISTERED", reason_code=context.reason_code, before_version=None, after_version=1, runtime_claim=runtime_claim)
        if runtime_claim is not None:
            uow.runtime_finalization.succeed(runtime_claim, receipt_id=receipt_id, result_hash=result_hash)

    def _replay(self, uow: ExperimentUnitOfWork, receipt: ReceiptRecord, kind: str, runtime_claim: AttemptClaim | None) -> ExperimentMutationResult:
        ensure_replay_succeeded(receipt)
        if receipt.result_aggregate_kind != kind or receipt.result_aggregate_id is None or receipt.result_hash is None:
            raise ArtifactIntegrityError("Experiment receipt is incomplete")
        aggregate_id = UUID(receipt.result_aggregate_id)
        record = uow.experiments.record(aggregate_id, lock=False) if kind == "EXPERIMENT" else uow.experiments.run_record(aggregate_id, lock=False)
        if canonical_json_sha256(record) != receipt.result_hash:
            raise ArtifactIntegrityError("Experiment receipt and Authority differ")
        if runtime_claim is not None:
            uow.runtime_finalization.succeed(runtime_claim, receipt_id=receipt.receipt_id, result_hash=receipt.result_hash)
            uow.commit()
        return ExperimentMutationResult(kind, aggregate_id, receipt.receipt_id, receipt.result_hash, True)


__all__ = ["ExperimentCommands", "ExperimentMutationResult"]
