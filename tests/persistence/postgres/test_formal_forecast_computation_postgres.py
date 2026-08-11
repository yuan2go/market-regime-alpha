from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from market_regime_alpha.application.research_validation.formal_forecast_computation import (
    FormalForecastComputationRequest,
)
from market_regime_alpha.application.research_validation.formal_protocol import (
    OutcomeTargetForecastStatus,
)
from market_regime_alpha.application.research_validation.postgres_formal_protocol import (
    FormalProtocolConflict,
    PostgresFormalProtocolRepository,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.pit_authority import (
    FormalPITValidationRequest,
    PITArtifactKind,
    PITArtifactReference,
    PITFactEvidenceMode,
    PITFactKind,
    PITFactTemporalAuthority,
    PITProviderEvidence,
    PITProviderEvidenceKind,
    PITProviderEvidenceUse,
    PITValidationLineage,
    PITValidationOutcome,
)
from market_regime_alpha.data.postgres_pit_authority import PostgresPITAuthority
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from tests.persistence.postgres.phase_c_owner_fixture import (
    StablePhaseCPITResolver,
    record_phase_c_protocol_owners,
)
from tests.persistence.postgres.pit_fixture import (
    HASH_A,
    HASH_B,
    fixture_provider_policy,
    pit_fact,
    required_facts,
    source_qualification,
)


DECISION_TIME = datetime(2026, 1, 21, 6, 45, tzinfo=UTC)
SYMBOL = "600000.SH"
SOURCE = PITArtifactReference(
    PITArtifactKind.SOURCE_MANIFEST.value,
    ArtifactId("source-manifest-a"),
    HASH_B,
)
ELIGIBILITY = PITArtifactReference(
    PITArtifactKind.ELIGIBILITY.value,
    ArtifactId("eligibility-a"),
    HASH_A,
)
FEATURE_MATERIALIZATION = PITArtifactReference(
    PITArtifactKind.FEATURE_MATERIALIZATION.value,
    ArtifactId("feature-run-a"),
    HASH_A,
)


def test_owner_computed_forecast_is_idempotent_and_deterministically_replayable(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    fixture = record_phase_c_protocol_owners(postgres_factory)
    repository = PostgresFormalProtocolRepository(postgres_factory)
    repository.record_protocol(protocol=fixture.protocol)
    evidence = _record_formal_pit(postgres_factory, fixture)
    assert evidence.outcome is PITValidationOutcome.SATISFIED
    request = FormalForecastComputationRequest.create(
        formal_protocol_id=fixture.protocol.protocol_id,
        formal_pit_evidence_id=evidence.evidence_id,
        symbol=SYMBOL,
        idempotency_key="phase-c-owner-forecast-compute",
    )

    first = repository.compute_forecast(request)
    second = repository.compute_forecast(request)

    assert first == second
    assert repository.replay_forecast_computation(first.receipt_id) == first
    forecast = repository.get_forecast(first.forecast_reference.artifact_id)
    assert forecast.decision_time == DECISION_TIME
    assert forecast.created_at == first.materialized_at
    assert all(
        item.status is OutcomeTargetForecastStatus.NOT_ESTIMABLE
        and item.reason_codes == ("FORMAL_FORECAST_EXECUTOR_UNSUPPORTED",)
        for item in forecast.estimates
    )
    with postgres_factory.connection(read_only=True) as connection:
        row = connection.execute(
            """
            SELECT forecast_authority, production_authorized
            FROM outcome_target_bound_forecast WHERE forecast_id = %s
            """,
            (str(forecast.forecast_id),),
        ).fetchone()
        assert row == ("FORMAL_OWNER_COMPUTED", False)
        assert connection.execute(
            "SELECT count(*) FROM formal_forecast_computation_command"
        ).fetchone()[0] == 1

    conflicting = FormalForecastComputationRequest.create(
        formal_protocol_id=fixture.protocol.protocol_id,
        formal_pit_evidence_id=evidence.evidence_id,
        symbol="000001.SZ",
        idempotency_key=request.idempotency_key,
    )
    with pytest.raises(FormalProtocolConflict, match="idempotency key conflict"):
        repository.compute_forecast(conflicting)


def _record_formal_pit(postgres_factory, fixture):
    authority = PostgresPITAuthority(
        postgres_factory,
        artifact_resolver=StablePhaseCPITResolver(),
        provider_policy=fixture_provider_policy(),
    )
    authority.record_source_qualification(
        source_qualification(source_manifest=SOURCE),
        idempotency_key="phase-c-formal-pit-source",
    )
    lineage = PITValidationLineage(
        model_id=fixture.model_lineage.model_id,
        definition_hash=fixture.model_lineage.definition_hash,
        model_lineage_id=fixture.model_lineage.lineage_id,
        model_lineage_hash=fixture.model_lineage.lineage_hash,
        dataset=PITArtifactReference(
            PITArtifactKind.MARKET_DATA_DATASET.value,
            fixture.protocol.dataset_reference.artifact_id,
            fixture.protocol.dataset_reference.content_hash,
        ),
        source_manifests=(SOURCE,),
        universe=PITArtifactReference(
            PITArtifactKind.UNIVERSE.value,
            fixture.protocol.universe_reference.artifact_id,
            fixture.protocol.universe_reference.content_hash,
        ),
        eligibility=ELIGIBILITY,
        feature_definition_ids=tuple(
            str(item) for item in fixture.model_lineage.feature_definition_ids
        ),
        feature_materializations=(FEATURE_MATERIALIZATION,),
        configuration=PITArtifactReference(
            PITArtifactKind.CONFIGURATION.value,
            fixture.model_lineage.configuration.artifact_id,
            fixture.model_lineage.configuration.content_hash,
        ),
        code_revision=fixture.model_lineage.code_revision,
        code_hash=fixture.model_lineage.code_hash,
        validation_protocol=PITArtifactReference(
            PITArtifactKind.VALIDATION_PROTOCOL.value,
            fixture.evaluation.protocol_id,
            fixture.evaluation.protocol_hash,
        ),
        adjustment_mode="RAW",
    )
    artifact_by_kind = {
        PITFactKind.MARKET_DATA: lineage.dataset,
        PITFactKind.UNIVERSE_MEMBERSHIP: lineage.universe,
        PITFactKind.TRADING_CALENDAR: PITArtifactReference(
            PITArtifactKind.TRADING_CALENDAR.value,
            fixture.protocol.trading_calendar_reference.artifact_id,
            fixture.protocol.trading_calendar_reference.content_hash,
        ),
        PITFactKind.TRADING_STATUS: ELIGIBILITY,
        PITFactKind.ST_STATUS: ELIGIBILITY,
        PITFactKind.LISTING_STATUS: ELIGIBILITY,
        PITFactKind.TRADING_ELIGIBILITY: ELIGIBILITY,
        PITFactKind.FEATURE_MATERIALIZATION: FEATURE_MATERIALIZATION,
    }
    available_at = DECISION_TIME - timedelta(minutes=4)
    recorded_at = DECISION_TIME - timedelta(minutes=3)
    temporal = _historical_temporal_authority(
        available_at=available_at,
        recorded_at=recorded_at,
    )
    facts = required_facts()
    for index, required in enumerate(facts):
        authority.record_fact(
            pit_fact(
                required,
                scope_id="phase-c:2026-01-21",
                event_time=DECISION_TIME - timedelta(minutes=5),
                effective_from=DECISION_TIME - timedelta(minutes=5),
                available_at=available_at,
                recorded_at=recorded_at,
                artifact=artifact_by_kind[required.fact_kind],
                source_manifest=SOURCE,
                temporal_authority=temporal,
            ),
            actor="phase-c-formal-pit-test",
            reason="record historical Provider PIT fact",
            idempotency_key=f"phase-c-formal-pit-fact-{index}",
        )
    return authority.validate(
        FormalPITValidationRequest.create(
            scope_id="phase-c:2026-01-21",
            decision_time=DECISION_TIME,
            symbols=(SYMBOL,),
            required_facts=facts,
            lineage=lineage,
            actor="phase-c-formal-pit-validator",
            reason="validate Phase C Formal PIT computation scope",
            idempotency_key="phase-c-formal-pit-validate",
        )
    )


def _historical_temporal_authority(
    *,
    available_at: datetime,
    recorded_at: datetime,
) -> PITFactTemporalAuthority:
    evidence = tuple(
        PITProviderEvidence(
            evidence_kind=kind,
            reference=PITArtifactReference(
                PITArtifactKind.PROVIDER_EVIDENCE.value,
                ArtifactId(f"phase-c-historical-{kind.value.lower()}"),
                HASH_A,
            ),
            provider_id="formal-provider",
            provider_contract="formal-provider-contract-v1",
            evidence_use=PITProviderEvidenceUse.HISTORICAL_PROVIDER_PIT,
        )
        for kind in sorted(
            (
                PITProviderEvidenceKind.ARCHIVE_INTEGRITY,
                PITProviderEvidenceKind.HISTORICAL_AVAILABILITY,
                PITProviderEvidenceKind.REVISION_POLICY,
            ),
            key=lambda item: item.value,
        )
    )
    return PITFactTemporalAuthority(
        mode=PITFactEvidenceMode.HISTORICAL_PROVIDER_PIT,
        provider_id="formal-provider",
        provider_contract="formal-provider-contract-v1",
        provider_available_at=available_at,
        provider_recorded_at=recorded_at,
        provider_revision="phase-c-provider-revision-r1",
        provider_dataset_version="phase-c-provider-dataset-v1",
        provider_archive=PITArtifactReference(
            PITArtifactKind.PROVIDER_ARCHIVE.value,
            ArtifactId("phase-c-historical-provider-archive"),
            HASH_A,
        ),
        provider_evidence=evidence,
    )
