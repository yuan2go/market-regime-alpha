"""Compatibility adapter from legacy MR2A record dictionaries."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.core.time import AvailabilityTime
from market_regime_alpha.research.platform_v2.inputs import MarketObservation


def adapt_mr2a_context_record(
    record: Mapping[str, Any],
    *,
    available_at: datetime,
    source_artifact_id: ArtifactId,
) -> MarketObservation:
    """Project a complete legacy MR2A record into a typed V2 observation."""

    if record.get("data_status") != "AVAILABLE":
        return MarketObservation(
            available_at=AvailabilityTime(available_at),
            source_artifact_id=source_artifact_id,
            market_direction_return=None,
            market_intraday_range_to_cutoff=None,
            market_amount_change_same_cutoff=None,
            candidate_breadth_at_cutoff=None,
            limit_structure_score=None,
            coverage=float(record.get("coverage", 0.0)),
            reason_codes=(
                str(record.get("missing_reason") or "MR2A_CONTEXT_UNAVAILABLE"),
            ),
        )
    return MarketObservation(
        available_at=AvailabilityTime(available_at),
        source_artifact_id=source_artifact_id,
        market_direction_return=float(record["market_direction_return"]),
        market_intraday_range_to_cutoff=float(
            record["market_intraday_range_to_cutoff"]
        ),
        market_amount_change_same_cutoff=float(
            record["market_amount_change_same_cutoff"]
        ),
        candidate_breadth_at_cutoff=float(
            record["candidate_breadth_at_cutoff"]
        ),
        limit_structure_score=None,
        coverage=float(record["coverage"]),
        reason_codes=("LIMIT_STRUCTURE_OBSERVATION_UNAVAILABLE",),
    )

