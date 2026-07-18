"""Deterministic chronological statistics for PIT replication v2."""

from __future__ import annotations

from dataclasses import dataclass
import math
import random
from statistics import mean
from typing import Iterable, Mapping

from market_regime_alpha.research.mr2b_f2b_statistics import linear_quantile
from market_regime_alpha.research.pit_replication_success_v2_protocol import (
    PITCandidateReplicationProtocolV2,
)


@dataclass(frozen=True, slots=True)
class PITReplicationAssessment:
    status: str
    observed_effect: float | None
    ci_lower: float | None
    ci_upper: float | None
    first_half_effect: float | None
    second_half_effect: float | None
    seed_panel_effects: tuple[float, ...]
    cost_robustness_effects: tuple[tuple[str, float], ...]
    largest_absolute_contribution_share: float | None
    top_3_absolute_contribution_share: float | None
    rolling_positive_window_count: int
    rolling_window_count: int
    leave_one_out_minimum: float | None
    leave_one_out_maximum: float | None
    reasons: tuple[str, ...]
    authority: str


def assess_daily_replication(
    rows: Iterable[Mapping[str, object]],
    *,
    protocol: PITCandidateReplicationProtocolV2,
) -> PITReplicationAssessment:
    ordered = tuple(sorted((dict(row) for row in rows), key=lambda row: str(row["decision_date"])))
    values = tuple(_finite_float(row["net_lift_vs_multiseed_median"]) for row in ordered)
    insufficiency: list[str] = []
    if len(values) < protocol.minimum_decision_dates:
        insufficiency.append("INSUFFICIENT_DECISION_DATES")
    average_population = (
        mean(_finite_float(row["population_size"]) for row in ordered) if ordered else 0.0
    )
    if average_population < protocol.minimum_average_population_size:
        insufficiency.append("INSUFFICIENT_AVERAGE_POPULATION")
    minimum_coverage = min(
        (_finite_float(row["evaluation_symbol_coverage"]) for row in ordered),
        default=0.0,
    )
    if minimum_coverage < protocol.minimum_symbol_coverage:
        insufficiency.append("INSUFFICIENT_EVALUATION_COVERAGE")
    if insufficiency:
        return _insufficient(protocol, tuple(insufficiency))
    observed = mean(values)
    effects = _moving_block_means(
        values,
        draws=protocol.bootstrap_draws,
        block_length=protocol.bootstrap_block_length,
        seed=protocol.bootstrap_seed,
    )
    alpha = (1.0 - protocol.bootstrap_interval) / 2.0
    lower = linear_quantile(effects, alpha)
    upper = linear_quantile(effects, 1.0 - alpha)
    split = len(values) // 2
    first = mean(values[:split])
    second = mean(values[split:])
    panel_effects = tuple(
        mean(_finite_float(row[f"seed_panel_{panel}_net_lift"]) for row in ordered)
        for panel in ("A", "B", "C", "D")
    )
    cost_effects = tuple(
        (
            scenario,
            mean(
                _finite_float(row[f"cost_scenario_{scenario}_net_lift"])
                for row in ordered
            ),
        )
        for scenario in protocol.cost_robustness_scenarios
    )
    mass = sum(abs(value) for value in values)
    if mass == 0:
        largest_share = top_3_share = None
    else:
        shares = sorted((abs(value) / mass for value in values), reverse=True)
        largest_share = shares[0]
        top_3_share = sum(shares[:3])
    rolling = tuple(
        mean(values[index : index + protocol.rolling_window])
        for index in range(len(values) - protocol.rolling_window + 1)
    )
    leave_one_out = tuple(
        mean(values[:index] + values[index + 1 :]) for index in range(len(values))
    )
    reasons: list[str] = []
    if observed < protocol.economic_effect_floor:
        reasons.append("BELOW_ECONOMIC_EFFECT_FLOOR")
    if lower <= 0:
        reasons.append("BOOTSTRAP_INTERVAL_INCLUDES_ZERO")
    if first <= 0 or second <= 0:
        reasons.append("TEMPORAL_DIRECTION_INCONSISTENT")
    if sum(value > 0 for value in panel_effects) < protocol.required_positive_seed_panels:
        reasons.append("COMPARATOR_PANEL_UNSTABLE")
    if any(value <= 0 for _, value in cost_effects):
        reasons.append("COST_ROBUSTNESS_UNSTABLE")
    if largest_share is None:
        reasons.append("NO_EFFECT_MASS")
    elif (
        largest_share > protocol.largest_contribution_limit
        or top_3_share is not None
        and top_3_share > protocol.top_3_contribution_limit
    ):
        reasons.append("CONCENTRATED_EFFECT")
    return PITReplicationAssessment(
        (
            "PIT_REPLICATION_SUPPORTED_REHEARSAL"
            if not reasons
            else "PIT_REPLICATION_NOT_SUPPORTED"
        ),
        observed,
        lower,
        upper,
        first,
        second,
        panel_effects,
        cost_effects,
        largest_share,
        top_3_share,
        sum(value > 0 for value in rolling),
        len(rolling),
        min(leave_one_out),
        max(leave_one_out),
        tuple(reasons),
        protocol.authority_ceiling,
    )


def _finite_float(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("PIT replication statistic must be numeric")
    converted = float(value)
    if not math.isfinite(converted):
        raise ValueError("PIT replication statistic must be finite")
    return converted


def _insufficient(
    protocol: PITCandidateReplicationProtocolV2, reasons: tuple[str, ...]
) -> PITReplicationAssessment:
    return PITReplicationAssessment(
        "INSUFFICIENT_PIT_EVIDENCE",
        None,
        None,
        None,
        None,
        None,
        (),
        (),
        None,
        None,
        0,
        0,
        None,
        None,
        reasons,
        protocol.authority_ceiling,
    )


def _moving_block_means(
    values: tuple[float, ...], *, draws: int, block_length: int, seed: int
) -> tuple[float, ...]:
    generator = random.Random(seed)
    count = len(values)
    output: list[float] = []
    for _ in range(draws):
        sampled: list[float] = []
        while len(sampled) < count:
            start = generator.randrange(count)
            sampled.extend(values[(start + offset) % count] for offset in range(block_length))
        output.append(mean(sampled[:count]))
    return tuple(output)
