"""Shared strict input and structured output helpers for Feature CLI commands."""

from __future__ import annotations

from datetime import date
import json
from pathlib import Path
from typing import Any, Mapping

from market_regime_alpha.evidence.canonical import canonical_json
from market_regime_alpha.features.spine import FeatureSetConfiguration
from market_regime_alpha.market_data.contracts import parse_utc_second


EXIT_SUCCESS = 0
EXIT_ARGUMENT_ERROR = 2
EXIT_INPUT_TAMPERED = 3
EXIT_DATA_INSUFFICIENT = 4
EXIT_COMPUTATION_FAILED = 5
EXIT_CANONICAL_REGRESSION = 6
EXIT_IO_ERROR = 7
EXIT_PARTIAL_COVERAGE = 8


def safety_declarations() -> dict[str, object]:
    return {
        "NO_ORDER_CREATED": True,
        "BROKER_NOT_INVOKED": True,
        "NO_FILL_CREATED": True,
        "TRADING_AUTHORITY_NOT_GRANTED": True,
        "automatic_order_execution": False,
        "broker_integration_proven": False,
        "entry_model_empirically_validated": False,
        "formal_oos_alpha": False,
        "production_ready": False,
    }


def emit(payload: Mapping[str, object]) -> None:
    print(json.dumps({**payload, **safety_declarations()}, ensure_ascii=True, sort_keys=True))


def emit_error(*, status: str, reason_code: str, error: Exception) -> None:
    emit(
        {
            "status": status,
            "reason_codes": [reason_code],
            "error": str(error),
        }
    )


def read_canonical_object(path: Path, label: str) -> dict[str, Any]:
    try:
        raw = path.resolve().read_bytes()
        payload = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    canonical = canonical_json(payload).encode("utf-8")
    if raw.rstrip(b"\n") != canonical:
        raise ValueError(f"{label} is not canonical JSON")
    return payload


def load_feature_set(path: Path) -> FeatureSetConfiguration:
    return FeatureSetConfiguration.from_canonical_dict(
        read_canonical_object(path, "Feature Set Configuration")
    )


def parse_symbols(raw_symbols: list[str] | None) -> tuple[str, ...]:
    if not raw_symbols:
        raise ValueError("at least one --symbols value is required")
    values = tuple(
        sorted(
            {
                item.strip()
                for group in raw_symbols
                for item in group.split(",")
                if item.strip()
            }
        )
    )
    if not values:
        raise ValueError("selected symbols cannot be empty")
    return values


def require_decision_scope(*, decision_date: str, as_of: str) -> tuple[date, Any]:
    try:
        parsed_date = date.fromisoformat(decision_date)
    except ValueError as exc:
        raise ValueError("decision date must use YYYY-MM-DD") from exc
    parsed_time = parse_utc_second("as_of", as_of)
    if parsed_time.date() != parsed_date:
        raise ValueError("decision date must equal the UTC as-of date")
    return parsed_date, parsed_time


__all__ = [
    "EXIT_ARGUMENT_ERROR",
    "EXIT_CANONICAL_REGRESSION",
    "EXIT_COMPUTATION_FAILED",
    "EXIT_DATA_INSUFFICIENT",
    "EXIT_INPUT_TAMPERED",
    "EXIT_IO_ERROR",
    "EXIT_PARTIAL_COVERAGE",
    "EXIT_SUCCESS",
    "emit",
    "emit_error",
    "load_feature_set",
    "parse_symbols",
    "read_canonical_object",
    "require_decision_scope",
    "safety_declarations",
]
