"""PostgreSQL authority for pre-Strategy Risk and Strategy Opportunity facts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Protocol

from psycopg.types.json import Jsonb

from market_regime_alpha.application.continuous_research.journal import (
    RuntimeArtifactReference,
)
from market_regime_alpha.application.historical_corpus.materialization_contracts import (
    HistoricalSessionComponent,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.postgres.migrator import PostgresMigrator
from market_regime_alpha.research.candidate_discovery.contracts import CandidateSet
from market_regime_alpha.strategies.contracts import (
    StrategyOpportunityInput,
    StrategyRegistry,
    StrategyVersion,
)
from market_regime_alpha.strategies.opportunity import PreStrategyRiskState


@dataclass(frozen=True, slots=True)
class ResolvedStrategySource:
    reference: RuntimeArtifactReference
    available_at: datetime
    symbols: tuple[str, ...]
    source_references: tuple[RuntimeArtifactReference, ...]
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.available_at.tzinfo is None or self.available_at.utcoffset() is None:
            raise ValueError("Strategy source availability must be timezone-aware")
        if self.symbols != tuple(sorted(set(self.symbols))):
            raise ValueError("Strategy source symbols must be unique and sorted")
        if self.source_references != _references(self.source_references):
            raise ValueError("Strategy source lineage must be unique and sorted")


class StrategySourceAuthority(Protocol):
    def reload(
        self,
        reference: RuntimeArtifactReference,
    ) -> ResolvedStrategySource: ...


class StrategyOpportunityResolverAuthority(Protocol):
    def resolve(
        self,
        *,
        candidate_reference: RuntimeArtifactReference,
        decision_time: datetime,
        registry: StrategyRegistry,
    ) -> tuple[StrategyOpportunityInput, ...]: ...


class PostgresStrategySourceAuthority:
    """Resolve supported canonical source owners directly from PostgreSQL."""

    def __init__(self, factory: PostgresConnectionFactory) -> None:
        self._factory = factory

    def reload(
        self,
        reference: RuntimeArtifactReference,
    ) -> ResolvedStrategySource:
        if reference.reference_kind == "CANDIDATE_SET":
            return self._candidate(reference)
        if reference.reference_kind.startswith("HISTORICAL_"):
            return self._historical(reference)
        if reference.reference_kind == "STRATEGY_VERSION":
            return self._strategy_version(reference)
        if reference.reference_kind == "RESEARCH_MODEL_ARTIFACT":
            return self._research_model(reference)
        return self._research_validation(reference)

    def _candidate(
        self,
        reference: RuntimeArtifactReference,
    ) -> ResolvedStrategySource:
        with self._factory.connection(read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT payload_json, created_at
                FROM state_runtime_candidate_artifact
                WHERE candidate_id = %s AND candidate_hash = %s
                UNION ALL
                SELECT payload_json->'payload', source_max_event_time
                FROM historical_corpus_session_component
                WHERE component_kind = 'CANDIDATE'
                  AND payload_json->'payload'->'envelope'->>'artifact_id' = %s
                  AND payload_json->'payload'->'envelope'->>'content_hash' = %s
                """,
                (
                    str(reference.artifact_id),
                    reference.content_hash,
                    str(reference.artifact_id),
                    reference.content_hash,
                ),
            ).fetchall()
        if len(rows) != 1 or not isinstance(rows[0][0], Mapping):
            raise KeyError(str(reference.artifact_id))
        candidate = CandidateSet.from_canonical_dict(dict(rows[0][0]))
        candidate.envelope.verify_payload(candidate.artifact_payload())
        actual = RuntimeArtifactReference(
            "CANDIDATE_SET",
            candidate.envelope.artifact_id,
            candidate.envelope.content_hash,
        )
        if actual != reference:
            raise ValueError("Candidate owner projection drifted")
        return ResolvedStrategySource(
            reference,
            rows[0][1],
            tuple(sorted(item.symbol for item in candidate.records)),
            (),
            candidate.to_canonical_dict(),
        )

    def _historical(
        self,
        reference: RuntimeArtifactReference,
    ) -> ResolvedStrategySource:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT payload_json, source_max_event_time
                FROM historical_corpus_session_component
                WHERE component_id = %s AND component_hash = %s
                """,
                (str(reference.artifact_id), reference.content_hash),
            ).fetchone()
        if row is None or not isinstance(row[0], Mapping):
            raise KeyError(str(reference.artifact_id))
        component = HistoricalSessionComponent.from_canonical_dict(row[0])
        actual = _runtime_reference(component.reference)
        if actual != reference:
            raise ValueError("Historical Strategy source owner drifted")
        return ResolvedStrategySource(
            reference,
            row[1],
            _payload_symbols(component.payload),
            tuple(_runtime_reference(item) for item in component.source_references),
            component.to_canonical_dict(),
        )

    def _strategy_version(
        self,
        reference: RuntimeArtifactReference,
    ) -> ResolvedStrategySource:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT payload_json, created_at
                FROM strategy_version
                WHERE version_id = %s AND version_hash = %s
                """,
                (str(reference.artifact_id), reference.content_hash),
            ).fetchone()
        if row is None or not isinstance(row[0], Mapping):
            raise KeyError(str(reference.artifact_id))
        version = StrategyVersion.from_canonical_dict(row[0])
        if version.version_id != reference.artifact_id or version.version_hash != reference.content_hash:
            raise ValueError("Strategy Version owner drifted")
        return ResolvedStrategySource(reference, row[1], (), (), dict(row[0]))

    def _research_model(
        self,
        reference: RuntimeArtifactReference,
    ) -> ResolvedStrategySource:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT payload_json, trained_at
                FROM research_model_artifact
                WHERE artifact_id = %s AND artifact_hash = %s
                """,
                (str(reference.artifact_id), reference.content_hash),
            ).fetchone()
        if row is None or not isinstance(row[0], Mapping):
            raise KeyError(str(reference.artifact_id))
        return ResolvedStrategySource(
            reference,
            row[1],
            _payload_symbols(row[0]),
            _payload_references(row[0]),
            dict(row[0]),
        )

    def _research_validation(
        self,
        reference: RuntimeArtifactReference,
    ) -> ResolvedStrategySource:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT payload_json, created_at
                FROM research_validation_artifact
                WHERE artifact_kind = %s AND artifact_id = %s
                  AND artifact_hash = %s
                """,
                (
                    reference.reference_kind,
                    str(reference.artifact_id),
                    reference.content_hash,
                ),
            ).fetchone()
        if row is None or not isinstance(row[0], Mapping):
            raise KeyError(str(reference.artifact_id))
        return ResolvedStrategySource(
            reference,
            row[1],
            _payload_symbols(row[0]),
            _payload_references(row[0]),
            dict(row[0]),
        )


class PostgresStrategyOpportunityAuthority:
    """Persist, reload and semantically verify both pre-Strategy owner facts."""

    def __init__(
        self,
        factory: PostgresConnectionFactory,
        *,
        source_authority: StrategySourceAuthority | None = None,
        apply_migrations: bool = False,
    ) -> None:
        self._factory = factory
        self._sources = source_authority or PostgresStrategySourceAuthority(factory)
        if apply_migrations:
            PostgresMigrator().apply_all(factory)

    def record_risk_state(
        self,
        state: PreStrategyRiskState,
        *,
        created_at: datetime,
    ) -> PreStrategyRiskState:
        resolved = tuple(self._sources.reload(item) for item in state.source_references)
        if any(item.available_at > state.decision_time for item in resolved):
            raise ValueError("pre-Strategy Risk source is unavailable at DecisionTime")

        def operation(connection: Any) -> None:
            connection.execute(
                """
                INSERT INTO pre_strategy_risk_state(
                    risk_state_id, risk_state_hash, account_scope,
                    candidate_id, candidate_hash, decision_time,
                    available_at, payload_json, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (risk_state_id) DO NOTHING
                """,
                (
                    str(state.risk_state_id),
                    state.risk_state_hash,
                    state.account_scope,
                    str(state.candidate_reference.artifact_id),
                    state.candidate_reference.content_hash,
                    state.decision_time,
                    state.available_at,
                    Jsonb(state.to_canonical_dict()),
                    created_at,
                ),
            )
            _insert_bindings(
                connection,
                table="pre_strategy_risk_source_binding",
                id_column="risk_state_id",
                hash_column="risk_state_hash",
                owner_id=state.risk_state_id,
                owner_hash=state.risk_state_hash,
                references=state.source_references,
            )

        self._factory.run_transaction(operation)
        return self.get_risk_state(state.reference)

    def get_risk_state(
        self,
        reference: RuntimeArtifactReference,
    ) -> PreStrategyRiskState:
        if reference.reference_kind != "PRE_STRATEGY_RISK_STATE":
            raise ValueError("pre-Strategy Risk reference kind is invalid")
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT payload_json FROM pre_strategy_risk_state
                WHERE risk_state_id = %s AND risk_state_hash = %s
                """,
                (str(reference.artifact_id), reference.content_hash),
            ).fetchone()
            bindings = _load_bindings(
                connection,
                table="pre_strategy_risk_source_binding",
                id_column="risk_state_id",
                owner_id=reference.artifact_id,
            )
        if row is None or not isinstance(row[0], Mapping):
            raise KeyError(str(reference.artifact_id))
        state = PreStrategyRiskState.from_canonical_dict(row[0])
        if state.reference != reference or bindings != state.source_references:
            raise ValueError("pre-Strategy Risk PostgreSQL projection drifted")
        return state

    def record_opportunity(
        self,
        opportunity: StrategyOpportunityInput,
        *,
        created_at: datetime,
    ) -> StrategyOpportunityInput:
        self._verify_opportunity(opportunity)
        references = _opportunity_sources(opportunity)

        def operation(connection: Any) -> None:
            connection.execute(
                """
                INSERT INTO strategy_opportunity(
                    opportunity_id, opportunity_hash,
                    strategy_version_id, strategy_version_hash,
                    candidate_id, candidate_hash, risk_state_id,
                    risk_state_hash, symbol, decision_time, available_at,
                    payload_json, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (opportunity_id) DO NOTHING
                """,
                (
                    str(opportunity.opportunity_id),
                    opportunity.binding_hash,
                    str(opportunity.strategy_version_reference.artifact_id),
                    opportunity.strategy_version_reference.content_hash,
                    str(opportunity.candidate_reference.artifact_id),
                    opportunity.candidate_reference.content_hash,
                    str(opportunity.risk_state_reference.artifact_id),
                    opportunity.risk_state_reference.content_hash,
                    opportunity.symbol,
                    opportunity.decision_time,
                    opportunity.available_at,
                    Jsonb(opportunity.to_canonical_dict()),
                    created_at,
                ),
            )
            _insert_bindings(
                connection,
                table="strategy_opportunity_source_binding",
                id_column="opportunity_id",
                hash_column="opportunity_hash",
                owner_id=opportunity.opportunity_id,
                owner_hash=opportunity.binding_hash,
                references=references,
            )

        self._factory.run_transaction(operation)
        return self.reload(opportunity)

    def reload(
        self,
        opportunity: StrategyOpportunityInput,
    ) -> StrategyOpportunityInput:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT payload_json FROM strategy_opportunity
                WHERE opportunity_id = %s AND opportunity_hash = %s
                """,
                (str(opportunity.opportunity_id), opportunity.binding_hash),
            ).fetchone()
            bindings = _load_bindings(
                connection,
                table="strategy_opportunity_source_binding",
                id_column="opportunity_id",
                owner_id=opportunity.opportunity_id,
            )
        if row is None or not isinstance(row[0], Mapping):
            raise KeyError(str(opportunity.opportunity_id))
        restored = StrategyOpportunityInput.from_canonical_dict(row[0])
        if restored != opportunity or bindings != _opportunity_sources(restored):
            raise ValueError("Strategy Opportunity PostgreSQL projection drifted")
        self._verify_opportunity(restored)
        return restored

    def resolve(
        self,
        *,
        candidate_reference: RuntimeArtifactReference,
        decision_time: datetime,
        registry: StrategyRegistry,
    ) -> tuple[StrategyOpportunityInput, ...]:
        version_references = tuple(
            RuntimeArtifactReference(
                "STRATEGY_VERSION", item.version_id, item.version_hash
            )
            for item in registry.active_versions
        )
        if not version_references:
            return ()
        with self._factory.connection(read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT payload_json FROM strategy_opportunity
                WHERE candidate_id = %s AND candidate_hash = %s
                  AND decision_time = %s
                ORDER BY strategy_version_id, symbol
                """,
                (
                    str(candidate_reference.artifact_id),
                    candidate_reference.content_hash,
                    decision_time,
                ),
            ).fetchall()
        allowed = set(version_references)
        opportunities = tuple(
            StrategyOpportunityInput.from_canonical_dict(row[0])
            for row in rows
            if isinstance(row[0], Mapping)
        )
        if len(opportunities) != len(rows):
            raise ValueError("Strategy Opportunity owner payload is malformed")
        selected = tuple(
            item for item in opportunities if item.strategy_version_reference in allowed
        )
        for item in selected:
            self.reload(item)
        return selected

    def _verify_opportunity(self, opportunity: StrategyOpportunityInput) -> None:
        risk = self.get_risk_state(opportunity.risk_state_reference)
        if (
            risk.candidate_reference != opportunity.candidate_reference
            or risk.decision_time != opportunity.decision_time
        ):
            raise ValueError("Strategy Opportunity Risk/Candidate DecisionTime drifted")
        risk_decision = risk.decision_for(opportunity.symbol)
        if (
            risk_decision.allows_action != opportunity.risk_allows_action
            or risk_decision.reason_codes != opportunity.risk_reason_codes
        ):
            raise ValueError("Strategy Opportunity Risk projection drifted")
        resolved = {
            item.reference: item
            for item in (
                self._sources.reload(reference)
                for reference in _opportunity_sources(opportunity)
                if reference != opportunity.risk_state_reference
            )
        }
        if any(item.available_at > opportunity.decision_time for item in resolved.values()):
            raise ValueError("Strategy Opportunity owner is unavailable at DecisionTime")
        for reference in (
            opportunity.candidate_reference,
            opportunity.signal_reference,
            opportunity.forecast_reference,
        ):
            if opportunity.symbol not in resolved[reference].symbols:
                raise ValueError("Strategy Opportunity owner has different symbol")
        signal = resolved[opportunity.signal_reference]
        forecast = resolved[opportunity.forecast_reference]
        if opportunity.candidate_reference not in signal.source_references:
            raise ValueError("Strategy Signal does not bind the Candidate owner")
        for required in (
            opportunity.signal_reference,
            opportunity.context_reference,
            opportunity.model_reference,
        ):
            if required not in forecast.source_references:
                raise ValueError("Strategy Forecast lineage is incomplete")
        maximum_availability = max(
            risk.available_at,
            *(item.available_at for item in resolved.values()),
        )
        if opportunity.available_at != maximum_availability:
            raise ValueError("Strategy Opportunity available_at drifted from owners")


def _opportunity_sources(
    opportunity: StrategyOpportunityInput,
) -> tuple[RuntimeArtifactReference, ...]:
    return _references(
        (
            opportunity.strategy_version_reference,
            opportunity.candidate_reference,
            opportunity.signal_reference,
            opportunity.forecast_reference,
            opportunity.context_reference,
            opportunity.risk_state_reference,
            opportunity.model_reference,
        )
    )


def _insert_bindings(
    connection: Any,
    *,
    table: str,
    id_column: str,
    hash_column: str,
    owner_id: ArtifactId,
    owner_hash: str,
    references: tuple[RuntimeArtifactReference, ...],
) -> None:
    allowed = {
        (
            "pre_strategy_risk_source_binding",
            "risk_state_id",
            "risk_state_hash",
        ),
        (
            "strategy_opportunity_source_binding",
            "opportunity_id",
            "opportunity_hash",
        ),
    }
    if (table, id_column, hash_column) not in allowed:
        raise ValueError("Strategy binding table is not allowed")
    with connection.cursor() as cursor:
        cursor.executemany(
            f"""
            INSERT INTO {table}(
                {id_column}, {hash_column}, ordinal,
                reference_kind, artifact_id, content_hash
            ) VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT ({id_column}, ordinal) DO NOTHING
            """,
            tuple(
                (
                    str(owner_id),
                    owner_hash,
                    ordinal,
                    item.reference_kind,
                    str(item.artifact_id),
                    item.content_hash,
                )
                for ordinal, item in enumerate(references, 1)
            ),
        )


def _load_bindings(
    connection: Any,
    *,
    table: str,
    id_column: str,
    owner_id: ArtifactId,
) -> tuple[RuntimeArtifactReference, ...]:
    allowed = {
        ("pre_strategy_risk_source_binding", "risk_state_id"),
        ("strategy_opportunity_source_binding", "opportunity_id"),
    }
    if (table, id_column) not in allowed:
        raise ValueError("Strategy binding table is not allowed")
    rows = connection.execute(
        f"""
        SELECT reference_kind, artifact_id, content_hash
        FROM {table} WHERE {id_column} = %s ORDER BY ordinal
        """,
        (str(owner_id),),
    ).fetchall()
    return tuple(
        RuntimeArtifactReference(str(row[0]), ArtifactId(str(row[1])), str(row[2]))
        for row in rows
    )


def _payload_symbols(payload: Mapping[str, Any]) -> tuple[str, ...]:
    found: set[str] = set()

    def visit(value: object) -> None:
        if isinstance(value, Mapping):
            symbol = value.get("symbol")
            if isinstance(symbol, str) and symbol.strip():
                found.add(symbol)
            for item in value.values():
                visit(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                visit(item)

    visit(payload)
    return tuple(sorted(found))


def _payload_references(
    payload: Mapping[str, Any],
) -> tuple[RuntimeArtifactReference, ...]:
    found: set[RuntimeArtifactReference] = set()

    def visit(value: object) -> None:
        if isinstance(value, Mapping):
            if set(value) >= {"artifact_id", "content_hash"}:
                kind = value.get("reference_kind", value.get("artifact_kind"))
                if isinstance(kind, str):
                    try:
                        found.add(
                            RuntimeArtifactReference(
                                kind,
                                ArtifactId(str(value["artifact_id"])),
                                str(value["content_hash"]),
                            )
                        )
                    except ValueError:
                        pass
            for item in value.values():
                visit(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                visit(item)

    visit(payload)
    return _references(tuple(found))


def _runtime_reference(reference: Any) -> RuntimeArtifactReference:
    return RuntimeArtifactReference(
        reference.artifact_kind,
        reference.artifact_id,
        reference.content_hash,
    )


def _references(
    references: tuple[RuntimeArtifactReference, ...],
) -> tuple[RuntimeArtifactReference, ...]:
    return tuple(
        sorted(
            set(references),
            key=lambda item: (
                item.reference_kind,
                str(item.artifact_id),
                item.content_hash,
            ),
        )
    )


__all__ = [
    "PostgresStrategyOpportunityAuthority",
    "PostgresStrategySourceAuthority",
    "ResolvedStrategySource",
    "StrategySourceAuthority",
    "StrategyOpportunityResolverAuthority",
]
