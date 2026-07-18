from datetime import date, timedelta

import pytest

from market_regime_alpha.research.mr2b_context import WatchlistDirection
from market_regime_alpha.research.mr2b_f2b_statistics import (
    F2BPrimaryObservation,
    circular_shift_randomization,
    concentration_diagnostics,
    moving_block_bootstrap,
    temporal_stability,
)


def _rows(values: list[tuple[WatchlistDirection, float]]) -> tuple[F2BPrimaryObservation, ...]:
    start = date(2026, 1, 1)
    return tuple(
        F2BPrimaryObservation(
            decision_date=start + timedelta(days=index),
            dataset_id="dataset",
            mr1_run_id="mr1",
            f2a_run_id="f2a",
            model_id="prr-mvp-1-b1-e-v1",
            exit_time="10:30",
            cost_scenario="BASE",
            context_id=f"context-{index}",
            context_label=label,
            population_hash=f"population-{index}",
            seed_set_id="seed-set",
            metric_value=value,
        )
        for index, (label, value) in enumerate(values)
    )


def test_moving_block_bootstrap_is_paired_order_stable_and_deterministic() -> None:
    rows = _rows([(WatchlistDirection.UP if i % 2 else WatchlistDirection.DOWN, i / 1000) for i in range(40)])
    first = moving_block_bootstrap(rows, draws=200, block_length=5, seed=17, minimum_slice_size=5)
    second = moving_block_bootstrap(tuple(reversed(rows)), draws=200, block_length=5, seed=17, minimum_slice_size=5)
    assert first == second
    assert first.valid_draw_count + first.invalid_draw_count == 200
    assert len(first.effects) == first.valid_draw_count


def test_circular_shift_uses_one_sided_direction_without_absolute_value() -> None:
    rows = _rows(
        [
            (WatchlistDirection.UP, 0.03),
            (WatchlistDirection.UP, 0.02),
            (WatchlistDirection.DOWN, -0.01),
            (WatchlistDirection.DOWN, -0.02),
        ]
    )
    result = circular_shift_randomization(rows)
    assert result.shift_count == 3
    assert result.observed_effect == pytest.approx(0.04)
    assert result.one_sided_p_value == pytest.approx(0.25)


def test_temporal_and_concentration_diagnostics_use_complete_date_order() -> None:
    rows = _rows(
        [(WatchlistDirection.UP, 0.02), (WatchlistDirection.DOWN, 0.0)] * 20
    )
    temporal = temporal_stability(rows, half_minimum_slice_size=5, rolling_window=20)
    concentration = concentration_diagnostics(rows)
    assert temporal.first_half_effect == pytest.approx(0.02)
    assert temporal.second_half_effect == pytest.approx(0.02)
    assert temporal.leave_one_out_sign_flip_count == 0
    assert concentration.largest_absolute_contribution_share <= 0.5
