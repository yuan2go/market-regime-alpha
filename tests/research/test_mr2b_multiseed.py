from __future__ import annotations

from datetime import date

import pytest

from market_regime_alpha.research.mr1_candidate_baselines import (
    build_candidate_daily_baselines,
    build_model_candidate_populations,
)
from market_regime_alpha.research.mr2b_multiseed import (
    build_multiseed_matched_k_reference,
    empirical_percentile,
    linear_quantile,
)
from market_regime_alpha.research.prr_mvp_1 import ExploratoryExecutionCostConfig


DATASET_ID = "prr-dataset-test"
MR1_RUN_ID = "mr1-test"
TARGET_ID = "target-r5-decision-reference-to-next-session-close-return-v1"
DAY = date(2026, 1, 5)
SYMBOLS = tuple(f"{index:06d}.SZ" for index in range(1, 7))


def _rankings(symbols: tuple[str, ...] = SYMBOLS) -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "decision_date": DAY.isoformat(),
            "target_id": TARGET_ID,
            "model_id": "B1-E",
            "symbol": symbol,
            "eligible_for_ranking": True,
            "rank": rank,
        }
        for rank, symbol in enumerate(symbols, start=1)
    )


def _targets(day: date = DAY) -> tuple[dict[str, object], ...]:
    rows: list[dict[str, object]] = []
    for endpoint, target_id in (
        ("09:35", "NEXT_SESSION_0935_RETURN"),
        ("10:00", "NEXT_SESSION_1000_RETURN"),
        ("10:30", "NEXT_SESSION_1030_RETURN"),
        ("CLOSE", "NEXT_SESSION_CLOSE_RETURN"),
    ):
        for index, symbol in enumerate(SYMBOLS, start=1):
            rows.append(
                {
                    "decision_date": day.isoformat(),
                    "target_session_date": "2026-01-06",
                    "target_id": target_id,
                    "symbol": symbol,
                    "status": "AVAILABLE",
                    "reference_price": 10.0,
                    "exit_price": 10.0 + index / 10.0,
                    "exit_time": endpoint,
                }
            )
    return tuple(rows)


def _evidence(*, ranking_rows: tuple[dict[str, object], ...] | None = None):
    populations = build_model_candidate_populations(
        dataset_id=DATASET_ID,
        ranking_rows=ranking_rows or _rankings(),
    )
    costs = {"BASE": ExploratoryExecutionCostConfig(minimum_commission=0.0)}
    primary = build_candidate_daily_baselines(
        populations=populations,
        target_rows=_targets(),
        decision_dates=(DAY,),
        cost_configs=costs,
        top_k=3,
        baseline_seed=17,
    )
    equity = tuple(
        {
            "session_date": DAY.isoformat(),
            "model_id": "B1-E",
            "exit_time": exit_time,
            "cost_scenario": "BASE",
            "gross_return": 0.02,
            "net_return": 0.019,
        }
        for exit_time in ("09:35", "10:00", "10:30", "CLOSE")
    )
    return build_multiseed_matched_k_reference(
        dataset_id=DATASET_ID,
        mr1_run_id=MR1_RUN_ID,
        populations=populations,
        target_rows=_targets(),
        decision_dates=(DAY,),
        cost_configs=costs,
        top_k=3,
        seeds=(0, 1, 2, 17),
        primary_seed=17,
        verified_primary_baseline_rows=primary.baseline_rows,
        verified_primary_selection_rows=primary.selection_rows,
        model_equity_rows=equity,
    )


def test_multiseed_is_deterministic_under_ranking_input_order() -> None:
    ordinary = _evidence()
    reversed_input = _evidence(ranking_rows=tuple(reversed(_rankings())))

    assert ordinary == reversed_input


def test_quantiles_use_documented_linear_r7_method() -> None:
    values = (0.0, 10.0, 20.0, 30.0, 40.0)

    assert linear_quantile(values, 0.10) == 4.0
    assert linear_quantile(values, 0.25) == 10.0
    assert linear_quantile(values, 0.50) == 20.0
    assert linear_quantile(values, 0.75) == 30.0
    assert linear_quantile(values, 0.90) == 36.0


def test_empirical_percentile_uses_midrank_ties() -> None:
    assert empirical_percentile((1.0, 2.0, 2.0, 4.0), 2.0) == 0.5
    assert empirical_percentile((1.0, 2.0, 3.0), -1.0) == 0.0
    assert empirical_percentile((1.0, 2.0, 3.0), 9.0) == 1.0


def test_seed_17_exactly_reconciles_to_verified_mr1() -> None:
    evidence = _evidence()

    assert evidence.primary_seed_reconciliation["status"] == "EXACT_MATCH"
    assert evidence.primary_seed_reconciliation["mismatch_rows"] == 0
    assert evidence.primary_seed_reconciliation["maximum_numeric_difference"] == 0.0


def test_seeds_do_not_inflate_daily_summary_sample_count() -> None:
    evidence = _evidence()

    assert len(evidence.selection_rows) == 1 * 1 * 4 * 3
    assert len(evidence.return_rows) == 1 * 1 * 4 * 1 * 4
    assert len(evidence.null_summary_rows) == 1 * 1 * 4 * 1
    assert {row["seed_count"] for row in evidence.null_summary_rows} == {4}
    assert all(row["unique_selection_count"] <= 4 for row in evidence.null_summary_rows)


def test_seed_contract_rejects_empty_duplicate_or_unsorted_values() -> None:
    evidence = _evidence()
    assert evidence.seed_set_id

    populations = build_model_candidate_populations(dataset_id=DATASET_ID, ranking_rows=_rankings())
    with pytest.raises(ValueError, match="seeds must be non-empty, ordered, and unique"):
        build_multiseed_matched_k_reference(
            dataset_id=DATASET_ID,
            mr1_run_id=MR1_RUN_ID,
            populations=populations,
            target_rows=_targets(),
            decision_dates=(DAY,),
            cost_configs={"BASE": ExploratoryExecutionCostConfig()},
            top_k=3,
            seeds=(1, 1),
            primary_seed=17,
            verified_primary_baseline_rows=(),
            verified_primary_selection_rows=(),
            model_equity_rows=(),
        )


def test_close_cash_lock_applies_to_every_seed_without_fake_return_selection() -> None:
    second = date(2026, 1, 6)
    rankings = tuple(
        {
            **row,
            "decision_date": decision_day.isoformat(),
        }
        for decision_day in (DAY, second)
        for row in _rankings()
    )
    targets = tuple(
        {
            **row,
            "decision_date": decision_day.isoformat(),
            "target_session_date": target_day,
        }
        for decision_day, target_day in ((DAY, "2026-01-06"), (second, "2026-01-07"))
        for row in _targets()
    )
    populations = build_model_candidate_populations(dataset_id=DATASET_ID, ranking_rows=rankings)
    costs = {"BASE": ExploratoryExecutionCostConfig(minimum_commission=0.0)}
    primary = build_candidate_daily_baselines(
        populations=populations,
        target_rows=targets,
        decision_dates=(DAY, second),
        cost_configs=costs,
        top_k=3,
        baseline_seed=17,
    )
    equity = tuple(
        {
            "session_date": decision_day.isoformat(),
            "model_id": "B1-E",
            "exit_time": exit_time,
            "cost_scenario": "BASE",
            "gross_return": 0.0,
            "net_return": 0.0,
        }
        for decision_day in (DAY, second)
        for exit_time in ("09:35", "10:00", "10:30", "CLOSE")
    )

    evidence = build_multiseed_matched_k_reference(
        dataset_id=DATASET_ID,
        mr1_run_id=MR1_RUN_ID,
        populations=populations,
        target_rows=targets,
        decision_dates=(DAY, second),
        cost_configs=costs,
        top_k=3,
        seeds=(17, 18),
        primary_seed=17,
        verified_primary_baseline_rows=primary.baseline_rows,
        verified_primary_selection_rows=primary.selection_rows,
        model_equity_rows=equity,
    )

    locked = tuple(
        row
        for row in evidence.return_rows
        if row["decision_date"] == second.isoformat() and row["exit_time"] == "CLOSE"
    )
    assert len(locked) == 2
    assert all(row["selection_status"] == "CASH_LOCKED" for row in locked)
    assert all(row["selected_symbol_count"] == 0 for row in locked)
    assert all(row["gross_return"] == row["net_return"] == 0.0 for row in locked)
    assert all(row["cash_locked_weight"] == 1.0 for row in locked)
