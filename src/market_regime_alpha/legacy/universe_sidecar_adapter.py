"""Compatibility adapter from the existing Legacy historical universe sidecar shape.

The Legacy sidecar field ``eligible`` is interpreted only as membership under that sidecar's
own universe method. It is not promoted to canonical Trading Eligibility.

The Legacy sidecar provides date-level ``as_of_date`` records but no separate availability or
effective timestamp. This adapter therefore records an explicit rehearsal compatibility
assumption rather than silently treating the convention as universal provider truth.
"""

from __future__ import annotations

from datetime import date
import json
from pathlib import Path
from typing import Any

from market_regime_alpha.core.identity import DatasetId
from market_regime_alpha.universe.artifacts import (
    HistoricalPITUniverseArtifact,
    HistoricalUniverseMembershipRecord,
    build_historical_pit_universe_artifact,
)


LEGACY_UNIVERSE_EFFECTIVE_TIME_CONVENTION = "LEGACY_AS_OF_DATE_EFFECTIVE_FROM_LOCAL_DAY_START"


class LegacyUniverseSidecarAdapterError(ValueError):
    """Raised when the existing sidecar cannot be adapted truthfully."""


def load_legacy_universe_sidecar(
    path: Path,
    *,
    source_dataset_id: DatasetId,
    method_version: str,
    timezone_name: str = "Asia/Shanghai",
) -> HistoricalPITUniverseArtifact:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LegacyUniverseSidecarAdapterError("PIT_UNIVERSE_INVALID") from exc
    return adapt_legacy_universe_mapping(
        raw,
        source_dataset_id=source_dataset_id,
        method_version=method_version,
        timezone_name=timezone_name,
    )


def adapt_legacy_universe_mapping(
    raw: dict[str, Any],
    *,
    source_dataset_id: DatasetId,
    method_version: str,
    timezone_name: str = "Asia/Shanghai",
) -> HistoricalPITUniverseArtifact:
    if not isinstance(raw, dict):
        raise LegacyUniverseSidecarAdapterError("PIT_UNIVERSE_INVALID")
    rows = raw.get("records")
    if not isinstance(rows, list) or not rows:
        raise LegacyUniverseSidecarAdapterError("PIT_UNIVERSE_RECORDS_REQUIRED")

    records: list[HistoricalUniverseMembershipRecord] = []
    for row in rows:
        if not isinstance(row, dict):
            raise LegacyUniverseSidecarAdapterError("PIT_UNIVERSE_RECORD_INVALID")
        required = {"as_of_date", "symbol", "eligible"}
        if not required <= set(row):
            raise LegacyUniverseSidecarAdapterError("PIT_UNIVERSE_RECORD_INVALID")
        if not isinstance(row["eligible"], bool):
            raise LegacyUniverseSidecarAdapterError("PIT_UNIVERSE_ELIGIBLE_MUST_BE_BOOLEAN")
        try:
            as_of_date = date.fromisoformat(str(row["as_of_date"]))
        except ValueError as exc:
            raise LegacyUniverseSidecarAdapterError("PIT_UNIVERSE_AS_OF_DATE_INVALID") from exc
        records.append(
            HistoricalUniverseMembershipRecord(
                as_of_date=as_of_date,
                symbol=str(row["symbol"]),
                is_member=row["eligible"],
            )
        )

    return build_historical_pit_universe_artifact(
        source_dataset_id=source_dataset_id,
        method_version=method_version,
        timezone_name=timezone_name,
        effective_time_convention=LEGACY_UNIVERSE_EFFECTIVE_TIME_CONVENTION,
        records=tuple(records),
    )
