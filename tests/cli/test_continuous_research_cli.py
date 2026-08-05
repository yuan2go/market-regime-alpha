from __future__ import annotations

import json
import os

from market_regime_alpha.cli.continuous_research import (
    ARGUMENT_ERROR,
    SUCCESS,
    main,
)
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
                f"sqlite://user:{secret}@localhost/database",
                "report",
                "--run-id",
                "missing-run",
            ]
        )
        == ARGUMENT_ERROR
    )
    output = capsys.readouterr().out
    assert secret not in output
    assert json.loads(output)["status"] == "FAILED"
