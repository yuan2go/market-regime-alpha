"""The daily research branch of the existing mra CLI."""

from __future__ import annotations

import argparse
from contextlib import nullcontext
from dataclasses import replace
from datetime import date, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5
from market_regime_alpha.runtime.application import ActorType, CommandContext

from market_regime_alpha.bootstrap import TargetSettings, bootstrap_application
from market_regime_alpha.interfaces.daily_research import DailyResearchOperations, decode_daily_plan, encode_daily_plan
from market_regime_alpha.interfaces.prospective_operation_guard import operational_session
from market_regime_alpha.interfaces.prospective_operations import load_operation_config
from market_regime_alpha.interfaces.deployment_profile import require_installation
from market_regime_alpha.infrastructure.postgres.prospective_operation_session import daily_research_admission
from market_regime_alpha.runtime.errors import RuntimeNotFoundError


def add_daily_parser(areas: Any) -> None:
    research = areas.add_parser("research")
    commands = research.add_subparsers(dest="research_command", required=True)
    from market_regime_alpha.interfaces.cli.research import add_historical_parser
    add_historical_parser(commands)
    validity = commands.add_parser("validity")
    validity_commands = validity.add_subparsers(dest="validity_command", required=True)
    validity_daily = validity_commands.add_parser("daily")
    from market_regime_alpha.research_qualification.domain.validity_protocol import CURRENT_PROTOCOL_VERSION
    validity_daily.add_argument("--protocol-version", type=int, default=CURRENT_PROTOCOL_VERSION)
    validity_daily.add_argument("--target-session-from", type=date.fromisoformat)
    validity_daily.add_argument("--target-session-to", type=date.fromisoformat)
    for budget in ("collection", "backup", "publication"):
        validity_daily.add_argument("--" + budget + "-budget-seconds", type=float,
            help="Measured operational scenario duration; omitted means NOT_ESTIMABLE")
    daily = commands.add_parser("daily")
    operations = daily.add_subparsers(dest="daily_command", required=True)
    lineage = operations.add_parser("lineage")
    lineage.add_argument("--model-version-id", type=UUID, required=True)
    for command in ("data-ready", "freeze-plan", "predict", "collect-outcome", "settle", "status", "report", "replay", "deliver", "delivery-status", "refresh-calendar"):
        operation = operations.add_parser(command)
        operation.add_argument("--plan", required=True, type=Path)
        if command == "freeze-plan":
            operation.add_argument("--output", required=True, type=Path)
        if command in {"deliver", "delivery-status"}:
            operation.add_argument("--channel", required=True)
        if command in {"predict", "collect-outcome", "settle", "deliver", "refresh-calendar"}:
            operation.add_argument("--operation-config", required=True, type=Path)
        if command in {"predict", "collect-outcome", "settle"}:
            operation.add_argument("--maximum-steps", type=int, default=9 if command == "predict" else 64)
    backlog = operations.add_parser("backlog")
    backlog.add_argument("--kind", choices=("outcome", "delivery"), default="outcome")
    backlog.add_argument("--channel", default="feishu")
    backlog.add_argument("--page-size", type=int, default=64)
    backlog.add_argument("--after-requested-at", type=datetime.fromisoformat)
    backlog.add_argument("--after-run-id", type=UUID)
    backlog.add_argument("--after-priority", type=int, choices=range(4))
    revoke = operations.add_parser("revoke-model")
    revoke.add_argument("--experimental-model-use-id", type=UUID, required=True)
    revoke.add_argument("--operation-config", type=Path, required=True)
    retry = operations.add_parser("retry-population")
    retry.add_argument("--collection-plan", type=Path, required=True)
    retry.add_argument("--operation-config", type=Path, required=True)
    retry.add_argument("--maximum-steps", type=int, default=2)
    health = operations.add_parser('health')
    health.add_argument('--series-code', required=True)
    health.add_argument('--cutover-at', type=datetime.fromisoformat)
    health.add_argument('--recent-sessions', type=int, default=5)
    health.add_argument('--replay', action='store_true')
    health.add_argument('--backup-receipts-directory', type=Path)
    observation = operations.add_parser("observations")
    observation.add_argument("--target-session-date", type=date.fromisoformat)
    observation.add_argument("--model-version-id", type=UUID)
    observation.add_argument("--target-definition-id", type=UUID)
    observation.add_argument("--target-session-from", type=date.fromisoformat)
    observation.add_argument("--target-session-to", type=date.fromisoformat)
    observation.add_argument("--experimental-model-use-id", type=UUID)
    observation.add_argument("--dataset-id", type=UUID)
    observation.add_argument("--decision-run-id", type=UUID)
    availability = observation.add_mutually_exclusive_group()
    availability.add_argument("--completed-only", dest="completed_only", action="store_true")
    availability.add_argument("--include-unavailable", dest="completed_only", action="store_false")
    observation.set_defaults(completed_only=False)


def dispatch_daily(arguments: argparse.Namespace, settings: TargetSettings) -> object:
    if arguments.research_command == "validity":
        from market_regime_alpha.interfaces.daily_observations import daily_observations
        from market_regime_alpha.research_qualification.application.validity import validity_report
        from market_regime_alpha.research_qualification.domain.validity_protocol import load_validity_protocol
        protocol = load_validity_protocol(arguments.protocol_version)
        identities = protocol["identities"]
        with bootstrap_application(settings) as app:
            operational = daily_observations(app, model_version_id=UUID(identities["model_version"]["id"]),
                target_definition_id=UUID(identities["target_definition"]["id"]))
            use_id = UUID(identities["experimental_model_use"]["id"])
            observations = {**operational, **{
                key: [row for row in operational[key] if row["experimental_model_use_id"] == use_id]
                for key in ("cycles", "unavailable")
            }}
            use = app.daily_prediction_reads.experimental_model_use_record(use_id)
            witness = app.calendar_continuity_reads.calendar_coverage(
                UUID(protocol["frozen_population_semantics"]["provider_product_id"]),
                operational["observed_at"],
            ) if "frozen_population_semantics" in protocol else None
            calendar = app.daily_prediction_reads.validity_calendar()
            result = validity_report(observations, protocol, calendar,
                target_session_from=arguments.target_session_from, target_session_to=arguments.target_session_to,
                model_use=use, calendar_coverage_witness=witness, operational_observations=operational)
            from market_regime_alpha.research_qualification.domain.operational_capacity import operational_capacity
            from market_regime_alpha.interfaces.daily_service import _OUTCOME_GRACE
            result["operational_reachability"] = operational_capacity(result["cohort_capacity"], calendar,
                observed_at=operational["observed_at"], collection_seconds=arguments.collection_budget_seconds,
                backup_seconds=arguments.backup_budget_seconds, publication_seconds=arguments.publication_budget_seconds,
                outcome_grace_seconds=_OUTCOME_GRACE.total_seconds())
            return result
    command = arguments.daily_command
    if command == "lineage":
        from market_regime_alpha.interfaces.model_lineage import model_lineage
        with bootstrap_application(settings) as app:
            return model_lineage(app, arguments.model_version_id)
    if command == "observations":
        from market_regime_alpha.interfaces.daily_observations import daily_observations
        with bootstrap_application(settings) as app:
            return daily_observations(app, target_session_date=arguments.target_session_date,
                                      model_version_id=arguments.model_version_id,
                                      target_definition_id=arguments.target_definition_id,
                                      target_session_from=arguments.target_session_from,
                                      target_session_to=arguments.target_session_to,
                                      experimental_model_use_id=arguments.experimental_model_use_id,
                                      dataset_id=arguments.dataset_id, decision_run_id=arguments.decision_run_id,
                                      completed_only=arguments.completed_only)
    if command == 'health':
        from market_regime_alpha.interfaces.daily_health import daily_health
        with bootstrap_application(settings) as app:
            health_result = {
                'daily': daily_health(app,cutover_at=arguments.cutover_at,recent_sessions=arguments.recent_sessions,replay=arguments.replay),
                'prospective': app.prospective_health.inspect(arguments.series_code,cutover_at=arguments.cutover_at,recent_sessions=arguments.recent_sessions),
            }
            if arguments.backup_receipts_directory is not None:
                from market_regime_alpha.interfaces.operational_reliability import scheduled_backup_reliability
                health_result['scheduled_backup'] = scheduled_backup_reliability(arguments.backup_receipts_directory)
            return health_result
    if command == "retry-population":
        import importlib
        from market_regime_alpha.interfaces.daily_collection import DailyCollectionPlan, PerCaptureBaoStockProvider, retry_failed_population_collection
        from market_regime_alpha.interfaces.prospective_operation_guard import quiet_provider_output

        failed = DailyCollectionPlan.decode(arguments.collection_plan.read_bytes())
        config = load_operation_config(arguments.operation_config)
        require_installation(config)
        with operational_session(settings, config) as guard, bootstrap_application(settings) as app:
            guard.verify_startup(app)
            app.daily_prediction_reads.validate_configuration(failed.prediction)
            provider = PerCaptureBaoStockProvider(importlib.import_module("baostock"), timeout_seconds=config.provider_timeout_seconds,
                maximum_rows=config.provider_maximum_rows, maximum_response_bytes=config.provider_maximum_response_bytes)
            with quiet_provider_output():
                successor = retry_failed_population_collection(app, failed, provider, worker_id=config.worker_id,
                    maximum_steps=min(arguments.maximum_steps, config.maximum_attempts_per_tick), before_action=guard.before_action)
            return {"failed_run_id": failed.run_id, "failed_run_preserved": True, "successor": successor}
    if command == "revoke-model":
        config = load_operation_config(arguments.operation_config)
        require_installation(config)
        with operational_session(settings, config) as guard, bootstrap_application(settings) as app:
            guard.verify_startup(app)
            guard.before_action()
            return app.research_models.revoke_experimental_use(
                arguments.experimental_model_use_id,
                CommandContext(
                    "revoke-daily-use:" + str(arguments.experimental_model_use_id),
                    ActorType.OPERATOR,
                    config.actor_id,
                    "STOP_EXPERIMENTAL_MODEL_USE",
                ),
            )
    if command == "backlog":
        from market_regime_alpha.research_qualification.ports.daily_prediction import DailyDeliveryWorkItem, DailyOutcomeWorkItem
        page: tuple[DailyDeliveryWorkItem | DailyOutcomeWorkItem, ...]
        if (arguments.after_requested_at is None) != (arguments.after_run_id is None):
            raise ValueError("backlog cursor requires both requested-at and run-id")
        pair = None if arguments.after_requested_at is None else (arguments.after_requested_at, arguments.after_run_id)
        with bootstrap_application(settings) as app:
            reads = app.daily_prediction_reads
            if arguments.kind == "outcome":
                if (pair is None) != (arguments.after_priority is None):
                    raise ValueError("Outcome cursor requires its exact priority")
                page = reads.outcome_work_items(limit=arguments.page_size, after=None if pair is None else (arguments.after_priority, *pair))
                counts = reads.outcome_work_counts()
            else:
                if arguments.after_priority is not None:
                    raise ValueError("delivery cursor has no priority")
                page = reads.delivery_work_items(arguments.channel, limit=arguments.page_size, after=pair)
                counts = reads.delivery_work_counts(arguments.channel)
            from dataclasses import asdict
            items = [{key: value for key, value in asdict(item).items() if key != "plan_content"} for item in page]
            if arguments.kind == "delivery":
                from market_regime_alpha.interfaces.daily_delivery import DailyReportDelivery
                from market_regime_alpha.interfaces.daily_work import published_delivery_plan
                delivery = DailyReportDelivery(app, reads, admission_scope=lambda _: nullcontext())
                for item, value in zip(page, items):
                    assert isinstance(item, DailyDeliveryWorkItem)
                    try:
                        value["delivery_observation"] = delivery.inspect(published_delivery_plan(item), arguments.channel)
                    except (RuntimeError, ValueError) as exc:
                        value["delivery_observation"] = {"state": "INTEGRITY_BLOCKED", "error_type": type(exc).__name__}
            return {"kind": arguments.kind, "complete_runtime_counts": counts,
                    "items": items,
                    "next_cursor": page[-1].cursor if len(page) == arguments.page_size else None,
                    "page_size": arguments.page_size, "business_writes": 0}
    plan = decode_daily_plan(arguments.plan.read_bytes())
    if command == "deliver":
        from market_regime_alpha.interfaces.daily_service import _deliver_report, prepare_pending_daily_recovery
        from market_regime_alpha.interfaces.daily_delivery import LegacyNotifierDeliveryAdapter
        from market_regime_alpha.notifications import build_notifiers
        config = load_operation_config(arguments.operation_config)
        require_installation(config)
        notifiers, unavailable = build_notifiers(channels=arguments.channel)
        if unavailable or len(notifiers) != 1:
            raise ValueError("DAILY_DELIVERY_CHANNEL_UNAVAILABLE")
        with operational_session(settings, config) as guard, bootstrap_application(settings) as app:
            prepare_pending_daily_recovery(app, guard.session)
            guard.verify_startup(app)
            app.daily_prediction_reads.validate_configuration(plan)
            return _deliver_report(app, plan, LegacyNotifierDeliveryAdapter(notifiers[0]),
                                   worker_id=config.worker_id, before_action=guard.before_action)
    if command == "refresh-calendar":
        import importlib
        from market_regime_alpha.interfaces.calendar_continuity import refresh_calendar
        from market_regime_alpha.interfaces.daily_collection import PerCaptureBaoStockProvider
        from market_regime_alpha.interfaces.daily_service import prepare_pending_daily_recovery
        from market_regime_alpha.interfaces.prospective_operation_guard import quiet_provider_output
        config = load_operation_config(arguments.operation_config)
        require_installation(config)
        with operational_session(settings, config) as guard, bootstrap_application(settings) as app:
            prepare_pending_daily_recovery(app, guard.session)
            guard.verify_startup(app)
            app.daily_prediction_reads.validate_configuration(plan)
            provider = PerCaptureBaoStockProvider(importlib.import_module("baostock"), timeout_seconds=config.provider_timeout_seconds,
                maximum_rows=config.provider_maximum_rows, maximum_response_bytes=config.provider_maximum_response_bytes)
            with quiet_provider_output():
                return refresh_calendar(app, provider_product_id=plan.provider_product_id, code_sha=config.code_sha,
                    provider=provider, worker_id=config.worker_id, before_action=guard.before_action,
                    experimental_model_use_id=plan.experimental_model_use_id)
    if command in {"predict", "collect-outcome", "settle"}:
        config = load_operation_config(arguments.operation_config)
        require_installation(config)
        with operational_session(settings, config) as guard:
            with (nullcontext() if command == "collect-outcome" else daily_research_admission(
                prediction_id=plan.prediction_id, code_sha=plan.code_sha, config_sha256=sha256(encode_daily_plan(plan)).hexdigest()
            )):
                with bootstrap_application(settings) as app:
                    if command == "predict" and config.code_sha != plan.code_sha:
                        if app.daily_prediction_reads.run_plan_content(plan.runtime_run_id) != encode_daily_plan(plan):
                            raise ValueError("OPERATION_DAILY_CODE_IDENTITY_MISMATCH")
                    guard.verify_startup(app)
                    app.daily_prediction_reads.validate_configuration(plan)
                    if command == "collect-outcome":
                        return _collect_pending_outcome(app, plan, config, guard, arguments.maximum_steps)
                    operations = DailyResearchOperations(app, app.daily_prediction_reads, before_action=guard.before_action)
                    if command == "predict":
                        return operations.execute(plan, worker_id=config.worker_id, maximum_steps=arguments.maximum_steps)
                    return operations.settle_and_evaluate(plan, worker_id=config.worker_id, maximum_steps=arguments.maximum_steps)
    with bootstrap_application(settings) as app:
        reads = app.daily_prediction_reads
        if command == "delivery-status":
            from market_regime_alpha.interfaces.daily_delivery import DailyReportDelivery
            return DailyReportDelivery(app, reads, admission_scope=lambda _: nullcontext()).inspect(plan, arguments.channel)
        if command in {"data-ready", "freeze-plan"}:
            ready = reads.observe(plan)
            if command == "data-ready":
                from dataclasses import asdict
                population_ready = reads.population_source_ready(plan)
                return {**asdict(ready), "content_sha256": ready.content_sha256,
                    "price_input_state": ready.state, "population_source_ready": population_ready,
                    "state": ready.state if population_ready else "NOT_READY",
                    "reason_code": None if population_ready else "POPULATION_DEPENDENCIES_INCOMPLETE"}
            frozen = replace(plan, input_content_sha256=ready.content_sha256)
            content = encode_daily_plan(frozen)
            # Immutable local request file: never overwrite another frozen plan.
            if arguments.output.exists():
                if arguments.output.read_bytes() != content:
                    raise ValueError("daily output already contains another frozen request")
            else:
                with arguments.output.open("xb") as stream:
                    stream.write(content)
            return {"state": ready.state, "plan_sha256": frozen.content_sha256, "prediction_id": frozen.prediction_id}
        if command == "status":
            try:
                trace = app.runtime.inspect_run(plan.runtime_run_id)
            except RuntimeNotFoundError:
                trace = None
            return {
                "data_ready": reads.observe(plan),
                "runtime": trace,
                "health": reads.operational_health(plan),
                "state": "NOT_SCHEDULED" if trace is None else trace.run_state,
            }
        if command in {"report", "replay"}:
            try:
                outcomes = app.runtime.inspect_run(uuid5(plan.prediction_id, "outcome-evaluation-runtime"))
            except RuntimeNotFoundError:
                outcomes = None
            completed = outcomes is not None and outcomes.run_state == "SUCCEEDED"
            reconciled = (app.daily_research.replay_completed_cycle(plan) if completed
                          else app.daily_research.replay(plan))
            result = {"state": "COMPLETED" if completed else "PENDING_OR_BLOCKED_OUTCOME",
                      "outcome_runtime": outcomes, "reconciliation": reconciled}
            if command == "report":
                result["prediction"] = reads.forecast_projection(plan)
                result["evaluation"] = (reads.evaluation_projection(uuid5(plan.prediction_id, "evaluation"))
                                        if completed else None)
            return result
    raise ValueError("unsupported daily research command")


def _collect_pending_outcome(app: Any, plan: Any, config: Any, guard: Any, maximum_steps: int) -> object:
    """Explicit late observation preserves publication and never reopens settlement."""
    from market_regime_alpha.interfaces.daily_collection import PerCaptureBaoStockProvider
    import importlib
    from market_regime_alpha.interfaces.daily_service import _collection
    from market_regime_alpha.interfaces.prospective_operation_guard import quiet_provider_output

    reads = app.daily_prediction_reads
    if reads.run_plan_content(plan.runtime_run_id) != encode_daily_plan(plan):
        raise ValueError("DAILY_OUTCOME_RECOVERY_FROZEN_PLAN_MISMATCH")
    if app.runtime.inspect_run(plan.runtime_run_id).run_state != "SUCCEEDED":
        raise ValueError("DAILY_OUTCOME_RECOVERY_REQUIRES_PUBLICATION")
    outcome_id = uuid5(plan.prediction_id, "outcome-evaluation-runtime")
    outcome = app.runtime.inspect_run(outcome_id)
    if (reads.run_plan_content(outcome_id) != encode_daily_plan(plan)
            or outcome.run_state not in {"QUEUED", "RUNNING"}
            or any(step.step_key.startswith("settle-") and step.current_fence > 0 for step in outcome.steps)):
        raise ValueError("DAILY_OUTCOME_RECOVERY_SETTLEMENT_ALREADY_STARTED_OR_TERMINAL")
    ready = reads.ready(plan)
    now = reads.now()
    if now < ready.target_window_end:
        raise ValueError("DAILY_OUTCOME_RECOVERY_NOT_MATURE")
    if not app.daily_research.replay(plan)["matched"]:
        raise ValueError("DAILY_OUTCOME_RECOVERY_PUBLICATION_NOT_RECONCILED")
    provider = PerCaptureBaoStockProvider(importlib.import_module("baostock"), timeout_seconds=config.provider_timeout_seconds,
        maximum_rows=config.provider_maximum_rows, maximum_response_bytes=config.provider_maximum_response_bytes)
    with quiet_provider_output():
        result = _collection(app, plan, "outcome", provider, config.worker_id,
            min(maximum_steps, config.maximum_attempts_per_tick, 128), guard.before_action)
    return {"prediction_id": plan.prediction_id, "observed_at": now,
            "target_window_end": ready.target_window_end, "observation_disposition": "LATE_OUTCOME_OBSERVATION",
            "prediction_replaced": False, "collection": result}
