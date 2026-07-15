"""Historical point-in-time Trading Eligibility artifacts.

Eligibility is a policy result, not Universe membership and not final execution feasibility. This
module stores explicit identified eligibility snapshots; it does not infer eligibility from raw
provider fields or silently carry stale states forward to a later Decision Time.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json

from market_regime_alpha.core.identity import ArtifactId, DatasetId
from market_regime_alpha.core.time import AsOfTime, DecisionTime
from market_regime_alpha.universe.contracts import (
    TradingEligibilityRecord,
    TradingEligibilitySnapshot,
    TradingEligibilityStatus,
)


def _validate_optional_non_empty(label: str, value: str | None) -> None:
    if value is not None and (not isinstance(value, str) or not value.strip() or value != value.strip()):
        raise ValueError(f"{label} must be a non-empty trimmed string when present")


@dataclass(frozen=True, slots=True)
class HistoricalTradingEligibilityRecord:
    """One explicit eligibility-policy result at one exact historical as-of time."""

    as_of: AsOfTime
    symbol: str
    status: TradingEligibilityStatus
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.symbol, str) or not self.symbol.strip() or self.symbol != self.symbol.strip():
            raise ValueError("symbol must be a non-empty trimmed string")
        if not isinstance(self.status, TradingEligibilityStatus):
            raise TypeError("status must be a TradingEligibilityStatus")
        for reason in self.reasons:
            if not isinstance(reason, str) or not reason.strip() or reason != reason.strip():
                raise ValueError("eligibility reasons must be non-empty trimmed strings")
        if len(self.reasons) != len(set(self.reasons)):
            raise ValueError("eligibility reasons must be unique")


@dataclass(frozen=True, slots=True)
class HistoricalTradingEligibilityArtifact:
    """Identified exact-time Trading Eligibility snapshots under one policy version."""

    artifact_id: ArtifactId
    source_dataset_id: DatasetId
    policy_version: str
    snapshots: tuple[TradingEligibilitySnapshot, ...]
    policy_artifact_id: ArtifactId | None = None
    materializer_version: str | None = None
    raw_evidence_convention: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.policy_version, str) or not self.policy_version.strip() or self.policy_version != self.policy_version.strip():
            raise ValueError("policy_version must be a non-empty trimmed string")
        _validate_optional_non_empty("materializer_version", self.materializer_version)
        _validate_optional_non_empty("raw_evidence_convention", self.raw_evidence_convention)
        if not self.snapshots:
            raise ValueError("historical Trading Eligibility artifact must contain at least one snapshot")
        times = tuple(snapshot.as_of.value for snapshot in self.snapshots)
        if len(times) != len(set(times)):
            raise ValueError("historical Trading Eligibility snapshot times must be unique")
        if tuple(sorted(times)) != times:
            raise ValueError("historical Trading Eligibility snapshots must be chronological")
        for snapshot in self.snapshots:
            if snapshot.source_dataset_id != self.source_dataset_id:
                raise ValueError("Trading Eligibility snapshot source Dataset mismatch")
            if snapshot.evidence_artifact_id != self.artifact_id:
                raise ValueError("Trading Eligibility snapshot evidence Artifact mismatch")

    @property
    def snapshot_times(self) -> tuple[datetime, ...]:
        return tuple(snapshot.as_of.value for snapshot in self.snapshots)

    def snapshot_at(self, as_of: AsOfTime) -> TradingEligibilitySnapshot:
        """Return one exact-time snapshot; never carry eligibility forward silently."""

        for snapshot in self.snapshots:
            if snapshot.as_of == as_of:
                return snapshot
        raise KeyError(as_of.isoformat())

    def snapshot_for_decision_time(self, decision_time: DecisionTime) -> TradingEligibilitySnapshot:
        """Require an eligibility snapshot identified at the exact Candidate Decision Time."""

        return self.snapshot_at(AsOfTime(decision_time.value))


def build_historical_trading_eligibility_artifact(
    *,
    source_dataset_id: DatasetId,
    policy_version: str,
    records: tuple[HistoricalTradingEligibilityRecord, ...],
    policy_artifact_id: ArtifactId | None = None,
    materializer_version: str | None = None,
    raw_evidence_convention: str | None = None,
    snapshot_as_of_times: tuple[AsOfTime, ...] = (),
) -> HistoricalTradingEligibilityArtifact:
    """Build deterministic exact-time eligibility snapshots from explicit policy results.

    ``snapshot_as_of_times`` preserves identified empty snapshots when a valid historical Universe
    contains no members at a Decision Time. A valid empty opportunity set must not disappear merely
    because there are zero symbol-level eligibility records.
    """

    if not isinstance(policy_version, str) or not policy_version.strip() or policy_version != policy_version.strip():
        raise ValueError("policy_version must be a non-empty trimmed string")
    _validate_optional_non_empty("materializer_version", materializer_version)
    _validate_optional_non_empty("raw_evidence_convention", raw_evidence_convention)
    if any(not isinstance(as_of, AsOfTime) for as_of in snapshot_as_of_times):
        raise TypeError("snapshot_as_of_times must contain AsOfTime values")
    explicit_times = tuple(as_of.value for as_of in snapshot_as_of_times)
    if len(explicit_times) != len(set(explicit_times)):
        raise ValueError("snapshot_as_of_times must be unique")
    if not records and not explicit_times:
        raise ValueError("historical Trading Eligibility artifact requires records or explicit snapshot times")

    keys = tuple((record.as_of.value, record.symbol) for record in records)
    if len(keys) != len(set(keys)):
        raise ValueError("historical Trading Eligibility records must have unique time-symbol keys")
    ordered_records = tuple(sorted(records, key=lambda record: (record.as_of.value, record.symbol)))
    all_snapshot_times = tuple(sorted(set(explicit_times) | {record.as_of.value for record in ordered_records}))

    payload = {
        "schema_version": "historical-trading-eligibility-artifact-v4",
        "source_dataset_id": str(source_dataset_id),
        "policy_version": policy_version,
        "policy_artifact_id": str(policy_artifact_id) if policy_artifact_id is not None else None,
        "materializer_version": materializer_version,
        "raw_evidence_convention": raw_evidence_convention,
        "snapshot_as_of_times": [value.isoformat() for value in all_snapshot_times],
        "records": [
            {
                "as_of": record.as_of.isoformat(),
                "symbol": record.symbol,
                "status": record.status.value,
                "reasons": list(record.reasons),
            }
            for record in ordered_records
        ],
    }
    canonical = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    digest = sha256(canonical.encode("utf-8")).hexdigest()
    artifact_id = ArtifactId(f"trading-eligibility-artifact-{digest[:24]}")

    by_time: dict[datetime, list[HistoricalTradingEligibilityRecord]] = defaultdict(list)
    for as_of_value in all_snapshot_times:
        by_time[as_of_value]
    for record in ordered_records:
        by_time[record.as_of.value].append(record)

    snapshots = tuple(
        TradingEligibilitySnapshot(
            as_of=AsOfTime(as_of_value),
            source_dataset_id=source_dataset_id,
            evidence_artifact_id=artifact_id,
            records=tuple(
                TradingEligibilityRecord(
                    symbol=record.symbol,
                    status=record.status,
                    reasons=record.reasons,
                )
                for record in time_records
            ),
        )
        for as_of_value, time_records in sorted(by_time.items())
    )
    return HistoricalTradingEligibilityArtifact(
        artifact_id=artifact_id,
        source_dataset_id=source_dataset_id,
        policy_version=policy_version,
        snapshots=snapshots,
        policy_artifact_id=policy_artifact_id,
        materializer_version=materializer_version,
        raw_evidence_convention=raw_evidence_convention,
    )
