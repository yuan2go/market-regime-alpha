from __future__ import annotations

from datetime import date, datetime, timezone

from market_regime_alpha.application.controlled_operation.evidence_package import (
    publish_controlled_operation_package,
)
from market_regime_alpha.application.controlled_operation.postgres_longitudinal_index import (
    PostgresLongitudinalOperationalIndex,
)
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from tests.application.controlled_operation.test_evidence_package import _artifact
from tests.application.controlled_operation.test_longitudinal_index import _calendar


NOW = datetime(2026, 8, 6, 1, 0, tzinfo=timezone.utc)


def test_postgres_longitudinal_index_is_append_only_and_queryable(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    package = _artifact(
        decision_time=datetime(2026, 8, 4, 6, 55, tzinfo=timezone.utc)
    )
    index = PostgresLongitudinalOperationalIndex(
        postgres_factory, clock=lambda: NOW
    )
    locator = "artifact-root-v1/packages/one"
    record = index.append(package=package, package_locator=locator)
    assert index.append(package=package, package_locator=locator) == record
    assert PostgresLongitudinalOperationalIndex(
        postgres_factory, clock=lambda: NOW
    ).get(package.command.run_id) == record
    assert PostgresLongitudinalOperationalIndex(
        postgres_factory, clock=lambda: NOW
    ).get_by_package_id(package.package_id) == record
    assert index.query(
        start_date=date(2026, 8, 4),
        end_date=date(2026, 8, 4),
        signal_model_id=package.signal_model_id,
        signal_model_version=package.signal_model_version,
    ) == (record,)
    assert index.missing_trading_dates(
        calendar=_calendar(),
        start_date=date(2026, 8, 3),
        end_date=date(2026, 8, 5),
    ) == (date(2026, 8, 3), date(2026, 8, 5))


def test_postgres_longitudinal_index_rebuilds_from_immutable_packages(
    tmp_path,
    postgres_factory: PostgresConnectionFactory,
) -> None:
    package = _artifact(
        decision_time=datetime(2026, 8, 4, 6, 55, tzinfo=timezone.utc)
    )
    package_path = publish_controlled_operation_package(
        root=tmp_path / "packages", artifact=package
    )
    rebuilt = PostgresLongitudinalOperationalIndex.rebuild(
        factory=postgres_factory,
        packages=((package_path, "artifact-root-v1/packages/one"),),
        clock=lambda: NOW,
    )
    assert rebuilt.query() == (rebuilt.get(package.command.run_id),)
