"""Formal point-in-time fact, snapshot and validation evidence contracts.

The contracts are provider-neutral. PostgreSQL owns recording, as-of selection
and replay; Model Governance consumes only a satisfied evidence reference.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import json
from typing import Any, Mapping

from market_regime_alpha.core.identity import ArtifactId, ModelId
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    require_sha256,
    require_text,
)
from market_regime_alpha.market_data.contracts import (
    parse_utc_second,
    require_utc_second,
)


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
        _require_fields(payload, {"reference_kind", "artifact_id", "content_hash"}, "PIT Artifact Reference")
        return cls(
            reference_kind=_string(payload["reference_kind"]),
            artifact_id=ArtifactId(_string(payload["artifact_id"])),
            content_hash=_string(payload["content_hash"]),
        )


@dataclass(frozen=True, slots=True)
class PITSourceQualification:
    qualification_id: ArtifactId
    qualification_hash: str
    source_manifest: PITArtifactReference
    provider_id: str
    provider_contract: str
    status: PITSourceAuthorityStatus
    evidence_references: tuple[PITArtifactReference, ...]
    revision: int
    supersedes_qualification_id: ArtifactId | None
    effective_at: datetime
    recorded_at: datetime
    actor: str
    reason: str
    schema_version: str = "pit-source-qualification-v1"

    def __post_init__(self) -> None:
        if self.schema_version != "pit-source-qualification-v1":
            raise ValueError("unsupported PIT Source Qualification schema")
        require_sha256("qualification_hash", self.qualification_hash)
        for label, value in (
            ("provider_id", self.provider_id),
            ("provider_contract", self.provider_contract),
            ("actor", self.actor),
            ("reason", self.reason),
        ):
            require_text(label, value)
        _ordered_references(
            "evidence_references", self.evidence_references, required=True
        )
        if isinstance(self.revision, bool) or self.revision <= 0:
            raise ValueError("source qualification revision must be positive")
        if (self.revision == 1) != (self.supersedes_qualification_id is None):
            raise ValueError("source qualification supersession/revision mismatch")
        require_utc_second("effective_at", self.effective_at)
        require_utc_second("recorded_at", self.recorded_at)
        if self.recorded_at < self.effective_at:
            raise ValueError("source qualification recorded before effective")
        if canonical_hash(self.semantic_payload()) != self.qualification_hash:
            raise ValueError("PIT Source Qualification hash mismatch")
        if self.qualification_id != _content_id(
            "pit-source-qualification", self.qualification_hash
        ):
            raise ValueError("PIT Source Qualification identity mismatch")

    @classmethod
    def create(cls, **values: Any) -> PITSourceQualification:
        normalized = dict(values)
        normalized["evidence_references"] = tuple(
            sorted(set(values["evidence_references"]), key=_reference_key)
        )
        digest = canonical_hash(_source_qualification_payload(**normalized))
        return cls(
            qualification_id=_content_id("pit-source-qualification", digest),
            qualification_hash=digest,
            **normalized,
        )

    def semantic_payload(self) -> dict[str, Any]:
        return _source_qualification_payload(
            source_manifest=self.source_manifest,
            provider_id=self.provider_id,
            provider_contract=self.provider_contract,
            status=self.status,
            evidence_references=self.evidence_references,
            revision=self.revision,
            supersedes_qualification_id=self.supersedes_qualification_id,
            effective_at=self.effective_at,
            recorded_at=self.recorded_at,
            actor=self.actor,
            reason=self.reason,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "qualification_id": str(self.qualification_id),
            "qualification_hash": self.qualification_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> PITSourceQualification:
        expected = {
            "schema_version", "qualification_id", "qualification_hash",
            "source_manifest", "provider_id", "provider_contract", "status",
            "evidence_references", "revision", "supersedes_qualification_id",
            "effective_at", "recorded_at", "actor", "reason",
        }
        _require_fields(payload, expected, "PIT Source Qualification")
        supersedes = payload["supersedes_qualification_id"]
        return cls(
            qualification_id=ArtifactId(_string(payload["qualification_id"])),
            qualification_hash=_string(payload["qualification_hash"]),
            source_manifest=PITArtifactReference.from_canonical_dict(
                _mapping(payload["source_manifest"])
            ),
            provider_id=_string(payload["provider_id"]),
            provider_contract=_string(payload["provider_contract"]),
            status=PITSourceAuthorityStatus(_string(payload["status"])),
            evidence_references=tuple(
                PITArtifactReference.from_canonical_dict(_mapping(item))
                for item in _sequence(payload["evidence_references"])
            ),
            revision=_integer(payload["revision"]),
            supersedes_qualification_id=(
                ArtifactId(_string(supersedes)) if supersedes is not None else None
            ),
            effective_at=parse_utc_second("effective_at", payload["effective_at"]),
            recorded_at=parse_utc_second("recorded_at", payload["recorded_at"]),
            actor=_string(payload["actor"]),
            reason=_string(payload["reason"]),
            schema_version=_string(payload["schema_version"]),
        )


@dataclass(frozen=True, slots=True)
class PITFactRevision:
    fact_id: ArtifactId
    content_hash: str
    scope_id: str
    logical_key: str
    fact_kind: PITFactKind
    subject: str
    revision: int
    supersedes_fact_id: ArtifactId | None
    event_time: datetime
    effective_from: datetime
    effective_to: datetime | None
    available_at: datetime
    recorded_at: datetime
    artifact: PITArtifactReference
    source_manifest: PITArtifactReference
    provider_id: str
    provider_contract: str
    value_json: str
    data_eligibility: DataEligibility
    schema_version: str = "pit-fact-revision-v1"

    def __post_init__(self) -> None:
        if self.schema_version != "pit-fact-revision-v1":
            raise ValueError("unsupported PIT Fact Revision schema")
        require_sha256("content_hash", self.content_hash)
        for label, text_value in (
            ("scope_id", self.scope_id),
            ("logical_key", self.logical_key),
            ("subject", self.subject),
            ("provider_id", self.provider_id),
            ("provider_contract", self.provider_contract),
        ):
            require_text(label, text_value)
        if isinstance(self.revision, bool) or self.revision <= 0:
            raise ValueError("revision must be positive")
        if self.revision == 1 and self.supersedes_fact_id is not None:
            raise ValueError("revision one cannot supersede another fact")
        if self.revision > 1 and self.supersedes_fact_id is None:
            raise ValueError("later revision requires superseded fact")
        for label, timestamp in (
            ("event_time", self.event_time),
            ("effective_from", self.effective_from),
            ("available_at", self.available_at),
            ("recorded_at", self.recorded_at),
        ):
            require_utc_second(label, timestamp)
        if self.effective_to is not None:
            require_utc_second("effective_to", self.effective_to)
            if self.effective_to <= self.effective_from:
                raise ValueError("effective_to must follow effective_from")
        if self.available_at < self.event_time:
            raise ValueError("PIT fact became available before event")
        if self.recorded_at < self.available_at:
            raise ValueError("PIT fact was recorded before available")
        _require_canonical_json(self.value_json)
        if canonical_hash(self.semantic_payload()) != self.content_hash:
            raise ValueError("PIT Fact Revision hash mismatch")
        if self.fact_id != _content_id("pit-fact", self.content_hash):
            raise ValueError("PIT Fact Revision identity mismatch")

    @classmethod
    def create(cls, **values: Any) -> PITFactRevision:
        digest = canonical_hash(_pit_fact_payload(**values))
        return cls(
            fact_id=_content_id("pit-fact", digest),
            content_hash=digest,
            **values,
        )

    def semantic_payload(self) -> dict[str, Any]:
        return _pit_fact_payload(
            scope_id=self.scope_id,
            logical_key=self.logical_key,
            fact_kind=self.fact_kind,
            subject=self.subject,
            revision=self.revision,
            supersedes_fact_id=self.supersedes_fact_id,
            event_time=self.event_time,
            effective_from=self.effective_from,
            effective_to=self.effective_to,
            available_at=self.available_at,
            recorded_at=self.recorded_at,
            artifact=self.artifact,
            source_manifest=self.source_manifest,
            provider_id=self.provider_id,
            provider_contract=self.provider_contract,
            value_json=self.value_json,
            data_eligibility=self.data_eligibility,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "fact_id": str(self.fact_id),
            "content_hash": self.content_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> PITFactRevision:
        expected = {
            "schema_version", "fact_id", "content_hash", "scope_id",
            "logical_key", "fact_kind", "subject", "revision",
            "supersedes_fact_id", "event_time", "effective_from",
            "effective_to", "available_at", "recorded_at", "artifact",
            "source_manifest", "provider_id", "provider_contract",
            "value_json", "data_eligibility",
        }
        _require_fields(payload, expected, "PIT Fact Revision")
        effective_to = payload["effective_to"]
        supersedes = payload["supersedes_fact_id"]
        return cls(
            fact_id=ArtifactId(_string(payload["fact_id"])),
            content_hash=_string(payload["content_hash"]),
            scope_id=_string(payload["scope_id"]),
            logical_key=_string(payload["logical_key"]),
            fact_kind=PITFactKind(_string(payload["fact_kind"])),
            subject=_string(payload["subject"]),
            revision=_integer(payload["revision"]),
            supersedes_fact_id=(ArtifactId(_string(supersedes)) if supersedes is not None else None),
            event_time=parse_utc_second("event_time", payload["event_time"]),
            effective_from=parse_utc_second("effective_from", payload["effective_from"]),
            effective_to=(parse_utc_second("effective_to", effective_to) if effective_to is not None else None),
            available_at=parse_utc_second("available_at", payload["available_at"]),
            recorded_at=parse_utc_second("recorded_at", payload["recorded_at"]),
            artifact=PITArtifactReference.from_canonical_dict(_mapping(payload["artifact"])),
            source_manifest=PITArtifactReference.from_canonical_dict(_mapping(payload["source_manifest"])),
            provider_id=_string(payload["provider_id"]),
            provider_contract=_string(payload["provider_contract"]),
            value_json=_string(payload["value_json"]),
            data_eligibility=DataEligibility(_string(payload["data_eligibility"])),
            schema_version=_string(payload["schema_version"]),
        )


@dataclass(frozen=True, slots=True)
class RecordedPITFactRevision:
    fact: PITFactRevision
    authority_revision: int
    ingested_at: datetime

    def __post_init__(self) -> None:
        if isinstance(self.authority_revision, bool) or self.authority_revision <= 0:
            raise ValueError("authority_revision must be positive")
        require_utc_second("ingested_at", self.ingested_at)

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "fact": self.fact.to_canonical_dict(),
            "authority_revision": self.authority_revision,
            "ingested_at": canonical_datetime(self.ingested_at),
        }


@dataclass(frozen=True, slots=True)
class PITRequiredFact:
    logical_key: str
    fact_kind: PITFactKind
    subject: str

    def __post_init__(self) -> None:
        require_text("logical_key", self.logical_key)
        require_text("subject", self.subject)

    def to_canonical_dict(self) -> dict[str, str]:
        return {
            "logical_key": self.logical_key,
            "fact_kind": self.fact_kind.value,
            "subject": self.subject,
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> PITRequiredFact:
        _require_fields(payload, {"logical_key", "fact_kind", "subject"}, "PIT Required Fact")
        return cls(
            logical_key=_string(payload["logical_key"]),
            fact_kind=PITFactKind(_string(payload["fact_kind"])),
            subject=_string(payload["subject"]),
        )


@dataclass(frozen=True, slots=True)
class PITValidationLineage:
    model_id: ModelId
    definition_hash: str
    model_lineage_id: ArtifactId
    model_lineage_hash: str
    dataset: PITArtifactReference
    source_manifests: tuple[PITArtifactReference, ...]
    universe: PITArtifactReference
    eligibility: PITArtifactReference
    feature_definition_ids: tuple[str, ...]
    feature_materializations: tuple[PITArtifactReference, ...]
    configuration: PITArtifactReference
    code_revision: str
    code_hash: str
    validation_protocol: PITArtifactReference
    adjustment_mode: str

    def __post_init__(self) -> None:
        if len(self.definition_hash) != 64 or any(
            character not in "0123456789abcdef" for character in self.definition_hash
        ):
            raise ValueError("definition_hash must be a lowercase SHA-256 digest")
        require_sha256("model_lineage_hash", self.model_lineage_hash)
        require_sha256("code_hash", self.code_hash)
        require_text("code_revision", self.code_revision)
        if self.adjustment_mode not in {"RAW", "PIT_ADJUSTED", "RESEARCH_BACK_ADJUSTED"}:
            raise ValueError("unsupported adjustment_mode")
        _ordered_references("source_manifests", self.source_manifests, required=True)
        _ordered_references("feature_materializations", self.feature_materializations, required=True)
        if self.feature_definition_ids != tuple(sorted(set(self.feature_definition_ids))):
            raise ValueError("feature_definition_ids must be sorted and unique")
        if len(self.feature_definition_ids) != len(self.feature_materializations):
            raise ValueError("feature definitions/materializations must align")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "model_id": str(self.model_id),
            "definition_hash": self.definition_hash,
            "model_lineage_id": str(self.model_lineage_id),
            "model_lineage_hash": self.model_lineage_hash,
            "dataset": self.dataset.to_canonical_dict(),
            "source_manifests": [item.to_canonical_dict() for item in self.source_manifests],
            "universe": self.universe.to_canonical_dict(),
            "eligibility": self.eligibility.to_canonical_dict(),
            "feature_definition_ids": list(self.feature_definition_ids),
            "feature_materializations": [item.to_canonical_dict() for item in self.feature_materializations],
            "configuration": self.configuration.to_canonical_dict(),
            "code_revision": self.code_revision,
            "code_hash": self.code_hash,
            "validation_protocol": self.validation_protocol.to_canonical_dict(),
            "adjustment_mode": self.adjustment_mode,
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> PITValidationLineage:
        expected = {
            "model_id", "definition_hash", "model_lineage_id",
            "model_lineage_hash", "dataset", "source_manifests", "universe",
            "eligibility", "feature_definition_ids", "feature_materializations",
            "configuration", "code_revision", "code_hash",
            "validation_protocol", "adjustment_mode",
        }
        _require_fields(payload, expected, "PIT Validation Lineage")
        return cls(
            model_id=ModelId(_string(payload["model_id"])),
            definition_hash=_string(payload["definition_hash"]),
            model_lineage_id=ArtifactId(_string(payload["model_lineage_id"])),
            model_lineage_hash=_string(payload["model_lineage_hash"]),
            dataset=PITArtifactReference.from_canonical_dict(_mapping(payload["dataset"])),
            source_manifests=tuple(PITArtifactReference.from_canonical_dict(_mapping(item)) for item in _sequence(payload["source_manifests"])),
            universe=PITArtifactReference.from_canonical_dict(_mapping(payload["universe"])),
            eligibility=PITArtifactReference.from_canonical_dict(_mapping(payload["eligibility"])),
            feature_definition_ids=tuple(_string(item) for item in _sequence(payload["feature_definition_ids"])),
            feature_materializations=tuple(PITArtifactReference.from_canonical_dict(_mapping(item)) for item in _sequence(payload["feature_materializations"])),
            configuration=PITArtifactReference.from_canonical_dict(_mapping(payload["configuration"])),
            code_revision=_string(payload["code_revision"]),
            code_hash=_string(payload["code_hash"]),
            validation_protocol=PITArtifactReference.from_canonical_dict(_mapping(payload["validation_protocol"])),
            adjustment_mode=_string(payload["adjustment_mode"]),
        )


@dataclass(frozen=True, slots=True)
class FormalPITValidationRequest:
    request_hash: str
    scope_id: str
    decision_time: datetime
    symbols: tuple[str, ...]
    required_facts: tuple[PITRequiredFact, ...]
    lineage: PITValidationLineage
    actor: str
    reason: str
    idempotency_key: str
    schema_version: str = "formal-pit-validation-request-v1"

    def __post_init__(self) -> None:
        if self.schema_version != "formal-pit-validation-request-v1":
            raise ValueError("unsupported Formal PIT Validation Request schema")
        require_sha256("request_hash", self.request_hash)
        require_text("scope_id", self.scope_id)
        require_text("actor", self.actor)
        require_text("reason", self.reason)
        require_text("idempotency_key", self.idempotency_key)
        require_utc_second("decision_time", self.decision_time)
        if not self.symbols or self.symbols != tuple(sorted(set(self.symbols))):
            raise ValueError("symbols must be non-empty, sorted and unique")
        ordered = tuple(sorted(set(self.required_facts), key=_required_fact_key))
        if self.required_facts != ordered:
            raise ValueError("required_facts must be sorted and unique")
        if canonical_hash(self.semantic_payload()) != self.request_hash:
            raise ValueError("Formal PIT Validation Request hash mismatch")

    @classmethod
    def create(cls, **values: Any) -> FormalPITValidationRequest:
        normalized = dict(values)
        normalized["symbols"] = tuple(sorted(set(values["symbols"])))
        normalized["required_facts"] = tuple(sorted(set(values["required_facts"]), key=_required_fact_key))
        digest = canonical_hash(_validation_request_payload(**normalized))
        return cls(request_hash=digest, **normalized)

    def semantic_payload(self) -> dict[str, Any]:
        return _validation_request_payload(
            scope_id=self.scope_id,
            decision_time=self.decision_time,
            symbols=self.symbols,
            required_facts=self.required_facts,
            lineage=self.lineage,
            actor=self.actor,
            reason=self.reason,
            idempotency_key=self.idempotency_key,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {"request_hash": self.request_hash, **self.semantic_payload()}

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> FormalPITValidationRequest:
        expected = {
            "schema_version", "request_hash", "scope_id", "decision_time",
            "symbols", "required_facts", "lineage", "actor", "reason",
            "idempotency_key",
        }
        _require_fields(payload, expected, "Formal PIT Validation Request")
        request = cls.create(
            scope_id=_string(payload["scope_id"]),
            decision_time=parse_utc_second("decision_time", payload["decision_time"]),
            symbols=tuple(_string(item) for item in _sequence(payload["symbols"])),
            required_facts=tuple(PITRequiredFact.from_canonical_dict(_mapping(item)) for item in _sequence(payload["required_facts"])),
            lineage=PITValidationLineage.from_canonical_dict(_mapping(payload["lineage"])),
            actor=_string(payload["actor"]),
            reason=_string(payload["reason"]),
            idempotency_key=_string(payload["idempotency_key"]),
        )
        if request.request_hash != payload["request_hash"]:
            raise ValueError("Formal PIT Validation Request stored identity mismatch")
        return request


@dataclass(frozen=True, slots=True)
class PITAsOfQuery:
    query_hash: str
    scope_id: str
    decision_time: datetime
    required_facts: tuple[PITRequiredFact, ...]
    authority_revision: int | None = None

    @classmethod
    def create(
        cls,
        *,
        scope_id: str,
        decision_time: datetime,
        required_facts: tuple[PITRequiredFact, ...],
        authority_revision: int | None = None,
    ) -> PITAsOfQuery:
        require_text("scope_id", scope_id)
        require_utc_second("decision_time", decision_time)
        ordered = tuple(sorted(set(required_facts), key=_required_fact_key))
        if authority_revision is not None and (isinstance(authority_revision, bool) or authority_revision <= 0):
            raise ValueError("authority_revision must be positive")
        payload = {
            "schema_version": "pit-as-of-query-v1",
            "scope_id": scope_id,
            "decision_time": canonical_datetime(decision_time),
            "required_facts": [item.to_canonical_dict() for item in ordered],
            "authority_revision": authority_revision,
        }
        return cls(canonical_hash(payload), scope_id, decision_time, ordered, authority_revision)


@dataclass(frozen=True, slots=True)
class PITAsOfSnapshot:
    snapshot_id: ArtifactId
    snapshot_hash: str
    query_hash: str
    scope_id: str
    decision_time: datetime
    authority_revision: int
    outcome: PITValidationOutcome
    selected_fact_references: tuple[tuple[ArtifactId, str], ...]
    rejection_codes: tuple[str, ...]
    schema_version: str = "pit-as-of-snapshot-v1"

    @classmethod
    def create(cls, **values: Any) -> PITAsOfSnapshot:
        normalized = dict(values)
        normalized["selected_fact_references"] = tuple(sorted(set(values["selected_fact_references"]), key=lambda item: str(item[0])))
        normalized["rejection_codes"] = tuple(sorted(set(values["rejection_codes"])))
        digest = canonical_hash(_snapshot_payload(**normalized))
        return cls(_content_id("pit-as-of-snapshot", digest), digest, **normalized)

    def __post_init__(self) -> None:
        require_sha256("snapshot_hash", self.snapshot_hash)
        require_sha256("query_hash", self.query_hash)
        require_text("scope_id", self.scope_id)
        require_utc_second("decision_time", self.decision_time)
        if self.authority_revision <= 0:
            raise ValueError("authority_revision must be positive")
        if (self.outcome is PITValidationOutcome.SATISFIED) != (not self.rejection_codes):
            raise ValueError("snapshot outcome/rejection mismatch")
        for _, item_hash in self.selected_fact_references:
            require_sha256("selected fact hash", item_hash)
        if canonical_hash(self.semantic_payload()) != self.snapshot_hash:
            raise ValueError("PIT As-Of Snapshot hash mismatch")
        if self.snapshot_id != _content_id("pit-as-of-snapshot", self.snapshot_hash):
            raise ValueError("PIT As-Of Snapshot identity mismatch")

    def semantic_payload(self) -> dict[str, Any]:
        return _snapshot_payload(
            query_hash=self.query_hash,
            scope_id=self.scope_id,
            decision_time=self.decision_time,
            authority_revision=self.authority_revision,
            outcome=self.outcome,
            selected_fact_references=self.selected_fact_references,
            rejection_codes=self.rejection_codes,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {"snapshot_id": str(self.snapshot_id), "snapshot_hash": self.snapshot_hash, **self.semantic_payload()}

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> PITAsOfSnapshot:
        refs = tuple((ArtifactId(_string(item["fact_id"])), _string(item["content_hash"])) for item in _sequence(payload["selected_fact_references"]))
        return cls(
            snapshot_id=ArtifactId(_string(payload["snapshot_id"])),
            snapshot_hash=_string(payload["snapshot_hash"]),
            query_hash=_string(payload["query_hash"]),
            scope_id=_string(payload["scope_id"]),
            decision_time=parse_utc_second("decision_time", payload["decision_time"]),
            authority_revision=_integer(payload["authority_revision"]),
            outcome=PITValidationOutcome(_string(payload["outcome"])),
            selected_fact_references=refs,
            rejection_codes=tuple(_string(item) for item in _sequence(payload["rejection_codes"])),
            schema_version=_string(payload["schema_version"]),
        )


@dataclass(frozen=True, slots=True)
class FormalPITEvidenceArtifact:
    evidence_id: ArtifactId
    evidence_hash: str
    request_hash: str
    snapshot_id: ArtifactId
    snapshot_hash: str
    authority_revision: int
    lineage: PITValidationLineage
    outcome: PITValidationOutcome
    rejection_codes: tuple[str, ...]
    selected_fact_references: tuple[tuple[ArtifactId, str], ...]
    available_at: datetime
    recorded_at: datetime
    actor: str
    reason: str
    schema_version: str = "formal-pit-evidence-v1"

    @classmethod
    def create(cls, **values: Any) -> FormalPITEvidenceArtifact:
        normalized = dict(values)
        normalized["rejection_codes"] = tuple(sorted(set(values["rejection_codes"])))
        normalized["selected_fact_references"] = tuple(sorted(set(values["selected_fact_references"]), key=lambda item: str(item[0])))
        digest = canonical_hash(_evidence_payload(**normalized))
        return cls(_content_id("formal-pit-evidence", digest), digest, **normalized)

    def __post_init__(self) -> None:
        require_sha256("evidence_hash", self.evidence_hash)
        require_sha256("request_hash", self.request_hash)
        require_sha256("snapshot_hash", self.snapshot_hash)
        if self.authority_revision <= 0:
            raise ValueError("authority_revision must be positive")
        require_utc_second("available_at", self.available_at)
        require_utc_second("recorded_at", self.recorded_at)
        if self.recorded_at < self.available_at:
            raise ValueError("Formal PIT evidence recorded before available")
        require_text("actor", self.actor)
        require_text("reason", self.reason)
        if (self.outcome is PITValidationOutcome.SATISFIED) != (not self.rejection_codes):
            raise ValueError("Formal PIT evidence outcome/rejection mismatch")
        if canonical_hash(self.semantic_payload()) != self.evidence_hash:
            raise ValueError("Formal PIT Evidence hash mismatch")
        if self.evidence_id != _content_id("formal-pit-evidence", self.evidence_hash):
            raise ValueError("Formal PIT Evidence identity mismatch")

    def semantic_payload(self) -> dict[str, Any]:
        return _evidence_payload(
            request_hash=self.request_hash,
            snapshot_id=self.snapshot_id,
            snapshot_hash=self.snapshot_hash,
            authority_revision=self.authority_revision,
            lineage=self.lineage,
            outcome=self.outcome,
            rejection_codes=self.rejection_codes,
            selected_fact_references=self.selected_fact_references,
            available_at=self.available_at,
            recorded_at=self.recorded_at,
            actor=self.actor,
            reason=self.reason,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {"evidence_id": str(self.evidence_id), "evidence_hash": self.evidence_hash, **self.semantic_payload()}

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> FormalPITEvidenceArtifact:
        refs = tuple((ArtifactId(_string(item["fact_id"])), _string(item["content_hash"])) for item in _sequence(payload["selected_fact_references"]))
        return cls(
            evidence_id=ArtifactId(_string(payload["evidence_id"])),
            evidence_hash=_string(payload["evidence_hash"]),
            request_hash=_string(payload["request_hash"]),
            snapshot_id=ArtifactId(_string(payload["snapshot_id"])),
            snapshot_hash=_string(payload["snapshot_hash"]),
            authority_revision=_integer(payload["authority_revision"]),
            lineage=PITValidationLineage.from_canonical_dict(_mapping(payload["lineage"])),
            outcome=PITValidationOutcome(_string(payload["outcome"])),
            rejection_codes=tuple(_string(item) for item in _sequence(payload["rejection_codes"])),
            selected_fact_references=refs,
            available_at=parse_utc_second("available_at", payload["available_at"]),
            recorded_at=parse_utc_second("recorded_at", payload["recorded_at"]),
            actor=_string(payload["actor"]),
            reason=_string(payload["reason"]),
            schema_version=_string(payload["schema_version"]),
        )


def formal_pit_request_rejection_codes(request: FormalPITValidationRequest) -> tuple[str, ...]:
    reasons: set[str] = set()
    by_subject_kind = {(item.subject, item.fact_kind) for item in request.required_facts}
    for symbol in request.symbols:
        for kind in (
            PITFactKind.MARKET_DATA,
            PITFactKind.UNIVERSE_MEMBERSHIP,
            PITFactKind.TRADING_STATUS,
            PITFactKind.ST_STATUS,
            PITFactKind.LISTING_STATUS,
            PITFactKind.TRADING_ELIGIBILITY,
        ):
            if (symbol, kind) not in by_subject_kind:
                reasons.add(f"{kind.value}_COVERAGE_MISSING:{symbol}")
    if not any(item.fact_kind is PITFactKind.TRADING_CALENDAR for item in request.required_facts):
        reasons.add("TRADING_CALENDAR_COVERAGE_MISSING")
    feature_count = sum(item.fact_kind is PITFactKind.FEATURE_MATERIALIZATION for item in request.required_facts)
    if feature_count < len(request.lineage.feature_materializations):
        reasons.add("FEATURE_MATERIALIZATION_COVERAGE_MISSING")
    if request.lineage.adjustment_mode == "PIT_ADJUSTED" and not any(
        item.fact_kind is PITFactKind.ADJUSTMENT_FACTOR for item in request.required_facts
    ):
        reasons.add("ADJUSTMENT_FACTOR_COVERAGE_MISSING")
    if request.lineage.adjustment_mode == "RESEARCH_BACK_ADJUSTED":
        reasons.add("RESEARCH_BACK_ADJUSTED_NOT_PIT_SAFE")
    return tuple(sorted(reasons))


def _source_qualification_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": "pit-source-qualification-v1",
        "source_manifest": values["source_manifest"].to_canonical_dict(),
        "provider_id": values["provider_id"],
        "provider_contract": values["provider_contract"],
        "status": values["status"].value,
        "evidence_references": [
            item.to_canonical_dict() for item in values["evidence_references"]
        ],
        "revision": values["revision"],
        "supersedes_qualification_id": (
            str(values["supersedes_qualification_id"])
            if values["supersedes_qualification_id"] is not None
            else None
        ),
        "effective_at": canonical_datetime(values["effective_at"]),
        "recorded_at": canonical_datetime(values["recorded_at"]),
        "actor": values["actor"],
        "reason": values["reason"],
    }


def _pit_fact_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": "pit-fact-revision-v1",
        "scope_id": values["scope_id"],
        "logical_key": values["logical_key"],
        "fact_kind": values["fact_kind"].value,
        "subject": values["subject"],
        "revision": values["revision"],
        "supersedes_fact_id": str(values["supersedes_fact_id"]) if values["supersedes_fact_id"] is not None else None,
        "event_time": canonical_datetime(values["event_time"]),
        "effective_from": canonical_datetime(values["effective_from"]),
        "effective_to": canonical_datetime(values["effective_to"]) if values["effective_to"] is not None else None,
        "available_at": canonical_datetime(values["available_at"]),
        "recorded_at": canonical_datetime(values["recorded_at"]),
        "artifact": values["artifact"].to_canonical_dict(),
        "source_manifest": values["source_manifest"].to_canonical_dict(),
        "provider_id": values["provider_id"],
        "provider_contract": values["provider_contract"],
        "value_json": values["value_json"],
        "data_eligibility": values["data_eligibility"].value,
    }


def _validation_request_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": "formal-pit-validation-request-v1",
        "scope_id": values["scope_id"],
        "decision_time": canonical_datetime(values["decision_time"]),
        "symbols": list(values["symbols"]),
        "required_facts": [item.to_canonical_dict() for item in values["required_facts"]],
        "lineage": values["lineage"].to_canonical_dict(),
        "actor": values["actor"],
        "reason": values["reason"],
        "idempotency_key": values["idempotency_key"],
    }


def _snapshot_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": "pit-as-of-snapshot-v1",
        "query_hash": values["query_hash"],
        "scope_id": values["scope_id"],
        "decision_time": canonical_datetime(values["decision_time"]),
        "authority_revision": values["authority_revision"],
        "outcome": values["outcome"].value,
        "selected_fact_references": [
            {"fact_id": str(item_id), "content_hash": item_hash}
            for item_id, item_hash in values["selected_fact_references"]
        ],
        "rejection_codes": list(values["rejection_codes"]),
    }


def _evidence_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": "formal-pit-evidence-v1",
        "request_hash": values["request_hash"],
        "snapshot_id": str(values["snapshot_id"]),
        "snapshot_hash": values["snapshot_hash"],
        "authority_revision": values["authority_revision"],
        "lineage": values["lineage"].to_canonical_dict(),
        "outcome": values["outcome"].value,
        "rejection_codes": list(values["rejection_codes"]),
        "selected_fact_references": [
            {"fact_id": str(item_id), "content_hash": item_hash}
            for item_id, item_hash in values["selected_fact_references"]
        ],
        "available_at": canonical_datetime(values["available_at"]),
        "recorded_at": canonical_datetime(values["recorded_at"]),
        "actor": values["actor"],
        "reason": values["reason"],
    }


def _content_id(prefix: str, content_hash: str) -> ArtifactId:
    return ArtifactId(f"{prefix}-{content_hash.split(':', 1)[1][:24]}")


def _required_fact_key(item: PITRequiredFact) -> tuple[str, str, str]:
    return item.fact_kind.value, item.subject, item.logical_key


def _ordered_references(label: str, values: tuple[PITArtifactReference, ...], *, required: bool) -> None:
    ordered = tuple(sorted(set(values), key=_reference_key))
    if values != ordered or (required and not values):
        raise ValueError(f"{label} must be non-empty, sorted and unique")


def _reference_key(item: PITArtifactReference) -> tuple[str, str, str]:
    return item.reference_kind, str(item.artifact_id), item.content_hash


def _require_canonical_json(value: str) -> None:
    require_text("value_json", value)
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError("value_json must be canonical JSON") from exc
    canonical = json.dumps(parsed, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if value != canonical:
        raise ValueError("value_json must be canonical JSON")


def _require_fields(payload: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(payload) != expected:
        raise ValueError(f"{label} fields mismatch")


def _string(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("expected string")
    return value


def _integer(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("expected integer")
    return value


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("expected object")
    return value


def _sequence(value: object) -> tuple[Any, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError("expected array")
    return tuple(value)


__all__ = [
    "FormalPITEvidenceArtifact",
    "FormalPITValidationRequest",
    "PITArtifactReference",
    "PITAsOfQuery",
    "PITAsOfSnapshot",
    "PITFactKind",
    "PITFactRevision",
    "PITRequiredFact",
    "PITSourceAuthorityStatus",
    "PITSourceQualification",
    "PITValidationLineage",
    "PITValidationOutcome",
    "RecordedPITFactRevision",
    "formal_pit_request_rejection_codes",
]
