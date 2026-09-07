"""Exact DAILY facts: a sealed archive is never an actual-time fallback."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.research_qualification.domain.daily_inputs import DailyInputMember, DailyInputState
from market_regime_alpha.research_qualification.domain.exploratory import ExploratoryRetrospectiveDatasetScope
from market_regime_alpha.research_qualification.ports.artifacts import ResearchArtifactByteStore
from market_regime_alpha.runtime.errors import ArtifactIntegrityError, RuntimeStateConflictError
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.identity import InstrumentId
from market_regime_alpha.shared.time import require_utc


class PostgresDailyFeatureInputReadPort:
    def __init__(self, pool: TargetPostgresPool, byte_store: ResearchArtifactByteStore) -> None:
        self._pool = pool
        self._byte_store = byte_store

    def archived(self, *, scope: ExploratoryRetrospectiveDatasetScope, instrument_id: InstrumentId, session_date: date) -> DailyInputMember:
        with self._pool.connection(read_only=True) as connection:
            root = connection.execute(
                """
                SELECT archive.provider_product_id, session.session_id, session.close_at
                FROM mra.market_archive archive
                JOIN mra.market_archive_seal seal USING (market_archive_id)
                JOIN mra.instrument instrument ON instrument.instrument_id = %s
                JOIN mra.trading_session session ON session.exchange = instrument.exchange AND session.session_date = %s
                WHERE archive.market_archive_id = %s AND seal.market_archive_seal_id = %s
                  AND archive.lane = 'RETROSPECTIVE_BACKFILL'
                  AND archive.evidence_class = 'EXPLORATORY_RETROSPECTIVE'
                  AND seal.knowledge_cutoff = %s
                  AND EXISTS (SELECT 1 FROM mra.market_capture_instrument_normalization binding
                    JOIN mra.market_archive_capture_observation observation USING (capture_id)
                    WHERE binding.instrument_id = instrument.instrument_id
                      AND observation.market_archive_id = archive.market_archive_id AND observation.known_at <= %s)
                  AND EXISTS (SELECT 1 FROM mra.market_capture_trading_session_normalization binding
                    JOIN mra.market_archive_capture_observation observation USING (capture_id)
                    WHERE binding.session_id = session.session_id
                      AND observation.market_archive_id = archive.market_archive_id AND observation.known_at <= %s)
                """,
                (
                    instrument_id.value,
                    session_date,
                    scope.market_archive_id,
                    scope.market_archive_seal_id,
                    scope.knowledge_cutoff,
                    scope.knowledge_cutoff,
                    scope.knowledge_cutoff,
                ),
            ).fetchone()
        if root is None or root[2] > scope.simulated_event_cutoff:
            raise RuntimeStateConflictError("exact historical daily archive/session scope is absent or incomplete")
        return self._read(UUID(str(root[0])), UUID(str(root[1])), (instrument_id.value,), scope.knowledge_cutoff, scope.market_archive_id)[
            0
        ]

    def visible(
        self, *, provider_product_id: UUID, session_id: UUID, instrument_ids: tuple[UUID, ...], input_cutoff: datetime
    ) -> tuple[DailyInputMember, ...]:
        return self._read(provider_product_id, session_id, instrument_ids, input_cutoff, None)

    def _read(
        self, product: UUID, session: UUID, instruments: tuple[UUID, ...], cutoff: datetime, archive: UUID | None
    ) -> tuple[DailyInputMember, ...]:
        require_utc(cutoff, field="input_cutoff")
        if not instruments or len(set(instruments)) != len(instruments):
            raise ValueError("daily input requires an exact unique instrument roster")
        with self._pool.connection(read_only=True) as connection:
            if archive is None:
                clock = connection.execute("SELECT clock_timestamp()").fetchone()
                if clock is None or cutoff > clock[0]:
                    raise RuntimeStateConflictError("actual daily input cutoff cannot be in the future")
            session_row = connection.execute(
                """
                SELECT open_at, close_at FROM mra.trading_session session WHERE session_id = %s
                AND EXISTS (SELECT 1 FROM mra.market_capture_trading_session_normalization binding
                    JOIN mra.data_capture capture USING (capture_id)
                    WHERE binding.session_id = session.session_id AND capture.status = 'CAPTURED'
                      AND capture.recorded_at <= %s)
                """,
                (session, cutoff),
            ).fetchone()
            if session_row is None or session_row[1] > cutoff:
                raise RuntimeStateConflictError("daily input session is absent or has not closed")
            rows = connection.execute(
                """
                SELECT bar.instrument_id, bar.bar_revision_id, bar.capture_id,
                       bar.known_at, bar.recorded_at, bar.event_start, bar.event_end,
                       bar.open_value, bar.close_value, artifact.content_sha256,
                       artifact.size_bytes, mra.market_artifact_is_readable(artifact.integrity_state, artifact.last_verified_at)
                FROM mra.market_bar_revision bar
                JOIN mra.data_capture capture ON capture.capture_id = bar.capture_id
                  AND capture.provider_product_id = bar.provider_product_id AND capture.status = 'CAPTURED'
                JOIN mra.artifact artifact ON artifact.artifact_id = capture.artifact_id
                WHERE bar.provider_product_id = %s AND bar.session_id = %s AND bar.instrument_id = ANY(%s)
                  AND bar.timeframe = 'DAILY' AND bar.price_basis = 'RAW_UNADJUSTED'
                  AND bar.event_start = %s AND bar.event_end = %s AND bar.decision_visible_at <= %s
                  AND bar.recorded_at <= %s AND capture.recorded_at <= %s
                  AND (%s::uuid IS NULL OR EXISTS (SELECT 1 FROM mra.market_archive_capture_observation observation
                       WHERE observation.market_archive_id = %s AND observation.capture_id = bar.capture_id AND observation.known_at <= %s))
                  AND NOT EXISTS (SELECT 1 FROM mra.market_bar_revision successor
                       WHERE successor.supersedes_revision_id = bar.bar_revision_id AND successor.decision_visible_at <= %s)
                ORDER BY bar.instrument_id, bar.bar_revision_id
                """,
                (product, session, list(instruments), *session_row, cutoff, cutoff, cutoff, archive, archive, cutoff, cutoff),
            ).fetchall()
            gaps = connection.execute(
                """
                SELECT gap.instrument_id, gap.gap_id, gap.capture_id, gap.known_at, gap.recorded_at,
                       gap.event_start, gap.event_end, gap.gap_kind, gap.reason_code
                FROM mra.source_gap gap
                JOIN mra.data_capture capture ON capture.capture_id = gap.capture_id AND capture.provider_product_id = gap.provider_product_id
                WHERE gap.provider_product_id = %s AND gap.session_id = %s AND gap.instrument_id = ANY(%s)
                  AND gap.fact_kind = 'MARKET_BAR' AND gap.timeframe = 'DAILY' AND gap.price_basis = 'RAW_UNADJUSTED'
                  AND gap.event_start = %s AND gap.event_end = %s AND gap.decision_visible_at <= %s AND gap.recorded_at <= %s
                  AND (%s::uuid IS NULL OR EXISTS (SELECT 1 FROM mra.market_archive_capture_observation observation
                       WHERE observation.market_archive_id = %s AND observation.capture_id = gap.capture_id AND observation.known_at <= %s))
                ORDER BY gap.instrument_id, gap.gap_id
                """,
                (product, session, list(instruments), *session_row, cutoff, cutoff, archive, archive, cutoff),
            ).fetchall()
        # Physical I/O never holds the read connection or a business transaction.
        for content, size in {(str(row[9]), int(row[10])) for row in rows}:
            self._byte_store.read_bytes(content, expected_size=size)
        result = []
        for instrument in instruments:
            bars = [row for row in rows if row[0] == instrument]
            missing = [row for row in gaps if row[0] == instrument]
            if len(bars) > 1 or (not bars and len(missing) > 1):
                result.append(DailyInputMember(instrument, DailyInputState.CONFLICT, "AMBIGUOUS_DAILY_SOURCE"))
            elif bars:
                row = bars[0]
                if not row[11]:
                    raise ArtifactIntegrityError("daily Feature Artifact is not verified/readable")
                result.append(
                    DailyInputMember(
                        instrument,
                        DailyInputState.AVAILABLE,
                        "EXACT_DAILY_BAR",
                        row[1],
                        row[2],
                        canonical_json_sha256(tuple(row[:11])),
                        row[3],
                        row[4],
                        row[5],
                        row[6],
                        Decimal(row[7]),
                        Decimal(row[8]),
                    )
                )
            elif missing:
                row = missing[0]
                state = {
                    "PROVIDER_FAILURE": DailyInputState.UNKNOWN,
                    "CONFLICT": DailyInputState.CONFLICT,
                    "INVALID_OHLC": DailyInputState.CONFLICT,
                }.get(str(row[7]), DailyInputState.MISSING)
                result.append(
                    DailyInputMember(
                        instrument,
                        state,
                        str(row[8]),
                        capture_id=row[2],
                        source_sha256=canonical_json_sha256(tuple(row)),
                        known_at=row[3],
                        recorded_at=row[4],
                        event_start=row[5],
                        event_end=row[6],
                        source_gap_id=row[1],
                    )
                )
            else:
                result.append(DailyInputMember(instrument, DailyInputState.MISSING, "EXACT_DAILY_SOURCE_ABSENT"))
        return tuple(result)
