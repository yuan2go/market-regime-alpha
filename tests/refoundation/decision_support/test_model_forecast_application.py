from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any
from dataclasses import replace

import pytest

from market_regime_alpha.decision_support.application import ModelForecastCommands
from market_regime_alpha.decision_support.domain import (
    DecisionArtifactBinding,
    ModelForecastPrediction,
    ModelPredictionState,
)
from market_regime_alpha.decision_support.ports import (
    ModelForecastBindingSummary,
    ModelForecastReconciliation,
    PreparedModelForecastInputs,
)
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.runtime.errors import IdempotencyKeyReusedError
from tests.refoundation.decision_support.test_decision_domain import _uuid
from tests.refoundation.decision_support.test_wp13_strategy_inference_application import (
    _Artifacts,
    _Audit,
    _Dependencies,
    _Inference,
    _InferenceQuery,
    _Receipts,
    _Runtime,
    _claim,
    _context,
    _prepared,
)
from tests.refoundation.decision_support.test_wp13_strategy_inference_domain import (
    RECORDED_AT,
)


def _model_prepared() -> PreparedModelForecastInputs:
    inference = _prepared()
    return PreparedModelForecastInputs(
        inference=inference,
        dataset_id=_uuid(4000),
        exploratory_backtest_run_id=_uuid(4001),
        exploratory_backtest_arm_id=_uuid(4002),
        exploratory_backtest_fold_id=_uuid(4003),
        exploratory_backtest_fold_session_id=_uuid(4004),
        inference_fold_ordinal=2,
        model_version_id=_uuid(4005),
        model_id=_uuid(4006),
        model_training_run_id=_uuid(4007),
        training_fold_id=_uuid(4008),
        training_fold_ordinal=1,
        model_version_sha256="a" * 64,
        fitted_model_artifact=DecisionArtifactBinding(_uuid(4009), "b" * 64, 10),
        model_registered_at=RECORDED_AT - timedelta(seconds=1),
        target_metric_definition_id=(
            inference.signal_inputs.strategy_version.forecast_rules[0]
            .target_metric_definition_id
        ),
        predictions=tuple(
            ModelForecastPrediction(
                candidate_id=item.candidate_id,
                commitment_id=item.commitment_id,
                dataset_id=_uuid(4000),
                feature_vector_sha256=format(4100 + ordinal, "064x"),
                state=ModelPredictionState.AVAILABLE,
                reason_code="MODEL_ESTIMATE_AVAILABLE",
                point_estimate=Decimal(ordinal) / Decimal("100"),
            )
            for ordinal, item in enumerate(inference.commitments, start=1)
        ),
    )


class _Preparation:
    def __init__(self, prepared: PreparedModelForecastInputs) -> None:
        self.prepared = prepared
        self.calls = 0

    def prepare(self, decision_run_id, strategy_version_id, model_version_id):
        self.calls += 1
        assert decision_run_id == self.prepared.inference.signal_inputs.decision_run_id
        assert model_version_id == self.prepared.model_version_id
        return self.prepared


class _ModelForecasts:
    def __init__(self, state: dict[str, Any]) -> None:
        self.state = state

    def lock_and_revalidate(self, prepared):
        self.state.setdefault("order", []).append("model_dependencies")

    def insert(self, bindings):
        self.state["model_bindings"] = bindings

    def reconcile(self, forecast_group_id, model_version_id, *, lock):
        del lock
        bindings = self.state["model_bindings"]
        roster = canonical_json_sha256(
            tuple(
                {
                    "content_sha256": str(item.content_sha256),
                    "forecast_model_binding_id": item.forecast_model_binding_id,
                    "ordinal": ordinal,
                }
                for ordinal, item in enumerate(bindings, start=1)
            )
        )
        return ModelForecastReconciliation(
            forecast_group_id=forecast_group_id,
            model_version_id=model_version_id,
            forecast_count=len(bindings),
            binding_count=len(bindings),
            binding_roster_sha256=roster,
            matched=True,
        )


class _InferenceWithAuthority(_Inference):
    def insert(self, signal, forecast):
        self.state["signal_authority"] = signal
        self.state["forecast_authority"] = forecast
        return super().insert(signal, forecast)


class _Uow:
    def __init__(self, state, query) -> None:
        self.state = state
        self.inference = _InferenceWithAuthority(state, query)
        self.dependencies = _Dependencies(state)
        self.model_forecasts = _ModelForecasts(state)
        self.artifacts = _Artifacts()
        self.receipts = _Receipts(state)
        self.audit = _Audit(state)
        self.runtime_finalization = _Runtime(state)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def commit(self):
        self.state["commits"] = self.state.get("commits", 0) + 1


class _UowProvider:
    def __init__(self, state, query) -> None:
        self.state = state
        self.query = query

    def __call__(self):
        return _Uow(self.state, self.query)


class _ModelQueries:
    def __init__(self, state) -> None:
        self.state = state

    def summary(self, forecast_group_id):
        bindings = self.state.get("model_bindings")
        receipt = self.state.get("receipt")
        if not bindings or not receipt:
            return None
        roster = canonical_json_sha256(
            tuple(
                {
                    "content_sha256": str(item.content_sha256),
                    "forecast_model_binding_id": item.forecast_model_binding_id,
                    "ordinal": ordinal,
                }
                for ordinal, item in enumerate(bindings, start=1)
            )
        )
        return ModelForecastBindingSummary(
            forecast_group_id=forecast_group_id,
            model_version_id=bindings[0].model_version_id,
            binding_count=len(bindings),
            binding_roster_sha256=roster,
            receipt_result_hash=receipt["result_hash"],
        )


def test_model_forecast_is_one_fence_first_complete_transaction_and_replays() -> None:
    prepared = _model_prepared()
    state: dict[str, Any] = {}
    inference_queries = _InferenceQuery()
    preparation = _Preparation(prepared)
    identities = iter(range(4200, 4500))
    commands = ModelForecastCommands(
        preparation,
        _UowProvider(state, inference_queries),
        inference_queries,
        _ModelQueries(state),
        id_factory=lambda: _uuid(next(identities)),
    )
    context = _context("produce-model-inference-1")

    first = commands.produce(
        prepared.inference.signal_inputs.decision_run_id,
        prepared.inference.signal_inputs.strategy_version.strategy_version_id,
        prepared.model_version_id,
        context,
        runtime_claim=_claim(),
    )
    replay = commands.produce(
        prepared.inference.signal_inputs.decision_run_id,
        prepared.inference.signal_inputs.strategy_version.strategy_version_id,
        prepared.model_version_id,
        context,
        runtime_claim=_claim(),
    )

    assert replay == first.as_replay()
    assert first.binding_count == first.inference.forecast_count == 2
    assert preparation.calls == 1
    assert state["order"][:3] == ["fence", "inference_lock", "dependencies"]
    authority = state["forecast_authority"]
    assert [item.estimates[0].point_estimate for item in authority.forecasts] == [
        Decimal("0.010000000000000000"),
        Decimal("0.020000000000000000"),
    ]
    assert all(item.reason_code == "MODEL_ESTIMATE_AVAILABLE" for item in authority.forecasts)
    assert all(item.estimates[0].lower_bound == item.estimates[0].upper_bound for item in authority.forecasts)
    with pytest.raises(IdempotencyKeyReusedError):
        commands.produce(
            prepared.inference.signal_inputs.decision_run_id,
            prepared.inference.signal_inputs.strategy_version.strategy_version_id,
            _uuid(9999),
            context,
            runtime_claim=_claim(),
        )


def test_model_forecast_retains_not_estimable_candidate() -> None:
    original = _model_prepared()
    prepared = replace(
        original,
        predictions=(
            replace(
                original.predictions[0],
                state=ModelPredictionState.NOT_ESTIMABLE,
                reason_code="FEATURE_MISSING",
                point_estimate=None,
            ),
            original.predictions[1],
        ),
    )
    state: dict[str, Any] = {}
    inference_queries = _InferenceQuery()
    identities = iter(range(4600, 4900))
    result = ModelForecastCommands(
        _Preparation(prepared),
        _UowProvider(state, inference_queries),
        inference_queries,
        _ModelQueries(state),
        id_factory=lambda: _uuid(next(identities)),
    ).produce(
        prepared.inference.signal_inputs.decision_run_id,
        prepared.inference.signal_inputs.strategy_version.strategy_version_id,
        prepared.model_version_id,
        _context("produce-model-inference-not-estimable"),
        runtime_claim=_claim(),
    )

    assert result.binding_count == 2
    forecasts = state["forecast_authority"].forecasts
    assert forecasts[0].status.value == "NOT_ESTIMABLE"
    assert forecasts[0].estimates[0].point_estimate is None
    assert state["model_bindings"][0].reason_code == "FEATURE_MISSING"
