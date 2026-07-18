"""Typed, descriptive MR-2B Candidate-excess primitives without hypothesis promotion."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
import math
from statistics import mean
from typing import Iterable

from market_regime_alpha.research.prr_artifact_schemas import (
    CandidateBaselineId,
    MatchedKSelection,
    ModelCandidatePopulation,
)


MR2B_PRIMARY_MODEL_ID = "prr-mvp-1-b1-e-v1"
MR2B_PRIMARY_EXIT_TIME = "10:30"
MR2B_PRIMARY_COST_SCENARIO = "BASE"
MR2B_EFFECT_THRESHOLD = 0.001


class WatchlistDirection(str, Enum):
    UP = "UP"
    DOWN = "DOWN"
    FLAT = "FLAT"


@dataclass(frozen=True, slots=True)
class DailyConditionalityObservation:
    decision_date: date
    dataset_id: str
    mr1_run_id: str
    model_population_hash: str
    matched_k_selection_id: str
    matched_k_seed: int
    context_label: WatchlistDirection
    model_id: str
    exit_time: str
    cost_scenario: str
    model_gross_return: float
    model_net_return: float
    all_candidate_gross_return: float
    matched_k_gross_return: float
    matched_k_net_return: float

    def __post_init__(self) -> None:
        if not isinstance(self.decision_date, date):
            raise TypeError("decision_date must be a date")
        if not isinstance(self.context_label, WatchlistDirection):
            raise TypeError("context_label must be a WatchlistDirection")
        for label, value in (
            ("model_gross_return", self.model_gross_return),
            ("model_net_return", self.model_net_return),
            ("all_candidate_gross_return", self.all_candidate_gross_return),
            ("matched_k_gross_return", self.matched_k_gross_return),
            ("matched_k_net_return", self.matched_k_net_return),
        ):
            _finite_number(value, label)
        for label, text_value in (
            ("dataset_id", self.dataset_id),
            ("mr1_run_id", self.mr1_run_id),
            ("model_population_hash", self.model_population_hash),
            ("matched_k_selection_id", self.matched_k_selection_id),
            ("model_id", self.model_id),
            ("exit_time", self.exit_time),
            ("cost_scenario", self.cost_scenario),
        ):
            if not isinstance(text_value, str) or not text_value.strip():
                raise ValueError(f"{label} must be non-empty")
        if not isinstance(self.matched_k_seed, int) or isinstance(self.matched_k_seed, bool):
            raise TypeError("matched_k_seed must be an int")

    @property
    def gross_excess_vs_all_candidate(self) -> float:
        return self.model_gross_return - self.all_candidate_gross_return

    @property
    def gross_excess_vs_matched_k(self) -> float:
        return self.model_gross_return - self.matched_k_gross_return

    @property
    def net_excess_vs_matched_k(self) -> float:
        return self.model_net_return - self.matched_k_net_return

    @property
    def cost_drag_difference(self) -> float:
        return (self.model_net_return - self.model_gross_return) - (
            self.matched_k_net_return - self.matched_k_gross_return
        )


def primary_assessment(rows: Iterable[DailyConditionalityObservation]) -> dict[str, object]:
    """Summarize the frozen primary slice descriptively; F2 owns statistical promotion."""

    ordered = tuple(sorted(rows, key=lambda item: item.decision_date))
    if not ordered:
        return {"assessment": "INSUFFICIENT_EVIDENCE"}
    dates = tuple(row.decision_date for row in ordered)
    if len(dates) != len(set(dates)):
        raise ValueError("Decision Dates must be unique")
    if len({(row.dataset_id, row.mr1_run_id) for row in ordered}) != 1:
        raise ValueError("observations must share one Dataset and MR-1 run")
    for row in ordered:
        if (
            row.model_id != MR2B_PRIMARY_MODEL_ID
            or row.exit_time != MR2B_PRIMARY_EXIT_TIME
            or row.cost_scenario != MR2B_PRIMARY_COST_SCENARIO
        ):
            raise ValueError("observations must match the frozen MR-2B primary comparison")
    grouped = {
        direction: tuple(row for row in ordered if row.context_label is direction)
        for direction in (WatchlistDirection.UP, WatchlistDirection.DOWN)
    }
    if any(not values for values in grouped.values()):
        return {"assessment": "INSUFFICIENT_EVIDENCE"}
    up = grouped[WatchlistDirection.UP]
    down = grouped[WatchlistDirection.DOWN]
    up_net = mean(row.net_excess_vs_matched_k for row in up)
    down_net = mean(row.net_excess_vs_matched_k for row in down)
    difference = up_net - down_net
    all_excess = tuple(row.net_excess_vs_matched_k for row in ordered)
    if all(abs(value) < 1e-12 for value in all_excess):
        assessment = "NO_EXCESS"
    elif abs(difference) >= MR2B_EFFECT_THRESHOLD:
        assessment = "EFFECT_THRESHOLD_MET"
    else:
        assessment = "EFFECT_THRESHOLD_NOT_MET"
    return {
        "assessment": assessment,
        "slice_counts": {"UP": len(up), "DOWN": len(down)},
        "up_mean_net_excess_vs_matched_k": up_net,
        "down_mean_net_excess_vs_matched_k": down_net,
        "difference_of_mean_net_excess_vs_matched_k": difference,
        "mean_gross_excess_vs_all_candidate": mean(
            row.gross_excess_vs_all_candidate for row in ordered
        ),
        "mean_gross_excess_vs_matched_k": mean(row.gross_excess_vs_matched_k for row in ordered),
        "mean_cost_drag_difference": mean(row.cost_drag_difference for row in ordered),
    }


def build_daily_conditionality_observation(
    *,
    dataset_id: str,
    mr1_run_id: str,
    context_label: WatchlistDirection,
    model_equity_row: dict[str, object],
    baseline_family_rows: Iterable[dict[str, object]],
    population: ModelCandidatePopulation,
    matched_k_selection: MatchedKSelection,
) -> DailyConditionalityObservation:
    """Build one typed observation from already verified MR-1 population evidence."""

    rows = tuple(baseline_family_rows)
    indexed = {CandidateBaselineId(str(row["baseline_id"])): row for row in rows}
    if set(indexed) != set(CandidateBaselineId):
        raise ValueError("conditionality observation requires one complete baseline family")
    decision_day = date.fromisoformat(str(model_equity_row["session_date"]))
    model_id = str(model_equity_row["model_id"])
    exit_time = str(model_equity_row["exit_time"])
    cost_scenario = str(model_equity_row["cost_scenario"])
    if (
        population.dataset_id != dataset_id
        or population.decision_date != decision_day
        or population.model_id != model_id
        or matched_k_selection.population != population
    ):
        raise ValueError("conditionality observation population evidence is misaligned")
    for row in rows:
        if (
            str(row["decision_date"]) != decision_day.isoformat()
            or str(row["model_id"]) != model_id
            or str(row["exit_time"]) != exit_time
            or str(row["cost_scenario"]) != cost_scenario
            or str(row["candidate_population_hash"]) != population.population_hash
        ):
            raise ValueError("conditionality baseline family is misaligned")
    return DailyConditionalityObservation(
        decision_date=decision_day,
        dataset_id=dataset_id,
        mr1_run_id=mr1_run_id,
        model_population_hash=population.population_hash,
        matched_k_selection_id=matched_k_selection.selection_id,
        matched_k_seed=matched_k_selection.seed,
        context_label=context_label,
        model_id=model_id,
        exit_time=exit_time,
        cost_scenario=cost_scenario,
        model_gross_return=_finite_number(
            model_equity_row["gross_return"], "model gross return"
        ),
        model_net_return=_finite_number(model_equity_row["net_return"], "model net return"),
        all_candidate_gross_return=_finite_number(
            indexed[CandidateBaselineId.ALL_CANDIDATE_GROSS_V1]["gross_return"],
            "all-Candidate gross return",
        ),
        matched_k_gross_return=_finite_number(
            indexed[CandidateBaselineId.MATCHED_K_HASH_GROSS_V1]["gross_return"],
            "matched-K gross return",
        ),
        matched_k_net_return=_finite_number(
            indexed[CandidateBaselineId.MATCHED_K_HASH_NET_V1]["net_return"],
            "matched-K net return",
        ),
    )


def _finite_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be finite numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite numeric")
    return result
