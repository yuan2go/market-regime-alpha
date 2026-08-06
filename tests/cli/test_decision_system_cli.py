from __future__ import annotations

import csv
import json
import os
from pathlib import Path

import pytest

from market_regime_alpha.cli.decision_system import build_parser, main
from market_regime_alpha.persistence.postgres.connection import PostgresConnectionFactory
from tests.application.decision_system.support import observation
from tests.persistence.postgres.conftest import (
    TEST_DATABASE_URL_ENV,
    postgres_factory as postgres_factory,
)


def _database_arguments(factory: PostgresConnectionFactory) -> list[str]:
    return [
        "--database-url",
        os.environ[TEST_DATABASE_URL_ENV],
        "--database-schema",
        factory.application_schema,
    ]


def _write_json(path: Path) -> None:
    payload = observation().semantic_payload()
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_json_record_and_inspect_are_deterministic_and_research_only(
    postgres_factory: PostgresConnectionFactory,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "account.json"
    _write_json(source)

    code = main(
        [
            *_database_arguments(postgres_factory),
            "record-manual-account",
            "--input",
            str(source),
        ]
    )
    recorded_line = capsys.readouterr().out.strip()
    recorded = json.loads(recorded_line)
    observation_id = recorded["observation"]["observation_id"]
    inspected_code = main(
        [
            *_database_arguments(postgres_factory),
            "inspect-manual-account",
            "--observation-id",
            observation_id,
        ]
    )
    inspected_line = capsys.readouterr().out.strip()
    inspected = json.loads(inspected_line)

    assert code == inspected_code == 0
    assert recorded_line == json.dumps(recorded, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    assert inspected["observation"] == recorded["observation"]
    assert inspected["entry_authority_granted"] is False
    assert inspected["order_created"] is False
    assert inspected["fill_created"] is False
    assert inspected["position_mutated"] is False
    assert inspected["broker_called"] is False


def test_csv_import_preserves_decimal_strings(
    postgres_factory: PostgresConnectionFactory,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "account.csv"
    account = observation().semantic_payload()
    position = account["positions"][0]
    fieldnames = [
        "account_id",
        "trading_date",
        "as_of_time",
        "total_equity",
        "available_cash",
        "frozen_cash",
        "source",
        "actor",
        "reason",
        "notes",
        "idempotency_key",
        "revision",
        "previous_observation_id",
        "created_at",
        "symbol",
        "total_quantity",
        "available_quantity",
        "frozen_quantity",
        "average_cost",
        "observed_market_value",
        "position_notes",
    ]
    row = {name: account.get(name, "") for name in fieldnames}
    for name in (
        "symbol",
        "total_quantity",
        "available_quantity",
        "frozen_quantity",
        "average_cost",
        "observed_market_value",
    ):
        row[name] = position[name]
    row["position_notes"] = position["notes"]
    with source.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(row)

    code = main(
        [
            *_database_arguments(postgres_factory),
            "import-manual-account",
            "--input",
            str(source),
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert code == 0
    assert output["observation"]["total_equity"] == "100000.120000"
    assert output["observation"]["positions"][0]["average_cost"] == "10.123456"


@pytest.mark.parametrize(
    "operation",
    (
        "record-manual-account",
        "import-manual-account",
        "inspect-manual-account",
        "reconcile-account",
        "inspect-reconciliation",
        "preview-daily-decision",
        "finalize-daily-decision",
        "inspect-daily-decision",
        "inspect-portfolio-proposal",
        "inspect-risk-decision",
    ),
)
def test_cli_exposes_required_bounded_operations(operation: str) -> None:
    assert operation in build_parser()._subparsers._group_actions[0].choices


def test_cli_rejects_sqlite_dsn_without_opening_a_database(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "account.json"
    _write_json(source)

    code = main(
        [
            "--database-url",
            f"sqlite:///{tmp_path / 'authority.db'}",
            "record-manual-account",
            "--input",
            str(source),
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert code == 2
    assert output["status"] == "FAILED"
    assert output["reason_code"] == "DECISION_COMMAND_VALIDATION_FAILED"
