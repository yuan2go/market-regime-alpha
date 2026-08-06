"""Attach verified T+1 facts and settle a Controlled operation."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from market_regime_alpha.application.controlled_operation.runner import (
    ControlledOperationDataBlocked,
    ControlledOperationSettlementInputPaths,
)
from market_regime_alpha.cli._controlled_operation import (
    ControlledCLIError,
    ControlledExitCode,
    StructuredParser,
    add_repository_arguments,
    emit,
    emit_error,
    load_snapshot,
    operation_payload,
    repository_exception,
    runner_and_journal,
)


def build_parser() -> StructuredParser:
    parser = StructuredParser(description=__doc__)
    add_repository_arguments(parser)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--outcome-source-archive", type=Path, required=True)
    parser.add_argument("--outcome-source-manifest", type=Path, required=True)
    parser.add_argument("--outcome-dataset", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    run_id: str | None = None
    repositories = None
    try:
        args = build_parser().parse_args(argv)
        run_id = args.run_id
        runner, journal, repositories = runner_and_journal(args)
        repositories.assert_runtime_binding("CONTROLLED_OPERATION", run_id)
        command = load_snapshot(journal, run_id).command
        result = runner.settle(
            command=command,
            inputs=ControlledOperationSettlementInputPaths(
                outcome_source_archive=args.outcome_source_archive.resolve(),
                outcome_source_manifest=args.outcome_source_manifest.resolve(),
                outcome_dataset=args.outcome_dataset.resolve(),
            ),
        )
        emit(operation_payload(result))
        return ControlledExitCode.SUCCESS
    except ControlledCLIError as exc:
        emit_error(status="FAILED", reason_code="ARGUMENT_ERROR", exc=exc, run_id=run_id)
        return ControlledExitCode.ARGUMENT_ERROR
    except ControlledOperationDataBlocked as exc:
        emit_error(status="DATA_BLOCKED", reason_code=str(exc), exc=exc, run_id=run_id)
        return ControlledExitCode.DATA_BLOCKED
    except Exception as exc:
        emit_error(status="FAILED", reason_code="OUTCOME_SETTLEMENT_FAILED", exc=exc, run_id=run_id)
        if repository_exception(exc):
            return ControlledExitCode.REPOSITORY_ERROR
        return ControlledExitCode.RUN_CONFLICT
    finally:
        if repositories is not None:
            repositories.close()


if __name__ == "__main__":
    raise SystemExit(main())
