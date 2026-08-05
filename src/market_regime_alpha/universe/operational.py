"""Controlled exploratory Operational Universe artifact and immutable package."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Mapping

from market_regime_alpha.core.identity import ArtifactId, UniverseId
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    canonical_json,
    require_sha256,
    require_text,
    require_unique_text,
)
from market_regime_alpha.market_data import (
    AssetType,
    Exchange,
    FormalPitStatus,
)
from market_regime_alpha.market_data.contracts import (
    parse_utc_second,
    require_decimal,
    require_utc_second,
)


OPERATIONAL_UNIVERSE_SCHEMA = "operational-universe-artifact-v1"


class ListingStatus(str, Enum):
    LISTED = "LISTED"
    DELISTED = "DELISTED"
    UNKNOWN = "UNKNOWN"


class STStatus(str, Enum):
    NOT_ST = "NOT_ST"
    ST = "ST"
    UNKNOWN = "UNKNOWN"


class SuspensionStatus(str, Enum):
    NOT_SUSPENDED = "NOT_SUSPENDED"
    SUSPENDED = "SUSPENDED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class OperationalLiquidityEvidence:
    lookback_sessions: int
    observed_sessions: int
    median_daily_amount: Decimal | None
    minimum_daily_amount: Decimal | None
    available_at: datetime
    source_artifact_id: ArtifactId
    source_content_hash: str

    def __post_init__(self) -> None:
        if (
            isinstance(self.lookback_sessions, bool)
            or not isinstance(self.lookback_sessions, int)
            or self.lookback_sessions <= 0
        ):
            raise ValueError("lookback_sessions must be positive")
        if (
            isinstance(self.observed_sessions, bool)
            or not isinstance(self.observed_sessions, int)
            or not 0 <= self.observed_sessions <= self.lookback_sessions
        ):
            raise ValueError("observed_sessions is outside lookback scope")
        for label, value in (
            ("median_daily_amount", self.median_daily_amount),
            ("minimum_daily_amount", self.minimum_daily_amount),
        ):
            if value is not None:
                require_decimal(label, value, non_negative=True)
        require_utc_second("liquidity available_at", self.available_at)
        require_sha256("liquidity source_content_hash", self.source_content_hash)

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "lookback_sessions": self.lookback_sessions,
            "observed_sessions": self.observed_sessions,
            "median_daily_amount": _decimal(self.median_daily_amount),
            "minimum_daily_amount": _decimal(self.minimum_daily_amount),
            "available_at": canonical_datetime(self.available_at),
            "source_artifact_id": str(self.source_artifact_id),
            "source_content_hash": self.source_content_hash,
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> OperationalLiquidityEvidence:
        _exact(
            payload,
            {
                "lookback_sessions",
                "observed_sessions",
                "median_daily_amount",
                "minimum_daily_amount",
                "available_at",
                "source_artifact_id",
                "source_content_hash",
            },
            "Operational liquidity evidence",
        )
        return cls(
            lookback_sessions=_integer(payload["lookback_sessions"], "lookback_sessions"),
            observed_sessions=_integer(payload["observed_sessions"], "observed_sessions"),
            median_daily_amount=_parse_decimal(payload["median_daily_amount"]),
            minimum_daily_amount=_parse_decimal(payload["minimum_daily_amount"]),
            available_at=parse_utc_second("available_at", payload["available_at"]),
            source_artifact_id=ArtifactId(str(payload["source_artifact_id"])),
            source_content_hash=str(payload["source_content_hash"]),
        )


@dataclass(frozen=True, slots=True)
class OperationalUniverseRecord:
    symbol: str
    asset_type: AssetType
    exchange: Exchange
    membership_source: str
    listing_status: ListingStatus
    st_status: STStatus
    suspension_status: SuspensionStatus
    liquidity_evidence: OperationalLiquidityEvidence
    history_sessions_observed: int
    history_sessions_required: int
    included: bool
    inclusion_reasons: tuple[str, ...]
    exclusion_reasons: tuple[str, ...]
    source_artifact_references: tuple[tuple[ArtifactId, str], ...]
    data_eligibility: DataEligibility

    def __post_init__(self) -> None:
        require_text("symbol", self.symbol)
        require_text("membership_source", self.membership_source)
        for label, value in (
            ("history_sessions_observed", self.history_sessions_observed),
            ("history_sessions_required", self.history_sessions_required),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{label} must be a non-negative integer")
        if self.history_sessions_required <= 0:
            raise ValueError("history_sessions_required must be positive")
        require_unique_text("inclusion reason", self.inclusion_reasons)
        require_unique_text("exclusion reason", self.exclusion_reasons)
        if self.inclusion_reasons != tuple(sorted(self.inclusion_reasons)):
            raise ValueError("inclusion reasons must be sorted")
        if self.exclusion_reasons != tuple(sorted(self.exclusion_reasons)):
            raise ValueError("exclusion reasons must be sorted")
        if self.included and (not self.inclusion_reasons or self.exclusion_reasons):
            raise ValueError("included record requires only inclusion reasons")
        if not self.included and (not self.exclusion_reasons or self.inclusion_reasons):
            raise ValueError("excluded record requires only exclusion reasons")
        refs = tuple((str(item), digest) for item, digest in self.source_artifact_references)
        if not refs or refs != tuple(sorted(set(refs))):
            raise ValueError("source artifact references must be non-empty and sorted")
        for _, digest in self.source_artifact_references:
            require_sha256("source artifact hash", digest)

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "asset_type": self.asset_type.value,
            "exchange": self.exchange.value,
            "membership_source": self.membership_source,
            "listing_status": self.listing_status.value,
            "st_status": self.st_status.value,
            "suspension_status": self.suspension_status.value,
            "liquidity_evidence": self.liquidity_evidence.to_canonical_dict(),
            "history_sessions_observed": self.history_sessions_observed,
            "history_sessions_required": self.history_sessions_required,
            "included": self.included,
            "inclusion_reasons": list(self.inclusion_reasons),
            "exclusion_reasons": list(self.exclusion_reasons),
            "source_artifact_references": [
                {"artifact_id": str(item), "content_hash": digest}
                for item, digest in self.source_artifact_references
            ],
            "data_eligibility": self.data_eligibility.value,
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> OperationalUniverseRecord:
        _exact(
            payload,
            {
                "symbol",
                "asset_type",
                "exchange",
                "membership_source",
                "listing_status",
                "st_status",
                "suspension_status",
                "liquidity_evidence",
                "history_sessions_observed",
                "history_sessions_required",
                "included",
                "inclusion_reasons",
                "exclusion_reasons",
                "source_artifact_references",
                "data_eligibility",
            },
            "Operational Universe record",
        )
        liquidity = payload["liquidity_evidence"]
        if not isinstance(liquidity, dict):
            raise ValueError("liquidity_evidence must be an object")
        refs = _object_array(payload["source_artifact_references"], "source references")
        return cls(
            symbol=str(payload["symbol"]),
            asset_type=AssetType(str(payload["asset_type"])),
            exchange=Exchange(str(payload["exchange"])),
            membership_source=str(payload["membership_source"]),
            listing_status=ListingStatus(str(payload["listing_status"])),
            st_status=STStatus(str(payload["st_status"])),
            suspension_status=SuspensionStatus(str(payload["suspension_status"])),
            liquidity_evidence=OperationalLiquidityEvidence.from_canonical_dict(liquidity),
            history_sessions_observed=_integer(
                payload["history_sessions_observed"], "history_sessions_observed"
            ),
            history_sessions_required=_integer(
                payload["history_sessions_required"], "history_sessions_required"
            ),
            included=_boolean(payload["included"], "included"),
            inclusion_reasons=_string_tuple(payload["inclusion_reasons"], "inclusion reasons"),
            exclusion_reasons=_string_tuple(payload["exclusion_reasons"], "exclusion reasons"),
            source_artifact_references=tuple(
                (
                    ArtifactId(str(_required(item, "artifact_id"))),
                    str(_required(item, "content_hash")),
                )
                for item in refs
            ),
            data_eligibility=DataEligibility(str(payload["data_eligibility"])),
        )


@dataclass(frozen=True, slots=True)
class OperationalUniverseArtifact:
    schema_version: str
    universe_id: UniverseId
    content_hash: str
    decision_date: date
    effective_at: datetime
    available_at: datetime
    records: tuple[OperationalUniverseRecord, ...]
    formal_pit_status: FormalPitStatus
    data_eligibility: DataEligibility
    source_artifact_references: tuple[tuple[ArtifactId, str], ...]
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != OPERATIONAL_UNIVERSE_SCHEMA:
            raise ValueError("unsupported Operational Universe schema")
        require_sha256("content_hash", self.content_hash)
        require_utc_second("effective_at", self.effective_at)
        require_utc_second("available_at", self.available_at)
        if self.available_at < self.effective_at:
            raise ValueError("Operational Universe cannot be available before effective_at")
        symbols = tuple(item.symbol for item in self.records)
        if not self.records or symbols != tuple(sorted(set(symbols))):
            raise ValueError("Operational Universe records must be non-empty and sorted")
        if not 1 <= len(self.symbols) <= 300:
            raise ValueError("Operational Universe included scope must be 1 to 300 Symbols")
        refs = tuple((str(item), digest) for item, digest in self.source_artifact_references)
        if not refs or refs != tuple(sorted(set(refs))):
            raise ValueError("Operational Universe sources must be non-empty and sorted")
        for _, digest in self.source_artifact_references:
            require_sha256("Operational Universe source hash", digest)
        require_unique_text("Operational Universe limitation", self.limitations)
        if self.limitations != tuple(sorted(self.limitations)):
            raise ValueError("Operational Universe limitations must be sorted")
        if self.formal_pit_status is FormalPitStatus.FORMAL_PIT_NOT_ESTABLISHED:
            if "FORMAL_PIT_NOT_ESTABLISHED" not in self.limitations:
                raise ValueError("exploratory Universe must preserve formal PIT limitation")
        elif self.data_eligibility is not DataEligibility.FORMAL_RESEARCH:
            raise ValueError("PIT-correct Universe requires FORMAL_RESEARCH eligibility")

    @property
    def symbols(self) -> tuple[str, ...]:
        return tuple(item.symbol for item in self.records if item.included)

    @classmethod
    def create(
        cls,
        *,
        decision_date: date,
        effective_at: datetime,
        available_at: datetime,
        records: tuple[OperationalUniverseRecord, ...],
        formal_pit_status: FormalPitStatus,
        data_eligibility: DataEligibility,
        source_artifact_references: tuple[tuple[ArtifactId, str], ...],
        limitations: tuple[str, ...],
    ) -> OperationalUniverseArtifact:
        ordered = tuple(sorted(records, key=lambda item: item.symbol))
        sources = tuple(sorted(source_artifact_references, key=lambda item: (str(item[0]), item[1])))
        limitations = tuple(sorted(limitations))
        semantic = _universe_payload(
            decision_date=decision_date,
            effective_at=effective_at,
            available_at=available_at,
            records=ordered,
            formal_pit_status=formal_pit_status,
            data_eligibility=data_eligibility,
            source_artifact_references=sources,
            limitations=limitations,
        )
        digest = canonical_hash(semantic)
        result = cls(
            schema_version=OPERATIONAL_UNIVERSE_SCHEMA,
            universe_id=UniverseId(f"operational-universe-{digest.split(':', 1)[1][:24]}"),
            content_hash=digest,
            decision_date=decision_date,
            effective_at=effective_at,
            available_at=available_at,
            records=ordered,
            formal_pit_status=formal_pit_status,
            data_eligibility=data_eligibility,
            source_artifact_references=sources,
            limitations=limitations,
        )
        result.verify_identity()
        return result

    def semantic_payload(self) -> dict[str, Any]:
        return _universe_payload(
            decision_date=self.decision_date,
            effective_at=self.effective_at,
            available_at=self.available_at,
            records=self.records,
            formal_pit_status=self.formal_pit_status,
            data_eligibility=self.data_eligibility,
            source_artifact_references=self.source_artifact_references,
            limitations=self.limitations,
        )

    def verify_identity(self) -> None:
        digest = canonical_hash(self.semantic_payload())
        if digest != self.content_hash:
            raise ValueError("Operational Universe content hash mismatch")
        if str(self.universe_id) != f"operational-universe-{digest.split(':', 1)[1][:24]}":
            raise ValueError("Operational Universe identity mismatch")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "universe_id": str(self.universe_id),
            "content_hash": self.content_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> OperationalUniverseArtifact:
        expected = {
            "schema_version",
            "universe_id",
            "content_hash",
            "decision_date",
            "effective_at",
            "available_at",
            "records",
            "formal_pit_status",
            "data_eligibility",
            "source_artifact_references",
            "limitations",
        }
        _exact(payload, expected, "Operational Universe")
        records = _object_array(payload["records"], "records")
        refs = _object_array(payload["source_artifact_references"], "source references")
        result = cls(
            schema_version=str(payload["schema_version"]),
            universe_id=UniverseId(str(payload["universe_id"])),
            content_hash=str(payload["content_hash"]),
            decision_date=date.fromisoformat(str(payload["decision_date"])),
            effective_at=parse_utc_second("effective_at", payload["effective_at"]),
            available_at=parse_utc_second("available_at", payload["available_at"]),
            records=tuple(OperationalUniverseRecord.from_canonical_dict(item) for item in records),
            formal_pit_status=FormalPitStatus(str(payload["formal_pit_status"])),
            data_eligibility=DataEligibility(str(payload["data_eligibility"])),
            source_artifact_references=tuple(
                (ArtifactId(str(_required(item, "artifact_id"))), str(_required(item, "content_hash")))
                for item in refs
            ),
            limitations=_string_tuple(payload["limitations"], "limitations"),
        )
        result.verify_identity()
        return result


def publish_operational_universe(
    *, root: Path, artifact: OperationalUniverseArtifact
) -> Path:
    artifact.verify_identity()
    root.mkdir(parents=True, exist_ok=True)
    final = root / str(artifact.universe_id)
    if final.exists():
        if load_operational_universe(final) != artifact:
            raise FileExistsError("conflicting Operational Universe exists")
        return final
    stage = Path(tempfile.mkdtemp(prefix=f".{final.name}.", dir=root))
    installed = False
    try:
        payload = (canonical_json(artifact.to_canonical_dict()) + "\n").encode()
        (stage / "artifact.json").write_bytes(payload)
        checksums = {"artifact.json": f"sha256:{sha256(payload).hexdigest()}"}
        (stage / "SHA256SUMS.json").write_text(
            canonical_json(checksums) + "\n", encoding="utf-8"
        )
        _fsync_tree(stage)
        _load_operational_universe(stage, enforce_identity=False)
        os.replace(stage, final)
        installed = True
        _fsync_directory(root)
        return final
    finally:
        if not installed and stage.exists():
            shutil.rmtree(stage)


def load_operational_universe(path: Path) -> OperationalUniverseArtifact:
    return _load_operational_universe(path, enforce_identity=True)


def _load_operational_universe(
    path: Path, *, enforce_identity: bool
) -> OperationalUniverseArtifact:
    root = path.resolve()
    if not root.is_dir() or {item.name for item in root.iterdir()} != {
        "SHA256SUMS.json",
        "artifact.json",
    }:
        raise ValueError("Operational Universe exact file set mismatch")
    checksums = json.loads((root / "SHA256SUMS.json").read_text(encoding="utf-8"))
    raw = (root / "artifact.json").read_bytes()
    if checksums != {"artifact.json": f"sha256:{sha256(raw).hexdigest()}"}:
        raise ValueError("Operational Universe checksum mismatch")
    payload = json.loads(raw)
    if not isinstance(payload, dict) or raw != (canonical_json(payload) + "\n").encode():
        raise ValueError("Operational Universe artifact JSON is not canonical")
    artifact = OperationalUniverseArtifact.from_canonical_dict(payload)
    if enforce_identity and root.name != str(artifact.universe_id):
        raise ValueError("Operational Universe directory identity mismatch")
    return artifact


def _universe_payload(
    *,
    decision_date: date,
    effective_at: datetime,
    available_at: datetime,
    records: tuple[OperationalUniverseRecord, ...],
    formal_pit_status: FormalPitStatus,
    data_eligibility: DataEligibility,
    source_artifact_references: tuple[tuple[ArtifactId, str], ...],
    limitations: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "schema_version": OPERATIONAL_UNIVERSE_SCHEMA,
        "decision_date": decision_date.isoformat(),
        "effective_at": canonical_datetime(effective_at),
        "available_at": canonical_datetime(available_at),
        "records": [item.to_canonical_dict() for item in records],
        "formal_pit_status": formal_pit_status.value,
        "data_eligibility": data_eligibility.value,
        "source_artifact_references": [
            {"artifact_id": str(item), "content_hash": digest}
            for item, digest in source_artifact_references
        ],
        "limitations": list(limitations),
    }


def _decimal(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


def _parse_decimal(value: object) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be boolean")
    return value


def _string_tuple(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be a string array")
    return tuple(value)


def _object_array(value: object, label: str) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError(f"{label} must be an object array")
    return tuple(value)


def _required(payload: Mapping[str, Any], key: str) -> object:
    if key not in payload:
        raise ValueError(f"missing {key}")
    return payload[key]


def _exact(payload: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(payload) != expected:
        raise ValueError(f"{label} fields mismatch")


def _fsync_tree(root: Path) -> None:
    for path in root.iterdir():
        with path.open("rb") as handle:
            os.fsync(handle.fileno())
    _fsync_directory(root)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


__all__ = [
    "ListingStatus",
    "OPERATIONAL_UNIVERSE_SCHEMA",
    "OperationalLiquidityEvidence",
    "OperationalUniverseArtifact",
    "OperationalUniverseRecord",
    "STStatus",
    "SuspensionStatus",
    "load_operational_universe",
    "publish_operational_universe",
]
