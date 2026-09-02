from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from market_regime_alpha.decision_support.application import (
    InferenceCommands,
    StrategyCommands,
)
from market_regime_alpha.decision_support.domain import (
    PreparedForecastCommitment,
    PreparedInferenceInputs,
    PreparedSignalInputs,
)
from market_regime_alpha.decision_support.ports import (
    InferenceRecord,
    InferenceReconciliation,
    StrategyReconciliation,
    StrategyVersionRecord,
)
from market_regime_alpha.runtime.application import ActorType, CommandContext
from market_regime_alpha.runtime.errors import IdempotencyKeyReusedError
from market_regime_alpha.runtime.ports import AttemptClaim, ReceiptRecord
from tests.refoundation.decision_support.test_decision_domain import _uuid
from tests.refoundation.decision_support.test_wp13_strategy_inference_domain import (
    DECISION_TIME,
    RECORDED_AT,
    _candidate,
    _strategy,
)


def _context(key: str) -> CommandContext:
    return CommandContext(
        idempotency_key=key,
        actor_type=ActorType.WORKER,
        actor_id="decision-worker",
        reason_code="WP13_DECISION_SUPPORT",
    )


def _claim() -> AttemptClaim:
    return AttemptClaim(
        attempt_id=_uuid(3000),
        run_id=_uuid(3001),
        step_id=_uuid(3002),
        step_key="signal_and_forecast",
        attempt_no=1,
        fence_token=1,
        lease_owner="decision-worker",
        lease_until=datetime(2026, 9, 1, 7, 10, tzinfo=UTC),
    )


class _Receipts:
    def __init__(self, state: dict[str, Any]) -> None:
        self.state = state

    def start(self, **kwargs):
        existing = self.state.get("receipt")
        if existing is not None:
            return ReceiptRecord(**existing, is_new=False)
        self.state["pending_receipt"] = kwargs
        return ReceiptRecord(
            receipt_id=kwargs["receipt_id"],
            status="PENDING",
            request_hash=kwargs["request_hash"],
            result_aggregate_kind=None,
            result_aggregate_id=None,
            result_aggregate_version=None,
            result_hash=None,
            error_code=None,
            is_new=True,
        )

    def succeed(self, **kwargs):
        pending = self.state["pending_receipt"]
        self.state["receipt"] = {
            "receipt_id": kwargs["receipt_id"],
            "status": "SUCCEEDED",
            "request_hash": pending["request_hash"],
            "result_aggregate_kind": kwargs["aggregate_kind"],
            "result_aggregate_id": kwargs["aggregate_id"],
            "result_aggregate_version": kwargs["aggregate_version"],
            "result_hash": kwargs["result_hash"],
            "error_code": None,
        }

    def fail(self, **kwargs):
        self.state["failed"] = kwargs


class _Audit:
    def __init__(self, state):
        self.state = state

    def append(self, **kwargs):
        self.state.setdefault("audit", []).append(kwargs)


class _Artifacts:
    def require_exact(self, binding, *, lock):
        assert lock
        return binding


class _StrategyQuery:
    def __init__(self) -> None:
        self.records: dict[tuple[object, str], StrategyVersionRecord] = {}

    def find_request(self, strategy_id, request_identity):
        return self.records.get((strategy_id, request_identity))


class _Strategies:
    def __init__(self, state, query):
        self.state = state
        self.query = query

    def lock_identity(self, strategy_id):
        self.state.setdefault("order", []).append("strategy_lock")

    def register(self, plan, *, request_identity, request_sha256):
        record = StrategyVersionRecord(
            strategy_id=plan.strategy.strategy_id,
            strategy_version_id=plan.strategy_version_id,
            version=plan.version,
            context_requirement_count=plan.context_requirement_count,
            forecast_rule_count=plan.forecast_rule_count,
            content_sha256=plan.content_sha256,
            request_identity=request_identity,
            request_sha256=request_sha256,
            frozen_at=RECORDED_AT,
            receipt_id=self.state["pending_receipt"]["receipt_id"],
        )
        self.query.records[(record.strategy_id, request_identity)] = record
        self.state["strategy_record"] = record
        return record

    def record(self, strategy_version_id, *, lock):
        del lock
        record = self.state["strategy_record"]
        assert record.strategy_version_id == strategy_version_id
        return record

    def reconcile(self, strategy_version_id, *, lock):
        assert lock
        plan = self.state["strategy_plan"]
        assert plan.strategy_version_id == strategy_version_id
        return StrategyReconciliation(
            strategy_version_id=strategy_version_id,
            context_requirement_count=plan.context_requirement_count,
            signal_rule_count=1,
            forecast_rule_count=plan.forecast_rule_count,
            context_requirement_roster_sha256=(
                plan.context_requirement_roster_sha256
            ),
            forecast_rule_roster_sha256=plan.forecast_rule_roster_sha256,
            matched=True,
        )


class _StrategyUow:
    def __init__(self, state, query):
        self.state = state
        self.strategies = _Strategies(state, query)
        self.artifacts = _Artifacts()
        self.receipts = _Receipts(state)
        self.audit = _Audit(state)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def commit(self):
        self.state["commits"] = self.state.get("commits", 0) + 1


class _StrategyUowProvider:
    def __init__(self, state, query):
        self.state = state
        self.query = query

    def __call__(self):
        return _StrategyUow(self.state, self.query)


def test_strategy_registration_freezes_complete_roster_and_exact_replay() -> None:
    plan = _strategy()
    state: dict[str, Any] = {"strategy_plan": plan}
    query = _StrategyQuery()
    identities = iter(range(3100, 3150))
    commands = StrategyCommands(
        _StrategyUowProvider(state, query),
        query,
        id_factory=lambda: _uuid(next(identities)),
    )
    context = _context("register-strategy-1")

    first = commands.register(plan, context)
    replay = commands.register(plan, context)

    assert replay == first.as_replay()
    assert first.context_requirement_count == 2
    assert first.forecast_rule_count == 1
    assert state["commits"] == 1
    with pytest.raises(IdempotencyKeyReusedError):
        commands.register(plan, CommandContext(
            idempotency_key=context.idempotency_key,
            actor_type=context.actor_type,
            actor_id="different-worker",
            reason_code=context.reason_code,
        ))


def _prepared() -> PreparedInferenceInputs:
    strategy = _strategy()
    candidates = (
        _candidate(strategy, 1, strategy.signal_rule.eligible_disposition),
        _candidate(strategy, 2, strategy.signal_rule.eligible_disposition),
    )
    signal = PreparedSignalInputs(
        decision_run_id=_uuid(3200),
        candidate_set_id=_uuid(3201),
        candidate_set_content_sha256="6" * 64,
        candidate_roster_sha256="7" * 64,
        decision_time=DECISION_TIME,
        strategy_version=strategy,
        candidates=candidates,
    )
    rule = strategy.forecast_rules[0]
    return PreparedInferenceInputs(
        signal_inputs=signal,
        commitments=tuple(
            PreparedForecastCommitment(
                commitment_id=_uuid(3210 + ordinal),
                candidate_id=candidate.candidate_id,
                instrument_id=candidate.instrument_id,
                target_definition_id=rule.target_definition_id,
                target_definition_sha256=rule.target_definition_sha256,
                target_checkpoint_id=rule.target_checkpoint_id,
                target_checkpoint_sha256=rule.target_checkpoint_sha256,
                commitment_content_sha256=format(3210 + ordinal, "064x"),
            )
            for ordinal, candidate in enumerate(candidates, start=1)
        ),
    )


class _Preparation:
    def __init__(self, prepared):
        self.prepared = prepared
        self.calls = 0

    def prepare(self, decision_run_id, strategy_version_id):
        self.calls += 1
        assert decision_run_id == self.prepared.signal_inputs.decision_run_id
        assert strategy_version_id == (
            self.prepared.signal_inputs.strategy_version.strategy_version_id
        )
        return self.prepared


class _InferenceQuery:
    def __init__(self) -> None:
        self.record: InferenceRecord | None = None

    def find_request(self, decision_run_id, strategy_version_id, request_identity):
        if self.record is None:
            return None
        if (
            self.record.decision_run_id,
            self.record.strategy_version_id,
            self.record.request_identity,
        ) == (decision_run_id, strategy_version_id, request_identity):
            return self.record
        return None


class _Runtime:
    def __init__(self, state):
        self.state = state

    def lock_live_for_step(self, claim, *, expected_step_kind):
        self.state.setdefault("order", []).append("fence")
        assert expected_step_kind == "SIGNAL_AND_FORECAST"

    def lock_live(self, claim):
        self.state.setdefault("order", []).append("fence")

    def succeed(self, claim, *, receipt_id, result_hash):
        self.state["runtime_success"] = (claim, receipt_id, result_hash)
        return 2, 2

    def fail(self, *args, **kwargs):
        raise AssertionError("failure path not expected")


class _Dependencies:
    def __init__(self, state):
        self.state = state

    def lock_and_revalidate(self, prepared):
        self.state.setdefault("order", []).append("dependencies")


class _Inference:
    def __init__(self, state, query):
        self.state = state
        self.query = query

    def lock_identity(self, decision_run_id, strategy_version_id):
        self.state.setdefault("order", []).append("inference_lock")

    def authoritative_recorded_at(self):
        return RECORDED_AT

    def insert(self, signal, forecast):
        record = InferenceRecord(
            decision_run_id=signal.decision_run_id,
            strategy_version_id=signal.strategy_version.strategy_version_id,
            signal_group_id=signal.signal_group_id,
            forecast_group_id=forecast.forecast_group_id,
            signal_count=signal.signal_count,
            forecast_count=forecast.forecast_count,
            context_binding_count=signal.context_binding_count,
            estimate_count=forecast.estimate_count,
            signal_content_sha256=signal.content_sha256,
            forecast_content_sha256=forecast.content_sha256,
            request_identity=signal.request_identity,
            request_sha256=signal.request_sha256,
            recorded_at=signal.recorded_at,
            receipt_id=signal.command_receipt_id,
        )
        self.query.record = record
        self.state["inference_record"] = record
        return record

    def record(self, signal_group_id, forecast_group_id, *, lock):
        del lock
        record = self.state["inference_record"]
        assert (record.signal_group_id, record.forecast_group_id) == (
            signal_group_id,
            forecast_group_id,
        )
        return record

    def forecast_group_for_signal(self, signal_group_id, *, lock):
        del lock
        record = self.state["inference_record"]
        assert record.signal_group_id == signal_group_id
        return record.forecast_group_id

    def reconcile(self, signal_group_id, forecast_group_id, *, lock):
        assert lock
        record = self.state["inference_record"]
        return InferenceReconciliation(
            signal_group_id=signal_group_id,
            forecast_group_id=forecast_group_id,
            signal_count=record.signal_count,
            context_binding_count=record.context_binding_count,
            forecast_count=record.forecast_count,
            estimate_count=record.estimate_count,
            matched=True,
        )


class _InferenceUow:
    def __init__(self, state, query):
        self.state = state
        self.inference = _Inference(state, query)
        self.dependencies = _Dependencies(state)
        self.receipts = _Receipts(state)
        self.audit = _Audit(state)
        self.runtime_finalization = _Runtime(state)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def commit(self):
        self.state["commits"] = self.state.get("commits", 0) + 1


class _InferenceUowProvider:
    def __init__(self, state, query):
        self.state = state
        self.query = query

    def __call__(self):
        return _InferenceUow(self.state, self.query)


def test_signal_and_forecast_are_one_fence_first_complete_transaction() -> None:
    prepared = _prepared()
    state: dict[str, Any] = {}
    query = _InferenceQuery()
    preparation = _Preparation(prepared)
    identities = iter(range(3300, 3500))
    commands = InferenceCommands(
        preparation,
        _InferenceUowProvider(state, query),
        query,
        id_factory=lambda: _uuid(next(identities)),
    )
    context = _context("produce-inference-1")

    first = commands.produce(
        prepared.signal_inputs.decision_run_id,
        prepared.signal_inputs.strategy_version.strategy_version_id,
        context,
        runtime_claim=_claim(),
    )
    replay = commands.produce(
        prepared.signal_inputs.decision_run_id,
        prepared.signal_inputs.strategy_version.strategy_version_id,
        context,
        runtime_claim=_claim(),
    )

    assert replay == first.as_replay()
    assert first.signal_count == 2
    assert first.context_binding_count == 4
    assert first.forecast_count == 2
    assert first.estimate_count == 2
    assert state["order"][0] == "fence"
    assert state["commits"] == 1
    assert preparation.calls == 1
    with pytest.raises(IdempotencyKeyReusedError):
        commands.produce(
            prepared.signal_inputs.decision_run_id,
            prepared.signal_inputs.strategy_version.strategy_version_id,
            CommandContext(
                idempotency_key=context.idempotency_key,
                actor_type=context.actor_type,
                actor_id="different-worker",
                reason_code=context.reason_code,
            ),
            runtime_claim=_claim(),
        )
