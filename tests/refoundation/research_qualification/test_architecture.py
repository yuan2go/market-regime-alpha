from __future__ import annotations

import ast
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "src" / "market_regime_alpha"
RESEARCH = PACKAGE / "research_qualification"


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


def test_research_qualification_is_permanent_and_does_not_execute_legacy_planes() -> None:
    assert (RESEARCH / "__init__.py").is_file()
    assert not any(
        path.name.startswith(("v2", "next", "new_")) for path in RESEARCH.iterdir()
    )
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import market_regime_alpha.research_qualification; "
                "assert 'market_regime_alpha.research' not in sys.modules; "
                "assert 'market_regime_alpha.features' not in sys.modules; "
                "assert 'market_regime_alpha.candidates' not in sys.modules"
            ),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert probe.returncode == 0, probe.stderr


def test_research_domain_application_and_ports_do_not_cross_forbidden_boundaries() -> None:
    forbidden = (
        "market_regime_alpha.research",
        "market_regime_alpha.features",
        "market_regime_alpha.candidates",
        "market_regime_alpha.persistence",
        "market_regime_alpha.infrastructure",
        "market_regime_alpha.market",
        "market_regime_alpha.selection",
    )
    violations = tuple(
        f"{path.relative_to(PACKAGE)} -> {module}"
        for path in RESEARCH.rglob("*.py")
        for module in _imports(path)
        if any(_matches(module, item) for item in forbidden)
    )
    assert violations == ()


def test_research_uses_an_independent_narrow_uow_and_target_composes_it() -> None:
    runtime_uow = (PACKAGE / "infrastructure/postgres/uow.py").read_text(
        encoding="utf-8"
    )
    market_uow = (PACKAGE / "infrastructure/postgres/market_uow.py").read_text(
        encoding="utf-8"
    )
    selection_uow = (
        PACKAGE / "infrastructure/postgres/selection_uow.py"
    ).read_text(encoding="utf-8")
    research_uow = (
        PACKAGE / "infrastructure/postgres/research_uow.py"
    ).read_text(encoding="utf-8")
    bootstrap = (PACKAGE / "bootstrap.py").read_text(encoding="utf-8")
    assert "def research_definitions(" not in runtime_uow
    assert "def research_definitions(" not in market_uow
    assert "def research_definitions(" not in selection_uow
    assert "def research_definitions(" in research_uow
    assert "def runtime(" not in research_uow
    assert "def candidates(" not in research_uow
    assert "research_definitions: ResearchQualificationApplication" in bootstrap
    assert "PostgresResearchUnitOfWorkProvider(pool)" in bootstrap


def test_research_core_contains_no_generic_framework_or_cross_owner_shortcut() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8") for path in RESEARCH.rglob("*.py")
    )
    prohibited = (
        "CommandBus",
        "Mediator",
        "WorkflowEngine",
        "ServiceLocator",
        "GenericRegistry",
        "QualificationAssessment",
        "CandidateSet",
    )
    assert tuple(item for item in prohibited if item in source) == ()
    feature_fields = ast.parse(
        (RESEARCH / "domain/model.py").read_text(encoding="utf-8")
    )
    feature_class = next(
        item
        for item in feature_fields.body
        if isinstance(item, ast.ClassDef) and item.name == "FeatureDefinition"
    )
    field_names = {
        node.target.id
        for node in feature_class.body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    }
    assert "dependencies" not in field_names


def test_research_stable_export_files_remain_small() -> None:
    limits = {
        RESEARCH / "__init__.py": 20,
        RESEARCH / "application/__init__.py": 40,
        RESEARCH / "domain/__init__.py": 120,
        RESEARCH / "ports/__init__.py": 120,
    }
    for path, limit in limits.items():
        assert len(path.read_text(encoding="utf-8").splitlines()) <= limit


def test_research_application_facade_does_not_become_a_god_service() -> None:
    facade = (RESEARCH / "application/service.py").read_text(encoding="utf-8")
    assert len(facade.splitlines()) <= 140
    assert "with self._uow_provider()" not in facade
    assert "target_uow_provider: TargetUnitOfWorkProvider" in facade
    assert "TargetDefinitionCommands(\n            target_uow_provider" in facade
    assert (RESEARCH / "application/feature_definitions.py").is_file()
    assert (RESEARCH / "application/datasets.py").is_file()
    assert (RESEARCH / "application/_dataset_validation.py").is_file()
    assert (RESEARCH / "application/target_definitions.py").is_file()
