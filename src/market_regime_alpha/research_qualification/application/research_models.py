"""Commands for the narrow optional Model family/training/version Authority."""

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
from market_regime_alpha.research_qualification.domain.research_models import (
    ModelTrainingRunPlan,
    ModelVersionPlan,
    ReproducibleModelTrainingRunPlan,
    ResearchModelPlan,
)
from market_regime_alpha.research_qualification.domain.model import ArtifactBinding
from market_regime_alpha.research_qualification.ports.model_execution import (
    FrozenModelTrainingInput,
    ModelScalarParameter,
    ModelScalarType,
    ModelTrainer,
)
from market_regime_alpha.research_qualification.ports.model_inputs import (
    ModelArtifactPublisher,
    ModelTrainingInputProvider,
    OpenModelTrainingRunRequest,
    ReproducibleModelTrainingRunRequest,
)
from market_regime_alpha.research_qualification.ports.model_uow import (
    ResearchModelUnitOfWork,
    ResearchModelUnitOfWorkProvider,
)
from market_regime_alpha.runtime.application import (
    CommandContext,
    RuntimeCommandFailureRecorder,
)
from market_regime_alpha.runtime.errors import ArtifactIntegrityError
from market_regime_alpha.runtime.ports import (
    AttemptClaim,
    CommandFailureUnitOfWorkProvider,
    ArtifactRecord,
    ReceiptRecord,
)
from market_regime_alpha.shared.hashing import canonical_json_sha256


@dataclass(frozen=True, slots=True)
class ModelMutationResult:
    aggregate_kind: str
    aggregate_id: UUID
    aggregate_version: int
    result_hash: str
    receipt_id: UUID
    replayed: bool


@dataclass(frozen=True, slots=True)
class RegisterModelVersionRequest:
    model_version_id: UUID
    model_id: UUID
    version: int
    model_training_run_id: UUID
    provenance_sha256: str


class ModelCommands:
    """Internal mutation boundary; public operations derive training rosters."""

    def __init__(
        self,
        uow_provider: ResearchModelUnitOfWorkProvider,
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
    def register_model(
        self,
        plan: ResearchModelPlan,
        context: CommandContext,
        *,
        runtime_claim: AttemptClaim | None = None,
    ) -> ModelMutationResult:
        request_hash = canonical_json_sha256(plan)
        with terminal_failure_boundary(
            self._failure_recorder,
            operation="REGISTER_RESEARCH_MODEL",
            scope_id=plan.model_code,
            request_hash=request_hash,
            error_class="COMMAND",
            error_code="REGISTER_RESEARCH_MODEL_REJECTED",
            context=context,
            runtime_claim=runtime_claim,
        ):
            with self._uow_provider() as uow:
                receipt = self._start(
                    uow,
                    "REGISTER_RESEARCH_MODEL",
                    plan.model_code,
                    request_hash,
                    context,
                    runtime_claim,
                )
                if not receipt.is_new:
                    return self._replay(uow, receipt, runtime_claim)
                uow.research_models.lock_model_identity(plan.model_code)
                uow.artifacts.require_exact(plan.code_artifact, lock=True)
                uow.artifacts.require_exact(plan.config_artifact, lock=True)
                record = uow.research_models.register_model(
                    plan,
                    request_identity=context.idempotency_key,
                    request_sha256=request_hash,
                )
                return self._finish(
                    uow,
                    receipt,
                    "MODEL",
                    record.model_id,
                    1,
                    canonical_json_sha256(record),
                    context,
                    runtime_claim,
                )

    @retry_transient_transaction
    @replay_concurrent_success
    def open_training_run(
        self,
        plan: ModelTrainingRunPlan,
        context: CommandContext,
        *,
        runtime_claim: AttemptClaim | None = None,
    ) -> ModelMutationResult:
        request_hash = canonical_json_sha256(plan)
        scope_id = f"{plan.model_id}:{plan.evaluation_run_id}"
        with terminal_failure_boundary(
            self._failure_recorder,
            operation="OPEN_MODEL_TRAINING_RUN",
            scope_id=scope_id,
            request_hash=request_hash,
            error_class="COMMAND",
            error_code="OPEN_MODEL_TRAINING_RUN_REJECTED",
            context=context,
            runtime_claim=runtime_claim,
        ):
            with self._uow_provider() as uow:
                receipt = self._start(
                    uow,
                    "OPEN_MODEL_TRAINING_RUN",
                    scope_id,
                    request_hash,
                    context,
                    runtime_claim,
                )
                if not receipt.is_new:
                    return self._replay(uow, receipt, runtime_claim)
                uow.research_models.model_record(plan.model_id, lock=True)
                for artifact in (
                    plan.training_input_artifact,
                    plan.code_artifact,
                    plan.config_artifact,
                ):
                    uow.artifacts.require_exact(artifact, lock=True)
                record = uow.research_models.register_training_run(
                    plan,
                    request_identity=context.idempotency_key,
                    request_sha256=request_hash,
                )
                return self._finish(
                    uow,
                    receipt,
                    "MODEL_TRAINING_RUN",
                    record.model_training_run_id,
                    1,
                    canonical_json_sha256(record),
                    context,
                    runtime_claim,
                )

    @retry_transient_transaction
    @replay_concurrent_success
    def register_version(
        self,
        plan: ModelVersionPlan,
        context: CommandContext,
        *,
        runtime_claim: AttemptClaim | None = None,
    ) -> ModelMutationResult:
        request_hash = canonical_json_sha256(plan)
        scope_id = f"{plan.model_id}:{plan.version}"
        with terminal_failure_boundary(
            self._failure_recorder,
            operation="REGISTER_MODEL_VERSION",
            scope_id=scope_id,
            request_hash=request_hash,
            error_class="COMMAND",
            error_code="REGISTER_MODEL_VERSION_REJECTED",
            context=context,
            runtime_claim=runtime_claim,
        ):
            with self._uow_provider() as uow:
                receipt = self._start(
                    uow,
                    "REGISTER_MODEL_VERSION",
                    scope_id,
                    request_hash,
                    context,
                    runtime_claim,
                )
                if not receipt.is_new:
                    return self._replay(uow, receipt, runtime_claim)
                uow.research_models.training_run_record(
                    plan.model_training_run_id,
                    lock=True,
                )
                for artifact in (
                    plan.training_input_artifact,
                    plan.fitted_model_artifact,
                    plan.code_artifact,
                    plan.config_artifact,
                ):
                    uow.artifacts.require_exact(artifact, lock=True)
                record = uow.research_models.register_version(
                    plan,
                    request_identity=context.idempotency_key,
                    request_sha256=request_hash,
                )
                return self._finish(
                    uow,
                    receipt,
                    "MODEL_VERSION",
                    record.model_version_id,
                    record.version,
                    canonical_json_sha256(record),
                    context,
                    runtime_claim,
                )

    @retry_transient_transaction
    @replay_concurrent_success
    def open_reproducible_training_run(
        self,
        plan: ReproducibleModelTrainingRunPlan,
        context: CommandContext,
        *,
        runtime_claim: AttemptClaim | None = None,
    ) -> ModelMutationResult:
        request_hash = canonical_json_sha256(plan)
        training = plan.training_run
        scope_id = f"{training.model_id}:{training.evaluation_run_id}"
        with terminal_failure_boundary(
            self._failure_recorder,
            operation="REGISTER_REPRODUCIBLE_MODEL_TRAINING_RUN",
            scope_id=scope_id,
            request_hash=request_hash,
            error_class="COMMAND",
            error_code="REGISTER_REPRODUCIBLE_MODEL_TRAINING_RUN_REJECTED",
            context=context,
            runtime_claim=runtime_claim,
        ):
            with self._uow_provider() as uow:
                receipt = self._start(
                    uow,
                    "REGISTER_REPRODUCIBLE_MODEL_TRAINING_RUN",
                    scope_id,
                    request_hash,
                    context,
                    runtime_claim,
                )
                if not receipt.is_new:
                    return self._replay(uow, receipt, runtime_claim)
                uow.research_models.model_record(training.model_id, lock=True)
                for artifact in (
                    training.training_input_artifact,
                    training.code_artifact,
                    training.config_artifact,
                ):
                    uow.artifacts.require_exact(artifact, lock=True)
                record = uow.research_models.register_reproducible_training_run(
                    plan,
                    request_identity=context.idempotency_key,
                    request_sha256=request_hash,
                )
                return self._finish(
                    uow,
                    receipt,
                    "MODEL_TRAINING_RUN",
                    training.model_training_run_id,
                    1,
                    canonical_json_sha256(record),
                    context,
                    runtime_claim,
                )

    def _start(
        self,
        uow: ResearchModelUnitOfWork,
        command_kind: str,
        scope_id: str,
        request_hash: str,
        context: CommandContext,
        runtime_claim: AttemptClaim | None,
    ) -> ReceiptRecord:
        if runtime_claim is not None:
            uow.runtime_finalization.lock_live(runtime_claim)
        return uow.receipts.start(
            receipt_id=self._id_factory(),
            command_kind=command_kind,
            scope_id=scope_id,
            idempotency_key=context.idempotency_key,
            request_hash=request_hash,
        )

    def _finish(
        self,
        uow: ResearchModelUnitOfWork,
        receipt: ReceiptRecord,
        aggregate_kind: str,
        aggregate_id: UUID,
        aggregate_version: int,
        result_hash: str,
        context: CommandContext,
        runtime_claim: AttemptClaim | None,
    ) -> ModelMutationResult:
        uow.receipts.succeed(
            receipt_id=receipt.receipt_id,
            aggregate_kind=aggregate_kind,
            aggregate_id=str(aggregate_id),
            aggregate_version=aggregate_version,
            result_hash=result_hash,
            runtime_claim=runtime_claim,
        )
        uow.audit.append(
            audit_event_id=self._id_factory(),
            receipt_id=receipt.receipt_id,
            actor_type=context.actor_type.value,
            actor_id=context.actor_id,
            aggregate_kind=aggregate_kind,
            aggregate_id=str(aggregate_id),
            action={
                "MODEL": "REGISTER_RESEARCH_MODEL",
                "MODEL_TRAINING_RUN": "OPEN_MODEL_TRAINING_RUN",
                "MODEL_VERSION": "REGISTER_MODEL_VERSION",
            }[aggregate_kind],
            reason_code=context.reason_code,
            before_version=None,
            after_version=aggregate_version,
            runtime_claim=runtime_claim,
        )
        if runtime_claim is not None:
            uow.runtime_finalization.succeed(
                runtime_claim,
                receipt_id=receipt.receipt_id,
                result_hash=result_hash,
            )
        uow.commit()
        return ModelMutationResult(
            aggregate_kind,
            aggregate_id,
            aggregate_version,
            result_hash,
            receipt.receipt_id,
            False,
        )

    def _replay(
        self,
        uow: ResearchModelUnitOfWork,
        receipt: ReceiptRecord,
        runtime_claim: AttemptClaim | None,
    ) -> ModelMutationResult:
        ensure_replay_succeeded(receipt)
        if (
            receipt.result_aggregate_kind is None
            or receipt.result_aggregate_id is None
            or receipt.result_aggregate_version is None
            or receipt.result_hash is None
        ):
            raise ArtifactIntegrityError("Model command receipt is incomplete")
        aggregate_id = UUID(receipt.result_aggregate_id)
        if receipt.result_aggregate_kind == "MODEL":
            observed_hash = canonical_json_sha256(uow.research_models.model_record(aggregate_id, lock=False))
        elif receipt.result_aggregate_kind == "MODEL_TRAINING_RUN":
            reproducible = uow.research_models.reproducible_training_run_record(
                aggregate_id,
                lock=False,
            )
            observed_hash = canonical_json_sha256(
                reproducible
                if reproducible is not None
                else uow.research_models.training_run_record(
                    aggregate_id,
                    lock=False,
                )
            )
        elif receipt.result_aggregate_kind == "MODEL_VERSION":
            observed_hash = canonical_json_sha256(uow.research_models.version_record(aggregate_id, lock=False))
        else:
            raise ArtifactIntegrityError("Model receipt aggregate kind is invalid")
        if observed_hash != receipt.result_hash:
            raise ArtifactIntegrityError("Model receipt and Authority differ")
        if runtime_claim is not None:
            uow.runtime_finalization.succeed(
                runtime_claim,
                receipt_id=receipt.receipt_id,
                result_hash=receipt.result_hash,
            )
            uow.commit()
        return ModelMutationResult(
            receipt.result_aggregate_kind,
            aggregate_id,
            int(receipt.result_aggregate_version),
            receipt.result_hash,
            receipt.receipt_id,
            True,
        )


class ResearchModelApplication:
    """Public seam that derives inputs and publishes bytes before short writes."""

    def __init__(
        self,
        commands: ModelCommands,
        inputs: ModelTrainingInputProvider,
        artifacts: ModelArtifactPublisher,
        trainer: ModelTrainer,
    ) -> None:
        self._commands = commands
        self._inputs = inputs
        self._artifacts = artifacts
        self._trainer = trainer

    def register_model(
        self,
        plan: ResearchModelPlan,
        context: CommandContext,
        *,
        runtime_claim: AttemptClaim | None = None,
    ) -> ModelMutationResult:
        return self._commands.register_model(
            plan,
            context,
            runtime_claim=runtime_claim,
        )

    def open_training_run(
        self,
        request: OpenModelTrainingRunRequest,
        context: CommandContext,
        *,
        runtime_claim: AttemptClaim | None = None,
    ) -> ModelMutationResult:
        prepared = self._inputs.prepare(request)
        input_record = self._artifacts.publish(
            prepared.training_input_content,
            media_type="application/json",
            context=_child_context(context, "model-training-input"),
            expected_sha256=str(prepared.training_input_content_sha256),
            pin_reason_code="MODEL_TRAINING_INPUT",
        )
        input_artifact = _artifact_binding(input_record)
        plan = ModelTrainingRunPlan(
            model_training_run_id=request.model_training_run_id,
            model_id=request.model_id,
            evaluation_run_id=request.evaluation_run_id,
            evaluation_protocol_metric_id=request.evaluation_protocol_metric_id,
            exploratory_backtest_run_id=request.exploratory_backtest_run_id,
            exploratory_backtest_arm_id=request.exploratory_backtest_arm_id,
            exploratory_backtest_fold_id=request.exploratory_backtest_fold_id,
            algorithm_code=request.algorithm_code,
            algorithm_version=request.algorithm_version,
            algorithm_sha256=request.algorithm_sha256,
            ridge_alpha=request.ridge_alpha,
            random_seed=request.random_seed,
            training_input_artifact=input_artifact,
            code_artifact=request.code_artifact,
            config_artifact=request.config_artifact,
            provenance_sha256=request.provenance_sha256,
            samples=prepared.samples,
        )
        return self._commands.open_training_run(
            plan,
            context,
            runtime_claim=runtime_claim,
        )

    def fit_and_register_version(
        self,
        request: RegisterModelVersionRequest,
        context: CommandContext,
        *,
        runtime_claim: AttemptClaim | None = None,
    ) -> ModelMutationResult:
        registered = self._inputs.load_registered(request.model_training_run_id)
        if registered.model_id != request.model_id:
            raise ValueError("ModelVersion request does not match training Model")
        if registered.ridge_alpha is None:
            raise ValueError(
                "legacy ModelVersion path requires historical ridge_alpha; "
                "current models use reproducible typed hyperparameters"
            )
        fitted = self._trainer.fit(
            FrozenModelTrainingInput(
                algorithm_code=registered.algorithm_code,
                algorithm_version=registered.algorithm_version,
                implementation_sha256=registered.implementation_sha256,
                feature_definition_ids=registered.feature_definition_ids,
                hyperparameters=(
                    ModelScalarParameter(
                        parameter_code="ridge_alpha",
                        value_type=ModelScalarType.DECIMAL,
                        decimal_value=registered.ridge_alpha,
                    ),
                ),
                seed=registered.random_seed,
                rows=registered.linear_rows,
            )
        )
        fitted_record = self._artifacts.publish(
            fitted.content,
            media_type="application/json",
            context=_child_context(context, "fitted-model"),
            expected_sha256=str(fitted.content_sha256),
            pin_reason_code="FITTED_MODEL",
        )
        fitted_artifact = _artifact_binding(fitted_record)
        plan = ModelVersionPlan(
            model_version_id=request.model_version_id,
            model_id=request.model_id,
            version=request.version,
            model_training_run_id=request.model_training_run_id,
            training_input_artifact=registered.training_input_artifact,
            fitted_model_artifact=fitted_artifact,
            coefficient_count=fitted.coefficient_count,
            fitted_model_sha256=fitted.content_sha256,
            code_artifact=registered.code_artifact,
            config_artifact=registered.config_artifact,
            provenance_sha256=request.provenance_sha256,
        )
        return self._commands.register_version(
            plan,
            context,
            runtime_claim=runtime_claim,
        )

    def open_reproducible_training_run(
        self,
        request: ReproducibleModelTrainingRunRequest,
        context: CommandContext,
        *,
        runtime_claim: AttemptClaim | None = None,
    ) -> ModelMutationResult:
        prepared = self._inputs.prepare_reproducible(request)
        input_record = self._artifacts.publish(
            prepared.training.training_input_content,
            media_type="application/json",
            context=_child_context(context, "model-training-input"),
            expected_sha256=str(prepared.training.training_input_content_sha256),
            pin_reason_code="MODEL_TRAINING_INPUT",
        )
        legacy = request.training
        plan = ModelTrainingRunPlan(
            model_training_run_id=legacy.model_training_run_id,
            model_id=legacy.model_id,
            evaluation_run_id=legacy.evaluation_run_id,
            evaluation_protocol_metric_id=legacy.evaluation_protocol_metric_id,
            exploratory_backtest_run_id=legacy.exploratory_backtest_run_id,
            exploratory_backtest_arm_id=legacy.exploratory_backtest_arm_id,
            exploratory_backtest_fold_id=legacy.exploratory_backtest_fold_id,
            algorithm_code=legacy.algorithm_code,
            algorithm_version=legacy.algorithm_version,
            algorithm_sha256=legacy.algorithm_sha256,
            ridge_alpha=legacy.ridge_alpha,
            random_seed=legacy.random_seed,
            training_input_artifact=_artifact_binding(input_record),
            code_artifact=legacy.code_artifact,
            config_artifact=legacy.config_artifact,
            provenance_sha256=legacy.provenance_sha256,
            samples=prepared.training.samples,
        )
        return self._commands.open_reproducible_training_run(
            ReproducibleModelTrainingRunPlan(
                training_run=plan,
                reproducibility=prepared.reproducibility,
            ),
            context,
            runtime_claim=runtime_claim,
        )

    def fit_and_register_reproducible_version(
        self,
        request: RegisterModelVersionRequest,
        context: CommandContext,
        *,
        runtime_claim: AttemptClaim | None = None,
    ) -> ModelMutationResult:
        registered = self._inputs.load_registered_reproducible(request.model_training_run_id)
        training = registered.training
        if training.model_id != request.model_id:
            raise ValueError("ModelVersion request does not match training Model")
        fitted = self._trainer.fit(
            FrozenModelTrainingInput(
                algorithm_code=training.algorithm_code,
                algorithm_version=training.algorithm_version,
                implementation_sha256=training.implementation_sha256,
                feature_definition_ids=training.feature_definition_ids,
                hyperparameters=tuple(
                    ModelScalarParameter(
                        parameter_code=item.parameter_code,
                        value_type=ModelScalarType(item.value_type.value),
                        decimal_value=item.decimal_value,
                        integer_value=item.integer_value,
                        boolean_value=item.boolean_value,
                        text_value=item.text_value,
                    )
                    for item in registered.reproducibility.hyperparameters
                ),
                seed=training.random_seed,
                rows=training.linear_rows,
            )
        )
        fitted_record = self._artifacts.publish(
            fitted.content,
            media_type="application/json",
            context=_child_context(context, "fitted-model"),
            expected_sha256=str(fitted.content_sha256),
            pin_reason_code="FITTED_MODEL",
        )
        plan = ModelVersionPlan(
            model_version_id=request.model_version_id,
            model_id=request.model_id,
            version=request.version,
            model_training_run_id=request.model_training_run_id,
            training_input_artifact=training.training_input_artifact,
            fitted_model_artifact=_artifact_binding(fitted_record),
            coefficient_count=fitted.coefficient_count,
            fitted_model_sha256=fitted.content_sha256,
            code_artifact=training.code_artifact,
            config_artifact=training.config_artifact,
            provenance_sha256=request.provenance_sha256,
        )
        return self._commands.register_version(
            plan,
            context,
            runtime_claim=runtime_claim,
        )


def _artifact_binding(record: ArtifactRecord) -> ArtifactBinding:
    return ArtifactBinding(
        artifact_id=record.artifact_id,
        content_sha256=record.content_sha256,
        size_bytes=record.size_bytes,
    )


def _child_context(context: CommandContext, suffix: str) -> CommandContext:
    candidate = f"{context.idempotency_key}/{suffix}"
    if len(candidate) > 200:
        digest = canonical_json_sha256({"idempotency_key": context.idempotency_key, "suffix": suffix})
        candidate = f"{context.idempotency_key[:130]}/{digest}"
    return CommandContext(
        idempotency_key=candidate,
        actor_type=context.actor_type,
        actor_id=context.actor_id,
        reason_code=context.reason_code,
    )


__all__ = [
    "ModelCommands",
    "ModelMutationResult",
    "RegisterModelVersionRequest",
    "ResearchModelApplication",
]
