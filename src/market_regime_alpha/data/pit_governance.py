"""Narrow bridge from satisfied Formal PIT evidence to Model Governance."""

from __future__ import annotations

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.pit_authority import (
    PITArtifactReference,
    PITValidationOutcome,
)
from market_regime_alpha.data.postgres_pit_authority import PostgresPITAuthority
from market_regime_alpha.platform.postgres_runtime_governance import (
    PostgresModelGovernanceRepository,
)
from market_regime_alpha.platform.runtime_governance import (
    ArtifactLineageReference,
    ModelQualificationEvidence,
    ModelVersionLineage,
    QualificationEvidenceKind,
    QualificationEvidenceOutcome,
)


def record_formal_pit_qualification_evidence(
    *,
    pit_authority: PostgresPITAuthority,
    model_governance: PostgresModelGovernanceRepository,
    pit_evidence_id: ArtifactId,
    model_lineage: ModelVersionLineage,
    actor: str,
    reason: str,
    idempotency_key: str,
) -> ModelQualificationEvidence:
    """Consume one immutable satisfied PIT artifact without granting qualification."""

    pit_evidence = pit_authority.get_evidence(pit_evidence_id)
    if pit_evidence.outcome is not PITValidationOutcome.SATISFIED:
        raise ValueError("rejected Formal PIT evidence cannot enter Model Governance")
    pit_lineage = pit_evidence.lineage
    mismatches: list[str] = []
    for label, pit_value, model_value in (
        ("model", pit_lineage.model_id, model_lineage.model_id),
        ("definition", pit_lineage.definition_hash, model_lineage.definition_hash),
        ("lineage_id", pit_lineage.model_lineage_id, model_lineage.lineage_id),
        ("lineage_hash", pit_lineage.model_lineage_hash, model_lineage.lineage_hash),
        (
            "feature_definitions",
            pit_lineage.feature_definition_ids,
            tuple(str(item) for item in model_lineage.feature_definition_ids),
        ),
        (
            "configuration",
            _governance_reference(
                pit_lineage.configuration,
                reference_kind="MODEL_CONFIGURATION",
            ),
            model_lineage.configuration,
        ),
        ("code_revision", pit_lineage.code_revision, model_lineage.code_revision),
        ("code_hash", pit_lineage.code_hash, model_lineage.code_hash),
    ):
        if pit_value != model_value:
            mismatches.append(label)
    validation_protocol = _governance_reference(pit_lineage.validation_protocol)
    if validation_protocol not in model_lineage.validation_protocol_refs:
        mismatches.append("validation_protocol")
    if mismatches:
        raise ValueError("Formal PIT/Model lineage mismatch: " + ",".join(mismatches))

    qualification_evidence = ModelQualificationEvidence.create(
        model_id=model_lineage.model_id,
        definition_hash=model_lineage.definition_hash,
        lineage_id=model_lineage.lineage_id,
        lineage_hash=model_lineage.lineage_hash,
        evidence_kind=QualificationEvidenceKind.FORMAL_PIT,
        outcome=QualificationEvidenceOutcome.SATISFIED,
        evidence=ArtifactLineageReference(
            reference_kind="FORMAL_PIT_VALIDATION",
            artifact_id=pit_evidence.evidence_id,
            content_hash=pit_evidence.evidence_hash,
        ),
        validation_protocol_ref=validation_protocol,
        available_at=pit_evidence.available_at,
        recorded_at=pit_evidence.recorded_at,
        actor=actor,
        reason=reason,
    )
    return model_governance.record_evidence(
        qualification_evidence,
        idempotency_key=idempotency_key,
    )


def _governance_reference(
    reference: PITArtifactReference,
    *,
    reference_kind: str | None = None,
) -> ArtifactLineageReference:
    return ArtifactLineageReference(
        reference_kind=reference_kind or reference.reference_kind,
        artifact_id=reference.artifact_id,
        content_hash=reference.content_hash,
    )


__all__ = ["record_formal_pit_qualification_evidence"]
