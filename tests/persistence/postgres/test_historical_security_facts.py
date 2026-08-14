from __future__ import annotations

from datetime import date, timedelta

import psycopg
import pytest
from psycopg.types.json import Jsonb

from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.universe.postgres_historical_facts import (
    HistoricalSecurityFactsConflict,
    PostgresHistoricalSecurityFactsRepository,
)
from market_regime_alpha.universe.historical_facts import (
    HistoricalSecurityFact,
    HistoricalSecurityFactKind,
)
from tests.universe.test_historical_security_facts import _owner


def test_historical_security_facts_publish_reload_and_bulk_project(
    postgres_factory,
) -> None:
    repository = PostgresHistoricalSecurityFactsRepository(postgres_factory)
    owner = _owner()

    assert repository.publish(owner) == owner
    assert repository.publish(owner) == owner
    projection = repository.resolve_as_of(
        owner.reference,
        symbols=("600000.SH", "600001.SH"),
        decision_date=date(2025, 1, 2),
    )

    assert projection.industries["600000.SH"].effective_date == date(2024, 12, 30)
    assert projection.share_capital["600000.SH"].effective_date == date(2024, 9, 30)
    assert "600001.SH" not in projection.industries
    assert "600001.SH" not in projection.share_capital


def test_historical_security_facts_enforce_publication_and_action_interval(
    postgres_factory,
) -> None:
    repository = PostgresHistoricalSecurityFactsRepository(postgres_factory)
    owner = repository.publish(_owner())

    early = repository.resolve_as_of(
        owner.reference,
        symbols=("600000.SH",),
        decision_date=date(2025, 1, 2),
    )
    late = repository.resolve_as_of(
        owner.reference,
        symbols=("600000.SH",),
        decision_date=date(2025, 5, 2),
    )
    actions = repository.corporate_actions_for_symbols(
        owner.reference,
        symbols=("600000.SH",),
        after=date(2025, 6, 17),
        through=date(2025, 6, 18),
    )

    assert early.share_capital["600000.SH"].effective_date == date(2024, 9, 30)
    assert late.share_capital["600000.SH"].effective_date == date(2024, 12, 31)
    assert len(actions["600000.SH"]) == 2
    assert (
        repository.corporate_actions_for_symbols(
            owner.reference,
            symbols=("600000.SH",),
            after=date(2025, 6, 18),
            through=date(2025, 6, 19),
        )
        == {}
    )


def test_historical_security_facts_fail_on_reference_hash_drift(
    postgres_factory,
) -> None:
    repository = PostgresHistoricalSecurityFactsRepository(postgres_factory)
    owner = repository.publish(_owner())
    wrong = ValidationArtifactReference(
        owner.reference.artifact_kind,
        owner.reference.artifact_id,
        "sha256:" + "0" * 64,
    )

    try:
        repository.resolve_as_of(
            wrong,
            symbols=("600000.SH",),
            decision_date=date(2025, 1, 2),
        )
    except Exception as exc:
        assert "hash diverged" in str(exc)
    else:
        raise AssertionError("Historical Security Facts hash drift did not fail")


def test_historical_security_fact_gaps_are_owner_resolved_and_interval_bounded(
    postgres_factory,
) -> None:
    repository = PostgresHistoricalSecurityFactsRepository(postgres_factory)
    owner = repository.publish(_owner(include_gap=True))

    gaps = repository.corporate_action_gaps_for_symbols(
        owner.reference,
        symbols=("600000.SH",),
        after=date(2025, 6, 17),
        through=date(2025, 6, 18),
    )

    assert len(gaps["600000.SH"]) == 1
    assert repository.get(owner.owner_id) == owner


def test_historical_security_fact_scope_fails_absence_closed(
    postgres_factory,
) -> None:
    repository = PostgresHistoricalSecurityFactsRepository(postgres_factory)
    owner = repository.publish(_owner())

    gaps = repository.corporate_action_gaps_for_symbols(
        owner.reference,
        symbols=("600001.SH",),
        after=date(2025, 6, 17),
        through=date(2025, 6, 18),
    )
    assert gaps["600001.SH"][0].reason_codes == (
        "CORPORATE_ACTION_SYMBOL_OUTSIDE_ACQUISITION_SCOPE",
        "RAW_UNADJUSTED_RETURN_FAILS_CLOSED",
    )
    actions, resolved_gaps = repository.corporate_action_evidence_for_symbols(
        owner.reference,
        symbols=("600001.SH",),
        after=date(2025, 6, 17),
        through=date(2025, 6, 18),
    )
    assert actions == {}
    assert resolved_gaps == gaps
    with pytest.raises(
        HistoricalSecurityFactsConflict,
        match="active Universe symbols",
    ):
        repository.verify_acquisition_scope(
            owner.reference,
            symbols=("600000.SH", "600001.SH"),
            universe_references=owner.universe_scope_references,
            decision_date=date(2025, 6, 17),
        )


def test_historical_security_fact_projection_rejects_non_member_child(
    postgres_factory,
) -> None:
    repository = PostgresHistoricalSecurityFactsRepository(postgres_factory)
    owner = repository.publish(_owner())
    extra = HistoricalSecurityFact.create(
        fact_kind=HistoricalSecurityFactKind.INDUSTRY,
        symbol="600000.SH",
        effective_date=date(2025, 1, 1),
        published_date=None,
        values={"industry": "INJECTED", "classification": "INJECTED"},
        source_reference=owner.facts[0].source_reference,
    )

    with postgres_factory.connection() as connection, pytest.raises(
        psycopg.errors.RaiseException,
        match="not an exact member of its owner",
    ):
        connection.execute(
            """
            INSERT INTO free_data_historical_security_fact(
                owner_id, owner_hash, fact_id, fact_hash, symbol,
                fact_kind, effective_date, published_date,
                source_artifact_kind, source_artifact_id,
                source_content_hash, payload_json
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                str(owner.owner_id),
                owner.owner_hash,
                str(extra.fact_id),
                extra.fact_hash,
                extra.symbol,
                extra.fact_kind.value,
                extra.effective_date,
                extra.published_date,
                extra.source_reference.artifact_kind,
                str(extra.source_reference.artifact_id),
                extra.source_reference.content_hash,
                Jsonb(extra.to_canonical_dict()),
            ),
        )


def test_historical_security_fact_projection_binds_publication_date(
    postgres_factory,
) -> None:
    owner = PostgresHistoricalSecurityFactsRepository(postgres_factory).publish(
        _owner()
    )
    fact = next(item for item in owner.facts if item.published_date is not None)

    with pytest.raises(psycopg.errors.CheckViolation):
        with postgres_factory.connection() as connection:
            connection.execute(
                "ALTER TABLE free_data_historical_security_fact "
                "DISABLE TRIGGER free_data_historical_security_fact_no_update"
            )
            connection.execute(
                "DELETE FROM free_data_historical_security_fact "
                "WHERE owner_id = %s AND fact_id = %s",
                (str(owner.owner_id), str(fact.fact_id)),
            )
            connection.execute(
                """
                INSERT INTO free_data_historical_security_fact(
                    owner_id, owner_hash, fact_id, fact_hash, symbol,
                    fact_kind, effective_date, published_date,
                    source_artifact_kind, source_artifact_id,
                    source_content_hash, payload_json
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    str(owner.owner_id),
                    owner.owner_hash,
                    str(fact.fact_id),
                    fact.fact_hash,
                    fact.symbol,
                    fact.fact_kind.value,
                    fact.effective_date,
                    fact.published_date - timedelta(days=1),
                    fact.source_reference.artifact_kind,
                    str(fact.source_reference.artifact_id),
                    fact.source_reference.content_hash,
                    Jsonb(fact.to_canonical_dict()),
                ),
            )


def test_historical_security_fact_projection_detects_missing_child(
    postgres_factory,
) -> None:
    owner = PostgresHistoricalSecurityFactsRepository(postgres_factory).publish(_owner())
    with postgres_factory.connection() as connection:
        connection.execute(
            "ALTER TABLE free_data_historical_security_fact "
            "DISABLE TRIGGER free_data_historical_security_fact_no_update"
        )
        connection.execute(
            "DELETE FROM free_data_historical_security_fact "
            "WHERE owner_id = %s AND fact_id = %s",
            (str(owner.owner_id), str(owner.facts[0].fact_id)),
        )
        connection.execute(
            "ALTER TABLE free_data_historical_security_fact "
            "ENABLE TRIGGER free_data_historical_security_fact_no_update"
        )

    repository = PostgresHistoricalSecurityFactsRepository(
        postgres_factory,
        apply_migrations=False,
    )
    with pytest.raises(
        HistoricalSecurityFactsConflict,
        match="bounded projection digest diverged",
    ):
        repository.resolve_as_of(
            owner.reference,
            symbols=("600000.SH",),
            decision_date=date(2025, 1, 2),
        )
