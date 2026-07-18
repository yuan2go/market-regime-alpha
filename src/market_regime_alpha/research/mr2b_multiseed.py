"""Deterministic multi-seed matched-K reference distributions for MR-2B F2A."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
import math
from numbers import Real
from typing import Any

from market_regime_alpha.research.mr1_candidate_baselines import (
    reference_trade_economics,
    select_matched_k_population,
)
from market_regime_alpha.research.prr_artifact_schemas import (
    CandidateBaselineId,
    MR1_BASELINE_PRIMARY_SEED,
    MR1_MATCHED_K_ALGORITHM_ID,
    ModelCandidatePopulation,
    canonical_identity_hash,
    selected_symbols_hash,
)
from market_regime_alpha.research.prr_mvp_1 import ExploratoryExecutionCostConfig


MR2B_F2A_SEEDS = tuple(range(256))
MR2B_MULTISEED_SCHEMA_VERSION = "mr-2b-multiseed-matched-k-v1"
MR2B_QUANTILE_METHOD_ID = "linear-r7-quantile-v1"
MR2B_PERCENTILE_METHOD_ID = "empirical-midrank-ties-v1"
_EXIT_TARGETS = {
    "09:35": "NEXT_SESSION_0935_RETURN",
    "10:00": "NEXT_SESSION_1000_RETURN",
    "10:30": "NEXT_SESSION_1030_RETURN",
    "CLOSE": "NEXT_SESSION_CLOSE_RETURN",
}


@dataclass(frozen=True, slots=True)
class MultiSeedReferenceEvidence:
    seed_set_id: str
    selection_rows: tuple[dict[str, Any], ...]
    return_rows: tuple[dict[str, Any], ...]
    null_summary_rows: tuple[dict[str, Any], ...]
    primary_seed_reconciliation: dict[str, Any]


def linear_quantile(values: Iterable[float], probability: float) -> float:
    """Return the deterministic R7/linear sample quantile used by F2A."""

    ordered = tuple(sorted(_finite(value, "quantile value") for value in values))
    if not ordered:
        raise ValueError("quantile values must not be empty")
    if not 0.0 <= probability <= 1.0:
        raise ValueError("quantile probability must be within [0, 1]")
    location = (len(ordered) - 1) * probability
    lower = math.floor(location)
    upper = math.ceil(location)
    if lower == upper:
        return ordered[lower]
    fraction = location - lower
    return ordered[lower] + fraction * (ordered[upper] - ordered[lower])


def empirical_percentile(values: Iterable[float], observed: float) -> float:
    """Place one model return in a null distribution using midrank ties."""

    distribution = tuple(_finite(value, "percentile value") for value in values)
    model_value = _finite(observed, "observed percentile value")
    if not distribution:
        raise ValueError("percentile distribution must not be empty")
    less = sum(value < model_value for value in distribution)
    equal = sum(value == model_value for value in distribution)
    return (less + 0.5 * equal) / len(distribution)


def build_multiseed_matched_k_reference(
    *,
    dataset_id: str,
    mr1_run_id: str,
    populations: Iterable[ModelCandidatePopulation],
    target_rows: Iterable[Mapping[str, Any]],
    decision_dates: Iterable[date],
    cost_configs: Mapping[str, ExploratoryExecutionCostConfig],
    top_k: int,
    seeds: Iterable[int] = MR2B_F2A_SEEDS,
    primary_seed: int = MR1_BASELINE_PRIMARY_SEED,
    verified_primary_baseline_rows: Iterable[Mapping[str, Any]] = (),
    verified_primary_selection_rows: Iterable[Mapping[str, Any]] = (),
    model_equity_rows: Iterable[Mapping[str, Any]] = (),
) -> MultiSeedReferenceEvidence:
    """Build logical selections once and reuse them across endpoint/cost evaluations."""

    seed_values = tuple(seeds)
    if (
        not seed_values
        or seed_values != tuple(sorted(seed_values))
        or len(seed_values) != len(set(seed_values))
    ):
        raise ValueError("seeds must be non-empty, ordered, and unique")
    if primary_seed not in seed_values:
        raise ValueError("primary seed must belong to the frozen seed set")
    if top_k <= 0:
        raise ValueError("top_k must be positive")
    if not dataset_id or not mr1_run_id:
        raise ValueError("Dataset and MR-1 identities must be non-empty")
    dates = tuple(decision_dates)
    if not dates or dates != tuple(sorted(dates)) or len(dates) != len(set(dates)):
        raise ValueError("Decision Dates must be chronological and unique")
    population_rows = tuple(populations)
    if not population_rows:
        raise ValueError("model Candidate Populations must not be empty")
    if any(item.dataset_id != dataset_id for item in population_rows):
        raise ValueError("model Candidate Population Dataset identity mismatch")
    population_index = {(item.decision_date, item.model_id): item for item in population_rows}
    if len(population_index) != len(population_rows):
        raise ValueError("each model/date must have exactly one Candidate Population")
    model_ids = tuple(sorted({item.model_id for item in population_rows}))
    if set(population_index) != {(day, model) for day in dates for model in model_ids}:
        raise ValueError("model Candidate Populations must exactly cover model/date grid")
    if not cost_configs:
        raise ValueError("cost configurations must not be empty")

    targets = tuple(dict(row) for row in target_rows)
    target_index = _target_index(targets)
    baseline_rows = tuple(dict(row) for row in verified_primary_baseline_rows)
    selection_evidence = tuple(dict(row) for row in verified_primary_selection_rows)
    equity_rows = tuple(dict(row) for row in model_equity_rows)
    baseline_index = _baseline_index(baseline_rows)
    equity_index = _equity_index(equity_rows)
    primary_symbols = _primary_selection_symbols(selection_evidence)
    seed_set_id = canonical_identity_hash(
        {
            "schema_version": MR2B_MULTISEED_SCHEMA_VERSION,
            "seeds": seed_values,
            "primary_seed": primary_seed,
        }
    )

    selections: dict[tuple[date, str, int], Any] = {}
    selection_rows: list[dict[str, Any]] = []
    for day in dates:
        for model_id in model_ids:
            population = population_index[(day, model_id)]
            for seed in seed_values:
                selection = select_matched_k_population(population, top_k=top_k, seed=seed)
                selections[(day, model_id, seed)] = selection
                for slot_index, symbol in enumerate(selection.symbols, start=1):
                    selection_rows.append(
                        {
                            "schema_version": MR2B_MULTISEED_SCHEMA_VERSION,
                            "dataset_id": dataset_id,
                            "mr1_run_id": mr1_run_id,
                            "decision_date": day.isoformat(),
                            "model_id": model_id,
                            "target_id": population.target_id,
                            "population_definition_id": population.definition_id,
                            "population_size": population.population_size,
                            "population_hash": population.population_hash,
                            "seed": seed,
                            "top_k": top_k,
                            "slot_index": slot_index,
                            "symbol": symbol,
                            "selection_algorithm_id": MR1_MATCHED_K_ALGORITHM_ID,
                            "selection_id": selection.selection_id,
                            "selected_symbols_hash": selection.selected_symbols_hash,
                            "data_eligibility": "EXPLORATORY",
                        }
                    )

    return_rows: list[dict[str, Any]] = []
    for day in dates:
        for model_id in model_ids:
            population = population_index[(day, model_id)]
            for exit_time, endpoint_target in _EXIT_TARGETS.items():
                for scenario in sorted(cost_configs):
                    primary_baselines = _primary_baseline_pair(
                        baseline_index, day, model_id, exit_time, scenario, primary_seed
                    )
                    cash_locked = primary_baselines[0]["baseline_slot_status"] == "CASH_LOCKED"
                    for seed in seed_values:
                        selection = selections[(day, model_id, seed)]
                        if cash_locked:
                            lock_id = _cash_lock_selection_id(
                                population=population,
                                exit_time=exit_time,
                                scenario=scenario,
                                seed=seed,
                                top_k=top_k,
                            )
                            values = (0.0, 0.0, 0.0, 0.0, 1.0, "CASH_LOCKED", lock_id, 0)
                        else:
                            gross, net, observed, missing = _evaluate_selection(
                                selection_symbols=selection.symbols,
                                decision_day=day,
                                endpoint_target=endpoint_target,
                                target_index=target_index,
                                top_k=top_k,
                                costs=cost_configs[scenario],
                            )
                            values = (
                                gross,
                                net,
                                observed,
                                missing,
                                0.0,
                                "EXECUTED",
                                selection.selection_id,
                                len(selection.symbols),
                            )
                        gross, net, observed, missing, locked, status, selection_id, selected_count = values
                        return_rows.append(
                            {
                                "schema_version": MR2B_MULTISEED_SCHEMA_VERSION,
                                "dataset_id": dataset_id,
                                "mr1_run_id": mr1_run_id,
                                "decision_date": day.isoformat(),
                                "model_id": model_id,
                                "exit_time": exit_time,
                                "cost_scenario": scenario,
                                "seed": seed,
                                "gross_return": gross,
                                "net_return": net,
                                "observed_weight": observed,
                                "missing_weight": missing,
                                "cash_locked_weight": locked,
                                "selected_symbol_count": selected_count,
                                "selection_status": status,
                                "selection_id": selection_id,
                                "selected_symbols_hash": (
                                    selection.selected_symbols_hash
                                    if not cash_locked
                                    else selected_symbols_hash(())
                                ),
                                "population_hash": population.population_hash,
                                "data_eligibility": "EXPLORATORY",
                            }
                        )
    null_summary = _summaries(
        return_rows=return_rows,
        equity_index=equity_index,
        primary_seed=primary_seed,
        seed_count=len(seed_values),
    )
    reconciliation = _reconcile_primary_seed(
        primary_seed=primary_seed,
        return_rows=return_rows,
        baseline_index=baseline_index,
        selections=selections,
        primary_symbols=primary_symbols,
        dates=dates,
        model_ids=model_ids,
        scenarios=tuple(sorted(cost_configs)),
    )
    return MultiSeedReferenceEvidence(
        seed_set_id=seed_set_id,
        selection_rows=tuple(selection_rows),
        return_rows=tuple(return_rows),
        null_summary_rows=tuple(null_summary),
        primary_seed_reconciliation=reconciliation,
    )


def _target_index(rows: tuple[dict[str, Any], ...]) -> dict[tuple[str, str, str], dict[str, Any]]:
    keys = [(str(row.get("decision_date")), str(row.get("target_id")), str(row.get("symbol"))) for row in rows]
    if not rows or len(keys) != len(set(keys)):
        raise ValueError("MR-1 target rows must be non-empty with unique keys")
    return {key: row for key, row in zip(keys, rows, strict=True)}


def _baseline_index(rows: tuple[dict[str, Any], ...]) -> dict[tuple[str, str, str, str, int, str], dict[str, Any]]:
    index: dict[tuple[str, str, str, str, int, str], dict[str, Any]] = {}
    for row in rows:
        key = (
            str(row.get("decision_date")),
            str(row.get("model_id")),
            str(row.get("exit_time")),
            str(row.get("cost_scenario")),
            int(row.get("baseline_seed", -1)),
            str(row.get("baseline_id")),
        )
        if key in index:
            raise ValueError("verified primary baseline keys must be unique")
        index[key] = row
    return index


def _equity_index(rows: tuple[dict[str, Any], ...]) -> dict[tuple[str, str, str, str], dict[str, Any]]:
    index: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = (
            str(row.get("session_date")),
            str(row.get("model_id")),
            str(row.get("exit_time")),
            str(row.get("cost_scenario")),
        )
        if key in index:
            raise ValueError("model daily equity keys must be unique")
        index[key] = row
    return index


def _primary_selection_symbols(rows: tuple[dict[str, Any], ...]) -> dict[tuple[str, str], tuple[str, ...]]:
    grouped: dict[tuple[str, str], dict[int, str]] = {}
    for row in rows:
        key = (str(row.get("decision_date")), str(row.get("model_id")))
        slot = int(row.get("slot_index", 0))
        existing = grouped.setdefault(key, {})
        if slot in existing and existing[slot] != str(row.get("symbol")):
            raise ValueError("verified MR-1 selection evidence is inconsistent across endpoints")
        existing[slot] = str(row.get("symbol"))
    return {key: tuple(value[index] for index in sorted(value)) for key, value in grouped.items()}


def _primary_baseline_pair(index: Mapping[tuple[str, str, str, str, int, str], dict[str, Any]], day: date, model: str, exit_time: str, scenario: str, seed: int) -> tuple[dict[str, Any], dict[str, Any]]:
    prefix = (day.isoformat(), model, exit_time, scenario, seed)
    try:
        return (
            index[(*prefix, CandidateBaselineId.MATCHED_K_HASH_GROSS_V1.value)],
            index[(*prefix, CandidateBaselineId.MATCHED_K_HASH_NET_V1.value)],
        )
    except KeyError as exc:
        raise ValueError("verified MR-1 matched-K baseline row is missing") from exc


def _evaluate_selection(*, selection_symbols: tuple[str, ...], decision_day: date, endpoint_target: str, target_index: Mapping[tuple[str, str, str], Mapping[str, Any]], top_k: int, costs: ExploratoryExecutionCostConfig) -> tuple[float, float, float, float]:
    gross = net = 0.0
    observed = 0
    weight = 1.0 / top_k
    for symbol in selection_symbols:
        target = target_index.get((decision_day.isoformat(), endpoint_target, symbol))
        if target is None:
            raise ValueError("multi-seed target coverage is structurally incomplete")
        if target.get("status") != "AVAILABLE":
            continue
        economics = reference_trade_economics(
            reference_price=_finite(target.get("reference_price"), "reference price"),
            exit_price=_finite(target.get("exit_price"), "exit price"),
            weight=weight,
            cost_config=costs,
        )
        gross += weight * economics.gross_return
        net += weight * economics.net_return
        observed += 1
    observed_weight = observed * weight
    missing_weight = 1.0 - observed_weight
    if abs(observed_weight + missing_weight - 1.0) > 1e-12:
        raise ValueError("multi-seed baseline weights must reconcile")
    return gross, net, observed_weight, missing_weight


def _cash_lock_selection_id(*, population: ModelCandidatePopulation, exit_time: str, scenario: str, seed: int, top_k: int) -> str:
    return canonical_identity_hash(
        {
            "status": "CASH_LOCKED",
            "population_hash": population.population_hash,
            "exit_time": exit_time,
            "cost_scenario": scenario,
            "seed": seed,
            "top_k": top_k,
        }
    )


def _summaries(*, return_rows: list[dict[str, Any]], equity_index: Mapping[tuple[str, str, str, str], dict[str, Any]], primary_seed: int, seed_count: int) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for row in return_rows:
        key = (
            str(row["decision_date"]),
            str(row["model_id"]),
            str(row["exit_time"]),
            str(row["cost_scenario"]),
        )
        grouped.setdefault(key, []).append(row)
    output: list[dict[str, Any]] = []
    for key, rows in sorted(grouped.items()):
        if len(rows) != seed_count:
            raise ValueError("daily null group must contain every seed exactly once")
        gross = tuple(float(row["gross_return"]) for row in rows)
        net = tuple(float(row["net_return"]) for row in rows)
        primary = next((row for row in rows if row["seed"] == primary_seed), None)
        if primary is None:
            raise ValueError("daily null group is missing primary seed")
        model = equity_index.get(key)
        if model is None:
            raise ValueError("daily null group is missing model equity evidence")
        selection_applicable = primary["selection_status"] == "EXECUTED"
        unique_count = (
            len({str(row["selected_symbols_hash"]) for row in rows})
            if selection_applicable
            else None
        )
        output.append(
            {
                "schema_version": MR2B_MULTISEED_SCHEMA_VERSION,
                "decision_date": key[0],
                "model_id": key[1],
                "exit_time": key[2],
                "cost_scenario": key[3],
                "seed_count": seed_count,
                "selection_applicable": selection_applicable,
                "unique_selection_count": unique_count,
                "unique_selection_ratio": (
                    unique_count / seed_count if unique_count is not None else None
                ),
                "selection_collision_rate": (
                    1.0 - unique_count / seed_count if unique_count is not None else None
                ),
                "primary_seed": primary_seed,
                "primary_seed_selection_id": primary["selection_id"],
                "primary_seed_gross_return": primary["gross_return"],
                "primary_seed_net_return": primary["net_return"],
                "population_hash": primary["population_hash"],
                **_distribution_fields("gross", gross),
                **_distribution_fields("net", net),
                "model_gross_percentile": empirical_percentile(gross, _finite(model.get("gross_return"), "model gross return")),
                "model_net_percentile": empirical_percentile(net, _finite(model.get("net_return"), "model net return")),
                "cash_locked": not selection_applicable,
                "data_status": "AVAILABLE",
                "data_eligibility": "EXPLORATORY",
            }
        )
    return output


def _distribution_fields(prefix: str, values: tuple[float, ...]) -> dict[str, float]:
    return {
        f"{prefix}_median": linear_quantile(values, 0.50),
        f"{prefix}_p10": linear_quantile(values, 0.10),
        f"{prefix}_p25": linear_quantile(values, 0.25),
        f"{prefix}_p75": linear_quantile(values, 0.75),
        f"{prefix}_p90": linear_quantile(values, 0.90),
        f"{prefix}_min": min(values),
        f"{prefix}_max": max(values),
    }


def _reconcile_primary_seed(*, primary_seed: int, return_rows: list[dict[str, Any]], baseline_index: Mapping[tuple[str, str, str, str, int, str], dict[str, Any]], selections: Mapping[tuple[date, str, int], Any], primary_symbols: Mapping[tuple[str, str], tuple[str, ...]], dates: tuple[date, ...], model_ids: tuple[str, ...], scenarios: tuple[str, ...]) -> dict[str, Any]:
    return_index = {
        (str(row["decision_date"]), str(row["model_id"]), str(row["exit_time"]), str(row["cost_scenario"]), int(row["seed"])): row
        for row in return_rows
    }
    checked = mismatches = 0
    maximum = 0.0
    for day in dates:
        for model in model_ids:
            selection = selections[(day, model, primary_seed)]
            persisted_symbols = primary_symbols.get((day.isoformat(), model))
            if persisted_symbols is not None and persisted_symbols != selection.symbols:
                mismatches += 1
            for exit_time in _EXIT_TARGETS:
                for scenario in scenarios:
                    checked += 1
                    row = return_index[(day.isoformat(), model, exit_time, scenario, primary_seed)]
                    gross, net = _primary_baseline_pair(
                        baseline_index, day, model, exit_time, scenario, primary_seed
                    )
                    differences = (
                        abs(float(row["gross_return"]) - float(gross["gross_return"])),
                        abs(float(row["net_return"]) - float(net["net_return"])),
                        abs(float(row["observed_weight"]) - float(net["observed_weight"])),
                        abs(float(row["missing_weight"]) - float(net["missing_weight"])),
                        abs(float(row["cash_locked_weight"]) - float(net["cash_locked_weight"])),
                    )
                    maximum = max(maximum, *differences)
                    expected_status = str(net["baseline_slot_status"])
                    expected_count = int(net["selected_symbol_count"])
                    expected_symbols_hash = str(net["selected_symbols_hash"])
                    if (
                        max(differences) > 1e-12
                        or row["selection_id"] != net["selection_id"]
                        or row["selection_status"] != expected_status
                        or int(row["selected_symbol_count"]) != expected_count
                        or row["selected_symbols_hash"] != expected_symbols_hash
                    ):
                        mismatches += 1
    return {
        "schema_version": "mr-2b-primary-seed-reconciliation-v2",
        "primary_seed": primary_seed,
        "checked_identity_fields": [
            "selection_id",
            "selected_symbols_hash",
            "selection_status",
            "selected_symbol_count",
        ],
        "checked_rows": checked,
        "matched_rows": checked - mismatches,
        "mismatch_rows": mismatches,
        "maximum_numeric_difference": maximum,
        "status": "EXACT_MATCH" if mismatches == 0 else "MISMATCH",
    }


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{label} must be finite numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite numeric")
    return result
