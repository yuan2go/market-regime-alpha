"""Model Registry with explicit lifecycle and evidence-level authority."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

from market_regime_alpha.core.identity import ModelId
from market_regime_alpha.platform.contracts import EvidenceLevel, ModelDefinition, ModelLifecycleStatus


def _require_aware(value: datetime) -> None:
    if not isinstance(value, datetime):
        raise TypeError("transition time must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("transition time must be timezone-aware")


def _require_non_empty(label: str, value: str) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{label} must be a non-empty trimmed string")


_ALLOWED_TRANSITIONS: dict[ModelLifecycleStatus, frozenset[ModelLifecycleStatus]] = {
    ModelLifecycleStatus.DRAFT: frozenset({ModelLifecycleStatus.RESEARCH, ModelLifecycleStatus.RETIRED}),
    ModelLifecycleStatus.RESEARCH: frozenset({ModelLifecycleStatus.BACKTESTED, ModelLifecycleStatus.SUSPENDED, ModelLifecycleStatus.RETIRED}),
    ModelLifecycleStatus.BACKTESTED: frozenset({ModelLifecycleStatus.OOS_VALIDATED, ModelLifecycleStatus.RESEARCH, ModelLifecycleStatus.SUSPENDED}),
    ModelLifecycleStatus.OOS_VALIDATED: frozenset({ModelLifecycleStatus.SHADOW, ModelLifecycleStatus.SUSPENDED}),
    ModelLifecycleStatus.SHADOW: frozenset({ModelLifecycleStatus.PROMOTION_CANDIDATE, ModelLifecycleStatus.DEGRADED, ModelLifecycleStatus.SUSPENDED}),
    ModelLifecycleStatus.PROMOTION_CANDIDATE: frozenset({ModelLifecycleStatus.ACTIVE, ModelLifecycleStatus.SHADOW, ModelLifecycleStatus.SUSPENDED}),
    ModelLifecycleStatus.ACTIVE: frozenset({ModelLifecycleStatus.DEGRADED, ModelLifecycleStatus.SUSPENDED, ModelLifecycleStatus.RETIRED}),
    ModelLifecycleStatus.DEGRADED: frozenset({ModelLifecycleStatus.SHADOW, ModelLifecycleStatus.SUSPENDED, ModelLifecycleStatus.RETIRED}),
    ModelLifecycleStatus.SUSPENDED: frozenset({ModelLifecycleStatus.RESEARCH, ModelLifecycleStatus.SHADOW, ModelLifecycleStatus.RETIRED}),
    ModelLifecycleStatus.RETIRED: frozenset(),
}


@dataclass(frozen=True, slots=True)
class ModelLifecycleTransition:
    model_id: ModelId
    from_status: ModelLifecycleStatus
    to_status: ModelLifecycleStatus
    changed_at: datetime
    reason: str
    evidence_refs: tuple[str, ...]
    approval_ref: str | None = None

    def __post_init__(self) -> None:
        _require_aware(self.changed_at)
        _require_non_empty("reason", self.reason)
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("evidence_refs must be unique")
        for value in self.evidence_refs:
            _require_non_empty("evidence_ref", value)
        if self.approval_ref is not None:
            _require_non_empty("approval_ref", self.approval_ref)


@dataclass(frozen=True, slots=True)
class ModelRegistration:
    definition: ModelDefinition
    lifecycle_status: ModelLifecycleStatus
    evidence_level: EvidenceLevel
    transitions: tuple[ModelLifecycleTransition, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.lifecycle_status, ModelLifecycleStatus):
            raise TypeError("lifecycle_status must be a ModelLifecycleStatus")
        if not isinstance(self.evidence_level, EvidenceLevel):
            raise TypeError("evidence_level must be an EvidenceLevel")
        for transition in self.transitions:
            if transition.model_id != self.definition.model_id:
                raise ValueError("transition model identity mismatch")


class ModelRegistry:
    """Single in-memory authority for immutable model definitions and lifecycle state."""

    def __init__(self) -> None:
        self._registrations: dict[ModelId, ModelRegistration] = {}

    def register(
        self,
        definition: ModelDefinition,
        *,
        lifecycle_status: ModelLifecycleStatus = ModelLifecycleStatus.DRAFT,
        evidence_level: EvidenceLevel = EvidenceLevel.UNQUALIFIED,
    ) -> ModelRegistration:
        registration = ModelRegistration(definition, lifecycle_status, evidence_level)
        existing = self._registrations.get(definition.model_id)
        if existing is not None and existing != registration:
            raise ValueError(f"model identity conflict: {definition.model_id}")
        self._registrations[definition.model_id] = registration
        return registration

    def get(self, model_id: ModelId) -> ModelRegistration:
        try:
            return self._registrations[model_id]
        except KeyError as exc:
            raise KeyError(str(model_id)) from exc

    def transition(
        self,
        model_id: ModelId,
        *,
        to_status: ModelLifecycleStatus,
        changed_at: datetime,
        reason: str,
        evidence_refs: tuple[str, ...] = (),
        evidence_level: EvidenceLevel | None = None,
        approval_ref: str | None = None,
    ) -> ModelRegistration:
        current = self.get(model_id)
        if to_status not in _ALLOWED_TRANSITIONS[current.lifecycle_status]:
            raise ValueError(f"invalid model lifecycle transition: {current.lifecycle_status.value}->{to_status.value}")
        if to_status in {
            ModelLifecycleStatus.OOS_VALIDATED,
            ModelLifecycleStatus.SHADOW,
            ModelLifecycleStatus.PROMOTION_CANDIDATE,
            ModelLifecycleStatus.ACTIVE,
        } and not evidence_refs:
            raise ValueError("promotion transition requires evidence_refs")
        if to_status is ModelLifecycleStatus.ACTIVE and approval_ref is None:
            raise ValueError("ACTIVE transition requires approval_ref")
        next_evidence = evidence_level or current.evidence_level
        if (
            next_evidence is not EvidenceLevel.UNQUALIFIED
            and next_evidence not in current.definition.supported_data_grades
            and next_evidence not in {EvidenceLevel.SHADOW_EVIDENCE, EvidenceLevel.LIVE_OBSERVED}
        ):
            raise ValueError("evidence level is incompatible with model definition")
        transition = ModelLifecycleTransition(
            model_id=model_id,
            from_status=current.lifecycle_status,
            to_status=to_status,
            changed_at=changed_at,
            reason=reason,
            evidence_refs=evidence_refs,
            approval_ref=approval_ref,
        )
        updated = replace(
            current,
            lifecycle_status=to_status,
            evidence_level=next_evidence,
            transitions=current.transitions + (transition,),
        )
        self._registrations[model_id] = updated
        return updated

    def by_status(self, status: ModelLifecycleStatus) -> tuple[ModelRegistration, ...]:
        return tuple(
            sorted(
                (item for item in self._registrations.values() if item.lifecycle_status is status),
                key=lambda item: str(item.definition.model_id),
            )
        )

    def __len__(self) -> int:
        return len(self._registrations)
