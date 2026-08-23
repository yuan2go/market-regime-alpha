"""Lightweight import guards for converged authority direction."""

from __future__ import annotations

import ast
from pathlib import Path


PACKAGE = Path(__file__).parents[2] / "src" / "market_regime_alpha"


def _imports(root: Path) -> tuple[tuple[Path, str], ...]:
    result: list[tuple[Path, str]] = []
    paths = (root,) if root.is_file() else tuple(sorted(root.rglob("*.py")))
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                result.extend((path, item.name) for item in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                result.append((path, node.module))
    return tuple(result)


def _violations(
    roots: tuple[Path, ...], forbidden: tuple[str, ...]
) -> tuple[str, ...]:
    return tuple(
        f"{path.relative_to(PACKAGE)} -> {module}"
        for root in roots
        for path, module in _imports(root)
        if module.startswith(forbidden)
    )


def test_canonical_runtimes_never_depend_on_legacy_runtime_planes() -> None:
    legacy = (
        "market_regime_alpha.application.daily_loop",
        "market_regime_alpha.daily_research",
        "market_regime_alpha.dividend_t",
        "market_regime_alpha.legacy",
        "market_regime_alpha.migration.legacy",
        "market_regime_alpha.backtesting",
    )
    assert _violations(
        (
            PACKAGE / "application" / "continuous_research",
            PACKAGE / "application" / "historical_research",
        ),
        legacy,
    ) == ()


def test_research_helpers_cannot_mutate_positions_or_execution() -> None:
    mutation_domains = (
        "market_regime_alpha.position",
        "market_regime_alpha.execution",
    )
    assert _violations(
        (
            PACKAGE / "application" / "historical_corpus",
            PACKAGE / "application" / "research_validation",
            PACKAGE / "research",
        ),
        mutation_domains,
    ) == ()


def test_legacy_and_old_backtest_code_cannot_reenter_canonical_write_paths() -> None:
    canonical_writers = (
        "market_regime_alpha.application.continuous_research",
        "market_regime_alpha.application.historical_research",
        "market_regime_alpha.application.state_system",
        "market_regime_alpha.application.decision_system",
        "market_regime_alpha.persistence.postgres",
        "market_regime_alpha.strategies.postgres",
    )
    assert _violations(
        (
            PACKAGE / "dividend_t",
            PACKAGE / "legacy",
            PACKAGE / "migration" / "legacy",
            PACKAGE.parent.parent / "backtesting",
        ),
        canonical_writers,
    ) == ()


def test_strategy_does_not_import_post_portfolio_account_risk_owner() -> None:
    assert _violations(
        (PACKAGE / "strategies",),
        ("market_regime_alpha.portfolio.account_authority",),
    ) == ()
