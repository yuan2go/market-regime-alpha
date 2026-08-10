"""Prepare calendar, Universe, daily data, and static Features."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from market_regime_alpha.application.controlled_operation.runner import (
    ControlledOperationDataBlocked,
)
from market_regime_alpha.application.controlled_operation.policy import (
    default_decision_time_operation_policy,
)
from market_regime_alpha.cli._controlled_operation import (
    ControlledExitCode,
    StructuredParser,
    add_repository_arguments,
    command_from_prepare_args,
    emit,
    emit_error,
    input_paths_from_prepare_args,
    operation_payload,
    repository_exception,
    runner_and_journal,
)


def build_parser() -> argparse.ArgumentParser:
    parser = StructuredParser(description=__doc__)
    add_repository_arguments(parser)
    parser.add_argument("--decision-date", required=True)
    parser.add_argument("--idempotency-key", required=True)
    parser.add_argument("--code-revision", required=True)
    parser.add_argument("--trading-calendar", type=Path, required=True)
    parser.add_argument("--operational-universe", type=Path, required=True)
    parser.add_argument("--daily-source-stage", type=Path, required=True)
    parser.add_argument("--daily-source-manifest", type=Path, required=True)
    parser.add_argument("--supplemental-research-evidence", type=Path, required=True)
    parser.add_argument("--runtime-configuration", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    run_id: str | None = None
    try:
        args = build_parser().parse_args(argv)
        command = command_from_prepare_args(args)
        run_id = str(command.run_id)
        runner, _, repositories = runner_and_journal(args)
        repositories.bind_runtime(
            "CONTROLLED_OPERATION",
            str(command.run_id),
        )
        result = runner.prepare(
            command=command,
            policy=default_decision_time_operation_policy(),
            inputs=input_paths_from_prepare_args(args),
        )
        emit(operation_payload(result))
        return ControlledExitCode.SUCCESS
    except ControlledOperationDataBlocked as exc:
        reason = str(exc)
        emit_error(status="DATA_BLOCKED", reason_code=reason, exc=exc, run_id=run_id)
        return ControlledExitCode.NON_TRADING_DAY if "TRADING_CALENDAR" in reason else ControlledExitCode.DATA_BLOCKED
    except Exception as exc:
        emit_error(status="FAILED", reason_code="PREPARE_FAILED", exc=exc, run_id=run_id)
        if repository_exception(exc):
            return ControlledExitCode.REPOSITORY_ERROR
        return ControlledExitCode.ARGUMENT_ERROR
