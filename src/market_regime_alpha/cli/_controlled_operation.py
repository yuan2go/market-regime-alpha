"""Shared JSON and repository boundary for Controlled operation CLIs."""

from __future__ import annotations

import argparse
from enum import IntEnum
import json
from typing import Any, NoReturn

import psycopg

from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionUnavailable,
)


class ControlledExitCode(IntEnum):
    SUCCESS = 0
    ARGUMENT_ERROR = 2
    NON_TRADING_DAY = 3
    TOO_EARLY = 4
    DEADLINE_MISSED = 5
    DATA_BLOCKED = 6
    PARTIAL_PROVIDER_FAILURE = 7
    RUN_CONFLICT = 8
    RESUME_REJECTED = 9
    REPLAY_DIVERGENCE = 10
    REPOSITORY_ERROR = 11


class ControlledCLIError(ValueError):
    pass


class StructuredParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise ControlledCLIError(message)


def safety_declarations() -> dict[str, bool]:
    return {
        "NO_ORDER_CREATED": True,
        "BROKER_NOT_INVOKED": True,
        "NO_FILL_CREATED": True,
        "ENTRY_MODEL_EMPIRICALLY_VALIDATED_FALSE": True,
        "FORMAL_OOS_ALPHA_NOT_ESTABLISHED": True,
    }


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=True, sort_keys=True))


def emit_error(
    *,
    status: str,
    reason_code: str,
    exc: Exception,
    run_id: str | None = None,
) -> None:
    emit(
        {
            "status": status,
            "reason_code": reason_code,
            "error": f"{type(exc).__name__}:{exc}",
            "run_id": run_id,
            "limitations": ["CONTROLLED_OPERATION_FAILED_CLOSED"],
            **safety_declarations(),
        }
    )


def repository_exception(exc: Exception) -> bool:
    return isinstance(
        exc,
        (psycopg.Error, PostgresConnectionUnavailable, OSError),
    )
