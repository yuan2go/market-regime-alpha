from __future__ import annotations

from market_regime_alpha.research.mr2_failure_decomposition import (
    decompose_model_failures,
    feature_target_diagnostics,
)


def test_feature_ic_is_cross_sectional_per_decision_date_then_aggregated() -> None:
    rankings = tuple(
        {
            "decision_date": "2026-01-05",
            "target_id": "target-r5-decision-reference-to-next-session-close-return-v1",
            "symbol": symbol,
            "feature_values": {"feature-r5-momentum-5s-v1": value},
        }
        for symbol, value in (("A", 1.0), ("B", 2.0), ("C", 3.0), ("D", 4.0), ("E", 5.0), ("F", 6.0), ("G", 7.0), ("H", 8.0))
    )
    targets = tuple(
        {"decision_date": "2026-01-05", "symbol": symbol, "target_id": "NEXT_SESSION_1030_RETURN", "status": "AVAILABLE", "value": value}
        for symbol, value in (("A", -0.03), ("B", -0.02), ("C", -0.01), ("D", 0.0), ("E", 0.01), ("F", 0.02), ("G", 0.03), ("H", 0.04))
    )

    ic, spreads = feature_target_diagnostics(ranking_rows=rankings, target_rows=targets)

    aggregate = next(row for row in ic if row["scope"] == "AGGREGATE")
    assert aggregate["spearman_rank_ic"] == 1.0
    assert next(row for row in spreads if row["scope"] == "AGGREGATE")["best_minus_worst"] > 0.0


def test_failure_decomposition_keeps_independent_reasons() -> None:
    base = {
        "model_id": "B0", "exit_time": "10:30", "cost_scenario": "BASE", "gross_cumulative_return": 0.02,
        "net_cumulative_return": -0.01, "top5_gross_minus_candidate_gross": -0.01,
        "top5_net_minus_candidate_net": -0.02, "maximum_drawdown": -0.2,
        "first_20_return": 0.01, "middle_20_return": -0.02, "last_20_return": 0.01,
    }
    rows = (base, {**base, "cost_scenario": "LOW", "net_cumulative_return": 0.01}, {**base, "cost_scenario": "HIGH", "net_cumulative_return": -0.03})

    result = decompose_model_failures(mr1_metrics=rows, target_coverage={"NEXT_SESSION_1030_RETURN": 1.0})

    assert set(result[0]["failure_reasons"]) == {"NO_CROSS_SECTIONAL_ALPHA", "COST_FRAGILE", "REGIME_UNSTABLE", "DRAWDOWN_FAILED"}
