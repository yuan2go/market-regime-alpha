from __future__ import annotations

from datetime import date

import pytest
from psycopg.errors import UniqueViolation

from market_regime_alpha.application.historical_corpus.materialization_contracts import (
    HistoricalComponentKind,
    HistoricalSessionComponent,
)
from market_regime_alpha.application.historical_corpus.postgres_materialization import (
    HistoricalMaterializationConflict,
    PostgresHistoricalMaterializationRepository,
)
from market_regime_alpha.application.historical_research.postgres_journal import (
    PostgresHistoricalResearchJournal,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.universe.postgres_runtime_scope import PostgresRuntimeScopeRepository
from tests.application.historical_research.test_contracts import CREATED_AT, _command
from tests.persistence.postgres.test_historical_research_journal import MutableClock
from tests.universe.test_runtime_scope import _policy


def test_session_component_is_idempotent_owner_resolved_and_append_only(
    postgres_factory,
) -> None:
    command = _command(sessions=(date(2020, 1, 2),))
    request = command.session_request(date(2020, 1, 2))
    PostgresRuntimeScopeRepository(postgres_factory).register_policy(_policy())
    PostgresHistoricalResearchJournal(
        postgres_factory,
        clock=MutableClock(CREATED_AT),
    ).create_or_get(command)
    repository = PostgresHistoricalMaterializationRepository(postgres_factory)
    source = ValidationArtifactReference(
        "NORMALIZED_DATASET",
        ArtifactId("normalized-owner-test"),
        canonical_hash({"normalized": "test"}),
    )
    component = HistoricalSessionComponent.create(
        run_id=command.run_id,
        session_id=request.session_id,
        trading_date=request.trading_date,
        component_kind=HistoricalComponentKind.FEATURE,
        source_max_event_time=request.decision_time,
        materialized_at=request.materialized_at,
        source_references=(source,),
        payload={"available": 3, "missing": 1},
    )

    first = repository.put(component=component, ordinal=1)
    repeated = repository.put(component=component, ordinal=1)

    assert first == component
    assert repeated == component
    assert repository.get(component.reference) == component

    conflicting = HistoricalSessionComponent.create(
        run_id=command.run_id,
        session_id=request.session_id,
        trading_date=request.trading_date,
        component_kind=HistoricalComponentKind.FEATURE,
        source_max_event_time=request.decision_time,
        materialized_at=request.materialized_at,
        source_references=(source,),
        payload={"available": 4, "missing": 0},
    )
    with pytest.raises(UniqueViolation):
        repository.put(component=conflicting, ordinal=1)

    wrong_reference = ValidationArtifactReference(
        "HISTORICAL_SIGNAL", component.component_id, component.component_hash
    )
    with pytest.raises(
        HistoricalMaterializationConflict,
        match="reference kind mismatch",
    ):
        repository.get(wrong_reference)
