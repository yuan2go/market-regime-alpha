"""Shared strict input and structured output helpers for Feature CLI commands."""

from __future__ import annotations

import json
from typing import Mapping


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
