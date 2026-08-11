"""Immutable C3/C4 qualification policies and owner decision contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping

from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
    content_identity,
    decimal_text,
    timestamp,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import (
    canonical_hash,
    require_sha256,
    require_text,
)


class QualificationOutcome(str, Enum):
    SATISFIED = "SATISFIED"
    REJECTED = "REJECTED"
    NOT_ESTIMABLE = "NOT_ESTIMABLE"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class FormalEvaluationObservationBinding:
    """Immutable owner references for one Formal Evaluation observation.

    Scores, labels, dates, symbols, and slice values are deliberately absent:
    the PostgreSQL qualification owner resolves them from these immutable
    Forecast/Outcome/Panel authorities instead of accepting caller values.
    """

    observation_id: str
    forecast_reference: ValidationArtifactReference
    label_reference: ValidationArtifactReference
    panel_slice_reference: ValidationArtifactReference
    panel_row_reference: ValidationArtifactReference
    schema_version: str = "formal-evaluation-observation-binding/v1"

    def __post_init__(self) -> None:
        if self.schema_version != "formal-evaluation-observation-binding/v1":
            raise ValueError("unsupported Formal Evaluation observation binding schema")
        expected_kinds = {
            "forecast_reference": "OUTCOME_TARGET_BOUND_FORECAST",
            "label_reference": "TARGET_OUTCOME_LABEL",
            "panel_slice_reference": "RESEARCH_PANEL_SLICE_V2",
            "panel_row_reference": "RESEARCH_PANEL_ROW_V2",
        }
        for name, kind in expected_kinds.items():
            if getattr(self, name).artifact_kind != kind:
                raise ValueError(f"Formal Evaluation {name} kind mismatch")
        digest = canonical_hash(self.identity_payload())
        if self.observation_id != f"formal-evaluation-observation:{digest[7:]}":
            raise ValueError("Formal Evaluation observation identity mismatch")

    @classmethod
    def create(
        cls,
        *,
        forecast_reference: ValidationArtifactReference,
        label_reference: ValidationArtifactReference,
        panel_slice_reference: ValidationArtifactReference,
        panel_row_reference: ValidationArtifactReference,
    ) -> FormalEvaluationObservationBinding:
        payload = _formal_evaluation_observation_binding_payload(
            forecast_reference=forecast_reference,
            label_reference=label_reference,
            panel_slice_reference=panel_slice_reference,
            panel_row_reference=panel_row_reference,
        )
        digest = canonical_hash(payload)
        return cls(
            observation_id=f"formal-evaluation-observation:{digest[7:]}",
            forecast_reference=forecast_reference,
            label_reference=label_reference,
            panel_slice_reference=panel_slice_reference,
            panel_row_reference=panel_row_reference,
        )

    def identity_payload(self) -> dict[str, Any]:
        return _formal_evaluation_observation_binding_payload(
            forecast_reference=self.forecast_reference,
            label_reference=self.label_reference,
            panel_slice_reference=self.panel_slice_reference,
            panel_row_reference=self.panel_row_reference,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {"observation_id": self.observation_id, **self.identity_payload()}

    @classmethod
    def from_canonical_dict(
        cls, value: Mapping[str, Any]
    ) -> FormalEvaluationObservationBinding:
        return cls(
            observation_id=str(value["observation_id"]),
            forecast_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(value["forecast_reference"])
            ),
            label_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(value["label_reference"])
            ),
            panel_slice_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(value["panel_slice_reference"])
            ),
            panel_row_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(value["panel_row_reference"])
            ),
            schema_version=str(value["schema_version"]),
        )


@dataclass(frozen=True, slots=True)
class LockedOOSEvidenceIdentity:
    """Semantic OOS identity that survives regenerated label/model artifacts."""

    dataset_reference: ValidationArtifactReference
    universe_reference: ValidationArtifactReference
    target_protocol_reference: ValidationArtifactReference
    target_reference: ValidationArtifactReference
    subject: str
    session_date: date
    label_end_date: date
    partition_kind: str = "LOCKED_OOS"
    schema_version: str = "locked-oos-evidence-identity/v2"

    def __post_init__(self) -> None:
        expected_kinds = (
            (self.dataset_reference, "MARKET_DATA_DATASET"),
            (self.universe_reference, "UNIVERSE"),
            (self.target_protocol_reference, "OUTCOME_TARGET_PROTOCOL"),
            (self.target_reference, "OUTCOME_TARGET"),
        )
        if any(item.artifact_kind != kind for item, kind in expected_kinds):
            raise ValueError("Locked OOS evidence owner kind mismatch")
        require_text("Locked OOS evidence subject", self.subject)
        if self.label_end_date < self.session_date:
            raise ValueError("Locked OOS evidence label ends before its session")
        if self.partition_kind != "LOCKED_OOS":
            raise ValueError("Locked OOS evidence partition cannot be weakened")
        if self.schema_version != "locked-oos-evidence-identity/v2":
            raise ValueError("unsupported Locked OOS evidence identity schema")

    @property
    def identity_hash(self) -> str:
        return canonical_hash(self.to_canonical_dict())

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_reference": self.dataset_reference.to_canonical_dict(),
            "universe_reference": self.universe_reference.to_canonical_dict(),
            "target_protocol_reference": (
                self.target_protocol_reference.to_canonical_dict()
            ),
            "target_reference": self.target_reference.to_canonical_dict(),
            "subject": self.subject,
            "session_date": self.session_date.isoformat(),
            "label_end_date": self.label_end_date.isoformat(),
            "partition_kind": self.partition_kind,
        }

    @classmethod
    def from_canonical_dict(
        cls, value: Mapping[str, Any]
    ) -> LockedOOSEvidenceIdentity:
        return cls(
            dataset_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(value["dataset_reference"])
            ),
            universe_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(value["universe_reference"])
            ),
            target_protocol_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(value["target_protocol_reference"])
            ),
            target_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(value["target_reference"])
            ),
            subject=str(value["subject"]),
            session_date=date.fromisoformat(str(value["session_date"])),
            label_end_date=date.fromisoformat(str(value["label_end_date"])),
            partition_kind=str(value["partition_kind"]),
            schema_version=str(value["schema_version"]),
        )


@dataclass(frozen=True, slots=True)
class FormalOOSMetricFloor:
    metric_name: str
    minimum_estimate: Decimal | None
    maximum_estimate: Decimal | None

    def __post_init__(self) -> None:
        if not self.metric_name.strip():
            raise ValueError("Formal OOS metric name must be non-empty")
        if self.minimum_estimate is None and self.maximum_estimate is None:
            raise ValueError("Formal OOS metric floor requires at least one bound")
        if (
            self.minimum_estimate is not None
            and self.maximum_estimate is not None
            and self.minimum_estimate > self.maximum_estimate
        ):
            raise ValueError("Formal OOS metric floor bounds are inverted")

    def to_canonical_dict(self) -> dict[str, str | None]:
        return {
            "metric_name": self.metric_name,
            "minimum_estimate": decimal_text(self.minimum_estimate),
            "maximum_estimate": decimal_text(self.maximum_estimate),
        }


@dataclass(frozen=True, slots=True)
class FormalOOSQualificationPolicy:
    policy_id: ArtifactId
    policy_hash: str
    policy_version: str
    metric_floors: tuple[FormalOOSMetricFloor, ...]
    minimum_sample_count: int
    maximum_adjusted_p_value: Decimal
    require_confidence_interval_excludes_zero: bool
    required_sensitivity_multipliers: tuple[Decimal, ...]
    locked_at: datetime
    schema_version: str = "formal-oos-qualification-policy/v1"

    def __post_init__(self) -> None:
        require_sha256("policy_hash", self.policy_hash)
        if self.schema_version != "formal-oos-qualification-policy/v1":
            raise ValueError("unsupported Formal OOS Qualification Policy schema")
        if not self.policy_version.strip() or self.minimum_sample_count <= 0:
            raise ValueError("Formal OOS Qualification Policy is invalid")
        if not Decimal("0") < self.maximum_adjusted_p_value <= Decimal("1"):
            raise ValueError("Formal OOS adjusted p-value ceiling is invalid")
        if self.metric_floors != tuple(
            sorted(self.metric_floors, key=lambda item: item.metric_name)
        ) or len({item.metric_name for item in self.metric_floors}) != len(
            self.metric_floors
        ):
            raise ValueError("Formal OOS metric floors must be unique and sorted")
        if not self.metric_floors:
            raise ValueError("Formal OOS Qualification Policy requires metric floors")
        if self.required_sensitivity_multipliers != tuple(
            sorted(set(self.required_sensitivity_multipliers))
        ) or Decimal("1") not in self.required_sensitivity_multipliers:
            raise ValueError(
                "Formal OOS sensitivity multipliers must be unique and include baseline"
            )
        if self.locked_at.tzinfo is None or self.locked_at.utcoffset() is None:
            raise ValueError("Formal OOS policy lock time must be timezone-aware")
        if canonical_hash(self.identity_payload()) != self.policy_hash:
            raise ValueError("Formal OOS Qualification Policy hash mismatch")
        if self.policy_id != ArtifactId(
            f"formal-oos-policy:{self.policy_hash[7:]}"
        ):
            raise ValueError("Formal OOS Qualification Policy identity mismatch")

    @classmethod
    def create(
        cls,
        *,
        policy_version: str,
        metric_floors: tuple[FormalOOSMetricFloor, ...],
        minimum_sample_count: int,
        maximum_adjusted_p_value: Decimal,
        require_confidence_interval_excludes_zero: bool,
        required_sensitivity_multipliers: tuple[Decimal, ...],
        locked_at: datetime,
    ) -> FormalOOSQualificationPolicy:
        floors = tuple(sorted(metric_floors, key=lambda item: item.metric_name))
        sensitivity = tuple(sorted(set(required_sensitivity_multipliers)))
        payload = _formal_oos_policy_payload(
            policy_version=policy_version,
            metric_floors=floors,
            minimum_sample_count=minimum_sample_count,
            maximum_adjusted_p_value=maximum_adjusted_p_value,
            require_confidence_interval_excludes_zero=require_confidence_interval_excludes_zero,
            required_sensitivity_multipliers=sensitivity,
            locked_at=locked_at,
        )
        policy_id, policy_hash = content_identity("formal-oos-policy", payload)
        return cls(
            policy_id,
            policy_hash,
            policy_version,
            floors,
            minimum_sample_count,
            maximum_adjusted_p_value,
            require_confidence_interval_excludes_zero,
            sensitivity,
            locked_at,
        )

    def identity_payload(self) -> dict[str, Any]:
        return _formal_oos_policy_payload(
            policy_version=self.policy_version,
            metric_floors=self.metric_floors,
            minimum_sample_count=self.minimum_sample_count,
            maximum_adjusted_p_value=self.maximum_adjusted_p_value,
            require_confidence_interval_excludes_zero=self.require_confidence_interval_excludes_zero,
            required_sensitivity_multipliers=self.required_sensitivity_multipliers,
            locked_at=self.locked_at,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "policy_id": str(self.policy_id),
            "policy_hash": self.policy_hash,
            **self.identity_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, value: Mapping[str, Any]
    ) -> FormalOOSQualificationPolicy:
        return cls(
            policy_id=ArtifactId(str(value["policy_id"])),
            policy_hash=str(value["policy_hash"]),
            policy_version=str(value["policy_version"]),
            metric_floors=tuple(
                FormalOOSMetricFloor(
                    metric_name=str(_mapping(item)["metric_name"]),
                    minimum_estimate=_optional_decimal(
                        _mapping(item)["minimum_estimate"]
                    ),
                    maximum_estimate=_optional_decimal(
                        _mapping(item)["maximum_estimate"]
                    ),
                )
                for item in _sequence(value["metric_floors"])
            ),
            minimum_sample_count=int(value["minimum_sample_count"]),
            maximum_adjusted_p_value=Decimal(
                str(value["maximum_adjusted_p_value"])
            ),
            require_confidence_interval_excludes_zero=bool(
                value["require_confidence_interval_excludes_zero"]
            ),
            required_sensitivity_multipliers=tuple(
                Decimal(str(item))
                for item in _sequence(value["required_sensitivity_multipliers"])
            ),
            locked_at=datetime.fromisoformat(str(value["locked_at"])),
            schema_version=str(value["schema_version"]),
        )


@dataclass(frozen=True, slots=True)
class HistoricalSampleQualificationDecision:
    decision_id: ArtifactId
    decision_hash: str
    dataset_reference: ValidationArtifactReference
    formal_protocol_reference: ValidationArtifactReference | None
    formal_pit_reference: ValidationArtifactReference | None
    formal_pit_references: tuple[ValidationArtifactReference, ...]
    provider_fact_decision_references: tuple[ValidationArtifactReference, ...]
    outcome: QualificationOutcome
    qualified: bool
    revision: int
    supersedes_decision_id: ArtifactId | None
    evaluated_at: datetime
    actor: str
    reason: str
    reason_codes: tuple[str, ...]
    formal_forecast_receipt_references: tuple[ValidationArtifactReference, ...] = ()
    schema_version: str = "historical-sample-qualification-decision/v1"

    def __post_init__(self) -> None:
        _validate_decision_common(
            decision_hash=self.decision_hash,
            outcome=self.outcome,
            passed=self.qualified,
            revision=self.revision,
            supersedes=self.supersedes_decision_id,
            evaluated_at=self.evaluated_at,
            actor=self.actor,
            reason=self.reason,
            reason_codes=self.reason_codes,
        )
        if self.dataset_reference.artifact_kind != "HISTORICAL_SAMPLE_DATASET":
            raise ValueError("Historical Sample decision requires Dataset authority")
        if self.formal_protocol_reference is not None and (
            self.formal_protocol_reference.artifact_kind != "FORMAL_RESEARCH_PROTOCOL"
        ):
            raise ValueError("Historical Sample decision Formal Protocol kind mismatch")
        if self.formal_pit_reference is not None and (
            self.formal_pit_reference.artifact_kind != "FORMAL_PIT_EVIDENCE"
        ):
            raise ValueError("Historical Sample decision Formal PIT kind mismatch")
        if self.formal_pit_references != _ordered_references(
            self.formal_pit_references
        ) or any(
            item.artifact_kind != "FORMAL_PIT_EVIDENCE"
            for item in self.formal_pit_references
        ):
            raise ValueError("Historical Sample decision Formal PIT set mismatch")
        if self.formal_pit_reference is None:
            if self.formal_pit_references:
                raise ValueError("Historical Sample primary PIT projection is missing")
        elif not self.formal_pit_references or self.formal_pit_reference != self.formal_pit_references[0]:
            raise ValueError("Historical Sample primary PIT projection mismatch")
        if self.provider_fact_decision_references != _ordered_references(
            self.provider_fact_decision_references
        ):
            raise ValueError("Provider Fact decisions must be unique and sorted")
        if self.formal_forecast_receipt_references != _ordered_references(
            self.formal_forecast_receipt_references
        ) or any(
            item.artifact_kind != "FORMAL_FORECAST_COMPUTATION_RECEIPT"
            for item in self.formal_forecast_receipt_references
        ):
            raise ValueError("Historical Sample Forecast receipts must be unique and sorted")
        if self.qualified and not self.formal_forecast_receipt_references:
            raise ValueError("Qualified Historical Sample requires Formal Forecast receipts")
        if canonical_hash(self.identity_payload()) != self.decision_hash:
            raise ValueError("Historical Sample Qualification hash mismatch")
        if self.decision_id != ArtifactId(
            f"historical-sample-qualification:{self.decision_hash[7:]}"
        ):
            raise ValueError("Historical Sample Qualification identity mismatch")

    @classmethod
    def create(cls, **values: Any) -> HistoricalSampleQualificationDecision:
        normalized = dict(values)
        primary = values["formal_pit_reference"]
        normalized["formal_pit_references"] = _ordered_references(
            tuple(values.get("formal_pit_references") or (() if primary is None else (primary,)))
        )
        normalized["provider_fact_decision_references"] = _ordered_references(
            tuple(values["provider_fact_decision_references"])
        )
        normalized["formal_forecast_receipt_references"] = _ordered_references(
            tuple(values.get("formal_forecast_receipt_references") or ())
        )
        normalized["reason_codes"] = tuple(sorted(set(values["reason_codes"])))
        payload = _historical_decision_payload(**normalized)
        decision_id, decision_hash = content_identity(
            "historical-sample-qualification", payload
        )
        return cls(decision_id, decision_hash, **normalized)

    def identity_payload(self) -> dict[str, Any]:
        return _historical_decision_payload(
            dataset_reference=self.dataset_reference,
            formal_protocol_reference=self.formal_protocol_reference,
            formal_pit_reference=self.formal_pit_reference,
            formal_pit_references=self.formal_pit_references,
            provider_fact_decision_references=self.provider_fact_decision_references,
            formal_forecast_receipt_references=(
                self.formal_forecast_receipt_references
            ),
            outcome=self.outcome,
            qualified=self.qualified,
            revision=self.revision,
            supersedes_decision_id=self.supersedes_decision_id,
            evaluated_at=self.evaluated_at,
            actor=self.actor,
            reason=self.reason,
            reason_codes=self.reason_codes,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "decision_id": str(self.decision_id),
            "decision_hash": self.decision_hash,
            **self.identity_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, value: Mapping[str, Any]
    ) -> HistoricalSampleQualificationDecision:
        return cls(
            decision_id=ArtifactId(str(value["decision_id"])),
            decision_hash=str(value["decision_hash"]),
            dataset_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(value["dataset_reference"])
            ),
            formal_protocol_reference=_optional_reference(
                value["formal_protocol_reference"]
            ),
            formal_pit_reference=_optional_reference(value["formal_pit_reference"]),
            formal_pit_references=tuple(
                ValidationArtifactReference.from_canonical_dict(_mapping(item))
                for item in _sequence(
                    value.get(
                        "formal_pit_references",
                        []
                        if value["formal_pit_reference"] is None
                        else [value["formal_pit_reference"]],
                    )
                )
            ),
            provider_fact_decision_references=tuple(
                ValidationArtifactReference.from_canonical_dict(_mapping(item))
                for item in _sequence(value["provider_fact_decision_references"])
            ),
            outcome=QualificationOutcome(str(value["outcome"])),
            qualified=bool(value["qualified"]),
            revision=int(value["revision"]),
            supersedes_decision_id=_optional_id(value["supersedes_decision_id"]),
            evaluated_at=datetime.fromisoformat(str(value["evaluated_at"])),
            actor=str(value["actor"]),
            reason=str(value["reason"]),
            reason_codes=tuple(str(item) for item in _sequence(value["reason_codes"])),
            formal_forecast_receipt_references=tuple(
                ValidationArtifactReference.from_canonical_dict(_mapping(item))
                for item in _sequence(
                    value.get("formal_forecast_receipt_references", ())
                )
            ),
            schema_version=str(value["schema_version"]),
        )


@dataclass(frozen=True, slots=True)
class FormalOOSQualificationDecision:
    decision_id: ArtifactId
    decision_hash: str
    policy_reference: ValidationArtifactReference
    formal_protocol_reference: ValidationArtifactReference
    evaluation_result_reference: ValidationArtifactReference
    historical_sample_decision_reference: ValidationArtifactReference
    historical_sample_decision_references: tuple[ValidationArtifactReference, ...]
    formal_pit_reference: ValidationArtifactReference
    outcome: QualificationOutcome
    formal_evaluation_complete: bool
    formal_oos_passed: bool
    revision: int
    supersedes_decision_id: ArtifactId | None
    evaluated_at: datetime
    actor: str
    reason: str
    reason_codes: tuple[str, ...]
    formal_pit_references: tuple[ValidationArtifactReference, ...] = ()
    schema_version: str = "formal-oos-qualification-decision/v1"

    def __post_init__(self) -> None:
        _validate_decision_common(
            decision_hash=self.decision_hash,
            outcome=self.outcome,
            passed=self.formal_oos_passed,
            revision=self.revision,
            supersedes=self.supersedes_decision_id,
            evaluated_at=self.evaluated_at,
            actor=self.actor,
            reason=self.reason,
            reason_codes=self.reason_codes,
        )
        expected_complete = self.outcome is not QualificationOutcome.BLOCKED
        if self.formal_evaluation_complete != expected_complete:
            raise ValueError("Formal OOS evidence-complete projection mismatch")
        expected_kinds = {
            "policy_reference": "FORMAL_OOS_QUALIFICATION_POLICY",
            "formal_protocol_reference": "FORMAL_RESEARCH_PROTOCOL",
            "historical_sample_decision_reference": "HISTORICAL_SAMPLE_QUALIFICATION_DECISION",
            "formal_pit_reference": "FORMAL_PIT_EVIDENCE",
        }
        for name, kind in expected_kinds.items():
            if getattr(self, name).artifact_kind != kind:
                raise ValueError(f"Formal OOS {name} kind mismatch")
        if not self.formal_pit_references:
            object.__setattr__(self, "formal_pit_references", (self.formal_pit_reference,))
        if (
            self.formal_pit_references
            != _ordered_references(self.formal_pit_references)
            or self.formal_pit_reference != self.formal_pit_references[0]
            or any(
                item.artifact_kind != "FORMAL_PIT_EVIDENCE"
                for item in self.formal_pit_references
            )
        ):
            raise ValueError("Formal OOS PIT Evidence family mismatch")
        if self.historical_sample_decision_references != _ordered_references(
            self.historical_sample_decision_references
        ) or (
            not self.historical_sample_decision_references
            or self.historical_sample_decision_reference
            != self.historical_sample_decision_references[0]
            or any(
                item.artifact_kind != "HISTORICAL_SAMPLE_QUALIFICATION_DECISION"
                for item in self.historical_sample_decision_references
            )
        ):
            raise ValueError("Formal OOS Historical decision family mismatch")
        if self.evaluation_result_reference.artifact_kind not in {
            "FORMAL_EVALUATION_RESULT",
            "FORMAL_HYPOTHESIS_FAMILY_EVALUATION_RESULT",
        }:
            raise ValueError("Formal OOS evaluation_result_reference kind mismatch")
        if canonical_hash(self.identity_payload()) != self.decision_hash:
            raise ValueError("Formal OOS Qualification hash mismatch")
        if self.decision_id != ArtifactId(
            f"formal-oos-qualification:{self.decision_hash[7:]}"
        ):
            raise ValueError("Formal OOS Qualification identity mismatch")

    @classmethod
    def create(cls, **values: Any) -> FormalOOSQualificationDecision:
        normalized = dict(values)
        primary = values["historical_sample_decision_reference"]
        normalized["historical_sample_decision_references"] = _ordered_references(
            tuple(values.get("historical_sample_decision_references") or (primary,))
        )
        primary_pit = values["formal_pit_reference"]
        normalized["formal_pit_references"] = _ordered_references(
            tuple(values.get("formal_pit_references") or (primary_pit,))
        )
        normalized["reason_codes"] = tuple(sorted(set(values["reason_codes"])))
        payload = _formal_oos_decision_payload(**normalized)
        decision_id, decision_hash = content_identity(
            "formal-oos-qualification", payload
        )
        return cls(decision_id, decision_hash, **normalized)

    def identity_payload(self) -> dict[str, Any]:
        return _formal_oos_decision_payload(
            policy_reference=self.policy_reference,
            formal_protocol_reference=self.formal_protocol_reference,
            evaluation_result_reference=self.evaluation_result_reference,
            historical_sample_decision_reference=self.historical_sample_decision_reference,
            historical_sample_decision_references=(
                self.historical_sample_decision_references
            ),
            formal_pit_reference=self.formal_pit_reference,
            formal_pit_references=self.formal_pit_references,
            outcome=self.outcome,
            formal_evaluation_complete=self.formal_evaluation_complete,
            formal_oos_passed=self.formal_oos_passed,
            revision=self.revision,
            supersedes_decision_id=self.supersedes_decision_id,
            evaluated_at=self.evaluated_at,
            actor=self.actor,
            reason=self.reason,
            reason_codes=self.reason_codes,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "decision_id": str(self.decision_id),
            "decision_hash": self.decision_hash,
            **self.identity_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, value: Mapping[str, Any]
    ) -> FormalOOSQualificationDecision:
        return cls(
            decision_id=ArtifactId(str(value["decision_id"])),
            decision_hash=str(value["decision_hash"]),
            policy_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(value["policy_reference"])
            ),
            formal_protocol_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(value["formal_protocol_reference"])
            ),
            evaluation_result_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(value["evaluation_result_reference"])
            ),
            historical_sample_decision_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(value["historical_sample_decision_reference"])
            ),
            historical_sample_decision_references=tuple(
                ValidationArtifactReference.from_canonical_dict(_mapping(item))
                for item in _sequence(
                    value.get(
                        "historical_sample_decision_references",
                        [value["historical_sample_decision_reference"]],
                    )
                )
            ),
            formal_pit_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(value["formal_pit_reference"])
            ),
            outcome=QualificationOutcome(str(value["outcome"])),
            formal_evaluation_complete=bool(value["formal_evaluation_complete"]),
            formal_oos_passed=bool(value["formal_oos_passed"]),
            revision=int(value["revision"]),
            supersedes_decision_id=_optional_id(value["supersedes_decision_id"]),
            evaluated_at=datetime.fromisoformat(str(value["evaluated_at"])),
            actor=str(value["actor"]),
            reason=str(value["reason"]),
            reason_codes=tuple(str(item) for item in _sequence(value["reason_codes"])),
            formal_pit_references=tuple(
                ValidationArtifactReference.from_canonical_dict(_mapping(item))
                for item in _sequence(
                    value.get(
                        "formal_pit_references", [value["formal_pit_reference"]]
                    )
                )
            ),
            schema_version=str(value["schema_version"]),
        )


def evaluate_metric_floor_payloads(
    *,
    policy: FormalOOSQualificationPolicy,
    metrics: tuple[Mapping[str, Any], ...],
) -> tuple[QualificationOutcome, tuple[str, ...]]:
    """Evaluate already owner-replayed metric payloads without selecting winners."""

    required = {
        (floor.metric_name, multiplier)
        for floor in policy.metric_floors
        for multiplier in policy.required_sensitivity_multipliers
    }
    scoped: dict[tuple[str, Decimal], list[Mapping[str, Any]]] = {}
    for item in metrics:
        if not (
            str(item["partition"]) == "LOCKED_OOS"
            and str(item["slice_kind"]) == "ALL"
            and str(item["slice_value"]) == "ALL"
        ):
            continue
        key = (
            str(item["metric_name"]),
            Decimal(str(item["sensitivity_return_multiplier"])),
        )
        scoped.setdefault(key, []).append(item)
    missing = required.difference(scoped)
    if missing:
        return QualificationOutcome.NOT_ESTIMABLE, tuple(
            f"LOCKED_OOS_METRIC_MISSING_{name}_{multiplier}"
            for name, multiplier in sorted(missing)
        )
    not_estimable: set[str] = set()
    rejected: set[str] = set()
    floors = {item.metric_name: item for item in policy.metric_floors}
    for key in sorted(required):
        name, multiplier = key
        for item in scoped[key]:
            fold = int(item["fold"])
            suffix = f"{name}_{multiplier}_FOLD_{fold}"
            if str(item["status"]) != "ESTIMATED":
                not_estimable.add(f"LOCKED_OOS_METRIC_NOT_ESTIMABLE_{suffix}")
                continue
            if int(item["sample_count"]) < policy.minimum_sample_count:
                not_estimable.add(f"LOCKED_OOS_SAMPLE_FLOOR_NOT_MET_{suffix}")
                continue
            estimate = Decimal(str(item["estimate"]))
            adjusted = Decimal(str(item["adjusted_p_value"]))
            confidence_low = Decimal(str(item["confidence_low"]))
            confidence_high = Decimal(str(item["confidence_high"]))
            floor = floors[name]
            if floor.minimum_estimate is not None and estimate < floor.minimum_estimate:
                rejected.add(f"LOCKED_OOS_MINIMUM_NOT_MET_{suffix}")
            if floor.maximum_estimate is not None and estimate > floor.maximum_estimate:
                rejected.add(f"LOCKED_OOS_MAXIMUM_EXCEEDED_{suffix}")
            if adjusted > policy.maximum_adjusted_p_value:
                rejected.add(f"LOCKED_OOS_ADJUSTED_P_VALUE_EXCEEDED_{suffix}")
            if policy.require_confidence_interval_excludes_zero and (
                confidence_low <= 0 <= confidence_high
            ):
                rejected.add(f"LOCKED_OOS_CONFIDENCE_INTERVAL_INCLUDES_ZERO_{suffix}")
    if not_estimable:
        return QualificationOutcome.NOT_ESTIMABLE, tuple(sorted(not_estimable))
    if rejected:
        return QualificationOutcome.REJECTED, tuple(sorted(rejected))
    return QualificationOutcome.SATISFIED, ()


def _validate_decision_common(
    *,
    decision_hash: str,
    outcome: QualificationOutcome,
    passed: bool,
    revision: int,
    supersedes: ArtifactId | None,
    evaluated_at: datetime,
    actor: str,
    reason: str,
    reason_codes: tuple[str, ...],
) -> None:
    require_sha256("decision_hash", decision_hash)
    if passed != (outcome is QualificationOutcome.SATISFIED):
        raise ValueError("Qualification outcome/pass projection mismatch")
    if revision <= 0 or (revision == 1) != (supersedes is None):
        raise ValueError("Qualification decision revision/supersession mismatch")
    if evaluated_at.tzinfo is None or evaluated_at.utcoffset() is None:
        raise ValueError("Qualification decision time must be timezone-aware")
    if not actor.strip() or not reason.strip():
        raise ValueError("Qualification actor/reason must be non-empty")
    if reason_codes != tuple(sorted(set(reason_codes))):
        raise ValueError("Qualification reasons must be unique and sorted")
    if (outcome is QualificationOutcome.SATISFIED) == bool(reason_codes):
        raise ValueError("Qualification reasons/outcome mismatch")


def _formal_oos_policy_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": "formal-oos-qualification-policy/v1",
        "policy_version": values["policy_version"],
        "metric_floors": [
            item.to_canonical_dict() for item in values["metric_floors"]
        ],
        "minimum_sample_count": values["minimum_sample_count"],
        "maximum_adjusted_p_value": str(values["maximum_adjusted_p_value"]),
        "require_confidence_interval_excludes_zero": values[
            "require_confidence_interval_excludes_zero"
        ],
        "required_sensitivity_multipliers": [
            str(item) for item in values["required_sensitivity_multipliers"]
        ],
        "locked_at": timestamp(values["locked_at"]),
        "multiple_testing_required": True,
        "locked_oos_reuse_prohibited": True,
        "engineering_default": False,
    }


def _formal_evaluation_observation_binding_payload(
    *,
    forecast_reference: ValidationArtifactReference,
    label_reference: ValidationArtifactReference,
    panel_slice_reference: ValidationArtifactReference,
    panel_row_reference: ValidationArtifactReference,
) -> dict[str, Any]:
    return {
        "schema_version": "formal-evaluation-observation-binding/v1",
        "forecast_reference": forecast_reference.to_canonical_dict(),
        "label_reference": label_reference.to_canonical_dict(),
        "panel_slice_reference": panel_slice_reference.to_canonical_dict(),
        "panel_row_reference": panel_row_reference.to_canonical_dict(),
    }


def _historical_decision_payload(**values: Any) -> dict[str, Any]:
    payload = {
        "schema_version": "historical-sample-qualification-decision/v1",
        "dataset_reference": values["dataset_reference"].to_canonical_dict(),
        "formal_protocol_reference": _reference_payload(
            values["formal_protocol_reference"]
        ),
        "formal_pit_reference": _reference_payload(values["formal_pit_reference"]),
        "provider_fact_decision_references": [
            item.to_canonical_dict()
            for item in values["provider_fact_decision_references"]
        ],
        "outcome": values["outcome"].value,
        "qualified": values["qualified"],
        "revision": values["revision"],
        "supersedes_decision_id": (
            None
            if values["supersedes_decision_id"] is None
            else str(values["supersedes_decision_id"])
        ),
        "evaluated_at": timestamp(values["evaluated_at"]),
        "actor": values["actor"],
        "reason": values["reason"],
        "reason_codes": list(values["reason_codes"]),
    }
    pit_references = values.get("formal_pit_references") or ()
    if len(pit_references) > 1:
        payload["formal_pit_references"] = [
            item.to_canonical_dict() for item in pit_references
        ]
    forecast_receipts = values.get("formal_forecast_receipt_references") or ()
    if forecast_receipts:
        payload["formal_forecast_receipt_references"] = [
            item.to_canonical_dict() for item in forecast_receipts
        ]
    return payload


def _formal_oos_decision_payload(**values: Any) -> dict[str, Any]:
    payload = {
        "schema_version": "formal-oos-qualification-decision/v1",
        "policy_reference": values["policy_reference"].to_canonical_dict(),
        "formal_protocol_reference": values[
            "formal_protocol_reference"
        ].to_canonical_dict(),
        "evaluation_result_reference": values[
            "evaluation_result_reference"
        ].to_canonical_dict(),
        "historical_sample_decision_reference": values[
            "historical_sample_decision_reference"
        ].to_canonical_dict(),
        "formal_pit_reference": values["formal_pit_reference"].to_canonical_dict(),
        "outcome": values["outcome"].value,
        "formal_evaluation_complete": values["formal_evaluation_complete"],
        "formal_oos_passed": values["formal_oos_passed"],
        "revision": values["revision"],
        "supersedes_decision_id": (
            None
            if values["supersedes_decision_id"] is None
            else str(values["supersedes_decision_id"])
        ),
        "evaluated_at": timestamp(values["evaluated_at"]),
        "actor": values["actor"],
        "reason": values["reason"],
        "reason_codes": list(values["reason_codes"]),
    }
    historical = values.get("historical_sample_decision_references") or ()
    if len(historical) > 1:
        payload["historical_sample_decision_references"] = [
            item.to_canonical_dict() for item in historical
        ]
    pits = values.get("formal_pit_references") or ()
    if len(pits) > 1:
        payload["formal_pit_references"] = [
            item.to_canonical_dict() for item in pits
        ]
    return payload


def _ordered_references(
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


def _reference_payload(
    value: ValidationArtifactReference | None,
) -> dict[str, str] | None:
    return None if value is None else value.to_canonical_dict()


def _optional_reference(value: object) -> ValidationArtifactReference | None:
    return (
        None
        if value is None
        else ValidationArtifactReference.from_canonical_dict(_mapping(value))
    )


def _optional_id(value: object) -> ArtifactId | None:
    return None if value is None else ArtifactId(str(value))


def _optional_decimal(value: object) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("Qualification payload is not an object")
    return value


def _sequence(value: object) -> tuple[object, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError("Qualification payload is not an array")
    return tuple(value)


__all__ = [
    "FormalOOSMetricFloor",
    "FormalOOSQualificationDecision",
    "FormalOOSQualificationPolicy",
    "HistoricalSampleQualificationDecision",
    "LockedOOSEvidenceIdentity",
    "QualificationOutcome",
    "evaluate_metric_floor_payloads",
]
