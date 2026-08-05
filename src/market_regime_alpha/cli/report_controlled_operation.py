"""Report one Controlled operation without changing repository state."""

from __future__ import annotations

from typing import Sequence

from market_regime_alpha.application.controlled_operation.evidence_package import (
    load_controlled_operation_package,
)
from market_regime_alpha.cli._controlled_operation import (
    ControlledExitCode,
    StructuredParser,
    add_repository_arguments,
    emit,
    emit_error,
    load_snapshot,
    repository_exception,
    repository_paths,
    runner_and_journal,
    safety_declarations,
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
        _, journal = runner_and_journal(args)
        output_root, _ = repository_paths(args)
        snapshot = load_snapshot(journal, run_id)
        package_root = output_root / run_id / "operation-packages"
        packages = (
            tuple(
                load_controlled_operation_package(path)
                for path in sorted(package_root.iterdir())
                if path.is_dir() and not path.name.startswith(".")
            )
            if package_root.is_dir()
            else ()
        )
        current = next(
            (item for item in packages if item.status.value == "SETTLED"),
            next(
                (item for item in packages if item.status.value == "OUTCOME_PENDING"),
                packages[-1] if packages else None,
            ),
        )
        command = snapshot.command
        emit(
            {
                "status": snapshot.status.value,
                "run_id": str(command.run_id),
                "decision_date": command.decision_date.isoformat(),
                "decision_time": command.decision_time.isoformat().replace("+00:00", "Z"),
                "deadline_status": current.deadline_status if current else "NOT_AVAILABLE",
                "universe_count": current.universe_count if current else 0,
                "candidate_count": current.candidate_count if current else 0,
                "minute_success_count": current.minute_success_count if current else 0,
                "minute_failure_count": current.minute_failure_count if current else 0,
                "signal_state_counts": dict(current.signal_state_counts) if current else {},
                "package_id": str(current.package_id) if current else None,
                "package_hash": current.content_hash if current else None,
                "outcome_status": current.status.value if current else snapshot.status.value,
                "limitations": list(current.limitations if current else command.limitations),
                "stage_statuses": {item.stage_name.value: item.status.value for item in snapshot.stages},
                **safety_declarations(),
            }
        )
        return ControlledExitCode.SUCCESS
    except Exception as exc:
        emit_error(status="FAILED", reason_code="REPORT_FAILED", exc=exc, run_id=run_id)
        if repository_exception(exc):
            return ControlledExitCode.REPOSITORY_ERROR
        return ControlledExitCode.ARGUMENT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
