from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest

from market_regime_alpha.research.mr2b_context import (
    AuxiliaryWatchlistContext,
    ContextDataStatus,
)
from market_regime_alpha.research.mr2b_excess import WatchlistDirection
from market_regime_alpha.research.mr2b_f2a import F2AInputs
from market_regime_alpha.research.mr2b_f2a_artifacts import publish_f2a_artifact
from market_regime_alpha.research.mr2b_f2a_reader import load_verified_f2a_run
from market_regime_alpha.research.mr2b_multiseed import MultiSeedReferenceEvidence
from market_regime_alpha.research.prr_artifact_schemas import (
    ModelCandidatePopulation,
    model_population_hash,
)


DAY = date(2026, 1, 5)
DATASET = "prr-dataset-test"
MR1 = "mr1-test"
MODEL = "prr-mvp-1-b1-e-v1"
TARGET = "target-r5-decision-reference-to-next-session-close-return-v1"


def _inputs() -> F2AInputs:
    symbols = ("000001.SZ",)
    population = ModelCandidatePopulation(
        dataset_id=DATASET,
        decision_date=DAY,
        model_id=MODEL,
        target_id=TARGET,
        symbols=symbols,
        population_size=1,
        population_hash=model_population_hash(
            dataset_id=DATASET,
            decision_date=DAY,
            target_id=TARGET,
            symbols=symbols,
        ),
    )
    context = AuxiliaryWatchlistContext(
        decision_date=DAY,
        decision_time=datetime.fromisoformat("2026-01-05T14:55:00+08:00"),
        cutoff_time=datetime.fromisoformat("2026-01-05T14:50:00+08:00"),
        dataset_id=DATASET,
        watchlist_id="sha256:watchlist",
        context_id="sha256:context",
        expected_symbol_count=1,
        available_symbol_count=1,
        coverage=1.0,
        expected_bar_count_per_symbol=46,
        available_bar_count_per_symbol=46,
        grid_status="COMPLETE",
        data_status=ContextDataStatus.AVAILABLE,
        missing_reason=None,
        watchlist_direction_return=0.01,
        watchlist_direction=WatchlistDirection.UP,
        watchlist_breadth_at_cutoff=1.0,
        watchlist_intraday_range_to_cutoff=0.01,
        watchlist_amount_to_cutoff=100.0,
        prior_watchlist_amount_same_cutoff=90.0,
        watchlist_amount_change_same_cutoff=100 / 90 - 1,
    )
    selection = {
        "schema_version": "mr-2b-multiseed-matched-k-v1",
        "dataset_id": DATASET,
        "mr1_run_id": MR1,
        "decision_date": DAY.isoformat(),
        "model_id": MODEL,
        "target_id": TARGET,
        "population_definition_id": population.definition_id,
        "population_size": 1,
        "population_hash": population.population_hash,
        "seed": 17,
        "top_k": 1,
        "slot_index": 1,
        "symbol": symbols[0],
        "selection_algorithm_id": "mr1-matched-k-sha256-rank-blind-v1",
        "selection_id": "sha256:selection",
        "selected_symbols_hash": "sha256:symbols",
        "data_eligibility": "EXPLORATORY",
    }
    return_row = {
        "schema_version": "mr-2b-multiseed-matched-k-v1",
        "dataset_id": DATASET,
        "mr1_run_id": MR1,
        "decision_date": DAY.isoformat(),
        "model_id": MODEL,
        "exit_time": "10:30",
        "cost_scenario": "BASE",
        "seed": 17,
        "gross_return": 0.01,
        "net_return": 0.009,
        "observed_weight": 1.0,
        "missing_weight": 0.0,
        "cash_locked_weight": 0.0,
        "selected_symbol_count": 1,
        "selection_status": "EXECUTED",
        "selection_id": "sha256:selection",
        "selected_symbols_hash": "sha256:symbols",
        "population_hash": population.population_hash,
        "data_eligibility": "EXPLORATORY",
    }
    summary = {
        "schema_version": "mr-2b-multiseed-matched-k-v1",
        "decision_date": DAY.isoformat(),
        "model_id": MODEL,
        "exit_time": "10:30",
        "cost_scenario": "BASE",
        "seed_count": 1,
        "unique_selection_count": 1,
        "unique_selection_ratio": 1.0,
        "primary_seed": 17,
        "primary_seed_selection_id": "sha256:selection",
        "primary_seed_gross_return": 0.01,
        "primary_seed_net_return": 0.009,
        "gross_median": 0.01,
        "gross_p10": 0.01,
        "gross_p25": 0.01,
        "gross_p75": 0.01,
        "gross_p90": 0.01,
        "gross_min": 0.01,
        "gross_max": 0.01,
        "net_median": 0.009,
        "net_p10": 0.009,
        "net_p25": 0.009,
        "net_p75": 0.009,
        "net_p90": 0.009,
        "net_min": 0.009,
        "net_max": 0.009,
        "population_hash": population.population_hash,
        "model_gross_percentile": 0.5,
        "model_net_percentile": 0.5,
        "cash_locked": False,
        "data_status": "AVAILABLE",
        "data_eligibility": "EXPLORATORY",
    }
    daily = {
        "schema_version": "mr-2b-daily-candidate-excess-v1",
        "dataset_id": DATASET,
        "mr1_run_id": MR1,
        "decision_date": DAY.isoformat(),
        "model_id": MODEL,
        "exit_time": "10:30",
        "cost_scenario": "BASE",
        "context_id": context.context_id,
        "context_label": "UP",
        "context_data_status": "AVAILABLE",
        "population_hash": population.population_hash,
        "population_size": 1,
        "primary_seed": 17,
        "primary_seed_selection_id": "sha256:selection",
        "seed_set_id": "sha256:seed-set",
        "model_gross_return": 0.02,
        "model_net_return": 0.019,
        "all_candidate_gross_return": 0.015,
        "primary_seed_matched_k_gross_return": 0.01,
        "primary_seed_matched_k_net_return": 0.009,
        "multiseed_gross_median": 0.01,
        "multiseed_net_median": 0.009,
        "multiseed_gross_p10": 0.01,
        "multiseed_gross_p90": 0.01,
        "multiseed_net_p10": 0.009,
        "multiseed_net_p90": 0.009,
        "gross_lift_vs_all_candidate": 0.005,
        "gross_lift_vs_primary_seed": 0.01,
        "net_lift_vs_primary_seed": 0.01,
        "gross_lift_vs_multiseed_median": 0.01,
        "net_lift_vs_multiseed_median": 0.01,
        "model_gross_percentile": 0.5,
        "model_net_percentile": 0.5,
        "cost_drag_model": -0.001,
        "cost_drag_primary_seed": -0.001,
        "cost_drag_difference_primary_seed": 0.0,
        "data_status": "AVAILABLE",
        "data_eligibility": "EXPLORATORY",
    }
    return F2AInputs(
        contexts=(context,),
        populations=(population,),
        multiseed=MultiSeedReferenceEvidence(
            seed_set_id="sha256:seed-set",
            selection_rows=(selection,),
            return_rows=(return_row,),
            null_summary_rows=(summary,),
            primary_seed_reconciliation={
                "schema_version": "mr-2b-primary-seed-reconciliation-v1",
                "primary_seed": 17,
                "checked_rows": 1,
                "matched_rows": 1,
                "mismatch_rows": 0,
                "maximum_numeric_difference": 0.0,
                "status": "EXACT_MATCH",
            },
        ),
        daily_excess_rows=(daily,),
        primary_comparison_input={
            "schema_version": "mr-2b-primary-comparison-input-v1",
            "primary_hypothesis_id": "mr2b-primary-b1e-1030-base-watchlist-direction-v1",
            "authority": "DESCRIPTIVE_INPUT_ONLY",
            "UP_count": 1,
            "DOWN_count": 0,
            "FLAT_count": 0,
            "unavailable_count": 0,
        },
        coverage={"schema_version": "mr-2b-f2a-coverage-v1", "context_date_count": 1},
    )


def _publish(tmp_path: Path) -> Path:
    return publish_f2a_artifact(
        output_root=tmp_path,
        run_identity={"dataset_id": DATASET, "mr1_run_id": MR1, "seed_set": [17]},
        inputs=_inputs(),
    )


def test_f2a_artifact_has_exact_files_and_is_verified(tmp_path: Path) -> None:
    root = _publish(tmp_path)

    verified = load_verified_f2a_run(
        root,
        expected_dataset_id=DATASET,
        expected_mr1_run_id=MR1,
    )

    assert verified.manifest["data_eligibility"] == "EXPLORATORY"
    assert verified.primary_comparison_input["authority"] == "DESCRIPTIVE_INPUT_ONLY"


@pytest.mark.parametrize(
    "filename",
    (
        "auxiliary_watchlist_context.parquet",
        "multi_seed_matched_k_selections.parquet",
        "multi_seed_matched_k_returns.parquet",
        "multi_seed_null_summary.parquet",
        "daily_candidate_excess.parquet",
        "manifest.json",
    ),
)
def test_verified_reader_rejects_tampered_payload(tmp_path: Path, filename: str) -> None:
    root = _publish(tmp_path / filename.replace(".", "-"))
    path = root / filename
    path.write_bytes(path.read_bytes() + b"tamper")

    with pytest.raises(ValueError, match="checksum mismatch"):
        load_verified_f2a_run(root, expected_dataset_id=DATASET, expected_mr1_run_id=MR1)
