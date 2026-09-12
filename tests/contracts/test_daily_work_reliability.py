"""Service allocation/observational failure contracts; no real trading-day proof."""

from contextlib import nullcontext
from dataclasses import replace
from datetime import timedelta
from hashlib import sha256
from types import SimpleNamespace
from uuid import UUID, uuid5

import pytest

from market_regime_alpha.interfaces import daily_service
from market_regime_alpha.interfaces.daily_research import encode_daily_plan
from market_regime_alpha.interfaces.daily_work import DailyWorkCursor, advance_daily_work
from market_regime_alpha.interfaces.operation_observation import ActionGuard
from market_regime_alpha.research_qualification.ports.daily_prediction import DailyOutcomeWorkItem
from tests.contracts.research_qualification.test_daily_prediction import plan


def test_guard_remembers_the_original_rejection_and_never_rechecks_to_allow_writes():
    calls = []
    original = ValueError("OPERATION_PERMISSION_CHANGED")
    def check():
        calls.append(1)
        if len(calls) == 1:
            raise original
    guard = ActionGuard(check)
    for _ in range(3):
        with pytest.raises(ValueError) as failure:
            guard()
        assert failure.value is original
    assert calls == [1]


def test_current_notification_is_found_before_old_unknown_cursor_and_never_resends_unknown(monkeypatch):
    from market_regime_alpha.interfaces import daily_work
    from market_regime_alpha.research_qualification.ports.daily_prediction import DailyDeliveryWorkItem
    plans = [replace(plan(), prediction_id=UUID(int=500+i)) for i in range(34)]
    items = [DailyDeliveryWorkItem(p.runtime_run_id, p.decision_time + timedelta(seconds=i), p.code_sha,
        sha256(encode_daily_plan(p)).hexdigest(), uuid5(p.experimental_model_use_id, "daily-prediction-schedule"),
        "daily-model-" + p.experimental_model_use_id.hex, "daily:" + str(p.prediction_id), encode_daily_plan(p),
        "WAITING" if i < 33 else "NOT_REQUESTED", None) for i, p in enumerate(plans)]
    calls = []
    reads = SimpleNamespace(delivery_work_items=lambda channel, **kwargs: (items[-1],) if kwargs.get("recent") else tuple(items[:32]),
        validate_configuration=lambda _: None, delivery_work_counts=lambda _: {"WAITING": 33, "NOT_REQUESTED": 1})
    def deliver(_app, frozen, *_args, **_kwargs):
        calls.append(frozen.prediction_id)
        return {"state": "ACCEPTED" if frozen == plans[-1] else "DELIVERY_UNKNOWN",
                "delivery_attempted": True, "attempted_this_call": frozen == plans[-1]}
    monkeypatch.setattr(daily_service, "_deliver_report", deliver)
    result = daily_work.advance_delivery_work(SimpleNamespace(daily_prediction_reads=reads),
        SimpleNamespace(channel="fixture"), worker_id="fixture", before_action=lambda: None, cursor=DailyWorkCursor())
    assert calls == [plans[-1].prediction_id]
    assert result["items"][0]["state"] == "ACCEPTED"


def test_failed_delivery_discovery_does_not_erase_prediction_results(monkeypatch):
    import psycopg
    monkeypatch.setattr(daily_service, "daily_tick", lambda *_args, **_kwargs: {"state": "SUCCEEDED", "receipt": "original"})
    def failed(*_args, **_kwargs):
        raise psycopg.errors.QueryCanceled("query cancelled")
    reads = SimpleNamespace(delivery_work_items=failed, outcome_work_counts=lambda: {"SUCCEEDED": 1})
    result = advance_daily_work(SimpleNamespace(daily_prediction_reads=reads), plan(), None,
        worker_id="fixture", maximum_steps=2, before_action=lambda: None,
        delivery_adapter=SimpleNamespace(channel="fixture"), cursor=DailyWorkCursor())
    assert result["prediction"]["receipt"] == result["outcome"]["receipt"] == "original"
    assert result["delivery"]["state"] == "HEALTH_QUERY_FAILED"


@pytest.mark.parametrize("budget", [1, 2, 9, 32])
def test_both_current_prediction_and_outcome_receive_bounded_opportunities(monkeypatch, budget):
    calls = []
    def lane(*_args, **kwargs):
        calls.append((kwargs["_phase"], kwargs["maximum_steps"]))
        return {"state": "PERSISTENT_BACKLOG_PROGRESS"}
    monkeypatch.setattr(daily_service, "daily_tick", lane)
    cursor = DailyWorkCursor()
    app = SimpleNamespace(daily_prediction_reads=SimpleNamespace(outcome_work_counts=lambda: {"RUNNING": 1000}))
    for _ in range(4):
        result = advance_daily_work(app, plan(), None, worker_id="fixture", maximum_steps=budget,
            before_action=lambda: None, delivery_adapter=None, cursor=cursor)
        assert sum(result["step_budgets"].values()) <= budget
        assert result["outcome_work"]["complete_runtime_counts"] == {"RUNNING": 1000}
    assert {phase for phase, _ in calls} == {"prediction", "outcome"}
    if budget > 1:
        assert [phase for phase, _ in calls] == ["prediction", "outcome"] * 4
    assert all(0 < steps <= budget for _, steps in calls)


def _work(number):
    frozen = replace(plan(), prediction_id=UUID(int=1000 + number), experimental_model_use_id=UUID(int=2000 + number))
    content = encode_daily_plan(frozen)
    return frozen, DailyOutcomeWorkItem(uuid5(frozen.prediction_id, "outcome-evaluation-runtime"),
        uuid5(frozen.experimental_model_use_id, "daily-outcome-schedule"),
        "daily-outcome-" + frozen.experimental_model_use_id.hex, "daily-outcome:" + str(frozen.prediction_id),
        frozen.runtime_run_id, "RUNNING", frozen.decision_time + timedelta(seconds=number),
        frozen.code_sha, sha256(content).hexdigest(), content, None, True)


def test_cursor_advances_past_persistently_incomplete_work_across_many_model_uses(monkeypatch):
    pairs = [_work(i) for i in range(130)]
    seen = []
    reads = SimpleNamespace(
        outcome_work_items=lambda *, limit, after: tuple(item for _, item in pairs if after is None or item.cursor > after)[:limit],
        validate_configuration=lambda _: None,
        ready=lambda frozen: SimpleNamespace(target_window_end=frozen.decision_time - timedelta(hours=1)),
        now=lambda: pairs[0][0].decision_time,
    )
    monkeypatch.setattr(daily_service, "daily_research_admission", lambda **_: nullcontext())
    def settle(_self, frozen, **_):
        seen.append(frozen.prediction_id)
        return {"state": "RUNNING"}  # Deliberately remains pending on every invocation.
    monkeypatch.setattr(daily_service.DailyResearchOperations, "settle_and_evaluate", settle)
    cursor = DailyWorkCursor()
    app = SimpleNamespace(daily_prediction_reads=reads)
    for _ in pairs:
        daily_service.daily_tick(app, pairs[0][0], None, worker_id="fixture", maximum_steps=1,
            before_action=lambda: None, work_cursor=cursor, _phase="outcome")
    assert seen == [frozen.prediction_id for frozen, _ in pairs]


def test_safety_failure_during_outcome_is_not_downgraded_to_a_business_failure(monkeypatch):
    frozen, work = _work(1)
    reads = SimpleNamespace(outcome_work_items=lambda **_: (work,), validate_configuration=lambda _: None,
        ready=lambda _: SimpleNamespace(target_window_end=frozen.decision_time - timedelta(hours=1)),
        now=lambda: frozen.decision_time)
    failure = ValueError("OPERATION_BACKUP_BASELINE_EXPIRED")
    calls = []
    def guard():
        calls.append("check")
        if len(calls) > 1:
            raise failure
    def settle(self, *_args, **_kwargs):
        self._before_action()
        calls.append("forbidden-write")
    monkeypatch.setattr(daily_service, "daily_research_admission", lambda **_: nullcontext())
    monkeypatch.setattr(daily_service.DailyResearchOperations, "settle_and_evaluate", settle)
    with pytest.raises(ValueError) as observed:
        daily_service.daily_tick(SimpleNamespace(daily_prediction_reads=reads), frozen, None,
            worker_id="fixture", maximum_steps=1, before_action=guard)
    assert observed.value is failure
    assert "forbidden-write" not in calls
