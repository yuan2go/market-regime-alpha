"""Opt-in independent IC summaries over retained canonical daily estimates.

The original paired IC summary correctly requires both rankings. A constant
reference cannot supply one. V3 exposes each model's own daily estimates without
changing that paired estimand, its missing days, or the frozen v1/v2 projection.
"""

from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from typing import Any

from market_regime_alpha.shared.hashing import canonical_json_sha256


def with_independent_ordering(original: dict[str, Any]) -> dict[str, Any]:
    if original.get("schema") != "mra-historical-comparison-v2":
        raise ValueError("independent ordering projection requires the original rolling v2 projection")
    prior = {key: value for key, value in original.items() if key != "projection_sha256"}
    if canonical_json_sha256(prior) != original.get("projection_sha256"):
        raise ValueError("original historical projection hash differs")
    with localcontext() as context:
        context.prec, context.rounding = 38, ROUND_HALF_EVEN
        ordering = _ordering(original)
    result = prior | {"schema": "mra-historical-comparison-v3",
        "prior_projection_sha256": original["projection_sha256"], "independent_ordering": ordering}
    return result | {"projection_sha256": canonical_json_sha256(result)}


def _summary(rows, side: str) -> dict[str, Any]:
    days = tuple(row["session"] for row in rows)
    if len(set(days)) != len(days) or days != tuple(sorted(days)):
        raise ValueError("independent IC requires complete unique ordered decision dates")
    daily = []
    for row in rows:
        metric = row[side]["rank_ic"]
        value = metric["value"]
        if value is not None and (not isinstance(value, Decimal) or not value.is_finite()):
            raise ValueError("independent IC requires original finite Decimal estimates")
        if (metric["state"] == "NOT_ESTIMABLE") != (value is None):
            raise ValueError("independent IC estimate and original state conflict")
        daily.append({"session": row["session"], "observation_count": row["common_observation_count"],
            "rank_ic": value, "state": metric["state"], "reason_code": metric["reason_code"]})
    values = tuple(row["rank_ic"] for row in daily if row["rank_ic"] is not None)
    ordered = sorted(values)
    count = len(values)
    middle = count // 2
    median = None if not count else ordered[middle] if count % 2 else (ordered[middle - 1] + ordered[middle]) / 2
    return {"state": "DESCRIPTIVE" if values else "NOT_ESTIMABLE", "expected_sessions": len(days),
        "estimable_sessions": count, "not_estimable_sessions": len(days) - count,
        "mean": None if not count else sum(values, Decimal(0)) / count, "median": median,
        "minimum": min(values) if values else None, "maximum": max(values) if values else None,
        "positive_sessions": sum(value > 0 for value in values), "negative_sessions": sum(value < 0 for value in values),
        "zero_sessions": sum(value == 0 for value in values), "per_day": tuple(daily),
        "denominator": "ONE_WEIGHT_PER_ESTIMABLE_DECISION_SESSION; UNAVAILABLE_DAYS_RETAINED",
        "uncertainty": "DESCRIPTIVE_SUMMARY; ORIGINAL_PREDECLARED_PAIRED_DELTA_INTERVALS_UNCHANGED"}


def _ordering(original) -> dict[str, Any]:
    arms = []
    for arm in original["statistics"]["arms"]:
        daily = arm["common_population"]["daily"]
        years = tuple(dict.fromkeys(str(row["session"])[:4] for row in daily))
        arms.append({"arm_id": arm["arm_id"], "arm_code": arm["arm_code"],
            "own_population": _summary(arm["own_population"]["daily"], "model"),
            "all_arm_common_population": _summary(daily, "model"),
            "per_fold": tuple({"fold_id": row["fold_id"], "statistics": _summary(row["statistics"]["daily"], "model")} for row in arm["per_fold"]),
            "per_month": tuple({"month": row["month"], "statistics": _summary(row["statistics"]["daily"], "model")} for row in arm["per_month"]),
            "per_year": tuple({"year": year, "statistics": _summary(tuple(row for row in daily if str(row["session"]).startswith(year)), "model")} for year in years)})
    pairs = []
    for comparison in original["robustness"]["comparisons"]:
        daily = comparison["comparison"]["daily"]
        pairs.append({"model": comparison["model"], "reference": comparison["reference"],
            "paired_observations": comparison["paired_observations"],
            "model_on_pair_population": _summary(daily, "model"),
            "reference_on_pair_population": _summary(daily, "baseline"),
            "mean_paired_daily_rank_ic_delta": comparison["mean_daily_rank_ic_delta"],
            "paired_daily_ic_uncertainty": comparison["paired_daily_ic_uncertainty"],
            "paired_ic_day_signs": comparison["ic_day_signs"]})
    return {"schema": "mra-independent-ordering-diagnostics-v1", "arms": tuple(arms), "comparisons": tuple(pairs),
        "source": "UNCHANGED_CANONICAL_DAILY_RANK_IC_ESTIMATES; NO_NEW_LABELS_OR_RANK_FORMULA",
        "interpretation": "MODEL_RANK_ESTIMABILITY_IS_INDEPENDENT_OF_CONSTANT_REFERENCE; PAIRED_DELTA_STILL_REQUIRES_BOTH",
        "selection_rule_changed": False, "economic_validity": "NOT_ESTIMABLE_NO_ACCOUNT_EXECUTION_PATH"}
