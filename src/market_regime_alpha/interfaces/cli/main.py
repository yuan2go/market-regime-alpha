"""Small `mra` command tree over the sole target composition root."""

from __future__ import annotations

import argparse
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import Enum
from io import TextIOBase
import json
import os
from pathlib import Path
import sys
from time import perf_counter
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
    inspect_operational_database,
    inspect_prospective_series,
)
from market_regime_alpha.shared.errors import MraError
from market_regime_alpha.interfaces.archive import (
    archive_report,
    continue_prospective_series,
    load_archive_manifest,
    require_isolated_operational_target,
    resume_archive,
    start_archive,
)
from market_regime_alpha.interfaces.backtest import load_backtest_specification
from market_regime_alpha.interfaces.prospective_service import OperationAlertChanges, OperationStopped, OperationStopRequest, serve_prospective
from market_regime_alpha.interfaces.prospective_operations import load_operation_config, validate_operation_arguments
from market_regime_alpha.interfaces.prospective_operation_guard import operational_session, quiet_provider_output, verify_provider_access
from market_regime_alpha.market.application.prospective_runtime import ProspectiveRuntimeIntegrityError
from market_regime_alpha.market.ports import MarketProviderError
from market_regime_alpha.market.domain import ArchiveLane
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
    operation_mode = False
    try:
        arguments = _parser().parse_args(argv)
        if (arguments.area == "archive" and arguments.archive_command == "prospective"
                and arguments.prospective_command in {"continue", "predeclare", "run-due", "resume"}):
            raise ValueError("OPERATION_GUARDED_PROSPECTIVE_ENTRY_REQUIRED: use mra archive prospective serve with --operation-config")
        operation_mode = (arguments.area == "archive" and arguments.archive_command == "prospective"
                          and arguments.prospective_command in {"serve", "preflight"})
        settings = TargetSettings.from_environ(os.environ if environ is None else environ)
        payload: object
        if operation_mode:
            if arguments.operation_config is None:
                raise ValueError("operation-config is required before prospective service startup")
            operation_config = load_operation_config(arguments.operation_config)
            if arguments.prospective_command == "serve":
                validate_operation_arguments(operation_config, arguments)
            elif arguments.expected_database_name != operation_config.database_name:
                raise ValueError("OPERATION_DATABASE_IDENTITY_MISMATCH")

            def emit(value: object) -> None:
                output.write(json.dumps(_json_value(value), sort_keys=True) + "\n")
                output.flush()

            with operational_session(settings, operation_config) as guard:
                import baostock as sdk
                with bootstrap_application(settings) as application:
                    preflight = guard.verify_startup(application)
                    preflight["provider_access"] = verify_provider_access(
                        sdk, timeout_seconds=operation_config.provider_timeout_seconds,
                    )
                    daily_template=None
                    if arguments.prospective_command=='serve' and arguments.daily_plan_template is not None:
                        from market_regime_alpha.interfaces.daily_research import decode_daily_plan
                        from hashlib import sha256
                        daily_content=arguments.daily_plan_template.read_bytes()
                        daily_template=decode_daily_plan(daily_content)
                        if daily_template.code_sha!=operation_config.code_sha:
                            raise ValueError('OPERATION_DAILY_CODE_IDENTITY_MISMATCH')
                        application.daily_prediction_reads.validate_configuration(daily_template)
                        preflight['daily_template_sha256']=sha256(daily_content).hexdigest()
                    preflight["health"] = (
                        application.prospective_health.inspect(operation_config.series_code)["summary"]
                        if arguments.prospective_command == "preflight"
                        else {"state": "OWNER_RECONCILIATION_PENDING"}
                    )
                alerts = OperationAlertChanges()
                stop_request = OperationStopRequest()

                def tick() -> object:
                    started = perf_counter()
                    def check_stop() -> None:
                        if stop_request.requested:
                            raise OperationStopped("STOP_REQUESTED")
                        if perf_counter() - started >= operation_config.maximum_tick_seconds:
                            raise OperationStopped("TICK_BUDGET_EXCEEDED")
                    def before_action() -> None:
                        check_stop()
                        guard.before_action()
                        check_stop()
                    guard.snapshot()
                    # Revalidate the new composition connection, not only the
                    # separate supervisor-lock connection, before owner writes.
                    with bootstrap_application(settings) as application:
                        guard.validate_scope(application.evidence.inventory())
                        try:
                            with quiet_provider_output():
                                result = continue_prospective_series(
                                    application, series_code=operation_config.series_code, sdk=sdk,
                                    code_sha=operation_config.code_sha, actor_id=operation_config.actor_id,
                                    worker_id=operation_config.worker_id,
                                    lease_duration=timedelta(seconds=operation_config.lease_seconds),
                                    provider_timeout_seconds=operation_config.provider_timeout_seconds,
                                    provider_maximum_rows=operation_config.provider_maximum_rows,
                                    provider_maximum_response_bytes=operation_config.provider_maximum_response_bytes,
                                    maximum_attempts=operation_config.maximum_attempts_per_tick,
                                    before_action=before_action,
                                )
                        except OperationStopped as exc:
                            result = {"state": "OPERATOR_STOPPED", "reason_code": exc.reason_code,
                                      "completed_action_accounting": "CANONICAL_HEALTH_ROSTER"}
                        daily_result=None
                        if daily_template is not None and not stop_request.requested:
                            from market_regime_alpha.interfaces.daily_service import daily_tick
                            from market_regime_alpha.interfaces.daily_collection import PerCaptureBaoStockProvider
                            try:
                                daily_result=daily_tick(application,daily_template,PerCaptureBaoStockProvider(sdk,
                                    timeout_seconds=operation_config.provider_timeout_seconds,maximum_rows=operation_config.provider_maximum_rows,
                                    maximum_response_bytes=operation_config.provider_maximum_response_bytes),worker_id=operation_config.worker_id,
                                    maximum_steps=operation_config.maximum_attempts_per_tick,before_action=before_action)
                            except OperationStopped as exc:
                                daily_result={'state':'OPERATOR_STOPPED','reason_code':exc.reason_code}
                        health = application.prospective_health.inspect(operation_config.series_code)
                    summary = health["summary"]
                    return {
                        "event": "PROSPECTIVE_TICK", "database": health["database"],
                        "series_code": operation_config.series_code, "observed_at": health["observed_at"],
                        "configuration_sha256": operation_config.content_sha256,
                        "continuation": result,
                        "daily_research": daily_result,
                        "health": {key: value for key, value in summary.items() if key != "alerts"},
                        "alert_changes": alerts.observe(summary["alerts"]),
                        "tick_elapsed_seconds": perf_counter() - started,
                    }

                if arguments.prospective_command == "preflight":
                    payload = preflight
                else:
                    emit({"event": "PROSPECTIVE_PREFLIGHT", **preflight})
                    payload = serve_prospective(
                        tick, emit=emit, wakeup_seconds=arguments.wakeup_seconds,
                        maximum_wakeups=arguments.maximum_wakeups,
                        maximum_tick_seconds=operation_config.maximum_tick_seconds,
                        stop_request=stop_request,
                    )
        else:
            payload = _dispatch(arguments, settings)
        output.write(json.dumps(_json_value(payload), sort_keys=True) + "\n")
        return 2 if isinstance(payload, dict) and (
            payload.get("stop_reason") == "TICK_BUDGET_EXCEEDED" or
            (arguments.area == "evidence" and (payload.get("matched") is False or payload.get("ready") is False))
        ) else 0
    except (MraError, ValueError, OSError, psycopg.Error, ProspectiveRuntimeIntegrityError, MarketProviderError) as exc:
        message = str(exc)
        if operation_mode and not (
            message.startswith("operation configuration") or message.startswith("operation-config")
            or (message.startswith("OPERATION_") and all(c.isupper() or c == "_" for c in message))
        ):
            message = "OPERATION_FAILED_CLOSED_RECONCILE_BEFORE_RESTART"
        error_output.write(
            json.dumps(
                {"error_type": type(exc).__name__, "message": message},
                sort_keys=True,
            )
            + "\n"
        )
        return 2


def _dispatch(arguments: argparse.Namespace, settings: TargetSettings) -> object:
    if arguments.area == "research":
        from market_regime_alpha.interfaces.cli.daily import dispatch_daily
        return dispatch_daily(arguments, settings)
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
    if arguments.area == "evidence":
        if arguments.evidence_command == "diagnose":
            return inspect_operational_database(
                settings, run_id=arguments.run_id, expected_database_name=arguments.expected_database_name,
                expected_database_oid=arguments.expected_database_oid,
                expected_cluster_identity=arguments.expected_cluster_identity, repetitions=arguments.repetitions,
            )
        with bootstrap_application(settings) as application:
            if arguments.evidence_command == "inventory":
                return application.evidence.inventory(logical_role=arguments.role, records_directory=arguments.records_directory)
            if arguments.evidence_command == "restore-check":
                return application.evidence.restore_check(arguments.bundle)
            if arguments.evidence_command in {"backup-plan", "backup"}:
                operation = application.evidence.backup_plan if arguments.evidence_command == "backup-plan" else application.evidence.backup
                return operation(arguments.directory, expected_name=arguments.expected_database_name, expected_oid=arguments.expected_database_oid, minimum_free_bytes=arguments.minimum_free_bytes)
            return application.evidence.verify()
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
            if command in {"run", "resume", "inspect", "progress"}:
                run = application.backtest_specifications.load(arguments.run_id)
                if command in {"run", "resume"} and arguments.operation_config is not None:
                    from market_regime_alpha.infrastructure.postgres.prospective_operation_session import backtest_research_admission
                    config = load_operation_config(arguments.operation_config)
                    with operational_session(settings, config) as guard:
                        guard.verify_startup(application)
                        guard.before_action()
                        with backtest_research_admission(backtest_run_id=arguments.run_id, specification_sha256=str(run.specification_sha256)):
                            execute_backtest = application.backtest_execution.run if command == "run" else application.backtest_execution.resume
                            return execute_backtest(run)
                if command == "progress":
                    return application.backtest_execution.progress(run)
                if command == "run":
                    return application.backtest_execution.run(run)
                if command == "resume":
                    return application.backtest_execution.resume(run)
                return application.backtest_execution.inspect(run)
            if command == "replay":
                return application.backtest_replay.verify(arguments.run_id)
            if command == "diagnose":
                if arguments.format == "markdown":
                    return {"format": "markdown",
                            "content": application.backtest_diagnostics.render_markdown(arguments.run_id).decode("utf-8")}
                return application.backtest_diagnostics.project(arguments.run_id)
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
        if (arguments.archive_command == "prospective"
                and arguments.prospective_command in {"continue", "predeclare", "run-due", "resume"}):
            raise ValueError("OPERATION_GUARDED_PROSPECTIVE_ENTRY_REQUIRED: use mra archive prospective serve with --operation-config")
        manifest = None
        if arguments.archive_command in {"start", "resume", "retry"}:
            manifest = load_archive_manifest(arguments.manifest)
            if manifest.start_request.lane is ArchiveLane.PROSPECTIVE_CONTEMPORANEOUS:
                raise ValueError("OPERATION_GUARDED_PROSPECTIVE_ENTRY_REQUIRED: use mra archive prospective serve with --operation-config")
        if arguments.archive_command == "prospective" and arguments.prospective_command == "status":
            return inspect_prospective_series(
                settings, series_code=arguments.series_code,
                expected_database_name=arguments.expected_database_name,
                expected_database_oid=arguments.expected_database_oid,
                expected_cluster_identity=arguments.expected_cluster_identity,
            )
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
                        runtime_revision=arguments.runtime_revision,
                    )
            if arguments.archive_command in {"inspect", "gap-report", "revision-report", "daily-health"}:
                return archive_report(
                    application,
                    arguments.archive_id,
                    arguments.archive_command,
                )
            assert manifest is not None
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
    from market_regime_alpha.interfaces.cli.daily import add_daily_parser
    add_daily_parser(areas)

    evidence = areas.add_parser("evidence")
    evidence_commands = evidence.add_subparsers(dest="evidence_command", required=True)
    inventory = evidence_commands.add_parser("inventory")
    inventory.add_argument("--role", default="UNSPECIFIED")
    inventory.add_argument("--records-directory", type=Path)
    evidence_commands.add_parser("verify")
    diagnose = evidence_commands.add_parser("diagnose")
    diagnose.add_argument("--run-id", required=True, type=UUID)
    diagnose.add_argument("--expected-database-name", required=True)
    diagnose.add_argument("--expected-database-oid", required=True, type=int)
    diagnose.add_argument("--expected-cluster-identity", required=True)
    diagnose.add_argument("--repetitions", type=int, default=2)
    for command in ("backup-plan", "backup"):
        backup = evidence_commands.add_parser(command)
        backup.add_argument("--directory", type=Path, required=True)
        backup.add_argument("--expected-database-name", required=True)
        backup.add_argument("--expected-database-oid", type=int, required=True)
        backup.add_argument("--minimum-free-bytes", type=int, default=256_000_000)
    restore = evidence_commands.add_parser("restore-check")
    restore.add_argument("--bundle", type=Path, required=True)

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
    for command in ("run", "resume", "inspect", "replay", "progress"):
        operation = backtest_commands.add_parser(command)
        operation.add_argument("--run-id", required=True, type=UUID)
        if command in {"run", "resume"}:
            operation.add_argument("--operation-config", type=Path)
    report = backtest_commands.add_parser("report")
    report.add_argument("--run-id", required=True, type=UUID)
    report.add_argument("--format", choices=("json", "markdown"), default="json")
    diagnosis = backtest_commands.add_parser("diagnose")
    diagnosis.add_argument("--run-id", required=True, type=UUID)
    diagnosis.add_argument("--format", choices=("json", "markdown"), default="json")
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
    preflight = prospective_commands.add_parser("preflight")
    preflight.add_argument("--operation-config", required=True, type=Path)
    preflight.add_argument("--expected-database-name", required=True)
    status = prospective_commands.add_parser("status")
    status.add_argument("--series-code", required=True)
    status.add_argument("--expected-database-name", required=True)
    status.add_argument("--expected-database-oid", required=True, type=int)
    status.add_argument("--expected-cluster-identity", required=True)
    for command in ("continue", "serve"):
        continuity = prospective_commands.add_parser(
            command, help=("Guarded prospective operation" if command == "serve"
                           else "Retired unguarded entry; use serve with --operation-config"),
        )
        continuity.add_argument("--series-code", required=True)
        continuity.add_argument("--code-sha", required=True)
        continuity.add_argument("--expected-database-name", required=True)
        continuity.add_argument("--actor-id", required=True)
        continuity.add_argument("--worker-id", required=True)
        continuity.add_argument("--lease-seconds", type=int, default=120)
        if command == "serve":
            continuity.add_argument("--operation-config", type=Path)
            continuity.add_argument("--daily-plan-template", type=Path)
            continuity.add_argument("--wakeup-seconds", required=True, type=float)
            continuity.add_argument("--maximum-wakeups", type=int)
    prospective_plan = prospective_commands.add_parser("plan-next")
    prospective_plan.add_argument("--manifest", required=True, type=Path)
    prospective_plan.add_argument("--code-sha", required=True)
    prospective_plan.add_argument("--runtime-revision", type=int, choices=(1, 2), default=2)
    prospective_plan.add_argument("--expected-database-name", required=True)
    for command in ("predeclare", "run-due", "resume"):
        mutation = prospective_commands.add_parser(
            command, help="Retired unguarded entry; use serve with --operation-config",
        )
        mutation.add_argument("--manifest", required=True, type=Path)
        mutation.add_argument("--code-sha", required=True)
        mutation.add_argument("--runtime-revision", type=int, choices=(1, 2), default=2)
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
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("CLI Decimal output must be finite")
        return str(value)
    if isinstance(value, (UUID, datetime, date, Path)):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    return value


__all__ = ["main"]
