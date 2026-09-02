from __future__ import annotations

import ast
from pathlib import Path
import subprocess
import sys

from market_regime_alpha.infrastructure.postgres.schema import (
    EXPECTED_RESEARCH_VALIDITY_TABLES,
)


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
        "market_regime_alpha.research_qualification",
    )
    for path in (SRC / "selection").rglob("*.py"):
        imported = _imports(path)
        assert not {item for item in imported if item.startswith(forbidden)}, path
    market_imports = {imported for path in (SRC / "market").rglob("*.py") for imported in _imports(path)}
    assert not {item for item in market_imports if item.startswith("market_regime_alpha.selection")}


def test_market_physical_modules_keep_stable_export_files_small() -> None:
    limits = {
        SRC / "market" / "domain" / "__init__.py": 145,
        SRC / "market" / "ports" / "__init__.py": 115,
        SRC / "market" / "application" / "__init__.py": 60,
        SRC / "infrastructure" / "postgres" / "queries" / "market.py": 80,
        SRC / "infrastructure" / "postgres" / "repositories" / "market.py": 40,
    }
    for path, limit in limits.items():
        assert len(path.read_text(encoding="utf-8").splitlines()) <= limit
    market_owned_paths = (
        *tuple((SRC / "market").rglob("*.py")),
        SRC / "infrastructure" / "postgres" / "queries" / "market.py",
        SRC / "infrastructure" / "postgres" / "repositories" / "market.py",
    )
    target_source = "\n".join(
        path.read_text(encoding="utf-8") for path in market_owned_paths
    )
    assert "decision_reference_1455" not in target_source
    assert "DecisionReference" not in target_source
    assert "classify_decision_reference" not in target_source


def test_wp12_preserves_prior_authorities_without_later_authorities() -> None:
    baseline = (SRC / "infrastructure" / "postgres" / "migrations" / "001_baseline.sql").read_text(encoding="utf-8")
    candidate_tables = {
        "candidate_policy",
        "candidate_policy_component",
        "candidate_set",
        "candidate",
        "candidate_score_component",
    }
    for table in candidate_tables:
        assert f"CREATE TABLE mra.{table}" in baseline
    for table in (
        "target_definition",
        "target_checkpoint",
        "target_metric_definition",
        "target_metric_dependency",
        "decision_run",
        "decision_run_target",
        "decision_target_commitment",
        "decision_reference_observation",
    ):
        assert f"CREATE TABLE mra.{table}" in baseline
    for table in (
        "market_target_outcome",
        "market_target_outcome_revision",
        "market_target_outcome_source",
        "market_target_outcome_observation",
        "market_target_outcome_metric",
        "market_target_outcome_metric_reference",
        "market_target_outcome_metric_observation",
        "market_target_outcome_reason",
    ):
        assert f"CREATE TABLE mra.{table}" in baseline
    for table in (
        "evidence_item",
        "evidence_dependency",
        "research_assessment",
        "research_assessment_evaluation",
        "research_assessment_evidence",
        "research_qualification_policy",
        "research_qualification_policy_floor",
        "research_qualification_decision",
        "research_qualification_floor_result",
        "research_qualification_floor_evidence",
    ):
        assert f"CREATE TABLE mra.{table}" in baseline
    for table in (
        "evaluation_dataset",
        "trade_outcome",
    ):
        assert f"CREATE TABLE mra.{table} (" not in baseline
    for table in EXPECTED_RESEARCH_VALIDITY_TABLES:
        assert f"CREATE TABLE mra.{table}" in baseline


def test_candidate_uses_an_independent_narrow_uow() -> None:
    runtime_uow = (SRC / "infrastructure/postgres/uow.py").read_text(
        encoding="utf-8"
    )
    market_uow = (SRC / "infrastructure/postgres/market_uow.py").read_text(
        encoding="utf-8"
    )
    selection_uow = (
        SRC / "infrastructure/postgres/selection_uow.py"
    ).read_text(encoding="utf-8")
    research_uow = (
        SRC / "infrastructure/postgres/research_uow.py"
    ).read_text(encoding="utf-8")
    candidate_uow = (
        SRC / "infrastructure/postgres/candidate_uow.py"
    ).read_text(encoding="utf-8")
    bootstrap = (SRC / "bootstrap.py").read_text(encoding="utf-8")
    assert "def candidates(" not in runtime_uow
    assert "def candidates(" not in market_uow
    assert "def candidates(" not in selection_uow
    assert "def candidates(" not in research_uow
    assert "def candidates(" in candidate_uow
    assert "def research_definitions(" not in candidate_uow
    assert "candidates: CandidateApplication" in bootstrap
    assert "candidate_queries: CandidateQueryProvider" in bootstrap
    assert "PostgresCandidateResearchInputLoader(pool, byte_store)" in bootstrap
    assert "PostgresCandidateUnitOfWorkProvider(pool)" in bootstrap


def test_candidate_surface_contains_no_future_owner_or_framework() -> None:
    candidate_paths = tuple((SRC / "selection").rglob("*candidate*.py"))
    source = "\n".join(path.read_text(encoding="utf-8") for path in candidate_paths)
    prohibited = (
        "CommandBus",
        "Mediator",
        "ServiceLocator",
        "GenericRegistry",
        "ModelVersion",
        "TargetDefinition",
        "QualificationAssessment",
        "DecisionRun",
        "OutcomeAuthority",
        "ExecutionAuthority",
    )
    assert tuple(item for item in prohibited if item in source) == ()


def test_candidate_research_input_adapter_does_not_borrow_research_repository() -> None:
    adapter = (
        SRC
        / "infrastructure"
        / "postgres"
        / "queries"
        / "candidate_research_inputs.py"
    )
    imported = _imports(adapter)
    forbidden_imports = (
        "market_regime_alpha.infrastructure.postgres.repositories.research_definitions",
        "market_regime_alpha.infrastructure.postgres.research_uow",
    )
    assert not {
        item
        for item in imported
        if any(item.startswith(prefix) for prefix in forbidden_imports)
    }
    assert "PostgresResearchDefinitionRepository" not in adapter.read_text(
        encoding="utf-8"
    )
