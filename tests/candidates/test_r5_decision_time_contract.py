from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.candidates.contracts import CandidatePopulation
from market_regime_alpha.candidates.rehearsal_targets import materialize_r5_next_session_return_target
from market_regime_alpha.core.identity import DatasetId, UniverseId
from market_regime_alpha.core.time import AsOfTime, DecisionTime
from market_regime_alpha.features.rehearsal_baselines import materialize_r5_baseline_features


TZ = ZoneInfo("Asia/Shanghai")
SOURCE_DATASET_ID = DatasetId("dataset-r5-decision-time-guard")


def _wrong_time_population() -> CandidatePopulation:
    return CandidatePopulation(
        universe_id=UniverseId("universe-r5-decision-time-guard"),
        decision_time=DecisionTime(datetime(2026, 7, 15, 14, 50, tzinfo=TZ)),
        symbols=("000001.SZ",),
        source_dataset_ids=(SOURCE_DATASET_ID,),
    )


def test_r5_feature_materializer_rejects_non_1455_decision_time() -> None:
    with pytest.raises(ValueError, match="14:55:00 Asia/Shanghai"):
        materialize_r5_baseline_features(
            population=_wrong_time_population(),
            source_dataset_id=SOURCE_DATASET_ID,
            daily_bars=(),
            decision_snapshots=(),
            code_revision="abc123",
            config_hash="r5-baseline-features-v1",
        )


def test_r5_target_materializer_rejects_non_1455_decision_time() -> None:
    with pytest.raises(ValueError, match="14:55:00 Asia/Shanghai"):
        materialize_r5_next_session_return_target(
            population=_wrong_time_population(),
            source_dataset_id=SOURCE_DATASET_ID,
            decision_snapshots=(),
            next_session_date=date(2026, 7, 16),
            next_session_closes=(),
            materialized_at=AsOfTime(datetime(2026, 7, 16, 15, 30, tzinfo=TZ)),
            code_revision="abc123",
            config_hash="r5-next-session-target-v1",
        )
