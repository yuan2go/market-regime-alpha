"""Budget/time declaration tests; real performance evidence is recorded separately."""

from dataclasses import asdict, replace
from datetime import date
from decimal import Decimal
import json

import pytest

from market_regime_alpha.research_qualification.domain.historical_matrix import (
    HistoricalMatrixPlan, HistoricalRidgeCandidate, HistoricalTimeSplit,
)
from tests.contracts.research_qualification.test_historical_study_plan import plan


def matrix():
    later = HistoricalTimeSplit((date(2026,2,2),),(date(2026,2,3),),(date(2026,2,4),),(date(2026,2,5),))
    return HistoricalMatrixPlan(plan(), (later,),
        (HistoricalRidgeCandidate("ridge_full",("intraday","return_1"),Decimal("1")),), 20)


def payload():
    result=json.loads(json.dumps(asdict(matrix()),default=str))
    result["schema"]="mra-historical-matrix-v1"
    result["baseline"]["schema"]="mra-historical-study-v1"
    return result


def test_matrix_roundtrip_keeps_all_controls_per_fold_and_exact_feature_order():
    original=matrix()
    assert HistoricalMatrixPlan.from_bytes(json.dumps(payload()).encode())==original
    assert len(original.splits)==2
    assert original.splits[0].fit_dates==original.baseline.fit_dates


@pytest.mark.parametrize("changes",[
    {"step_sessions":True}, {"step_sessions":0}, {"ridge_candidates":()},
    {"baseline":replace(plan(),candidates=("ridge_v2",))},
    {"ridge_candidates":matrix().ridge_candidates*2},
    {"additional_splits":(matrix().splits[0],)},
    {"additional_splits":(replace(matrix().splits[1],fit_dates=(date(2026,2,1),date(2026,2,2))),)},
])
def test_matrix_refuses_changed_denominators_time_overlap_or_unbounded_search(changes):
    with pytest.raises(ValueError):
        replace(matrix(),**changes)


@pytest.mark.parametrize("features,alpha",[
    (("return_1","intraday"),"1"), (("intraday","intraday"),"1"), (("future",),"1"),
    (("intraday",),".01"), (("intraday",),"NaN"), (("intraday",),"Infinity"),
])
def test_candidate_refuses_feature_drift_and_outside_alpha_budget(features,alpha):
    with pytest.raises(ValueError):
        HistoricalRidgeCandidate("ridge_expanded",features,Decimal(alpha))


@pytest.mark.parametrize("field,value",[("ridge_alpha",True),("ridge_alpha",0.1),("extra","unknown")])
def test_parser_refuses_ambiguous_parameter_types_and_unknown_fields(field,value):
    data=payload()
    data["ridge_candidates"][0][field]=value
    with pytest.raises(ValueError):
        HistoricalMatrixPlan.from_bytes(json.dumps(data).encode())


def test_parser_rejects_duplicate_fields_before_owner_writes():
    with pytest.raises(ValueError,match="duplicate"):
        HistoricalMatrixPlan.from_bytes(b'{"schema":"a","schema":"b"}')
