from __future__ import annotations

import ast
from pathlib import Path


PACKAGE = Path(__file__).parents[2] / "src" / "market_regime_alpha"
TARGET_ROOTS = (
    PACKAGE / "shared",
    PACKAGE / "runtime",
    PACKAGE / "market",
    PACKAGE / "infrastructure",
    PACKAGE / "interfaces",
    PACKAGE / "bootstrap.py",
)


def _python_files(root: Path) -> tuple[Path, ...]:
    return (root,) if root.is_file() else tuple(sorted(root.rglob("*.py")))


def _imports(root: Path) -> tuple[tuple[Path, str], ...]:
    result: list[tuple[Path, str]] = []
    for source_file in _python_files(root):
        tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                result.extend((source_file, item.name) for item in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                result.append((source_file, node.module))
    return tuple(result)


def test_target_packages_never_import_old_runtime_or_persistence_planes() -> None:
    forbidden = (
        "market_regime_alpha.application",
        "market_regime_alpha.core",
        "market_regime_alpha.persistence",
        "market_regime_alpha.platform",
        "market_regime_alpha.legacy",
        "market_regime_alpha.migration",
        "market_regime_alpha.daily_research",
        "market_regime_alpha.daily_decision",
        "market_regime_alpha.dividend_t",
    )
    violations = tuple(
        f"{source_file.relative_to(PACKAGE)} -> {module}"
        for root in TARGET_ROOTS
        for source_file, module in _imports(root)
        if module.startswith(forbidden)
    )
    assert violations == ()


def test_domain_imports_only_standard_library_shared_and_own_domain() -> None:
    violations = tuple(
        f"{source_file.relative_to(PACKAGE)} -> {module}"
        for source_file, module in _imports(PACKAGE / "runtime" / "domain")
        if module.startswith("market_regime_alpha.")
        and not module.startswith(
            ("market_regime_alpha.shared", "market_regime_alpha.runtime.domain")
        )
    )
    assert violations == ()


def test_market_domain_and_ports_do_not_depend_on_infrastructure_or_legacy_market_planes() -> None:
    forbidden = (
        "market_regime_alpha.infrastructure",
        "market_regime_alpha.data",
        "market_regime_alpha.market_data",
        "market_regime_alpha.persistence",
        "market_regime_alpha.application",
        "market_regime_alpha.migration",
    )
    violations = tuple(
        f"{source_file.relative_to(PACKAGE)} -> {module}"
        for root in (PACKAGE / "market" / "domain", PACKAGE / "market" / "ports")
        for source_file, module in _imports(root)
        if module.startswith(forbidden)
    )
    assert violations == ()


def test_market_application_has_no_repository_factory_service_locator_or_legacy_fallback() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in _python_files(PACKAGE / "market")
    )
    forbidden_tokens = (
        "RepositoryFactory",
        "PostgresPITAuthority",
        "market_regime_alpha.data",
        "market_regime_alpha.market_data",
        "compatibility",
        "fallback",
    )
    assert tuple(token for token in forbidden_tokens if token in source) == ()


def test_runtime_uow_is_not_expanded_into_a_market_mega_uow() -> None:
    runtime_uow = (
        PACKAGE / "infrastructure" / "postgres" / "uow.py"
    ).read_text(encoding="utf-8")
    market_uow = (
        PACKAGE / "infrastructure" / "postgres" / "market_uow.py"
    ).read_text(encoding="utf-8")
    assert "def market(" not in runtime_uow
    assert "def runtime(" not in market_uow
    assert "def runtime_finalization(" in market_uow


def test_target_sql_is_confined_to_postgres_adapter() -> None:
    violations: list[str] = []
    sql_tokens = ("SELECT ", "INSERT INTO ", "UPDATE mra.", "DELETE FROM ", "DROP SCHEMA")
    for root in TARGET_ROOTS:
        for source_file in _python_files(root):
            if PACKAGE / "infrastructure" / "postgres" in source_file.parents:
                continue
            content = source_file.read_text(encoding="utf-8")
            if any(token in content for token in sql_tokens):
                violations.append(str(source_file.relative_to(PACKAGE)))
    assert violations == []


def test_bootstrap_is_the_only_target_composition_root() -> None:
    constructors = (
        "TargetPostgresPool(",
        "PostgresUnitOfWorkProvider(",
        "RuntimeApplication(",
        "ArtifactApplication(",
        "LocalArtifactStore(",
    )
    violations: list[str] = []
    for root in TARGET_ROOTS:
        for source_file in _python_files(root):
            if source_file == PACKAGE / "bootstrap.py":
                continue
            content = source_file.read_text(encoding="utf-8")
            if any(constructor in content for constructor in constructors):
                violations.append(str(source_file.relative_to(PACKAGE)))
    assert violations == []


def test_target_has_no_generic_factory_bus_workflow_or_registry_framework() -> None:
    prohibited = ("RepositoryFactory", "CommandBus", "WorkflowEngine", "ServiceLocator")
    offenders = tuple(
        str(source_file.relative_to(PACKAGE))
        for root in TARGET_ROOTS
        for source_file in _python_files(root)
        if any(
            name in source_file.read_text(encoding="utf-8")
            for name in prohibited
        )
    )
    assert offenders == ()


def test_target_repositories_do_not_own_transactions() -> None:
    offenders = tuple(
        str(source_file.relative_to(PACKAGE))
        for source_file in _python_files(PACKAGE / "infrastructure" / "postgres" / "repositories")
        if ".commit(" in source_file.read_text(encoding="utf-8")
        or ".rollback(" in source_file.read_text(encoding="utf-8")
        or ".transaction(" in source_file.read_text(encoding="utf-8")
    )
    assert offenders == ()
