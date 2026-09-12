"""Protocol boundaries; the PostgreSQL suite resolves the actual Calendar."""

from dataclasses import asdict, replace
from datetime import date, timedelta
from decimal import Decimal
import json

import pytest

from market_regime_alpha.research_qualification.domain.historical_matrix import HistoricalMatrixPlan, HistoricalRidgeCandidate, HistoricalTimeSplit
from market_regime_alpha.research_qualification.domain.historical_rolling import HistoricalRollingPlan, RollingStudyPlan, ROBUSTNESS_CONTROLS
from market_regime_alpha.research_qualification.domain.historical_study import HistoricalStudyPlan
from tests.contracts.research_qualification.test_historical_study_plan import plan


def rolling(fit=126, mode="ROLLING"):
    # Explicit synthetic session dates test structure, not exchange coverage.
    days = tuple(date(2022,1,1) + timedelta(days=i) for i in range(500))
    base = plan()
    baseline = RollingStudyPlan(**(asdict(base) | {"fit_dates":days[:fit], "purge_dates":days[fit:fit+1],
        "embargo_dates":days[fit+1:fit+2], "validation_dates":days[fit+2:fit+24], "candidates":ROBUSTNESS_CONTROLS}))
    second = HistoricalTimeSplit(days[0 if mode=="EXPANDING" else 42:fit+42], days[fit+42:fit+43],
        days[fit+43:fit+44], days[fit+44:fit+66])
    return HistoricalRollingPlan(baseline, (second,),
        (HistoricalRidgeCandidate("ridge_momentum", ("intraday","return_1","return_5","return_20"), Decimal(1)),), 42, mode)


@pytest.mark.parametrize("fit,mode", [(126,"ROLLING"),(252,"ROLLING"),(126,"EXPANDING")])
def test_overlapping_fit_roundtrip_preserves_frozen_dates_and_mature_update_policy(fit,mode):
    original = rolling(fit,mode)
    raw = json.loads(json.dumps(asdict(original), default=str))
    raw["schema"] = "mra-historical-rolling-v2"
    raw["baseline"]["schema"] = "mra-rolling-study-v2"
    assert HistoricalRollingPlan.from_bytes(json.dumps(raw).encode()) == original
    assert set(original.splits[0].fit_dates) & set(original.splits[1].fit_dates)
    assert not set(original.splits[0].validation_dates) & set(original.splits[1].validation_dates)
    assert set(original.splits[0].validation_dates) <= set(original.splits[1].fit_dates)
    assert original.splits[1].purge_dates[0] > original.splits[1].fit_dates[-1]


def test_old_schema_cannot_accept_median_or_silently_gain_overlapping_windows():
    new = rolling()
    with pytest.raises(ValueError,match="baseline candidate"):
        HistoricalStudyPlan(**asdict(new.baseline))
    with pytest.raises(ValueError,match="seven"):
        HistoricalMatrixPlan(new.baseline,new.additional_splits,new.ridge_candidates,42)


@pytest.mark.parametrize("change", [
    {"additional_splits":(rolling().splits[0],)}, {"step_sessions":True},
    {"update_policy":"ALLOW_FUTURE_LABELS"}, {"mode":"UNBOUNDED"},
    {"additional_splits":rolling().additional_splits*24},
    {"ridge_candidates":rolling().ridge_candidates*7},
])
def test_rolling_rejects_repeated_scoring_unbounded_work_and_access_inflation(change):
    with pytest.raises(ValueError):
        replace(rolling(),**change)


def test_rolling_decoder_rejects_duplicate_fields_before_owner_declarations():
    with pytest.raises(ValueError,match="duplicate"):
        HistoricalRollingPlan.from_bytes(b'{"schema":"mra-historical-rolling-v2","schema":"mra-historical-matrix-v1"}')
