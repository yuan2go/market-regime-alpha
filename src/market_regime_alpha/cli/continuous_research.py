"""Bounded PostgreSQL administration for Continuous Research runs."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, time, timedelta
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
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.core.time import DecisionTime
from market_regime_alpha.data.providers.public_composite import (
    BaoStockHistoryClient,
    BaoStockSecurityStatusClient,
    TENCENT_FREE_OPERATIONAL_PROFILE_ID,
    TencentCurrentQuoteClient,
    TencentFreeOperationalProfile,
)
from market_regime_alpha.data_sources.a_share_bars import AShareDataError
from market_regime_alpha.market_data import AssetType
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.settings import DatabaseSettings
from market_regime_alpha.persistence.repository_factory import RepositoryFactory
from zoneinfo import ZoneInfo


SUCCESS = 0
ARGUMENT_ERROR = 2
DATABASE_ERROR = 3
_SHANGHAI = ZoneInfo("Asia/Shanghai")


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
    run_due = subparsers.add_parser(
        "run-due",
        help="Execute one due BaoStock/Tencent Canonical Runtime Tick.",
    )
    run_due.add_argument("--run-command", type=Path, required=True)
    run_due.add_argument("--trading-day-assessment", type=Path, required=True)
    run_due.add_argument("--runtime-configuration", type=Path, required=True)
    run_due.add_argument("--output-root", type=Path, required=True)
    run_due.add_argument("--at", required=True)
    run_due.add_argument(
        "--runtime-clock-mode",
        choices=("LIVE", "SIMULATED"),
        default="LIVE",
        help=(
            "LIVE requires --at to match the PostgreSQL host clock; SIMULATED "
            "is an explicit engineering/replay mode."
        ),
    )
    run_due.add_argument(
        "--supplemental-evidence",
        type=Path,
        help="Explicit immutable Free Supplemental Evidence bundle; no discovery/fallback.",
    )
    run_due.add_argument("--minimum-history-sessions", type=int, default=21)
    run_due.add_argument("--liquidity-lookback-sessions", type=int, default=21)
    run_due.add_argument(
        "--minimum-median-daily-amount",
        type=Decimal,
        default=Decimal("10000000"),
    )
    run_due.add_argument("--provider-timeout-seconds", type=float, default=8.0)
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
        factory = PostgresConnectionFactory(
            settings, application_schema=args.application_schema
        )
        read_only = args.operation in {"report", "replay"}
        journal = PostgresContinuousResearchJournal(
            factory, apply_migrations=not read_only
        )
        output = (
            _run_due(args, settings, factory, journal)
            if args.operation == "run-due"
            else _dispatch(args, journal)
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
    args: argparse.Namespace, journal: PostgresContinuousResearchJournal
) -> dict[str, Any]:
    if args.operation == "prepare":
        run_command = ContinuousResearchCommand.from_canonical_dict(
            _load_json_object(args.run_command)
        )
        snapshot = journal.create_or_get(run_command)
        return {
            "status": snapshot.status.value,
            "operation": "PREPARE",
            "run_id": str(run_command.run_id),
            "command_hash": run_command.command_hash,
            **_authority_ceiling(),
        }
    if args.operation == "admit-tick":
        tick_command = RuntimeTickCommand.from_canonical_dict(
            _load_json_object(args.tick_command)
        )
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
        schedule_command = ContinuousResearchCommand.from_canonical_dict(
            _load_json_object(args.run_command)
        )
        trading_day = TradingDayAssessment.from_canonical_dict(
            _load_json_object(args.trading_day_assessment)
        )
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
        reserve_command = ContinuousResearchCommand.from_canonical_dict(
            _load_json_object(args.run_command)
        )
        reserved_tick = journal.reserve_due_tick(
            run_command=reserve_command,
            policy=default_continuous_decision_window_policy(),
            now=_instant(args.at),
        )
        return {
            "operation": "RESERVE_DUE_TICK",
            "status": "NOT_DUE" if reserved_tick is None else "PENDING",
            "run_id": str(reserve_command.run_id),
            "tick_id": (
                None if reserved_tick is None else str(reserved_tick.command.tick_id)
            ),
            "tick_sequence": (
                None if reserved_tick is None else reserved_tick.tick_sequence
            ),
            **_authority_ceiling(),
        }
    run_id = ArtifactId(args.run_id)
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
    run_command = ContinuousResearchCommand.from_canonical_dict(
        _load_json_object(args.run_command)
    )
    trading_day = TradingDayAssessment.from_canonical_dict(
        _load_json_object(args.trading_day_assessment)
    )
    now = _instant(args.at).astimezone(UTC)
    operational_now = _operational_now()
    if (
        args.runtime_clock_mode == "LIVE"
        and abs((now - operational_now).total_seconds()) > 5
    ):
        raise ValueError(
            "LIVE --at must match the trusted runtime clock within five seconds"
        )
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
        scale=FreeDataOperationScale.from_symbol_count(
            len(run_command.requested_symbols)
        ),
        provider_profile_id=TENCENT_FREE_OPERATIONAL_PROFILE_ID,
        decision_time=DecisionTime(decision),
        created_at=now,
        code_revision=run_command.code_revision,
        instruments=tuple(
            FreeDataInstrument(symbol=symbol, asset_type=AssetType.A_SHARE)
            for symbol in run_command.requested_symbols
        ),
        membership_source=(
            f"CANONICAL_FREE_DATA_{len(run_command.requested_symbols)}"
        ),
        minimum_history_sessions=args.minimum_history_sessions,
        liquidity_lookback_sessions=args.liquidity_lookback_sessions,
        minimum_median_daily_amount=args.minimum_median_daily_amount,
        configuration_hash=configuration.configuration_hash,
    )
    repositories = RepositoryFactory(settings, postgres_factory=factory)
    repositories.bind_runtime("CONTINUOUS_RESEARCH", str(run_command.run_id))
    profile = TencentFreeOperationalProfile(
        history_client=BaoStockHistoryClient(
            provider_profile_id=TENCENT_FREE_OPERATIONAL_PROFILE_ID,
        ),
        security_status_client=BaoStockSecurityStatusClient(
            timeout_seconds=args.provider_timeout_seconds,
            provider_profile_id=TENCENT_FREE_OPERATIONAL_PROFILE_ID,
        ),
        current_client=TencentCurrentQuoteClient(
            timeout_seconds=args.provider_timeout_seconds,
            provider_profile_id=TENCENT_FREE_OPERATIONAL_PROFILE_ID,
        ),
    )
    simulated_runtime_now = [now]

    def simulated_sleep(seconds: float) -> None:
        simulated_runtime_now[0] += timedelta(seconds=seconds)

    runtime_clock = (
        _operational_now
        if args.runtime_clock_mode == "LIVE"
        else lambda: simulated_runtime_now[0]
    )
    runtime_sleeper = (
        wall_time.sleep
        if args.runtime_clock_mode == "LIVE"
        else simulated_sleep
    )
    # Every durable lease/receipt in one invocation must observe the same
    # trusted (LIVE) or explicitly simulated engineering clock.
    journal = PostgresContinuousResearchJournal(
        factory,
        clock=runtime_clock,
        apply_migrations=False,
    )

    service = FreeDataOperationService(
        repositories=repositories,
        output_root=args.output_root,
        code_revision=run_command.code_revision,
        clock=runtime_clock,
        live_profile=profile,
        sleeper=runtime_sleeper,
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
    if local_now.timetz().replace(tzinfo=None) < time(14, 54, 59):
        service.prepare(
            request=free_request,
            runtime_configuration_path=configuration_path,
            idempotency_key=f"{run_command.run_id}:free-data",
            supplemental_evidence_path=args.supplemental_evidence,
        )
        return _run_due_stage_output(
            run_command=run_command,
            status="PREPARED",
            stage="TENCENT_QUOTE_AND_STATIC_FEATURES_FROZEN",
            reason_codes=(
                "ENTRY_BLOCKED",
                "FREE_DATA_STATIC_INPUTS_READY",
                "TENCENT_DECISION_QUOTE_FROZEN",
            ),
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
        model_selector=ControlledRuntimeModelSelector(
            repositories.model_governance()
        ),
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

    def provider_request_builder(
        _: ContinuousResearchCommand, __: RuntimeTickCommand
    ) -> ProviderAcquisitionRequest:
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
        predecision_lead=timedelta(seconds=1),
    )
    summary_id = None
    summary_outcome = None
    if result.tick_result is not None:
        try:
            summary = repositories.decision_system().get_research_summary_for_tick(
                run_id=run_command.run_id,
                tick_id=result.tick_result.tick.command.tick_id,
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
    }


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
