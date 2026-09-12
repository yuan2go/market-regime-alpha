"""One bounded read preparation per Dataset; bytes verified after connection release."""

from datetime import date
from uuid import UUID

from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.postgres.queries.historical_failures import read_historical_failures
from market_regime_alpha.research_qualification.domain.backtest_dataset import BacktestFeatureDependency as Dependency, BacktestFeatureLineageKind as Kind
from market_regime_alpha.research_qualification.domain.exploratory import ExploratoryRetrospectiveDatasetScope
from market_regime_alpha.research_qualification.domain.historical_features import HistoricalDailyPoint
from market_regime_alpha.research_qualification.ports.artifacts import ResearchArtifactByteStore
from market_regime_alpha.research_qualification.ports.historical_features import HistoricalFeatureSnapshot
from market_regime_alpha.runtime.errors import ArtifactIntegrityError, RuntimeStateConflictError


class PostgresHistoricalFeatureInputReadPort:
    def __init__(self, pool: TargetPostgresPool, byte_store: ResearchArtifactByteStore) -> None:
        self._pool, self._bytes = pool, byte_store

    def snapshot(self, *, scope: ExploratoryRetrospectiveDatasetScope,
                 instruments: tuple[UUID, ...], session_date: date) -> HistoricalFeatureSnapshot:
        if not instruments or len(instruments) > 500 or len(set(instruments)) != len(instruments):
            raise ValueError("historical input requires 1..500 unique population members")
        with self._pool.connection(read_only=True) as connection:
            archive = connection.execute("""
                SELECT archive.provider_product_id, archive.exchange_code
                FROM mra.market_archive archive JOIN mra.market_archive_seal seal USING (market_archive_id)
                WHERE archive.market_archive_id=%s AND seal.market_archive_seal_id=%s AND seal.knowledge_cutoff=%s
                  AND archive.lane='RETROSPECTIVE_BACKFILL' AND archive.evidence_class='EXPLORATORY_RETROSPECTIVE'
                  AND archive.price_basis='MIXED_EXPLICIT'
                """, (scope.market_archive_id, scope.market_archive_seal_id, scope.knowledge_cutoff)).fetchone()
            if archive is None:
                raise RuntimeStateConflictError("exact sealed mixed historical price inventory is absent")
            roster = connection.execute("""
                SELECT instrument.instrument_id, instrument.exchange FROM mra.instrument instrument
                WHERE instrument.instrument_id=ANY(%s)
                  AND EXISTS (SELECT 1 FROM mra.market_capture_instrument_normalization binding
                    JOIN mra.market_archive_capture_observation observation USING (capture_id)
                    WHERE binding.instrument_id=instrument.instrument_id AND observation.market_archive_id=%s AND observation.known_at<=%s)
                """, (list(instruments), scope.market_archive_id, scope.knowledge_cutoff)).fetchall()
            if {row[0] for row in roster} != set(instruments):
                raise RuntimeStateConflictError("historical population lacks exact archive instrument bindings")
            exchanges = {row[1] for row in roster}
            calendar_rows = connection.execute("""
                SELECT session_date, session_id, close_at, exchange FROM (
                SELECT session_date, session_id, close_at, exchange,
                    row_number() OVER (PARTITION BY exchange ORDER BY session_date DESC) AS position
                FROM mra.trading_session session
                WHERE exchange=ANY(%s) AND session_date<=%s
                  AND EXISTS (SELECT 1 FROM mra.market_capture_trading_session_normalization binding
                    JOIN mra.market_archive_capture_observation observation USING (capture_id)
                    WHERE binding.session_id=session.session_id AND observation.market_archive_id=%s AND observation.known_at<=%s)
                ) calendar WHERE position<=21 ORDER BY exchange, session_date
                """, (sorted(exchanges), session_date, scope.market_archive_id, scope.knowledge_cutoff)).fetchall()
            by_exchange = {exchange: [s for s in calendar_rows if s[3] == exchange] for exchange in exchanges}
            sessions = by_exchange[sorted(exchanges)[0]]
            if any(tuple((s[0], s[2]) for s in rows) != tuple((s[0], s[2]) for s in sessions) for rows in by_exchange.values()):
                raise RuntimeStateConflictError("historical cross-exchange Calendar dates/closes do not align")
            if not sessions or sessions[-1][0] != session_date or sessions[-1][2] > scope.simulated_event_cutoff:
                raise RuntimeStateConflictError("historical feature session absent or exceeds event cutoff")
            session_ids = [s[1] for s in calendar_rows]
            bars = connection.execute("""
                SELECT bar.instrument_id, session.session_date, bar.price_basis, bar.bar_revision_id,
                       bar.open_value, bar.close_value, bar.volume_value, bar.turnover_value,
                       artifact.content_sha256, artifact.size_bytes,
                       mra.market_artifact_is_readable(artifact.integrity_state, artifact.last_verified_at)
                FROM mra.market_bar_revision bar JOIN mra.trading_session session USING (session_id)
                JOIN mra.data_capture capture ON capture.capture_id=bar.capture_id AND capture.status='CAPTURED'
                JOIN mra.artifact artifact ON artifact.artifact_id=capture.artifact_id
                WHERE bar.provider_product_id=%s AND bar.instrument_id=ANY(%s) AND bar.session_id=ANY(%s)
                  AND bar.timeframe='DAILY' AND bar.price_basis IN ('RAW_UNADJUSTED','BACKWARD_ADJUSTED')
                  AND bar.event_start=session.open_at AND bar.event_end=session.close_at
                  AND bar.event_end<=%s AND bar.decision_visible_at<=%s AND bar.recorded_at<=%s AND capture.recorded_at<=%s
                  AND EXISTS (SELECT 1 FROM mra.market_archive_capture_observation observation
                    WHERE observation.capture_id=bar.capture_id AND observation.market_archive_id=%s AND observation.known_at<=%s)
                  AND NOT EXISTS (SELECT 1 FROM mra.market_bar_revision successor
                    WHERE successor.supersedes_revision_id=bar.bar_revision_id AND successor.decision_visible_at<=%s)
                ORDER BY bar.instrument_id, session.session_date, bar.price_basis, bar.bar_revision_id
                """, (archive[0], list(instruments), session_ids, scope.simulated_event_cutoff,
                    scope.knowledge_cutoff, scope.knowledge_cutoff, scope.knowledge_cutoff,
                    scope.market_archive_id, scope.knowledge_cutoff, scope.knowledge_cutoff)).fetchall()
            gaps = connection.execute("""
                SELECT gap.instrument_id, session.session_date, gap.price_basis, gap.gap_id, gap.gap_kind
                FROM mra.source_gap gap JOIN mra.trading_session session USING (session_id)
                WHERE gap.provider_product_id=%s AND gap.instrument_id=ANY(%s) AND gap.session_id=ANY(%s)
                  AND gap.fact_kind='MARKET_BAR' AND gap.timeframe='DAILY'
                  AND gap.price_basis IN ('RAW_UNADJUSTED','BACKWARD_ADJUSTED')
                  AND gap.decision_visible_at<=%s AND gap.recorded_at<=%s AND gap.event_end<=%s
                  AND EXISTS (SELECT 1 FROM mra.market_archive_capture_observation observation
                    WHERE observation.capture_id=gap.capture_id AND observation.market_archive_id=%s AND observation.known_at<=%s)
                """, (archive[0], list(instruments), session_ids, scope.knowledge_cutoff, scope.knowledge_cutoff,
                    scope.simulated_event_cutoff, scope.market_archive_id, scope.knowledge_cutoff)).fetchall()
            failures = read_historical_failures(connection, scope.market_archive_id, scope.knowledge_cutoff, scope.simulated_event_cutoff)
        for digest, size, readable in {(str(b[8]), int(b[9]), bool(b[10])) for b in bars}:
            if not readable:
                raise ArtifactIntegrityError("historical feature source is not verified/readable")
            self._bytes.read_bytes(digest, expected_size=size)
        by_key: dict[tuple[UUID, date, str], list[tuple]] = {}
        gap_by_key: dict[tuple[UUID, date, str], list[tuple]] = {}
        for row in bars:
            by_key.setdefault((row[0], row[1], str(row[2])), []).append(row)
        for row in gaps:
            gap_by_key.setdefault((row[0], row[1], str(row[2])), []).append(row)
        dependencies, problems, population = {}, {}, {}
        instrument_exchanges = dict(roster)
        for instrument in instruments:
            points = []
            for day, sid, _close, _exchange in by_exchange[instrument_exchanges[instrument]]:
                exact = {}
                for basis in ("RAW_UNADJUSTED", "BACKWARD_ADJUSTED"):
                    key = (instrument, day, basis)
                    rows, missing = by_key.get(key, []), gap_by_key.get(key, [])
                    failed_requests = tuple(gap for gap, context in failures.items() if context.instrument_id==instrument
                        and context.price_basis==basis and context.window_start.date()<=day<=context.window_end.date())
                    dependencies[key] = (Dependency(Kind.TRADING_SESSION, sid),
                        *(Dependency(Kind.BAR_REVISION, b[3]) for b in rows),
                        *(Dependency(Kind.SOURCE_GAP, g[3]) for g in missing),
                        *(Dependency(Kind.SOURCE_GAP, gap) for gap in failed_requests))
                    if len(rows) == 1 and not missing and not failed_requests:
                        exact[basis] = rows[0]
                    else:
                        problems[key] = ("FEATURE_INPUT_CONFLICT" if len(rows) > 1 or (rows and missing) or len(missing) > 1
                            or any(g[4] in {"CONFLICT", "INVALID_OHLC"} for g in missing)
                            else "FEATURE_PROVIDER_UNKNOWN" if failed_requests or (missing and missing[0][4] == "PROVIDER_FAILURE")
                            else "FEATURE_INPUT_MISSING")
                raw, adj = exact.get("RAW_UNADJUSTED"), exact.get("BACKWARD_ADJUSTED")
                points.append(HistoricalDailyPoint(day, None if raw is None else raw[4], None if raw is None else raw[5],
                    None if adj is None else adj[5], None if raw is None else raw[6], None if raw is None else raw[7]))
            population[instrument] = tuple(points)
        return HistoricalFeatureSnapshot(tuple((s[0], s[1], s[2]) for s in sessions), population, dependencies, problems, frozenset(failures))
