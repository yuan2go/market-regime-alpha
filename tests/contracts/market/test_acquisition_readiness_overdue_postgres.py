"""Exact overdue SELECT over temporary relations, never canonical live evidence."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import psycopg

from market_regime_alpha.infrastructure.postgres.repositories.market_archive import PostgresArchiveRepository


class _TemporaryConnection:
    def __init__(self, connection):
        self.connection = connection

    def execute(self, query, parameters=None):
        return self.connection.execute(query.replace("mra.", "pg_temp."), parameters)


def test_raw_capture_without_normalization_remains_visible_when_archive_window_becomes_missed(target_database_url):
    root, elapsed, future, capture = (uuid4() for _ in range(4))
    now = datetime.now(UTC)
    with psycopg.connect(target_database_url) as connection:
        connection.execute("CREATE TEMP TABLE market_archive_slice(market_archive_slice_id uuid PRIMARY KEY,event_window_end timestamptz)")
        connection.execute("CREATE TEMP TABLE prospective_archive_slice_schedule(market_archive_slice_id uuid PRIMARY KEY,market_archive_id uuid,ordinal int)")
        connection.execute("CREATE TEMP TABLE prospective_archive_slice_terminal(market_archive_slice_id uuid PRIMARY KEY,market_archive_id uuid,terminal_state text,reason_code text)")
        connection.execute("CREATE TEMP TABLE raw_capture(capture_id uuid,market_archive_slice_id uuid,readiness_state text,normalized_observation_count int)")
        connection.execute("INSERT INTO market_archive_slice VALUES (%s,%s),(%s,%s)", (elapsed, now-timedelta(seconds=1), future, now+timedelta(days=1)))
        connection.execute("INSERT INTO prospective_archive_slice_schedule VALUES (%s,%s,1),(%s,%s,2)", (elapsed,root,future,root))
        connection.execute("INSERT INTO raw_capture VALUES (%s,%s,'NO_MATURE_INTERVAL',0)", (capture,elapsed))
        repository = PostgresArchiveRepository(_TemporaryConnection(connection))
        # Terminal persistence is a fixture seam; selection executes the unchanged
        # production owner SQL, which asks for qualified observations, not raw I/O.
        repository._insert_terminal = lambda archive_id, slice_id, state, reason: connection.execute(
            "INSERT INTO prospective_archive_slice_terminal VALUES (%s,%s,%s,%s)", (slice_id,archive_id,state,reason))
        assert repository.finalize_overdue(root) == (elapsed,)
        assert repository.finalize_overdue(root) == (elapsed,)
        assert connection.execute("SELECT terminal_state,reason_code FROM prospective_archive_slice_terminal").fetchall() == [("MISSED", "CAPTURE_WINDOW_ELAPSED")]
        assert connection.execute("SELECT capture_id,readiness_state,normalized_observation_count FROM raw_capture").fetchall() == [(capture,"NO_MATURE_INTERVAL",0)]
