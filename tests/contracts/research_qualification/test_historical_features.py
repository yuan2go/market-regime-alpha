"""Independent arithmetic and boundary contracts; synthetic inputs are not research evidence."""

from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal as D, localcontext
import math
import statistics
from uuid import UUID

import pytest

from market_regime_alpha.research_qualification.domain.historical_features import (
    FACTORS, HistoricalDailyPoint, append_historical_session, calculate_historical_features,
)


def _population(count=21):
    # Explicit test Calendar, including deliberate non-weekday spacing.
    days = tuple(date(2022, 1, 1) + timedelta(days=i * 2) for i in range(count))
    return days, {UUID(int=i): tuple(HistoricalDailyPoint(day, D(100), D(100+i),
        D(100) + D(i*j), D(10+j), D(1000+100*j)) for j, day in enumerate(days)) for i in (1,2,3)}


def test_ten_features_match_independent_reference_values_and_rank_ties():
    days, population = _population()
    computed = calculate_historical_features(days, population)
    assert len(FACTORS) == 10 and all(len(values) == 10 for values in computed.values())
    for instrument, points in population.items():
        i = instrument.int
        prices = [100+i*j for j in range(21)]
        returns = [b/a-1 for a,b in zip(prices, prices[1:])]
        reference = {"intraday": i/100, "return_1": prices[-1]/prices[-2]-1,
            "return_5": prices[-1]/prices[-6]-1, "return_20": prices[-1]/prices[0]-1,
            "volatility_20": statistics.stdev(returns), "volume_5_20": statistics.mean(range(26,31))/statistics.mean(range(11,31))-1,
            "amount_5_20": statistics.mean(range(2600,3100,100))/statistics.mean(range(1100,3100,100))-1,
            "peer_relative_5": prices[-1]/prices[-6]-1-statistics.mean((100+k*20)/(100+k*15)-1 for k in (1,2,3)),
            "peer_relative_20": i*.2-.4, "cross_section_5": (i-1)/2}
        for name, expected in reference.items():
            value = computed[instrument][name]
            assert value.reason == "EXACT_HISTORICAL_FACTOR"
            assert math.isclose(float(value.value), expected, abs_tol=2e-12)
    tied = {i: population[UUID(int=1)] for i in population}
    assert {v["cross_section_5"].value for v in calculate_historical_features(days,tied).values()} == {D(".5")}


def test_full_and_bounded_incremental_computation_are_identical_with_missing_windows():
    all_days, all_population = _population(28)
    points = list(all_population[UUID(int=2)])
    points[12] = replace(points[12], adjusted_close=None)
    all_population[UUID(int=2)] = tuple(points)
    days, population = (), {i: () for i in all_population}
    for offset in range(len(all_days)):
        days, population = append_historical_session(days, population, {i: p[offset] for i,p in all_population.items()})
        assert calculate_historical_features(days,population) == calculate_historical_features(
            all_days[max(0,offset-20):offset+1], {i:p[max(0,offset-20):offset+1] for i,p in all_population.items()})
        assert len(days) <= 21


def test_warmup_adjustment_gaps_and_zero_activity_are_not_imputed():
    days, population = _population()
    instrument = UUID(int=1)
    constant = tuple(replace(p, raw_close=D(50), adjusted_close=D(100), volume=D(0)) for p in population[instrument])
    population[instrument] = constant
    result = calculate_historical_features(days,population)[instrument]
    assert result["return_20"].value == result["volatility_20"].value == 0
    assert result["intraday"].value == D("-.5")
    assert result["volume_5_20"].value is None
    assert result["volume_5_20"].reason == "FEATURE_ZERO_ACTIVITY_DENOMINATOR"
    incomplete = list(constant)
    incomplete[10] = replace(incomplete[10],adjusted_close=None)
    population[instrument] = tuple(incomplete)
    assert calculate_historical_features(days,population)[instrument]["return_20"].value is None
    warm = calculate_historical_features(days[-2:],{instrument:constant[-2:]})[instrument]
    assert warm["return_5"].reason == "FEATURE_WARMUP_INSUFFICIENT"
    assert warm["peer_relative_5"].value is None


def test_factor_results_do_not_depend_on_ambient_decimal_context():
    days,population = _population()
    expected = calculate_historical_features(days,population)
    with localcontext() as context:
        context.prec = 5
        assert calculate_historical_features(days,population) == expected


def test_rank_uses_unrounded_returns_before_final_cell_quantization():
    days,population = _population()
    for instrument, points in population.items():
        population[instrument] = tuple(replace(p, adjusted_close=D(1000) + (D(instrument.int-1)*D("1e-10") if n==20 else D(0))) for n,p in enumerate(points))
    computed = calculate_historical_features(days,population)
    assert {v["return_5"].value for v in computed.values()} == {D(0)}
    assert [computed[UUID(int=i)]["cross_section_5"].value for i in (1,2,3)] == [D(0),D(".5"),D(1)]


@pytest.mark.parametrize("bad", [D("NaN"),D("Infinity"),D(0),D(-1)])
def test_invalid_prices_are_rejected(bad):
    with pytest.raises(ValueError,match="finite"):
        HistoricalDailyPoint(date(2022,1,1),bad,D(1),D(1),D(0),None)


def test_calendar_order_missing_rows_and_unknown_member_change_are_rejected():
    days,population = _population()
    with pytest.raises(ValueError,match="ordered"):
        calculate_historical_features(days[::-1],population)
    with pytest.raises(ValueError,match="every exact Calendar"):
        calculate_historical_features(days,{i:p[:-1] for i,p in population.items()})
    with pytest.raises(ValueError,match="unchanged"):
        append_historical_session(days,population,{UUID(int=1):population[UUID(int=1)][-1]})
