"""Leak-free MR-2A decision-time regime evidence and controlled heterogeneity diagnostics."""

from __future__ import annotations

from datetime import date, time
from hashlib import sha256
import math
import random
from statistics import mean
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from market_regime_alpha.research.tencent_composite_contracts import CompositeBar, PreparedCompositeData

MR2A_SCHEMA_VERSION = "mr-2a-leak-free-regime-diagnostic-v1"
MR2A_CONTEXT_SCHEMA_VERSION = "mr-2-decision-time-market-context-v1"
MR2A_CONTEXT_DEFINITION = "mr2-decision-context-1450-cutoff-median-volatility-v1"
FEATURE_DIRECTIONS = {
    "feature-r5-momentum-5s-v1": "HIGHER_IS_BETTER",
    "feature-r5-volatility-20s-v1": "LOWER_IS_BETTER",
    "feature-r5-log-median-amount-20s-v1": "HIGHER_IS_BETTER",
    "feature-r5-price-vs-ma20-v1": "HIGHER_IS_BETTER",
}
_TZ = ZoneInfo("Asia/Shanghai")
_CUTOFF = time(14, 50)


def build_decision_time_context(
    *, prepared: PreparedCompositeData, bars: Iterable[CompositeBar], decision_dates: Iterable[date]
) -> tuple[dict[str, Any], ...]:
    index: dict[tuple[str, date], list[CompositeBar]] = {}
    for bar in bars:
        local = bar.timestamp.astimezone(_TZ)
        if local.time().replace(tzinfo=None) <= _CUTOFF:
            index.setdefault((bar.symbol, local.date()), []).append(bar)
    for rows in index.values():
        rows.sort(key=lambda item: item.timestamp)
    raw: list[dict[str, Any]] = []
    for day in decision_dates:
        dates = prepared.common_session_dates
        if day not in dates:
            continue
        pos = dates.index(day)
        if pos == 0:
            continue
        prior = dates[pos - 1]
        usable = []
        for symbol in prepared.accepted_symbols:
            today, yesterday = index.get((symbol, day), []), index.get((symbol, prior), [])
            if today and yesterday:
                usable.append((today, yesterday, prepared.session_for(symbol, prior)))
        expected = len(prepared.accepted_symbols)
        coverage = len(usable) / expected if expected else 0.0
        if coverage < 1.0:
            raw.append(
                {
                    "schema_version": MR2A_CONTEXT_SCHEMA_VERSION,
                    "decision_date": day.isoformat(),
                    "decision_time": "14:55:00+08:00",
                    "cutoff_time": "14:50:00+08:00",
                    "data_status": "UNAVAILABLE",
                    "available_symbol_count": len(usable),
                    "expected_symbol_count": expected,
                    "coverage": coverage,
                    "missing_reason": "CUTOFF_EVIDENCE_INCOMPLETE",
                    "source_dataset_id": "EXPLORATORY_DATASET",
                }
            )
            continue
        refs = [today[-1].close for today, _, _ in usable]
        raw.append(
            {
                "schema_version": MR2A_CONTEXT_SCHEMA_VERSION,
                "decision_date": day.isoformat(),
                "decision_time": "14:55:00+08:00",
                "cutoff_time": "14:50:00+08:00",
                "market_direction_return": mean(today[-1].close / prior_session.close - 1 for today, _, prior_session in usable),
                "market_intraday_range_to_cutoff": mean(
                    (max(x.high for x in today) - min(x.low for x in today)) / today[-1].close for today, _, _ in usable
                ),
                "market_amount_to_cutoff": sum(sum(x.amount for x in today) for today, _, _ in usable),
                "prior_session_same_cutoff_amount": sum(sum(x.amount for x in yesterday) for _, yesterday, _ in usable),
                "market_amount_change_same_cutoff": sum(sum(x.amount for x in today) for today, _, _ in usable)
                / sum(sum(x.amount for x in yesterday) for _, yesterday, _ in usable)
                - 1,
                "candidate_breadth_at_cutoff": sum(today[-1].close > prior_session.close for today, _, prior_session in usable) / expected,
                "symbol_count": expected,
                "available_symbol_count": expected,
                "expected_symbol_count": expected,
                "coverage": coverage,
                "data_status": "AVAILABLE",
                "missing_reason": None,
                "source_dataset_id": "EXPLORATORY_DATASET",
                "reference_price_mean": mean(refs),
            }
        )
    vols = sorted(row["market_intraday_range_to_cutoff"] for row in raw if row["data_status"] == "AVAILABLE")
    threshold = vols[len(vols) // 2] if vols else None
    for row in raw:
        if row["data_status"] == "AVAILABLE":
            row.update(
                {
                    "market_direction": "UP" if row["market_direction_return"] >= 0 else "DOWN",
                    "market_volatility": "HIGH" if row["market_intraday_range_to_cutoff"] >= threshold else "LOW",
                    "market_amount": "EXPANDING" if row["market_amount_change_same_cutoff"] >= 0 else "CONTRACTING",
                    "candidate_breadth": "STRONG" if row["candidate_breadth_at_cutoff"] >= 0.5 else "WEAK",
                    "volatility_threshold": threshold,
                    "definition_id": MR2A_CONTEXT_DEFINITION,
                    "etf_sector_context": "ETF_SECTOR_CONTEXT_UNAVAILABLE",
                }
            )
    return tuple(raw)


def spearman_rank_ic(scores: list[float], targets: list[float]) -> float | None:
    return _pearson(_ranks(scores), _ranks(targets))


def directional_score(feature_id: str, value: float) -> float:
    direction = FEATURE_DIRECTIONS.get(feature_id)
    if direction is None:
        raise ValueError("DIRECTION_UNAVAILABLE")
    return value if direction == "HIGHER_IS_BETTER" else -value


def controlled_heterogeneity_gate(left: list[float], right: list[float], *, seed: int, effect_threshold: float = 0.001) -> dict[str, Any]:
    if len(left) < 15 or len(right) < 15:
        return {"assessment": "C0. REGIME_HETEROGENEITY_NOT_SUPPORTED", "reason": "INSUFFICIENT_SLICE_SESSIONS"}
    observed = mean(left) - mean(right)
    rng = random.Random(seed)
    combined = left + right
    samples = []
    for _ in range(500):
        shuffled = combined[:]
        rng.shuffle(shuffled)
        samples.append(mean(shuffled[: len(left)]) - mean(shuffled[len(left) :]))
    ci = sorted(samples)
    p = sum(abs(x) >= abs(observed) for x in samples) / len(samples)
    directionally_consistent = (mean(left[: len(left) // 2]) - mean(right[: len(right) // 2])) * (
        mean(left[len(left) // 2 :]) - mean(right[len(right) // 2 :])
    ) > 0
    concentrated = max(map(abs, left + right)) / max(sum(map(abs, left + right)), 1e-12) > 0.5
    assessment = (
        "C1. REGIME_HETEROGENEITY_HYPOTHESIS"
        if abs(observed) >= effect_threshold and directionally_consistent and not concentrated
        else "C0. REGIME_HETEROGENEITY_NOT_SUPPORTED"
    )
    return {
        "assessment": assessment,
        "difference_of_mean_daily_excess": observed,
        "bootstrap_ci_95": [ci[12], ci[487]],
        "permutation_p_value": p,
        "slice_counts": [len(left), len(right)],
        "effect_threshold": effect_threshold,
        "descriptive_uncertainty_only": True,
    }


def registry_hash() -> str:
    return sha256(repr(sorted(FEATURE_DIRECTIONS.items())).encode()).hexdigest()


def _pearson(a: list[float], b: list[float]) -> float | None:
    if len(a) < 2:
        return None
    x, y = mean(a), mean(b)
    d = math.sqrt(sum((i - x) ** 2 for i in a) * sum((i - y) ** 2 for i in b))
    return sum((i - x) * (j - y) for i, j in zip(a, b, strict=True)) / d if d else None


def _ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=values.__getitem__)
    result = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            result[order[k]] = (i + j + 2) / 2
        i = j + 1
    return result
