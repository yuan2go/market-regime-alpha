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
from market_regime_alpha.research_qualification.ports.daily_prediction import (
    DailyOutcomeWorkItem,
)
from market_regime_alpha.runtime.errors import (
    ArtifactIntegrityError,
    RuntimeNotFoundError,
    RuntimeStateConflictError,
)

if TYPE_CHECKING:
    from market_regime_alpha.bootstrap import TargetApplication
    from market_regime_alpha.interfaces.daily_delivery import DailyDeliveryAdapter
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


def _historical_outcome_plan(item: DailyOutcomeWorkItem) -> DailyPredictionPlan:
    """Authenticate one discovered Run from its own immutable plan, not today's template."""

    if item.plan_content is None:
        raise ArtifactIntegrityError(
            item.error_code or "DAILY_FROZEN_PLAN_UNAVAILABLE"
        )
    plan = decode_daily_plan(item.plan_content)
    config_sha256 = sha256(item.plan_content).hexdigest()
    expected_run_id = uuid5(plan.prediction_id, "outcome-evaluation-runtime")
    expected_schedule_id = uuid5(
        plan.experimental_model_use_id, "daily-outcome-schedule"
    )
    if (
        item.run_id != expected_run_id
        or item.schedule_id != expected_schedule_id
        or item.schedule_code
        != "daily-outcome-" + plan.experimental_model_use_id.hex
        or item.fire_key != "daily-outcome:" + str(plan.prediction_id)
        or item.parent_run_id != plan.runtime_run_id
        or item.code_sha != plan.code_sha
        or item.config_sha256 != config_sha256
        or item.plan_content != encode_daily_plan(plan)
    ):
        raise ArtifactIntegrityError("DAILY_OUTCOME_FROZEN_IDENTITY_CHANGED")
    return plan


def daily_tick(
    app: TargetApplication,
    template: DailyPredictionPlan,
    provider: MarketProvider,
    *,
    worker_id: str,
    maximum_steps: int,
    before_action: Callable[[], None],
    delivery_adapter: DailyDeliveryAdapter | None = None,
) -> dict[str, Any]:
    """No sleeping, dates inferred by neither process nor supervisor; DB clock/calendar decide."""
    before_action()
    reads = app.daily_prediction_reads

    def finish(payload: dict[str, Any]) -> dict[str, Any]:
        payload.setdefault(
            "delivery",
            {
                "state": (
                    "NOT_CONFIGURED"
                    if delivery_adapter is None
                    else "NOT_DUE"
                ),
                "channel": (
                    None
                    if delivery_adapter is None
                    else delivery_adapter.channel
                ),
                "delivery_attempted": False,
                "prediction_and_settlement_blocked": False,
            },
        )
        try:
            payload["health"] = reads.operational_health(template)
        except (AttributeError, RuntimeError, ValueError) as exc:
            payload["health"] = {
                "state": "HEALTH_QUERY_FAILED",
                "reason_code": type(exc).__name__,
            }
        return payload

    completed: list[dict[str, Any]] = []
    outcome_action: dict[str, Any] | None = None

    def finish_abstention(
        abstention_plan: DailyPredictionPlan, reason: str
    ) -> dict[str, Any]:
        payload = _abstain(
            app,
            abstention_plan,
            reason,
            worker_id,
            before_action,
        )
        payload["pending"] = completed
        return finish(payload)

    # Durable pending work was declared at prediction publication. Inspect future
    # items across every historical ModelUse, then claim at most one task per tick.
    for item in reads.outcome_work_items(limit=64):
        status: dict[str, Any] = {
            "run_id": item.run_id,
            "run_state": item.run_state,
        }
        if item.run_state in {"FAILED", "WAITING"}:
            completed.append(
                {
                    **status,
                    "state": "RECOVERY_REQUIRED",
                    "reason_code": item.error_code
                    or (
                        "EXTERNAL_EFFECT_RECONCILIATION_REQUIRED"
                        if item.run_state == "WAITING"
                        else "TERMINAL_FAILURE_REQUIRES_SUPERSESSION"
                    ),
                    "automatic_retry": False,
                }
            )
            continue
        try:
            plan = _historical_outcome_plan(item)
            reads.validate_configuration(plan)
            ready = reads.ready(plan)
        except (
            ArtifactIntegrityError,
            RuntimeNotFoundError,
            RuntimeStateConflictError,
            ValueError,
        ) as exc:
            completed.append(
                {
                    **status,
                    "state": "INTEGRITY_BLOCKED",
                    "reason_code": str(exc),
                    "automatic_retry": False,
                }
            )
            continue
        status["prediction_id"] = plan.prediction_id
        status["experimental_model_use_id"] = plan.experimental_model_use_id
        status["model_version_id"] = plan.model_version_id
        now = reads.now()
        if now < ready.target_window_end:
            completed.append(
                {
                    **status,
                    "state": "PENDING_MATURITY",
                    "due_at": ready.target_window_end,
                }
            )
            continue
        try:
            members = reads.target_price_members(plan)
        except (RuntimeError, ValueError) as exc:
            completed.append(
                {
                    **status,
                    "state": "OUTCOME_DATA_FAILED",
                    "reason_code": str(exc),
                }
            )
            continue
        if not all(m.state in _TERMINAL_INPUT for m in members) and now < ready.target_window_end + _OUTCOME_GRACE:
            if outcome_action is None:
                try:
                    result = _collection(
                        app,
                        plan,
                        "outcome",
                        provider,
                        worker_id,
                        maximum_steps,
                        before_action,
                    )
                except (RuntimeError, ValueError) as exc:
                    completed.append(
                        {
                            **status,
                            "state": "OUTCOME_DATA_FAILED",
                            "reason_code": str(exc),
                        }
                    )
                    continue
                completed.append(
                    {**status, "state": "OUTCOME_DATA_PENDING", "collection": result}
                )
                if result["state"] == "COLLECTION_PROGRESS":
                    outcome_action = completed[-1]
            else:
                completed.append({**status, "state": "OUTCOME_DATA_PENDING"})
            continue
        if outcome_action is not None:
            completed.append({**status, "state": "READY_FOR_SETTLEMENT"})
            continue
        try:
            with daily_research_admission(
                prediction_id=plan.prediction_id,
                code_sha=plan.code_sha,
                config_sha256=sha256(encode_daily_plan(plan)).hexdigest(),
            ):
                settlement = DailyResearchOperations(
                    app, reads, before_action=before_action
                ).settle_and_evaluate(
                    plan, worker_id=worker_id, maximum_steps=maximum_steps
                )
        except (RuntimeError, ValueError) as exc:
            completed.append(
                {
                    **status,
                    "state": "SETTLEMENT_FAILED",
                    "reason_code": str(exc),
                }
            )
            continue
        outcome_action = {**status, "state": "SETTLEMENT_PROGRESS", "result": settlement}
        completed.append(outcome_action)
    if outcome_action is not None:
        return finish({"state": "OUTCOME_PROGRESS", "outcomes": completed})
    try:
        reads.validate_configuration(template)
    except (
        ArtifactIntegrityError,
        RuntimeNotFoundError,
        RuntimeStateConflictError,
        ValueError,
    ) as exc:
        return finish(
            {
                "state": "PREDICTION_CONFIGURATION_BLOCKED",
                "reason_code": str(exc),
                "pending": completed,
            }
        )
    elapsed = reads.missing_elapsed_session_pairs(template)
    if elapsed:
        input_session, target_session = elapsed[0]
        now = reads.now()
        missed = replace(template,
            prediction_id=uuid5(template.experimental_model_use_id,"daily:"+str(input_session)+":"+str(target_session)),
            input_session_id=input_session,target_session_id=target_session,
            input_cutoff=now,decision_time=now,input_content_sha256="0"*64)
        missed = replace(missed,input_content_sha256=reads.observe(missed).content_sha256)
        return finish_abstention(
            missed,
            "PROCESS_DOWNTIME_MISSED_PUBLICATION",
        )
    try:
        plan = current_daily_plan(app, template)
    except RuntimeStateConflictError as exc:
        if str(exc) != (
            "RUNTIME_STATE_CONFLICT: DAILY_CALENDAR_COVERAGE_INCOMPLETE"
        ):
            raise
        return finish({
            "state": "CALENDAR_COVERAGE_INCOMPLETE",
            "reason_code": str(exc),
            "pending": completed,
        })
    if reads.run_plan_content(uuid5(plan.prediction_id, "abstention-runtime")) is not None:
        for phase in ("population", "input"):
            rounds=reads.collection_rounds(plan.prediction_id,phase)
            if rounds and rounds[-1][1] in {'QUEUED','RUNNING'}:
                _collection(app,plan,phase,provider,worker_id,min(maximum_steps,2),before_action)
        reason = DailyResearchOperations(
            app, reads, before_action=before_action
        ).frozen_abstention_reason(plan)
        return finish_abstention(plan, reason)
    existing = reads.run_plan_content(plan.runtime_run_id)
    ready = reads.ready(plan)
    if existing is None:
        if not reads.model_use_available(plan):
            return finish_abstention(
                plan,
                "MODEL_USE_UNAVAILABLE",
            )
        if ready.state == "MISSED_CUTOFF":
            for phase in ("population", "input"):
                rounds = reads.collection_rounds(plan.prediction_id, phase)
                if rounds and rounds[-1][1] in {"QUEUED", "RUNNING"}:
                    _collection(app, plan, phase, provider, worker_id, min(maximum_steps, 2), before_action)
            return finish_abstention(
                plan,
                "MISSED_PUBLICATION_CUTOFF",
            )
        if not reads.population_source_ready(plan):
            result = _collection(app, plan, "population", provider, worker_id, maximum_steps, before_action)
            if result["state"] == "BUDGET_EXHAUSTED":
                return finish_abstention(
                    plan,
                    "POPULATION_EVIDENCE_UNAVAILABLE",
                )
            return finish(
                {
                    "state": "POPULATION_PENDING",
                    "collection": result,
                    "pending": completed,
                }
            )
        if not all(m.state in _TERMINAL_INPUT for m in ready.members):
            result = _collection(app, plan, "input", provider, worker_id, maximum_steps, before_action)
            if result["state"] != "BUDGET_EXHAUSTED":
                return finish(
                    {
                        "state": "DATA_PENDING",
                        "collection": result,
                        "pending": completed,
                    }
                )
            if ready.state not in {"READY", "PARTIAL"}:
                return finish_abstention(
                    plan,
                    "DATA_READINESS_BUDGET_EXHAUSTED",
                )
        if ready.feature_ready_count == 0:
            return finish_abstention(
                plan,
                "NO_FEATURE_READY_MEMBERS",
            )
    with daily_research_admission(
        prediction_id=plan.prediction_id, code_sha=plan.code_sha, config_sha256=sha256(encode_daily_plan(plan)).hexdigest()
    ):
        execution = DailyResearchOperations(app, reads, before_action=before_action).execute(
            plan, worker_id=worker_id, maximum_steps=min(maximum_steps, 9)
        )
    projection_state = "PREDICTION_PROGRESS"
    if execution.run_state == "SUCCEEDED":
        projection = reads.forecast_projection(plan)
        projection_state = (
            "PREDICTION_PUBLISHED"
            if projection["denominators"]["model_prediction"] > 0
            else "PREDICTION_COMPLETED_ZERO"
        )
    elif any(
        step.latest_attempt_error_code
        == "MODEL_USE_UNAVAILABLE_FOR_NEW_PREDICTION"
        for step in execution.steps
    ):
        projection_state = "PREDICTION_BLOCKED_MODEL_USE"
    payload: dict[str, Any] = {
        "state": projection_state,
        "result": execution,
        "pending": completed,
    }
    if execution.run_state == "SUCCEEDED" and delivery_adapter is not None:
        try:
            payload["delivery"] = _deliver_report(
                app,
                plan,
                delivery_adapter,
                worker_id=worker_id,
                before_action=before_action,
            )
        except (RuntimeError, ValueError) as exc:
            payload["delivery"] = {
                "state": "DELIVERY_FAILED",
                "reason_code": str(exc),
                "delivery_attempted": True,
                "prediction_and_settlement_blocked": False,
            }
    return finish(payload)


def _deliver_report(
    app: TargetApplication,
    plan: DailyPredictionPlan,
    adapter: DailyDeliveryAdapter,
    *,
    worker_id: str,
    before_action: Callable[[], None],
) -> dict[str, object]:
    from market_regime_alpha.infrastructure.postgres.prospective_operation_session import (
        daily_delivery_admission,
    )
    from market_regime_alpha.interfaces.daily_delivery import DailyReportDelivery

    def admission(delivery_plan: Any) -> Any:
        return daily_delivery_admission(
            prediction_id=delivery_plan.prediction_id,
            experimental_model_use_id=delivery_plan.experimental_model_use_id,
            code_sha=delivery_plan.code_sha,
            config_sha256=delivery_plan.content_sha256,
            channel=delivery_plan.channel,
        )

    return DailyReportDelivery(
        app,
        app.daily_prediction_reads,
        admission_scope=admission,
        before_action=before_action,
    ).deliver(plan, adapter, worker_id=worker_id)


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
