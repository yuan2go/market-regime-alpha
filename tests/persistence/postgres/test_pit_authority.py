from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import replace
from datetime import timedelta

import pytest

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.pit_authority import (
    PITArtifactKind,
    PITArtifactReference,
    PITAsOfQuery,
    PITContractError,
    PITFactEvidenceMode,
    PITFactTemporalAuthority,
    PITProviderEvidence,
    PITProviderEvidenceKind,
    PITRequiredFact,
    PITSourceAuthorityStatus,
    PITValidationOutcome,
    ProviderQualificationPolicy,
    RecordedPITFactRevision,
)
from market_regime_alpha.data.postgres_pit_authority import (
    PITAuthorityConflictError,
    PITAuthorityIntegrityError,
    PostgresPITAuthority,
)
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.postgres.native_repository import (
    acquire_scope_lock,
)
from tests.persistence.postgres.pit_fixture import (
    DECISION_TIME,
    HASH_A,
    INGEST_TIME,
    MutableClock,
    NOW,
    authorize_source,
    FixturePITArtifactAuthorityResolver,
    pit_authority,
    pit_fact,
    pit_request,
    required_facts,
    source_qualification,
)


def _record_complete_scope(
    repository: PostgresPITAuthority,
) -> dict[PITRequiredFact, RecordedPITFactRevision]:
    authorize_source(repository)
    recorded: dict[PITRequiredFact, RecordedPITFactRevision] = {}
    for index, required in enumerate(required_facts()):
        recorded[required] = repository.record_fact(
            pit_fact(required),
            actor="source-ingestor",
            reason="record formal source fact",
            idempotency_key=f"fact-{index}",
        )
    return recorded


def test_postgres_as_of_uses_current_snapshot_and_rejects_revision_prefix_replay(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    repository = pit_authority(postgres_factory, clock=lambda: INGEST_TIME)
    authorize_source(repository)
    first_required = required_facts()[1]
    first = repository.record_fact(
        pit_fact(first_required),
        actor="source-ingestor",
        reason="record original",
        idempotency_key="fact-original",
    )
    assert repository.record_fact(
        first.fact,
        actor="source-ingestor",
        reason="record original",
        idempotency_key="fact-original",
    ) == first
    first_authority_revision = repository.current_revision()

    corrected = repository.record_fact(
        pit_fact(
            first_required,
            revision=2,
            supersedes_fact_id=first.fact.fact_id,
            value_json='{"value":"corrected"}',
        ),
        actor="source-ingestor",
        reason="record correction",
        idempotency_key="fact-corrected",
    )
    current = repository.as_of(
        PITAsOfQuery.create(
            scope_id="daily:2026-08-08",
            decision_time=DECISION_TIME,
            required_facts=(first_required,),
        )
    )
    with pytest.raises(PITAuthorityIntegrityError, match="audit metadata"):
        repository.as_of(
            PITAsOfQuery.create(
                scope_id="daily:2026-08-08",
                decision_time=DECISION_TIME,
                required_facts=(first_required,),
                authority_revision=first_authority_revision,
            )
        )

    assert current.outcome is PITValidationOutcome.SATISFIED
    assert current.selected_fact_references == ((corrected.fact.fact_id, corrected.fact.content_hash),)


def test_repository_rejects_caller_built_query_collision_before_sql_selection(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    repository = pit_authority(postgres_factory, clock=lambda: INGEST_TIME)
    valid = PITAsOfQuery.create(
        scope_id="daily:2026-08-08",
        decision_time=DECISION_TIME,
        required_facts=(required_facts()[0],),
    )
    malformed = object.__new__(PITAsOfQuery)
    for field_name in (
        "query_hash",
        "scope_id",
        "decision_time",
        "authority_revision",
    ):
        object.__setattr__(malformed, field_name, getattr(valid, field_name))
    object.__setattr__(
        malformed,
        "required_facts",
        (required_facts()[0], required_facts()[0]),
    )

    with pytest.raises(PITContractError, match="logical_key collision"):
        repository.as_of(malformed)


def test_postgres_fact_revision_cas_and_concurrency(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    repository = pit_authority(postgres_factory, clock=lambda: INGEST_TIME)
    authorize_source(repository)
    required = required_facts()[1]
    first = repository.record_fact(
        pit_fact(required),
        actor="source-ingestor",
        reason="record original",
        idempotency_key="concurrent-original",
    )

    def correct(value: str) -> object:
        return pit_authority(
            postgres_factory, clock=lambda: INGEST_TIME
        ).record_fact(
            pit_fact(
                required,
                revision=2,
                supersedes_fact_id=first.fact.fact_id,
                value_json=f'{{"value":"{value}"}}',
            ),
            actor="source-ingestor",
            reason="concurrent correction",
            idempotency_key=f"concurrent-{value}",
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(correct, value) for value in ("a", "b")]
    results = []
    failures = []
    for future in futures:
        try:
            results.append(future.result())
        except PITAuthorityConflictError as exc:
            failures.append(exc)
    assert len(results) == 1
    assert len(failures) == 1


def test_different_symbols_progress_while_one_fact_aggregate_is_locked(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    repository = pit_authority(postgres_factory, clock=lambda: INGEST_TIME)
    authorize_source(repository)
    blocked_required = required_facts()[1]
    unrelated_required = PITRequiredFact(
        "market:000001.SZ:2026-08-08T06:44:00Z",
        blocked_required.fact_kind,
        "000001.SZ",
    )

    with postgres_factory.connection() as holder:
        acquire_scope_lock(
            holder,
            namespace="pit-fact",
            identity=f"daily:2026-08-08:{blocked_required.logical_key}",
        )
        with ThreadPoolExecutor(max_workers=2) as executor:
            blocked = executor.submit(
                pit_authority(
                    postgres_factory, clock=lambda: INGEST_TIME
                ).record_fact,
                pit_fact(blocked_required),
                actor="source-ingestor",
                reason="blocked aggregate probe",
                idempotency_key="blocked-symbol-fact",
            )
            with pytest.raises(FutureTimeoutError):
                blocked.result(timeout=0.2)
            unrelated = executor.submit(
                pit_authority(
                    postgres_factory, clock=lambda: INGEST_TIME
                ).record_fact,
                pit_fact(unrelated_required),
                actor="source-ingestor",
                reason="unrelated aggregate progress probe",
                idempotency_key="unrelated-symbol-fact",
            )
            assert unrelated.result(timeout=3).fact.subject == "000001.SZ"
            holder.commit()
            assert blocked.result(timeout=3).fact.subject == "600000.SH"


def test_different_scopes_progress_with_same_logical_key(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    repository = pit_authority(postgres_factory, clock=lambda: INGEST_TIME)
    authorize_source(repository)
    required = required_facts()[1]

    with postgres_factory.connection() as holder:
        acquire_scope_lock(
            holder,
            namespace="pit-fact",
            identity=f"daily:2026-08-08:{required.logical_key}",
        )
        with ThreadPoolExecutor(max_workers=2) as executor:
            blocked = executor.submit(
                pit_authority(
                    postgres_factory, clock=lambda: INGEST_TIME
                ).record_fact,
                pit_fact(required),
                actor="source-ingestor",
                reason="blocked scope probe",
                idempotency_key="blocked-scope-fact",
            )
            with pytest.raises(FutureTimeoutError):
                blocked.result(timeout=0.2)
            unrelated = executor.submit(
                pit_authority(
                    postgres_factory, clock=lambda: INGEST_TIME
                ).record_fact,
                pit_fact(required, scope_id="daily:2026-08-09"),
                actor="source-ingestor",
                reason="unrelated scope progress probe",
                idempotency_key="unrelated-scope-fact",
            )
            assert unrelated.result(timeout=3).fact.scope_id == "daily:2026-08-09"
            holder.commit()
            assert blocked.result(timeout=3).fact.scope_id == "daily:2026-08-08"


def test_validation_uses_repeatable_snapshot_while_ingestion_is_waiting(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    clock = MutableClock(INGEST_TIME)
    repository = pit_authority(postgres_factory, clock=clock)
    recorded = _record_complete_scope(repository)
    market_required = required_facts()[1]
    original = recorded[market_required]

    with postgres_factory.connection() as holder:
        acquire_scope_lock(
            holder,
            namespace="pit-fact",
            identity=f"daily:2026-08-08:{market_required.logical_key}",
        )
        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(
                pit_authority(
                    postgres_factory, clock=lambda: INGEST_TIME
                ).record_fact,
                pit_fact(
                    market_required,
                    revision=2,
                    supersedes_fact_id=original.fact.fact_id,
                    value_json='{"value":"concurrent-correction"}',
                ),
                actor="source-ingestor",
                reason="concurrent correction",
                idempotency_key="validation-concurrent-correction",
            )
            with pytest.raises(FutureTimeoutError):
                pending.result(timeout=0.2)
            clock.value = NOW
            evidence = repository.validate(
                pit_request(idempotency_key="validation-during-ingestion")
            )
            assert evidence.outcome is PITValidationOutcome.SATISFIED
            assert (original.fact.fact_id, original.fact.content_hash) in (
                evidence.selected_fact_references
            )
            holder.commit()
            pending.result(timeout=3)

    assert repository.replay_evidence(evidence.evidence_id) == evidence


def test_source_qualification_waits_for_inflight_source_admission(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    repository = pit_authority(postgres_factory, clock=lambda: INGEST_TIME)
    qualified = authorize_source(repository)
    identity = (
        f"{qualified.source_manifest.artifact_id}:{qualified.provider_id}:"
        f"{qualified.provider_contract}"
    )
    key = f"market-regime-alpha:pit-source-qualification:{identity}"

    with postgres_factory.connection() as holder:
        holder.execute(
            "SELECT pg_advisory_xact_lock_shared(hashtextextended(%s, 0))",
            (key,),
        )
        with ThreadPoolExecutor(max_workers=1) as executor:
            suspension = executor.submit(
                pit_authority(
                    postgres_factory, clock=lambda: INGEST_TIME
                ).record_source_qualification,
                source_qualification(
                    status=PITSourceAuthorityStatus.SUSPENDED,
                    revision=2,
                    supersedes_qualification_id=qualified.qualification_id,
                ),
                idempotency_key="qualification-fact-race-suspension",
            )
            with pytest.raises(FutureTimeoutError):
                suspension.result(timeout=0.2)
            holder.commit()
            assert (
                suspension.result(timeout=3).status
                is PITSourceAuthorityStatus.SUSPENDED
            )


def test_validation_replay_is_pinned_after_later_revision(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    clock = MutableClock(INGEST_TIME)
    repository = pit_authority(postgres_factory, clock=clock)
    recorded = _record_complete_scope(repository)
    clock.value = NOW
    evidence = repository.validate(pit_request())

    assert evidence.outcome is PITValidationOutcome.SATISFIED
    market_required = required_facts()[1]
    original = recorded[market_required]
    repository.record_fact(
        pit_fact(
            market_required,
            revision=2,
            supersedes_fact_id=original.fact.fact_id,
            value_json='{"value":"later-correction"}',
        ),
        actor="source-ingestor",
        reason="later correction",
        idempotency_key="later-correction",
    )
    repository.record_source_qualification(
        source_qualification(
            status=PITSourceAuthorityStatus.SUSPENDED,
            revision=2,
            supersedes_qualification_id=repository.get_fact(
                original.fact.fact_id
            ).source_qualification_id,
        ),
        idempotency_key="later-source-suspension",
    )

    assert repository.replay_evidence(evidence.evidence_id) == evidence


def test_forged_artifact_reference_is_rejected_before_fact_admission(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    repository = pit_authority(postgres_factory, clock=lambda: INGEST_TIME)
    authorize_source(repository)

    with pytest.raises(PITAuthorityConflictError, match="Artifact authority"):
        repository.record_fact(
            pit_fact(
                required_facts()[1],
                artifact=PITArtifactReference(
                    PITArtifactKind.MARKET_DATA_DATASET.value,
                    ArtifactId("forged-dataset"),
                    HASH_A,
                ),
            ),
            actor="source-ingestor",
            reason="attempt forged Artifact admission",
            idempotency_key="forged-dataset-fact",
        )

    with postgres_factory.connection() as connection:
        assert connection.execute(
            "SELECT count(*) FROM pit_fact_revision"
        ).fetchone()[0] == 0


def test_provider_policy_prevents_operator_authority_inflation(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    policy = ProviderQualificationPolicy.default()
    repository = PostgresPITAuthority(
        postgres_factory,
        clock=lambda: INGEST_TIME,
        artifact_resolver=FixturePITArtifactAuthorityResolver(),
        provider_policy=policy,
    )

    with pytest.raises(PITAuthorityConflictError, match="not established"):
        repository.record_source_qualification(
            source_qualification(
                provider_id="tencent",
                provider_contract="caller-declared-formal",
                policy=policy,
            ),
            idempotency_key="operator-inflation-tencent",
        )


def test_formal_provider_qualification_requires_complete_typed_evidence(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    repository = pit_authority(postgres_factory, clock=lambda: INGEST_TIME)

    with pytest.raises(PITAuthorityConflictError, match="not established"):
        repository.record_source_qualification(
            source_qualification(
                evidence_kinds=(PITProviderEvidenceKind.PROVIDER_CONTRACT,),
            ),
            idempotency_key="incomplete-provider-evidence",
        )


def _historical_temporal_authority() -> PITFactTemporalAuthority:
    evidence = tuple(
        PITProviderEvidence(
            kind,
            PITArtifactReference(
                PITArtifactKind.PROVIDER_EVIDENCE.value,
                ArtifactId(f"historical-{kind.value.lower()}"),
                HASH_A,
            ),
        )
        for kind in (
            PITProviderEvidenceKind.ARCHIVE_INTEGRITY,
            PITProviderEvidenceKind.HISTORICAL_AVAILABILITY,
            PITProviderEvidenceKind.REVISION_POLICY,
        )
    )
    return PITFactTemporalAuthority(
        mode=PITFactEvidenceMode.HISTORICAL_PROVIDER_PIT,
        provider_available_at=DECISION_TIME - timedelta(minutes=5),
        provider_recorded_at=DECISION_TIME - timedelta(minutes=4),
        provider_revision="provider-revision-2026-08-08-r1",
        provider_dataset_version="provider-dataset-2026-08-08",
        provider_archive=PITArtifactReference(
            PITArtifactKind.PROVIDER_ARCHIVE.value,
            ArtifactId("historical-provider-archive-a"),
            HASH_A,
        ),
        provider_evidence=evidence,
    )


def test_historical_provider_fact_may_be_imported_after_decision_time(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    clock = MutableClock(INGEST_TIME)
    repository = pit_authority(postgres_factory, clock=clock)
    authorize_source(repository)
    market_required = required_facts()[1]
    for index, required in enumerate(required_facts()):
        if required == market_required:
            clock.value = NOW
            temporal = _historical_temporal_authority()
            fact = pit_fact(
                required,
                available_at=temporal.provider_available_at,
                recorded_at=temporal.provider_recorded_at,
                temporal_authority=temporal,
            )
        else:
            clock.value = INGEST_TIME
            fact = pit_fact(required)
        repository.record_fact(
            fact,
            actor="source-ingestor",
            reason="record mixed prospective and historical Provider PIT",
            idempotency_key=f"historical-import-{index}",
        )
    clock.value = NOW

    evidence = repository.validate(
        pit_request(idempotency_key="validate-historical-import")
    )

    assert evidence.outcome is PITValidationOutcome.SATISFIED
    selected_market = next(
        repository.get_fact(fact_id)
        for fact_id, _ in evidence.selected_fact_references
        if repository.get_fact(fact_id).fact.fact_kind.value == "MARKET_DATA"
    )
    assert selected_market.ingested_at > DECISION_TIME

    corrected_temporal = replace(
        selected_market.fact.temporal_authority,
        provider_revision="provider-revision-2026-08-08-r2",
    )
    repository.record_fact(
        pit_fact(
            market_required,
            revision=2,
            supersedes_fact_id=selected_market.fact.fact_id,
            available_at=corrected_temporal.provider_available_at,
            recorded_at=corrected_temporal.provider_recorded_at,
            temporal_authority=corrected_temporal,
            value_json='{"value":"provider-correction-r2"}',
        ),
        actor="source-ingestor",
        reason="import later Provider revision correction",
        idempotency_key="historical-provider-correction-r2",
    )

    assert repository.replay_evidence(evidence.evidence_id) == evidence


def test_pit_tables_are_append_only(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    repository = pit_authority(postgres_factory, clock=lambda: INGEST_TIME)
    authorize_source(repository)
    recorded = repository.record_fact(
        pit_fact(required_facts()[0]),
        actor="source-ingestor",
        reason="record calendar",
        idempotency_key="append-only-calendar",
    )
    with postgres_factory.connection() as connection:
        with pytest.raises(Exception, match="append-only"):
            connection.execute(
                "UPDATE pit_fact_revision SET value_json = value_json WHERE fact_id = %s",
                (str(recorded.fact.fact_id),),
            )
        connection.rollback()
        with pytest.raises(Exception, match="append-only"):
            connection.execute(
                "DELETE FROM pit_fact_revision WHERE fact_id = %s",
                (str(recorded.fact.fact_id),),
            )


def test_conflicting_idempotency_key_fails_closed(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    repository = pit_authority(postgres_factory, clock=lambda: INGEST_TIME)
    authorize_source(repository)
    original = pit_fact(required_facts()[0])
    repository.record_fact(
        original,
        actor="source-ingestor",
        reason="record calendar",
        idempotency_key="same-command",
    )
    with pytest.raises(PITAuthorityConflictError, match="idempotency"):
        repository.record_fact(
            pit_fact(required_facts()[0], value_json='{"value":false}'),
            actor="source-ingestor",
            reason="conflicting retry",
            idempotency_key="same-command",
        )


def test_formal_fact_requires_explicit_active_source_authority(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    repository = pit_authority(
        postgres_factory,
        clock=lambda: INGEST_TIME,
    )
    with pytest.raises(PITAuthorityConflictError, match="source qualification"):
        repository.record_fact(
            pit_fact(required_facts()[0]),
            actor="source-ingestor",
            reason="attempt unqualified formal source",
            idempotency_key="unqualified-source-fact",
        )

    qualified = repository.record_source_qualification(
        source_qualification(),
        idempotency_key="qualify-source",
    )
    with pytest.raises(PITAuthorityConflictError, match="different hash"):
        repository.record_source_qualification(
            source_qualification(
                source_manifest=PITArtifactReference(
                    qualified.source_manifest.reference_kind,
                    qualified.source_manifest.artifact_id,
                    "sha256:" + "f" * 64,
                )
            ),
            idempotency_key="conflicting-source-manifest-identity",
        )
    with postgres_factory.connection() as connection:
        with pytest.raises(Exception, match="append-only"):
            connection.execute(
                "UPDATE pit_source_qualification SET status = 'SUSPENDED' "
                "WHERE qualification_id = %s",
                (str(qualified.qualification_id),),
            )
        connection.rollback()
    repository.record_fact(
        pit_fact(required_facts()[0]),
        actor="source-ingestor",
        reason="record under qualified source",
        idempotency_key="qualified-source-fact",
    )
    repository.record_source_qualification(
        source_qualification(
            status=PITSourceAuthorityStatus.SUSPENDED,
            revision=2,
            supersedes_qualification_id=qualified.qualification_id,
        ),
        idempotency_key="suspend-source",
    )
    with pytest.raises(PITAuthorityConflictError, match="not qualified"):
        repository.record_fact(
            pit_fact(required_facts()[1]),
            actor="source-ingestor",
            reason="attempt fact after source suspension",
            idempotency_key="suspended-source-fact",
        )


def test_as_of_rejects_unknown_future_authority_revision(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    repository = pit_authority(
        postgres_factory,
        clock=lambda: INGEST_TIME,
    )
    authorize_source(repository)
    repository.record_fact(
        pit_fact(required_facts()[0]),
        actor="source-ingestor",
        reason="record calendar",
        idempotency_key="future-revision-calendar",
    )
    with pytest.raises(PITAuthorityIntegrityError, match="audit metadata"):
        repository.as_of(
            PITAsOfQuery.create(
                scope_id="daily:2026-08-08",
                decision_time=DECISION_TIME,
                required_facts=(required_facts()[0],),
                authority_revision=repository.current_revision() + 1,
            )
        )
