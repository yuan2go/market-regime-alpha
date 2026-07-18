"""Application facade for PIT replication blocked/invalid evidence v2."""

from __future__ import annotations

from pathlib import Path

from market_regime_alpha.research.pit_replication_v2_artifacts import publish_pit_replication_v2
from market_regime_alpha.research.pit_replication_v2_preflight import preflight_xuntou_replication_v2
from market_regime_alpha.research.pit_replication_v2_protocol import frozen_pit_replication_v2_protocol
from market_regime_alpha.research.pit_replication_v2_reader import load_verified_pit_replication_v2


def run_pit_replication_v2(*, xuntou_bundle: Path | None, output_root: Path) -> Path:
    protocol = frozen_pit_replication_v2_protocol()
    preflight = preflight_xuntou_replication_v2(xuntou_bundle)
    final = publish_pit_replication_v2(
        output_root=output_root,
        protocol=protocol,
        preflight=preflight,
    )
    load_verified_pit_replication_v2(final)
    return final
