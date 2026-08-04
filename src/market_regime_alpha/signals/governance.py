"""Controlled governance registration for the Canonical Decimal Signal model.

Registration is deliberately an explicit application action. Importing this
module or constructing a lifecycle stage never mutates the Model Registry.
"""

from __future__ import annotations

from datetime import datetime

from market_regime_alpha.core.identity import FeatureDefinitionId, TargetId, UniverseId
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.platform.contracts import (
    EvidenceLevel,
    ModelDefinition,
    ModelLifecycleStatus,
    ModelRole,
)
from market_regime_alpha.platform.durable_governance import PersistentModelRegistry
from market_regime_alpha.platform.model_registry import ModelRegistration, ModelRegistry
from market_regime_alpha.platform.repositories import VersionedModelRegistration
from market_regime_alpha.signals.decimal_model import SignalModelConfigurationV2
from market_regime_alpha.signals.input_v3 import SignalInputMappingConfigurationV2


CANONICAL_SIGNAL_TARGET_ID = TargetId("canonical-signal-observation-v3")


def canonical_signal_model_definition(
    *,
    universe_id: UniverseId,
    mapping: SignalInputMappingConfigurationV2,
    model_configuration: SignalModelConfigurationV2,
) -> ModelDefinition:
    """Bind the governed model identity to exact features and parameters."""

    mapping.verify_identity()
    model_configuration.verify_identity()
    return ModelDefinition(
        model_id=model_configuration.model_id,
        name="Canonical five-factor Decimal Signal",
        version=model_configuration.model_version,
        family="CANONICAL_SIGNAL",
        role=ModelRole.CANDIDATE,
        target_id=CANONICAL_SIGNAL_TARGET_ID,
        universe_id=universe_id,
        feature_ids=tuple(
            sorted(
                {
                    FeatureDefinitionId(item.source_feature_id)
                    for item in mapping.mappings
                },
                key=str,
            )
        ),
        implementation_ref=(
            "market_regime_alpha.signals.decimal_model:CanonicalSignalModelV2"
        ),
        parameter_hash=model_configuration.configuration_hash,
        decision_time_convention="EXPLICIT_CANONICAL_DECISION_TIME",
        horizon="SIGNAL_OBSERVATION_ONLY_NO_AUTOMATIC_HOLDING_PERIOD",
        supported_data_eligibilities=(DataEligibility.EXPLORATORY,),
        compatibility_refs=(
            "signal-run-artifact-v1-reader-replay-only",
            "signal-run-artifact-v2-reader-replay-only",
        ),
    )


def register_canonical_signal_model_for_research(
    registry: ModelRegistry,
    *,
    universe_id: UniverseId,
    mapping: SignalInputMappingConfigurationV2,
    model_configuration: SignalModelConfigurationV2,
    changed_at: datetime,
    evidence_refs: tuple[str, ...],
    transition_reason: str,
    approval_boundary_ref: str,
) -> ModelRegistration:
    """Register DRAFT then explicitly transition only to RESEARCH/EXPLORATORY."""

    if not evidence_refs:
        raise ValueError("Canonical Signal research registration requires evidence refs")
    definition = canonical_signal_model_definition(
        universe_id=universe_id,
        mapping=mapping,
        model_configuration=model_configuration,
    )
    registry.register(definition)
    registration = registry.transition(
        definition.model_id,
        to_status=ModelLifecycleStatus.RESEARCH,
        changed_at=changed_at,
        reason=transition_reason,
        evidence_refs=evidence_refs,
        evidence_level=EvidenceLevel.EXPLORATORY,
        approval_ref=approval_boundary_ref,
    )
    if (
        registration.lifecycle_status is not ModelLifecycleStatus.RESEARCH
        or registration.evidence_level is not EvidenceLevel.EXPLORATORY
    ):
        raise AssertionError("Canonical Signal registration exceeded its authority ceiling")
    return registration


def persist_canonical_signal_model_for_research(
    registry: PersistentModelRegistry,
    *,
    universe_id: UniverseId,
    mapping: SignalInputMappingConfigurationV2,
    model_configuration: SignalModelConfigurationV2,
    changed_at: datetime,
    evidence_refs: tuple[str, ...],
    transition_reason: str,
    approval_boundary_ref: str,
    registration_idempotency_key: str,
    transition_idempotency_key: str,
) -> VersionedModelRegistration:
    """Persist the same bounded DRAFT→RESEARCH transition with CAS evidence."""

    if not evidence_refs:
        raise ValueError("Canonical Signal research registration requires evidence refs")
    definition = canonical_signal_model_definition(
        universe_id=universe_id,
        mapping=mapping,
        model_configuration=model_configuration,
    )
    draft = registry.register(
        definition,
        idempotency_key=registration_idempotency_key,
    )
    result = registry.transition(
        definition.model_id,
        expected_version=draft.version,
        idempotency_key=transition_idempotency_key,
        to_status=ModelLifecycleStatus.RESEARCH,
        changed_at=changed_at,
        reason=transition_reason,
        evidence_refs=evidence_refs,
        evidence_level=EvidenceLevel.EXPLORATORY,
        approval_ref=approval_boundary_ref,
    )
    if (
        result.registration.lifecycle_status is not ModelLifecycleStatus.RESEARCH
        or result.registration.evidence_level is not EvidenceLevel.EXPLORATORY
    ):
        raise AssertionError("Canonical Signal registration exceeded its authority ceiling")
    return result


__all__ = [
    "CANONICAL_SIGNAL_TARGET_ID",
    "canonical_signal_model_definition",
    "persist_canonical_signal_model_for_research",
    "register_canonical_signal_model_for_research",
]
