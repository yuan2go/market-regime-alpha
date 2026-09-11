"""A Model-use installation handoff preserves original frozen session work."""

from dataclasses import replace
from datetime import timedelta
from hashlib import sha256
from types import SimpleNamespace
from uuid import UUID, uuid4, uuid5

import pytest

from market_regime_alpha.interfaces import daily_service
from market_regime_alpha.interfaces.daily_research import encode_daily_plan
from market_regime_alpha.research_qualification.ports.daily_prediction import DailySessionWorkItem, DailyOutcomeWorkItem
from market_regime_alpha.runtime.errors import ArtifactIntegrityError
from tests.contracts.research_qualification.test_daily_prediction import plan


@pytest.fixture(autouse=True)
def _isolated_calendar_handoff(monkeypatch):
    monkeypatch.setattr("market_regime_alpha.interfaces.daily_service.refresh_calendar", lambda *_, **__: {
        "state": "NOT_DUE", "reason_code": "SYNTHETIC_TEST_CALENDAR", "coverage": {"state": "VERIFIED"}})


def session_work(frozen, phase="prediction"):
    content = encode_daily_plan(frozen)
    return DailySessionWorkItem(
        frozen.experimental_model_use_id, frozen.prediction_id, phase,
        uuid5(frozen.prediction_id, phase + "-runtime"),
        uuid5(frozen.experimental_model_use_id, "daily-" + phase + "-schedule"),
        "daily-" + ("model" if phase == "prediction" else "abstention") + "-" + frozen.experimental_model_use_id.hex,
        ("daily:" if phase == "prediction" else "daily-abstention:") + str(frozen.prediction_id),
        frozen.code_sha, sha256(content).hexdigest(), content,
    )


def _original():
    frozen = plan()
    return replace(frozen, prediction_id=uuid5(frozen.experimental_model_use_id,
        "daily:" + str(frozen.input_session_id) + ":" + str(frozen.target_session_id)))


def _no_effect(*_args, **_kwargs):
    raise AssertionError("rollover must not acquire inputs or write replacement work")


def _reads(original, work):
    return SimpleNamespace(
        current_sessions=lambda: (original.input_session_id, original.target_session_id, original.decision_time + timedelta(minutes=5)),
        session_work_items=lambda *_: work, validate_configuration=lambda _: None,
        observe=_no_effect, collection_rounds=_no_effect,
    )


@pytest.mark.parametrize("phase", ["prediction", "abstention"])
def test_rollover_keeps_original_frozen_plan_bytes_for_existing_session(phase):
    original = _original()
    successor = replace(original, experimental_model_use_id=uuid4(), code_sha="d"*40,
                        code_artifact=replace(original.code_artifact, artifact_id=uuid4()))
    reads = _reads(original, (session_work(original, phase),))
    assert daily_service.current_daily_plan(SimpleNamespace(daily_prediction_reads=reads), successor) == original


@pytest.mark.parametrize("field,value", [
    ("model_version_id", UUID(int=101)), ("feature_definition_id", UUID(int=102)),
    ("target_definition_id", UUID(int=103)), ("baseline_strategy_version_id", UUID(int=104)),
    ("candidate_policy_id", UUID(int=105)), ("eligibility_policy_id", UUID(int=106)),
    ("context_policy_id", UUID(int=107)), ("strategy_version_id", UUID(int=108)),
    ("provider_product_id", UUID(int=109)), ("instrument_ids", (UUID(int=7),)),
    ("classification_code", "CHANGED_POPULATION"),
])
def test_rollover_refuses_any_changed_research_semantics(field, value):
    original = _original()
    successor = replace(original, experimental_model_use_id=uuid4(), **{field: value})
    with pytest.raises(ArtifactIntegrityError, match="DAILY_FROZEN_CONFIGURATION_CHANGED"):
        daily_service.current_daily_plan(SimpleNamespace(daily_prediction_reads=_reads(original, (session_work(original),))), successor)


@pytest.mark.parametrize("field,value", [
    ("schedule_id", UUID(int=111)), ("schedule_code", "foreign-model"),
    ("fire_key", "daily:foreign"), ("code_sha", "e"*40), ("config_sha256", "e"*64),
    ("experimental_model_use_id", UUID(int=112)), ("prediction_id", UUID(int=113)),
    ("run_id", UUID(int=114)), ("phase", "outcome"),
])
def test_rollover_authenticates_original_runtime_and_artifact(field, value):
    original = _original()
    broken = replace(session_work(original), **{field: value})
    with pytest.raises(ArtifactIntegrityError, match="DAILY_SESSION_FROZEN_IDENTITY_CHANGED"):
        daily_service.current_daily_plan(SimpleNamespace(daily_prediction_reads=_reads(original, (broken,))), original)


def test_rollover_refuses_multiple_frozen_predictions_for_same_model_session():
    original = _original()
    duplicate = replace(original, experimental_model_use_id=uuid4())
    duplicate = replace(duplicate, prediction_id=uuid5(duplicate.experimental_model_use_id,
        "daily:" + str(duplicate.input_session_id) + ":" + str(duplicate.target_session_id)))
    reads = _reads(original, (session_work(original), session_work(duplicate)))
    with pytest.raises(ArtifactIntegrityError, match="DAILY_SESSION_MULTIPLE_FROZEN_PREDICTIONS"):
        daily_service.current_daily_plan(SimpleNamespace(daily_prediction_reads=reads), duplicate)


def test_new_session_uses_successor_without_changing_old_session_population():
    original = _original()
    successor = replace(original, experimental_model_use_id=uuid4())
    future_input, future_target = uuid4(), uuid4()
    observed = []
    reads = _reads(original, ())
    reads.current_sessions = lambda: (future_input, future_target, original.decision_time + timedelta(days=3))
    reads.collection_rounds = lambda *_: ()
    reads.observe = lambda p: observed.append(p) or SimpleNamespace(content_sha256="e"*64)
    selected = daily_service.current_daily_plan(SimpleNamespace(daily_prediction_reads=reads), successor)
    assert selected.prediction_id == uuid5(successor.experimental_model_use_id, "daily:" + str(future_input) + ":" + str(future_target))
    assert selected.prediction_id != original.prediction_id
    assert selected.experimental_model_use_id == successor.experimental_model_use_id
    assert selected.instrument_ids == original.instrument_ids == observed[0].instrument_ids
    assert original.input_session_id != selected.input_session_id


@pytest.mark.parametrize("outcome_state", ["QUEUED", "RUNNING", "FAILED", "WAITING"])
def test_rollover_published_prediction_and_old_outcome_remain_original(outcome_state):
    original = _original()
    successor = replace(original, experimental_model_use_id=uuid4())
    reads = _reads(original, (session_work(original),))
    content = encode_daily_plan(original)
    item = DailyOutcomeWorkItem(
        uuid5(original.prediction_id, "outcome-evaluation-runtime"),
        uuid5(original.experimental_model_use_id, "daily-outcome-schedule"),
        "daily-outcome-" + original.experimental_model_use_id.hex,
        "daily-outcome:" + str(original.prediction_id), original.runtime_run_id,
        outcome_state, original.decision_time, original.code_sha, sha256(content).hexdigest(), content, None,
    )
    reads.outcome_work_items = lambda **_: (item,)
    reads.missing_elapsed_session_pairs = lambda _: ()
    reads.now = lambda: original.decision_time
    reads.ready = lambda p: SimpleNamespace(state="READY", target_window_end=original.decision_time + timedelta(days=1))
    reads.run_plan_content = lambda identity: content if identity == original.runtime_run_id else None
    reads.forecast_projection = lambda p: {"denominators": {"model_prediction": len(p.instrument_ids)}}
    reads.operational_health = lambda p, **kwargs: {"selected": p, "template": kwargs["template"]}
    trace = SimpleNamespace(run_id=original.runtime_run_id, run_state="SUCCEEDED")
    app = SimpleNamespace(daily_prediction_reads=reads, runtime=SimpleNamespace(inspect_run=lambda _: trace))
    result = daily_service.daily_tick(app, successor, None, worker_id="fixture", maximum_steps=1, before_action=lambda: None)
    assert result["state"] == "PREDICTION_PUBLISHED"
    assert result["result"] is trace
    assert result["pending"][0]["run_state"] == outcome_state
    assert result["pending"][0]["run_id"] == item.run_id
    assert result["pending"][0]["state"] == ("PENDING_MATURITY" if outcome_state in {"QUEUED", "RUNNING"} else "RECOVERY_REQUIRED")
    assert result["health"]["selected"] == original and result["health"]["template"] == successor


@pytest.mark.parametrize("state", ["QUEUED", "RUNNING", "FAILED", "WAITING", "CANCELLED"])
def test_rollover_cannot_reopen_or_replace_original_unpublished_prediction(state):
    original = _original()
    successor = replace(original, experimental_model_use_id=uuid4())
    reads = _reads(original, (session_work(original),))
    reads.outcome_work_items = lambda **_: ()
    reads.missing_elapsed_session_pairs = lambda _: ()
    reads.run_plan_content = lambda identity: encode_daily_plan(original) if identity == original.runtime_run_id else None
    reads.ready = _no_effect
    trace = SimpleNamespace(run_id=original.runtime_run_id, run_state=state, steps=())
    app = SimpleNamespace(daily_prediction_reads=reads, runtime=SimpleNamespace(inspect_run=lambda _: trace))
    result = daily_service.daily_tick(app, successor, None, worker_id="fixture", maximum_steps=1, before_action=lambda: None)
    assert result["state"] == "PREDICTION_RECOVERY_REQUIRED" and result["automatic_retry"] is False
    assert result["failed_run_id"] == original.runtime_run_id
