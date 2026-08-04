from __future__ import annotations

import ast
from pathlib import Path


PACKAGE_ROOT = Path(__file__).parents[2] / "src" / "market_regime_alpha"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            result.add(node.module)
    return result


def _python_files(root: Path) -> tuple[Path, ...]:
    return tuple(
        sorted(
            path
            for path in root.rglob("*.py")
            if "__pycache__" not in path.parts
        )
    )


def test_canonical_feature_modules_do_not_depend_on_legacy_execution_or_broker() -> None:
    forbidden = (
        "market_regime_alpha.dividend_t",
        "market_regime_alpha.migration.legacy",
        "market_regime_alpha.execution",
        "market_regime_alpha.brokers",
    )
    violations = []
    for path in _python_files(PACKAGE_ROOT / "features"):
        for imported in _imports(path):
            if imported.startswith(forbidden):
                violations.append(f"{path.relative_to(PACKAGE_ROOT)} -> {imported}")
    assert not violations, "canonical Feature boundary violations:\n" + "\n".join(
        violations
    )


def test_signal_input_assembler_does_not_depend_on_legacy_or_execution() -> None:
    path = PACKAGE_ROOT / "signals" / "input_assembly.py"
    forbidden = (
        "market_regime_alpha.dividend_t",
        "market_regime_alpha.migration",
        "market_regime_alpha.execution",
        "market_regime_alpha.brokers",
    )
    violations = tuple(
        imported for imported in _imports(path) if imported.startswith(forbidden)
    )
    assert violations == ()


def test_only_migration_legacy_adapter_imports_legacy_technical_implementation() -> None:
    canonical_paths = (
        *_python_files(PACKAGE_ROOT / "features"),
        PACKAGE_ROOT / "signals" / "input_assembly.py",
        PACKAGE_ROOT
        / "application"
        / "canonical_lifecycle"
        / "stages"
        / "signal_forecast.py",
    )
    assert all(
        not any(
            imported.startswith("market_regime_alpha.dividend_t")
            for imported in _imports(path)
        )
        for path in canonical_paths
    )
    legacy = (
        PACKAGE_ROOT
        / "migration"
        / "legacy"
        / "adapters"
        / "technical_observables.py"
    )
    assert any(
        imported.startswith("market_regime_alpha.dividend_t")
        for imported in _imports(legacy)
    )
