"""Daily handoff shares the existing atomic writer reservation in a disposable DB."""

from datetime import timedelta
from hashlib import sha256
from uuid import uuid4

import pytest

from market_regime_alpha.bootstrap import bootstrap_application
from market_regime_alpha.interfaces.daily_research import encode_daily_plan, prediction_steps
from market_regime_alpha.interfaces.prospective_operation_guard import operational_session
from market_regime_alpha.runtime.domain import RunSpec, RuntimeMode, ScheduleSpec
from market_regime_alpha.shared.hashing import canonical_json_sha256
from tests.refoundation.market.test_prospective_operation_guard_postgres import guarded_scope  # noqa: F401
from tests.refoundation.research_qualification.test_daily_prediction import plan
from tests.refoundation.test_runtime_postgres import _context


def test_sequential_daily_handoff_is_exact_and_does_not_grant_foreign_workers(request):
    from concurrent.futures import ThreadPoolExecutor
    from market_regime_alpha.infrastructure.postgres.prospective_operation_session import daily_research_admission

    settings, _, config = request.getfixturevalue("guarded_scope")
    frozen = plan()
    content = encode_daily_plan(frozen)
    with bootstrap_application(settings) as app:
        artifact = app.artifacts.publish(content, media_type="application/json", context=_context("daily-plan"))
        schedule_id = uuid4()
        app.runtime.create_schedule(
            ScheduleSpec(schedule_id, "daily-model-handoff", 1, RuntimeMode.SHADOW, None, "Asia/Shanghai", "a" * 64, True),
            _context("daily-schedule"),
        )
        steps, deps = prediction_steps(frozen)
        app.runtime.schedule_run(
            RunSpec(
                frozen.runtime_run_id,
                schedule_id,
                "daily:" + str(frozen.prediction_id),
                RuntimeMode.SHADOW,
                frozen.decision_time,
                frozen.decision_time,
                frozen.code_sha,
                artifact.artifact_id,
                artifact.content_sha256,
            ),
            steps,
            deps,
            _context("daily-run"),
        )
        app.runtime.start_run(frozen.runtime_run_id, _context("daily-start"))

        def claim(key):
            return app.runtime.claim_next(
                run_id=frozen.runtime_run_id, worker_id="same-text", lease_duration=timedelta(seconds=2), context=_context(key)
            )

        with operational_session(settings, config) as guard:
            guard.before_action()
            with pytest.raises(ValueError, match="OUTSIDE_SERIES"):
                claim("not-handed-off")
            with daily_research_admission(
                prediction_id=frozen.prediction_id, code_sha=frozen.code_sha, config_sha256=sha256(content).hexdigest()
            ):
                with ThreadPoolExecutor(1) as executor:
                    with pytest.raises(ValueError, match="ADMISSION_CONFLICT"):
                        executor.submit(claim, "foreign-thread").result()
                owned = claim("owned-daily")
                assert owned is not None
                guard.before_action()  # Own canonical Attempt is not a foreign worker.
                app.runtime.start_attempt(owned, _context("owned-start"))
                app.runtime.succeed_attempt(owned, result_hash=canonical_json_sha256("completed"), context=_context("owned-complete"))
            with pytest.raises(ValueError, match="OUTSIDE_SERIES"):
                claim("after-handoff")
            with daily_research_admission(prediction_id=frozen.prediction_id, code_sha="0" * 40, config_sha256=sha256(content).hexdigest()):
                with pytest.raises(ValueError, match="OUTSIDE_SERIES"):
                    claim("wrong-code")
            with daily_research_admission(
                prediction_id=frozen.prediction_id, code_sha=frozen.code_sha, config_sha256=sha256(content).hexdigest()
            ):
                guard.connection.close()
                with pytest.raises(ValueError, match="SUPERVISOR"):
                    claim("lost-supervisor")
        trace = app.runtime.inspect_run(frozen.runtime_run_id)
        assert trace.steps[0].state == "SUCCEEDED"
        assert trace.steps[0].attempt_states == ("SUCCEEDED",)
        assert all(not step.attempt_states for step in trace.steps[1:])
