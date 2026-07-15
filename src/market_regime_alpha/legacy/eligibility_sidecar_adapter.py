"""Compatibility adapter for the existing Legacy historical eligibility sidecar shape.

The Legacy sidecar exposes a timestamp but no separate availability timestamp. This adapter records
the explicit rehearsal-only compatibility assumption that each record is available at its own
observation timestamp. Provider-backed data must supply actual availability semantics instead.
"""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from market_regime_alpha.core.time import AsOfTime, AvailabilityTime
from market_regime_alpha.universe.eligibility_policy import RawTradingEligibilityObservation


LEGACY_ELIGIBILITY_AVAILABILITY_CONVENTION = "LEGACY_TIMESTAMP_AVAILABLE_AT_OBSERVATION_TIME"


class LegacyEligibilitySidecarAdapterError(ValueError):
    """Raised when the existing Legacy eligibility sidecar cannot be adapted truthfully."""


def load_legacy_eligibility_sidecar(
    path: Path,
    *,
    timezone_name: str = "Asia/Shanghai",
) -> tuple[RawTradingEligibilityObservation, ...]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LegacyEligibilitySidecarAdapterError("ELIGIBILITY_SIDECAR_INVALID") from exc
    return adapt_legacy_eligibility_mapping(raw, timezone_name=timezone_name)


def adapt_legacy_eligibility_mapping(
    raw: dict[str, Any],
    *,
    timezone_name: str = "Asia/Shanghai",
) -> tuple[RawTradingEligibilityObservation, ...]:
    if not isinstance(raw, dict):
        raise LegacyEligibilitySidecarAdapterError("ELIGIBILITY_SIDECAR_INVALID")
    rows = raw.get("records")
    if not isinstance(rows, list) or not rows:
        raise LegacyEligibilitySidecarAdapterError("ELIGIBILITY_RECORDS_REQUIRED")

    zone = ZoneInfo(timezone_name)
    observations: list[RawTradingEligibilityObservation] = []
    required = {
        "symbol",
        "timestamp",
        "is_suspended",
        "is_st",
        "prev_close",
        "limit_up_price",
        "limit_down_price",
        "limit_regime",
    }
    for row in rows:
        if not isinstance(row, dict) or not required <= set(row):
            raise LegacyEligibilitySidecarAdapterError("ELIGIBILITY_RECORD_INVALID")
        if not isinstance(row["is_suspended"], bool) or not isinstance(row["is_st"], bool):
            raise LegacyEligibilitySidecarAdapterError("ELIGIBILITY_BOOLEAN_FIELD_INVALID")
        try:
            timestamp = datetime.fromisoformat(str(row["timestamp"]))
        except ValueError as exc:
            raise LegacyEligibilitySidecarAdapterError("ELIGIBILITY_TIMESTAMP_INVALID") from exc
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            timestamp = timestamp.replace(tzinfo=zone)
        else:
            timestamp = timestamp.astimezone(zone)

        try:
            observation = RawTradingEligibilityObservation(
                as_of=AsOfTime(timestamp),
                available_at=AvailabilityTime(timestamp),
                symbol=str(row["symbol"]),
                is_suspended=row["is_suspended"],
                is_st=row["is_st"],
                prev_close=float(row["prev_close"]),
                limit_up_price=float(row["limit_up_price"]),
                limit_down_price=float(row["limit_down_price"]),
                limit_regime=str(row["limit_regime"]),
            )
        except (TypeError, ValueError) as exc:
            raise LegacyEligibilitySidecarAdapterError("ELIGIBILITY_RECORD_INVALID") from exc
        observations.append(observation)

    keys = tuple((observation.as_of.value, observation.symbol) for observation in observations)
    if len(keys) != len(set(keys)):
        raise LegacyEligibilitySidecarAdapterError("ELIGIBILITY_DUPLICATE_TIME_SYMBOL")
    return tuple(sorted(observations, key=lambda observation: (observation.as_of.value, observation.symbol)))
