"""Historical point-in-time Universe membership artifacts.

Membership is intentionally separate from Trading Eligibility. A historical Universe artifact
answers which symbols belong to the declared research population under an explicit effective-
time convention; it does not claim those symbols are tradable, buyable, liquid, or execution-
feasible.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time
from hashlib import sha256
import json
from zoneinfo import ZoneInfo

from market_regime_alpha.core.identity import ArtifactId, DatasetId, UniverseId
from market_regime_alpha.core.time import AsOfTime, DecisionTime
from market_regime_alpha.universe.contracts import PITUniverseSnapshot, UniverseMembershipRecord


@dataclass(frozen=True, slots=True)
class HistoricalUniverseMembershipRecord:
    """One explicit symbol membership state on one historical as-of date."""

    as_of_date: date
    symbol: str
    is_member: bool

    def __post_init__(self) -> None:
        if not isinstance(self.as_of_date, date):
            raise TypeError("as_of_date must be a date")
        if not isinstance(self.symbol, str) or not self.symbol.strip() or self.symbol != self.symbol.strip():
            raise ValueError("symbol must be a non-empty trimmed string")
        if not isinstance(self.is_member, bool):
            raise TypeError("is_member must be boolean")


@dataclass(frozen=True, slots=True)
class HistoricalPITUniverseArtifact:
    """Identified collection of exact-date PIT Universe snapshots."""

    artifact_id: ArtifactId
    source_dataset_id: DatasetId
    method_version: str
    timezone_name: str
    effective_time_convention: str
    snapshots: tuple[PITUniverseSnapshot, ...]

    def __post_init__(self) -> None:
        for label, value in (
            ("method_version", self.method_version),
            ("timezone_name", self.timezone_name),
            ("effective_time_convention", self.effective_time_convention),
        ):
            if not isinstance(value, str) or not value.strip() or value != value.strip():
                raise ValueError(f"{label} must be a non-empty trimmed string")
        if not self.snapshots:
            raise ValueError("historical PIT Universe artifact must contain at least one snapshot")
        dates = tuple(self._snapshot_date(snapshot) for snapshot in self.snapshots)
        if len(dates) != len(set(dates)):
            raise ValueError("historical PIT Universe snapshot dates must be unique")
        if tuple(sorted(dates)) != dates:
            raise ValueError("historical PIT Universe snapshots must be chronological")
        for snapshot in self.snapshots:
            if snapshot.source_dataset_id != self.source_dataset_id:
                raise ValueError("historical PIT Universe snapshot source Dataset mismatch")
            if snapshot.evidence_artifact_id != self.artifact_id:
                raise ValueError("historical PIT Universe snapshot evidence Artifact mismatch")
            if snapshot.method_version != self.method_version:
                raise ValueError("historical PIT Universe snapshot method version mismatch")

    @property
    def snapshot_dates(self) -> tuple[date, ...]:
        return tuple(self._snapshot_date(snapshot) for snapshot in self.snapshots)

    def snapshot_on(self, as_of_date: date) -> PITUniverseSnapshot:
        """Return the exact-date snapshot; never carry membership forward silently."""

        for snapshot in self.snapshots:
            if self._snapshot_date(snapshot) == as_of_date:
                return snapshot
        raise KeyError(as_of_date.isoformat())

    def snapshot_for_decision_time(self, decision_time: DecisionTime) -> PITUniverseSnapshot:
        """Resolve only the snapshot for the Decision Time's local calendar date."""

        local_date = decision_time.value.astimezone(ZoneInfo(self.timezone_name)).date()
        snapshot = self.snapshot_on(local_date)
        if snapshot.as_of.value > decision_time.value:
            raise ValueError("PIT Universe snapshot is not available by Decision Time")
        return snapshot

    def _snapshot_date(self, snapshot: PITUniverseSnapshot) -> date:
        return snapshot.as_of.value.astimezone(ZoneInfo(self.timezone_name)).date()


def build_historical_pit_universe_artifact(
    *,
    source_dataset_id: DatasetId,
    method_version: str,
    timezone_name: str,
    effective_time_convention: str,
    records: tuple[HistoricalUniverseMembershipRecord, ...],
) -> HistoricalPITUniverseArtifact:
    """Build deterministic exact-date PIT Universe snapshots from explicit membership records."""

    for label, value in (
        ("method_version", method_version),
        ("timezone_name", timezone_name),
        ("effective_time_convention", effective_time_convention),
    ):
        if not isinstance(value, str) or not value.strip() or value != value.strip():
            raise ValueError(f"{label} must be a non-empty trimmed string")
    if not records:
        raise ValueError("historical PIT Universe records must not be empty")
    keys = tuple((record.as_of_date, record.symbol) for record in records)
    if len(keys) != len(set(keys)):
        raise ValueError("historical PIT Universe records must have unique date-symbol keys")
    ordered_records = tuple(sorted(records, key=lambda record: (record.as_of_date, record.symbol)))

    payload = {
        "schema_version": "historical-pit-universe-artifact-v2",
        "source_dataset_id": str(source_dataset_id),
        "method_version": method_version,
        "timezone_name": timezone_name,
        "effective_time_convention": effective_time_convention,
        "records": [
            {
                "as_of_date": record.as_of_date.isoformat(),
                "symbol": record.symbol,
                "is_member": record.is_member,
            }
            for record in ordered_records
        ],
    }
    canonical = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    digest = sha256(canonical.encode("utf-8")).hexdigest()
    artifact_id = ArtifactId(f"pit-universe-artifact-{digest[:24]}")

    by_date: dict[date, list[HistoricalUniverseMembershipRecord]] = defaultdict(list)
    for record in ordered_records:
        by_date[record.as_of_date].append(record)

    zone = ZoneInfo(timezone_name)
    snapshots = tuple(
        _build_snapshot(
            source_dataset_id=source_dataset_id,
            evidence_artifact_id=artifact_id,
            method_version=method_version,
            timezone_name=timezone_name,
            effective_time_convention=effective_time_convention,
            as_of_date=as_of_date,
            records=tuple(date_records),
            zone=zone,
        )
        for as_of_date, date_records in sorted(by_date.items())
    )
    return HistoricalPITUniverseArtifact(
        artifact_id=artifact_id,
        source_dataset_id=source_dataset_id,
        method_version=method_version,
        timezone_name=timezone_name,
        effective_time_convention=effective_time_convention,
        snapshots=snapshots,
    )


def _build_snapshot(
    *,
    source_dataset_id: DatasetId,
    evidence_artifact_id: ArtifactId,
    method_version: str,
    timezone_name: str,
    effective_time_convention: str,
    as_of_date: date,
    records: tuple[HistoricalUniverseMembershipRecord, ...],
    zone: ZoneInfo,
) -> PITUniverseSnapshot:
    snapshot_payload = {
        "schema_version": "pit-universe-snapshot-v2",
        "source_dataset_id": str(source_dataset_id),
        "method_version": method_version,
        "timezone_name": timezone_name,
        "effective_time_convention": effective_time_convention,
        "as_of_date": as_of_date.isoformat(),
        "records": [
            {"symbol": record.symbol, "is_member": record.is_member}
            for record in records
        ],
    }
    canonical = json.dumps(snapshot_payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    digest = sha256(canonical.encode("utf-8")).hexdigest()
    as_of = AsOfTime(datetime.combine(as_of_date, time.min, tzinfo=zone))
    return PITUniverseSnapshot(
        universe_id=UniverseId(f"pit-universe-{digest[:24]}"),
        as_of=as_of,
        source_dataset_id=source_dataset_id,
        evidence_artifact_id=evidence_artifact_id,
        method_version=method_version,
        records=tuple(
            UniverseMembershipRecord(symbol=record.symbol, is_member=record.is_member)
            for record in records
        ),
    )
