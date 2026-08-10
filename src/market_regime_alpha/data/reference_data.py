"""Exploratory ETF and Theme reference facts below the Formal PIT boundary."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import Enum
import json
from pathlib import Path
from typing import Any, Mapping

from market_regime_alpha.application.canonical_lifecycle._immutable_io import (
    publish_immutable_text,
)
from market_regime_alpha.application.continuous_research.journal import (
    RuntimeArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.data.free_operational_policy import (
    FreeOperationalEvidencePolicy,
)
from market_regime_alpha.data.pit_contracts import PITSourceEvidenceLevel
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    canonical_json,
    require_sha256,
    require_text,
)


REFERENCE_SNAPSHOT_SCHEMA_V1 = "etf-theme-reference-snapshot/v1"
REFERENCE_SNAPSHOT_SCHEMA = "etf-theme-reference-snapshot/v2"


class ReferenceRole(str, Enum):
    PRIMARY = "PRIMARY"
    ALTERNATIVE = "ALTERNATIVE"
    SUPPORTING = "SUPPORTING"


class MembershipKind(str, Enum):
    DECLARED_MEMBERSHIP = "DECLARED_MEMBERSHIP"
    DERIVED_MEMBERSHIP = "DERIVED_MEMBERSHIP"
    PROXY_MEMBERSHIP = "PROXY_MEMBERSHIP"


@dataclass(frozen=True, slots=True)
class ReferenceValidity:
    effective_from: datetime
    effective_to: datetime | None
    available_at: datetime
    source_reference: RuntimeArtifactReference
    source_contract: str

    def __post_init__(self) -> None:
        _aware("effective_from", self.effective_from)
        _aware("available_at", self.available_at)
        if self.effective_to is not None:
            _aware("effective_to", self.effective_to)
            if self.effective_to <= self.effective_from:
                raise ValueError("Reference effective_to must follow effective_from")
        require_text("source_contract", self.source_contract)

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "effective_from": canonical_datetime(self.effective_from),
            "effective_to": (
                None
                if self.effective_to is None
                else canonical_datetime(self.effective_to)
            ),
            "available_at": canonical_datetime(self.available_at),
            "source_reference": self.source_reference.to_canonical_dict(),
            "source_contract": self.source_contract,
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> ReferenceValidity:
        effective_to = payload["effective_to"]
        return cls(
            effective_from=_instant(payload["effective_from"]),
            effective_to=(None if effective_to is None else _instant(effective_to)),
            available_at=_instant(payload["available_at"]),
            source_reference=RuntimeArtifactReference.from_canonical_dict(
                _mapping(payload["source_reference"])
            ),
            source_contract=_text(payload["source_contract"]),
        )


@dataclass(frozen=True, slots=True)
class ETFReferenceRecord:
    etf_id: str
    etf_name: str
    tracking_index_id: str
    tracking_index_name: str
    listing_date: date | None
    delisting_date: date | None
    role: ReferenceRole
    liquidity_policy_id: str
    validity: ReferenceValidity

    def __post_init__(self) -> None:
        for label, value in (
            ("etf_id", self.etf_id),
            ("etf_name", self.etf_name),
            ("tracking_index_id", self.tracking_index_id),
            ("tracking_index_name", self.tracking_index_name),
            ("liquidity_policy_id", self.liquidity_policy_id),
        ):
            require_text(label, value)
        if (
            self.listing_date is not None
            and self.delisting_date is not None
            and self.delisting_date <= self.listing_date
        ):
            raise ValueError("ETF delisting date must follow listing date")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "etf_id": self.etf_id,
            "etf_name": self.etf_name,
            "tracking_index_id": self.tracking_index_id,
            "tracking_index_name": self.tracking_index_name,
            "listing_date": _date_text(self.listing_date),
            "delisting_date": _date_text(self.delisting_date),
            "role": self.role.value,
            "liquidity_policy_id": self.liquidity_policy_id,
            "validity": self.validity.to_canonical_dict(),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> ETFReferenceRecord:
        return cls(
            etf_id=_text(payload["etf_id"]),
            etf_name=_text(payload["etf_name"]),
            tracking_index_id=_text(payload["tracking_index_id"]),
            tracking_index_name=_text(payload["tracking_index_name"]),
            listing_date=_optional_date(payload["listing_date"]),
            delisting_date=_optional_date(payload["delisting_date"]),
            role=ReferenceRole(_text(payload["role"])),
            liquidity_policy_id=_text(payload["liquidity_policy_id"]),
            validity=ReferenceValidity.from_canonical_dict(
                _mapping(payload["validity"])
            ),
        )


@dataclass(frozen=True, slots=True)
class ThemeTaxonomyRecord:
    theme_id: str
    theme_name: str
    parent_theme_id: str | None
    benchmark_id: str | None
    validity: ReferenceValidity

    def __post_init__(self) -> None:
        require_text("theme_id", self.theme_id)
        require_text("theme_name", self.theme_name)
        if self.parent_theme_id is not None:
            require_text("parent_theme_id", self.parent_theme_id)
            if self.parent_theme_id == self.theme_id:
                raise ValueError("Theme cannot parent itself")
        if self.benchmark_id is not None:
            require_text("benchmark_id", self.benchmark_id)

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "theme_id": self.theme_id,
            "theme_name": self.theme_name,
            "parent_theme_id": self.parent_theme_id,
            "benchmark_id": self.benchmark_id,
            "validity": self.validity.to_canonical_dict(),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> ThemeTaxonomyRecord:
        return cls(
            theme_id=_text(payload["theme_id"]),
            theme_name=_text(payload["theme_name"]),
            parent_theme_id=_optional_text(payload["parent_theme_id"]),
            benchmark_id=_optional_text(payload["benchmark_id"]),
            validity=ReferenceValidity.from_canonical_dict(
                _mapping(payload["validity"])
            ),
        )


@dataclass(frozen=True, slots=True)
class ThemeMembershipRecord:
    symbol: str
    theme_id: str
    role: ReferenceRole
    validity: ReferenceValidity
    membership_kind: MembershipKind = MembershipKind.PROXY_MEMBERSHIP

    def __post_init__(self) -> None:
        require_text("symbol", self.symbol)
        require_text("theme_id", self.theme_id)

    def to_canonical_dict(
        self, *, include_membership_kind: bool = True
    ) -> dict[str, Any]:
        payload = {
            "symbol": self.symbol,
            "theme_id": self.theme_id,
            "role": self.role.value,
            "validity": self.validity.to_canonical_dict(),
        }
        if include_membership_kind:
            payload["membership_kind"] = self.membership_kind.value
        return payload

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> ThemeMembershipRecord:
        return cls(
            symbol=_text(payload["symbol"]),
            theme_id=_text(payload["theme_id"]),
            role=ReferenceRole(_text(payload["role"])),
            validity=ReferenceValidity.from_canonical_dict(
                _mapping(payload["validity"])
            ),
            membership_kind=MembershipKind(
                _text(
                    payload.get(
                        "membership_kind", MembershipKind.PROXY_MEMBERSHIP.value
                    )
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class ETFThemeMappingRecord:
    etf_id: str
    theme_id: str
    role: ReferenceRole
    validity: ReferenceValidity
    membership_kind: MembershipKind = MembershipKind.PROXY_MEMBERSHIP

    def __post_init__(self) -> None:
        require_text("etf_id", self.etf_id)
        require_text("theme_id", self.theme_id)

    def to_canonical_dict(
        self, *, include_membership_kind: bool = True
    ) -> dict[str, Any]:
        payload = {
            "etf_id": self.etf_id,
            "theme_id": self.theme_id,
            "role": self.role.value,
            "validity": self.validity.to_canonical_dict(),
        }
        if include_membership_kind:
            payload["membership_kind"] = self.membership_kind.value
        return payload

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> ETFThemeMappingRecord:
        return cls(
            etf_id=_text(payload["etf_id"]),
            theme_id=_text(payload["theme_id"]),
            role=ReferenceRole(_text(payload["role"])),
            validity=ReferenceValidity.from_canonical_dict(
                _mapping(payload["validity"])
            ),
            membership_kind=MembershipKind(
                _text(
                    payload.get(
                        "membership_kind", MembershipKind.PROXY_MEMBERSHIP.value
                    )
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class ETFThemeReferenceSnapshot:
    snapshot_id: ArtifactId
    content_hash: str
    reference_version: str
    etfs: tuple[ETFReferenceRecord, ...]
    themes: tuple[ThemeTaxonomyRecord, ...]
    memberships: tuple[ThemeMembershipRecord, ...]
    mappings: tuple[ETFThemeMappingRecord, ...]
    data_eligibility: DataEligibility
    evidence_ceiling: PITSourceEvidenceLevel
    created_at: datetime
    limitations: tuple[str, ...]
    schema_version: str = REFERENCE_SNAPSHOT_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version not in {
            REFERENCE_SNAPSHOT_SCHEMA_V1,
            REFERENCE_SNAPSHOT_SCHEMA,
        }:
            raise ValueError("unsupported ETF/Theme Reference schema")
        require_sha256("content_hash", self.content_hash)
        require_text("reference_version", self.reference_version)
        _aware("created_at", self.created_at)
        if self.data_eligibility is not DataEligibility.EXPLORATORY:
            raise ValueError("free Reference Snapshot must remain EXPLORATORY")
        if self.evidence_ceiling not in {
            PITSourceEvidenceLevel.FREE_DATA_EXPLORATORY,
            PITSourceEvidenceLevel.PIT_INCOMPLETE,
        }:
            raise ValueError("Reference Snapshot cannot claim Formal PIT")
        _unique_sorted("ETF", tuple(item.etf_id for item in self.etfs))
        _unique_sorted("Theme", tuple(item.theme_id for item in self.themes))
        _unique_sorted(
            "Theme membership",
            tuple((item.symbol, item.theme_id) for item in self.memberships),
        )
        _unique_sorted(
            "ETF Theme mapping",
            tuple((item.etf_id, item.theme_id) for item in self.mappings),
        )
        etf_ids = {item.etf_id for item in self.etfs}
        theme_ids = {item.theme_id for item in self.themes}
        if any(
            item.parent_theme_id is not None
            and item.parent_theme_id not in theme_ids
            for item in self.themes
        ):
            raise ValueError("Theme parent is absent from taxonomy")
        if any(item.theme_id not in theme_ids for item in self.memberships):
            raise ValueError("Theme membership references unknown Theme")
        if any(
            item.etf_id not in etf_ids or item.theme_id not in theme_ids
            for item in self.mappings
        ):
            raise ValueError("ETF Theme mapping references unknown identity")
        required = {
            "EXPLORATORY_UNQUALIFIED",
            "FORMAL_PIT_NOT_ESTABLISHED",
            "NO_INVENTED_THEME_MEMBERSHIP",
            "NO_TRADING_AUTHORITY",
        }
        if not required.issubset(self.limitations):
            raise ValueError("Reference Snapshot authority ceiling is incomplete")
        if self.limitations != tuple(sorted(set(self.limitations))):
            raise ValueError("Reference limitations must be unique and sorted")
        validity_records: tuple[
            ETFReferenceRecord
            | ThemeTaxonomyRecord
            | ThemeMembershipRecord
            | ETFThemeMappingRecord,
            ...,
        ] = (*self.etfs, *self.themes, *self.memberships, *self.mappings)
        if any(
            item.validity.available_at > self.created_at
            for item in validity_records
        ):
            raise ValueError("Reference Snapshot predates source availability")
        if canonical_hash(self.semantic_payload()) != self.content_hash:
            raise ValueError("Reference Snapshot hash mismatch")
        if self.snapshot_id != _content_id("etf-theme-reference", self.content_hash):
            raise ValueError("Reference Snapshot identity mismatch")

    @classmethod
    def create(cls, **values: Any) -> ETFThemeReferenceSnapshot:
        normalized = dict(values)
        normalized["etfs"] = tuple(sorted(values["etfs"], key=lambda item: item.etf_id))
        normalized["themes"] = tuple(
            sorted(values["themes"], key=lambda item: item.theme_id)
        )
        normalized["memberships"] = tuple(
            sorted(values["memberships"], key=lambda item: (item.symbol, item.theme_id))
        )
        normalized["mappings"] = tuple(
            sorted(values["mappings"], key=lambda item: (item.etf_id, item.theme_id))
        )
        normalized["limitations"] = tuple(sorted(set(values["limitations"])))
        normalized["schema_version"] = values.get(
            "schema_version", REFERENCE_SNAPSHOT_SCHEMA
        )
        digest = canonical_hash(_snapshot_payload(**normalized))
        return cls(
            snapshot_id=_content_id("etf-theme-reference", digest),
            content_hash=digest,
            **normalized,
        )

    @property
    def available_at(self) -> datetime:
        validity_records: tuple[
            ETFReferenceRecord
            | ThemeTaxonomyRecord
            | ThemeMembershipRecord
            | ETFThemeMappingRecord,
            ...,
        ] = (*self.etfs, *self.themes, *self.memberships, *self.mappings)
        return max(
            item.validity.available_at
            for item in validity_records
        )

    def semantic_payload(self) -> dict[str, Any]:
        return _snapshot_payload(
            reference_version=self.reference_version,
            etfs=self.etfs,
            themes=self.themes,
            memberships=self.memberships,
            mappings=self.mappings,
            data_eligibility=self.data_eligibility,
            evidence_ceiling=self.evidence_ceiling,
            created_at=self.created_at,
            limitations=self.limitations,
            schema_version=self.schema_version,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": str(self.snapshot_id),
            "content_hash": self.content_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> ETFThemeReferenceSnapshot:
        return cls(
            snapshot_id=ArtifactId(_text(payload["snapshot_id"])),
            content_hash=_text(payload["content_hash"]),
            reference_version=_text(payload["reference_version"]),
            etfs=tuple(
                ETFReferenceRecord.from_canonical_dict(_mapping(item))
                for item in _array(payload["etfs"])
            ),
            themes=tuple(
                ThemeTaxonomyRecord.from_canonical_dict(_mapping(item))
                for item in _array(payload["themes"])
            ),
            memberships=tuple(
                ThemeMembershipRecord.from_canonical_dict(_mapping(item))
                for item in _array(payload["memberships"])
            ),
            mappings=tuple(
                ETFThemeMappingRecord.from_canonical_dict(_mapping(item))
                for item in _array(payload["mappings"])
            ),
            data_eligibility=DataEligibility(_text(payload["data_eligibility"])),
            evidence_ceiling=PITSourceEvidenceLevel(
                _text(payload["evidence_ceiling"])
            ),
            created_at=_instant(payload["created_at"]),
            limitations=_strings(payload["limitations"]),
            schema_version=_text(payload["schema_version"]),
        )


def free_v1_reference_snapshot(
    *,
    policy: FreeOperationalEvidencePolicy,
    available_at: datetime,
) -> ETFThemeReferenceSnapshot:
    """Translate only declared Free V1 proxy identities; invent no constituents."""

    source = RuntimeArtifactReference(
        "FREE_OPERATIONAL_EVIDENCE_POLICY", policy.policy_id, policy.content_hash
    )
    contract = "free-operational-etf-theme-policy/v1"
    themes = tuple(
        ThemeTaxonomyRecord(
            theme_id=item.theme_id,
            theme_name=item.theme_name,
            parent_theme_id=None,
            benchmark_id=item.benchmark_id,
            validity=ReferenceValidity(
                effective_from=datetime.combine(item.effective_from, datetime.min.time(), UTC),
                effective_to=None,
                available_at=available_at,
                source_reference=source,
                source_contract=contract,
            ),
        )
        for item in policy.themes
    )
    etfs = tuple(
        ETFReferenceRecord(
            etf_id=item.etf_id,
            etf_name=item.etf_name,
            tracking_index_id=item.tracking_index_id,
            tracking_index_name=item.tracking_index_name,
            listing_date=None,
            delisting_date=None,
            role=ReferenceRole.PRIMARY,
            liquidity_policy_id="FREE_V1_OBSERVED_LIQUIDITY_GATE",
            validity=ReferenceValidity(
                effective_from=min(value.validity.effective_from for value in themes),
                effective_to=None,
                available_at=available_at,
                source_reference=source,
                source_contract=contract,
            ),
        )
        for item in policy.etfs
    )
    mappings = tuple(
        ETFThemeMappingRecord(
            etf_id=item.etf_id,
            theme_id=item.theme_id,
            role=ReferenceRole.PRIMARY,
            validity=etfs[index].validity,
            membership_kind=MembershipKind.PROXY_MEMBERSHIP,
        )
        for index, item in enumerate(policy.etfs)
    )
    return ETFThemeReferenceSnapshot.create(
        reference_version=f"free-v1:{policy.policy_version}",
        etfs=etfs,
        themes=themes,
        memberships=(),
        mappings=mappings,
        data_eligibility=DataEligibility.EXPLORATORY,
        evidence_ceiling=PITSourceEvidenceLevel.FREE_DATA_EXPLORATORY,
        created_at=available_at,
        limitations=(
            "EXPLORATORY_UNQUALIFIED",
            "FORMAL_PIT_NOT_ESTABLISHED",
            "FREE_V1_PROXY_ONLY",
            "NO_INVENTED_THEME_MEMBERSHIP",
            "NO_TRADING_AUTHORITY",
        ),
    )


def publish_reference_snapshot(
    *, root: Path, snapshot: ETFThemeReferenceSnapshot
) -> Path:
    path = root / f"{snapshot.snapshot_id}.json"
    publish_immutable_text(
        path=path,
        payload=canonical_json(snapshot.to_canonical_dict()) + "\n",
        collision_message="ETF/Theme Reference identity conflict",
    )
    if load_reference_snapshot(path) != snapshot:
        raise ValueError("published ETF/Theme Reference semantic mismatch")
    return path


def load_reference_snapshot(path: Path) -> ETFThemeReferenceSnapshot:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("ETF/Theme Reference payload must be an object")
    return ETFThemeReferenceSnapshot.from_canonical_dict(payload)


def _snapshot_payload(**values: Any) -> dict[str, Any]:
    schema_version = values.get("schema_version", REFERENCE_SNAPSHOT_SCHEMA)
    include_membership_kind = schema_version != REFERENCE_SNAPSHOT_SCHEMA_V1
    return {
        "schema_version": schema_version,
        "reference_version": values["reference_version"],
        "etfs": [item.to_canonical_dict() for item in values["etfs"]],
        "themes": [item.to_canonical_dict() for item in values["themes"]],
        "memberships": [
            item.to_canonical_dict(
                include_membership_kind=include_membership_kind
            )
            for item in values["memberships"]
        ],
        "mappings": [
            item.to_canonical_dict(
                include_membership_kind=include_membership_kind
            )
            for item in values["mappings"]
        ],
        "data_eligibility": values["data_eligibility"].value,
        "evidence_ceiling": values["evidence_ceiling"].value,
        "created_at": canonical_datetime(values["created_at"]),
        "limitations": list(values["limitations"]),
    }


def _content_id(prefix: str, digest: str) -> ArtifactId:
    return ArtifactId(f"{prefix}-{digest.split(':', 1)[1][:24]}")


def _unique_sorted(label: str, values: tuple[Any, ...]) -> None:
    if values != tuple(sorted(set(values))):
        raise ValueError(f"{label} records must be unique and sorted")


def _aware(label: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")


def _instant(value: object) -> datetime:
    parsed = datetime.fromisoformat(_text(value).replace("Z", "+00:00"))
    _aware("instant", parsed)
    return parsed


def _date_text(value: date | None) -> str | None:
    return None if value is None else value.isoformat()


def _optional_date(value: object) -> date | None:
    return None if value is None else date.fromisoformat(_text(value))


def _optional_text(value: object) -> str | None:
    return None if value is None else _text(value)


def _text(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("Reference value must be non-empty text")
    return value


def _mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Reference value must be an object")
    return value


def _array(value: object) -> list[object]:
    if not isinstance(value, list):
        raise ValueError("Reference value must be an array")
    return value


def _strings(value: object) -> tuple[str, ...]:
    values = _array(value)
    if any(not isinstance(item, str) for item in values):
        raise ValueError("Reference value must be a string array")
    return tuple(str(item) for item in values)


__all__ = [
    "ETFReferenceRecord",
    "ETFThemeMappingRecord",
    "ETFThemeReferenceSnapshot",
    "MembershipKind",
    "ReferenceRole",
    "ReferenceValidity",
    "ThemeMembershipRecord",
    "ThemeTaxonomyRecord",
    "free_v1_reference_snapshot",
    "load_reference_snapshot",
    "publish_reference_snapshot",
]
