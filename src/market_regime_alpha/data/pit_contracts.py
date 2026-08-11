"""Small immutable contracts shared across Formal PIT authority components."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import (
    canonical_hash,
    require_sha256,
    require_text,
)


class PITContractError(ValueError):
    """A caller attempted to bypass a Formal PIT contract invariant."""


class PITFactKind(str, Enum):
    MARKET_DATA = "MARKET_DATA"
    TRADING_CALENDAR = "TRADING_CALENDAR"
    UNIVERSE_MEMBERSHIP = "UNIVERSE_MEMBERSHIP"
    TRADING_STATUS = "TRADING_STATUS"
    ST_STATUS = "ST_STATUS"
    LISTING_STATUS = "LISTING_STATUS"
    TRADING_ELIGIBILITY = "TRADING_ELIGIBILITY"
    ADJUSTMENT_FACTOR = "ADJUSTMENT_FACTOR"
    FEATURE_MATERIALIZATION = "FEATURE_MATERIALIZATION"
    FUNDAMENTAL = "FUNDAMENTAL"
    INDEX_MEMBERSHIP = "INDEX_MEMBERSHIP"
    INDUSTRY_MEMBERSHIP = "INDUSTRY_MEMBERSHIP"
    THEME_MEMBERSHIP = "THEME_MEMBERSHIP"
    ETF_MEMBERSHIP = "ETF_MEMBERSHIP"


class PITValidationOutcome(str, Enum):
    SATISFIED = "SATISFIED"
    REJECTED = "REJECTED"


class PITSourceAuthorityStatus(str, Enum):
    QUALIFIED = "QUALIFIED"
    SUSPENDED = "SUSPENDED"


class PITArtifactKind(str, Enum):
    SOURCE_MANIFEST = "SOURCE_MANIFEST"
    MARKET_DATA_DATASET = "DATASET"
    TRADING_CALENDAR = "TRADING_CALENDAR"
    UNIVERSE = "UNIVERSE"
    ELIGIBILITY = "ELIGIBILITY"
    FEATURE_MATERIALIZATION = "FEATURE_MATERIALIZATION"
    ADJUSTMENT_POLICY = "ADJUSTMENT_POLICY"
    CONFIGURATION = "CONFIGURATION"
    VALIDATION_PROTOCOL = "VALIDATION_PROTOCOL"
    PROVIDER_EVIDENCE = "PROVIDER_EVIDENCE"
    PROVIDER_ARCHIVE = "PROVIDER_ARCHIVE"
    MEMBERSHIP_DATASET = "MEMBERSHIP_DATASET"
    FUNDAMENTAL_DATASET = "FUNDAMENTAL_DATASET"


class PITFactEvidenceMode(str, Enum):
    PROSPECTIVE_CAPTURED_PIT = "PROSPECTIVE_CAPTURED_PIT"
    HISTORICAL_PROVIDER_PIT = "HISTORICAL_PROVIDER_PIT"


class PITSourceEvidenceLevel(str, Enum):
    FIXTURE = "FIXTURE"
    REPLAY = "REPLAY"
    FREE_DATA_EXPLORATORY = "FREE_DATA_EXPLORATORY"
    PIT_INCOMPLETE = "PIT_INCOMPLETE"
    FORMAL_PIT_CANDIDATE = "FORMAL_PIT_CANDIDATE"
    FORMAL_PIT_PROVIDER = "FORMAL_PIT_PROVIDER"


class PITProviderEvidenceKind(str, Enum):
    PROVIDER_CONTRACT = "PROVIDER_CONTRACT"
    HISTORICAL_AVAILABILITY = "HISTORICAL_AVAILABILITY"
    REVISION_POLICY = "REVISION_POLICY"
    DATASET_VERSIONING = "DATASET_VERSIONING"
    ARCHIVE_INTEGRITY = "ARCHIVE_INTEGRITY"
    INDEPENDENT_VALIDATION = "INDEPENDENT_VALIDATION"
    QUALIFICATION_DECISION = "QUALIFICATION_DECISION"
    SUSPENSION_DECISION = "SUSPENSION_DECISION"


class PITProviderEvidenceUse(str, Enum):
    SOURCE_QUALIFICATION = "SOURCE_QUALIFICATION"
    HISTORICAL_PROVIDER_PIT = "HISTORICAL_PROVIDER_PIT"


_SOURCE_EVIDENCE_RANK = {
    PITSourceEvidenceLevel.FIXTURE: 0,
    PITSourceEvidenceLevel.REPLAY: 1,
    PITSourceEvidenceLevel.FREE_DATA_EXPLORATORY: 2,
    PITSourceEvidenceLevel.PIT_INCOMPLETE: 3,
    PITSourceEvidenceLevel.FORMAL_PIT_CANDIDATE: 4,
    PITSourceEvidenceLevel.FORMAL_PIT_PROVIDER: 5,
}

FORMAL_PROVIDER_EVIDENCE_KINDS = tuple(
    sorted(
        {
            PITProviderEvidenceKind.PROVIDER_CONTRACT,
            PITProviderEvidenceKind.HISTORICAL_AVAILABILITY,
            PITProviderEvidenceKind.REVISION_POLICY,
            PITProviderEvidenceKind.DATASET_VERSIONING,
            PITProviderEvidenceKind.ARCHIVE_INTEGRITY,
            PITProviderEvidenceKind.INDEPENDENT_VALIDATION,
            PITProviderEvidenceKind.QUALIFICATION_DECISION,
        },
        key=lambda item: item.value,
    )
)


@dataclass(frozen=True, slots=True)
class PITArtifactReference:
    reference_kind: str
    artifact_id: ArtifactId
    content_hash: str

    def __post_init__(self) -> None:
        require_text("reference_kind", self.reference_kind)
        require_sha256("content_hash", self.content_hash)

    def to_canonical_dict(self) -> dict[str, str]:
        return {
            "reference_kind": self.reference_kind,
            "artifact_id": str(self.artifact_id),
            "content_hash": self.content_hash,
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> PITArtifactReference:
        _require_fields(
            payload,
            {"reference_kind", "artifact_id", "content_hash"},
            "PIT Artifact Reference",
        )
        return cls(
            reference_kind=_string(payload["reference_kind"]),
            artifact_id=ArtifactId(_string(payload["artifact_id"])),
            content_hash=_string(payload["content_hash"]),
        )


@dataclass(frozen=True, slots=True)
class PITProviderEvidence:
    evidence_kind: PITProviderEvidenceKind
    reference: PITArtifactReference
    provider_id: str
    provider_contract: str
    evidence_use: PITProviderEvidenceUse

    def __post_init__(self) -> None:
        require_text("provider_id", self.provider_id)
        require_text("provider_contract", self.provider_contract)
        if self.reference.reference_kind != PITArtifactKind.PROVIDER_EVIDENCE.value:
            raise PITContractError(
                "typed Provider evidence requires PROVIDER_EVIDENCE authority"
            )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "evidence_kind": self.evidence_kind.value,
            "reference": self.reference.to_canonical_dict(),
            "provider_id": self.provider_id,
            "provider_contract": self.provider_contract,
            "evidence_use": self.evidence_use.value,
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> PITProviderEvidence:
        _require_fields(
            payload,
            {
                "evidence_kind",
                "reference",
                "provider_id",
                "provider_contract",
                "evidence_use",
            },
            "PIT Provider Evidence",
        )
        reference = payload["reference"]
        if not isinstance(reference, Mapping):
            raise PITContractError("PIT Provider Evidence reference must be an object")
        return cls(
            evidence_kind=PITProviderEvidenceKind(_string(payload["evidence_kind"])),
            reference=PITArtifactReference.from_canonical_dict(reference),
            provider_id=_string(payload["provider_id"]),
            provider_contract=_string(payload["provider_contract"]),
            evidence_use=PITProviderEvidenceUse(_string(payload["evidence_use"])),
        )


@dataclass(frozen=True, slots=True)
class ProviderQualificationPolicy:
    policy_id: ArtifactId
    policy_hash: str
    provider_ceilings: tuple[tuple[str, PITSourceEvidenceLevel], ...]
    default_ceiling: PITSourceEvidenceLevel
    formal_required_evidence: tuple[PITProviderEvidenceKind, ...]
    schema_version: str = "pit-provider-qualification-policy-v1"

    def __post_init__(self) -> None:
        if self.schema_version != "pit-provider-qualification-policy-v1":
            raise PITContractError("unsupported Provider Qualification Policy schema")
        require_sha256("policy_hash", self.policy_hash)
        ordered = tuple(
            sorted(self.provider_ceilings, key=lambda item: item[0].casefold())
        )
        if not ordered or ordered != self.provider_ceilings:
            raise PITContractError("provider ceilings must be non-empty and sorted")
        normalized_ids = tuple(item[0].casefold() for item in ordered)
        if len(normalized_ids) != len(set(normalized_ids)):
            raise PITContractError("provider ceilings must be unique")
        for provider_id, _ in ordered:
            require_text("provider_id", provider_id)
        if self.formal_required_evidence != tuple(
            sorted(set(self.formal_required_evidence), key=lambda item: item.value)
        ):
            raise PITContractError("formal evidence kinds must be sorted and unique")
        if canonical_hash(self.semantic_payload()) != self.policy_hash:
            raise PITContractError("Provider Qualification Policy hash mismatch")
        if self.policy_id != _content_id("pit-provider-policy", self.policy_hash):
            raise PITContractError("Provider Qualification Policy identity mismatch")

    @classmethod
    def create(
        cls,
        *,
        provider_ceilings: tuple[tuple[str, PITSourceEvidenceLevel], ...],
        default_ceiling: PITSourceEvidenceLevel,
        formal_required_evidence: tuple[
            PITProviderEvidenceKind, ...
        ] = FORMAL_PROVIDER_EVIDENCE_KINDS,
    ) -> ProviderQualificationPolicy:
        normalized = tuple(
            sorted(
                (
                    (provider_id.casefold(), level)
                    for provider_id, level in provider_ceilings
                ),
                key=lambda item: item[0],
            )
        )
        required = tuple(
            sorted(set(formal_required_evidence), key=lambda item: item.value)
        )
        payload = _provider_policy_payload(
            provider_ceilings=normalized,
            default_ceiling=default_ceiling,
            formal_required_evidence=required,
        )
        digest = canonical_hash(payload)
        return cls(
            policy_id=_content_id("pit-provider-policy", digest),
            policy_hash=digest,
            provider_ceilings=normalized,
            default_ceiling=default_ceiling,
            formal_required_evidence=required,
        )

    @classmethod
    def default(cls) -> ProviderQualificationPolicy:
        return cls.create(
            provider_ceilings=(
                ("akshare", PITSourceEvidenceLevel.FREE_DATA_EXPLORATORY),
                ("baostock", PITSourceEvidenceLevel.FREE_DATA_EXPLORATORY),
                ("qmt", PITSourceEvidenceLevel.FORMAL_PIT_CANDIDATE),
                ("tencent", PITSourceEvidenceLevel.FREE_DATA_EXPLORATORY),
                ("thinktrader", PITSourceEvidenceLevel.FORMAL_PIT_CANDIDATE),
                ("tushare", PITSourceEvidenceLevel.PIT_INCOMPLETE),
                ("tushare-free", PITSourceEvidenceLevel.FREE_DATA_EXPLORATORY),
                ("xuntou", PITSourceEvidenceLevel.FORMAL_PIT_CANDIDATE),
                ("xtquant", PITSourceEvidenceLevel.FORMAL_PIT_CANDIDATE),
            ),
            default_ceiling=PITSourceEvidenceLevel.PIT_INCOMPLETE,
        )

    def maximum_level(self, provider_id: str) -> PITSourceEvidenceLevel:
        return dict(self.provider_ceilings).get(
            provider_id.casefold(), self.default_ceiling
        )

    def require_level(
        self,
        provider_id: str,
        requested: PITSourceEvidenceLevel,
        *,
        provider_contract: str | None = None,
        fact_kinds: tuple[PITFactKind, ...] = (),
    ) -> None:
        del provider_contract, fact_kinds
        require_text("provider_id", provider_id)
        maximum = self.maximum_level(provider_id)
        if _SOURCE_EVIDENCE_RANK[requested] > _SOURCE_EVIDENCE_RANK[maximum]:
            raise PITContractError(
                f"Provider evidence ceiling rejected {provider_id}: "
                f"{requested.value} exceeds {maximum.value}"
            )

    def require_formal_evidence(
        self, evidence: tuple[PITProviderEvidence, ...]
    ) -> None:
        kinds = {item.evidence_kind for item in evidence}
        missing = set(self.formal_required_evidence).difference(kinds)
        if missing:
            raise PITContractError(
                "formal Provider evidence incomplete: "
                + ",".join(sorted(item.value for item in missing))
            )

    def semantic_payload(self) -> dict[str, Any]:
        return _provider_policy_payload(
            provider_ceilings=self.provider_ceilings,
            default_ceiling=self.default_ceiling,
            formal_required_evidence=self.formal_required_evidence,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "policy_id": str(self.policy_id),
            "policy_hash": self.policy_hash,
            **self.semantic_payload(),
        }

    @property
    def reference(self) -> PITArtifactReference:
        return PITArtifactReference(
            PITArtifactKind.CONFIGURATION.value,
            self.policy_id,
            self.policy_hash,
        )


@dataclass(frozen=True, slots=True)
class ProviderFactCeiling:
    """Maximum evidence level for one exact Provider/Contract/Fact scope."""

    provider_id: str
    provider_contract: str
    fact_kind: PITFactKind
    maximum_level: PITSourceEvidenceLevel

    def __post_init__(self) -> None:
        require_text("provider_id", self.provider_id)
        require_text("provider_contract", self.provider_contract)

    def to_canonical_dict(self) -> dict[str, str]:
        return {
            "provider_id": self.provider_id,
            "provider_contract": self.provider_contract,
            "fact_kind": self.fact_kind.value,
            "maximum_level": self.maximum_level.value,
        }


@dataclass(frozen=True, slots=True)
class ProviderQualificationPolicyV2:
    """Fact-scoped Provider ceiling; it never promotes a Provider wholesale."""

    policy_id: ArtifactId
    policy_hash: str
    scope_ceilings: tuple[ProviderFactCeiling, ...]
    default_ceiling: PITSourceEvidenceLevel
    formal_required_evidence: tuple[PITProviderEvidenceKind, ...]
    schema_version: str = "pit-provider-qualification-policy-v2"

    def __post_init__(self) -> None:
        if self.schema_version != "pit-provider-qualification-policy-v2":
            raise PITContractError("unsupported Provider Qualification Policy V2 schema")
        require_sha256("policy_hash", self.policy_hash)
        ordered = tuple(sorted(self.scope_ceilings, key=_provider_fact_ceiling_key))
        if not ordered or ordered != self.scope_ceilings:
            raise PITContractError("Provider fact ceilings must be non-empty and sorted")
        keys = tuple(_provider_fact_ceiling_key(item) for item in ordered)
        if len(keys) != len(set(keys)):
            raise PITContractError("Provider fact ceilings must be unique")
        if self.formal_required_evidence != tuple(
            sorted(set(self.formal_required_evidence), key=lambda item: item.value)
        ):
            raise PITContractError("formal evidence kinds must be sorted and unique")
        if canonical_hash(self.semantic_payload()) != self.policy_hash:
            raise PITContractError("Provider Qualification Policy V2 hash mismatch")
        if self.policy_id != _content_id("pit-provider-policy-v2", self.policy_hash):
            raise PITContractError("Provider Qualification Policy V2 identity mismatch")

    @classmethod
    def create(
        cls,
        *,
        scope_ceilings: tuple[ProviderFactCeiling, ...],
        default_ceiling: PITSourceEvidenceLevel,
        formal_required_evidence: tuple[
            PITProviderEvidenceKind, ...
        ] = FORMAL_PROVIDER_EVIDENCE_KINDS,
    ) -> ProviderQualificationPolicyV2:
        normalized = tuple(
            sorted(
                (
                    ProviderFactCeiling(
                        item.provider_id.casefold(),
                        item.provider_contract,
                        item.fact_kind,
                        item.maximum_level,
                    )
                    for item in scope_ceilings
                ),
                key=_provider_fact_ceiling_key,
            )
        )
        required = tuple(
            sorted(set(formal_required_evidence), key=lambda item: item.value)
        )
        payload = _provider_policy_v2_payload(
            scope_ceilings=normalized,
            default_ceiling=default_ceiling,
            formal_required_evidence=required,
        )
        digest = canonical_hash(payload)
        return cls(
            _content_id("pit-provider-policy-v2", digest),
            digest,
            normalized,
            default_ceiling,
            required,
        )

    @classmethod
    def default(cls) -> ProviderQualificationPolicyV2:
        free_scopes = tuple(
            ProviderFactCeiling(
                provider_id,
                provider_contract,
                fact_kind,
                PITSourceEvidenceLevel.FREE_DATA_EXPLORATORY,
            )
            for provider_id, provider_contract, fact_kinds in (
                (
                    "provider-baostock-public",
                    "baostock-public-history-v1",
                    (PITFactKind.ADJUSTMENT_FACTOR, PITFactKind.MARKET_DATA),
                ),
                (
                    "provider-baostock-public",
                    "baostock-public-status-v1",
                    (
                        PITFactKind.LISTING_STATUS,
                        PITFactKind.ST_STATUS,
                        PITFactKind.TRADING_CALENDAR,
                        PITFactKind.TRADING_ELIGIBILITY,
                        PITFactKind.TRADING_STATUS,
                    ),
                ),
                (
                    "provider-baostock-public",
                    "baostock-query-stock-basic-all/v1",
                    (PITFactKind.UNIVERSE_MEMBERSHIP,),
                ),
                (
                    "provider-tencent-public",
                    "tencent-public-current-v1",
                    (PITFactKind.MARKET_DATA,),
                ),
                (
                    "provider-tencent-public",
                    "tencent-public-minute-v1",
                    (PITFactKind.MARKET_DATA,),
                ),
            )
            for fact_kind in fact_kinds
        )
        return cls.create(
            scope_ceilings=free_scopes,
            default_ceiling=PITSourceEvidenceLevel.PIT_INCOMPLETE,
        )

    def maximum_level(
        self,
        provider_id: str,
        *,
        provider_contract: str,
        fact_kind: PITFactKind,
    ) -> PITSourceEvidenceLevel:
        key = (provider_id.casefold(), provider_contract, fact_kind.value)
        values = {
            _provider_fact_ceiling_key(item): item.maximum_level
            for item in self.scope_ceilings
        }
        return values.get(key, self.default_ceiling)

    def require_level(
        self,
        provider_id: str,
        requested: PITSourceEvidenceLevel,
        *,
        provider_contract: str | None = None,
        fact_kinds: tuple[PITFactKind, ...] = (),
    ) -> None:
        require_text("provider_id", provider_id)
        if provider_contract is None or not fact_kinds:
            raise PITContractError(
                "Provider Qualification Policy V2 requires Contract and Fact Kind"
            )
        require_text("provider_contract", provider_contract)
        for fact_kind in fact_kinds:
            maximum = self.maximum_level(
                provider_id,
                provider_contract=provider_contract,
                fact_kind=fact_kind,
            )
            if _SOURCE_EVIDENCE_RANK[requested] > _SOURCE_EVIDENCE_RANK[maximum]:
                raise PITContractError(
                    "Provider evidence ceiling rejected "
                    f"{provider_id}/{provider_contract}/{fact_kind.value}: "
                    f"{requested.value} exceeds {maximum.value}"
                )

    def require_formal_evidence(
        self, evidence: tuple[PITProviderEvidence, ...]
    ) -> None:
        kinds = {item.evidence_kind for item in evidence}
        missing = set(self.formal_required_evidence).difference(kinds)
        if missing:
            raise PITContractError(
                "formal Provider evidence incomplete: "
                + ",".join(sorted(item.value for item in missing))
            )

    def semantic_payload(self) -> dict[str, Any]:
        return _provider_policy_v2_payload(
            scope_ceilings=self.scope_ceilings,
            default_ceiling=self.default_ceiling,
            formal_required_evidence=self.formal_required_evidence,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "policy_id": str(self.policy_id),
            "policy_hash": self.policy_hash,
            **self.semantic_payload(),
        }

    @property
    def reference(self) -> PITArtifactReference:
        return PITArtifactReference(
            PITArtifactKind.CONFIGURATION.value,
            self.policy_id,
            self.policy_hash,
        )


def provider_evidence_key(
    item: PITProviderEvidence,
) -> tuple[str, str, str, str, tuple[str, str, str]]:
    reference_key = (
        item.reference.reference_kind,
        str(item.reference.artifact_id),
        item.reference.content_hash,
    )
    return (
        item.evidence_kind.value,
        item.provider_id,
        item.provider_contract,
        item.evidence_use.value,
        reference_key,
    )


def _provider_policy_payload(
    *,
    provider_ceilings: tuple[tuple[str, PITSourceEvidenceLevel], ...],
    default_ceiling: PITSourceEvidenceLevel,
    formal_required_evidence: tuple[PITProviderEvidenceKind, ...],
) -> dict[str, Any]:
    return {
        "schema_version": "pit-provider-qualification-policy-v1",
        "provider_ceilings": [
            {"provider_id": provider_id, "maximum_level": level.value}
            for provider_id, level in provider_ceilings
        ],
        "default_ceiling": default_ceiling.value,
        "formal_required_evidence": [
            item.value for item in formal_required_evidence
        ],
    }


def _provider_fact_ceiling_key(
    item: ProviderFactCeiling,
) -> tuple[str, str, str]:
    return (
        item.provider_id.casefold(),
        item.provider_contract,
        item.fact_kind.value,
    )


def _provider_policy_v2_payload(
    *,
    scope_ceilings: tuple[ProviderFactCeiling, ...],
    default_ceiling: PITSourceEvidenceLevel,
    formal_required_evidence: tuple[PITProviderEvidenceKind, ...],
) -> dict[str, Any]:
    return {
        "schema_version": "pit-provider-qualification-policy-v2",
        "scope": "PROVIDER_X_CONTRACT_X_FACT_KIND",
        "scope_ceilings": [item.to_canonical_dict() for item in scope_ceilings],
        "default_ceiling": default_ceiling.value,
        "formal_required_evidence": [
            item.value for item in formal_required_evidence
        ],
        "qualification_decision_rule": (
            "LATEST_NON_SUPERSEDED_SOURCE_QUALIFICATION_AND_ALL_REQUIRED_EVIDENCE"
        ),
        "suspension_revocation_rule": "LATEST_SCOPE_DECISION_CONTROLS",
        "silent_fallback": False,
    }


def _content_id(prefix: str, content_hash: str) -> ArtifactId:
    return ArtifactId(f"{prefix}-{content_hash.split(':', 1)[1][:24]}")


def _require_fields(payload: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(payload) != expected:
        raise PITContractError(f"{label} fields mismatch")


def _string(value: object) -> str:
    if not isinstance(value, str):
        raise PITContractError("expected string")
    return value


__all__ = [
    "FORMAL_PROVIDER_EVIDENCE_KINDS",
    "PITArtifactKind",
    "PITArtifactReference",
    "PITContractError",
    "PITFactEvidenceMode",
    "PITFactKind",
    "PITProviderEvidence",
    "PITProviderEvidenceKind",
    "PITProviderEvidenceUse",
    "ProviderFactCeiling",
    "PITSourceAuthorityStatus",
    "PITSourceEvidenceLevel",
    "PITValidationOutcome",
    "ProviderQualificationPolicy",
    "ProviderQualificationPolicyV2",
    "provider_evidence_key",
]
