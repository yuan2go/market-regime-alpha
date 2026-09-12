"""Batch listing identities for price-independent historical controls."""

from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.research_qualification.ports.artifacts import ResearchArtifactByteStore
from market_regime_alpha.research_qualification.ports.backtest_actions import BacktestFeatureRequest
from market_regime_alpha.runtime.errors import ArtifactIntegrityError


class PostgresResearchInterceptInputs:
    def __init__(self, pool: TargetPostgresPool, byte_store: ResearchArtifactByteStore) -> None:
        self._pool, self._bytes = pool, byte_store

    def listing_identities(self, requests: tuple[BacktestFeatureRequest, ...]) -> dict:
        first = requests[0]
        scope = first.scope
        with self._pool.connection(read_only=True) as connection:
            rows = connection.execute("""
                SELECT fact.instrument_id,fact.fact_revision_id,session.session_id,
                    artifact.content_sha256,artifact.size_bytes,
                    mra.market_artifact_is_readable(artifact.integrity_state,artifact.last_verified_at)
                FROM mra.market_archive archive JOIN mra.market_archive_seal seal USING(market_archive_id)
                JOIN mra.instrument_fact_revision fact ON fact.provider_product_id=archive.provider_product_id
                JOIN mra.instrument instrument USING(instrument_id)
                JOIN mra.trading_session session ON session.exchange=instrument.exchange AND session.session_date=%s
                JOIN mra.data_capture capture ON capture.capture_id=fact.capture_id AND capture.status='CAPTURED'
                JOIN mra.artifact artifact ON artifact.artifact_id=capture.artifact_id
                WHERE archive.market_archive_id=%s AND seal.market_archive_seal_id=%s AND seal.knowledge_cutoff=%s
                    AND archive.lane='RETROSPECTIVE_BACKFILL' AND archive.evidence_class='EXPLORATORY_RETROSPECTIVE'
                    AND fact.instrument_id=ANY(%s) AND fact.fact_kind='LISTING_STATUS'
                    AND fact.evidence_scope='EFFECTIVE_INTERVAL' AND fact.session_id IS NULL
                    AND fact.event_start<=%s AND (fact.event_end IS NULL OR fact.event_end>%s)
                    AND fact.decision_visible_at<=%s AND fact.recorded_at<=%s AND capture.recorded_at<=%s
                    AND session.close_at=%s AND session.close_at<=%s AND session.known_at<=%s
                    AND EXISTS (SELECT 1 FROM mra.market_archive_capture_observation observation
                        WHERE observation.market_archive_id=archive.market_archive_id AND observation.capture_id=fact.capture_id AND observation.known_at<=%s)
                    AND EXISTS (SELECT 1 FROM mra.market_capture_instrument_normalization binding
                        JOIN mra.market_archive_capture_observation observation USING(capture_id)
                        WHERE binding.instrument_id=instrument.instrument_id AND observation.market_archive_id=archive.market_archive_id AND observation.known_at<=%s)
                    AND EXISTS (SELECT 1 FROM mra.market_capture_trading_session_normalization binding
                        JOIN mra.market_archive_capture_observation observation USING(capture_id)
                        WHERE binding.session_id=session.session_id AND observation.market_archive_id=archive.market_archive_id AND observation.known_at<=%s)
                    AND NOT EXISTS (SELECT 1 FROM mra.instrument_fact_revision successor
                        WHERE successor.supersedes_revision_id=fact.fact_revision_id AND successor.decision_visible_at<=%s)
                ORDER BY fact.instrument_id,fact.fact_revision_id
                """, (first.session_date,scope.market_archive_id,scope.market_archive_seal_id,scope.knowledge_cutoff,
                    [r.instrument_id.value for r in requests],scope.simulated_event_cutoff,scope.simulated_event_cutoff,
                    scope.knowledge_cutoff,scope.knowledge_cutoff,scope.knowledge_cutoff,first.session_close_at,
                    scope.simulated_event_cutoff,scope.knowledge_cutoff,scope.knowledge_cutoff,scope.knowledge_cutoff,
                    scope.knowledge_cutoff,scope.knowledge_cutoff)).fetchall()
        if len(rows) != len(requests) or {row[0] for row in rows} != {r.instrument_id.value for r in requests}:
            raise ArtifactIntegrityError("research intercept requires one exact archived listing fact per eligible instrument")
        for digest, size, readable in {(str(row[3]), int(row[4]), bool(row[5])) for row in rows}:
            if not readable:
                raise ArtifactIntegrityError("research intercept listing Artifact is not readable")
            self._bytes.read_bytes(digest, expected_size=size)
        return {row[0]: (row[1],row[2]) for row in rows}
