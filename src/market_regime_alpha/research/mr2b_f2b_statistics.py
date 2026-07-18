"""Deterministic dependence-aware statistics for frozen MR-2B observations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import math
from random import Random
from statistics import mean, median, pstdev
from typing import Any, Iterable, Mapping

from market_regime_alpha.research.mr2b_context import WatchlistDirection
from market_regime_alpha.research.mr2b_multiseed import linear_quantile


@dataclass(frozen=True, slots=True)
class F2BPrimaryObservation:
    decision_date: date
    dataset_id: str
    mr1_run_id: str
    f2a_run_id: str
    model_id: str
    exit_time: str
    cost_scenario: str
    context_id: str
    context_label: WatchlistDirection
    population_hash: str
    seed_set_id: str
    metric_value: float

    def __post_init__(self) -> None:
        if not isinstance(self.decision_date, date):
            raise TypeError("decision_date must be a date")
        for label, value in (
            ("dataset_id", self.dataset_id),
            ("mr1_run_id", self.mr1_run_id),
            ("f2a_run_id", self.f2a_run_id),
            ("model_id", self.model_id),
            ("exit_time", self.exit_time),
            ("cost_scenario", self.cost_scenario),
            ("context_id", self.context_id),
            ("population_hash", self.population_hash),
            ("seed_set_id", self.seed_set_id),
        ):
            if not isinstance(value, str) or not value:
                raise ValueError(f"{label} must be non-empty")
        if self.context_label not in (WatchlistDirection.UP, WatchlistDirection.DOWN):
            raise ValueError("Primary observation Context must be UP or DOWN")
        _finite(self.metric_value, "metric_value")


@dataclass(frozen=True, slots=True)
class BootstrapResult:
    method_id: str
    block_length: int
    draw_count: int
    valid_draw_count: int
    invalid_draw_count: int
    observed_up_mean: float
    observed_down_mean: float
    observed_effect: float
    bootstrap_effect_mean: float
    bootstrap_effect_median: float
    bootstrap_effect_std: float
    ci_lower_95: float
    ci_upper_95: float
    probability_effect_positive: float
    probability_effect_above_floor: float
    effects: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class CircularShiftResult:
    method_id: str
    observed_effect: float
    shift_count: int
    null_min: float
    null_median: float
    null_max: float
    one_sided_p_value: float
    effects: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class PermutationResult:
    method_id: str
    observed_effect: float
    draw_count: int
    one_sided_p_value: float
    null_lower_95: float
    null_upper_95: float
    effects: tuple[float, ...]
    authority: str = "EXCHANGEABILITY_SENSITIVE_ROBUSTNESS_ONLY"


@dataclass(frozen=True, slots=True)
class TemporalStability:
    first_half_effect: float | None
    second_half_effect: float | None
    first_half_up_count: int
    first_half_down_count: int
    second_half_up_count: int
    second_half_down_count: int
    half_coverage_complete: bool
    rolling_rows: tuple[dict[str, object], ...]
    rolling_positive_windows: int
    leave_one_out_min_effect: float
    leave_one_out_max_effect: float
    leave_one_out_positive_ratio: float
    leave_one_out_sign_flip_count: int


@dataclass(frozen=True, slots=True)
class ConcentrationResult:
    status: str
    largest_absolute_contribution_share: float | None
    top_3_absolute_contribution_share: float | None
    top_5_absolute_contribution_share: float | None
    largest_contributing_dates: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PrimaryObservationSet:
    observations: tuple[F2BPrimaryObservation, ...]
    total_date_count: int
    flat_count: int
    unavailable_count: int


@dataclass(frozen=True, slots=True)
class SeedPanelRobustness:
    full_seed_effect: float
    panel_A_effect: float
    panel_B_effect: float
    panel_C_effect: float
    panel_D_effect: float
    positive_panel_count: int
    direction_agreement: bool
    maximum_absolute_panel_deviation: float
    rows: tuple[dict[str, Any], ...]


def build_primary_observations(
    daily_rows: Iterable[Mapping[str, Any]],
    *,
    dataset_id: str,
    mr1_run_id: str,
    f2a_run_id: str,
    model_id: str,
    exit_time: str,
    cost_scenario: str,
) -> PrimaryObservationSet:
    selected = tuple(
        dict(row)
        for row in daily_rows
        if row.get("model_id") == model_id
        and row.get("exit_time") == exit_time
        and row.get("cost_scenario") == cost_scenario
    )
    if not selected:
        raise ValueError("frozen Primary comparison is absent from F2A evidence")
    dates = tuple(str(row.get("decision_date")) for row in selected)
    if len(dates) != len(set(dates)):
        raise ValueError("Primary F2A rows must have unique Decision Dates")
    output: list[F2BPrimaryObservation] = []
    flat = unavailable = 0
    for row in selected:
        if row.get("dataset_id") != dataset_id or row.get("mr1_run_id") != mr1_run_id:
            raise ValueError("Primary row input identity mismatch")
        if row.get("context_data_status") != "AVAILABLE" or row.get("data_status") != "AVAILABLE":
            unavailable += 1
            continue
        raw_label = str(row.get("context_label"))
        if raw_label == WatchlistDirection.FLAT.value:
            flat += 1
            continue
        try:
            label = WatchlistDirection(raw_label)
        except ValueError as exc:
            raise ValueError("Primary row has an unknown Context label") from exc
        output.append(
            F2BPrimaryObservation(
                decision_date=date.fromisoformat(str(row["decision_date"])),
                dataset_id=dataset_id,
                mr1_run_id=mr1_run_id,
                f2a_run_id=f2a_run_id,
                model_id=model_id,
                exit_time=exit_time,
                cost_scenario=cost_scenario,
                context_id=str(row["context_id"]),
                context_label=label,
                population_hash=str(row["population_hash"]),
                seed_set_id=str(row["seed_set_id"]),
                metric_value=_finite(row["net_lift_vs_multiseed_median"], "Primary metric"),
            )
        )
    return PrimaryObservationSet(tuple(sorted(output, key=lambda row: row.decision_date)), len(selected), flat, unavailable)


def seed_panel_robustness(
    observations: Iterable[F2BPrimaryObservation],
    *,
    multiseed_return_rows: Iterable[Mapping[str, Any]],
) -> SeedPanelRobustness:
    primary = _ordered(observations)
    primary_by_date = {row.decision_date.isoformat(): row for row in primary}
    first = primary[0]
    grouped: dict[tuple[str, int], list[float]] = {}
    full_by_day: dict[str, list[float]] = {}
    for raw in multiseed_return_rows:
        if (
            raw.get("model_id") != first.model_id
            or raw.get("exit_time") != first.exit_time
            or raw.get("cost_scenario") != first.cost_scenario
        ):
            continue
        day = str(raw.get("decision_date"))
        if day not in primary_by_date:
            continue
        seed = int(raw.get("seed", -1))
        value = _finite(raw.get("net_return"), "panel net return")
        grouped.setdefault((day, seed % 4), []).append(value)
        full_by_day.setdefault(day, []).append(value)
    rows: list[dict[str, Any]] = []
    panel_effects: list[float] = []
    for panel in range(4):
        panel_observations: list[F2BPrimaryObservation] = []
        for day, model_row in sorted(primary_by_date.items()):
            values = grouped.get((day, panel), [])
            if not values:
                raise ValueError("seed-panel return evidence is incomplete")
            panel_observations.append(
                F2BPrimaryObservation(
                    decision_date=model_row.decision_date,
                    dataset_id=model_row.dataset_id,
                    mr1_run_id=model_row.mr1_run_id,
                    f2a_run_id=model_row.f2a_run_id,
                    model_id=model_row.model_id,
                    exit_time=model_row.exit_time,
                    cost_scenario=model_row.cost_scenario,
                    context_id=model_row.context_id,
                    context_label=model_row.context_label,
                    population_hash=model_row.population_hash,
                    seed_set_id=model_row.seed_set_id,
                    metric_value=model_row.metric_value + median(full_by_day[day]) - median(values),
                )
            )
        effect = _effect(tuple(panel_observations))[2]
        panel_effects.append(effect)
        rows.append({"panel": "ABCD"[panel], "effect": effect, "date_count": len(panel_observations)})
    full_effect = _effect(primary)[2]
    return SeedPanelRobustness(
        full_seed_effect=full_effect,
        panel_A_effect=panel_effects[0],
        panel_B_effect=panel_effects[1],
        panel_C_effect=panel_effects[2],
        panel_D_effect=panel_effects[3],
        positive_panel_count=sum(value > 0 for value in panel_effects),
        direction_agreement=all(value > 0 for value in panel_effects),
        maximum_absolute_panel_deviation=max(abs(value - full_effect) for value in panel_effects),
        rows=tuple(rows),
    )


def moving_block_bootstrap(
    observations: Iterable[F2BPrimaryObservation],
    *,
    draws: int,
    block_length: int,
    seed: int,
    minimum_slice_size: int,
    effect_floor: float = 0.001,
) -> BootstrapResult:
    rows = _ordered(observations)
    if draws <= 0 or block_length <= 0 or minimum_slice_size <= 0:
        raise ValueError("bootstrap parameters must be positive")
    observed_up, observed_down, observed = _effect(rows)
    rng = Random(seed)
    effects: list[float] = []
    n = len(rows)
    for _ in range(draws):
        sampled: list[F2BPrimaryObservation] = []
        while len(sampled) < n:
            start = rng.randrange(n)
            sampled.extend(rows[(start + offset) % n] for offset in range(block_length))
        draw_rows = tuple(sampled[:n])
        up_count, down_count = _counts(draw_rows)
        if up_count < minimum_slice_size or down_count < minimum_slice_size:
            continue
        effects.append(_effect(draw_rows)[2])
    if not effects:
        raise ValueError("bootstrap produced no valid draws")
    alpha = 0.025
    return BootstrapResult(
        method_id="circular-moving-block-bootstrap-paired-observations-v1",
        block_length=block_length,
        draw_count=draws,
        valid_draw_count=len(effects),
        invalid_draw_count=draws - len(effects),
        observed_up_mean=observed_up,
        observed_down_mean=observed_down,
        observed_effect=observed,
        bootstrap_effect_mean=mean(effects),
        bootstrap_effect_median=median(effects),
        bootstrap_effect_std=pstdev(effects),
        ci_lower_95=linear_quantile(effects, alpha),
        ci_upper_95=linear_quantile(effects, 1 - alpha),
        probability_effect_positive=sum(value > 0 for value in effects) / len(effects),
        probability_effect_above_floor=sum(value >= effect_floor for value in effects) / len(effects),
        effects=tuple(effects),
    )


def circular_shift_randomization(
    observations: Iterable[F2BPrimaryObservation],
) -> CircularShiftResult:
    rows = _ordered(observations)
    labels = tuple(row.context_label for row in rows)
    values = tuple(row.metric_value for row in rows)
    observed = _label_effect(labels, values)
    shifted = tuple(
        _label_effect(labels[shift:] + labels[:shift], values)
        for shift in range(1, len(rows))
    )
    return CircularShiftResult(
        method_id="context-label-circular-shift-randomization-v1",
        observed_effect=observed,
        shift_count=len(shifted),
        null_min=min(shifted),
        null_median=median(shifted),
        null_max=max(shifted),
        one_sided_p_value=(1 + sum(value >= observed for value in shifted)) / len(rows),
        effects=shifted,
    )


def count_preserving_permutation(
    observations: Iterable[F2BPrimaryObservation], *, draws: int, seed: int
) -> PermutationResult:
    rows = _ordered(observations)
    labels = [row.context_label for row in rows]
    values = tuple(row.metric_value for row in rows)
    observed = _label_effect(tuple(labels), values)
    rng = Random(seed)
    effects: list[float] = []
    for _ in range(draws):
        shuffled = labels.copy()
        rng.shuffle(shuffled)
        effects.append(_label_effect(tuple(shuffled), values))
    return PermutationResult(
        method_id="count-preserving-label-permutation-v1",
        observed_effect=observed,
        draw_count=draws,
        one_sided_p_value=(1 + sum(value >= observed for value in effects)) / (draws + 1),
        null_lower_95=linear_quantile(effects, 0.025),
        null_upper_95=linear_quantile(effects, 0.975),
        effects=tuple(effects),
    )


def temporal_stability(
    observations: Iterable[F2BPrimaryObservation], *, half_minimum_slice_size: int = 5, rolling_window: int = 20
) -> TemporalStability:
    rows = _ordered(observations)
    midpoint = len(rows) // 2
    first, second = rows[:midpoint], rows[midpoint:]
    f_up, f_down = _counts(first)
    s_up, s_down = _counts(second)
    first_effect = _effect(first)[2] if f_up and f_down else None
    second_effect = _effect(second)[2] if s_up and s_down else None
    rolling: list[dict[str, object]] = []
    for start in range(0, len(rows) - rolling_window + 1):
        window = rows[start : start + rolling_window]
        up_count, down_count = _counts(window)
        effect = _effect(window)[2] if up_count and down_count else None
        rolling.append(
            {
                "start_date": window[0].decision_date.isoformat(),
                "end_date": window[-1].decision_date.isoformat(),
                "UP_count": up_count,
                "DOWN_count": down_count,
                "effect": effect,
                "coverage_status": "AVAILABLE" if up_count and down_count else "INSUFFICIENT_WINDOW_COVERAGE",
            }
        )
    observed = _effect(rows)[2]
    loo = tuple(_effect(rows[:index] + rows[index + 1 :])[2] for index in range(len(rows)))
    return TemporalStability(
        first_half_effect=first_effect,
        second_half_effect=second_effect,
        first_half_up_count=f_up,
        first_half_down_count=f_down,
        second_half_up_count=s_up,
        second_half_down_count=s_down,
        half_coverage_complete=min(f_up, f_down, s_up, s_down) >= half_minimum_slice_size,
        rolling_rows=tuple(rolling),
        rolling_positive_windows=sum(
            row["effect"] is not None and _finite(row["effect"], "rolling effect") > 0
            for row in rolling
        ),
        leave_one_out_min_effect=min(loo),
        leave_one_out_max_effect=max(loo),
        leave_one_out_positive_ratio=sum(value > 0 for value in loo) / len(loo),
        leave_one_out_sign_flip_count=sum((value > 0) != (observed > 0) for value in loo),
    )


def concentration_diagnostics(
    observations: Iterable[F2BPrimaryObservation],
) -> ConcentrationResult:
    rows = _ordered(observations)
    up_count, down_count = _counts(rows)
    contributions = tuple(
        (
            row.decision_date.isoformat(),
            row.metric_value / up_count
            if row.context_label is WatchlistDirection.UP
            else -row.metric_value / down_count,
        )
        for row in rows
    )
    mass = sum(abs(value) for _, value in contributions)
    if mass <= 1e-15:
        return ConcentrationResult("NO_EFFECT_MASS", None, None, None, ())
    ordered = tuple(sorted(contributions, key=lambda item: (-abs(item[1]), item[0])))
    shares = tuple(abs(value) / mass for _, value in ordered)
    return ConcentrationResult(
        status="AVAILABLE",
        largest_absolute_contribution_share=shares[0],
        top_3_absolute_contribution_share=sum(shares[:3]),
        top_5_absolute_contribution_share=sum(shares[:5]),
        largest_contributing_dates=tuple(day for day, _ in ordered[:5]),
    )


def _ordered(observations: Iterable[F2BPrimaryObservation]) -> tuple[F2BPrimaryObservation, ...]:
    rows = tuple(sorted(observations, key=lambda row: row.decision_date))
    if len(rows) < 2 or len({row.decision_date for row in rows}) != len(rows):
        raise ValueError("Primary observations require unique Decision Dates")
    identities = {
        (row.dataset_id, row.mr1_run_id, row.f2a_run_id, row.model_id, row.exit_time, row.cost_scenario, row.seed_set_id)
        for row in rows
    }
    if len(identities) != 1:
        raise ValueError("Primary observation identities must be constant")
    if not {row.context_label for row in rows} <= {WatchlistDirection.UP, WatchlistDirection.DOWN}:
        raise ValueError("Primary observations must contain only UP/DOWN")
    if len({row.context_label for row in rows}) != 2:
        raise ValueError("Primary observations require both UP and DOWN")
    return rows


def _counts(rows: tuple[F2BPrimaryObservation, ...]) -> tuple[int, int]:
    return (
        sum(row.context_label is WatchlistDirection.UP for row in rows),
        sum(row.context_label is WatchlistDirection.DOWN for row in rows),
    )


def _effect(rows: tuple[F2BPrimaryObservation, ...]) -> tuple[float, float, float]:
    up = tuple(row.metric_value for row in rows if row.context_label is WatchlistDirection.UP)
    down = tuple(row.metric_value for row in rows if row.context_label is WatchlistDirection.DOWN)
    if not up or not down:
        raise ValueError("UP-minus-DOWN effect requires both slices")
    up_mean, down_mean = mean(up), mean(down)
    return up_mean, down_mean, up_mean - down_mean


def _label_effect(labels: tuple[WatchlistDirection, ...], values: tuple[float, ...]) -> float:
    up = tuple(value for label, value in zip(labels, values, strict=True) if label is WatchlistDirection.UP)
    down = tuple(value for label, value in zip(labels, values, strict=True) if label is WatchlistDirection.DOWN)
    return mean(up) - mean(down)


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise TypeError(f"{label} must be a finite real number")
    return float(value)
