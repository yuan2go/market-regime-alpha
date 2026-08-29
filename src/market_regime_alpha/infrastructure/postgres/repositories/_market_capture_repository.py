"""PostgreSQL write owner for the target Market/PIT bounded context."""

from __future__ import annotations

from dataclasses import replace
from uuid import UUID


from market_regime_alpha.market.domain import (
    NormalizationBatch,
    ProviderCapture,
    SourceGap,
    TemporalEnvelope,
)
from market_regime_alpha.market.ports import CaptureSource
from market_regime_alpha.runtime.errors import (
    ArtifactIntegrityError,
    RuntimeNotFoundError,
    RuntimeStateConflictError,
)
from market_regime_alpha.runtime.ports import PublishedArtifact
from market_regime_alpha.shared.time import DecisionTime


from market_regime_alpha.infrastructure.postgres.repositories._market_repository_mapping import _capture_source
from market_regime_alpha.infrastructure.postgres.repositories._market_repository_support import _MarketRepositorySupport


class _MarketCaptureRepository(_MarketRepositorySupport):
    def record_capture(self, capture: ProviderCapture, published: PublishedArtifact | None) -> ProviderCapture:
        product = self._connection.execute(
            "\n            SELECT media_type, payload_encoding, source_availability_policy\n            FROM mra.provider_product\n            WHERE provider_product_id = %s\n            FOR SHARE\n            ",
            (capture.provider_product_id,),
        ).fetchone()
        if product is None:
            raise RuntimeNotFoundError(f"ProviderProduct {capture.provider_product_id} does not exist")
        if capture.status.value == "CAPTURED" and str(product[2]) != capture.temporal.source_availability_status.value:
            raise RuntimeStateConflictError("Capture availability semantics differ from ProviderProduct contract")
        if published is not None:
            if capture.artifact_id is None:
                raise ArtifactIntegrityError("captured bytes have no Artifact identity")
            if (str(product[0]), str(product[1])) != (published.media_type, capture.payload_encoding):
                raise ArtifactIntegrityError("captured payload media type or encoding differs from ProviderProduct")
            artifact = self._connection.execute(
                "\n                SELECT content_sha256, size_bytes, media_type, locator, integrity_state\n                FROM mra.artifact\n                WHERE artifact_id = %s\n                FOR SHARE\n                ",
                (capture.artifact_id,),
            ).fetchone()
            if artifact != (published.content_sha256, published.size_bytes, published.media_type, published.locator, "AVAILABLE"):
                raise ArtifactIntegrityError("Capture Artifact is not the exact verified published object")
        temporal = self._connection.execute(
            "\n            WITH database_clock AS (\n                SELECT clock_timestamp() AS recorded_at\n            ), canonical_time AS (\n                SELECT recorded_at,\n                       GREATEST(%s::timestamptz, recorded_at) AS known_at\n                FROM database_clock\n            )\n            INSERT INTO mra.data_capture (\n                capture_id, provider_product_id, capture_key, request_hash,\n                artifact_id, status, provider_time,\n                source_availability_status, source_available_at,\n                capture_started_at, capture_completed_at, recorded_at, known_at,\n                decision_visible_at, error_code, limitation_code,\n                payload_encoding\n            )\n            SELECT %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,\n                   canonical_time.recorded_at, canonical_time.known_at,\n                   canonical_time.known_at, %s, %s, %s\n            FROM canonical_time\n            RETURNING recorded_at, known_at, decision_visible_at\n            ",
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

    def record_capture_failure(self, capture: ProviderCapture, gap: SourceGap) -> tuple[ProviderCapture, DecisionTime]:
        canonical = self.record_capture(capture, None)
        if gap.capture_id != canonical.capture_id:
            raise RuntimeStateConflictError("Capture failure Gap has different Capture")
        if gap.provider_product_id != canonical.provider_product_id:
            raise RuntimeStateConflictError("Capture failure Gap has different ProviderProduct")
        self._validate_product_capabilities(  # type: ignore[attr-defined]
            NormalizationBatch(
                source_capture_id=canonical.capture_id, source_provider_product_id=canonical.provider_product_id, gaps=(gap,)
            )
        )
        recorded_at = canonical.temporal.known_at.value
        known_at = canonical.temporal.known_at.value
        self._insert_source_gap(  # type: ignore[attr-defined]
            gap,
            recorded_at=recorded_at,
            known_at=known_at,
        )
        return (canonical, DecisionTime(known_at))

    def get_capture(self, capture_id: UUID) -> ProviderCapture:
        return self.capture_source(capture_id, lock=False).capture

    def normalization_decision_visible_at(self, capture_id: UUID) -> DecisionTime:
        row = self._connection.execute(
            "\n            SELECT min(decision_visible_at), max(decision_visible_at), count(*)\n            FROM (\n                SELECT decision_visible_at FROM mra.instrument\n                WHERE source_capture_id = %(capture_id)s\n                UNION ALL\n                SELECT decision_visible_at FROM mra.instrument_identifier\n                WHERE source_capture_id = %(capture_id)s\n                UNION ALL\n                SELECT decision_visible_at FROM mra.trading_session\n                WHERE source_capture_id = %(capture_id)s\n                UNION ALL\n                SELECT decision_visible_at FROM mra.classification\n                WHERE source_capture_id = %(capture_id)s\n                UNION ALL\n                SELECT decision_visible_at\n                FROM mra.classification_membership_revision\n                WHERE source_capture_id = %(capture_id)s\n                UNION ALL\n                SELECT decision_visible_at FROM mra.market_bar_revision\n                WHERE capture_id = %(capture_id)s\n                UNION ALL\n                SELECT decision_visible_at FROM mra.instrument_fact_revision\n                WHERE capture_id = %(capture_id)s\n                UNION ALL\n                SELECT decision_visible_at FROM mra.corporate_action_revision\n                WHERE capture_id = %(capture_id)s\n                UNION ALL\n                SELECT decision_visible_at FROM mra.source_gap\n                WHERE capture_id = %(capture_id)s\n            ) AS normalized\n            ",
            {"capture_id": capture_id},
        ).fetchone()
        if row is None or int(row[2]) == 0:
            raise RuntimeNotFoundError(f"Capture {capture_id} has no committed normalization evidence")
        if row[0] != row[1]:
            raise RuntimeStateConflictError(f"Capture {capture_id} normalization has inconsistent visibility")
        return DecisionTime(row[0])

    def capture_source(self, capture_id: UUID, *, lock: bool = False) -> CaptureSource:
        suffix = " FOR UPDATE OF capture" if lock else ""
        row = self._connection.execute(
            "\n            SELECT\n                capture.capture_id, capture.provider_product_id,\n                capture.capture_key, capture.request_hash, capture.status,\n                capture.provider_time, capture.source_availability_status,\n                capture.source_available_at, capture.capture_started_at,\n                capture.capture_completed_at, capture.known_at,\n                capture.decision_visible_at, capture.artifact_id,\n                capture.error_code, capture.limitation_code,\n                capture.payload_encoding,\n                artifact.content_sha256, artifact.size_bytes,\n                artifact.media_type, artifact.locator,\n                artifact.integrity_state, artifact.retention_until,\n                artifact.pin_reason_code\n            FROM mra.data_capture AS capture\n            LEFT JOIN mra.artifact AS artifact\n              ON artifact.artifact_id = capture.artifact_id\n            WHERE capture.capture_id = %s\n            "
            + suffix,
            (capture_id,),
        ).fetchone()
        if row is None:
            raise RuntimeNotFoundError(f"Capture {capture_id} does not exist")
        return _capture_source(row)

    def lock_capture_source(self, capture_id: UUID) -> CaptureSource:
        self._connection.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (f"mra:capture-normalization:{capture_id}",))
        source = self.capture_source(capture_id, lock=True)
        if source.artifact is None or source.artifact.integrity_state != "AVAILABLE":
            raise ArtifactIntegrityError("Capture source Artifact is not AVAILABLE")
        locked_artifact = self._connection.execute(
            "\n            SELECT content_sha256, size_bytes, integrity_state\n            FROM mra.artifact\n            WHERE artifact_id = %s\n            FOR SHARE\n            ",
            (source.artifact.artifact_id,),
        ).fetchone()
        if locked_artifact != (source.artifact.content_sha256, source.artifact.size_bytes, "AVAILABLE"):
            raise ArtifactIntegrityError("Capture source Artifact changed before binding")
        return source
