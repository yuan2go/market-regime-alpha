"""Daily static input references must participate in the existing integrity refresh."""

import importlib.util
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4


def test_refresh_includes_daily_static_sources_once_without_relabeling_capture(monkeypatch):
    path = Path(__file__).resolve().parents[2] / "docs/operations/templates/verify_prospective_artifacts.py"
    spec = importlib.util.spec_from_file_location("daily_artifact_refresh_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original, instrument, membership = uuid4(), uuid4(), uuid4()
    observations = []

    class Connection:
        def transaction(self):
            return nullcontext()

        def execute(self, query, parameters):
            if "WITH generations AS" in query:
                return SimpleNamespace(fetchall=lambda: [(original,)])
            assert parameters[0] == [instrument]
            return SimpleNamespace(fetchall=lambda: [(membership,), (original,)])

    guard = SimpleNamespace(connection=Connection(), before_action=lambda: None)

    def verify(artifact_id, **kwargs):
        observations.append(artifact_id)
        return SimpleNamespace(result="VERIFIED", verification_id=uuid4())

    monkeypatch.setattr(module, "bootstrap_application", lambda _: nullcontext(SimpleNamespace(artifacts=SimpleNamespace(verify=verify))))
    plan = SimpleNamespace(
        instrument_ids=(instrument,), classification_scheme="INDEX_MEMBERSHIP", classification_code="CSI300", provider_product_id=uuid4()
    )
    module.verify_scope(None, SimpleNamespace(series_code="daily", actor_id="operator"), guard, "observation", daily_plan=plan)
    assert set(observations) == {original, membership}
    assert len(observations) == 2
