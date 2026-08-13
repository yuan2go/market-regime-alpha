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


class ResearchUniverseSelectionBasis(str, Enum):
    CURRENT_SECURITY_MASTER = "CURRENT_SECURITY_MASTER"
    HISTORICAL_CONSTITUENT_SNAPSHOT = "HISTORICAL_CONSTITUENT_SNAPSHOT"


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
    selection_basis: ResearchUniverseSelectionBasis = (
        ResearchUniverseSelectionBasis.CURRENT_SECURITY_MASTER
    )
    constituent_effective_date: date | None = None
    constituent_source_reference: ValidationArtifactReference | None = None
    schema_version: str = "free-research-universe-snapshot/v1"

    def __post_init__(self) -> None:
        if self.schema_version not in {
            "free-research-universe-snapshot/v1",
            "free-research-universe-snapshot/v2",
        }:
            raise ValueError("unsupported free Research Universe schema")
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
        if self.selection_basis is ResearchUniverseSelectionBasis.CURRENT_SECURITY_MASTER:
            if (
                self.constituent_effective_date is not None
                or self.constituent_source_reference is not None
                or self.schema_version != "free-research-universe-snapshot/v1"
            ):
                raise ValueError("current Security Master snapshot basis is inconsistent")
        else:
            if (
                self.schema_version != "free-research-universe-snapshot/v2"
                or self.constituent_effective_date is None
                or self.constituent_source_reference is None
            ):
                raise ValueError("Historical constituent snapshot source is incomplete")
            historical_required = {
                "CURRENT_CLASSIFICATION_NOT_BACKFILLED",
                "FROZEN_HISTORICAL_CONSTITUENT_SNAPSHOT",
                "RETRIEVED_AFTER_CONSTITUENT_EFFECTIVE_DATE",
            }
            if not historical_required.issubset(self.limitations):
                raise ValueError("Historical constituent evidence limitations are incomplete")
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
        payload = {
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
        if self.schema_version == "free-research-universe-snapshot/v2":
            payload.update(
                {
                    "selection_basis": self.selection_basis.value,
                    "constituent_effective_date": (
                        None
                        if self.constituent_effective_date is None
                        else self.constituent_effective_date.isoformat()
                    ),
                    "constituent_source_reference": (
                        None
                        if self.constituent_source_reference is None
                        else self.constituent_source_reference.to_canonical_dict()
                    ),
                }
            )
        return payload

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
            selection_basis=ResearchUniverseSelectionBasis(
                str(
                    payload.get(
                        "selection_basis",
                        ResearchUniverseSelectionBasis.CURRENT_SECURITY_MASTER.value,
                    )
                )
            ),
            constituent_effective_date=(
                None
                if payload.get("constituent_effective_date") is None
                else date.fromisoformat(str(payload["constituent_effective_date"]))
            ),
            constituent_source_reference=(
                None
                if payload.get("constituent_source_reference") is None
                else ValidationArtifactReference.from_canonical_dict(
                    payload["constituent_source_reference"]
                )
            ),
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


def project_free_research_universe_as_of(
    snapshot: FreeResearchUniverseSnapshot,
    *,
    as_of_date: date,
    symbols: tuple[str, ...] | None = None,
) -> FreeResearchUniverseSnapshot:
    """Project retrieved listing dates without rewriting the true known-at clock."""

    if (
        snapshot.selection_basis
        is ResearchUniverseSelectionBasis.HISTORICAL_CONSTITUENT_SNAPSHOT
    ):
        return _project_historical_constituent_snapshot(
            snapshot,
            as_of_date=as_of_date,
            symbols=symbols,
        )

    selected = None if symbols is None else tuple(sorted(set(symbols)))
    if selected is not None and not selected:
        raise ValueError("Research Universe projection symbols must not be empty")
    projected = tuple(
        _project_record_as_of(item, as_of_date=as_of_date)
        for item in snapshot.records
        if selected is None or item.symbol in selected
    )
    if not projected:
        raise ValueError("Research Universe projection has no Security Master records")
    limitations = tuple(
        sorted(
            {
                *snapshot.limitations,
                "CURRENT_SECURITY_MASTER_PROJECTED_RETROSPECTIVELY",
                "HISTORICAL_AVAILABILITY_NOT_PROVIDED",
                "PIT_INCOMPLETE",
                *(
                    ("FROZEN_SELECTOR_SUBSET_PROJECTION",)
                    if selected is not None
                    else ()
                ),
            }
        )
    )
    values = {
        "schema_version": snapshot.schema_version,
        "as_of_date": as_of_date.isoformat(),
        "known_at": timestamp(snapshot.known_at),
        "provider_id": snapshot.provider_id,
        "provider_contract": snapshot.provider_contract,
        "source_manifest_reference": snapshot.source_manifest_reference.to_canonical_dict(),
        "raw_archive_id": snapshot.raw_archive_id,
        "evidence_origin": FreeDataEvidenceOrigin.ARCHIVED_REPLAY.value,
        "records": [item.to_canonical_dict() for item in projected],
        "data_eligibility": DataEligibility.EXPLORATORY.value,
        "evidence_ceiling": PITSourceEvidenceLevel.PIT_INCOMPLETE.value,
        "formal_pit": False,
        "limitations": list(limitations),
    }
    snapshot_id, digest = content_identity("free-research-universe", values)
    return FreeResearchUniverseSnapshot(
        snapshot_id=snapshot_id,
        snapshot_hash=digest,
        as_of_date=as_of_date,
        known_at=snapshot.known_at,
        provider_id=snapshot.provider_id,
        provider_contract=snapshot.provider_contract,
        source_manifest_reference=snapshot.source_manifest_reference,
        raw_archive_id=snapshot.raw_archive_id,
        evidence_origin=FreeDataEvidenceOrigin.ARCHIVED_REPLAY,
        records=projected,
        data_eligibility=DataEligibility.EXPLORATORY,
        evidence_ceiling=PITSourceEvidenceLevel.PIT_INCOMPLETE,
        formal_pit=False,
        limitations=limitations,
    )


def build_historical_constituent_universe_snapshot(
    *,
    effective_date: date,
    known_at: datetime,
    provider_id: str,
    provider_contract: str,
    source_manifest_reference: ValidationArtifactReference,
    constituent_source_reference: ValidationArtifactReference,
    raw_archive_id: str,
    evidence_origin: FreeDataEvidenceOrigin,
    constituent_rows: tuple[Mapping[str, Any], ...],
    security_master_rows: tuple[Mapping[str, Any], ...],
) -> FreeResearchUniverseSnapshot:
    """Build a frozen real historical membership set without current additions."""

    if not constituent_rows:
        raise ValueError("Historical constituent response must not be empty")
    basic_by_code = {
        str(item.get("code", "")).lower(): item for item in security_master_rows
    }
    records = tuple(
        sorted(
            (
                _historical_constituent_record(
                    row,
                    basic=basic_by_code.get(str(row.get("code", "")).lower()),
                    effective_date=effective_date,
                )
                for row in constituent_rows
            ),
            key=lambda item: item.symbol,
        )
    )
    limitations = (
        "CURRENT_CLASSIFICATION_NOT_BACKFILLED",
        "FORMAL_PIT_NOT_ESTABLISHED",
        "FREE_DATA_EXPLORATORY",
        "FROZEN_HISTORICAL_CONSTITUENT_SNAPSHOT",
        "HISTORICAL_AVAILABILITY_NOT_PROVIDED",
        "NO_PRODUCTION_AUTHORITY",
        "PIT_INCOMPLETE",
        "RETRIEVED_AFTER_CONSTITUENT_EFFECTIVE_DATE",
        "UNKNOWN_SECURITIES_RETAINED",
    )
    values = {
        "schema_version": "free-research-universe-snapshot/v2",
        "as_of_date": effective_date.isoformat(),
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
        "selection_basis": (
            ResearchUniverseSelectionBasis.HISTORICAL_CONSTITUENT_SNAPSHOT.value
        ),
        "constituent_effective_date": effective_date.isoformat(),
        "constituent_source_reference": (
            constituent_source_reference.to_canonical_dict()
        ),
    }
    snapshot_id, digest = content_identity("free-research-universe", values)
    return FreeResearchUniverseSnapshot(
        snapshot_id=snapshot_id,
        snapshot_hash=digest,
        as_of_date=effective_date,
        known_at=known_at,
        provider_id=provider_id,
        provider_contract=provider_contract,
        source_manifest_reference=source_manifest_reference,
        raw_archive_id=raw_archive_id,
        evidence_origin=evidence_origin,
        records=records,
        data_eligibility=DataEligibility.EXPLORATORY,
        evidence_ceiling=PITSourceEvidenceLevel.PIT_INCOMPLETE,
        formal_pit=False,
        limitations=limitations,
        selection_basis=(
            ResearchUniverseSelectionBasis.HISTORICAL_CONSTITUENT_SNAPSHOT
        ),
        constituent_effective_date=effective_date,
        constituent_source_reference=constituent_source_reference,
        schema_version="free-research-universe-snapshot/v2",
    )


def _project_historical_constituent_snapshot(
    snapshot: FreeResearchUniverseSnapshot,
    *,
    as_of_date: date,
    symbols: tuple[str, ...] | None,
) -> FreeResearchUniverseSnapshot:
    effective_date = snapshot.constituent_effective_date
    if effective_date is None or snapshot.constituent_source_reference is None:
        raise ValueError("Historical constituent snapshot source is incomplete")
    if as_of_date < effective_date:
        raise ValueError("projection predates frozen constituent effective date")
    selected = None if symbols is None else tuple(sorted(set(symbols)))
    if selected is not None and not selected:
        raise ValueError("Research Universe projection symbols must not be empty")
    records = tuple(
        item
        for item in snapshot.records
        if selected is None or item.symbol in selected
    )
    if not records:
        raise ValueError("Research Universe projection has no constituent records")
    limitations = tuple(
        sorted(
            {
                *snapshot.limitations,
                "FROZEN_HISTORICAL_CONSTITUENT_REPLAY",
                *(
                    ("FROZEN_SELECTOR_SUBSET_PROJECTION",)
                    if selected is not None
                    else ()
                ),
            }
        )
    )
    values = {
        "schema_version": "free-research-universe-snapshot/v2",
        "as_of_date": as_of_date.isoformat(),
        "known_at": timestamp(snapshot.known_at),
        "provider_id": snapshot.provider_id,
        "provider_contract": snapshot.provider_contract,
        "source_manifest_reference": snapshot.source_manifest_reference.to_canonical_dict(),
        "raw_archive_id": snapshot.raw_archive_id,
        "evidence_origin": FreeDataEvidenceOrigin.ARCHIVED_REPLAY.value,
        "records": [item.to_canonical_dict() for item in records],
        "data_eligibility": DataEligibility.EXPLORATORY.value,
        "evidence_ceiling": PITSourceEvidenceLevel.PIT_INCOMPLETE.value,
        "formal_pit": False,
        "limitations": list(limitations),
        "selection_basis": snapshot.selection_basis.value,
        "constituent_effective_date": effective_date.isoformat(),
        "constituent_source_reference": (
            snapshot.constituent_source_reference.to_canonical_dict()
        ),
    }
    snapshot_id, digest = content_identity("free-research-universe", values)
    return FreeResearchUniverseSnapshot(
        snapshot_id=snapshot_id,
        snapshot_hash=digest,
        as_of_date=as_of_date,
        known_at=snapshot.known_at,
        provider_id=snapshot.provider_id,
        provider_contract=snapshot.provider_contract,
        source_manifest_reference=snapshot.source_manifest_reference,
        raw_archive_id=snapshot.raw_archive_id,
        evidence_origin=FreeDataEvidenceOrigin.ARCHIVED_REPLAY,
        records=records,
        data_eligibility=DataEligibility.EXPLORATORY,
        evidence_ceiling=PITSourceEvidenceLevel.PIT_INCOMPLETE,
        formal_pit=False,
        limitations=limitations,
        selection_basis=snapshot.selection_basis,
        constituent_effective_date=effective_date,
        constituent_source_reference=snapshot.constituent_source_reference,
        schema_version="free-research-universe-snapshot/v2",
    )


def _project_record_as_of(
    item: FreeResearchUniverseRecord,
    *,
    as_of_date: date,
) -> FreeResearchUniverseRecord:
    reasons = {
        "CURRENT_SECURITY_MASTER_PROJECTED_RETROSPECTIVELY",
        "HISTORICAL_AVAILABILITY_NOT_PROVIDED",
    }
    if item.provider_security_type != "1":
        membership = ResearchUniverseMembershipStatus.EXCLUDED
        listing = SecurityMasterListingStatus.UNKNOWN
        reasons.add("NOT_A_SHARE_SECURITY_TYPE")
    elif item.listing_date is None:
        membership = ResearchUniverseMembershipStatus.UNKNOWN
        listing = SecurityMasterListingStatus.UNKNOWN
        reasons.add("LISTING_DATE_UNKNOWN")
    elif item.listing_date > as_of_date:
        membership = ResearchUniverseMembershipStatus.EXCLUDED
        listing = SecurityMasterListingStatus.UNKNOWN
        reasons.add("NOT_YET_LISTED_AS_OF_DATE")
    elif item.delisting_date is not None and item.delisting_date <= as_of_date:
        membership = ResearchUniverseMembershipStatus.EXCLUDED
        listing = SecurityMasterListingStatus.DELISTED
        reasons.add("DELISTED_BY_AS_OF_DATE")
    else:
        membership = ResearchUniverseMembershipStatus.INCLUDED
        listing = SecurityMasterListingStatus.LISTED
        reasons.add("LISTED_BY_RETRIEVED_IPO_OUT_DATES")
    return FreeResearchUniverseRecord(
        symbol=item.symbol,
        security_name=item.security_name,
        provider_security_type=item.provider_security_type,
        listing_date=item.listing_date,
        delisting_date=item.delisting_date,
        listing_status=listing,
        membership_status=membership,
        reason_codes=tuple(sorted(reasons)),
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
    if row.get("_provider_row_malformed") is True:
        membership = ResearchUniverseMembershipStatus.UNKNOWN
        listing_status = SecurityMasterListingStatus.UNKNOWN
        reasons.update(
            {
                "PROVIDER_ROW_FIELD_COUNT_MISMATCH",
                "SECURITY_MASTER_FIELDS_UNKNOWN",
            }
        )
    elif security_type is None or listing_date is None:
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


def _historical_constituent_record(
    row: Mapping[str, Any],
    *,
    basic: Mapping[str, Any] | None,
    effective_date: date,
) -> FreeResearchUniverseRecord:
    provider_effective_date = _optional_date(row.get("updateDate"))
    if provider_effective_date is None:
        raise ValueError("Historical constituent row requires provider effective date")
    if provider_effective_date > effective_date:
        raise ValueError("Historical constituent row is effective after snapshot")
    symbol = _baostock_symbol(str(row.get("code", "")))
    listing_date = None if basic is None else _optional_date(basic.get("ipoDate"))
    delisting_date = None if basic is None else _optional_date(basic.get("outDate"))
    security_type = (
        None
        if basic is None or not str(basic.get("type", "")).strip()
        else str(basic["type"]).strip()
    )
    reasons = {
        "CURRENT_CLASSIFICATION_NOT_BACKFILLED",
        "HISTORICAL_CONSTITUENT_MEMBER",
        "MEMBERSHIP_FROM_PROVIDER_EFFECTIVE_SNAPSHOT",
    }
    if listing_date is None:
        listing_status = SecurityMasterListingStatus.UNKNOWN
        reasons.add("LISTING_DATE_UNKNOWN")
    elif listing_date > effective_date:
        raise ValueError("Historical constituent membership predates listing")
    elif delisting_date is not None and delisting_date <= effective_date:
        raise ValueError("Historical constituent membership follows delisting")
    else:
        listing_status = SecurityMasterListingStatus.LISTED
        reasons.add("LISTED_BY_RETRIEVED_LIFECYCLE_FACTS")
    if basic is None:
        reasons.add("SECURITY_MASTER_LIFECYCLE_UNKNOWN")
    return FreeResearchUniverseRecord(
        symbol=symbol,
        security_name=str(row.get("code_name", "")).strip() or symbol,
        provider_security_type=security_type,
        listing_date=listing_date,
        delisting_date=delisting_date,
        listing_status=listing_status,
        membership_status=ResearchUniverseMembershipStatus.INCLUDED,
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
    "ResearchUniverseSelectionBasis",
    "ResearchUniverseMembershipStatus",
    "SecurityMasterListingStatus",
    "build_free_research_universe_snapshot",
    "build_historical_constituent_universe_snapshot",
    "project_free_research_universe_as_of",
]
