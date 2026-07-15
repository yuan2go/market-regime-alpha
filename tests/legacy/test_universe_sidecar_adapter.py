from __future__ import annotations

from datetime import date

import pytest

from market_regime_alpha.core.identity import DatasetId
from market_regime_alpha.legacy.universe_sidecar_adapter import (
    LEGACY_UNIVERSE_EFFECTIVE_TIME_CONVENTION,
    LegacyUniverseSidecarAdapterError,
    adapt_legacy_universe_mapping,
)


def test_legacy_universe_sidecar_maps_eligible_to_membership_only() -> None:
    artifact = adapt_legacy_universe_mapping(
        {
            "records": [
                {"as_of_date": "2026-07-15", "symbol": "000001.SZ", "eligible": True},
                {"as_of_date": "2026-07-15", "symbol": "000002.SZ", "eligible": False},
                {"as_of_date": "2026-07-16", "symbol": "000001.SZ", "eligible": False},
                {"as_of_date": "2026-07-16", "symbol": "000002.SZ", "eligible": True},
            ]
        },
        source_dataset_id=DatasetId("dataset-legacy-universe-v1"),
        method_version="legacy-universe-sidecar-v1",
    )

    assert artifact.effective_time_convention == LEGACY_UNIVERSE_EFFECTIVE_TIME_CONVENTION
    assert artifact.snapshot_dates == (date(2026, 7, 15), date(2026, 7, 16))
    assert artifact.snapshot_on(date(2026, 7, 15)).member_symbols == ("000001.SZ",)
    assert artifact.snapshot_on(date(2026, 7, 16)).member_symbols == ("000002.SZ",)


def test_legacy_universe_sidecar_requires_historical_as_of_date() -> None:
    with pytest.raises(LegacyUniverseSidecarAdapterError, match="PIT_UNIVERSE_RECORD_INVALID"):
        adapt_legacy_universe_mapping(
            {
                "records": [
                    {"symbol": "000001.SZ", "eligible": True},
                ]
            },
            source_dataset_id=DatasetId("dataset-legacy-universe-v1"),
            method_version="legacy-universe-sidecar-v1",
        )


def test_legacy_universe_sidecar_rejects_string_boolean() -> None:
    with pytest.raises(LegacyUniverseSidecarAdapterError, match="PIT_UNIVERSE_ELIGIBLE_MUST_BE_BOOLEAN"):
        adapt_legacy_universe_mapping(
            {
                "records": [
                    {"as_of_date": "2026-07-15", "symbol": "000001.SZ", "eligible": "true"},
                ]
            },
            source_dataset_id=DatasetId("dataset-legacy-universe-v1"),
            method_version="legacy-universe-sidecar-v1",
        )
