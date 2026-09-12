from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal as D, localcontext
from uuid import UUID

import pytest

from market_regime_alpha.research_qualification.domain.historical_comparison import (
    HistoricalEvaluationPoint,
    historical_comparison_statistics,
    paired_block_uncertainty,
)


def source():
    arms = ((UUID(int=1), "zero"), (UUID(int=2), "model"))
    sessions = ((UUID(int=3), UUID(int=4), date(2024, 1, 8)), (UUID(int=3), UUID(int=5), date(2024, 1, 9)))
    instruments = tuple(UUID(int=i) for i in (6, 7, 8))
    points = []
    for arm, _ in arms:
        for fold, session, day in sessions:
            for instrument, label in zip(instruments, (D(-1), D(0), D(1)), strict=True):
                key = UUID(int=100 + len(points))
                points.append(
                    HistoricalEvaluationPoint(
                        arm,
                        fold,
                        session,
                        day,
                        instrument,
                        key,
                        key,
                        key,
                        key,
                        key,
                        key,
                        key,
                        None,
                        "INCLUDED",
                        "COMPLETE_INPUT",
                        "AVAILABLE",
                        "COMPLETE",
                        D(0) if arm.int == 1 else label / 2,
                        label,
                        "a" * 64,
                        "b" * 64,
                    )
                )
    return tuple(points), dict(arms=arms, sessions=sessions, instruments=instruments, baseline_arm_id=arms[0][0])


def test_common_errors_have_independent_reference_and_constant_rank_is_not_estimable():
    points, kwargs = source()
    result = historical_comparison_statistics(points, **kwargs)
    zero, model = result["arms"]
    with localcontext() as context:
        context.prec = 38
        assert model["common_population"]["pooled"]["model"]["mae"]["value"] == D(1) / 3
        assert abs(model["common_population"]["pooled"]["model"]["rmse"]["value"] - (D(1) / 6).sqrt()) < D("1e-30")
    assert zero["own_population"]["daily"][0]["model"]["rank_ic"]["state"] == "NOT_ESTIMABLE"
    assert model["own_population"]["daily"][0]["model"]["rank_ic"]["value"] == 1
    assert model["paired_mae_uncertainty"]["state"] == "NOT_ESTIMABLE"
    with localcontext() as context:
        context.prec = 6
        assert historical_comparison_statistics(points, **kwargs) == result


def test_missing_rows_never_change_full_denominator_and_bad_days_remain_visible():
    points, kwargs = source()
    modified = tuple(
        replace(p, prediction=None, input_state="NOT_ESTIMABLE", forecast_status="NOT_ESTIMABLE", reason_code="FEATURE_MISSING")
        if p.arm_id.int == 2 and p.session_id.int == 5
        else p
        for p in points
    )
    result = historical_comparison_statistics(modified, **kwargs)
    assert len(result["expected_population"]) == 6
    assert len(result["label_available_population"]) == 6
    assert len(result["common_population"]) == 3
    for arm in result["arms"]:
        assert arm["expected_observations"] == 6
        assert arm["common_population"]["expected_session_count"] == 2
        assert arm["common_population"]["daily"][1]["state"] == "NOT_ESTIMABLE"
        assert arm["paired_mae_uncertainty"]["reason_code"] == "EMPTY_COMMON_DAY"
    assert len(result["arms"][1]["excluded_inputs"]) == 3


@pytest.mark.parametrize("correction", ["duplicate", "label", "outside"])
def test_duplicate_conflicting_or_outside_samples_fail_closed(correction):
    points, kwargs = source()
    if correction == "duplicate":
        points = (*points, points[0])
    elif correction == "label":
        points = (*points[:-1], replace(points[-1], label=D(2)))
    else:
        points = (*points[:-1], replace(points[-1], instrument_id=UUID(int=999)))
    with pytest.raises(ValueError):
        historical_comparison_statistics(points, **kwargs)


def test_bootstrap_uses_days_and_never_creates_confidence_from_many_stocks():
    rows = tuple((UUID(int=1), date(2024, 1, 1) + timedelta(days=i), 500, D(-50)) for i in range(49))
    assert paired_block_uncertainty(rows)["state"] == "NOT_ESTIMABLE"
    rows = (*rows, (UUID(int=1), date(2024, 2, 19), 500, D(-50)))
    assert paired_block_uncertainty(rows)["reason_code"] == "CONTIGUOUS_MARKET_CALENDAR_NOT_VERIFIED"
    result = paired_block_uncertainty(rows, calendar_verified=True)
    assert result["lower"] == result["upper"] == D("-.1")
    assert result["effective_block_count"] == 10 and result["draws"] == 1000
    assert paired_block_uncertainty(rows, calendar_verified=True) == result


def test_empty_completed_population_keeps_every_member_and_day():
    _, kwargs = source()
    result = historical_comparison_statistics((), **kwargs)
    assert len(result["expected_population"]) == 6
    assert result["common_population"] == result["label_available_population"] == ()
    for arm in result["arms"]:
        assert arm["own_estimable_observations"] == 0
        assert len(arm["missing_evaluation_members"]) == 6
        assert arm["common_population"]["pooled"]["model"]["mae"]["state"] == "NOT_ESTIMABLE"
