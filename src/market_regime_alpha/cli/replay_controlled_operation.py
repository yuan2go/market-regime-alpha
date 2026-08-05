"""Replay one Controlled evidence package entirely offline."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from market_regime_alpha.application.controlled_operation.replay import (
    replay_controlled_operation,
)
from market_regime_alpha.cli._controlled_operation import (
    ControlledCLIError,
    ControlledExitCode,
    StructuredParser,
    emit,
    emit_error,
    repository_exception,
    safety_declarations,
)


def build_parser() -> StructuredParser:
    parser = StructuredParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        report = replay_controlled_operation(args.package.resolve())
        emit({**report.to_canonical_dict(), **safety_declarations()})
        return ControlledExitCode.SUCCESS
    except ControlledCLIError as exc:
        emit_error(status="FAILED", reason_code="ARGUMENT_ERROR", exc=exc)
        return ControlledExitCode.ARGUMENT_ERROR
    except Exception as exc:
        emit_error(status="REPLAY_DIVERGENCE", reason_code="REPLAY_DIVERGENCE", exc=exc)
        if repository_exception(exc):
            return ControlledExitCode.REPOSITORY_ERROR
        return ControlledExitCode.REPLAY_DIVERGENCE


if __name__ == "__main__":
    raise SystemExit(main())
