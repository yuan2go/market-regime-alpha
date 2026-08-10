"""Executable guards for the final Canonical/Legacy authority boundary."""

from __future__ import annotations

import ast
from importlib.util import resolve_name
from pathlib import Path
import tomllib

from market_regime_alpha.application.authority_boundary import (
    AuthorityCapability,
    canonical_authority_catalog,
)
from market_regime_alpha.daily_decision.entry import EntryAssessmentState


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "src" / "market_regime_alpha"
LEGACY_EXECUTABLE_PREFIXES = (
    "market_regime_alpha.daily_research",
    "market_regime_alpha.dividend_t",
    "market_regime_alpha.web.dividend_t_app",
)


def _module_name(path: Path) -> str:
    parts = list(path.relative_to(SOURCE.parent).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _imports(path: Path) -> tuple[str, ...]:
    module = _module_name(path)
    package = module if path.name == "__init__.py" else module.rpartition(".")[0]
    values: list[str] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            values.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported = node.module or ""
            values.append(
                imported
                if node.level == 0
                else resolve_name(f"{'.' * node.level}{imported}", package)
            )
    return tuple(values)


def test_catalog_has_one_current_daily_runtime_and_no_legacy_writer() -> None:
    catalog = canonical_authority_catalog()

    assert catalog.daily_runtime.owner == "CONTINUOUS_RESEARCH"
    assert catalog.lifecycle_runtime.owner == "CANONICAL_DECISION_LIFECYCLE"
    assert "NOT_A_PARALLEL_DAILY_RUNTIME" in catalog.lifecycle_runtime.limitations
    assert all(
        AuthorityCapability.EXECUTE not in item.capabilities
        and AuthorityCapability.WRITE not in item.capabilities
        for item in catalog.legacy_namespaces
    )


def test_canonical_entry_has_no_enter_state() -> None:
    assert {item.value for item in EntryAssessmentState} == {
        "REJECT",
        "WAIT_CONFIRMATION",
    }


def test_canonical_compositions_do_not_import_legacy_executable_producers() -> None:
    violations: list[str] = []
    roots = (
        SOURCE / "application" / "continuous_research",
        SOURCE / "application" / "decision_system",
        SOURCE / "application" / "shadow_research",
        SOURCE / "application" / "state_system",
    )
    for root in roots:
        for path in sorted(root.rglob("*.py")):
            for imported in _imports(path):
                if imported.startswith(LEGACY_EXECUTABLE_PREFIXES):
                    violations.append(f"{path.relative_to(ROOT)} -> {imported}")
    assert violations == []


def test_installed_cli_entry_points_are_not_legacy_producers() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    scripts = project["project"]["scripts"]
    assert scripts
    assert not any(
        target.startswith(LEGACY_EXECUTABLE_PREFIXES)
        for target in scripts.values()
    )
