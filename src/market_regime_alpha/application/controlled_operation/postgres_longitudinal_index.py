"""Native PostgreSQL discovery index for Controlled operation packages."""

from __future__ import annotations

from datetime import date, datetime, timezone
import json
from pathlib import Path
from typing import Callable, Iterable

from market_regime_alpha.application.controlled_operation.evidence_package import (
    ControlledOperationalEvidencePackage,
    ControlledOperationalEvidenceStatus,
    load_controlled_operation_package,
)
from market_regime_alpha.application.controlled_operation.longitudinal_index import (
    LongitudinalOperationalRecord,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.trading_calendar import TradingCalendarArtifact
from market_regime_alpha.evidence.canonical import canonical_json
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.postgres.native_repository import (
    NativePostgresRepository,
    acquire_scope_lock,
    aware_datetime,
    date_value,
)


Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


class PostgresLongitudinalOperationalIndex(NativePostgresRepository):
    """Append-only PostgreSQL index; packages remain evidence authority."""

    def __init__(
        self,
        factory: PostgresConnectionFactory,
        *,
        clock: Clock = _utc_now,
    ) -> None:
        if not callable(clock):
            raise TypeError("clock must be callable")
        self._clock = clock
        super().__init__(factory)

    def append(
        self,
        *,
        package: ControlledOperationalEvidencePackage,
        package_locator: str,
    ) -> LongitudinalOperationalRecord:
        if package.status not in {
            ControlledOperationalEvidenceStatus.OUTCOME_PENDING,
            ControlledOperationalEvidenceStatus.SETTLED,
        }:
            raise ValueError("only pending or settled packages enter the Longitudinal Index")
        record = _record_from_package(
            package=package,
            package_locator=package_locator,
            indexed_at=self._now(),
        )
        with self._connect() as connection:
            acquire_scope_lock(
                connection,
                namespace="longitudinal-operation",
                identity=str(record.operation_run_id),
            )
            existing = connection.execute(
                "SELECT package_hash FROM longitudinal_operational_index "
                "WHERE operation_run_id = %s",
                (str(record.operation_run_id),),
            ).fetchone()
            if existing is not None:
                if str(existing["package_hash"]) != record.package_hash:
                    raise ValueError("Longitudinal operation identity conflict")
                row = connection.execute(
                    "SELECT * FROM longitudinal_operational_index "
                    "WHERE operation_run_id = %s",
                    (str(record.operation_run_id),),
                ).fetchone()
                if row is None:
                    raise RuntimeError("Longitudinal operation disappeared under lock")
                return _record_from_row(row)
            connection.execute(
                "INSERT INTO longitudinal_operational_index ("
                "decision_date, operation_run_id, universe_id, daily_dataset_id, "
                "minute_dataset_id, feature_set_id, signal_model_id, "
                "signal_model_version, configuration_hashes_json, candidate_count, "
                "signal_state_counts_json, minute_success_count, minute_failure_count, "
                "deadline_status, outcome_status, package_id, package_hash, "
                "package_locator, indexed_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
                "%s, %s, %s, %s, %s, %s)",
                _record_row(record),
            )
        return record

    def get(self, run_id: ArtifactId) -> LongitudinalOperationalRecord:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM longitudinal_operational_index "
                "WHERE operation_run_id = %s",
                (str(run_id),),
            ).fetchone()
        if row is None:
            raise KeyError(str(run_id))
        return _record_from_row(row)

    def get_by_package_id(
        self, package_id: ArtifactId
    ) -> LongitudinalOperationalRecord:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM longitudinal_operational_index "
                "WHERE package_id = %s ORDER BY operation_run_id",
                (str(package_id),),
            ).fetchall()
        if len(rows) != 1:
            raise KeyError(str(package_id))
        return _record_from_row(rows[0])

    def query(
        self,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
        signal_model_id: str | None = None,
        signal_model_version: str | None = None,
    ) -> tuple[LongitudinalOperationalRecord, ...]:
        clauses: list[str] = []
        parameters: list[object] = []
        if start_date is not None:
            clauses.append("decision_date >= %s")
            parameters.append(start_date)
        if end_date is not None:
            clauses.append("decision_date <= %s")
            parameters.append(end_date)
        if signal_model_id is not None:
            clauses.append("signal_model_id = %s")
            parameters.append(signal_model_id)
        if signal_model_version is not None:
            clauses.append("signal_model_version = %s")
            parameters.append(signal_model_version)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM longitudinal_operational_index"
                + where
                + " ORDER BY decision_date, operation_run_id",
                tuple(parameters),
            ).fetchall()
        return tuple(_record_from_row(item) for item in rows)

    def configuration_switches(
        self,
    ) -> tuple[tuple[date, tuple[str, ...], tuple[str, ...]], ...]:
        records = self.query()
        return tuple(
            (current.decision_date, prior.configuration_hashes, current.configuration_hashes)
            for prior, current in zip(records, records[1:])
            if prior.configuration_hashes != current.configuration_hashes
        )

    def missing_trading_dates(
        self,
        *,
        calendar: TradingCalendarArtifact,
        start_date: date,
        end_date: date,
    ) -> tuple[date, ...]:
        if end_date < start_date:
            raise ValueError("Longitudinal date range is reversed")
        present = {
            item.decision_date
            for item in self.query(start_date=start_date, end_date=end_date)
        }
        expected = {
            item.trade_date
            for item in calendar.sessions
            if start_date <= item.trade_date <= end_date
        }
        return tuple(sorted(expected - present))

    @classmethod
    def rebuild(
        cls,
        *,
        factory: PostgresConnectionFactory,
        packages: Iterable[tuple[Path, str]],
        clock: Clock = _utc_now,
    ) -> PostgresLongitudinalOperationalIndex:
        index = cls(factory, clock=clock)
        if index.query():
            raise FileExistsError("PostgreSQL Longitudinal rebuild target is not empty")
        for package_path, locator in packages:
            index.append(
                package=load_controlled_operation_package(package_path),
                package_locator=locator,
            )
        return index

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Longitudinal Index clock must be timezone-aware")
        return value.astimezone(timezone.utc).replace(microsecond=0)


def _record_from_package(
    *,
    package: ControlledOperationalEvidencePackage,
    package_locator: str,
    indexed_at: datetime,
) -> LongitudinalOperationalRecord:
    refs = {item.reference_type: item for item in package.evidence_references}
    required = ("OPERATIONAL_UNIVERSE", "DAILY_DATASET", "MINUTE_DATASET")
    if any(item not in refs for item in required):
        raise ValueError("Longitudinal package is missing indexed references")
    return LongitudinalOperationalRecord(
        decision_date=package.command.decision_date,
        operation_run_id=package.command.run_id,
        universe_id=refs["OPERATIONAL_UNIVERSE"].object_id,
        daily_dataset_id=refs["DAILY_DATASET"].object_id,
        minute_dataset_id=refs["MINUTE_DATASET"].object_id,
        feature_set_id=package.feature_set_id,
        signal_model_id=package.signal_model_id,
        signal_model_version=package.signal_model_version,
        configuration_hashes=package.configuration_hashes,
        candidate_count=package.candidate_count,
        signal_state_counts=package.signal_state_counts,
        minute_success_count=package.minute_success_count,
        minute_failure_count=package.minute_failure_count,
        deadline_status=package.deadline_status,
        outcome_status=package.status.value,
        package_id=package.package_id,
        package_hash=package.content_hash,
        package_locator=package_locator,
        indexed_at=indexed_at,
    )


def _record_row(record: LongitudinalOperationalRecord) -> tuple[object, ...]:
    return (
        record.decision_date,
        str(record.operation_run_id),
        str(record.universe_id),
        str(record.daily_dataset_id),
        str(record.minute_dataset_id),
        str(record.feature_set_id),
        record.signal_model_id,
        record.signal_model_version,
        json.dumps(list(record.configuration_hashes), separators=(",", ":")),
        record.candidate_count,
        canonical_json(dict(record.signal_state_counts)),
        record.minute_success_count,
        record.minute_failure_count,
        record.deadline_status,
        record.outcome_status,
        str(record.package_id),
        record.package_hash,
        record.package_locator,
        record.indexed_at,
    )


def _record_from_row(row: dict[str, object]) -> LongitudinalOperationalRecord:
    config = json.loads(str(row["configuration_hashes_json"]))
    signals = json.loads(str(row["signal_state_counts_json"]))
    if not isinstance(config, list) or not isinstance(signals, dict):
        raise ValueError("Longitudinal Index JSON payload is invalid")
    return LongitudinalOperationalRecord(
        decision_date=date_value(row["decision_date"], label="decision_date"),
        operation_run_id=ArtifactId(str(row["operation_run_id"])),
        universe_id=ArtifactId(str(row["universe_id"])),
        daily_dataset_id=ArtifactId(str(row["daily_dataset_id"])),
        minute_dataset_id=ArtifactId(str(row["minute_dataset_id"])),
        feature_set_id=ArtifactId(str(row["feature_set_id"])),
        signal_model_id=str(row["signal_model_id"]),
        signal_model_version=str(row["signal_model_version"]),
        configuration_hashes=tuple(str(item) for item in config),
        candidate_count=int(str(row["candidate_count"])),
        signal_state_counts=tuple(
            sorted((str(key), int(value)) for key, value in signals.items())
        ),
        minute_success_count=int(str(row["minute_success_count"])),
        minute_failure_count=int(str(row["minute_failure_count"])),
        deadline_status=str(row["deadline_status"]),
        outcome_status=str(row["outcome_status"]),
        package_id=ArtifactId(str(row["package_id"])),
        package_hash=str(row["package_hash"]),
        package_locator=str(row["package_locator"]),
        indexed_at=aware_datetime(row["indexed_at"], label="indexed_at"),
    )


__all__ = ["PostgresLongitudinalOperationalIndex"]
