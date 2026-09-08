"""Retired work-package executors must not remain installable execution paths."""

import ast
from importlib.util import find_spec, resolve_name
from pathlib import Path

import pytest

from tests.architecture.test_canonical_execution_boundary import _module_name


SOURCE = Path(__file__).resolve().parents[2] / "src" / "market_regime_alpha"
RETIRED_MODULES = tuple(
    f"market_regime_alpha.interfaces.{name}"
    for name in (
        "wp17p_campaign", "wp17p_decisions", "wp17p_evaluation",
        "wp17p_models", "wp17p_operations", "wp17p_outcomes",
        "wp17p_research", "wp17p_authorities", "wp17p_pilot", "wp18_archive",
    )
)


def _imported_names(source: str, *, package: str) -> tuple[str, ...]:
    names = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                base = resolve_name("." * node.level + base, package)
            names.append(base)
            names.extend(base + "." + alias.name for alias in node.names)
    return tuple(names)


def test_import_guard_covers_module_aliases_and_relative_imports() -> None:
    names = _imported_names(
        "from market_regime_alpha.interfaces import wp17p_campaign as campaign\n"
        "from . import wp17p_models as models\n"
        "import market_regime_alpha.interfaces.wp18_archive as archive\n",
        package="market_regime_alpha.interfaces",
    )
    assert set(names).intersection(RETIRED_MODULES) == {
        "market_regime_alpha.interfaces.wp17p_campaign",
        "market_regime_alpha.interfaces.wp17p_models",
        "market_regime_alpha.interfaces.wp18_archive",
    }


@pytest.mark.parametrize("module", RETIRED_MODULES)
def test_work_package_executor_is_not_importable(module: str) -> None:
    assert find_spec(module) is None


def test_production_consumers_have_no_retired_executor_import() -> None:
    violations = []
    for path in SOURCE.rglob("*.py"):
        module = _module_name(path)
        package = module if path.name == "__init__.py" else module.rpartition(".")[0]
        for imported in _imported_names(path.read_text(), package=package):
            if any(imported == name or imported.startswith(name + ".") for name in RETIRED_MODULES):
                violations.append((str(path.relative_to(SOURCE)), imported))
    assert violations == []


def test_private_historical_decoder_and_generic_execution_remain_available() -> None:
    assert find_spec("market_regime_alpha.research_qualification.domain.backtest_compatibility")
    assert find_spec("market_regime_alpha.interfaces.backtest_actions")
    assert find_spec("market_regime_alpha.market.application.prospective_continuity")
