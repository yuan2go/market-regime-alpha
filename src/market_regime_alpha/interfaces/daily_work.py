"""Bounded work allocation inside the existing daily service tick.

Cursors are process-local scan positions, never saved work or authorization.
Restart scans from the beginning; PostgreSQL retains every pending/failed item.
"""

from dataclasses import dataclass
from contextlib import nullcontext
from hashlib import sha256
from typing import Any, Callable
from time import perf_counter
from uuid import uuid5

from market_regime_alpha.interfaces.daily_research import decode_daily_plan, encode_daily_plan
from market_regime_alpha.interfaces.operation_observation import ActionGuard, observe_health
from market_regime_alpha.research_qualification.ports.daily_prediction import DailyDeliveryWorkItem, DailyOutcomeCursor, DailyPublicationCursor
from market_regime_alpha.runtime.errors import ArtifactIntegrityError


@dataclass(slots=True)
class DailyWorkCursor:
    outcome_after: DailyOutcomeCursor | None = None
    delivery_after: DailyPublicationCursor | None = None
    turn: int = 0


def prepare_delivery_recovery(app: Any, session: Any) -> None:
    """Authenticate original notification plans before expired-attempt admission."""
    from market_regime_alpha.interfaces.daily_delivery import DailyDeliveryPlan
    from market_regime_alpha.interfaces.daily_research import render_daily_report
    reads = app.daily_prediction_reads
    for channel in reads.unfinished_delivery_channels():
        after = None
        while True:
            page = reads.delivery_work_items(channel, limit=32, after=after)
            for item in page:
                if item.delivery_state not in {"QUEUED", "RUNNING", "WAITING"}:
                    continue
                plan = published_delivery_plan(item)
                reads.validate_configuration(plan)
                _json_report, markdown = render_daily_report(plan, reads.forecast_projection(plan))
                report = reads.published_report(plan, "report-markdown", markdown)
                content = reads.run_plan_content(uuid5(plan.prediction_id, "report-delivery:" + channel))
                if content is None:
                    raise ArtifactIntegrityError("DELIVERY_RECOVERY_PLAN_UNAVAILABLE")
                frozen = DailyDeliveryPlan.decode(content)
                if (frozen.prediction_id != plan.prediction_id or frozen.experimental_model_use_id != plan.experimental_model_use_id
                    or frozen.model_version_id != plan.model_version_id or frozen.channel != channel
                    or frozen.code_sha != plan.code_sha or frozen.report != report or frozen.content != content):
                    raise ArtifactIntegrityError("DELIVERY_RECOVERY_PLAN_DIFFERS")
                session.allow_frozen_delivery_recovery(prediction_id=frozen.prediction_id,
                    experimental_model_use_id=frozen.experimental_model_use_id, code_sha=frozen.code_sha,
                    config_sha256=frozen.content_sha256, channel=channel)
            if len(page) < 32:
                break
            after = page[-1].cursor


def published_delivery_plan(item: DailyDeliveryWorkItem) -> Any:
    if item.plan_content is None:
        raise ArtifactIntegrityError(item.error_code or "DAILY_DELIVERY_FROZEN_PLAN_UNAVAILABLE")
    plan = decode_daily_plan(item.plan_content)
    if (item.run_id != plan.runtime_run_id or item.code_sha != plan.code_sha
        or item.config_sha256 != sha256(item.plan_content).hexdigest()
        or item.schedule_id != uuid5(plan.experimental_model_use_id, "daily-prediction-schedule")
        or item.schedule_code != "daily-model-" + plan.experimental_model_use_id.hex
        or item.fire_key != "daily:" + str(plan.prediction_id)
        or encode_daily_plan(plan) != item.plan_content):
        raise ArtifactIntegrityError("DAILY_DELIVERY_PUBLICATION_IDENTITY_CHANGED")
    return plan


def advance_delivery_work(app: Any, adapter: Any, *, worker_id: str,
                          before_action: Callable[[], None], cursor: DailyWorkCursor) -> dict[str, Any]:
    from market_regime_alpha.interfaces.daily_service import _deliver_report
    guard = ActionGuard(before_action)
    if adapter is None:
        return {"state": "NOT_CONFIGURED", "delivery_attempted": False}
    discovery = observe_health(lambda: {
        "recent": app.daily_prediction_reads.delivery_work_items(adapter.channel, limit=1, recent=True),
        "items": app.daily_prediction_reads.delivery_work_items(adapter.channel, limit=32, after=cursor.delivery_after)})
    if discovery.get("state") == "HEALTH_QUERY_FAILED":
        return {**discovery, "delivery_attempted": False}
    history = discovery["items"]
    recent = discovery["recent"]
    recent_ids = {item.run_id for item in recent}
    page = (*recent, *(item for item in history if item.run_id not in recent_ids))
    observations = []
    for item in page:
        if item.run_id not in recent_ids:
            cursor.delivery_after = item.cursor
        try:
            plan = published_delivery_plan(item)
            app.daily_prediction_reads.validate_configuration(plan)
            result = None
            if item.delivery_state in {"SUCCEEDED", "WAITING", "FAILED", "CANCELLED"}:
                from market_regime_alpha.interfaces.daily_delivery import DailyReportDelivery
                status = DailyReportDelivery(app, app.daily_prediction_reads, admission_scope=lambda _: nullcontext()).inspect(plan, adapter.channel)
                response = status.get("response")
                # Only a proved absence can enter the original owner's retry.
                if item.delivery_state != "WAITING" or not isinstance(response, dict) or response.get("state") != "PROVEN_NOT_SENT":
                    result = status
            if result is None:
                result = _deliver_report(app, plan, adapter, worker_id=worker_id, before_action=guard)
        except (RuntimeError, ValueError) as exc:
            guard.raise_if_failed()
            result = {"state": "DELIVERY_RECOVERY_REQUIRED", "run_id": item.run_id,
                      "error_type": type(exc).__name__, "reason_code": str(exc), "automatic_retry": False}
        observations.append(result)
        # At most one potentially effectful request per wakeup. UNKNOWN work is
        # inspected without resend, then the cursor moves on at the next wakeup.
        if result.get("attempted_this_call"):
            break
    else:
        if len(history) < 32:
            cursor.delivery_after = None
    return {"state": "INSPECTED", "items": observations, "next_cursor": cursor.delivery_after,
            "complete_runtime_counts": observe_health(lambda: app.daily_prediction_reads.delivery_work_counts(adapter.channel)),
            "prediction_and_settlement_blocked": False}


def advance_daily_work(app: Any, template: Any, provider: Any, *, worker_id: str, maximum_steps: int,
                       before_action: Callable[[], None], delivery_adapter: Any, cursor: DailyWorkCursor) -> dict[str, Any]:
    from market_regime_alpha.interfaces.daily_service import daily_tick
    if type(maximum_steps) is not int or not 1 <= maximum_steps <= 512:
        raise ValueError("daily step budget must be between 1 and 512")
    guard = ActionGuard(before_action)
    cursor.turn += 1
    if maximum_steps == 1:
        budgets = {"prediction": cursor.turn % 2, "outcome": 1 - cursor.turn % 2}
    else:
        budgets = {"prediction": min(9, (maximum_steps + 1) // 2), "outcome": maximum_steps // 2}
    result: dict[str, Any] = {"state": "DAILY_WORK_INSPECTED", "step_budgets": budgets,
                              "scan_cursor_contract": "PROCESS_LOCAL; DURABLE_WORK_REDISCOVERED_AFTER_RESTART"}
    timings = {}
    for phase, budget in budgets.items():
        if not budget:
            result[phase] = {"state": "NEXT_TICK_BUDGET_RESERVED"}
            continue
        started = perf_counter()
        try:
            result[phase] = daily_tick(app, template, provider, worker_id=worker_id, maximum_steps=budget,
                before_action=guard, work_cursor=cursor, _phase=phase)
        except (RuntimeError, ValueError) as exc:
            guard.raise_if_failed()
            result[phase] = {"state": "OWNER_RECOVERY_REQUIRED", "error_type": type(exc).__name__,
                             "reason_code": str(exc), "automatic_retry": False}
        finally:
            timings[phase] = {"elapsed_seconds": perf_counter() - started}
    guard.raise_if_failed()
    if result.get("prediction", {}).get("calendar_continuity", {}).get("coverage", {}).get("state") == "VERIFIED":
        try:
            result["missed_publications"] = daily_tick(app, template, provider, worker_id=worker_id, maximum_steps=1,
                before_action=guard, work_cursor=cursor, _phase="missed")
        except (RuntimeError, ValueError) as exc:
            guard.raise_if_failed()
            result["missed_publications"] = {"state": "OWNER_RECOVERY_REQUIRED", "error_type": type(exc).__name__}
    started = perf_counter()
    result["delivery"] = advance_delivery_work(app, delivery_adapter, worker_id=worker_id, before_action=guard, cursor=cursor)
    timings["delivery"] = {"elapsed_seconds": perf_counter() - started}
    result["phase_timings"] = timings
    result["outcome_work"] = {"complete_runtime_counts": observe_health(app.daily_prediction_reads.outcome_work_counts),
                              "next_cursor": cursor.outcome_after, "page_size": 64}
    return result
