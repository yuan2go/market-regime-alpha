"""Market-owned immutable Provider qualification contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
import re
from uuid import UUID

from market_regime_alpha.market.domain.vocabulary import BarTimeframe, PriceBasis
from market_regime_alpha.shared.financial import bounded_decimal
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.identity import ContentHash
from market_regime_alpha.shared.time import require_utc


def _content_hash(value: ContentHash | str) -> ContentHash:
    return value if isinstance(value, ContentHash) else ContentHash(value)


class ProviderQualificationPurpose(StrEnum):
    HISTORICAL_PIT = "HISTORICAL_PIT"
    PROSPECTIVE_DECISION = "PROSPECTIVE_DECISION"
    OUTCOME_SETTLEMENT = "OUTCOME_SETTLEMENT"


class ProviderEvidenceClass(StrEnum):
    ENGINEERING_REHEARSAL = "ENGINEERING_REHEARSAL"
    RECORDED_PROVIDER = "RECORDED_PROVIDER"


class ProviderRequirementKind(StrEnum):
    COVERAGE = "COVERAGE"
    RAW_SOURCE_LINEAGE = "RAW_SOURCE_LINEAGE"
    HISTORICAL_AVAILABILITY = "HISTORICAL_AVAILABILITY"
    KNOWN_TIME = "KNOWN_TIME"
    REVISION_FINALITY = "REVISION_FINALITY"
    PRICE_BASIS = "PRICE_BASIS"
    TRADING_CALENDAR = "TRADING_CALENDAR"
    MEMBERSHIP_STATUS = "MEMBERSHIP_STATUS"
    DECISION_REFERENCE = "DECISION_REFERENCE"
    OUTCOME_PATH = "OUTCOME_PATH"


class ProviderRequirementResult(StrEnum):
    SATISFIED = "SATISFIED"
    REJECTED = "REJECTED"
    INCONCLUSIVE = "INCONCLUSIVE"


class ProviderQualificationDecisionStatus(StrEnum):
    ADMITTED = "ADMITTED"
    REJECTED = "REJECTED"
    INCONCLUSIVE = "INCONCLUSIVE"


class ProviderFinalityStatus(StrEnum):
    FINAL = "FINAL"
    PROVISIONAL = "PROVISIONAL"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class ProviderQualificationArtifact:
    artifact_id: UUID
    content_sha256: ContentHash | str
    size_bytes: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "content_sha256", _content_hash(self.content_sha256))
        if isinstance(self.size_bytes, bool) or self.size_bytes < 0:
            raise ValueError("Artifact size_bytes must be non-negative")


@dataclass(frozen=True, slots=True)
class ProviderQualificationRequirement:
    provider_qualification_requirement_id: UUID
    provider_qualification_protocol_id: UUID
    ordinal: int
    requirement_kind: ProviderRequirementKind
    minimum_observation_count: int
    minimum_ratio: Decimal
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        if isinstance(self.ordinal, bool) or self.ordinal < 1:
            raise ValueError("requirement ordinal must be positive")
        if not isinstance(self.requirement_kind, ProviderRequirementKind):
            raise TypeError("requirement_kind must be ProviderRequirementKind")
        if (
            isinstance(self.minimum_observation_count, bool)
            or self.minimum_observation_count < 1
        ):
            raise ValueError("minimum_observation_count must be positive")
        ratio = bounded_decimal(
            self.minimum_ratio,
            field="minimum_ratio",
            precision=12,
            scale=10,
        )
        if ratio < 0 or ratio > 1:
            raise ValueError("minimum_ratio must be between zero and one")
        object.__setattr__(self, "minimum_ratio", ratio)
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(
                canonical_json_sha256(
                    {
                        "minimum_observation_count": self.minimum_observation_count,
                        "minimum_ratio": ratio,
                        "ordinal": self.ordinal,
                        "requirement_kind": self.requirement_kind,
                    }
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class ProviderQualificationProtocol:
    provider_qualification_protocol_id: UUID
    protocol_code: str
    revision: int
    supersedes_protocol_id: UUID | None
    provider_product_id: UUID
    purpose: ProviderQualificationPurpose
    evidence_class: ProviderEvidenceClass
    market_scope: str
    instrument_scope: str
    exchange_code: str
    timeframe: BarTimeframe
    price_basis: PriceBasis
    decision_time_rule: str
    capture_window_start: datetime
    capture_window_end: datetime
    evidence_cutoff: datetime
    outcome_path_sessions: int
    requirements: tuple[ProviderQualificationRequirement, ...]
    code_artifact: ProviderQualificationArtifact
    config_artifact: ProviderQualificationArtifact
    provenance_sha256: ContentHash | str
    requirement_count: int = field(init=False)
    requirement_roster_sha256: ContentHash = field(init=False)
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,99}", self.protocol_code):
            raise ValueError("protocol_code has an invalid format")
        if isinstance(self.revision, bool) or self.revision < 1:
            raise ValueError("revision must be positive")
        if (self.revision == 1) != (self.supersedes_protocol_id is None):
            raise ValueError("Provider qualification protocol revision chain is invalid")
        for name, expected in (
            ("purpose", ProviderQualificationPurpose),
            ("evidence_class", ProviderEvidenceClass),
            ("timeframe", BarTimeframe),
            ("price_basis", PriceBasis),
        ):
            if not isinstance(getattr(self, name), expected):
                raise TypeError(f"{name} must be {expected.__name__}")
        if not self.market_scope or not self.instrument_scope:
            raise ValueError("market_scope and instrument_scope are required")
        if not re.fullmatch(r"[A-Z][A-Z0-9]{1,15}", self.exchange_code):
            raise ValueError("exchange_code has an invalid format")
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,99}", self.decision_time_rule):
            raise ValueError("decision_time_rule has an invalid format")
        start = require_utc(self.capture_window_start, field="capture_window_start")
        end = require_utc(self.capture_window_end, field="capture_window_end")
        cutoff = require_utc(self.evidence_cutoff, field="evidence_cutoff")
        object.__setattr__(self, "capture_window_start", start)
        object.__setattr__(self, "capture_window_end", end)
        object.__setattr__(self, "evidence_cutoff", cutoff)
        if end <= start:
            raise ValueError("capture window must be positive")
        if cutoff < end:
            raise ValueError("evidence cutoff cannot precede capture window end")
        if isinstance(self.outcome_path_sessions, bool) or self.outcome_path_sessions < 1:
            raise ValueError("outcome_path_sessions must be positive")
        expected_requirements = set(ProviderRequirementKind)
        actual = [item.requirement_kind for item in self.requirements]
        if len(actual) != len(expected_requirements) or set(actual) != expected_requirements:
            raise ValueError("every Provider requirement kind must occur exactly once")
        if any(
            item.provider_qualification_protocol_id
            != self.provider_qualification_protocol_id
            for item in self.requirements
        ):
            raise ValueError("requirement belongs to another Protocol")
        if tuple(item.ordinal for item in self.requirements) != tuple(
            range(1, len(self.requirements) + 1)
        ):
            raise ValueError("Provider requirement ordinals must be contiguous")
        provenance = _content_hash(self.provenance_sha256)
        roster_hash = ContentHash(
            canonical_json_sha256(
                [
                    {
                        "content_sha256": str(item.content_sha256),
                        "ordinal": item.ordinal,
                        "requirement_kind": item.requirement_kind,
                    }
                    for item in self.requirements
                ]
            )
        )
        object.__setattr__(self, "provenance_sha256", provenance)
        object.__setattr__(self, "requirement_count", len(self.requirements))
        object.__setattr__(self, "requirement_roster_sha256", roster_hash)
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(
                canonical_json_sha256(
                    {
                        "capture_window_end": end,
                        "capture_window_start": start,
                        "code_artifact": self.code_artifact,
                        "config_artifact": self.config_artifact,
                        "decision_time_rule": self.decision_time_rule,
                        "evidence_class": self.evidence_class,
                        "evidence_cutoff": cutoff,
                        "exchange_code": self.exchange_code,
                        "instrument_scope": self.instrument_scope,
                        "market_scope": self.market_scope,
                        "outcome_path_sessions": self.outcome_path_sessions,
                        "price_basis": self.price_basis,
                        "provider_product_id": self.provider_product_id,
                        "provenance_sha256": str(provenance),
                        "purpose": self.purpose,
                        "requirement_count": len(self.requirements),
                        "requirement_roster_sha256": str(roster_hash),
                        "revision": self.revision,
                        "supersedes_protocol_id": self.supersedes_protocol_id,
                        "timeframe": self.timeframe,
                    }
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class ProviderFinalityObservation:
    provider_finality_observation_id: UUID
    capture_id: UUID
    observation_ordinal: int
    supersedes_observation_id: UUID | None
    finality_status: ProviderFinalityStatus
    publication_observed_at: datetime
    code_artifact: ProviderQualificationArtifact
    config_artifact: ProviderQualificationArtifact
    provenance_sha256: ContentHash | str
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        if (
            isinstance(self.observation_ordinal, bool)
            or self.observation_ordinal < 1
        ):
            raise ValueError("observation_ordinal must be positive")
        if (self.observation_ordinal == 1) != (
            self.supersedes_observation_id is None
        ):
            raise ValueError("Provider finality observation revision chain is invalid")
        if not isinstance(self.finality_status, ProviderFinalityStatus):
            raise TypeError("finality_status must be ProviderFinalityStatus")
        observed = require_utc(
            self.publication_observed_at,
            field="publication_observed_at",
        )
        provenance = _content_hash(self.provenance_sha256)
        object.__setattr__(self, "publication_observed_at", observed)
        object.__setattr__(self, "provenance_sha256", provenance)
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(
                canonical_json_sha256(
                    {
                        "capture_id": self.capture_id,
                        "code_artifact": self.code_artifact,
                        "config_artifact": self.config_artifact,
                        "finality_status": self.finality_status,
                        "observation_ordinal": self.observation_ordinal,
                        "provenance_sha256": str(provenance),
                        "publication_observed_at": observed,
                        "supersedes_observation_id": self.supersedes_observation_id,
                    }
                )
            ),
        )


__all__ = [
    "ProviderEvidenceClass",
    "ProviderFinalityStatus",
    "ProviderFinalityObservation",
    "ProviderQualificationArtifact",
    "ProviderQualificationDecisionStatus",
    "ProviderQualificationProtocol",
    "ProviderQualificationPurpose",
    "ProviderQualificationRequirement",
    "ProviderRequirementKind",
    "ProviderRequirementResult",
]
