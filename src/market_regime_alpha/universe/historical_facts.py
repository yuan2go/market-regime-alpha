"""Immutable exploratory historical Security Facts owned by Free Research Universe."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
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


class HistoricalSecurityFactKind(str, Enum):
    INDUSTRY = "INDUSTRY"
    SHARE_CAPITAL = "SHARE_CAPITAL"
    ADJUSTMENT_EVENT = "ADJUSTMENT_EVENT"
    DIVIDEND_EVENT = "DIVIDEND_EVENT"


_REQUIRED_VALUE_KEYS = {
    HistoricalSecurityFactKind.INDUSTRY: {"industry", "classification"},
    HistoricalSecurityFactKind.SHARE_CAPITAL: {
        "liquid_shares",
        "total_shares",
    },
    HistoricalSecurityFactKind.ADJUSTMENT_EVENT: {
        "adjustment_factor",
        "back_adjust_factor",
        "forward_adjust_factor",
    },
    HistoricalSecurityFactKind.DIVIDEND_EVENT: {
        "cash_dividend_per_share_before_tax",
        "reserve_to_stock_per_share",
        "stock_dividend_per_share",
    },
}


@dataclass(frozen=True, slots=True)
class HistoricalSecurityFact:
    fact_id: ArtifactId
    fact_hash: str
    fact_kind: HistoricalSecurityFactKind
    symbol: str
    effective_date: date
    published_date: date | None
    values: tuple[tuple[str, str], ...]
    source_reference: ValidationArtifactReference
    reason_codes: tuple[str, ...]
    schema_version: str = "historical-security-fact/v1"

    def __post_init__(self) -> None:
        if self.schema_version != "historical-security-fact/v1":
            raise ValueError("unsupported Historical Security Fact schema")
        require_sha256("historical Security Fact hash", self.fact_hash)
        require_text("historical Security Fact symbol", self.symbol)
        if self.values != tuple(sorted(self.values)) or len(dict(self.values)) != len(self.values):
            raise ValueError("Historical Security Fact values must be sorted and unique")
        if set(dict(self.values)) != _REQUIRED_VALUE_KEYS[self.fact_kind]:
            raise ValueError("Historical Security Fact values do not match fact kind")
        if self.reason_codes != tuple(sorted(set(self.reason_codes))):
            raise ValueError("Historical Security Fact reasons must be sorted and unique")
        _validate_values(self.fact_kind, dict(self.values))
        if canonical_hash(self.identity_payload()) != self.fact_hash:
            raise ValueError("Historical Security Fact hash mismatch")
        if str(self.fact_id) != f"historical-security-fact:{self.fact_hash[7:]}":
            raise ValueError("Historical Security Fact identity mismatch")

    @classmethod
    def create(
        cls,
        *,
        fact_kind: HistoricalSecurityFactKind,
        symbol: str,
        effective_date: date,
        published_date: date | None,
        values: Mapping[str, str],
        source_reference: ValidationArtifactReference,
        reason_codes: tuple[str, ...] = (),
    ) -> HistoricalSecurityFact:
        ordered_values = tuple(sorted((str(key), str(value)) for key, value in values.items()))
        ordered_reasons = tuple(sorted(set(reason_codes)))
        payload = _fact_payload(
            fact_kind=fact_kind,
            symbol=symbol,
            effective_date=effective_date,
            published_date=published_date,
            values=ordered_values,
            source_reference=source_reference,
            reason_codes=ordered_reasons,
        )
        fact_id, digest = content_identity("historical-security-fact", payload)
        return cls(
            fact_id=fact_id,
            fact_hash=digest,
            fact_kind=fact_kind,
            symbol=symbol,
            effective_date=effective_date,
            published_date=published_date,
            values=ordered_values,
            source_reference=source_reference,
            reason_codes=ordered_reasons,
        )

    def identity_payload(self) -> dict[str, Any]:
        return _fact_payload(
            fact_kind=self.fact_kind,
            symbol=self.symbol,
            effective_date=self.effective_date,
            published_date=self.published_date,
            values=self.values,
            source_reference=self.source_reference,
            reason_codes=self.reason_codes,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "fact_id": str(self.fact_id),
            "fact_hash": self.fact_hash,
            **self.identity_payload(),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> HistoricalSecurityFact:
        values = payload.get("values")
        if not isinstance(values, Mapping):
            raise ValueError("Historical Security Fact values must be an object")
        return cls(
            fact_id=ArtifactId(str(payload["fact_id"])),
            fact_hash=str(payload["fact_hash"]),
            fact_kind=HistoricalSecurityFactKind(str(payload["fact_kind"])),
            symbol=str(payload["symbol"]),
            effective_date=date.fromisoformat(str(payload["effective_date"])),
            published_date=(None if payload.get("published_date") is None else date.fromisoformat(str(payload["published_date"]))),
            values=tuple(sorted((str(key), str(value)) for key, value in values.items())),
            source_reference=ValidationArtifactReference.from_canonical_dict(payload["source_reference"]),
            reason_codes=tuple(str(item) for item in payload["reason_codes"]),
            schema_version=str(payload["schema_version"]),
        )


@dataclass(frozen=True, slots=True)
class HistoricalSecurityFactCoverageGap:
    gap_id: ArtifactId
    gap_hash: str
    fact_kind: HistoricalSecurityFactKind
    symbol: str
    coverage_start: date
    coverage_end: date
    raw_row_hash: str
    source_reference: ValidationArtifactReference
    reason_codes: tuple[str, ...]
    schema_version: str = "historical-security-fact-coverage-gap/v1"

    def __post_init__(self) -> None:
        if self.schema_version != "historical-security-fact-coverage-gap/v1":
            raise ValueError("unsupported Historical Security Fact coverage-gap schema")
        if self.fact_kind not in {
            HistoricalSecurityFactKind.ADJUSTMENT_EVENT,
            HistoricalSecurityFactKind.DIVIDEND_EVENT,
        }:
            raise ValueError("Historical Security Fact coverage gaps are corporate-action only")
        require_sha256("historical Security Fact coverage-gap hash", self.gap_hash)
        require_sha256("historical Security Fact raw-row hash", self.raw_row_hash)
        require_text("historical Security Fact coverage-gap symbol", self.symbol)
        if self.coverage_start > self.coverage_end:
            raise ValueError("Historical Security Fact coverage-gap range is reversed")
        if not self.reason_codes or self.reason_codes != tuple(sorted(set(self.reason_codes))):
            raise ValueError("Historical Security Fact coverage-gap reasons must be ordered")
        if canonical_hash(self.identity_payload()) != self.gap_hash:
            raise ValueError("Historical Security Fact coverage-gap hash mismatch")
        if str(self.gap_id) != f"historical-security-fact-gap:{self.gap_hash[7:]}":
            raise ValueError("Historical Security Fact coverage-gap identity mismatch")

    @classmethod
    def create(
        cls,
        *,
        fact_kind: HistoricalSecurityFactKind,
        symbol: str,
        coverage_start: date,
        coverage_end: date,
        raw_row_hash: str,
        source_reference: ValidationArtifactReference,
        reason_codes: tuple[str, ...],
    ) -> HistoricalSecurityFactCoverageGap:
        ordered_reasons = tuple(sorted(set(reason_codes)))
        payload = _gap_payload(
            fact_kind=fact_kind,
            symbol=symbol,
            coverage_start=coverage_start,
            coverage_end=coverage_end,
            raw_row_hash=raw_row_hash,
            source_reference=source_reference,
            reason_codes=ordered_reasons,
        )
        gap_id, digest = content_identity("historical-security-fact-gap", payload)
        return cls(
            gap_id=gap_id,
            gap_hash=digest,
            fact_kind=fact_kind,
            symbol=symbol,
            coverage_start=coverage_start,
            coverage_end=coverage_end,
            raw_row_hash=raw_row_hash,
            source_reference=source_reference,
            reason_codes=ordered_reasons,
        )

    def identity_payload(self) -> dict[str, Any]:
        return _gap_payload(
            fact_kind=self.fact_kind,
            symbol=self.symbol,
            coverage_start=self.coverage_start,
            coverage_end=self.coverage_end,
            raw_row_hash=self.raw_row_hash,
            source_reference=self.source_reference,
            reason_codes=self.reason_codes,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "gap_id": str(self.gap_id),
            "gap_hash": self.gap_hash,
            **self.identity_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> HistoricalSecurityFactCoverageGap:
        return cls(
            gap_id=ArtifactId(str(payload["gap_id"])),
            gap_hash=str(payload["gap_hash"]),
            fact_kind=HistoricalSecurityFactKind(str(payload["fact_kind"])),
            symbol=str(payload["symbol"]),
            coverage_start=date.fromisoformat(str(payload["coverage_start"])),
            coverage_end=date.fromisoformat(str(payload["coverage_end"])),
            raw_row_hash=str(payload["raw_row_hash"]),
            source_reference=ValidationArtifactReference.from_canonical_dict(
                payload["source_reference"]
            ),
            reason_codes=tuple(str(item) for item in payload["reason_codes"]),
            schema_version=str(payload["schema_version"]),
        )


@dataclass(frozen=True, slots=True)
class HistoricalSecurityFactsOwner:
    owner_id: ArtifactId
    owner_hash: str
    first_effective_date: date
    last_effective_date: date
    known_at: datetime
    provider_id: str
    provider_contracts: tuple[str, ...]
    source_manifest_reference: ValidationArtifactReference
    raw_archive_id: str
    facts: tuple[HistoricalSecurityFact, ...]
    coverage_gaps: tuple[HistoricalSecurityFactCoverageGap, ...]
    limitations: tuple[str, ...]
    data_eligibility: DataEligibility = DataEligibility.EXPLORATORY
    evidence_ceiling: PITSourceEvidenceLevel = PITSourceEvidenceLevel.PIT_INCOMPLETE
    formal_pit: bool = False
    schema_version: str = "historical-security-facts-owner/v2"

    def __post_init__(self) -> None:
        if self.schema_version != "historical-security-facts-owner/v2":
            raise ValueError("unsupported Historical Security Facts owner schema")
        require_sha256("Historical Security Facts owner hash", self.owner_hash)
        require_text("Historical Security Facts provider", self.provider_id)
        require_text("Historical Security Facts raw archive", self.raw_archive_id)
        if self.first_effective_date > self.last_effective_date:
            raise ValueError("Historical Security Facts effective range is reversed")
        if self.known_at.tzinfo is None or self.known_at.utcoffset() is None:
            raise ValueError("Historical Security Facts known_at must be aware")
        if not self.provider_contracts or self.provider_contracts != tuple(sorted(set(self.provider_contracts))):
            raise ValueError("Historical Security Fact contracts must be ordered")
        if not self.facts or self.facts != tuple(sorted(self.facts, key=_fact_key)):
            raise ValueError("Historical Security Facts must be non-empty and ordered")
        if len({item.fact_id for item in self.facts}) != len(self.facts):
            raise ValueError("Historical Security Fact identities must be unique")
        if self.coverage_gaps != tuple(sorted(self.coverage_gaps, key=_gap_key)):
            raise ValueError("Historical Security Fact coverage gaps must be ordered")
        if len({item.gap_id for item in self.coverage_gaps}) != len(self.coverage_gaps):
            raise ValueError("Historical Security Fact coverage-gap identities must be unique")
        if any(not self.first_effective_date <= item.effective_date <= self.last_effective_date for item in self.facts):
            raise ValueError("Historical Security Fact is outside owner range")
        if any(
            item.coverage_start < self.first_effective_date
            or item.coverage_end > self.last_effective_date
            for item in self.coverage_gaps
        ):
            raise ValueError("Historical Security Fact coverage gap is outside owner range")
        if self.data_eligibility is not DataEligibility.EXPLORATORY:
            raise ValueError("Historical Security Facts must remain EXPLORATORY")
        if self.evidence_ceiling is not PITSourceEvidenceLevel.PIT_INCOMPLETE:
            raise ValueError("Historical Security Facts must remain PIT_INCOMPLETE")
        if self.formal_pit:
            raise ValueError("free Historical Security Facts cannot establish Formal PIT")
        required = {
            "FORMAL_PIT_NOT_ESTABLISHED",
            "FREE_DATA_EXPLORATORY",
            "HISTORICAL_AVAILABILITY_NOT_PROVIDED",
            "NO_CURRENT_STATE_BACKFILL",
            "PIT_INCOMPLETE",
            "UNRESOLVED_PROVIDER_ROWS_FAIL_CLOSED",
        }
        if not required.issubset(self.limitations):
            raise ValueError("Historical Security Facts limitations are incomplete")
        if canonical_hash(self.identity_payload()) != self.owner_hash:
            raise ValueError("Historical Security Facts owner hash mismatch")
        if str(self.owner_id) != f"historical-security-facts:{self.owner_hash[7:]}":
            raise ValueError("Historical Security Facts owner identity mismatch")

    @classmethod
    def create(
        cls,
        *,
        known_at: datetime,
        provider_id: str,
        provider_contracts: tuple[str, ...],
        source_manifest_reference: ValidationArtifactReference,
        raw_archive_id: str,
        facts: tuple[HistoricalSecurityFact, ...],
        coverage_gaps: tuple[HistoricalSecurityFactCoverageGap, ...] = (),
    ) -> HistoricalSecurityFactsOwner:
        ordered = tuple(sorted(facts, key=_fact_key))
        ordered_gaps = tuple(sorted(coverage_gaps, key=_gap_key))
        if not ordered:
            raise ValueError("Historical Security Facts owner requires facts")
        range_starts = [item.effective_date for item in ordered]
        range_starts.extend(item.coverage_start for item in ordered_gaps)
        range_ends = [item.effective_date for item in ordered]
        range_ends.extend(item.coverage_end for item in ordered_gaps)
        first_effective_date = min(range_starts)
        last_effective_date = max(range_ends)
        contracts = tuple(sorted(set(provider_contracts)))
        limitations = (
            "FORMAL_PIT_NOT_ESTABLISHED",
            "FREE_DATA_EXPLORATORY",
            "HISTORICAL_AVAILABILITY_NOT_PROVIDED",
            "NO_CURRENT_STATE_BACKFILL",
            "NO_PRODUCTION_AUTHORITY",
            "PIT_INCOMPLETE",
            "UNRESOLVED_PROVIDER_ROWS_FAIL_CLOSED",
        )
        values = _owner_payload(
            first_effective_date=first_effective_date,
            last_effective_date=last_effective_date,
            known_at=known_at,
            provider_id=provider_id,
            provider_contracts=contracts,
            source_manifest_reference=source_manifest_reference,
            raw_archive_id=raw_archive_id,
            facts=ordered,
            coverage_gaps=ordered_gaps,
            limitations=limitations,
        )
        owner_id, digest = content_identity("historical-security-facts", values)
        return cls(
            owner_id=owner_id,
            owner_hash=digest,
            first_effective_date=first_effective_date,
            last_effective_date=last_effective_date,
            known_at=known_at,
            provider_id=provider_id,
            provider_contracts=contracts,
            source_manifest_reference=source_manifest_reference,
            raw_archive_id=raw_archive_id,
            facts=ordered,
            coverage_gaps=ordered_gaps,
            limitations=limitations,
        )

    @property
    def reference(self) -> ValidationArtifactReference:
        return ValidationArtifactReference(
            "HISTORICAL_SECURITY_FACTS",
            self.owner_id,
            self.owner_hash,
        )

    def identity_payload(self) -> dict[str, Any]:
        return _owner_payload(
            first_effective_date=self.first_effective_date,
            last_effective_date=self.last_effective_date,
            known_at=self.known_at,
            provider_id=self.provider_id,
            provider_contracts=self.provider_contracts,
            source_manifest_reference=self.source_manifest_reference,
            raw_archive_id=self.raw_archive_id,
            facts=self.facts,
            coverage_gaps=self.coverage_gaps,
            limitations=self.limitations,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "owner_id": str(self.owner_id),
            "owner_hash": self.owner_hash,
            **self.identity_payload(),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> HistoricalSecurityFactsOwner:
        return cls(
            owner_id=ArtifactId(str(payload["owner_id"])),
            owner_hash=str(payload["owner_hash"]),
            first_effective_date=date.fromisoformat(str(payload["first_effective_date"])),
            last_effective_date=date.fromisoformat(str(payload["last_effective_date"])),
            known_at=datetime.fromisoformat(str(payload["known_at"])),
            provider_id=str(payload["provider_id"]),
            provider_contracts=tuple(str(item) for item in payload["provider_contracts"]),
            source_manifest_reference=ValidationArtifactReference.from_canonical_dict(payload["source_manifest_reference"]),
            raw_archive_id=str(payload["raw_archive_id"]),
            facts=tuple(HistoricalSecurityFact.from_canonical_dict(item) for item in payload["facts"]),
            coverage_gaps=tuple(
                HistoricalSecurityFactCoverageGap.from_canonical_dict(item)
                for item in payload["coverage_gaps"]
            ),
            limitations=tuple(str(item) for item in payload["limitations"]),
            data_eligibility=DataEligibility(str(payload["data_eligibility"])),
            evidence_ceiling=PITSourceEvidenceLevel(str(payload["evidence_ceiling"])),
            formal_pit=bool(payload["formal_pit"]),
            schema_version=str(payload["schema_version"]),
        )

    def industry_as_of(self, symbol: str, decision_date: date) -> HistoricalSecurityFact | None:
        return _latest(
            self.facts,
            symbol=symbol,
            fact_kind=HistoricalSecurityFactKind.INDUSTRY,
            decision_date=decision_date,
            require_publication=False,
        )

    def share_capital_as_of(self, symbol: str, decision_date: date) -> HistoricalSecurityFact | None:
        return _latest(
            self.facts,
            symbol=symbol,
            fact_kind=HistoricalSecurityFactKind.SHARE_CAPITAL,
            decision_date=decision_date,
            require_publication=True,
        )

    def corporate_actions(
        self,
        symbol: str,
        *,
        after: date,
        through: date,
    ) -> tuple[HistoricalSecurityFact, ...]:
        if after >= through:
            raise ValueError("Corporate-action interval must advance")
        return tuple(
            item
            for item in self.facts
            if item.symbol == symbol
            and item.fact_kind
            in {
                HistoricalSecurityFactKind.ADJUSTMENT_EVENT,
                HistoricalSecurityFactKind.DIVIDEND_EVENT,
            }
            and after < item.effective_date <= through
        )

    def corporate_action_gaps(
        self,
        symbol: str,
        *,
        after: date,
        through: date,
    ) -> tuple[HistoricalSecurityFactCoverageGap, ...]:
        if after >= through:
            raise ValueError("Corporate-action interval must advance")
        return tuple(
            item
            for item in self.coverage_gaps
            if item.symbol == symbol
            and item.coverage_start <= through
            and item.coverage_end > after
        )


def _fact_payload(
    *,
    fact_kind: HistoricalSecurityFactKind,
    symbol: str,
    effective_date: date,
    published_date: date | None,
    values: tuple[tuple[str, str], ...],
    source_reference: ValidationArtifactReference,
    reason_codes: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "schema_version": "historical-security-fact/v1",
        "fact_kind": fact_kind.value,
        "symbol": symbol,
        "effective_date": effective_date.isoformat(),
        "published_date": (None if published_date is None else published_date.isoformat()),
        "values": dict(values),
        "source_reference": source_reference.to_canonical_dict(),
        "reason_codes": list(reason_codes),
    }


def _gap_payload(
    *,
    fact_kind: HistoricalSecurityFactKind,
    symbol: str,
    coverage_start: date,
    coverage_end: date,
    raw_row_hash: str,
    source_reference: ValidationArtifactReference,
    reason_codes: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "schema_version": "historical-security-fact-coverage-gap/v1",
        "fact_kind": fact_kind.value,
        "symbol": symbol,
        "coverage_start": coverage_start.isoformat(),
        "coverage_end": coverage_end.isoformat(),
        "raw_row_hash": raw_row_hash,
        "source_reference": source_reference.to_canonical_dict(),
        "reason_codes": list(reason_codes),
    }


def _owner_payload(
    *,
    first_effective_date: date,
    last_effective_date: date,
    known_at: datetime,
    provider_id: str,
    provider_contracts: tuple[str, ...],
    source_manifest_reference: ValidationArtifactReference,
    raw_archive_id: str,
    facts: tuple[HistoricalSecurityFact, ...],
    coverage_gaps: tuple[HistoricalSecurityFactCoverageGap, ...],
    limitations: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "schema_version": "historical-security-facts-owner/v2",
        "first_effective_date": first_effective_date.isoformat(),
        "last_effective_date": last_effective_date.isoformat(),
        "known_at": timestamp(known_at),
        "provider_id": provider_id,
        "provider_contracts": list(provider_contracts),
        "source_manifest_reference": source_manifest_reference.to_canonical_dict(),
        "raw_archive_id": raw_archive_id,
        "facts": [item.to_canonical_dict() for item in facts],
        "coverage_gaps": [item.to_canonical_dict() for item in coverage_gaps],
        "data_eligibility": DataEligibility.EXPLORATORY.value,
        "evidence_ceiling": PITSourceEvidenceLevel.PIT_INCOMPLETE.value,
        "formal_pit": False,
        "limitations": list(limitations),
    }


def _validate_values(fact_kind: HistoricalSecurityFactKind, values: Mapping[str, str]) -> None:
    if fact_kind is HistoricalSecurityFactKind.INDUSTRY:
        if not values["industry"].strip() or not values["classification"].strip():
            raise ValueError("Historical Industry values must be present")
        return
    for key, value in values.items():
        if value == "":
            continue
        try:
            parsed = Decimal(value)
        except InvalidOperation as exc:
            raise ValueError(f"Historical Security Fact {key} must be decimal") from exc
        if not parsed.is_finite() or parsed < 0:
            raise ValueError(f"Historical Security Fact {key} must be non-negative")
    if fact_kind is HistoricalSecurityFactKind.SHARE_CAPITAL and not any(values[key] for key in ("total_shares", "liquid_shares")):
        raise ValueError("Historical Share Capital requires an observed share value")
    if fact_kind is HistoricalSecurityFactKind.ADJUSTMENT_EVENT and not values["adjustment_factor"]:
        raise ValueError("Historical Adjustment Event requires adjustment factor")


def _latest(
    facts: tuple[HistoricalSecurityFact, ...],
    *,
    symbol: str,
    fact_kind: HistoricalSecurityFactKind,
    decision_date: date,
    require_publication: bool,
) -> HistoricalSecurityFact | None:
    eligible = tuple(
        item
        for item in facts
        if item.symbol == symbol
        and item.fact_kind is fact_kind
        and item.effective_date <= decision_date
        and (not require_publication or (item.published_date is not None and item.published_date <= decision_date))
    )
    return (
        None
        if not eligible
        else max(
            eligible,
            key=lambda item: (
                item.published_date or item.effective_date,
                item.effective_date,
                str(item.fact_id),
            ),
        )
    )


def _fact_key(
    item: HistoricalSecurityFact,
) -> tuple[str, date, str, date, str]:
    return (
        item.symbol,
        item.effective_date,
        item.fact_kind.value,
        item.published_date or date.min,
        str(item.fact_id),
    )


def _gap_key(
    item: HistoricalSecurityFactCoverageGap,
) -> tuple[str, date, date, str, str]:
    return (
        item.symbol,
        item.coverage_start,
        item.coverage_end,
        item.fact_kind.value,
        str(item.gap_id),
    )


__all__ = [
    "HistoricalSecurityFact",
    "HistoricalSecurityFactCoverageGap",
    "HistoricalSecurityFactKind",
    "HistoricalSecurityFactsOwner",
]
