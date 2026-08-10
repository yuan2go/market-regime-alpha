from __future__ import annotations

import json
import os
from datetime import UTC, datetime

from market_regime_alpha.cli.continuous_research import (
    ARGUMENT_ERROR,
    DATABASE_ERROR,
    SUCCESS,
    build_parser,
    main,
)
from market_regime_alpha.application.continuous_research.scheduler import (
    TradingDayAssessment,
)
from market_regime_alpha.application.governance.access_control import (
    PostgresAccessGovernance,
    RoleEventKind,
    SecurityRole,
)
from market_regime_alpha.core.identity import ArtifactId
from tests.application.continuous_research.test_runner import NOW
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from tests.application.continuous_research.test_runner import _command, _tick
from tests.persistence.postgres.conftest import (
    TEST_DATABASE_URL_ENV,
    postgres_factory as postgres_factory,
)


def _authority_args(postgres_factory: PostgresConnectionFactory) -> list[str]:
    admin = PostgresAccessGovernance(postgres_factory).bootstrap_admin(
        external_subject="test:continuous-cli-admin",
        display_name="Continuous CLI Admin",
        reason="CLI authorization fixture",
        occurred_at=datetime(2026, 8, 11, tzinfo=UTC),
        idempotency_key="continuous-cli-admin",
    )
    return [
        "--database-url",
        os.environ[TEST_DATABASE_URL_ENV],
        "--application-schema",
        postgres_factory.application_schema,
        "--principal-id",
        str(admin.principal_id),
    ]


def test_cli_exposes_converged_free_data_day_operations() -> None:
    args = build_parser().parse_args(
        [
            "--database-url",
            "postgresql://runtime-authority",
            "run-due",
            "--run-command",
            "run.json",
            "--trading-day-assessment",
            "trading-day.json",
            "--runtime-configuration",
            "configuration.json",
            "--output-root",
            "runtime-output",
            "--at",
            "2025-02-03T14:54:00+08:00",
        ]
    )

    assert args.operation == "run-due"
    assert args.runtime_clock_mode == "LIVE"

    run_day = build_parser().parse_args(
        [
            "--database-url",
            "postgresql://runtime-authority",
            "run-day",
            "--run-command",
            "run.json",
            "--trading-day-assessment",
            "trading-day.json",
            "--runtime-configuration",
            "configuration.json",
            "--output-root",
            "runtime-output",
            "--at",
            "2025-02-03T14:54:00+08:00",
        ]
    )
    strategy_day = build_parser().parse_args(
        [
            "--database-url",
            "postgresql://runtime-authority",
            "strategy-day",
            "--observations",
            "observations.json",
        ]
    )
    settle_day = build_parser().parse_args(
        [
            "--database-url",
            "postgresql://runtime-authority",
            "settle-day",
            "--trading-date",
            "2025-02-03",
            "--next-session-date",
            "2025-02-04",
            "--artifact-root",
            "runtime-output",
            "--at",
            "2025-02-04T15:01:00+08:00",
        ]
    )
    report_day = build_parser().parse_args(
        [
            "--database-url",
            "postgresql://runtime-authority",
            "report-day",
            "--trading-date",
            "2025-02-03",
            "--at",
            "2025-02-04T15:01:00+08:00",
        ]
    )
    replay_day = build_parser().parse_args(
        [
            "--database-url",
            "postgresql://runtime-authority",
            "replay-day",
            "--trading-date",
            "2025-02-03",
        ]
    )
    universe_sync = build_parser().parse_args(
        [
            "--database-url",
            "postgresql://runtime-authority",
            "research-universe-sync",
            "--as-of-date",
            "2025-02-03",
            "--artifact-root",
            "runtime-output",
        ]
    )
    universe_replay = build_parser().parse_args(
        [
            "--database-url",
            "postgresql://runtime-authority",
            "research-universe-replay",
            "--snapshot-id",
            "research-universe-1",
        ]
    )
    portfolio_day = build_parser().parse_args(
        [
            "--database-url",
            "postgresql://runtime-authority",
            "portfolio-shadow-day",
            "--observations",
            "portfolio-observations.json",
        ]
    )
    portfolio_replay = build_parser().parse_args(
        [
            "--database-url",
            "postgresql://runtime-authority",
            "portfolio-shadow-replay",
            "--portfolio-id",
            "portfolio-1",
        ]
    )
    recovery_audit = build_parser().parse_args(
        [
            "--database-url",
            "postgresql://runtime-authority",
            "recovery-audit",
            "--checked-at",
            "2026-08-11T08:00:00+08:00",
        ]
    )

    assert run_day.operation == "run-day"
    assert strategy_day.operation == "strategy-day"
    assert settle_day.operation == "settle-day"
    assert report_day.operation == "report-day"
    assert replay_day.operation == "replay-day"
    assert universe_sync.operation == "research-universe-sync"
    assert universe_replay.operation == "research-universe-replay"
    assert portfolio_day.operation == "portfolio-shadow-day"
    assert portfolio_replay.operation == "portfolio-shadow-replay"
    assert recovery_audit.operation == "recovery-audit"


def test_cli_exposes_read_only_preflight_and_canonical_inspection() -> None:
    preflight = build_parser().parse_args(
        [
            "--database-url",
            "postgresql://runtime-authority",
            "preflight",
            "--trading-date",
            "2026-08-10",
            "--runtime-mode",
            "SHADOW",
            "--provider-profile-id",
            "TENCENT_BAOSTOCK_FREE_OPERATIONAL_V1",
            "--operational-policy-effective-from",
            "2026-01-01",
            "--artifact-root",
            "artifacts",
            "--runtime-configuration",
            "configuration.json",
            "--trading-calendar",
            "calendar.json",
        ]
    )
    inspect_tick = build_parser().parse_args(
        [
            "--database-url",
            "postgresql://runtime-authority",
            "inspect-tick",
            "--run-id",
            "run-1",
            "--tick-id",
            "tick-1",
        ]
    )

    assert preflight.operation == "preflight"
    assert preflight.runtime_mode == "SHADOW"
    assert inspect_tick.operation == "inspect-tick"


def test_cli_prepare_admit_report_and_replay_are_structured(
    postgres_factory: PostgresConnectionFactory,
    tmp_path,
    capsys,
) -> None:
    command = _command()
    tick = _tick(command, 0)
    command_path = tmp_path / "run.json"
    tick_path = tmp_path / "tick.json"
    command_path.write_text(
        json.dumps(command.to_canonical_dict()), encoding="utf-8"
    )
    tick_path.write_text(json.dumps(tick.to_canonical_dict()), encoding="utf-8")
    authority = _authority_args(postgres_factory)

    assert main([*authority, "prepare", "--run-command", str(command_path)]) == SUCCESS
    prepared = json.loads(capsys.readouterr().out)
    assert prepared["run_id"] == str(command.run_id)
    assert prepared["entry_authority_granted"] is False

    assert (
        main(
            [
                *authority,
                "admit-tick",
                "--tick-command",
                str(tick_path),
                "--session-phase",
                "DECISION_WINDOW",
            ]
        )
        == SUCCESS
    )
    admitted = json.loads(capsys.readouterr().out)
    assert admitted["tick_id"] == str(tick.tick_id)

    assert main([*authority, "report", "--run-id", str(command.run_id)]) == SUCCESS
    report = json.loads(capsys.readouterr().out)
    assert report["tick_count"] == 1
    assert report["daily_decision_window_summary_delivered"] is False

    assert main([*authority, "replay", "--run-id", str(command.run_id)]) == SUCCESS
    replay = json.loads(capsys.readouterr().out)
    assert replay["integrity_status"] == "VERIFIED"
    assert replay["entry_authority_granted"] is False


def test_cli_requires_explicit_postgres_and_never_echoes_credentials(capsys) -> None:
    assert main(["report", "--run-id", "missing-run"]) == ARGUMENT_ERROR
    missing = capsys.readouterr().out
    assert "explicit --database-url is required" not in missing

    secret = "do-not-echo-this-password"
    assert (
        main(
            [
                "--database-url",
                f"postgresql://user:{secret}@localhost/database",
                "--principal-id",
                "unavailable-database-principal",
                "report",
                "--run-id",
                "missing-run",
            ]
        )
        == DATABASE_ERROR
    )
    output = capsys.readouterr().out
    assert secret not in output
    failed = json.loads(output)
    assert failed["status"] == "FAILED"
    assert failed["reason_code"] == "POSTGRESQL_OPERATION_FAILED"


def test_cli_requires_authorized_principal_for_shadow_mutation(
    postgres_factory: PostgresConnectionFactory,
    capsys,
    tmp_path,
) -> None:
    authority = _authority_args(postgres_factory)
    admin_id = ArtifactId(authority[-1])
    governance = PostgresAccessGovernance(postgres_factory, apply_migrations=False)
    researcher = governance.create_principal(
        actor=admin_id,
        external_subject="test:continuous-cli-researcher",
        display_name="Continuous CLI Researcher",
        reason="authorization boundary fixture",
        occurred_at=datetime(2026, 8, 11, 0, 0, 1, tzinfo=UTC),
        idempotency_key="continuous-cli-researcher",
    )
    governance.change_role(
        actor=admin_id,
        principal_id=researcher.principal_id,
        role=SecurityRole.RESEARCHER,
        event_kind=RoleEventKind.GRANTED,
        reason="authorization boundary fixture",
        occurred_at=datetime(2026, 8, 11, 0, 0, 2, tzinfo=UTC),
        idempotency_key="continuous-cli-grant-researcher",
    )
    denied_authority = [*authority[:-1], str(researcher.principal_id)]

    assert main(
        [*denied_authority, "strategy-day", "--observations", "missing.json"]
    ) == ARGUMENT_ERROR
    output = json.loads(capsys.readouterr().out)
    assert output["reason_code"] == "OPERATOR_NOT_AUTHORIZED"

    command_path = tmp_path / "research-run.json"
    command_path.write_text(
        json.dumps(_command().to_canonical_dict()),
        encoding="utf-8",
    )
    assert main(
        [
            *denied_authority,
            "prepare",
            "--run-command",
            str(command_path),
        ]
    ) == SUCCESS


def test_cli_schedules_and_reserves_a_due_tick(
    postgres_factory: PostgresConnectionFactory,
    tmp_path,
    capsys,
) -> None:
    command = _command()
    trading_day = TradingDayAssessment(
        trading_calendar_id=command.trading_calendar_id,
        trading_calendar_hash=command.trading_calendar_hash,
        trading_date=command.trading_date,
        is_trading_day=True,
        reason_codes=("TRADING_DAY",),
    )
    command_path = tmp_path / "schedule-run.json"
    trading_day_path = tmp_path / "trading-day.json"
    command_path.write_text(json.dumps(command.to_canonical_dict()), encoding="utf-8")
    trading_day_path.write_text(
        json.dumps(trading_day.to_canonical_dict()), encoding="utf-8"
    )
    authority = _authority_args(postgres_factory)

    assert main(
        [
            *authority,
            "schedule",
            "--run-command",
            str(command_path),
            "--trading-day-assessment",
            str(trading_day_path),
            "--at",
            NOW.isoformat(),
        ]
    ) == SUCCESS
    scheduled = json.loads(capsys.readouterr().out)
    assert scheduled["status"] == "ACTIVE"

    assert main(
        [
            *authority,
            "reserve-due-tick",
            "--run-command",
            str(command_path),
            "--at",
            NOW.isoformat(),
        ]
    ) == SUCCESS
    reserved = json.loads(capsys.readouterr().out)
    assert reserved["status"] == "PENDING"
    assert reserved["entry_authority_granted"] is False
