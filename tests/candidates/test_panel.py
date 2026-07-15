from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from market_regime_alpha.candidates.dataset import (
    CandidateDatasetRow,
    CandidateFeatureValue,
    CandidateResearchDataset,
    CandidateTargetValue,
    TargetObservationStatus,
)
from market_regime_alpha.candidates.panel import assemble_candidate_research_panel
from market_regime_alpha.core.identity import (
    ArtifactId,
    DatasetId,
    FeatureDefinitionId,
    FeatureMaterializationId,
    TargetId,
    UniverseId,
)
from market_regime_alpha.core.status import InputAvailabilityStatus
from market_regime_alpha.core.time import DecisionTime
from market_regime_alpha.data.contracts import DataEligibility


BASE = datetime(2026, 7, 13, 6, 55, tzinfo=timezone.utc)
FEATURE_ID = FeatureDefinitionId("feature-relative-strength-20d-v1")
TARGET_ID = TargetId("target-next-session-return-v1")


def _slice(day_offset: int, *, eligibility: DataEligibility, universe_suffix: str) -> CandidateResearchDataset:
    decision_time = DecisionTime(BASE + timedelta(days=day_offset))
    symbol = f"00000{day_offset + 1}.SZ"
    return CandidateResearchDataset(
        dataset_id=DatasetId(f"candidate-slice-{day_offset}"),
        source_dataset_ids=(DatasetId(f"source-{day_offset}"),),
        data_eligibility=eligibility,
        universe_id=UniverseId(f"universe-{universe_suffix}"),
        decision_time=decision_time,
        population_symbols=(symbol,),
        target_id=TARGET_ID,
        target_materialization_artifact_id=ArtifactId(f"target-artifact-{day_offset}"),
        feature_definition_ids=(FEATURE_ID,),
        feature_materialization_ids=(FeatureMaterializationId(f"fm-{day_offset}"),),
        rows=(
            CandidateDatasetRow(
                symbol=symbol,
                feature_values=(
                    CandidateFeatureValue(
                        feature_id=FEATURE_ID,
                        status=InputAvailabilityStatus.AVAILABLE,
                        value=0.1 + day_offset,
                    ),
                ),
                target=CandidateTargetValue(
                    target_id=TARGET_ID,
                    status=TargetObservationStatus.NOT_YET_OBSERVED,
                    value=None,
                ),
            ),
        ),
    )


def test_panel_orders_slices_and_allows_pit_universe_to_change() -> None:
    later = _slice(2, eligibility=DataEligibility.REHEARSAL, universe_suffix="20260715")
    earlier = _slice(0, eligibility=DataEligibility.EXPLORATORY, universe_suffix="20260713")

    panel = assemble_candidate_research_panel((later, earlier), limitations=("rehearsal only",))
    repeated = assemble_candidate_research_panel((earlier, later), limitations=("rehearsal only",))

    assert panel.dataset_id == repeated.dataset_id
    assert panel.decision_times == (earlier.decision_time, later.decision_time)
    assert panel.slice_dataset_ids == (earlier.dataset_id, later.dataset_id)
    assert panel.slices[0].universe_id != panel.slices[1].universe_id
    assert panel.data_eligibility is DataEligibility.EXPLORATORY
    assert panel.slice_count == 2
    assert panel.row_count == 2


def test_panel_rejects_target_drift() -> None:
    first = _slice(0, eligibility=DataEligibility.REHEARSAL, universe_suffix="a")
    second = _slice(1, eligibility=DataEligibility.REHEARSAL, universe_suffix="b")
    second = CandidateResearchDataset(
        dataset_id=second.dataset_id,
        source_dataset_ids=second.source_dataset_ids,
        data_eligibility=second.data_eligibility,
        universe_id=second.universe_id,
        decision_time=second.decision_time,
        population_symbols=second.population_symbols,
        target_id=TargetId("target-different-v1"),
        target_materialization_artifact_id=second.target_materialization_artifact_id,
        feature_definition_ids=second.feature_definition_ids,
        feature_materialization_ids=second.feature_materialization_ids,
        rows=(
            CandidateDatasetRow(
                symbol=second.rows[0].symbol,
                feature_values=second.rows[0].feature_values,
                target=CandidateTargetValue(
                    target_id=TargetId("target-different-v1"),
                    status=TargetObservationStatus.NOT_YET_OBSERVED,
                    value=None,
                ),
            ),
        ),
    )

    with pytest.raises(ValueError, match="cannot mix Target identities"):
        assemble_candidate_research_panel((first, second))


def test_panel_rejects_duplicate_decision_times() -> None:
    first = _slice(0, eligibility=DataEligibility.REHEARSAL, universe_suffix="a")
    second = CandidateResearchDataset(
        dataset_id=DatasetId("candidate-slice-duplicate-time"),
        source_dataset_ids=(DatasetId("source-duplicate-time"),),
        data_eligibility=DataEligibility.REHEARSAL,
        universe_id=UniverseId("universe-b"),
        decision_time=first.decision_time,
        population_symbols=("000002.SZ",),
        target_id=TARGET_ID,
        target_materialization_artifact_id=ArtifactId("target-artifact-duplicate-time"),
        feature_definition_ids=(FEATURE_ID,),
        feature_materialization_ids=(FeatureMaterializationId("fm-duplicate-time"),),
        rows=(
            CandidateDatasetRow(
                symbol="000002.SZ",
                feature_values=(
                    CandidateFeatureValue(FEATURE_ID, InputAvailabilityStatus.AVAILABLE, 0.2),
                ),
                target=CandidateTargetValue(TARGET_ID, TargetObservationStatus.NOT_YET_OBSERVED, None),
            ),
        ),
    )

    with pytest.raises(ValueError, match="duplicate Decision Times"):
        assemble_candidate_research_panel((first, second))
