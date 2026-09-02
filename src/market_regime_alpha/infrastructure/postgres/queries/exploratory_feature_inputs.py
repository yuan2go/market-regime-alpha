"""Exact sealed-archive feature inputs for retrospective simulation only."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID

from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.research_qualification.domain.exploratory import (
    ExploratoryRetrospectiveDatasetScope,
)
from market_regime_alpha.research_qualification.ports.exploratory_feature_inputs import (
    ExploratoryIntradayFeatureGap,
    ExploratoryIntradayFeatureInput,
    ExploratoryIntradayFeatureObservation,
)
from market_regime_alpha.runtime.errors import (
    ArtifactIntegrityError,
    RuntimeNotFoundError,
    RuntimeStateConflictError,
)
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.identity import ContentHash, InstrumentId, TradingSessionId
from market_regime_alpha.shared.time import require_utc


class PostgresExploratoryFeatureInputReadPort:
    """Resolve no latest/current row: only one leaf visible at the frozen seal."""

    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool

    def exact_intraday_move(
        self,
        *,
        scope: ExploratoryRetrospectiveDatasetScope,
        instrument_id: InstrumentId,
        session_id: TradingSessionId,
        feature_event_end: datetime,
    ) -> ExploratoryIntradayFeatureInput:
        instrument_id = InstrumentId.parse(instrument_id)
        session_id = TradingSessionId.parse(session_id)
        event_end = require_utc(feature_event_end, field="feature_event_end")
        if event_end > scope.simulated_event_cutoff:
            raise ValueError("feature checkpoint exceeds simulated DecisionTime")
        event_start = event_end - timedelta(minutes=5)
        with self._pool.connection(read_only=True) as connection:
            root = connection.execute(
                """
                SELECT archive.lane, archive.evidence_class,
                       seal.knowledge_cutoff, session.close_at,
                       session.open_at, session.break_start_at,
                       session.break_end_at
                FROM mra.market_archive AS archive
                JOIN mra.market_archive_seal AS seal
                  ON seal.market_archive_id = archive.market_archive_id
                 AND seal.market_archive_seal_id = %s
                JOIN mra.trading_session AS session ON session.session_id = %s
                WHERE archive.market_archive_id = %s
                """,
                (
                    scope.market_archive_seal_id,
                    session_id.value,
                    scope.market_archive_id,
                ),
            ).fetchone()
            if root is None:
                raise RuntimeStateConflictError("retrospective archive seal/session is absent")
            if str(root[0]) != "RETROSPECTIVE_BACKFILL" or str(root[1]) != "EXPLORATORY_RETROSPECTIVE" or root[2] != scope.knowledge_cutoff:
                raise RuntimeStateConflictError("retrospective feature scope differs from Archive Authority")
            if (
                event_start < root[4]
                or event_end > root[3]
                or (root[5] is not None and root[6] is not None and event_start < root[6] and event_end > root[5])
            ):
                raise ValueError("feature interval is outside the exact trading session")
            rows = connection.execute(
                """
                SELECT bar.bar_revision_id, bar.capture_id,
                       bar.instrument_id, bar.session_id,
                       bar.event_start, bar.event_end, bar.known_at,
                       bar.open_value, bar.close_value,
                       mra.market_artifact_is_readable(
                           artifact.integrity_state, artifact.last_verified_at
                       )
                FROM mra.market_bar_revision AS bar
                JOIN mra.data_capture AS capture
                  ON capture.capture_id = bar.capture_id
                 AND capture.provider_product_id = bar.provider_product_id
                 AND capture.status = 'CAPTURED'
                JOIN mra.artifact AS artifact
                  ON artifact.artifact_id = capture.artifact_id
                WHERE bar.instrument_id = %s
                  AND bar.session_id = %s
                  AND bar.timeframe = 'MINUTE_5'
                  AND bar.price_basis = 'RAW_UNADJUSTED'
                  AND bar.event_start = %s
                  AND bar.event_end = %s
                  AND bar.decision_visible_at <= %s
                  AND EXISTS (
                      SELECT 1
                      FROM mra.market_archive_capture_observation AS observation
                      WHERE observation.market_archive_id = %s
                        AND observation.capture_id = bar.capture_id
                        AND observation.known_at <= %s
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM mra.market_bar_revision AS successor
                      WHERE successor.supersedes_revision_id = bar.bar_revision_id
                        AND successor.decision_visible_at <= %s
                  )
                ORDER BY bar.revision, bar.bar_revision_id
                """,
                (
                    instrument_id.value,
                    session_id.value,
                    event_start,
                    event_end,
                    scope.knowledge_cutoff,
                    scope.market_archive_id,
                    scope.knowledge_cutoff,
                    scope.knowledge_cutoff,
                ),
            ).fetchall()
            gaps = (
                ()
                if rows
                else connection.execute(
                    """
                    SELECT gap.gap_id, gap.capture_id, gap.instrument_id,
                           gap.session_id, gap.event_start, gap.event_end,
                           gap.known_at, gap.gap_kind, gap.reason_code
                    FROM mra.source_gap AS gap
                    WHERE gap.instrument_id = %s
                      AND gap.session_id = %s
                      AND gap.fact_kind = 'MARKET_BAR'
                      AND gap.timeframe = 'MINUTE_5'
                      AND gap.price_basis = 'RAW_UNADJUSTED'
                      AND gap.event_start = %s
                      AND gap.event_end = %s
                      AND gap.decision_visible_at <= %s
                      AND EXISTS (
                          SELECT 1
                          FROM mra.market_archive_capture_observation AS observation
                          WHERE observation.market_archive_id = %s
                            AND observation.capture_id = gap.capture_id
                            AND observation.known_at <= %s
                      )
                    ORDER BY gap.gap_id
                    """,
                    (
                        instrument_id.value,
                        session_id.value,
                        event_start,
                        event_end,
                        scope.knowledge_cutoff,
                        scope.market_archive_id,
                        scope.knowledge_cutoff,
                    ),
                ).fetchall()
            )
        if not rows:
            if not gaps:
                raise RuntimeNotFoundError(
                    "retrospective feature checkpoint has neither exact bar nor SourceGap"
                )
            if len(gaps) != 1:
                raise ArtifactIntegrityError(
                    "retrospective feature SourceGap is ambiguous at the frozen cutoff"
                )
            gap = gaps[0]
            payload = {
                "capture_id": UUID(str(gap[1])),
                "event_end": gap[5],
                "event_start": gap[4],
                "gap_id": UUID(str(gap[0])),
                "gap_kind": str(gap[7]),
                "instrument_id": instrument_id,
                "known_at": gap[6],
                "reason_code": str(gap[8]),
                "session_id": session_id,
            }
            return ExploratoryIntradayFeatureGap(
                **payload,
                content_sha256=ContentHash(canonical_json_sha256(payload)),
            )
        if len(rows) != 1:
            raise ArtifactIntegrityError("retrospective feature bar is ambiguous at the frozen cutoff")
        row = rows[0]
        if not bool(row[9]):
            raise ArtifactIntegrityError("retrospective feature Artifact is not verified and readable")
        open_value = Decimal(row[7])
        close_value = Decimal(row[8])
        move = (close_value / open_value - Decimal("1")).quantize(Decimal("0.000000000001"))
        payload = {
            "bar_revision_id": UUID(str(row[0])),
            "capture_id": UUID(str(row[1])),
            "close_value": close_value,
            "event_end": row[5],
            "event_start": row[4],
            "instrument_id": instrument_id,
            "intraday_move": move,
            "known_at": row[6],
            "open_value": open_value,
            "session_id": session_id,
        }
        return ExploratoryIntradayFeatureObservation(
            **payload,
            content_sha256=ContentHash(canonical_json_sha256(payload)),
        )


__all__ = ["PostgresExploratoryFeatureInputReadPort"]
