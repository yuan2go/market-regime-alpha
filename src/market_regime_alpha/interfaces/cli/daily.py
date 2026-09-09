"""The daily research branch of the existing mra CLI."""

from __future__ import annotations

import argparse
from dataclasses import replace
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
    for command in ("data-ready", "freeze-plan", "predict", "settle", "status", "report", "replay"):
        operation = operations.add_parser(command)
        operation.add_argument("--plan", required=True, type=Path)
        if command == "freeze-plan":
            operation.add_argument("--output", required=True, type=Path)
        if command in {"predict", "settle"}:
            operation.add_argument("--operation-config", required=True, type=Path)
            operation.add_argument("--maximum-steps", type=int, default=9 if command == "predict" else 64)
    revoke = operations.add_parser("revoke-model")
    revoke.add_argument("--experimental-model-use-id", type=UUID, required=True)
    revoke.add_argument("--operation-config", type=Path, required=True)


def dispatch_daily(arguments: argparse.Namespace, settings: TargetSettings) -> object:
    command = arguments.daily_command
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
    if command in {"predict", "settle"}:
        config = load_operation_config(arguments.operation_config)
        require_installation(config)
        with operational_session(settings, config) as guard:
            with daily_research_admission(
                prediction_id=plan.prediction_id, code_sha=plan.code_sha, config_sha256=sha256(encode_daily_plan(plan)).hexdigest()
            ):
                with bootstrap_application(settings) as app:
                    if command == "predict" and config.code_sha != plan.code_sha:
                        if app.daily_prediction_reads.run_plan_content(plan.runtime_run_id) != encode_daily_plan(plan):
                            raise ValueError("OPERATION_DAILY_CODE_IDENTITY_MISMATCH")
                    guard.verify_startup(app)
                    app.daily_prediction_reads.validate_configuration(plan)
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
