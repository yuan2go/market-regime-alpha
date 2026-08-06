from __future__ import annotations

import csv
import json
import os
from pathlib import Path

import pytest

from market_regime_alpha.application.decision_system.postgres_repository import (
    DecisionSystemConflict,
    DecisionSystemIntegrityError,
)
from market_regime_alpha.application.decision_system.window import (
    DecisionWindowBlocked,
)
from market_regime_alpha.cli import decision_system
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
    assert output["observation"]["total_equity"] == "100000.12"
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
    assert output["error_code"] == "DOCON-002"
    assert output["reason_code"] == "INVALID_TYPE"


def test_json_record_rejects_unknown_fields(
    postgres_factory: PostgresConnectionFactory,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "account-extra.json"
    payload = observation().semantic_payload()
    payload["positions_from_caller"] = []
    source.write_text(json.dumps(payload), encoding="utf-8")

    code = main(
        [
            *_database_arguments(postgres_factory),
            "record-manual-account",
            "--input",
            str(source),
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert code == 2
    assert output["error_code"] == "DOCON-002"
    assert output["position_mutated"] is False


@pytest.mark.parametrize(
    ("failure", "error_code", "reason_code"),
    (
        (
            DecisionWindowBlocked("WINDOW_NOT_OPEN"),
            "DECSYS-002",
            "DECISION_WINDOW_BLOCKED",
        ),
        (
            DecisionSystemConflict("CAS rejected"),
            "DECSYS-003",
            "DECISION_CONFLICT",
        ),
        (
            DecisionSystemIntegrityError("lineage mismatch"),
            "DECSYS-001",
            "DECISION_INPUT_BLOCKED",
        ),
    ),
)
def test_cli_preserves_typed_decision_error_catalog_codes(
    postgres_factory: PostgresConnectionFactory,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    failure: Exception,
    error_code: str,
    reason_code: str,
) -> None:
    def fail(*_: object, **__: object) -> dict[str, object]:
        raise failure

    monkeypatch.setattr(decision_system, "_dispatch", fail)
    code = main(
        [
            *_database_arguments(postgres_factory),
            "inspect-manual-account",
            "--observation-id",
            "unused",
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert code == 2
    assert output["error_code"] == error_code
    assert output["reason_code"] == reason_code
