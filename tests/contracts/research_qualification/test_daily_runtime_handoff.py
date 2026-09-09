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
from tests.contracts.market.test_prospective_operation_guard_postgres import guarded_scope  # noqa: F401
from tests.contracts.research_qualification.test_daily_prediction import plan
from tests.contracts.test_runtime_postgres import _context


def test_daily_service_import_does_not_depend_on_bootstrap_import_order():
    import subprocess
    subprocess.run(
        ["uv", "run", "--no-sync", "python", "-c",
         "from market_regime_alpha.interfaces.daily_service import daily_tick; "
         "from market_regime_alpha.interfaces.daily_collection import DailyCollectionPlan"],
        check=True, capture_output=True, text=True, timeout=15,
    )


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
            ScheduleSpec(schedule_id, "daily-model-" + frozen.experimental_model_use_id.hex, 1, RuntimeMode.SHADOW, None, "Asia/Shanghai", "a" * 64, True),
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
                interrupted = claim("owned-before-supervisor-loss")
                assert interrupted is not None
                guard.connection.close()
                with pytest.raises(ValueError, match="SUPERVISOR"):
                    claim("lost-supervisor")
        trace = app.runtime.inspect_run(frozen.runtime_run_id)
        assert trace.steps[0].state == "SUCCEEDED"
        assert trace.steps[0].attempt_states == ("SUCCEEDED",)
        assert len(trace.steps[1].attempt_states) == 1
        import time
        time.sleep(2.05)  # Synthetic lease expiry, not a future market window.
        with operational_session(settings, config) as recovered:
            with pytest.raises(ValueError, match="ACTIVE_ATTEMPT_CONFLICT"):
                recovered.before_action()
            recovered.session.allow_expired_daily_recovery(frozen.experimental_model_use_id, frozen.code_sha)
            recovered.before_action()
            with pytest.raises(ValueError, match="OUTSIDE_SERIES"):
                claim("recovery-is-not-claim-permission")
            with daily_research_admission(prediction_id=frozen.prediction_id, code_sha=frozen.code_sha, config_sha256=sha256(content).hexdigest()):
                app.runtime.recover_expired(actor_id="same-text", reason_code="DAILY_RESTART", run_id=frozen.runtime_run_id)
                next_claim = claim("restarted-own-scope")
                assert next_claim is not None and next_claim.attempt_id != interrupted.attempt_id
                recovered.before_action()


def test_expired_old_outcome_recovery_requires_its_original_plan_after_model_handoff(request):
    import time
    from uuid import uuid5
    from market_regime_alpha.infrastructure.postgres.prospective_operation_session import daily_research_admission
    from market_regime_alpha.runtime.domain import StepSpec, RetryPolicy, ExternalEffectClass

    settings, _, config = request.getfixturevalue("guarded_scope")
    frozen = plan()
    content = encode_daily_plan(frozen)
    digest = sha256(content).hexdigest()
    with bootstrap_application(settings) as app:
        artifact = app.artifacts.publish(content, media_type="application/json", context=_context("old-plan"))
        schedule_id = uuid4()
        app.runtime.create_schedule(
            ScheduleSpec(schedule_id, "daily-outcome-" + frozen.experimental_model_use_id.hex, 1,
                         RuntimeMode.SHADOW, None, "Asia/Shanghai", "a" * 64, True), _context("old-schedule"))
        step = StepSpec("settle", "SETTLE_OUTCOME", "research.daily_outcome.settle", "1", 1, True,
                        "b" * 64, None, RetryPolicy(3, (), frozenset()), ExternalEffectClass.NONE)
        parent = RunSpec(frozen.runtime_run_id, schedule_id, "parent", RuntimeMode.SHADOW,
                         frozen.decision_time, frozen.decision_time, frozen.code_sha, artifact.artifact_id, artifact.content_sha256)
        app.runtime.schedule_run(parent, (step,), (), _context("old-parent"))
        run_id = uuid5(frozen.prediction_id, "outcome-evaluation-runtime")
        app.runtime.schedule_run(
            RunSpec(run_id, schedule_id, "daily-outcome:" + str(frozen.prediction_id), RuntimeMode.SHADOW,
                    frozen.decision_time, frozen.decision_time, frozen.code_sha, artifact.artifact_id,
                    artifact.content_sha256, parent_run_id=frozen.runtime_run_id),
            (step,), (), _context("old-outcome"))
        app.runtime.start_run(run_id, _context("old-start"))
        with operational_session(settings, config):
            with daily_research_admission(prediction_id=frozen.prediction_id, code_sha=frozen.code_sha, config_sha256=digest):
                abandoned = app.runtime.claim_next(run_id=run_id, worker_id="old-worker",
                    lease_duration=timedelta(seconds=1), context=_context("old-claim"))
        assert abandoned is not None
        time.sleep(1.05)
        with operational_session(settings, config) as guard:
            guard.session.allow_expired_daily_recovery(uuid4(), "e" * 40)
            with pytest.raises(ValueError, match="ACTIVE_ATTEMPT_CONFLICT"):
                guard.before_action()
            guard.session.allow_frozen_daily_recovery(prediction_id=frozen.prediction_id, code_sha=frozen.code_sha, config_sha256="0" * 64)
            with pytest.raises(ValueError, match="ACTIVE_ATTEMPT_CONFLICT"):
                guard.before_action()
            guard.session.allow_frozen_daily_recovery(prediction_id=frozen.prediction_id, code_sha=frozen.code_sha, config_sha256=digest)
            guard.before_action()
            with pytest.raises(ValueError, match="OUTSIDE_SERIES"):
                app.runtime.recover_expired(actor_id="new-worker", reason_code="RESTART", run_id=run_id)
            with daily_research_admission(prediction_id=frozen.prediction_id, code_sha=frozen.code_sha, config_sha256=digest):
                assert app.runtime.recover_expired(actor_id="new-worker", reason_code="RESTART", run_id=run_id) == (abandoned.attempt_id,)
                assert app.runtime.recover_expired(actor_id="new-worker", reason_code="RESTART", run_id=run_id) == ()
        assert app.runtime.inspect_run(run_id).code_sha == frozen.code_sha
