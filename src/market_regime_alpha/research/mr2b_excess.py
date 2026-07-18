"""Typed, descriptive MR-2B Candidate-excess primitives without hypothesis promotion."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
import math
from statistics import mean
from typing import Iterable


MR2B_PRIMARY_MODEL_ID = "prr-mvp-1-b1-e-v1"
MR2B_PRIMARY_EXIT_TIME = "10:30"
MR2B_PRIMARY_COST_SCENARIO = "BASE"
MR2B_EFFECT_THRESHOLD = 0.001


class WatchlistDirection(str, Enum):
    UP = "UP"
    DOWN = "DOWN"


@dataclass(frozen=True, slots=True)
class DailyConditionalityObservation:
    decision_date: date
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
            ("model_id", self.model_id),
            ("exit_time", self.exit_time),
            ("cost_scenario", self.cost_scenario),
        ):
            if not isinstance(text_value, str) or not text_value.strip():
                raise ValueError(f"{label} must be non-empty")

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
    for row in ordered:
        if (
            row.model_id != MR2B_PRIMARY_MODEL_ID
            or row.exit_time != MR2B_PRIMARY_EXIT_TIME
            or row.cost_scenario != MR2B_PRIMARY_COST_SCENARIO
        ):
            raise ValueError("observations must match the frozen MR-2B primary comparison")
    grouped = {
        direction: tuple(row for row in ordered if row.context_label is direction)
        for direction in WatchlistDirection
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


def _finite_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be finite numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite numeric")
    return result
