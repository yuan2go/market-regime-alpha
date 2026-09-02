from __future__ import annotations

import ast
from pathlib import Path

from market_regime_alpha.infrastructure.postgres.schema import (
    EXPECTED_RESEARCH_VALIDITY_TABLES,
)


ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "src" / "market_regime_alpha" / "outcome"
POSTGRES = ROOT / "src" / "market_regime_alpha" / "infrastructure" / "postgres"


def _imports(path: Path) -> set[str]:
    result: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            result.update(item.name for item in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            result.add(node.module)
    return result


def test_outcome_is_a_permanent_deep_bounded_context() -> None:
    assert {
        path.name
        for path in PACKAGE.iterdir()
        if path.is_dir() and not path.name.startswith("__")
    } == {
        "application",
        "domain",
        "ports",
    }
    for relative in (
        "application/__init__.py",
        "domain/__init__.py",
        "ports/__init__.py",
        "errors.py",
    ):
        assert (PACKAGE / relative).is_file()
    public_surface = (PACKAGE / "__init__.py").read_text(encoding="utf-8")
    assert "OutcomeReadPort" in public_surface
    assert "OutcomeSnapshot" in public_surface
    assert "calculate_market_target_outcome" not in public_surface
    assert "OutcomeApplication" not in public_surface


def test_outcome_domain_application_and_ports_do_not_cross_owner_boundaries() -> None:
    forbidden = (
        "market_regime_alpha.infrastructure",
        "market_regime_alpha.market",
        "market_regime_alpha.decision_support",
        "market_regime_alpha.research_qualification",
        "market_regime_alpha.selection",
        "market_regime_alpha.legacy",
        "market_regime_alpha.persistence",
    )
    for path in PACKAGE.rglob("*.py"):
        imports = _imports(path)
        assert not {
            imported
            for imported in imports
            if imported.startswith(forbidden)
        }, path


def test_pure_numerical_kernel_has_no_io_or_runtime_dependency() -> None:
    imports = _imports(PACKAGE / "domain" / "kernel.py")
    forbidden = (
        "psycopg",
        "pathlib",
        "requests",
        "httpx",
        "market_regime_alpha.infrastructure",
        "market_regime_alpha.runtime",
    )
    assert not {
        imported for imported in imports if imported.startswith(forbidden)
    }
    source = (PACKAGE / "domain" / "kernel.py").read_text(encoding="utf-8")
    assert "open(" not in source
    assert "latest" not in source.lower()
    assert "current" not in source.lower()


def test_outcome_postgres_adapters_have_no_provider_or_legacy_dependency() -> None:
    paths = (
        POSTGRES / "outcome_uow.py",
        POSTGRES / "queries" / "outcome_inputs.py",
        POSTGRES / "queries" / "outcomes.py",
        POSTGRES / "queries" / "outcome_verification.py",
        POSTGRES / "repositories" / "outcomes.py",
    )
    forbidden = (
        "market_regime_alpha.legacy",
        "market_regime_alpha.providers",
        "market_regime_alpha.daily_research",
        "market_regime_alpha.daily_decision",
    )
    for path in paths:
        imports = _imports(path)
        assert not {
            imported
            for imported in imports
            if imported.startswith(forbidden)
        }, path
    preparation = (POSTGRES / "queries" / "outcome_inputs.py").read_text(
        encoding="utf-8"
    )
    assert "ProviderClient" not in preparation
    assert "latest_bar" not in preparation
    assert "current_bar" not in preparation


def test_wp10_boundary_now_admits_wp11_and_wp12_but_no_later_authority_tables() -> None:
    baseline = (POSTGRES / "migrations" / "001_baseline.sql").read_text(
        encoding="utf-8"
    )
    for table in EXPECTED_RESEARCH_VALIDITY_TABLES:
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
        "model",
        "model_version",
        "context",
    ):
        assert f"CREATE TABLE mra.{table}" not in baseline
