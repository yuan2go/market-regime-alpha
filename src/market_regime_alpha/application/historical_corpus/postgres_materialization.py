"""PostgreSQL owner repository for immutable Phase E session components."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime
from typing import Any, Mapping

from psycopg.types.json import Jsonb

from market_regime_alpha.application.historical_corpus.materialization_contracts import (
    HistoricalComponentKind,
    HistoricalSessionComponent,
)
from market_regime_alpha.application.research_evaluation.targeted_outcome import (
    TargetOutcomeLabel,
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
            item.run_id != first.run_id or item.session_id != first.session_id or item.trading_date != first.trading_date
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
            raise HistoricalMaterializationConflict("Historical component session owner mismatch")

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
        if component.component_kind is HistoricalComponentKind.OUTCOME:
            raw_labels = component.payload.get("labels")
            if not isinstance(raw_labels, list):
                raise HistoricalMaterializationConflict("Historical Outcome labels projection is missing")
            labels = tuple(TargetOutcomeLabel.from_canonical_dict(item) for item in raw_labels if isinstance(item, Mapping))
            if len(labels) != len(raw_labels):
                raise HistoricalMaterializationConflict("Historical Outcome labels projection is invalid")
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO historical_corpus_outcome_label(
                        component_id, component_hash, trading_date,
                        label_id, label_hash, symbol, target_id,
                        label_interval_end, outcome_available_at,
                        availability_status, payload_json
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (component_id, label_id) DO NOTHING
                    """,
                    tuple(
                        (
                            str(component.component_id),
                            component.component_hash,
                            component.trading_date,
                            str(label.label_id),
                            label.label_hash,
                            label.symbol,
                            str(label.target.artifact_id),
                            label.label_interval_end,
                            label.outcome_available_at,
                            label.availability_status.value,
                            Jsonb(label.to_canonical_dict()),
                        )
                        for label in labels
                    ),
                )
        self._verify_projection(connection, component, ordinal)

    def get(self, reference: ValidationArtifactReference) -> HistoricalSessionComponent:
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
                raise HistoricalMaterializationConflict("Historical component payload projection is invalid")
            component = HistoricalSessionComponent.from_canonical_dict(payload)
            self._verify_projection(connection, component, int(row[0]))
        if component.reference != reference:
            raise HistoricalMaterializationConflict("Historical component reference kind mismatch")
        return component

    def list_for_run(
        self,
        *,
        run_id: ArtifactId,
        component_kind: HistoricalComponentKind | None = None,
    ) -> tuple[HistoricalSessionComponent, ...]:
        return tuple(
            component
            for batch in self.iter_for_run(
                run_id=run_id,
                component_kind=component_kind,
                batch_size=256,
            )
            for component in batch
        )

    def iter_for_run(
        self,
        *,
        run_id: ArtifactId,
        component_kind: HistoricalComponentKind | None = None,
        batch_size: int = 16,
    ) -> Iterator[tuple[HistoricalSessionComponent, ...]]:
        """Keyset-stream exact components under one consistent DB snapshot."""

        if batch_size <= 0 or batch_size > 1_000:
            raise ValueError("Historical component batch_size must be 1..1000")
        with self._factory.connection(read_only=True) as connection:
            cursor: tuple[date, int, str] | None = None
            while True:
                parameters: list[object] = [str(run_id)]
                kind_clause = ""
                if component_kind is not None:
                    kind_clause = "AND component_kind = %s"
                    parameters.append(component_kind.value)
                cursor_clause = ""
                if cursor is not None:
                    cursor_clause = "AND (trading_date, ordinal, component_id) > (%s, %s, %s)"
                    parameters.extend(cursor)
                parameters.append(batch_size)
                rows = connection.execute(
                    f"""
                    SELECT component_id, component_hash, component_kind,
                           ordinal, trading_date, payload_json
                    FROM historical_corpus_session_component
                    WHERE run_id = %s {kind_clause} {cursor_clause}
                    ORDER BY trading_date, ordinal, component_id
                    LIMIT %s
                    """,  # noqa: S608 -- clauses are fixed internal literals.
                    tuple(parameters),
                ).fetchall()
                if not rows:
                    break
                component_ids = [str(row[0]) for row in rows]
                source_rows = connection.execute(
                    """
                    SELECT component_id, ordinal, artifact_kind, artifact_id,
                           content_hash
                    FROM historical_corpus_component_source_binding
                    WHERE component_id = ANY(%s)
                    ORDER BY component_id, ordinal
                    """,
                    (component_ids,),
                ).fetchall()
                yield self._restore_batch(
                    rows=rows,
                    source_rows=source_rows,
                    run_id=run_id,
                )
                last = rows[-1]
                cursor = (last[4], int(last[3]), str(last[0]))

    def list_for_run_before(
        self,
        *,
        run_id: ArtifactId,
        component_kind: HistoricalComponentKind,
        before: date,
        maximum_components: int,
    ) -> tuple[HistoricalSessionComponent, ...]:
        """Read a declared, bounded prior component window in canonical order."""

        if maximum_components <= 0:
            raise ValueError("Historical prior component limit must be positive")
        with self._factory.connection(read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT component_id, component_hash, component_kind,
                       ordinal, trading_date, payload_json
                FROM historical_corpus_session_component
                WHERE run_id = %s AND component_kind = %s
                  AND trading_date < %s
                ORDER BY trading_date DESC, ordinal DESC, component_id DESC
                LIMIT %s
                """,
                (
                    str(run_id),
                    component_kind.value,
                    before,
                    maximum_components + 1,
                ),
            ).fetchall()
            if len(rows) > maximum_components:
                raise ValueError("Historical prior component window exceeds declared ceiling")
            rows = sorted(rows, key=lambda row: (row[4], int(row[3]), str(row[0])))
            component_ids = [str(row[0]) for row in rows]
            source_rows = (
                []
                if not component_ids
                else connection.execute(
                    """
                    SELECT component_id, ordinal, artifact_kind, artifact_id,
                           content_hash
                    FROM historical_corpus_component_source_binding
                    WHERE component_id = ANY(%s)
                    ORDER BY component_id, ordinal
                    """,
                    (component_ids,),
                ).fetchall()
            )
        return self._restore_batch(
            rows=rows,
            source_rows=source_rows,
            run_id=run_id,
        )

    def list_outcome_labels_before(
        self,
        *,
        run_id: ArtifactId,
        before: date,
        symbol: str,
        target_id: ArtifactId,
        maximum_labels: int,
    ) -> tuple[tuple[ValidationArtifactReference, TargetOutcomeLabel], ...]:
        """Project only one symbol/Target history for Forecast sampling."""

        return self.list_outcome_labels_for_symbols_before(
            run_id=run_id,
            before=before,
            symbols=(symbol,),
            target_id=target_id,
            maximum_labels_per_symbol=maximum_labels,
        )[symbol]

    def list_outcome_labels_for_symbols_before(
        self,
        *,
        run_id: ArtifactId,
        before: date,
        symbols: tuple[str, ...],
        target_id: ArtifactId,
        maximum_labels_per_symbol: int,
    ) -> Mapping[
        str,
        tuple[tuple[ValidationArtifactReference, TargetOutcomeLabel], ...],
    ]:
        """Project a bounded multi-symbol Forecast sample window in one read."""

        if not symbols or symbols != tuple(sorted(set(symbols))):
            raise ValueError("Historical Outcome symbols must be ordered")
        if maximum_labels_per_symbol <= 0:
            raise ValueError("Historical Outcome label limit must be positive")
        with self._factory.connection(read_only=True) as connection:
            rows = connection.execute(
                """
                WITH ranked_labels AS (
                    SELECT label.symbol, component.component_id,
                           component.component_hash, label.payload_json,
                           (
                               SELECT count(*) = 1
                               FROM jsonb_array_elements(
                                   component.payload_json->'payload'->'labels'
                               ) AS owned_label
                               WHERE owned_label->>'label_id' = label.label_id
                                 AND owned_label = label.payload_json
                           ) AS owner_matches,
                           row_number() OVER (
                               PARTITION BY label.symbol
                               ORDER BY label.trading_date DESC,
                                        component.component_id DESC,
                                        label.label_id DESC
                           ) AS sample_ordinal
                    FROM historical_corpus_outcome_label AS label
                    JOIN historical_corpus_session_component AS component
                      ON component.component_id = label.component_id
                     AND component.component_hash = label.component_hash
                    WHERE component.run_id = %s
                      AND component.component_kind = 'OUTCOME'
                      AND label.trading_date < %s
                      AND label.symbol = ANY(%s)
                      AND label.target_id = %s
                )
                SELECT symbol, component_id, component_hash, payload_json,
                       owner_matches
                FROM ranked_labels
                WHERE sample_ordinal <= %s
                ORDER BY symbol, sample_ordinal DESC, component_id, payload_json->>'label_id'
                """,
                (
                    str(run_id),
                    before,
                    list(symbols),
                    str(target_id),
                    maximum_labels_per_symbol,
                ),
            ).fetchall()
        if any(not bool(row[4]) for row in rows):
            raise HistoricalMaterializationConflict(
                "Historical Outcome label projection diverged from owner"
            )
        grouped: dict[
            str,
            list[tuple[ValidationArtifactReference, TargetOutcomeLabel]],
        ] = {symbol: [] for symbol in symbols}
        for row in rows:
            grouped[str(row[0])].append(
                (
                    ValidationArtifactReference(
                        "HISTORICAL_OUTCOME",
                        ArtifactId(str(row[1])),
                        str(row[2]),
                    ),
                    TargetOutcomeLabel.from_canonical_dict(row[3]),
                )
            )
        return {symbol: tuple(grouped[symbol]) for symbol in symbols}

    def list_references_for_run(
        self,
        *,
        run_id: ArtifactId,
        component_kind: HistoricalComponentKind,
    ) -> tuple[ValidationArtifactReference, ...]:
        """Project only ordered immutable identities for set bindings."""

        with self._factory.connection(read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT component_id, component_hash, component_kind
                FROM historical_corpus_session_component
                WHERE run_id = %s AND component_kind = %s
                ORDER BY trading_date, ordinal, component_id
                """,
                (str(run_id), component_kind.value),
            ).fetchall()
        references = tuple(
            ValidationArtifactReference(
                f"HISTORICAL_{str(row[2])}",
                ArtifactId(str(row[0])),
                str(row[1]),
            )
            for row in rows
        )
        if len(references) != len(set(references)):
            raise HistoricalMaterializationConflict("Historical component reference projection is not unique")
        return references

    def maximum_materialized_at(
        self,
        *,
        run_id: ArtifactId,
        component_kinds: tuple[HistoricalComponentKind, ...],
    ) -> datetime:
        if not component_kinds or component_kinds != tuple(sorted(set(component_kinds), key=lambda item: item.value)):
            raise ValueError("Historical component kinds must be ordered")
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT max(materialized_at), count(*)
                FROM historical_corpus_session_component
                WHERE run_id = %s AND component_kind = ANY(%s)
                """,
                (
                    str(run_id),
                    [item.value for item in component_kinds],
                ),
            ).fetchone()
        if row is None or row[0] is None or int(row[1]) == 0:
            raise KeyError(str(run_id))
        return row[0]

    @staticmethod
    def _restore_batch(
        *,
        rows: list[Any],
        source_rows: list[Any],
        run_id: ArtifactId,
    ) -> tuple[HistoricalSessionComponent, ...]:
        sources: dict[str, list[tuple[int, str, str, str]]] = {}
        for item in source_rows:
            sources.setdefault(str(item[0]), []).append((int(item[1]), str(item[2]), str(item[3]), str(item[4])))
        components = []
        for row in rows:
            payload = row[5]
            if not isinstance(payload, Mapping):
                raise HistoricalMaterializationConflict("Historical component payload projection is invalid")
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
                or component.trading_date != row[4]
                or int(row[3]) <= 0
                or tuple(sources.get(str(component.component_id), ())) != source_projection
            ):
                raise HistoricalMaterializationConflict("Historical component batch projection conflict")
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
            raise HistoricalMaterializationConflict("Historical component PostgreSQL projection conflict")
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
            raise HistoricalMaterializationConflict("Historical component source projection conflict")
        if component.component_kind is HistoricalComponentKind.OUTCOME:
            label_rows = connection.execute(
                "SELECT payload_json FROM historical_corpus_outcome_label WHERE component_id = %s ORDER BY symbol, target_id, label_id",
                (str(component.component_id),),
            ).fetchall()
            expected_labels = tuple(
                sorted(
                    (
                        TargetOutcomeLabel.from_canonical_dict(item)
                        for item in component.payload.get("labels", ())
                        if isinstance(item, Mapping)
                    ),
                    key=lambda item: (
                        item.symbol,
                        str(item.target.artifact_id),
                        str(item.label_id),
                    ),
                )
            )
            if tuple(dict(row[0]) for row in label_rows) != tuple(item.to_canonical_dict() for item in expected_labels):
                raise HistoricalMaterializationConflict("Historical Outcome label projection conflict")


__all__ = [
    "HistoricalMaterializationConflict",
    "PostgresHistoricalMaterializationRepository",
]
