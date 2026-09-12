"""Exact failed-request context shared by preparation and committing owner reload."""

from datetime import datetime
from dataclasses import replace
from uuid import UUID

from market_regime_alpha.infrastructure.historical_request_failure import historical_request_failure
from market_regime_alpha.research_qualification.ports.sources import DatasetRequestFailureContext
from market_regime_alpha.runtime.errors import ArtifactIntegrityError


def read_historical_failure_requests(connection, archive_id: UUID, cutoff: datetime,
                                     gap_ids: tuple[UUID, ...] | None = None) -> dict[UUID, DatasetRequestFailureContext]:
    """Resolve original request identities without imposing a feature window."""
    rows = connection.execute("""
        SELECT gap.gap_id, slice.market_archive_slice_id, slice.content_sha256, slice.scope_key,
            slice.event_window_start, slice.event_window_end, capture.provider_product_id, capture.capture_id,
            capture.capture_key, slice.request_sha256, capture.request_hash, identifier.instrument_id, identifier.identifier_value
        FROM mra.market_archive_slice_gap binding
        JOIN mra.market_archive archive USING(market_archive_id)
        JOIN mra.market_archive_slice slice USING(market_archive_slice_id,market_archive_id)
        JOIN mra.source_gap gap USING(gap_id)
        JOIN mra.data_capture capture ON capture.capture_id=gap.capture_id
        JOIN mra.instrument_identifier identifier ON identifier.identifier_scheme='BAOSTOCK'
            AND identifier.identifier_value=split_part(slice.scope_key,':',2)
        WHERE binding.market_archive_id=%s AND archive.lane='RETROSPECTIVE_BACKFILL' AND archive.price_basis='MIXED_EXPLICIT'
            AND gap.fact_kind='DATA_CAPTURE' AND gap.gap_kind='PROVIDER_FAILURE' AND capture.status='PROVIDER_FAILURE'
            AND capture.provider_product_id=archive.provider_product_id AND gap.known_at<=%s AND capture.recorded_at<=%s
            AND slice.expected_fact_kind='MARKET_BAR'
            AND (%s::uuid[] IS NULL OR gap.gap_id=ANY(%s))
            AND EXISTS (SELECT 1 FROM mra.market_capture_instrument_identifier_normalization source
                JOIN mra.market_archive_capture_observation observation USING(capture_id)
                WHERE source.instrument_identifier_id=identifier.instrument_identifier_id
                AND observation.market_archive_id=archive.market_archive_id AND observation.known_at<=%s)
        ORDER BY gap.gap_id
        """, (archive_id,cutoff,cutoff,None if gap_ids is None else list(gap_ids),
            None if gap_ids is None else list(gap_ids),cutoff)).fetchall()
    result = {}
    for row in rows:
        if row[0] in result:
            raise ArtifactIntegrityError("historical failed request has ambiguous original instrument/slice bindings")
        result[row[0]] = historical_request_failure(slice_id=row[1],slice_sha256=row[2],scope_key=row[3],
            window_start=row[4],window_end=row[5],product_id=row[6],capture_id=row[7],capture_key=row[8],
            slice_request_sha256=row[9],capture_request_sha256=row[10],instrument_id=row[11],identifier=row[12])
    return result


def read_historical_failures(connection, archive_id: UUID, cutoff: datetime,
                            event_cutoff: datetime,
                            gap_ids: tuple[UUID, ...] | None = None) -> dict[UUID, DatasetRequestFailureContext]:
    result = read_historical_failure_requests(connection, archive_id, cutoff, gap_ids)
    if result:
        calendars = connection.execute("""SELECT instrument_id,session_id,close_at FROM (
            SELECT instrument.instrument_id,session.session_id,session.close_at,
                row_number() OVER (PARTITION BY instrument.instrument_id ORDER BY session.session_date DESC) AS position
            FROM mra.instrument instrument JOIN mra.trading_session session ON session.exchange=instrument.exchange
            WHERE instrument.instrument_id=ANY(%s) AND session.close_at<=%s
            AND EXISTS (SELECT 1 FROM mra.market_capture_trading_session_normalization binding
                JOIN mra.market_archive_capture_observation observation USING(capture_id)
                WHERE binding.session_id=session.session_id AND observation.market_archive_id=%s AND observation.known_at<=%s)
            ) current_window WHERE position<=21 ORDER BY instrument_id,close_at""",
            (list({context.instrument_id for context in result.values()}),event_cutoff,archive_id,cutoff)).fetchall()
        result = {gap:replace(context,closed_sessions=tuple((row[1],row[2]) for row in calendars if row[0]==context.instrument_id)) for gap,context in result.items()}
    return result
