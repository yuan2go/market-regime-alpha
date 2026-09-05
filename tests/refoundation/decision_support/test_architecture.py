from __future__ import annotations

import ast
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "src" / "market_regime_alpha"
DECISION_SUPPORT = PACKAGE / "decision_support"


def _imports(path: Path) -> set[str]:
    imported: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            imported.update(item.name for item in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)
    return imported


def _matches(module: str, forbidden: str) -> bool:
    return module == forbidden or module.startswith(f"{forbidden}.")


def test_decision_support_is_permanent_and_does_not_load_legacy_decision() -> None:
    assert (DECISION_SUPPORT / "domain").is_dir()
    assert (DECISION_SUPPORT / "application").is_dir()
    assert (DECISION_SUPPORT / "ports").is_dir()
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import market_regime_alpha.decision_support; "
                "assert 'market_regime_alpha.decision' not in sys.modules; "
                "assert 'market_regime_alpha.daily_decision' not in sys.modules; "
                "assert 'market_regime_alpha.legacy' not in sys.modules"
            ),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert probe.returncode == 0, probe.stderr


def test_decision_domain_and_ports_have_no_infrastructure_or_owner_leakage() -> None:
    forbidden = (
        "market_regime_alpha.infrastructure",
        "market_regime_alpha.persistence",
        "market_regime_alpha.market",
        "market_regime_alpha.selection",
        "market_regime_alpha.research_qualification",
        "market_regime_alpha.decision",
        "market_regime_alpha.daily_decision",
        "market_regime_alpha.legacy",
    )
    violations = tuple(
        f"{path.relative_to(PACKAGE)} -> {module}"
        for layer in ("domain", "ports")
        for path in (DECISION_SUPPORT / layer).glob("*.py")
        for module in _imports(path)
        if any(_matches(module, item) for item in forbidden)
    )
    assert violations == ()


def test_decision_application_depends_only_on_owned_model_ports_and_runtime_contract() -> None:
    forbidden = (
        "market_regime_alpha.infrastructure",
        "market_regime_alpha.persistence",
        "market_regime_alpha.market",
        "market_regime_alpha.selection",
        "market_regime_alpha.research_qualification",
        "market_regime_alpha.decision",
        "market_regime_alpha.daily_decision",
        "market_regime_alpha.legacy",
    )
    violations = tuple(
        f"{path.relative_to(PACKAGE)} -> {module}"
        for path in (DECISION_SUPPORT / "application").glob("*.py")
        for module in _imports(path)
        if any(_matches(module, item) for item in forbidden)
    )
    assert violations == ()


def test_decision_postgres_adapters_do_not_import_other_owner_repositories() -> None:
    adapter_files = (
        PACKAGE / "infrastructure/postgres/decision_uow.py",
        PACKAGE / "infrastructure/postgres/queries/decision_inputs.py",
        PACKAGE / "infrastructure/postgres/queries/decision_runs.py",
        PACKAGE / "infrastructure/postgres/queries/decision_verification.py",
        PACKAGE / "infrastructure/postgres/repositories/decision_runs.py",
    )
    forbidden = (
        "market_regime_alpha.infrastructure.postgres.repositories.candidate",
        "market_regime_alpha.infrastructure.postgres.repositories.market",
        "market_regime_alpha.infrastructure.postgres.repositories.target_definitions",
        "market_regime_alpha.infrastructure.postgres.candidate_uow",
        "market_regime_alpha.infrastructure.postgres.market_uow",
        "market_regime_alpha.infrastructure.postgres.target_uow",
        "market_regime_alpha.legacy",
    )
    violations = tuple(
        f"{path.relative_to(PACKAGE)} -> {module}"
        for path in adapter_files
        for module in _imports(path)
        if any(_matches(module, item) for item in forbidden)
    )
    assert violations == ()


def test_decision_support_has_narrow_uow_wiring_and_no_future_authority() -> None:
    runtime_uow = (PACKAGE / "infrastructure/postgres/uow.py").read_text(
        encoding="utf-8"
    )
    decision_uow = (
        PACKAGE / "infrastructure/postgres/decision_uow.py"
    ).read_text(encoding="utf-8")
    bootstrap = (PACKAGE / "bootstrap.py").read_text(encoding="utf-8")
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in DECISION_SUPPORT.rglob("*.py")
    )
    assert "def decision_runs(" not in runtime_uow
    assert "def decision_runs(" in decision_uow
    assert "def target_definitions(" not in decision_uow
    assert "def candidates(" not in decision_uow
    assert "PostgresDecisionSupportUnitOfWorkProvider(pool)" in bootstrap
    assert "decision_support_application = DecisionSupportApplication(" in bootstrap
    assert bootstrap.count("DecisionSupportApplication(") == 1
    # Generic Backtest actions and TargetApplication share the same owner.
    assert bootstrap.count("decision_support=decision_support_application,") == 2
    prohibited = (
        "MarketTargetOutcome",
        "GenericSubjectRegistry",
        "CompatibilityFacade",
        "ExperimentRepository",
        "EvaluationRepository",
    )
    assert tuple(item for item in prohibited if item in source) == ()


def test_replay_adapter_contains_no_provider_or_unrestricted_latest_lookup() -> None:
    verification = (
        PACKAGE / "infrastructure/postgres/queries/decision_verification.py"
    ).read_text(encoding="utf-8")
    query = (
        PACKAGE / "infrastructure/postgres/queries/decision_runs.py"
    ).read_text(encoding="utf-8")
    combined = verification + query
    assert "MarketApplication" not in combined
    assert "MarketProvider" not in combined
    assert "LIMIT 1" not in combined
    assert "UPDATE mra." not in combined
    assert "INSERT INTO mra." not in combined
    assert "DELETE FROM mra." not in combined
