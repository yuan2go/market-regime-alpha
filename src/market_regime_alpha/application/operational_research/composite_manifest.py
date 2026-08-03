"""Typed, content-addressed authority for operational evidence composition."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Mapping

if TYPE_CHECKING:
    from market_regime_alpha.application.operational_research.supplemental_artifact import (
        VerifiedSupplementalResearchEvidence,
    )
    from market_regime_alpha.daily_decision.reader import (
        VerifiedPhaseDDailyDecisionArtifact,
    )

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.core.time import AvailabilityTime, DecisionTime
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.daily_decision.serialization import (
    eligibility_snapshot_to_dict,
    universe_snapshot_to_dict,
)
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    normalize_canonical_datetime,
    require_sha256,
    require_text,
)


COMPOSITE_OPERATIONAL_COMPOSITION_POLICY_SCHEMA = (
    "composite-operational-composition-policy-v1"
)
COMPOSITE_OPERATIONAL_INPUT_MANIFEST_SCHEMA = (
    "composite-operational-input-manifest-v1"
)


class CompositeOperationalCompositionStatus(str, Enum):
    ASSEMBLING = "ASSEMBLING"
    VERIFIED = "VERIFIED"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"
    CONFLICTED = "CONFLICTED"


class CompositeDecisionTimePolicy(str, Enum):
    EXACT_MATCH = "EXACT_MATCH"


class CompositeSourceConflictPolicy(str, Enum):
    FAIL_CLOSED = "FAIL_CLOSED"


class CompositeCoveragePolicy(str, Enum):
    EXACT_PREDICTION_POPULATION = "EXACT_PREDICTION_POPULATION"


class CompositeOperationalComponentRole(str, Enum):
    DAILY_DECISION_ARTIFACT = "DAILY_DECISION_ARTIFACT"
    DAILY_SOURCE_MANIFEST = "DAILY_SOURCE_MANIFEST"
    UNIVERSE_SNAPSHOT = "UNIVERSE_SNAPSHOT"
    ELIGIBILITY_SNAPSHOT = "ELIGIBILITY_SNAPSHOT"
    DECISION_PRICE_SNAPSHOT = "DECISION_PRICE_SNAPSHOT"
    PREDICTION_RUN = "PREDICTION_RUN"
    SUPPLEMENTAL_EVIDENCE_BUNDLE = "SUPPLEMENTAL_EVIDENCE_BUNDLE"
    SUPPLEMENTAL_SOURCE_MANIFEST = "SUPPLEMENTAL_SOURCE_MANIFEST"
    MARKET_OBSERVATION = "MARKET_OBSERVATION"
    THEME_OBSERVATION = "THEME_OBSERVATION"
    CAPITAL_OBSERVATION = "CAPITAL_OBSERVATION"
    SYMBOL_OBSERVATION = "SYMBOL_OBSERVATION"
    THEME_MEMBERSHIP = "THEME_MEMBERSHIP"
    ETF_THEME_MAPPING = "ETF_THEME_MAPPING"
    ETF_OBSERVATION = "ETF_OBSERVATION"
    STOCK_DAILY_BAR = "STOCK_DAILY_BAR"


class CompositeOperationalFieldGroup(str, Enum):
    PRICE = "PRICE"
    TRADING_STATUS = "TRADING_STATUS"
    ST_LISTING_STATUS = "ST_LISTING_STATUS"
    HISTORY = "HISTORY"
    UNIVERSE = "UNIVERSE"
    ELIGIBILITY = "ELIGIBILITY"
    PREDICTION_POPULATION = "PREDICTION_POPULATION"
    MARKET_OBSERVATION = "MARKET_OBSERVATION"
    THEME_OBSERVATION = "THEME_OBSERVATION"
    CAPITAL_OBSERVATION = "CAPITAL_OBSERVATION"
    SYMBOL_CAPITAL_PROXY = "SYMBOL_CAPITAL_PROXY"
    THEME_MEMBERSHIP = "THEME_MEMBERSHIP"
    ETF_THEME_MAPPING = "ETF_THEME_MAPPING"
    ETF_OBSERVATION = "ETF_OBSERVATION"
    STOCK_DAILY_BAR = "STOCK_DAILY_BAR"


@dataclass(frozen=True, slots=True)
class CompositeOperationalFieldAuthorityRequirement:
    field_group: CompositeOperationalFieldGroup
    component_role: CompositeOperationalComponentRole

    def __post_init__(self) -> None:
        if not isinstance(self.field_group, CompositeOperationalFieldGroup):
            raise TypeError("field_group must be CompositeOperationalFieldGroup")
        if not isinstance(self.component_role, CompositeOperationalComponentRole):
            raise TypeError("component_role must be CompositeOperationalComponentRole")

    @property
    def sort_key(self) -> tuple[str, str]:
        return (self.field_group.value, self.component_role.value)

    def to_canonical_dict(self) -> dict[str, str]:
        return {
            "field_group": self.field_group.value,
            "component_role": self.component_role.value,
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> CompositeOperationalFieldAuthorityRequirement:
        _fields(payload, {"field_group", "component_role"}, "field authority requirement")
        return cls(
            field_group=CompositeOperationalFieldGroup(str(payload["field_group"])),
            component_role=CompositeOperationalComponentRole(
                str(payload["component_role"])
            ),
        )


@dataclass(frozen=True, slots=True)
class CompositeOperationalCompositionPolicy:
    schema_version: str
    policy_id: ArtifactId
    policy_hash: str
    profile_id: str
    required_component_roles: tuple[CompositeOperationalComponentRole, ...]
    required_field_authorities: tuple[
        CompositeOperationalFieldAuthorityRequirement, ...
    ]
    allowed_data_eligibility: tuple[DataEligibility, ...]
    decision_time_policy: CompositeDecisionTimePolicy
    source_conflict_policy: CompositeSourceConflictPolicy
    coverage_policy: CompositeCoveragePolicy
    builder_revision: str

    def __post_init__(self) -> None:
        if self.schema_version != COMPOSITE_OPERATIONAL_COMPOSITION_POLICY_SCHEMA:
            raise ValueError("unsupported composite composition policy schema")
        require_text("profile_id", self.profile_id)
        require_text("builder_revision", self.builder_revision)
        if self.required_component_roles != tuple(
            sorted(self.required_component_roles, key=lambda item: item.value)
        ) or len(self.required_component_roles) != len(
            set(self.required_component_roles)
        ):
            raise ValueError("required component roles must be sorted and unique")
        if not self.required_component_roles:
            raise ValueError("required component roles must not be empty")
        if self.required_field_authorities != tuple(
            sorted(
                self.required_field_authorities,
                key=lambda item: item.sort_key,
            )
        ) or len(self.required_field_authorities) != len(
            set(self.required_field_authorities)
        ):
            raise ValueError("required field authorities must be sorted and unique")
        if not self.required_field_authorities:
            raise ValueError("required field authorities must not be empty")
        if self.allowed_data_eligibility != (DataEligibility.EXPLORATORY,):
            raise ValueError(
                "allowed_data_eligibility must be exactly EXPLORATORY"
            )
        if self.decision_time_policy is not CompositeDecisionTimePolicy.EXACT_MATCH:
            raise ValueError("unsupported decision time policy")
        if self.source_conflict_policy is not CompositeSourceConflictPolicy.FAIL_CLOSED:
            raise ValueError("unsupported source conflict policy")
        if (
            self.coverage_policy
            is not CompositeCoveragePolicy.EXACT_PREDICTION_POPULATION
        ):
            raise ValueError("unsupported coverage policy")
        require_sha256("policy_hash", self.policy_hash)
        expected_hash = canonical_hash(self.semantic_payload())
        expected_id = ArtifactId(
            f"composite-policy-{expected_hash.split(':', 1)[1][:24]}"
        )
        if self.policy_hash != expected_hash or self.policy_id != expected_id:
            raise ValueError("composite composition policy identity mismatch")

    @classmethod
    def create(
        cls,
        *,
        profile_id: str,
        required_component_roles: tuple[CompositeOperationalComponentRole, ...],
        required_field_authorities: tuple[
            CompositeOperationalFieldAuthorityRequirement, ...
        ],
        allowed_data_eligibility: tuple[DataEligibility, ...],
        decision_time_policy: CompositeDecisionTimePolicy,
        source_conflict_policy: CompositeSourceConflictPolicy,
        coverage_policy: CompositeCoveragePolicy,
        builder_revision: str,
    ) -> CompositeOperationalCompositionPolicy:
        if len(required_component_roles) != len(set(required_component_roles)):
            raise ValueError("required component roles must be unique")
        if len(required_field_authorities) != len(
            set(required_field_authorities)
        ):
            raise ValueError("required field authorities must be unique")
        roles = tuple(
            sorted(required_component_roles, key=lambda item: item.value)
        )
        authorities = tuple(
            sorted(required_field_authorities, key=lambda item: item.sort_key)
        )
        eligibility = tuple(allowed_data_eligibility)
        digest = canonical_hash(
            cls.semantic_payload_for(
                profile_id=profile_id,
                required_component_roles=roles,
                required_field_authorities=authorities,
                allowed_data_eligibility=eligibility,
                decision_time_policy=decision_time_policy,
                source_conflict_policy=source_conflict_policy,
                coverage_policy=coverage_policy,
                builder_revision=builder_revision,
            )
        )
        return cls(
            schema_version=COMPOSITE_OPERATIONAL_COMPOSITION_POLICY_SCHEMA,
            policy_id=ArtifactId(
                f"composite-policy-{digest.split(':', 1)[1][:24]}"
            ),
            policy_hash=digest,
            profile_id=profile_id,
            required_component_roles=roles,
            required_field_authorities=authorities,
            allowed_data_eligibility=eligibility,
            decision_time_policy=decision_time_policy,
            source_conflict_policy=source_conflict_policy,
            coverage_policy=coverage_policy,
            builder_revision=builder_revision,
        )

    @staticmethod
    def semantic_payload_for(**values: Any) -> dict[str, Any]:
        return {
            "schema_version": COMPOSITE_OPERATIONAL_COMPOSITION_POLICY_SCHEMA,
            "profile_id": values["profile_id"],
            "required_component_roles": [
                item.value for item in values["required_component_roles"]
            ],
            "required_field_authorities": [
                item.to_canonical_dict()
                for item in values["required_field_authorities"]
            ],
            "allowed_data_eligibility": [
                item.value for item in values["allowed_data_eligibility"]
            ],
            "decision_time_policy": values["decision_time_policy"].value,
            "source_conflict_policy": values["source_conflict_policy"].value,
            "coverage_policy": values["coverage_policy"].value,
            "builder_revision": values["builder_revision"],
        }

    def semantic_payload(self) -> dict[str, Any]:
        return self.semantic_payload_for(
            profile_id=self.profile_id,
            required_component_roles=self.required_component_roles,
            required_field_authorities=self.required_field_authorities,
            allowed_data_eligibility=self.allowed_data_eligibility,
            decision_time_policy=self.decision_time_policy,
            source_conflict_policy=self.source_conflict_policy,
            coverage_policy=self.coverage_policy,
            builder_revision=self.builder_revision,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            **self.semantic_payload(),
            "policy_id": str(self.policy_id),
            "policy_hash": self.policy_hash,
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> CompositeOperationalCompositionPolicy:
        _fields(
            payload,
            {
                "schema_version",
                "policy_id",
                "policy_hash",
                "profile_id",
                "required_component_roles",
                "required_field_authorities",
                "allowed_data_eligibility",
                "decision_time_policy",
                "source_conflict_policy",
                "coverage_policy",
                "builder_revision",
            },
            "composite composition policy",
        )
        return cls(
            schema_version=str(payload["schema_version"]),
            policy_id=ArtifactId(str(payload["policy_id"])),
            policy_hash=str(payload["policy_hash"]),
            profile_id=str(payload["profile_id"]),
            required_component_roles=tuple(
                CompositeOperationalComponentRole(str(item))
                for item in _array(payload["required_component_roles"])
            ),
            required_field_authorities=tuple(
                CompositeOperationalFieldAuthorityRequirement.from_canonical_dict(
                    _object(item)
                )
                for item in _array(payload["required_field_authorities"])
            ),
            allowed_data_eligibility=tuple(
                DataEligibility(str(item))
                for item in _array(payload["allowed_data_eligibility"])
            ),
            decision_time_policy=CompositeDecisionTimePolicy(
                str(payload["decision_time_policy"])
            ),
            source_conflict_policy=CompositeSourceConflictPolicy(
                str(payload["source_conflict_policy"])
            ),
            coverage_policy=CompositeCoveragePolicy(
                str(payload["coverage_policy"])
            ),
            builder_revision=str(payload["builder_revision"]),
        )


@dataclass(frozen=True, slots=True)
class CompositeOperationalComponentReference:
    role: CompositeOperationalComponentRole
    scope_key: str
    artifact_id: ArtifactId
    content_hash: str
    source_manifest_id: ArtifactId
    source_manifest_hash: str
    availability_time: AvailabilityTime
    data_eligibility: DataEligibility

    def __post_init__(self) -> None:
        if not isinstance(self.role, CompositeOperationalComponentRole):
            raise TypeError("role must be CompositeOperationalComponentRole")
        require_text("scope_key", self.scope_key)
        require_sha256("content_hash", self.content_hash)
        require_sha256("source_manifest_hash", self.source_manifest_hash)
        if not isinstance(self.availability_time, AvailabilityTime):
            raise TypeError("availability_time must be AvailabilityTime")
        object.__setattr__(
            self,
            "availability_time",
            AvailabilityTime(
                normalize_canonical_datetime(self.availability_time.value)
            ),
        )
        if self.data_eligibility is not DataEligibility.EXPLORATORY:
            raise ValueError("component authority cannot exceed EXPLORATORY")

    @property
    def sort_key(self) -> tuple[str, str]:
        return (self.role.value, self.scope_key)

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "role": self.role.value,
            "scope_key": self.scope_key,
            "artifact_id": str(self.artifact_id),
            "content_hash": self.content_hash,
            "source_manifest_id": str(self.source_manifest_id),
            "source_manifest_hash": self.source_manifest_hash,
            "availability_time": canonical_datetime(
                self.availability_time.value
            ),
            "data_eligibility": self.data_eligibility.value,
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> CompositeOperationalComponentReference:
        _fields(
            payload,
            {
                "role",
                "scope_key",
                "artifact_id",
                "content_hash",
                "source_manifest_id",
                "source_manifest_hash",
                "availability_time",
                "data_eligibility",
            },
            "composite component reference",
        )
        return cls(
            role=CompositeOperationalComponentRole(str(payload["role"])),
            scope_key=str(payload["scope_key"]),
            artifact_id=ArtifactId(str(payload["artifact_id"])),
            content_hash=str(payload["content_hash"]),
            source_manifest_id=ArtifactId(str(payload["source_manifest_id"])),
            source_manifest_hash=str(payload["source_manifest_hash"]),
            availability_time=AvailabilityTime(
                datetime.fromisoformat(str(payload["availability_time"]))
            ),
            data_eligibility=DataEligibility(str(payload["data_eligibility"])),
        )


@dataclass(frozen=True, slots=True)
class CompositeOperationalFieldAuthorityReference:
    field_group: CompositeOperationalFieldGroup
    scope_key: str
    component_role: CompositeOperationalComponentRole
    artifact_id: ArtifactId
    content_hash: str

    def __post_init__(self) -> None:
        if not isinstance(self.field_group, CompositeOperationalFieldGroup):
            raise TypeError("field_group must be CompositeOperationalFieldGroup")
        if not isinstance(self.component_role, CompositeOperationalComponentRole):
            raise TypeError("component_role must be CompositeOperationalComponentRole")
        require_text("scope_key", self.scope_key)
        require_sha256("content_hash", self.content_hash)

    @property
    def sort_key(self) -> tuple[str, str]:
        return (self.field_group.value, self.scope_key)

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "field_group": self.field_group.value,
            "scope_key": self.scope_key,
            "component_role": self.component_role.value,
            "artifact_id": str(self.artifact_id),
            "content_hash": self.content_hash,
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> CompositeOperationalFieldAuthorityReference:
        _fields(
            payload,
            {
                "field_group",
                "scope_key",
                "component_role",
                "artifact_id",
                "content_hash",
            },
            "composite field authority reference",
        )
        return cls(
            field_group=CompositeOperationalFieldGroup(str(payload["field_group"])),
            scope_key=str(payload["scope_key"]),
            component_role=CompositeOperationalComponentRole(
                str(payload["component_role"])
            ),
            artifact_id=ArtifactId(str(payload["artifact_id"])),
            content_hash=str(payload["content_hash"]),
        )


@dataclass(frozen=True, slots=True)
class CompositeOperationalInputManifest:
    schema_version: str
    manifest_id: ArtifactId
    content_hash: str
    status: CompositeOperationalCompositionStatus
    decision_time: DecisionTime
    created_at: datetime
    composition_policy_id: ArtifactId
    composition_policy_hash: str
    builder_revision: str
    daily_artifact_id: ArtifactId
    daily_artifact_hash: str
    daily_source_manifest_id: ArtifactId
    daily_source_manifest_hash: str
    supplemental_bundle_id: ArtifactId
    supplemental_bundle_hash: str
    supplemental_source_manifest_id: ArtifactId
    supplemental_source_manifest_hash: str
    component_references: tuple[CompositeOperationalComponentReference, ...]
    field_authority_references: tuple[
        CompositeOperationalFieldAuthorityReference, ...
    ]
    missing_evidence: tuple[str, ...]
    source_conflicts: tuple[str, ...]
    reason_codes: tuple[str, ...]
    limitations: tuple[str, ...]
    data_eligibility: DataEligibility
    formal_pit: str
    formal_oos_alpha: str
    trading_authority: str

    def __post_init__(self) -> None:
        if self.schema_version != COMPOSITE_OPERATIONAL_INPUT_MANIFEST_SCHEMA:
            raise ValueError("unsupported composite operational manifest schema")
        if self.status is CompositeOperationalCompositionStatus.ASSEMBLING:
            raise ValueError("ASSEMBLING cannot be an immutable manifest")
        if not isinstance(self.status, CompositeOperationalCompositionStatus):
            raise TypeError("status must be CompositeOperationalCompositionStatus")
        if not isinstance(self.decision_time, DecisionTime):
            raise TypeError("decision_time must be DecisionTime")
        _aware("created_at", self.created_at)
        object.__setattr__(
            self,
            "decision_time",
            DecisionTime(normalize_canonical_datetime(self.decision_time.value)),
        )
        object.__setattr__(
            self,
            "created_at",
            normalize_canonical_datetime(self.created_at),
        )
        if self.created_at < self.decision_time.value:
            raise ValueError("composite manifest cannot predate DecisionTime")
        require_text("builder_revision", self.builder_revision)
        for label, value in (
            ("content_hash", self.content_hash),
            ("composition_policy_hash", self.composition_policy_hash),
            ("daily_artifact_hash", self.daily_artifact_hash),
            ("daily_source_manifest_hash", self.daily_source_manifest_hash),
            ("supplemental_bundle_hash", self.supplemental_bundle_hash),
            (
                "supplemental_source_manifest_hash",
                self.supplemental_source_manifest_hash,
            ),
        ):
            require_sha256(label, value)
        if self.component_references != tuple(
            sorted(self.component_references, key=lambda item: item.sort_key)
        ) or len({item.sort_key for item in self.component_references}) != len(
            self.component_references
        ):
            raise ValueError("component reference keys must be sorted and unique")
        if self.field_authority_references != tuple(
            sorted(self.field_authority_references, key=lambda item: item.sort_key)
        ) or len(
            {item.sort_key for item in self.field_authority_references}
        ) != len(self.field_authority_references):
            raise ValueError("field authority reference keys must be sorted and unique")
        hashes_by_id: dict[ArtifactId, str] = {}
        for item in self.component_references:
            existing = hashes_by_id.get(item.artifact_id)
            if existing is not None and existing != item.content_hash:
                raise ValueError("component Artifact identity has conflicting hashes")
            hashes_by_id[item.artifact_id] = item.content_hash
            if item.availability_time.value > self.decision_time.value:
                raise ValueError("component is not available by DecisionTime")
        component_keys = {
            (
                item.role,
                item.scope_key,
                item.artifact_id,
                item.content_hash,
            )
            for item in self.component_references
        }
        for field_item in self.field_authority_references:
            if (
                field_item.component_role,
                field_item.scope_key,
                field_item.artifact_id,
                field_item.content_hash,
            ) not in component_keys:
                raise ValueError("field authority does not reference a component")
        for label, values in (
            ("missing evidence", self.missing_evidence),
            ("source conflicts", self.source_conflicts),
            ("reason codes", self.reason_codes),
            ("limitations", self.limitations),
        ):
            _sorted_unique_text(label, values)
        if (
            self.status is CompositeOperationalCompositionStatus.VERIFIED
            and (self.missing_evidence or self.source_conflicts)
        ):
            raise ValueError("VERIFIED manifest cannot carry missing/conflicting evidence")
        if (
            self.status is CompositeOperationalCompositionStatus.DATA_INSUFFICIENT
            and not self.missing_evidence
        ):
            raise ValueError("DATA_INSUFFICIENT requires missing evidence")
        if (
            self.status is CompositeOperationalCompositionStatus.CONFLICTED
            and not self.source_conflicts
        ):
            raise ValueError("CONFLICTED requires source conflicts")
        if (
            self.data_eligibility is not DataEligibility.EXPLORATORY
            or self.formal_pit != "FORMAL_PIT_NOT_ESTABLISHED"
            or self.formal_oos_alpha != "FORMAL_OOS_ALPHA_NOT_ESTABLISHED"
            or self.trading_authority != "TRADING_AUTHORITY_NOT_GRANTED"
        ):
            raise ValueError("composite operational authority cannot be inflated")
        expected_hash = canonical_hash(self.semantic_payload())
        expected_id = ArtifactId(
            f"composite-operational-{expected_hash.split(':', 1)[1][:24]}"
        )
        if self.content_hash != expected_hash or self.manifest_id != expected_id:
            raise ValueError("composite operational manifest identity mismatch")

    @classmethod
    def create(
        cls,
        *,
        status: CompositeOperationalCompositionStatus,
        decision_time: DecisionTime,
        created_at: datetime,
        composition_policy: CompositeOperationalCompositionPolicy,
        daily_artifact_id: ArtifactId,
        daily_artifact_hash: str,
        daily_source_manifest_id: ArtifactId,
        daily_source_manifest_hash: str,
        supplemental_bundle_id: ArtifactId,
        supplemental_bundle_hash: str,
        supplemental_source_manifest_id: ArtifactId,
        supplemental_source_manifest_hash: str,
        component_references: tuple[CompositeOperationalComponentReference, ...],
        field_authority_references: tuple[
            CompositeOperationalFieldAuthorityReference, ...
        ],
        missing_evidence: tuple[str, ...],
        source_conflicts: tuple[str, ...],
        reason_codes: tuple[str, ...],
        limitations: tuple[str, ...],
    ) -> CompositeOperationalInputManifest:
        policy = CompositeOperationalCompositionPolicy.from_canonical_dict(
            composition_policy.to_canonical_dict()
        )
        components = tuple(
            sorted(component_references, key=lambda item: item.sort_key)
        )
        authorities = tuple(
            sorted(field_authority_references, key=lambda item: item.sort_key)
        )
        missing = tuple(sorted(set(missing_evidence)))
        conflicts = tuple(sorted(set(source_conflicts)))
        reasons = tuple(sorted(set(reason_codes)))
        declared_limitations = tuple(sorted(set(limitations)))
        coverage_values = {
            "status": status,
            "component_references": components,
            "field_authority_references": authorities,
        }
        _validate_policy_coverage(policy, coverage_values)
        semantic = cls.semantic_payload_for(
            status=status,
            decision_time=decision_time,
            created_at=created_at,
            composition_policy_id=policy.policy_id,
            composition_policy_hash=policy.policy_hash,
            builder_revision=policy.builder_revision,
            daily_artifact_id=daily_artifact_id,
            daily_artifact_hash=daily_artifact_hash,
            daily_source_manifest_id=daily_source_manifest_id,
            daily_source_manifest_hash=daily_source_manifest_hash,
            supplemental_bundle_id=supplemental_bundle_id,
            supplemental_bundle_hash=supplemental_bundle_hash,
            supplemental_source_manifest_id=supplemental_source_manifest_id,
            supplemental_source_manifest_hash=supplemental_source_manifest_hash,
            component_references=components,
            field_authority_references=authorities,
            missing_evidence=missing,
            source_conflicts=conflicts,
            reason_codes=reasons,
            limitations=declared_limitations,
            data_eligibility=DataEligibility.EXPLORATORY,
            formal_pit="FORMAL_PIT_NOT_ESTABLISHED",
            formal_oos_alpha="FORMAL_OOS_ALPHA_NOT_ESTABLISHED",
            trading_authority="TRADING_AUTHORITY_NOT_GRANTED",
        )
        digest = canonical_hash(semantic)
        return cls(
            schema_version=COMPOSITE_OPERATIONAL_INPUT_MANIFEST_SCHEMA,
            manifest_id=ArtifactId(
                f"composite-operational-{digest.split(':', 1)[1][:24]}"
            ),
            content_hash=digest,
            status=status,
            decision_time=decision_time,
            created_at=created_at,
            composition_policy_id=policy.policy_id,
            composition_policy_hash=policy.policy_hash,
            builder_revision=policy.builder_revision,
            daily_artifact_id=daily_artifact_id,
            daily_artifact_hash=daily_artifact_hash,
            daily_source_manifest_id=daily_source_manifest_id,
            daily_source_manifest_hash=daily_source_manifest_hash,
            supplemental_bundle_id=supplemental_bundle_id,
            supplemental_bundle_hash=supplemental_bundle_hash,
            supplemental_source_manifest_id=supplemental_source_manifest_id,
            supplemental_source_manifest_hash=supplemental_source_manifest_hash,
            component_references=components,
            field_authority_references=authorities,
            missing_evidence=missing,
            source_conflicts=conflicts,
            reason_codes=reasons,
            limitations=declared_limitations,
            data_eligibility=DataEligibility.EXPLORATORY,
            formal_pit="FORMAL_PIT_NOT_ESTABLISHED",
            formal_oos_alpha="FORMAL_OOS_ALPHA_NOT_ESTABLISHED",
            trading_authority="TRADING_AUTHORITY_NOT_GRANTED",
        )

    @staticmethod
    def semantic_payload_for(**values: Any) -> dict[str, Any]:
        return {
            "schema_version": COMPOSITE_OPERATIONAL_INPUT_MANIFEST_SCHEMA,
            "status": values["status"].value,
            "decision_time": canonical_datetime(values["decision_time"].value),
            "created_at": canonical_datetime(values["created_at"]),
            "composition_policy_id": str(values["composition_policy_id"]),
            "composition_policy_hash": values["composition_policy_hash"],
            "builder_revision": values["builder_revision"],
            "daily_artifact_id": str(values["daily_artifact_id"]),
            "daily_artifact_hash": values["daily_artifact_hash"],
            "daily_source_manifest_id": str(values["daily_source_manifest_id"]),
            "daily_source_manifest_hash": values["daily_source_manifest_hash"],
            "supplemental_bundle_id": str(values["supplemental_bundle_id"]),
            "supplemental_bundle_hash": values["supplemental_bundle_hash"],
            "supplemental_source_manifest_id": str(
                values["supplemental_source_manifest_id"]
            ),
            "supplemental_source_manifest_hash": values[
                "supplemental_source_manifest_hash"
            ],
            "component_references": [
                item.to_canonical_dict() for item in values["component_references"]
            ],
            "field_authority_references": [
                item.to_canonical_dict()
                for item in values["field_authority_references"]
            ],
            "missing_evidence": list(values["missing_evidence"]),
            "source_conflicts": list(values["source_conflicts"]),
            "reason_codes": list(values["reason_codes"]),
            "limitations": list(values["limitations"]),
            "data_eligibility": values["data_eligibility"].value,
            "formal_pit": values["formal_pit"],
            "formal_oos_alpha": values["formal_oos_alpha"],
            "trading_authority": values["trading_authority"],
        }

    def semantic_payload(self) -> dict[str, Any]:
        names = (
            "status",
            "decision_time",
            "created_at",
            "composition_policy_id",
            "composition_policy_hash",
            "builder_revision",
            "daily_artifact_id",
            "daily_artifact_hash",
            "daily_source_manifest_id",
            "daily_source_manifest_hash",
            "supplemental_bundle_id",
            "supplemental_bundle_hash",
            "supplemental_source_manifest_id",
            "supplemental_source_manifest_hash",
            "component_references",
            "field_authority_references",
            "missing_evidence",
            "source_conflicts",
            "reason_codes",
            "limitations",
            "data_eligibility",
            "formal_pit",
            "formal_oos_alpha",
            "trading_authority",
        )
        return self.semantic_payload_for(
            **{name: getattr(self, name) for name in names}
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            **self.semantic_payload(),
            "manifest_id": str(self.manifest_id),
            "content_hash": self.content_hash,
        }

    @classmethod
    def from_canonical_dict(
        cls,
        payload: Mapping[str, Any],
        *,
        composition_policy: CompositeOperationalCompositionPolicy,
    ) -> CompositeOperationalInputManifest:
        expected = {
            "schema_version",
            "manifest_id",
            "content_hash",
            "status",
            "decision_time",
            "created_at",
            "composition_policy_id",
            "composition_policy_hash",
            "builder_revision",
            "daily_artifact_id",
            "daily_artifact_hash",
            "daily_source_manifest_id",
            "daily_source_manifest_hash",
            "supplemental_bundle_id",
            "supplemental_bundle_hash",
            "supplemental_source_manifest_id",
            "supplemental_source_manifest_hash",
            "component_references",
            "field_authority_references",
            "missing_evidence",
            "source_conflicts",
            "reason_codes",
            "limitations",
            "data_eligibility",
            "formal_pit",
            "formal_oos_alpha",
            "trading_authority",
        }
        _fields(payload, expected, "composite operational manifest")
        policy = CompositeOperationalCompositionPolicy.from_canonical_dict(
            composition_policy.to_canonical_dict()
        )
        result = cls(
            schema_version=str(payload["schema_version"]),
            manifest_id=ArtifactId(str(payload["manifest_id"])),
            content_hash=str(payload["content_hash"]),
            status=CompositeOperationalCompositionStatus(str(payload["status"])),
            decision_time=DecisionTime(
                datetime.fromisoformat(str(payload["decision_time"]))
            ),
            created_at=datetime.fromisoformat(str(payload["created_at"])),
            composition_policy_id=ArtifactId(
                str(payload["composition_policy_id"])
            ),
            composition_policy_hash=str(payload["composition_policy_hash"]),
            builder_revision=str(payload["builder_revision"]),
            daily_artifact_id=ArtifactId(str(payload["daily_artifact_id"])),
            daily_artifact_hash=str(payload["daily_artifact_hash"]),
            daily_source_manifest_id=ArtifactId(
                str(payload["daily_source_manifest_id"])
            ),
            daily_source_manifest_hash=str(payload["daily_source_manifest_hash"]),
            supplemental_bundle_id=ArtifactId(
                str(payload["supplemental_bundle_id"])
            ),
            supplemental_bundle_hash=str(payload["supplemental_bundle_hash"]),
            supplemental_source_manifest_id=ArtifactId(
                str(payload["supplemental_source_manifest_id"])
            ),
            supplemental_source_manifest_hash=str(
                payload["supplemental_source_manifest_hash"]
            ),
            component_references=tuple(
                CompositeOperationalComponentReference.from_canonical_dict(
                    _object(item)
                )
                for item in _array(payload["component_references"])
            ),
            field_authority_references=tuple(
                CompositeOperationalFieldAuthorityReference.from_canonical_dict(
                    _object(item)
                )
                for item in _array(payload["field_authority_references"])
            ),
            missing_evidence=_strings(payload["missing_evidence"]),
            source_conflicts=_strings(payload["source_conflicts"]),
            reason_codes=_strings(payload["reason_codes"]),
            limitations=_strings(payload["limitations"]),
            data_eligibility=DataEligibility(str(payload["data_eligibility"])),
            formal_pit=str(payload["formal_pit"]),
            formal_oos_alpha=str(payload["formal_oos_alpha"]),
            trading_authority=str(payload["trading_authority"]),
        )
        if (
            result.composition_policy_id != policy.policy_id
            or result.composition_policy_hash != policy.policy_hash
            or result.builder_revision != policy.builder_revision
        ):
            raise ValueError("composite manifest composition policy mismatch")
        _validate_policy_coverage(
            policy,
            {
                "status": result.status,
                "component_references": result.component_references,
                "field_authority_references": result.field_authority_references,
            },
        )
        return result


class CompositeOperationalManifestBuilder:
    """Compose two verified authorities without inventing missing evidence."""

    def build(
        self,
        *,
        daily: VerifiedPhaseDDailyDecisionArtifact,
        supplemental: VerifiedSupplementalResearchEvidence,
        composition_policy: CompositeOperationalCompositionPolicy,
        created_at: datetime,
    ) -> CompositeOperationalInputManifest:
        from market_regime_alpha.application.operational_research.supplemental_artifact import (
            VerifiedSupplementalResearchEvidence,
            load_verified_supplemental_research_evidence,
        )
        from market_regime_alpha.daily_decision.artifact import (
            DailyDecisionArtifactStatus,
        )
        from market_regime_alpha.daily_decision.reader import (
            VerifiedPhaseDDailyDecisionArtifact,
        )
        from market_regime_alpha.daily_decision.reader_registry import (
            load_verified_daily_decision_artifact,
        )

        if not isinstance(daily, VerifiedPhaseDDailyDecisionArtifact):
            raise TypeError("daily must be VerifiedPhaseDDailyDecisionArtifact")
        if not isinstance(supplemental, VerifiedSupplementalResearchEvidence):
            raise TypeError(
                "supplemental must be VerifiedSupplementalResearchEvidence"
            )
        _aware("created_at", created_at)
        policy = CompositeOperationalCompositionPolicy.from_canonical_dict(
            composition_policy.to_canonical_dict()
        )
        verified_daily = load_verified_daily_decision_artifact(daily.root)
        verified_supplemental = load_verified_supplemental_research_evidence(
            supplemental.root
        )
        daily_bundle = verified_daily.bundle
        supplemental_bundle = verified_supplemental.bundle
        decision_time = daily_bundle.source_manifest.decision_time
        missing: set[str] = set()
        conflicts: set[str] = set()

        if daily_bundle.status is not DailyDecisionArtifactStatus.DECISION_PUBLISHED:
            missing.add("DAILY_DECISION_NOT_PUBLISHED")
        if daily_bundle.universe_snapshot is None:
            missing.add("DAILY_UNIVERSE_SNAPSHOT_MISSING")
        if daily_bundle.eligibility_snapshot is None:
            missing.add("DAILY_ELIGIBILITY_SNAPSHOT_MISSING")
        if daily_bundle.decision_price_snapshot is None:
            missing.add("DAILY_DECISION_PRICE_SNAPSHOT_MISSING")
        if not daily_bundle.prediction_runs:
            missing.add("DAILY_PREDICTION_RUNS_MISSING")
        for missing_item in supplemental_bundle.missing_evidence:
            missing.update(missing_item.reason_codes)
        if not supplemental_bundle.theme_observations:
            missing.add("SUPPLEMENTAL_THEME_OBSERVATIONS_MISSING")
        if not supplemental_bundle.capital_observations:
            missing.add("SUPPLEMENTAL_CAPITAL_OBSERVATIONS_MISSING")
        if not supplemental_bundle.symbol_observations:
            missing.add("SUPPLEMENTAL_SYMBOL_OBSERVATIONS_MISSING")
        if not supplemental_bundle.theme_memberships:
            missing.add("SUPPLEMENTAL_THEME_MEMBERSHIP_MISSING")
        if not supplemental_bundle.etf_theme_mappings:
            missing.add("SUPPLEMENTAL_ETF_MAPPING_MISSING")
        if not supplemental_bundle.etf_observations:
            missing.add("SUPPLEMENTAL_ETF_OBSERVATIONS_MISSING")

        if supplemental_bundle.decision_time != decision_time:
            conflicts.add("DAILY_SUPPLEMENTAL_DECISION_TIME_CONFLICT")
        if (
            daily_bundle.source_manifest.data_eligibility
            is not DataEligibility.EXPLORATORY
            or supplemental_bundle.data_eligibility
            is not DataEligibility.EXPLORATORY
            or supplemental_bundle.source_manifest.data_eligibility
            is not DataEligibility.EXPLORATORY
        ):
            conflicts.add("COMPOSITE_DATA_ELIGIBILITY_INFLATION")
        conflicts.update(
            f"DAILY_SOURCE_CONFLICT:{item}"
            for item in daily_bundle.source_manifest.source_conflicts
        )
        conflicts.update(
            f"SUPPLEMENTAL_SOURCE_CONFLICT:{item}"
            for item in supplemental_bundle.source_manifest.source_conflicts
        )

        populations = tuple(
            {
                *(item.symbol for item in run.predictions),
                *(item.symbol for item in run.rejections),
            }
            for run in daily_bundle.prediction_runs
        )
        if populations and any(
            population != populations[0] for population in populations[1:]
        ):
            conflicts.add("PREDICTION_RUN_POPULATION_CONFLICT")
        population = populations[0] if populations else set()
        membership_symbols = {
            item.symbol for item in supplemental_bundle.theme_memberships
        }
        if populations and membership_symbols and membership_symbols != population:
            conflicts.add("PREDICTION_THEME_MEMBERSHIP_COVERAGE_CONFLICT")
        symbol_observation_symbols = {
            item.symbol for item in supplemental_bundle.symbol_observations
        }
        if (
            populations
            and symbol_observation_symbols
            and symbol_observation_symbols != population
        ):
            conflicts.add("PREDICTION_SYMBOL_OBSERVATION_COVERAGE_CONFLICT")

        theme_ids = {
            item.theme_id for item in supplemental_bundle.theme_observations
        }
        capital_theme_ids = {
            item.theme_id for item in supplemental_bundle.capital_observations
        }
        if theme_ids and capital_theme_ids and theme_ids != capital_theme_ids:
            conflicts.add("THEME_CAPITAL_COVERAGE_CONFLICT")
        membership_theme_ids = {
            theme_id
            for item in supplemental_bundle.theme_memberships
            for theme_id in (item.primary_theme_id, *item.supporting_theme_ids)
        }
        if theme_ids and membership_theme_ids and not membership_theme_ids.issubset(
            theme_ids
        ):
            conflicts.add("THEME_MEMBERSHIP_UNKNOWN_THEME_CONFLICT")
        expected_etf_pairs = {
            (etf_id, item.theme_id)
            for item in supplemental_bundle.theme_observations
            for etf_id in item.proxy_etf_ids
        }
        mapping_pairs = {
            (item.etf_id, item.theme_id)
            for item in supplemental_bundle.etf_theme_mappings
        }
        observation_pairs = {
            (item.etf_id, item.theme_id)
            for item in supplemental_bundle.etf_observations
        }
        if expected_etf_pairs and mapping_pairs and mapping_pairs != expected_etf_pairs:
            conflicts.add("THEME_ETF_MAPPING_COVERAGE_CONFLICT")
        if mapping_pairs and observation_pairs and observation_pairs != mapping_pairs:
            conflicts.add("ETF_MAPPING_OBSERVATION_COVERAGE_CONFLICT")

        components: list[CompositeOperationalComponentReference] = []
        fields: list[CompositeOperationalFieldAuthorityReference] = []
        hashes_by_id: dict[ArtifactId, str] = {}

        def add_component(
            *,
            role: CompositeOperationalComponentRole,
            scope_key: str,
            artifact_id: ArtifactId,
            content_hash: str,
            source_manifest_id: ArtifactId,
            source_manifest_hash: str,
            available_at: datetime,
        ) -> CompositeOperationalComponentReference | None:
            existing = hashes_by_id.get(artifact_id)
            if existing is not None and existing != content_hash:
                conflicts.add(f"ARTIFACT_HASH_CONFLICT:{artifact_id}")
                return None
            if available_at > decision_time.value:
                conflicts.add(f"COMPONENT_AVAILABLE_AFTER_DECISION_TIME:{role.value}:{scope_key}")
                return None
            hashes_by_id[artifact_id] = content_hash
            component = CompositeOperationalComponentReference(
                role=role,
                scope_key=scope_key,
                artifact_id=artifact_id,
                content_hash=content_hash,
                source_manifest_id=source_manifest_id,
                source_manifest_hash=source_manifest_hash,
                availability_time=AvailabilityTime(available_at),
                data_eligibility=DataEligibility.EXPLORATORY,
            )
            components.append(component)
            return component

        def add_field(
            field_group: CompositeOperationalFieldGroup,
            component: CompositeOperationalComponentReference | None,
        ) -> None:
            if component is None:
                return
            fields.append(
                CompositeOperationalFieldAuthorityReference(
                    field_group=field_group,
                    scope_key=component.scope_key,
                    component_role=component.role,
                    artifact_id=component.artifact_id,
                    content_hash=component.content_hash,
                )
            )

        daily_manifest = daily_bundle.source_manifest
        supplemental_manifest = supplemental_bundle.source_manifest
        daily_authority_available_at = max(
            item.retrieved_at.value for item in daily_manifest.source_artifacts
        )
        supplemental_authority_available_at = max(
            (
                item.retrieved_at.value
                for item in supplemental_manifest.source_artifacts
            ),
            default=supplemental_bundle.market_observation.available_at.value,
        )
        supplemental_authority_available_at = max(
            supplemental_authority_available_at,
            supplemental_bundle.market_observation.available_at.value,
            *(
                item.available_at.value
                for values in (
                    supplemental_bundle.theme_observations,
                    supplemental_bundle.capital_observations,
                    supplemental_bundle.symbol_observations,
                    supplemental_bundle.theme_memberships,
                    supplemental_bundle.etf_theme_mappings,
                    supplemental_bundle.etf_observations,
                    supplemental_bundle.stock_daily_bars,
                )
                for item in values
            ),
        )
        daily_source = add_component(
            role=CompositeOperationalComponentRole.DAILY_SOURCE_MANIFEST,
            scope_key="PRIMARY",
            artifact_id=daily_manifest.source_manifest_id,
            content_hash=daily_manifest.content_hash,
            source_manifest_id=daily_manifest.source_manifest_id,
            source_manifest_hash=daily_manifest.content_hash,
            available_at=daily_authority_available_at,
        )
        add_component(
            role=CompositeOperationalComponentRole.DAILY_DECISION_ARTIFACT,
            scope_key="PRIMARY",
            artifact_id=ArtifactId(verified_daily.artifact_id),
            content_hash=daily_bundle.content_hash,
            source_manifest_id=daily_manifest.source_manifest_id,
            source_manifest_hash=daily_manifest.content_hash,
            available_at=daily_authority_available_at,
        )
        for field_group in (
            CompositeOperationalFieldGroup.TRADING_STATUS,
            CompositeOperationalFieldGroup.ST_LISTING_STATUS,
            CompositeOperationalFieldGroup.HISTORY,
        ):
            add_field(field_group, daily_source)
        if daily_bundle.universe_snapshot is not None:
            universe = daily_bundle.universe_snapshot
            component = add_component(
                role=CompositeOperationalComponentRole.UNIVERSE_SNAPSHOT,
                scope_key="ALL",
                artifact_id=universe.evidence_artifact_id,
                content_hash=canonical_hash(universe_snapshot_to_dict(universe)),
                source_manifest_id=daily_manifest.source_manifest_id,
                source_manifest_hash=daily_manifest.content_hash,
                available_at=universe.as_of.value,
            )
            add_field(CompositeOperationalFieldGroup.UNIVERSE, component)
        if daily_bundle.eligibility_snapshot is not None:
            eligibility = daily_bundle.eligibility_snapshot
            component = add_component(
                role=CompositeOperationalComponentRole.ELIGIBILITY_SNAPSHOT,
                scope_key="ALL",
                artifact_id=eligibility.evidence_artifact_id,
                content_hash=canonical_hash(
                    eligibility_snapshot_to_dict(eligibility)
                ),
                source_manifest_id=daily_manifest.source_manifest_id,
                source_manifest_hash=daily_manifest.content_hash,
                available_at=eligibility.as_of.value,
            )
            add_field(CompositeOperationalFieldGroup.ELIGIBILITY, component)
        if daily_bundle.decision_price_snapshot is not None:
            price = daily_bundle.decision_price_snapshot
            component = add_component(
                role=CompositeOperationalComponentRole.DECISION_PRICE_SNAPSHOT,
                scope_key="ALL",
                artifact_id=price.decision_snapshot_id,
                content_hash=price.content_hash,
                source_manifest_id=daily_manifest.source_manifest_id,
                source_manifest_hash=daily_manifest.content_hash,
                available_at=price.decision_time.value,
            )
            add_field(CompositeOperationalFieldGroup.PRICE, component)
        for run in daily_bundle.prediction_runs:
            component = add_component(
                role=CompositeOperationalComponentRole.PREDICTION_RUN,
                scope_key=str(run.prediction_run_id),
                artifact_id=run.prediction_run_id,
                content_hash=run.content_hash,
                source_manifest_id=daily_manifest.source_manifest_id,
                source_manifest_hash=daily_manifest.content_hash,
                available_at=run.decision_time.value,
            )
            add_field(
                CompositeOperationalFieldGroup.PREDICTION_POPULATION,
                component,
            )

        supplemental_source = add_component(
            role=CompositeOperationalComponentRole.SUPPLEMENTAL_SOURCE_MANIFEST,
            scope_key="SUPPLEMENTAL",
            artifact_id=supplemental_manifest.source_manifest_id,
            content_hash=supplemental_manifest.content_hash,
            source_manifest_id=supplemental_manifest.source_manifest_id,
            source_manifest_hash=supplemental_manifest.content_hash,
            available_at=supplemental_authority_available_at,
        )
        del supplemental_source
        add_component(
            role=CompositeOperationalComponentRole.SUPPLEMENTAL_EVIDENCE_BUNDLE,
            scope_key="SUPPLEMENTAL",
            artifact_id=supplemental_bundle.bundle_id,
            content_hash=supplemental_bundle.content_hash,
            source_manifest_id=supplemental_manifest.source_manifest_id,
            source_manifest_hash=supplemental_manifest.content_hash,
            available_at=supplemental_authority_available_at,
        )
        supplemental_hashes = {
            item.artifact_id: item.content_hash
            for item in supplemental_manifest.source_artifacts
        }

        def add_supplemental(
            *,
            role: CompositeOperationalComponentRole,
            field_group: CompositeOperationalFieldGroup,
            scope_key: str,
            artifact_id: ArtifactId,
            available_at: datetime,
        ) -> None:
            content_hash = supplemental_hashes.get(artifact_id)
            if content_hash is None:
                missing.add(f"SUPPLEMENTAL_SOURCE_ARTIFACT_OMITTED:{artifact_id}")
                return
            component = add_component(
                role=role,
                scope_key=scope_key,
                artifact_id=artifact_id,
                content_hash=content_hash,
                source_manifest_id=supplemental_manifest.source_manifest_id,
                source_manifest_hash=supplemental_manifest.content_hash,
                available_at=available_at,
            )
            add_field(field_group, component)

        add_supplemental(
            role=CompositeOperationalComponentRole.MARKET_OBSERVATION,
            field_group=CompositeOperationalFieldGroup.MARKET_OBSERVATION,
            scope_key="MARKET",
            artifact_id=supplemental_bundle.market_observation.source_artifact_id,
            available_at=supplemental_bundle.market_observation.available_at.value,
        )
        for theme_item in supplemental_bundle.theme_observations:
            add_supplemental(
                role=CompositeOperationalComponentRole.THEME_OBSERVATION,
                field_group=CompositeOperationalFieldGroup.THEME_OBSERVATION,
                scope_key=theme_item.theme_id,
                artifact_id=theme_item.source_artifact_id,
                available_at=theme_item.available_at.value,
            )
        for capital_item in supplemental_bundle.capital_observations:
            add_supplemental(
                role=CompositeOperationalComponentRole.CAPITAL_OBSERVATION,
                field_group=CompositeOperationalFieldGroup.CAPITAL_OBSERVATION,
                scope_key=capital_item.theme_id,
                artifact_id=capital_item.source_artifact_id,
                available_at=capital_item.available_at.value,
            )
        for symbol_item in supplemental_bundle.symbol_observations:
            add_supplemental(
                role=CompositeOperationalComponentRole.SYMBOL_OBSERVATION,
                field_group=CompositeOperationalFieldGroup.SYMBOL_CAPITAL_PROXY,
                scope_key=symbol_item.symbol,
                artifact_id=symbol_item.source_artifact_id,
                available_at=symbol_item.available_at.value,
            )
        for membership_item in supplemental_bundle.theme_memberships:
            add_supplemental(
                role=CompositeOperationalComponentRole.THEME_MEMBERSHIP,
                field_group=CompositeOperationalFieldGroup.THEME_MEMBERSHIP,
                scope_key=membership_item.symbol,
                artifact_id=membership_item.source_artifact_id,
                available_at=membership_item.available_at.value,
            )
        for mapping_item in supplemental_bundle.etf_theme_mappings:
            add_supplemental(
                role=CompositeOperationalComponentRole.ETF_THEME_MAPPING,
                field_group=CompositeOperationalFieldGroup.ETF_THEME_MAPPING,
                scope_key=mapping_item.etf_id,
                artifact_id=mapping_item.source_artifact_id,
                available_at=mapping_item.available_at.value,
            )
        for etf_item in supplemental_bundle.etf_observations:
            add_supplemental(
                role=CompositeOperationalComponentRole.ETF_OBSERVATION,
                field_group=CompositeOperationalFieldGroup.ETF_OBSERVATION,
                scope_key=etf_item.etf_id,
                artifact_id=etf_item.source_artifact_id,
                available_at=etf_item.available_at.value,
            )
        for bar_item in supplemental_bundle.stock_daily_bars:
            add_supplemental(
                role=CompositeOperationalComponentRole.STOCK_DAILY_BAR,
                field_group=CompositeOperationalFieldGroup.STOCK_DAILY_BAR,
                scope_key=(
                    f"{bar_item.symbol}:{bar_item.session_date.isoformat()}"
                ),
                artifact_id=bar_item.source_artifact_id,
                available_at=bar_item.available_at.value,
            )

        actual_roles = {item.role for item in components}
        for required in policy.required_component_roles:
            if required not in actual_roles:
                missing.add(f"REQUIRED_COMPONENT_ROLE_MISSING:{required.value}")
        for requirement in policy.required_field_authorities:
            if not any(
                item.field_group is requirement.field_group
                and item.component_role is requirement.component_role
                for item in fields
            ):
                missing.add(
                    "REQUIRED_FIELD_AUTHORITY_MISSING:"
                    f"{requirement.field_group.value}:{requirement.component_role.value}"
                )

        if conflicts:
            status = CompositeOperationalCompositionStatus.CONFLICTED
        elif missing:
            status = CompositeOperationalCompositionStatus.DATA_INSUFFICIENT
        else:
            status = CompositeOperationalCompositionStatus.VERIFIED
        return CompositeOperationalInputManifest.create(
            status=status,
            decision_time=decision_time,
            created_at=created_at,
            composition_policy=policy,
            daily_artifact_id=ArtifactId(verified_daily.artifact_id),
            daily_artifact_hash=daily_bundle.content_hash,
            daily_source_manifest_id=daily_manifest.source_manifest_id,
            daily_source_manifest_hash=daily_manifest.content_hash,
            supplemental_bundle_id=supplemental_bundle.bundle_id,
            supplemental_bundle_hash=supplemental_bundle.content_hash,
            supplemental_source_manifest_id=(
                supplemental_manifest.source_manifest_id
            ),
            supplemental_source_manifest_hash=supplemental_manifest.content_hash,
            component_references=tuple(components),
            field_authority_references=tuple(fields),
            missing_evidence=tuple(missing),
            source_conflicts=tuple(conflicts),
            reason_codes=(f"COMPOSITE_OPERATIONAL_EVIDENCE_{status.value}",),
            limitations=tuple(
                {
                    *daily_manifest.limitations,
                    *supplemental_manifest.limitations,
                    "FORMAL_PIT_NOT_ESTABLISHED",
                    "FORMAL_OOS_ALPHA_NOT_ESTABLISHED",
                    "TRADING_AUTHORITY_NOT_GRANTED",
                }
            ),
        )


def _validate_policy_coverage(
    policy: CompositeOperationalCompositionPolicy,
    values: Mapping[str, Any],
) -> None:
    if values["status"] is not CompositeOperationalCompositionStatus.VERIFIED:
        return
    components = values["component_references"]
    fields = values["field_authority_references"]
    actual_roles = {item.role for item in components}
    if not set(policy.required_component_roles).issubset(actual_roles):
        raise ValueError("VERIFIED manifest omits a required component role")
    for requirement in policy.required_field_authorities:
        if not any(
            item.field_group is requirement.field_group
            and item.component_role is requirement.component_role
            for item in fields
        ):
            raise ValueError("VERIFIED manifest omits a required field authority")


def _fields(payload: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(payload) != expected:
        raise ValueError(f"{label} fields mismatch")


def _array(value: object) -> list[object]:
    if not isinstance(value, list):
        raise ValueError("composite operational value must be an array")
    return value


def _object(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("composite operational value must be an object")
    return value


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError("composite operational value must be a string array")
    return tuple(value)


def _sorted_unique_text(label: str, values: tuple[str, ...]) -> None:
    if values != tuple(sorted(values)) or len(values) != len(set(values)):
        raise ValueError(f"{label} must be sorted and unique")
    for value in values:
        require_text(label, value)


def _aware(label: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
