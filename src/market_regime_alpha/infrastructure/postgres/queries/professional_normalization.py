"""Batch verified Market references for the exact recorded Provider product.

This supports normalization only. Archive sealing and study preparation still
independently require the selected Archive's complete source bindings.
"""

from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.market.domain import ProviderCapture
from market_regime_alpha.market.domain.professional_daily import ProfessionalDailyContract
from market_regime_alpha.market.ports.professional_normalization import ProfessionalInstrumentReference
from market_regime_alpha.market.ports.session_roster import ArchiveTradingSession
from market_regime_alpha.research_qualification.ports.artifacts import ResearchArtifactByteStore
from market_regime_alpha.runtime.errors import ArtifactIntegrityError
from market_regime_alpha.shared.identity import InstrumentId, TradingSessionId


class PostgresProfessionalNormalizationReferences:
    def __init__(self, pool: TargetPostgresPool, byte_store: ResearchArtifactByteStore) -> None:
        self._pool, self._bytes = pool, byte_store

    def references(self, contract: ProfessionalDailyContract, capture: ProviderCapture) -> tuple[ProfessionalInstrumentReference, ...]:
        codes = {stock: stock[:6]+"."+{"SH":"XSHG","SZ":"XSHE"}[stock[-2:]] for stock in contract.instruments}
        cutoff = capture.temporal.known_at.value
        with self._pool.connection(read_only=True) as connection:
            instruments = connection.execute("""
                SELECT instrument.instrument_id,instrument.canonical_code,instrument.exchange,
                    source.content_sha256,source.size_bytes,source.readable
                FROM mra.instrument instrument LEFT JOIN LATERAL (
                    SELECT artifact.content_sha256,artifact.size_bytes,
                        mra.market_artifact_is_readable(artifact.integrity_state,artifact.last_verified_at) AS readable
                    FROM mra.market_capture_instrument_normalization binding
                    JOIN mra.market_capture_reference_normalization normalized USING(capture_id)
                    JOIN mra.data_capture capture USING(capture_id) JOIN mra.artifact artifact USING(artifact_id)
                    WHERE binding.instrument_id=instrument.instrument_id AND capture.provider_product_id=%s
                        AND capture.status='CAPTURED' AND capture.recorded_at<=%s AND normalized.recorded_at<=%s
                    ORDER BY capture.recorded_at,capture.capture_id LIMIT 1
                ) source ON true WHERE instrument.canonical_code=ANY(%s)
                """, (capture.provider_product_id,cutoff,cutoff,list(codes.values()))).fetchall()
            if len(instruments) != len(codes) or {row[1] for row in instruments} != set(codes.values()):
                raise ArtifactIntegrityError("professional recording requires exact Market instrument identities")
            sessions = connection.execute("""
                SELECT session.session_id,session.exchange,session.session_date,session.open_at,
                    session.break_start_at,session.break_end_at,session.close_at,
                    source.content_sha256,source.size_bytes,source.readable
                FROM mra.trading_session session LEFT JOIN LATERAL (
                    SELECT artifact.content_sha256,artifact.size_bytes,
                        mra.market_artifact_is_readable(artifact.integrity_state,artifact.last_verified_at) AS readable
                    FROM mra.market_capture_trading_session_normalization binding
                    JOIN mra.market_capture_reference_normalization normalized USING(capture_id)
                    JOIN mra.data_capture capture USING(capture_id) JOIN mra.artifact artifact USING(artifact_id)
                    WHERE binding.session_id=session.session_id AND capture.provider_product_id=%s
                        AND capture.status='CAPTURED' AND capture.recorded_at<=%s AND normalized.recorded_at<=%s
                    ORDER BY capture.recorded_at,capture.capture_id LIMIT 1
                ) source ON true
                WHERE session.exchange=ANY(%s) AND session.session_date BETWEEN %s AND %s
                ORDER BY session.exchange,session.session_date LIMIT 4003
                """, (capture.provider_product_id,cutoff,cutoff,sorted({row[2] for row in instruments}),contract.start_date,contract.end_date)).fetchall()
        if not sessions or len(sessions)>4002 or len({(r[1],r[2]) for r in sessions})!=len(sessions):
            raise ArtifactIntegrityError("professional recording requires a bounded unambiguous Market Calendar")
        artifacts = {(row[-3],row[-2],row[-1]) for row in (*instruments,*sessions)}
        for digest,size,readable in artifacts:
            if digest is None or not readable:
                raise ArtifactIntegrityError("professional Market reference lacks an exact readable product Capture binding")
            self._bytes.read_bytes(digest,expected_size=size)
        by_code = {row[1]:row for row in instruments}
        return tuple(ProfessionalInstrumentReference(stock,InstrumentId(by_code[code][0]),
            tuple(ArchiveTradingSession(TradingSessionId(r[0]),*r[1:7]) for r in sessions if r[1]==by_code[code][2]))
            for stock,code in codes.items())
