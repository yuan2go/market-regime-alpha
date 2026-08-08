from __future__ import annotations

import ast
from pathlib import Path


STATE_ROOTS = (
    Path("src/market_regime_alpha/research/state_system"),
    Path("src/market_regime_alpha/application/state_system"),
)

FORBIDDEN_IMPORT_PREFIXES = (
    "market_regime_alpha.execution",
    "market_regime_alpha.portfolio",
    "market_regime_alpha.position",
    "market_regime_alpha.opportunity",
)

FORBIDDEN_CALL_TOKENS = {
    "broker",
    "qmt",
    "ptrade",
    "xtquant",
    "order",
    "fill",
    "position",
    "dailydecisionwindowsummary",
}


def test_state_system_has_no_trading_or_daily_summary_authority_path() -> None:
    violations: list[str] = []
    for root in STATE_ROOTS:
        for path in sorted(root.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    if module.startswith(FORBIDDEN_IMPORT_PREFIXES):
                        violations.append(f"{path}:{node.lineno}:import:{module}")
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.startswith(FORBIDDEN_IMPORT_PREFIXES):
                            violations.append(f"{path}:{node.lineno}:import:{alias.name}")
                if isinstance(node, ast.Call):
                    name = _call_name(node.func).lower()
                    if name in FORBIDDEN_CALL_TOKENS:
                        violations.append(f"{path}:{node.lineno}:call:{name}")

    assert violations == []


def _call_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""
