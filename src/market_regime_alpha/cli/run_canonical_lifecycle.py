"""Run or resume the canonical backend lifecycle without execution authority."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys
from typing import Any, NoReturn, Sequence, cast

from market_regime_alpha.application.canonical_lifecycle.commands import (
    CanonicalLifecycleCommand,
)
from market_regime_alpha.application.canonical_lifecycle.contracts import (
    LifecycleConfigurationKind,
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
)
from market_regime_alpha.application.canonical_lifecycle.replay import (
    LifecycleReplayStatus,
    verify_lifecycle_replay,
)
from market_regime_alpha.application.canonical_lifecycle.runner import (
    CanonicalDecisionLifecycleRunner,
    LifecycleRunResult,
    LifecycleStageExecutionError,
)
from market_regime_alpha.application.canonical_lifecycle.runtime_configuration import (
    RuntimeConfigurationReader,
    RuntimeConfigurationSet,
)
from market_regime_alpha.application.canonical_lifecycle.sqlite_repository import (
    SQLiteLifecycleRunRepository,
)
from market_regime_alpha.application.canonical_lifecycle.stages.contracts import (
    LifecycleStageHandler,
)
from market_regime_alpha.application.canonical_lifecycle.stages.evidence import (
    VerifiedCompositeEvidenceStageHandler,
)
from market_regime_alpha.application.canonical_lifecycle.stages.assessment import (
    ExitAssessmentStageHandler,
    HoldingAssessmentStageHandler,
    OutcomeReviewStageHandler,
    ThesisHealthStageHandler,
)
from market_regime_alpha.application.canonical_lifecycle.stages.decision_risk import (
    OpportunityStageHandler,
    PortfolioRiskStageHandler,
    ThesisStageHandler,
)
from market_regime_alpha.application.canonical_lifecycle.stages.execution_position import (
    FillPositionStageHandler,
    ManualConfirmationStageHandler,
    ManualTradeStageHandler,
)
from market_regime_alpha.application.canonical_lifecycle.stages.research import (
    PlatformResearchStageHandler,
)
from market_regime_alpha.application.canonical_lifecycle.stages.risk_reduction import (
    RiskReductionStageHandler,
)
from market_regime_alpha.application.canonical_lifecycle.stages.signal_forecast import (
    EntryAssessmentStageHandler,
    PathForecastStageHandler,
    SignalStageHandler,
)
from market_regime_alpha.application.canonical_lifecycle.stages.unavailable import (
    UnavailableLifecycleStageHandler,
)
from market_regime_alpha.application.canonical_lifecycle.states import (
    LIFECYCLE_STAGE_ORDER,
    LifecycleRunStatus,
    LifecycleRunType,
    LifecycleStageName,
)
from market_regime_alpha.forecasting.path import PathForecastConfig
from market_regime_alpha.application.operational_research.sqlite_composite_repository import (
    SQLiteCompositeOperationalRepository,
)
from market_regime_alpha.application.trading_lifecycle.sqlite_risk_reduction import (
    SQLiteRiskReductionManualIntentRepository,
)
from market_regime_alpha.decision.sqlite_repository import (
    SQLiteDecisionLifecycleRepository,
)
from market_regime_alpha.portfolio.sqlite_account_authority import (
    SQLiteCompleteAccountPortfolioRiskRepository,
)
from market_regime_alpha.portfolio.sqlite_risk_routes import (
    SQLiteRiskRouteRepository,
)
from market_regime_alpha.position.sqlite_thesis_health import (
    SQLiteThesisHealthRepository,
)
from market_regime_alpha.research.platform_v2.configs import ResearchPipelineConfig
from market_regime_alpha.signals.engine import SignalModelConfig


EXIT_SUCCESS = 0
EXIT_RUNTIME_FAILED = 1
EXIT_VALIDATION_ERROR = 2
EXIT_IDEMPOTENCY_CONFLICT = 3
EXIT_JOURNAL_ERROR = 4
EXIT_REPLAY_NOT_COMPARABLE = 5
EXIT_REPLAY_FAILED = 6


class CLIValidationError(ValueError):
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
    except CLIValidationError as exc:
        _print_error("COMMAND_VALIDATION_FAILED", exc, args=args)
        return EXIT_VALIDATION_ERROR
    except LifecycleIdempotencyConflict as exc:
        _print_error("IDEMPOTENCY_KEY_CONFLICT", exc, args=args)
        return EXIT_IDEMPOTENCY_CONFLICT
    except LifecycleStageExecutionError as exc:
        repository = _repository_from_args(args)
        if repository is None:
            _print_error("LIFECYCLE_STAGE_FAILED", exc, args=args)
        else:
            _print_history_failure(repository, exc)
        return EXIT_RUNTIME_FAILED
    except LifecycleRepositoryError as exc:
        _print_error("LIFECYCLE_JOURNAL_ERROR", exc, args=args)
        return EXIT_JOURNAL_ERROR
    except (OSError, TypeError, ValueError) as exc:
        _print_error("COMMAND_VALIDATION_FAILED", exc, args=args)
        return EXIT_VALIDATION_ERROR

    print(json.dumps(_result_payload(result), ensure_ascii=True, sort_keys=True))
    return (
        EXIT_RUNTIME_FAILED
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
    repository = SQLiteLifecycleRunRepository(database)
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
                **_safety_declarations(),
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
    repository = SQLiteLifecycleRunRepository(database)
    runner = _runner(
        repository=repository,
        command=command,
        manifest=manifest,
        configurations=configurations,
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
        raise CLIValidationError("resume requires an existing lifecycle database")
    repository = SQLiteLifecycleRunRepository(database)
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
        raise CLIValidationError(
            "resume authority database must match the stored command binding"
        )
    if (
        command.authority_database_locator is not None
        and not command.authority_database_locator.is_file()
    ):
        raise CLIValidationError(
            "stored authority database binding is no longer available"
        )
    if (
        requested_output_directory is not None
        and requested_output_directory != command.output_directory
    ):
        raise CLIValidationError(
            "resume output directory must match the stored command"
        )
    manifest = _restore_command_manifest(command)
    configurations = RuntimeConfigurationReader().read_all(
        command.configuration_references
    )
    runner = _runner(
        repository=repository,
        command=command,
        manifest=manifest,
        configurations=configurations,
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


def _runner(
    *,
    repository: SQLiteLifecycleRunRepository,
    command: CanonicalLifecycleCommand,
    manifest: CanonicalLifecycleInputManifest | None,
    configurations: RuntimeConfigurationSet,
) -> CanonicalDecisionLifecycleRunner:
    handlers = _build_handlers(
        command=command,
        manifest=manifest,
        configurations=configurations,
    )
    return CanonicalDecisionLifecycleRunner(
        repository=repository,
        handlers=handlers,
        clock=_utc_now,
    )


def _build_handlers(
    *,
    command: CanonicalLifecycleCommand,
    manifest: CanonicalLifecycleInputManifest | None,
    configurations: RuntimeConfigurationSet,
) -> tuple[LifecycleStageHandler, ...]:
    output_root = command.output_directory
    research_configuration = configurations.get(
        LifecycleConfigurationKind.RESEARCH_PIPELINE
    )
    signal_configuration = configurations.get(
        LifecycleConfigurationKind.SIGNAL_MODEL
    )
    forecast_configuration = configurations.get(
        LifecycleConfigurationKind.PATH_FORECAST
    )

    handlers: dict[LifecycleStageName, LifecycleStageHandler] = {
        stage: _unavailable(
            stage,
            "COMMAND_BOUND_DOMAIN_REPOSITORY_UNAVAILABLE",
            (
                "the standalone CLI was not given an explicit authority mapping; "
                "no Repository, ManualTrade, Fill or Broker operation was inferred"
            ),
        )
        for stage in LIFECYCLE_STAGE_ORDER
    }
    handlers[LifecycleStageName.VERIFY_COMPOSITE_EVIDENCE] = (
        VerifiedCompositeEvidenceStageHandler()
    )
    if isinstance(research_configuration, ResearchPipelineConfig):
        handlers[LifecycleStageName.PLATFORM_RESEARCH] = PlatformResearchStageHandler(
            configuration=research_configuration,
            output_root=output_root / "platform-research",
        )
    else:
        handlers[LifecycleStageName.PLATFORM_RESEARCH] = _unavailable(
            LifecycleStageName.PLATFORM_RESEARCH,
            "RESEARCH_PIPELINE_CONFIGURATION_UNAVAILABLE",
            "no command-bound RESEARCH_PIPELINE configuration was supplied",
        )
    if isinstance(signal_configuration, SignalModelConfig):
        handlers[LifecycleStageName.SIGNAL] = SignalStageHandler(
            configuration=signal_configuration,
            output_root=output_root / "signals",
        )
    else:
        handlers[LifecycleStageName.SIGNAL] = _unavailable(
            LifecycleStageName.SIGNAL,
            "SIGNAL_MODEL_CONFIGURATION_UNAVAILABLE",
            "no command-bound SIGNAL_MODEL configuration was supplied",
        )
    if isinstance(forecast_configuration, PathForecastConfig):
        handlers[LifecycleStageName.PATH_FORECAST] = PathForecastStageHandler(
            configuration=forecast_configuration,
            output_root=output_root / "path-forecasts",
        )
    else:
        handlers[LifecycleStageName.PATH_FORECAST] = _unavailable(
            LifecycleStageName.PATH_FORECAST,
            "PATH_FORECAST_CONFIGURATION_UNAVAILABLE",
            "no command-bound PATH_FORECAST configuration was supplied",
        )
    if manifest is not None:
        handlers[LifecycleStageName.ENTRY_ASSESSMENT] = EntryAssessmentStageHandler(
            authority_ceiling=manifest.authority_ceiling
        )
    if command.authority_database_locator is not None:
        authority_path = command.authority_database_locator
        decision_repository = SQLiteDecisionLifecycleRepository(authority_path)
        portfolio_repository = SQLiteCompleteAccountPortfolioRiskRepository(
            authority_path
        )
        risk_repository = SQLiteRiskRouteRepository(authority_path)
        execution_repository = SQLiteRiskReductionManualIntentRepository(
            authority_path
        )
        thesis_health_repository = SQLiteThesisHealthRepository(authority_path)
        composite_repository = SQLiteCompositeOperationalRepository(authority_path)
        handlers[LifecycleStageName.OPPORTUNITY] = OpportunityStageHandler(
            repository=decision_repository
        )
        handlers[LifecycleStageName.THESIS] = ThesisStageHandler(
            repository=decision_repository
        )
        handlers[LifecycleStageName.PORTFOLIO_RISK] = PortfolioRiskStageHandler(
            repository=portfolio_repository
        )
        handlers[LifecycleStageName.RISK_REDUCTION] = RiskReductionStageHandler(
            risk_repository=risk_repository,
            execution_repository=execution_repository,
            decision_repository=decision_repository,
            thesis_health_repository=thesis_health_repository,
            composite_repository=composite_repository,
        )
        handlers[LifecycleStageName.MANUAL_CONFIRMATION] = (
            ManualConfirmationStageHandler(repository=execution_repository)
        )
        handlers[LifecycleStageName.MANUAL_TRADE] = ManualTradeStageHandler(
            repository=execution_repository
        )
        handlers[LifecycleStageName.FILL_POSITION] = FillPositionStageHandler(
            repository=execution_repository
        )
        handlers[LifecycleStageName.THESIS_HEALTH] = ThesisHealthStageHandler(
            repository=thesis_health_repository
        )
        handlers[LifecycleStageName.HOLDING_ASSESSMENT] = (
            HoldingAssessmentStageHandler()
        )
        handlers[LifecycleStageName.EXIT_ASSESSMENT] = ExitAssessmentStageHandler()
        handlers[LifecycleStageName.OUTCOME_REVIEW] = OutcomeReviewStageHandler()
    return tuple(handlers[stage] for stage in LIFECYCLE_STAGE_ORDER)


def _unavailable(
    stage: LifecycleStageName,
    reason_code: str,
    detail: str,
) -> UnavailableLifecycleStageHandler:
    return UnavailableLifecycleStageHandler(
        stage_name=stage,
        reason_code=reason_code,
        detail=detail,
    )


def _result_payload(result: LifecycleRunResult) -> dict[str, Any]:
    manual_trade_observed = any(
        reference.object_type.value == "MANUAL_TRADE"
        for stage in result.stages
        for reference in stage.output_references
    )
    return {
        "run_id": str(result.run.run_id),
        "run_type": result.run.run_type.value,
        "command_hash": result.run.command_hash,
        "status": result.run.status.value,
        "current_stage": (
            result.run.current_stage.value if result.run.current_stage else None
        ),
        "completed_stages": [item.value for item in result.run.completed_stages],
        "stage_statuses": {
            item.stage_name.value: item.stage_status.value for item in result.stages
        },
        "receipt_ids": [str(item.receipt_id) for item in result.receipts],
        "receipt_hashes": [item.receipt_hash for item in result.receipts],
        "attempted_stages": [item.value for item in result.attempted_stages],
        "recovered_stages": [item.value for item in result.recovered_stages],
        "stopped_after_stage": (
            result.stopped_after_stage.value
            if result.stopped_after_stage is not None
            else None
        ),
        "blocker_reason": result.run.blocker_reason,
        "failure_reason": result.run.failure_reason,
        "manual_trade_observed": manual_trade_observed,
        "MANUAL_CONFIRMATION_REQUIRED": (
            result.run.status
            is LifecycleRunStatus.WAITING_FOR_MANUAL_CONFIRMATION
        ),
        "MANUAL_TRADE_CREATED": False,
        **_safety_declarations(),
    }


def _print_history_failure(
    repository: SQLiteLifecycleRunRepository,
    exc: LifecycleStageExecutionError,
) -> None:
    try:
        history = repository.history(exc.run_id)
    except (
        LifecycleRepositoryError,
        OSError,
        sqlite3.Error,
        TypeError,
        ValueError,
    ):
        _print_error("LIFECYCLE_STAGE_FAILED", exc, args=None)
        return
    payload = {
        "run_id": str(history.run.run_id),
        "run_type": history.run.run_type.value,
        "command_hash": history.run.command_hash,
        "status": history.run.status.value,
        "current_stage": (
            history.run.current_stage.value if history.run.current_stage else None
        ),
        "completed_stages": [item.value for item in history.run.completed_stages],
        "blocker_reason": history.run.blocker_reason,
        "failure_reason": history.run.failure_reason,
        "error": str(exc),
        "reason_codes": ["LIFECYCLE_STAGE_FAILED"],
        "MANUAL_CONFIRMATION_REQUIRED": (
            history.run.status
            is LifecycleRunStatus.WAITING_FOR_MANUAL_CONFIRMATION
        ),
        "MANUAL_TRADE_CREATED": False,
        **_safety_declarations(),
    }
    print(json.dumps(payload, ensure_ascii=True, sort_keys=True))


def _print_error(
    reason_code: str,
    exc: Exception,
    *,
    args: argparse.Namespace | None,
) -> None:
    print(
        json.dumps(
            {
                "run_id": (
                    getattr(args, "resume_run_id", None) if args is not None else None
                ),
                "status": "REJECTED",
                "current_stage": None,
                "completed_stages": [],
                "blocker_reason": str(exc),
                "failure_reason": None,
                "error": str(exc),
                "reason_codes": [reason_code],
                "MANUAL_CONFIRMATION_REQUIRED": False,
                "MANUAL_TRADE_CREATED": False,
                **_safety_declarations(),
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )


def _safety_declarations() -> dict[str, bool]:
    return {
        "NO_ORDER_CREATED": True,
        "BROKER_NOT_INVOKED": True,
        "NO_FILL_CREATED": True,
        "automatic_order_execution": False,
        "broker_integration_proven": False,
        "entry_model_empirically_validated": False,
        "production_ready": False,
    }


def _repository_from_args(
    args: argparse.Namespace | None,
) -> SQLiteLifecycleRunRepository | None:
    if args is None:
        return None
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
    try:
        return SQLiteLifecycleRunRepository(database)
    except (OSError, sqlite3.Error, TypeError, ValueError):
        return None


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


if __name__ == "__main__":
    sys.exit(main())
