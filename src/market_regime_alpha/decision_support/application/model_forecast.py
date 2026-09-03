"""Produce complete uncalibrated Forecasts from one exact later-generation model."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable
from uuid import UUID, uuid4

from market_regime_alpha.decision_support.application.inference import (
    ProduceInferenceResult,
    _InferenceIdentities,
    _record_hash,
    _require_succeeded,
    _result,
)
from market_regime_alpha.decision_support.domain import (
    ForecastModelBindingPlan,
    ForecastStatus,
    ModelPredictionState,
    PreparedForecastInputs,
    SignalStatus,
    build_forecast_authority,
    build_signal_authority,
)
from market_regime_alpha.decision_support.errors import (
    DecisionCommitOutcomeUnknownError,
    DecisionRetryableTransactionError,
    DecisionTransactionRetryExhaustedError,
    InferenceAuthorityIntegrityError,
)
from market_regime_alpha.decision_support.ports import (
    InferenceQueryProvider,
    InferenceUnitOfWork,
    InferenceUnitOfWorkProvider,
    ModelForecastInputPreparationProvider,
    ModelForecastQueryProvider,
    PreparedModelForecastInputs,
)
from market_regime_alpha.runtime.application import CommandContext
from market_regime_alpha.runtime.errors import (
    IdempotencyKeyReusedError,
    StaleFenceError,
)
from market_regime_alpha.runtime.ports import AttemptClaim, ReceiptRecord
from market_regime_alpha.shared.hashing import canonical_json_sha256


_MAX_TRANSACTION_ATTEMPTS = 3


@dataclass(frozen=True, slots=True)
class ProduceModelForecastResult:
    inference: ProduceInferenceResult
    model_version_id: UUID
    binding_count: int
    binding_roster_sha256: str
    result_hash: str
    replayed: bool

    def as_replay(self) -> ProduceModelForecastResult:
        return replace(self, replayed=True, inference=self.inference.as_replay())


class ModelForecastCommands:
    def __init__(
        self,
        preparation: ModelForecastInputPreparationProvider,
        uow_provider: InferenceUnitOfWorkProvider,
        inference_queries: InferenceQueryProvider,
        model_queries: ModelForecastQueryProvider,
        *,
        id_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self._preparation = preparation
        self._uow_provider = uow_provider
        self._inference_queries = inference_queries
        self._model_queries = model_queries
        self._id_factory = id_factory

    def produce(
        self,
        decision_run_id: UUID,
        strategy_version_id: UUID,
        model_version_id: UUID,
        context: CommandContext,
        *,
        runtime_claim: AttemptClaim,
    ) -> ProduceModelForecastResult:
        request_hash = canonical_json_sha256(
            {
                "actor_id": context.actor_id,
                "actor_type": context.actor_type,
                "decision_run_id": decision_run_id,
                "model_version_id": model_version_id,
                "reason_code": context.reason_code,
                "strategy_version_id": strategy_version_id,
            }
        )
        existing = self._inference_queries.find_request(
            decision_run_id,
            strategy_version_id,
            context.idempotency_key,
        )
        if existing is not None:
            if existing.request_sha256 != request_hash:
                raise IdempotencyKeyReusedError("Model Forecast replay inputs differ")
            return self._external_replay(existing, model_version_id)
        prepared = self._preparation.prepare(
            decision_run_id,
            strategy_version_id,
            model_version_id,
        )
        if (
            prepared.inference.signal_inputs.decision_run_id != decision_run_id
            or prepared.inference.signal_inputs.strategy_version.strategy_version_id
            != strategy_version_id
            or prepared.model_version_id != model_version_id
        ):
            raise InferenceAuthorityIntegrityError(
                "Model Forecast preparation returned another Authority identity"
            )
        identities = _ModelForecastIdentities.create(prepared, self._id_factory)
        for attempt in range(_MAX_TRANSACTION_ATTEMPTS):
            try:
                return self._produce_once(
                    prepared,
                    context,
                    request_hash=request_hash,
                    identities=identities,
                    runtime_claim=runtime_claim,
                )
            except (
                DecisionRetryableTransactionError,
                DecisionCommitOutcomeUnknownError,
            ) as exc:
                existing = self._inference_queries.find_request(
                    decision_run_id,
                    strategy_version_id,
                    context.idempotency_key,
                )
                if existing is not None:
                    if existing.request_sha256 != request_hash:
                        raise IdempotencyKeyReusedError(
                            "Model Forecast replay inputs differ"
                        ) from exc
                    return self._external_replay(existing, model_version_id)
                if attempt == _MAX_TRANSACTION_ATTEMPTS - 1:
                    if isinstance(exc, DecisionRetryableTransactionError):
                        raise DecisionTransactionRetryExhaustedError(
                            "Model Forecast exhausted transaction retries"
                        ) from exc
                    raise
            except StaleFenceError as exc:
                existing = self._inference_queries.find_request(
                    decision_run_id,
                    strategy_version_id,
                    context.idempotency_key,
                )
                if existing is not None:
                    if existing.request_sha256 != request_hash:
                        raise IdempotencyKeyReusedError(
                            "Model Forecast replay inputs differ"
                        ) from exc
                    return self._external_replay(existing, model_version_id)
                raise
        raise AssertionError("Model Forecast bounded retry loop did not terminate")

    def _produce_once(
        self,
        prepared: PreparedModelForecastInputs,
        context: CommandContext,
        *,
        request_hash: str,
        identities: _ModelForecastIdentities,
        runtime_claim: AttemptClaim,
    ) -> ProduceModelForecastResult:
        signal_inputs = prepared.inference.signal_inputs
        with self._uow_provider() as uow:
            uow.runtime_finalization.lock_live_for_step(
                runtime_claim,
                expected_step_kind="SIGNAL_AND_FORECAST",
            )
            receipt = uow.receipts.start(
                receipt_id=identities.inference.receipt_id,
                command_kind="PRODUCE_MODEL_SIGNAL_AND_FORECAST",
                scope_id=(
                    f"{signal_inputs.decision_run_id}:"
                    f"{signal_inputs.strategy_version.strategy_version_id}:"
                    f"{prepared.model_version_id}"
                ),
                idempotency_key=context.idempotency_key,
                request_hash=request_hash,
            )
            if not receipt.is_new:
                return self._replay_in_transaction(
                    uow,
                    receipt,
                    prepared.model_version_id,
                    runtime_claim,
                    request_hash=request_hash,
                )
            uow.inference.lock_identity(
                signal_inputs.decision_run_id,
                signal_inputs.strategy_version.strategy_version_id,
            )
            uow.dependencies.lock_and_revalidate(prepared.inference)
            uow.model_forecasts.lock_and_revalidate(prepared)
            uow.artifacts.require_exact(prepared.fitted_model_artifact, lock=True)
            recorded_at = uow.inference.authoritative_recorded_at()
            signal = build_signal_authority(
                signal_group_id=identities.inference.signal_group_id,
                prepared=signal_inputs,
                request_identity=context.idempotency_key,
                request_sha256=request_hash,
                command_receipt_id=receipt.receipt_id,
                recorded_at=recorded_at,
                signal_id_factory=identities.inference.signal_id,
                binding_id_factory=identities.inference.binding_id,
            )
            predictions = {
                item.commitment_id: item for item in prepared.predictions
            }

            def prediction(signal_item, commitment):
                item = predictions[commitment.commitment_id]
                if signal_item.status is not SignalStatus.PRESENT:
                    return (
                        ForecastStatus.NOT_ESTIMABLE,
                        "SIGNAL_NOT_PRESENT",
                        None,
                    )
                return (
                    ForecastStatus(item.state.value),
                    item.reason_code,
                    item.point_estimate,
                )

            forecast = build_forecast_authority(
                forecast_group_id=identities.inference.forecast_group_id,
                prepared=PreparedForecastInputs(
                    decision_run_id=signal_inputs.decision_run_id,
                    strategy_version=signal_inputs.strategy_version,
                    signal_authority=signal,
                    commitments=prepared.inference.commitments,
                ),
                request_identity=context.idempotency_key,
                request_sha256=request_hash,
                command_receipt_id=receipt.receipt_id,
                recorded_at=recorded_at,
                forecast_id_factory=identities.inference.forecast_id,
                estimate_id_factory=identities.inference.estimate_id,
                prediction_factory=prediction,
            )
            record = uow.inference.insert(signal, forecast)
            bindings = tuple(
                _binding_plan(
                    prepared,
                    forecast,
                    item,
                    identities.binding_ids[item.commitment.commitment_id],
                )
                for item in forecast.forecasts
            )
            uow.model_forecasts.insert(bindings)
            inference_check = uow.inference.reconcile(
                signal.signal_group_id,
                forecast.forecast_group_id,
                lock=True,
            )
            model_check = uow.model_forecasts.reconcile(
                forecast.forecast_group_id,
                prepared.model_version_id,
                lock=True,
            )
            expected_roster = canonical_json_sha256(
                tuple(
                    {
                        "content_sha256": str(item.content_sha256),
                        "forecast_model_binding_id": (
                            item.forecast_model_binding_id
                        ),
                        "ordinal": ordinal,
                    }
                    for ordinal, item in enumerate(bindings, start=1)
                )
            )
            if (
                not inference_check.matched
                or not model_check.matched
                or model_check.binding_count != forecast.forecast_count
                or model_check.binding_roster_sha256 != expected_roster
            ):
                raise InferenceAuthorityIntegrityError(
                    "Model Signal/Forecast relational closure did not reconcile"
                )
            result_hash = _model_result_hash(
                record,
                prepared.model_version_id,
                model_check.binding_count,
                model_check.binding_roster_sha256,
            )
            uow.receipts.succeed(
                receipt_id=receipt.receipt_id,
                aggregate_kind="MODEL_SIGNAL_FORECAST_AUTHORITY",
                aggregate_id=str(signal.signal_group_id),
                aggregate_version=1,
                result_hash=result_hash,
                runtime_claim=runtime_claim,
            )
            uow.audit.append(
                audit_event_id=identities.inference.audit_event_id,
                receipt_id=receipt.receipt_id,
                actor_type=context.actor_type.value,
                actor_id=context.actor_id,
                aggregate_kind="MODEL_SIGNAL_FORECAST_AUTHORITY",
                aggregate_id=str(signal.signal_group_id),
                action="MODEL_SIGNAL_AND_FORECAST_PRODUCED",
                reason_code=context.reason_code,
                before_version=None,
                after_version=1,
                runtime_claim=runtime_claim,
            )
            uow.runtime_finalization.succeed(
                runtime_claim,
                receipt_id=receipt.receipt_id,
                result_hash=result_hash,
            )
            uow.commit()
            return _model_result(
                record,
                prepared.model_version_id,
                model_check.binding_count,
                model_check.binding_roster_sha256,
                result_hash=result_hash,
                replayed=False,
            )

    def _replay_in_transaction(
        self,
        uow: InferenceUnitOfWork,
        receipt: ReceiptRecord,
        model_version_id: UUID,
        runtime_claim: AttemptClaim,
        *,
        request_hash: str,
    ) -> ProduceModelForecastResult:
        _require_succeeded(receipt)
        if receipt.request_hash != request_hash:
            raise IdempotencyKeyReusedError("Model Forecast replay inputs differ")
        assert receipt.result_aggregate_id is not None
        assert receipt.result_hash is not None
        signal_group_id = UUID(receipt.result_aggregate_id)
        record = uow.inference.record(
            signal_group_id,
            uow.inference.forecast_group_for_signal(signal_group_id, lock=False),
            lock=False,
        )
        reconciliation = uow.model_forecasts.reconcile(
            record.forecast_group_id,
            model_version_id,
            lock=False,
        )
        result_hash = _model_result_hash(
            record,
            model_version_id,
            reconciliation.binding_count,
            reconciliation.binding_roster_sha256,
        )
        if not reconciliation.matched or result_hash != receipt.result_hash:
            raise InferenceAuthorityIntegrityError(
                "Model Forecast receipt and Authority differ"
            )
        uow.runtime_finalization.succeed(
            runtime_claim,
            receipt_id=receipt.receipt_id,
            result_hash=receipt.result_hash,
        )
        uow.commit()
        return _model_result(
            record,
            model_version_id,
            reconciliation.binding_count,
            reconciliation.binding_roster_sha256,
            result_hash=result_hash,
            replayed=True,
        )

    def _external_replay(
        self,
        record,
        model_version_id: UUID,
    ) -> ProduceModelForecastResult:
        summary = self._model_queries.summary(record.forecast_group_id)
        if (
            summary is None
            or summary.model_version_id != model_version_id
            or summary.binding_count != record.forecast_count
        ):
            raise InferenceAuthorityIntegrityError(
                "Model Forecast replay binding roster is incomplete"
            )
        result_hash = _model_result_hash(
            record,
            model_version_id,
            summary.binding_count,
            summary.binding_roster_sha256,
        )
        if result_hash != summary.receipt_result_hash:
            raise InferenceAuthorityIntegrityError(
                "Model Forecast receipt and Authority differ"
            )
        return _model_result(
            record,
            model_version_id,
            summary.binding_count,
            summary.binding_roster_sha256,
            result_hash=result_hash,
            replayed=True,
        )


@dataclass(frozen=True, slots=True)
class _ModelForecastIdentities:
    inference: _InferenceIdentities
    binding_ids: dict[UUID, UUID]

    @classmethod
    def create(
        cls,
        prepared: PreparedModelForecastInputs,
        factory: Callable[[], UUID],
    ) -> _ModelForecastIdentities:
        return cls(
            inference=_InferenceIdentities.create(prepared.inference, factory),
            binding_ids={
                item.commitment_id: factory() for item in prepared.predictions
            },
        )


def _binding_plan(prepared, authority, forecast, binding_id) -> ForecastModelBindingPlan:
    if len(forecast.estimates) != 1:
        raise InferenceAuthorityIntegrityError(
            "Model Forecast requires exactly one estimate"
        )
    estimate = forecast.estimates[0]
    prediction = next(
        item
        for item in prepared.predictions
        if item.commitment_id == forecast.commitment.commitment_id
    )
    state = (
        ModelPredictionState.AVAILABLE
        if forecast.status is ForecastStatus.AVAILABLE
        else ModelPredictionState.NOT_ESTIMABLE
    )
    return ForecastModelBindingPlan(
        forecast_model_binding_id=binding_id,
        forecast_id=forecast.forecast_id,
        forecast_group_id=authority.forecast_group_id,
        forecast_estimate_id=estimate.forecast_estimate_id,
        decision_run_id=prepared.inference.signal_inputs.decision_run_id,
        strategy_version_id=(
            prepared.inference.signal_inputs.strategy_version.strategy_version_id
        ),
        commitment_id=forecast.commitment.commitment_id,
        target_metric_definition_id=estimate.rule.target_metric_definition_id,
        forecast_estimate_content_sha256=estimate.content_sha256,
        dataset_id=prepared.dataset_id,
        exploratory_backtest_run_id=prepared.exploratory_backtest_run_id,
        exploratory_backtest_arm_id=prepared.exploratory_backtest_arm_id,
        exploratory_backtest_fold_id=prepared.exploratory_backtest_fold_id,
        exploratory_backtest_fold_session_id=(
            prepared.exploratory_backtest_fold_session_id
        ),
        inference_fold_ordinal=prepared.inference_fold_ordinal,
        model_version_id=prepared.model_version_id,
        model_id=prepared.model_id,
        model_training_run_id=prepared.model_training_run_id,
        training_fold_id=prepared.training_fold_id,
        training_fold_ordinal=prepared.training_fold_ordinal,
        model_version_sha256=prepared.model_version_sha256,
        fitted_model_artifact_id=prepared.fitted_model_artifact.artifact_id,
        fitted_model_content_sha256=(
            prepared.fitted_model_artifact.content_sha256
        ),
        fitted_model_size_bytes=prepared.fitted_model_artifact.size_bytes,
        feature_vector_sha256=prediction.feature_vector_sha256,
        prediction_state=state,
        reason_code=forecast.reason_code,
        point_estimate=estimate.point_estimate,
        model_registered_at=prepared.model_registered_at,
        forecast_recorded_at=authority.recorded_at,
    )


def _model_result_hash(
    record,
    model_version_id: UUID,
    binding_count: int,
    binding_roster_sha256: str,
) -> str:
    return canonical_json_sha256(
        {
            "binding_count": binding_count,
            "binding_roster_sha256": binding_roster_sha256,
            "inference_sha256": _record_hash(record),
            "model_version_id": model_version_id,
        }
    )


def _model_result(
    record,
    model_version_id: UUID,
    binding_count: int,
    binding_roster_sha256: str,
    *,
    result_hash: str,
    replayed: bool,
) -> ProduceModelForecastResult:
    return ProduceModelForecastResult(
        inference=_result(record, replayed=replayed),
        model_version_id=model_version_id,
        binding_count=binding_count,
        binding_roster_sha256=binding_roster_sha256,
        result_hash=result_hash,
        replayed=replayed,
    )


__all__ = ["ModelForecastCommands", "ProduceModelForecastResult"]
