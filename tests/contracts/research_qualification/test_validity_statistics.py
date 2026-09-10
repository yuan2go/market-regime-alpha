"""Independent arithmetic and population contracts for read-only validity v1."""

from dataclasses import FrozenInstanceError, replace
from datetime import date
from decimal import Decimal, localcontext
from uuid import UUID

import pytest

from market_regime_alpha.research_qualification.domain.validity_statistics import (
    ValidityPair,
    validity_statistics,
)


D = Decimal
DAY = date(2026, 9, 10)


def _pairs(*, session: date = DAY, model: tuple[str, ...] = ("1", "2", "3"),
           baseline: tuple[str, ...] = ("3", "2", "1"),
           labels: tuple[str, ...] = ("3", "5", "7")) -> tuple[ValidityPair, ...]:
    return tuple(ValidityPair(UUID(int=index), session, D(x), D(b), D(y), UUID(int=100 + index))
                 for index, (x, b, y) in enumerate(zip(model, baseline, labels, strict=True), 1))


def _report(pairs: tuple[ValidityPair, ...], **kwargs: int) -> dict:
    return validity_statistics(pairs, **{"minimum_sessions": 2, "minimum_observations": 6,
                                         "rolling_sessions": 2, "ranking_k": 1, "quantiles": 3, **kwargs})


def test_validity_arithmetic_uses_canonical_labels_and_exact_common_population() -> None:
    result = _report(_pairs())
    session = result["per_session"][0]
    assert session["model"]["bias"]["value"] == D(-3)
    assert session["model"]["mae"]["value"] == D(3)
    with localcontext() as context:
        context.prec = 38
        assert session["model"]["rmse"]["value"] == (D(29) / D(3)).sqrt()
    assert session["model"]["rank_ic"]["value"] == D(1)
    assert session["baseline"]["rank_ic"]["value"] == D(-1)
    assert session["delta"]["rank_ic"]["value"] == D(2)
    assert session["model"]["calibration_slope"]["value"] == D(2)
    assert session["model"]["calibration_intercept"]["value"] == D(1)
    assert session["model"]["forecast_dispersion"]["value"] == D(1)
    assert session["actual_distribution"]["sample_std"]["value"] == D(2)
    assert session["model"]["mae"]["denominator"] == session["baseline"]["mae"]["denominator"] == 3
    assert result["state"] == "INSUFFICIENT_SESSIONS"
    assert result["reason_codes"] == ("INSUFFICIENT_SESSIONS", "INSUFFICIENT_OBSERVATIONS")


def test_direction_and_positive_ratios_count_flat_as_a_separate_exact_sign() -> None:
    row = _report(_pairs(model=("-1", "0", "1"), baseline=("1", "0", "-1"), labels=("-2", "0", "3")))["per_session"][0]
    assert row["model"]["directional_hit_rate"]["value"] == D(1)
    assert row["baseline"]["directional_hit_rate"]["numerator"] == 1
    assert row["baseline"]["directional_hit_rate"]["denominator"] == 3
    assert row["baseline"]["directional_hit_rate"]["denominator_kind"] == "COMMON_OBSERVATIONS"
    assert row["model"]["predicted_positive_proportion"]["numerator"] == 1
    assert row["model"]["actual_positive_proportion"]["numerator"] == 1
    assert row["actual_distribution"]["flat_count"] == 1


def test_multi_session_ic_uses_sessions_and_retains_negative_day() -> None:
    first = _pairs(labels=("1", "2", "3"))
    second = _pairs(session=date(2026, 9, 11), labels=("3", "2", "1"))
    report = _report(first + second)
    summary = report["aggregate"]["daily_rank_ic"]
    model = summary["model"]
    assert report["session_count"] == 2
    assert report["common_observation_count"] == 6
    assert summary["common_session_roster"] == (DAY, date(2026, 9, 11))
    assert model["mean"]["value"] == D(0)
    assert model["median"]["value"] == D(0)
    assert model["positive_count"] == model["negative_count"] == 1
    assert model["positive_session_ratio"]["numerator"] == 1
    assert model["positive_session_ratio"]["denominator"] == 2
    assert model["mean"]["denominator_kind"] == "ESTIMABLE_COMMON_SESSIONS"
    assert model["icir"]["value"] == D(0)
    assert model["minimum"]["value"] == D(-1)
    assert model["maximum"]["value"] == D(1)
    with localcontext() as context:
        context.prec = 38
        assert model["sample_std"]["value"] == D(2).sqrt()
    assert model["descriptive_standard_error"]["value"] == D(1)
    assert "NOT_CONFIDENCE_INTERVAL" in model["uncertainty_class"]
    assert report["state"] == "DESCRIPTIVE_STATISTICS_AVAILABLE"


def test_one_day_cannot_satisfy_sessions_even_with_many_instruments() -> None:
    pairs = tuple(ValidityPair(UUID(int=index), DAY, D(index), D(-index), D(index)) for index in range(1, 32))
    report = _report(pairs, minimum_sessions=20, minimum_observations=30)
    assert report["state"] == "INSUFFICIENT_SESSIONS"
    assert report["reason_codes"] == ("INSUFFICIENT_SESSIONS",)
    summary = report["aggregate"]["daily_rank_ic"]["model"]
    assert summary["session_count"] == 1
    assert summary["mean"]["value"] == D(1)
    assert summary["sample_std"]["value"] is None
    assert summary["descriptive_standard_error"]["value"] is None


def test_ic_summary_uses_exact_common_estimable_session_roster() -> None:
    first = _pairs()
    second = _pairs(session=date(2026, 9, 11), model=("1", "1", "1"))
    report = _report(first + second)
    summary = report["aggregate"]["daily_rank_ic"]
    assert summary["model_estimable_session_count"] == 1
    assert summary["baseline_estimable_session_count"] == 2
    assert summary["common_estimable_session_count"] == 1
    assert summary["model"]["mean"]["denominator"] == summary["baseline"]["mean"]["denominator"] == 1
    assert summary["common_observation_count"] == 3
    assert summary["excluded_sessions"][0]["session"] == date(2026, 9, 11)
    assert report["common_observation_count"] == 6


def test_ranking_is_forecast_only_and_hypothetical_with_visible_rosters() -> None:
    row = _report(_pairs(labels=("9", "5", "-7")))["per_session"][0]
    ranking = row["ranking"]["model"]
    assert ranking["top_commitments"] == (UUID(int=3),)
    assert ranking["bottom_commitments"] == (UUID(int=1),)
    assert ranking["metrics"]["top_k_realized_return"]["value"] == D(-7)
    assert ranking["metrics"]["bottom_k_realized_return"]["value"] == D(9)
    assert ranking["metrics"]["top_bottom_spread"]["value"] == D(-16)
    assert ranking["metrics"]["quantile_spread"]["value"] == D(-16)
    assert ranking["evidence_class"] == "HYPOTHETICAL_NONTRADABLE; NOT_ACCOUNT_PNL"
    changed = _report(_pairs(labels=("-99", "0", "300")))["per_session"][0]["ranking"]["model"]
    assert changed["top_commitments"] == ranking["top_commitments"]
    assert changed["bottom_commitments"] == ranking["bottom_commitments"]


def test_tie_ranks_use_midranks_and_ranking_tie_break_does_not_use_outcome() -> None:
    report = _report(_pairs(model=("1", "1", "3"), labels=("2", "2", "4")))
    row = report["per_session"][0]
    assert row["model"]["rank_ic"]["value"] == D(1)
    assert row["ranking"]["model"]["bottom_commitments"] == (UUID(int=2),)
    assert report == _report(tuple(reversed(_pairs(model=("1", "1", "3"), labels=("2", "2", "4")))))


def test_insufficient_rank_members_are_not_replaced_with_zero_or_overlapping_spread() -> None:
    row = _report(_pairs()[:2], ranking_k=2, quantiles=3)["per_session"][0]
    assert row["model"]["rank_ic"]["value"] is None
    assert row["model"]["rank_ic"]["reason_code"] == "INSUFFICIENT_OBSERVATIONS"
    assert row["model"]["calibration_slope"]["value"] is None
    ranking = row["ranking"]["model"]["metrics"]
    assert ranking["top_k_realized_return"]["value"] is None
    assert ranking["bottom_k_realized_return"]["value"] is None
    assert ranking["top_bottom_spread"]["value"] is None
    assert ranking["top_bottom_spread"]["reason_code"] == "INSUFFICIENT_DISJOINT_RANKING_MEMBERS"
    assert ranking["quantile_spread"]["value"] is None


def test_frozen_ranking_contract_orders_all_ties_by_uuid_and_uses_floor_quantile_tails() -> None:
    pairs = tuple(ValidityPair(UUID(int=index), DAY, D(1), D(index), D(index)) for index in range(1, 32))
    report = _report(tuple(reversed(pairs)), ranking_k=5, quantiles=5)
    ranking = report["per_session"][0]["ranking"]["model"]
    assert ranking["top_commitments"] == tuple(UUID(int=index) for index in range(1, 6))
    assert ranking["bottom_commitments"] == tuple(UUID(int=index) for index in range(27, 32))
    assert set(ranking["top_commitments"]).isdisjoint(ranking["bottom_commitments"])
    assert ranking["metrics"]["top_k_realized_return"]["value"] == D(3)
    assert ranking["metrics"]["bottom_k_realized_return"]["value"] == D(29)
    assert ranking["metrics"]["top_bottom_spread"]["value"] == D(-26)
    assert ranking["quantile_tail_size"] == 6
    assert ranking["unselected_quantile_middle_count"] == 19
    assert ranking["quantiles"][0]["commitments"] == tuple(UUID(int=index) for index in range(1, 7))
    assert ranking["quantiles"][1]["commitments"] == tuple(UUID(int=index) for index in range(26, 32))
    assert ranking["quantiles"][0]["metric"]["value"] == D("3.5")
    assert ranking["quantiles"][1]["metric"]["value"] == D("28.5")
    assert ranking["metrics"]["quantile_spread"]["value"] == D(-25)
    assert ranking["metrics"]["quantile_spread"]["denominator"] == 12
    assert report["ranking_policy"]["sort"] == "FORECAST_DESCENDING_THEN_COMMITMENT_UUID_ASCENDING"
    baseline = report["per_session"][0]["ranking"]["baseline"]
    assert baseline["top_commitments"] == tuple(UUID(int=index) for index in range(31, 26, -1))
    assert baseline["quantiles"][0]["commitments"] == tuple(UUID(int=index) for index in range(31, 25, -1))
    assert baseline["quantiles"][1]["commitments"] == tuple(UUID(int=index) for index in range(6, 0, -1))
    assert baseline["metrics"]["quantile_spread"]["value"] == D(25)


def test_forecast_ranking_does_not_round_frozen_values_before_ordering() -> None:
    pairs = (ValidityPair(UUID(int=1), DAY, D("1.000000000000000000000000000000000000001"), D(1), D(1)),
             ValidityPair(UUID(int=2), DAY, D("1.000000000000000000000000000000000000002"), D(2), D(2)),
             ValidityPair(UUID(int=3), DAY, D(0), D(3), D(3)))
    ranking = _report(pairs)["per_session"][0]["ranking"]["model"]
    assert ranking["top_commitments"] == (UUID(int=2),)


def test_zero_variance_calibration_ic_and_icir_fail_explicitly() -> None:
    row = _report(_pairs(model=("1", "1", "1")))["per_session"][0]
    assert row["model"]["rank_ic"]["value"] is None
    assert row["model"]["calibration_slope"]["value"] is None
    assert row["model"]["calibration_slope"]["reason_code"] == "ZERO_FORECAST_VARIANCE"
    assert row["model"]["forecast_dispersion"]["value"] == D(0)
    report = _report(_pairs() + _pairs(session=date(2026, 9, 11)))
    summary = report["aggregate"]["daily_rank_ic"]["model"]
    assert summary["sample_std"]["value"] == D(0)
    assert summary["icir"]["value"] is None
    assert summary["icir"]["reason_code"] == "ZERO_VARIANCE"


def test_empty_common_population_retains_unavailable_statistics() -> None:
    report = _report(())
    assert report["session_count"] == report["common_observation_count"] == 0
    assert report["per_session"] == report["rolling"] == report["rank_stability"] == ()
    assert report["aggregate"]["pooled"]["model"]["mae"]["value"] is None
    assert report["aggregate"]["pooled"]["model"]["directional_hit_rate"]["value"] is None
    assert report["aggregate"]["pooled"]["model"]["directional_hit_rate"]["denominator"] == 0
    assert report["aggregate"]["daily_rank_ic"]["model"]["mean"]["value"] is None


def test_rolling_uses_actual_supplied_sessions_and_retains_cumulative_count() -> None:
    report = _report(_pairs() + _pairs(session=date(2026, 9, 14)) + _pairs(session=date(2026, 9, 18)))
    windows = report["rolling"]
    assert len(windows) == 3
    assert windows[0]["window_state"] == "PARTIAL_WINDOW"
    assert windows[2]["session_roster"] == (date(2026, 9, 14), date(2026, 9, 18))
    assert windows[2]["aggregate"]["common_observation_count"] == 6
    assert report["common_observation_count"] == 9
    assert report["per_session"][2]["cumulative_common_observation_count"] == 9
    assert "CALENDAR_CONTIGUITY_NOT_INFERRED" in report["rank_stability"][0]["adjacency_basis"]


def test_calendar_roster_retains_empty_sessions_without_bridging_rank_stability() -> None:
    roster = (DAY, date(2026, 9, 11), date(2026, 9, 14))
    pairs = _pairs() + _pairs(session=roster[2])
    report = validity_statistics(pairs, minimum_sessions=3, minimum_observations=6,
                                 rolling_sessions=2, ranking_k=1, quantiles=3, session_roster=roster)
    assert report["expected_session_count"] == 3
    assert report["estimable_session_count"] == report["session_count"] == 2
    assert report["reason_codes"] == ("INSUFFICIENT_SESSIONS",)
    assert report["per_session"][1]["session"] == roster[1]
    assert report["per_session"][1]["state"] == "NOT_ESTIMABLE"
    assert report["per_session"][1]["model"]["mae"]["value"] is None
    assert report["per_session"][1]["cumulative_common_observation_count"] == 3
    assert report["rolling"][2]["session_roster"] == roster[1:]
    assert report["rolling"][2]["aggregate"]["common_observation_count"] == 3
    assert report["rolling"][2]["aggregate"]["expected_session_count"] == 2
    assert report["rolling"][2]["aggregate"]["estimable_session_count"] == 1
    assert len(report["rank_stability"]) == 2
    assert all(row["model"]["reason_code"] == "SESSION_COMMON_POPULATION_UNAVAILABLE"
               and row["common_population_jaccard"]["value"] is None for row in report["rank_stability"])


@pytest.mark.parametrize("roster", ((date(2026, 9, 11),), (DAY, DAY), (date(2026, 9, 11), DAY)))
def test_session_roster_cannot_drop_pairs_duplicate_or_reorder_sessions(roster: tuple[date, ...]) -> None:
    with pytest.raises(ValueError, match="session roster"):
        validity_statistics(_pairs(), minimum_sessions=2, minimum_observations=6, session_roster=roster)


def test_rank_stability_uses_instrument_overlap_and_reports_population_basis() -> None:
    first = _pairs()
    second = _pairs(session=date(2026, 9, 11), model=("3", "2", "1"))
    stability = _report(first + second)["rank_stability"][0]
    assert stability["common_instrument_count"] == 3
    assert stability["model"]["value"] == D(-1)
    assert stability["baseline"]["value"] == D(1)
    assert stability["common_population_jaccard"]["value"] == D(1)
    assert stability["common_population_jaccard"]["numerator"] == 3
    assert stability["common_population_jaccard"]["denominator"] == 3
    changed = (replace(second[0], instrument_id=UUID(int=999)), *second[1:])
    stability = _report(first + changed)["rank_stability"][0]
    assert stability["common_population_jaccard"]["value"] == D("0.5")
    assert stability["common_instrument_count"] == 2
    assert stability["model"]["value"] is None


def test_missing_instrument_identity_is_not_silently_removed_for_stability() -> None:
    first = _pairs()
    second = tuple(replace(pair, instrument_id=None) for pair in _pairs(session=date(2026, 9, 11)))
    stability = _report(first + second)["rank_stability"][0]
    assert stability["model"]["value"] is None
    assert stability["model"]["reason_code"] == "INSTRUMENT_IDENTITY_UNAVAILABLE"
    assert stability["common_population_jaccard"]["value"] is None


def test_duplicate_commitments_or_instruments_fail_closed_and_pairs_are_immutable() -> None:
    pairs = _pairs()
    with pytest.raises(ValueError, match="duplicate session/commitment"):
        _report(pairs + (pairs[0],))
    with pytest.raises(ValueError, match="duplicate session/instrument"):
        _report((pairs[0], replace(pairs[1], instrument_id=pairs[0].instrument_id)))
    with pytest.raises(FrozenInstanceError):
        pairs[0].label = D(99)  # type: ignore[misc]
    assert _report(pairs + _pairs(session=date(2026, 9, 11)))["common_observation_count"] == 6


@pytest.mark.parametrize("invalid", ("NaN", "Infinity", "-Infinity"))
def test_nonfinite_pairs_are_rejected_instead_of_missingness_becoming_zero(invalid: str) -> None:
    with pytest.raises(ValueError, match="finite canonical Decimal"):
        replace(_pairs()[0], label=D(invalid))


@pytest.mark.parametrize("parameter,value", (("minimum_sessions", 0), ("minimum_observations", -1),
                                           ("rolling_sessions", True), ("ranking_k", 0), ("quantiles", 1)))
def test_invalid_sample_and_ranking_parameters_fail_closed(parameter: str, value: int) -> None:
    with pytest.raises(ValueError, match="positive integers"):
        _report(_pairs(), **{parameter: value})


def test_decimal_context_and_input_order_do_not_change_replay() -> None:
    pairs = _pairs(model=("0.0000000000000000000000000000123", "0.2", "-0.13579"),
                   labels=("0.12", "-0.987654321", "-0.7"))
    expected = _report(pairs)
    with localcontext() as context:
        context.prec = 6
        actual = _report(tuple(reversed(pairs)))
    assert actual == expected
    assert pairs[0].label == D("0.12")
    assert actual["decimal_precision"] == 38
    assert actual["rounding_mode"] == "ROUND_HALF_EVEN"
