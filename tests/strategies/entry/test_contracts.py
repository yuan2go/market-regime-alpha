from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.core.time import AvailabilityTime
from market_regime_alpha.strategies.entry import (
    DAILY_OHLC_OPEN_THEN_UNORDERED_EXTREMES_V1,
    DECISION_TIME_1455_SNAPSHOT_REFERENCE_PRICE_V1,
    ENTRY_PATH_MATERIALIZATION_SCHEMA_VERSION,
    ENTRY_PATH_OBSERVATION_SCHEMA_VERSION,
    ENTRY_PATH_TARGET_SCHEMA_VERSION,
    NEXT_TRADING_SESSION_OPEN_AFTER_DECISION_V1,
    EntryBarrierSpec,
    EntryPathObservation,
    EntryPathObservationStatus,
    EntryPathOutcome,
    EntryPathReasonCode,
    EntryPathTriggerType,
    build_entry_path_target_contract,
)


TZ = ZoneInfo("Asia/Shanghai")
SESSION = date(2026, 7, 20)
OBSERVED_AT = AvailabilityTime(datetime(2026, 7, 20, 15, 5, tzinfo=TZ))


def _spec(**changes: object) -> EntryBarrierSpec:
    values: dict[str, object] = {
        "upper_return": 0.02,
        "lower_return": -0.02,
        "horizon_sessions": 3,
        "price_adjustment_basis": "RAW_UNADJUSTED_TRADABLE_PRICE_V1",
    }
    values.update(changes)
    return EntryBarrierSpec(**values)  # type: ignore[arg-type]


def _observation(**changes: object) -> EntryPathObservation:
    values: dict[str, object] = {
        "symbol": "000001.SZ",
        "status": EntryPathObservationStatus.AVAILABLE,
        "outcome": EntryPathOutcome.UP_FIRST,
        "reference_price": 10.0,
        "upper_price": 10.2,
        "lower_price": 9.8,
        "event_session_date": SESSION,
        "event_session_index": 1,
        "trigger_type": EntryPathTriggerType.OPEN_GAP_UP,
        "evaluated_session_dates": (SESSION,),
        "first_missing_session_date": None,
        "reason_code": EntryPathReasonCode.OUTCOME_RESOLVED,
        "observed_at": OBSERVED_AT,
    }
    values.update(changes)
    return EntryPathObservation(**values)  # type: ignore[arg-type]


def test_target_identity_is_deterministic_over_complete_semantics() -> None:
    first = build_entry_path_target_contract(_spec())
    second = build_entry_path_target_contract(_spec())

    assert first.target_id == second.target_id
    assert first.spec.target_start_convention == NEXT_TRADING_SESSION_OPEN_AFTER_DECISION_V1
    assert (
        first.spec.reference_price_convention
        == DECISION_TIME_1455_SNAPSHOT_REFERENCE_PRICE_V1
    )
    assert (
        first.spec.path_ordering_convention
        == DAILY_OHLC_OPEN_THEN_UNORDERED_EXTREMES_V1
    )
    assert first.spec.schema_version == ENTRY_PATH_TARGET_SCHEMA_VERSION


@pytest.mark.parametrize(
    "changed_spec",
    (
        _spec(upper_return=0.03),
        _spec(lower_return=-0.03),
        _spec(horizon_sessions=4),
        _spec(target_start_convention="NEXT_TRADING_SESSION_OPEN_AFTER_DECISION_V2"),
        _spec(reference_price_convention="DECISION_REFERENCE_PRICE_V2"),
        _spec(path_ordering_convention="ORDERED_INTRADAY_PATH_V2"),
        _spec(price_adjustment_basis="FORWARD_ADJUSTED_V1"),
        _spec(schema_version="entry-path-target-v2"),
    ),
)
def test_target_identity_changes_with_each_semantic_field(
    changed_spec: EntryBarrierSpec,
) -> None:
    assert (
        build_entry_path_target_contract(changed_spec).target_id
        != build_entry_path_target_contract(_spec()).target_id
    )


@pytest.mark.parametrize(
    "changes",
    (
        {"upper_return": 0.0},
        {"lower_return": 0.0},
        {"lower_return": -1.0},
        {"lower_return": -1.01},
        {"horizon_sessions": True},
        {"horizon_sessions": 0},
        {"price_adjustment_basis": ""},
    ),
)
def test_barrier_spec_rejects_invalid_semantics(changes: dict[str, object]) -> None:
    with pytest.raises((TypeError, ValueError)):
        _spec(**changes)


def test_observation_accepts_exact_available_ambiguous_missing_and_pending_states() -> None:
    assert _observation().outcome is EntryPathOutcome.UP_FIRST
    assert (
        _observation(
            status=EntryPathObservationStatus.AMBIGUOUS,
            outcome=None,
            trigger_type=EntryPathTriggerType.INTRADAY_DUAL_TOUCH_UNORDERED,
            reason_code=EntryPathReasonCode.DAILY_BAR_DUAL_TOUCH_ORDER_UNRESOLVED,
        ).status
        is EntryPathObservationStatus.AMBIGUOUS
    )
    assert (
        _observation(
            status=EntryPathObservationStatus.MISSING,
            outcome=None,
            event_session_date=None,
            event_session_index=None,
            trigger_type=None,
            evaluated_session_dates=(),
            first_missing_session_date=SESSION,
            reason_code=EntryPathReasonCode.FUTURE_DAILY_BAR_MISSING,
        ).status
        is EntryPathObservationStatus.MISSING
    )
    assert (
        _observation(
            status=EntryPathObservationStatus.NOT_YET_OBSERVED,
            outcome=None,
            event_session_date=None,
            event_session_index=None,
            trigger_type=None,
            evaluated_session_dates=(),
            reason_code=EntryPathReasonCode.HORIZON_NOT_COMPLETE,
            observed_at=None,
        ).status
        is EntryPathObservationStatus.NOT_YET_OBSERVED
    )


def test_observation_uses_and_enforces_v2_schema() -> None:
    assert _observation().schema_version == ENTRY_PATH_OBSERVATION_SCHEMA_VERSION

    with pytest.raises(ValueError, match="entry-path-observation-v2"):
        _observation(schema_version="entry-path-observation-v1")


def test_v2_public_schema_has_no_unproducible_invalid_state() -> None:
    assert "INVALID" not in EntryPathObservationStatus.__members__
    assert ENTRY_PATH_MATERIALIZATION_SCHEMA_VERSION == "entry-path-materialization-v2"


@pytest.mark.parametrize(
    "invalid",
    (
        {"status": EntryPathObservationStatus.AVAILABLE, "outcome": None},
        {
            "status": EntryPathObservationStatus.AMBIGUOUS,
            "outcome": EntryPathOutcome.UP_FIRST,
        },
        {
            "status": EntryPathObservationStatus.MISSING,
            "outcome": None,
            "event_session_date": None,
            "event_session_index": None,
            "trigger_type": None,
            "first_missing_session_date": None,
        },
        {
            "status": EntryPathObservationStatus.NOT_YET_OBSERVED,
            "outcome": None,
            "event_session_date": None,
            "event_session_index": None,
            "trigger_type": None,
            "observed_at": OBSERVED_AT,
        },
        {"event_session_index": 2},
        {"upper_price": 9.9},
    ),
)
def test_observation_rejects_cross_state_and_audit_mismatches(
    invalid: dict[str, object],
) -> None:
    with pytest.raises((TypeError, ValueError)):
        _observation(**invalid)


def test_observation_rejects_reason_not_permitted_by_status() -> None:
    with pytest.raises(ValueError, match="reason_code"):
        _observation(
            status=EntryPathObservationStatus.MISSING,
            outcome=None,
            event_session_date=None,
            event_session_index=None,
            trigger_type=None,
            evaluated_session_dates=(),
            first_missing_session_date=SESSION,
            reason_code=EntryPathReasonCode.OUTCOME_RESOLVED,
        )


def test_observation_is_immutable() -> None:
    observation = _observation()

    with pytest.raises(Exception):
        replace(observation, symbol="")
