from __future__ import annotations

from datetime import datetime, timezone

import pytest

from market_regime_alpha.core.identity import ArtifactId, DatasetId, UniverseId
from market_regime_alpha.core.time import AsOfTime, DecisionTime
from market_regime_alpha.candidates.contracts import build_candidate_population
from market_regime_alpha.universe.contracts import (
    PITUniverseSnapshot,
    TradingEligibilityRecord,
    TradingEligibilitySnapshot,
    TradingEligibilityStatus,
    UniverseMembershipRecord,
)


AS_OF = datetime(2026, 7, 15, 6, 55, tzinfo=timezone.utc)


def test_universe_membership_and_trading_eligibility_are_separate() -> None:
    universe = PITUniverseSnapshot(
        universe_id=UniverseId("universe-v1"),
        as_of=AsOfTime(AS_OF),
        source_dataset_id=DatasetId("universe-dataset-v1"),
        evidence_artifact_id=ArtifactId("universe-artifact-v1"),
        method_version="pit-universe-v1",
        records=(
            UniverseMembershipRecord("000001.SZ", True),
            UniverseMembershipRecord("000002.SZ", True),
            UniverseMembershipRecord("000003.SZ", False),
        ),
    )
    eligibility = TradingEligibilitySnapshot(
        as_of=AsOfTime(AS_OF),
        source_dataset_id=DatasetId("eligibility-dataset-v1"),
        evidence_artifact_id=ArtifactId("eligibility-artifact-v1"),
        records=(
            TradingEligibilityRecord("000001.SZ", TradingEligibilityStatus.ELIGIBLE),
            TradingEligibilityRecord(
                "000002.SZ",
                TradingEligibilityStatus.INELIGIBLE,
                reasons=("SUSPENDED",),
            ),
        ),
    )

    population = build_candidate_population(
        universe,
        eligibility,
        decision_time=DecisionTime(AS_OF),
    )

    assert universe.member_symbols == ("000001.SZ", "000002.SZ")
    assert population.symbols == ("000001.SZ",)


def test_missing_eligibility_is_unknown_and_not_silently_eligible() -> None:
    eligibility = TradingEligibilitySnapshot(
        as_of=AsOfTime(AS_OF),
        source_dataset_id=DatasetId("eligibility-dataset-v1"),
        evidence_artifact_id=ArtifactId("eligibility-artifact-v1"),
        records=(),
    )

    assert eligibility.status_for("000001.SZ") is TradingEligibilityStatus.UNKNOWN


def test_valid_candidate_population_may_be_empty() -> None:
    universe = PITUniverseSnapshot(
        universe_id=UniverseId("universe-v1"),
        as_of=AsOfTime(AS_OF),
        source_dataset_id=DatasetId("universe-dataset-v1"),
        evidence_artifact_id=ArtifactId("universe-artifact-v1"),
        method_version="pit-universe-v1",
        records=(
            UniverseMembershipRecord("000001.SZ", True),
            UniverseMembershipRecord("000002.SZ", True),
        ),
    )
    eligibility = TradingEligibilitySnapshot(
        as_of=AsOfTime(AS_OF),
        source_dataset_id=DatasetId("eligibility-dataset-v1"),
        evidence_artifact_id=ArtifactId("eligibility-artifact-v1"),
        records=(
            TradingEligibilityRecord("000001.SZ", TradingEligibilityStatus.INELIGIBLE),
        ),
    )

    population = build_candidate_population(
        universe,
        eligibility,
        decision_time=DecisionTime(AS_OF),
    )

    assert population.symbols == ()


def test_trading_eligibility_status_must_use_canonical_enum() -> None:
    with pytest.raises(TypeError, match="TradingEligibilityStatus"):
        TradingEligibilityRecord("000001.SZ", "ELIGIBLE")  # type: ignore[arg-type]


def test_future_universe_snapshot_cannot_build_past_candidate_population() -> None:
    future = datetime(2026, 7, 16, 6, 55, tzinfo=timezone.utc)
    universe = PITUniverseSnapshot(
        universe_id=UniverseId("universe-v1"),
        as_of=AsOfTime(future),
        source_dataset_id=DatasetId("universe-dataset-v1"),
        evidence_artifact_id=ArtifactId("universe-artifact-v1"),
        method_version="pit-universe-v1",
        records=(UniverseMembershipRecord("000001.SZ", True),),
    )
    eligibility = TradingEligibilitySnapshot(
        as_of=AsOfTime(AS_OF),
        source_dataset_id=DatasetId("eligibility-dataset-v1"),
        evidence_artifact_id=ArtifactId("eligibility-artifact-v1"),
        records=(TradingEligibilityRecord("000001.SZ", TradingEligibilityStatus.ELIGIBLE),),
    )

    with pytest.raises(ValueError, match="universe snapshot must not be from the future"):
        build_candidate_population(
            universe,
            eligibility,
            decision_time=DecisionTime(AS_OF),
        )
