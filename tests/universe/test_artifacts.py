from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.core.identity import DatasetId
from market_regime_alpha.core.time import DecisionTime
from market_regime_alpha.universe.artifacts import (
    HistoricalUniverseMembershipRecord,
    build_historical_pit_universe_artifact,
)


TZ = ZoneInfo("Asia/Shanghai")
SOURCE_DATASET_ID = DatasetId("dataset-pit-universe-v1")
EFFECTIVE_TIME_CONVENTION = "AS_OF_DATE_EFFECTIVE_FROM_LOCAL_DAY_START"


def test_historical_pit_universe_resolves_exact_decision_date_and_allows_membership_change() -> None:
    artifact = build_historical_pit_universe_artifact(
        source_dataset_id=SOURCE_DATASET_ID,
        method_version="fixture-universe-v1",
        timezone_name="Asia/Shanghai",
        effective_time_convention=EFFECTIVE_TIME_CONVENTION,
        records=(
            HistoricalUniverseMembershipRecord(date(2026, 7, 15), "000001.SZ", True),
            HistoricalUniverseMembershipRecord(date(2026, 7, 15), "000002.SZ", True),
            HistoricalUniverseMembershipRecord(date(2026, 7, 16), "000001.SZ", False),
            HistoricalUniverseMembershipRecord(date(2026, 7, 16), "000002.SZ", True),
            HistoricalUniverseMembershipRecord(date(2026, 7, 16), "000003.SZ", True),
        ),
    )

    first = artifact.snapshot_for_decision_time(
        DecisionTime(datetime(2026, 7, 15, 14, 55, tzinfo=TZ))
    )
    second = artifact.snapshot_for_decision_time(
        DecisionTime(datetime(2026, 7, 16, 14, 55, tzinfo=TZ))
    )

    assert artifact.effective_time_convention == EFFECTIVE_TIME_CONVENTION
    assert first.member_symbols == ("000001.SZ", "000002.SZ")
    assert second.member_symbols == ("000002.SZ", "000003.SZ")
    assert first.universe_id != second.universe_id
    assert first.evidence_artifact_id == artifact.artifact_id
    assert second.evidence_artifact_id == artifact.artifact_id


def test_historical_pit_universe_does_not_carry_forward_missing_date() -> None:
    artifact = build_historical_pit_universe_artifact(
        source_dataset_id=SOURCE_DATASET_ID,
        method_version="fixture-universe-v1",
        timezone_name="Asia/Shanghai",
        effective_time_convention=EFFECTIVE_TIME_CONVENTION,
        records=(
            HistoricalUniverseMembershipRecord(date(2026, 7, 15), "000001.SZ", True),
            HistoricalUniverseMembershipRecord(date(2026, 7, 17), "000001.SZ", True),
        ),
    )

    with pytest.raises(KeyError):
        artifact.snapshot_for_decision_time(
            DecisionTime(datetime(2026, 7, 16, 14, 55, tzinfo=TZ))
        )


def test_historical_pit_universe_identity_is_stable_under_record_ordering() -> None:
    records = (
        HistoricalUniverseMembershipRecord(date(2026, 7, 15), "000001.SZ", True),
        HistoricalUniverseMembershipRecord(date(2026, 7, 15), "000002.SZ", False),
    )
    first = build_historical_pit_universe_artifact(
        source_dataset_id=SOURCE_DATASET_ID,
        method_version="fixture-universe-v1",
        timezone_name="Asia/Shanghai",
        effective_time_convention=EFFECTIVE_TIME_CONVENTION,
        records=records,
    )
    second = build_historical_pit_universe_artifact(
        source_dataset_id=SOURCE_DATASET_ID,
        method_version="fixture-universe-v1",
        timezone_name="Asia/Shanghai",
        effective_time_convention=EFFECTIVE_TIME_CONVENTION,
        records=tuple(reversed(records)),
    )

    assert first.artifact_id == second.artifact_id
    assert first.snapshots == second.snapshots


def test_historical_pit_universe_identity_changes_with_effective_time_convention() -> None:
    records = (
        HistoricalUniverseMembershipRecord(date(2026, 7, 15), "000001.SZ", True),
    )
    first = build_historical_pit_universe_artifact(
        source_dataset_id=SOURCE_DATASET_ID,
        method_version="fixture-universe-v1",
        timezone_name="Asia/Shanghai",
        effective_time_convention="AS_OF_DATE_EFFECTIVE_FROM_LOCAL_DAY_START",
        records=records,
    )
    second = build_historical_pit_universe_artifact(
        source_dataset_id=SOURCE_DATASET_ID,
        method_version="fixture-universe-v1",
        timezone_name="Asia/Shanghai",
        effective_time_convention="AS_OF_DATE_EFFECTIVE_FROM_SESSION_OPEN",
        records=records,
    )

    assert first.artifact_id != second.artifact_id
    assert first.snapshots[0].universe_id != second.snapshots[0].universe_id


def test_historical_pit_universe_rejects_duplicate_date_symbol_key() -> None:
    with pytest.raises(ValueError, match="unique date-symbol keys"):
        build_historical_pit_universe_artifact(
            source_dataset_id=SOURCE_DATASET_ID,
            method_version="fixture-universe-v1",
            timezone_name="Asia/Shanghai",
            effective_time_convention=EFFECTIVE_TIME_CONVENTION,
            records=(
                HistoricalUniverseMembershipRecord(date(2026, 7, 15), "000001.SZ", True),
                HistoricalUniverseMembershipRecord(date(2026, 7, 15), "000001.SZ", False),
            ),
        )
