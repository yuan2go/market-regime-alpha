from dataclasses import replace
from decimal import Decimal as D, localcontext
from uuid import UUID

import pytest

from market_regime_alpha.research_qualification.domain.robustness_statistics import robustness_statistics
from tests.contracts.research_qualification.test_historical_comparison import source


def inputs():
    originals,kwargs = source()
    names = ("zero","training_mean","training_median","ridge_v2","ridge_momentum")
    arms = tuple((UUID(int=i),name) for i,name in enumerate(names,20))
    rows = []
    for identity,name in arms:
        for point in originals[:6]:
            prediction = D(0) if name in names[:3] else point.label/(2 if name=="ridge_v2" else 1)
            rows.append(replace(point,arm_id=identity,prediction=prediction))
    return tuple(rows),dict(arms=arms,sessions=kwargs["sessions"],instruments=kwargs["instruments"],contiguous_folds=frozenset({UUID(int=3)}))


def test_primary_pairs_have_independent_errors_constant_rank_and_security_sensitivity():
    points,kwargs = inputs()
    result = robustness_statistics(points,**kwargs)
    assert len(result["comparisons"])==7
    mom = next(r for r in result["comparisons"] if (r["model"],r["reference"])==("ridge_momentum","ridge_v2"))
    with localcontext() as ctx:
        ctx.prec=38
        # Labels -1,0,+1: perfect momentum vs half-label Ridge saves 1/3 MAE.
        assert mom["mae_delta"]==-D(1)/3
    assert mom["mean_daily_rank_ic_delta"]==0  # Same ranking, different point error.
    assert mom["mae_day_signs"]["negative"]==2 and mom["ic_day_signs"]["zero"]==2
    assert mom["leave_one_security_out"][1]["remaining_mae_delta"]==D("-.5")
    assert mom["paired_mae_uncertainty"]["state"]=="NOT_ESTIMABLE"
    for comparison in result["comparisons"]:
        if comparison["reference"] in {"zero","training_mean","training_median"}:
            assert comparison["mean_daily_rank_ic_delta"] is None
            assert comparison["paired_daily_ic_uncertainty"]["state"]=="NOT_ESTIMABLE"


def test_pair_population_is_not_reduced_by_an_unrelated_missing_model():
    points,kwargs = inputs()
    points = tuple(replace(p,prediction=None,forecast_status="NOT_ESTIMABLE",input_state="NOT_ESTIMABLE")
        if p.arm_id==kwargs["arms"][-1][0] and p.instrument_id==kwargs["instruments"][0] else p for p in points)
    result = robustness_statistics(points,**kwargs)
    ridge = next(r for r in result["comparisons"] if (r["model"],r["reference"])==("ridge_v2","zero"))
    assert ridge["expected_observations"]==ridge["paired_observations"]==6
    assert ridge["all_arm_common_observations"]==4
    mom = next(r for r in result["comparisons"] if (r["model"],r["reference"])==("ridge_momentum","zero"))
    assert mom["model_own_observations"]==4 and mom["reference_own_observations"]==6
    assert mom["paired_observations"]==4


def test_duplicate_dates_and_conflicting_labels_are_refused():
    points,kwargs = inputs()
    with pytest.raises(ValueError,match="repeated"):
        robustness_statistics(points,**(kwargs|{"sessions":kwargs["sessions"]*2}))
    with pytest.raises(ValueError,match="conflict"):
        robustness_statistics((*points[:-1],replace(points[-1],label=D(9))),**kwargs)
