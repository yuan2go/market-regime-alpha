"""Pure validation and application facade for PIT Candidate replication."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Mapping

from market_regime_alpha.research.pit_replication_preflight import (
    PITReplicationPreflightStatus,
    preflight_xuntou_replication,
)
from market_regime_alpha.research.pit_replication_protocol import (
    PITCandidateReplicationProtocol,
    frozen_pit_replication_protocol,
)
from market_regime_alpha.research.mr1_candidate_baselines import select_matched_k_symbols


Row = Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class PITReplicationTableValidation:
    decision_date_count: int
    population_row_count: int
    ranking_row_count: int
    selection_row_count: int


def validate_replication_tables(
    universe_rows: Iterable[Row],
    eligibility_rows: Iterable[Row],
    population_rows: Iterable[Row],
    ranking_rows: Iterable[Row],
    selection_rows: Iterable[Row],
    *,
    protocol: PITCandidateReplicationProtocol | None = None,
) -> PITReplicationTableValidation:
    """Validate PIT lineage, eligibility and comparator-population parity."""

    frozen = protocol or frozen_pit_replication_protocol()
    universe = tuple(universe_rows)
    eligibility = tuple(eligibility_rows)
    population = tuple(population_rows)
    rankings = tuple(ranking_rows)
    selections = tuple(selection_rows)

    universe_index = _unique_index(universe, ("decision_date", "symbol"), "Universe")
    eligibility_index = _unique_index(
        eligibility, ("decision_date", "symbol"), "Eligibility"
    )
    population_index = _unique_index(
        population, ("decision_date", "symbol"), "Candidate population"
    )
    _unique_index(
        rankings,
        ("decision_date", "model_id", "symbol"),
        "Candidate ranking",
    )
    _unique_index(
        selections,
        ("decision_date", "model_id", "seed", "slot_index"),
        "matched-K selection",
        optional=("model_id",),
        defaults={"model_id": frozen.candidate_model_id},
    )

    for key, row in universe_index.items():
        source = str(row.get("membership_source", ""))
        if source in {"CURRENT_WATCHLIST_BACKFILL", "CURRENT_MEMBERSHIP_BACKFILL"}:
            raise ValueError("current-watchlist membership cannot be PIT Universe evidence")
        if row.get("is_member") is not True:
            continue
        if not source or "PIT" not in source.upper():
            raise ValueError(f"Universe row {key!r} lacks historical PIT membership lineage")

    for key in population_index:
        universe_row = universe_index.get(key)
        eligibility_row = eligibility_index.get(key)
        if universe_row is None or universe_row.get("is_member") is not True:
            raise ValueError(f"Candidate population row {key!r} lacks Universe membership")
        if eligibility_row is None or eligibility_row.get("status") != "ELIGIBLE":
            raise ValueError(f"Candidate population row {key!r} is not ELIGIBLE")
        if eligibility_row.get("buyability") != "BUYABLE":
            raise ValueError(f"Candidate population row {key!r} is not explicitly BUYABLE")

    population_by_date: dict[str, set[str]] = defaultdict(set)
    for decision_date, symbol in population_index:
        population_by_date[decision_date].add(symbol)

    ranks_by_date: dict[str, list[int]] = defaultdict(list)
    ranked_symbols_by_date: dict[str, set[str]] = defaultdict(set)
    for row in rankings:
        decision_date = _text(row, "decision_date")
        model_id = _text(row, "model_id")
        symbol = _text(row, "symbol")
        if model_id != frozen.candidate_model_id:
            raise ValueError("Candidate ranking model does not match frozen B1-E")
        if symbol not in population_by_date[decision_date]:
            raise ValueError("Candidate ranking symbol is outside the same-date population")
        rank = row.get("rank")
        if isinstance(rank, bool) or not isinstance(rank, int) or rank <= 0:
            raise ValueError("Candidate ranking rank must be a positive integer")
        ranks_by_date[decision_date].append(rank)
        ranked_symbols_by_date[decision_date].add(symbol)
    for decision_date in population_by_date:
        ranks = ranks_by_date.get(decision_date, [])
        if sorted(ranks) != list(range(1, len(ranks) + 1)):
            raise ValueError(f"Candidate ranks are not continuous on {decision_date}")
        if not ranks or ranked_symbols_by_date.get(decision_date, set()) != population_by_date[decision_date]:
            raise ValueError("Candidate rankings must cover the frozen eligible population")

    grouped_selections: dict[tuple[str, str, int], list[Row]] = defaultdict(list)
    for row in selections:
        decision_date = _text(row, "decision_date")
        model_id = str(row.get("model_id", frozen.candidate_model_id))
        seed = _integer(row, "seed")
        symbol = _text(row, "symbol")
        if model_id != frozen.candidate_model_id:
            raise ValueError("matched-K selection model does not match frozen B1-E")
        if seed not in frozen.matched_k_seed_set:
            raise ValueError("matched-K seed is outside the frozen seed family")
        if symbol not in population_by_date[decision_date]:
            raise ValueError("matched-K selection symbol is outside the same-date population")
        grouped_selections[(decision_date, model_id, seed)].append(row)
    for (decision_date, _, _), rows in grouped_selections.items():
        slots = sorted(_integer(row, "slot_index") for row in rows)
        expected_count = min(frozen.top_k, len(population_by_date[decision_date]))
        if slots != list(range(1, expected_count + 1)):
            raise ValueError("matched-K slots must be continuous and match population Top-K")
        symbols = [_text(row, "symbol") for row in rows]
        if len(symbols) != len(set(symbols)):
            raise ValueError("matched-K selection symbols must be unique")

    expected_selection_groups = {
        (decision_date, frozen.candidate_model_id, seed)
        for decision_date in population_by_date
        for seed in frozen.matched_k_seed_set
    }
    if set(grouped_selections) != expected_selection_groups:
        raise ValueError("matched-K selections must cover every frozen date and seed")
    for decision_date, model_id, seed in sorted(expected_selection_groups):
        rows = grouped_selections[(decision_date, model_id, seed)]
        population_group = tuple(sorted(population_by_date[decision_date]))
        dataset_ids = {
            str(row.get("dataset_id", ""))
            for row in population
            if str(row.get("decision_date")) == decision_date
        }
        if len(dataset_ids) != 1 or not next(iter(dataset_ids)).strip():
            raise ValueError("Candidate population requires one immutable Dataset ID per date")
        dataset_id = next(iter(dataset_ids))
        expected_symbols = select_matched_k_symbols(
            dataset_id=dataset_id,
            decision_date=date.fromisoformat(decision_date),
            symbols=population_group,
            top_k=frozen.top_k,
            baseline_seed=seed,
        )
        actual_symbols = tuple(
            _text(row, "symbol")
            for row in sorted(rows, key=lambda item: _integer(item, "slot_index"))
        )
        if actual_symbols != expected_symbols:
            raise ValueError("matched-K selection does not match the frozen rank-blind algorithm")

    decision_date_count = len(population_by_date)
    if decision_date_count < frozen.minimum_decision_dates:
        raise ValueError("PIT evidence has fewer than the Protocol minimum Decision Dates")
    average_population_size = len(population) / decision_date_count
    if average_population_size < frozen.minimum_average_population_size:
        raise ValueError("PIT evidence has less than the Protocol minimum average population size")
    symbol_coverage = len(rankings) / len(population)
    if symbol_coverage < frozen.minimum_symbol_coverage:
        raise ValueError("PIT evidence has less than the Protocol minimum symbol coverage")

    return PITReplicationTableValidation(
        decision_date_count=decision_date_count,
        population_row_count=len(population),
        ranking_row_count=len(rankings),
        selection_row_count=len(selections),
    )


def run_pit_replication(
    *,
    xuntou_bundle: Path | None,
    output_root: Path,
    code_revision: str,
) -> Path:
    """Run provider preflight and truthfully publish the current bounded outcome."""

    protocol = frozen_pit_replication_protocol()
    preflight = preflight_xuntou_replication(xuntou_bundle)
    if preflight.status is PITReplicationPreflightStatus.AVAILABLE:
        raise RuntimeError(
            "verified Xuntou input is available, but a sealed validation partition and "
            "PIT replication evidence payload are required before result publication"
        )
    if preflight.status is PITReplicationPreflightStatus.INVALID_PIT_EVIDENCE:
        raise ValueError(
            "provided Xuntou input failed PIT validation: " + ", ".join(preflight.reasons)
        )
    from market_regime_alpha.research.pit_replication_artifacts import (
        publish_blocked_pit_replication,
    )

    return publish_blocked_pit_replication(
        output_root=output_root,
        protocol=protocol,
        preflight=preflight,
        code_revision=code_revision,
    )


def _unique_index(
    rows: tuple[Row, ...],
    fields: tuple[str, ...],
    label: str,
    *,
    optional: tuple[str, ...] = (),
    defaults: Mapping[str, Any] | None = None,
) -> dict[tuple[str, ...], Row]:
    result: dict[tuple[str, ...], Row] = {}
    defaults = defaults or {}
    for row in rows:
        values: list[str] = []
        for field in fields:
            if field in optional and field not in row:
                value = defaults[field]
            else:
                value = row.get(field)
            if value is None or str(value).strip() == "":
                raise ValueError(f"{label} primary key field {field} is missing")
            values.append(str(value))
        key = tuple(values)
        if key in result:
            raise ValueError(f"duplicate {label} primary key {key!r}")
        result[key] = row
    return result


def _text(row: Row, field: str) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _integer(row: Row, field: str) -> int:
    value = row.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an integer")
    return value
