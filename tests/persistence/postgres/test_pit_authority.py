from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import pytest

from market_regime_alpha.data.pit_authority import (
    PITArtifactReference,
    PITAsOfQuery,
    PITRequiredFact,
    PITSourceAuthorityStatus,
    PITValidationOutcome,
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
from tests.persistence.postgres.pit_fixture import (
    DECISION_TIME,
    INGEST_TIME,
    MutableClock,
    NOW,
    authorize_source,
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


def test_postgres_as_of_is_idempotent_and_revision_aware(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    repository = PostgresPITAuthority(postgres_factory, clock=lambda: INGEST_TIME)
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
    historical = repository.as_of(
        PITAsOfQuery.create(
            scope_id="daily:2026-08-08",
            decision_time=DECISION_TIME,
            required_facts=(first_required,),
            authority_revision=first_authority_revision,
        )
    )

    assert current.outcome is PITValidationOutcome.SATISFIED
    assert current.selected_fact_references == ((corrected.fact.fact_id, corrected.fact.content_hash),)
    assert historical.selected_fact_references == ((first.fact.fact_id, first.fact.content_hash),)


def test_postgres_fact_revision_cas_and_concurrency(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    repository = PostgresPITAuthority(postgres_factory, clock=lambda: INGEST_TIME)
    authorize_source(repository)
    required = required_facts()[1]
    first = repository.record_fact(
        pit_fact(required),
        actor="source-ingestor",
        reason="record original",
        idempotency_key="concurrent-original",
    )

    def correct(value: str) -> object:
        return PostgresPITAuthority(
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


def test_validation_replay_is_pinned_after_later_revision(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    clock = MutableClock(INGEST_TIME)
    repository = PostgresPITAuthority(postgres_factory, clock=clock)
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

    assert repository.replay_evidence(evidence.evidence_id) == evidence


def test_pit_tables_are_append_only(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    repository = PostgresPITAuthority(postgres_factory, clock=lambda: INGEST_TIME)
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
    repository = PostgresPITAuthority(postgres_factory, clock=lambda: INGEST_TIME)
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
    repository = PostgresPITAuthority(
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
    repository = PostgresPITAuthority(
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
    with pytest.raises(PITAuthorityIntegrityError, match="newer than current authority"):
        repository.as_of(
            PITAsOfQuery.create(
                scope_id="daily:2026-08-08",
                decision_time=DECISION_TIME,
                required_facts=(required_facts()[0],),
                authority_revision=repository.current_revision() + 1,
            )
        )
