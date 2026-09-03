"""Small `mra` command tree over the sole target composition root."""

from __future__ import annotations

import argparse
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timedelta
from enum import Enum
from io import TextIOBase
import json
import os
from pathlib import Path
import sys
from typing import Mapping, Sequence
from uuid import UUID

import psycopg

from market_regime_alpha.bootstrap import (
    TargetSettings,
    apply_operational_database_upgrade,
    apply_database_recreate,
    bootstrap_application,
    bootstrap_database,
    load_operational_upgrade_plan,
    load_recreate_plan,
    make_operational_upgrade_authorization,
    make_recreate_authorization,
    plan_operational_database_upgrade,
    plan_database_recreate,
    verify_database,
)
from market_regime_alpha.shared.errors import MraError
from market_regime_alpha.interfaces.archive import (
    archive_report,
    load_archive_manifest,
    predeclare_prospective_runtime,
    require_isolated_operational_target,
    resume_archive,
    run_due_prospective_runtime,
    start_archive,
)
from market_regime_alpha.interfaces.backtest import load_backtest_specification
from market_regime_alpha.market.application import compile_prospective_runtime_plan
from market_regime_alpha.runtime.application import ActorType, CommandContext


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    stdout: TextIOBase | None = None,
    stderr: TextIOBase | None = None,
) -> int:
    output = sys.stdout if stdout is None else stdout
    error_output = sys.stderr if stderr is None else stderr
    try:
        arguments = _parser().parse_args(argv)
        settings = TargetSettings.from_environ(os.environ if environ is None else environ)
        payload = _dispatch(arguments, settings)
        output.write(json.dumps(_json_value(payload), sort_keys=True) + "\n")
        return 0
    except (MraError, ValueError, OSError, psycopg.Error) as exc:
        error_output.write(
            json.dumps(
                {"error_type": type(exc).__name__, "message": str(exc)},
                sort_keys=True,
            )
            + "\n"
        )
        return 2


def _dispatch(arguments: argparse.Namespace, settings: TargetSettings) -> object:
    if arguments.area == "db":
        if arguments.db_command == "bootstrap":
            return bootstrap_database(settings)
        if arguments.db_command == "verify":
            return verify_database(settings)
        if arguments.db_command == "recreate-plan":
            recreate_plan = plan_database_recreate(
                settings,
                make_recreate_authorization(
                    expected_database_name=arguments.expected_database_name,
                    expected_database_oid=arguments.expected_database_oid,
                    operator_id=arguments.operator_id,
                    reason=arguments.reason,
                    backup_attestation=arguments.backup_attestation,
                ),
            )
            if arguments.output is not None:
                arguments.output.write_text(recreate_plan.to_json(), encoding="utf-8")
            return recreate_plan
        if arguments.db_command == "recreate-apply":
            recreate_plan = load_recreate_plan(arguments.plan.read_text(encoding="utf-8"))
            return apply_database_recreate(
                settings,
                recreate_plan,
                challenge=arguments.challenge,
                operator_id=arguments.operator_id,
            )
        if arguments.db_command == "upgrade-plan":
            upgrade_plan = plan_operational_database_upgrade(
                settings,
                make_operational_upgrade_authorization(
                    expected_database_name=arguments.expected_database_name,
                    expected_database_oid=arguments.expected_database_oid,
                    operator_id=arguments.operator_id,
                    reason=arguments.reason,
                    backup_path=arguments.backup,
                    backup_sha256=arguments.backup_sha256,
                    backup_size_bytes=arguments.backup_size_bytes,
                    minimum_free_bytes=arguments.minimum_free_bytes,
                    code_sha=arguments.code_sha,
                ),
            )
            if arguments.output is not None:
                arguments.output.write_text(upgrade_plan.to_json(), encoding="utf-8")
            return upgrade_plan
        if arguments.db_command == "upgrade-apply":
            upgrade_plan = load_operational_upgrade_plan(arguments.plan.read_text(encoding="utf-8"))
            return apply_operational_database_upgrade(
                settings,
                upgrade_plan,
                challenge=arguments.challenge,
                operator_id=arguments.operator_id,
            )
    if arguments.area == "runtime":
        with bootstrap_application(settings) as application:
            if arguments.runtime_command == "inspect":
                return application.runtime.inspect_run(arguments.run_id)
            if arguments.runtime_command == "recover":
                recovered = application.runtime.recover_expired(
                    actor_id=arguments.actor_id,
                    reason_code="LEASE_EXPIRED",
                )
                return {"recovered_attempt_ids": recovered}
    if arguments.area == "backtest":
        with bootstrap_application(settings) as application:
            command = arguments.backtest_command
            if command in {"validate", "plan", "predeclare"}:
                specification = load_backtest_specification(arguments.specification)
                if command == "validate":
                    return application.backtests.validate(specification)
                if command == "plan":
                    return application.backtests.plan(specification)
                return application.backtests.predeclare(
                    specification,
                    _backtest_context(arguments, "PREDECLARE_BACKTEST"),
                )
            if command in {"run", "resume", "inspect"}:
                run = application.backtest_specifications.load(arguments.run_id)
                if command == "run":
                    return application.backtest_execution.run(run)
                if command == "resume":
                    return application.backtest_execution.resume(run)
                return application.backtest_execution.inspect(run)
            if command == "replay":
                return application.backtest_replay.verify(arguments.run_id)
            if command == "report":
                if arguments.format == "markdown":
                    return {
                        "format": "markdown",
                        "content": application.backtest_reports.render_markdown(arguments.run_id).decode("utf-8"),
                    }
                return application.backtest_reports.project(arguments.run_id)
            if command == "publish-report":
                return application.backtest_reports.publish(
                    arguments.run_id,
                    artifacts=application.artifacts,
                    bindings=application.backtests,
                    context=_backtest_context(arguments, "PUBLISH_BACKTEST_REPORT"),
                )
            if command == "compare":
                return application.backtest_reports.compare(
                    arguments.left_run_id,
                    arguments.right_run_id,
                    descriptive=arguments.descriptive,
                )
    if arguments.area == "archive":
        require_isolated_operational_target(
            settings,
            expected_database_name=arguments.expected_database_name,
        )
        with bootstrap_application(settings) as application:
            if arguments.archive_command == "prospective":
                command = arguments.prospective_command
                if command in {"inspect", "health"}:
                    return archive_report(
                        application,
                        arguments.archive_id,
                        "inspect" if command == "inspect" else "daily-health",
                    )
                manifest = load_archive_manifest(arguments.manifest)
                if command == "plan-next":
                    return compile_prospective_runtime_plan(
                        manifest,
                        code_sha=arguments.code_sha,
                    )
                if command == "predeclare":
                    return predeclare_prospective_runtime(
                        application,
                        manifest,
                        code_sha=arguments.code_sha,
                        actor_id=arguments.actor_id,
                        lease_duration=timedelta(seconds=arguments.lease_seconds),
                    )
                if command in {"run-due", "resume"}:
                    import baostock as sdk

                    return run_due_prospective_runtime(
                        application,
                        manifest,
                        sdk=sdk,
                        code_sha=arguments.code_sha,
                        actor_id=arguments.actor_id,
                        worker_id=arguments.worker_id,
                        lease_duration=timedelta(seconds=arguments.lease_seconds),
                    )
            if arguments.archive_command in {"inspect", "gap-report", "revision-report", "daily-health"}:
                return archive_report(
                    application,
                    arguments.archive_id,
                    arguments.archive_command,
                )
            manifest = load_archive_manifest(arguments.manifest)
            if arguments.archive_command == "start":
                return start_archive(
                    application,
                    manifest,
                    actor_id=arguments.actor_id,
                )
            if arguments.archive_command in {"resume", "retry"}:
                import baostock as sdk

                return resume_archive(
                    application,
                    manifest,
                    sdk=sdk,
                    actor_id=arguments.actor_id,
                    operation_key=arguments.operation_key,
                    slice_ids=(tuple(arguments.slice_id) if arguments.slice_id else None),
                )
    raise ValueError("command is not implemented")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mra")
    areas = parser.add_subparsers(dest="area", required=True)

    database = areas.add_parser("db")
    database_commands = database.add_subparsers(dest="db_command", required=True)
    database_commands.add_parser("bootstrap")
    database_commands.add_parser("verify")
    recreate_plan = database_commands.add_parser("recreate-plan")
    recreate_plan.add_argument("--expected-database-name", required=True)
    recreate_plan.add_argument("--expected-database-oid", required=True, type=int)
    recreate_plan.add_argument("--operator-id", required=True)
    recreate_plan.add_argument("--reason", required=True)
    recreate_plan.add_argument("--backup-attestation", required=True)
    recreate_plan.add_argument("--output", type=Path)
    recreate_apply = database_commands.add_parser("recreate-apply")
    recreate_apply.add_argument("--plan", required=True, type=Path)
    recreate_apply.add_argument("--challenge", required=True)
    recreate_apply.add_argument("--operator-id", required=True)
    upgrade_plan = database_commands.add_parser("upgrade-plan")
    upgrade_plan.add_argument("--expected-database-name", required=True)
    upgrade_plan.add_argument("--expected-database-oid", required=True, type=int)
    upgrade_plan.add_argument("--operator-id", required=True)
    upgrade_plan.add_argument("--reason", required=True)
    upgrade_plan.add_argument("--backup", required=True, type=Path)
    upgrade_plan.add_argument("--backup-sha256", required=True)
    upgrade_plan.add_argument("--backup-size-bytes", required=True, type=int)
    upgrade_plan.add_argument(
        "--minimum-free-bytes",
        type=int,
        default=1024 * 1024 * 1024,
    )
    upgrade_plan.add_argument("--code-sha", required=True)
    upgrade_plan.add_argument("--output", type=Path)
    upgrade_apply = database_commands.add_parser("upgrade-apply")
    upgrade_apply.add_argument("--plan", required=True, type=Path)
    upgrade_apply.add_argument("--challenge", required=True)
    upgrade_apply.add_argument("--operator-id", required=True)

    runtime = areas.add_parser("runtime")
    runtime_commands = runtime.add_subparsers(dest="runtime_command", required=True)
    inspect = runtime_commands.add_parser("inspect")
    inspect.add_argument("--run-id", required=True, type=UUID)
    recover = runtime_commands.add_parser("recover")
    recover.add_argument("--actor-id", required=True)

    backtest = areas.add_parser("backtest")
    backtest_commands = backtest.add_subparsers(
        dest="backtest_command",
        required=True,
    )
    for command in ("validate", "plan", "predeclare"):
        operation = backtest_commands.add_parser(command)
        operation.add_argument("--specification", required=True, type=Path)
        if command == "predeclare":
            _add_backtest_mutation_arguments(operation)
    for command in ("run", "resume", "inspect", "replay"):
        operation = backtest_commands.add_parser(command)
        operation.add_argument("--run-id", required=True, type=UUID)
    report = backtest_commands.add_parser("report")
    report.add_argument("--run-id", required=True, type=UUID)
    report.add_argument("--format", choices=("json", "markdown"), default="json")
    publish_report = backtest_commands.add_parser("publish-report")
    publish_report.add_argument("--run-id", required=True, type=UUID)
    _add_backtest_mutation_arguments(publish_report)
    compare = backtest_commands.add_parser("compare")
    compare.add_argument("--left-run-id", required=True, type=UUID)
    compare.add_argument("--right-run-id", required=True, type=UUID)
    compare.add_argument("--descriptive", action="store_true")

    archive = areas.add_parser("archive")
    archive_commands = archive.add_subparsers(dest="archive_command", required=True)
    prospective = archive_commands.add_parser("prospective")
    prospective_commands = prospective.add_subparsers(
        dest="prospective_command",
        required=True,
    )
    prospective_plan = prospective_commands.add_parser("plan-next")
    prospective_plan.add_argument("--manifest", required=True, type=Path)
    prospective_plan.add_argument("--code-sha", required=True)
    prospective_plan.add_argument("--expected-database-name", required=True)
    for command in ("predeclare", "run-due", "resume"):
        mutation = prospective_commands.add_parser(command)
        mutation.add_argument("--manifest", required=True, type=Path)
        mutation.add_argument("--code-sha", required=True)
        mutation.add_argument("--expected-database-name", required=True)
        mutation.add_argument("--actor-id", required=True)
        mutation.add_argument("--lease-seconds", type=int, default=120)
        if command in {"run-due", "resume"}:
            mutation.add_argument("--worker-id", required=True)
    for command in ("inspect", "health"):
        inspection = prospective_commands.add_parser(command)
        inspection.add_argument("--archive-id", required=True, type=UUID)
        inspection.add_argument("--expected-database-name", required=True)
    for command in ("start", "resume", "retry"):
        mutation = archive_commands.add_parser(command)
        mutation.add_argument("--manifest", required=True, type=Path)
        mutation.add_argument("--expected-database-name", required=True)
        mutation.add_argument("--actor-id", required=True)
        if command in {"resume", "retry"}:
            mutation.add_argument("--operation-key", required=True)
            mutation.add_argument("--slice-id", action="append", type=UUID)
    for command in ("inspect", "gap-report", "revision-report", "daily-health"):
        inspection = archive_commands.add_parser(command)
        inspection.add_argument("--archive-id", required=True, type=UUID)
        inspection.add_argument("--expected-database-name", required=True)
    return parser


def _add_backtest_mutation_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--actor-id", required=True)
    parser.add_argument("--idempotency-key", required=True)


def _backtest_context(
    arguments: argparse.Namespace,
    reason_code: str,
) -> CommandContext:
    return CommandContext(
        idempotency_key=arguments.idempotency_key,
        actor_type=ActorType.OPERATOR,
        actor_id=arguments.actor_id,
        reason_code=reason_code,
    )


def _json_value(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return _json_value(asdict(value))
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_json_value(item) for item in value]
    if isinstance(value, (UUID, datetime, date, Path)):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    return value


__all__ = ["main"]
