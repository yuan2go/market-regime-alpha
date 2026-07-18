"""Versioned provider preflight projection for PIT Artifact identity v2."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from market_regime_alpha.research.pit_replication_preflight import (
    PITReplicationPreflight,
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
