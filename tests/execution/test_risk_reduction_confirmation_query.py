from __future__ import annotations

from datetime import timedelta
import sqlite3

import pytest

from market_regime_alpha.application.trading_lifecycle.sqlite_risk_reduction import (
    SQLiteRiskReductionManualIntentRepository,
)
from market_regime_alpha.application.trading_lifecycle.manual_execution import (
    ManualExecutionApplicationService,
)
from market_regime_alpha.portfolio.risk_routes import RiskChangeKind
from tests.execution.risk_reduction_confirmation_support import (
    build_confirmation_fixture,
)


pytest_plugins = ("tests.daily_decision.conftest",)


def test_confirmed_risk_reduction_query_is_read_only_and_restart_safe(
    tmp_path, daily_decision_fixture
) -> None:
    fixture = build_confirmation_fixture(tmp_path, daily_decision_fixture)

    assert fixture.repository.get_confirmed_risk_reduction(fixture.decision_id) is None
    confirmed = fixture.repository.confirm_risk_reduction(fixture.command)
    assert (
        fixture.repository.get_fill_derived_position(fixture.decision_id)
        is None
    )
    with sqlite3.connect(fixture.repository.path) as connection:
        counts_before = tuple(
            connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "risk_reduction_confirmation_attempts",
                "manual_trade_records",
                "manual_fills",
            )
        )

    observed = fixture.repository.get_confirmed_risk_reduction(fixture.decision_id)
    restarted = SQLiteRiskReductionManualIntentRepository(fixture.repository.path)
    replayed = restarted.get_confirmed_risk_reduction(fixture.decision_id)

    assert observed == confirmed
    assert replayed == confirmed
    with sqlite3.connect(fixture.repository.path) as connection:
        counts_after = tuple(
            connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "risk_reduction_confirmation_attempts",
                "manual_trade_records",
                "manual_fills",
            )
        )
    assert counts_after == counts_before


def test_confirmed_risk_reduction_query_detects_trade_lineage_tamper(
    tmp_path, daily_decision_fixture
) -> None:
    fixture = build_confirmation_fixture(tmp_path, daily_decision_fixture)
    confirmed = fixture.repository.confirm_risk_reduction(fixture.command)
    assert confirmed.manual_trade is not None
    with sqlite3.connect(fixture.repository.path) as connection:
        connection.execute("DROP TRIGGER risk_reducing_manual_trade_bindings_no_update")
        connection.execute(
            """
            UPDATE risk_reducing_manual_trade_bindings
            SET risk_reducing_decision_hash = ?
            WHERE manual_trade_id = ?
            """,
            (
                "sha256:" + "f" * 64,
                str(confirmed.manual_trade.manual_trade_id),
            ),
        )

    with pytest.raises(ValueError, match="trace index mismatch"):
        fixture.repository.get_confirmed_risk_reduction(fixture.decision_id)


def test_fill_derived_position_reader_replays_historical_fill_prefix(
    tmp_path, daily_decision_fixture
) -> None:
    fixture = build_confirmation_fixture(
        tmp_path,
        daily_decision_fixture,
        action=RiskChangeKind.REDUCE,
    )
    confirmed = fixture.repository.confirm_risk_reduction(fixture.command)
    assert confirmed.manual_trade is not None
    service = ManualExecutionApplicationService(fixture.repository)
    first_time = fixture.command.confirmed_at + timedelta(seconds=2)
    service.record_fill(
        confirmed.manual_trade.manual_trade_id,
        external_fill_id="historical-prefix-first",
        quantity=20,
        price=10.0,
        fees=0.0,
        occurred_at=first_time - timedelta(seconds=1),
        recorded_at=first_time,
        actor="manual-operator",
        reason="first external partial reduction",
        idempotency_key="historical-prefix-first",
    )
    first_position = fixture.repository.get_fill_derived_position(
        fixture.decision_id
    )
    assert first_position is not None
    second_time = first_time + timedelta(seconds=2)
    service.record_fill(
        confirmed.manual_trade.manual_trade_id,
        external_fill_id="historical-prefix-second",
        quantity=20,
        price=10.0,
        fees=0.0,
        occurred_at=second_time - timedelta(seconds=1),
        recorded_at=second_time,
        actor="manual-operator",
        reason="second external partial reduction",
        idempotency_key="historical-prefix-second",
    )

    current_position = fixture.repository.get_fill_derived_position(
        fixture.decision_id
    )
    historical = fixture.repository.get_fill_derived_position(
        fixture.decision_id,
        position_snapshot_id=first_position.snapshot_id,
    )

    assert current_position is not None
    assert current_position.snapshot_id != first_position.snapshot_id
    assert historical == first_position
