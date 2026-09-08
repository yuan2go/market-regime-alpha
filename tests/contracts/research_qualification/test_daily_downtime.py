"""Uncreated daily windows become current-time abstentions, never past predictions."""

from contextlib import nullcontext
from dataclasses import replace
from datetime import timedelta
from hashlib import sha256
from types import SimpleNamespace
from uuid import UUID, uuid5

import pytest

from market_regime_alpha.bootstrap import (
    TargetSettings,
    bootstrap_application,
    bootstrap_database,
)
from market_regime_alpha.infrastructure.postgres.prospective_operation_session import (
    prospective_operation_session,
)
from market_regime_alpha.research_qualification.domain.daily_inputs import (
    DailyInputMember,
    DailyInputState,
    freeze_data_ready,
)
from market_regime_alpha.research_qualification.ports.daily_prediction import (
    DailyOutcomeWorkItem,
)
from tests.contracts.research_qualification.test_daily_prediction import plan


def test_elapsed_unpublished_window_is_recorded_before_current_prediction(monkeypatch):
    from market_regime_alpha.interfaces import daily_service

    template = plan()
    now = template.decision_time + timedelta(days=3)
    observed = []
    reads = SimpleNamespace(
        validate_configuration=lambda _: None,
        outcome_work_items=lambda **_: (),
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
    assert result["state"] == "ABSTAINED"
    assert result["reason_code"] == "PROCESS_DOWNTIME_MISSED_PUBLICATION"
    assert result["health"]["state"] == "HEALTH_QUERY_FAILED"
    assert len(observed) == 1


def test_calendar_exhaustion_is_a_typed_non_prediction_state():
    from market_regime_alpha.interfaces.daily_service import daily_tick
    from market_regime_alpha.runtime.errors import RuntimeStateConflictError

    reads = SimpleNamespace(
        validate_configuration=lambda _: None,
        outcome_work_items=lambda **_: (),
        missing_elapsed_session_pairs=lambda _: (),
        current_sessions=lambda: (_ for _ in ()).throw(
            RuntimeStateConflictError("DAILY_CALENDAR_COVERAGE_INCOMPLETE")
        ),
    )
    result = daily_tick(
        SimpleNamespace(daily_prediction_reads=reads),
        plan(),
        None,
        worker_id="daily",
        maximum_steps=1,
        before_action=lambda: None,
    )
    assert result["state"] == "CALENDAR_COVERAGE_INCOMPLETE"
    assert result["pending"] == []
    assert result["delivery"]["state"] == "NOT_CONFIGURED"


def test_elapsed_scan_bounds_outstanding_gaps_not_complete_model_use_lifetime():
    from market_regime_alpha.infrastructure.postgres.queries.daily_predictions import (
        PostgresDailyPredictionReads,
    )

    template = plan()
    pairs = tuple(
        (UUID(int=1_000 + index), UUID(int=2_000 + index))
        for index in range(300)
    )
    represented = {
        uuid5(
            uuid5(
                template.experimental_model_use_id,
                "daily:" + str(input_id) + ":" + str(target_id),
            ),
            "prediction-runtime",
        )
        for input_id, target_id in pairs[:130]
    }

    class Result:
        def __init__(self, rows):
            self._rows = rows

        def fetchall(self):
            return self._rows

    class Cursor:
        def __init__(self):
            self.offset = 0
            self.fetch_count = 0

        def execute(self, _query, _parameters):
            return self

        def fetchmany(self, size):
            self.fetch_count += 1
            rows = pairs[self.offset : self.offset + size]
            self.offset += len(rows)
            return rows

    cursor = Cursor()

    class Connection:
        def cursor(self):
            return cursor

        def execute(self, _query, parameters):
            requested = parameters[0]
            return Result([(run_id,) for run_id in requested if run_id in represented])

    connection = Connection()

    class ConnectionScope:
        def __enter__(self):
            return connection

        def __exit__(self, *_args):
            return False

    class Pool:
        def connection(self, *, read_only):
            assert read_only
            return ConnectionScope()

    reads = PostgresDailyPredictionReads(Pool(), object())  # type: ignore[arg-type]
    actual = reads.missing_elapsed_session_pairs(template)
    assert actual == pairs[130:194]
    assert cursor.fetch_count == 2


def test_zero_prediction_success_is_not_reported_as_publication(monkeypatch):
    from market_regime_alpha.interfaces import daily_service
    from market_regime_alpha.interfaces.daily_research import encode_daily_plan

    frozen = plan()
    content = encode_daily_plan(frozen)
    reads = SimpleNamespace(
        validate_configuration=lambda _: None,
        outcome_work_items=lambda **_: (),
        missing_elapsed_session_pairs=lambda _: (),
        run_plan_content=lambda run_id: (
            content if run_id == frozen.runtime_run_id else None
        ),
        ready=lambda _: SimpleNamespace(state="READY"),
        forecast_projection=lambda _: {
            "denominators": {"model_prediction": 0}
        },
    )
    monkeypatch.setattr(
        daily_service, "current_daily_plan", lambda _app, _template: frozen
    )
    monkeypatch.setattr(
        daily_service, "daily_research_admission", lambda **_: nullcontext()
    )
    monkeypatch.setattr(
        daily_service.DailyResearchOperations,
        "execute",
        lambda *_args, **_kwargs: SimpleNamespace(run_state="SUCCEEDED"),
    )
    result = daily_service.daily_tick(
        SimpleNamespace(daily_prediction_reads=reads),
        frozen,
        None,
        worker_id="daily",
        maximum_steps=1,
        before_action=lambda: None,
    )
    assert result["state"] == "PREDICTION_COMPLETED_ZERO"
    assert result["delivery"]["state"] == "NOT_CONFIGURED"


def test_late_target_data_within_grace_uses_canonical_collection_before_settlement(
    monkeypatch,
):
    from market_regime_alpha.interfaces import daily_service
    from market_regime_alpha.interfaces.daily_research import encode_daily_plan

    frozen = plan()
    content = encode_daily_plan(frozen)
    work = DailyOutcomeWorkItem(
        run_id=uuid5(frozen.prediction_id, "outcome-evaluation-runtime"),
        schedule_id=uuid5(
            frozen.experimental_model_use_id, "daily-outcome-schedule"
        ),
        schedule_code="daily-outcome-" + frozen.experimental_model_use_id.hex,
        fire_key="daily-outcome:" + str(frozen.prediction_id),
        parent_run_id=frozen.runtime_run_id,
        run_state="RUNNING",
        requested_at=frozen.decision_time,
        code_sha=frozen.code_sha,
        config_sha256=sha256(content).hexdigest(),
        plan_content=content,
        error_code=None,
    )
    collected = []
    reads = SimpleNamespace(
        validate_configuration=lambda _: None,
        outcome_work_items=lambda **_: (work,),
        ready=lambda _: SimpleNamespace(
            target_window_end=frozen.decision_time - timedelta(hours=1)
        ),
        now=lambda: frozen.decision_time,
        target_price_members=lambda _: (
            SimpleNamespace(state=DailyInputState.MISSING),
        ),
    )

    def collect(*args, **kwargs):
        collected.append((args, kwargs))
        return {"state": "COLLECTION_PROGRESS"}

    monkeypatch.setattr(daily_service, "_collection", collect)
    monkeypatch.setattr(
        daily_service.DailyResearchOperations,
        "settle_and_evaluate",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("settlement ran before late-data grace elapsed")
        ),
    )
    result = daily_service.daily_tick(
        SimpleNamespace(daily_prediction_reads=reads),
        frozen,
        None,
        worker_id="daily",
        maximum_steps=1,
        before_action=lambda: None,
        delivery_adapter=SimpleNamespace(channel="fake"),
    )
    assert result["state"] == "OUTCOME_PROGRESS"
    assert result["outcomes"][0]["state"] == "OUTCOME_DATA_PENDING"
    assert result["delivery"] == {
        "state": "NOT_DUE",
        "channel": "fake",
        "delivery_attempted": False,
        "prediction_and_settlement_blocked": False,
    }
    assert len(collected) == 1


def test_real_daily_tick_records_downtime_once_through_runtime_handoff(
    target_database_url, tmp_path, monkeypatch
):
    settings = TargetSettings(target_database_url, tmp_path / "artifacts")
    bootstrap_database(settings)
    template = plan()
    with bootstrap_application(settings) as app:
        now = app.daily_prediction_reads.now()
    input_session = UUID(int=101)
    target_session = UUID(int=102)
    ready = freeze_data_ready(
        input_session_id=input_session,
        target_session_id=target_session,
        input_event_end=now - timedelta(hours=2),
        input_cutoff=now,
        decision_time=now,
        target_window_start=now - timedelta(hours=1),
        target_window_end=now + timedelta(hours=5),
        expected_instruments=template.instrument_ids,
        members=tuple(
            DailyInputMember(
                instrument_id,
                DailyInputState.SUSPENDED,
                "SYNTHETIC_SUSPENSION",
            )
            for instrument_id in template.instrument_ids
        ),
    )

    class DowntimeReads:
        def __init__(self, persisted, *, expose_gap):
            self._persisted = persisted
            self._expose_gap = expose_gap

        def validate_configuration(self, _plan):
            return None

        def outcome_work_items(self, **_):
            return ()

        def missing_elapsed_session_pairs(self, _plan):
            return (
                ((input_session, target_session),)
                if self._expose_gap
                else ()
            )

        def current_sessions(self):
            return input_session, target_session, now

        def run_plan_content(self, run_id):
            return self._persisted.run_plan_content(run_id)

        def collection_rounds(self, prediction_id, phase):
            return self._persisted.collection_rounds(prediction_id, phase)

        def now(self):
            return now

        def observe(self, _plan):
            return ready

        def ready(self, _plan):
            return ready

    def invoke(*, expose_gap, crash_after_artifact=False):
        # A new application composition and supervisor session exercise restart
        # recovery rather than only a second call on the same Python objects.
        with bootstrap_application(settings) as app:
            app.daily_prediction_reads = DowntimeReads(  # type: ignore[assignment]
                app.daily_prediction_reads,
                expose_gap=expose_gap,
            )
            identity = app.evidence.inventory()["database"]
            with prospective_operation_session(
                target_database_url,
                database_name=identity["name"],
                database_oid=identity["oid"],
                cluster_identity=identity["cluster_identity"],
                series_code="daily-downtime-fixture",
            ) as supervisor:
                supervisor.allow_expired_daily_recovery(
                    template.experimental_model_use_id,
                    template.code_sha,
                )

                def before_action():
                    supervisor.require_supervisor_lock(
                        "daily-downtime-fixture"
                    )
                    assert not supervisor.has_conflicting_attempts(
                        "daily-downtime-fixture"
                    )

                from market_regime_alpha.interfaces.daily_service import daily_tick

                if crash_after_artifact:
                    monkeypatch.setattr(
                        app.runtime,
                        "succeed_attempt",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(
                            SystemExit("simulated lost abstention completion receipt")
                        ),
                    )
                return daily_tick(
                    app,
                    template,
                    None,
                    worker_id="daily-downtime-fixture",
                    maximum_steps=1,
                    before_action=before_action,
                )

    from market_regime_alpha.interfaces import daily_research

    monkeypatch.setattr(
        daily_research,
        "_ABSTENTION_LEASE_DURATION",
        timedelta(seconds=1),
    )
    with pytest.raises(SystemExit, match="lost abstention completion receipt"):
        invoke(expose_gap=True, crash_after_artifact=True)
    import time

    time.sleep(1.05)
    recovered = invoke(expose_gap=False)
    repeated = invoke(expose_gap=False)
    assert {
        key: value for key, value in recovered.items() if key != "health"
    } == {
        key: value for key, value in repeated.items() if key != "health"
    }
    assert recovered["state"] == "ABSTAINED"
    assert recovered["reason_code"] == "PROCESS_DOWNTIME_MISSED_PUBLICATION"
    assert recovered["runtime"].run_state == "SUCCEEDED"
    assert recovered["runtime"].steps[0].attempt_states == (
        "ABANDONED",
        "SUCCEEDED",
    )
    assert recovered["runtime"].steps[0].current_fence == 2


def test_switched_template_settles_old_frozen_model_plan(monkeypatch):
    from market_regime_alpha.interfaces import daily_service
    from market_regime_alpha.interfaces.daily_research import encode_daily_plan

    historical = plan()
    current = replace(
        historical,
        prediction_id=UUID(int=201),
        experimental_model_use_id=UUID(int=202),
        model_version_id=UUID(int=203),
    )
    content = encode_daily_plan(historical)
    work = DailyOutcomeWorkItem(
        run_id=UUID(int=0),
        schedule_id=UUID(int=0),
        schedule_code="",
        fire_key="",
        parent_run_id=historical.runtime_run_id,
        run_state="RUNNING",
        requested_at=historical.decision_time,
        code_sha=historical.code_sha,
        config_sha256=sha256(content).hexdigest(),
        plan_content=content,
        error_code=None,
    )
    work = replace(
        work,
        run_id=uuid5(historical.prediction_id, "outcome-evaluation-runtime"),
        schedule_id=uuid5(
            historical.experimental_model_use_id, "daily-outcome-schedule"
        ),
        schedule_code="daily-outcome-" + historical.experimental_model_use_id.hex,
        fire_key="daily-outcome:" + str(historical.prediction_id),
    )
    malformed = replace(work, run_id=UUID(int=301))
    waiting = replace(
        work,
        run_id=UUID(int=302),
        run_state="WAITING",
        error_code="EXTERNAL_EFFECT_UNKNOWN",
    )
    failed = replace(
        work,
        run_id=UUID(int=303),
        run_state="FAILED",
        error_code="DAILY_OUTCOME_STEP_FAILED",
    )
    observed = []
    def validate_configuration(frozen):
        if frozen == current:
            raise AssertionError(
                "current prediction configuration blocked historical settlement"
            )
        observed.append(frozen)

    reads = SimpleNamespace(
        validate_configuration=validate_configuration,
        outcome_work_items=lambda **_: (malformed, waiting, failed, work),
        ready=lambda _: SimpleNamespace(
            target_window_end=historical.decision_time - timedelta(hours=1)
        ),
        now=lambda: historical.decision_time,
        target_price_members=lambda _: (
            SimpleNamespace(state=DailyInputState.SUSPENDED),
        ),
    )
    monkeypatch.setattr(
        daily_service, "daily_research_admission", lambda **_: nullcontext()
    )

    def settle(self, frozen, **_):
        observed.append(frozen)
        return {"state": "SUCCEEDED"}

    monkeypatch.setattr(
        daily_service.DailyResearchOperations, "settle_and_evaluate", settle
    )
    result = daily_service.daily_tick(
        SimpleNamespace(daily_prediction_reads=reads),
        current,
        None,
        worker_id="daily",
        maximum_steps=1,
        before_action=lambda: None,
    )
    assert result["state"] == "OUTCOME_PROGRESS"
    assert observed == [historical, historical]
    assert [item["state"] for item in result["outcomes"]] == [
        "INTEGRITY_BLOCKED",
        "RECOVERY_REQUIRED",
        "RECOVERY_REQUIRED",
        "SETTLEMENT_PROGRESS",
    ]
    assert not result["outcomes"][1]["automatic_retry"]
    assert not result["outcomes"][2]["automatic_retry"]
    assert (
        result["outcomes"][3]["experimental_model_use_id"]
        == historical.experimental_model_use_id
    )
