"""Resume an expired or failed Controlled operation safely."""

from __future__ import annotations

from typing import Sequence

from market_regime_alpha.application.controlled_operation.policy import (
    default_decision_time_operation_policy,
)
from market_regime_alpha.application.controlled_operation.runner import (
    ControlledOperationDataBlocked,
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


def build_parser() -> StructuredParser:
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
        result = runner.resume(
            command=command,
            policy=default_decision_time_operation_policy(),
            inputs=frozen_input_paths(output_root, command.run_id),
        )
        emit(operation_payload(result))
        return ControlledExitCode.PARTIAL_PROVIDER_FAILURE if result.minute_coverage.failed_count else ControlledExitCode.SUCCESS
    except ControlledCLIError as exc:
        emit_error(status="FAILED", reason_code="ARGUMENT_ERROR", exc=exc, run_id=run_id)
        return ControlledExitCode.ARGUMENT_ERROR
    except ControlledOperationDataBlocked as exc:
        emit_error(status="DATA_BLOCKED", reason_code=str(exc), exc=exc, run_id=run_id)
        return ControlledExitCode.DATA_BLOCKED
    except Exception as exc:
        emit_error(status="RESUME_REJECTED", reason_code="RESUME_REJECTED", exc=exc, run_id=run_id)
        if repository_exception(exc):
            return ControlledExitCode.REPOSITORY_ERROR
        return ControlledExitCode.RESUME_REJECTED


if __name__ == "__main__":
    raise SystemExit(main())
