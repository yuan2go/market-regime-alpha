from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

import pytest
from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb

from market_regime_alpha.application.historical_corpus.materialization_contracts import (
    HistoricalComponentKind,
    HistoricalSessionComponent,
)
from market_regime_alpha.application.historical_corpus.postgres_materialization import (
    HistoricalMaterializationConflict,
    PostgresHistoricalMaterializationRepository,
)
from market_regime_alpha.application.continuous_research.journal import (
    RuntimeArtifactReference,
)
from market_regime_alpha.application.controlled_operation.prospective_outcome import (
    OutcomeAvailabilityStatus,
    OutcomeMarketCondition,
)
from market_regime_alpha.application.research_evaluation.targeted_outcome import (
    BarrierOrderingOutcome,
    TargetOutcomeLabel,
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


def test_prior_outcome_projection_keeps_newest_bounded_window(
    postgres_factory,
) -> None:
    sessions = (date(2020, 1, 2), date(2020, 1, 3), date(2020, 1, 4))
    command = _command(sessions=sessions)
    PostgresRuntimeScopeRepository(postgres_factory).register_policy(_policy())
    PostgresHistoricalResearchJournal(
        postgres_factory,
        clock=MutableClock(CREATED_AT),
    ).create_or_get(command)
    repository = PostgresHistoricalMaterializationRepository(postgres_factory)
    source = ValidationArtifactReference(
        "NORMALIZED_DATASET",
        ArtifactId("bounded-outcome-source"),
        canonical_hash({"bounded": "outcome-source"}),
    )
    target = RuntimeArtifactReference(
        "OUTCOME_TARGET_DEFINITION",
        ArtifactId("bounded-outcome-target"),
        canonical_hash({"bounded": "outcome-target"}),
    )
    labels: list[TargetOutcomeLabel] = []
    for trading_date in sessions:
        request = command.session_request(trading_date)
        start = datetime.combine(trading_date, time(10, 30), tzinfo=UTC)
        end = start + timedelta(days=1)
        label = TargetOutcomeLabel.create(
            symbol="600000.SH",
            target=target,
            label_interval_start=start,
            label_interval_end=end,
            decision_reference_price=Decimal("10"),
            checkpoint_price=Decimal("10.1"),
            mfe=Decimal("0.02"),
            mae=Decimal("-0.01"),
            barrier_passages=(),
            barrier_ordering=BarrierOrderingOutcome.NOT_APPLICABLE,
            market_conditions=(OutcomeMarketCondition.TRADING,),
            availability_status=OutcomeAvailabilityStatus.COMPLETE,
            outcome_available_at=end,
            reason_codes=("TARGET_COMPLETE",),
        )
        labels.append(label)
        component = HistoricalSessionComponent.create(
            run_id=command.run_id,
            session_id=request.session_id,
            trading_date=trading_date,
            component_kind=HistoricalComponentKind.OUTCOME,
            source_max_event_time=end,
            materialized_at=request.materialized_at,
            source_references=(source,),
            payload={"labels": [label.to_canonical_dict()]},
        )
        repository.put(component=component, ordinal=1)

    projected = repository.list_outcome_labels_before(
        run_id=command.run_id,
        before=date(2020, 1, 5),
        symbol="600000.SH",
        target_id=target.artifact_id,
        maximum_labels=2,
    )

    assert tuple(item[1] for item in projected) == tuple(labels[-2:])

    with postgres_factory.connection() as connection:
        owner = connection.execute(
            """
            SELECT component_id, component_hash
            FROM historical_corpus_session_component
            WHERE run_id = %s AND trading_date = %s
              AND component_kind = 'OUTCOME'
            """,
            (str(command.run_id), sessions[-1]),
        ).fetchone()
        assert owner is not None
        forged = labels[0]
        connection.execute(
            """
            INSERT INTO historical_corpus_outcome_label(
                component_id, component_hash, trading_date,
                label_id, label_hash, symbol, target_id,
                label_interval_end, outcome_available_at,
                availability_status, payload_json
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                str(owner[0]),
                str(owner[1]),
                sessions[-1],
                str(forged.label_id),
                forged.label_hash,
                forged.symbol,
                str(forged.target.artifact_id),
                forged.label_interval_end,
                forged.outcome_available_at,
                forged.availability_status.value,
                Jsonb(forged.to_canonical_dict()),
            ),
        )
    with pytest.raises(
        HistoricalMaterializationConflict,
        match="diverged from owner",
    ):
        repository.list_outcome_labels_before(
            run_id=command.run_id,
            before=date(2020, 1, 5),
            symbol="600000.SH",
            target_id=target.artifact_id,
            maximum_labels=10,
        )
