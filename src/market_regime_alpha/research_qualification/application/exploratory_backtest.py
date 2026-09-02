"""Register one immutable exploratory backtest protocol and lineage root."""

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
from market_regime_alpha.research_qualification.domain.exploratory_backtest import (
    ExploratoryBacktestRunPlan,
)
from market_regime_alpha.research_qualification.ports.exploratory_backtest_uow import (
    ExploratoryBacktestUnitOfWork,
    ExploratoryBacktestUnitOfWorkProvider,
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
class ExploratoryBacktestMutationResult:
    exploratory_backtest_run_id: UUID
    receipt_id: UUID
    result_hash: str
    replayed: bool


class ExploratoryBacktestCommands:
    def __init__(
        self,
        uow_provider: ExploratoryBacktestUnitOfWorkProvider,
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
    def register(
        self,
        plan: ExploratoryBacktestRunPlan,
        context: CommandContext,
        *,
        runtime_claim: AttemptClaim | None = None,
    ) -> ExploratoryBacktestMutationResult:
        request_hash = canonical_json_sha256(plan)
        with terminal_failure_boundary(
            self._failure_recorder,
            operation="REGISTER_EXPLORATORY_BACKTEST_RUN",
            scope_id=f"{plan.run_code}:{plan.generation}",
            request_hash=request_hash,
            error_class="COMMAND",
            error_code="REGISTER_EXPLORATORY_BACKTEST_RUN_REJECTED",
            context=context,
            runtime_claim=runtime_claim,
        ):
            return self._register_once(
                plan,
                context,
                request_hash=request_hash,
                runtime_claim=runtime_claim,
            )

    def _register_once(
        self,
        plan: ExploratoryBacktestRunPlan,
        context: CommandContext,
        *,
        request_hash: str,
        runtime_claim: AttemptClaim | None,
    ) -> ExploratoryBacktestMutationResult:
        with self._uow_provider() as uow:
            if runtime_claim is not None:
                uow.runtime_finalization.lock_live(runtime_claim)
            receipt = uow.receipts.start(
                receipt_id=self._id_factory(),
                command_kind="REGISTER_EXPLORATORY_BACKTEST_RUN",
                scope_id=f"{plan.run_code}:{plan.generation}",
                idempotency_key=context.idempotency_key,
                request_hash=request_hash,
            )
            if not receipt.is_new:
                return self._replay(uow, receipt, runtime_claim)
            uow.exploratory_backtests.lock_identity(plan.run_code, plan.generation)
            uow.artifacts.require_exact(plan.code_artifact, lock=True)
            uow.artifacts.require_exact(plan.config_artifact, lock=True)
            record = uow.exploratory_backtests.register(
                plan,
                request_identity=context.idempotency_key,
                request_sha256=request_hash,
            )
            result_hash = canonical_json_sha256(record)
            uow.receipts.succeed(
                receipt_id=receipt.receipt_id,
                aggregate_kind="EXPLORATORY_BACKTEST_RUN",
                aggregate_id=str(record.exploratory_backtest_run_id),
                aggregate_version=plan.generation,
                result_hash=result_hash,
                runtime_claim=runtime_claim,
            )
            uow.audit.append(
                audit_event_id=self._id_factory(),
                receipt_id=receipt.receipt_id,
                actor_type=context.actor_type.value,
                actor_id=context.actor_id,
                aggregate_kind="EXPLORATORY_BACKTEST_RUN",
                aggregate_id=str(record.exploratory_backtest_run_id),
                action="REGISTER_EXPLORATORY_BACKTEST_RUN",
                reason_code=context.reason_code,
                before_version=None,
                after_version=plan.generation,
                runtime_claim=runtime_claim,
            )
            if runtime_claim is not None:
                uow.runtime_finalization.succeed(
                    runtime_claim,
                    receipt_id=receipt.receipt_id,
                    result_hash=result_hash,
                )
            uow.commit()
            return ExploratoryBacktestMutationResult(
                record.exploratory_backtest_run_id,
                receipt.receipt_id,
                result_hash,
                False,
            )

    def _replay(
        self,
        uow: ExploratoryBacktestUnitOfWork,
        receipt: ReceiptRecord,
        runtime_claim: AttemptClaim | None,
    ) -> ExploratoryBacktestMutationResult:
        ensure_replay_succeeded(receipt)
        if (
            receipt.result_aggregate_kind != "EXPLORATORY_BACKTEST_RUN"
            or receipt.result_aggregate_id is None
            or receipt.result_hash is None
        ):
            raise ArtifactIntegrityError(
                "Exploratory backtest receipt is incomplete"
            )
        aggregate_id = UUID(receipt.result_aggregate_id)
        record = uow.exploratory_backtests.record(aggregate_id, lock=False)
        if canonical_json_sha256(record) != receipt.result_hash:
            raise ArtifactIntegrityError(
                "Exploratory backtest receipt and Authority differ"
            )
        if runtime_claim is not None:
            uow.runtime_finalization.succeed(
                runtime_claim,
                receipt_id=receipt.receipt_id,
                result_hash=receipt.result_hash,
            )
            uow.commit()
        return ExploratoryBacktestMutationResult(
            aggregate_id,
            receipt.receipt_id,
            receipt.result_hash,
            True,
        )


__all__ = ["ExploratoryBacktestCommands", "ExploratoryBacktestMutationResult"]
