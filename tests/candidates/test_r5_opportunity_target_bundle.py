from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.candidates.contracts import CandidatePopulation
from market_regime_alpha.candidates.dataset import TargetObservationStatus
from market_regime_alpha.candidates.rehearsal_opportunity_targets import (
    R5_NEXT_SESSION_MAE_TARGET_ID,
    R5_NEXT_SESSION_MFE_TARGET_ID,
    materialize_r5_next_session_opportunity_targets,
    r5_next_session_opportunity_target_contracts,
)
from market_regime_alpha.candidates.rehearsal_targets import R5_NEXT_SESSION_RETURN_TARGET_ID
from market_regime_alpha.core.identity import DatasetId, UniverseId
from market_regime_alpha.core.time import AsOfTime, AvailabilityTime, DecisionTime
from market_regime_alpha.data.rehearsal import RehearsalDecisionSnapshot, RehearsalNextSessionBar


TZ = ZoneInfo("Asia/Shanghai")
DECISION_AT = datetime(2026, 7, 15, 14, 55, tzinfo=TZ)
NEXT_SESSION_DATE = date(2026, 7, 16)
AVAILABLE_AT = AvailabilityTime(datetime(2026, 7, 16, 15, 5, tzinfo=TZ))
MATERIALIZED_AT = AsOfTime(datetime(2026, 7, 16, 15, 30, tzinfo=TZ))
SOURCE_DATASET_ID = DatasetId("dataset-r5-opportunity-target-fixture-v1")
UNIVERSE_ID = UniverseId("universe-r5-opportunity-20260715")


def _population() -> CandidatePopulation:
    return CandidatePopulation(
        universe_id=UNIVERSE_ID,
        decision_time=DecisionTime(DECISION_AT),
        symbols=("000001.SZ", "000002.SZ", "000003.SZ"),
        source_dataset_ids=(SOURCE_DATASET_ID,),
    )


def test_opportunity_target_bundle_keeps_close_mfe_mae_identity_distinct() -> None:
    population = _population()
    bundle = materialize_r5_next_session_opportunity_targets(
        population=population,
        source_dataset_id=SOURCE_DATASET_ID,
        decision_snapshots=(
            RehearsalDecisionSnapshot(
                "000001.SZ",
                population.decision_time,
                100.0,
                AvailabilityTime(DECISION_AT),
            ),
            RehearsalDecisionSnapshot(
                "000002.SZ",
                population.decision_time,
                100.0,
                AvailabilityTime(DECISION_AT),
            ),
        ),
        next_session_date=NEXT_SESSION_DATE,
        next_session_bars=(
            RehearsalNextSessionBar(
                "000001.SZ",
                NEXT_SESSION_DATE,
                101.0,
                110.0,
                95.0,
                105.0,
                AVAILABLE_AT,
            ),
            RehearsalNextSessionBar(
                "000002.SZ",
                NEXT_SESSION_DATE,
                102.0,
                103.0,
                101.0,
                102.0,
                AVAILABLE_AT,
            ),
        ),
        materialized_at=MATERIALIZED_AT,
        code_revision="abc123",
        config_hash="r5-opportunity-targets-v1",
    )

    expected_target_ids = tuple(
        sorted(
            (
                R5_NEXT_SESSION_RETURN_TARGET_ID,
                R5_NEXT_SESSION_MFE_TARGET_ID,
                R5_NEXT_SESSION_MAE_TARGET_ID,
            ),
            key=str,
        )
    )
    assert bundle.target_ids == expected_target_ids
    assert len({item.artifact_id for item in bundle.materializations}) == 3

    close_by_symbol = {
        observation.symbol: observation
        for observation in bundle.get(R5_NEXT_SESSION_RETURN_TARGET_ID).observations
    }
    mfe_by_symbol = {
        observation.symbol: observation
        for observation in bundle.get(R5_NEXT_SESSION_MFE_TARGET_ID).observations
    }
    mae_by_symbol = {
        observation.symbol: observation
        for observation in bundle.get(R5_NEXT_SESSION_MAE_TARGET_ID).observations
    }

    assert close_by_symbol["000001.SZ"].value == pytest.approx(0.05)
    assert mfe_by_symbol["000001.SZ"].value == pytest.approx(0.10)
    assert mae_by_symbol["000001.SZ"].value == pytest.approx(-0.05)

    assert close_by_symbol["000002.SZ"].value == pytest.approx(0.02)
    assert mfe_by_symbol["000002.SZ"].value == pytest.approx(0.03)
    assert mae_by_symbol["000002.SZ"].value == pytest.approx(0.0)

    for target_id in expected_target_ids:
        observation = {
            item.symbol: item
            for item in bundle.get(target_id).observations
        }["000003.SZ"]
        assert observation.status is TargetObservationStatus.INVALID
        assert observation.value is None


def test_opportunity_target_contracts_are_independent_targets() -> None:
    contracts = r5_next_session_opportunity_target_contracts()
    assert {contract.target_id for contract in contracts} == {
        R5_NEXT_SESSION_RETURN_TARGET_ID,
        R5_NEXT_SESSION_MFE_TARGET_ID,
        R5_NEXT_SESSION_MAE_TARGET_ID,
    }
    assert len({contract.outcome for contract in contracts}) == 3


def test_opportunity_target_bundle_rejects_wrong_next_session_date() -> None:
    population = _population()
    with pytest.raises(ValueError, match="resolved next_session_date"):
        materialize_r5_next_session_opportunity_targets(
            population=population,
            source_dataset_id=SOURCE_DATASET_ID,
            decision_snapshots=(
                RehearsalDecisionSnapshot(
                    "000001.SZ",
                    population.decision_time,
                    100.0,
                    AvailabilityTime(DECISION_AT),
                ),
            ),
            next_session_date=NEXT_SESSION_DATE,
            next_session_bars=(
                RehearsalNextSessionBar(
                    "000001.SZ",
                    date(2026, 7, 17),
                    101.0,
                    110.0,
                    95.0,
                    105.0,
                    AvailabilityTime(datetime(2026, 7, 17, 15, 5, tzinfo=TZ)),
                ),
            ),
            materialized_at=AsOfTime(datetime(2026, 7, 17, 15, 30, tzinfo=TZ)),
            code_revision="abc123",
            config_hash="r5-opportunity-targets-v1",
        )


def test_rehearsal_next_session_bar_validates_ohlc_bounds() -> None:
    with pytest.raises(ValueError, match="low <= open <= high"):
        RehearsalNextSessionBar(
            "000001.SZ",
            NEXT_SESSION_DATE,
            120.0,
            110.0,
            95.0,
            105.0,
            AVAILABLE_AT,
        )
