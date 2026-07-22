"""Versioned provider preflight projection for PIT Artifact identity v2."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping

from market_regime_alpha.research.pit_replication_preflight import (
    PITReplicationPreflight,
    PITReplicationPreflightStatus,
    preflight_xuntou_replication,
)


PIT_REPLICATION_V2_PREFLIGHT_SCHEMA_VERSION = "pit-replication-provider-preflight-v2"
PIT_REPLICATION_V2_PROVIDER_CONTRACTS = {
    "xuntou-p0-native-bundle-v3": (
        "ThinkTrader/XtQuant normalized native export",
        ("xuntou_normalized_native_bundle_v3.json",),
    ),
    "xuntou-pit-validation-bundle-v4": (
        "XTQUANT",
        ("xuntou_pit_validation_bundle_v4.json",),
    ),
}


def preflight_xuntou_replication_v2(
    bundle: Path | None,
    *,
    membership_source: str | None = None,
) -> PITReplicationPreflight:
    return replace(
        preflight_xuntou_replication(bundle, membership_source=membership_source),
        schema_version=PIT_REPLICATION_V2_PREFLIGHT_SCHEMA_VERSION,
    )


def parse_pit_replication_v2_preflight(
    payload: Mapping[str, Any],
) -> PITReplicationPreflight:
    expected_fields = set(PITReplicationPreflight.__dataclass_fields__) - {"prepared"}
    if set(payload) != expected_fields:
        raise ValueError("PIT replication v2 preflight fields mismatch")
    values = dict(payload)
    try:
        values["status"] = PITReplicationPreflightStatus(str(values["status"]))
        values["expected_source_files"] = tuple(values["expected_source_files"])
        values["reasons"] = tuple(values["reasons"])
    except (TypeError, ValueError) as exc:
        raise ValueError("PIT replication v2 preflight values are invalid") from exc
    parsed = PITReplicationPreflight(**values, prepared=None)
    provider_contract = PIT_REPLICATION_V2_PROVIDER_CONTRACTS.get(
        parsed.required_bundle_schema
    )
    if provider_contract is None:
        raise ValueError("PIT replication v2 preflight bundle contract mismatch")
    expected_product, expected_source_files = provider_contract
    if (
        parsed.schema_version != PIT_REPLICATION_V2_PREFLIGHT_SCHEMA_VERSION
        or parsed.provider != "XUNTOU"
        or parsed.required_product != expected_product
        or parsed.expected_source_files != expected_source_files
        or parsed.tencent_fallback_allowed
    ):
        raise ValueError("PIT replication v2 preflight constants mismatch")
    if parsed.status is PITReplicationPreflightStatus.BLOCKED_EXTERNAL_PROVIDER_INPUT:
        source_identity = (
            parsed.bundle_content_hash,
            parsed.provider_artifact_id,
            parsed.provider_dataset_id,
            parsed.membership_source,
        )
        if any(value is not None for value in source_identity):
            raise ValueError("PIT replication v2 blocked preflight is not reconstructible")
    return parsed
