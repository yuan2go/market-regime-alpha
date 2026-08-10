"""Exploratory full-market Security Master and historical Research Universe.

BaoStock's current ``query_stock_basic`` response is useful engineering input,
but it does not disclose historical publication time.  Every snapshot therefore
uses retrieval time as ``known_at`` and remains PIT-incomplete.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any, Mapping

from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
    content_identity,
    timestamp,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.data.pit_contracts import PITSourceEvidenceLevel
from market_regime_alpha.evidence.canonical import (
    canonical_hash,
    require_sha256,
    require_text,
)


class FreeDataEvidenceOrigin(str, Enum):
    REAL_FREE_PROVIDER_OBSERVATION = "REAL_FREE_PROVIDER_OBSERVATION"
    ARCHIVED_REPLAY = "ARCHIVED_REPLAY"
    ENGINEERING_FIXTURE = "ENGINEERING_FIXTURE"


class ResearchUniverseMembershipStatus(str, Enum):
    INCLUDED = "INCLUDED"
    EXCLUDED = "EXCLUDED"
    UNKNOWN = "UNKNOWN"


class SecurityMasterListingStatus(str, Enum):
    LISTED = "LISTED"
    DELISTED = "DELISTED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class FreeResearchUniverseRecord:
    symbol: str
    security_name: str
    provider_security_type: str | None
    listing_date: date | None
    delisting_date: date | None
    listing_status: SecurityMasterListingStatus
    membership_status: ResearchUniverseMembershipStatus
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        require_text("symbol", self.symbol)
        require_text("security_name", self.security_name)
        if self.delisting_date is not None and self.listing_date is not None:
            if self.delisting_date < self.listing_date:
                raise ValueError("Security Master delisting predates listing")
        if self.reason_codes != tuple(sorted(set(self.reason_codes))):
            raise ValueError("Research Universe reasons must be unique and sorted")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "security_name": self.security_name,
            "provider_security_type": self.provider_security_type,
            "listing_date": (
                None if self.listing_date is None else self.listing_date.isoformat()
            ),
            "delisting_date": (
                None
                if self.delisting_date is None
                else self.delisting_date.isoformat()
            ),
            "listing_status": self.listing_status.value,
            "membership_status": self.membership_status.value,
            "reason_codes": list(self.reason_codes),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> FreeResearchUniverseRecord:
        return cls(
            symbol=str(payload["symbol"]),
            security_name=str(payload["security_name"]),
            provider_security_type=(
                None
                if payload["provider_security_type"] is None
                else str(payload["provider_security_type"])
            ),
            listing_date=_optional_date(payload["listing_date"]),
            delisting_date=_optional_date(payload["delisting_date"]),
            listing_status=SecurityMasterListingStatus(
                str(payload["listing_status"])
            ),
            membership_status=ResearchUniverseMembershipStatus(
                str(payload["membership_status"])
            ),
            reason_codes=tuple(str(item) for item in payload["reason_codes"]),
        )


@dataclass(frozen=True, slots=True)
class FreeResearchUniverseSnapshot:
    snapshot_id: ArtifactId
    snapshot_hash: str
    as_of_date: date
    known_at: datetime
    provider_id: str
    provider_contract: str
    source_manifest_reference: ValidationArtifactReference
    raw_archive_id: str
    evidence_origin: FreeDataEvidenceOrigin
    records: tuple[FreeResearchUniverseRecord, ...]
    data_eligibility: DataEligibility
    evidence_ceiling: PITSourceEvidenceLevel
    formal_pit: bool
    limitations: tuple[str, ...]
    schema_version: str = "free-research-universe-snapshot/v1"

    def __post_init__(self) -> None:
        require_sha256("snapshot_hash", self.snapshot_hash)
        require_text("provider_id", self.provider_id)
        require_text("provider_contract", self.provider_contract)
        require_text("raw_archive_id", self.raw_archive_id)
        if self.known_at.tzinfo is None or self.known_at.utcoffset() is None:
            raise ValueError("Research Universe known_at must be timezone-aware")
        if not self.records or self.records != tuple(
            sorted(self.records, key=lambda item: item.symbol)
        ):
            raise ValueError("Research Universe records must be non-empty and sorted")
        if len({item.symbol for item in self.records}) != len(self.records):
            raise ValueError("Research Universe Security Master symbols must be unique")
        if self.data_eligibility is not DataEligibility.EXPLORATORY:
            raise ValueError("free Research Universe must remain EXPLORATORY")
        if self.evidence_ceiling is not PITSourceEvidenceLevel.PIT_INCOMPLETE:
            raise ValueError("free Research Universe must remain PIT_INCOMPLETE")
        if self.formal_pit:
            raise ValueError("free Research Universe cannot establish Formal PIT")
        required = {
            "FREE_DATA_EXPLORATORY",
            "FORMAL_PIT_NOT_ESTABLISHED",
            "HISTORICAL_AVAILABILITY_NOT_PROVIDED",
            "UNKNOWN_SECURITIES_RETAINED",
        }
        if not required.issubset(self.limitations):
            raise ValueError("Research Universe evidence ceiling is incomplete")
        if canonical_hash(self.identity_payload()) != self.snapshot_hash:
            raise ValueError("Research Universe snapshot hash mismatch")

    @property
    def security_master_count(self) -> int:
        return len(self.records)

    @property
    def included_count(self) -> int:
        return sum(
            item.membership_status is ResearchUniverseMembershipStatus.INCLUDED
            for item in self.records
        )

    @property
    def unknown_count(self) -> int:
        return sum(
            item.membership_status is ResearchUniverseMembershipStatus.UNKNOWN
            for item in self.records
        )

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "as_of_date": self.as_of_date.isoformat(),
            "known_at": timestamp(self.known_at),
            "provider_id": self.provider_id,
            "provider_contract": self.provider_contract,
            "source_manifest_reference": self.source_manifest_reference.to_canonical_dict(),
            "raw_archive_id": self.raw_archive_id,
            "evidence_origin": self.evidence_origin.value,
            "records": [item.to_canonical_dict() for item in self.records],
            "data_eligibility": self.data_eligibility.value,
            "evidence_ceiling": self.evidence_ceiling.value,
            "formal_pit": self.formal_pit,
            "limitations": list(self.limitations),
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": str(self.snapshot_id),
            "snapshot_hash": self.snapshot_hash,
            **self.identity_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> FreeResearchUniverseSnapshot:
        return cls(
            snapshot_id=ArtifactId(str(payload["snapshot_id"])),
            snapshot_hash=str(payload["snapshot_hash"]),
            as_of_date=date.fromisoformat(str(payload["as_of_date"])),
            known_at=datetime.fromisoformat(str(payload["known_at"])),
            provider_id=str(payload["provider_id"]),
            provider_contract=str(payload["provider_contract"]),
            source_manifest_reference=ValidationArtifactReference.from_canonical_dict(
                payload["source_manifest_reference"]
            ),
            raw_archive_id=str(payload["raw_archive_id"]),
            evidence_origin=FreeDataEvidenceOrigin(str(payload["evidence_origin"])),
            records=tuple(
                FreeResearchUniverseRecord.from_canonical_dict(item)
                for item in payload["records"]
            ),
            data_eligibility=DataEligibility(str(payload["data_eligibility"])),
            evidence_ceiling=PITSourceEvidenceLevel(
                str(payload["evidence_ceiling"])
            ),
            formal_pit=bool(payload["formal_pit"]),
            limitations=tuple(str(item) for item in payload["limitations"]),
            schema_version=str(payload["schema_version"]),
        )


def build_free_research_universe_snapshot(
    *,
    as_of_date: date,
    known_at: datetime,
    provider_id: str,
    provider_contract: str,
    source_manifest_reference: ValidationArtifactReference,
    raw_archive_id: str,
    evidence_origin: FreeDataEvidenceOrigin,
    rows: tuple[Mapping[str, Any], ...],
) -> FreeResearchUniverseSnapshot:
    if not rows:
        raise ValueError("free Security Master response must not be empty")
    records = tuple(
        sorted(
            (_record_from_baostock(row, as_of_date=as_of_date) for row in rows),
            key=lambda item: item.symbol,
        )
    )
    limitations = (
        "FREE_DATA_EXPLORATORY",
        "FORMAL_PIT_NOT_ESTABLISHED",
        "HISTORICAL_AVAILABILITY_NOT_PROVIDED",
        "NO_PRODUCTION_AUTHORITY",
        "PIT_INCOMPLETE",
        "UNKNOWN_SECURITIES_RETAINED",
    )
    values = {
        "schema_version": "free-research-universe-snapshot/v1",
        "as_of_date": as_of_date.isoformat(),
        "known_at": timestamp(known_at),
        "provider_id": provider_id,
        "provider_contract": provider_contract,
        "source_manifest_reference": source_manifest_reference.to_canonical_dict(),
        "raw_archive_id": raw_archive_id,
        "evidence_origin": evidence_origin.value,
        "records": [item.to_canonical_dict() for item in records],
        "data_eligibility": DataEligibility.EXPLORATORY.value,
        "evidence_ceiling": PITSourceEvidenceLevel.PIT_INCOMPLETE.value,
        "formal_pit": False,
        "limitations": list(limitations),
    }
    snapshot_id, digest = content_identity("free-research-universe", values)
    return FreeResearchUniverseSnapshot(
        snapshot_id,
        digest,
        as_of_date,
        known_at,
        provider_id,
        provider_contract,
        source_manifest_reference,
        raw_archive_id,
        evidence_origin,
        records,
        DataEligibility.EXPLORATORY,
        PITSourceEvidenceLevel.PIT_INCOMPLETE,
        False,
        limitations,
    )


def _record_from_baostock(
    row: Mapping[str, Any], *, as_of_date: date
) -> FreeResearchUniverseRecord:
    code = str(row.get("code", ""))
    symbol = _baostock_symbol(code)
    security_type = str(row.get("type", "")).strip() or None
    listing_date = _optional_date(row.get("ipoDate"))
    delisting_date = _optional_date(row.get("outDate"))
    listing_status = {
        "1": SecurityMasterListingStatus.LISTED,
        "0": SecurityMasterListingStatus.DELISTED,
    }.get(str(row.get("status", "")), SecurityMasterListingStatus.UNKNOWN)
    reasons: set[str] = set()
    if security_type is None or listing_date is None:
        membership = ResearchUniverseMembershipStatus.UNKNOWN
        reasons.add("SECURITY_MASTER_FIELDS_UNKNOWN")
    elif security_type != "1":
        membership = ResearchUniverseMembershipStatus.EXCLUDED
        reasons.add("NOT_A_SHARE_SECURITY_TYPE")
    elif listing_date > as_of_date:
        membership = ResearchUniverseMembershipStatus.EXCLUDED
        reasons.add("NOT_YET_LISTED_AS_OF_DATE")
    elif delisting_date is not None and delisting_date <= as_of_date:
        membership = ResearchUniverseMembershipStatus.EXCLUDED
        reasons.add("DELISTED_BY_AS_OF_DATE")
    elif listing_status is SecurityMasterListingStatus.UNKNOWN:
        membership = ResearchUniverseMembershipStatus.UNKNOWN
        reasons.add("CURRENT_LISTING_STATUS_UNKNOWN")
    else:
        membership = ResearchUniverseMembershipStatus.INCLUDED
        reasons.add("DERIVED_FROM_RETRIEVED_SECURITY_MASTER")
    if listing_status is SecurityMasterListingStatus.UNKNOWN:
        reasons.add("CURRENT_LISTING_STATUS_UNKNOWN")
    return FreeResearchUniverseRecord(
        symbol=symbol,
        security_name=str(row.get("code_name", "")).strip() or symbol,
        provider_security_type=security_type,
        listing_date=listing_date,
        delisting_date=delisting_date,
        listing_status=listing_status,
        membership_status=membership,
        reason_codes=tuple(sorted(reasons)),
    )


def _baostock_symbol(code: str) -> str:
    parts = code.lower().split(".")
    if len(parts) != 2 or parts[0] not in {"sh", "sz", "bj"}:
        raise ValueError(f"unsupported BaoStock Security Master code: {code}")
    digits = parts[1]
    if not digits.isdigit() or len(digits) != 6:
        raise ValueError(f"invalid BaoStock Security Master code: {code}")
    return f"{digits}.{parts[0].upper()}"


def _optional_date(value: object) -> date | None:
    text = "" if value is None else str(value).strip()
    return None if not text else date.fromisoformat(text)


__all__ = [
    "FreeDataEvidenceOrigin",
    "FreeResearchUniverseRecord",
    "FreeResearchUniverseSnapshot",
    "ResearchUniverseMembershipStatus",
    "SecurityMasterListingStatus",
    "build_free_research_universe_snapshot",
]
