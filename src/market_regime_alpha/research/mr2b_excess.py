"""Excess-based, order-stable MR-2B primary conditionality diagnostic."""
from __future__ import annotations

from statistics import mean
from typing import Iterable

MR2B_PRIMARY_HYPOTHESIS_ID = "mr2b-primary-b1e-1030-base-watchlist-direction-v1"


def primary_assessment(rows: Iterable[tuple[str, str, float, float]]) -> dict[str, object]:
    """Use model-net minus Candidate-net excess, never absolute return."""
    ordered = sorted(rows, key=lambda item: item[0])
    grouped: dict[str, list[float]] = {"UP": [], "DOWN": []}
    for _, label, model_net, candidate_net in ordered:
        if label in grouped:
            grouped[label].append(model_net - candidate_net)
    if not grouped["UP"] or not grouped["DOWN"]:
        return {"assessment": "INSUFFICIENT_EVIDENCE"}
    up, down = mean(grouped["UP"]), mean(grouped["DOWN"])
    difference = up - down
    if all(abs(value) < 1e-12 for value in (*grouped["UP"], *grouped["DOWN"])):
        assessment = "NO_EXCESS_CONDITIONALITY"
    elif len(grouped["UP"]) >= 15 and len(grouped["DOWN"]) >= 15 and abs(difference) >= 0.001:
        assessment = "PRIMARY_HYPOTHESIS_SUPPORTED_EXPLORATORY"
    else:
        assessment = "PRIMARY_HYPOTHESIS_NOT_SUPPORTED"
    return {
        "hypothesis_id": MR2B_PRIMARY_HYPOTHESIS_ID,
        "left_mean_daily_excess": up,
        "right_mean_daily_excess": down,
        "difference_of_mean_daily_excess": difference,
        "slice_counts": [len(grouped["UP"]), len(grouped["DOWN"])],
        "assessment": assessment,
    }
