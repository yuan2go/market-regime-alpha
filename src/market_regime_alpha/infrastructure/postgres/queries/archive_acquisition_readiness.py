"""Rebuild capture-only readiness without changing Archive terminal truth."""

from dataclasses import asdict
import json
from typing import Any
from uuid import UUID

from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.postgres.queries.archive_sessions import PostgresArchiveTradingSessionReadPort
from market_regime_alpha.infrastructure.postgres.repositories.market import PostgresMarketRepository
from market_regime_alpha.infrastructure.providers.baostock_acquisition_readiness import preopen_empty_5m_readiness
from market_regime_alpha.infrastructure.providers.baostock_archive import BaoStockArchiveQuery
from market_regime_alpha.market.ports import CaptureRequest, MarketArtifactByteStore
from market_regime_alpha.runtime.errors import ArtifactIntegrityError
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.identity import ContentHash


class PostgresArchiveAcquisitionReadinessReads:
    def __init__(self, pool: TargetPostgresPool, byte_store: MarketArtifactByteStore) -> None:
        self._pool, self._byte_store = pool, byte_store

    def project(self, archive_id: UUID) -> tuple[dict[str, Any], ...]:
        with self._pool.connection(read_only=True) as connection:
            rows = connection.execute("""
                SELECT slice.market_archive_slice_id, terminal.terminal_state, capture.capture_id,
                       captured.result_hash, step.run_id, step.step_id, attempt.attempt_id, captured.receipt_id
                FROM mra.market_archive root JOIN mra.market_archive_slice slice USING(market_archive_id)
                JOIN mra.command_receipt captured ON captured.command_kind='CAPTURE_MARKET_DATA'
                    AND captured.scope_id=root.provider_product_id::text
                    AND captured.idempotency_key='archive:'||root.market_archive_id::text||':runtime:'||slice.market_archive_slice_id::text||':capture'
                JOIN mra.data_capture capture ON capture.capture_id::text=captured.result_aggregate_id
                JOIN mra.runtime_attempt attempt ON attempt.attempt_id=captured.runtime_attempt_id
                    AND attempt.result_receipt_id=captured.receipt_id
                JOIN mra.runtime_step step ON step.step_id=attempt.step_id AND step.step_id=captured.runtime_step_id
                LEFT JOIN mra.prospective_archive_slice_terminal terminal USING(market_archive_slice_id)
                WHERE root.market_archive_id=%s AND root.lane='PROSPECTIVE_CONTEMPORANEOUS'
                    AND captured.status='SUCCEEDED' AND captured.result_aggregate_kind='DATA_CAPTURE'
                    AND captured.result_aggregate_version=1 AND captured.request_hash=capture.request_hash
                    AND capture.request_hash=slice.request_sha256 AND capture.provider_product_id=root.provider_product_id
                    AND capture.status='CAPTURED' AND attempt.state='SUCCEEDED' AND step.state='SUCCEEDED'
                    AND attempt.fence_token=captured.fence_token AND step.current_fence=attempt.fence_token
                    AND step.current_attempt_id IS NULL AND attempt.external_effect_class='CONTENT_PUT'
                    AND capture.capture_started_at>=slice.event_window_start AND capture.capture_started_at<=slice.event_window_end
                    AND NOT EXISTS (SELECT 1 FROM mra.command_receipt normalized
                        WHERE normalized.command_kind='NORMALIZE_MARKET_PIT' AND normalized.scope_id=capture.capture_id::text)
                    AND (SELECT normalized_revision_count FROM mra.market_capture_normalized_roster(capture.capture_id))=0
                ORDER BY slice.ordinal
            """, (archive_id,)).fetchall()
            sources = [(row, PostgresMarketRepository(connection).capture_source(row[2], lock=False)) for row in rows]
        results = []
        for row, source in sources:
            if source.artifact is None or source.artifact.integrity_state != "AVAILABLE":
                raise ArtifactIntegrityError("ACQUISITION_REPORT_SOURCE_UNAVAILABLE")
            capture, artifact = source.capture, source.artifact
            content = self._byte_store.read_bytes(ContentHash(artifact.content_sha256), expected_size=artifact.size_bytes)
            query = BaoStockArchiveQuery.from_resource(json.dumps(json.loads(content)["query"], sort_keys=True, separators=(",", ":")))
            request = CaptureRequest(capture.provider_product_id, capture.capture_key, query.resource,
                                     ContentHash(canonical_json_sha256({"headers": {}})))
            if canonical_json_sha256(request) != str(capture.request_hash) or row[3] != canonical_json_sha256({
                "capture": capture, "artifact_hash": artifact.content_sha256, "artifact_size": artifact.size_bytes,
            }):
                raise ArtifactIntegrityError("ACQUISITION_REPORT_RECEIPT_IDENTITY_CHANGED")
            readiness = preopen_empty_5m_readiness(capture, content, query, PostgresArchiveTradingSessionReadPort(self._pool))
            if readiness is None:
                raise ArtifactIntegrityError("ACQUISITION_REPORT_NO_READINESS_PROOF")
            results.append({**asdict(readiness), "market_archive_slice_id": row[0], "archive_terminal_state": row[1],
                "runtime_run_id": row[4], "runtime_step_id": row[5], "runtime_attempt_id": row[6], "capture_receipt_id": row[7],
                "raw_capture_occurred": True, "normalized_observation_count": 0,
                "archive_terminal_semantics": "MISSED_MEANS_NO_QUALIFIED_NORMALIZED_OBSERVATION; RAW_CAPTURE_RETAINED",
                "business_writes": 0})
        return tuple(results)
