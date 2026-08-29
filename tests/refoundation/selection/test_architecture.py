from __future__ import annotations

import ast
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src" / "market_regime_alpha"


def _imports(path: Path) -> set[str]:
    result: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            result.update(item.name for item in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            result.add(node.module)
    return result


def test_selection_has_a_permanent_namespace_and_does_not_execute_legacy_universe() -> None:
    assert (SRC / "selection" / "__init__.py").is_file()
    assert not any(path.name.startswith(("v2", "next", "new_")) for path in (SRC / "selection").iterdir())
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import market_regime_alpha.selection; assert 'market_regime_alpha.universe' not in sys.modules",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert probe.returncode == 0, probe.stderr


def test_selection_domain_application_and_ports_do_not_cross_forbidden_boundaries() -> None:
    forbidden = (
        "market_regime_alpha.universe",
        "market_regime_alpha.state",
        "market_regime_alpha.candidate",
        "market_regime_alpha.persistence",
        "market_regime_alpha.infrastructure.postgres",
    )
    for path in (SRC / "selection").rglob("*.py"):
        imported = _imports(path)
        assert not {item for item in imported if item.startswith(forbidden)}, path
    market_imports = {imported for path in (SRC / "market").rglob("*.py") for imported in _imports(path)}
    assert not {item for item in market_imports if item.startswith("market_regime_alpha.selection")}


def test_market_physical_modules_keep_stable_export_files_small() -> None:
    limits = {
        SRC / "market" / "domain" / "__init__.py": 120,
        SRC / "market" / "ports" / "__init__.py": 80,
        SRC / "market" / "application" / "__init__.py": 40,
        SRC / "infrastructure" / "postgres" / "queries" / "market.py": 80,
        SRC / "infrastructure" / "postgres" / "repositories" / "market.py": 40,
    }
    for path, limit in limits.items():
        assert len(path.read_text(encoding="utf-8").splitlines()) <= limit
    target_source = "\n".join(
        path.read_text(encoding="utf-8")
        for base in (
            SRC / "market",
            SRC / "infrastructure" / "postgres" / "queries",
        )
        for path in base.rglob("*.py")
    )
    assert "decision_reference_1455" not in target_source
    assert "DecisionReference" not in target_source
    assert "classify_decision_reference" not in target_source


def test_candidate_and_future_research_authority_are_not_stubbed_in_target_schema() -> None:
    baseline = (SRC / "infrastructure" / "postgres" / "migrations" / "001_baseline.sql").read_text(encoding="utf-8")
    for table in (
        "candidate_set",
        "candidate",
        "evaluation_dataset",
        "research_evidence",
        "qualification_assessment",
        "model",
        "model_version",
        "decision_run",
    ):
        assert f"CREATE TABLE mra.{table}" not in baseline
