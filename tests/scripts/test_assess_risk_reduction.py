from __future__ import annotations

from datetime import timedelta
import json
from pathlib import Path
import pytest

from market_regime_alpha.dividend_t.brokers import PaperBrokerAdapter
from market_regime_alpha.portfolio import ExecutionConstraintState, RiskChangeKind
from scripts.assess_risk_reduction import main
from tests.portfolio.risk_route_test_support import (
    NOW,
    make_configuration,
    make_observation,
    make_position,
)
from tests.postgres_path_repositories import (
    postgres_cli_arguments,
    postgres_connection,
)


def _write_request(
    path: Path,
    *,
    idempotency_key: str,
    observation_state: ExecutionConstraintState = ExecutionConstraintState.EXECUTABLE,
    observation_age: timedelta = timedelta(seconds=10),
) -> None:
    payload = {
        "action": RiskChangeKind.REDUCE.value,
        "position_snapshot": make_position().to_canonical_dict(),
        "target_quantity": 80,
        "order_quantity": 20,
        "execution_observation": make_observation(
            observation_state,
            availability_time=NOW - observation_age,
        ).to_canonical_dict(),
        "configuration": make_configuration().to_canonical_dict(),
        "actor": "risk-reduction-operator",
        "reason": "CLI decision-only fixture",
        "assessed_at": (NOW + timedelta(seconds=1)).isoformat(),
        "idempotency_key": idempotency_key,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _invoke(database: Path, request: Path, capsys) -> dict[str, object]:
    assert (
        main(
            [
                *postgres_cli_arguments(database),
                "--request",
                str(request),
            ]
        )
        == 0
    )
    return json.loads(capsys.readouterr().out)


def test_cli_persists_and_replays_decision_without_execution_authority(tmp_path, capsys, monkeypatch) -> None:
    database = tmp_path / "risk-routes.postgres-scope"
    request = tmp_path / "request.json"
    _write_request(request, idempotency_key="cli-replay")
    monkeypatch.setattr(
        PaperBrokerAdapter,
        "place_order",
        lambda *_args, **_kwargs: pytest.fail("CLI must not call a Broker"),
    )

    first = _invoke(database, request, capsys)
    duplicate = _invoke(database, request, capsys)

    assert duplicate["decision_id"] == first["decision_id"]
    assert first["state"] == "PERMITTED_FOR_MANUAL_CONFIRMATION"
    assert first["mode"] == "DECISION_ONLY"
    assert first["manual_confirmation_required"] is True
    assert first["order_created"] is False
    assert first["execution_boundary"] == "NO_ORDER_CREATED"
    assert first["trading_authority"] == "TRADING_AUTHORITY_NOT_GRANTED"
    assert first["position_snapshot_id"]
    assert first["execution_observation_id"]
    assert first["configuration_id"]

    with postgres_connection(database) as connection:
        counts = tuple(
            connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in (
                "manual_trade_records",
                "manual_trade_events",
                "manual_fills",
                "execution_commands",
            )
        )
        decision_count = connection.execute("SELECT count(*) FROM risk_reducing_decisions").fetchone()[0]
    assert decision_count == 1
    assert counts == (0, 0, 0, 0)


@pytest.mark.parametrize(
    ("state", "age", "expected_state", "expected_reason"),
    (
        (
            ExecutionConstraintState.PRICE_LIMIT_BLOCKED,
            timedelta(seconds=10),
            "BLOCKED",
            "REDUCE_BLOCKED_BY_MARKET_CONSTRAINT",
        ),
        (
            ExecutionConstraintState.EXECUTABLE,
            timedelta(minutes=2),
            "DATA_INSUFFICIENT",
            "EXECUTION_OBSERVATION_STALE",
        ),
    ),
)
def test_cli_reports_non_permitted_decisions_with_explicit_reasons(
    tmp_path,
    capsys,
    state: ExecutionConstraintState,
    age: timedelta,
    expected_state: str,
    expected_reason: str,
) -> None:
    request = tmp_path / f"{expected_state}.json"
    _write_request(
        request,
        idempotency_key=f"cli-{expected_state.lower()}",
        observation_state=state,
        observation_age=age,
    )

    result = _invoke(tmp_path / f"{expected_state}.postgres-scope", request, capsys)

    assert result["state"] == expected_state
    assert expected_reason in result["reason_codes"]
    assert result["manual_confirmation_required"] is False
    assert result["execution_boundary"] == "NO_ORDER_CREATED"
    assert result["trading_authority"] == "TRADING_AUTHORITY_NOT_GRANTED"


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("action", 1),
        ("actor", True),
        ("reason", 123),
        ("assessed_at", False),
        ("idempotency_key", 456),
    ),
)
def test_cli_rejects_non_string_command_and_audit_fields(
    tmp_path,
    field: str,
    value: object,
) -> None:
    request = tmp_path / f"invalid-{field}.json"
    _write_request(request, idempotency_key="strict-string-input")
    payload = json.loads(request.read_text(encoding="utf-8"))
    payload[field] = value
    request.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match=f"{field} must be a string"):
        main(
            [
                *postgres_cli_arguments(tmp_path / "invalid.postgres-scope"),
                "--request",
                str(request),
            ]
        )
