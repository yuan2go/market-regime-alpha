from __future__ import annotations

import sqlite3

import pytest

from market_regime_alpha.execution.sqlite_repository import (
    MANUAL_EXECUTION_UP_MIGRATION,
)
from market_regime_alpha.execution.sqlite_traceability import (
    EXECUTION_TRACEABILITY_UP_MIGRATION,
)
from market_regime_alpha.execution.sqlite_risk_reduction import (
    SQLiteRiskReductionManualIntentRepository,
)


def _migration(name: str) -> str:
    root = MANUAL_EXECUTION_UP_MIGRATION.parent
    return (root / name).read_text(encoding="utf-8")


def _legacy_database(path) -> str:
    aggregate = '{"schema_version":"manual-trade-record-v2-traceable"}'
    with sqlite3.connect(path, isolation_level=None) as connection:
        connection.executescript(
            MANUAL_EXECUTION_UP_MIGRATION.read_text(encoding="utf-8")
        )
        connection.executescript(
            EXECUTION_TRACEABILITY_UP_MIGRATION.read_text(encoding="utf-8")
        )
        connection.execute(
            """
            INSERT INTO manual_trade_records(
                manual_trade_id, risk_decision_id, account_id, symbol, side,
                state, filled_quantity, aggregate_json, version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "trade-old",
                "risk-old",
                "account-a",
                "000001.SZ",
                "BUY",
                "RECORDED",
                0,
                aggregate,
                0,
            ),
        )
        connection.execute(
            """
            INSERT INTO manual_trade_events(
                manual_trade_id, sequence, state, aggregate_json,
                idempotency_key, created_at
            ) VALUES ('trade-old', 0, 'RECORDED', ?, 'old-event', '2026-08-04')
            """,
            (aggregate,),
        )
    return aggregate


def test_migration_010_preserves_old_json_events_and_projects_increasing_route(
    tmp_path,
) -> None:
    path = tmp_path / "migration.sqlite3"
    aggregate = _legacy_database(path)

    with sqlite3.connect(path, isolation_level=None) as connection:
        connection.executescript(
            _migration("010_risk_reduction_manual_intent_up.sql")
        )
        row = connection.execute(
            """
            SELECT authority_route, risk_decision_id,
                   risk_reducing_decision_id,
                   risk_reduction_confirmation_id, aggregate_json
            FROM manual_trade_records
            WHERE manual_trade_id = 'trade-old'
            """
        ).fetchone()
        event = connection.execute(
            "SELECT aggregate_json FROM manual_trade_events"
        ).fetchone()

        assert row == ("INCREASING", "risk-old", None, None, aggregate)
        assert event == (aggregate,)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute(
            "SELECT 1 FROM pdl_schema_migrations WHERE version = 10"
        ).fetchone() == (1,)


@pytest.mark.parametrize(
    "values",
    [
        ("INCREASING", None, None, None),
        ("INCREASING", "risk-a", "reducing-a", "attempt-a"),
        ("REDUCING", None, None, None),
        ("REDUCING", "risk-a", "reducing-a", "attempt-a"),
    ],
)
def test_migration_010_database_check_rejects_mixed_or_missing_routes(
    tmp_path, values: tuple[str, str | None, str | None, str | None]
) -> None:
    path = tmp_path / "checks.sqlite3"
    _legacy_database(path)
    with sqlite3.connect(path, isolation_level=None) as connection:
        connection.executescript(
            _migration("010_risk_reduction_manual_intent_up.sql")
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO manual_trade_records(
                    manual_trade_id, authority_route, risk_decision_id,
                    risk_reducing_decision_id,
                    risk_reduction_confirmation_id, account_id, symbol,
                    side, state, filled_quantity, aggregate_json, version
                ) VALUES ('invalid', ?, ?, ?, ?, 'account-a', '000001.SZ',
                          'SELL', 'RECORDED', 0, '{}', 0)
                """,
                values,
            )


def test_migration_010_attempt_uniqueness_and_append_only_guards(tmp_path) -> None:
    path = tmp_path / "append-only.sqlite3"
    _legacy_database(path)
    with sqlite3.connect(path, isolation_level=None) as connection:
        connection.executescript(
            _migration("010_risk_reduction_manual_intent_up.sql")
        )
        connection.execute(
            """
            INSERT INTO operational_exit_directives(
                directive_id, content_hash, exit_assessment_id,
                risk_reducing_decision_id, thesis_health_observation_id,
                composite_manifest_id, directive_json, exit_assessment_json,
                created_at
            ) VALUES ('directive-a', 'hash-a', 'exit-a', 'reducing-a',
                      'health-a', 'manifest-a', '{}', '{}', '2026-08-04')
            """
        )
        connection.execute(
            """
            INSERT INTO risk_reduction_confirmation_attempts(
                attempt_id, content_hash, state, risk_reducing_decision_id,
                exit_directive_id, manual_trade_id, attempt_json, policy_json,
                recheck_observation_json, current_position_json,
                trading_calendar_json, symbol_trading_status_json, created_at
            ) VALUES ('attempt-failed', 'failed-hash', 'POSITION_CHANGED',
                      'reducing-a', 'directive-a', NULL, '{}', '{}', '{}',
                      '{}', '{}', '{}', '2026-08-04')
            """
        )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(
                "UPDATE risk_reduction_confirmation_attempts SET state = 'EXPIRED'"
            )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(
                "DELETE FROM operational_exit_directives"
            )


def test_migration_010_down_isolated_restores_v2_projection(tmp_path) -> None:
    path = tmp_path / "down.sqlite3"
    aggregate = _legacy_database(path)
    with sqlite3.connect(path, isolation_level=None) as connection:
        connection.executescript(
            _migration("010_risk_reduction_manual_intent_up.sql")
        )
        connection.executescript(
            _migration("010_risk_reduction_manual_intent_down.sql")
        )
        columns = {
            row[1] for row in connection.execute(
                "PRAGMA table_info(manual_trade_records)"
            )
        }
        row = connection.execute(
            "SELECT risk_decision_id, aggregate_json FROM manual_trade_records"
        ).fetchone()

        assert "authority_route" not in columns
        assert row == ("risk-old", aggregate)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute(
            "SELECT 1 FROM pdl_schema_migrations WHERE version = 10"
        ).fetchone() is None


def test_repository_rejects_spoofed_append_only_trigger(tmp_path) -> None:
    path = tmp_path / "spoofed-trigger.sqlite3"
    SQLiteRiskReductionManualIntentRepository(path)
    with sqlite3.connect(path) as connection:
        connection.execute("DROP TRIGGER operational_exit_directives_no_update")
        connection.execute(
            """
            CREATE TRIGGER operational_exit_directives_no_update
            BEFORE UPDATE ON operational_exit_directives
            BEGIN
                SELECT 1;
            END
            """
        )

    with pytest.raises(ValueError, match="append-only trigger mismatch"):
        SQLiteRiskReductionManualIntentRepository(path)


def test_repository_rejects_weak_schema_with_spoofed_migration_marker(
    tmp_path,
) -> None:
    path = tmp_path / "weak-schema.sqlite3"
    _legacy_database(path)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO pdl_schema_migrations(version, applied_at) VALUES (10, 'fake')"
        )

    with pytest.raises(ValueError, match="table schema mismatch"):
        SQLiteRiskReductionManualIntentRepository(path)
