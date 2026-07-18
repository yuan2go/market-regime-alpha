"""Scope-consistent competing-event diagnostics for MR-2B F2B v2."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Any, Iterable, Mapping

from market_regime_alpha.research.mr2b_f2b_competing_events import (
    COMPETING_EVENT_RULE_ID,
    COMPETING_EVENT_TARGET_ID,
)


@dataclass(frozen=True, slots=True)
class CompetingEventCoverage:
    top5_requested_count: int
    top5_observed_count: int
    top5_missing_target_count: int
    top5_coverage: float
    population_requested_count: int
    population_observed_count: int
    population_missing_target_count: int
    population_coverage: float
    matched_k_requested_count_median: float
    matched_k_observed_count_median: float
    matched_k_missing_target_median: float
    matched_k_coverage_median: float
    global_target_row_count: int
    global_unavailable_target_count: int


@dataclass(frozen=True, slots=True)
class CompetingEventResultV2:
    status: str
    target_contract_id: str
    rule_id: str
    rows: tuple[dict[str, Any], ...]
    coverage: CompetingEventCoverage
    interpretation: str = "SECONDARY_PATH_DIAGNOSTIC"


def build_competing_event_diagnostics_v2(
    *,
    target_rows: Iterable[Mapping[str, Any]],
    ranking_rows: Iterable[Mapping[str, Any]],
    multiseed_selection_rows: Iterable[Mapping[str, Any]],
    primary_model_id: str,
    top_k: int,
) -> CompetingEventResultV2:
    targets = tuple(dict(row) for row in target_rows if row.get("target_id") == COMPETING_EVENT_TARGET_ID)
    target_index: dict[tuple[str, str], str] = {}
    unavailable = 0
    for row in targets:
        key = (str(row.get("decision_date")), str(row.get("symbol")))
        if key in target_index:
            raise ValueError("competing-event target keys must be unique")
        outcome = row.get("outcome")
        if row.get("status") != "AVAILABLE" or outcome not in {
            "UP_FIRST",
            "DOWN_FIRST",
            "TIMEOUT",
            "AMBIGUOUS",
        }:
            unavailable += 1
            continue
        target_index[key] = str(outcome)
    rankings = tuple(
        dict(row)
        for row in ranking_rows
        if row.get("model_id") == primary_model_id
        and row.get("target_id") == "target-r5-decision-reference-to-next-session-close-return-v1"
    )
    selections = tuple(dict(row) for row in multiseed_selection_rows if row.get("model_id") == primary_model_id)
    if not targets or not rankings or not selections:
        empty = CompetingEventCoverage(0, 0, 0, 0.0, 0, 0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, len(targets), unavailable)
        return CompetingEventResultV2(
            "COMPETING_EVENT_EVIDENCE_UNAVAILABLE",
            COMPETING_EVENT_TARGET_ID,
            COMPETING_EVENT_RULE_ID,
            (),
            empty,
        )
    by_date: dict[str, list[dict[str, Any]]] = {}
    for row in rankings:
        by_date.setdefault(str(row.get("decision_date")), []).append(row)
    top5_symbols: list[tuple[str, str]] = []
    population_symbols: list[tuple[str, str]] = []
    for day, rows in sorted(by_date.items()):
        eligible = tuple(
            sorted(
                (int(row["rank"]), str(row["symbol"]))
                for row in rows
                if bool(row.get("eligible_for_ranking")) and row.get("rank") is not None
            )
        )
        if tuple(rank for rank, _ in eligible) != tuple(range(1, len(eligible) + 1)):
            raise ValueError("Primary competing-event ranking must be contiguous")
        population_symbols.extend((day, symbol) for _, symbol in eligible)
        top5_symbols.extend((day, symbol) for rank, symbol in eligible if rank <= top_k)
    top5 = _metrics(top5_symbols, target_index)
    population = _metrics(population_symbols, target_index)
    by_seed: dict[int, list[tuple[str, str]]] = {}
    for row in selections:
        by_seed.setdefault(int(row["seed"]), []).append(
            (str(row["decision_date"]), str(row["symbol"]))
        )
    seed_metrics = tuple(_metrics(rows, target_index) for _, rows in sorted(by_seed.items()))
    matched = {
        key: median(float(row[key]) for row in seed_metrics)
        for key in (
            "requested_count",
            "observed_count",
            "missing_target_count",
            "coverage",
            "UP_FIRST_rate",
            "DOWN_FIRST_rate",
            "TIMEOUT_rate",
            "AMBIGUOUS_rate",
        )
    }
    coverage = CompetingEventCoverage(
        top5_requested_count=int(top5["requested_count"]),
        top5_observed_count=int(top5["observed_count"]),
        top5_missing_target_count=int(top5["missing_target_count"]),
        top5_coverage=float(top5["coverage"]),
        population_requested_count=int(population["requested_count"]),
        population_observed_count=int(population["observed_count"]),
        population_missing_target_count=int(population["missing_target_count"]),
        population_coverage=float(population["coverage"]),
        matched_k_requested_count_median=matched["requested_count"],
        matched_k_observed_count_median=matched["observed_count"],
        matched_k_missing_target_median=matched["missing_target_count"],
        matched_k_coverage_median=matched["coverage"],
        global_target_row_count=len(targets),
        global_unavailable_target_count=unavailable,
    )
    output_rows = (
        {"scope": "B1_E_TOP5", **top5},
        {"scope": "MODEL_POPULATION_ALL_CANDIDATE", **population},
        {"scope": "MULTISEED_MATCHED_K_MEDIAN", **matched},
        {
            "scope": "PRIMARY_DIAGNOSTIC_LIFTS",
            "UP_FIRST_lift_vs_all_candidate": top5["UP_FIRST_rate"] - population["UP_FIRST_rate"],
            "UP_FIRST_lift_vs_matched_k_median": top5["UP_FIRST_rate"] - matched["UP_FIRST_rate"],
            "DOWN_FIRST_reduction_vs_all_candidate": population["DOWN_FIRST_rate"] - top5["DOWN_FIRST_rate"],
            "DOWN_FIRST_reduction_vs_matched_k_median": matched["DOWN_FIRST_rate"] - top5["DOWN_FIRST_rate"],
            "opportunity_recall": (
                top5["UP_FIRST_count"] / population["UP_FIRST_count"]
                if population["UP_FIRST_count"]
                else None
            ),
            "adverse_first_rate": top5["DOWN_FIRST_rate"],
            "coverage": top5["coverage"],
        },
    )
    output = tuple(
        dict(row, target_id=COMPETING_EVENT_TARGET_ID, diagnostic_role="SECONDARY_PATH_DIAGNOSTIC")
        for row in output_rows
    )
    return CompetingEventResultV2("AVAILABLE", COMPETING_EVENT_TARGET_ID, COMPETING_EVENT_RULE_ID, output, coverage)


def _metrics(
    symbols: Iterable[tuple[str, str]], target_index: Mapping[tuple[str, str], str]
) -> dict[str, Any]:
    values = tuple(symbols)
    outcomes = tuple(target_index[key] for key in values if key in target_index)
    observed = len(outcomes)
    counts = {name: outcomes.count(name) for name in ("UP_FIRST", "DOWN_FIRST", "TIMEOUT", "AMBIGUOUS")}
    return {
        "requested_count": len(values),
        "observed_count": observed,
        "missing_target_count": len(values) - observed,
        "coverage": observed / len(values) if values else 0.0,
        **{f"{name}_count": count for name, count in counts.items()},
        **{f"{name}_rate": count / observed if observed else 0.0 for name, count in counts.items()},
    }
