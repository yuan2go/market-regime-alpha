"""Uncreated daily windows become current-time abstentions, never past predictions."""

from datetime import timedelta
from types import SimpleNamespace
from uuid import UUID

from tests.refoundation.research_qualification.test_daily_prediction import plan


def test_elapsed_unpublished_window_is_recorded_before_current_prediction(monkeypatch):
    from market_regime_alpha.interfaces import daily_service

    template = plan()
    now = template.decision_time + timedelta(days=3)
    observed = []
    reads = SimpleNamespace(
        validate_configuration=lambda _: None,
        pending_outcome_plans=lambda _: (),
        missing_elapsed_session_pairs=lambda _: ((UUID(int=21), UUID(int=22)),),
        now=lambda: now,
        observe=lambda p: observed.append(p) or SimpleNamespace(content_sha256="d" * 64),
    )

    def abstain(app, frozen, reason, worker, before):
        assert frozen.input_session_id == UUID(int=21)
        assert frozen.target_session_id == UUID(int=22)
        assert frozen.decision_time == frozen.input_cutoff == now
        assert frozen.input_content_sha256 == "d" * 64
        return {"state": "ABSTAINED", "reason_code": reason}

    monkeypatch.setattr(daily_service, "_abstain", abstain)
    result = daily_service.daily_tick(
        SimpleNamespace(daily_prediction_reads=reads), template, None, worker_id="daily", maximum_steps=1, before_action=lambda: None
    )
    assert result == {"state": "ABSTAINED", "reason_code": "PROCESS_DOWNTIME_MISSED_PUBLICATION"}
    assert len(observed) == 1
