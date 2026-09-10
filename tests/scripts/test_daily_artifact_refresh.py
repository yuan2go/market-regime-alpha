"""Daily static input references must participate in the existing integrity refresh."""

import importlib.util
from dataclasses import replace
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
import pytest
from market_regime_alpha.interfaces.daily_research import encode_daily_plan

from tests.contracts.research_qualification.test_daily_prediction import plan as example_plan


def test_refresh_includes_daily_static_sources_once_without_relabeling_capture(monkeypatch):
    path = Path(__file__).resolve().parents[2] / "docs/operations/templates/verify_prospective_artifacts.py"
    spec = importlib.util.spec_from_file_location("daily_artifact_refresh_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original, instrument, membership, completed_source = uuid4(), uuid4(), uuid4(), uuid4()
    observations = []

    class Connection:
        def transaction(self):
            return nullcontext()

        def execute(self, query, parameters):
            if "WITH generations AS" in query:
                return SimpleNamespace(fetchall=lambda: [(original,)])
            if isinstance(parameters, dict):
                assert parameters["target"] == plan.target_definition_id
                assert len(parameters["runs"]) == 2
                assert plan.code_artifact.artifact_id in parameters["plan_artifacts"]
                return SimpleNamespace(fetchall=lambda: [(original,)])
            assert parameters[0] == [instrument]
            if "bar.timeframe='DAILY'" in query and completed_plan.input_session_id in parameters[2]:
                return SimpleNamespace(fetchall=lambda: [(completed_source,)])
            return SimpleNamespace(fetchall=lambda: [(membership,), (original,)])

    guard = SimpleNamespace(connection=Connection(), before_action=lambda: None)

    def verify(artifact_id, **kwargs):
        observations.append(artifact_id)
        return SimpleNamespace(result="VERIFIED", verification_id=uuid4())

    plan = replace(example_plan(), instrument_ids=(instrument,),
        classification_scheme="INDEX_MEMBERSHIP", classification_code="CSI300", provider_product_id=uuid4()
    )
    completed_plan = replace(plan, prediction_id=uuid4(), input_session_id=uuid4())
    published_row = {"state": "SUCCEEDED", "schedule_code": "daily-model-original",
                     "plan_content": encode_daily_plan(completed_plan),
                     "run_id": completed_plan.runtime_run_id, "code_sha": completed_plan.code_sha}
    reads = SimpleNamespace(current_sessions=lambda: (plan.input_session_id, plan.target_session_id, plan.decision_time),
                            outcome_work_items=lambda **_: (), collection_rounds=lambda *_: (),
                            operational_ledger_rows=lambda: {"runs": [published_row]})
    monkeypatch.setattr(module, "bootstrap_application", lambda _: nullcontext(SimpleNamespace(artifacts=SimpleNamespace(verify=verify), daily_prediction_reads=reads)))
    module.verify_scope(None, SimpleNamespace(series_code="daily", actor_id="operator"), guard, "observation", daily_plan=plan)
    assert set(observations) == {original, membership, completed_source}
    assert len(observations) == 3
    for bad in ({"plan_content": None}, {"run_id": uuid4()}, {"code_sha": "f" * 40}):
        observations.clear()
        reads.operational_ledger_rows = lambda: {"runs": [{**published_row, **bad}]}
        with pytest.raises(ValueError, match="PUBLISHED_PLAN"):
            module.verify_scope(None, SimpleNamespace(series_code="daily", actor_id="operator"), guard, "bad", daily_plan=plan)
        assert observations == []
