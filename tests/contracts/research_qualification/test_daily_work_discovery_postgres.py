"""Real Runtime rows beyond page limits; fixture identities carry no market proof."""

from dataclasses import replace
from datetime import timedelta
from io import StringIO
import json
from uuid import UUID, uuid5

from market_regime_alpha.bootstrap import TargetSettings, bootstrap_application, bootstrap_database
from market_regime_alpha.interfaces.cli import main
from market_regime_alpha.interfaces.daily_research import encode_daily_plan
from market_regime_alpha.runtime.domain import ExternalEffectClass, RetryPolicy, RunSpec, RuntimeMode, ScheduleSpec, StepSpec
from tests.contracts.research_qualification.test_daily_prediction import plan
from tests.contracts.test_runtime_postgres import _context


def test_keyset_pages_and_cli_keep_all_work_across_uses_without_scan_truncation(target_database_url, tmp_path):
    settings = TargetSettings(target_database_url, tmp_path / "artifacts")
    bootstrap_database(settings)
    base = plan()
    expected = []
    with bootstrap_application(settings) as app:
        for index in range(130):
            frozen = replace(base, prediction_id=UUID(int=1000+index), experimental_model_use_id=UUID(int=2000+index%2))
            schedule_id = uuid5(frozen.experimental_model_use_id, "daily-outcome-schedule")
            app.runtime.create_schedule(ScheduleSpec(schedule_id, "daily-outcome-" + frozen.experimental_model_use_id.hex,
                1, RuntimeMode.SHADOW, None, "UTC", "a"*64, True), _context("schedule:" + str(index%2)))
            artifact = app.artifacts.publish(encode_daily_plan(frozen), media_type="application/json", context=_context("plan:" + str(index)))
            publication_schedule = uuid5(frozen.experimental_model_use_id, "daily-publication-schedule")
            app.runtime.create_schedule(ScheduleSpec(publication_schedule, "daily-model-" + frozen.experimental_model_use_id.hex,
                1, RuntimeMode.SHADOW, None, "UTC", "a"*64, True), _context("publication-schedule:" + str(index%2)))
            app.runtime.schedule_run(RunSpec(frozen.runtime_run_id, publication_schedule, "daily-model:" + str(frozen.prediction_id),
                RuntimeMode.SHADOW, frozen.decision_time + timedelta(seconds=index), frozen.decision_time,
                frozen.code_sha, artifact.artifact_id, artifact.content_sha256),
                (StepSpec("publication", "RECORD_EVIDENCE", "research.daily.fixture", "1", 1, True, "b"*64, None,
                          RetryPolicy(1, (), frozenset()), ExternalEffectClass.NONE),), (), _context("publication:" + str(index)))
            run_id = uuid5(frozen.prediction_id, "outcome-evaluation-runtime")
            expected.append(run_id)
            app.runtime.schedule_run(RunSpec(run_id, schedule_id, "daily-outcome:" + str(frozen.prediction_id), RuntimeMode.SHADOW,
                frozen.decision_time + timedelta(seconds=index), frozen.decision_time, frozen.code_sha,
                artifact.artifact_id, artifact.content_sha256, parent_run_id=frozen.runtime_run_id),
                (StepSpec("settle-fixture", "SETTLE_OUTCOME", "research.daily_outcome.fixture", "1", 1, True, "b"*64, None,
                          RetryPolicy(1, (), frozenset()), ExternalEffectClass.NONE),), (), _context("run:" + str(index)))
        cursor, observed, sizes = None, [], []
        while True:
            page = app.daily_prediction_reads.outcome_work_items(limit=64, after=cursor)
            observed.extend(item.run_id for item in page)
            sizes.append(len(page))
            if len(page) < 64:
                break
            cursor = page[-1].cursor
        assert observed == expected and sizes == [64, 64, 2]
        assert app.daily_prediction_reads.outcome_work_counts() == {"QUEUED": 130}
        ledger = app.daily_prediction_reads.operational_ledger_rows()
        assert len(ledger["runs"]) == 256 and ledger["history_truncated"] is True
        assert ledger["complete_runtime_counts"] == [
            {"work_kind": "model", "state": "QUEUED", "count": 130},
            {"work_kind": "outcome", "state": "QUEUED", "count": 130}]
        assert {row["run_id"] for row in ledger["runs"] if row["parent_run_id"] is not None} == set(expected[2:])
        assert len(app.daily_prediction_reads.operational_ledger_rows(complete_history=True)["runs"]) == 260
    output = StringIO()
    assert main(["research", "daily", "backlog", "--page-size", "64"],
        environ={"MRA_DATABASE_URL": target_database_url, "MRA_ARTIFACT_ROOT": str(settings.artifact_root)}, stdout=output) == 0
    payload = json.loads(output.getvalue())
    assert len(payload["items"]) == 64 and payload["complete_runtime_counts"] == {"QUEUED": 130}
    assert payload["next_cursor"][2] == str(expected[63])
    assert payload["business_writes"] == 0
