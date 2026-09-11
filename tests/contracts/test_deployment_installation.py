"""Installed artifact admission is distinct from editable owner integration tests."""

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

import pytest


def test_an_updated_content_hash_is_not_an_installed_handoff():
    from market_regime_alpha.interfaces.deployment_profile import require_installation

    with pytest.raises(ValueError, match="DEPLOYMENT_HANDOFF_REQUIRED"):
        require_installation(SimpleNamespace(version=1, source_sha256="a" * 64))


def test_wheel_installation_requires_exact_bytes_and_complete_roster(tmp_path):
    from market_regime_alpha.interfaces.deployment_profile import verify_package_roster

    root = tmp_path / "market_regime_alpha"
    root.mkdir()
    (root / "__init__.py").write_bytes(b"x = 1\n")
    wheel = tmp_path / "example.whl"
    with ZipFile(wheel, "w") as archive:
        archive.writestr("market_regime_alpha/__init__.py", b"x = 1\n")
        archive.writestr("market_regime_alpha/schema.sql", b"SELECT 1;\n")
    with pytest.raises(ValueError, match="INSTALLED_PACKAGE_MISMATCH"):
        verify_package_roster(wheel, root)
    (root / "schema.sql").write_bytes(b"SELECT 1;\n")
    original = verify_package_roster(wheel, root)
    (root / "schema.sql").write_bytes(b"SELECT 2;\n")
    with pytest.raises(ValueError, match="INSTALLED_PACKAGE_MISMATCH"):
        verify_package_roster(wheel, root)
    (root / "schema.sql").write_bytes(b"SELECT 1;\n")
    (root / "alternate_writer.py").write_bytes(b"pass\n")
    with pytest.raises(ValueError, match="INSTALLED_PACKAGE_MISMATCH"):
        verify_package_roster(wheel, root)
    (root / "alternate_writer.py").unlink()
    assert verify_package_roster(wheel, root) == original


def test_profile_handoff_never_adopts_a_restored_database(request, tmp_path, monkeypatch):
    from market_regime_alpha.interfaces.deployment_profile import prepare_deployment_profile

    settings, _, config = request.getfixturevalue("guarded_scope")
    wrong = replace(config, database_oid=config.database_oid + 1)
    # Package verification has its own real-wheel contract. This counterexample
    # targets scope admission before any profile can be emitted.
    monkeypatch.setattr(
        "market_regime_alpha.interfaces.deployment_profile.inspect_installation",
        lambda **_: {"source_sha": "b" * 40, "source_sha256": config.source_sha256},
    )
    output = tmp_path / "next-profile.json"
    with pytest.raises(ValueError, match="DATABASE_IDENTITY_MISMATCH"):
        prepare_deployment_profile(settings, wrong, wheel=Path("unused.whl"),
            source_checkout=tmp_path, expected_source_sha="b" * 40,
            backup_directory=Path(config.backup_directory), output=output)
    assert not output.exists()


from tests.contracts.market.test_prospective_operation_guard_postgres import guarded_scope  # noqa: E402, F401


@pytest.mark.parametrize("command,existing,accepted", [("settle", False, True), ("predict", True, True), ("predict", False, False)])
def test_cli_handoff_preserves_old_plan_but_cannot_create_old_code_work(tmp_path, monkeypatch, command, existing, accepted):
    from contextlib import nullcontext
    from market_regime_alpha.interfaces.cli import daily
    from market_regime_alpha.interfaces.daily_research import encode_daily_plan
    from tests.contracts.research_qualification.test_daily_prediction import plan

    frozen = plan()
    content = encode_daily_plan(frozen)
    path = tmp_path / "plan.json"
    path.write_bytes(content)
    observed = []
    app = SimpleNamespace(daily_prediction_reads=SimpleNamespace(
        run_plan_content=lambda _: content if existing else None,
        validate_configuration=lambda p: observed.append(p),
    ))
    guard = SimpleNamespace(verify_startup=lambda _: None, before_action=lambda: None)
    config = SimpleNamespace(code_sha="f" * 40, worker_id="installed-worker")
    monkeypatch.setattr(daily, "load_operation_config", lambda _: config)
    monkeypatch.setattr(daily, "require_installation", lambda _: None)
    monkeypatch.setattr(daily, "operational_session", lambda *_: nullcontext(guard))
    monkeypatch.setattr(daily, "bootstrap_application", lambda *_: nullcontext(app))
    monkeypatch.setattr(daily, "daily_research_admission", lambda **_: nullcontext())
    def execute(_self, p, **_kwargs):
        observed.append(p)
        return {"state": "OWNER_CALLED", "prediction_id": p.prediction_id}
    monkeypatch.setattr(daily.DailyResearchOperations, "execute", execute)
    monkeypatch.setattr(daily.DailyResearchOperations, "settle_and_evaluate", execute)
    args = SimpleNamespace(research_command="daily", daily_command=command, plan=path, operation_config=path, maximum_steps=1)
    if accepted:
        assert daily.dispatch_daily(args, None)["prediction_id"] == frozen.prediction_id
        assert observed == [frozen, frozen]
    else:
        with pytest.raises(ValueError, match="DAILY_CODE_IDENTITY_MISMATCH"):
            daily.dispatch_daily(args, None)
        assert observed == []


def test_retired_research_runners_are_not_importable():
    from importlib.util import find_spec
    from market_regime_alpha.application.continuous_research import scheduler

    assert find_spec("market_regime_alpha.application.continuous_research.runner") is None
    assert find_spec("market_regime_alpha.application.continuous_research.free_data_runtime") is None
    assert not hasattr(scheduler, "ContinuousResearchScheduleRunner")


def test_backup_from_another_schema_revision_cannot_activate_same_database(request):
    import json
    from hashlib import sha256
    from market_regime_alpha.interfaces.prospective_operation_guard import operational_session

    settings, snapshot, config = request.getfixturevalue("guarded_scope")
    bundle = Path(config.backup_directory)
    inventory = json.loads((bundle / "inventory.json").read_bytes())
    inventory["schema"]["catalog_checksum"] = "0" * 64
    payload = json.dumps(inventory, sort_keys=True).encode()
    (bundle / "inventory.json").write_bytes(payload)
    receipt = json.loads((bundle / "receipt.json").read_bytes())
    receipt["inventory_sha256"] = sha256(payload).hexdigest()
    content = json.dumps(receipt, sort_keys=True).encode()
    (bundle / "receipt.json").write_bytes(content)
    config = replace(config, backup_receipt_sha256=sha256(content).hexdigest())
    with operational_session(settings, config) as guard:
        with pytest.raises(ValueError, match="BACKUP_SCHEMA_MISMATCH"):
            guard.verify_backup(snapshot)
