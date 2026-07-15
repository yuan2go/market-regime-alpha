from __future__ import annotations

from copy import deepcopy
from math import inf

import pytest

from market_regime_alpha.core.time import DecisionTime
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.research.provider_export_adapter import (
    GenericProviderExportAdapterError,
    adapt_generic_provider_export_mapping,
)
from market_regime_alpha.universe.contracts import TradingEligibilityStatus
from market_regime_alpha.universe.eligibility_policy import (
    r5_provider_rehearsal_trading_eligibility_policy_v2,
)


LIQUIDITY_MEASURE = "AVG_AMOUNT_20D_CNY"


def _bundle() -> dict:
    return {
        "schema_version": "generic-provider-export-bundle-v1",
        "provider_references": [
            {
                "provider_id": "provider-fixture",
                "product": "normalized-export",
                "contract_version": "v1",
            }
        ],
        "source_artifacts": [
            {
                "artifact_id": "source-bars-v1",
                "provider_id": "provider-fixture",
                "retrieved_at": "2026-07-17T09:00:00+08:00",
                "content_hash": "sha256:bars",
                "locator": "file:///exports/bars.csv",
            },
            {
                "artifact_id": "source-eligibility-v1",
                "provider_id": "provider-fixture",
                "retrieved_at": "2026-07-17T09:05:00+08:00",
                "content_hash": "sha256:eligibility",
                "locator": "file:///exports/eligibility.csv",
            },
        ],
        "conventions": {
            "retrieval_convention": "SOURCE_EXPORT_RETRIEVED_AFTER_SAMPLE_WINDOW",
            "market_availability_convention": "PROVIDER_EXPLICIT_AVAILABLE_AT",
            "raw_eligibility_evidence_convention": "PROVIDER_EXPLICIT_AVAILABLE_AT",
            "bar_finality_convention": "DAILY_BAR_FINAL_AFTER_IDENTIFIED_SESSION_CLOSE",
            "price_adjustment_basis": "RAW_TRADABLE_PRICE_FOR_REHEARSAL_BASELINE",
        },
        "pit_correct_for_scope": False,
        "limitations": ["fixture only"],
        "calendar": {
            "source_dataset_id": "dataset-calendar-v1",
            "market": "CN_A_SHARE",
            "calendar_version": "fixture-calendar-v1",
            "timezone_name": "Asia/Shanghai",
            "sessions": [
                {"trade_date": "2026-07-14", "session_close": "2026-07-14T15:00:00+08:00"},
                {"trade_date": "2026-07-15", "session_close": "2026-07-15T15:00:00+08:00"},
                {"trade_date": "2026-07-16", "session_close": "2026-07-16T15:00:00+08:00"},
            ],
        },
        "universe": {
            "source_dataset_id": "dataset-universe-v1",
            "method_version": "fixture-universe-v1",
            "timezone_name": "Asia/Shanghai",
            "effective_time_convention": "AS_OF_DATE_EFFECTIVE_FROM_LOCAL_DAY_START",
            "records": [
                {"as_of_date": "2026-07-15", "symbol": "000001.SZ", "is_member": True},
            ],
        },
        "daily_bars": [
            {
                "symbol": "000001.SZ",
                "session_date": "2026-07-14",
                "close": 9.8,
                "amount": 100000000.0,
                "available_at": "2026-07-14T15:01:00+08:00",
                "finalized": True,
            }
        ],
        "decision_snapshots": [
            {
                "symbol": "000001.SZ",
                "decision_time": "2026-07-15T14:55:00+08:00",
                "reference_price": 10.2,
                "available_at": "2026-07-15T14:55:00+08:00",
            }
        ],
        "next_session_bars": [
            {
                "symbol": "000001.SZ",
                "session_date": "2026-07-16",
                "open": 10.3,
                "high": 10.8,
                "low": 10.0,
                "close": 10.6,
                "available_at": "2026-07-16T15:01:00+08:00",
            }
        ],
        "raw_eligibility_observations": [
            {
                "as_of": "2026-07-15T14:55:00+08:00",
                "available_at": "2026-07-15T14:55:00+08:00",
                "symbol": "000001.SZ",
                "is_suspended": False,
                "is_st": False,
                "prev_close": 10.0,
                "limit_up_price": 11.0,
                "limit_down_price": 9.0,
                "limit_regime": "MAIN_BOARD_10PCT",
                "listing_age_calendar_days": 120,
                "liquidity_value": 80000000.0,
                "liquidity_measure_id": LIQUIDITY_MEASURE,
                "decision_buyability": "BUYABLE",
            }
        ],
    }


def test_generic_provider_export_adapter_builds_rehearsal_artifact_and_v2_eligibility() -> None:
    artifact = adapt_generic_provider_export_mapping(_bundle())
    policy = r5_provider_rehearsal_trading_eligibility_policy_v2(
        minimum_liquidity_value=50_000_000.0,
        liquidity_measure_id=LIQUIDITY_MEASURE,
    )
    eligibility = artifact.materialize_trading_eligibility(policy=policy)
    decision_time = DecisionTime(artifact.decision_times[0].value)

    assert artifact.dataset_contract.eligibility is DataEligibility.REHEARSAL
    assert eligibility.snapshot_for_decision_time(decision_time).status_for("000001.SZ") is TradingEligibilityStatus.ELIGIBLE


def test_source_artifact_order_does_not_change_identity() -> None:
    first = adapt_generic_provider_export_mapping(_bundle())
    reordered = _bundle()
    reordered["source_artifacts"] = list(reversed(reordered["source_artifacts"]))
    second = adapt_generic_provider_export_mapping(reordered)

    assert first.artifact_id == second.artifact_id
    assert first.dataset_contract.dataset_id == second.dataset_contract.dataset_id


def test_missing_explicit_availability_time_is_rejected() -> None:
    raw = _bundle()
    del raw["decision_snapshots"][0]["available_at"]

    with pytest.raises(GenericProviderExportAdapterError):
        adapt_generic_provider_export_mapping(raw)


def test_naive_datetime_is_rejected_instead_of_assuming_timezone() -> None:
    raw = _bundle()
    raw["decision_snapshots"][0]["decision_time"] = "2026-07-15T14:55:00"

    with pytest.raises(GenericProviderExportAdapterError, match="TIMEZONE_REQUIRED"):
        adapt_generic_provider_export_mapping(raw)


def test_unknown_buyability_enum_is_rejected() -> None:
    raw = _bundle()
    raw["raw_eligibility_observations"][0]["decision_buyability"] = "PROBABLY_BUYABLE"

    with pytest.raises(GenericProviderExportAdapterError, match="BUYABILITY_INVALID"):
        adapt_generic_provider_export_mapping(raw)


def test_non_finite_numeric_values_are_rejected() -> None:
    raw = deepcopy(_bundle())
    raw["daily_bars"][0]["close"] = inf

    with pytest.raises(GenericProviderExportAdapterError):
        adapt_generic_provider_export_mapping(raw)
