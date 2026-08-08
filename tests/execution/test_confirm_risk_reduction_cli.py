from __future__ import annotations

from dataclasses import replace
import json

from scripts.confirm_risk_reduction import main
from tests.execution.risk_reduction_confirmation_support import (
    build_confirmation_fixture,
)
from tests.postgres_path_repositories import postgres_cli_arguments


pytest_plugins = ("tests.daily_decision.conftest",)


def _arguments(tmp_path, fixture) -> tuple[str, ...]:
    calendar = tmp_path / "calendar.json"
    statuses = tmp_path / "statuses.json"
    observation = tmp_path / "observation.json"
    policy = tmp_path / "policy.json"
    calendar.write_text(
        json.dumps(fixture.command.trading_calendar.to_canonical_dict()),
        encoding="utf-8",
    )
    statuses.write_text(
        json.dumps(
            [
                item.to_canonical_dict()
                for item in fixture.command.symbol_trading_statuses
            ]
        ),
        encoding="utf-8",
    )
    observation.write_text(
        json.dumps(fixture.command.execution_observation.to_canonical_dict()),
        encoding="utf-8",
    )
    policy.write_text(
        json.dumps(fixture.command.confirmation_policy.to_canonical_dict()),
        encoding="utf-8",
    )
    command = fixture.command
    return (
        *postgres_cli_arguments(fixture.repository.path),
        "--risk-reducing-decision-id",
        str(command.risk_reducing_decision_id),
        "--risk-reducing-decision-hash",
        command.risk_reducing_decision_hash,
        "--exit-directive-id",
        str(command.exit_directive_id),
        "--exit-directive-hash",
        command.exit_directive_hash,
        "--thesis-health-observation-id",
        str(command.thesis_health_observation_id),
        "--thesis-health-observation-hash",
        command.thesis_health_observation_hash,
        "--composite-manifest-id",
        str(command.composite_manifest_id),
        "--composite-manifest-hash",
        command.composite_manifest_hash,
        "--trading-calendar",
        str(calendar),
        "--symbol-trading-status",
        str(statuses),
        "--execution-observation",
        str(observation),
        "--confirmation-policy",
        str(policy),
        "--expected-price-lower",
        str(command.expected_price_lower),
        "--expected-price-upper",
        str(command.expected_price_upper),
        "--confirmed-at",
        command.confirmed_at.isoformat(),
        "--actor",
        command.actor,
        "--reason",
        command.reason,
        "--idempotency-key",
        command.idempotency_key,
    )


def test_cli_outputs_only_manual_intent_authority_boundaries(
    tmp_path, daily_decision_fixture, capsys
) -> None:
    fixture = build_confirmation_fixture(tmp_path, daily_decision_fixture)

    assert main(_arguments(tmp_path, fixture)) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["state"] == "CONFIRMED_INTENT"
    assert payload["outcome"] == "MANUAL_INTENT_CREATED"
    assert payload["MANUAL_INTENT_CREATED"] is True
    assert payload["manual_trade_id"]
    assert payload["NO_FILL_CREATED"] is True
    assert payload["NO_BROKER_ORDER_CREATED"] is True
    assert payload["TRADING_AUTHORITY_NOT_GRANTED"] is True
    assert payload["OPERATOR_AUTHENTICATION_NOT_ESTABLISHED"] is True


def test_cli_failed_attempt_outputs_evidence_and_null_trade(
    tmp_path, daily_decision_fixture, capsys
) -> None:
    fixture = build_confirmation_fixture(tmp_path, daily_decision_fixture)
    blocked = replace(
        fixture,
        command=replace(
            fixture.command,
            expected_price_lower=9.7,
            expected_price_upper=9.9,
            idempotency_key="cli-price-blocked",
        ),
    )

    assert main(_arguments(tmp_path, blocked)) == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["attempt_id"]
    assert payload["state"] == "BLOCKED_ON_RECHECK"
    assert payload["manual_trade_id"] is None
    assert payload["source_position_snapshot_id"]
    assert payload["current_position_snapshot_id"]
    assert payload["recheck_observation_id"]


def test_cli_unknown_decision_reference_persists_data_insufficient_attempt(
    tmp_path, daily_decision_fixture, capsys
) -> None:
    fixture = build_confirmation_fixture(tmp_path, daily_decision_fixture)
    arguments = list(_arguments(tmp_path, fixture))
    decision_index = arguments.index("--risk-reducing-decision-id") + 1
    arguments[decision_index] = "missing-risk-reducing-decision"

    assert main(arguments) == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["attempt_id"]
    assert payload["state"] == "DATA_INSUFFICIENT"
    assert payload["reason_codes"] == [
        "RISK_REDUCING_DECISION_HASH_MISMATCH"
    ]
    assert payload["source_position_snapshot_id"]
    assert payload["current_position_snapshot_id"]
    assert payload["recheck_observation_id"]
    assert payload["manual_trade_id"] is None
    assert payload["MANUAL_INTENT_CREATED"] is False
    assert payload["NO_FILL_CREATED"] is True
    assert payload["NO_BROKER_ORDER_CREATED"] is True


def test_cli_unknown_directive_reference_persists_data_insufficient_attempt(
    tmp_path, daily_decision_fixture, capsys
) -> None:
    fixture = build_confirmation_fixture(tmp_path, daily_decision_fixture)
    arguments = list(_arguments(tmp_path, fixture))
    directive_index = arguments.index("--exit-directive-id") + 1
    arguments[directive_index] = "missing-exit-directive"

    assert main(arguments) == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["attempt_id"]
    assert payload["state"] == "DATA_INSUFFICIENT"
    assert payload["reason_codes"] == [
        "OPERATIONAL_EXIT_DIRECTIVE_REFERENCE_MISMATCH"
    ]
    assert payload["source_position_snapshot_id"]
    assert payload["current_position_snapshot_id"]
    assert payload["recheck_observation_id"]
    assert payload["manual_trade_id"] is None
    assert payload["MANUAL_INTENT_CREATED"] is False
    assert payload["NO_FILL_CREATED"] is True
    assert payload["NO_BROKER_ORDER_CREATED"] is True


def test_cli_fully_unresolvable_authority_is_structured_command_rejection(
    tmp_path, daily_decision_fixture, capsys
) -> None:
    fixture = build_confirmation_fixture(tmp_path, daily_decision_fixture)
    arguments = list(_arguments(tmp_path, fixture))
    arguments[arguments.index("--risk-reducing-decision-id") + 1] = (
        "missing-risk-reducing-decision"
    )
    arguments[arguments.index("--exit-directive-id") + 1] = (
        "missing-exit-directive"
    )

    assert main(arguments) == 2

    payload = json.loads(capsys.readouterr().out)
    assert payload["attempt_id"] is None
    assert payload["reason_codes"] == ["AUTHORITY_REFERENCE_NOT_RESOLVED"]
    assert payload["manual_trade_id"] is None
    assert payload["MANUAL_INTENT_CREATED"] is False
