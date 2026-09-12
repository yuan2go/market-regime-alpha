"""Small `mra` command tree over the sole target composition root."""

from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
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
from typing import Any, Callable, Iterator, Mapping, Sequence
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
from market_regime_alpha.interfaces.deployment_profile import prepare_deployment_profile, require_installation
from market_regime_alpha.interfaces.operation_observation import observe_health
from market_regime_alpha.interfaces.daily_work import DailyWorkCursor
from market_regime_alpha.interfaces.prospective_service import OperationAlertChanges, OperationStopped, OperationStopRequest, serve_prospective
from market_regime_alpha.interfaces.prospective_operations import load_operation_config, validate_operation_arguments
from market_regime_alpha.interfaces.prospective_operation_guard import operational_session, quiet_provider_output, verify_provider_access
from market_regime_alpha.market.application.prospective_runtime import ProspectiveRuntimeIntegrityError
from market_regime_alpha.market.ports import MarketProviderError
from market_regime_alpha.market.domain import ArchiveLane
from market_regime_alpha.market.application import compile_prospective_runtime_plan
from market_regime_alpha.runtime.application import ActorType, CommandContext


@contextmanager
def _operation_stage(timings: dict[str, dict[str, Any]], name: str, *, phase: str,
                     emit: Callable[[object], None], tick_sequence: int | None = None,
                     inclusive_child: bool = False) -> Iterator[None]:
    """Measure an existing boundary; no retry, budget or business-time policy."""
    started = perf_counter()
    state, error_type = "PASS", None
    try:
        yield
    except BaseException as exc:
        state = "STOPPED" if isinstance(exc, OperationStopped) else "FAIL"
        error_type = type(exc).__name__
        raise
    finally:
        elapsed = perf_counter() - started
        previous = timings.get(name, {})
        timings[name] = {
            "count": int(previous.get("count", 0)) + 1,
            "elapsed_seconds": float(previous.get("elapsed_seconds", 0.0)) + elapsed,
            "failed_count": int(previous.get("failed_count", 0)) + (state == "FAIL"),
            "stopped_count": int(previous.get("stopped_count", 0)) + (state == "STOPPED"),
            "last_state": state,
            "inclusive_child": inclusive_child,
            "add_to_other_stage_totals": not inclusive_child,
        }
        if state != "PASS":
            emit({"event": "PROSPECTIVE_STAGE_FAILURE", "phase": phase, "stage": name,
                  "tick_sequence": tick_sequence, "state": state, "error_type": error_type,
                  "stage_elapsed_seconds": elapsed, "inclusive_child": inclusive_child,
                  "stage_timings": timings})


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
    deployment_mode = False
    try:
        arguments = _parser().parse_args(argv)
        deployment_mode = arguments.area == "runtime" and arguments.runtime_command == "prepare-deployment"
        if (arguments.area == "archive" and arguments.archive_command == "prospective"
                and arguments.prospective_command in {"continue", "predeclare", "run-due", "resume"}):
            raise ValueError("OPERATION_GUARDED_PROSPECTIVE_ENTRY_REQUIRED: use mra archive prospective serve with --operation-config")
        operation_mode = (arguments.area == "archive" and arguments.archive_command == "prospective"
                          and arguments.prospective_command in {"serve", "preflight"})
        runtime_environ = os.environ if environ is None else environ
        settings = TargetSettings.from_environ(runtime_environ)
        payload: object
        if operation_mode:
            def emit(value: object) -> None:
                output.write(json.dumps(_json_value(value), sort_keys=True) + "\n")
                output.flush()

            startup_timings: dict[str, dict[str, Any]] = {}
            if arguments.operation_config is None:
                raise ValueError("operation-config is required before prospective service startup")
            with _operation_stage(startup_timings, "installed_profile", phase="STARTUP", emit=emit):
                operation_config = load_operation_config(arguments.operation_config)
                require_installation(operation_config)
                if arguments.prospective_command == "serve":
                    validate_operation_arguments(operation_config, arguments)
                elif arguments.expected_database_name != operation_config.database_name:
                    raise ValueError("OPERATION_DATABASE_IDENTITY_MISMATCH")

            with ExitStack() as supervisor_stack:
                with _operation_stage(startup_timings, "supervisor_scope", phase="STARTUP", emit=emit):
                    guard = supervisor_stack.enter_context(operational_session(settings, operation_config))
                import baostock as sdk
                with ExitStack() as startup_stack:
                    with _operation_stage(startup_timings, "bootstrap_scope", phase="STARTUP", emit=emit):
                        application = startup_stack.enter_context(bootstrap_application(settings))
                    daily_template=None
                    daily_delivery_adapter = None
                    daily_delivery_configuration: dict[str, object] = {
                        "state": "NOT_CONFIGURED",
                        "channels": (),
                    }
                    with _operation_stage(startup_timings, "daily_preparation", phase="STARTUP", emit=emit):
                        if arguments.daily_plan_template is not None:
                            from market_regime_alpha.interfaces.daily_service import prepare_pending_daily_recovery
                            from market_regime_alpha.interfaces.daily_delivery import (
                                LegacyNotifierDeliveryAdapter,
                            )
                            from market_regime_alpha.interfaces.daily_research import decode_daily_plan
                            from market_regime_alpha.notifications import build_notifiers
                            from hashlib import sha256
                            daily_content=arguments.daily_plan_template.read_bytes()
                            daily_template=decode_daily_plan(daily_content)
                            if daily_template.code_sha!=operation_config.code_sha:
                                raise ValueError('OPERATION_DAILY_CODE_IDENTITY_MISMATCH')
                            application.daily_prediction_reads.validate_configuration(daily_template)
                            guard.session.allow_expired_daily_recovery(daily_template.experimental_model_use_id, daily_template.code_sha)
                            prepare_pending_daily_recovery(application, guard.session)
                            notifiers, unavailable_channels = build_notifiers(
                                env=dict(runtime_environ)
                            )
                            if len(notifiers) > 1:
                                raise ValueError(
                                    "OPERATION_DAILY_MULTIPLE_DELIVERY_CHANNELS_UNSUPPORTED"
                                )
                            if notifiers:
                                daily_delivery_adapter = LegacyNotifierDeliveryAdapter(
                                    notifiers[0]
                                )
                                daily_delivery_configuration = {
                                    "state": "CONFIGURED",
                                    "channels": (notifiers[0].channel,),
                                }
                            elif unavailable_channels:
                                daily_delivery_configuration = {
                                    "state": "NOT_CONFIGURED",
                                    "channels": tuple(
                                        result.channel
                                        for result in unavailable_channels
                                    ),
                                    "reason_codes": tuple(
                                        "CHANNEL_UNAVAILABLE"
                                        for _result in unavailable_channels
                                    ),
                                }
                    with _operation_stage(startup_timings, "guard_preflight_principal_artifact_backup", phase="STARTUP", emit=emit):
                        preflight = guard.verify_startup(application)
                    with _operation_stage(startup_timings, "provider_login", phase="STARTUP", emit=emit):
                        preflight["provider_access"] = verify_provider_access(
                            sdk, timeout_seconds=operation_config.provider_timeout_seconds,
                        )
                    if daily_template is not None:
                        preflight['daily_template_sha256']=sha256(daily_content).hexdigest()
                        preflight["daily_delivery"] = daily_delivery_configuration
                    if arguments.prospective_command == "preflight":
                        with _operation_stage(startup_timings, "prospective_health", phase="STARTUP", emit=emit):
                            preflight["health"] = application.prospective_health.inspect(operation_config.series_code)["summary"]
                    else:
                        preflight["health"] = {"state": "OWNER_RECONCILIATION_PENDING"}
                    preflight["stage_timings"] = startup_timings
                alerts = OperationAlertChanges()
                stop_request = OperationStopRequest()
                tick_sequence = 0
                daily_work_cursor = DailyWorkCursor()

                def tick() -> object:
                    nonlocal tick_sequence
                    tick_sequence += 1
                    started = perf_counter()
                    tick_timings: dict[str, dict[str, Any]] = {}
                    def check_stop() -> None:
                        if stop_request.requested:
                            raise OperationStopped("STOP_REQUESTED")
                        if perf_counter() - started >= operation_config.maximum_tick_seconds:
                            raise OperationStopped("TICK_BUDGET_EXCEEDED")
                    def before_action() -> None:
                        check_stop()
                        with _operation_stage(tick_timings, "before_action_guard", phase="TICK", emit=emit,
                                              tick_sequence=tick_sequence, inclusive_child=True):
                            guard.before_action()
                        check_stop()
                    with _operation_stage(tick_timings, "installation_scope_checks", phase="TICK", emit=emit, tick_sequence=tick_sequence):
                        guard.operation_scope()
                    # Revalidate the new composition connection, not only the
                    # separate supervisor-lock connection, before owner writes.
                    with ExitStack() as tick_stack:
                        with _operation_stage(tick_timings, "bootstrap_scope", phase="TICK", emit=emit, tick_sequence=tick_sequence):
                            application = tick_stack.enter_context(bootstrap_application(settings))
                        with _operation_stage(tick_timings, "installation_scope_checks", phase="TICK", emit=emit, tick_sequence=tick_sequence):
                            guard.validate_scope(application.evidence.operation_scope())
                        def advance_daily() -> object:
                            if daily_template is None or stop_request.requested:
                                return None
                            from market_regime_alpha.interfaces.daily_service import daily_tick
                            from market_regime_alpha.interfaces.daily_collection import PerCaptureBaoStockProvider
                            try:
                                with _operation_stage(tick_timings, "daily_research", phase="TICK", emit=emit, tick_sequence=tick_sequence):
                                    check_stop()
                                    return daily_tick(application,daily_template,PerCaptureBaoStockProvider(sdk,
                                        timeout_seconds=operation_config.provider_timeout_seconds,maximum_rows=operation_config.provider_maximum_rows,
                                        maximum_response_bytes=operation_config.provider_maximum_response_bytes),worker_id=operation_config.worker_id,
                                        maximum_steps=operation_config.maximum_attempts_per_tick,before_action=before_action,
                                        delivery_adapter=daily_delivery_adapter, work_cursor=daily_work_cursor)
                            except OperationStopped as exc:
                                return {'state':'OPERATOR_STOPPED','reason_code':exc.reason_code,
                                    'completed_action_accounting': 'CANONICAL_HEALTH_ROSTER'}
                        def advance_prospective() -> object:
                            try:
                                with _operation_stage(tick_timings, "prospective_continuation", phase="TICK", emit=emit, tick_sequence=tick_sequence), quiet_provider_output():
                                    check_stop()
                                    return continue_prospective_series(
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
                                return {"state": "OPERATOR_STOPPED", "reason_code": exc.reason_code,
                                        "completed_action_accounting": "CANONICAL_HEALTH_ROSTER"}
                        # Alternate first access to the unchanged wall-clock budget.
                        # A slow owner cannot permanently consume every wakeup.
                        if tick_sequence % 2:
                            daily_result, result = advance_daily(), advance_prospective()
                        else:
                            result, daily_result = advance_prospective(), advance_daily()
                        def measured_health(name: str, read: Callable[[], dict[str, Any]]) -> dict[str, Any]:
                            def measured() -> dict[str, Any]:
                                with _operation_stage(tick_timings, name, phase="TICK", emit=emit, tick_sequence=tick_sequence):
                                    return read()
                            return observe_health(measured)
                        health = measured_health("prospective_health", lambda: application.prospective_health.inspect(
                            operation_config.series_code, cutover_at=arguments.health_cutover_at))
                        daily_scoped_health = None
                        if daily_template is not None:
                            from market_regime_alpha.interfaces.daily_health import daily_health
                            daily_scoped_health = measured_health("daily_health", lambda: daily_health(
                                application, cutover_at=arguments.health_cutover_at))
                            if "ledger" in daily_scoped_health:
                                daily_scoped_health['pending_work'] = [
                                    {key: row.get(key) for key in ('run_id','prediction_id','target_session','state','reason_code')}
                                    for row in daily_scoped_health.pop('ledger')
                                ]
                    summary = health.get("summary", health)
                    health_available = health.get("state") != "HEALTH_QUERY_FAILED"
                    alert_summary = (health['scopes']['POST_CURRENT_CUTOVER']['summary']
                                     if health_available and arguments.health_cutover_at is not None else summary)
                    return {
                        "event": "PROSPECTIVE_TICK", "database": health.get("database"),
                        "tick_sequence": tick_sequence, "stage_timings": tick_timings,
                        "stage_timing_contract": "WALL_CLOCK; BEFORE_ACTION_GUARD_IS_INCLUSIVE_CHILD_DO_NOT_SUM_WITH_PARENT_STAGES",
                        "series_code": operation_config.series_code, "observed_at": health.get("observed_at"),
                        "configuration_sha256": operation_config.content_sha256,
                        "continuation": result,
                        "daily_research": daily_result,
                        "health": {key: value for key, value in summary.items() if key != "alerts"},
                        "health_scopes": health.get("scopes", {"state": "UNKNOWN"}),
                        "daily_health": daily_scoped_health,
                        "backup_observation": {
                            "snapshot_at": guard.backup_snapshot_at,
                            "verified_at": guard.backup_verified_at,
                            "age_seconds": (None if guard.backup_snapshot_at is None or not health_available else
                                (health['observed_at'] - guard.backup_snapshot_at).total_seconds()),
                            "receipt_sha256": operation_config.backup_receipt_sha256,
                            "state": 'VERIFIED_AT_PREFLIGHT_AND_ENFORCED_BEFORE_ACTION',
                        },
                        "alert_scope": 'POST_CURRENT_CUTOVER' if arguments.health_cutover_at is not None else 'ALL_HISTORY',
                        "alert_changes": alerts.observe(alert_summary["alerts"]) if health_available else (),
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
        if (operation_mode or deployment_mode) and not (
            message.startswith("operation configuration") or message.startswith("operation-config")
            or (message.startswith(("OPERATION_", "DEPLOYMENT_")) and all(c.isupper() or c == "_" for c in message))
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
        if arguments.research_command in {"prepare-historical", "prepare-history-data", "history-inventory", "history-compare"}:
            from market_regime_alpha.interfaces.cli.research import execute_research
            return execute_research(settings, arguments)
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
        if arguments.evidence_command == "fresh-restore":
            if not arguments.disposable:
                raise ValueError("RESTORE_REQUIRES_EXPLICIT_DISPOSABLE_TARGET")
            from market_regime_alpha.infrastructure.postgres.evidence_backup import PostgresEvidenceBackup
            PostgresEvidenceBackup(settings.database_url, settings.artifact_root).fresh_restore(
                arguments.bundle, expected_name=arguments.expected_database_name, expected_oid=arguments.expected_database_oid,
                expected_cluster_identity=arguments.expected_cluster_identity, expected_backup_sha256=arguments.expected_backup_sha256)
            with bootstrap_application(settings) as restored:
                return restored.evidence.restore_check(arguments.bundle)
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
        if arguments.runtime_command == "prepare-deployment":
            return prepare_deployment_profile(
                settings, load_operation_config(arguments.operation_config),
                wheel=arguments.wheel, source_checkout=arguments.source_checkout,
                expected_source_sha=arguments.expected_source_sha,
                backup_directory=arguments.backup_directory, output=arguments.output,
            )
        with bootstrap_application(settings) as application:
            if arguments.runtime_command == "inspect":
                return application.runtime.inspect_run(arguments.run_id)
            if arguments.runtime_command == "recover":
                recovered = application.runtime.recover_expired(
                    actor_id=arguments.actor_id,
                    reason_code="LEASE_EXPIRED",
                    run_id=arguments.run_id,
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
                    require_installation(config)
                    with operational_session(settings, config) as guard:
                        guard.verify_startup(application)
                        guard.before_action()
                        with backtest_research_admission(backtest_run_id=arguments.run_id, specification_sha256=str(run.specification_sha256)):
                            return _execute_backtest(application, run, arguments)
                if command == "progress":
                    return application.backtest_execution.progress(run)
                if command == "run":
                    return _execute_backtest(application, run, arguments)
                if command == "resume":
                    return _execute_backtest(application, run, arguments)
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
            if arguments.archive_command in {
                "inspect", "gap-report", "revision-report", "daily-health", "acquisition-readiness",
            }:
                return archive_report(
                    application,
                    arguments.archive_id,
                    arguments.archive_command,
                )
            if arguments.archive_command == "seal":
                from market_regime_alpha.market.domain import ArchiveSealDisposition
                return application.market_archives.seal_retrospective(
                    market_archive_id=arguments.archive_id,
                    disposition=ArchiveSealDisposition(arguments.disposition),
                    context=CommandContext(actor_id=arguments.actor_id, actor_type=ActorType.OPERATOR,
                        idempotency_key=arguments.operation_key, reason_code="HISTORICAL_ARCHIVE_SEAL"))
            assert manifest is not None
            if arguments.archive_command == "start":
                return start_archive(
                    application,
                    manifest,
                    actor_id=arguments.actor_id,
                )
            if arguments.archive_command in {"resume", "retry"}:
                import baostock as sdk
                from time import monotonic
                from market_regime_alpha.market.domain.historical_acquisition import HistoricalAcquisitionBudget
                budget = (HistoricalAcquisitionBudget(arguments.maximum_slices if arguments.maximum_slices is not None else 8, arguments.maximum_seconds if arguments.maximum_seconds is not None else 1200)
                          if arguments.maximum_slices is not None or arguments.maximum_seconds is not None or manifest.start_request.price_basis.value == "MIXED_EXPLICIT" else None)
                started = monotonic()
                result = resume_archive(
                    application,
                    manifest,
                    sdk=sdk,
                    actor_id=arguments.actor_id,
                    operation_key=arguments.operation_key,
                    slice_ids=(tuple(arguments.slice_id) if arguments.slice_id else None),
                    budget=budget,
                )
                if budget is None:
                    return result
                return {"results": result, "elapsed_seconds": monotonic() - started,
                        "inspection": application.archive_inspection.inspect(manifest.start_request.market_archive_id)}
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
    fresh = evidence_commands.add_parser("fresh-restore")
    fresh.add_argument("--bundle", type=Path, required=True)
    fresh.add_argument("--disposable", action="store_true")
    fresh.add_argument("--expected-database-name", required=True)
    fresh.add_argument("--expected-database-oid", required=True, type=int)
    fresh.add_argument("--expected-cluster-identity", required=True)
    fresh.add_argument("--expected-backup-sha256", required=True)

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
    deployment = runtime_commands.add_parser("prepare-deployment")
    for name in ("operation-config", "wheel", "source-checkout", "backup-directory", "output"):
        deployment.add_argument("--" + name, type=Path, required=True)
    deployment.add_argument("--expected-source-sha", required=True)
    inspect = runtime_commands.add_parser("inspect")
    inspect.add_argument("--run-id", required=True, type=UUID)
    recover = runtime_commands.add_parser("recover")
    recover.add_argument("--actor-id", required=True)
    recover.add_argument("--run-id", required=True, type=UUID)

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
            operation.add_argument("--maximum-actions", type=int, help="Stop before another owner action; resume reads the original plan")
            operation.add_argument("--maximum-seconds", type=float, help="Elapsed invocation budget; does not interrupt an atomic owner command")
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
    preflight.add_argument("--daily-plan-template", type=Path)
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
            continuity.add_argument("--health-cutover-at", type=datetime.fromisoformat)
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
            mutation.add_argument("--maximum-slices", type=int)
            mutation.add_argument("--maximum-seconds", type=float)
    for command in (
        "inspect", "gap-report", "revision-report", "daily-health", "acquisition-readiness",
    ):
        inspection = archive_commands.add_parser(command)
        inspection.add_argument("--archive-id", required=True, type=UUID)
        inspection.add_argument("--expected-database-name", required=True)
    seal = archive_commands.add_parser("seal")
    seal.add_argument("--archive-id", required=True, type=UUID)
    seal.add_argument("--expected-database-name", required=True)
    seal.add_argument("--actor-id", required=True)
    seal.add_argument("--operation-key", required=True)
    seal.add_argument("--disposition", required=True, choices=("COMPLETE", "PARTIAL_WITH_GAPS", "PARTIAL_WITH_RESOURCE_LIMIT"))
    return parser


def _execute_backtest(application, run, arguments):
    from market_regime_alpha.research_qualification.domain.backtest_execution import BacktestExecutionBudget
    maximum_actions = getattr(arguments, "maximum_actions", None)
    maximum_seconds = getattr(arguments, "maximum_seconds", None)
    operation = application.backtest_execution.run if arguments.backtest_command == "run" else application.backtest_execution.resume
    if maximum_actions is None and maximum_seconds is None:
        return operation(run)
    budget = BacktestExecutionBudget(100_000 if maximum_actions is None else maximum_actions,
                                    3600.0 if maximum_seconds is None else maximum_seconds)
    return {"execution": operation(run, budget=budget), "invocation": application.backtest_execution.last_invocation}


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
