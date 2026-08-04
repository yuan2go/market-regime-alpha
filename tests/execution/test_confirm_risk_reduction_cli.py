from __future__ import annotations

from dataclasses import replace
import json

from scripts.confirm_risk_reduction import main
from tests.execution.risk_reduction_confirmation_support import (
    build_confirmation_fixture,
)


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
        "--database",
        str(fixture.repository.path),
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
