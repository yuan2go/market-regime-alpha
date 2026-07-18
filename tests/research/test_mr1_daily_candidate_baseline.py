from __future__ import annotations

import runpy
from pathlib import Path

import pytest

from market_regime_alpha.research.prr_mvp_1 import ExploratoryExecutionCostConfig


RUNNER = Path(__file__).resolve().parents[2] / "scripts" / "run_mr1_overnight_morning_pop_validation.py"
MR1_RUNNER = runpy.run_path(str(RUNNER))
daily_baselines = MR1_RUNNER["_candidate_daily_baselines"]
compound_daily_baselines = MR1_RUNNER["_compound_daily_baselines"]


def _target(symbol: str, status: str, value: float | None) -> dict[str, object]:
    return {
        "decision_date": "2026-01-05",
        "target_id": "NEXT_SESSION_1030_RETURN",
        "symbol": symbol,
        "status": status,
        "value": value,
        "reference_price": 10.0,
        "exit_price": 11.0,
    }


def test_daily_candidate_baseline_keeps_missing_target_weight_as_cash() -> None:
    rows = daily_baselines(
        (_target("000001.SZ", "AVAILABLE", 0.1), _target("000002.SZ", "UNAVAILABLE", None)),
        {"BASE": ExploratoryExecutionCostConfig(minimum_commission=0.0)},
    )

    row = next(item for item in rows if item["exit_time"] == "10:30")
    assert row["candidate_gross_return"] == 0.05
    assert row["candidate_observed_weight"] == 0.5
    assert row["candidate_missing_weight"] == 0.5
    assert row["candidate_net_return"] < row["candidate_gross_return"]
    assert row["baseline_kind"] == "NON_TRADABLE_CROSS_SECTIONAL_DIAGNOSTIC_WITH_SAME_COST_MECHANICS"


def test_cumulative_candidate_baseline_is_compounded_from_daily_rows() -> None:
    values = compound_daily_baselines(
        [
            {
                "cost_scenario": "BASE",
                "exit_time": "10:30",
                "candidate_gross_return": 0.10,
                "candidate_net_return": 0.08,
            },
            {
                "cost_scenario": "BASE",
                "exit_time": "10:30",
                "candidate_gross_return": -0.10,
                "candidate_net_return": -0.08,
            },
        ]
    )

    assert values["BASE"]["10:30"] == pytest.approx({"gross": -0.01, "net": -0.0064})
