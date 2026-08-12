"""Ordered, fail-closed orchestration over existing Formal evidence owners."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Mapping, Protocol

from market_regime_alpha.application.research_validation.calibration_qualification import (
    CalibrationQualificationDecision,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
    content_identity,
    timestamp,
)
from market_regime_alpha.application.research_validation.formal_protocol import (
    FormalResearchProtocol,
)
from market_regime_alpha.application.research_validation.qualification import (
    FormalOOSQualificationDecision,
    HistoricalSampleQualificationDecision,
    QualificationOutcome,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.pit_authority import FormalPITEvidenceArtifact
from market_regime_alpha.data.pit_contracts import PITFactKind, PITValidationOutcome
from market_regime_alpha.data.postgres_provider_qualification import (
    ProviderFactQualificationDecision,
    ProviderFactQualificationStatus,
)
from market_regime_alpha.evidence.canonical import canonical_hash, require_sha256, require_text
from market_regime_alpha.platform.runtime_governance import (
    ModelQualificationDecision,
    QualificationStatus,
    RuntimePurpose,
)


class FormalExecutionStatus(str, Enum):
    SATISFIED = "SATISFIED"
    BLOCKED = "BLOCKED"
    INCOMPLETE = "INCOMPLETE"
    REJECTED = "REJECTED"
    NOT_ESTIMABLE = "NOT_ESTIMABLE"


class FormalExecutionStage(str, Enum):
    PROVIDER_FACT_QUALIFICATION = "PROVIDER_FACT_QUALIFICATION"
    FORMAL_PROTOCOL = "FORMAL_PROTOCOL"
    FORMAL_PIT = "FORMAL_PIT"
    HISTORICAL_DATASET = "HISTORICAL_DATASET"
    MODEL_QUALIFICATION = "MODEL_QUALIFICATION"
    FORMAL_OOS = "FORMAL_OOS"
    CALIBRATION = "CALIBRATION"
    COMPLETE = "COMPLETE"


@dataclass(frozen=True, slots=True)
class ProviderFactRequirement:
    provider_id: str
    provider_contract: str
    fact_kind: PITFactKind
    decision_id: ArtifactId | None

    def __post_init__(self) -> None:
        require_text("Formal Provider id", self.provider_id)
        require_text("Formal Provider contract", self.provider_contract)

    @property
    def key(self) -> tuple[str, str, str]:
        return self.provider_id, self.provider_contract, self.fact_kind.value

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "provider_contract": self.provider_contract,
            "fact_kind": self.fact_kind.value,
            "decision_id": None if self.decision_id is None else str(self.decision_id),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> ProviderFactRequirement:
        decision_id = payload["decision_id"]
        return cls(
            provider_id=str(payload["provider_id"]),
            provider_contract=str(payload["provider_contract"]),
            fact_kind=PITFactKind(str(payload["fact_kind"])),
            decision_id=None if decision_id is None else ArtifactId(str(decision_id)),
        )


@dataclass(frozen=True, slots=True)
class FormalExecutionRequest:
    request_id: ArtifactId
    request_hash: str
    provider_requirements: tuple[ProviderFactRequirement, ...]
    formal_protocol_id: ArtifactId | None
    formal_pit_evidence_ids: tuple[ArtifactId, ...]
    historical_qualification_ids: tuple[ArtifactId, ...]
    model_qualification_decision_id: ArtifactId | None
    formal_oos_decision_id: ArtifactId | None
    calibration_decision_id: ArtifactId | None
    assessed_at: datetime
    actor: str
    reason: str
    idempotency_key: str
    schema_version: str = "formal-execution-request/v1"

    def __post_init__(self) -> None:
        require_sha256("Formal Execution request hash", self.request_hash)
        _aware("Formal Execution assessed_at", self.assessed_at)
        for label, value in (
            ("actor", self.actor),
            ("reason", self.reason),
            ("idempotency_key", self.idempotency_key),
        ):
            require_text(f"Formal Execution {label}", value)
        if not self.provider_requirements or self.provider_requirements != tuple(
            sorted(set(self.provider_requirements), key=lambda item: item.key)
        ):
            raise ValueError("Formal Execution Provider requirements must be non-empty, unique and sorted")
        for ids, label in (
            (self.formal_pit_evidence_ids, "PIT Evidence"),
            (self.historical_qualification_ids, "Historical decisions"),
        ):
            if ids != tuple(sorted(set(ids), key=str)):
                raise ValueError(f"Formal Execution {label} must be unique and sorted")
        if canonical_hash(self.identity_payload()) != self.request_hash:
            raise ValueError("Formal Execution request hash mismatch")
        if self.request_id != ArtifactId(f"formal-execution-request:{self.request_hash[7:]}"):
            raise ValueError("Formal Execution request identity mismatch")

    @classmethod
    def create(cls, **values: Any) -> FormalExecutionRequest:
        normalized = dict(values)
        normalized["provider_requirements"] = tuple(
            sorted(set(values["provider_requirements"]), key=lambda item: item.key)
        )
        normalized["formal_pit_evidence_ids"] = tuple(
            sorted(set(values.get("formal_pit_evidence_ids", ())), key=str)
        )
        normalized["historical_qualification_ids"] = tuple(
            sorted(set(values.get("historical_qualification_ids", ())), key=str)
        )
        payload = _request_payload(**normalized)
        request_id, digest = content_identity("formal-execution-request", payload)
        return cls(request_id, digest, **normalized)

    def identity_payload(self) -> dict[str, Any]:
        return _request_payload(
            provider_requirements=self.provider_requirements,
            formal_protocol_id=self.formal_protocol_id,
            formal_pit_evidence_ids=self.formal_pit_evidence_ids,
            historical_qualification_ids=self.historical_qualification_ids,
            model_qualification_decision_id=self.model_qualification_decision_id,
            formal_oos_decision_id=self.formal_oos_decision_id,
            calibration_decision_id=self.calibration_decision_id,
            assessed_at=self.assessed_at,
            actor=self.actor,
            reason=self.reason,
            idempotency_key=self.idempotency_key,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "request_id": str(self.request_id),
            "request_hash": self.request_hash,
            **self.identity_payload(),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> FormalExecutionRequest:
        return cls(
            request_id=ArtifactId(str(payload["request_id"])),
            request_hash=str(payload["request_hash"]),
            provider_requirements=tuple(
                ProviderFactRequirement.from_canonical_dict(_mapping(item))
                for item in _array(payload["provider_requirements"])
            ),
            formal_protocol_id=_optional_id(payload["formal_protocol_id"]),
            formal_pit_evidence_ids=tuple(ArtifactId(str(item)) for item in _array(payload["formal_pit_evidence_ids"])),
            historical_qualification_ids=tuple(ArtifactId(str(item)) for item in _array(payload["historical_qualification_ids"])),
            model_qualification_decision_id=_optional_id(payload["model_qualification_decision_id"]),
            formal_oos_decision_id=_optional_id(payload["formal_oos_decision_id"]),
            calibration_decision_id=_optional_id(payload["calibration_decision_id"]),
            assessed_at=_instant(payload["assessed_at"]),
            actor=str(payload["actor"]),
            reason=str(payload["reason"]),
            idempotency_key=str(payload["idempotency_key"]),
            schema_version=str(payload["schema_version"]),
        )


@dataclass(frozen=True, slots=True)
class FormalExecutionStageAssessment:
    stage: FormalExecutionStage
    status: FormalExecutionStatus
    owner_references: tuple[ValidationArtifactReference, ...]
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.owner_references != _references(self.owner_references):
            raise ValueError("Formal stage owners must be unique and sorted")
        if self.reason_codes != tuple(sorted(set(self.reason_codes))):
            raise ValueError("Formal stage reasons must be unique and sorted")
        if self.status is FormalExecutionStatus.SATISFIED and self.reason_codes:
            raise ValueError("Satisfied Formal stage cannot have rejection reasons")
        if self.status is not FormalExecutionStatus.SATISFIED and not self.reason_codes:
            raise ValueError("Non-satisfied Formal stage requires reasons")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage.value,
            "status": self.status.value,
            "owner_references": [item.to_canonical_dict() for item in self.owner_references],
            "reason_codes": list(self.reason_codes),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> FormalExecutionStageAssessment:
        return cls(
            stage=FormalExecutionStage(str(payload["stage"])),
            status=FormalExecutionStatus(str(payload["status"])),
            owner_references=tuple(_reference(item) for item in _array(payload["owner_references"])),
            reason_codes=tuple(str(item) for item in _array(payload["reason_codes"])),
        )


@dataclass(frozen=True, slots=True)
class FormalExecutionAssessment:
    assessment_id: ArtifactId
    assessment_hash: str
    request_reference: ValidationArtifactReference
    status: FormalExecutionStatus
    terminal_stage: FormalExecutionStage
    stages: tuple[FormalExecutionStageAssessment, ...]
    source_references: tuple[ValidationArtifactReference, ...]
    formal_model_qualified: bool
    formal_oos_alpha_established: bool
    calibrated: bool
    production_authorized: bool
    assessed_at: datetime
    reason_codes: tuple[str, ...]
    schema_version: str = "formal-execution-assessment/v1"

    def __post_init__(self) -> None:
        require_sha256("Formal Execution assessment hash", self.assessment_hash)
        _aware("Formal Execution assessment time", self.assessed_at)
        if not self.stages or self.stages[-1].stage is not self.terminal_stage:
            raise ValueError("Formal Execution terminal stage projection mismatch")
        if tuple(item.stage for item in self.stages) != tuple(
            sorted((item.stage for item in self.stages), key=_stage_order)
        ):
            raise ValueError("Formal Execution stages are out of order")
        if self.source_references != _references(self.source_references):
            raise ValueError("Formal Execution sources must be unique and sorted")
        if self.reason_codes != tuple(sorted(set(self.reason_codes))):
            raise ValueError("Formal Execution reasons must be unique and sorted")
        if self.formal_oos_alpha_established and not self.formal_model_qualified:
            raise ValueError("Formal OOS cannot precede Formal Model qualification")
        if self.calibrated and not self.formal_oos_alpha_established:
            raise ValueError("Calibration cannot precede Formal OOS")
        if self.production_authorized:
            raise ValueError("Formal Execution assessment cannot authorize Production")
        if self.status is not FormalExecutionStatus.SATISFIED and (
            self.formal_oos_alpha_established or self.calibrated
        ):
            raise ValueError("Blocked Formal Execution cannot claim downstream evidence")
        if canonical_hash(self.identity_payload()) != self.assessment_hash:
            raise ValueError("Formal Execution assessment hash mismatch")
        if self.assessment_id != ArtifactId(f"formal-execution-assessment:{self.assessment_hash[7:]}"):
            raise ValueError("Formal Execution assessment identity mismatch")

    @classmethod
    def create(cls, **values: Any) -> FormalExecutionAssessment:
        normalized = dict(values)
        normalized["source_references"] = _references(values["source_references"])
        normalized["reason_codes"] = tuple(sorted(set(values["reason_codes"])))
        payload = _assessment_payload(**normalized)
        assessment_id, digest = content_identity("formal-execution-assessment", payload)
        return cls(assessment_id, digest, **normalized)

    def identity_payload(self) -> dict[str, Any]:
        return _assessment_payload(
            request_reference=self.request_reference,
            status=self.status,
            terminal_stage=self.terminal_stage,
            stages=self.stages,
            source_references=self.source_references,
            formal_model_qualified=self.formal_model_qualified,
            formal_oos_alpha_established=self.formal_oos_alpha_established,
            calibrated=self.calibrated,
            production_authorized=self.production_authorized,
            assessed_at=self.assessed_at,
            reason_codes=self.reason_codes,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "assessment_id": str(self.assessment_id),
            "assessment_hash": self.assessment_hash,
            **self.identity_payload(),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> FormalExecutionAssessment:
        return cls(
            assessment_id=ArtifactId(str(payload["assessment_id"])),
            assessment_hash=str(payload["assessment_hash"]),
            request_reference=_reference(payload["request_reference"]),
            status=FormalExecutionStatus(str(payload["status"])),
            terminal_stage=FormalExecutionStage(str(payload["terminal_stage"])),
            stages=tuple(FormalExecutionStageAssessment.from_canonical_dict(_mapping(item)) for item in _array(payload["stages"])),
            source_references=tuple(_reference(item) for item in _array(payload["source_references"])),
            formal_model_qualified=_boolean(payload["formal_model_qualified"]),
            formal_oos_alpha_established=_boolean(payload["formal_oos_alpha_established"]),
            calibrated=_boolean(payload["calibrated"]),
            production_authorized=_boolean(payload["production_authorized"]),
            assessed_at=_instant(payload["assessed_at"]),
            reason_codes=tuple(str(item) for item in _array(payload["reason_codes"])),
            schema_version=str(payload["schema_version"]),
        )


class FormalExecutionOwnerResolver(Protocol):
    def provider_fact(self, decision_id: ArtifactId) -> ProviderFactQualificationDecision: ...
    def protocol(self, protocol_id: ArtifactId) -> FormalResearchProtocol: ...
    def formal_pit(self, evidence_id: ArtifactId) -> FormalPITEvidenceArtifact: ...
    def historical(self, decision_id: ArtifactId) -> HistoricalSampleQualificationDecision: ...
    def model(self, decision_id: ArtifactId) -> ModelQualificationDecision: ...
    def formal_oos(self, decision_id: ArtifactId) -> FormalOOSQualificationDecision: ...
    def calibration(self, decision_id: ArtifactId) -> CalibrationQualificationDecision: ...


def assess_formal_execution(
    request: FormalExecutionRequest,
    *,
    resolver: FormalExecutionOwnerResolver,
) -> FormalExecutionAssessment:
    stages: list[FormalExecutionStageAssessment] = []
    sources: list[ValidationArtifactReference] = []
    provider_reasons: set[str] = set()
    provider_statuses: set[FormalExecutionStatus] = set()
    qualified_source_ids: set[ArtifactId] = set()
    for requirement in request.provider_requirements:
        scope = ":".join(requirement.key)
        if requirement.decision_id is None:
            provider_reasons.add(f"PROVIDER_FACT_DECISION_MISSING:{scope}")
            provider_statuses.add(FormalExecutionStatus.BLOCKED)
            continue
        try:
            decision = resolver.provider_fact(requirement.decision_id)
        except (KeyError, ValueError):
            provider_reasons.add(f"PROVIDER_FACT_OWNER_INVALID:{scope}")
            provider_statuses.add(FormalExecutionStatus.BLOCKED)
            continue
        reference = ValidationArtifactReference(
            "PROVIDER_FACT_QUALIFICATION_DECISION",
            decision.decision_id,
            decision.decision_hash,
        )
        sources.append(reference)
        if (
            decision.provider_id,
            decision.provider_contract,
            decision.fact_kind.value,
        ) != requirement.key:
            provider_reasons.add(f"PROVIDER_FACT_SCOPE_MISMATCH:{scope}")
            provider_statuses.add(FormalExecutionStatus.REJECTED)
        elif decision.status is not ProviderFactQualificationStatus.QUALIFIED:
            status = _provider_status(decision.status)
            provider_statuses.add(status)
            provider_reasons.add(f"PROVIDER_FACT_{decision.status.value}:{scope}")
        else:
            qualified_source_ids.update(
                item.artifact_id for item in decision.source_qualification_references
            )
    if provider_reasons:
        status = _worst_status(provider_statuses)
        stages.append(_stage(FormalExecutionStage.PROVIDER_FACT_QUALIFICATION, status, sources, provider_reasons))
        return _finish(request, stages, sources, status)
    stages.append(_stage(FormalExecutionStage.PROVIDER_FACT_QUALIFICATION, FormalExecutionStatus.SATISFIED, sources, ()))

    if request.formal_protocol_id is None:
        return _blocked(request, stages, sources, FormalExecutionStage.FORMAL_PROTOCOL, "FORMAL_PROTOCOL_MISSING")
    try:
        protocol = resolver.protocol(request.formal_protocol_id)
    except (KeyError, ValueError):
        return _blocked(request, stages, sources, FormalExecutionStage.FORMAL_PROTOCOL, "FORMAL_PROTOCOL_OWNER_INVALID")
    protocol_ref = ValidationArtifactReference("FORMAL_RESEARCH_PROTOCOL", protocol.protocol_id, protocol.protocol_hash)
    sources.append(protocol_ref)
    stages.append(_stage(FormalExecutionStage.FORMAL_PROTOCOL, FormalExecutionStatus.SATISFIED, (protocol_ref,), ()))

    if not request.formal_pit_evidence_ids:
        return _blocked(request, stages, sources, FormalExecutionStage.FORMAL_PIT, "FORMAL_PIT_EVIDENCE_MISSING")
    pit_refs = []
    for evidence_id in request.formal_pit_evidence_ids:
        try:
            evidence = resolver.formal_pit(evidence_id)
        except (KeyError, ValueError):
            return _blocked(request, stages, sources, FormalExecutionStage.FORMAL_PIT, "FORMAL_PIT_OWNER_INVALID")
        reference = ValidationArtifactReference("FORMAL_PIT_EVIDENCE", evidence.evidence_id, evidence.evidence_hash)
        pit_refs.append(reference)
        sources.append(reference)
        if evidence.outcome is not PITValidationOutcome.SATISFIED:
            return _terminal(request, stages, sources, FormalExecutionStage.FORMAL_PIT, FormalExecutionStatus.REJECTED, evidence.rejection_codes or ("FORMAL_PIT_REJECTED",))
        if any(
            item.source_qualification_id not in qualified_source_ids
            for item in evidence.selected_fact_authorities
        ):
            return _terminal(request, stages, sources, FormalExecutionStage.FORMAL_PIT, FormalExecutionStatus.REJECTED, ("FORMAL_PIT_PROVIDER_FACT_BINDING_MISMATCH",))
    stages.append(_stage(FormalExecutionStage.FORMAL_PIT, FormalExecutionStatus.SATISFIED, pit_refs, ()))

    if not request.historical_qualification_ids:
        return _blocked(request, stages, sources, FormalExecutionStage.HISTORICAL_DATASET, "HISTORICAL_QUALIFICATION_MISSING")
    historical_refs = []
    for decision_id in request.historical_qualification_ids:
        try:
            historical = resolver.historical(decision_id)
        except (KeyError, ValueError):
            return _blocked(request, stages, sources, FormalExecutionStage.HISTORICAL_DATASET, "HISTORICAL_QUALIFICATION_OWNER_INVALID")
        reference = ValidationArtifactReference("HISTORICAL_SAMPLE_QUALIFICATION_DECISION", historical.decision_id, historical.decision_hash)
        historical_refs.append(reference)
        sources.append(reference)
        if historical.formal_protocol_reference != protocol_ref:
            return _terminal(request, stages, sources, FormalExecutionStage.HISTORICAL_DATASET, FormalExecutionStatus.REJECTED, ("HISTORICAL_PROTOCOL_BINDING_MISMATCH",))
        if historical.outcome is not QualificationOutcome.SATISFIED:
            return _terminal(request, stages, sources, FormalExecutionStage.HISTORICAL_DATASET, _qualification_status(historical.outcome), historical.reason_codes)
    stages.append(_stage(FormalExecutionStage.HISTORICAL_DATASET, FormalExecutionStatus.SATISFIED, historical_refs, ()))

    if request.model_qualification_decision_id is None:
        return _blocked(request, stages, sources, FormalExecutionStage.MODEL_QUALIFICATION, "FORMAL_MODEL_QUALIFICATION_MISSING")
    try:
        model = resolver.model(request.model_qualification_decision_id)
    except (KeyError, ValueError):
        return _blocked(request, stages, sources, FormalExecutionStage.MODEL_QUALIFICATION, "FORMAL_MODEL_QUALIFICATION_OWNER_INVALID")
    model_ref = ValidationArtifactReference("MODEL_QUALIFICATION_DECISION", model.decision_id, model.decision_hash)
    sources.append(model_ref)
    if (
        model.status is not QualificationStatus.QUALIFIED
        or model.purpose is not RuntimePurpose.BACKTEST
        or model.lineage_id != protocol.model_reference.artifact_id
        or model.lineage_hash != protocol.model_reference.content_hash
    ):
        return _terminal(request, stages, sources, FormalExecutionStage.MODEL_QUALIFICATION, FormalExecutionStatus.REJECTED, ("FORMAL_MODEL_QUALIFICATION_NOT_SATISFIED",))
    stages.append(_stage(FormalExecutionStage.MODEL_QUALIFICATION, FormalExecutionStatus.SATISFIED, (model_ref,), ()))

    if request.formal_oos_decision_id is None:
        return _blocked(request, stages, sources, FormalExecutionStage.FORMAL_OOS, "FORMAL_OOS_QUALIFICATION_MISSING")
    try:
        oos = resolver.formal_oos(request.formal_oos_decision_id)
    except (KeyError, ValueError):
        return _blocked(request, stages, sources, FormalExecutionStage.FORMAL_OOS, "FORMAL_OOS_QUALIFICATION_OWNER_INVALID")
    oos_ref = ValidationArtifactReference("FORMAL_OOS_QUALIFICATION_DECISION", oos.decision_id, oos.decision_hash)
    sources.append(oos_ref)
    if (
        oos.formal_protocol_reference != protocol_ref
        or set(oos.formal_pit_references) != set(pit_refs)
        or set(oos.historical_sample_decision_references) != set(historical_refs)
    ):
        return _terminal(request, stages, sources, FormalExecutionStage.FORMAL_OOS, FormalExecutionStatus.REJECTED, ("FORMAL_OOS_PREDECESSOR_BINDING_MISMATCH",))
    if oos.outcome is not QualificationOutcome.SATISFIED or not oos.formal_oos_passed:
        return _terminal(request, stages, sources, FormalExecutionStage.FORMAL_OOS, _qualification_status(oos.outcome), oos.reason_codes)
    stages.append(_stage(FormalExecutionStage.FORMAL_OOS, FormalExecutionStatus.SATISFIED, (oos_ref,), ()))

    if request.calibration_decision_id is None:
        return _blocked(request, stages, sources, FormalExecutionStage.CALIBRATION, "CALIBRATION_QUALIFICATION_MISSING")
    try:
        calibration = resolver.calibration(request.calibration_decision_id)
    except (KeyError, ValueError):
        return _blocked(request, stages, sources, FormalExecutionStage.CALIBRATION, "CALIBRATION_QUALIFICATION_OWNER_INVALID")
    calibration_ref = ValidationArtifactReference("CALIBRATION_QUALIFICATION_DECISION", calibration.decision_id, calibration.decision_hash)
    sources.append(calibration_ref)
    if calibration.formal_protocol_reference != protocol_ref or calibration.formal_oos_reference != oos_ref:
        return _terminal(request, stages, sources, FormalExecutionStage.CALIBRATION, FormalExecutionStatus.REJECTED, ("CALIBRATION_PREDECESSOR_BINDING_MISMATCH",))
    if calibration.outcome is not QualificationOutcome.SATISFIED or not calibration.calibrated:
        return _terminal(request, stages, sources, FormalExecutionStage.CALIBRATION, _qualification_status(calibration.outcome), calibration.reason_codes)
    stages.append(_stage(FormalExecutionStage.CALIBRATION, FormalExecutionStatus.SATISFIED, (calibration_ref,), ()))
    stages.append(_stage(FormalExecutionStage.COMPLETE, FormalExecutionStatus.SATISFIED, (), ()))
    return FormalExecutionAssessment.create(
        request_reference=_request_reference(request),
        status=FormalExecutionStatus.SATISFIED,
        terminal_stage=FormalExecutionStage.COMPLETE,
        stages=tuple(stages),
        source_references=tuple(sources),
        formal_model_qualified=True,
        formal_oos_alpha_established=True,
        calibrated=True,
        production_authorized=False,
        assessed_at=request.assessed_at,
        reason_codes=(),
    )


def _blocked(request: FormalExecutionRequest, stages: list[FormalExecutionStageAssessment], sources: list[ValidationArtifactReference], stage: FormalExecutionStage, reason: str) -> FormalExecutionAssessment:
    return _terminal(request, stages, sources, stage, FormalExecutionStatus.BLOCKED, (reason,))


def _terminal(request: FormalExecutionRequest, stages: list[FormalExecutionStageAssessment], sources: list[ValidationArtifactReference], stage: FormalExecutionStage, status: FormalExecutionStatus, reasons: tuple[str, ...]) -> FormalExecutionAssessment:
    stages.append(_stage(stage, status, (), reasons))
    return _finish(request, stages, sources, status)


def _finish(request: FormalExecutionRequest, stages: list[FormalExecutionStageAssessment], sources: list[ValidationArtifactReference], status: FormalExecutionStatus) -> FormalExecutionAssessment:
    reasons = tuple(sorted({reason for item in stages for reason in item.reason_codes}))
    return FormalExecutionAssessment.create(
        request_reference=_request_reference(request),
        status=status,
        terminal_stage=stages[-1].stage,
        stages=tuple(stages),
        source_references=tuple(sources),
        formal_model_qualified=False,
        formal_oos_alpha_established=False,
        calibrated=False,
        production_authorized=False,
        assessed_at=request.assessed_at,
        reason_codes=reasons,
    )


def _stage(stage: FormalExecutionStage, status: FormalExecutionStatus, owners: Any, reasons: Any) -> FormalExecutionStageAssessment:
    return FormalExecutionStageAssessment(stage, status, _references(tuple(owners)), tuple(sorted(set(reasons))))


def _provider_status(status: ProviderFactQualificationStatus) -> FormalExecutionStatus:
    if status is ProviderFactQualificationStatus.INCOMPLETE:
        return FormalExecutionStatus.INCOMPLETE
    if status is ProviderFactQualificationStatus.REJECTED:
        return FormalExecutionStatus.REJECTED
    return FormalExecutionStatus.BLOCKED


def _qualification_status(outcome: QualificationOutcome) -> FormalExecutionStatus:
    return {
        QualificationOutcome.REJECTED: FormalExecutionStatus.REJECTED,
        QualificationOutcome.NOT_ESTIMABLE: FormalExecutionStatus.NOT_ESTIMABLE,
        QualificationOutcome.BLOCKED: FormalExecutionStatus.BLOCKED,
        QualificationOutcome.SATISFIED: FormalExecutionStatus.SATISFIED,
    }[outcome]


def _worst_status(statuses: set[FormalExecutionStatus]) -> FormalExecutionStatus:
    for status in (
        FormalExecutionStatus.REJECTED,
        FormalExecutionStatus.INCOMPLETE,
        FormalExecutionStatus.BLOCKED,
        FormalExecutionStatus.NOT_ESTIMABLE,
    ):
        if status in statuses:
            return status
    return FormalExecutionStatus.BLOCKED


def _request_reference(request: FormalExecutionRequest) -> ValidationArtifactReference:
    return ValidationArtifactReference("FORMAL_EXECUTION_REQUEST", request.request_id, request.request_hash)


def _request_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": "formal-execution-request/v1",
        "provider_requirements": [item.to_canonical_dict() for item in values["provider_requirements"]],
        "formal_protocol_id": _id_value(values.get("formal_protocol_id")),
        "formal_pit_evidence_ids": [str(item) for item in values.get("formal_pit_evidence_ids", ())],
        "historical_qualification_ids": [str(item) for item in values.get("historical_qualification_ids", ())],
        "model_qualification_decision_id": _id_value(values.get("model_qualification_decision_id")),
        "formal_oos_decision_id": _id_value(values.get("formal_oos_decision_id")),
        "calibration_decision_id": _id_value(values.get("calibration_decision_id")),
        "assessed_at": timestamp(values["assessed_at"]),
        "actor": values["actor"],
        "reason": values["reason"],
        "idempotency_key": values["idempotency_key"],
    }


def _assessment_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": "formal-execution-assessment/v1",
        "request_reference": values["request_reference"].to_canonical_dict(),
        "status": values["status"].value,
        "terminal_stage": values["terminal_stage"].value,
        "stages": [item.to_canonical_dict() for item in values["stages"]],
        "source_references": [item.to_canonical_dict() for item in values["source_references"]],
        "formal_model_qualified": values["formal_model_qualified"],
        "formal_oos_alpha_established": values["formal_oos_alpha_established"],
        "calibrated": values["calibrated"],
        "production_authorized": values["production_authorized"],
        "assessed_at": timestamp(values["assessed_at"]),
        "reason_codes": list(values["reason_codes"]),
    }


_STAGE_ORDER = {item: index for index, item in enumerate(FormalExecutionStage)}


def _stage_order(stage: FormalExecutionStage) -> int:
    return _STAGE_ORDER[stage]


def _references(values: tuple[ValidationArtifactReference, ...]) -> tuple[ValidationArtifactReference, ...]:
    return tuple(sorted(set(values), key=lambda item: (item.artifact_kind, str(item.artifact_id), item.content_hash)))


def _reference(value: object) -> ValidationArtifactReference:
    return ValidationArtifactReference.from_canonical_dict(_mapping(value))


def _id_value(value: object) -> str | None:
    return None if value is None else str(value)


def _optional_id(value: object) -> ArtifactId | None:
    return None if value is None else ArtifactId(str(value))


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("expected object")
    return value


def _array(value: object) -> list[object]:
    if not isinstance(value, list):
        raise ValueError("expected array")
    return value


def _instant(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value))
    _aware("timestamp", parsed)
    return parsed


def _aware(name: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _boolean(value: object) -> bool:
    if not isinstance(value, bool):
        raise ValueError("expected boolean")
    return value


__all__ = [
    "FormalExecutionAssessment",
    "FormalExecutionOwnerResolver",
    "FormalExecutionRequest",
    "FormalExecutionStage",
    "FormalExecutionStageAssessment",
    "FormalExecutionStatus",
    "ProviderFactRequirement",
    "assess_formal_execution",
]
