from __future__ import annotations

from datetime import UTC, datetime

import pytest

from market_regime_alpha.core.identity import (
    ArtifactId,
    DatasetId,
    FeatureMaterializationId,
    ModelId,
    UniverseId,
)
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.platform.contracts import (
    EvidenceLevel,
    ModelLifecycleStatus,
)
from market_regime_alpha.platform.model_registry import ModelRegistry
from market_regime_alpha.platform.runtime_governance import (
    ArtifactLineageReference,
    AssignmentLane,
    ModelGovernancePolicy,
    ModelQualificationEvidence,
    ModelRuntimeAssignment,
    ModelSelectionReceipt,
    ModelVersionLineage,
    QualificationEvidenceKind,
    QualificationEvidenceOutcome,
    QualificationStatus,
    RuntimeModelLineage,
    RuntimePurpose,
    SelectionStatus,
    evaluate_qualification,
)
from tests.platform.test_platform_kernel import _model_definition


NOW = datetime(2026, 8, 8, 6, 0, tzinfo=UTC)
HASH_A = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64
HASH_C = "sha256:" + "c" * 64


def _lineage(definition=None) -> ModelVersionLineage:
    definition = definition or _model_definition()
    return ModelVersionLineage.create(
        model_id=definition.model_id,
        model_version=definition.version,
        definition_hash=definition.definition_hash,
        target_id=definition.target_id,
        universe_contract_id=definition.universe_id,
        feature_definition_ids=definition.feature_ids,
        model_parameter_hash=definition.parameter_hash,
        configuration=ArtifactLineageReference(
            reference_kind="MODEL_CONFIGURATION",
            artifact_id=ArtifactId("model-config-v1"),
            content_hash=HASH_A,
        ),
        implementation_ref=definition.implementation_ref,
        code_revision="bd868b06df13c4a657a169e5039c91c1d69a5ef9",
        code_hash=HASH_B,
        validation_protocol_refs=(
            ArtifactLineageReference(
                reference_kind="VALIDATION_PROTOCOL",
                artifact_id=ArtifactId("validation-protocol-v1"),
                content_hash=HASH_C,
            ),
        ),
        supported_data_eligibilities=definition.supported_data_eligibilities,
        created_at=NOW,
    )


def _runtime_lineage(
    lineage: ModelVersionLineage,
    *,
    configuration_hash: str = HASH_A,
    data_eligibility: DataEligibility = DataEligibility.EXPLORATORY,
) -> RuntimeModelLineage:
    return RuntimeModelLineage.create(
        model_id=lineage.model_id,
        definition_hash=lineage.definition_hash,
        dataset=ArtifactLineageReference(
            "DATASET", ArtifactId(str(DatasetId("daily-dataset-2026-08-08"))), HASH_A
        ),
        universe_id=UniverseId("daily-universe-2026-08-08"),
        feature_definition_ids=lineage.feature_definition_ids,
        feature_materializations=(
            ArtifactLineageReference(
                "FEATURE_MATERIALIZATION",
                ArtifactId(
                    str(FeatureMaterializationId("feature-values-2026-08-08"))
                ),
                HASH_B,
            ),
        ),
        configuration=ArtifactLineageReference(
            "MODEL_CONFIGURATION",
            lineage.configuration.artifact_id,
            configuration_hash,
        ),
        code_revision=lineage.code_revision,
        code_hash=lineage.code_hash,
        validation_protocol_refs=lineage.validation_protocol_refs,
        data_eligibility=data_eligibility,
    )


def _evidence(
    lineage: ModelVersionLineage,
    kind: QualificationEvidenceKind,
    *,
    outcome: QualificationEvidenceOutcome = QualificationEvidenceOutcome.SATISFIED,
    at: datetime = NOW,
    validation_protocol_ref: ArtifactLineageReference | None = None,
) -> ModelQualificationEvidence:
    return ModelQualificationEvidence.create(
        model_id=lineage.model_id,
        definition_hash=lineage.definition_hash,
        lineage_id=lineage.lineage_id,
        lineage_hash=lineage.lineage_hash,
        evidence_kind=kind,
        outcome=outcome,
        evidence=ArtifactLineageReference(
            reference_kind=kind.value,
            artifact_id=ArtifactId(f"evidence-{kind.value.lower()}"),
            content_hash=HASH_C,
        ),
        validation_protocol_ref=(
            validation_protocol_ref or lineage.validation_protocol_refs[0]
        ),
        available_at=at,
        recorded_at=at,
        actor="research-reviewer",
        reason="explicit WP-GOV-01 engineering evidence",
    )


def _research_policy() -> ModelGovernancePolicy:
    return ModelGovernancePolicy.create(
        name="research-runtime-policy",
        version="1",
        purpose=RuntimePurpose.RESEARCH,
        allowed_lifecycle_statuses=(ModelLifecycleStatus.RESEARCH,),
        required_evidence_kinds=(
            QualificationEvidenceKind.DATASET_INTEGRITY,
            QualificationEvidenceKind.FEATURE_LINEAGE,
            QualificationEvidenceKind.IMPLEMENTATION_REPRODUCIBILITY,
        ),
        allowed_data_eligibilities=(DataEligibility.EXPLORATORY,),
        production_authorization=False,
    )


def test_version_and_runtime_lineage_are_distinct_and_content_addressed() -> None:
    lineage = _lineage()
    runtime = _runtime_lineage(lineage)

    assert runtime.universe_id != lineage.universe_contract_id
    assert runtime.runtime_lineage_hash.startswith("sha256:")
    assert runtime.model_id == lineage.model_id
    assert runtime.configuration == lineage.configuration

    mismatched_lineage = ModelVersionLineage.create(
        model_id=lineage.model_id,
        model_version=lineage.model_version,
        definition_hash=lineage.definition_hash,
        target_id=lineage.target_id,
        universe_contract_id=lineage.universe_contract_id,
        feature_definition_ids=lineage.feature_definition_ids,
        model_parameter_hash=lineage.model_parameter_hash,
        configuration=ArtifactLineageReference(
            "MODEL_CONFIGURATION", ArtifactId("model-config-v2"), HASH_C
        ),
        implementation_ref=lineage.implementation_ref,
        code_revision=lineage.code_revision,
        code_hash=lineage.code_hash,
        validation_protocol_refs=lineage.validation_protocol_refs,
        supported_data_eligibilities=lineage.supported_data_eligibilities,
        created_at=lineage.created_at,
    )
    with pytest.raises(ValueError, match="configuration"):
        runtime.validate_against(mismatched_lineage)


def test_qualification_requires_explicit_complete_satisfied_evidence() -> None:
    definition = _model_definition()
    registry = ModelRegistry()
    registry.register(definition)
    registration = registry.transition(
        definition.model_id,
        to_status=ModelLifecycleStatus.RESEARCH,
        changed_at=NOW,
        reason="explicit research transition",
        evidence_refs=("governance-evidence",),
        evidence_level=EvidenceLevel.EXPLORATORY,
    )
    lineage = _lineage()
    policy = _research_policy()
    evidence = tuple(_evidence(lineage, kind) for kind in policy.required_evidence_kinds)

    qualified = evaluate_qualification(
        registration=registration,
        lineage=lineage,
        policy=policy,
        evidence=evidence,
        decided_at=NOW,
        actor="governance-reviewer",
        reason="approve research-only runtime use",
        approval_ref="approval:wp-gov-01-research",
        governance_revision=7,
    )

    assert qualified.status is QualificationStatus.QUALIFIED
    assert qualified.production_authorized is False
    assert qualified.evidence_ids == tuple(sorted((item.evidence_id for item in evidence), key=str))

    rejected = evaluate_qualification(
        registration=registration,
        lineage=lineage,
        policy=policy,
        evidence=evidence[:-1],
        decided_at=NOW,
        actor="governance-reviewer",
        reason="record incomplete evidence",
        approval_ref="approval:wp-gov-01-research",
        governance_revision=8,
    )
    assert rejected.status is QualificationStatus.NOT_QUALIFIED
    assert "REQUIRED_EVIDENCE_MISSING" in rejected.reason_codes


def test_production_policy_cannot_be_satisfied_by_research_evidence() -> None:
    definition = _model_definition()
    registry = ModelRegistry()
    registry.register(definition)
    research = registry.transition(
        definition.model_id,
        to_status=ModelLifecycleStatus.RESEARCH,
        changed_at=NOW,
        reason="research only",
        evidence_refs=("research-evidence",),
        evidence_level=EvidenceLevel.EXPLORATORY,
    )
    lineage = _lineage()
    production = ModelGovernancePolicy.create(
        name="production-decision-policy",
        version="1",
        purpose=RuntimePurpose.PRODUCTION_DECISION,
        allowed_lifecycle_statuses=(ModelLifecycleStatus.ACTIVE,),
        required_evidence_kinds=tuple(QualificationEvidenceKind),
        allowed_data_eligibilities=(DataEligibility.FORMAL_RESEARCH,),
        production_authorization=True,
    )

    decision = evaluate_qualification(
        registration=research,
        lineage=lineage,
        policy=production,
        evidence=(),
        decided_at=NOW,
        actor="governance-reviewer",
        reason="record fail-closed production review",
        approval_ref=None,
        governance_revision=9,
    )

    assert decision.status is QualificationStatus.NOT_QUALIFIED
    assert decision.production_authorized is False
    assert set(decision.reason_codes) == {
        "LIFECYCLE_NOT_ALLOWED",
        "PRODUCTION_APPROVAL_REQUIRED",
        "REQUIRED_EVIDENCE_MISSING",
    }


def test_policy_cannot_make_terminal_lifecycle_or_weak_evidence_production_eligible() -> None:
    with pytest.raises(ValueError, match="Suspended or retired"):
        ModelGovernancePolicy.create(
            name="invalid-suspended-research-policy",
            version="1",
            purpose=RuntimePurpose.RESEARCH,
            allowed_lifecycle_statuses=(ModelLifecycleStatus.SUSPENDED,),
            required_evidence_kinds=(QualificationEvidenceKind.DATASET_INTEGRITY,),
            allowed_data_eligibilities=(DataEligibility.EXPLORATORY,),
            production_authorization=False,
        )

    with pytest.raises(ValueError, match="mandatory evidence floor"):
        ModelGovernancePolicy.create(
            name="invalid-weak-production-policy",
            version="1",
            purpose=RuntimePurpose.PRODUCTION_DECISION,
            allowed_lifecycle_statuses=(ModelLifecycleStatus.ACTIVE,),
            required_evidence_kinds=(QualificationEvidenceKind.OPERATOR_APPROVAL,),
            allowed_data_eligibilities=(DataEligibility.FORMAL_RESEARCH,),
            production_authorization=True,
        )


def test_assignment_and_selection_keep_challenger_out_of_authoritative_output() -> None:
    lineage = _lineage()
    policy = _research_policy()
    champion = ModelRuntimeAssignment.create(
        runtime_scope="DAILY_LOOP",
        model_slot="DAILY_B0",
        purpose=RuntimePurpose.RESEARCH,
        lane=AssignmentLane.CHAMPION,
        model_id=lineage.model_id,
        definition_hash=lineage.definition_hash,
        policy_id=policy.policy_id,
        policy_hash=policy.policy_hash,
        effective_at=NOW,
        actor="governance-operator",
        reason="explicit research Champion",
        approval_ref="approval:daily-b0-research",
        governance_revision=10,
    )
    challenger = ModelRuntimeAssignment.create(
        runtime_scope="DAILY_LOOP",
        model_slot="DAILY_B0",
        purpose=RuntimePurpose.RESEARCH,
        lane=AssignmentLane.CHALLENGER,
        model_id=ModelId("candidate-challenger-v1"),
        definition_hash="d" * 64,
        policy_id=policy.policy_id,
        policy_hash=policy.policy_hash,
        effective_at=NOW,
        actor="governance-operator",
        reason="shadow comparison only",
        approval_ref="approval:daily-b0-challenger",
        governance_revision=11,
    )

    receipt = ModelSelectionReceipt.accepted(
        request_hash=HASH_A,
        runtime_scope="DAILY_LOOP",
        model_slot="DAILY_B0",
        purpose=RuntimePurpose.RESEARCH,
        governance_revision=11,
        policy=policy,
        champion=champion,
        challengers=(challenger,),
        qualification_decision_id=ArtifactId("qualification-decision-a"),
        qualification_decision_hash=HASH_B,
        selected_registry_version=1,
        runtime_lineage_hash=HASH_C,
        evidence_ids=(ArtifactId("evidence-a"),),
        selected_at=NOW,
    )

    assert receipt.status is SelectionStatus.SELECTED
    assert receipt.selected_model_id == champion.model_id
    assert receipt.challenger_model_ids == (challenger.model_id,)
    assert receipt.production_authorized is False
