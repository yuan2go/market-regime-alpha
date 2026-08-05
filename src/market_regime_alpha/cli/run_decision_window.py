"""Run the time-bounded Controlled 14:55 decision window."""

from __future__ import annotations

import argparse
from typing import Sequence

from market_regime_alpha.application.controlled_operation.runner import (
    ControlledOperationDataBlocked,
)
from market_regime_alpha.application.controlled_operation.policy import (
    default_decision_time_operation_policy,
)
from market_regime_alpha.cli._controlled_operation import (
    ControlledCLIError,
    ControlledExitCode,
    StructuredParser,
    add_repository_arguments,
    emit,
    emit_error,
    frozen_input_paths,
    load_snapshot,
    operation_payload,
    repository_exception,
    repository_paths,
    runner_and_journal,
)


def build_parser() -> argparse.ArgumentParser:
    parser = StructuredParser(description=__doc__)
    add_repository_arguments(parser)
    parser.add_argument("--run-id", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    run_id: str | None = None
    try:
        args = build_parser().parse_args(argv)
        run_id = args.run_id
        runner, journal = runner_and_journal(args)
        output_root, _ = repository_paths(args)
        command = load_snapshot(journal, run_id).command
        result = runner.run_decision_window(
            command=command,
            policy=default_decision_time_operation_policy(),
            inputs=frozen_input_paths(output_root, command.run_id),
        )
        payload = operation_payload(result)
        emit(payload)
        return ControlledExitCode.PARTIAL_PROVIDER_FAILURE if result.minute_coverage.failed_count else ControlledExitCode.SUCCESS
    except ControlledCLIError as exc:
        emit_error(status="FAILED", reason_code="ARGUMENT_ERROR", exc=exc, run_id=run_id)
        return ControlledExitCode.ARGUMENT_ERROR
    except ControlledOperationDataBlocked as exc:
        reason = str(exc)
        status = "DEADLINE_MISSED" if "DEADLINE" in reason else "DATA_BLOCKED"
        emit_error(status=status, reason_code=reason, exc=exc, run_id=run_id)
        if "TOO_EARLY" in reason or "WINDOW_NOT_OPEN" in reason:
            return ControlledExitCode.TOO_EARLY
        if "DEADLINE" in reason or "CUTOFF" in reason:
            return ControlledExitCode.DEADLINE_MISSED
        if "TRADING_CALENDAR" in reason:
            return ControlledExitCode.NON_TRADING_DAY
        return ControlledExitCode.DATA_BLOCKED
    except Exception as exc:
        emit_error(status="FAILED", reason_code="DECISION_WINDOW_FAILED", exc=exc, run_id=run_id)
        if repository_exception(exc):
            return ControlledExitCode.REPOSITORY_ERROR
        return ControlledExitCode.RUN_CONFLICT


if __name__ == "__main__":
    raise SystemExit(main())
