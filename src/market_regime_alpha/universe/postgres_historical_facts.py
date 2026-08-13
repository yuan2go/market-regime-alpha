"""PostgreSQL Authority for exploratory historical Security Facts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping

from psycopg.types.json import Jsonb

from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.postgres.migrator import PostgresMigrator
from market_regime_alpha.universe.historical_facts import (
    HistoricalSecurityFact,
    HistoricalSecurityFactCoverageGap,
    HistoricalSecurityFactKind,
    HistoricalSecurityFactsOwner,
)


class HistoricalSecurityFactsConflict(RuntimeError):
    """Raised when immutable historical fact projections diverge."""


@dataclass(frozen=True, slots=True)
class HistoricalSecurityFactProjection:
    """One bounded Decision-time projection over an exact fact-set owner."""

    industries: Mapping[str, HistoricalSecurityFact]
    share_capital: Mapping[str, HistoricalSecurityFact]


class PostgresHistoricalSecurityFactsRepository:
    def __init__(
        self,
        factory: PostgresConnectionFactory,
        *,
        apply_migrations: bool = True,
    ) -> None:
        self._factory = factory
        if apply_migrations:
            PostgresMigrator().apply_all(factory)

    def publish(self, owner: HistoricalSecurityFactsOwner) -> HistoricalSecurityFactsOwner:
        def operation(connection: Any) -> None:
            connection.execute(
                """
                INSERT INTO free_data_historical_security_fact_set(
                    owner_id, owner_hash, first_effective_date,
                    last_effective_date, known_at, provider_id,
                    source_manifest_id, source_manifest_hash, raw_archive_id,
                    fact_count, coverage_gap_count, data_eligibility, evidence_ceiling, formal_pit,
                    payload_json, created_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, false, %s, %s
                ) ON CONFLICT (owner_id) DO NOTHING
                """,
                (
                    str(owner.owner_id),
                    owner.owner_hash,
                    owner.first_effective_date,
                    owner.last_effective_date,
                    owner.known_at,
                    owner.provider_id,
                    str(owner.source_manifest_reference.artifact_id),
                    owner.source_manifest_reference.content_hash,
                    owner.raw_archive_id,
                    len(owner.facts),
                    len(owner.coverage_gaps),
                    owner.data_eligibility.value,
                    owner.evidence_ceiling.value,
                    Jsonb(owner.to_canonical_dict()),
                    owner.known_at,
                ),
            )
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO free_data_historical_security_fact(
                        owner_id, owner_hash, fact_id, fact_hash, symbol,
                        fact_kind, effective_date, published_date,
                        source_artifact_kind, source_artifact_id,
                        source_content_hash, payload_json
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    ) ON CONFLICT (owner_id, fact_id) DO NOTHING
                    """,
                    (
                        (
                            str(owner.owner_id),
                            owner.owner_hash,
                            str(item.fact_id),
                            item.fact_hash,
                            item.symbol,
                            item.fact_kind.value,
                            item.effective_date,
                            item.published_date,
                            item.source_reference.artifact_kind,
                            str(item.source_reference.artifact_id),
                            item.source_reference.content_hash,
                            Jsonb(item.to_canonical_dict()),
                        )
                        for item in owner.facts
                    ),
                )
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO free_data_historical_security_fact_coverage_gap(
                        owner_id, owner_hash, gap_id, gap_hash, symbol,
                        fact_kind, coverage_start, coverage_end,
                        source_artifact_kind, source_artifact_id,
                        source_content_hash, payload_json
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    ) ON CONFLICT (owner_id, gap_id) DO NOTHING
                    """,
                    (
                        (
                            str(owner.owner_id),
                            owner.owner_hash,
                            str(item.gap_id),
                            item.gap_hash,
                            item.symbol,
                            item.fact_kind.value,
                            item.coverage_start,
                            item.coverage_end,
                            item.source_reference.artifact_kind,
                            str(item.source_reference.artifact_id),
                            item.source_reference.content_hash,
                            Jsonb(item.to_canonical_dict()),
                        )
                        for item in owner.coverage_gaps
                    ),
                )
            self._verify_projection(connection, owner)

        self._factory.run_transaction(operation)
        return self.get(owner.owner_id)

    def get(self, owner_id: ArtifactId) -> HistoricalSecurityFactsOwner:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT owner_hash, fact_count, coverage_gap_count, payload_json
                FROM free_data_historical_security_fact_set
                WHERE owner_id = %s
                """,
                (str(owner_id),),
            ).fetchone()
            facts = connection.execute(
                """
                SELECT payload_json
                FROM free_data_historical_security_fact
                WHERE owner_id = %s
                ORDER BY symbol, effective_date, fact_kind,
                         published_date NULLS FIRST, fact_id
                """,
                (str(owner_id),),
            ).fetchall()
            gaps = connection.execute(
                """
                SELECT payload_json
                FROM free_data_historical_security_fact_coverage_gap
                WHERE owner_id = %s
                ORDER BY symbol, coverage_start, coverage_end, fact_kind, gap_id
                """,
                (str(owner_id),),
            ).fetchall()
        if row is None or not isinstance(row[3], Mapping):
            raise KeyError(str(owner_id))
        owner = HistoricalSecurityFactsOwner.from_canonical_dict(row[3])
        projected = tuple(HistoricalSecurityFact.from_canonical_dict(item[0]) for item in facts)
        projected_gaps = tuple(
            HistoricalSecurityFactCoverageGap.from_canonical_dict(item[0])
            for item in gaps
        )
        if (
            str(row[0]) != owner.owner_hash
            or int(row[1]) != len(owner.facts)
            or int(row[2]) != len(owner.coverage_gaps)
            or projected != owner.facts
            or projected_gaps != owner.coverage_gaps
        ):
            raise HistoricalSecurityFactsConflict("Historical Security Facts owner projection diverged")
        return owner

    def industry_as_of(
        self,
        reference: ValidationArtifactReference,
        *,
        symbol: str,
        decision_date: date,
    ) -> HistoricalSecurityFact | None:
        return self._latest(
            reference,
            symbol=symbol,
            fact_kind=HistoricalSecurityFactKind.INDUSTRY,
            decision_date=decision_date,
            require_publication=False,
        )

    def share_capital_as_of(
        self,
        reference: ValidationArtifactReference,
        *,
        symbol: str,
        decision_date: date,
    ) -> HistoricalSecurityFact | None:
        return self._latest(
            reference,
            symbol=symbol,
            fact_kind=HistoricalSecurityFactKind.SHARE_CAPITAL,
            decision_date=decision_date,
            require_publication=True,
        )

    def corporate_actions(
        self,
        reference: ValidationArtifactReference,
        *,
        symbol: str,
        after: date,
        through: date,
    ) -> tuple[HistoricalSecurityFact, ...]:
        if after >= through:
            raise ValueError("Corporate-action interval must advance")
        self._verify_reference(reference)
        with self._factory.connection(read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT payload_json
                FROM free_data_historical_security_fact
                WHERE owner_id = %s AND owner_hash = %s AND symbol = %s
                  AND fact_kind IN ('ADJUSTMENT_EVENT', 'DIVIDEND_EVENT')
                  AND effective_date > %s AND effective_date <= %s
                ORDER BY effective_date, fact_kind,
                         published_date NULLS FIRST, fact_id
                """,
                (
                    str(reference.artifact_id),
                    reference.content_hash,
                    symbol,
                    after,
                    through,
                ),
            ).fetchall()
        return tuple(self._restore_fact(row[0], reference) for row in rows)

    def resolve_as_of(
        self,
        reference: ValidationArtifactReference,
        *,
        symbols: tuple[str, ...],
        decision_date: date,
    ) -> HistoricalSecurityFactProjection:
        """Resolve Industry and publication-safe shares without N+1 reads."""

        if not symbols or symbols != tuple(sorted(set(symbols))):
            raise ValueError("Historical Security Fact symbols must be ordered")
        self._verify_reference(reference)
        with self._factory.connection(read_only=True) as connection:
            industry_rows = connection.execute(
                """
                SELECT DISTINCT ON (symbol) symbol, payload_json
                FROM free_data_historical_security_fact
                WHERE owner_id = %s AND owner_hash = %s
                  AND symbol = ANY(%s) AND fact_kind = 'INDUSTRY'
                  AND effective_date <= %s
                ORDER BY symbol, effective_date DESC,
                         published_date DESC NULLS LAST, fact_id DESC
                """,
                (
                    str(reference.artifact_id),
                    reference.content_hash,
                    list(symbols),
                    decision_date,
                ),
            ).fetchall()
            share_rows = connection.execute(
                """
                SELECT DISTINCT ON (symbol) symbol, payload_json
                FROM free_data_historical_security_fact
                WHERE owner_id = %s AND owner_hash = %s
                  AND symbol = ANY(%s) AND fact_kind = 'SHARE_CAPITAL'
                  AND effective_date <= %s
                  AND published_date IS NOT NULL AND published_date <= %s
                ORDER BY symbol, published_date DESC,
                         effective_date DESC, fact_id DESC
                """,
                (
                    str(reference.artifact_id),
                    reference.content_hash,
                    list(symbols),
                    decision_date,
                    decision_date,
                ),
            ).fetchall()
        return HistoricalSecurityFactProjection(
            industries={str(row[0]): self._restore_fact(row[1], reference) for row in industry_rows},
            share_capital={str(row[0]): self._restore_fact(row[1], reference) for row in share_rows},
        )

    def corporate_actions_for_symbols(
        self,
        reference: ValidationArtifactReference,
        *,
        symbols: tuple[str, ...],
        after: date,
        through: date,
    ) -> Mapping[str, tuple[HistoricalSecurityFact, ...]]:
        """Return every observed corporate action in one exact T+1 interval."""

        if not symbols or symbols != tuple(sorted(set(symbols))):
            raise ValueError("Historical Security Fact symbols must be ordered")
        if after >= through:
            raise ValueError("Corporate-action interval must advance")
        self._verify_reference(reference)
        with self._factory.connection(read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT symbol, payload_json
                FROM free_data_historical_security_fact
                WHERE owner_id = %s AND owner_hash = %s
                  AND symbol = ANY(%s)
                  AND fact_kind IN ('ADJUSTMENT_EVENT', 'DIVIDEND_EVENT')
                  AND effective_date > %s AND effective_date <= %s
                ORDER BY symbol, effective_date, fact_kind,
                         published_date NULLS FIRST, fact_id
                """,
                (
                    str(reference.artifact_id),
                    reference.content_hash,
                    list(symbols),
                    after,
                    through,
                ),
            ).fetchall()
        grouped: dict[str, list[HistoricalSecurityFact]] = {}
        for row in rows:
            grouped.setdefault(str(row[0]), []).append(self._restore_fact(row[1], reference))
        return {symbol: tuple(items) for symbol, items in grouped.items()}

    def corporate_action_gaps_for_symbols(
        self,
        reference: ValidationArtifactReference,
        *,
        symbols: tuple[str, ...],
        after: date,
        through: date,
    ) -> Mapping[str, tuple[HistoricalSecurityFactCoverageGap, ...]]:
        """Return unresolved corporate-action coverage intersecting T+1."""

        if not symbols or symbols != tuple(sorted(set(symbols))):
            raise ValueError("Historical Security Fact symbols must be ordered")
        if after >= through:
            raise ValueError("Corporate-action interval must advance")
        self._verify_reference(reference)
        with self._factory.connection(read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT symbol, payload_json
                FROM free_data_historical_security_fact_coverage_gap
                WHERE owner_id = %s AND owner_hash = %s
                  AND symbol = ANY(%s)
                  AND coverage_start <= %s AND coverage_end > %s
                ORDER BY symbol, coverage_start, coverage_end, fact_kind, gap_id
                """,
                (
                    str(reference.artifact_id),
                    reference.content_hash,
                    list(symbols),
                    through,
                    after,
                ),
            ).fetchall()
        grouped: dict[str, list[HistoricalSecurityFactCoverageGap]] = {}
        for row in rows:
            payload = row[1]
            if not isinstance(payload, Mapping):
                raise HistoricalSecurityFactsConflict(
                    "Historical Security Fact coverage-gap payload is invalid"
                )
            grouped.setdefault(str(row[0]), []).append(
                HistoricalSecurityFactCoverageGap.from_canonical_dict(payload)
            )
        return {symbol: tuple(items) for symbol, items in grouped.items()}

    def _latest(
        self,
        reference: ValidationArtifactReference,
        *,
        symbol: str,
        fact_kind: HistoricalSecurityFactKind,
        decision_date: date,
        require_publication: bool,
    ) -> HistoricalSecurityFact | None:
        self._verify_reference(reference)
        publication_clause = "AND published_date IS NOT NULL AND published_date <= %s" if require_publication else ""
        parameters: tuple[object, ...] = (
            str(reference.artifact_id),
            reference.content_hash,
            symbol,
            fact_kind.value,
            decision_date,
        )
        if require_publication:
            parameters = (*parameters, decision_date)
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                f"""
                SELECT payload_json
                FROM free_data_historical_security_fact
                WHERE owner_id = %s AND owner_hash = %s AND symbol = %s
                  AND fact_kind = %s AND effective_date <= %s
                  {publication_clause}
                ORDER BY published_date DESC NULLS LAST,
                         effective_date DESC, fact_id DESC
                LIMIT 1
                """,  # noqa: S608 -- clause is selected from two constant literals.
                parameters,
            ).fetchone()
        return None if row is None else self._restore_fact(row[0], reference)

    def _verify_reference(self, reference: ValidationArtifactReference) -> None:
        if reference.artifact_kind != "HISTORICAL_SECURITY_FACTS":
            raise ValueError("Historical Security Facts reference kind mismatch")
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT owner_hash
                FROM free_data_historical_security_fact_set
                WHERE owner_id = %s
                """,
                (str(reference.artifact_id),),
            ).fetchone()
        if row is None:
            raise KeyError(str(reference.artifact_id))
        if str(row[0]) != reference.content_hash:
            raise HistoricalSecurityFactsConflict("Historical Security Facts owner hash diverged")

    @staticmethod
    def _restore_fact(
        payload: object,
        owner_reference: ValidationArtifactReference,
    ) -> HistoricalSecurityFact:
        if not isinstance(payload, Mapping):
            raise HistoricalSecurityFactsConflict("Historical Security Fact payload is invalid")
        fact = HistoricalSecurityFact.from_canonical_dict(payload)
        if owner_reference.artifact_kind != "HISTORICAL_SECURITY_FACTS":
            raise HistoricalSecurityFactsConflict("Historical Security Fact owner reference is invalid")
        return fact

    @staticmethod
    def _verify_projection(
        connection: Any,
        owner: HistoricalSecurityFactsOwner,
    ) -> None:
        row = connection.execute(
            """
            SELECT owner_hash, fact_count, coverage_gap_count, payload_json
            FROM free_data_historical_security_fact_set
            WHERE owner_id = %s
            """,
            (str(owner.owner_id),),
        ).fetchone()
        facts = connection.execute(
            """
            SELECT payload_json
            FROM free_data_historical_security_fact
            WHERE owner_id = %s AND owner_hash = %s
            ORDER BY symbol, effective_date, fact_kind,
                     published_date NULLS FIRST, fact_id
            """,
            (str(owner.owner_id), owner.owner_hash),
        ).fetchall()
        gaps = connection.execute(
            """
            SELECT payload_json
            FROM free_data_historical_security_fact_coverage_gap
            WHERE owner_id = %s AND owner_hash = %s
            ORDER BY symbol, coverage_start, coverage_end, fact_kind, gap_id
            """,
            (str(owner.owner_id), owner.owner_hash),
        ).fetchall()
        if (
            row is None
            or str(row[0]) != owner.owner_hash
            or int(row[1]) != len(owner.facts)
            or int(row[2]) != len(owner.coverage_gaps)
            or not isinstance(row[3], Mapping)
            or dict(row[3]) != owner.to_canonical_dict()
            or tuple(item[0] for item in facts) != tuple(item.to_canonical_dict() for item in owner.facts)
            or tuple(item[0] for item in gaps)
            != tuple(item.to_canonical_dict() for item in owner.coverage_gaps)
        ):
            raise HistoricalSecurityFactsConflict("Historical Security Facts PostgreSQL projection conflict")


__all__ = [
    "HistoricalSecurityFactProjection",
    "HistoricalSecurityFactsConflict",
    "PostgresHistoricalSecurityFactsRepository",
]
