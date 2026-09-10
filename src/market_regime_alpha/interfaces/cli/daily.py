"""The daily research branch of the existing mra CLI."""

from __future__ import annotations

import argparse
from contextlib import nullcontext
from dataclasses import replace
from datetime import datetime
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
    daily = commands.add_parser("daily")
    operations = daily.add_subparsers(dest="daily_command", required=True)
    for command in ("data-ready", "freeze-plan", "predict", "collect-outcome", "settle", "status", "report", "replay"):
        operation = operations.add_parser(command)
        operation.add_argument("--plan", required=True, type=Path)
        if command == "freeze-plan":
            operation.add_argument("--output", required=True, type=Path)
        if command in {"predict", "collect-outcome", "settle"}:
            operation.add_argument("--operation-config", required=True, type=Path)
            operation.add_argument("--maximum-steps", type=int, default=9 if command == "predict" else 64)
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


def dispatch_daily(arguments: argparse.Namespace, settings: TargetSettings) -> object:
    command = arguments.daily_command
    if command == 'health':
        from market_regime_alpha.interfaces.daily_health import daily_health
        with bootstrap_application(settings) as app:
            return {
                'daily': daily_health(app,cutover_at=arguments.cutover_at,recent_sessions=arguments.recent_sessions,replay=arguments.replay),
                'prospective': app.prospective_health.inspect(arguments.series_code,cutover_at=arguments.cutover_at,recent_sessions=arguments.recent_sessions),
            }
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
    plan = decode_daily_plan(arguments.plan.read_bytes())
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
        if command in {"data-ready", "freeze-plan"}:
            ready = reads.observe(plan)
            if command == "data-ready":
                return ready
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
