from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.research.mr2b_context import (
    AuxiliaryWatchlistContext,
    ContextDataStatus,
)
from market_regime_alpha.research.mr2b_excess import WatchlistDirection
from market_regime_alpha.research.mr2b_f2a import (
    F2A_PRIMARY_HYPOTHESIS_ID,
    build_daily_candidate_excess,
    build_primary_comparison_input,
)
from market_regime_alpha.research.prr_artifact_schemas import (
    CandidateBaselineId,
    ModelCandidatePopulation,
    model_population_hash,
)


DAY = date(2026, 1, 5)
MODEL = "prr-mvp-1-b1-e-v1"
DATASET = "prr-dataset-test"
MR1 = "mr1-test"
TARGET = "target-r5-decision-reference-to-next-session-close-return-v1"
SYMBOLS = ("000001.SZ", "000002.SZ", "000003.SZ")
SHANGHAI = ZoneInfo("Asia/Shanghai")


def _population() -> ModelCandidatePopulation:
    return ModelCandidatePopulation(
        dataset_id=DATASET,
        decision_date=DAY,
        model_id=MODEL,
        target_id=TARGET,
        symbols=SYMBOLS,
        population_size=3,
        population_hash=model_population_hash(
            dataset_id=DATASET,
            decision_date=DAY,
            target_id=TARGET,
            symbols=SYMBOLS,
        ),
    )


def _context() -> AuxiliaryWatchlistContext:
    return AuxiliaryWatchlistContext(
        decision_date=DAY,
        decision_time=datetime.fromisoformat("2026-01-05T14:55:00+08:00"),
        cutoff_time=datetime.fromisoformat("2026-01-05T14:50:00+08:00"),
        dataset_id=DATASET,
        watchlist_id="sha256:watchlist",
        context_id="sha256:context",
        expected_symbol_count=3,
        available_symbol_count=3,
        coverage=1.0,
        expected_bar_count_per_symbol=46,
        available_bar_count_per_symbol=46,
        grid_status="COMPLETE",
        data_status=ContextDataStatus.AVAILABLE,
        missing_reason=None,
        watchlist_direction_return=0.01,
        watchlist_direction=WatchlistDirection.UP,
        watchlist_breadth_at_cutoff=2 / 3,
        watchlist_intraday_range_to_cutoff=0.02,
        watchlist_amount_to_cutoff=1_000.0,
        prior_watchlist_amount_same_cutoff=900.0,
        watchlist_amount_change_same_cutoff=1_000 / 900 - 1,
    )


def _baseline_rows(population: ModelCandidatePopulation) -> tuple[dict[str, object], ...]:
    common = {
        "decision_date": DAY.isoformat(),
        "model_id": MODEL,
        "exit_time": "10:30",
        "cost_scenario": "BASE",
        "baseline_seed": 17,
        "candidate_population_hash": population.population_hash,
        "candidate_population_size": population.population_size,
        "selection_id": "sha256:primary",
    }
    return (
        {**common, "baseline_id": CandidateBaselineId.ALL_CANDIDATE_GROSS_V1.value, "gross_return": 0.01, "net_return": 0.01},
        {**common, "baseline_id": CandidateBaselineId.MATCHED_K_HASH_GROSS_V1.value, "gross_return": 0.012, "net_return": 0.012},
        {**common, "baseline_id": CandidateBaselineId.MATCHED_K_HASH_NET_V1.value, "gross_return": 0.012, "net_return": 0.011},
        {**common, "baseline_id": CandidateBaselineId.ALL_CANDIDATE_NET_DIAGNOSTIC_V1.value, "gross_return": 0.01, "net_return": 0.009},
    )


def _null_summary(population: ModelCandidatePopulation) -> dict[str, object]:
    return {
        "decision_date": DAY.isoformat(),
        "model_id": MODEL,
        "exit_time": "10:30",
        "cost_scenario": "BASE",
        "primary_seed": 17,
        "primary_seed_selection_id": "sha256:primary",
        "primary_seed_gross_return": 0.012,
        "primary_seed_net_return": 0.011,
        "gross_median": 0.009,
        "net_median": 0.008,
        "gross_p10": -0.01,
        "gross_p90": 0.02,
        "net_p10": -0.012,
        "net_p90": 0.018,
        "model_gross_percentile": 0.8,
        "model_net_percentile": 0.75,
        "population_hash": population.population_hash,
    }


def test_daily_excess_binds_all_input_identities_and_uses_daily_differences() -> None:
    population = _population()
    rows = build_daily_candidate_excess(
        dataset_id=DATASET,
        mr1_run_id=MR1,
        contexts=(_context(),),
        populations=(population,),
        baseline_rows=_baseline_rows(population),
        null_summary_rows=(_null_summary(population),),
        model_equity_rows=(
            {
                "session_date": DAY.isoformat(),
                "model_id": MODEL,
                "exit_time": "10:30",
                "cost_scenario": "BASE",
                "gross_return": 0.02,
                "net_return": 0.018,
            },
        ),
        seed_set_id="sha256:seeds",
        primary_seed=17,
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["context_id"] == "sha256:context"
    assert row["population_hash"] == population.population_hash
    assert row["primary_seed_selection_id"] == "sha256:primary"
    assert row["net_lift_vs_primary_seed"] == pytest.approx(0.007)
    assert row["net_lift_vs_multiseed_median"] == pytest.approx(0.01)
    assert "compounded_excess" not in row


def test_daily_excess_rejects_cross_identity_join() -> None:
    population = _population()
    summary = _null_summary(population)
    summary["population_hash"] = "sha256:wrong"

    with pytest.raises(ValueError, match="population identity"):
        build_daily_candidate_excess(
            dataset_id=DATASET,
            mr1_run_id=MR1,
            contexts=(_context(),),
            populations=(population,),
            baseline_rows=_baseline_rows(population),
            null_summary_rows=(summary,),
            model_equity_rows=(),
            seed_set_id="sha256:seeds",
            primary_seed=17,
        )


def test_primary_comparison_is_descriptive_input_only() -> None:
    population = _population()
    rows = build_daily_candidate_excess(
        dataset_id=DATASET,
        mr1_run_id=MR1,
        contexts=(_context(),),
        populations=(population,),
        baseline_rows=_baseline_rows(population),
        null_summary_rows=(_null_summary(population),),
        model_equity_rows=(
            {
                "session_date": DAY.isoformat(),
                "model_id": MODEL,
                "exit_time": "10:30",
                "cost_scenario": "BASE",
                "gross_return": 0.02,
                "net_return": 0.018,
            },
        ),
        seed_set_id="sha256:seeds",
        primary_seed=17,
    )

    primary = build_primary_comparison_input(rows)

    assert primary["primary_hypothesis_id"] == F2A_PRIMARY_HYPOTHESIS_ID
    assert primary["authority"] == "DESCRIPTIVE_INPUT_ONLY"
    assert primary["UP_count"] == 1
    assert "assessment" not in primary
