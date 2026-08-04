"""Run or resume the canonical backend lifecycle without execution authority."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys
from typing import NoReturn, Sequence, cast

from market_regime_alpha.application.canonical_lifecycle.commands import (
    CanonicalLifecycleCommand,
)
from market_regime_alpha.application.canonical_lifecycle.contracts import (
    LifecycleRunId,
    parse_utc_second,
)
from market_regime_alpha.application.canonical_lifecycle.input_manifest import (
    CanonicalLifecycleInputManifest,
    CanonicalLifecycleInputManifestReader,
)
from market_regime_alpha.application.canonical_lifecycle.repositories import (
    LifecycleIdempotencyConflict,
    LifecycleRepositoryError,
    LifecycleRunNotFound,
    LifecycleUnsafeResume,
)
from market_regime_alpha.application.canonical_lifecycle.replay import (
    LifecycleReplayStatus,
    verify_lifecycle_replay,
)
from market_regime_alpha.application.canonical_lifecycle.runner import (
    LifecycleRunResult,
    LifecycleStageExecutionError,
)
from market_regime_alpha.application.canonical_lifecycle.runtime_configuration import (
    RuntimeConfigurationReader,
)
from market_regime_alpha.application.canonical_lifecycle.sqlite_repository import (
    SQLiteLifecycleRunRepository,
)
from market_regime_alpha.application.canonical_lifecycle.sqlite_composition import (
    build_sqlite_lifecycle_runner,
)
from market_regime_alpha.application.canonical_lifecycle.states import (
    LifecycleRunStatus,
    LifecycleRunType,
    LifecycleStageName,
)
from market_regime_alpha.cli._canonical_lifecycle_output import (
    print_error,
    print_history_failure,
    repository_from_args,
    result_payload,
    safety_declarations,
)


EXIT_SUCCESS = 0
EXIT_VALIDATION_ERROR = 2
EXIT_IDEMPOTENCY_CONFLICT = 3
EXIT_RESUME_REJECTED = 4
EXIT_STAGE_FAILED = 5
EXIT_REPOSITORY_ERROR = 6
EXIT_REPLAY_NOT_COMPARABLE = 5
EXIT_REPLAY_FAILED = 6


class CLIValidationError(ValueError):
    pass


class CLIResumeRejected(CLIValidationError):
    pass


class _StructuredArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise CLIValidationError(message)


def build_parser() -> argparse.ArgumentParser:
    parser = _StructuredArgumentParser(
        description=(
            "Run the recoverable canonical decision lifecycle. This command never "
            "calls a broker or creates a Fill."
        )
    )
    parser.add_argument("--input-manifest", type=Path)
    parser.add_argument("--decision-date")
    parser.add_argument("--as-of")
    parser.add_argument("--idempotency-key")
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument("--resume-run-id")
    operation.add_argument("--replay-run-id")
    parser.add_argument(
        "--stop-after-stage",
        choices=tuple(item.value for item in LifecycleStageName),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
    )
    parser.add_argument("--database", type=Path)
    parser.add_argument("--authority-database", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args: argparse.Namespace | None = None
    try:
        args = build_parser().parse_args(argv)
        stop_after = (
            LifecycleStageName(args.stop_after_stage)
            if args.stop_after_stage is not None
            else None
        )
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
        if args.replay_run_id is not None:
            return _replay(args=args, database=database)
        if args.resume_run_id is not None:
            result = _resume(
                args=args,
                database=database,
                stop_after_stage=stop_after,
                requested_output_directory=(
                    args.output_dir.resolve()
                    if args.output_dir is not None
                    else None
                ),
            )
        else:
            result = _start(
                args=args,
                database=database,
                stop_after_stage=stop_after,
                output_directory=output_directory,
            )
    except CLIResumeRejected as exc:
        print_error("LIFECYCLE_RESUME_REJECTED", exc, args=args)
        return EXIT_RESUME_REJECTED
    except CLIValidationError as exc:
        print_error("COMMAND_VALIDATION_FAILED", exc, args=args)
        return EXIT_VALIDATION_ERROR
    except LifecycleIdempotencyConflict as exc:
        print_error("IDEMPOTENCY_KEY_CONFLICT", exc, args=args)
        return EXIT_IDEMPOTENCY_CONFLICT
    except (LifecycleRunNotFound, LifecycleUnsafeResume) as exc:
        print_error("LIFECYCLE_RESUME_REJECTED", exc, args=args)
        return EXIT_RESUME_REJECTED
    except LifecycleStageExecutionError as exc:
        repository = repository_from_args(args)
        if repository is None:
            print_error("LIFECYCLE_STAGE_FAILED", exc, args=args)
        else:
            print_history_failure(repository, exc)
        return EXIT_STAGE_FAILED
    except (LifecycleRepositoryError, sqlite3.Error) as exc:
        print_error("LIFECYCLE_REPOSITORY_ERROR", exc, args=args)
        return EXIT_REPOSITORY_ERROR
    except (OSError, TypeError, ValueError) as exc:
        print_error("COMMAND_VALIDATION_FAILED", exc, args=args)
        return EXIT_VALIDATION_ERROR

    print(json.dumps(result_payload(result), ensure_ascii=True, sort_keys=True))
    return (
        EXIT_STAGE_FAILED
        if result.run.status is LifecycleRunStatus.FAILED
        else EXIT_SUCCESS
    )


def _replay(*, args: argparse.Namespace, database: Path) -> int:
    forbidden = tuple(
        name
        for name in (
            "input_manifest",
            "decision_date",
            "as_of",
            "idempotency_key",
            "authority_database",
            "stop_after_stage",
        )
        if getattr(args, name) is not None
    )
    if forbidden:
        raise CLIValidationError(
            "--replay-run-id cannot be combined with "
            + ", ".join(f"--{name.replace('_', '-')}" for name in forbidden)
        )
    if not database.is_file():
        raise CLIValidationError("replay requires an existing lifecycle database")
    repository = _repository(database)
    run_id = LifecycleRunId(str(args.replay_run_id))
    first = verify_lifecycle_replay(repository=repository, run_id=run_id)
    second = verify_lifecycle_replay(repository=repository, run_id=run_id)
    stable = (
        first.report_hash == second.report_hash
        and first.to_canonical_dict() == second.to_canonical_dict()
    )
    if not stable:
        raise CLIValidationError(
            "read-only replay report changed between identical reads"
        )
    print(
        json.dumps(
            {
                **first.to_canonical_dict(),
                "replay_status": first.status.value,
                "REPORT_HASH_STABLE": True,
                "RUNNER_INVOKED": False,
                "MANUAL_CONFIRMATION_REQUIRED": False,
                "MANUAL_TRADE_CREATED": False,
                **safety_declarations(),
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    return {
        LifecycleReplayStatus.STABLE: EXIT_SUCCESS,
        LifecycleReplayStatus.NOT_COMPARABLE: EXIT_REPLAY_NOT_COMPARABLE,
        LifecycleReplayStatus.FAILED: EXIT_REPLAY_FAILED,
    }[first.status]


def _start(
    *,
    args: argparse.Namespace,
    database: Path,
    stop_after_stage: LifecycleStageName | None,
    output_directory: Path,
) -> LifecycleRunResult:
    missing = tuple(
        name
        for name in ("input_manifest", "decision_date", "as_of", "idempotency_key")
        if getattr(args, name) is None
    )
    if missing:
        raise CLIValidationError(
            "new run requires " + ", ".join(f"--{name.replace('_', '-')}" for name in missing)
        )
    if (
        args.authority_database is not None
        and not args.authority_database.resolve().is_file()
    ):
        raise CLIValidationError(
            "authority database must be an existing explicitly supplied file"
        )
    manifest_path = cast(Path, args.input_manifest).resolve()
    manifest = CanonicalLifecycleInputManifestReader().read(manifest_path)
    decision_date = _date(str(args.decision_date))
    as_of_time = parse_utc_second("as_of", args.as_of)
    if manifest.decision_date != decision_date or manifest.as_of_time != as_of_time:
        raise CLIValidationError(
            "command decision date and as-of must exactly match the input manifest"
        )
    configurations = RuntimeConfigurationReader().read_all(
        manifest.configuration_references
    )
    command = CanonicalLifecycleCommand(
        run_type=LifecycleRunType.CANONICAL_DECISION_LIFECYCLE,
        decision_date=decision_date,
        as_of_time=as_of_time,
        idempotency_key=str(args.idempotency_key),
        input_manifest_id=manifest.manifest_id,
        input_content_hash=manifest.content_hash,
        input_manifest_locator=manifest_path,
        input_references=manifest.input_references,
        configuration_references=manifest.configuration_references,
        model_references=manifest.model_references,
        stop_after_stage=stop_after_stage,
        output_directory=output_directory,
        authority_database_locator=(
            args.authority_database.resolve()
            if args.authority_database is not None
            else None
        ),
    )
    repository = _repository(database)
    runner = build_sqlite_lifecycle_runner(
        repository=repository,
        command=command,
        manifest=manifest,
        configurations=configurations,
        clock=_utc_now,
    )
    return runner.run(command)


def _resume(
    *,
    args: argparse.Namespace,
    database: Path,
    stop_after_stage: LifecycleStageName | None,
    requested_output_directory: Path | None,
) -> LifecycleRunResult:
    forbidden = tuple(
        name
        for name in ("input_manifest", "decision_date", "as_of", "idempotency_key")
        if getattr(args, name) is not None
    )
    if forbidden:
        raise CLIValidationError(
            "--resume-run-id cannot be combined with "
            + ", ".join(f"--{name.replace('_', '-')}" for name in forbidden)
        )
    if not database.is_file():
        raise CLIResumeRejected("resume requires an existing lifecycle database")
    repository = _repository(database)
    run_id = LifecycleRunId(str(args.resume_run_id))
    command = repository.get_command(run_id)
    requested_authority = (
        args.authority_database.resolve()
        if args.authority_database is not None
        else None
    )
    if (
        requested_authority is not None
        and requested_authority != command.authority_database_locator
    ):
        raise CLIResumeRejected(
            "resume authority database must match the stored command binding"
        )
    if (
        command.authority_database_locator is not None
        and not command.authority_database_locator.is_file()
    ):
        raise CLIResumeRejected(
            "stored authority database binding is no longer available"
        )
    if (
        requested_output_directory is not None
        and requested_output_directory != command.output_directory
    ):
        raise CLIResumeRejected(
            "resume output directory must match the stored command"
        )
    try:
        manifest = _restore_command_manifest(command)
        configurations = RuntimeConfigurationReader().read_all(
            command.configuration_references
        )
    except (OSError, TypeError, ValueError) as exc:
        raise CLIResumeRejected(
            "stored resume inputs no longer reconstruct the original command"
        ) from exc
    runner = build_sqlite_lifecycle_runner(
        repository=repository,
        command=command,
        manifest=manifest,
        configurations=configurations,
        clock=_utc_now,
    )
    return runner.resume(run_id, stop_after_stage=stop_after_stage)


def _restore_command_manifest(
    command: CanonicalLifecycleCommand,
) -> CanonicalLifecycleInputManifest | None:
    if command.input_manifest_locator is None:
        return None
    if command.input_manifest_id is None or command.input_content_hash is None:
        raise CLIValidationError("stored command has an incomplete input manifest binding")
    manifest = CanonicalLifecycleInputManifestReader().read(
        command.input_manifest_locator,
        expected_manifest_id=command.input_manifest_id,
        expected_content_hash=command.input_content_hash,
    )
    if (
        manifest.input_references != command.input_references
        or manifest.configuration_references != command.configuration_references
        or manifest.model_references != command.model_references
    ):
        raise CLIValidationError(
            "stored input manifest no longer reconstructs the lifecycle command"
        )
    return manifest


def _date(value: str) -> date:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise CLIValidationError("decision date must be an ISO date") from exc
    if parsed.isoformat() != value:
        raise CLIValidationError("decision date is not canonical")
    return parsed


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _repository(database: Path) -> SQLiteLifecycleRunRepository:
    try:
        return SQLiteLifecycleRunRepository(database)
    except LifecycleRepositoryError:
        raise
    except (OSError, sqlite3.Error) as exc:
        raise LifecycleRepositoryError(
            "lifecycle repository could not be opened or migrated"
        ) from exc


if __name__ == "__main__":
    sys.exit(main())
