from __future__ import annotations

from datetime import timedelta

import pytest

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.pit_authority import (
    FormalPITValidationRequest,
    PITArtifactReference,
    PITFactKind,
    PITValidationLineage,
)
from market_regime_alpha.data.pit_governance import (
    record_formal_pit_qualification_evidence,
)
from market_regime_alpha.data.postgres_pit_authority import PostgresPITAuthority
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.platform.durable_governance import PersistentModelRegistry
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
from tests.persistence.postgres.pit_fixture import (
    DECISION_TIME,
    INGEST_TIME,
    MutableClock,
    NOW,
    authorize_source,
    pit_authority,
    pit_fact,
    ref,
    required_facts,
)
from tests.platform.test_platform_kernel import _model_definition
from tests.platform.test_runtime_governance import HASH_C, _lineage


def _pit_reference(reference: ArtifactLineageReference) -> PITArtifactReference:
    return PITArtifactReference(
        reference.reference_kind,
        reference.artifact_id,
        reference.content_hash,
    )


def _matching_pit_lineage(model_lineage: ModelVersionLineage) -> PITValidationLineage:
    return PITValidationLineage(
        model_id=model_lineage.model_id,
        definition_hash=model_lineage.definition_hash,
        model_lineage_id=model_lineage.lineage_id,
        model_lineage_hash=model_lineage.lineage_hash,
        dataset=ref("DATASET", "formal-dataset"),
        source_manifests=(ref("SOURCE_MANIFEST", "formal-source-manifest"),),
        universe=ref("UNIVERSE", "formal-universe"),
        eligibility=ref("ELIGIBILITY", "formal-eligibility"),
        feature_definition_ids=tuple(
            str(item) for item in model_lineage.feature_definition_ids
        ),
        feature_materializations=(
            ref("FEATURE_MATERIALIZATION", "formal-feature-run"),
        ),
        configuration=_pit_reference(model_lineage.configuration),
        code_revision=model_lineage.code_revision,
        code_hash=model_lineage.code_hash,
        validation_protocol=_pit_reference(
            model_lineage.validation_protocol_refs[0]
        ),
        adjustment_mode="RAW",
    )


def _record_model_lineage(
    governance: PostgresModelGovernanceRepository,
) -> ModelVersionLineage:
    definition = _model_definition()
    PersistentModelRegistry(governance).register(
        definition,
        idempotency_key="pit-governance-register-model",
    )
    return governance.record_version_lineage(
        _lineage(definition),
        actor="governance-operator",
        reason="bind model lineage for PIT evidence",
        idempotency_key="pit-governance-model-lineage",
    )


def _record_pit_evidence(
    pit: PostgresPITAuthority,
    clock: MutableClock,
    lineage: PITValidationLineage,
    *,
    idempotency_prefix: str,
):
    authorize_source(
        pit,
        source_manifest=lineage.source_manifests[0],
        idempotency_key=f"{idempotency_prefix}-source",
    )
    artifact_by_kind = {
        PITFactKind.MARKET_DATA: lineage.dataset,
        PITFactKind.UNIVERSE_MEMBERSHIP: lineage.universe,
        PITFactKind.TRADING_STATUS: lineage.eligibility,
        PITFactKind.ST_STATUS: lineage.eligibility,
        PITFactKind.LISTING_STATUS: lineage.eligibility,
        PITFactKind.TRADING_ELIGIBILITY: lineage.eligibility,
        PITFactKind.FEATURE_MATERIALIZATION: lineage.feature_materializations[0],
    }
    for index, required in enumerate(required_facts()):
        pit.record_fact(
            pit_fact(
                required,
                artifact=artifact_by_kind.get(
                    required.fact_kind,
                    ref(required.fact_kind.value, f"formal-{required.fact_kind.value}"),
                ),
                source_manifest=lineage.source_manifests[0],
            ),
            actor="source-ingestor",
            reason="record governed Formal PIT fixture",
            idempotency_key=f"{idempotency_prefix}-fact-{index}",
        )
    clock.value = NOW
    return pit.validate(
        FormalPITValidationRequest.create(
            scope_id="daily:2026-08-08",
            decision_time=DECISION_TIME,
            symbols=("600000.SH",),
            required_facts=required_facts(),
            lineage=lineage,
            actor="pit-validator",
            reason="validate immutable Formal PIT evidence",
            idempotency_key=f"{idempotency_prefix}-validate",
        )
    )


def test_satisfied_pit_evidence_enters_existing_governance_without_qualification(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    governance = PostgresModelGovernanceRepository(postgres_factory)
    model_lineage = _record_model_lineage(governance)
    lineage = _matching_pit_lineage(model_lineage)
    clock = MutableClock(INGEST_TIME)
    pit = pit_authority(postgres_factory, clock=clock)
    formal_pit = _record_pit_evidence(
        pit,
        clock,
        lineage,
        idempotency_prefix="satisfied-pit",
    )

    consumed = record_formal_pit_qualification_evidence(
        pit_authority=pit,
        model_governance=governance,
        pit_evidence_id=formal_pit.evidence_id,
        model_lineage=model_lineage,
        actor="governance-reviewer",
        reason="consume PIT evidence reference only",
        idempotency_key="consume-formal-pit",
    )

    assert consumed.evidence_kind is QualificationEvidenceKind.FORMAL_PIT
    assert consumed.evidence.artifact_id == formal_pit.evidence_id
    assert consumed.evidence.content_hash == formal_pit.evidence_hash
    mismatched_lineage = ModelVersionLineage.create(
        model_id=model_lineage.model_id,
        model_version=model_lineage.model_version,
        definition_hash=model_lineage.definition_hash,
        target_id=model_lineage.target_id,
        universe_contract_id=model_lineage.universe_contract_id,
        feature_definition_ids=model_lineage.feature_definition_ids,
        model_parameter_hash=model_lineage.model_parameter_hash,
        configuration=model_lineage.configuration,
        implementation_ref=model_lineage.implementation_ref,
        code_revision="different-code-revision",
        code_hash=model_lineage.code_hash,
        validation_protocol_refs=model_lineage.validation_protocol_refs,
        supported_data_eligibilities=model_lineage.supported_data_eligibilities,
        created_at=model_lineage.created_at + timedelta(seconds=1),
    )
    with pytest.raises(ValueError, match="Formal PIT/Model lineage mismatch"):
        record_formal_pit_qualification_evidence(
            pit_authority=pit,
            model_governance=governance,
            pit_evidence_id=formal_pit.evidence_id,
            model_lineage=mismatched_lineage,
            actor="governance-reviewer",
            reason="must not consume mismatched evidence",
            idempotency_key="consume-mismatched-pit",
        )
    with postgres_factory.connection(read_only=True) as connection:
        qualification_count = connection.execute(
            "SELECT count(*) FROM model_qualification_decision"
        ).fetchone()
        assignment_count = connection.execute(
            "SELECT count(*) FROM model_runtime_assignment"
        ).fetchone()
    assert qualification_count == (0,)
    assert assignment_count == (0,)


def test_caller_cannot_forge_formal_pit_governance_evidence(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    governance = PostgresModelGovernanceRepository(postgres_factory)
    lineage = _record_model_lineage(governance)
    forged = ModelQualificationEvidence.create(
        model_id=lineage.model_id,
        definition_hash=lineage.definition_hash,
        lineage_id=lineage.lineage_id,
        lineage_hash=lineage.lineage_hash,
        evidence_kind=QualificationEvidenceKind.FORMAL_PIT,
        outcome=QualificationEvidenceOutcome.SATISFIED,
        evidence=ArtifactLineageReference(
            "FORMAL_PIT_VALIDATION",
            ArtifactId("caller-invented-pit-evidence"),
            HASH_C,
        ),
        validation_protocol_ref=lineage.validation_protocol_refs[0],
        available_at=NOW,
        recorded_at=NOW,
        actor="caller",
        reason="attempt forged Formal PIT authority",
    )

    with pytest.raises(ValueError, match="not owned by PIT Data Authority"):
        governance.record_evidence(
            forged,
            idempotency_key="forged-formal-pit",
        )
    with postgres_factory.connection(read_only=True) as connection:
        count = connection.execute(
            "SELECT count(*) FROM model_governance_action "
            "WHERE idempotency_key = 'forged-formal-pit'"
        ).fetchone()
    assert count == (0,)


def test_rejected_pit_evidence_cannot_be_consumed(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    governance = PostgresModelGovernanceRepository(postgres_factory)
    model_lineage = _record_model_lineage(governance)
    lineage = _matching_pit_lineage(model_lineage)
    clock = MutableClock(INGEST_TIME)
    pit = pit_authority(postgres_factory, clock=clock)
    authorize_source(pit, idempotency_key="rejected-pit-source")
    for index, required in enumerate(required_facts()):
        pit.record_fact(
            pit_fact(required),
            actor="source-ingestor",
            reason="record mismatched PIT lineage",
            idempotency_key=f"rejected-pit-fact-{index}",
        )
    clock.value = NOW
    rejected = pit.validate(
        FormalPITValidationRequest.create(
            scope_id="daily:2026-08-08",
            decision_time=DECISION_TIME,
            symbols=("600000.SH",),
            required_facts=required_facts(),
            lineage=lineage,
            actor="pit-validator",
            reason="reject mismatched PIT lineage",
            idempotency_key="rejected-pit-validate",
        )
    )

    with pytest.raises(ValueError, match="rejected Formal PIT"):
        record_formal_pit_qualification_evidence(
            pit_authority=pit,
            model_governance=governance,
            pit_evidence_id=rejected.evidence_id,
            model_lineage=model_lineage,
            actor="governance-reviewer",
            reason="must not consume rejected evidence",
            idempotency_key="consume-rejected-pit",
        )
