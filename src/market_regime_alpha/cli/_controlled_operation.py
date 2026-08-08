"""Shared JSON and repository boundary for Controlled operation CLIs."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
from enum import IntEnum
import json
from pathlib import Path
from typing import Any, NoReturn

import psycopg

from market_regime_alpha.application.controlled_operation.input_artifacts import (
    load_controlled_runtime_configuration,
    load_controlled_trading_calendar,
)
from market_regime_alpha.application.controlled_operation.journal import (
    ControlledOperationCommand,
    DecisionTimeOperationRunSnapshot,
    DecisionTimeOperationJournal,
)
from market_regime_alpha.application.controlled_operation.policy import (
    default_decision_time_operation_policy,
)
from market_regime_alpha.application.controlled_operation.runner import (
    ControlledDecisionTimeOperationRunner,
    ControlledOperationDecisionResult,
    ControlledOperationInputPaths,
    ControlledOperationPreparation,
    ControlledOperationSettlementResult,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.persistence.repository_factory import (
    RepositoryFactory,
    add_database_arguments,
    settings_from_namespace,
)
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionUnavailable,
)


class ControlledExitCode(IntEnum):
    SUCCESS = 0
    ARGUMENT_ERROR = 2
    NON_TRADING_DAY = 3
    TOO_EARLY = 4
    DEADLINE_MISSED = 5
    DATA_BLOCKED = 6
    PARTIAL_PROVIDER_FAILURE = 7
    RUN_CONFLICT = 8
    RESUME_REJECTED = 9
    REPLAY_DIVERGENCE = 10
    REPOSITORY_ERROR = 11


class ControlledCLIError(ValueError):
    pass


class StructuredParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise ControlledCLIError(message)


def add_repository_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output-root", type=Path, required=True)
    add_database_arguments(parser)


def repository_paths(args: argparse.Namespace) -> tuple[Path, Path]:
    output_root = args.output_root.resolve()
    return output_root, output_root / "postgresql-authority"


def runner_and_journal(
    args: argparse.Namespace,
) -> tuple[
    ControlledDecisionTimeOperationRunner,
    DecisionTimeOperationJournal,
    RepositoryFactory,
]:
    output_root, _ = repository_paths(args)
    repositories = RepositoryFactory(settings_from_namespace(args))
    journal = repositories.controlled_operation(clock=_utc_now)
    runner = ControlledDecisionTimeOperationRunner(
        journal=journal,
        output_root=output_root,
        longitudinal_index=repositories.longitudinal(clock=_utc_now),
        canonical_repository_factory=(
            repositories.controlled_canonical_repository
        ),
        feature_repository_factory=(
            repositories.feature_materialization_for_path
        ),
    )
    return (
        runner,
        journal,
        repositories,
    )


def command_from_prepare_args(args: argparse.Namespace) -> ControlledOperationCommand:
    policy = default_decision_time_operation_policy()
    calendar = load_controlled_trading_calendar(args.trading_calendar.resolve())
    configuration = load_controlled_runtime_configuration(args.runtime_configuration.resolve())
    decision_date = _date(args.decision_date)
    return ControlledOperationCommand.create(
        idempotency_key=args.idempotency_key,
        decision_date=decision_date,
        decision_time=policy.decision_instant(decision_date),
        policy_id=policy.policy_id,
        policy_hash=policy.content_hash,
        trading_calendar_id=calendar.artifact_id,
        trading_calendar_hash=calendar.content_hash,
        configuration_manifest_id=configuration.configuration_id,
        configuration_manifest_hash=configuration.configuration_hash,
        model_manifest_id=configuration.model_manifest_id,
        model_manifest_hash=configuration.model_manifest_hash,
        code_revision=args.code_revision,
        limitations=(
            "ENTRY_BLOCKED",
            "FORMAL_OOS_ALPHA_NOT_ESTABLISHED",
            "NO_BROKER_AUTHORITY",
        ),
    )


def input_paths_from_prepare_args(args: argparse.Namespace) -> ControlledOperationInputPaths:
    return ControlledOperationInputPaths(
        trading_calendar=args.trading_calendar.resolve(),
        operational_universe=args.operational_universe.resolve(),
        daily_source_stage=args.daily_source_stage.resolve(),
        daily_source_manifest=args.daily_source_manifest.resolve(),
        supplemental_research_evidence=args.supplemental_research_evidence.resolve(),
        runtime_configuration=args.runtime_configuration.resolve(),
    )


def frozen_input_paths(output_root: Path, run_id: ArtifactId) -> ControlledOperationInputPaths:
    root = output_root / str(run_id) / "input-freeze"
    return ControlledOperationInputPaths(
        trading_calendar=_one_directory(root / "trading-calendar"),
        operational_universe=_one_directory(root / "operational-universe"),
        daily_source_stage=_one_directory(root / "daily-source-stage"),
        daily_source_manifest=_one_directory(root / "daily-source-manifest"),
        supplemental_research_evidence=_one_directory(root / "supplemental-research-evidence"),
        runtime_configuration=_one_directory(root / "runtime-configuration"),
    )


def load_snapshot(
    journal: DecisionTimeOperationJournal, run_id: str
) -> DecisionTimeOperationRunSnapshot:
    return journal.get(ArtifactId(run_id))


def operation_payload(
    value: ControlledOperationPreparation | ControlledOperationDecisionResult | ControlledOperationSettlementResult,
) -> dict[str, Any]:
    snapshot = value.snapshot
    command = snapshot.command
    result: dict[str, Any] = {
        "status": snapshot.status.value,
        "run_id": str(command.run_id),
        "decision_date": command.decision_date.isoformat(),
        "decision_time": command.decision_time.isoformat().replace("+00:00", "Z"),
        "deadline_status": "NOT_EVALUATED",
        "universe_count": 0,
        "candidate_count": 0,
        "minute_success_count": 0,
        "minute_failure_count": 0,
        "signal_state_counts": {},
        "package_id": None,
        "package_hash": None,
        "outcome_status": snapshot.status.value,
        "limitations": list(command.limitations),
        **safety_declarations(),
    }
    if isinstance(value, ControlledOperationPreparation):
        result["universe_count"] = len(value.universe.symbols)
        result["limitations"] = list(value.static_bundle.limitations)
    elif isinstance(value, ControlledOperationDecisionResult):
        result.update(_package_payload(value.package))
    else:
        result.update(_package_payload(value.package))
        result["outcome_observation_count"] = len(value.outcome.observations)
        result["longitudinal_index_status"] = value.longitudinal_record.outcome_status
    return result


def _package_payload(package: Any) -> dict[str, Any]:
    return {
        "deadline_status": package.deadline_status,
        "universe_count": package.universe_count,
        "candidate_count": package.candidate_count,
        "minute_success_count": package.minute_success_count,
        "minute_failure_count": package.minute_failure_count,
        "signal_state_counts": dict(package.signal_state_counts),
        "package_id": str(package.package_id),
        "package_hash": package.content_hash,
        "outcome_status": package.status.value,
        "limitations": list(package.limitations),
    }


def safety_declarations() -> dict[str, bool]:
    return {
        "NO_ORDER_CREATED": True,
        "BROKER_NOT_INVOKED": True,
        "NO_FILL_CREATED": True,
        "ENTRY_MODEL_EMPIRICALLY_VALIDATED_FALSE": True,
        "FORMAL_OOS_ALPHA_NOT_ESTABLISHED": True,
    }


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=True, sort_keys=True))


def emit_error(
    *,
    status: str,
    reason_code: str,
    exc: Exception,
    run_id: str | None = None,
) -> None:
    emit(
        {
            "status": status,
            "reason_code": reason_code,
            "error": f"{type(exc).__name__}:{exc}",
            "run_id": run_id,
            "limitations": ["CONTROLLED_OPERATION_FAILED_CLOSED"],
            **safety_declarations(),
        }
    )


def repository_exception(exc: Exception) -> bool:
    return isinstance(
        exc,
        (psycopg.Error, PostgresConnectionUnavailable, OSError),
    )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _one_directory(root: Path) -> Path:
    if not root.is_dir():
        raise ControlledCLIError(f"frozen input directory is missing: {root}")
    values = tuple(item for item in root.iterdir() if item.is_dir())
    if len(values) != 1:
        raise ControlledCLIError(f"frozen input identity is ambiguous: {root}")
    return values[0]


def _date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ControlledCLIError("decision date must be YYYY-MM-DD") from exc


__all__ = [
    "ControlledCLIError",
    "ControlledExitCode",
    "StructuredParser",
    "add_repository_arguments",
    "command_from_prepare_args",
    "emit",
    "emit_error",
    "frozen_input_paths",
    "input_paths_from_prepare_args",
    "load_snapshot",
    "operation_payload",
    "repository_exception",
    "repository_paths",
    "runner_and_journal",
    "safety_declarations",
]
