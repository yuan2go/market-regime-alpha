"""Model qualification, deployment and Runtime-selection evidence contracts.

This module extends the existing Model Registry.  It deliberately does not own
model lifecycle transitions: :mod:`model_registry` remains that authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import re
from typing import Any, Mapping

from market_regime_alpha.core.identity import (
    ArtifactId,
    FeatureDefinitionId,
    ModelId,
    TargetId,
    UniverseId,
)
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    require_sha256,
    require_text,
)
from market_regime_alpha.market_data.contracts import parse_utc_second
from market_regime_alpha.platform.contracts import ModelDefinition, ModelLifecycleStatus
from market_regime_alpha.platform.model_registry import ModelRegistration


_RAW_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class RuntimePurpose(str, Enum):
    RESEARCH = "RESEARCH"
    BACKTEST = "BACKTEST"
    SHADOW = "SHADOW"
    PRODUCTION_DECISION = "PRODUCTION_DECISION"


class RuntimeAuthorityMode(str, Enum):
    """Top-level Runtime authority; never inferred from data or model state."""

    RESEARCH = "RESEARCH"
    SHADOW = "SHADOW"
    PRODUCTION = "PRODUCTION"

    @property
    def runtime_purpose(self) -> RuntimePurpose:
        return {
            RuntimeAuthorityMode.RESEARCH: RuntimePurpose.RESEARCH,
            RuntimeAuthorityMode.SHADOW: RuntimePurpose.SHADOW,
            RuntimeAuthorityMode.PRODUCTION: RuntimePurpose.PRODUCTION_DECISION,
        }[self]

    @property
    def requires_production_authorization(self) -> bool:
        return self is RuntimeAuthorityMode.PRODUCTION


class AssignmentLane(str, Enum):
    CHAMPION = "CHAMPION"
    CHALLENGER = "CHALLENGER"


class AssignmentStatus(str, Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    REPLACED = "REPLACED"


class QualificationEvidenceKind(str, Enum):
    DATASET_INTEGRITY = "DATASET_INTEGRITY"
    FEATURE_LINEAGE = "FEATURE_LINEAGE"
    IMPLEMENTATION_REPRODUCIBILITY = "IMPLEMENTATION_REPRODUCIBILITY"
    BACKTEST_VALIDATION = "BACKTEST_VALIDATION"
    FORMAL_PIT = "FORMAL_PIT"
    FORMAL_OOS = "FORMAL_OOS"
    ECONOMIC_VALIDATION = "ECONOMIC_VALIDATION"
    COST_CAPACITY = "COST_CAPACITY"
    SHADOW_OPERATION = "SHADOW_OPERATION"
    OPERATOR_APPROVAL = "OPERATOR_APPROVAL"


class QualificationEvidenceOutcome(str, Enum):
    SATISFIED = "SATISFIED"
    FAILED = "FAILED"
    REVOKED = "REVOKED"


class QualificationStatus(str, Enum):
    QUALIFIED = "QUALIFIED"
    NOT_QUALIFIED = "NOT_QUALIFIED"


class SelectionStatus(str, Enum):
    SELECTED = "SELECTED"
    REJECTED = "REJECTED"


PRODUCTION_DECISION_EVIDENCE_FLOOR = frozenset(QualificationEvidenceKind)
_TERMINAL_RUNTIME_LIFECYCLES = frozenset(
    {ModelLifecycleStatus.SUSPENDED, ModelLifecycleStatus.RETIRED}
)


@dataclass(frozen=True, slots=True)
class ModelSelectionRequest:
    request_hash: str
    runtime_scope: str
    model_slot: str
    purpose: RuntimePurpose
    runtime_lineage: RuntimeModelLineage
    selected_at: datetime
    idempotency_key: str
    preselection_rejection_codes: tuple[str, ...] = ()
    schema_version: str = "model-selection-request-v1"

    def __post_init__(self) -> None:
        if self.schema_version != "model-selection-request-v1":
            raise ValueError("unsupported Model Selection Request schema")
        require_sha256("request_hash", self.request_hash)
        require_text("runtime_scope", self.runtime_scope)
        require_text("model_slot", self.model_slot)
        require_text("idempotency_key", self.idempotency_key)
        _ordered_text(
            "preselection_rejection_codes",
            self.preselection_rejection_codes,
        )
        _aware("selected_at", self.selected_at)
        if canonical_hash(self.semantic_payload()) != self.request_hash:
            raise ValueError("Model Selection Request hash mismatch")

    @classmethod
    def create(cls, **values: Any) -> ModelSelectionRequest:
        normalized = {"preselection_rejection_codes": (), **values}
        normalized["preselection_rejection_codes"] = tuple(
            sorted(set(normalized["preselection_rejection_codes"]))
        )
        digest = canonical_hash(_selection_request_payload(**normalized))
        return cls(request_hash=digest, **normalized)

    def semantic_payload(self) -> dict[str, Any]:
        return _selection_request_payload(
            runtime_scope=self.runtime_scope,
            model_slot=self.model_slot,
            purpose=self.purpose,
            runtime_lineage=self.runtime_lineage,
            selected_at=self.selected_at,
            idempotency_key=self.idempotency_key,
            preselection_rejection_codes=self.preselection_rejection_codes,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {"request_hash": self.request_hash, **self.semantic_payload()}

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> ModelSelectionRequest:
        rebuilt = cls.create(
            runtime_scope=_string(payload["runtime_scope"]),
            model_slot=_string(payload["model_slot"]),
            purpose=RuntimePurpose(_string(payload["purpose"])),
            runtime_lineage=RuntimeModelLineage.from_canonical_dict(
                _mapping(payload["runtime_lineage"])
            ),
            selected_at=_instant(payload["selected_at"]),
            idempotency_key=_string(payload["idempotency_key"]),
            preselection_rejection_codes=tuple(
                _string(item)
                for item in _sequence(
                    payload.get("preselection_rejection_codes", ())
                )
            ),
        )
        if rebuilt.request_hash != payload.get("request_hash"):
            raise ValueError("Model Selection Request stored identity mismatch")
        return rebuilt


@dataclass(frozen=True, slots=True)
class ArtifactLineageReference:
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
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> ArtifactLineageReference:
        _fields(
            payload,
            {"reference_kind", "artifact_id", "content_hash"},
            "ArtifactLineageReference",
        )
        return cls(
            reference_kind=_string(payload["reference_kind"]),
            artifact_id=ArtifactId(_string(payload["artifact_id"])),
            content_hash=_string(payload["content_hash"]),
        )


@dataclass(frozen=True, slots=True)
class ModelVersionLineage:
    lineage_id: ArtifactId
    lineage_hash: str
    model_id: ModelId
    model_version: str
    definition_hash: str
    target_id: TargetId
    universe_contract_id: UniverseId
    feature_definition_ids: tuple[FeatureDefinitionId, ...]
    model_parameter_hash: str
    configuration: ArtifactLineageReference
    implementation_ref: str
    code_revision: str
    code_hash: str
    validation_protocol_refs: tuple[ArtifactLineageReference, ...]
    supported_data_eligibilities: tuple[DataEligibility, ...]
    created_at: datetime
    schema_version: str = "model-version-lineage-v1"

    def __post_init__(self) -> None:
        if self.schema_version != "model-version-lineage-v1":
            raise ValueError("unsupported Model Version Lineage schema")
        for label, value in (
            ("model_version", self.model_version),
            ("implementation_ref", self.implementation_ref),
            ("model_parameter_hash", self.model_parameter_hash),
            ("code_revision", self.code_revision),
        ):
            require_text(label, value)
        _definition_hash(self.definition_hash)
        require_sha256("lineage_hash", self.lineage_hash)
        require_sha256("code_hash", self.code_hash)
        _ordered_ids("feature_definition_ids", self.feature_definition_ids)
        _ordered_references(
            "validation_protocol_refs", self.validation_protocol_refs
        )
        if not self.validation_protocol_refs:
            raise ValueError("validation_protocol_refs must not be empty")
        if self.supported_data_eligibilities != tuple(
            sorted(set(self.supported_data_eligibilities), key=lambda item: item.value)
        ):
            raise ValueError(
                "supported_data_eligibilities must be sorted and unique"
            )
        if not self.supported_data_eligibilities:
            raise ValueError("supported_data_eligibilities must not be empty")
        _aware("created_at", self.created_at)
        if canonical_hash(self.semantic_payload()) != self.lineage_hash:
            raise ValueError("Model Version Lineage hash mismatch")
        if self.lineage_id != _content_id("model-version-lineage", self.lineage_hash):
            raise ValueError("Model Version Lineage identity mismatch")

    @classmethod
    def create(cls, **values: Any) -> ModelVersionLineage:
        normalized = dict(values)
        normalized["feature_definition_ids"] = tuple(
            sorted(set(values["feature_definition_ids"]), key=str)
        )
        normalized["validation_protocol_refs"] = _sort_references(
            values["validation_protocol_refs"]
        )
        normalized["supported_data_eligibilities"] = tuple(
            sorted(set(values["supported_data_eligibilities"]), key=lambda item: item.value)
        )
        digest = canonical_hash(_model_version_lineage_payload(**normalized))
        return cls(
            lineage_id=_content_id("model-version-lineage", digest),
            lineage_hash=digest,
            **normalized,
        )

    def semantic_payload(self) -> dict[str, Any]:
        return _model_version_lineage_payload(
            model_id=self.model_id,
            model_version=self.model_version,
            definition_hash=self.definition_hash,
            target_id=self.target_id,
            universe_contract_id=self.universe_contract_id,
            feature_definition_ids=self.feature_definition_ids,
            model_parameter_hash=self.model_parameter_hash,
            configuration=self.configuration,
            implementation_ref=self.implementation_ref,
            code_revision=self.code_revision,
            code_hash=self.code_hash,
            validation_protocol_refs=self.validation_protocol_refs,
            supported_data_eligibilities=self.supported_data_eligibilities,
            created_at=self.created_at,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "lineage_id": str(self.lineage_id),
            "lineage_hash": self.lineage_hash,
            **self.semantic_payload(),
        }

    def validate_definition(self, definition: ModelDefinition) -> None:
        mismatches = []
        for label, lineage_value, definition_value in (
            ("model", self.model_id, definition.model_id),
            ("version", self.model_version, definition.version),
            ("definition", self.definition_hash, definition.definition_hash),
            ("target", self.target_id, definition.target_id),
            ("universe_contract", self.universe_contract_id, definition.universe_id),
            ("feature", self.feature_definition_ids, definition.feature_ids),
            ("model_parameter", self.model_parameter_hash, definition.parameter_hash),
            ("implementation", self.implementation_ref, definition.implementation_ref),
            (
                "data_eligibility",
                self.supported_data_eligibilities,
                definition.supported_data_eligibilities,
            ),
        ):
            if lineage_value != definition_value:
                mismatches.append(label)
        if mismatches:
            raise ValueError(
                "Model Version Lineage/Definition mismatch: "
                + ",".join(mismatches)
            )

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> ModelVersionLineage:
        expected = {
            "schema_version",
            "lineage_id",
            "lineage_hash",
            "model_id",
            "model_version",
            "definition_hash",
            "target_id",
            "universe_contract_id",
            "feature_definition_ids",
            "model_parameter_hash",
            "configuration",
            "implementation_ref",
            "code_revision",
            "code_hash",
            "validation_protocol_refs",
            "supported_data_eligibilities",
            "created_at",
        }
        _fields(payload, expected, "ModelVersionLineage")
        return cls(
            lineage_id=ArtifactId(_string(payload["lineage_id"])),
            lineage_hash=_string(payload["lineage_hash"]),
            model_id=ModelId(_string(payload["model_id"])),
            model_version=_string(payload["model_version"]),
            definition_hash=_string(payload["definition_hash"]),
            target_id=TargetId(_string(payload["target_id"])),
            universe_contract_id=UniverseId(
                _string(payload["universe_contract_id"])
            ),
            feature_definition_ids=tuple(
                FeatureDefinitionId(_string(item))
                for item in _sequence(payload["feature_definition_ids"])
            ),
            model_parameter_hash=_string(payload["model_parameter_hash"]),
            configuration=ArtifactLineageReference.from_canonical_dict(
                _mapping(payload["configuration"])
            ),
            implementation_ref=_string(payload["implementation_ref"]),
            code_revision=_string(payload["code_revision"]),
            code_hash=_string(payload["code_hash"]),
            validation_protocol_refs=tuple(
                ArtifactLineageReference.from_canonical_dict(_mapping(item))
                for item in _sequence(payload["validation_protocol_refs"])
            ),
            supported_data_eligibilities=tuple(
                DataEligibility(_string(item))
                for item in _sequence(payload["supported_data_eligibilities"])
            ),
            created_at=_instant(payload["created_at"]),
            schema_version=_string(payload["schema_version"]),
        )


@dataclass(frozen=True, slots=True)
class RuntimeModelLineage:
    runtime_lineage_id: ArtifactId
    runtime_lineage_hash: str
    model_id: ModelId
    definition_hash: str
    dataset: ArtifactLineageReference
    universe_id: UniverseId
    feature_definition_ids: tuple[FeatureDefinitionId, ...]
    feature_materializations: tuple[ArtifactLineageReference, ...]
    configuration: ArtifactLineageReference
    code_revision: str
    code_hash: str
    validation_protocol_refs: tuple[ArtifactLineageReference, ...]
    data_eligibility: DataEligibility
    schema_version: str = "runtime-model-lineage-v1"

    def __post_init__(self) -> None:
        if self.schema_version != "runtime-model-lineage-v1":
            raise ValueError("unsupported Runtime Model Lineage schema")
        _definition_hash(self.definition_hash)
        require_sha256("runtime_lineage_hash", self.runtime_lineage_hash)
        require_sha256("code_hash", self.code_hash)
        require_text("code_revision", self.code_revision)
        _ordered_ids("feature_definition_ids", self.feature_definition_ids)
        if len(self.feature_definition_ids) != len(
            self.feature_materializations
        ) or len(set(self.feature_materializations)) != len(
            self.feature_materializations
        ):
            raise ValueError(
                "feature definitions/materializations must be paired and unique"
            )
        _ordered_references(
            "validation_protocol_refs", self.validation_protocol_refs
        )
        if canonical_hash(self.semantic_payload()) != self.runtime_lineage_hash:
            raise ValueError("Runtime Model Lineage hash mismatch")
        if self.runtime_lineage_id != _content_id(
            "runtime-model-lineage", self.runtime_lineage_hash
        ):
            raise ValueError("Runtime Model Lineage identity mismatch")

    @classmethod
    def create(cls, **values: Any) -> RuntimeModelLineage:
        normalized = dict(values)
        pairs = tuple(
            sorted(
                zip(
                    values["feature_definition_ids"],
                    values["feature_materializations"],
                    strict=True,
                ),
                key=lambda item: str(item[0]),
            )
        )
        if len({item[0] for item in pairs}) != len(pairs) or len(
            {item[1] for item in pairs}
        ) != len(pairs):
            raise ValueError(
                "feature definitions/materializations must be paired and unique"
            )
        normalized["feature_definition_ids"] = tuple(item[0] for item in pairs)
        normalized["feature_materializations"] = tuple(item[1] for item in pairs)
        normalized["validation_protocol_refs"] = _sort_references(
            values["validation_protocol_refs"]
        )
        digest = canonical_hash(_runtime_model_lineage_payload(**normalized))
        return cls(
            runtime_lineage_id=_content_id("runtime-model-lineage", digest),
            runtime_lineage_hash=digest,
            **normalized,
        )

    def semantic_payload(self) -> dict[str, Any]:
        return _runtime_model_lineage_payload(
            model_id=self.model_id,
            definition_hash=self.definition_hash,
            dataset=self.dataset,
            universe_id=self.universe_id,
            feature_definition_ids=self.feature_definition_ids,
            feature_materializations=self.feature_materializations,
            configuration=self.configuration,
            code_revision=self.code_revision,
            code_hash=self.code_hash,
            validation_protocol_refs=self.validation_protocol_refs,
            data_eligibility=self.data_eligibility,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "runtime_lineage_id": str(self.runtime_lineage_id),
            "runtime_lineage_hash": self.runtime_lineage_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> RuntimeModelLineage:
        expected = {
            "schema_version",
            "runtime_lineage_id",
            "runtime_lineage_hash",
            "model_id",
            "definition_hash",
            "dataset",
            "universe_id",
            "feature_definition_ids",
            "feature_materializations",
            "configuration",
            "code_revision",
            "code_hash",
            "validation_protocol_refs",
            "data_eligibility",
        }
        _fields(payload, expected, "RuntimeModelLineage")
        return cls(
            runtime_lineage_id=ArtifactId(
                _string(payload["runtime_lineage_id"])
            ),
            runtime_lineage_hash=_string(payload["runtime_lineage_hash"]),
            model_id=ModelId(_string(payload["model_id"])),
            definition_hash=_string(payload["definition_hash"]),
            dataset=ArtifactLineageReference.from_canonical_dict(
                _mapping(payload["dataset"])
            ),
            universe_id=UniverseId(_string(payload["universe_id"])),
            feature_definition_ids=tuple(
                FeatureDefinitionId(_string(item))
                for item in _sequence(payload["feature_definition_ids"])
            ),
            feature_materializations=tuple(
                ArtifactLineageReference.from_canonical_dict(_mapping(item))
                for item in _sequence(payload["feature_materializations"])
            ),
            configuration=ArtifactLineageReference.from_canonical_dict(
                _mapping(payload["configuration"])
            ),
            code_revision=_string(payload["code_revision"]),
            code_hash=_string(payload["code_hash"]),
            validation_protocol_refs=tuple(
                ArtifactLineageReference.from_canonical_dict(_mapping(item))
                for item in _sequence(payload["validation_protocol_refs"])
            ),
            data_eligibility=DataEligibility(_string(payload["data_eligibility"])),
            schema_version=_string(payload["schema_version"]),
        )

    def validate_against(self, lineage: ModelVersionLineage) -> None:
        mismatches = []
        for label, runtime_value, registered_value in (
            ("model", self.model_id, lineage.model_id),
            ("definition", self.definition_hash, lineage.definition_hash),
            ("feature", self.feature_definition_ids, lineage.feature_definition_ids),
            ("configuration", self.configuration, lineage.configuration),
            ("code_revision", self.code_revision, lineage.code_revision),
            ("code_hash", self.code_hash, lineage.code_hash),
            (
                "validation_protocol",
                self.validation_protocol_refs,
                lineage.validation_protocol_refs,
            ),
        ):
            if runtime_value != registered_value:
                mismatches.append(label)
        if self.data_eligibility not in lineage.supported_data_eligibilities:
            mismatches.append("data_eligibility")
        if mismatches:
            raise ValueError(
                "Runtime model lineage mismatch: " + ",".join(mismatches)
            )


@dataclass(frozen=True, slots=True)
class ModelQualificationEvidence:
    evidence_id: ArtifactId
    evidence_hash: str
    model_id: ModelId
    definition_hash: str
    lineage_id: ArtifactId
    lineage_hash: str
    evidence_kind: QualificationEvidenceKind
    outcome: QualificationEvidenceOutcome
    evidence: ArtifactLineageReference
    validation_protocol_ref: ArtifactLineageReference
    available_at: datetime
    recorded_at: datetime
    actor: str
    reason: str
    schema_version: str = "model-qualification-evidence-v1"

    def __post_init__(self) -> None:
        if self.schema_version != "model-qualification-evidence-v1":
            raise ValueError("unsupported Model Qualification Evidence schema")
        _definition_hash(self.definition_hash)
        require_sha256("lineage_hash", self.lineage_hash)
        require_sha256("evidence_hash", self.evidence_hash)
        _aware("available_at", self.available_at)
        _aware("recorded_at", self.recorded_at)
        if self.available_at > self.recorded_at:
            raise ValueError("qualification evidence cannot be recorded before available")
        require_text("actor", self.actor)
        require_text("reason", self.reason)
        if canonical_hash(self.semantic_payload()) != self.evidence_hash:
            raise ValueError("Model Qualification Evidence hash mismatch")
        if self.evidence_id != _content_id(
            "model-qualification-evidence", self.evidence_hash
        ):
            raise ValueError("Model Qualification Evidence identity mismatch")

    @classmethod
    def create(cls, **values: Any) -> ModelQualificationEvidence:
        digest = canonical_hash(_qualification_evidence_payload(**values))
        return cls(
            evidence_id=_content_id("model-qualification-evidence", digest),
            evidence_hash=digest,
            **values,
        )

    def semantic_payload(self) -> dict[str, Any]:
        return _qualification_evidence_payload(
            model_id=self.model_id,
            definition_hash=self.definition_hash,
            lineage_id=self.lineage_id,
            lineage_hash=self.lineage_hash,
            evidence_kind=self.evidence_kind,
            outcome=self.outcome,
            evidence=self.evidence,
            validation_protocol_ref=self.validation_protocol_ref,
            available_at=self.available_at,
            recorded_at=self.recorded_at,
            actor=self.actor,
            reason=self.reason,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": str(self.evidence_id),
            "evidence_hash": self.evidence_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> ModelQualificationEvidence:
        expected = {
            "schema_version",
            "evidence_id",
            "evidence_hash",
            "model_id",
            "definition_hash",
            "lineage_id",
            "lineage_hash",
            "evidence_kind",
            "outcome",
            "evidence",
            "validation_protocol_ref",
            "available_at",
            "recorded_at",
            "actor",
            "reason",
        }
        _fields(payload, expected, "ModelQualificationEvidence")
        return cls(
            evidence_id=ArtifactId(_string(payload["evidence_id"])),
            evidence_hash=_string(payload["evidence_hash"]),
            model_id=ModelId(_string(payload["model_id"])),
            definition_hash=_string(payload["definition_hash"]),
            lineage_id=ArtifactId(_string(payload["lineage_id"])),
            lineage_hash=_string(payload["lineage_hash"]),
            evidence_kind=QualificationEvidenceKind(
                _string(payload["evidence_kind"])
            ),
            outcome=QualificationEvidenceOutcome(_string(payload["outcome"])),
            evidence=ArtifactLineageReference.from_canonical_dict(
                _mapping(payload["evidence"])
            ),
            validation_protocol_ref=ArtifactLineageReference.from_canonical_dict(
                _mapping(payload["validation_protocol_ref"])
            ),
            available_at=_instant(payload["available_at"]),
            recorded_at=_instant(payload["recorded_at"]),
            actor=_string(payload["actor"]),
            reason=_string(payload["reason"]),
            schema_version=_string(payload["schema_version"]),
        )


@dataclass(frozen=True, slots=True)
class ModelGovernancePolicy:
    policy_id: ArtifactId
    policy_hash: str
    name: str
    version: str
    purpose: RuntimePurpose
    allowed_lifecycle_statuses: tuple[ModelLifecycleStatus, ...]
    required_evidence_kinds: tuple[QualificationEvidenceKind, ...]
    allowed_data_eligibilities: tuple[DataEligibility, ...]
    production_authorization: bool
    schema_version: str = "model-governance-policy-v1"

    def __post_init__(self) -> None:
        if self.schema_version != "model-governance-policy-v1":
            raise ValueError("unsupported Model Governance Policy schema")
        require_text("name", self.name)
        require_text("version", self.version)
        require_sha256("policy_hash", self.policy_hash)
        for label, values in (
            ("allowed_lifecycle_statuses", self.allowed_lifecycle_statuses),
            ("required_evidence_kinds", self.required_evidence_kinds),
            ("allowed_data_eligibilities", self.allowed_data_eligibilities),
        ):
            if not values or values != tuple(
                sorted(set(values), key=lambda item: getattr(item, "value"))
            ):
                raise ValueError(f"{label} must be non-empty, sorted and unique")
        if self.production_authorization != (
            self.purpose is RuntimePurpose.PRODUCTION_DECISION
        ):
            raise ValueError("Production authorization must match policy purpose")
        if set(self.allowed_lifecycle_statuses).intersection(
            _TERMINAL_RUNTIME_LIFECYCLES
        ):
            raise ValueError("Suspended or retired Models cannot be Runtime-qualified")
        if self.purpose is RuntimePurpose.PRODUCTION_DECISION:
            if self.allowed_lifecycle_statuses != (ModelLifecycleStatus.ACTIVE,):
                raise ValueError("Production policy requires ACTIVE lifecycle")
            if not PRODUCTION_DECISION_EVIDENCE_FLOOR.issubset(
                self.required_evidence_kinds
            ):
                raise ValueError(
                    "Production policy lacks the mandatory evidence floor"
                )
            if self.allowed_data_eligibilities != (
                DataEligibility.FORMAL_RESEARCH,
            ):
                raise ValueError(
                    "Production policy requires FORMAL_RESEARCH data eligibility"
                )
        if canonical_hash(self.semantic_payload()) != self.policy_hash:
            raise ValueError("Model Governance Policy hash mismatch")
        if self.policy_id != _content_id("model-governance-policy", self.policy_hash):
            raise ValueError("Model Governance Policy identity mismatch")

    @classmethod
    def create(cls, **values: Any) -> ModelGovernancePolicy:
        normalized = dict(values)
        for label in (
            "allowed_lifecycle_statuses",
            "required_evidence_kinds",
            "allowed_data_eligibilities",
        ):
            normalized[label] = tuple(
                sorted(set(values[label]), key=lambda item: item.value)
            )
        digest = canonical_hash(_governance_policy_payload(**normalized))
        return cls(
            policy_id=_content_id("model-governance-policy", digest),
            policy_hash=digest,
            **normalized,
        )

    def semantic_payload(self) -> dict[str, Any]:
        return _governance_policy_payload(
            name=self.name,
            version=self.version,
            purpose=self.purpose,
            allowed_lifecycle_statuses=self.allowed_lifecycle_statuses,
            required_evidence_kinds=self.required_evidence_kinds,
            allowed_data_eligibilities=self.allowed_data_eligibilities,
            production_authorization=self.production_authorization,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "policy_id": str(self.policy_id),
            "policy_hash": self.policy_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> ModelGovernancePolicy:
        expected = {
            "schema_version",
            "policy_id",
            "policy_hash",
            "name",
            "version",
            "purpose",
            "allowed_lifecycle_statuses",
            "required_evidence_kinds",
            "allowed_data_eligibilities",
            "production_authorization",
        }
        _fields(payload, expected, "ModelGovernancePolicy")
        return cls(
            policy_id=ArtifactId(_string(payload["policy_id"])),
            policy_hash=_string(payload["policy_hash"]),
            name=_string(payload["name"]),
            version=_string(payload["version"]),
            purpose=RuntimePurpose(_string(payload["purpose"])),
            allowed_lifecycle_statuses=tuple(
                ModelLifecycleStatus(_string(item))
                for item in _sequence(payload["allowed_lifecycle_statuses"])
            ),
            required_evidence_kinds=tuple(
                QualificationEvidenceKind(_string(item))
                for item in _sequence(payload["required_evidence_kinds"])
            ),
            allowed_data_eligibilities=tuple(
                DataEligibility(_string(item))
                for item in _sequence(payload["allowed_data_eligibilities"])
            ),
            production_authorization=_boolean(payload["production_authorization"]),
            schema_version=_string(payload["schema_version"]),
        )


@dataclass(frozen=True, slots=True)
class ModelQualificationDecision:
    decision_id: ArtifactId
    decision_hash: str
    model_id: ModelId
    definition_hash: str
    lineage_id: ArtifactId
    lineage_hash: str
    policy_id: ArtifactId
    policy_hash: str
    purpose: RuntimePurpose
    status: QualificationStatus
    evidence_ids: tuple[ArtifactId, ...]
    evidence_hashes: tuple[str, ...]
    reason_codes: tuple[str, ...]
    production_authorized: bool
    decided_at: datetime
    actor: str
    reason: str
    approval_ref: str | None
    governance_revision: int
    schema_version: str = "model-qualification-decision-v1"

    def __post_init__(self) -> None:
        if self.schema_version != "model-qualification-decision-v1":
            raise ValueError("unsupported Model Qualification Decision schema")
        _definition_hash(self.definition_hash)
        require_sha256("lineage_hash", self.lineage_hash)
        require_sha256("policy_hash", self.policy_hash)
        require_sha256("decision_hash", self.decision_hash)
        _ordered_ids("evidence_ids", self.evidence_ids)
        for digest in self.evidence_hashes:
            require_sha256("evidence_hash", digest)
        if len(self.evidence_ids) != len(self.evidence_hashes):
            raise ValueError("qualification evidence identity/hash mismatch")
        _ordered_text("reason_codes", self.reason_codes)
        _aware("decided_at", self.decided_at)
        require_text("actor", self.actor)
        require_text("reason", self.reason)
        if self.approval_ref is not None:
            require_text("approval_ref", self.approval_ref)
        _positive_revision(self.governance_revision)
        if self.production_authorized and (
            self.status is not QualificationStatus.QUALIFIED
            or self.purpose is not RuntimePurpose.PRODUCTION_DECISION
            or self.approval_ref is None
        ):
            raise ValueError("invalid Production qualification decision")
        if canonical_hash(self.semantic_payload()) != self.decision_hash:
            raise ValueError("Model Qualification Decision hash mismatch")
        if self.decision_id != _content_id(
            "model-qualification-decision", self.decision_hash
        ):
            raise ValueError("Model Qualification Decision identity mismatch")

    @classmethod
    def create(cls, **values: Any) -> ModelQualificationDecision:
        normalized = dict(values)
        pairs = sorted(
            zip(values["evidence_ids"], values["evidence_hashes"], strict=True),
            key=lambda pair: str(pair[0]),
        )
        normalized["evidence_ids"] = tuple(pair[0] for pair in pairs)
        normalized["evidence_hashes"] = tuple(pair[1] for pair in pairs)
        normalized["reason_codes"] = tuple(sorted(set(values["reason_codes"])))
        digest = canonical_hash(_qualification_decision_payload(**normalized))
        return cls(
            decision_id=_content_id("model-qualification-decision", digest),
            decision_hash=digest,
            **normalized,
        )

    def semantic_payload(self) -> dict[str, Any]:
        return _qualification_decision_payload(
            model_id=self.model_id,
            definition_hash=self.definition_hash,
            lineage_id=self.lineage_id,
            lineage_hash=self.lineage_hash,
            policy_id=self.policy_id,
            policy_hash=self.policy_hash,
            purpose=self.purpose,
            status=self.status,
            evidence_ids=self.evidence_ids,
            evidence_hashes=self.evidence_hashes,
            reason_codes=self.reason_codes,
            production_authorized=self.production_authorized,
            decided_at=self.decided_at,
            actor=self.actor,
            reason=self.reason,
            approval_ref=self.approval_ref,
            governance_revision=self.governance_revision,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "decision_id": str(self.decision_id),
            "decision_hash": self.decision_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> ModelQualificationDecision:
        rebuilt = cls.create(
            model_id=ModelId(_string(payload["model_id"])),
            definition_hash=_string(payload["definition_hash"]),
            lineage_id=ArtifactId(_string(payload["lineage_id"])),
            lineage_hash=_string(payload["lineage_hash"]),
            policy_id=ArtifactId(_string(payload["policy_id"])),
            policy_hash=_string(payload["policy_hash"]),
            purpose=RuntimePurpose(_string(payload["purpose"])),
            status=QualificationStatus(_string(payload["status"])),
            evidence_ids=tuple(
                ArtifactId(_string(item))
                for item in _sequence(payload["evidence_ids"])
            ),
            evidence_hashes=tuple(
                _string(item) for item in _sequence(payload["evidence_hashes"])
            ),
            reason_codes=tuple(
                _string(item) for item in _sequence(payload["reason_codes"])
            ),
            production_authorized=_boolean(payload["production_authorized"]),
            decided_at=_instant(payload["decided_at"]),
            actor=_string(payload["actor"]),
            reason=_string(payload["reason"]),
            approval_ref=_optional_string(payload["approval_ref"]),
            governance_revision=_integer(payload["governance_revision"]),
        )
        if (
            str(rebuilt.decision_id) != payload.get("decision_id")
            or rebuilt.decision_hash != payload.get("decision_hash")
        ):
            raise ValueError("Model Qualification Decision stored identity mismatch")
        return rebuilt


@dataclass(frozen=True, slots=True)
class ModelRuntimeAssignment:
    assignment_id: ArtifactId
    assignment_hash: str
    runtime_scope: str
    model_slot: str
    purpose: RuntimePurpose
    lane: AssignmentLane
    status: AssignmentStatus
    model_id: ModelId
    definition_hash: str
    policy_id: ArtifactId
    policy_hash: str
    effective_at: datetime
    actor: str
    reason: str
    approval_ref: str
    governance_revision: int
    version: int = 0
    supersedes_assignment_id: ArtifactId | None = None
    schema_version: str = "model-runtime-assignment-v1"

    def __post_init__(self) -> None:
        if self.schema_version != "model-runtime-assignment-v1":
            raise ValueError("unsupported Model Runtime Assignment schema")
        for label, value in (
            ("runtime_scope", self.runtime_scope),
            ("model_slot", self.model_slot),
            ("actor", self.actor),
            ("reason", self.reason),
            ("approval_ref", self.approval_ref),
        ):
            require_text(label, value)
        _definition_hash(self.definition_hash)
        require_sha256("policy_hash", self.policy_hash)
        require_sha256("assignment_hash", self.assignment_hash)
        _aware("effective_at", self.effective_at)
        _positive_revision(self.governance_revision)
        if self.version < 0:
            raise ValueError("assignment version must be non-negative")
        if canonical_hash(self.semantic_payload()) != self.assignment_hash:
            raise ValueError("Model Runtime Assignment hash mismatch")
        if self.assignment_id != _content_id(
            "model-runtime-assignment", self.assignment_hash
        ):
            raise ValueError("Model Runtime Assignment identity mismatch")

    @classmethod
    def create(cls, **values: Any) -> ModelRuntimeAssignment:
        normalized = {"status": AssignmentStatus.ACTIVE, **values}
        digest = canonical_hash(_runtime_assignment_payload(**normalized))
        return cls(
            assignment_id=_content_id("model-runtime-assignment", digest),
            assignment_hash=digest,
            **normalized,
        )

    def semantic_payload(self) -> dict[str, Any]:
        return _runtime_assignment_payload(
            runtime_scope=self.runtime_scope,
            model_slot=self.model_slot,
            purpose=self.purpose,
            lane=self.lane,
            status=self.status,
            model_id=self.model_id,
            definition_hash=self.definition_hash,
            policy_id=self.policy_id,
            policy_hash=self.policy_hash,
            effective_at=self.effective_at,
            actor=self.actor,
            reason=self.reason,
            approval_ref=self.approval_ref,
            governance_revision=self.governance_revision,
            version=self.version,
            supersedes_assignment_id=self.supersedes_assignment_id,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "assignment_id": str(self.assignment_id),
            "assignment_hash": self.assignment_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> ModelRuntimeAssignment:
        rebuilt = cls.create(
            runtime_scope=_string(payload["runtime_scope"]),
            model_slot=_string(payload["model_slot"]),
            purpose=RuntimePurpose(_string(payload["purpose"])),
            lane=AssignmentLane(_string(payload["lane"])),
            status=AssignmentStatus(_string(payload["status"])),
            model_id=ModelId(_string(payload["model_id"])),
            definition_hash=_string(payload["definition_hash"]),
            policy_id=ArtifactId(_string(payload["policy_id"])),
            policy_hash=_string(payload["policy_hash"]),
            effective_at=_instant(payload["effective_at"]),
            actor=_string(payload["actor"]),
            reason=_string(payload["reason"]),
            approval_ref=_string(payload["approval_ref"]),
            governance_revision=_integer(payload["governance_revision"]),
            version=_integer(payload["version"]),
            supersedes_assignment_id=_optional_artifact_id(
                payload["supersedes_assignment_id"]
            ),
        )
        if (
            str(rebuilt.assignment_id) != payload.get("assignment_id")
            or rebuilt.assignment_hash != payload.get("assignment_hash")
        ):
            raise ValueError("Model Runtime Assignment stored identity mismatch")
        return rebuilt


@dataclass(frozen=True, slots=True)
class ModelSelectionReceipt:
    receipt_id: ArtifactId
    receipt_hash: str
    request_hash: str
    runtime_scope: str
    model_slot: str
    purpose: RuntimePurpose
    status: SelectionStatus
    governance_revision: int
    policy_id: ArtifactId | None
    policy_hash: str | None
    champion_assignment_id: ArtifactId | None
    champion_assignment_hash: str | None
    champion_assignment_version: int | None
    selected_registry_version: int | None
    selected_model_id: ModelId | None
    selected_definition_hash: str | None
    challenger_model_ids: tuple[ModelId, ...]
    qualification_decision_id: ArtifactId | None
    qualification_decision_hash: str | None
    runtime_lineage_hash: str
    evidence_ids: tuple[ArtifactId, ...]
    reason_codes: tuple[str, ...]
    production_authorized: bool
    selected_at: datetime
    schema_version: str = "model-selection-receipt-v1"

    def __post_init__(self) -> None:
        if self.schema_version != "model-selection-receipt-v1":
            raise ValueError("unsupported Model Selection Receipt schema")
        require_sha256("receipt_hash", self.receipt_hash)
        require_sha256("request_hash", self.request_hash)
        require_sha256("runtime_lineage_hash", self.runtime_lineage_hash)
        require_text("runtime_scope", self.runtime_scope)
        require_text("model_slot", self.model_slot)
        if self.governance_revision < 0:
            raise ValueError("governance_revision must be non-negative")
        _ordered_ids("challenger_model_ids", self.challenger_model_ids)
        _ordered_ids("evidence_ids", self.evidence_ids)
        _ordered_text("reason_codes", self.reason_codes)
        _aware("selected_at", self.selected_at)
        selected_values = (
            self.policy_id,
            self.policy_hash,
            self.champion_assignment_id,
            self.champion_assignment_hash,
            self.champion_assignment_version,
            self.selected_registry_version,
            self.selected_model_id,
            self.selected_definition_hash,
            self.qualification_decision_id,
            self.qualification_decision_hash,
        )
        if self.status is SelectionStatus.SELECTED and any(
            value is None for value in selected_values
        ):
            raise ValueError("selected receipt requires complete governance authority")
        if self.status is SelectionStatus.REJECTED and self.production_authorized:
            raise ValueError("rejected selection cannot authorize Production")
        for digest in (
            self.policy_hash,
            self.champion_assignment_hash,
            self.qualification_decision_hash,
        ):
            if digest is not None:
                require_sha256("selection authority hash", digest)
        if self.selected_definition_hash is not None:
            _definition_hash(self.selected_definition_hash)
        if canonical_hash(self.semantic_payload()) != self.receipt_hash:
            raise ValueError("Model Selection Receipt hash mismatch")
        if self.receipt_id != _content_id("model-selection-receipt", self.receipt_hash):
            raise ValueError("Model Selection Receipt identity mismatch")

    @classmethod
    def accepted(
        cls,
        *,
        request_hash: str,
        runtime_scope: str,
        model_slot: str,
        purpose: RuntimePurpose,
        governance_revision: int,
        policy: ModelGovernancePolicy,
        champion: ModelRuntimeAssignment,
        challengers: tuple[ModelRuntimeAssignment, ...],
        qualification_decision_id: ArtifactId,
        qualification_decision_hash: str,
        selected_registry_version: int,
        runtime_lineage_hash: str,
        evidence_ids: tuple[ArtifactId, ...],
        selected_at: datetime,
        production_authorized: bool = False,
    ) -> ModelSelectionReceipt:
        if champion.lane is not AssignmentLane.CHAMPION:
            raise ValueError("accepted selection requires Champion assignment")
        if any(item.lane is not AssignmentLane.CHALLENGER for item in challengers):
            raise ValueError("selection challengers require Challenger assignments")
        return cls._create(
            request_hash=request_hash,
            runtime_scope=runtime_scope,
            model_slot=model_slot,
            purpose=purpose,
            status=SelectionStatus.SELECTED,
            governance_revision=governance_revision,
            policy_id=policy.policy_id,
            policy_hash=policy.policy_hash,
            champion_assignment_id=champion.assignment_id,
            champion_assignment_hash=champion.assignment_hash,
            champion_assignment_version=champion.version,
            selected_registry_version=selected_registry_version,
            selected_model_id=champion.model_id,
            selected_definition_hash=champion.definition_hash,
            challenger_model_ids=tuple(
                sorted((item.model_id for item in challengers), key=str)
            ),
            qualification_decision_id=qualification_decision_id,
            qualification_decision_hash=qualification_decision_hash,
            runtime_lineage_hash=runtime_lineage_hash,
            evidence_ids=tuple(sorted(set(evidence_ids), key=str)),
            reason_codes=("CHAMPION_SELECTED",),
            production_authorized=production_authorized,
            selected_at=selected_at,
        )

    @classmethod
    def rejected(
        cls,
        *,
        request_hash: str,
        runtime_scope: str,
        model_slot: str,
        purpose: RuntimePurpose,
        governance_revision: int,
        runtime_lineage_hash: str,
        reason_codes: tuple[str, ...],
        selected_at: datetime,
        policy: ModelGovernancePolicy | None = None,
        champion: ModelRuntimeAssignment | None = None,
        challengers: tuple[ModelRuntimeAssignment, ...] = (),
    ) -> ModelSelectionReceipt:
        if not reason_codes:
            raise ValueError("rejected selection requires reason codes")
        return cls._create(
            request_hash=request_hash,
            runtime_scope=runtime_scope,
            model_slot=model_slot,
            purpose=purpose,
            status=SelectionStatus.REJECTED,
            governance_revision=governance_revision,
            policy_id=None if policy is None else policy.policy_id,
            policy_hash=None if policy is None else policy.policy_hash,
            champion_assignment_id=(
                None if champion is None else champion.assignment_id
            ),
            champion_assignment_hash=(
                None if champion is None else champion.assignment_hash
            ),
            champion_assignment_version=(
                None if champion is None else champion.version
            ),
            selected_registry_version=None,
            selected_model_id=None,
            selected_definition_hash=None,
            challenger_model_ids=tuple(
                sorted((item.model_id for item in challengers), key=str)
            ),
            qualification_decision_id=None,
            qualification_decision_hash=None,
            runtime_lineage_hash=runtime_lineage_hash,
            evidence_ids=(),
            reason_codes=tuple(sorted(set(reason_codes))),
            production_authorized=False,
            selected_at=selected_at,
        )

    @classmethod
    def _create(cls, **values: Any) -> ModelSelectionReceipt:
        digest = canonical_hash(_selection_receipt_payload(**values))
        return cls(
            receipt_id=_content_id("model-selection-receipt", digest),
            receipt_hash=digest,
            **values,
        )

    def semantic_payload(self) -> dict[str, Any]:
        return _selection_receipt_payload(
            request_hash=self.request_hash,
            runtime_scope=self.runtime_scope,
            model_slot=self.model_slot,
            purpose=self.purpose,
            status=self.status,
            governance_revision=self.governance_revision,
            policy_id=self.policy_id,
            policy_hash=self.policy_hash,
            champion_assignment_id=self.champion_assignment_id,
            champion_assignment_hash=self.champion_assignment_hash,
            champion_assignment_version=self.champion_assignment_version,
            selected_registry_version=self.selected_registry_version,
            selected_model_id=self.selected_model_id,
            selected_definition_hash=self.selected_definition_hash,
            challenger_model_ids=self.challenger_model_ids,
            qualification_decision_id=self.qualification_decision_id,
            qualification_decision_hash=self.qualification_decision_hash,
            runtime_lineage_hash=self.runtime_lineage_hash,
            evidence_ids=self.evidence_ids,
            reason_codes=self.reason_codes,
            production_authorized=self.production_authorized,
            selected_at=self.selected_at,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "receipt_id": str(self.receipt_id),
            "receipt_hash": self.receipt_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> ModelSelectionReceipt:
        rebuilt = cls._create(
            request_hash=_string(payload["request_hash"]),
            runtime_scope=_string(payload["runtime_scope"]),
            model_slot=_string(payload["model_slot"]),
            purpose=RuntimePurpose(_string(payload["purpose"])),
            status=SelectionStatus(_string(payload["status"])),
            governance_revision=_integer(payload["governance_revision"]),
            policy_id=_optional_artifact_id(payload["policy_id"]),
            policy_hash=_optional_string(payload["policy_hash"]),
            champion_assignment_id=_optional_artifact_id(
                payload["champion_assignment_id"]
            ),
            champion_assignment_hash=_optional_string(
                payload["champion_assignment_hash"]
            ),
            champion_assignment_version=_optional_integer(
                payload["champion_assignment_version"]
            ),
            selected_registry_version=_optional_integer(
                payload["selected_registry_version"]
            ),
            selected_model_id=_optional_model_id(payload["selected_model_id"]),
            selected_definition_hash=_optional_string(
                payload["selected_definition_hash"]
            ),
            challenger_model_ids=tuple(
                ModelId(_string(item))
                for item in _sequence(payload["challenger_model_ids"])
            ),
            qualification_decision_id=_optional_artifact_id(
                payload["qualification_decision_id"]
            ),
            qualification_decision_hash=_optional_string(
                payload["qualification_decision_hash"]
            ),
            runtime_lineage_hash=_string(payload["runtime_lineage_hash"]),
            evidence_ids=tuple(
                ArtifactId(_string(item))
                for item in _sequence(payload["evidence_ids"])
            ),
            reason_codes=tuple(
                _string(item) for item in _sequence(payload["reason_codes"])
            ),
            production_authorized=_boolean(payload["production_authorized"]),
            selected_at=_instant(payload["selected_at"]),
        )
        if (
            str(rebuilt.receipt_id) != payload.get("receipt_id")
            or rebuilt.receipt_hash != payload.get("receipt_hash")
        ):
            raise ValueError("Model Selection Receipt stored identity mismatch")
        return rebuilt


def evaluate_qualification(
    *,
    registration: ModelRegistration,
    lineage: ModelVersionLineage,
    policy: ModelGovernancePolicy,
    evidence: tuple[ModelQualificationEvidence, ...],
    decided_at: datetime,
    actor: str,
    reason: str,
    approval_ref: str | None,
    governance_revision: int,
    authority_rejection_codes: tuple[str, ...] = (),
) -> ModelQualificationDecision:
    if registration.definition.model_id != lineage.model_id:
        raise ValueError("qualification Registry/lineage model mismatch")
    if registration.definition.definition_hash != lineage.definition_hash:
        raise ValueError("qualification Registry/lineage definition mismatch")
    reasons: set[str] = set(authority_rejection_codes)
    if registration.lifecycle_status not in policy.allowed_lifecycle_statuses:
        reasons.add("LIFECYCLE_NOT_ALLOWED")
    by_kind: dict[QualificationEvidenceKind, ModelQualificationEvidence] = {}
    for item in evidence:
        if (
            item.model_id != lineage.model_id
            or item.definition_hash != lineage.definition_hash
            or item.lineage_id != lineage.lineage_id
            or item.lineage_hash != lineage.lineage_hash
        ):
            reasons.add("EVIDENCE_LINEAGE_MISMATCH")
            continue
        if item.validation_protocol_ref not in lineage.validation_protocol_refs:
            reasons.add("EVIDENCE_PROTOCOL_MISMATCH")
        previous = by_kind.get(item.evidence_kind)
        if previous is not None:
            reasons.add("DUPLICATE_EVIDENCE_KIND")
        by_kind[item.evidence_kind] = item
        if item.outcome is not QualificationEvidenceOutcome.SATISFIED:
            reasons.add("EVIDENCE_NOT_SATISFIED")
        if item.available_at > decided_at or item.recorded_at > decided_at:
            reasons.add("EVIDENCE_NOT_AVAILABLE_AT_DECISION")
    if not set(policy.required_evidence_kinds).issubset(by_kind):
        reasons.add("REQUIRED_EVIDENCE_MISSING")
    if not set(lineage.supported_data_eligibilities).intersection(
        policy.allowed_data_eligibilities
    ):
        reasons.add("DATA_ELIGIBILITY_NOT_ALLOWED")
    if policy.production_authorization and approval_ref is None:
        reasons.add("PRODUCTION_APPROVAL_REQUIRED")
    status = (
        QualificationStatus.QUALIFIED
        if not reasons
        else QualificationStatus.NOT_QUALIFIED
    )
    production_authorized = (
        status is QualificationStatus.QUALIFIED
        and policy.production_authorization
        and approval_ref is not None
    )
    ordered_evidence = tuple(sorted(evidence, key=lambda item: str(item.evidence_id)))
    return ModelQualificationDecision.create(
        model_id=lineage.model_id,
        definition_hash=lineage.definition_hash,
        lineage_id=lineage.lineage_id,
        lineage_hash=lineage.lineage_hash,
        policy_id=policy.policy_id,
        policy_hash=policy.policy_hash,
        purpose=policy.purpose,
        status=status,
        evidence_ids=tuple(item.evidence_id for item in ordered_evidence),
        evidence_hashes=tuple(item.evidence_hash for item in ordered_evidence),
        reason_codes=tuple(sorted(reasons)),
        production_authorized=production_authorized,
        decided_at=decided_at,
        actor=actor,
        reason=reason,
        approval_ref=approval_ref,
        governance_revision=governance_revision,
    )


def _model_version_lineage_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": "model-version-lineage-v1",
        "model_id": str(values["model_id"]),
        "model_version": values["model_version"],
        "definition_hash": values["definition_hash"],
        "target_id": str(values["target_id"]),
        "universe_contract_id": str(values["universe_contract_id"]),
        "feature_definition_ids": [
            str(item) for item in values["feature_definition_ids"]
        ],
        "model_parameter_hash": values["model_parameter_hash"],
        "configuration": values["configuration"].to_canonical_dict(),
        "implementation_ref": values["implementation_ref"],
        "code_revision": values["code_revision"],
        "code_hash": values["code_hash"],
        "validation_protocol_refs": [
            item.to_canonical_dict()
            for item in values["validation_protocol_refs"]
        ],
        "supported_data_eligibilities": [
            item.value for item in values["supported_data_eligibilities"]
        ],
        "created_at": canonical_datetime(values["created_at"]),
    }


def _runtime_model_lineage_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": "runtime-model-lineage-v1",
        "model_id": str(values["model_id"]),
        "definition_hash": values["definition_hash"],
        "dataset": values["dataset"].to_canonical_dict(),
        "universe_id": str(values["universe_id"]),
        "feature_definition_ids": [
            str(item) for item in values["feature_definition_ids"]
        ],
        "feature_materializations": [
            item.to_canonical_dict()
            for item in values["feature_materializations"]
        ],
        "configuration": values["configuration"].to_canonical_dict(),
        "code_revision": values["code_revision"],
        "code_hash": values["code_hash"],
        "validation_protocol_refs": [
            item.to_canonical_dict()
            for item in values["validation_protocol_refs"]
        ],
        "data_eligibility": values["data_eligibility"].value,
    }


def _qualification_evidence_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": "model-qualification-evidence-v1",
        "model_id": str(values["model_id"]),
        "definition_hash": values["definition_hash"],
        "lineage_id": str(values["lineage_id"]),
        "lineage_hash": values["lineage_hash"],
        "evidence_kind": values["evidence_kind"].value,
        "outcome": values["outcome"].value,
        "evidence": values["evidence"].to_canonical_dict(),
        "validation_protocol_ref": values[
            "validation_protocol_ref"
        ].to_canonical_dict(),
        "available_at": canonical_datetime(values["available_at"]),
        "recorded_at": canonical_datetime(values["recorded_at"]),
        "actor": values["actor"],
        "reason": values["reason"],
    }


def _governance_policy_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": "model-governance-policy-v1",
        "name": values["name"],
        "version": values["version"],
        "purpose": values["purpose"].value,
        "allowed_lifecycle_statuses": [
            item.value for item in values["allowed_lifecycle_statuses"]
        ],
        "required_evidence_kinds": [
            item.value for item in values["required_evidence_kinds"]
        ],
        "allowed_data_eligibilities": [
            item.value for item in values["allowed_data_eligibilities"]
        ],
        "production_authorization": values["production_authorization"],
    }


def _qualification_decision_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": "model-qualification-decision-v1",
        "model_id": str(values["model_id"]),
        "definition_hash": values["definition_hash"],
        "lineage_id": str(values["lineage_id"]),
        "lineage_hash": values["lineage_hash"],
        "policy_id": str(values["policy_id"]),
        "policy_hash": values["policy_hash"],
        "purpose": values["purpose"].value,
        "status": values["status"].value,
        "evidence_ids": [str(item) for item in values["evidence_ids"]],
        "evidence_hashes": list(values["evidence_hashes"]),
        "reason_codes": list(values["reason_codes"]),
        "production_authorized": values["production_authorized"],
        "decided_at": canonical_datetime(values["decided_at"]),
        "actor": values["actor"],
        "reason": values["reason"],
        "approval_ref": values["approval_ref"],
        "governance_revision": values["governance_revision"],
    }


def _runtime_assignment_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": "model-runtime-assignment-v1",
        "runtime_scope": values["runtime_scope"],
        "model_slot": values["model_slot"],
        "purpose": values["purpose"].value,
        "lane": values["lane"].value,
        "status": values["status"].value,
        "model_id": str(values["model_id"]),
        "definition_hash": values["definition_hash"],
        "policy_id": str(values["policy_id"]),
        "policy_hash": values["policy_hash"],
        "effective_at": canonical_datetime(values["effective_at"]),
        "actor": values["actor"],
        "reason": values["reason"],
        "approval_ref": values["approval_ref"],
        "governance_revision": values["governance_revision"],
        "version": values.get("version", 0),
        "supersedes_assignment_id": (
            None
            if values.get("supersedes_assignment_id") is None
            else str(values["supersedes_assignment_id"])
        ),
    }


def _selection_request_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": "model-selection-request-v1",
        "runtime_scope": values["runtime_scope"],
        "model_slot": values["model_slot"],
        "purpose": values["purpose"].value,
        "runtime_lineage": values["runtime_lineage"].to_canonical_dict(),
        "selected_at": canonical_datetime(values["selected_at"]),
        "idempotency_key": values["idempotency_key"],
        "preselection_rejection_codes": list(
            values["preselection_rejection_codes"]
        ),
    }


def _selection_receipt_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": "model-selection-receipt-v1",
        "request_hash": values["request_hash"],
        "runtime_scope": values["runtime_scope"],
        "model_slot": values["model_slot"],
        "purpose": values["purpose"].value,
        "status": values["status"].value,
        "governance_revision": values["governance_revision"],
        "policy_id": _optional_id(values["policy_id"]),
        "policy_hash": values["policy_hash"],
        "champion_assignment_id": _optional_id(
            values["champion_assignment_id"]
        ),
        "champion_assignment_hash": values["champion_assignment_hash"],
        "champion_assignment_version": values["champion_assignment_version"],
        "selected_registry_version": values["selected_registry_version"],
        "selected_model_id": _optional_id(values["selected_model_id"]),
        "selected_definition_hash": values["selected_definition_hash"],
        "challenger_model_ids": [
            str(item) for item in values["challenger_model_ids"]
        ],
        "qualification_decision_id": _optional_id(
            values["qualification_decision_id"]
        ),
        "qualification_decision_hash": values["qualification_decision_hash"],
        "runtime_lineage_hash": values["runtime_lineage_hash"],
        "evidence_ids": [str(item) for item in values["evidence_ids"]],
        "reason_codes": list(values["reason_codes"]),
        "production_authorized": values["production_authorized"],
        "selected_at": canonical_datetime(values["selected_at"]),
    }


def _content_id(prefix: str, digest: str) -> ArtifactId:
    require_sha256("content hash", digest)
    return ArtifactId(f"{prefix}:{digest[7:]}")


def _definition_hash(value: str) -> None:
    if not isinstance(value, str) or _RAW_SHA256.fullmatch(value) is None:
        raise ValueError("definition_hash must be a lowercase SHA-256 digest")


def _aware(label: str, value: datetime) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    if value.microsecond:
        raise ValueError(f"{label} must use whole-second precision")


def _positive_revision(value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("governance_revision must be a positive integer")


def _ordered_ids(label: str, values: tuple[Any, ...]) -> None:
    if values != tuple(sorted(set(values), key=str)):
        raise ValueError(f"{label} must be sorted and unique")


def _ordered_text(label: str, values: tuple[str, ...]) -> None:
    if values != tuple(sorted(set(values))):
        raise ValueError(f"{label} must be sorted and unique")
    for value in values:
        require_text(label, value)


def _reference_key(value: ArtifactLineageReference) -> tuple[str, str, str]:
    return value.reference_kind, str(value.artifact_id), value.content_hash


def _sort_references(
    values: tuple[ArtifactLineageReference, ...],
) -> tuple[ArtifactLineageReference, ...]:
    return tuple(sorted(set(values), key=_reference_key))


def _ordered_references(
    label: str, values: tuple[ArtifactLineageReference, ...]
) -> None:
    if values != _sort_references(values):
        raise ValueError(f"{label} must be sorted and unique")


def _fields(payload: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(payload) != expected:
        raise ValueError(f"{label} fields mismatch")


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("expected object")
    return value


def _sequence(value: object) -> tuple[object, ...]:
    if not isinstance(value, list):
        raise ValueError("expected array")
    return tuple(value)


def _string(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("expected string")
    return value


def _boolean(value: object) -> bool:
    if not isinstance(value, bool):
        raise ValueError("expected boolean")
    return value


def _integer(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("expected integer")
    return value


def _optional_integer(value: object) -> int | None:
    return None if value is None else _integer(value)


def _optional_string(value: object) -> str | None:
    return None if value is None else _string(value)


def _optional_artifact_id(value: object) -> ArtifactId | None:
    return None if value is None else ArtifactId(_string(value))


def _optional_model_id(value: object) -> ModelId | None:
    return None if value is None else ModelId(_string(value))


def _instant(value: object) -> datetime:
    return parse_utc_second("datetime", value)


def _optional_id(value: object) -> str | None:
    return None if value is None else str(value)


__all__ = [
    "ArtifactLineageReference",
    "AssignmentLane",
    "AssignmentStatus",
    "ModelGovernancePolicy",
    "ModelQualificationDecision",
    "ModelQualificationEvidence",
    "ModelRuntimeAssignment",
    "ModelSelectionReceipt",
    "ModelVersionLineage",
    "QualificationEvidenceKind",
    "QualificationEvidenceOutcome",
    "QualificationStatus",
    "RuntimeModelLineage",
    "RuntimePurpose",
    "RuntimeAuthorityMode",
    "SelectionStatus",
    "evaluate_qualification",
]
