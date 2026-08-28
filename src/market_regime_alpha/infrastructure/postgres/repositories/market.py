"""PostgreSQL write owner for the target Market/PIT bounded context."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import psycopg

from market_regime_alpha.market.domain import (
    ClassificationMembershipRevision,
    ClassificationRevision,
    CorporateActionRevision,
    Instrument,
    InstrumentFactRevision,
    InstrumentIdentifier,
    MarketBarRevision,
    Provider,
    ProviderCapture,
    ProviderProduct,
    SecurityStatusFactRevision,
    SourceGap,
    TradingSession,
)
from market_regime_alpha.market.ports import CaptureSource
from market_regime_alpha.runtime.errors import (
    ArtifactIntegrityError,
    RuntimeNotFoundError,
    RuntimeStateConflictError,
)
from market_regime_alpha.runtime.ports import ArtifactRecord, PublishedArtifact


class PostgresMarketRepository:
    """Aggregate writes only; transaction ownership belongs to MarketUnitOfWork."""

    def __init__(self, connection: psycopg.Connection[Any]) -> None:
        self._connection = connection

    def register_provider(self, provider: Provider) -> int:
        self._connection.execute(
            """
            INSERT INTO mra.provider (
                provider_id, provider_code, display_name, provider_kind,
                authority_ceiling
            )
            VALUES (%s, %s, %s, %s, 'EXPLORATORY_UNQUALIFIED')
            """,
            (
                provider.provider_id,
                provider.provider_code,
                provider.display_name,
                provider.provider_kind,
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
                decision_visibility_policy, source_availability_policy,
                contract_sha256, supersedes_provider_product_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'KNOWN_AT', %s, %s, %s)
            """,
            (
                product.provider_product_id,
                product.provider_id,
                product.product_code,
                product.revision,
                product.payload_family,
                product.media_type,
                product.payload_encoding,
                product.source_availability_policy.value,
                product.contract_sha256,
                product.supersedes_provider_product_id,
            ),
        )
        return product.revision

    def insert_capture(
        self,
        capture: ProviderCapture,
        published: PublishedArtifact | None,
    ) -> int:
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
        if str(product[2]) != capture.temporal.source_availability_status.value:
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
        self._connection.execute(
            """
            INSERT INTO mra.data_capture (
                capture_id, provider_product_id, capture_key, request_hash,
                artifact_id, status, provider_time,
                source_availability_status, source_available_at,
                capture_started_at, capture_completed_at, known_at,
                decision_visible_at, error_code, limitation_code,
                payload_encoding
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s)
            """,
            (
                capture.capture_id,
                capture.provider_product_id,
                capture.capture_key,
                capture.request_hash,
                capture.artifact_id,
                capture.status.value,
                capture.temporal.provider_time,
                capture.temporal.source_availability_status.value,
                capture.temporal.source_available_at,
                capture.temporal.capture_started_at,
                capture.temporal.capture_completed_at,
                capture.temporal.known_at,
                capture.temporal.decision_visible_at,
                capture.error_code,
                capture.limitation_code,
                capture.payload_encoding,
            ),
        )
        return 1

    def get_capture(self, capture_id: UUID) -> ProviderCapture:
        return self.capture_source(capture_id, lock=False).capture

    def capture_source(self, capture_id: UUID, *, lock: bool = False) -> CaptureSource:
        suffix = " FOR SHARE OF capture" if lock else ""
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

    def insert_instrument(self, instrument: Instrument) -> None:
        self._connection.execute(
            """
            INSERT INTO mra.instrument (
                instrument_id, canonical_code, exchange, instrument_type,
                currency, source_capture_id
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                instrument.instrument_id,
                instrument.canonical_code,
                instrument.exchange,
                instrument.instrument_type,
                instrument.currency,
                instrument.source_capture_id,
            ),
        )

    def insert_instrument_identifier(self, identifier: InstrumentIdentifier) -> None:
        self._validate_identifier_predecessor(identifier)
        self._connection.execute(
            """
            INSERT INTO mra.instrument_identifier (
                instrument_identifier_id, instrument_id, identifier_scheme,
                identifier_value, effective_from, effective_to, revision,
                supersedes_identifier_id, source_capture_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                identifier.instrument_identifier_id,
                identifier.instrument_id,
                identifier.identifier_scheme,
                identifier.identifier_value,
                identifier.effective_from,
                identifier.effective_to,
                identifier.revision,
                identifier.supersedes_identifier_id,
                identifier.source_capture_id,
            ),
        )

    def insert_trading_session(self, session: TradingSession) -> int:
        self._connection.execute(
            """
            INSERT INTO mra.trading_session (
                session_id, exchange, session_date, timezone_name, open_at,
                break_start_at, break_end_at, close_at,
                decision_reference_at, source_capture_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                session.session_id,
                session.exchange,
                session.session_date,
                session.timezone_name,
                session.open_at,
                session.break_start_at,
                session.break_end_at,
                session.close_at,
                session.decision_reference_at,
                session.source_capture_id,
            ),
        )
        return 1

    def insert_classification(self, item: ClassificationRevision) -> None:
        self._validate_classification_predecessor(item)
        self._connection.execute(
            """
            INSERT INTO mra.classification (
                classification_id, classification_scheme,
                classification_code, display_name, revision,
                effective_from, effective_to,
                supersedes_classification_id, source_capture_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
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
            ),
        )

    def insert_classification_membership(
        self, item: ClassificationMembershipRevision
    ) -> None:
        self._validate_membership_predecessor(item)
        self._connection.execute(
            """
            INSERT INTO mra.classification_membership_revision (
                membership_revision_id, classification_id, instrument_id,
                source_capture_id, membership_status, effective_from,
                effective_to, revision, supersedes_membership_revision_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                item.membership_revision_id,
                item.classification_id,
                item.instrument_id,
                item.source_capture_id,
                item.membership_status,
                item.effective_from,
                item.effective_to,
                item.revision,
                item.supersedes_membership_revision_id,
            ),
        )

    def insert_bar_revision(self, bar: MarketBarRevision) -> None:
        self._validate_bar_predecessor(bar)
        self._connection.execute(
            """
            INSERT INTO mra.market_bar_revision (
                bar_revision_id, provider_product_id, capture_id,
                instrument_id, session_id, timeframe, adjustment_basis,
                event_start, event_end, revision, supersedes_revision_id,
                open_value, high_value, low_value, close_value,
                volume_value, turnover_value
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                bar.bar_revision_id,
                bar.provider_product_id,
                bar.capture_id,
                bar.instrument_id,
                bar.session_id,
                bar.timeframe.value,
                bar.adjustment_basis.value,
                bar.event_start,
                bar.event_end,
                bar.revision,
                bar.supersedes_revision_id,
                bar.open,
                bar.high,
                bar.low,
                bar.close,
                bar.volume,
                bar.turnover,
            ),
        )

    def insert_security_status_revision(
        self, fact: SecurityStatusFactRevision
    ) -> None:
        self._validate_fact_predecessor(fact)
        self._connection.execute(
            """
            INSERT INTO mra.instrument_fact_revision (
                fact_revision_id, provider_product_id, capture_id,
                instrument_id, session_id, fact_kind, evidence_scope,
                event_start, event_end, value_kind, status_value,
                revision, supersedes_revision_id
            )
            VALUES (%s, %s, %s, %s, %s, 'SECURITY_STATUS', %s,
                    %s, %s, 'STATUS', %s, %s, %s)
            """,
            (
                fact.fact_revision_id,
                fact.provider_product_id,
                fact.capture_id,
                fact.instrument_id,
                fact.session_id,
                fact.evidence_scope,
                fact.event_start,
                fact.event_end,
                fact.status.value,
                fact.revision,
                fact.supersedes_revision_id,
            ),
        )

    def insert_instrument_fact_revision(self, fact: InstrumentFactRevision) -> None:
        self._validate_generic_fact_predecessor(fact)
        self._connection.execute(
            """
            INSERT INTO mra.instrument_fact_revision (
                fact_revision_id, provider_product_id, capture_id,
                instrument_id, session_id, fact_kind, evidence_scope,
                event_start, event_end, value_kind, status_value,
                numeric_value, text_value, unit_code, revision,
                supersedes_revision_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s)
            """,
            (
                fact.fact_revision_id,
                fact.provider_product_id,
                fact.capture_id,
                fact.instrument_id,
                fact.session_id,
                fact.fact_kind,
                fact.evidence_scope,
                fact.event_start,
                fact.event_end,
                fact.value_kind.value,
                fact.status_value,
                fact.numeric_value,
                fact.text_value,
                fact.unit_code,
                fact.revision,
                fact.supersedes_revision_id,
            ),
        )

    def insert_corporate_action(self, action: CorporateActionRevision) -> None:
        self._validate_action_predecessor(action)
        self._connection.execute(
            """
            INSERT INTO mra.corporate_action_revision (
                corporate_action_revision_id, provider_product_id, capture_id,
                instrument_id, action_key, action_type, ex_session_id,
                payable_at, cash_amount, ratio_factor, currency, revision,
                supersedes_revision_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                action.corporate_action_revision_id,
                action.provider_product_id,
                action.capture_id,
                action.instrument_id,
                action.action_key,
                action.action_type,
                action.ex_session_id,
                action.payable_at,
                action.cash_amount,
                action.ratio_factor,
                action.currency,
                action.revision,
                action.supersedes_revision_id,
            ),
        )

    def insert_source_gap(self, gap: SourceGap) -> None:
        self._connection.execute(
            """
            INSERT INTO mra.source_gap (
                gap_id, provider_product_id, capture_id, instrument_id,
                session_id, gap_kind, reason_code, fact_kind, timeframe,
                adjustment_basis, event_start, event_end, detail
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                gap.gap_id,
                gap.provider_product_id,
                gap.capture_id,
                gap.instrument_id,
                gap.session_id,
                gap.gap_kind.value,
                gap.reason_code,
                gap.fact_kind,
                gap.timeframe.value if gap.timeframe is not None else None,
                gap.adjustment_basis.value if gap.adjustment_basis is not None else None,
                gap.event_start,
                gap.event_end,
                gap.detail,
            ),
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
            SELECT instrument_id, identifier_scheme, identifier_value, revision
            FROM mra.instrument_identifier
            WHERE instrument_identifier_id = %s
            FOR SHARE
            """,
            (item.supersedes_identifier_id,),
        ).fetchone()
        if row != (
            item.instrument_id,
            item.identifier_scheme,
            item.identifier_value,
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
            SELECT classification_scheme, classification_code, revision
            FROM mra.classification
            WHERE classification_id = %s
            FOR SHARE
            """,
            (item.supersedes_classification_id,),
        ).fetchone()
        if row != (
            item.classification_scheme,
            item.classification_code,
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
            SELECT classification_id, instrument_id, revision
            FROM mra.classification_membership_revision
            WHERE membership_revision_id = %s
            FOR SHARE
            """,
            (item.supersedes_membership_revision_id,),
        ).fetchone()
        if row != (item.classification_id, item.instrument_id, item.revision - 1):
            raise RuntimeStateConflictError("ClassificationMembership predecessor is not exact")

    def _validate_bar_predecessor(self, item: MarketBarRevision) -> None:
        if item.supersedes_revision_id is None:
            return
        row = self._connection.execute(
            """
            SELECT provider_product_id, instrument_id, session_id, timeframe,
                   adjustment_basis, event_start, event_end, revision
            FROM mra.market_bar_revision
            WHERE bar_revision_id = %s
            FOR SHARE
            """,
            (item.supersedes_revision_id,),
        ).fetchone()
        expected = (
            item.provider_product_id,
            item.instrument_id,
            item.session_id,
            item.timeframe.value,
            item.adjustment_basis.value,
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
            item.instrument_id,
            item.session_id,
            "SECURITY_STATUS",
            item.evidence_scope,
            item.event_start,
            item.event_end,
            item.revision - 1,
        )
        if row != expected:
            raise RuntimeStateConflictError("InstrumentFact predecessor is not the same logical fact")

    def _validate_generic_fact_predecessor(
        self, item: InstrumentFactRevision
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
        expected = (
            item.provider_product_id,
            item.instrument_id,
            item.session_id,
            item.fact_kind,
            item.evidence_scope,
            item.event_start,
            item.event_end,
            item.revision - 1,
        )
        if row != expected:
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
            item.instrument_id,
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
        request_hash=str(row[3]),
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
