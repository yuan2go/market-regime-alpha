from __future__ import annotations

import json
from pathlib import Path
import sqlite3

import pytest

import market_regime_alpha.execution  # noqa: F401  # existing package initialization order
from market_regime_alpha.dividend_t.brokers import PaperBrokerAdapter
from market_regime_alpha.portfolio import RiskRouteApplicationService
from scripts.build_thesis_health import main

from tests.position.test_thesis_health_builder import _bundle
from tests.position.thesis_health_fixtures import make_h5_fixture


def _write_request(path: Path, *, idempotency_key: str) -> None:
    payload = {
        "input_bundle": _bundle(make_h5_fixture()).to_canonical_dict(),
        "idempotency_key": idempotency_key,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _invoke(database: Path, request: Path, capsys) -> dict[str, object]:
    assert main(["--database", str(database), "--request", str(request)]) == 0
    return json.loads(capsys.readouterr().out)


def test_cli_persists_and_replays_v2_observation_without_trade_authority(
    tmp_path, capsys, monkeypatch
) -> None:
    database = tmp_path / "health.sqlite3"
    request = tmp_path / "health.json"
    _write_request(request, idempotency_key="cli-health-replay")
    monkeypatch.setattr(
        PaperBrokerAdapter,
        "place_order",
        lambda *_args, **_kwargs: pytest.fail("H5 CLI must not call a Broker"),
    )
    monkeypatch.setattr(
        RiskRouteApplicationService,
        "assess_reducing",
        lambda *_args, **_kwargs: pytest.fail("H5 CLI must not create an H4 decision"),
    )

    first = _invoke(database, request, capsys)
    replay = _invoke(database, request, capsys)

    assert replay["observation_id"] == first["observation_id"]
    assert first["schema_version"] == "thesis-health-observation-v2"
    assert first["observed_health_state"] == "HEALTHY"
    assert first["effective_health_state"] == "HEALTHY"
    assert first["mode"] == "OBSERVATION_ONLY"
    assert first["execution_boundary"] == "NO_TRADE_ACTION_CREATED"
    assert first["trading_authority"] == "TRADING_AUTHORITY_NOT_GRANTED"
    assert first["component_states"]["signal"] == "SUPPORTED"
    assert first["source_artifacts"]["candidate_set"]["artifact_id"]

    with sqlite3.connect(database) as connection:
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert "thesis_health_observations" in tables
    assert "risk_reducing_decisions" not in tables
    assert not any("manual_trade" in name for name in tables)
    assert not any("fill" in name for name in tables)


@pytest.mark.parametrize(
    "forbidden_field",
    (
        "signal_support",
        "theme_support",
        "capital_support",
        "triggered_condition_ids",
        "health_state",
    ),
)
def test_cli_rejects_v1_support_or_caller_authored_health(
    tmp_path, forbidden_field: str
) -> None:
    request = tmp_path / f"forbidden-{forbidden_field}.json"
    _write_request(request, idempotency_key="strict-v2-input")
    payload = json.loads(request.read_text(encoding="utf-8"))
    payload[forbidden_field] = True
    request.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="request fields mismatch"):
        main(
            [
                "--database",
                str(tmp_path / "forbidden.sqlite3"),
                "--request",
                str(request),
            ]
        )


def test_cli_rejects_v1_health_observation_as_operational_input(tmp_path) -> None:
    request = tmp_path / "v1.json"
    request.write_text(
        json.dumps(
            {
                "input_bundle": {
                    "signal_support": True,
                    "theme_support": True,
                    "capital_support": True,
                },
                "idempotency_key": "no-v1",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        main(
            [
                "--database",
                str(tmp_path / "v1.sqlite3"),
                "--request",
                str(request),
            ]
        )
