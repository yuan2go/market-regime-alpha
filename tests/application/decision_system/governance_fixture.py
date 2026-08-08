"""Explicit engineering-only Production authorization fixtures."""

from __future__ import annotations

from hashlib import sha256

from market_regime_alpha.core.identity import (
    ArtifactId,
    FeatureDefinitionId,
    ModelId,
    UniverseId,
)
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.platform.contracts import ModelLifecycleStatus
from market_regime_alpha.platform.runtime_governance import (
    ArtifactLineageReference,
    AssignmentLane,
    ModelGovernancePolicy,
    ModelRuntimeAssignment,
    ModelSelectionReceipt,
    ModelSelectionRequest,
    QualificationEvidenceKind,
    RuntimeModelLineage,
    RuntimePurpose,
)


def runtime_model_lineage(
    model_id: str,
    *,
    dataset: ArtifactLineageReference | None = None,
    universe_id: UniverseId | None = None,
    data_eligibility: DataEligibility = DataEligibility.EXPLORATORY,
) -> RuntimeModelLineage:
    raw_definition_hash = sha256(model_id.encode("utf-8")).hexdigest()
    content = canonical_hash({"fixture_model_id": model_id})
    return RuntimeModelLineage.create(
        model_id=ModelId(model_id),
        definition_hash=raw_definition_hash,
        dataset=dataset
        or ArtifactLineageReference(
            "DECISION_FIXTURE_DATASET",
            ArtifactId("decision-fixture-dataset"),
            content,
        ),
        universe_id=universe_id or UniverseId("decision-fixture-universe"),
        feature_definition_ids=(FeatureDefinitionId("decision-fixture-feature"),),
        feature_materializations=(
            dataset
            or ArtifactLineageReference(
                "FEATURE_MATERIALIZATION",
                ArtifactId("decision-fixture-materialization"),
                content,
            ),
        ),
        configuration=ArtifactLineageReference(
            "MODEL_CONFIGURATION",
            ArtifactId(f"decision-fixture-config:{model_id}"),
            content,
        ),
        code_revision="decision-system-engineering-fixture",
        code_hash=content,
        validation_protocol_refs=(
            ArtifactLineageReference(
                "VALIDATION_PROTOCOL",
                ArtifactId("decision-fixture-validation"),
                content,
            ),
        ),
        data_eligibility=data_eligibility,
    )


class EngineeringFixtureProductionSelector:
    """Typed unit fixture; it is neither PostgreSQL nor Production evidence."""

    def select(self, request: ModelSelectionRequest) -> ModelSelectionReceipt:
        if request.preselection_rejection_codes:
            return ModelSelectionReceipt.rejected(
                request_hash=request.request_hash,
                runtime_scope=request.runtime_scope,
                model_slot=request.model_slot,
                purpose=request.purpose,
                governance_revision=1,
                runtime_lineage_hash=(
                    request.runtime_lineage.runtime_lineage_hash
                ),
                reason_codes=request.preselection_rejection_codes,
                selected_at=request.selected_at,
            )
        policy = ModelGovernancePolicy.create(
            name="engineering-fixture-production-policy",
            version="1",
            purpose=RuntimePurpose.PRODUCTION_DECISION,
            allowed_lifecycle_statuses=(ModelLifecycleStatus.ACTIVE,),
            required_evidence_kinds=tuple(QualificationEvidenceKind),
            allowed_data_eligibilities=(DataEligibility.FORMAL_RESEARCH,),
            production_authorization=True,
        )
        champion = ModelRuntimeAssignment.create(
            runtime_scope=request.runtime_scope,
            model_slot=request.model_slot,
            purpose=request.purpose,
            lane=AssignmentLane.CHAMPION,
            model_id=request.runtime_lineage.model_id,
            definition_hash=request.runtime_lineage.definition_hash,
            policy_id=policy.policy_id,
            policy_hash=policy.policy_hash,
            effective_at=request.selected_at,
            actor="pytest-fixture",
            reason="Decision Runtime unit-test Production fixture",
            approval_ref="fixture:not-production-evidence",
            governance_revision=1,
        )
        digest = canonical_hash(
            {"fixture_qualification": str(request.runtime_lineage.model_id)}
        )
        return ModelSelectionReceipt.accepted(
            request_hash=request.request_hash,
            runtime_scope=request.runtime_scope,
            model_slot=request.model_slot,
            purpose=request.purpose,
            governance_revision=1,
            policy=policy,
            champion=champion,
            challengers=(),
            qualification_decision_id=ArtifactId(
                f"fixture-production-qualification:{request.runtime_lineage.model_id}"
            ),
            qualification_decision_hash=digest,
            selected_registry_version=1,
            runtime_lineage_hash=request.runtime_lineage.runtime_lineage_hash,
            evidence_ids=(ArtifactId(f"fixture-evidence:{digest[-24:]}"),),
            selected_at=request.selected_at,
            production_authorized=True,
        )


FIXTURE_PRODUCTION_SELECTOR = EngineeringFixtureProductionSelector()
