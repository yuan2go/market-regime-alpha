"""Secondary path-diagnostic projection for the frozen Primary model."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Any, Iterable, Mapping


COMPETING_EVENT_TARGET_ID = "MORNING_UP_005_DOWN_005_V1"
COMPETING_EVENT_RULE_ID = "mr2b-primary-morning-competing-event-diagnostic-v1"


@dataclass(frozen=True, slots=True)
class CompetingEventResult:
    status: str
    target_contract_id: str
    rows: tuple[dict[str, Any], ...]
    coverage: float
    missing_target_count: int
    interpretation: str = "SECONDARY_PATH_DIAGNOSTIC"


def build_competing_event_diagnostics(
    *,
    target_rows: Iterable[Mapping[str, Any]],
    ranking_rows: Iterable[Mapping[str, Any]],
    multiseed_selection_rows: Iterable[Mapping[str, Any]],
    primary_model_id: str,
    top_k: int,
) -> CompetingEventResult:
    targets = tuple(dict(row) for row in target_rows if row.get("target_id") == COMPETING_EVENT_TARGET_ID)
    rankings = tuple(dict(row) for row in ranking_rows)
    selections = tuple(dict(row) for row in multiseed_selection_rows)
    if not targets or not rankings or not selections:
        return CompetingEventResult(
            status="COMPETING_EVENT_EVIDENCE_UNAVAILABLE",
            target_contract_id=COMPETING_EVENT_TARGET_ID,
            rows=(),
            coverage=0.0,
            missing_target_count=len(targets),
        )
    target_index: dict[tuple[str, str], str] = {}
    missing_targets = 0
    for row in targets:
        key = (str(row.get("decision_date")), str(row.get("symbol")))
        if key in target_index:
            raise ValueError("competing-event target keys must be unique")
        if row.get("status") != "AVAILABLE" or row.get("outcome") not in {
            "UP_FIRST", "DOWN_FIRST", "TIMEOUT", "AMBIGUOUS"
        }:
            missing_targets += 1
            continue
        target_index[key] = str(row["outcome"])
    primary_rankings = tuple(
        row
        for row in rankings
        if row.get("model_id") == primary_model_id
        and row.get("target_id") == "target-r5-decision-reference-to-next-session-close-return-v1"
    )
    by_date: dict[str, list[dict[str, Any]]] = {}
    for row in primary_rankings:
        by_date.setdefault(str(row.get("decision_date")), []).append(row)
    if not by_date:
        return CompetingEventResult(
            "COMPETING_EVENT_EVIDENCE_UNAVAILABLE", COMPETING_EVENT_TARGET_ID, (), 0.0, len(targets)
        )
    model_symbols: list[tuple[str, str]] = []
    population_symbols: list[tuple[str, str]] = []
    for day, rows in sorted(by_date.items()):
        eligible = tuple(
            sorted(
                (
                    int(row["rank"]),
                    str(row["symbol"]),
                )
                for row in rows
                if bool(row.get("eligible_for_ranking")) and row.get("rank") is not None
            )
        )
        if tuple(rank for rank, _ in eligible) != tuple(range(1, len(eligible) + 1)):
            raise ValueError("Primary competing-event ranking must be contiguous")
        population_symbols.extend((day, symbol) for _, symbol in eligible)
        model_symbols.extend((day, symbol) for rank, symbol in eligible if rank <= top_k)
    model = _outcome_metrics(model_symbols, target_index)
    population = _outcome_metrics(population_symbols, target_index)
    selected_by_seed: dict[int, list[tuple[str, str]]] = {}
    for row in selections:
        if row.get("model_id") != primary_model_id:
            continue
        selected_by_seed.setdefault(int(row["seed"]), []).append(
            (str(row["decision_date"]), str(row["symbol"]))
        )
    if not selected_by_seed:
        return CompetingEventResult(
            "COMPETING_EVENT_EVIDENCE_UNAVAILABLE", COMPETING_EVENT_TARGET_ID, (), 0.0, len(targets)
        )
    seed_metrics = tuple(_outcome_metrics(values, target_index) for _, values in sorted(selected_by_seed.items()))
    matched = {
        key: median(float(item[key]) for item in seed_metrics)
        for key in ("UP_FIRST_rate", "DOWN_FIRST_rate", "TIMEOUT_rate", "AMBIGUOUS_rate", "coverage")
    }
    output_rows = (
        {"scope": "B1_E_TOP5", **model},
        {"scope": "MODEL_POPULATION_ALL_CANDIDATE", **population},
        {
            "scope": "MULTISEED_MATCHED_K_MEDIAN",
            **matched,
            "observed_count": median(float(item["observed_count"]) for item in seed_metrics),
            "missing_target_count": median(float(item["missing_target_count"]) for item in seed_metrics),
        },
        {
            "scope": "PRIMARY_DIAGNOSTIC_LIFTS",
            "UP_FIRST_lift_vs_all_candidate": model["UP_FIRST_rate"] - population["UP_FIRST_rate"],
            "UP_FIRST_lift_vs_matched_k_median": model["UP_FIRST_rate"] - matched["UP_FIRST_rate"],
            "DOWN_FIRST_reduction_vs_all_candidate": population["DOWN_FIRST_rate"] - model["DOWN_FIRST_rate"],
            "DOWN_FIRST_reduction_vs_matched_k_median": matched["DOWN_FIRST_rate"] - model["DOWN_FIRST_rate"],
            "opportunity_recall": (
                model["UP_FIRST_count"] / population["UP_FIRST_count"]
                if population["UP_FIRST_count"]
                else None
            ),
            "adverse_first_rate": model["DOWN_FIRST_rate"],
            "coverage": model["coverage"],
        },
    )
    return CompetingEventResult(
        status="AVAILABLE",
        target_contract_id=COMPETING_EVENT_TARGET_ID,
        rows=tuple(dict(row, target_id=COMPETING_EVENT_TARGET_ID, diagnostic_role="SECONDARY_PATH_DIAGNOSTIC") for row in output_rows),
        coverage=float(model["coverage"]),
        missing_target_count=missing_targets + int(model["missing_target_count"]),
    )


def _outcome_metrics(
    symbols: Iterable[tuple[str, str]], target_index: Mapping[tuple[str, str], str]
) -> dict[str, Any]:
    values = tuple(symbols)
    outcomes = tuple(target_index[key] for key in values if key in target_index)
    counts = {name: outcomes.count(name) for name in ("UP_FIRST", "DOWN_FIRST", "TIMEOUT", "AMBIGUOUS")}
    observed = len(outcomes)
    return {
        **{f"{name}_count": count for name, count in counts.items()},
        **{f"{name}_rate": count / observed if observed else 0.0 for name, count in counts.items()},
        "observed_count": observed,
        "missing_target_count": len(values) - observed,
        "coverage": observed / len(values) if values else 0.0,
    }
