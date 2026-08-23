"""PostgreSQL Authority for exploratory historical Security Facts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from hashlib import sha256
from typing import Any, Mapping
from uuid import uuid4

from psycopg.types.json import Jsonb

from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash, canonical_json
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
        apply_migrations: bool = False,
    ) -> None:
        self._factory = factory
        self._verified_record_sets: set[tuple[ArtifactId, str]] = set()
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
                    acquisition_start_date, acquisition_end_date,
                    requested_symbols, universe_scope_references,
                    payload_json, created_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, false, %s, %s, %s, %s, %s, %s
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
                    owner.acquisition_start_date,
                    owner.acquisition_end_date,
                    (
                        None
                        if not owner.requested_symbols
                        else Jsonb(list(owner.requested_symbols))
                    ),
                    (
                        None
                        if not owner.universe_scope_references
                        else Jsonb(
                            [
                                item.to_canonical_dict()
                                for item in owner.universe_scope_references
                            ]
                        )
                    ),
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
        self._acquisition_scope(reference)
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
        acquisition_start, acquisition_end, acquired_symbols, _references = (
            self._acquisition_scope(reference)
        )
        if (
            after < acquisition_start
            or through > acquisition_end
            or not set(symbols).issubset(acquired_symbols)
        ):
            raise HistoricalSecurityFactsConflict(
                "Corporate-action query is outside acquisition scope"
            )
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

    def verify_acquisition_scope(
        self,
        reference: ValidationArtifactReference,
        *,
        symbols: tuple[str, ...],
        universe_references: tuple[ValidationArtifactReference, ...],
        decision_date: date,
    ) -> None:
        """Require exact v3 symbol and constituent lineage before absence is evidence."""

        acquisition_start, acquisition_end, acquired_symbols, acquired_references = (
            self._acquisition_scope(reference)
        )
        if not acquisition_start <= decision_date <= acquisition_end:
            raise HistoricalSecurityFactsConflict(
                "Historical Security Facts do not cover the Decision date"
            )
        if not set(symbols).issubset(acquired_symbols):
            raise HistoricalSecurityFactsConflict(
                "Historical Security Facts do not cover the active Universe symbols"
            )
        if set(universe_references) != acquired_references:
            raise HistoricalSecurityFactsConflict(
                "Historical Security Facts Universe lineage is incomplete"
            )

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
        (
            acquisition_start,
            acquisition_end,
            acquired_symbols,
            _acquired_references,
        ) = self._acquisition_scope(reference)
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
        outside_interval = after < acquisition_start or through > acquisition_end
        for symbol in symbols:
            if symbol in acquired_symbols and not outside_interval:
                continue
            reason = (
                "CORPORATE_ACTION_SYMBOL_OUTSIDE_ACQUISITION_SCOPE"
                if symbol not in acquired_symbols
                else "CORPORATE_ACTION_INTERVAL_OUTSIDE_ACQUISITION_SCOPE"
            )
            gap = HistoricalSecurityFactCoverageGap.create(
                fact_kind=HistoricalSecurityFactKind.ADJUSTMENT_EVENT,
                symbol=symbol,
                coverage_start=after,
                coverage_end=through,
                raw_row_hash=canonical_hash(
                    {
                        "facts_owner_id": str(reference.artifact_id),
                        "facts_owner_hash": reference.content_hash,
                        "symbol": symbol,
                        "after": after.isoformat(),
                        "through": through.isoformat(),
                        "reason": reason,
                    }
                ),
                source_reference=reference,
                reason_codes=(reason, "RAW_UNADJUSTED_RETURN_FAILS_CLOSED"),
            )
            grouped.setdefault(symbol, []).append(gap)
        return {symbol: tuple(items) for symbol, items in grouped.items()}

    def corporate_action_evidence_for_symbols(
        self,
        reference: ValidationArtifactReference,
        *,
        symbols: tuple[str, ...],
        after: date,
        through: date,
    ) -> tuple[
        Mapping[str, tuple[HistoricalSecurityFact, ...]],
        Mapping[str, tuple[HistoricalSecurityFactCoverageGap, ...]],
    ]:
        """Resolve actions and fail-closed gaps without querying outside scope."""

        gaps = self.corporate_action_gaps_for_symbols(
            reference,
            symbols=symbols,
            after=after,
            through=through,
        )
        outside_scope_symbols = {
            symbol
            for symbol, items in gaps.items()
            if any(
                reason.startswith("CORPORATE_ACTION_SYMBOL_OUTSIDE_")
                or reason.startswith("CORPORATE_ACTION_INTERVAL_OUTSIDE_")
                for item in items
                for reason in item.reason_codes
            )
        }
        action_symbols = tuple(sorted(set(symbols) - outside_scope_symbols))
        actions = (
            {}
            if not action_symbols
            else self.corporate_actions_for_symbols(
                reference,
                symbols=action_symbols,
                after=after,
                through=through,
            )
        )
        return actions, gaps

    def _acquisition_scope(
        self,
        reference: ValidationArtifactReference,
    ) -> tuple[
        date,
        date,
        frozenset[str],
        frozenset[ValidationArtifactReference],
    ]:
        if reference.artifact_kind != "HISTORICAL_SECURITY_FACTS":
            raise ValueError("Historical Security Facts reference kind mismatch")
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT owner_hash, acquisition_start_date,
                       acquisition_end_date, requested_symbols,
                       universe_scope_references,
                       payload_json - 'owner_id' - 'owner_hash'
                                    - 'facts' - 'coverage_gaps'
                FROM free_data_historical_security_fact_set
                WHERE owner_id = %s
                """,
                (str(reference.artifact_id),),
            ).fetchone()
        if row is None:
            raise KeyError(str(reference.artifact_id))
        if str(row[0]) != reference.content_hash:
            raise HistoricalSecurityFactsConflict(
                "Historical Security Facts owner hash diverged"
            )
        if not isinstance(row[5], Mapping) or (
            row[5].get("schema_version")
            != "historical-security-facts-owner/v4"
        ):
            raise HistoricalSecurityFactsConflict(
                "Historical Security Facts owner lacks a bounded v4 identity envelope"
            )
        if canonical_hash(dict(row[5])) != reference.content_hash:
            raise HistoricalSecurityFactsConflict(
                "Historical Security Facts identity envelope diverged"
            )
        self._verify_record_set(reference, dict(row[5]))
        if (
            row[1] is None
            or row[2] is None
            or not isinstance(row[3], list)
            or not row[3]
            or not isinstance(row[4], list)
            or not row[4]
        ):
            raise HistoricalSecurityFactsConflict(
                "Historical Security Facts owner lacks v3 acquisition scope"
            )
        requested_symbols = tuple(str(item) for item in row[3])
        universe_references = tuple(
            ValidationArtifactReference.from_canonical_dict(item)
            for item in row[4]
            if isinstance(item, Mapping)
        )
        if (
            requested_symbols != tuple(sorted(set(requested_symbols)))
            or len(universe_references) != len(row[4])
            or universe_references
            != tuple(sorted(set(universe_references), key=lambda item: (
                item.artifact_kind,
                str(item.artifact_id),
                item.content_hash,
            )))
        ):
            raise HistoricalSecurityFactsConflict(
                "Historical Security Facts acquisition projection is invalid"
            )
        if (
            row[5].get("acquisition_start_date") != row[1].isoformat()
            or row[5].get("acquisition_end_date") != row[2].isoformat()
            or row[5].get("requested_symbols") != list(requested_symbols)
            or row[5].get("universe_scope_references")
            != [item.to_canonical_dict() for item in universe_references]
        ):
            raise HistoricalSecurityFactsConflict(
                "Historical Security Facts acquisition identity diverged"
            )
        return (
            row[1],
            row[2],
            frozenset(requested_symbols),
            frozenset(universe_references),
        )

    def _verify_record_set(
        self,
        reference: ValidationArtifactReference,
        identity_envelope: Mapping[str, Any],
    ) -> None:
        """Verify the bounded query projection once against its owner digests."""

        cache_key = (reference.artifact_id, reference.content_hash)
        if cache_key in self._verified_record_sets:
            return
        expected_fact_count = identity_envelope.get("fact_count")
        expected_gap_count = identity_envelope.get("coverage_gap_count")
        expected_fact_hash = identity_envelope.get("facts_hash")
        expected_gap_hash = identity_envelope.get("coverage_gaps_hash")
        if (
            isinstance(expected_fact_count, bool)
            or not isinstance(expected_fact_count, int)
            or expected_fact_count <= 0
            or isinstance(expected_gap_count, bool)
            or not isinstance(expected_gap_count, int)
            or expected_gap_count < 0
            or not isinstance(expected_fact_hash, str)
            or not isinstance(expected_gap_hash, str)
        ):
            raise HistoricalSecurityFactsConflict(
                "Historical Security Facts record-set digest is invalid"
            )
        with self._factory.connection(read_only=True) as connection:
            fact_count, fact_hash = _stream_projection_digest(
                connection,
                """
                SELECT payload_json
                FROM free_data_historical_security_fact
                WHERE owner_id = %s AND owner_hash = %s
                ORDER BY symbol, effective_date, fact_kind,
                         published_date NULLS FIRST, fact_id
                """,
                reference,
            )
            gap_count, gap_hash = _stream_projection_digest(
                connection,
                """
                SELECT payload_json
                FROM free_data_historical_security_fact_coverage_gap
                WHERE owner_id = %s AND owner_hash = %s
                ORDER BY symbol, coverage_start, coverage_end, fact_kind, gap_id
                """,
                reference,
            )
        if (
            fact_count != expected_fact_count
            or fact_hash != expected_fact_hash
            or gap_count != expected_gap_count
            or gap_hash != expected_gap_hash
        ):
            raise HistoricalSecurityFactsConflict(
                "Historical Security Facts bounded projection digest diverged"
            )
        self._verified_record_sets.add(cache_key)

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
            SELECT owner_hash, fact_count, coverage_gap_count, payload_json,
                   acquisition_start_date, acquisition_end_date,
                   requested_symbols, universe_scope_references
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
            or row[4] != owner.acquisition_start_date
            or row[5] != owner.acquisition_end_date
            or row[6]
            != (
                None
                if not owner.requested_symbols
                else list(owner.requested_symbols)
            )
            or row[7]
            != (
                None
                if not owner.universe_scope_references
                else [
                    item.to_canonical_dict()
                    for item in owner.universe_scope_references
                ]
            )
            or tuple(item[0] for item in facts) != tuple(item.to_canonical_dict() for item in owner.facts)
            or tuple(item[0] for item in gaps)
            != tuple(item.to_canonical_dict() for item in owner.coverage_gaps)
        ):
            raise HistoricalSecurityFactsConflict("Historical Security Facts PostgreSQL projection conflict")


def _stream_projection_digest(
    connection: Any,
    query: str,
    reference: ValidationArtifactReference,
) -> tuple[int, str]:
    """Hash an ordered JSON projection without retaining its object graph."""

    digest = sha256()
    digest.update(b"[")
    count = 0
    with connection.cursor(
        name=f"historical_fact_digest_{uuid4().hex}"
    ) as cursor:
        cursor.itersize = 512
        cursor.execute(
            query,
            (str(reference.artifact_id), reference.content_hash),
        )
        while batch := cursor.fetchmany(512):
            for row in batch:
                if not isinstance(row[0], Mapping):
                    raise HistoricalSecurityFactsConflict(
                        "Historical Security Facts child payload is invalid"
                    )
                if count:
                    digest.update(b",")
                digest.update(canonical_json(dict(row[0])).encode("utf-8"))
                count += 1
    digest.update(b"]")
    return count, f"sha256:{digest.hexdigest()}"


__all__ = [
    "HistoricalSecurityFactProjection",
    "HistoricalSecurityFactsConflict",
    "PostgresHistoricalSecurityFactsRepository",
]
