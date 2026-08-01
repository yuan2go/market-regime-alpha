"""Strict canonical serialization for durable governance repositories."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from market_regime_alpha.core.identity import (
    DatasetId,
    FeatureDefinitionId,
    ModelId,
    TargetId,
    UniverseId,
)
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.platform.contracts import (
    EvidenceLevel,
    EvaluationProtocolId,
    ModelDefinition,
    ModelLifecycleStatus,
    ModelRole,
    ResearchHypothesisId,
    TheoryId,
)
from market_regime_alpha.platform.experiment_governance import (
    ExperimentBudget,
    FrozenExperimentProtocol,
    PrimaryChangeDimension,
    ResearchHypothesis,
)
from market_regime_alpha.platform.model_registry import (
    ModelLifecycleTransition,
    ModelRegistration,
)


def model_registration_to_dict(
    registration: ModelRegistration,
) -> dict[str, Any]:
    return {
        "definition": registration.definition.canonical_payload(),
        "lifecycle_status": registration.lifecycle_status.value,
        "evidence_level": registration.evidence_level.value,
        "transitions": [
            {
                "model_id": str(item.model_id),
                "from_status": item.from_status.value,
                "to_status": item.to_status.value,
                "changed_at": item.changed_at.isoformat(),
                "reason": item.reason,
                "evidence_refs": list(item.evidence_refs),
                "evidence_level": item.evidence_level.value,
                "approval_ref": item.approval_ref,
            }
            for item in registration.transitions
        ],
    }


def model_registration_from_dict(
    payload: Mapping[str, Any],
) -> ModelRegistration:
    _fields(
        payload,
        {"definition", "lifecycle_status", "evidence_level", "transitions"},
        "ModelRegistration",
    )
    return ModelRegistration(
        definition=model_definition_from_dict(_mapping(payload["definition"])),
        lifecycle_status=ModelLifecycleStatus(str(payload["lifecycle_status"])),
        evidence_level=EvidenceLevel(str(payload["evidence_level"])),
        transitions=tuple(
            model_transition_from_dict(_mapping(item))
            for item in _array(payload["transitions"])
        ),
    )


def model_definition_from_dict(
    payload: Mapping[str, Any],
) -> ModelDefinition:
    expected = {
        "schema_version",
        "model_id",
        "name",
        "version",
        "family",
        "role",
        "target_id",
        "universe_id",
        "feature_ids",
        "implementation_ref",
        "parameter_hash",
        "decision_time_convention",
        "horizon",
        "theory_ids",
        "parent_model_id",
        "supported_data_eligibilities",
        "compatibility_refs",
    }
    _fields(payload, expected, "ModelDefinition")
    if payload["schema_version"] != ModelDefinition.SCHEMA_VERSION:
        raise ValueError("unsupported ModelDefinition schema")
    parent = payload["parent_model_id"]
    return ModelDefinition(
        model_id=ModelId(str(payload["model_id"])),
        name=str(payload["name"]),
        version=str(payload["version"]),
        family=str(payload["family"]),
        role=ModelRole(str(payload["role"])),
        target_id=TargetId(str(payload["target_id"])),
        universe_id=UniverseId(str(payload["universe_id"])),
        feature_ids=tuple(
            FeatureDefinitionId(item) for item in _strings(payload["feature_ids"])
        ),
        implementation_ref=str(payload["implementation_ref"]),
        parameter_hash=str(payload["parameter_hash"]),
        decision_time_convention=str(payload["decision_time_convention"]),
        horizon=str(payload["horizon"]),
        theory_ids=tuple(
            TheoryId(item) for item in _strings(payload["theory_ids"])
        ),
        parent_model_id=ModelId(str(parent)) if parent is not None else None,
        supported_data_eligibilities=tuple(
            DataEligibility(item)
            for item in _strings(payload["supported_data_eligibilities"])
        ),
        compatibility_refs=_strings(payload["compatibility_refs"]),
    )


def model_transition_from_dict(
    payload: Mapping[str, Any],
) -> ModelLifecycleTransition:
    _fields(
        payload,
        {
            "model_id",
            "from_status",
            "to_status",
            "changed_at",
            "reason",
            "evidence_refs",
            "evidence_level",
            "approval_ref",
        },
        "ModelLifecycleTransition",
    )
    approval = payload["approval_ref"]
    return ModelLifecycleTransition(
        model_id=ModelId(str(payload["model_id"])),
        from_status=ModelLifecycleStatus(str(payload["from_status"])),
        to_status=ModelLifecycleStatus(str(payload["to_status"])),
        changed_at=datetime.fromisoformat(str(payload["changed_at"])),
        reason=str(payload["reason"]),
        evidence_refs=_strings(payload["evidence_refs"]),
        evidence_level=EvidenceLevel(str(payload["evidence_level"])),
        approval_ref=str(approval) if approval is not None else None,
    )


def experiment_protocol_from_dict(
    payload: Mapping[str, Any],
) -> FrozenExperimentProtocol:
    expected = {
        "schema_version",
        "hypothesis",
        "model_id",
        "parent_model_id",
        "dataset_id",
        "universe_id",
        "target_ids",
        "evaluation_protocol_id",
        "feature_ids",
        "parameter_variants",
        "primary_change",
        "comparison_model_ids",
        "sample_split_ref",
        "cost_model_ref",
        "code_revision",
        "environment_ref",
        "budget",
    }
    _fields(payload, expected, "FrozenExperimentProtocol")
    if payload["schema_version"] != FrozenExperimentProtocol.SCHEMA_VERSION:
        raise ValueError("unsupported FrozenExperimentProtocol schema")
    hypothesis = _mapping(payload["hypothesis"])
    _fields(
        hypothesis,
        {
            "hypothesis_id",
            "statement",
            "rationale",
            "expected_result",
            "counter_evidence",
            "invalidation_condition",
        },
        "ResearchHypothesis",
    )
    budget = _mapping(payload["budget"])
    _fields(
        budget,
        {
            "max_parameter_variants",
            "max_targets",
            "max_validation_accesses",
            "max_sealed_test_accesses",
        },
        "ExperimentBudget",
    )
    parent = payload["parent_model_id"]
    return FrozenExperimentProtocol(
        hypothesis=ResearchHypothesis(
            hypothesis_id=ResearchHypothesisId(
                str(hypothesis["hypothesis_id"])
            ),
            statement=str(hypothesis["statement"]),
            rationale=str(hypothesis["rationale"]),
            expected_result=str(hypothesis["expected_result"]),
            counter_evidence=_strings(hypothesis["counter_evidence"]),
            invalidation_condition=str(hypothesis["invalidation_condition"]),
        ),
        model_id=ModelId(str(payload["model_id"])),
        parent_model_id=ModelId(str(parent)) if parent is not None else None,
        dataset_id=DatasetId(str(payload["dataset_id"])),
        universe_id=UniverseId(str(payload["universe_id"])),
        target_ids=tuple(
            TargetId(item) for item in _strings(payload["target_ids"])
        ),
        evaluation_protocol_id=EvaluationProtocolId(
            str(payload["evaluation_protocol_id"])
        ),
        feature_ids=tuple(
            FeatureDefinitionId(item)
            for item in _strings(payload["feature_ids"])
        ),
        parameter_variants=tuple(
            tuple((str(pair[0]), str(pair[1])) for pair in _pairs(variant))
            for variant in _array(payload["parameter_variants"])
        ),
        primary_change=PrimaryChangeDimension(str(payload["primary_change"])),
        comparison_model_ids=tuple(
            ModelId(item) for item in _strings(payload["comparison_model_ids"])
        ),
        sample_split_ref=str(payload["sample_split_ref"]),
        cost_model_ref=str(payload["cost_model_ref"]),
        code_revision=str(payload["code_revision"]),
        environment_ref=str(payload["environment_ref"]),
        budget=ExperimentBudget(
            max_parameter_variants=int(budget["max_parameter_variants"]),
            max_targets=int(budget["max_targets"]),
            max_validation_accesses=int(budget["max_validation_accesses"]),
            max_sealed_test_accesses=int(budget["max_sealed_test_accesses"]),
        ),
    )


def _fields(
    payload: Mapping[str, Any], expected: set[str], label: str
) -> None:
    if set(payload) != expected:
        raise ValueError(f"{label} fields mismatch")


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("governance value must be an object")
    return value


def _array(value: object) -> list[object]:
    if not isinstance(value, list):
        raise ValueError("governance value must be an array")
    return value


def _strings(value: object) -> tuple[str, ...]:
    items = _array(value)
    if any(not isinstance(item, str) for item in items):
        raise ValueError("governance value must be a string array")
    return tuple(str(item) for item in items)


def _pairs(value: object) -> tuple[tuple[object, object], ...]:
    items = _array(value)
    result: list[tuple[object, object]] = []
    for item in items:
        if not isinstance(item, list) or len(item) != 2:
            raise ValueError("parameter variant must contain key/value pairs")
        result.append((item[0], item[1]))
    return tuple(result)
