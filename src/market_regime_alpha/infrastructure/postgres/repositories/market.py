"""PostgreSQL write owner for the target Market/PIT bounded context."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Any
from uuid import UUID

import psycopg

from market_regime_alpha.market.domain import (
    ClassificationMembershipRevision,
    ClassificationRevision,
    CorporateActionRevision,
    GapFactKind,
    Instrument,
    InstrumentFactKind,
    InstrumentLifecycleFactRevision,
    InstrumentFactRevision,
    InstrumentIdentifier,
    MarketBarRevision,
    MarketFactKind,
    NormalizationBatch,
    Provider,
    ProviderCapture,
    ProviderProduct,
    SecurityStatusFactRevision,
    SourceGap,
    TemporalEnvelope,
    TradingSession,
)
from market_regime_alpha.market.ports import CaptureSource
from market_regime_alpha.runtime.errors import (
    ArtifactIntegrityError,
    RuntimeNotFoundError,
    RuntimeStateConflictError,
)
from market_regime_alpha.runtime.ports import ArtifactRecord, PublishedArtifact
from market_regime_alpha.shared.financial import Money
from market_regime_alpha.shared.identity import ContentHash
from market_regime_alpha.shared.time import DecisionTime


class PostgresMarketRepository:
    """Aggregate writes only; transaction ownership belongs to MarketUnitOfWork."""

    def __init__(self, connection: psycopg.Connection[Any]) -> None:
        self._connection = connection

    def register_provider(self, provider: Provider) -> int:
        self._connection.execute(
            """
            INSERT INTO mra.provider (
                provider_id, provider_code, display_name, provider_kind
            )
            VALUES (%s, %s, %s, %s)
            """,
            (
                provider.provider_id,
                provider.provider_code,
                provider.display_name,
                provider.provider_kind.value,
            ),
        )
        return 1

    def register_provider_product(self, product: ProviderProduct) -> int:
        self._validate_product_predecessor(product)
        self._connection.execute(
            """
            INSERT INTO mra.provider_product (
                provider_product_id, provider_id, product_code, revision,
                payload_family, media_type, payload_encoding,
                fact_kinds, instrument_fact_kinds, bar_timeframes,
                price_bases,
                decision_visibility_policy, source_availability_policy,
                supersedes_provider_product_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    'KNOWN_AT', %s, %s)
            """,
            (
                product.provider_product_id,
                product.provider_id,
                product.product_code,
                product.revision,
                product.payload_family,
                product.media_type,
                product.payload_encoding,
                [item.value for item in product.fact_kinds],
                [item.value for item in product.instrument_fact_kinds],
                [item.value for item in product.bar_timeframes],
                [item.value for item in product.price_bases],
                product.source_availability_policy.value,
                product.supersedes_provider_product_id,
            ),
        )
        return product.revision

    def record_capture(
        self,
        capture: ProviderCapture,
        published: PublishedArtifact | None,
    ) -> ProviderCapture:
        product = self._connection.execute(
            """
            SELECT media_type, payload_encoding, source_availability_policy
            FROM mra.provider_product
            WHERE provider_product_id = %s
            FOR SHARE
            """,
            (capture.provider_product_id,),
        ).fetchone()
        if product is None:
            raise RuntimeNotFoundError(
                f"ProviderProduct {capture.provider_product_id} does not exist"
            )
        if (
            capture.status.value == "CAPTURED"
            and str(product[2]) != capture.temporal.source_availability_status.value
        ):
            raise RuntimeStateConflictError(
                "Capture availability semantics differ from ProviderProduct contract"
            )
        if published is not None:
            if capture.artifact_id is None:
                raise ArtifactIntegrityError("captured bytes have no Artifact identity")
            if (str(product[0]), str(product[1])) != (
                published.media_type,
                capture.payload_encoding,
            ):
                raise ArtifactIntegrityError(
                    "captured payload media type or encoding differs from ProviderProduct"
                )
            artifact = self._connection.execute(
                """
                SELECT content_sha256, size_bytes, media_type, locator, integrity_state
                FROM mra.artifact
                WHERE artifact_id = %s
                FOR SHARE
                """,
                (capture.artifact_id,),
            ).fetchone()
            if artifact != (
                published.content_sha256,
                published.size_bytes,
                published.media_type,
                published.locator,
                "AVAILABLE",
            ):
                raise ArtifactIntegrityError(
                    "Capture Artifact is not the exact verified published object"
                )
        temporal = self._connection.execute(
            """
            WITH database_clock AS (
                SELECT clock_timestamp() AS recorded_at
            ), canonical_time AS (
                SELECT recorded_at,
                       GREATEST(%s::timestamptz, recorded_at) AS known_at
                FROM database_clock
            )
            INSERT INTO mra.data_capture (
                capture_id, provider_product_id, capture_key, request_hash,
                artifact_id, status, provider_time,
                source_availability_status, source_available_at,
                capture_started_at, capture_completed_at, recorded_at, known_at,
                decision_visible_at, error_code, limitation_code,
                payload_encoding
            )
            SELECT %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                   canonical_time.recorded_at, canonical_time.known_at,
                   canonical_time.known_at, %s, %s, %s
            FROM canonical_time
            RETURNING recorded_at, known_at, decision_visible_at
            """,
            (
                capture.temporal.capture_completed_at,
                capture.capture_id,
                capture.provider_product_id,
                capture.capture_key,
                capture.request_hash.value,
                capture.artifact_id,
                capture.status.value,
                capture.temporal.provider_time,
                capture.temporal.source_availability_status.value,
                capture.temporal.source_available_at,
                capture.temporal.capture_started_at,
                capture.temporal.capture_completed_at,
                capture.error_code,
                capture.limitation_code,
                capture.payload_encoding,
            ),
        ).fetchone()
        if temporal is None:
            raise AssertionError("Capture insert must return its canonical times")
        return replace(
            capture,
            temporal=TemporalEnvelope(
                provider_time=capture.temporal.provider_time,
                source_availability_status=capture.temporal.source_availability_status,
                source_available_at=capture.temporal.source_available_at,
                capture_started_at=capture.temporal.capture_started_at,
                capture_completed_at=capture.temporal.capture_completed_at,
                known_at=temporal[1],
                decision_visible_at=temporal[2],
            ),
        )

    def record_capture_failure(
        self,
        capture: ProviderCapture,
        gap: SourceGap,
    ) -> tuple[ProviderCapture, DecisionTime]:
        canonical = self.record_capture(capture, None)
        if gap.capture_id != canonical.capture_id:
            raise RuntimeStateConflictError("Capture failure Gap has different Capture")
        if gap.provider_product_id != canonical.provider_product_id:
            raise RuntimeStateConflictError(
                "Capture failure Gap has different ProviderProduct"
            )
        self._validate_product_capabilities(
            NormalizationBatch(
                source_capture_id=canonical.capture_id,
                source_provider_product_id=canonical.provider_product_id,
                gaps=(gap,),
            )
        )
        # The capture-level failure Gap is part of this same command, not a
        # later normalization. It therefore becomes visible with the canonical
        # Capture rather than acquiring a second, slightly later Known Time.
        recorded_at = canonical.temporal.known_at.value
        known_at = canonical.temporal.known_at.value
        self._insert_source_gap(gap, recorded_at=recorded_at, known_at=known_at)
        return canonical, DecisionTime(known_at)

    def insert_normalization(
        self,
        batch: NormalizationBatch,
        *,
        expected_artifact_sha256: ContentHash,
        expected_artifact_size: int,
    ) -> DecisionTime:
        """Bind one Capture-owned normalization aggregate in the active transaction."""

        source = self.lock_capture_source(batch.source_capture_id)
        if batch.source_provider_product_id != source.capture.provider_product_id:
            raise RuntimeStateConflictError(
                "Normalization ProviderProduct differs from its Capture"
            )
        if (
            source.artifact is None
            or source.artifact.content_sha256 != expected_artifact_sha256.value
            or source.artifact.size_bytes != expected_artifact_size
        ):
            raise ArtifactIntegrityError("Capture source changed during normalization")
        self._validate_product_capabilities(batch)
        classification_lineage = self._lock_normalization_roots(batch)
        recorded_at, known_at = self._normalization_times(source.capture)
        for instrument in sorted(
            batch.instruments,
            key=lambda item: (item.canonical_code, str(item.instrument_id)),
        ):
            self._insert_instrument(instrument, recorded_at=recorded_at, known_at=known_at)
        for identifier in sorted(
            batch.instrument_identifiers,
            key=lambda item: (
                item.identifier_scheme,
                item.effective_from,
                item.revision,
                item.identifier_value,
                str(item.instrument_id),
            ),
        ):
            self._insert_instrument_identifier(
                identifier, recorded_at=recorded_at, known_at=known_at
            )
        for session in sorted(
            batch.trading_sessions,
            key=lambda item: (item.exchange, item.session_date, str(item.session_id)),
        ):
            self._insert_trading_session(session, recorded_at=recorded_at, known_at=known_at)
        for classification in sorted(
            batch.classifications,
            key=lambda item: (
                item.classification_scheme,
                item.classification_code,
                item.effective_from,
                item.revision,
            ),
        ):
            self._insert_classification(
                classification, recorded_at=recorded_at, known_at=known_at
            )
        for membership in sorted(
            batch.classification_memberships,
            key=lambda item: (
                *classification_lineage[item.classification_id],
                str(item.instrument_id),
                item.effective_from,
                item.revision,
            ),
        ):
            self._insert_classification_membership(
                membership, recorded_at=recorded_at, known_at=known_at
            )
        for bar in sorted(
            batch.bars,
            key=lambda item: (
                str(item.instrument_id),
                str(item.session_id),
                item.timeframe.value,
                item.price_basis.value,
                item.event_start,
                item.revision,
            ),
        ):
            if bar.event_end > known_at:
                raise RuntimeStateConflictError(
                    "MarketBar cannot become known before its event interval ends"
                )
            self._insert_bar_revision(bar, recorded_at=recorded_at, known_at=known_at)
        for instrument_fact in sorted(
            batch.instrument_facts,
            key=lambda item: (
                str(item.instrument_id),
                item.fact_kind.value,
                item.event_start,
                item.revision,
            ),
        ):
            self._insert_instrument_fact_revision(
                instrument_fact, recorded_at=recorded_at, known_at=known_at
            )
        for security_fact in sorted(
            batch.security_status_facts,
            key=lambda item: (
                str(item.instrument_id),
                str(item.session_id),
                item.evidence_scope.value,
                item.revision,
            ),
        ):
            self._insert_security_status_revision(
                security_fact, recorded_at=recorded_at, known_at=known_at
            )
        for lifecycle_fact in sorted(
            batch.lifecycle_status_facts,
            key=lambda item: (
                str(item.instrument_id),
                item.fact_kind.value,
                item.effective_from,
                item.revision,
            ),
        ):
            self._insert_lifecycle_status_revision(
                lifecycle_fact,
                recorded_at=recorded_at,
                known_at=known_at,
            )
        for action in sorted(
            batch.corporate_actions,
            key=lambda item: (
                str(item.instrument_id),
                item.action_key,
                item.revision,
            ),
        ):
            self._insert_corporate_action(
                action, recorded_at=recorded_at, known_at=known_at
            )
        for gap in sorted(
            batch.gaps,
            key=lambda item: (
                item.fact_kind.value,
                str(item.instrument_id) if item.instrument_id is not None else "",
                str(item.session_id) if item.session_id is not None else "",
                item.event_start or datetime.min.replace(tzinfo=recorded_at.tzinfo),
                str(item.gap_id),
            ),
        ):
            if (
                gap.fact_kind is GapFactKind.MARKET_BAR
                and gap.event_end is not None
                and gap.event_end > known_at
            ):
                raise RuntimeStateConflictError(
                    "MarketBar SourceGap cannot become known before its expected interval ends"
                )
            self._insert_source_gap(gap, recorded_at=recorded_at, known_at=known_at)
        return DecisionTime(known_at)

    def _lock_normalization_roots(
        self,
        batch: NormalizationBatch,
    ) -> dict[UUID, tuple[str, str]]:
        """Acquire every multi-root advisory lock in one deterministic order."""

        classification_lineage = {
            item.classification_id: (
                item.classification_scheme,
                item.classification_code,
            )
            for item in batch.classifications
        }
        unresolved_ids = {
            item.classification_id
            for item in batch.classification_memberships
            if item.classification_id not in classification_lineage
        }
        if unresolved_ids:
            rows = self._connection.execute(
                """
                SELECT classification_id, classification_scheme, classification_code
                FROM mra.classification
                WHERE classification_id = ANY(%s)
                """,
                (list(unresolved_ids),),
            ).fetchall()
            classification_lineage.update(
                {
                    UUID(str(row[0])): (str(row[1]), str(row[2]))
                    for row in rows
                }
            )
        if any(
            item.classification_id not in classification_lineage
            for item in batch.classification_memberships
        ):
            raise RuntimeNotFoundError(
                "ClassificationMembership references an unknown Classification"
            )

        lock_keys = {
            f"mra:instrument-identifier:{item.identifier_scheme}"
            for item in batch.instrument_identifiers
        }
        lock_keys.update(
            f"mra:classification:{item.classification_scheme}:{item.classification_code}"
            for item in batch.classifications
        )
        lock_keys.update(
            "mra:classification-membership:"
            f"{classification_lineage[item.classification_id][0]}:"
            f"{classification_lineage[item.classification_id][1]}:"
            f"{item.instrument_id}"
            for item in batch.classification_memberships
        )
        lock_keys.update(
            "mra:instrument-fact-timeline:"
            f"{batch.source_provider_product_id}:{item.instrument_id}:"
            f"{item.fact_kind.value}"
            for item in batch.instrument_facts
            if item.evidence_scope.value == "EFFECTIVE_INTERVAL"
        )
        lock_keys.update(
            "mra:instrument-fact-timeline:"
            f"{batch.source_provider_product_id}:{item.instrument_id}:"
            f"{item.fact_kind.value}"
            for item in batch.lifecycle_status_facts
        )
        for lock_key in sorted(lock_keys):
            self._connection.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (lock_key,),
            )
        return classification_lineage

    def get_capture(self, capture_id: UUID) -> ProviderCapture:
        return self.capture_source(capture_id, lock=False).capture

    def normalization_decision_visible_at(self, capture_id: UUID) -> DecisionTime:
        row = self._connection.execute(
            """
            SELECT min(decision_visible_at), max(decision_visible_at), count(*)
            FROM (
                SELECT decision_visible_at FROM mra.instrument
                WHERE source_capture_id = %(capture_id)s
                UNION ALL
                SELECT decision_visible_at FROM mra.instrument_identifier
                WHERE source_capture_id = %(capture_id)s
                UNION ALL
                SELECT decision_visible_at FROM mra.trading_session
                WHERE source_capture_id = %(capture_id)s
                UNION ALL
                SELECT decision_visible_at FROM mra.classification
                WHERE source_capture_id = %(capture_id)s
                UNION ALL
                SELECT decision_visible_at
                FROM mra.classification_membership_revision
                WHERE source_capture_id = %(capture_id)s
                UNION ALL
                SELECT decision_visible_at FROM mra.market_bar_revision
                WHERE capture_id = %(capture_id)s
                UNION ALL
                SELECT decision_visible_at FROM mra.instrument_fact_revision
                WHERE capture_id = %(capture_id)s
                UNION ALL
                SELECT decision_visible_at FROM mra.corporate_action_revision
                WHERE capture_id = %(capture_id)s
                UNION ALL
                SELECT decision_visible_at FROM mra.source_gap
                WHERE capture_id = %(capture_id)s
            ) AS normalized
            """,
            {"capture_id": capture_id},
        ).fetchone()
        if row is None or int(row[2]) == 0:
            raise RuntimeNotFoundError(
                f"Capture {capture_id} has no committed normalization evidence"
            )
        if row[0] != row[1]:
            raise RuntimeStateConflictError(
                f"Capture {capture_id} normalization has inconsistent visibility"
            )
        return DecisionTime(row[0])

    def capture_source(self, capture_id: UUID, *, lock: bool = False) -> CaptureSource:
        suffix = " FOR UPDATE OF capture" if lock else ""
        row = self._connection.execute(
            """
            SELECT
                capture.capture_id, capture.provider_product_id,
                capture.capture_key, capture.request_hash, capture.status,
                capture.provider_time, capture.source_availability_status,
                capture.source_available_at, capture.capture_started_at,
                capture.capture_completed_at, capture.known_at,
                capture.decision_visible_at, capture.artifact_id,
                capture.error_code, capture.limitation_code,
                capture.payload_encoding,
                artifact.content_sha256, artifact.size_bytes,
                artifact.media_type, artifact.locator,
                artifact.integrity_state, artifact.retention_until,
                artifact.pin_reason_code
            FROM mra.data_capture AS capture
            LEFT JOIN mra.artifact AS artifact
              ON artifact.artifact_id = capture.artifact_id
            WHERE capture.capture_id = %s
            """
            + suffix,
            (capture_id,),
        ).fetchone()
        if row is None:
            raise RuntimeNotFoundError(f"Capture {capture_id} does not exist")
        return _capture_source(row)

    def lock_capture_source(self, capture_id: UUID) -> CaptureSource:
        # Capture is the first Market aggregate root. The transaction-scoped
        # advisory lock is shared with the DB bar/gap guard, so owner writes and
        # direct constraint checks serialize on the same identity.
        self._connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"mra:capture-normalization:{capture_id}",),
        )
        source = self.capture_source(capture_id, lock=True)
        if source.artifact is None or source.artifact.integrity_state != "AVAILABLE":
            raise ArtifactIntegrityError("Capture source Artifact is not AVAILABLE")
        locked_artifact = self._connection.execute(
            """
            SELECT content_sha256, size_bytes, integrity_state
            FROM mra.artifact
            WHERE artifact_id = %s
            FOR SHARE
            """,
            (source.artifact.artifact_id,),
        ).fetchone()
        if locked_artifact != (
            source.artifact.content_sha256,
            source.artifact.size_bytes,
            "AVAILABLE",
        ):
            raise ArtifactIntegrityError("Capture source Artifact changed before binding")
        return source

    def _insert_instrument(
        self,
        instrument: Instrument,
        *,
        recorded_at: datetime,
        known_at: datetime,
    ) -> None:
        self._connection.execute(
            """
            INSERT INTO mra.instrument (
                instrument_id, canonical_code, exchange, instrument_type,
                currency, source_capture_id, recorded_at, known_at,
                decision_visible_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                instrument.instrument_id.value,
                instrument.canonical_code,
                instrument.exchange,
                instrument.instrument_type.value,
                instrument.currency,
                instrument.source_capture_id,
                recorded_at,
                known_at,
                known_at,
            ),
        )

    def _insert_instrument_identifier(
        self,
        identifier: InstrumentIdentifier,
        *,
        recorded_at: datetime,
        known_at: datetime,
    ) -> None:
        self._validate_identifier_predecessor(identifier)
        self._connection.execute(
            """
            INSERT INTO mra.instrument_identifier (
                instrument_identifier_id, instrument_id, identifier_scheme,
                identifier_value, effective_from, effective_to, revision,
                supersedes_identifier_id, source_capture_id, recorded_at,
                known_at, decision_visible_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                identifier.instrument_identifier_id,
                identifier.instrument_id.value,
                identifier.identifier_scheme,
                identifier.identifier_value,
                identifier.effective_from,
                identifier.effective_to,
                identifier.revision,
                identifier.supersedes_identifier_id,
                identifier.source_capture_id,
                recorded_at,
                known_at,
                known_at,
            ),
        )

    def _insert_trading_session(
        self,
        session: TradingSession,
        *,
        recorded_at: datetime,
        known_at: datetime,
    ) -> None:
        self._connection.execute(
            """
            INSERT INTO mra.trading_session (
                session_id, exchange, session_date, timezone_name, open_at,
                break_start_at, break_end_at, close_at,
                decision_reference_at, source_capture_id, recorded_at,
                known_at, decision_visible_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                session.session_id.value,
                session.exchange,
                session.session_date,
                session.timezone_name,
                session.open_at,
                session.break_start_at,
                session.break_end_at,
                session.close_at,
                session.decision_reference_at,
                session.source_capture_id,
                recorded_at,
                known_at,
                known_at,
            ),
        )

    def _insert_classification(
        self,
        item: ClassificationRevision,
        *,
        recorded_at: datetime,
        known_at: datetime,
    ) -> None:
        self._validate_classification_predecessor(item)
        self._connection.execute(
            """
            INSERT INTO mra.classification (
                classification_id, classification_scheme,
                classification_code, display_name, revision,
                effective_from, effective_to,
                supersedes_classification_id, source_capture_id, recorded_at,
                known_at, decision_visible_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                item.classification_id,
                item.classification_scheme,
                item.classification_code,
                item.display_name,
                item.revision,
                item.effective_from,
                item.effective_to,
                item.supersedes_classification_id,
                item.source_capture_id,
                recorded_at,
                known_at,
                known_at,
            ),
        )

    def _insert_classification_membership(
        self,
        item: ClassificationMembershipRevision,
        *,
        recorded_at: datetime,
        known_at: datetime,
    ) -> None:
        self._validate_membership_predecessor(item)
        self._connection.execute(
            """
            INSERT INTO mra.classification_membership_revision (
                membership_revision_id, classification_id, instrument_id,
                source_capture_id, membership_status, effective_from,
                effective_to, revision, supersedes_membership_revision_id,
                recorded_at, known_at, decision_visible_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                item.membership_revision_id,
                item.classification_id,
                item.instrument_id.value,
                item.source_capture_id,
                item.membership_status.value,
                item.effective_from,
                item.effective_to,
                item.revision,
                item.supersedes_membership_revision_id,
                recorded_at,
                known_at,
                known_at,
            ),
        )

    def _insert_bar_revision(
        self,
        bar: MarketBarRevision,
        *,
        recorded_at: datetime,
        known_at: datetime,
    ) -> None:
        instrument_currency_row = self._connection.execute(
            """
            SELECT instrument.currency
            FROM mra.instrument AS instrument
            JOIN mra.data_capture AS capture
              ON capture.capture_id = instrument.source_capture_id
            JOIN mra.artifact AS artifact
              ON artifact.artifact_id = capture.artifact_id
            JOIN mra.trading_session AS session ON session.session_id = %s
            JOIN mra.data_capture AS session_capture
              ON session_capture.capture_id = session.source_capture_id
            JOIN mra.artifact AS session_artifact
              ON session_artifact.artifact_id = session_capture.artifact_id
            WHERE instrument.instrument_id = %s
              AND capture.status = 'CAPTURED'
              AND artifact.integrity_state = 'AVAILABLE'
              AND session_capture.status = 'CAPTURED'
              AND session_artifact.integrity_state = 'AVAILABLE'
            FOR SHARE OF instrument, session
            """,
            (bar.session_id.value, bar.instrument_id.value),
        ).fetchone()
        if instrument_currency_row is None:
            raise RuntimeNotFoundError(
                f"Instrument {bar.instrument_id} does not exist"
            )
        if str(instrument_currency_row[0]) != bar.open.currency:
            raise RuntimeStateConflictError(
                "MarketBar money currency differs from canonical Instrument"
            )
        self._validate_bar_predecessor(bar)
        self._connection.execute(
            """
            INSERT INTO mra.market_bar_revision (
                bar_revision_id, provider_product_id, capture_id,
                instrument_id, session_id, timeframe, price_basis,
                event_start, event_end, revision, supersedes_revision_id,
                open_value, high_value, low_value, close_value,
                volume_value, turnover_value, recorded_at, known_at,
                decision_visible_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                bar.bar_revision_id,
                bar.provider_product_id,
                bar.capture_id,
                bar.instrument_id.value,
                bar.session_id.value,
                bar.timeframe.value,
                bar.price_basis.value,
                bar.event_start,
                bar.event_end,
                bar.revision,
                bar.supersedes_revision_id,
                bar.open.amount,
                bar.high.amount,
                bar.low.amount,
                bar.close.amount,
                bar.volume.amount,
                bar.turnover.amount if bar.turnover is not None else None,
                recorded_at,
                known_at,
                known_at,
            ),
        )

    def _insert_security_status_revision(
        self,
        fact: SecurityStatusFactRevision,
        *,
        recorded_at: datetime,
        known_at: datetime,
    ) -> None:
        self._validate_fact_predecessor(fact)
        self._connection.execute(
            """
            INSERT INTO mra.instrument_fact_revision (
                fact_revision_id, provider_product_id, capture_id,
                instrument_id, session_id, fact_kind, evidence_scope,
                event_start, event_end, value_kind, status_value,
                revision, supersedes_revision_id, recorded_at, known_at,
                decision_visible_at
            )
            VALUES (%s, %s, %s, %s, %s, 'SECURITY_STATUS', %s,
                    %s, %s, 'STATUS', %s, %s, %s, %s, %s, %s)
            """,
            (
                fact.fact_revision_id,
                fact.provider_product_id,
                fact.capture_id,
                fact.instrument_id.value,
                fact.session_id.value,
                fact.evidence_scope.value,
                fact.event_start,
                fact.event_end,
                fact.status.value,
                fact.revision,
                fact.supersedes_revision_id,
                recorded_at,
                known_at,
                known_at,
            ),
        )

    def _insert_instrument_fact_revision(
        self,
        fact: InstrumentFactRevision,
        *,
        recorded_at: datetime,
        known_at: datetime,
    ) -> None:
        if isinstance(fact.value, Money):
            instrument_currency = self._connection.execute(
                "SELECT currency FROM mra.instrument WHERE instrument_id = %s FOR SHARE",
                (fact.instrument_id.value,),
            ).fetchone()
            if instrument_currency is None:
                raise RuntimeNotFoundError(
                    f"Instrument {fact.instrument_id} does not exist"
                )
            if str(instrument_currency[0]) != fact.value.currency:
                raise RuntimeStateConflictError(
                    "InstrumentFact Money currency differs from canonical Instrument"
                )
        self._validate_generic_fact_predecessor(fact)
        self._connection.execute(
            """
            INSERT INTO mra.instrument_fact_revision (
                fact_revision_id, provider_product_id, capture_id,
                instrument_id, session_id, fact_kind, evidence_scope,
                event_start, event_end, value_kind, numeric_value, unit_code,
                revision, supersedes_revision_id, recorded_at, known_at,
                decision_visible_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'DECIMAL',
                    %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                fact.fact_revision_id,
                fact.provider_product_id,
                fact.capture_id,
                fact.instrument_id.value,
                fact.session_id.value if fact.session_id is not None else None,
                fact.fact_kind.value,
                fact.evidence_scope.value,
                fact.event_start,
                fact.event_end,
                fact.numeric_value,
                fact.unit_code,
                fact.revision,
                fact.supersedes_revision_id,
                recorded_at,
                known_at,
                known_at,
            ),
        )

    def _insert_lifecycle_status_revision(
        self,
        fact: InstrumentLifecycleFactRevision,
        *,
        recorded_at: datetime,
        known_at: datetime,
    ) -> None:
        self._validate_generic_fact_predecessor(fact)
        self._connection.execute(
            """
            INSERT INTO mra.instrument_fact_revision (
                fact_revision_id, provider_product_id, capture_id,
                instrument_id, session_id, fact_kind, evidence_scope,
                event_start, event_end, value_kind, status_value,
                revision, supersedes_revision_id, recorded_at, known_at,
                decision_visible_at
            )
            VALUES (%s, %s, %s, %s, NULL, %s, 'EFFECTIVE_INTERVAL',
                    %s, %s, 'STATUS', %s, %s, %s, %s, %s, %s)
            """,
            (
                fact.fact_revision_id,
                fact.provider_product_id,
                fact.capture_id,
                fact.instrument_id.value,
                fact.fact_kind.value,
                fact.effective_from,
                fact.effective_to,
                fact.status.value,
                fact.revision,
                fact.supersedes_revision_id,
                recorded_at,
                known_at,
                known_at,
            ),
        )

    def _insert_corporate_action(
        self,
        action: CorporateActionRevision,
        *,
        recorded_at: datetime,
        known_at: datetime,
    ) -> None:
        instrument_currency_row = self._connection.execute(
            """
            SELECT currency
            FROM mra.instrument
            WHERE instrument_id = %s
            FOR SHARE
            """,
            (action.instrument_id.value,),
        ).fetchone()
        if instrument_currency_row is None:
            raise RuntimeNotFoundError(
                f"Instrument {action.instrument_id} does not exist"
            )
        if (
            action.currency is not None
            and str(instrument_currency_row[0]) != action.currency
        ):
            raise RuntimeStateConflictError(
                "CorporateAction money currency differs from canonical Instrument"
            )
        self._validate_action_predecessor(action)
        self._connection.execute(
            """
            INSERT INTO mra.corporate_action_revision (
                corporate_action_revision_id, provider_product_id, capture_id,
                instrument_id, action_key, action_type, ex_session_id,
                record_session_id, pay_session_id, successor_instrument_id,
                cash_amount_per_share,
                ratio_factor, subscription_price, currency, revision,
                supersedes_revision_id, recorded_at, known_at,
                decision_visible_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s)
            """,
            (
                action.corporate_action_revision_id,
                action.provider_product_id,
                action.capture_id,
                action.instrument_id.value,
                action.action_key,
                action.action_type.value,
                action.ex_session_id.value,
                action.record_session_id.value
                if action.record_session_id is not None
                else None,
                action.pay_session_id.value
                if action.pay_session_id is not None
                else None,
                action.successor_instrument_id.value
                if action.successor_instrument_id is not None
                else None,
                action.cash_amount_per_share.amount
                if action.cash_amount_per_share is not None
                else None,
                action.ratio_factor,
                action.subscription_price.amount
                if action.subscription_price is not None
                else None,
                action.currency,
                action.revision,
                action.supersedes_revision_id,
                recorded_at,
                known_at,
                known_at,
            ),
        )

    def _insert_source_gap(
        self,
        gap: SourceGap,
        *,
        recorded_at: datetime,
        known_at: datetime,
    ) -> None:
        self._connection.execute(
            """
            INSERT INTO mra.source_gap (
                gap_id, provider_product_id, capture_id, instrument_id,
                session_id, instrument_code, identifier_scheme,
                identifier_value, exchange, session_date,
                classification_scheme, classification_code, action_key,
                gap_kind, reason_code, fact_kind, timeframe,
                instrument_fact_kind, evidence_scope, price_basis,
                event_start, event_end, effective_from, effective_to,
                detail, recorded_at, known_at, decision_visible_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s)
            """,
            (
                gap.gap_id,
                gap.provider_product_id,
                gap.capture_id,
                gap.instrument_id.value if gap.instrument_id is not None else None,
                gap.session_id.value if gap.session_id is not None else None,
                gap.instrument_code,
                gap.identifier_scheme,
                gap.identifier_value,
                gap.exchange,
                gap.session_date,
                gap.classification_scheme,
                gap.classification_code,
                gap.action_key,
                gap.gap_kind.value,
                gap.reason_code.value,
                gap.fact_kind.value,
                gap.timeframe.value if gap.timeframe is not None else None,
                gap.instrument_fact_kind.value
                if gap.instrument_fact_kind is not None
                else None,
                gap.evidence_scope.value if gap.evidence_scope is not None else None,
                gap.price_basis.value if gap.price_basis is not None else None,
                gap.event_start,
                gap.event_end,
                gap.effective_from,
                gap.effective_to,
                gap.detail,
                recorded_at,
                known_at,
                known_at,
            ),
        )

    def _normalization_times(
        self,
        capture: ProviderCapture,
    ) -> tuple[datetime, datetime]:
        row = self._connection.execute("SELECT clock_timestamp()").fetchone()
        if row is None:
            raise AssertionError("PostgreSQL normalization clock must return one row")
        recorded_at = row[0]
        return recorded_at, max(capture.temporal.capture_completed_at, recorded_at)

    def _validate_product_capabilities(self, batch: NormalizationBatch) -> None:
        row = self._connection.execute(
            """
            SELECT fact_kinds, instrument_fact_kinds, bar_timeframes,
                   price_bases
            FROM mra.provider_product
            WHERE provider_product_id = %s
            FOR SHARE
            """,
            (batch.source_provider_product_id,),
        ).fetchone()
        if row is None:
            raise RuntimeNotFoundError(
                f"ProviderProduct {batch.source_provider_product_id} does not exist"
            )
        allowed_kinds = frozenset(MarketFactKind(str(item)) for item in row[0])
        if not batch.required_fact_kinds <= allowed_kinds:
            missing = sorted(
                item.value for item in batch.required_fact_kinds - allowed_kinds
            )
            raise RuntimeStateConflictError(
                f"Normalization exceeds ProviderProduct fact capabilities: {missing}"
            )
        allowed_instrument_fact_kinds = frozenset(
            InstrumentFactKind(str(item)) for item in row[1]
        )
        if not batch.required_instrument_fact_kinds <= allowed_instrument_fact_kinds:
            missing = sorted(
                item.value
                for item in (
                    batch.required_instrument_fact_kinds
                    - allowed_instrument_fact_kinds
                )
            )
            raise RuntimeStateConflictError(
                "Normalization exceeds ProviderProduct instrument-fact "
                f"capabilities: {missing}"
            )
        allowed_timeframes = frozenset(str(item) for item in row[2])
        allowed_bases = frozenset(str(item) for item in row[3])
        required_timeframes = {
            item.timeframe.value for item in batch.bars
        } | {
            item.timeframe.value for item in batch.gaps if item.timeframe is not None
        }
        required_bases = {
            item.price_basis.value for item in batch.bars
        } | {
            item.price_basis.value
            for item in batch.gaps
            if item.price_basis is not None
        }
        if not required_timeframes <= allowed_timeframes:
            raise RuntimeStateConflictError(
                "Normalization exceeds ProviderProduct timeframe capabilities"
            )
        if not required_bases <= allowed_bases:
            raise RuntimeStateConflictError(
                "Normalization exceeds ProviderProduct price-basis capabilities"
            )

    def _validate_product_predecessor(self, product: ProviderProduct) -> None:
        if product.supersedes_provider_product_id is None:
            return
        row = self._connection.execute(
            """
            SELECT provider_id, product_code, revision
            FROM mra.provider_product
            WHERE provider_product_id = %s
            FOR SHARE
            """,
            (product.supersedes_provider_product_id,),
        ).fetchone()
        if row != (product.provider_id, product.product_code, product.revision - 1):
            raise RuntimeStateConflictError("ProviderProduct predecessor is not exact")

    def _validate_identifier_predecessor(self, item: InstrumentIdentifier) -> None:
        if item.supersedes_identifier_id is None:
            return
        row = self._connection.execute(
            """
            SELECT instrument_id, identifier_scheme, identifier_value,
                   effective_from, revision
            FROM mra.instrument_identifier
            WHERE instrument_identifier_id = %s
            FOR SHARE
            """,
            (item.supersedes_identifier_id,),
        ).fetchone()
        if row != (
            item.instrument_id.value,
            item.identifier_scheme,
            item.identifier_value,
            item.effective_from,
            item.revision - 1,
        ):
            raise RuntimeStateConflictError("InstrumentIdentifier predecessor is not exact")

    def _validate_classification_predecessor(
        self, item: ClassificationRevision
    ) -> None:
        if item.supersedes_classification_id is None:
            return
        row = self._connection.execute(
            """
            SELECT classification_scheme, classification_code,
                   effective_from, revision
            FROM mra.classification
            WHERE classification_id = %s
            FOR SHARE
            """,
            (item.supersedes_classification_id,),
        ).fetchone()
        if row != (
            item.classification_scheme,
            item.classification_code,
            item.effective_from,
            item.revision - 1,
        ):
            raise RuntimeStateConflictError("Classification predecessor is not exact")

    def _validate_membership_predecessor(
        self, item: ClassificationMembershipRevision
    ) -> None:
        if item.supersedes_membership_revision_id is None:
            return
        row = self._connection.execute(
            """
            SELECT prior_classification.classification_scheme,
                   prior_classification.classification_code,
                   membership.instrument_id, membership.effective_from,
                   membership.revision
            FROM mra.classification_membership_revision AS membership
            JOIN mra.classification AS prior_classification
              ON prior_classification.classification_id = membership.classification_id
            WHERE membership.membership_revision_id = %s
            FOR SHARE
            """,
            (item.supersedes_membership_revision_id,),
        ).fetchone()
        classification = self._connection.execute(
            """
            SELECT classification_scheme, classification_code
            FROM mra.classification
            WHERE classification_id = %s
            FOR SHARE
            """,
            (item.classification_id,),
        ).fetchone()
        expected = (
            *(classification or (None, None)),
            item.instrument_id.value,
            item.effective_from,
            item.revision - 1,
        )
        if row != expected:
            raise RuntimeStateConflictError("ClassificationMembership predecessor is not exact")

    def _validate_bar_predecessor(self, item: MarketBarRevision) -> None:
        if item.supersedes_revision_id is None:
            return
        row = self._connection.execute(
            """
            SELECT provider_product_id, instrument_id, session_id, timeframe,
                   price_basis, event_start, event_end, revision
            FROM mra.market_bar_revision
            WHERE bar_revision_id = %s
            FOR SHARE
            """,
            (item.supersedes_revision_id,),
        ).fetchone()
        expected = (
            item.provider_product_id,
            item.instrument_id.value,
            item.session_id.value,
            item.timeframe.value,
            item.price_basis.value,
            item.event_start,
            item.event_end,
            item.revision - 1,
        )
        if row != expected:
            raise RuntimeStateConflictError("MarketBar predecessor is not the same logical fact")

    def _validate_fact_predecessor(self, item: SecurityStatusFactRevision) -> None:
        if item.supersedes_revision_id is None:
            return
        row = self._connection.execute(
            """
            SELECT provider_product_id, instrument_id, session_id, fact_kind,
                   evidence_scope, event_start, event_end, revision
            FROM mra.instrument_fact_revision
            WHERE fact_revision_id = %s
            FOR SHARE
            """,
            (item.supersedes_revision_id,),
        ).fetchone()
        expected = (
            item.provider_product_id,
            item.instrument_id.value,
            item.session_id.value,
            "SECURITY_STATUS",
            item.evidence_scope.value,
            item.event_start,
            item.event_end,
            item.revision - 1,
        )
        if row != expected:
            raise RuntimeStateConflictError("InstrumentFact predecessor is not the same logical fact")

    def _validate_generic_fact_predecessor(
        self, item: InstrumentFactRevision | InstrumentLifecycleFactRevision
    ) -> None:
        if item.supersedes_revision_id is None:
            return
        row = self._connection.execute(
            """
            SELECT provider_product_id, instrument_id, session_id, fact_kind,
                   evidence_scope, event_start, event_end, revision
            FROM mra.instrument_fact_revision
            WHERE fact_revision_id = %s
            FOR SHARE
            """,
            (item.supersedes_revision_id,),
        ).fetchone()
        expected_prefix = (
            item.provider_product_id,
            item.instrument_id.value,
            (
                item.session_id.value
                if isinstance(item, InstrumentFactRevision)
                and item.session_id is not None
                else None
            ),
            item.fact_kind.value,
            (
                item.evidence_scope.value
                if isinstance(item, InstrumentFactRevision)
                else "EFFECTIVE_INTERVAL"
            ),
            (
                item.event_start
                if isinstance(item, InstrumentFactRevision)
                else item.effective_from
            ),
        )
        effective_timeline = isinstance(item, InstrumentLifecycleFactRevision) or (
            isinstance(item, InstrumentFactRevision)
            and item.evidence_scope.value == "EFFECTIVE_INTERVAL"
        )
        if effective_timeline:
            matches = row is not None and (*row[:6], row[7]) == (
                *expected_prefix,
                item.revision - 1,
            )
        else:
            assert isinstance(item, InstrumentFactRevision)
            matches = row == (
                *expected_prefix,
                item.event_end,
                item.revision - 1,
            )
        if not matches:
            raise RuntimeStateConflictError("InstrumentFact predecessor is not the same logical fact")

    def _validate_action_predecessor(self, item: CorporateActionRevision) -> None:
        if item.supersedes_revision_id is None:
            return
        row = self._connection.execute(
            """
            SELECT provider_product_id, instrument_id, action_key, revision
            FROM mra.corporate_action_revision
            WHERE corporate_action_revision_id = %s
            FOR SHARE
            """,
            (item.supersedes_revision_id,),
        ).fetchone()
        if row != (
            item.provider_product_id,
            item.instrument_id.value,
            item.action_key,
            item.revision - 1,
        ):
            raise RuntimeStateConflictError("CorporateAction predecessor is not exact")


def _capture_source(row: tuple[Any, ...]) -> CaptureSource:
    from market_regime_alpha.market.domain import (
        CaptureStatus,
        SourceAvailabilityStatus,
        TemporalEnvelope,
    )

    capture = ProviderCapture(
        capture_id=UUID(str(row[0])),
        provider_product_id=UUID(str(row[1])),
        capture_key=str(row[2]),
        request_hash=ContentHash(str(row[3])),
        status=CaptureStatus(str(row[4])),
        temporal=TemporalEnvelope(
            provider_time=row[5],
            source_availability_status=SourceAvailabilityStatus(str(row[6])),
            source_available_at=row[7],
            capture_started_at=row[8],
            capture_completed_at=row[9],
            known_at=row[10],
            decision_visible_at=row[11],
        ),
        artifact_id=UUID(str(row[12])) if row[12] is not None else None,
        error_code=str(row[13]) if row[13] is not None else None,
        limitation_code=str(row[14]) if row[14] is not None else None,
        payload_encoding=str(row[15]) if row[15] is not None else None,
    )
    artifact = None
    if row[12] is not None:
        artifact = ArtifactRecord(
            artifact_id=UUID(str(row[12])),
            content_sha256=str(row[16]),
            size_bytes=int(row[17]),
            media_type=str(row[18]),
            locator=str(row[19]),
            integrity_state=str(row[20]),
            retention_until=row[21],
            pin_reason_code=str(row[22]) if row[22] is not None else None,
        )
    return CaptureSource(capture=capture, artifact=artifact)


__all__ = ["PostgresMarketRepository"]
