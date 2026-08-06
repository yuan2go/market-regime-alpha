from __future__ import annotations

import json
from pathlib import Path
import psycopg

import pytest

from market_regime_alpha.cli.create_manual_trade_from_risk_decision import (
    EXIT_DOMAIN_REJECTION,
    EXIT_IDEMPOTENCY_CONFLICT,
    EXIT_REPOSITORY_ERROR,
    EXIT_SUCCESS,
    EXIT_VALIDATION_ERROR,
    build_parser,
    main,
)
from market_regime_alpha.dividend_t.brokers import (
    PTradeAdapter,
    PaperBrokerAdapter,
    QMTAdapter,
)
from tests.execution.risk_reduction_confirmation_support import (
    build_confirmation_fixture,
)
from tests.postgres_path_repositories import (
    postgres_cli_arguments,
    postgres_connection,
)


pytest_plugins = ("tests.daily_decision.conftest",)


def _arguments(root: Path, fixture) -> tuple[str, ...]:
    calendar = root / "module-calendar.json"
    statuses = root / "module-statuses.json"
    observation = root / "module-observation.json"
    policy = root / "module-policy.json"
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


def _replace_argument(
    arguments: tuple[str, ...], option: str, value: str
) -> tuple[str, ...]:
    result = list(arguments)
    result[result.index(option) + 1] = value
    return tuple(result)


def _safety_declarations(payload: dict[str, object]) -> None:
    assert payload["MANUAL_CONFIRMATION_REQUIRED"] is True
    assert payload["NO_ORDER_CREATED"] is True
    assert payload["BROKER_NOT_INVOKED"] is True
    assert payload["NO_FILL_CREATED"] is True
    assert payload["NO_BROKER_ORDER_CREATED"] is True
    assert payload["TRADING_AUTHORITY_NOT_GRANTED"] is True
    assert payload["OPERATOR_AUTHENTICATION_NOT_ESTABLISHED"] is True


def test_module_cli_creates_only_one_manual_trade_and_invokes_no_broker(
    tmp_path, daily_decision_fixture, capsys, monkeypatch
) -> None:
    fixture = build_confirmation_fixture(tmp_path, daily_decision_fixture)
    broker_calls = 0

    def unexpected_broker_call(*_args, **_kwargs):
        nonlocal broker_calls
        broker_calls += 1
        raise AssertionError("H4.5 must not call a broker adapter")

    for adapter in (PaperBrokerAdapter, QMTAdapter, PTradeAdapter):
        monkeypatch.setattr(adapter, "place_order", unexpected_broker_call)
    with postgres_connection(fixture.repository.path) as connection:
        fill_count_before = connection.execute(
            "SELECT COUNT(*) FROM manual_fills"
        ).fetchone()[0]

    assert main(_arguments(tmp_path, fixture)) == EXIT_SUCCESS

    payload = json.loads(capsys.readouterr().out)
    _safety_declarations(payload)
    assert payload["state"] == "CONFIRMED_INTENT"
    assert payload["MANUAL_INTENT_CREATED"] is True
    assert payload["manual_trade_id"]
    assert broker_calls == 0
    with postgres_connection(fixture.repository.path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM manual_fills"
        ).fetchone()[0] == fill_count_before
        assert connection.execute(
            """
            SELECT COUNT(*) FROM manual_trade_records
            WHERE authority_route = 'REDUCING'
            """
        ).fetchone()[0] == 1
        assert connection.execute(
            """
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_schema = current_schema()
              AND lower(table_name) LIKE '%broker%order%'
            """
        ).fetchone()[0] == 0


def test_module_cli_domain_rejection_has_stable_exit_and_safety_payload(
    tmp_path, daily_decision_fixture, capsys
) -> None:
    fixture = build_confirmation_fixture(tmp_path, daily_decision_fixture)
    arguments = _arguments(tmp_path, fixture)
    arguments = _replace_argument(arguments, "--expected-price-lower", "9.7")
    arguments = _replace_argument(arguments, "--expected-price-upper", "9.9")
    arguments = _replace_argument(
        arguments, "--idempotency-key", "module-domain-rejection"
    )

    assert main(arguments) == EXIT_DOMAIN_REJECTION

    payload = json.loads(capsys.readouterr().out)
    _safety_declarations(payload)
    assert payload["state"] == "BLOCKED_ON_RECHECK"
    assert payload["manual_trade_id"] is None


def test_module_cli_validation_error_has_stable_exit_and_safety_payload(
    tmp_path, daily_decision_fixture, capsys
) -> None:
    fixture = build_confirmation_fixture(tmp_path, daily_decision_fixture)
    arguments = _replace_argument(
        _arguments(tmp_path, fixture), "--confirmed-at", "not-an-instant"
    )

    assert main(arguments) == EXIT_VALIDATION_ERROR

    payload = json.loads(capsys.readouterr().out)
    _safety_declarations(payload)
    assert payload["attempt_id"] is None
    assert payload["state"] == "DATA_INSUFFICIENT"
    assert payload["reason_codes"] == ["COMMAND_VALIDATION_FAILED"]


def test_module_cli_repository_error_has_distinct_stable_exit_and_safety_payload(
    tmp_path, daily_decision_fixture, capsys, monkeypatch
) -> None:
    fixture = build_confirmation_fixture(tmp_path, daily_decision_fixture)

    def unavailable_repository(_factory: object) -> object:
        raise psycopg.OperationalError("database is unavailable")

    monkeypatch.setattr(
        "market_regime_alpha.persistence.repository_factory."
        "RepositoryFactory.risk_reduction_manual_intent",
        unavailable_repository,
    )

    assert main(_arguments(tmp_path, fixture)) == EXIT_REPOSITORY_ERROR

    payload = json.loads(capsys.readouterr().out)
    _safety_declarations(payload)
    assert payload["attempt_id"] is None
    assert payload["state"] == "DATA_INSUFFICIENT"
    assert payload["manual_trade_id"] is None
    assert payload["reason_codes"] == ["H4_5_REPOSITORY_ERROR"]


def test_module_cli_idempotency_conflict_has_distinct_stable_exit(
    tmp_path, daily_decision_fixture, capsys
) -> None:
    fixture = build_confirmation_fixture(tmp_path, daily_decision_fixture)
    arguments = _arguments(tmp_path, fixture)
    with postgres_connection(fixture.repository.path) as connection:
        fill_count_before = connection.execute(
            "SELECT COUNT(*) FROM manual_fills"
        ).fetchone()[0]
    assert main(arguments) == EXIT_SUCCESS
    capsys.readouterr()
    conflicting = _replace_argument(
        arguments, "--reason", "conflicting idempotent command"
    )

    assert main(conflicting) == EXIT_IDEMPOTENCY_CONFLICT

    payload = json.loads(capsys.readouterr().out)
    _safety_declarations(payload)
    assert payload["attempt_id"] is None
    assert payload["manual_trade_id"] is None
    assert payload["reason_codes"] == ["IDEMPOTENCY_KEY_CONFLICT"]
    with postgres_connection(fixture.repository.path) as connection:
        assert connection.execute(
            """
            SELECT COUNT(*) FROM manual_trade_records
            WHERE authority_route = 'REDUCING'
            """
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM manual_fills"
        ).fetchone()[0] == fill_count_before


def test_module_cli_parser_exposes_no_broker_or_account_login_options() -> None:
    options = {
        option
        for action in build_parser()._actions
        for option in action.option_strings
    }
    forbidden_tokens = ("broker", "qmt", "ptrade", "account", "login")

    assert not {
        option
        for option in options
        if any(token in option.lower() for token in forbidden_tokens)
    }


@pytest.mark.parametrize("invalid_price", ("NaN", "Infinity", "0", "-0.01"))
def test_module_cli_parser_rejects_non_finite_or_non_positive_price(
    invalid_price: str, capsys
) -> None:
    assert main(("--expected-price-lower", invalid_price)) == (
        EXIT_VALIDATION_ERROR
    )

    payload = json.loads(capsys.readouterr().out)
    _safety_declarations(payload)
    assert payload["reason_codes"] == ["COMMAND_VALIDATION_FAILED"]
    assert "finite positive decimal" in payload["error"]


def test_module_cli_rejects_adjacent_decimal_prices_that_collapse_to_one_float(
    tmp_path, daily_decision_fixture, capsys
) -> None:
    fixture = build_confirmation_fixture(tmp_path, daily_decision_fixture)
    adjacent_prices = (
        "10.0000000000000001",
        "10.0000000000000002",
    )
    assert float(adjacent_prices[0]) == float(adjacent_prices[1])
    with postgres_connection(fixture.repository.path) as connection:
        trade_count_before = connection.execute(
            "SELECT COUNT(*) FROM manual_trade_records"
        ).fetchone()[0]

    for index, price in enumerate(adjacent_prices):
        arguments = _arguments(tmp_path, fixture)
        arguments = _replace_argument(arguments, "--expected-price-lower", price)
        arguments = _replace_argument(arguments, "--expected-price-upper", price)
        arguments = _replace_argument(
            arguments,
            "--idempotency-key",
            f"lossless-price-{index}",
        )

        assert main(arguments) == EXIT_VALIDATION_ERROR
        payload = json.loads(capsys.readouterr().out)
        _safety_declarations(payload)
        assert payload["reason_codes"] == ["COMMAND_VALIDATION_FAILED"]
        assert "losslessly" in payload["error"]

    with postgres_connection(fixture.repository.path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM manual_trade_records"
        ).fetchone()[0] == trade_count_before
