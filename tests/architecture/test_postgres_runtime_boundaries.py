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
