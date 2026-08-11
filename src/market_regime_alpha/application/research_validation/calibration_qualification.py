"""Frozen C5 Calibration qualification contracts.

Qualification is intentionally separate from the engineering Calibration
Artifact.  The PostgreSQL owner must resolve every observation back to one
exact OutcomeTarget-bound Forecast estimate and TargetOutcomeLabel, replay the
fit/evaluations, and only then issue one of these decisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping

from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
    content_identity,
    timestamp,
)
from market_regime_alpha.application.research_validation.qualification import (
    QualificationOutcome,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash, require_sha256


@dataclass(frozen=True, slots=True)
class CalibrationQualificationPolicy:
    policy_id: ArtifactId
    policy_hash: str
    policy_version: str
    target_protocol_reference: ValidationArtifactReference
    target_reference: ValidationArtifactReference
    barrier_id: str
    calibration_protocol_reference: ValidationArtifactReference
    minimum_oos_samples: int
    maximum_brier: Decimal
    maximum_log_loss: Decimal
    maximum_ece: Decimal
    minimum_coverage: Decimal
    locked_at: datetime
    schema_version: str = "calibration-qualification-policy/v1"

    def __post_init__(self) -> None:
        require_sha256("policy_hash", self.policy_hash)
        if self.schema_version != "calibration-qualification-policy/v1":
            raise ValueError("unsupported Calibration Qualification Policy schema")
        if self.target_protocol_reference.artifact_kind != "OUTCOME_TARGET_PROTOCOL":
            raise ValueError("Calibration qualification requires Outcome Target Protocol")
        if self.target_reference.artifact_kind != "OUTCOME_TARGET":
            raise ValueError("Calibration qualification requires one exact Outcome Target")
        if self.calibration_protocol_reference.artifact_kind != "CALIBRATION_PROTOCOL":
            raise ValueError("Calibration qualification requires a Calibration Protocol")
        if not self.policy_version.strip() or not self.barrier_id.strip():
            raise ValueError("Calibration qualification policy identity is incomplete")
        if self.minimum_oos_samples <= 0:
            raise ValueError("Calibration OOS sample floor must be positive")
        if any(
            value < 0
            for value in (
                self.maximum_brier,
                self.maximum_log_loss,
                self.maximum_ece,
            )
        ) or not Decimal("0") < self.minimum_coverage <= Decimal("1"):
            raise ValueError("Calibration metric floors are invalid")
        if self.locked_at.tzinfo is None or self.locked_at.utcoffset() is None:
            raise ValueError("Calibration policy lock time must be timezone-aware")
        if canonical_hash(self.identity_payload()) != self.policy_hash:
            raise ValueError("Calibration Qualification Policy hash mismatch")
        if self.policy_id != ArtifactId(
            f"calibration-qualification-policy:{self.policy_hash[7:]}"
        ):
            raise ValueError("Calibration Qualification Policy identity mismatch")

    @classmethod
    def create(
        cls,
        *,
        policy_version: str,
        target_protocol_reference: ValidationArtifactReference,
        target_reference: ValidationArtifactReference,
        barrier_id: str,
        calibration_protocol_reference: ValidationArtifactReference,
        minimum_oos_samples: int,
        maximum_brier: Decimal,
        maximum_log_loss: Decimal,
        maximum_ece: Decimal,
        minimum_coverage: Decimal,
        locked_at: datetime,
    ) -> CalibrationQualificationPolicy:
        payload = _policy_payload(
            policy_version=policy_version,
            target_protocol_reference=target_protocol_reference,
            target_reference=target_reference,
            barrier_id=barrier_id,
            calibration_protocol_reference=calibration_protocol_reference,
            minimum_oos_samples=minimum_oos_samples,
            maximum_brier=maximum_brier,
            maximum_log_loss=maximum_log_loss,
            maximum_ece=maximum_ece,
            minimum_coverage=minimum_coverage,
            locked_at=locked_at,
        )
        policy_id, policy_hash = content_identity(
            "calibration-qualification-policy", payload
        )
        return cls(
            policy_id,
            policy_hash,
            policy_version,
            target_protocol_reference,
            target_reference,
            barrier_id,
            calibration_protocol_reference,
            minimum_oos_samples,
            maximum_brier,
            maximum_log_loss,
            maximum_ece,
            minimum_coverage,
            locked_at,
        )

    def identity_payload(self) -> dict[str, Any]:
        return _policy_payload(
            policy_version=self.policy_version,
            target_protocol_reference=self.target_protocol_reference,
            target_reference=self.target_reference,
            barrier_id=self.barrier_id,
            calibration_protocol_reference=self.calibration_protocol_reference,
            minimum_oos_samples=self.minimum_oos_samples,
            maximum_brier=self.maximum_brier,
            maximum_log_loss=self.maximum_log_loss,
            maximum_ece=self.maximum_ece,
            minimum_coverage=self.minimum_coverage,
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
    ) -> CalibrationQualificationPolicy:
        return cls(
            policy_id=ArtifactId(str(value["policy_id"])),
            policy_hash=str(value["policy_hash"]),
            policy_version=str(value["policy_version"]),
            target_protocol_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(value["target_protocol_reference"])
            ),
            target_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(value["target_reference"])
            ),
            barrier_id=str(value["barrier_id"]),
            calibration_protocol_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(value["calibration_protocol_reference"])
            ),
            minimum_oos_samples=int(value["minimum_oos_samples"]),
            maximum_brier=Decimal(str(value["maximum_brier"])),
            maximum_log_loss=Decimal(str(value["maximum_log_loss"])),
            maximum_ece=Decimal(str(value["maximum_ece"])),
            minimum_coverage=Decimal(str(value["minimum_coverage"])),
            locked_at=datetime.fromisoformat(str(value["locked_at"])),
            schema_version=str(value["schema_version"]),
        )


@dataclass(frozen=True, slots=True)
class FormalCalibrationObservationBinding:
    observation_id: str
    forecast_reference: ValidationArtifactReference
    label_reference: ValidationArtifactReference
    partition: str

    def __post_init__(self) -> None:
        if not self.observation_id.strip():
            raise ValueError("Calibration observation id must be non-empty")
        if self.forecast_reference.artifact_kind != "OUTCOME_TARGET_BOUND_FORECAST":
            raise ValueError("Calibration binding requires a target-bound Forecast")
        if self.label_reference.artifact_kind != "TARGET_OUTCOME_LABEL":
            raise ValueError("Calibration binding requires a Target Outcome Label")
        if self.partition not in {"FIT", "VALIDATION", "OOS"}:
            raise ValueError("Calibration observation partition is invalid")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "forecast_reference": self.forecast_reference.to_canonical_dict(),
            "label_reference": self.label_reference.to_canonical_dict(),
            "partition": self.partition,
        }


@dataclass(frozen=True, slots=True)
class CalibrationQualificationDecision:
    decision_id: ArtifactId
    decision_hash: str
    policy_reference: ValidationArtifactReference
    formal_protocol_reference: ValidationArtifactReference
    formal_oos_reference: ValidationArtifactReference | None
    calibration_artifact_reference: ValidationArtifactReference | None
    outcome: QualificationOutcome
    calibrated: bool
    revision: int
    supersedes_decision_id: ArtifactId | None
    evaluated_at: datetime
    actor: str
    reason: str
    reason_codes: tuple[str, ...]
    schema_version: str = "calibration-qualification-decision/v1"

    def __post_init__(self) -> None:
        require_sha256("decision_hash", self.decision_hash)
        expected = self.outcome is QualificationOutcome.SATISFIED
        if self.calibrated != expected:
            raise ValueError("Calibration qualification outcome projection mismatch")
        if self.policy_reference.artifact_kind != "CALIBRATION_POLICY":
            raise ValueError("Calibration decision Policy kind mismatch")
        if self.formal_protocol_reference.artifact_kind != "FORMAL_RESEARCH_PROTOCOL":
            raise ValueError("Calibration decision Formal Protocol kind mismatch")
        if self.formal_oos_reference is not None and (
            self.formal_oos_reference.artifact_kind != "FORMAL_OOS_QUALIFICATION_DECISION"
        ):
            raise ValueError("Calibration decision Formal OOS kind mismatch")
        if self.calibration_artifact_reference is not None and (
            self.calibration_artifact_reference.artifact_kind != "CALIBRATION_ARTIFACT"
        ):
            raise ValueError("Calibration decision Artifact kind mismatch")
        if self.revision <= 0 or (self.revision == 1) != (
            self.supersedes_decision_id is None
        ):
            raise ValueError("Calibration decision revision/supersession mismatch")
        if not self.actor.strip() or not self.reason.strip():
            raise ValueError("Calibration decision actor/reason must be non-empty")
        if self.reason_codes != tuple(sorted(set(self.reason_codes))):
            raise ValueError("Calibration decision reasons must be unique and sorted")
        if expected == bool(self.reason_codes):
            raise ValueError("Calibration decision reasons/outcome mismatch")
        if canonical_hash(self.identity_payload()) != self.decision_hash:
            raise ValueError("Calibration Qualification Decision hash mismatch")
        if self.decision_id != ArtifactId(
            f"calibration-qualification:{self.decision_hash[7:]}"
        ):
            raise ValueError("Calibration Qualification Decision identity mismatch")

    @classmethod
    def create(cls, **values: Any) -> CalibrationQualificationDecision:
        normalized = dict(values)
        normalized["reason_codes"] = tuple(sorted(set(values["reason_codes"])))
        payload = _decision_payload(**normalized)
        decision_id, decision_hash = content_identity(
            "calibration-qualification", payload
        )
        return cls(decision_id, decision_hash, **normalized)

    def identity_payload(self) -> dict[str, Any]:
        return _decision_payload(
            policy_reference=self.policy_reference,
            formal_protocol_reference=self.formal_protocol_reference,
            formal_oos_reference=self.formal_oos_reference,
            calibration_artifact_reference=self.calibration_artifact_reference,
            outcome=self.outcome,
            calibrated=self.calibrated,
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
    ) -> CalibrationQualificationDecision:
        return cls(
            decision_id=ArtifactId(str(value["decision_id"])),
            decision_hash=str(value["decision_hash"]),
            policy_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(value["policy_reference"])
            ),
            formal_protocol_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(value["formal_protocol_reference"])
            ),
            formal_oos_reference=_optional_reference(value["formal_oos_reference"]),
            calibration_artifact_reference=_optional_reference(
                value["calibration_artifact_reference"]
            ),
            outcome=QualificationOutcome(str(value["outcome"])),
            calibrated=bool(value["calibrated"]),
            revision=int(value["revision"]),
            supersedes_decision_id=(
                None
                if value["supersedes_decision_id"] is None
                else ArtifactId(str(value["supersedes_decision_id"]))
            ),
            evaluated_at=datetime.fromisoformat(str(value["evaluated_at"])),
            actor=str(value["actor"]),
            reason=str(value["reason"]),
            reason_codes=tuple(str(item) for item in _sequence(value["reason_codes"])),
            schema_version=str(value["schema_version"]),
        )


def _policy_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": "calibration-qualification-policy/v1",
        "policy_version": values["policy_version"],
        "target_protocol_reference": values[
            "target_protocol_reference"
        ].to_canonical_dict(),
        "target_reference": values["target_reference"].to_canonical_dict(),
        "barrier_id": values["barrier_id"],
        "calibration_protocol_reference": values[
            "calibration_protocol_reference"
        ].to_canonical_dict(),
        "minimum_oos_samples": values["minimum_oos_samples"],
        "maximum_brier": str(values["maximum_brier"]),
        "maximum_log_loss": str(values["maximum_log_loss"]),
        "maximum_ece": str(values["maximum_ece"]),
        "minimum_coverage": str(values["minimum_coverage"]),
        "method_selection_uses_locked_oos": False,
        "locked_at": timestamp(values["locked_at"]),
        "engineering_default": False,
    }


def _decision_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": "calibration-qualification-decision/v1",
        "policy_reference": values["policy_reference"].to_canonical_dict(),
        "formal_protocol_reference": values[
            "formal_protocol_reference"
        ].to_canonical_dict(),
        "formal_oos_reference": (
            None
            if values["formal_oos_reference"] is None
            else values["formal_oos_reference"].to_canonical_dict()
        ),
        "calibration_artifact_reference": (
            None
            if values["calibration_artifact_reference"] is None
            else values["calibration_artifact_reference"].to_canonical_dict()
        ),
        "outcome": values["outcome"].value,
        "calibrated": values["calibrated"],
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
        "production_authorized": False,
    }


def _optional_reference(value: object) -> ValidationArtifactReference | None:
    return (
        None
        if value is None
        else ValidationArtifactReference.from_canonical_dict(_mapping(value))
    )


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("Calibration qualification payload is not an object")
    return value


def _sequence(value: object) -> tuple[object, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError("Calibration qualification payload is not an array")
    return tuple(value)


__all__ = [
    "CalibrationQualificationDecision",
    "CalibrationQualificationPolicy",
    "FormalCalibrationObservationBinding",
]
