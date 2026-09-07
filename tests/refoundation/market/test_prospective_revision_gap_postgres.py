"""Synthetic disposable 2099 windows; no real timeliness or Provider proof."""
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row
import pytest

from market_regime_alpha.infrastructure.postgres.evidence_backup import _table_hashes
from market_regime_alpha.market.application import RecordArchiveCaptureObservationRequest
from market_regime_alpha.market.domain import NormalizationBatch, MarketBarRevision, BarTimeframe, PriceBasis
from market_regime_alpha.market.ports import CaptureRequest
from market_regime_alpha.runtime.errors import RuntimeStateConflictError
from market_regime_alpha.shared.financial import Money, Quantity, QuantityUnit
from tests.refoundation.market.prospective_health_fixture import canonical_prospective_stack as _fixture
from tests.refoundation.market.test_archive_postgres import _CapturedGapNormalizer
from tests.refoundation.research_qualification import test_research_postgres as research


@pytest.fixture
def canonical_prospective_stack(target_database_url, tmp_path, request):
    yield from _fixture.__wrapped__(target_database_url, tmp_path, request)


def _context(key):
    return research._context('revision-gap:' + key, 'SYNTHETIC_REVISION_GAP_TEST')


def _record_gap(fixture, index):
    slot = fixture.manifest.slices[index]
    capture = fixture.stack.market.capture(
        CaptureRequest(fixture.stack.product.provider_product_id, f'gap-{index}', f'fixture://gap-{index}', '2'*64),
        research._BytesProvider(), _context(f'gap-capture-{index}'),
    ).capture
    fixture.stack.market.normalize(capture.capture_id, _CapturedGapNormalizer(), _context(f'gap-normalize-{index}'))
    with fixture.pool.connection(read_only=True) as connection:
        gap_id = connection.execute('SELECT gap_id FROM mra.source_gap WHERE capture_id=%s', (capture.capture_id,)).fetchone()[0]
    fixture.application.market_archives.record_slice_gap(
        market_archive_id=fixture.manifest.start_request.market_archive_id,
        market_archive_slice_id=slot.plan.market_archive_slice_id, gap_id=gap_id,
        terminal_status='GAP_RECORDED', context=_context(f'gap-terminal-{index}'),
    )


def _normalized_capture(fixture, index):
    slot = fixture.manifest.slices[index]
    capture = fixture.stack.market.capture(
        CaptureRequest(fixture.stack.product.provider_product_id, f'capture-{index}', f'fixture://bar-{index}', '3'*64),
        research._BytesProvider(), _context(f'capture-{index}'),
    ).capture
    observed_at = slot.plan.event_window_start + timedelta(seconds=5)
    # Test-only known-time injection, after exact disposable fixture identity check.
    # PG clock and any real evidence are untouched. Market/Archive owners still
    # validate normalized lineage and execute the actual closure transaction.
    with fixture.pool.connection() as connection:
        assert connection.execute('SELECT current_database()').fetchone()[0] == conninfo_to_dict(fixture.settings.database_url)['dbname']
        connection.execute('ALTER TABLE mra.data_capture DISABLE TRIGGER ALL')
        connection.execute('UPDATE mra.data_capture SET capture_started_at=%s,capture_completed_at=%s,recorded_at=%s,known_at=%s,decision_visible_at=%s WHERE capture_id=%s', (observed_at, observed_at, observed_at, observed_at, observed_at, capture.capture_id))
        connection.execute('ALTER TABLE mra.data_capture ENABLE TRIGGER ALL')
        connection.commit()
    schedule = fixture.manifest.start_request.prospective_generation.schedules[index]
    with fixture.pool.connection(read_only=True) as connection:
        session_close = connection.execute('SELECT close_at FROM mra.trading_session WHERE session_id=%s', (schedule.trading_session_id,)).fetchone()[0]
    event_end = min(slot.plan.event_window_start, session_close)
    fixture.stack.market.normalize(capture.capture_id, research._Normalizer(lambda source: NormalizationBatch(
        source_capture_id=source.capture_id, source_provider_product_id=source.provider_product_id,
        bars=(MarketBarRevision(
            bar_revision_id=uuid4(), provider_product_id=source.provider_product_id,
            capture_id=source.capture_id, instrument_id=fixture.stack.instrument_id,
            session_id=schedule.trading_session_id, timeframe=BarTimeframe.MINUTE_5,
            price_basis=PriceBasis.RAW_UNADJUSTED,
            event_start=event_end-timedelta(minutes=5), event_end=event_end,
            revision=1, supersedes_revision_id=None,
            open=Money(Decimal('10'), 'CNY'), high=Money(Decimal('10'), 'CNY'),
            low=Money(Decimal('10'), 'CNY'), close=Money(Decimal('10'), 'CNY'),
            volume=Quantity(Decimal('100'), QuantityUnit.SHARES), turnover=None,
        ),),
    )), _context(f'normalize-{index}'))
    return RecordArchiveCaptureObservationRequest(
        fixture.manifest.start_request.market_archive_id, slot.plan.market_archive_slice_id,
        capture.capture_id, slot.schedule_slot, slot.plan.event_window_start,
    )


def _record(fixture, index):
    request = _normalized_capture(fixture, index)
    return fixture.application.market_archives.record_capture_observation(request, _context(f'observation-{index}'))


def test_later_first_capture_after_first_comparison_gap_closes_and_replays(canonical_prospective_stack):
    fixture = canonical_prospective_stack
    _record_gap(fixture, 0)
    request = _normalized_capture(fixture, 1)
    result = fixture.application.market_archives.record_capture_observation(request, _context('observation-1'))
    assert result.timeliness == 'ON_TIME'
    with fixture.pool.connection(read_only=True) as connection:
        before = _table_hashes(connection)
        row = connection.execute('SELECT comparison_ordinal, predecessor_observation_id, relation FROM mra.prospective_archive_revision_observation').fetchone()
        assert row == (2, None, 'FIRST')
        assert connection.execute('SELECT terminal_state FROM mra.prospective_archive_slice_terminal ORDER BY terminal_state').fetchall() == [('CAPTURED_ON_TIME',), ('PROVIDER_GAP',)]
    repeated = fixture.application.market_archives.record_capture_observation(request, _context('observation-1'))
    assert repeated.market_archive_capture_observation_id == result.market_archive_capture_observation_id
    with fixture.pool.connection(read_only=True) as connection:
        assert _table_hashes(connection) == before


def test_success_gap_success_retains_latest_actual_predecessor_and_prior_hash(canonical_prospective_stack):
    fixture = canonical_prospective_stack
    first = _record(fixture, 0)
    with fixture.pool.connection(read_only=True) as connection:
        before = connection.execute('SELECT * FROM mra.prospective_archive_revision_observation WHERE comparison_ordinal=1').fetchone()
    _record_gap(fixture, 1)
    _record(fixture, 2)
    with fixture.pool.connection(read_only=True) as connection:
        assert connection.execute('SELECT * FROM mra.prospective_archive_revision_observation WHERE comparison_ordinal=1').fetchone() == before
        assert connection.execute('SELECT comparison_ordinal, predecessor_observation_id, relation FROM mra.prospective_archive_revision_observation ORDER BY comparison_ordinal').fetchall() == [
            (1, None, 'FIRST'), (3, first.market_archive_capture_observation_id, 'CHANGED'),
        ]


def test_unresolved_expected_comparison_cannot_be_silently_skipped(canonical_prospective_stack):
    fixture = canonical_prospective_stack
    request = _normalized_capture(fixture, 1)
    with fixture.pool.connection(read_only=True) as connection:
        before = _table_hashes(connection)
    with pytest.raises(RuntimeStateConflictError) as rejected:
        fixture.application.market_archives.record_capture_observation(request, _context('unresolved-observation'))
    assert 'unresolved expected window' in str(rejected.value.__cause__)
    with fixture.pool.connection(read_only=True) as connection:
        assert _table_hashes(connection) == before


@pytest.mark.parametrize('damage', ('predecessor', 'ordinal', 'relation', 'content'))
def test_gapped_revision_still_rejects_wrong_exact_inputs(canonical_prospective_stack, damage):
    fixture = canonical_prospective_stack
    _record(fixture, 0)
    _record_gap(fixture, 1)
    _record(fixture, 2)
    # Independently isolated corruption fixture: remove only the last revision,
    # retain its actual Capture/Observation, then exercise the real INSERT guard.
    with fixture.pool.connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            row = cursor.execute('SELECT * FROM mra.prospective_archive_revision_observation WHERE comparison_ordinal=3').fetchone()
        connection.execute('ALTER TABLE mra.prospective_archive_revision_observation DISABLE TRIGGER ALL')
        connection.execute('DELETE FROM mra.prospective_archive_revision_observation WHERE comparison_ordinal=3')
        connection.execute('ALTER TABLE mra.prospective_archive_revision_observation ENABLE TRIGGER ALL')
        connection.commit()
    if damage == 'predecessor':
        row['predecessor_observation_id'] = uuid4()
    elif damage == 'ordinal':
        row['comparison_ordinal'] = 2
    elif damage == 'relation':
        row['relation'] = 'IDENTICAL'
    else:
        row['content_sha256'] = 'a'*64
    with fixture.pool.connection(read_only=True) as connection:
        before = _table_hashes(connection)
    with pytest.raises(psycopg.Error) as rejected, fixture.pool.connection() as connection:
        connection.execute(psycopg.sql.SQL('INSERT INTO mra.prospective_archive_revision_observation ({}) VALUES ({})').format(
            psycopg.sql.SQL(',').join(map(psycopg.sql.Identifier, row)),
            psycopg.sql.SQL(',').join(psycopg.sql.Placeholder() for _ in row),
        ), tuple(row.values()))
    assert rejected.value.sqlstate == '55000'
    assert ('hash is invalid' if damage == 'content' else 'chain is invalid') in str(rejected.value)
    with fixture.pool.connection(read_only=True) as connection:
        assert _table_hashes(connection) == before
