from __future__ import annotations

from dataclasses import replace
from uuid import UUID

import pytest

from market_regime_alpha.research_qualification.domain.exploratory_backtest import (
    BacktestArmKind,
    BacktestArmPlan,
    BacktestContextMode,
)


def _arm(kind: BacktestArmKind, ordinal: int) -> BacktestArmPlan:
    return BacktestArmPlan(
        exploratory_backtest_arm_id=UUID(f"18100000-0000-0000-0000-{ordinal:012d}"),
        ordinal=ordinal,
        kind=kind,
        strategy_version_id=UUID(f"18200000-0000-0000-0000-{ordinal:012d}"),
        strategy_version_sha256=f"{ordinal:x}" * 64,
    )


def test_wp18_arm_roster_freezes_rule_ridge_and_context_mode() -> None:
    arms = (
        _arm(BacktestArmKind.RULE_CURRENT_CONTEXT, 1),
        _arm(BacktestArmKind.RIDGE_CURRENT_CONTEXT, 2),
        _arm(BacktestArmKind.RULE_CONTEXT_OBSERVATIONAL, 3),
        _arm(BacktestArmKind.RIDGE_CONTEXT_OBSERVATIONAL, 4),
    )

    assert tuple(item.context_mode for item in arms) == (
        BacktestContextMode.CURRENT_GATE,
        BacktestContextMode.CURRENT_GATE,
        BacktestContextMode.OBSERVATIONAL,
        BacktestContextMode.OBSERVATIONAL,
    )
    assert tuple(item.uses_model for item in arms) == (False, True, False, True)
    assert len({item.content_sha256 for item in arms}) == 4


def test_arm_hash_includes_exact_strategy_binding() -> None:
    arm = _arm(BacktestArmKind.RULE_CURRENT_CONTEXT, 1)
    changed = replace(
        arm,
        strategy_version_id=UUID("18200000-0000-0000-0000-000000000099"),
    )
    assert arm.content_sha256 != changed.content_sha256


def test_arm_rejects_strategy_hash_with_wrong_shape() -> None:
    with pytest.raises(ValueError):
        BacktestArmPlan(
            exploratory_backtest_arm_id=UUID("18100000-0000-0000-0000-000000000001"),
            ordinal=1,
            kind=BacktestArmKind.RULE_CURRENT_CONTEXT,
            strategy_version_id=UUID("18200000-0000-0000-0000-000000000001"),
            strategy_version_sha256="bad",
        )
