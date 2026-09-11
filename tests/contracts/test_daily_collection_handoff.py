"""Collection handoff preserves business identity before publication freezes time."""
from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid5, uuid4

import pytest

from market_regime_alpha.interfaces.daily_collection import DailyCollectionPlan
from market_regime_alpha.interfaces.daily_research import encode_daily_plan
from market_regime_alpha.interfaces.daily_service import current_daily_plan
from market_regime_alpha.runtime.errors import ArtifactIntegrityError
from tests.contracts.research_qualification.test_daily_prediction import plan
from tests.contracts.research_qualification.test_daily_model_use_rollover import session_work


@pytest.fixture(autouse=True)
def _isolated_calendar_handoff(monkeypatch):
    monkeypatch.setattr("market_regime_alpha.interfaces.daily_service.refresh_calendar", lambda *_, **__: {
        "state": "NOT_DUE", "reason_code": "SYNTHETIC_TEST_CALENDAR", "coverage": {"state": "VERIFIED"}})


@pytest.mark.parametrize('published', [False, True])
def test_installed_handoff_keeps_original_model_and_code_but_only_unpublished_cutoff_can_advance(published):
    original = plan()
    identity = uuid5(original.experimental_model_use_id, 'daily:' + str(original.input_session_id) + ':' + str(original.target_session_id))
    original = replace(original, prediction_id=identity)
    collection = DailyCollectionPlan(original, 'population', 1, original.decision_time)
    now = original.decision_time + timedelta(minutes=5)
    template = replace(original, code_sha='b'*40, code_artifact=replace(original.code_artifact, artifact_id=uuid4()))
    reads = SimpleNamespace(current_sessions=lambda: (original.input_session_id, original.target_session_id, now),
        session_work_items=lambda *_: (session_work(original),) if published else (), validate_configuration=lambda _: None,
        run_plan_content=lambda run_id: encode_daily_plan(original) if published and run_id==original.runtime_run_id else None,
        collection_rounds=lambda _, phase: ((1,'FAILED',original.decision_time,collection.content),) if phase=='population' else (),
        observe=lambda _: SimpleNamespace(content_sha256='c'*64))
    app = SimpleNamespace(daily_prediction_reads=reads)
    result = current_daily_plan(app, template)
    assert result.model_version_id == original.model_version_id
    assert result.code_sha == original.code_sha and result.code_artifact == original.code_artifact
    assert result.input_cutoff == (original.input_cutoff if published else now)
    if published:
        assert encode_daily_plan(result) == encode_daily_plan(original)
    with pytest.raises(ArtifactIntegrityError, match='FROZEN_CONFIGURATION_CHANGED'):
        current_daily_plan(app, replace(template, model_version_id=uuid4()))


def test_terminal_daily_failure_is_reported_without_reexecuting_or_blocking_the_service():
    from market_regime_alpha.interfaces.daily_service import daily_tick
    original = plan()
    identity = uuid5(original.experimental_model_use_id, "daily:"+str(original.input_session_id)+":"+str(original.target_session_id))
    original = replace(original,prediction_id=identity)
    def no_execution(*args):
        raise AssertionError("terminal failure must not read new inputs or execute")
    reads=SimpleNamespace(validate_configuration=lambda _:None, outcome_work_items=lambda **_:(), missing_elapsed_session_pairs=lambda _:(),
        session_work_items=lambda *_: (session_work(original),),
        current_sessions=lambda:(original.input_session_id,original.target_session_id,original.decision_time),
        run_plan_content=lambda rid:encode_daily_plan(original) if rid==original.runtime_run_id else None,
        ready=no_execution, operational_health=lambda _, **__: {"terminal_failures":1})
    trace=SimpleNamespace(run_state="FAILED",run_id=original.runtime_run_id,steps=(SimpleNamespace(latest_attempt_error_code="DAILY_PREDICTION_STEP_FAILED"),))
    app=SimpleNamespace(daily_prediction_reads=reads,runtime=SimpleNamespace(inspect_run=lambda _:trace))
    result=daily_tick(app,original,None,worker_id="fixture",maximum_steps=1,before_action=lambda:None)
    assert result["state"]=="PREDICTION_RECOVERY_REQUIRED"
    assert result["automatic_retry"] is False
    assert result["failed_run_id"]==original.runtime_run_id
    assert result["pending"]==[]
