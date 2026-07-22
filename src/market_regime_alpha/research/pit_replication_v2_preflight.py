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
    template = preflight_xuntou_replication_v2(None)
    invariant_fields = (
        "schema_version",
        "provider",
        "required_bundle_schema",
        "required_product",
        "expected_source_files",
        "tencent_fallback_allowed",
    )
    if any(getattr(parsed, name) != getattr(template, name) for name in invariant_fields):
        raise ValueError("PIT replication v2 preflight constants mismatch")
    if parsed.status is PITReplicationPreflightStatus.BLOCKED_EXTERNAL_PROVIDER_INPUT:
        if parsed.to_public_dict() != template.to_public_dict():
            raise ValueError("PIT replication v2 blocked preflight is not reconstructible")
    return parsed
