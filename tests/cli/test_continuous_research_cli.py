from __future__ import annotations

import json
import os

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
    return [
        "--database-url",
        os.environ[TEST_DATABASE_URL_ENV],
        "--application-schema",
        postgres_factory.application_schema,
    ]


def test_cli_exposes_one_formal_free_data_execution_entry() -> None:
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
