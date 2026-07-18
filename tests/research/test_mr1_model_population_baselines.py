from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import shutil

import pytest

from market_regime_alpha.research.mr1_candidate_baselines import (
    build_candidate_daily_baselines,
    build_model_candidate_populations,
    select_matched_k_population,
)
from market_regime_alpha.research.prr_artifact_schemas import CandidateBaselineId
from market_regime_alpha.research.prr_mvp_1 import ExploratoryExecutionCostConfig
from market_regime_alpha.research.mr1_research_runner import (
    build_mr1_run_identity,
    mr1_cost_scenarios,
    mr1_run_id,
)


DAY = date(2026, 1, 5)
DATASET_ID = "prr-dataset-test"
TARGET_ID = "target-r5-decision-reference-to-next-session-close-return-v1"
SYMBOLS = tuple(f"{index:06d}.SZ" for index in range(1, 21))


def _ranking_rows(
    model_id: str,
    symbols: tuple[str, ...],
    *,
    rejected: frozenset[str] = frozenset(),
) -> tuple[dict[str, object], ...]:
    eligible = tuple(symbol for symbol in symbols if symbol not in rejected)
    ranks = {symbol: index for index, symbol in enumerate(eligible, start=1)}
    return tuple(
        {
            "decision_date": DAY.isoformat(),
            "target_id": TARGET_ID,
            "model_id": model_id,
            "symbol": symbol,
            "eligible_for_ranking": symbol in ranks,
            "rank": ranks.get(symbol),
        }
        for symbol in symbols
    )


def test_model_specific_populations_exclude_each_models_rejected_symbols() -> None:
    rejected = frozenset(SYMBOLS[-3:])
    populations = build_model_candidate_populations(
        dataset_id=DATASET_ID,
        ranking_rows=(
            *_ranking_rows("B0-MOMENTUM", SYMBOLS),
            *_ranking_rows("B1-E", SYMBOLS, rejected=rejected),
        ),
    )
    indexed = {population.model_id: population for population in populations}

    b0_selection = select_matched_k_population(indexed["B0-MOMENTUM"], top_k=5, seed=17)
    b1_selection = select_matched_k_population(indexed["B1-E"], top_k=5, seed=17)

    assert set(b0_selection.symbols) <= set(indexed["B0-MOMENTUM"].symbols)
    assert set(b1_selection.symbols) <= set(indexed["B1-E"].symbols)
    assert not set(b1_selection.symbols) & rejected
    assert indexed["B0-MOMENTUM"].population_size == 20
    assert indexed["B1-E"].population_size == 17


def test_equal_symbol_populations_have_equal_population_and_selection_identity() -> None:
    populations = build_model_candidate_populations(
        dataset_id=DATASET_ID,
        ranking_rows=(
            *_ranking_rows("B0-MOMENTUM", SYMBOLS),
            *_ranking_rows("B1-E", tuple(reversed(SYMBOLS))),
        ),
    )
    left, right = populations
    left_selection = select_matched_k_population(left, top_k=5, seed=17)
    right_selection = select_matched_k_population(right, top_k=5, seed=17)

    assert left.population_hash == right.population_hash
    assert left_selection.symbols == right_selection.symbols
    assert left_selection.selection_id == right_selection.selection_id
    assert left_selection.selected_symbols_hash == right_selection.selected_symbols_hash


def test_population_hash_and_selection_are_input_order_independent() -> None:
    left = build_model_candidate_populations(
        dataset_id=DATASET_ID,
        ranking_rows=_ranking_rows("B1-E", SYMBOLS),
    )[0]
    right = build_model_candidate_populations(
        dataset_id=DATASET_ID,
        ranking_rows=_ranking_rows("B1-E", tuple(reversed(SYMBOLS))),
    )[0]

    assert left.population_hash == right.population_hash
    assert select_matched_k_population(left, top_k=5, seed=17) == select_matched_k_population(
        right,
        top_k=5,
        seed=17,
    )


def test_population_content_changes_population_and_selection_identity() -> None:
    full = build_model_candidate_populations(
        dataset_id=DATASET_ID,
        ranking_rows=_ranking_rows("B1-E", SYMBOLS),
    )[0]
    reduced = build_model_candidate_populations(
        dataset_id=DATASET_ID,
        ranking_rows=_ranking_rows("B1-E", SYMBOLS[:-1]),
    )[0]

    assert full.population_hash != reduced.population_hash
    assert select_matched_k_population(full, top_k=5, seed=17).selection_id != (
        select_matched_k_population(reduced, top_k=5, seed=17).selection_id
    )


@pytest.mark.parametrize(
    ("eligible", "rank", "message"),
    (
        (False, 3, "ineligible symbol must not have a rank"),
        (True, None, "eligible symbol must have a rank"),
    ),
)
def test_population_rejects_rank_eligibility_mismatch(
    eligible: bool,
    rank: int | None,
    message: str,
) -> None:
    row = dict(_ranking_rows("B1-E", SYMBOLS[:1])[0])
    row.update(eligible_for_ranking=eligible, rank=rank)

    with pytest.raises(ValueError, match=message):
        build_model_candidate_populations(dataset_id=DATASET_ID, ranking_rows=(row,))


@pytest.mark.parametrize("ranks", ((1, 3), (1, 1)))
def test_population_requires_contiguous_unique_ranks(ranks: tuple[int, int]) -> None:
    rows = [dict(row) for row in _ranking_rows("B1-E", SYMBOLS[:2])]
    for row, rank in zip(rows, ranks, strict=True):
        row["rank"] = rank

    with pytest.raises(ValueError, match="eligible ranks must be exactly 1..N"):
        build_model_candidate_populations(dataset_id=DATASET_ID, ranking_rows=rows)


def test_baselines_and_selection_evidence_use_each_models_population() -> None:
    rejected = frozenset(SYMBOLS[-3:])
    populations = build_model_candidate_populations(
        dataset_id=DATASET_ID,
        ranking_rows=(
            *_ranking_rows("B0-MOMENTUM", SYMBOLS),
            *_ranking_rows("B1-E", SYMBOLS, rejected=rejected),
        ),
    )
    result = build_candidate_daily_baselines(
        populations=populations,
        target_rows=_targets(SYMBOLS),
        decision_dates=(DAY,),
        cost_configs={"BASE": ExploratoryExecutionCostConfig(minimum_commission=0.0)},
        top_k=5,
        baseline_seed=17,
    )

    assert len(result.baseline_rows) == 2 * 4 * 1 * 1 * 4
    b1_rows = tuple(row for row in result.baseline_rows if row["model_id"] == "B1-E")
    assert {int(row["candidate_population_size"]) for row in b1_rows} == {17}
    b1_selected = {
        str(row["symbol"])
        for row in result.selection_rows
        if row["model_id"] == "B1-E"
    }
    assert len(b1_selected) == 5
    assert not b1_selected & rejected
    assert {
        row["baseline_id"]
        for row in b1_rows
    } == {baseline_id.value for baseline_id in CandidateBaselineId}


def test_equal_populations_persist_equal_logical_selections() -> None:
    populations = build_model_candidate_populations(
        dataset_id=DATASET_ID,
        ranking_rows=(
            *_ranking_rows("B0-MOMENTUM", SYMBOLS),
            *_ranking_rows("B1-E", tuple(reversed(SYMBOLS))),
        ),
    )
    result = build_candidate_daily_baselines(
        populations=populations,
        target_rows=_targets(SYMBOLS),
        decision_dates=(DAY,),
        cost_configs={"BASE": ExploratoryExecutionCostConfig()},
        top_k=5,
    )
    selections = {
        model_id: tuple(
            row
            for row in result.selection_rows
            if row["model_id"] == model_id
            and row["exit_time"] == "10:30"
            and row["cost_scenario"] == "BASE"
        )
        for model_id in ("B0-MOMENTUM", "B1-E")
    }

    assert [row["symbol"] for row in selections["B0-MOMENTUM"]] == [
        row["symbol"] for row in selections["B1-E"]
    ]
    assert {row["selection_id"] for row in selections["B0-MOMENTUM"]} == {
        row["selection_id"] for row in selections["B1-E"]
    }
    assert {row["population_hash"] for row in selections["B0-MOMENTUM"]} == {
        row["population_hash"] for row in selections["B1-E"]
    }


def _targets(symbols: tuple[str, ...]) -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "decision_date": DAY.isoformat(),
            "target_session_date": "2026-01-06",
            "target_id": target_id,
            "symbol": symbol,
            "status": "AVAILABLE",
            "reference_price": 10.0,
            "exit_price": 10.1,
        }
        for target_id in (
            "NEXT_SESSION_0935_RETURN",
            "NEXT_SESSION_1000_RETURN",
            "NEXT_SESSION_1030_RETURN",
            "NEXT_SESSION_CLOSE_RETURN",
        )
        for symbol in symbols
    )


def test_semantic_run_id_is_independent_of_machine_local_dataset_path(
    tmp_path: Path,
) -> None:
    left = tmp_path / "machine-a" / "dataset"
    right = tmp_path / "different" / "machine-b" / "dataset"
    left.mkdir(parents=True)
    (left / "dataset_manifest.json").write_text(
        json.dumps({"dataset_id": DATASET_ID}, sort_keys=True),
        encoding="utf-8",
    )
    (left / "SHA256SUMS.json").write_text(
        json.dumps({"payload": "sha256:test"}, sort_keys=True),
        encoding="utf-8",
    )
    right.parent.mkdir(parents=True)
    shutil.copytree(left, right)
    rankings = _ranking_rows("B1-E", SYMBOLS)
    populations = build_model_candidate_populations(
        dataset_id=DATASET_ID,
        ranking_rows=rankings,
    )

    left_identity = build_mr1_run_identity(
        dataset_path=left,
        top_k=5,
        rankings=tuple(dict(row) for row in rankings),
        populations=populations,
        cost_configs=mr1_cost_scenarios(),
    )
    right_identity = build_mr1_run_identity(
        dataset_path=right,
        top_k=5,
        rankings=tuple(dict(row) for row in rankings),
        populations=populations,
        cost_configs=mr1_cost_scenarios(),
    )

    assert left_identity == right_identity
    assert mr1_run_id(left_identity) == mr1_run_id(right_identity)
    assert str(left) not in json.dumps(left_identity, sort_keys=True)
