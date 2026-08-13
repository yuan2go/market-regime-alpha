"""PostgreSQL owner repository for immutable Phase E session components."""

from __future__ import annotations

from typing import Any, Mapping

from psycopg.types.json import Jsonb

from market_regime_alpha.application.historical_corpus.materialization_contracts import (
    HistoricalComponentKind,
    HistoricalSessionComponent,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.persistence.postgres.connection import PostgresConnectionFactory
from market_regime_alpha.persistence.postgres.migrator import PostgresMigrator


class HistoricalMaterializationConflict(RuntimeError):
    """Raised when an immutable session component conflicts with Authority."""


class PostgresHistoricalMaterializationRepository:
    def __init__(
        self,
        factory: PostgresConnectionFactory,
        *,
        apply_migrations: bool = True,
    ) -> None:
        self._factory = factory
        if apply_migrations:
            PostgresMigrator().apply_all(factory)

    def put(
        self,
        *,
        component: HistoricalSessionComponent,
        ordinal: int,
    ) -> HistoricalSessionComponent:
        component.verify_identity()
        if ordinal <= 0:
            raise ValueError("Historical component ordinal must be positive")

        def operation(connection: Any) -> None:
            self._verify_session(connection, component)
            self._insert(connection, component, ordinal)

        self._factory.run_transaction(operation)
        return component

    def put_many(
        self,
        items: tuple[tuple[HistoricalSessionComponent, int], ...],
    ) -> tuple[HistoricalSessionComponent, ...]:
        if not items:
            raise ValueError("Historical component batch must not be empty")
        components = tuple(item[0] for item in items)
        for component, ordinal in items:
            component.verify_identity()
            if ordinal <= 0:
                raise ValueError("Historical component ordinal must be positive")
        first = components[0]
        if any(
            item.run_id != first.run_id
            or item.session_id != first.session_id
            or item.trading_date != first.trading_date
            for item in components
        ):
            raise ValueError("Historical component batch must share one session")
        if len({item.component_id for item in components}) != len(components):
            raise ValueError("Historical component batch identities must be unique")
        if len({ordinal for _component, ordinal in items}) != len(items):
            raise ValueError("Historical component batch ordinals must be unique")

        def operation(connection: Any) -> None:
            self._verify_session(connection, first)
            for component, ordinal in items:
                self._insert(connection, component, ordinal)

        self._factory.run_transaction(operation)
        return components

    @staticmethod
    def _verify_session(connection: Any, component: HistoricalSessionComponent) -> None:
        session = connection.execute(
            """
            SELECT trading_date
            FROM historical_research_session
            WHERE run_id = %s AND session_id = %s
            """,
            (str(component.run_id), str(component.session_id)),
        ).fetchone()
        if session is None or session[0] != component.trading_date:
            raise HistoricalMaterializationConflict(
                "Historical component session owner mismatch"
            )

    def _insert(
        self,
        connection: Any,
        component: HistoricalSessionComponent,
        ordinal: int,
    ) -> None:
        connection.execute(
                """
                INSERT INTO historical_corpus_session_component(
                    component_id, component_hash, run_id, session_id,
                    trading_date, ordinal, component_kind,
                    source_max_event_time, materialized_at, payload_json, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (component_id) DO NOTHING
                """,
                (
                    str(component.component_id),
                    component.component_hash,
                    str(component.run_id),
                    str(component.session_id),
                    component.trading_date,
                    ordinal,
                    component.component_kind.value,
                    component.source_max_event_time,
                    component.materialized_at,
                    Jsonb(component.to_canonical_dict()),
                    component.materialized_at,
                ),
        )
        for source_ordinal, source in enumerate(component.source_references, 1):
            connection.execute(
                    """
                    INSERT INTO historical_corpus_component_source_binding(
                        component_id, component_hash, ordinal, artifact_kind,
                        artifact_id, content_hash
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (component_id, ordinal) DO NOTHING
                    """,
                    (
                        str(component.component_id),
                        component.component_hash,
                        source_ordinal,
                        source.artifact_kind,
                        str(source.artifact_id),
                        source.content_hash,
                    ),
            )
        self._verify_projection(connection, component, ordinal)

    def get(
        self, reference: ValidationArtifactReference
    ) -> HistoricalSessionComponent:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT ordinal, payload_json
                FROM historical_corpus_session_component
                WHERE component_id = %s AND component_hash = %s
                """,
                (str(reference.artifact_id), reference.content_hash),
            ).fetchone()
            if row is None:
                raise KeyError(str(reference.artifact_id))
            payload = row[1]
            if not isinstance(payload, Mapping):
                raise HistoricalMaterializationConflict(
                    "Historical component payload projection is invalid"
                )
            component = HistoricalSessionComponent.from_canonical_dict(payload)
            self._verify_projection(connection, component, int(row[0]))
        if component.reference != reference:
            raise HistoricalMaterializationConflict(
                "Historical component reference kind mismatch"
            )
        return component

    def list_for_run(
        self,
        *,
        run_id: ArtifactId,
        component_kind: HistoricalComponentKind | None = None,
    ) -> tuple[HistoricalSessionComponent, ...]:
        with self._factory.connection(read_only=True) as connection:
            if component_kind is None:
                rows = connection.execute(
                    """
                    SELECT component_id, component_hash, component_kind,
                           ordinal, payload_json
                    FROM historical_corpus_session_component
                    WHERE run_id = %s
                    ORDER BY trading_date, ordinal, component_id
                    """,
                    (str(run_id),),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT component_id, component_hash, component_kind,
                           ordinal, payload_json
                    FROM historical_corpus_session_component
                    WHERE run_id = %s AND component_kind = %s
                    ORDER BY trading_date, ordinal, component_id
                    """,
                    (str(run_id), component_kind.value),
                ).fetchall()
            if component_kind is None:
                source_rows = connection.execute(
                    """
                    SELECT binding.component_id, binding.ordinal,
                           binding.artifact_kind, binding.artifact_id,
                           binding.content_hash
                    FROM historical_corpus_component_source_binding AS binding
                    JOIN historical_corpus_session_component AS component
                      ON component.component_id = binding.component_id
                     AND component.component_hash = binding.component_hash
                    WHERE component.run_id = %s
                    ORDER BY binding.component_id, binding.ordinal
                    """,
                    (str(run_id),),
                ).fetchall()
            else:
                source_rows = connection.execute(
                    """
                    SELECT binding.component_id, binding.ordinal,
                           binding.artifact_kind, binding.artifact_id,
                           binding.content_hash
                    FROM historical_corpus_component_source_binding AS binding
                    JOIN historical_corpus_session_component AS component
                      ON component.component_id = binding.component_id
                     AND component.component_hash = binding.component_hash
                    WHERE component.run_id = %s AND component.component_kind = %s
                    ORDER BY binding.component_id, binding.ordinal
                    """,
                    (str(run_id), component_kind.value),
                ).fetchall()
        sources: dict[str, list[tuple[int, str, str, str]]] = {}
        for item in source_rows:
            sources.setdefault(str(item[0]), []).append(
                (int(item[1]), str(item[2]), str(item[3]), str(item[4]))
            )
        components = []
        for row in rows:
            payload = row[4]
            if not isinstance(payload, Mapping):
                raise HistoricalMaterializationConflict(
                    "Historical component payload projection is invalid"
                )
            component = HistoricalSessionComponent.from_canonical_dict(payload)
            expected_reference = ValidationArtifactReference(
                f"HISTORICAL_{str(row[2])}",
                ArtifactId(str(row[0])),
                str(row[1]),
            )
            source_projection = tuple(
                (index, item.artifact_kind, str(item.artifact_id), item.content_hash)
                for index, item in enumerate(component.source_references, 1)
            )
            if (
                component.reference != expected_reference
                or component.run_id != run_id
                or int(row[3]) <= 0
                or tuple(sources.get(str(component.component_id), ()))
                != source_projection
            ):
                raise HistoricalMaterializationConflict(
                    "Historical component batch projection conflict"
                )
            components.append(component)
        return tuple(components)

    @staticmethod
    def _verify_projection(
        connection: Any,
        component: HistoricalSessionComponent,
        ordinal: int,
    ) -> None:
        row = connection.execute(
            """
            SELECT run_id, session_id, trading_date, ordinal, component_kind,
                   source_max_event_time, materialized_at, payload_json
            FROM historical_corpus_session_component
            WHERE component_id = %s
            """,
            (str(component.component_id),),
        ).fetchone()
        expected = (
            str(component.run_id),
            str(component.session_id),
            component.trading_date,
            ordinal,
            component.component_kind.value,
            component.source_max_event_time,
            component.materialized_at,
            component.to_canonical_dict(),
        )
        actual = None if row is None else (*row[:7], dict(row[7]))
        if actual != expected:
            raise HistoricalMaterializationConflict(
                "Historical component PostgreSQL projection conflict"
            )
        rows = connection.execute(
            """
            SELECT ordinal, artifact_kind, artifact_id, content_hash
            FROM historical_corpus_component_source_binding
            WHERE component_id = %s AND component_hash = %s
            ORDER BY ordinal
            """,
            (str(component.component_id), component.component_hash),
        ).fetchall()
        source_projection = tuple(
            (index, item.artifact_kind, str(item.artifact_id), item.content_hash)
            for index, item in enumerate(component.source_references, 1)
        )
        if tuple((int(r[0]), str(r[1]), str(r[2]), str(r[3])) for r in rows) != source_projection:
            raise HistoricalMaterializationConflict(
                "Historical component source projection conflict"
            )


__all__ = [
    "HistoricalMaterializationConflict",
    "PostgresHistoricalMaterializationRepository",
]
