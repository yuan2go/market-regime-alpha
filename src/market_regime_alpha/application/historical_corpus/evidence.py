"""Immutable PostgreSQL-owned Phase E research evidence contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping

from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    require_sha256,
    require_text,
)
from market_regime_alpha.market_data.contracts import parse_utc_second, require_utc_second


class HistoricalEvidenceKind(str, Enum):
    CORPUS_SUMMARY = "CORPUS_SUMMARY"
    ALPHA_ABLATION = "ALPHA_ABLATION"
    STRATEGY_ECONOMICS = "STRATEGY_ECONOMICS"
    PORTFOLIO_PERFORMANCE = "PORTFOLIO_PERFORMANCE"
    EXPLORATORY_MODEL = "EXPLORATORY_MODEL"
    METHODOLOGY_ASSESSMENT = "METHODOLOGY_ASSESSMENT"
    ALPHA_CORRECTNESS = "ALPHA_CORRECTNESS"
    EXTERNAL_VALIDATION = "EXTERNAL_VALIDATION"
    CONTEXT_CONDITIONAL = "CONTEXT_CONDITIONAL"
    CANDIDATE_POLICY = "CANDIDATE_POLICY"
    CONDITIONAL_PREDICTION = "CONDITIONAL_PREDICTION"


class ResearchStatementKind(str, Enum):
    FACT = "FACT"
    MODEL_ASSUMPTION = "MODEL_ASSUMPTION"
    RESEARCH_RESULT = "RESEARCH_RESULT"
    INFERENCE = "INFERENCE"
    LIMITATION = "LIMITATION"
    INVALIDATION_CONDITION = "INVALIDATION_CONDITION"


@dataclass(frozen=True, slots=True)
class ResearchStatement:
    statement_kind: ResearchStatementKind
    text: str

    def __post_init__(self) -> None:
        require_text("Research statement", self.text)

    def to_canonical_dict(self) -> dict[str, str]:
        return {"statement_kind": self.statement_kind.value, "text": self.text}

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> ResearchStatement:
        return cls(
            ResearchStatementKind(str(payload["statement_kind"])),
            str(payload["text"]),
        )


class ResearchFinding(str, Enum):
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    INCONCLUSIVE = "INCONCLUSIVE"
    NOT_ESTIMABLE = "NOT_ESTIMABLE"


class EvidenceMetricStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    NOT_ESTIMABLE = "NOT_ESTIMABLE"


class MetricAssumptionStatus(str, Enum):
    EMPIRICAL = "EMPIRICAL"
    ENGINEERING_ASSUMPTION = "ENGINEERING_ASSUMPTION"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True, slots=True)
class HistoricalEvidenceMetric:
    variant_id: str
    slice_kind: str
    slice_value: str
    metric_name: str
    metric_value: Decimal | None
    metric_status: EvidenceMetricStatus
    assumption_status: MetricAssumptionStatus

    def __post_init__(self) -> None:
        for label, value in (
            ("variant_id", self.variant_id),
            ("slice_kind", self.slice_kind),
            ("slice_value", self.slice_value),
            ("metric_name", self.metric_name),
        ):
            require_text(label, value)
        if (self.metric_value is not None) != (
            self.metric_status is EvidenceMetricStatus.AVAILABLE
        ):
            raise ValueError("Historical Evidence metric status/value mismatch")
        if self.metric_value is not None and not self.metric_value.is_finite():
            raise ValueError("Historical Evidence metric must be finite")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "variant_id": self.variant_id,
            "slice_kind": self.slice_kind,
            "slice_value": self.slice_value,
            "metric_name": self.metric_name,
            "metric_value": (
                None if self.metric_value is None else str(self.metric_value)
            ),
            "metric_status": self.metric_status.value,
            "assumption_status": self.assumption_status.value,
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> HistoricalEvidenceMetric:
        return cls(
            variant_id=str(payload["variant_id"]),
            slice_kind=str(payload["slice_kind"]),
            slice_value=str(payload["slice_value"]),
            metric_name=str(payload["metric_name"]),
            metric_value=(
                None
                if payload["metric_value"] is None
                else Decimal(str(payload["metric_value"]))
            ),
            metric_status=EvidenceMetricStatus(str(payload["metric_status"])),
            assumption_status=MetricAssumptionStatus(
                str(payload["assumption_status"])
            ),
        )


@dataclass(frozen=True, slots=True)
class HistoricalResearchEvidence:
    evidence_id: ArtifactId
    evidence_hash: str
    run_id: ArtifactId
    command_hash: str
    experiment_reference: ValidationArtifactReference
    evidence_kind: HistoricalEvidenceKind
    research_question: str
    classification: ResearchFinding
    rationale: str
    source_references: tuple[ValidationArtifactReference, ...]
    metrics: tuple[HistoricalEvidenceMetric, ...]
    payload: Mapping[str, Any]
    created_at: datetime
    limitations: tuple[str, ...]
    statements: tuple[ResearchStatement, ...] = ()
    schema_version: str = "historical-research-evidence/v2"

    def __post_init__(self) -> None:
        require_sha256("evidence_hash", self.evidence_hash)
        require_sha256("command_hash", self.command_hash)
        require_text("research_question", self.research_question)
        require_text("rationale", self.rationale)
        require_utc_second("created_at", self.created_at)
        if self.experiment_reference.artifact_kind != "RESEARCH_EXPERIMENT_DEFINITION":
            raise ValueError("Historical Evidence requires one Experiment owner")
        if self.source_references != _references(self.source_references):
            raise ValueError("Historical Evidence sources must be unique and sorted")
        if not self.source_references:
            raise ValueError("Historical Evidence requires owner sources")
        metric_keys = tuple(_metric_key(item) for item in self.metrics)
        if metric_keys != tuple(sorted(set(metric_keys))):
            raise ValueError("Historical Evidence metrics must be unique and sorted")
        if self.limitations != tuple(sorted(set(self.limitations))):
            raise ValueError("Historical Evidence limitations must be unique and sorted")
        required = {
            "CALIBRATED_FALSE",
            "EXPLORATORY",
            "FORMAL_MODEL_QUALIFIED_FALSE",
            "FORMAL_OOS_FALSE",
            "PIT_INCOMPLETE",
        }
        if not required.issubset(self.limitations):
            raise ValueError("Historical Evidence ceiling is incomplete")
        if self.schema_version not in {
            "historical-research-evidence/v1",
            "historical-research-evidence/v2",
        }:
            raise ValueError("unsupported Historical Evidence schema")
        statement_keys = tuple(
            (item.statement_kind.value, item.text) for item in self.statements
        )
        if statement_keys != tuple(sorted(set(statement_keys))):
            raise ValueError("Historical Evidence statements must be unique and sorted")
        if self.schema_version == "historical-research-evidence/v2" and not self.statements:
            raise ValueError("Historical Evidence V2 requires typed statements")
        self.verify_identity()

    @classmethod
    def create(
        cls,
        *,
        run_id: ArtifactId,
        command_hash: str,
        experiment_reference: ValidationArtifactReference,
        evidence_kind: HistoricalEvidenceKind,
        research_question: str,
        classification: ResearchFinding,
        rationale: str,
        source_references: tuple[ValidationArtifactReference, ...],
        metrics: tuple[HistoricalEvidenceMetric, ...],
        payload: Mapping[str, Any],
        created_at: datetime,
        limitations: tuple[str, ...] = (),
        statements: tuple[ResearchStatement, ...] = (),
    ) -> HistoricalResearchEvidence:
        ordered_metrics = tuple(sorted(metrics, key=_metric_key))
        ordered_limitations = tuple(
            sorted(
                {
                    *limitations,
                    "CALIBRATED_FALSE",
                    "EXPLORATORY",
                    "FORMAL_MODEL_QUALIFIED_FALSE",
                    "FORMAL_OOS_FALSE",
                    "PIT_INCOMPLETE",
                }
            )
        )
        ordered_sources = _references(source_references)
        ordered_statements = tuple(
            sorted(
                {
                    *statements,
                    ResearchStatement(ResearchStatementKind.RESEARCH_RESULT, rationale),
                    *(
                        ResearchStatement(ResearchStatementKind.LIMITATION, item)
                        for item in ordered_limitations
                    ),
                },
                key=lambda item: (item.statement_kind.value, item.text),
            )
        )
        canonical_payload = dict(payload)
        values = {
            "run_id": run_id,
            "command_hash": command_hash,
            "experiment_reference": experiment_reference,
            "evidence_kind": evidence_kind,
            "research_question": research_question,
            "classification": classification,
            "rationale": rationale,
            "source_references": ordered_sources,
            "metrics": ordered_metrics,
            "payload": canonical_payload,
            "created_at": created_at,
            "limitations": ordered_limitations,
            "statements": ordered_statements,
            "schema_version": "historical-research-evidence/v2",
        }
        digest = canonical_hash(_payload(**values))
        return cls(
            evidence_id=ArtifactId(f"historical-evidence-{digest[7:31]}"),
            evidence_hash=digest,
            run_id=run_id,
            command_hash=command_hash,
            experiment_reference=experiment_reference,
            evidence_kind=evidence_kind,
            research_question=research_question,
            classification=classification,
            rationale=rationale,
            source_references=ordered_sources,
            metrics=ordered_metrics,
            payload=canonical_payload,
            created_at=created_at,
            limitations=ordered_limitations,
            statements=ordered_statements,
        )

    @property
    def reference(self) -> ValidationArtifactReference:
        return ValidationArtifactReference(
            f"HISTORICAL_{self.evidence_kind.value}_EVIDENCE",
            self.evidence_id,
            self.evidence_hash,
        )

    def semantic_payload(self) -> dict[str, Any]:
        return _payload(
            run_id=self.run_id,
            command_hash=self.command_hash,
            experiment_reference=self.experiment_reference,
            evidence_kind=self.evidence_kind,
            research_question=self.research_question,
            classification=self.classification,
            rationale=self.rationale,
            source_references=self.source_references,
            metrics=self.metrics,
            payload=self.payload,
            created_at=self.created_at,
            limitations=self.limitations,
            statements=self.statements,
            schema_version=self.schema_version,
        )

    def verify_identity(self) -> None:
        digest = canonical_hash(self.semantic_payload())
        if digest != self.evidence_hash:
            raise ValueError("Historical Evidence hash mismatch")
        if str(self.evidence_id) != f"historical-evidence-{digest[7:31]}":
            raise ValueError("Historical Evidence identity mismatch")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": str(self.evidence_id),
            "evidence_hash": self.evidence_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> HistoricalResearchEvidence:
        raw_payload = payload["payload"]
        if not isinstance(raw_payload, Mapping):
            raise ValueError("Historical Evidence payload must be an object")
        return cls(
            evidence_id=ArtifactId(str(payload["evidence_id"])),
            evidence_hash=str(payload["evidence_hash"]),
            run_id=ArtifactId(str(payload["run_id"])),
            command_hash=str(payload["command_hash"]),
            experiment_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(payload["experiment_reference"])
            ),
            evidence_kind=HistoricalEvidenceKind(str(payload["evidence_kind"])),
            research_question=str(payload["research_question"]),
            classification=ResearchFinding(str(payload["classification"])),
            rationale=str(payload["rationale"]),
            source_references=tuple(
                ValidationArtifactReference.from_canonical_dict(item)
                for item in _objects(payload["source_references"])
            ),
            metrics=tuple(
                HistoricalEvidenceMetric.from_canonical_dict(item)
                for item in _objects(payload["metrics"])
            ),
            payload=dict(raw_payload),
            created_at=parse_utc_second("created_at", payload["created_at"]),
            limitations=_strings(payload["limitations"]),
            statements=tuple(
                ResearchStatement.from_canonical_dict(item)
                for item in _objects(payload.get("statements", []))
            ),
            schema_version=str(payload["schema_version"]),
        )


def _payload(**values: Any) -> dict[str, Any]:
    schema_version = str(
        values.get("schema_version", "historical-research-evidence/v2")
    )
    payload = {
        "schema_version": schema_version,
        "run_id": str(values["run_id"]),
        "command_hash": values["command_hash"],
        "experiment_reference": values["experiment_reference"].to_canonical_dict(),
        "evidence_kind": values["evidence_kind"].value,
        "research_question": values["research_question"],
        "classification": values["classification"].value,
        "rationale": values["rationale"],
        "source_references": [
            item.to_canonical_dict() for item in values["source_references"]
        ],
        "metrics": [item.to_canonical_dict() for item in values["metrics"]],
        "payload": dict(values["payload"]),
        "created_at": canonical_datetime(values["created_at"]),
        "limitations": list(values["limitations"]),
    }
    if schema_version == "historical-research-evidence/v2":
        payload["statements"] = [
            item.to_canonical_dict() for item in values["statements"]
        ]
    return payload


def _metric_key(item: HistoricalEvidenceMetric) -> tuple[str, str, str, str]:
    return item.variant_id, item.slice_kind, item.slice_value, item.metric_name


def _references(
    values: tuple[ValidationArtifactReference, ...],
) -> tuple[ValidationArtifactReference, ...]:
    return tuple(
        sorted(
            set(values),
            key=lambda item: (
                item.artifact_kind,
                str(item.artifact_id),
                item.content_hash,
            ),
        )
    )


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("Historical Evidence value must be an object")
    return value


def _objects(value: object) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise ValueError("Historical Evidence value must be an object array")
    return tuple(value)


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError("Historical Evidence value must be a string array")
    return tuple(value)


__all__ = [
    "EvidenceMetricStatus",
    "HistoricalEvidenceKind",
    "HistoricalEvidenceMetric",
    "HistoricalResearchEvidence",
    "MetricAssumptionStatus",
    "ResearchFinding",
    "ResearchStatement",
    "ResearchStatementKind",
]
