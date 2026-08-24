from __future__ import annotations

import ast
from pathlib import Path


PACKAGE_ROOT = Path(__file__).parents[2] / "src" / "market_regime_alpha"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)
    return imported


def test_postgres_composition_does_not_import_sqlite_composition() -> None:
    path = PACKAGE_ROOT / "application" / "canonical_lifecycle" / "postgres_composition.py"

    assert not any("sqlite" in module for module in _imports(path))


def test_free_data_production_modules_cannot_import_sqlite_adapters() -> None:
    root = PACKAGE_ROOT / "application" / "free_data_operation"
    if not root.exists():
        return

    violations: list[str] = []
    for path in sorted(root.rglob("*.py")):
        for module in sorted(_imports(path)):
            if "sqlite" in module:
                violations.append(f"{path.relative_to(PACKAGE_ROOT)} -> {module}")

    assert violations == [], "PostgreSQL free-data boundary violations:\n" + "\n".join(violations)


def test_free_data_composition_cannot_import_trading_mutation_domains() -> None:
    roots = (
        PACKAGE_ROOT / "application" / "free_data_operation",
        PACKAGE_ROOT / "cli" / "free_data_operation.py",
    )
    prohibited = (".execution", ".portfolio", ".position", ".broker")
    violations: list[str] = []
    paths = tuple(roots[0].rglob("*.py")) + (roots[1],)
    for path in paths:
        for module in sorted(_imports(path)):
            if any(value in module for value in prohibited):
                violations.append(f"{path.relative_to(PACKAGE_ROOT)} -> {module}")

    assert violations == [], "Free-data trading mutation imports:\n" + "\n".join(violations)


def test_postgres_authority_constructors_never_default_to_migration() -> None:
    violations: list[str] = []
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name != "__init__":
                continue
            positional = tuple(node.args.args[-len(node.args.defaults) :]) if node.args.defaults else ()
            defaults = zip(positional + tuple(node.args.kwonlyargs), tuple(node.args.defaults) + tuple(node.args.kw_defaults), strict=True)
            for argument, default in defaults:
                if argument.arg not in {"apply_migrations", "migrate"}:
                    continue
                if isinstance(default, ast.Constant) and default.value is True:
                    violations.append(
                        f"{path.relative_to(PACKAGE_ROOT)}:{node.lineno} {argument.arg}=True"
                    )

    assert violations == [], "Implicit PostgreSQL migration defaults:\n" + "\n".join(violations)
