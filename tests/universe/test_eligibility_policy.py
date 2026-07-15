from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.core.identity import DatasetId
from market_regime_alpha.core.time import AsOfTime, AvailabilityTime, DecisionTime
from market_regime_alpha.universe.artifacts import (
    HistoricalUniverseMembershipRecord,
    build_historical_pit_universe_artifact,
)
from market_regime_alpha.universe.contracts import TradingEligibilityStatus
from market_regime_alpha.universe.eligibility_policy import (
    RawTradingEligibilityObservation,
    TradingEligibilityPolicy,
    TradingEligibilityReason,
    materialize_historical_trading_eligibility,
    r5_rehearsal_trading_eligibility_policy_v1,
)


TZ = ZoneInfo("Asia/Shanghai")
DECISION_AT = datetime(2026, 7, 15, 14, 55, tzinfo=TZ)
UNIVERSE_DATASET_ID = DatasetId("dataset-universe-v1")
ELIGIBILITY_DATASET_ID = DatasetId("dataset-eligibility-raw-v1")


def _universe():
    return build_historical_pit_universe_artifact(
        source_dataset_id=UNIVERSE_DATASET_ID,
        method_version="fixture-universe-v1",
        timezone_name="Asia/Shanghai",
        effective_time_convention="AS_OF_DATE_EFFECTIVE_FROM_LOCAL_DAY_START",
        records=(
            HistoricalUniverseMembershipRecord(date(2026, 7, 15), "000001.SZ", True),
            HistoricalUniverseMembershipRecord(date(2026, 7, 15), "000002.SZ", True),
            HistoricalUniverseMembershipRecord(date(2026, 7, 15), "000003.SZ", True),
            HistoricalUniverseMembershipRecord(date(2026, 7, 15), "000004.SZ", False),
        ),
    )


def _raw(
    symbol: str,
    *,
    available_at: datetime = DECISION_AT,
    is_suspended: bool | None = False,
    is_st: bool | None = False,
    prev_close: float | None = 10.0,
    limit_up_price: float | None = 11.0,
    limit_down_price: float | None = 9.0,
    limit_regime: str | None = "MAIN_BOARD_10PCT",
) -> RawTradingEligibilityObservation:
    return RawTradingEligibilityObservation(
        as_of=AsOfTime(DECISION_AT),
        available_at=AvailabilityTime(available_at),
        symbol=symbol,
        is_suspended=is_suspended,
        is_st=is_st,
        prev_close=prev_close,
        limit_up_price=limit_up_price,
        limit_down_price=limit_down_price,
        limit_regime=limit_regime,
    )


def test_policy_identity_changes_with_result_affecting_configuration() -> None:
    baseline = r5_rehearsal_trading_eligibility_policy_v1()
    include_st = TradingEligibilityPolicy(
        policy_name=baseline.policy_name,
        version=baseline.version,
        exclude_st=False,
        require_prev_close=True,
        require_limit_metadata=True,
    )

    assert baseline.policy_artifact_id != include_st.policy_artifact_id
    assert baseline.policy_version == "r5-rehearsal-trading-eligibility@v1"


def test_hard_ineligibility_evidence_wins_over_other_missing_fields() -> None:
    policy = r5_rehearsal_trading_eligibility_policy_v1()

    status, reasons = policy.evaluate(
        _raw(
            "000001.SZ",
            is_suspended=True,
            is_st=None,
            prev_close=None,
            limit_up_price=None,
            limit_down_price=None,
            limit_regime=None,
        )
    )

    assert status is TradingEligibilityStatus.INELIGIBLE
    assert reasons == (TradingEligibilityReason.SUSPENDED.value,)


def test_missing_required_evidence_is_unknown_not_eligible() -> None:
    policy = r5_rehearsal_trading_eligibility_policy_v1()

    status, reasons = policy.evaluate(
        _raw(
            "000001.SZ",
            limit_regime=None,
        )
    )

    assert status is TradingEligibilityStatus.UNKNOWN
    assert reasons == (TradingEligibilityReason.LIMIT_REGIME_MISSING.value,)


def test_complete_limit_metadata_does_not_create_execution_or_price_limit_exclusion() -> None:
    policy = r5_rehearsal_trading_eligibility_policy_v1()

    status, reasons = policy.evaluate(_raw("000001.SZ"))

    assert status is TradingEligibilityStatus.ELIGIBLE
    assert reasons == ()


def test_materializer_preserves_member_scope_and_explicit_unknown_states() -> None:
    policy = r5_rehearsal_trading_eligibility_policy_v1()
    artifact = materialize_historical_trading_eligibility(
        source_dataset_id=ELIGIBILITY_DATASET_ID,
        universe_artifact=_universe(),
        policy=policy,
        decision_times=(DecisionTime(DECISION_AT),),
        observations=(
            _raw("000001.SZ"),
            _raw("000002.SZ", is_st=True),
            _raw("000004.SZ"),
        ),
    )

    snapshot = artifact.snapshot_for_decision_time(DecisionTime(DECISION_AT))

    assert artifact.policy_version == policy.policy_version
    assert artifact.policy_artifact_id == policy.policy_artifact_id
    assert snapshot.status_for("000001.SZ") is TradingEligibilityStatus.ELIGIBLE
    assert snapshot.status_for("000002.SZ") is TradingEligibilityStatus.INELIGIBLE
    assert snapshot.status_for("000003.SZ") is TradingEligibilityStatus.UNKNOWN
    assert snapshot.status_for("000004.SZ") is TradingEligibilityStatus.UNKNOWN

    records = {record.symbol: record for record in snapshot.records}
    assert records["000002.SZ"].reasons == (TradingEligibilityReason.ST_EXCLUDED.value,)
    assert records["000003.SZ"].reasons == (TradingEligibilityReason.RAW_OBSERVATION_MISSING.value,)
    assert "000004.SZ" not in records


def test_observation_available_after_decision_time_becomes_unknown() -> None:
    policy = r5_rehearsal_trading_eligibility_policy_v1()
    artifact = materialize_historical_trading_eligibility(
        source_dataset_id=ELIGIBILITY_DATASET_ID,
        universe_artifact=_universe(),
        policy=policy,
        decision_times=(DecisionTime(DECISION_AT),),
        observations=(
            _raw("000001.SZ", available_at=DECISION_AT + timedelta(seconds=1)),
            _raw("000002.SZ"),
            _raw("000003.SZ"),
        ),
    )

    snapshot = artifact.snapshot_for_decision_time(DecisionTime(DECISION_AT))
    records = {record.symbol: record for record in snapshot.records}

    assert records["000001.SZ"].status is TradingEligibilityStatus.UNKNOWN
    assert records["000001.SZ"].reasons == (
        TradingEligibilityReason.RAW_OBSERVATION_NOT_AVAILABLE_BY_DECISION_TIME.value,
    )


def test_materializer_rejects_duplicate_exact_time_raw_observation() -> None:
    observation = _raw("000001.SZ")

    with pytest.raises(ValueError, match="unique time-symbol keys"):
        materialize_historical_trading_eligibility(
            source_dataset_id=ELIGIBILITY_DATASET_ID,
            universe_artifact=_universe(),
            policy=r5_rehearsal_trading_eligibility_policy_v1(),
            decision_times=(DecisionTime(DECISION_AT),),
            observations=(observation, observation),
        )
