from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.legacy.eligibility_sidecar_adapter import (
    LEGACY_ELIGIBILITY_AVAILABILITY_CONVENTION,
    LegacyEligibilitySidecarAdapterError,
    adapt_legacy_eligibility_mapping,
)


TZ = ZoneInfo("Asia/Shanghai")


def _mapping() -> dict[str, object]:
    return {
        "records": [
            {
                "symbol": "000001.SZ",
                "timestamp": "2026-07-15 14:55:00",
                "is_suspended": False,
                "is_st": False,
                "prev_close": 10.0,
                "limit_up_price": 11.0,
                "limit_down_price": 9.0,
                "limit_regime": "MAIN_BOARD_10PCT",
            }
        ]
    }


def test_legacy_eligibility_adapter_records_timestamp_availability_assumption() -> None:
    observations = adapt_legacy_eligibility_mapping(_mapping())

    assert LEGACY_ELIGIBILITY_AVAILABILITY_CONVENTION == "LEGACY_TIMESTAMP_AVAILABLE_AT_OBSERVATION_TIME"
    assert len(observations) == 1
    observation = observations[0]
    assert observation.symbol == "000001.SZ"
    assert observation.as_of.value == datetime(2026, 7, 15, 14, 55, tzinfo=TZ)
    assert observation.available_at.value == observation.as_of.value
    assert observation.limit_regime == "MAIN_BOARD_10PCT"


def test_legacy_eligibility_adapter_rejects_string_boolean() -> None:
    raw = _mapping()
    raw["records"][0]["is_st"] = "false"  # type: ignore[index]

    with pytest.raises(LegacyEligibilitySidecarAdapterError, match="ELIGIBILITY_BOOLEAN_FIELD_INVALID"):
        adapt_legacy_eligibility_mapping(raw)


def test_legacy_eligibility_adapter_rejects_missing_required_raw_field() -> None:
    raw = _mapping()
    del raw["records"][0]["limit_regime"]  # type: ignore[index]

    with pytest.raises(LegacyEligibilitySidecarAdapterError, match="ELIGIBILITY_RECORD_INVALID"):
        adapt_legacy_eligibility_mapping(raw)


def test_legacy_eligibility_adapter_rejects_none_limit_regime_instead_of_stringifying_it() -> None:
    raw = _mapping()
    raw["records"][0]["limit_regime"] = None  # type: ignore[index]

    with pytest.raises(LegacyEligibilitySidecarAdapterError, match="ELIGIBILITY_LIMIT_REGIME_INVALID"):
        adapt_legacy_eligibility_mapping(raw)


def test_legacy_eligibility_adapter_rejects_duplicate_time_symbol() -> None:
    record = _mapping()["records"][0]  # type: ignore[index]
    raw = {"records": [record, dict(record)]}

    with pytest.raises(LegacyEligibilitySidecarAdapterError, match="ELIGIBILITY_DUPLICATE_TIME_SYMBOL"):
        adapt_legacy_eligibility_mapping(raw)
