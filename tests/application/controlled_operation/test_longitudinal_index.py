from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
import sqlite3

import pytest

from market_regime_alpha.application.controlled_operation.evidence_package import (
    publish_controlled_operation_package,
)
from market_regime_alpha.application.controlled_operation.longitudinal_index import (
    SQLiteLongitudinalOperationalIndex,
)
from market_regime_alpha.core.identity import DatasetId
from market_regime_alpha.data.trading_calendar import (
    TradingSession,
    build_trading_calendar_artifact,
)
from tests.application.controlled_operation.test_evidence_package import _artifact


UTC = timezone.utc
NOW = datetime(2026, 8, 6, 1, 0, tzinfo=UTC)


def _calendar():
    return build_trading_calendar_artifact(
        source_dataset_id=DatasetId("longitudinal-calendar-source"),
        market="A_SHARE",
        calendar_version="longitudinal-test-v1",
        timezone_name="Asia/Shanghai",
        sessions=tuple(
            TradingSession(
                trade_date=date(2026, 8, 3) + timedelta(days=index),
                session_close=datetime.combine(
                    date(2026, 8, 3) + timedelta(days=index),
                    time(15),
                    tzinfo=timezone(timedelta(hours=8)),
                ),
            )
            for index in range(3)
        ),
    )


def test_longitudinal_index_is_append_only_queryable_and_rebuildable(tmp_path: Path) -> None:
    package = _artifact(decision_time=datetime(2026, 8, 4, 6, 55, tzinfo=UTC))
    package_path = publish_controlled_operation_package(
        root=tmp_path / "packages", artifact=package
    )
    index = SQLiteLongitudinalOperationalIndex(tmp_path / "longitudinal.sqlite3", clock=lambda: NOW)
    record = index.append(package=package, package_locator="packages/one")

    assert index.append(package=package, package_locator="packages/one") == record
    assert index.get(package.command.run_id) == record
    assert index.query(
        start_date=date(2026, 8, 4),
        end_date=date(2026, 8, 4),
        signal_model_id=package.signal_model_id,
        signal_model_version=package.signal_model_version,
    ) == (record,)
    assert index.missing_trading_dates(
        calendar=_calendar(), start_date=date(2026, 8, 3), end_date=date(2026, 8, 5)
    ) == (date(2026, 8, 3), date(2026, 8, 5))

    rebuilt = SQLiteLongitudinalOperationalIndex.rebuild(
        path=tmp_path / "rebuilt.sqlite3",
        packages=((package_path, "packages/one"),),
        clock=lambda: NOW,
    )
    assert rebuilt.query() == (record,)


def test_longitudinal_database_triggers_block_update_and_delete(tmp_path: Path) -> None:
    package = _artifact()
    path = tmp_path / "longitudinal.sqlite3"
    index = SQLiteLongitudinalOperationalIndex(path, clock=lambda: NOW)
    index.append(package=package, package_locator="packages/one")

    with sqlite3.connect(path) as connection, pytest.raises(
        sqlite3.IntegrityError, match="append-only"
    ):
        connection.execute(
            "UPDATE longitudinal_operational_index SET deadline_status = 'FORGED'"
        )
    with sqlite3.connect(path) as connection, pytest.raises(
        sqlite3.IntegrityError, match="append-only"
    ):
        connection.execute("DELETE FROM longitudinal_operational_index")
