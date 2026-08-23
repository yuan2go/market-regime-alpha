"""Architecture guard for the canonical-to-Legacy dependency boundary."""

from __future__ import annotations

import ast
from importlib.util import resolve_name
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parents[2] / "src" / "market_regime_alpha"
DIVIDEND_T_PACKAGE = "market_regime_alpha.dividend_t"
ALLOWED_DIRECT_IMPORT_PREFIXES = (
    "market_regime_alpha.dividend_t",
    "market_regime_alpha.legacy",
    "market_regime_alpha.migration.legacy",
)
ALLOWED_DIRECT_IMPORT_MODULES: set[str] = set()


def _module_name(path: Path) -> str:
    relative = path.relative_to(SOURCE_ROOT.parent).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _imported_module(
    node: ast.ImportFrom,
    *,
    package: str,
) -> str:
    module = node.module or ""
    if node.level == 0:
        return module
    return resolve_name(f"{'.' * node.level}{module}", package)


def _direct_dividend_t_imports(
    source: str,
    *,
    importer: str,
    package: str | None = None,
) -> tuple[int, ...]:
    resolved_package = package or importer.rpartition(".")[0]
    lines: list[int] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            if any(
                alias.name == DIVIDEND_T_PACKAGE
                or alias.name.startswith(f"{DIVIDEND_T_PACKAGE}.")
                for alias in node.names
            ):
                lines.append(node.lineno)
        elif isinstance(node, ast.ImportFrom):
            imported = _imported_module(
                node,
                package=resolved_package,
            )
            if imported == DIVIDEND_T_PACKAGE or imported.startswith(
                f"{DIVIDEND_T_PACKAGE}."
            ):
                lines.append(node.lineno)
    return tuple(sorted(lines))


def _is_allowed_importer(module: str) -> bool:
    return module in ALLOWED_DIRECT_IMPORT_MODULES or any(
        module == prefix or module.startswith(f"{prefix}.")
        for prefix in ALLOWED_DIRECT_IMPORT_PREFIXES
    )


def test_detector_identifies_absolute_and_relative_legacy_imports() -> None:
    source = """
from market_regime_alpha.dividend_t.storage import DEFAULT_RESEARCH_DIR
from ..dividend_t.trend_snapshot import build_dividend_trend_snapshot
"""

    assert _direct_dividend_t_imports(
        source,
        importer="market_regime_alpha.research.example",
    ) == (2, 3)


def test_canonical_modules_do_not_import_dividend_t_directly() -> None:
    violations: list[str] = []
    for path in sorted(SOURCE_ROOT.rglob("*.py")):
        module = _module_name(path)
        if _is_allowed_importer(module):
            continue
        for line in _direct_dividend_t_imports(
            path.read_text(encoding="utf-8"),
            importer=module,
            package=module if path.name == "__init__.py" else None,
        ):
            violations.append(f"{path.relative_to(SOURCE_ROOT.parent)}:{line}")

    assert violations == [], (
        "canonical modules must delegate dividend_t access through "
        f"market_regime_alpha.migration.legacy: {violations}"
    )
