"""MR-2 descriptive decomposition for the fixed B0/B1 morning-pop validation.

All functions consume post-hoc Target rows and frozen Candidate ranks.  They are diagnostics,
not Feature transforms or decision inputs, and preserve the EXPLORATORY authority ceiling.
"""

from __future__ import annotations

from collections import defaultdict
import math
from statistics import mean, pstdev
from typing import Any, Iterable, Mapping
from market_regime_alpha.research.mr2a_regime import directional_score


MR2_SCHEMA_VERSION = "mr-2-morning-pop-failure-decomposition-v1"


def feature_target_diagnostics(
    *,
    ranking_rows: Iterable[Mapping[str, Any]],
    target_rows: Iterable[Mapping[str, Any]],
) -> tuple[tuple[dict[str, Any], ...], tuple[dict[str, Any], ...]]:
    """Return per-date/aggregate IC and spread diagnostics without cross-date normalization."""

    targets = {(str(row["decision_date"]), str(row["symbol"]), str(row["target_id"])): row for row in target_rows}
    mfe_targets = {
        (str(row["decision_date"]), str(row["symbol"])): float(row["value"])
        for row in target_rows
        if row["target_id"] == "MORNING_1030_MFE" and row.get("status") == "AVAILABLE" and row.get("value") is not None
    }
    by_date_feature: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in ranking_rows:
        if str(row["target_id"]) == "target-r5-decision-reference-to-next-session-close-return-v1":
            for feature_id, value in dict(row.get("feature_values") or {}).items():
                if value is not None:
                    by_date_feature[(str(row["decision_date"]), str(feature_id))].append(row)
    ic_rows: list[dict[str, Any]] = []
    spread_rows: list[dict[str, Any]] = []
    target_ids = sorted({str(row["target_id"]) for row in target_rows if row.get("status") == "AVAILABLE" and row.get("value") is not None})
    for (decision_date, feature_id), rows in sorted(by_date_feature.items()):
        # The frozen Candidate rows repeat feature values for every model.  One row per symbol is
        # enough for a cross-section; diagnostics must not give models duplicate observations.
        unique = {str(row["symbol"]): row for row in rows}
        population = tuple(unique.values())
        for target_id in target_ids:
            pairs = [
                (directional_score(feature_id, float(row["feature_values"][feature_id])), float(target["value"]), str(row["symbol"]), mfe_targets.get((decision_date, str(row["symbol"]))))
                for row in population
                if (target := targets.get((decision_date, str(row["symbol"]), target_id))) is not None
                and target["status"] == "AVAILABLE"
                and target["value"] is not None
            ]
            ic_row, spread_row = _cross_section(feature_id, target_id, decision_date, pairs, len(population))
            ic_rows.append(ic_row)
            spread_rows.append(spread_row)
    return tuple(_aggregate_ic(ic_rows)), tuple(_aggregate_spreads(spread_rows))


def decompose_model_failures(
    *,
    mr1_metrics: Iterable[Mapping[str, Any]],
    target_coverage: Mapping[str, float],
) -> tuple[dict[str, Any], ...]:
    """Assign independently auditable failure reasons; never collapse them into one label."""

    scenarios = {(str(row["model_id"]), str(row["exit_time"]), str(row["cost_scenario"])): row for row in mr1_metrics}
    rows: list[dict[str, Any]] = []
    target_by_exit = {"09:35": "NEXT_SESSION_0935_RETURN", "10:00": "NEXT_SESSION_1000_RETURN", "10:30": "NEXT_SESSION_1030_RETURN", "CLOSE": "NEXT_SESSION_CLOSE_RETURN"}
    for (model_id, exit_time, scenario), base in sorted(scenarios.items()):
        if scenario != "BASE":
            continue
        low = scenarios[(model_id, exit_time, "LOW")]
        high = scenarios[(model_id, exit_time, "HIGH")]
        coverage = float(target_coverage.get(target_by_exit[exit_time], 0.0))
        segments = [base.get("first_20_return"), base.get("middle_20_return"), base.get("last_20_return")]
        reasons: list[str] = []
        if float(base["gross_cumulative_return"]) <= 0.0:
            reasons.append("NO_GROSS_SIGNAL")
        if float(base["top5_gross_minus_candidate_gross"]) <= 0.0:
            reasons.append("NO_CROSS_SECTIONAL_ALPHA")
        if float(base["gross_cumulative_return"]) > 0.0 and float(base["net_cumulative_return"]) <= 0.0:
            reasons.append("COST_FRAGILE")
        if any(value is not None and value <= 0.0 for value in segments) and any(value is not None and value > 0.0 for value in segments):
            reasons.append("REGIME_UNSTABLE")
        if float(base["maximum_drawdown"]) < -0.15:
            reasons.append("DRAWDOWN_FAILED")
        if coverage < 0.95:
            reasons.append("TARGET_COVERAGE_INSUFFICIENT")
        if not reasons:
            reasons.append("SAMPLE_INCONCLUSIVE")
        rows.append({
            "schema_version": MR2_SCHEMA_VERSION, "model_id": model_id, "exit_time": exit_time,
            "target_id": target_by_exit[exit_time], "gross_cumulative_return": base["gross_cumulative_return"],
            "net_cumulative_return": base["net_cumulative_return"], "gross_candidate_excess": base["top5_gross_minus_candidate_gross"],
            "net_candidate_excess": base["top5_net_minus_candidate_net"], "cost_drag": float(base["gross_cumulative_return"]) - float(base["net_cumulative_return"]),
            "maximum_drawdown": base["maximum_drawdown"], "coverage": coverage,
            "first_20_return": base.get("first_20_return"), "middle_20_return": base.get("middle_20_return"), "last_20_return": base.get("last_20_return"),
            "best_day_contribution": None, "worst_day_contribution": None,
            "low_cost_net_cumulative_return": low["net_cumulative_return"], "high_cost_net_cumulative_return": high["net_cumulative_return"],
            "failure_reasons": reasons, "data_eligibility": "EXPLORATORY",
        })
    return tuple(rows)


def target_coverage(target_rows: Iterable[Mapping[str, Any]]) -> dict[str, float]:
    totals: dict[str, int] = defaultdict(int)
    available: dict[str, int] = defaultdict(int)
    for row in target_rows:
        target_id = str(row["target_id"])
        totals[target_id] += 1
        if row.get("status") == "AVAILABLE":
            available[target_id] += 1
    return {target_id: available[target_id] / total for target_id, total in sorted(totals.items()) if total}


def _cross_section(feature_id: str, target_id: str, decision_date: str, pairs: list[tuple[float, float, str, float | None]], population_count: int) -> tuple[dict[str, Any], dict[str, Any]]:
    features = [item[0] for item in pairs]
    values = [item[1] for item in pairs]
    pearson = _pearson(features, values)
    spearman = _pearson(_ranks(features), _ranks(values))
    ordered = sorted(pairs, key=lambda item: (item[0], item[2]))
    size = max(1, len(ordered) // 4)
    bottom = [item[1] for item in ordered[:size]]
    top_items = ordered[-min(5, len(ordered)):]
    top = [item[1] for item in top_items]
    top_quartile = [item[1] for item in ordered[-size:]]
    bottom_quartile = bottom
    ic = {"schema_version": MR2_SCHEMA_VERSION, "scope": "DECISION_DATE", "decision_date": decision_date, "feature_id": feature_id, "target_id": target_id, "pearson_ic": pearson, "spearman_rank_ic": spearman, "coverage": len(pairs) / population_count if population_count else 0.0, "pair_count": len(pairs), "data_eligibility": "EXPLORATORY"}
    mfe_values = [item[3] for item in top_items if item[3] is not None]
    spread = {"schema_version": MR2_SCHEMA_VERSION, "scope": "DECISION_DATE", "decision_date": decision_date, "feature_id": feature_id, "target_id": target_id, "top5_mean": mean(top) if top else None, "bottom5_mean": mean(ordered[:min(5, len(ordered))][index][1] for index in range(min(5, len(ordered)))) if ordered else None, "top_minus_bottom_spread": (mean(top) - mean(ordered[:min(5, len(ordered))][index][1] for index in range(min(5, len(ordered))))) if top else None, "top_quartile_minus_bottom_quartile": (mean(top_quartile) - mean(bottom_quartile)) if top_quartile and bottom_quartile else None, "positive_return_hit_rate": sum(value > 0.0 for value in top) / len(top) if top else None, "mfe_threshold_hit_rate": sum(value >= 0.005 for value in mfe_values) / len(mfe_values) if mfe_values else None, "coverage": len(pairs) / population_count if population_count else 0.0, "data_eligibility": "EXPLORATORY"}
    return ic, spread


def _aggregate_ic(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = list(rows)
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(row["feature_id"], row["target_id"])].append(row)
    for (feature_id, target_id), group in sorted(groups.items()):
        pearsons = [float(row["pearson_ic"]) for row in group if row["pearson_ic"] is not None]
        spearmans = [float(row["spearman_rank_ic"]) for row in group if row["spearman_rank_ic"] is not None]
        result.append({"schema_version": MR2_SCHEMA_VERSION, "scope": "AGGREGATE", "decision_date": None, "feature_id": feature_id, "target_id": target_id, "pearson_ic": mean(pearsons) if pearsons else None, "spearman_rank_ic": mean(spearmans) if spearmans else None, "ic_mean": mean(spearmans) if spearmans else None, "ic_standard_deviation": pstdev(spearmans) if len(spearmans) > 1 else 0.0 if spearmans else None, "ic_positive_rate": sum(value > 0.0 for value in spearmans) / len(spearmans) if spearmans else None, "coverage": mean(float(row["coverage"]) for row in group), "pair_count": sum(int(row["pair_count"]) for row in group), "data_eligibility": "EXPLORATORY"})
    return result


def _aggregate_spreads(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = list(rows)
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(row["feature_id"], row["target_id"])].append(row)
    for (feature_id, target_id), group in sorted(groups.items()):
        result.append({"schema_version": MR2_SCHEMA_VERSION, "scope": "AGGREGATE", "decision_date": None, "feature_id": feature_id, "target_id": target_id, "best_5_mean": _mean_optional(group, "top5_mean"), "worst_5_mean": _mean_optional(group, "bottom5_mean"), "best_minus_worst": _mean_optional(group, "top_minus_bottom_spread"), "best_quartile_minus_worst_quartile": _mean_optional(group, "top_quartile_minus_bottom_quartile"), "positive_return_hit_rate": _mean_optional(group, "positive_return_hit_rate"), "mfe_threshold_hit_rate": _mean_optional(group, "mfe_threshold_hit_rate"), "mfe_hit_numerator": sum(round(float(row["mfe_threshold_hit_rate"])*5) for row in group if row.get("mfe_threshold_hit_rate") is not None), "mfe_hit_denominator": sum(5 for row in group if row.get("mfe_threshold_hit_rate") is not None), "coverage": _mean_optional(group, "coverage"), "data_eligibility": "EXPLORATORY"})
    return result


def _mean_optional(rows: list[dict[str, Any]], key: str) -> float | None:
    values = [float(row[key]) for row in rows if row.get(key) is not None]
    return mean(values) if values else None


def _pearson(left: list[float], right: list[float]) -> float | None:
    if len(left) < 2 or len(left) != len(right):
        return None
    left_mean, right_mean = mean(left), mean(right)
    numerator = sum((a - left_mean) * (b - right_mean) for a, b in zip(left, right, strict=True))
    denominator = math.sqrt(sum((a - left_mean) ** 2 for a in left) * sum((b - right_mean) ** 2 for b in right))
    return numerator / denominator if denominator else None


def _ranks(values: list[float]) -> list[float]:
    order = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    index = 0
    while index < len(order):
        end = index
        while end + 1 < len(order) and order[end + 1][1] == order[index][1]:
            end += 1
        rank = (index + end + 2) / 2.0
        for offset in range(index, end + 1):
            ranks[order[offset][0]] = rank
        index = end + 1
    return ranks
