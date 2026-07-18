from __future__ import annotations

from datetime import date, timedelta
import math

import pytest

from market_regime_alpha.research.mr2b_excess import (
    DailyConditionalityObservation,
    WatchlistDirection,
    primary_assessment,
)


def _observation(
    day: date,
    direction: WatchlistDirection,
    *,
    model_gross: float = 0.01,
    model_net: float = 0.009,
    all_gross: float = 0.005,
    matched_gross: float = 0.004,
    matched_net: float = 0.003,
) -> DailyConditionalityObservation:
    return DailyConditionalityObservation(
        decision_date=day,
        dataset_id="prr-dataset-test",
        mr1_run_id="mr1-test",
        model_population_hash="sha256:population",
        matched_k_selection_id="sha256:selection",
        matched_k_seed=17,
        context_label=direction,
        model_id="prr-mvp-1-b1-e-v1",
        exit_time="10:30",
        cost_scenario="BASE",
        model_gross_return=model_gross,
        model_net_return=model_net,
        all_candidate_gross_return=all_gross,
        matched_k_gross_return=matched_gross,
        matched_k_net_return=matched_net,
    )


def test_absolute_market_moves_without_excess_are_described_as_no_excess() -> None:
    start = date(2026, 1, 1)
    rows = tuple(
        _observation(
            start + timedelta(days=index),
            WatchlistDirection.UP if index < 15 else WatchlistDirection.DOWN,
            model_gross=0.02 if index < 15 else -0.02,
            model_net=0.02 if index < 15 else -0.02,
            all_gross=0.02 if index < 15 else -0.02,
            matched_gross=0.02 if index < 15 else -0.02,
            matched_net=0.02 if index < 15 else -0.02,
        )
        for index in range(30)
    )

    assert primary_assessment(rows)["assessment"] == "NO_EXCESS"


def test_primary_assessment_rejects_duplicate_decision_dates() -> None:
    row = _observation(date(2026, 1, 5), WatchlistDirection.UP)

    with pytest.raises(ValueError, match="Decision Dates must be unique"):
        primary_assessment((row, row))


@pytest.mark.parametrize("value", (math.nan, math.inf, -math.inf, True))
def test_daily_observation_rejects_non_finite_returns(value: float) -> None:
    with pytest.raises((TypeError, ValueError), match="finite numeric"):
        _observation(date(2026, 1, 5), WatchlistDirection.UP, model_net=value)


def test_daily_observation_rejects_unknown_context_label() -> None:
    with pytest.raises(TypeError, match="WatchlistDirection"):
        _observation(date(2026, 1, 5), "SIDEWAYS")  # type: ignore[arg-type]


def test_primary_uses_matched_k_net_excess_and_is_order_stable() -> None:
    start = date(2026, 1, 1)
    rows = tuple(
        _observation(
            start + timedelta(days=index),
            WatchlistDirection.UP if index < 15 else WatchlistDirection.DOWN,
            model_net=0.02 if index < 15 else -0.01,
            matched_net=0.01 if index < 15 else -0.01,
        )
        for index in range(30)
    )

    result = primary_assessment(reversed(rows))

    assert result["difference_of_mean_net_excess_vs_matched_k"] == pytest.approx(0.01)
    assert result["assessment"] == "EFFECT_THRESHOLD_MET"
    assert result["assessment"] in {
        "EFFECT_THRESHOLD_MET",
        "EFFECT_THRESHOLD_NOT_MET",
        "NO_EXCESS",
        "INSUFFICIENT_EVIDENCE",
    }


def test_observation_exposes_all_comparator_metrics() -> None:
    row = _observation(date(2026, 1, 5), WatchlistDirection.UP)

    assert row.gross_excess_vs_all_candidate == pytest.approx(0.005)
    assert row.gross_excess_vs_matched_k == pytest.approx(0.006)
    assert row.net_excess_vs_matched_k == pytest.approx(0.006)
    assert row.cost_drag_difference == pytest.approx(0.0)
