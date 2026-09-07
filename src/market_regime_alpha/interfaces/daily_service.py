"""One sequential daily consumer called by CONTINUOUS_RESEARCH's existing tick."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from hashlib import sha256
from typing import TYPE_CHECKING, Any, Callable
from uuid import uuid5

from market_regime_alpha.infrastructure.postgres.prospective_operation_session import daily_research_admission
from market_regime_alpha.interfaces.daily_collection import DailyCollectionPlan, collect_daily
from market_regime_alpha.interfaces.daily_research import DailyResearchOperations, decode_daily_plan, encode_daily_plan
from market_regime_alpha.research_qualification.domain.daily_prediction import DailyPredictionPlan
from market_regime_alpha.research_qualification.domain.daily_inputs import DailyInputState
from market_regime_alpha.runtime.errors import ArtifactIntegrityError

if TYPE_CHECKING:
    from market_regime_alpha.bootstrap import TargetApplication
    from market_regime_alpha.market.ports import MarketProvider


_TERMINAL_INPUT = {DailyInputState.AVAILABLE, DailyInputState.SUSPENDED, DailyInputState.EXCLUDED}
_MAX_ROUNDS = 16
_POLL_INTERVAL = timedelta(minutes=30)
_OUTCOME_GRACE = timedelta(hours=8)


def current_daily_plan(app: TargetApplication, template: DailyPredictionPlan) -> DailyPredictionPlan:
    input_session, target_session, now = app.daily_prediction_reads.current_sessions()
    identity = uuid5(template.experimental_model_use_id, "daily:" + str(input_session) + ":" + str(target_session))
    frozen = app.daily_prediction_reads.run_plan_content(uuid5(identity, "prediction-runtime"))
    if frozen is None:
        frozen = app.daily_prediction_reads.run_plan_content(uuid5(identity, "abstention-runtime"))
    if frozen is not None:
        plan = decode_daily_plan(frozen)
        _same_template(plan, template)
        if (plan.prediction_id, plan.input_session_id, plan.target_session_id) != (identity, input_session, target_session):
            raise ArtifactIntegrityError("daily frozen Run and input/target identities differ")
        return plan
    plan = replace(
        template,
        prediction_id=identity,
        input_session_id=input_session,
        target_session_id=target_session,
        input_cutoff=now,
        decision_time=now,
        input_content_sha256="0" * 64,
    )
    ready = app.daily_prediction_reads.observe(plan)
    return replace(plan, input_content_sha256=ready.content_sha256)


def _same_template(plan: DailyPredictionPlan, template: DailyPredictionPlan) -> None:
    changed = {name for name in plan.__dataclass_fields__ if getattr(plan, name) != getattr(template, name)}
    if changed - {"prediction_id", "input_session_id", "target_session_id", "input_cutoff", "decision_time", "input_content_sha256"}:
        raise ArtifactIntegrityError("DAILY_FROZEN_CONFIGURATION_CHANGED")


def daily_tick(
    app: TargetApplication,
    template: DailyPredictionPlan,
    provider: MarketProvider,
    *,
    worker_id: str,
    maximum_steps: int,
    before_action: Callable[[], None],
) -> dict[str, Any]:
    """No sleeping, dates inferred by neither process nor supervisor; DB clock/calendar decide."""
    before_action()
    reads = app.daily_prediction_reads
    reads.validate_configuration(template)
    completed = []
    # Durable pending work was declared at prediction publication. Inspect future
    # items honestly, then let the existing Runtime claim only a mature target.
    for content in reads.pending_outcome_plans(template.experimental_model_use_id):
        plan = decode_daily_plan(content)
        _same_template(plan, template)
        ready = reads.ready(plan)
        now = reads.now()
        if now < ready.target_window_end:
            completed.append({"prediction_id": plan.prediction_id, "state": "PENDING", "due_at": ready.target_window_end})
            continue
        members = reads.target_price_members(plan)
        if not all(m.state in _TERMINAL_INPUT for m in members) and now < ready.target_window_end + _OUTCOME_GRACE:
            result = _collection(app, plan, "outcome", provider, worker_id, maximum_steps, before_action)
            if result["state"] != "BUDGET_EXHAUSTED":
                return {"state": "OUTCOME_DATA_PENDING", "collection": result, "pending": completed}
        with daily_research_admission(
            prediction_id=plan.prediction_id, code_sha=plan.code_sha, config_sha256=sha256(encode_daily_plan(plan)).hexdigest()
        ):
            settlement = DailyResearchOperations(app, reads, before_action=before_action).settle_and_evaluate(
                plan, worker_id=worker_id, maximum_steps=maximum_steps
            )
        return {"state": "OUTCOME_PROGRESS", "result": settlement, "pending": completed}
    plan = current_daily_plan(app, template)
    if reads.run_plan_content(uuid5(plan.prediction_id, "abstention-runtime")) is not None:
        rounds=reads.collection_rounds(plan.prediction_id,'input')
        if rounds and rounds[-1][1] in {'QUEUED','RUNNING'}:
            _collection(app,plan,'input',provider,worker_id,min(maximum_steps,2),before_action)
        return {"state": "ABSTAINED", "prediction_id": plan.prediction_id, "pending": completed}
    existing = reads.run_plan_content(plan.runtime_run_id)
    ready = reads.ready(plan)
    if existing is None:
        if not reads.model_use_available(plan):
            return _abstain(app, plan, "MODEL_USE_UNAVAILABLE", worker_id, before_action)
        if ready.state == "MISSED_CUTOFF":
            rounds = reads.collection_rounds(plan.prediction_id, "input")
            if rounds and rounds[-1][1] in {"QUEUED", "RUNNING"}:
                _collection(app, plan, "input", provider, worker_id, min(maximum_steps, 2), before_action)
            return _abstain(app, plan, "MISSED_PUBLICATION_CUTOFF", worker_id, before_action)
        if not all(m.state in _TERMINAL_INPUT for m in ready.members):
            result = _collection(app, plan, "input", provider, worker_id, maximum_steps, before_action)
            if result["state"] != "BUDGET_EXHAUSTED":
                return {"state": "DATA_PENDING", "collection": result, "pending": completed}
            if ready.state not in {"READY", "PARTIAL"}:
                return _abstain(app, plan, "DATA_READINESS_BUDGET_EXHAUSTED", worker_id, before_action)
        if ready.feature_ready_count == 0:
            return _abstain(app, plan, "NO_FEATURE_READY_MEMBERS", worker_id, before_action)
    with daily_research_admission(
        prediction_id=plan.prediction_id, code_sha=plan.code_sha, config_sha256=sha256(encode_daily_plan(plan)).hexdigest()
    ):
        execution = DailyResearchOperations(app, reads, before_action=before_action).execute(
            plan, worker_id=worker_id, maximum_steps=min(maximum_steps, 9)
        )
    return {"state": "PREDICTION_PROGRESS", "result": execution, "pending": completed}


def _collection(
    app: TargetApplication,
    plan: DailyPredictionPlan,
    phase: str,
    provider: MarketProvider,
    worker: str,
    budget: int,
    before_action: Callable[[], None],
) -> dict[str, Any]:
    rounds = app.daily_prediction_reads.collection_rounds(plan.prediction_id, phase)
    now = app.daily_prediction_reads.now()
    if rounds and rounds[-1][1] not in {"QUEUED", "RUNNING", "SUCCEEDED"}:
        return {"state": "RECOVERY_REQUIRED", "run_state": rounds[-1][1], "round": rounds[-1][0]}
    if rounds and rounds[-1][1] in {"QUEUED", "RUNNING"}:
        collection = DailyCollectionPlan.decode(rounds[-1][3])
        _same_template(collection.prediction, plan)
        if collection.run_id != uuid5(plan.prediction_id, phase + "-collection:" + str(rounds[-1][0])):
            raise ArtifactIntegrityError("daily collection Run/config identity differs")
    else:
        if rounds and rounds[-1][0] >= _MAX_ROUNDS:
            return {"state": "BUDGET_EXHAUSTED", "rounds": _MAX_ROUNDS}
        if rounds and now < rounds[-1][2] + _POLL_INTERVAL:
            return {"state": "DATA_NOT_READY", "next_observation_at": rounds[-1][2] + _POLL_INTERVAL}
        collection = DailyCollectionPlan(plan, phase, len(rounds) + 1, now)
    with daily_research_admission(
        prediction_id=plan.prediction_id,
        code_sha=plan.code_sha,
        config_sha256=collection.content_sha256,
        collection_phase=phase,
        collection_round=collection.round,
    ):
        result = collect_daily(app, collection, provider, worker_id=worker, maximum_steps=budget, before_action=before_action)
    return {"state": "COLLECTION_PROGRESS", "round": collection.round, "result": result}


def _abstain(
    app: TargetApplication, plan: DailyPredictionPlan, reason: str, worker: str, before_action: Callable[[], None]
) -> dict[str, Any]:
    with daily_research_admission(
        prediction_id=plan.prediction_id, code_sha=plan.code_sha, config_sha256=sha256(encode_daily_plan(plan)).hexdigest()
    ):
        return DailyResearchOperations(app, app.daily_prediction_reads, before_action=before_action).abstain(
            plan, reason=reason, worker_id=worker
        )
