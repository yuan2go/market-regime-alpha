"""Owner-derived Feature projection used by Historical Research Panels."""

from __future__ import annotations

from typing import Any, Mapping

from market_regime_alpha.application.historical_corpus.materialization_contracts import (
    HistoricalSessionComponent,
)


def panel_research_features(
    feature: HistoricalSessionComponent,
) -> dict[str, tuple[Mapping[str, Any], ...]]:
    """Project every owner Feature output without recomputing its value."""

    result: dict[str, list[Mapping[str, Any]]] = {}
    for computation in _objects(feature.payload.get("features"), "features"):
        common = {
            "feature_id": str(computation["feature_id"]),
            "timeframe": str(computation["timeframe"]),
            "feature_available_at": str(computation["available_at"]),
            "configuration_id": str(computation["configuration_id"]),
            "configuration_hash": str(computation["configuration_hash"]),
            "limitations": list(computation.get("limitations", [])),
        }
        projected = result.setdefault(str(computation["symbol"]), [])
        for value in _objects(computation.get("values"), "feature values"):
            projected.append(
                {
                    **common,
                    "output_id": str(value["output_id"]),
                    "state": str(value["state"]),
                    "value": value.get("value"),
                    "available_at": str(value["available_at"]),
                    "source_bar_count": int(value["source_bar_count"]),
                    "source_bar_lineage_hash": str(
                        value["source_bar_lineage_hash"]
                    ),
                    "normalized_source_bar_ids": list(
                        value.get("normalized_source_bar_ids", [])
                    ),
                    "normalized_source_bar_hashes": list(
                        value.get("normalized_source_bar_hashes", [])
                    ),
                    "source_event_start": value.get("source_event_start"),
                    "source_event_end": value.get("source_event_end"),
                    "missing_reason_codes": list(
                        value.get("missing_reason_codes", [])
                    ),
                }
            )
    return {
        symbol: tuple(
            sorted(
                values,
                key=lambda item: (
                    str(item["feature_id"]),
                    str(item["output_id"]),
                ),
            )
        )
        for symbol, values in result.items()
    }


def _objects(value: object, name: str) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, Mapping) for item in value
    ):
        raise ValueError(f"Historical {name} must be an object list")
    return tuple(value)


__all__ = ["panel_research_features"]
