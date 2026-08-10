"""Bounded PostgreSQL administration for Continuous Research runs."""

from __future__ import annotations

import argparse
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
import json
from pathlib import Path
import time as wall_time
from typing import Any, Mapping, Sequence

from market_regime_alpha.application.continuous_research.contracts import (
    ContinuousResearchCommand,
    RuntimeTickCommand,
)
from market_regime_alpha.application.continuous_research.composition import (
    FreeDataPreparationInvocation,
)
from market_regime_alpha.application.continuous_research.free_data_runtime import (
    CanonicalFreeDataProvider,
    CanonicalFreeDataResearchComposition,
    ControlledRuntimeModelSelector,
)
from market_regime_alpha.application.continuous_research.policy import (
    ContinuousSessionPhase,
    default_continuous_decision_window_policy,
)
from market_regime_alpha.application.continuous_research.postgres_journal import (
    PostgresContinuousResearchJournal,
)
from market_regime_alpha.application.continuous_research.replay import (
    replay_continuous_research,
)
from market_regime_alpha.application.continuous_research.report import (
    build_continuous_research_report,
)
from market_regime_alpha.application.continuous_research.scheduler import (
    ContinuousResearchScheduleRunner,
    TradingDayAssessment,
)
from market_regime_alpha.application.continuous_research.runner import (
    ContinuousResearchTickRunner,
)
from market_regime_alpha.application.continuous_research.runtime_authority_evidence import (
    PostgresRuntimeAuthorityEvidenceRepository,
    RuntimeAuthorityEvidence,
)
from market_regime_alpha.application.continuous_research.ports import (
    ProviderAcquisitionRequest,
)
from market_regime_alpha.application.controlled_operation.input_artifacts import (
    load_controlled_runtime_configuration,
)
from market_regime_alpha.application.free_data_operation.contracts import (
    FreeDataInstrument,
    FreeDataOperationScale,
    FreeDataPreparationRequest,
)
from market_regime_alpha.application.free_data_operation.blocked import (
    FreeDataOperationBlocked,
)
from market_regime_alpha.application.free_data_operation.service import (
    FreeDataOperationService,
)
from market_regime_alpha.application.free_data_operation.research_universe import (
    FreeResearchUniverseOperator,
)
from market_regime_alpha.application.research_validation.free_historical_samples import (
    AShareBarProviderReader,
    FreeHistoricalSampleBuildResult,
    FreeHistoricalSamplePipeline,
)
from market_regime_alpha.application.research_validation.postgres_repository import (
    PostgresResearchValidationRepository,
)
from market_regime_alpha.application.runtime_operations.observability import (
    PostgresRuntimeObservability,
)
from market_regime_alpha.application.runtime_operations.preflight import (
    CanonicalRuntimePreflight,
    RuntimePreflightRequest,
)
from market_regime_alpha.application.runtime_operations.query import (
    PostgresCanonicalRuntimeQuery,
)
from market_regime_alpha.application.runtime_operations.recovery_audit import (
    PostgresRecoveryAudit,
)
from market_regime_alpha.application.shadow_research.attestation import (
    ClockMode,
    RuntimeOrigin,
)
from market_regime_alpha.application.shadow_research.operations import (
    ResearchShadowOperations,
)
from market_regime_alpha.application.shadow_research.free_data_settlement import (
    FreeDataSettlementOperator,
)
from market_regime_alpha.application.strategy_shadow.operator import (
    StrategyDayObservation,
    StrategyShadowDayOperator,
)
from market_regime_alpha.application.strategy_shadow.portfolio_operator import (
    PortfolioShadowDayInput,
    PortfolioShadowDayOperator,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.core.time import DecisionTime
from market_regime_alpha.data.providers.public_composite import (
    BaoStockFreeSupplementalClient,
    BaoStockHistoryClient,
    BaoStockSecurityStatusClient,
    TENCENT_FREE_OPERATIONAL_PROFILE_ID,
    TencentCurrentQuoteClient,
    TencentFreeOperationalProfile,
)
from market_regime_alpha.data.free_operational_policy import (
    canonical_free_operational_evidence_policy,
)
from market_regime_alpha.data_sources.a_share_bars import (
    AShareDataError,
    BaoStockADataProvider,
)
from market_regime_alpha.forecasting.sample_provider import (
    HistoricalRegistryPathForecastSampleProvider,
)
from market_regime_alpha.market_data import AssetType
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.settings import DatabaseSettings
from market_regime_alpha.persistence.repository_factory import RepositoryFactory
from market_regime_alpha.platform.runtime_governance import RuntimeAuthorityMode
from zoneinfo import ZoneInfo


SUCCESS = 0
ARGUMENT_ERROR = 2
DATABASE_ERROR = 3
_SHANGHAI = ZoneInfo("Asia/Shanghai")
_INSPECT_OPERATIONS = (
    "inspect-trading-date",
    "inspect-run",
    "inspect-tick",
    "inspect-provider",
    "inspect-evidence",
    "inspect-state",
    "inspect-pool",
    "inspect-candidate",
    "inspect-minute",
    "inspect-model-selection",
    "inspect-summary",
    "trace",
    "metrics",
)


def _add_run_arguments(command: argparse.ArgumentParser) -> None:
    command.add_argument("--run-command", type=Path, required=True)
    command.add_argument("--trading-day-assessment", type=Path, required=True)
    command.add_argument("--runtime-configuration", type=Path, required=True)
    command.add_argument("--output-root", type=Path, required=True)
    command.add_argument("--at", required=True)
    command.add_argument(
        "--runtime-clock-mode",
        choices=("LIVE", "SIMULATED"),
        default="LIVE",
        help="LIVE binds host/PostgreSQL clocks; SIMULATED is explicit engineering/replay.",
    )
    command.add_argument(
        "--supplemental-evidence",
        type=Path,
        help="Explicit immutable Free Supplemental Evidence bundle; no discovery/fallback.",
    )
    command.add_argument("--minimum-history-sessions", type=int, default=21)
    command.add_argument("--liquidity-lookback-sessions", type=int, default=21)
    command.add_argument(
        "--minimum-median-daily-amount",
        type=Decimal,
        default=Decimal("10000000"),
    )
    command.add_argument("--provider-timeout-seconds", type=float, default=8.0)
    command.add_argument("--historical-sample-lookback-calendar-days", type=int, default=180)
    command.add_argument("--historical-sample-maximum-per-symbol", type=int, default=60)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        help="Explicit PostgreSQL authority; environment fallback is disabled.",
    )
    parser.add_argument(
        "--application-schema",
        default="market_regime_alpha",
        help="Explicit lowercase PostgreSQL schema authority.",
    )
    subparsers = parser.add_subparsers(dest="operation", required=True)
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--run-command", type=Path, required=True)
    admit = subparsers.add_parser("admit-tick")
    admit.add_argument("--tick-command", type=Path, required=True)
    admit.add_argument(
        "--session-phase",
        choices=tuple(item.value for item in ContinuousSessionPhase),
        required=True,
    )
    schedule = subparsers.add_parser("schedule")
    schedule.add_argument("--run-command", type=Path, required=True)
    schedule.add_argument("--trading-day-assessment", type=Path, required=True)
    schedule.add_argument("--at", required=True)
    reserve = subparsers.add_parser("reserve-due-tick")
    reserve.add_argument("--run-command", type=Path, required=True)
    reserve.add_argument("--at", required=True)
    for name, help_text in (
        ("run-due", "Execute one due BaoStock/Tencent Canonical Runtime Tick."),
        ("run-day", "Execute the same Canonical Tick and attach/freeze Research Shadow when in SHADOW mode."),
    ):
        run_command = subparsers.add_parser(name, help=help_text)
        _add_run_arguments(run_command)
    strategy_day = subparsers.add_parser(
        "strategy-day",
        help="Run Entry Research through Strategy Shadow Outcome from PostgreSQL lineage.",
    )
    strategy_day.add_argument("--observations", type=Path, required=True)
    settle_day = subparsers.add_parser(
        "settle-day",
        help="Acquire free T+1 evidence, settle Research Shadow and build Panel V2 enrichment.",
    )
    settle_day.add_argument("--trading-date", required=True)
    settle_day.add_argument("--next-session-date", required=True)
    settle_day.add_argument("--artifact-root", type=Path, required=True)
    settle_day.add_argument("--at", required=True)
    strategy_replay = subparsers.add_parser("strategy-replay")
    strategy_replay.add_argument("--session-id", required=True)
    portfolio_day = subparsers.add_parser(
        "portfolio-shadow-day",
        help="Append one PostgreSQL-owned A-share Portfolio Shadow day.",
    )
    portfolio_day.add_argument("--observations", type=Path, required=True)
    portfolio_replay = subparsers.add_parser("portfolio-shadow-replay")
    portfolio_replay.add_argument("--portfolio-id", required=True)
    universe_sync = subparsers.add_parser("research-universe-sync")
    universe_sync.add_argument("--as-of-date", required=True)
    universe_sync.add_argument("--artifact-root", type=Path, required=True)
    universe_replay = subparsers.add_parser("research-universe-replay")
    universe_replay.add_argument("--snapshot-id", required=True)
    report_day = subparsers.add_parser("report-day")
    report_day.add_argument("--trading-date", required=True)
    report_day.add_argument("--at", required=True)
    replay_day = subparsers.add_parser("replay-day")
    replay_day.add_argument("--trading-date", required=True)
    recovery_audit = subparsers.add_parser("recovery-audit")
    recovery_audit.add_argument("--checked-at", required=True)
    preflight = subparsers.add_parser("preflight", help="Inspect engineering readiness without executing a Tick.")
    preflight.add_argument("--trading-date", required=True)
    preflight.add_argument(
        "--runtime-mode",
        choices=tuple(item.value for item in RuntimeAuthorityMode),
        required=True,
    )
    preflight.add_argument("--provider-profile-id", required=True)
    preflight.add_argument("--operational-policy-effective-from", required=True)
    preflight.add_argument("--artifact-root", type=Path, required=True)
    preflight.add_argument("--runtime-configuration", type=Path, required=True)
    preflight.add_argument("--trading-calendar", type=Path, required=True)
    preflight.add_argument("--run-id")
    preflight.add_argument("--minimum-free-bytes", type=int, default=1_000_000_000)
    preflight.add_argument("--maximum-clock-skew-seconds", type=float, default=5.0)
    for operation in _INSPECT_OPERATIONS:
        command = subparsers.add_parser(operation)
        if operation == "inspect-trading-date":
            command.add_argument("--trading-date", required=True)
        else:
            command.add_argument("--run-id", required=True)
        if operation == "inspect-tick":
            command.add_argument("--tick-id", required=True)
        if operation == "inspect-provider":
            command.add_argument("--attempt-id", type=int)
    for operation in ("resume", "report", "replay"):
        command = subparsers.add_parser(operation)
        command.add_argument("--run-id", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    factory: PostgresConnectionFactory | None = None
    try:
        args = build_parser().parse_args(argv)
        if args.database_url is None:
            raise ValueError("explicit --database-url is required")
        settings = DatabaseSettings.from_sources(
            database_url=args.database_url,
            environ={},
        )
        factory = PostgresConnectionFactory(settings, application_schema=args.application_schema)
        read_only = args.operation in {
            "preflight",
            "report",
            "replay",
            "replay-day",
            "research-universe-replay",
            "portfolio-shadow-replay",
            "recovery-audit",
            *_INSPECT_OPERATIONS,
        }
        journal = PostgresContinuousResearchJournal(factory, apply_migrations=not read_only)
        output = (
            _run_due(args, settings, factory, journal)
            if args.operation == "run-due"
            else _run_day(args, settings, factory, journal)
            if args.operation == "run-day"
            else _dispatch(args, journal, factory)
        )
        _emit(output)
        return SUCCESS
    except FreeDataOperationBlocked as exc:
        _emit_error("FREE_DATA_EVIDENCE_BLOCKED", exc)
        return DATABASE_ERROR
    except AShareDataError as exc:
        _emit_error("FREE_DATA_PROVIDER_FAILED", exc)
        return DATABASE_ERROR
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        _emit_error("ARGUMENT_OR_IDENTITY_INVALID", exc)
        return ARGUMENT_ERROR
    except Exception as exc:
        _emit_error("POSTGRESQL_OPERATION_FAILED", exc)
        return DATABASE_ERROR
    finally:
        if factory is not None:
            factory.close()


def _dispatch(
    args: argparse.Namespace,
    journal: PostgresContinuousResearchJournal,
    factory: PostgresConnectionFactory,
) -> dict[str, Any]:
    if args.operation == "strategy-day":
        return StrategyShadowDayOperator(factory).run(
            StrategyDayObservation.from_canonical_dict(
                _load_json_object(args.observations)
            )
        )
    if args.operation == "settle-day":
        return FreeDataSettlementOperator(
            factory,
            clock=lambda: _instant(args.at),
        ).settle_day(
            trading_date=date.fromisoformat(args.trading_date),
            next_session_date=date.fromisoformat(args.next_session_date),
            artifact_root=args.artifact_root.resolve(),
        )
    if args.operation == "strategy-replay":
        return StrategyShadowDayOperator(factory).replay(
            ArtifactId(args.session_id)
        )
    if args.operation == "portfolio-shadow-day":
        return PortfolioShadowDayOperator(factory).run(
            PortfolioShadowDayInput.from_canonical_dict(
                _load_json_object(args.observations)
            )
        )
    if args.operation == "portfolio-shadow-replay":
        return PortfolioShadowDayOperator(factory).replay(
            ArtifactId(args.portfolio_id)
        )
    if args.operation == "research-universe-sync":
        return FreeResearchUniverseOperator(factory).sync(
            as_of_date=date.fromisoformat(args.as_of_date),
            artifact_root=args.artifact_root.resolve(),
        )
    if args.operation == "research-universe-replay":
        return FreeResearchUniverseOperator(factory).replay(
            ArtifactId(args.snapshot_id)
        )
    if args.operation == "recovery-audit":
        return PostgresRecoveryAudit(factory).inspect(
            checked_at=_instant(args.checked_at)
        ).to_canonical_dict()
    if args.operation == "report-day":
        trading_date = date.fromisoformat(args.trading_date)
        runtime = PostgresCanonicalRuntimeQuery(factory).inspect_trading_date(
            trading_date
        )
        with factory.connection(read_only=True) as connection:
            shadow_rows = connection.execute(
                """
                SELECT session_id
                FROM shadow_research_session
                WHERE trading_date = %s
                ORDER BY session_id
                """,
                (trading_date,),
            ).fetchall()
            portfolio_rows = connection.execute(
                """
                SELECT portfolio_id, state_id, sequence, cash, nav,
                       gross_exposure, turnover, drawdown, total_cost
                FROM strategy_shadow_portfolio_day
                WHERE trading_date = %s
                ORDER BY portfolio_id
                """,
                (trading_date,),
            ).fetchall()
        research_reports = [
            ResearchShadowOperations(factory).report(ArtifactId(str(row[0])))
            for row in shadow_rows
        ]
        strategy_report = StrategyShadowDayOperator(factory).report_day(
            trading_date,
            generated_at=_instant(args.at),
        )
        return {
            "operation": "REPORT_DAY",
            "trading_date": trading_date.isoformat(),
            "runtime": runtime,
            "research_shadow": research_reports,
            "strategy_shadow": strategy_report,
            "portfolio_shadow": [
                {
                    "portfolio_id": str(row[0]),
                    "state_id": str(row[1]),
                    "sequence": int(row[2]),
                    "cash": str(row[3]),
                    "nav": str(row[4]),
                    "gross_exposure": str(row[5]),
                    "turnover": str(row[6]),
                    "drawdown": str(row[7]),
                    "total_cost": str(row[8]),
                    "shadow_fill_is_real_fill": False,
                    "shadow_position_is_real_position": False,
                }
                for row in portfolio_rows
            ],
            **_authority_ceiling(),
        }
    if args.operation == "replay-day":
        trading_date = date.fromisoformat(args.trading_date)
        with factory.connection(read_only=True) as connection:
            run_rows = connection.execute(
                "SELECT run_id FROM continuous_research_run WHERE trading_date = %s ORDER BY run_id",
                (trading_date,),
            ).fetchall()
            decision_rows = connection.execute(
                """
                SELECT decision.decision_id
                FROM shadow_research_decision AS decision
                JOIN shadow_research_session AS session
                  ON session.session_id = decision.session_id
                WHERE session.trading_date = %s
                ORDER BY decision.decision_id
                """,
                (trading_date,),
            ).fetchall()
            portfolio_rows = connection.execute(
                """
                SELECT portfolio_id FROM strategy_shadow_portfolio_day
                WHERE trading_date = %s ORDER BY portfolio_id
                """,
                (trading_date,),
            ).fetchall()
        research = ResearchShadowOperations(factory)
        strategy_operator = StrategyShadowDayOperator(factory)
        strategy_sessions = strategy_operator.list_sessions(trading_date)
        portfolio_operator = PortfolioShadowDayOperator(factory)
        return {
            "operation": "REPLAY_DAY",
            "trading_date": trading_date.isoformat(),
            "continuous_runtime": [
                replay_continuous_research(journal, ArtifactId(str(row[0]))).to_canonical_dict()
                for row in run_rows
            ],
            "research_shadow": [
                research.replay(ArtifactId(str(row[0]))).to_canonical_dict()
                for row in decision_rows
            ],
            "strategy_shadow": [
                strategy_operator.replay(item.session_id) for item in strategy_sessions
            ],
            "portfolio_shadow": [
                portfolio_operator.replay(ArtifactId(str(row[0])))
                for row in portfolio_rows
            ],
            **_authority_ceiling(),
        }
    if args.operation == "preflight":
        report = CanonicalRuntimePreflight(factory).inspect(
            RuntimePreflightRequest(
                trading_date=date.fromisoformat(args.trading_date),
                runtime_mode=RuntimeAuthorityMode(args.runtime_mode),
                provider_profile_id=args.provider_profile_id,
                operational_policy_effective_from=date.fromisoformat(args.operational_policy_effective_from),
                artifact_root=args.artifact_root,
                runtime_configuration_path=args.runtime_configuration,
                trading_calendar_path=args.trading_calendar,
                run_id=(None if args.run_id is None else ArtifactId(args.run_id)),
                minimum_free_bytes=args.minimum_free_bytes,
                maximum_clock_skew=timedelta(seconds=args.maximum_clock_skew_seconds),
            )
        )
        return {"operation": "PREFLIGHT", **report.to_canonical_dict()}
    if args.operation == "prepare":
        run_command = ContinuousResearchCommand.from_canonical_dict(_load_json_object(args.run_command))
        snapshot = journal.create_or_get(run_command)
        return {
            "status": snapshot.status.value,
            "operation": "PREPARE",
            "run_id": str(run_command.run_id),
            "command_hash": run_command.command_hash,
            **_authority_ceiling(),
        }
    if args.operation == "admit-tick":
        tick_command = RuntimeTickCommand.from_canonical_dict(_load_json_object(args.tick_command))
        tick = journal.admit_tick(
            tick_command,
            session_phase=ContinuousSessionPhase(args.session_phase),
        )
        return {
            "status": tick.status.value,
            "operation": "ADMIT_TICK",
            "run_id": str(tick_command.run_id),
            "tick_id": str(tick_command.tick_id),
            "tick_sequence": tick.tick_sequence,
            **_authority_ceiling(),
        }
    if args.operation == "schedule":
        schedule_command = ContinuousResearchCommand.from_canonical_dict(_load_json_object(args.run_command))
        trading_day = TradingDayAssessment.from_canonical_dict(_load_json_object(args.trading_day_assessment))
        journal.create_or_get(schedule_command)
        schedule = journal.initialize_schedule(
            run_command=schedule_command,
            policy=default_continuous_decision_window_policy(),
            trading_day=trading_day,
            initial_tick_at=_instant(args.at),
        )
        return {
            "operation": "SCHEDULE",
            **schedule.to_canonical_dict(),
            **_authority_ceiling(),
        }
    if args.operation == "reserve-due-tick":
        reserve_command = ContinuousResearchCommand.from_canonical_dict(_load_json_object(args.run_command))
        reserved_tick = journal.reserve_due_tick(
            run_command=reserve_command,
            policy=default_continuous_decision_window_policy(),
            now=_instant(args.at),
        )
        return {
            "operation": "RESERVE_DUE_TICK",
            "status": "NOT_DUE" if reserved_tick is None else "PENDING",
            "run_id": str(reserve_command.run_id),
            "tick_id": (None if reserved_tick is None else str(reserved_tick.command.tick_id)),
            "tick_sequence": (None if reserved_tick is None else reserved_tick.tick_sequence),
            **_authority_ceiling(),
        }
    if args.operation.startswith("inspect-"):
        query = PostgresCanonicalRuntimeQuery(factory)
        if args.operation == "inspect-trading-date":
            return query.inspect_trading_date(date.fromisoformat(args.trading_date))
        run_id = ArtifactId(args.run_id)
        if args.operation == "inspect-run":
            return {
                "operation": "INSPECT_RUN",
                **query.inspect_run(run_id).to_canonical_dict(),
            }
        if args.operation == "inspect-tick":
            return query.inspect_tick(run_id, ArtifactId(args.tick_id))
        if args.operation == "inspect-provider":
            return query.inspect_provider(run_id, attempt_id=args.attempt_id)
        operation_method = {
            "inspect-evidence": query.inspect_evidence,
            "inspect-state": query.inspect_state,
            "inspect-pool": query.inspect_pool,
            "inspect-candidate": query.inspect_candidate,
            "inspect-minute": query.inspect_minute,
            "inspect-model-selection": query.inspect_model_selection,
            "inspect-summary": query.inspect_summary,
        }[args.operation]
        return operation_method(run_id)
    run_id = ArtifactId(args.run_id)
    if args.operation in {"trace", "metrics"}:
        observability = PostgresRuntimeObservability(factory)
        return observability.trace_run(run_id) if args.operation == "trace" else observability.metrics(run_id)
    if args.operation == "resume":
        snapshot = journal.resume(run_id)
        return {
            "status": snapshot.status.value,
            "operation": "RESUME",
            "run_id": str(run_id),
            "tick_count": len(snapshot.ticks),
            **_authority_ceiling(),
        }
    if args.operation == "report":
        return build_continuous_research_report(journal, run_id)
    if args.operation == "replay":
        return replay_continuous_research(journal, run_id).to_canonical_dict()
    raise ValueError("unsupported Continuous Research operation")


def _run_due(
    args: argparse.Namespace,
    settings: DatabaseSettings,
    factory: PostgresConnectionFactory,
    journal: PostgresContinuousResearchJournal,
) -> dict[str, Any]:
    run_command = ContinuousResearchCommand.from_canonical_dict(_load_json_object(args.run_command))
    trading_day = TradingDayAssessment.from_canonical_dict(_load_json_object(args.trading_day_assessment))
    now = _instant(args.at).astimezone(UTC)
    operational_now = _operational_now()
    with factory.connection(read_only=True) as connection:
        row = connection.execute("SELECT clock_timestamp()").fetchone()
    if row is None or not isinstance(row[0], datetime):
        raise ValueError("PostgreSQL clock authority is unavailable")
    postgres_now = row[0].astimezone(UTC)
    if args.runtime_clock_mode == "LIVE" and (
        abs((now - operational_now).total_seconds()) > 5
        or abs((now - postgres_now).total_seconds()) > 5
        or abs((operational_now - postgres_now).total_seconds()) > 5
    ):
        raise ValueError("LIVE --at, host clock and PostgreSQL clock must agree within five seconds")
    configuration_path = args.runtime_configuration.resolve()
    configuration = load_controlled_runtime_configuration(configuration_path)
    if (
        run_command.research_configuration_id != configuration.configuration_id
        or run_command.research_configuration_hash != configuration.configuration_hash
    ):
        raise ValueError("run command does not bind Controlled configuration")
    decision = datetime.combine(
        run_command.trading_date,
        time(14, 55),
        tzinfo=_SHANGHAI,
    )
    decision_utc = decision.astimezone(UTC)
    free_request = FreeDataPreparationRequest(
        scale=FreeDataOperationScale.from_symbol_count(len(run_command.requested_symbols)),
        provider_profile_id=TENCENT_FREE_OPERATIONAL_PROFILE_ID,
        decision_time=DecisionTime(decision),
        created_at=now,
        code_revision=run_command.code_revision,
        instruments=tuple(FreeDataInstrument(symbol=symbol, asset_type=AssetType.A_SHARE) for symbol in run_command.requested_symbols),
        membership_source=(f"CANONICAL_FREE_DATA_{len(run_command.requested_symbols)}"),
        minimum_history_sessions=args.minimum_history_sessions,
        liquidity_lookback_sessions=args.liquidity_lookback_sessions,
        minimum_median_daily_amount=args.minimum_median_daily_amount,
        configuration_hash=configuration.configuration_hash,
    )
    repositories = RepositoryFactory(settings, postgres_factory=factory)
    repositories.bind_runtime("CONTINUOUS_RESEARCH", str(run_command.run_id))
    simulated_runtime_now = [now]

    def simulated_sleep(seconds: float) -> None:
        simulated_runtime_now[0] += timedelta(seconds=seconds)

    runtime_clock = _operational_now if args.runtime_clock_mode == "LIVE" else lambda: simulated_runtime_now[0]
    runtime_sleeper = wall_time.sleep if args.runtime_clock_mode == "LIVE" else simulated_sleep
    history_client = BaoStockHistoryClient(
        clock=runtime_clock,
        provider_profile_id=TENCENT_FREE_OPERATIONAL_PROFILE_ID,
    )
    canonical_supplemental_policy = canonical_free_operational_evidence_policy()
    supplemental_policy = (
        canonical_supplemental_policy
        if (
            args.runtime_clock_mode == "LIVE"
            and args.supplemental_evidence is None
            and run_command.trading_date >= min(item.effective_from for item in canonical_supplemental_policy.themes)
        )
        else None
    )
    profile = TencentFreeOperationalProfile(
        history_client=history_client,
        supplemental_client=(
            BaoStockFreeSupplementalClient(
                history_client=history_client,
                policy=supplemental_policy,
                provider_profile_id=TENCENT_FREE_OPERATIONAL_PROFILE_ID,
                clock=runtime_clock,
            )
            if supplemental_policy is not None
            else None
        ),
        security_status_client=BaoStockSecurityStatusClient(
            timeout_seconds=args.provider_timeout_seconds,
            clock=runtime_clock,
            provider_profile_id=TENCENT_FREE_OPERATIONAL_PROFILE_ID,
        ),
        current_client=TencentCurrentQuoteClient(
            timeout_seconds=args.provider_timeout_seconds,
            clock=runtime_clock,
            provider_profile_id=TENCENT_FREE_OPERATIONAL_PROFILE_ID,
        ),
    )
    # Every durable lease/receipt in one invocation must observe the same
    # trusted (LIVE) or explicitly simulated engineering clock.
    journal = PostgresContinuousResearchJournal(
        factory,
        clock=runtime_clock,
        lease_duration=timedelta(minutes=5),
        apply_migrations=False,
    )

    historical_sample_build: FreeHistoricalSampleBuildResult | None = None
    forecast_sample_provider = None
    validation_repository = None
    if run_command.authority_mode in {
        RuntimeAuthorityMode.RESEARCH,
        RuntimeAuthorityMode.SHADOW,
    }:
        validation_repository = PostgresResearchValidationRepository(
            factory,
            apply_migrations=False,
        )
        forecast_sample_provider = HistoricalRegistryPathForecastSampleProvider(
            validation_repository
        )

    service = FreeDataOperationService(
        repositories=repositories,
        output_root=args.output_root,
        code_revision=run_command.code_revision,
        clock=runtime_clock,
        live_profile=profile,
        sleeper=runtime_sleeper,
        forecast_sample_provider=forecast_sample_provider,
        operational_supplemental_policy=supplemental_policy,
    )
    policy = default_continuous_decision_window_policy()
    journal.create_or_get(run_command)
    schedule = journal.initialize_schedule(
        run_command=run_command,
        policy=policy,
        trading_day=trading_day,
        initial_tick_at=decision_utc,
    )
    if schedule.status.value == "NON_TRADING_DAY":
        return _run_due_stage_output(
            run_command=run_command,
            status="NON_TRADING_DAY",
            stage="NO_ACQUISITION",
            reason_codes=("ENTRY_BLOCKED", "NON_TRADING_DAY"),
        )
    local_now = now.astimezone(_SHANGHAI)
    if local_now.timetz().replace(tzinfo=None) < time(14, 54):
        service.prepare_static_sources(
            request=free_request,
            runtime_configuration_path=configuration_path,
        )
        return _run_due_stage_output(
            run_command=run_command,
            status="PREPARING",
            stage="BAOSTOCK_STATIC_SOURCES_FROZEN",
            reason_codes=(
                "BAOSTOCK_HISTORY_FROZEN",
                "BAOSTOCK_SECURITY_STATUS_FROZEN",
                "ENTRY_BLOCKED",
                "WAITING_FOR_TENCENT_DECISION_QUOTE",
            ),
        )

    if validation_repository is not None:
        historical_sample_build = FreeHistoricalSamplePipeline(
            reader=AShareBarProviderReader(BaoStockADataProvider()),
            repository=validation_repository,
            clock=runtime_clock,
            lookback_calendar_days=args.historical_sample_lookback_calendar_days,
            maximum_samples_per_symbol=args.historical_sample_maximum_per_symbol,
        ).build_and_register(
            symbols=run_command.requested_symbols,
            configuration=configuration.path_forecast,
            current_decision_time=DecisionTime(decision),
        )

    def invocation() -> FreeDataPreparationInvocation:
        return FreeDataPreparationInvocation(
            request=free_request,
            runtime_configuration_path=configuration_path,
            idempotency_key=f"{run_command.run_id}:free-data",
            supplemental_evidence_path=args.supplemental_evidence,
        )

    provider = CanonicalFreeDataProvider(
        service=service,
        invocation_builder=lambda _: invocation(),
        clock=runtime_clock,
    )
    children = CanonicalFreeDataResearchComposition(
        service=service,
        invocation_builder=lambda _: invocation(),
        model_selector=ControlledRuntimeModelSelector(repositories.model_governance()),
        summary_repository=repositories.decision_system(clock=runtime_clock),
        state_repository=repositories.state_system(clock=runtime_clock),
        clock=runtime_clock,
    )
    tick_runner = ContinuousResearchTickRunner(
        journal=journal,
        provider=provider,
        children=children,
        policy=policy,
        clock=runtime_clock,
    )

    def provider_request_builder(_: ContinuousResearchCommand, __: RuntimeTickCommand) -> ProviderAcquisitionRequest:
        return ProviderAcquisitionRequest(
            provider_id=TENCENT_FREE_OPERATIONAL_PROFILE_ID,
            product="BAOSTOCK_TENCENT_CANONICAL_FREE_DATA",
            request_hash=free_request.command_hash,
            provider_revision="canonical-free-data-profile-v1",
        )

    result = ContinuousResearchScheduleRunner(
        journal=journal,
        tick_runner=tick_runner,
        policy=policy,
        provider_request_builder=provider_request_builder,
    ).run_due_once(
        run_command=run_command,
        trading_day=trading_day,
        now=now,
        predecision_lead=timedelta(minutes=1),
    )
    summary_id = None
    summary_outcome = None
    if result.tick_result is not None:
        tick_id = result.tick_result.tick.command.tick_id
        PostgresRuntimeAuthorityEvidenceRepository(factory).record(
            RuntimeAuthorityEvidence.create(
                run_id=run_command.run_id,
                tick_id=tick_id,
                clock_mode=(ClockMode.LIVE_TRUSTED if args.runtime_clock_mode == "LIVE" else ClockMode.SIMULATED),
                runtime_origin=RuntimeOrigin.LIVE_ACQUISITION,
                clock_source=(
                    "POSTGRESQL_AND_SYSTEM_UTC_CLOCK" if args.runtime_clock_mode == "LIVE" else "EXPLICIT_SIMULATED_RUNTIME_CLOCK"
                ),
                origin_source="BAOSTOCK_TENCENT_CANONICAL_FREE_DATA",
                observed_at=(postgres_now if args.runtime_clock_mode == "LIVE" else now),
                recorded_at=(postgres_now if args.runtime_clock_mode == "LIVE" else max(postgres_now, now)),
                code_revision=run_command.code_revision,
            )
        )
        try:
            summary = repositories.decision_system().get_research_summary_for_tick(
                run_id=run_command.run_id,
                tick_id=tick_id,
                runtime_mode=run_command.authority_mode,
            )
        except (KeyError, ValueError):
            summary = None
        if summary is not None:
            summary_id = str(summary.summary_id)
            summary_outcome = summary.outcome.value
    return {
        "operation": "RUN_DUE",
        "status": result.status,
        "run_id": str(run_command.run_id),
        "runtime_mode": run_command.authority_mode.value,
        "provider_profile": TENCENT_FREE_OPERATIONAL_PROFILE_ID,
        "runtime_clock_mode": args.runtime_clock_mode,
        "summary_id": summary_id,
        "summary_outcome": summary_outcome,
        "reason_codes": list(result.reason_codes),
        "entry_authority_granted": False,
        "broker_authority_granted": False,
        "daily_decision_window_summary_delivered": summary_id is not None,
        "historical_sample_build": (
            None
            if historical_sample_build is None
            else historical_sample_build.to_canonical_dict()
        ),
        "path_forecast_registry_wired": forecast_sample_provider is not None,
    }


def _run_day(
    args: argparse.Namespace,
    settings: DatabaseSettings,
    factory: PostgresConnectionFactory,
    journal: PostgresContinuousResearchJournal,
) -> dict[str, Any]:
    output = _run_due(args, settings, factory, journal)
    output["operation"] = "RUN_DAY"
    if output.get("status") != "COMPLETED":
        output["research_shadow_status"] = "NOT_READY"
        return output
    run_id = ArtifactId(str(output["run_id"]))
    runtime = journal.get_run(run_id)
    if runtime.command.authority_mode is not RuntimeAuthorityMode.SHADOW:
        output["research_shadow_status"] = "NOT_APPLICABLE"
        return output
    session, decision = ResearchShadowOperations(factory).run_day(run_id)
    output.update(
        {
            "research_shadow_status": session.status.value,
            "research_shadow_session_id": str(session.command.session_id),
            "research_shadow_decision_id": str(decision.decision_id),
            "shadow_order_created": False,
            "shadow_fill_created": False,
            "real_position_mutated": False,
        }
    )
    return output


def _run_due_stage_output(
    *,
    run_command: ContinuousResearchCommand,
    status: str,
    stage: str,
    reason_codes: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "operation": "RUN_DUE",
        "status": status,
        "stage": stage,
        "run_id": str(run_command.run_id),
        "runtime_mode": run_command.authority_mode.value,
        "provider_profile": TENCENT_FREE_OPERATIONAL_PROFILE_ID,
        "summary_id": None,
        "summary_outcome": None,
        "reason_codes": list(reason_codes),
        "entry_authority_granted": False,
        "broker_authority_granted": False,
        "daily_decision_window_summary_delivered": False,
    }


def _load_json_object(path: Path) -> Mapping[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("command file must contain a JSON object")
    return payload


def _instant(value: str) -> datetime:
    instant = datetime.fromisoformat(value)
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("--at must be timezone-aware")
    if instant.microsecond:
        raise ValueError("--at must use whole-second precision")
    return instant


def _operational_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _authority_ceiling() -> dict[str, bool]:
    return {
        "entry_authority_granted": False,
        "broker_authority_granted": False,
        "daily_decision_window_summary_delivered": False,
    }


def _emit(payload: Mapping[str, Any]) -> None:
    print(
        json.dumps(
            dict(payload),
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
    )


def _emit_error(reason_code: str, exc: BaseException) -> None:
    _emit(
        {
            "status": "FAILED",
            "reason_code": reason_code,
            "error_type": type(exc).__name__,
            "message": "Continuous Research command failed; credentials are redacted",
            **_authority_ceiling(),
        }
    )


if __name__ == "__main__":
    raise SystemExit(main())
