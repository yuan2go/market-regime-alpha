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
    PITFactKind,
    PITFactRevision,
    PITRequiredFact,
    PITValidationLineage,
    PITValidationOutcome,
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
    evidence = FormalPITEvidenceArtifact.create(
        request_hash=HASH_A,
        snapshot_id=ArtifactId("pit-snapshot-a"),
        snapshot_hash=HASH_B,
        authority_revision=7,
        lineage=lineage(),
        outcome=PITValidationOutcome.SATISFIED,
        rejection_codes=(),
        selected_fact_references=((ArtifactId("pit-fact-a"), HASH_A),),
        available_at=DECISION_TIME,
        recorded_at=DECISION_TIME,
        actor="pit-validator",
        reason="formal point-in-time validation",
    )

    assert FormalPITEvidenceArtifact.from_canonical_dict(evidence.to_canonical_dict()) == evidence
    assert str(evidence.evidence_id).startswith("formal-pit-evidence-")
