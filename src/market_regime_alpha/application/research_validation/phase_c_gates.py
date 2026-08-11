"""Immutable C6/C7/C9 stage decisions and prospective Shadow policy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping

from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
    content_identity,
    timestamp,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.application.strategy_shadow.contracts import HoldingRuleKind
from market_regime_alpha.application.strategy_shadow.portfolio import (
    ShadowParameterProvenance,
)
from market_regime_alpha.evidence.canonical import canonical_hash, require_sha256


class PhaseCStage(str, Enum):
    ENTRY_HOLDING_EXIT_QUALIFICATION = "ENTRY_HOLDING_EXIT_QUALIFICATION"
    PROSPECTIVE_STRATEGY_SHADOW = "PROSPECTIVE_STRATEGY_SHADOW"
    CONTROLLED_EXECUTION_READINESS = "CONTROLLED_EXECUTION_READINESS"


class PhaseCStageOutcome(str, Enum):
    SATISFIED = "SATISFIED"
    REJECTED = "REJECTED"
    NOT_ESTIMABLE = "NOT_ESTIMABLE"
    BLOCKED = "BLOCKED"
    ACCUMULATING = "ACCUMULATING"


@dataclass(frozen=True, slots=True)
class EntryHoldingExitQualificationPolicy:
    policy_id: ArtifactId
    policy_hash: str
    policy_version: str
    entry_model_reference: ValidationArtifactReference
    strategy_policy_reference: ValidationArtifactReference
    portfolio_policy_reference: ValidationArtifactReference
    minimum_samples: int
    minimum_hit_rate: Decimal
    minimum_cost_adjusted_return: Decimal
    maximum_mean_mae: Decimal
    required_exit_rule_coverage: tuple[HoldingRuleKind, ...]
    allowed_result_provenance: tuple[ShadowParameterProvenance, ...]
    locked_at: datetime
    schema_version: str = "entry-holding-exit-qualification-policy/v1"

    def __post_init__(self) -> None:
        require_sha256("policy_hash", self.policy_hash)
        if self.schema_version != "entry-holding-exit-qualification-policy/v1":
            raise ValueError("unsupported Entry/Holding/Exit Policy schema")
        if self.entry_model_reference.artifact_kind != "ENTRY_RESEARCH_MODEL":
            raise ValueError("Entry/Holding/Exit policy requires Entry Research Model")
        if self.strategy_policy_reference.artifact_kind != "STRATEGY_SHADOW_POLICY":
            raise ValueError("Entry/Holding/Exit policy requires Strategy Shadow Policy")
        if self.portfolio_policy_reference.artifact_kind != "SHADOW_PORTFOLIO_POLICY":
            raise ValueError("Entry/Holding/Exit policy requires Portfolio Policy")
        if (
            self.minimum_samples <= 0
            or not Decimal("0") <= self.minimum_hit_rate <= Decimal("1")
            or self.maximum_mean_mae > 0
            or not self.required_exit_rule_coverage
            or not self.allowed_result_provenance
        ):
            raise ValueError("Entry/Holding/Exit qualification floors are invalid")
        if self.required_exit_rule_coverage != tuple(
            sorted(set(self.required_exit_rule_coverage), key=lambda item: item.value)
        ):
            raise ValueError("Entry/Holding/Exit rule coverage must be sorted and unique")
        if self.allowed_result_provenance != tuple(
            sorted(set(self.allowed_result_provenance), key=lambda item: item.value)
        ):
            raise ValueError("Entry/Holding/Exit provenance must be sorted and unique")
        if self.locked_at.tzinfo is None or self.locked_at.utcoffset() is None:
            raise ValueError("Entry/Holding/Exit policy lock time must be timezone-aware")
        if canonical_hash(self.identity_payload()) != self.policy_hash:
            raise ValueError("Entry/Holding/Exit Policy hash mismatch")
        if self.policy_id != ArtifactId(
            f"entry-holding-exit-policy:{self.policy_hash[7:]}"
        ):
            raise ValueError("Entry/Holding/Exit Policy identity mismatch")

    @classmethod
    def create(cls, **values: Any) -> EntryHoldingExitQualificationPolicy:
        normalized = dict(values)
        normalized["required_exit_rule_coverage"] = tuple(
            sorted(
                set(values["required_exit_rule_coverage"]),
                key=lambda item: item.value,
            )
        )
        normalized["allowed_result_provenance"] = tuple(
            sorted(
                set(values["allowed_result_provenance"]),
                key=lambda item: item.value,
            )
        )
        policy_id, policy_hash = content_identity(
            "entry-holding-exit-policy", _entry_holding_exit_policy_payload(**normalized)
        )
        return cls(policy_id, policy_hash, **normalized)

    def identity_payload(self) -> dict[str, Any]:
        return _entry_holding_exit_policy_payload(
            policy_version=self.policy_version,
            entry_model_reference=self.entry_model_reference,
            strategy_policy_reference=self.strategy_policy_reference,
            portfolio_policy_reference=self.portfolio_policy_reference,
            minimum_samples=self.minimum_samples,
            minimum_hit_rate=self.minimum_hit_rate,
            minimum_cost_adjusted_return=self.minimum_cost_adjusted_return,
            maximum_mean_mae=self.maximum_mean_mae,
            required_exit_rule_coverage=self.required_exit_rule_coverage,
            allowed_result_provenance=self.allowed_result_provenance,
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
    ) -> EntryHoldingExitQualificationPolicy:
        return cls(
            policy_id=ArtifactId(str(value["policy_id"])),
            policy_hash=str(value["policy_hash"]),
            policy_version=str(value["policy_version"]),
            entry_model_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(value["entry_model_reference"])
            ),
            strategy_policy_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(value["strategy_policy_reference"])
            ),
            portfolio_policy_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(value["portfolio_policy_reference"])
            ),
            minimum_samples=int(value["minimum_samples"]),
            minimum_hit_rate=Decimal(str(value["minimum_hit_rate"])),
            minimum_cost_adjusted_return=Decimal(
                str(value["minimum_cost_adjusted_return"])
            ),
            maximum_mean_mae=Decimal(str(value["maximum_mean_mae"])),
            required_exit_rule_coverage=tuple(
                HoldingRuleKind(str(item))
                for item in _sequence(value["required_exit_rule_coverage"])
            ),
            allowed_result_provenance=tuple(
                ShadowParameterProvenance(str(item))
                for item in _sequence(value["allowed_result_provenance"])
            ),
            locked_at=datetime.fromisoformat(str(value["locked_at"])),
            schema_version=str(value["schema_version"]),
        )


@dataclass(frozen=True, slots=True)
class ProspectiveShadowQualificationPolicy:
    policy_id: ArtifactId
    policy_hash: str
    policy_version: str
    strategy_policy_reference: ValidationArtifactReference
    portfolio_policy_reference: ValidationArtifactReference
    minimum_sessions: int
    minimum_distinct_days: int
    maximum_incidents: int
    maximum_drifts: int
    maximum_provider_failures: int
    locked_at: datetime
    schema_version: str = "prospective-shadow-qualification-policy/v1"

    def __post_init__(self) -> None:
        require_sha256("policy_hash", self.policy_hash)
        if self.schema_version != "prospective-shadow-qualification-policy/v1":
            raise ValueError("unsupported Prospective Shadow Policy schema")
        if self.strategy_policy_reference.artifact_kind != "STRATEGY_SHADOW_POLICY":
            raise ValueError("Prospective policy requires Strategy Shadow Policy")
        if self.portfolio_policy_reference.artifact_kind != "SHADOW_PORTFOLIO_POLICY":
            raise ValueError("Prospective policy requires Shadow Portfolio Policy")
        if (
            not self.policy_version.strip()
            or self.minimum_sessions <= 0
            or self.minimum_distinct_days <= 0
            or self.maximum_incidents < 0
            or self.maximum_drifts < 0
            or self.maximum_provider_failures < 0
        ):
            raise ValueError("Prospective Shadow policy floors are invalid")
        if self.locked_at.tzinfo is None or self.locked_at.utcoffset() is None:
            raise ValueError("Prospective Shadow policy lock time must be timezone-aware")
        if canonical_hash(self.identity_payload()) != self.policy_hash:
            raise ValueError("Prospective Shadow Policy hash mismatch")
        if self.policy_id != ArtifactId(
            f"prospective-shadow-policy:{self.policy_hash[7:]}"
        ):
            raise ValueError("Prospective Shadow Policy identity mismatch")

    @classmethod
    def create(cls, **values: Any) -> ProspectiveShadowQualificationPolicy:
        payload = _prospective_policy_payload(**values)
        policy_id, policy_hash = content_identity("prospective-shadow-policy", payload)
        return cls(policy_id, policy_hash, **values)

    def identity_payload(self) -> dict[str, Any]:
        return _prospective_policy_payload(
            policy_version=self.policy_version,
            strategy_policy_reference=self.strategy_policy_reference,
            portfolio_policy_reference=self.portfolio_policy_reference,
            minimum_sessions=self.minimum_sessions,
            minimum_distinct_days=self.minimum_distinct_days,
            maximum_incidents=self.maximum_incidents,
            maximum_drifts=self.maximum_drifts,
            maximum_provider_failures=self.maximum_provider_failures,
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
    ) -> ProspectiveShadowQualificationPolicy:
        return cls(
            policy_id=ArtifactId(str(value["policy_id"])),
            policy_hash=str(value["policy_hash"]),
            policy_version=str(value["policy_version"]),
            strategy_policy_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(value["strategy_policy_reference"])
            ),
            portfolio_policy_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(value["portfolio_policy_reference"])
            ),
            minimum_sessions=int(value["minimum_sessions"]),
            minimum_distinct_days=int(value["minimum_distinct_days"]),
            maximum_incidents=int(value["maximum_incidents"]),
            maximum_drifts=int(value["maximum_drifts"]),
            maximum_provider_failures=int(value["maximum_provider_failures"]),
            locked_at=datetime.fromisoformat(str(value["locked_at"])),
            schema_version=str(value["schema_version"]),
        )


@dataclass(frozen=True, slots=True)
class PhaseCStageDecision:
    decision_id: ArtifactId
    decision_hash: str
    stage: PhaseCStage
    scope_id: str
    policy_reference: ValidationArtifactReference | None
    evidence_references: tuple[ValidationArtifactReference, ...]
    outcome: PhaseCStageOutcome
    qualification_established: bool
    revision: int
    supersedes_decision_id: ArtifactId | None
    evaluated_at: datetime
    actor: str
    reason: str
    reason_codes: tuple[str, ...]
    schema_version: str = "phase-c-stage-decision/v1"

    def __post_init__(self) -> None:
        require_sha256("decision_hash", self.decision_hash)
        if self.schema_version != "phase-c-stage-decision/v1":
            raise ValueError("unsupported Phase C Stage Decision schema")
        if self.qualification_established != (
            self.outcome is PhaseCStageOutcome.SATISFIED
        ):
            raise ValueError("Phase C stage outcome projection mismatch")
        if not self.scope_id.strip() or not self.actor.strip() or not self.reason.strip():
            raise ValueError("Phase C stage scope/actor/reason must be non-empty")
        ordered = tuple(
            sorted(
                set(self.evidence_references),
                key=lambda item: (
                    item.artifact_kind,
                    str(item.artifact_id),
                    item.content_hash,
                ),
            )
        )
        if self.evidence_references != ordered:
            raise ValueError("Phase C stage evidence must be unique and sorted")
        if self.revision <= 0 or (self.revision == 1) != (
            self.supersedes_decision_id is None
        ):
            raise ValueError("Phase C stage revision/supersession mismatch")
        if self.evaluated_at.tzinfo is None or self.evaluated_at.utcoffset() is None:
            raise ValueError("Phase C stage evaluation time must be timezone-aware")
        if self.reason_codes != tuple(sorted(set(self.reason_codes))):
            raise ValueError("Phase C stage reasons must be unique and sorted")
        if self.qualification_established == bool(self.reason_codes):
            raise ValueError("Phase C stage reasons/outcome mismatch")
        if canonical_hash(self.identity_payload()) != self.decision_hash:
            raise ValueError("Phase C Stage Decision hash mismatch")
        if self.decision_id != ArtifactId(
            f"phase-c-stage-decision:{self.decision_hash[7:]}"
        ):
            raise ValueError("Phase C Stage Decision identity mismatch")

    @classmethod
    def create(cls, **values: Any) -> PhaseCStageDecision:
        normalized = dict(values)
        normalized["evidence_references"] = tuple(
            sorted(
                set(values["evidence_references"]),
                key=lambda item: (
                    item.artifact_kind,
                    str(item.artifact_id),
                    item.content_hash,
                ),
            )
        )
        normalized["reason_codes"] = tuple(sorted(set(values["reason_codes"])))
        decision_id, decision_hash = content_identity(
            "phase-c-stage-decision", _stage_payload(**normalized)
        )
        return cls(decision_id, decision_hash, **normalized)

    def identity_payload(self) -> dict[str, Any]:
        return _stage_payload(
            stage=self.stage,
            scope_id=self.scope_id,
            policy_reference=self.policy_reference,
            evidence_references=self.evidence_references,
            outcome=self.outcome,
            qualification_established=self.qualification_established,
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
    def from_canonical_dict(cls, value: Mapping[str, Any]) -> PhaseCStageDecision:
        return cls(
            decision_id=ArtifactId(str(value["decision_id"])),
            decision_hash=str(value["decision_hash"]),
            stage=PhaseCStage(str(value["stage"])),
            scope_id=str(value["scope_id"]),
            policy_reference=_optional_reference(value["policy_reference"]),
            evidence_references=tuple(
                ValidationArtifactReference.from_canonical_dict(_mapping(item))
                for item in _sequence(value["evidence_references"])
            ),
            outcome=PhaseCStageOutcome(str(value["outcome"])),
            qualification_established=bool(value["qualification_established"]),
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


def _entry_holding_exit_policy_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": "entry-holding-exit-qualification-policy/v1",
        "policy_version": values["policy_version"],
        "entry_model_reference": values[
            "entry_model_reference"
        ].to_canonical_dict(),
        "strategy_policy_reference": values[
            "strategy_policy_reference"
        ].to_canonical_dict(),
        "portfolio_policy_reference": values[
            "portfolio_policy_reference"
        ].to_canonical_dict(),
        "minimum_samples": values["minimum_samples"],
        "minimum_hit_rate": str(values["minimum_hit_rate"]),
        "minimum_cost_adjusted_return": str(
            values["minimum_cost_adjusted_return"]
        ),
        "maximum_mean_mae": str(values["maximum_mean_mae"]),
        "required_exit_rule_coverage": [
            item.value for item in values["required_exit_rule_coverage"]
        ],
        "allowed_result_provenance": [
            item.value for item in values["allowed_result_provenance"]
        ],
        "required_formal_oos": True,
        "required_calibration": True,
        "required_cost_capacity": True,
        "required_independent_governance_approval": True,
        "canonical_entry_unlock_automatic": False,
        "locked_at": timestamp(values["locked_at"]),
    }


def _prospective_policy_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": "prospective-shadow-qualification-policy/v1",
        "policy_version": values["policy_version"],
        "strategy_policy_reference": values[
            "strategy_policy_reference"
        ].to_canonical_dict(),
        "portfolio_policy_reference": values[
            "portfolio_policy_reference"
        ].to_canonical_dict(),
        "minimum_sessions": values["minimum_sessions"],
        "minimum_distinct_days": values["minimum_distinct_days"],
        "maximum_incidents": values["maximum_incidents"],
        "maximum_drifts": values["maximum_drifts"],
        "maximum_provider_failures": values["maximum_provider_failures"],
        "session_must_start_after_policy_lock": True,
        "require_exact_event_replay": True,
        "require_successful_source_acquisition": True,
        "required_clock_mode": "LIVE_TRUSTED",
        "required_runtime_origin": "LIVE_ACQUISITION",
        "replay_or_fixture_counts_as_prospective": False,
        "locked_at": timestamp(values["locked_at"]),
    }


def _stage_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": "phase-c-stage-decision/v1",
        "stage": values["stage"].value,
        "scope_id": values["scope_id"],
        "policy_reference": (
            None
            if values["policy_reference"] is None
            else values["policy_reference"].to_canonical_dict()
        ),
        "evidence_references": [
            item.to_canonical_dict() for item in values["evidence_references"]
        ],
        "outcome": values["outcome"].value,
        "qualification_established": values["qualification_established"],
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
        "broker_mutation_authorized": False,
        "automatic_promotion": False,
    }


def _optional_reference(value: object) -> ValidationArtifactReference | None:
    return (
        None
        if value is None
        else ValidationArtifactReference.from_canonical_dict(_mapping(value))
    )


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("Phase C gate payload is not an object")
    return value


def _sequence(value: object) -> tuple[object, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError("Phase C gate payload is not an array")
    return tuple(value)


__all__ = [
    "EntryHoldingExitQualificationPolicy",
    "PhaseCStage",
    "PhaseCStageDecision",
    "PhaseCStageOutcome",
    "ProspectiveShadowQualificationPolicy",
]
