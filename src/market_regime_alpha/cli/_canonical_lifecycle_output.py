"""Structured JSON and failure recovery output for the lifecycle CLI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
from typing import Any

from market_regime_alpha.application.canonical_lifecycle.repositories import (
    LifecycleRepositoryError,
)
from market_regime_alpha.application.canonical_lifecycle.runner import (
    LifecycleRunResult,
    LifecycleStageExecutionError,
)
from market_regime_alpha.application.canonical_lifecycle.sqlite_repository import (
    SQLiteLifecycleRunRepository,
)
from market_regime_alpha.application.canonical_lifecycle.states import (
    LifecycleRunStatus,
)


def safety_declarations() -> dict[str, bool]:
    return {
        "NO_ORDER_CREATED": True,
        "BROKER_NOT_INVOKED": True,
        "NO_FILL_CREATED": True,
        "automatic_order_execution": False,
        "broker_integration_proven": False,
        "entry_model_empirically_validated": False,
        "production_ready": False,
    }


def result_payload(result: LifecycleRunResult) -> dict[str, Any]:
    manual_trade_observed = any(
        reference.object_type.value == "MANUAL_TRADE"
        for stage in result.stages
        for reference in stage.output_references
    )
    return {
        "run_id": str(result.run.run_id),
        "run_type": result.run.run_type.value,
        "command_hash": result.run.command_hash,
        "status": result.run.status.value,
        "current_stage": (
            result.run.current_stage.value if result.run.current_stage else None
        ),
        "completed_stages": [item.value for item in result.run.completed_stages],
        "stage_statuses": {
            item.stage_name.value: item.stage_status.value for item in result.stages
        },
        "receipt_ids": [str(item.receipt_id) for item in result.receipts],
        "receipt_hashes": [item.receipt_hash for item in result.receipts],
        "attempted_stages": [item.value for item in result.attempted_stages],
        "recovered_stages": [item.value for item in result.recovered_stages],
        "stopped_after_stage": (
            result.stopped_after_stage.value
            if result.stopped_after_stage is not None
            else None
        ),
        "blocker_reason": result.run.blocker_reason,
        "failure_reason": result.run.failure_reason,
        "manual_trade_observed": manual_trade_observed,
        "MANUAL_CONFIRMATION_REQUIRED": (
            result.run.status is LifecycleRunStatus.WAITING_FOR_MANUAL_CONFIRMATION
        ),
        "MANUAL_TRADE_CREATED": False,
        **safety_declarations(),
    }


def print_history_failure(
    repository: SQLiteLifecycleRunRepository,
    exc: LifecycleStageExecutionError,
) -> None:
    try:
        history = repository.history(exc.run_id)
    except (
        LifecycleRepositoryError,
        OSError,
        sqlite3.Error,
        TypeError,
        ValueError,
    ):
        print_error("LIFECYCLE_STAGE_FAILED", exc, args=None)
        return
    payload = {
        "run_id": str(history.run.run_id),
        "run_type": history.run.run_type.value,
        "command_hash": history.run.command_hash,
        "status": history.run.status.value,
        "current_stage": (
            history.run.current_stage.value if history.run.current_stage else None
        ),
        "completed_stages": [item.value for item in history.run.completed_stages],
        "blocker_reason": history.run.blocker_reason,
        "failure_reason": history.run.failure_reason,
        "error": str(exc),
        "reason_codes": ["LIFECYCLE_STAGE_FAILED"],
        "MANUAL_CONFIRMATION_REQUIRED": (
            history.run.status is LifecycleRunStatus.WAITING_FOR_MANUAL_CONFIRMATION
        ),
        "MANUAL_TRADE_CREATED": False,
        **safety_declarations(),
    }
    print(json.dumps(payload, ensure_ascii=True, sort_keys=True))


def print_error(
    reason_code: str,
    exc: Exception,
    *,
    args: argparse.Namespace | None,
) -> None:
    print(
        json.dumps(
            {
                "run_id": (
                    getattr(args, "resume_run_id", None) if args is not None else None
                ),
                "status": "REJECTED",
                "current_stage": None,
                "completed_stages": [],
                "blocker_reason": str(exc),
                "failure_reason": None,
                "error": str(exc),
                "reason_codes": [reason_code],
                "MANUAL_CONFIRMATION_REQUIRED": False,
                "MANUAL_TRADE_CREATED": False,
                **safety_declarations(),
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )


def repository_from_args(
    args: argparse.Namespace | None,
) -> SQLiteLifecycleRunRepository | None:
    if args is None:
        return None
    output_directory = (
        args.output_dir.resolve()
        if args.output_dir is not None
        else Path("artifacts/canonical-lifecycle").resolve()
    )
    database = (
        args.database.resolve()
        if args.database is not None
        else output_directory / "lifecycle-runtime.sqlite3"
    )
    try:
        return SQLiteLifecycleRunRepository(database)
    except (OSError, sqlite3.Error, TypeError, ValueError):
        return None
