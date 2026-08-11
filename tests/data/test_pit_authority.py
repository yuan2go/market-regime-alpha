from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from market_regime_alpha.core.identity import ArtifactId, ModelId
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.data.pit_authority import (
    FormalPITEvidenceArtifact,
    FormalPITValidationRequest,
    PITArtifactReference,
    PITAsOfQuery,
    PITArtifactKind,
    PITContractError,
    PITFactEvidenceMode,
    PITFactKind,
    PITFactRevision,
    PITFactTemporalAuthority,
    PITProviderEvidence,
    PITProviderEvidenceKind,
    PITProviderEvidenceUse,
    ProviderFactCeiling,
    PITRequiredFact,
    PITSelectedFactAuthority,
    PITValidationLineage,
    PITValidationOutcome,
    PITSourceEvidenceLevel,
    ProviderQualificationPolicy,
    ProviderQualificationPolicyV2,
    formal_pit_request_rejection_codes,
)


UTC = timezone.utc
DECISION_TIME = datetime(2026, 8, 8, 6, 45, tzinfo=UTC)
HASH_A = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64


def reference(kind: str, name: str, content_hash: str = HASH_A) -> PITArtifactReference:
    return PITArtifactReference(kind, ArtifactId(name), content_hash)


def fact(**overrides: object) -> PITFactRevision:
    values: dict[str, object] = {
        "scope_id": "daily:2026-08-08",
        "logical_key": "market:600000.SH:2026-08-08T06:44:00Z",
        "fact_kind": PITFactKind.MARKET_DATA,
        "subject": "600000.SH",
        "revision": 1,
        "supersedes_fact_id": None,
        "event_time": datetime(2026, 8, 8, 6, 44, tzinfo=UTC),
        "effective_from": datetime(2026, 8, 8, 6, 44, tzinfo=UTC),
        "effective_to": None,
        "available_at": datetime(2026, 8, 8, 6, 44, 1, tzinfo=UTC),
        "recorded_at": datetime(2026, 8, 8, 6, 44, 2, tzinfo=UTC),
        "artifact": reference("DATASET", "dataset-a"),
        "source_manifest": reference("SOURCE_MANIFEST", "manifest-a", HASH_B),
        "provider_id": "formal-provider",
        "provider_contract": "formal-provider-contract-v1",
        "temporal_authority": PITFactTemporalAuthority(
            mode=PITFactEvidenceMode.PROSPECTIVE_CAPTURED_PIT,
            provider_id="formal-provider",
            provider_contract="formal-provider-contract-v1",
            provider_available_at=datetime(2026, 8, 8, 6, 44, 1, tzinfo=UTC),
            provider_recorded_at=datetime(2026, 8, 8, 6, 44, 2, tzinfo=UTC),
        ),
        "value_json": '{"close":"10.12"}',
        "data_eligibility": DataEligibility.FORMAL_RESEARCH,
    }
    values.update(overrides)
    return PITFactRevision.create(**values)


def lineage() -> PITValidationLineage:
    return PITValidationLineage(
        model_id=ModelId("model-a"),
        definition_hash="d" * 64,
        model_lineage_id=ArtifactId("model-lineage-a"),
        model_lineage_hash=HASH_A,
        dataset=reference("DATASET", "dataset-a"),
        source_manifests=(reference("SOURCE_MANIFEST", "manifest-a", HASH_B),),
        universe=reference("UNIVERSE", "universe-a"),
        eligibility=reference("ELIGIBILITY", "eligibility-a"),
        feature_definition_ids=("feature-a",),
        feature_materializations=(reference("FEATURE_MATERIALIZATION", "feature-run-a"),),
        configuration=reference("CONFIGURATION", "config-a"),
        code_revision="commit-a",
        code_hash=HASH_A,
        validation_protocol=reference("VALIDATION_PROTOCOL", "pit-protocol-a"),
        adjustment_mode="RAW",
    )


def request(required: tuple[PITRequiredFact, ...]) -> FormalPITValidationRequest:
    return FormalPITValidationRequest.create(
        scope_id="daily:2026-08-08",
        decision_time=DECISION_TIME,
        symbols=("600000.SH",),
        required_facts=required,
        lineage=lineage(),
        actor="pit-validator",
        reason="formal point-in-time validation",
        idempotency_key="pit-validation-a",
    )


@pytest.mark.parametrize(
    "required",
    [
        (
            PITRequiredFact("collision", PITFactKind.MARKET_DATA, "600000.SH"),
            PITRequiredFact("collision", PITFactKind.ST_STATUS, "600000.SH"),
        ),
        (
            PITRequiredFact("collision", PITFactKind.ST_STATUS, "600000.SH"),
            PITRequiredFact("collision", PITFactKind.ST_STATUS, "600001.SH"),
        ),
        (
            PITRequiredFact("collision", PITFactKind.ST_STATUS, "600000.SH"),
            PITRequiredFact("collision", PITFactKind.ST_STATUS, "600000.SH"),
        ),
    ],
)
def test_required_fact_logical_key_collision_is_rejected(
    required: tuple[PITRequiredFact, ...],
) -> None:
    with pytest.raises(PITContractError, match="logical_key collision"):
        request(required)
    with pytest.raises(PITContractError, match="logical_key collision"):
        PITAsOfQuery.create(
            scope_id="daily:2026-08-08",
            decision_time=DECISION_TIME,
            required_facts=required,
        )


def test_direct_query_construction_cannot_bypass_logical_key_collision() -> None:
    required = (
        PITRequiredFact("collision", PITFactKind.MARKET_DATA, "600000.SH"),
        PITRequiredFact("collision", PITFactKind.MARKET_DATA, "600001.SH"),
    )

    with pytest.raises(PITContractError, match="logical_key collision"):
        PITAsOfQuery(
            query_hash=HASH_A,
            scope_id="daily:2026-08-08",
            decision_time=DECISION_TIME,
            required_facts=required,
        )

    with pytest.raises(PITContractError, match="logical_key collision"):
        FormalPITValidationRequest(
            request_hash=HASH_A,
            scope_id="daily:2026-08-08",
            decision_time=DECISION_TIME,
            symbols=("600000.SH",),
            required_facts=required,
            lineage=lineage(),
            actor="pit-validator",
            reason="malformed direct caller construction",
            idempotency_key="malformed-direct-request",
        )


def test_default_provider_policy_prevents_authority_inflation() -> None:
    policy = ProviderQualificationPolicy.default()

    for provider_id in (
        "tencent",
        "baostock",
        "akshare",
        "tushare-free",
        "xuntou",
        "unknown-provider",
    ):
        with pytest.raises(PITContractError, match="evidence ceiling"):
            policy.require_level(
                provider_id,
                PITSourceEvidenceLevel.FORMAL_PIT_PROVIDER,
            )


def test_provider_policy_v2_is_scoped_by_contract_and_fact_kind() -> None:
    policy = ProviderQualificationPolicyV2.default()

    assert policy.maximum_level(
        "provider-baostock-public",
        provider_contract="baostock-public-history-v1",
        fact_kind=PITFactKind.MARKET_DATA,
    ) is PITSourceEvidenceLevel.FREE_DATA_EXPLORATORY
    assert policy.maximum_level(
        "provider-baostock-public",
        provider_contract="baostock-public-history-v1",
        fact_kind=PITFactKind.ST_STATUS,
    ) is PITSourceEvidenceLevel.PIT_INCOMPLETE
    with pytest.raises(PITContractError, match="MARKET_DATA"):
        policy.require_level(
            "provider-baostock-public",
            PITSourceEvidenceLevel.FORMAL_PIT_PROVIDER,
            provider_contract="baostock-public-history-v1",
            fact_kinds=(PITFactKind.MARKET_DATA,),
        )

    candidate = ProviderQualificationPolicyV2.create(
        scope_ceilings=(
            ProviderFactCeiling(
                "qualified-provider",
                "qualified-contract-v1",
                PITFactKind.MARKET_DATA,
                PITSourceEvidenceLevel.FORMAL_PIT_PROVIDER,
            ),
        ),
        default_ceiling=PITSourceEvidenceLevel.PIT_INCOMPLETE,
    )
    candidate.require_level(
        "qualified-provider",
        PITSourceEvidenceLevel.FORMAL_PIT_PROVIDER,
        provider_contract="qualified-contract-v1",
        fact_kinds=(PITFactKind.MARKET_DATA,),
    )
    with pytest.raises(PITContractError, match="ST_STATUS"):
        candidate.require_level(
            "qualified-provider",
            PITSourceEvidenceLevel.FORMAL_PIT_PROVIDER,
            provider_contract="qualified-contract-v1",
            fact_kinds=(PITFactKind.ST_STATUS,),
        )


def test_historical_provider_mode_requires_typed_revision_archive_evidence() -> None:
    with pytest.raises(PITContractError, match="revision and dataset version"):
        PITFactTemporalAuthority(
            mode=PITFactEvidenceMode.HISTORICAL_PROVIDER_PIT,
            provider_id="formal-provider",
            provider_contract="formal-provider-contract-v1",
            provider_available_at=DECISION_TIME,
            provider_recorded_at=DECISION_TIME,
        )

    evidence = tuple(
        sorted(
            (
                PITProviderEvidence(
                    kind,
                    reference(
                        PITArtifactKind.PROVIDER_EVIDENCE.value,
                        "provider-evidence-" + kind.value.lower(),
                    ),
                    "formal-provider",
                    "formal-provider-contract-v1",
                    PITProviderEvidenceUse.HISTORICAL_PROVIDER_PIT,
                )
                for kind in (
                    PITProviderEvidenceKind.HISTORICAL_AVAILABILITY,
                    PITProviderEvidenceKind.REVISION_POLICY,
                    PITProviderEvidenceKind.ARCHIVE_INTEGRITY,
                )
            ),
            key=lambda item: (
                item.evidence_kind.value,
                item.reference.reference_kind,
                str(item.reference.artifact_id),
                item.reference.content_hash,
            ),
        )
    )
    temporal = PITFactTemporalAuthority(
        mode=PITFactEvidenceMode.HISTORICAL_PROVIDER_PIT,
        provider_id="formal-provider",
        provider_contract="formal-provider-contract-v1",
        provider_available_at=DECISION_TIME,
        provider_recorded_at=DECISION_TIME,
        provider_revision="provider-revision-1",
        provider_dataset_version="provider-dataset-2024-v1",
        provider_archive=reference(
            PITArtifactKind.PROVIDER_ARCHIVE.value,
            "provider-archive-2024",
        ),
        provider_evidence=evidence,
    )

    assert temporal.mode is PITFactEvidenceMode.HISTORICAL_PROVIDER_PIT


def test_provider_evidence_cannot_use_an_arbitrary_reference_kind() -> None:
    with pytest.raises(PITContractError, match="PROVIDER_EVIDENCE"):
        PITProviderEvidence(
            PITProviderEvidenceKind.PROVIDER_CONTRACT,
            reference("ARBITRARY_STRING", "fake-evidence"),
            "formal-provider",
            "formal-provider-contract-v1",
            PITProviderEvidenceUse.SOURCE_QUALIFICATION,
        )


def test_validation_lineage_rejects_real_artifact_in_wrong_authority_slot() -> None:
    with pytest.raises(PITContractError, match="validation dataset requires DATASET"):
        replace(
            lineage(),
            dataset=reference("UNIVERSE", "real-but-wrong-universe"),
        )


def test_fact_rejects_real_artifact_kind_outside_fact_semantics() -> None:
    with pytest.raises(PITContractError, match="PIT Fact artifact requires DATASET"):
        fact(artifact=reference("UNIVERSE", "real-but-wrong-universe"))


def test_historical_provider_evidence_cannot_cross_provider_or_use() -> None:
    evidence = tuple(
        sorted(
            (
                PITProviderEvidence(
                    kind,
                    reference(
                        PITArtifactKind.PROVIDER_EVIDENCE.value,
                        "wrong-provider-" + kind.value.lower(),
                    ),
                    "different-provider",
                    "different-contract",
                    PITProviderEvidenceUse.SOURCE_QUALIFICATION,
                )
                for kind in (
                    PITProviderEvidenceKind.HISTORICAL_AVAILABILITY,
                    PITProviderEvidenceKind.REVISION_POLICY,
                    PITProviderEvidenceKind.ARCHIVE_INTEGRITY,
                )
            ),
            key=lambda item: (
                item.evidence_kind.value,
                item.provider_id,
                item.provider_contract,
            ),
        )
    )
    with pytest.raises(PITContractError, match="Provider, contract and use"):
        PITFactTemporalAuthority(
            mode=PITFactEvidenceMode.HISTORICAL_PROVIDER_PIT,
            provider_id="formal-provider",
            provider_contract="formal-provider-contract-v1",
            provider_available_at=DECISION_TIME,
            provider_recorded_at=DECISION_TIME,
            provider_revision="r1",
            provider_dataset_version="v1",
            provider_archive=reference(
                PITArtifactKind.PROVIDER_ARCHIVE.value,
                "provider-archive-a",
            ),
            provider_evidence=evidence,
        )


def test_fact_revision_has_canonical_identity_and_round_trips() -> None:
    original = fact()

    assert PITFactRevision.from_canonical_dict(original.to_canonical_dict()) == original
    assert str(original.fact_id).startswith("pit-fact-")


def test_fact_revision_rejects_temporal_and_revision_forgery() -> None:
    with pytest.raises(ValueError, match="available before event"):
        fact(available_at=datetime(2026, 8, 8, 6, 43, tzinfo=UTC))
    with pytest.raises(ValueError, match="recorded before available"):
        fact(recorded_at=datetime(2026, 8, 8, 6, 44, tzinfo=UTC))
    with pytest.raises(ValueError, match="revision one cannot supersede"):
        fact(supersedes_fact_id=ArtifactId("pit-fact-old"))
    with pytest.raises(ValueError, match="later revision requires superseded fact"):
        fact(revision=2)
    with pytest.raises(ValueError, match="canonical JSON"):
        fact(value_json='{"z":1, "a":2}')


def test_formal_request_reports_incomplete_symbol_and_global_coverage() -> None:
    incomplete = request(
        (
            PITRequiredFact(
                logical_key="market:600000.SH:2026-08-08T06:44:00Z",
                fact_kind=PITFactKind.MARKET_DATA,
                subject="600000.SH",
            ),
        )
    )

    assert formal_pit_request_rejection_codes(incomplete) == (
        "FEATURE_MATERIALIZATION_COVERAGE_MISSING",
        "LISTING_STATUS_COVERAGE_MISSING:600000.SH",
        "ST_STATUS_COVERAGE_MISSING:600000.SH",
        "TRADING_CALENDAR_COVERAGE_MISSING",
        "TRADING_ELIGIBILITY_COVERAGE_MISSING:600000.SH",
        "TRADING_STATUS_COVERAGE_MISSING:600000.SH",
        "UNIVERSE_MEMBERSHIP_COVERAGE_MISSING:600000.SH",
    )


def test_research_back_adjustment_is_never_formal_pit() -> None:
    forged = request(())
    forged = FormalPITValidationRequest.create(
        scope_id=forged.scope_id,
        decision_time=forged.decision_time,
        symbols=forged.symbols,
        required_facts=forged.required_facts,
        lineage=replace(lineage(), adjustment_mode="RESEARCH_BACK_ADJUSTED"),
        actor=forged.actor,
        reason=forged.reason,
        idempotency_key="pit-validation-back-adjusted",
    )

    assert "RESEARCH_BACK_ADJUSTED_NOT_PIT_SAFE" in formal_pit_request_rejection_codes(forged)


def test_formal_evidence_identity_binds_snapshot_and_lineage() -> None:
    selected_authority = PITSelectedFactAuthority(
        fact_id=ArtifactId("pit-fact-a"),
        fact_hash=HASH_A,
        source_qualification_id=ArtifactId("qualification-a"),
        source_qualification_hash=HASH_A,
        artifact_resolution_id=ArtifactId("artifact-resolution-a"),
        artifact_resolution_hash=HASH_A,
        source_manifest_resolution_id=ArtifactId("manifest-resolution-a"),
        source_manifest_resolution_hash=HASH_B,
        temporal_resolution_references=(),
        system_time_authority="POSTGRESQL_CLOCK",
    )
    evidence = FormalPITEvidenceArtifact.create(
        request_hash=HASH_A,
        snapshot_id=ArtifactId("pit-snapshot-a"),
        snapshot_hash=HASH_B,
        authority_revision=7,
        lineage=lineage(),
        outcome=PITValidationOutcome.SATISFIED,
        rejection_codes=(),
        selected_fact_references=((ArtifactId("pit-fact-a"), HASH_A),),
        selected_fact_authorities=(selected_authority,),
        lineage_resolution_references=((ArtifactId("lineage-resolution-a"), HASH_A),),
        available_at=DECISION_TIME,
        recorded_at=DECISION_TIME,
        actor="pit-validator",
        reason="formal point-in-time validation",
    )

    assert FormalPITEvidenceArtifact.from_canonical_dict(evidence.to_canonical_dict()) == evidence
    assert str(evidence.evidence_id).startswith("formal-pit-evidence-")
