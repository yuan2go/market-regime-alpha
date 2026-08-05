"""Append-only discovery index over immutable Controlled operation packages."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import json
from pathlib import Path, PurePosixPath
import sqlite3
from threading import Lock
from typing import Callable, Iterable, Protocol

from market_regime_alpha.application.controlled_operation.evidence_package import (
    ControlledOperationalEvidencePackage,
    ControlledOperationalEvidenceStatus,
    load_controlled_operation_package,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.trading_calendar import TradingCalendarArtifact
from market_regime_alpha.evidence.canonical import canonical_json, require_sha256


LONGITUDINAL_INDEX_MIGRATION = (
    Path(__file__).resolve().parent
    / "migrations"
    / "015_longitudinal_operational_index_up.sql"
)
Clock = Callable[[], datetime]
_SCHEMA_LOCK = Lock()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


@dataclass(frozen=True, slots=True)
class LongitudinalOperationalRecord:
    decision_date: date
    operation_run_id: ArtifactId
    universe_id: ArtifactId
    daily_dataset_id: ArtifactId
    minute_dataset_id: ArtifactId
    feature_set_id: ArtifactId
    signal_model_id: str
    signal_model_version: str
    configuration_hashes: tuple[str, ...]
    candidate_count: int
    signal_state_counts: tuple[tuple[str, int], ...]
    minute_success_count: int
    minute_failure_count: int
    deadline_status: str
    outcome_status: str
    package_id: ArtifactId
    package_hash: str
    package_locator: str
    indexed_at: datetime

    def __post_init__(self) -> None:
        require_sha256("package_hash", self.package_hash)
        if self.configuration_hashes != tuple(sorted(set(self.configuration_hashes))):
            raise ValueError("Longitudinal configuration hashes must be unique and sorted")
        for digest in self.configuration_hashes:
            require_sha256("configuration hash", digest)
        if self.signal_state_counts != tuple(sorted(set(self.signal_state_counts))):
            raise ValueError("Longitudinal Signal counts must be unique and sorted")
        if self.minute_success_count + self.minute_failure_count != self.candidate_count:
            raise ValueError("Longitudinal minute coverage counts mismatch")
        path = PurePosixPath(self.package_locator)
        if path.is_absolute() or ".." in path.parts or self.package_locator != path.as_posix():
            raise ValueError("Longitudinal package locator must be relative")
        if self.outcome_status not in {"OUTCOME_PENDING", "SETTLED"}:
            raise ValueError("Longitudinal Outcome status is invalid")


class LongitudinalOperationalIndex(Protocol):
    def append(
        self,
        *,
        package: ControlledOperationalEvidencePackage,
        package_locator: str,
    ) -> LongitudinalOperationalRecord: ...


class SQLiteLongitudinalOperationalIndex:
    """A rebuildable index; packages remain the evidence authority."""

    def __init__(self, path: Path, *, clock: Clock = _utc_now) -> None:
        self.path = path.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._clock = clock
        with _SCHEMA_LOCK, self._connect() as connection:
            connection.executescript(LONGITUDINAL_INDEX_MIGRATION.read_text(encoding="utf-8"))

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
            existing = connection.execute(
                "SELECT package_hash FROM longitudinal_operational_index WHERE operation_run_id = ?",
                (str(record.operation_run_id),),
            ).fetchone()
            if existing is not None:
                if str(existing["package_hash"]) != record.package_hash:
                    raise ValueError("Longitudinal operation identity conflict")
                return self.get(record.operation_run_id)
            connection.execute(
                "INSERT INTO longitudinal_operational_index ("
                "decision_date, operation_run_id, universe_id, daily_dataset_id, minute_dataset_id, "
                "feature_set_id, signal_model_id, signal_model_version, configuration_hashes_json, "
                "candidate_count, signal_state_counts_json, minute_success_count, minute_failure_count, "
                "deadline_status, outcome_status, package_id, package_hash, package_locator, indexed_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                _record_row(record),
            )
        return record

    def get(self, run_id: ArtifactId) -> LongitudinalOperationalRecord:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM longitudinal_operational_index WHERE operation_run_id = ?",
                (str(run_id),),
            ).fetchone()
        if row is None:
            raise KeyError(str(run_id))
        return _record_from_row(row)

    def query(
        self,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
        signal_model_id: str | None = None,
        signal_model_version: str | None = None,
    ) -> tuple[LongitudinalOperationalRecord, ...]:
        clauses: list[str] = []
        parameters: list[str] = []
        if start_date is not None:
            clauses.append("decision_date >= ?")
            parameters.append(start_date.isoformat())
        if end_date is not None:
            clauses.append("decision_date <= ?")
            parameters.append(end_date.isoformat())
        if signal_model_id is not None:
            clauses.append("signal_model_id = ?")
            parameters.append(signal_model_id)
        if signal_model_version is not None:
            clauses.append("signal_model_version = ?")
            parameters.append(signal_model_version)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self._connect() as connection:
            rows = tuple(
                connection.execute(
                    "SELECT * FROM longitudinal_operational_index"
                    + where
                    + " ORDER BY decision_date, operation_run_id",
                    tuple(parameters),
                )
            )
        return tuple(_record_from_row(item) for item in rows)

    def configuration_switches(self) -> tuple[tuple[date, tuple[str, ...], tuple[str, ...]], ...]:
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
        present = {item.decision_date for item in self.query(start_date=start_date, end_date=end_date)}
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
        path: Path,
        packages: Iterable[tuple[Path, str]],
        clock: Clock = _utc_now,
    ) -> SQLiteLongitudinalOperationalIndex:
        if path.exists():
            raise FileExistsError("Longitudinal rebuild destination already exists")
        index = cls(path, clock=clock)
        for package_path, locator in packages:
            index.append(
                package=load_controlled_operation_package(package_path),
                package_locator=locator,
            )
        return index

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

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
        record.decision_date.isoformat(), str(record.operation_run_id), str(record.universe_id),
        str(record.daily_dataset_id), str(record.minute_dataset_id), str(record.feature_set_id),
        record.signal_model_id, record.signal_model_version,
        json.dumps(list(record.configuration_hashes), separators=(",", ":")),
        record.candidate_count,
        canonical_json(dict(record.signal_state_counts)),
        record.minute_success_count, record.minute_failure_count, record.deadline_status,
        record.outcome_status, str(record.package_id), record.package_hash, record.package_locator,
        record.indexed_at.isoformat().replace("+00:00", "Z"),
    )


def _record_from_row(row: sqlite3.Row) -> LongitudinalOperationalRecord:
    config = json.loads(str(row["configuration_hashes_json"]))
    signals = json.loads(str(row["signal_state_counts_json"]))
    if not isinstance(config, list) or not isinstance(signals, dict):
        raise ValueError("Longitudinal Index JSON payload is invalid")
    return LongitudinalOperationalRecord(
        decision_date=date.fromisoformat(str(row["decision_date"])),
        operation_run_id=ArtifactId(str(row["operation_run_id"])),
        universe_id=ArtifactId(str(row["universe_id"])),
        daily_dataset_id=ArtifactId(str(row["daily_dataset_id"])),
        minute_dataset_id=ArtifactId(str(row["minute_dataset_id"])),
        feature_set_id=ArtifactId(str(row["feature_set_id"])),
        signal_model_id=str(row["signal_model_id"]),
        signal_model_version=str(row["signal_model_version"]),
        configuration_hashes=tuple(str(item) for item in config),
        candidate_count=int(row["candidate_count"]),
        signal_state_counts=tuple(sorted((str(key), int(value)) for key, value in signals.items())),
        minute_success_count=int(row["minute_success_count"]),
        minute_failure_count=int(row["minute_failure_count"]),
        deadline_status=str(row["deadline_status"]),
        outcome_status=str(row["outcome_status"]),
        package_id=ArtifactId(str(row["package_id"])),
        package_hash=str(row["package_hash"]),
        package_locator=str(row["package_locator"]),
        indexed_at=datetime.fromisoformat(str(row["indexed_at"]).replace("Z", "+00:00")),
    )


__all__ = [
    "LONGITUDINAL_INDEX_MIGRATION",
    "LongitudinalOperationalRecord",
    "SQLiteLongitudinalOperationalIndex",
]
