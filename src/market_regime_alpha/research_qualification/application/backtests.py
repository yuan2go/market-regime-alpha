"""Generic Backtest validation, planning, and predeclaration operations."""

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
from market_regime_alpha.research_qualification.domain.backtest import (
    BacktestSpecification,
    FrozenBacktestRun,
    freeze_backtest_specification,
)
from market_regime_alpha.research_qualification.domain.backtest_execution import (
    BacktestEvaluationExecution,
    BacktestRuntimeBinding,
)
from market_regime_alpha.research_qualification.domain.backtest_report import (
    BacktestReportArtifactBinding,
)
from market_regime_alpha.research_qualification.ports.backtest_uow import (
    BacktestUnitOfWork,
    BacktestUnitOfWorkProvider,
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
class BacktestValidation:
    valid: bool
    specification_sha256: str
    definition_sha256: str


@dataclass(frozen=True, slots=True)
class BacktestMutationResult:
    exploratory_backtest_run_id: UUID
    receipt_id: UUID
    result_hash: str
    replayed: bool


@dataclass(frozen=True, slots=True)
class BacktestLineageMutationResult:
    exploratory_backtest_run_id: UUID
    binding_id: UUID
    receipt_id: UUID
    result_hash: str
    replayed: bool


class BacktestApplication:
    def __init__(
        self,
        uow_provider: BacktestUnitOfWorkProvider,
        *,
        id_factory: Callable[[], UUID],
    ) -> None:
        self._uow_provider = uow_provider
        self._id_factory = id_factory
        self._failure_recorder = RuntimeCommandFailureRecorder(
            cast(CommandFailureUnitOfWorkProvider, uow_provider),
            id_factory=id_factory,
        )

    def validate(self, specification: BacktestSpecification) -> BacktestValidation:
        """Read-only structural validation; construction already froze invariants."""

        return BacktestValidation(
            True,
            str(specification.content_sha256),
            str(specification.definition_sha256),
        )

    def plan(self, specification: BacktestSpecification) -> FrozenBacktestRun:
        """Read-only immutable runtime projection, never a persistent Authority."""

        return freeze_backtest_specification(specification)

    @retry_transient_transaction
    @replay_concurrent_success
    def predeclare(
        self,
        specification: BacktestSpecification,
        context: CommandContext,
        *,
        runtime_claim: AttemptClaim | None = None,
    ) -> BacktestMutationResult:
        request_hash = canonical_json_sha256(specification)
        with terminal_failure_boundary(
            self._failure_recorder,
            operation="PREDECLARE_BACKTEST",
            scope_id=f"{specification.run_code}:{specification.generation}",
            request_hash=request_hash,
            error_class="COMMAND",
            error_code="PREDECLARE_BACKTEST_REJECTED",
            context=context,
            runtime_claim=runtime_claim,
        ):
            return self._predeclare_once(
                specification,
                context,
                request_hash=request_hash,
                runtime_claim=runtime_claim,
            )

    def _predeclare_once(
        self,
        specification: BacktestSpecification,
        context: CommandContext,
        *,
        request_hash: str,
        runtime_claim: AttemptClaim | None,
    ) -> BacktestMutationResult:
        with self._uow_provider() as uow:
            if runtime_claim is not None:
                uow.runtime_finalization.lock_live(runtime_claim)
            receipt = uow.receipts.start(
                receipt_id=self._id_factory(),
                command_kind="PREDECLARE_BACKTEST",
                scope_id=f"{specification.run_code}:{specification.generation}",
                idempotency_key=context.idempotency_key,
                request_hash=request_hash,
            )
            if not receipt.is_new:
                return self._replay(uow, receipt, runtime_claim)
            uow.backtests.lock_identity(specification.run_code, specification.generation)
            uow.artifacts.require_exact(specification.code_artifact, lock=True)
            uow.artifacts.require_exact(specification.config_artifact, lock=True)
            record = uow.backtests.predeclare(
                specification,
                request_identity=context.idempotency_key,
                request_sha256=request_hash,
            )
            result_hash = canonical_json_sha256(record)
            uow.receipts.succeed(
                receipt_id=receipt.receipt_id,
                aggregate_kind="EXPLORATORY_BACKTEST_RUN",
                aggregate_id=str(record.exploratory_backtest_run_id),
                aggregate_version=specification.generation,
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
                action="PREDECLARE_BACKTEST",
                reason_code=context.reason_code,
                before_version=None,
                after_version=specification.generation,
                runtime_claim=runtime_claim,
            )
            if runtime_claim is not None:
                uow.runtime_finalization.succeed(
                    runtime_claim,
                    receipt_id=receipt.receipt_id,
                    result_hash=result_hash,
                )
            uow.commit()
            return BacktestMutationResult(
                record.exploratory_backtest_run_id,
                receipt.receipt_id,
                result_hash,
                False,
            )

    def _replay(
        self,
        uow: BacktestUnitOfWork,
        receipt: ReceiptRecord,
        runtime_claim: AttemptClaim | None,
    ) -> BacktestMutationResult:
        ensure_replay_succeeded(receipt)
        if (
            receipt.result_aggregate_kind != "EXPLORATORY_BACKTEST_RUN"
            or receipt.result_aggregate_id is None
            or receipt.result_hash is None
        ):
            raise ArtifactIntegrityError("Backtest receipt is incomplete")
        aggregate_id = UUID(receipt.result_aggregate_id)
        record = uow.backtests.record(aggregate_id, lock=False)
        if canonical_json_sha256(record) != receipt.result_hash:
            raise ArtifactIntegrityError("Backtest receipt and Authority differ")
        if runtime_claim is not None:
            uow.runtime_finalization.succeed(
                runtime_claim,
                receipt_id=receipt.receipt_id,
                result_hash=receipt.result_hash,
            )
            uow.commit()
        return BacktestMutationResult(
            aggregate_id,
            receipt.receipt_id,
            receipt.result_hash,
            True,
        )

    @retry_transient_transaction
    @replay_concurrent_success
    def bind_runtime(
        self,
        binding: BacktestRuntimeBinding,
        context: CommandContext,
    ) -> BacktestLineageMutationResult:
        """Bind a derived action to Runtime without owning Runtime state."""

        return self._bind_runtime_once(binding, context)

    def _bind_runtime_once(
        self,
        binding: BacktestRuntimeBinding,
        context: CommandContext,
    ) -> BacktestLineageMutationResult:
        request_hash = canonical_json_sha256(binding)
        with self._uow_provider() as uow:
            receipt = uow.receipts.start(
                receipt_id=self._id_factory(),
                command_kind="BIND_BACKTEST_RUNTIME",
                scope_id=str(binding.action.action_id),
                idempotency_key=context.idempotency_key,
                request_hash=request_hash,
            )
            if not receipt.is_new:
                return self._replay_lineage(
                    uow,
                    receipt,
                    expected_kind="BACKTEST_RUNTIME_BINDING",
                    expected_id=binding.backtest_runtime_binding_id,
                    expected_hash=str(binding.content_sha256),
                    exploratory_backtest_run_id=(binding.exploratory_backtest_run_id),
                )
            uow.backtests.bind_runtime(binding)
            self._complete_lineage_receipt(
                uow,
                receipt,
                context,
                aggregate_kind="BACKTEST_RUNTIME_BINDING",
                aggregate_id=binding.backtest_runtime_binding_id,
                result_hash=str(binding.content_sha256),
                action="BIND_BACKTEST_RUNTIME",
            )
            uow.commit()
            return BacktestLineageMutationResult(
                binding.exploratory_backtest_run_id,
                binding.backtest_runtime_binding_id,
                receipt.receipt_id,
                str(binding.content_sha256),
                False,
            )

    @retry_transient_transaction
    @replay_concurrent_success
    def bind_evaluation(
        self,
        binding: BacktestEvaluationExecution,
        context: CommandContext,
    ) -> BacktestLineageMutationResult:
        """Bind one frozen requirement to an exact completed Evaluation."""

        request_hash = canonical_json_sha256(binding)
        with self._uow_provider() as uow:
            receipt = uow.receipts.start(
                receipt_id=self._id_factory(),
                command_kind="BIND_BACKTEST_EVALUATION",
                scope_id=str(binding.backtest_evaluation_requirement_id),
                idempotency_key=context.idempotency_key,
                request_hash=request_hash,
            )
            if not receipt.is_new:
                return self._replay_lineage(
                    uow,
                    receipt,
                    expected_kind="BACKTEST_EVALUATION_EXECUTION",
                    expected_id=binding.backtest_evaluation_execution_id,
                    expected_hash=str(binding.content_sha256),
                    exploratory_backtest_run_id=(binding.exploratory_backtest_run_id),
                )
            uow.backtests.bind_evaluation(binding)
            self._complete_lineage_receipt(
                uow,
                receipt,
                context,
                aggregate_kind="BACKTEST_EVALUATION_EXECUTION",
                aggregate_id=binding.backtest_evaluation_execution_id,
                result_hash=str(binding.content_sha256),
                action="BIND_BACKTEST_EVALUATION",
            )
            uow.commit()
            return BacktestLineageMutationResult(
                binding.exploratory_backtest_run_id,
                binding.backtest_evaluation_execution_id,
                receipt.receipt_id,
                str(binding.content_sha256),
                False,
            )

    @retry_transient_transaction
    @replay_concurrent_success
    def bind_report(
        self,
        binding: BacktestReportArtifactBinding,
        context: CommandContext,
    ) -> BacktestLineageMutationResult:
        """Bind verified report bytes as a derived, non-Authority projection."""

        request_hash = canonical_json_sha256(binding)
        with self._uow_provider() as uow:
            receipt = uow.receipts.start(
                receipt_id=self._id_factory(),
                command_kind="BIND_BACKTEST_REPORT",
                scope_id=str(binding.backtest_report_artifact_id),
                idempotency_key=context.idempotency_key,
                request_hash=request_hash,
            )
            if not receipt.is_new:
                return self._replay_lineage(
                    uow,
                    receipt,
                    expected_kind="BACKTEST_REPORT_ARTIFACT",
                    expected_id=binding.backtest_report_artifact_id,
                    expected_hash=str(binding.content_sha256),
                    exploratory_backtest_run_id=(binding.exploratory_backtest_run_id),
                )
            uow.artifacts.require_exact(binding.json_artifact, lock=True)
            uow.artifacts.require_exact(binding.markdown_artifact, lock=True)
            uow.backtests.bind_report(binding)
            self._complete_lineage_receipt(
                uow,
                receipt,
                context,
                aggregate_kind="BACKTEST_REPORT_ARTIFACT",
                aggregate_id=binding.backtest_report_artifact_id,
                result_hash=str(binding.content_sha256),
                action="BIND_BACKTEST_REPORT",
            )
            uow.commit()
            return BacktestLineageMutationResult(
                binding.exploratory_backtest_run_id,
                binding.backtest_report_artifact_id,
                receipt.receipt_id,
                str(binding.content_sha256),
                False,
            )

    def _complete_lineage_receipt(
        self,
        uow: BacktestUnitOfWork,
        receipt: ReceiptRecord,
        context: CommandContext,
        *,
        aggregate_kind: str,
        aggregate_id: UUID,
        result_hash: str,
        action: str,
    ) -> None:
        uow.receipts.succeed(
            receipt_id=receipt.receipt_id,
            aggregate_kind=aggregate_kind,
            aggregate_id=str(aggregate_id),
            aggregate_version=1,
            result_hash=result_hash,
        )
        uow.audit.append(
            audit_event_id=self._id_factory(),
            receipt_id=receipt.receipt_id,
            actor_type=context.actor_type.value,
            actor_id=context.actor_id,
            aggregate_kind=aggregate_kind,
            aggregate_id=str(aggregate_id),
            action=action,
            reason_code=context.reason_code,
            before_version=None,
            after_version=1,
        )

    @staticmethod
    def _replay_lineage(
        uow: BacktestUnitOfWork,
        receipt: ReceiptRecord,
        *,
        expected_kind: str,
        expected_id: UUID,
        expected_hash: str,
        exploratory_backtest_run_id: UUID,
    ) -> BacktestLineageMutationResult:
        ensure_replay_succeeded(receipt)
        if (
            receipt.result_aggregate_kind != expected_kind
            or receipt.result_aggregate_id != str(expected_id)
            or receipt.result_hash != expected_hash
        ):
            raise ArtifactIntegrityError("Backtest execution lineage receipt differs from Authority")
        return BacktestLineageMutationResult(
            exploratory_backtest_run_id,
            expected_id,
            receipt.receipt_id,
            expected_hash,
            True,
        )


__all__ = [
    "BacktestApplication",
    "BacktestLineageMutationResult",
    "BacktestMutationResult",
    "BacktestValidation",
]
