"""Explicit late Outcome capture cannot replace a publication or a started settlement."""
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid5

import pytest

from market_regime_alpha.interfaces.daily_research import encode_daily_plan
from tests.contracts.research_qualification.test_daily_prediction import plan


@pytest.mark.parametrize('failure', ['future', 'unpublished', 'changed_plan', 'started_settlement', 'terminal_failure'])
def test_late_collection_refuses_before_provider_effect(monkeypatch, failure):
    from market_regime_alpha.interfaces.cli import daily
    frozen = plan()
    content = encode_daily_plan(frozen)
    run_id = uuid5(frozen.prediction_id, 'outcome-evaluation-runtime')
    def trace(identity):
        if identity == frozen.runtime_run_id:
            return SimpleNamespace(run_state='QUEUED' if failure == 'unpublished' else 'SUCCEEDED')
        assert identity == run_id
        return SimpleNamespace(run_state='FAILED' if failure == 'terminal_failure' else 'QUEUED',
            steps=(SimpleNamespace(step_key='settle-x', current_fence=1 if failure == 'started_settlement' else 0),))
    reads = SimpleNamespace(run_plan_content=lambda _: b'changed' if failure == 'changed_plan' else content,
        validate_configuration=lambda _: None, ready=lambda _: SimpleNamespace(target_window_end=frozen.decision_time),
        now=lambda: frozen.decision_time-timedelta(seconds=1) if failure == 'future' else frozen.decision_time+timedelta(days=2))
    app = SimpleNamespace(runtime=SimpleNamespace(inspect_run=trace), daily_prediction_reads=reads)
    with pytest.raises(ValueError, match='DAILY_OUTCOME_RECOVERY'):
        daily._collect_pending_outcome(app, frozen, SimpleNamespace(), SimpleNamespace(), 1)


def test_late_collection_uses_original_plan_and_actual_clock(monkeypatch):
    from market_regime_alpha.interfaces.cli import daily
    from market_regime_alpha.interfaces import daily_service
    frozen = plan()
    observed = []
    app = SimpleNamespace(daily_research=SimpleNamespace(replay=lambda _:{"matched":True}), runtime=SimpleNamespace(inspect_run=lambda identity: SimpleNamespace(
        run_state='SUCCEEDED' if identity == frozen.runtime_run_id else 'QUEUED', steps=())),
        daily_prediction_reads=SimpleNamespace(run_plan_content=lambda _: encode_daily_plan(frozen),
            validate_configuration=lambda _: None, ready=lambda _: SimpleNamespace(target_window_end=frozen.decision_time),
            now=lambda: frozen.decision_time+timedelta(days=2)))
    monkeypatch.setattr(daily_service, '_collection', lambda app, p, phase, provider, worker, budget, before: observed.append((p,phase,budget)) or {'state':'COLLECTION_PROGRESS'})
    config = SimpleNamespace(provider_timeout_seconds=2,provider_maximum_rows=100,provider_maximum_response_bytes=4096,worker_id='exact',maximum_attempts_per_tick=2)
    result=daily._collect_pending_outcome(app,frozen,config,SimpleNamespace(before_action=lambda: None),2)
    assert result['observation_disposition']=='LATE_OUTCOME_OBSERVATION'
    assert result['prediction_id']==frozen.prediction_id
    assert observed==[(frozen,'outcome',2)]


def test_cli_collection_enters_one_atomic_daily_scope(request, tmp_path, monkeypatch):
    from market_regime_alpha.interfaces.cli import daily
    from market_regime_alpha.interfaces.prospective_operation_guard import ProspectiveOperationGuard
    from market_regime_alpha.infrastructure.postgres.prospective_operation_session import daily_research_admission
    from contextlib import nullcontext
    settings, _, config = request.getfixturevalue("guarded_scope")
    frozen = plan()
    path = tmp_path / 'frozen.json'
    path.write_bytes(encode_daily_plan(frozen))
    monkeypatch.setattr(daily,'load_operation_config',lambda _:config)
    monkeypatch.setattr(daily,'require_installation',lambda _:None)
    monkeypatch.setattr(ProspectiveOperationGuard,'verify_startup',lambda *_:None)
    monkeypatch.setattr(daily,'bootstrap_application',lambda _:nullcontext(SimpleNamespace(daily_prediction_reads=SimpleNamespace(validate_configuration=lambda _:None))))
    def collect(app,p,config,guard,maximum):
        with daily_research_admission(prediction_id=p.prediction_id,code_sha=p.code_sha,config_sha256='c'*64,collection_phase='outcome'):
            guard.before_action()
            return {'state':'ADMITTED'}
    monkeypatch.setattr(daily,'_collect_pending_outcome',collect)
    result=daily.dispatch_daily(SimpleNamespace(daily_command='collect-outcome',plan=path,operation_config=path,maximum_steps=1),settings)
    assert result=={'state':'ADMITTED'}


from tests.contracts.market.test_prospective_operation_guard_postgres import guarded_scope  # noqa: E402, F401
