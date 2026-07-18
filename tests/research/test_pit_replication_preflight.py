import json
from pathlib import Path

from market_regime_alpha.research.pit_replication_preflight import (
    PITReplicationPreflightStatus,
    preflight_xuntou_replication,
)


def test_missing_bundle_is_explicit_external_input_blocker() -> None:
    result = preflight_xuntou_replication(None)
    assert result.status is PITReplicationPreflightStatus.BLOCKED_EXTERNAL_PROVIDER_INPUT
    assert result.provider == "XUNTOU"
    assert result.tencent_fallback_allowed is False
    assert result.required_bundle_schema == "xuntou-p0-native-bundle-v3"
    assert result.prepared is None


def test_current_watchlist_cannot_masquerade_as_pit() -> None:
    result = preflight_xuntou_replication(
        Path("current-watchlist.json"),
        membership_source="CURRENT_WATCHLIST_BACKFILL",
    )
    assert result.status is PITReplicationPreflightStatus.INVALID_PIT_EVIDENCE
    assert "CURRENT_WATCHLIST_BACKFILL_REJECTED" in result.reasons


def test_missing_xuntou_never_selects_tencent_fallback() -> None:
    result = preflight_xuntou_replication(None)
    payload = result.to_public_dict()
    assert payload["provider"] == "XUNTOU"
    assert payload["tencent_fallback_allowed"] is False
    assert "TENCENT" not in json.dumps(payload)
