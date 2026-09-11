"""SQL scope/performance fixture, not canonical research or operational evidence."""

from contextlib import contextmanager
from uuid import UUID

import psycopg
import pytest

from market_regime_alpha.infrastructure.postgres.queries import daily_predictions
from market_regime_alpha.runtime.errors import ArtifactIntegrityError


class _TemporaryQueryConnection:
    def __init__(self, connection):
        self.connection = connection

    def execute(self, query, parameters=None):
        return self.connection.execute(query.replace("mra.", "pg_temp."), parameters)


@contextmanager
def _health_relations(database_url, *, malformed=False):
    # The exact SELECT executes against isolated per-connection relations. This
    # fixture intentionally does not claim owner-written research facts.
    with psycopg.connect(database_url) as connection:
        connection.execute("""CREATE TEMP TABLE command_receipt (
            command_kind text, scope_id text, idempotency_key text,
            status text, result_aggregate_kind text)""")
        connection.execute("""CREATE UNIQUE INDEX command_receipt_idempotency_uk
            ON command_receipt(command_kind,scope_id,idempotency_key)""")
        connection.execute("""CREATE TEMP TABLE runtime_schedule (
            schedule_id uuid PRIMARY KEY, schedule_code text)""")
        connection.execute("""CREATE TEMP TABLE runtime_run (
            run_id uuid PRIMARY KEY, schedule_id uuid, fire_key text, state text)""")
        connection.execute("CREATE INDEX runtime_run_schedule_idx ON runtime_run(schedule_id)")
        connection.execute("""INSERT INTO command_receipt
            SELECT 'OTHER_COMMAND',i::text,'unrelated:'||i,'SUCCEEDED','OTHER'
            FROM generate_series(1,112247) i""")
        connection.execute("""INSERT INTO command_receipt
            SELECT 'REGISTER_ARTIFACT',i::text,'unrelated-artifact:'||i,'SUCCEEDED','ARTIFACT'
            FROM generate_series(1,3892) i""")
        use_ids = (UUID(int=101), UUID(int=102))
        for use_id in use_ids:
            connection.execute("INSERT INTO runtime_schedule VALUES (%s,%s)", (use_id, "daily-outcome-" + use_id.hex))
        for number, state in enumerate(("SUCCEEDED",) * 5 + ("FAILED", "WAITING"), start=1):
            connection.execute("INSERT INTO runtime_run VALUES (%s,%s,%s,%s)",
                (UUID(int=number), use_ids[number % 2], "daily-outcome:" + str(UUID(int=number)), state))
        receipts = (
            (1, "review-a", "SUCCEEDED", "ARTIFACT"),
            (1, "review-b", "SUCCEEDED", "ARTIFACT"),  # multiple reviews still count one Run
            (2, "review", "SUCCEEDED", "ARTIFACT"),
            (3, "failed-review", "FAILED", "ARTIFACT"),
            (6, "terminal-run-review", "SUCCEEDED", "ARTIFACT"),
            (7, "waiting-run-review", "SUCCEEDED", "ARTIFACT"),
            (99, "foreign-review", "SUCCEEDED", "OTHER"),
        )
        for number, suffix, state, kind in receipts:
            connection.execute("INSERT INTO command_receipt VALUES ('REGISTER_ARTIFACT',%s,%s,%s,%s)",
                (suffix, f"daily:{UUID(int=number)}:research-disposition:{suffix}", state, kind))
        # A longer identity sharing a prefix is not the exact Prediction.
        connection.execute("INSERT INTO command_receipt VALUES ('REGISTER_ARTIFACT','prefix',%s,'SUCCEEDED','ARTIFACT')",
            (f"daily:{UUID(int=4)}-other:research-disposition:review",))
        if malformed:
            connection.execute("INSERT INTO command_receipt VALUES ('REGISTER_ARTIFACT','malformed',%s,'SUCCEEDED','OTHER')",
                (f"daily:{UUID(int=3)}:research-disposition:invalid-kind",))
        connection.execute("ANALYZE command_receipt")
        connection.execute("ANALYZE runtime_schedule")
        connection.execute("ANALYZE runtime_run")
        connection.commit()
        connection.read_only = True
        yield _TemporaryQueryConnection(connection)


def _nodes(plan):
    yield plan
    for child in plan.get("Plans", []):
        yield from _nodes(child)


def test_review_counts_preserve_complete_history_and_distinct_model_uses(target_database_url):
    with _health_relations(target_database_url) as connection:
        assert daily_predictions._research_disposition_counts(connection) == (3, 2)
        assert connection.execute("SHOW transaction_read_only").fetchone() == ("on",)


def test_review_query_reads_receipt_scope_once_with_existing_index(target_database_url):
    with _health_relations(target_database_url) as connection:
        plan = connection.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) "
            + daily_predictions._RESEARCH_DISPOSITION_SQL).fetchone()[0][0]["Plan"]
        receipt_scans = [node for node in _nodes(plan) if node.get("Relation Name") == "command_receipt"]
        assert len(receipt_scans) == 1
        assert receipt_scans[0]["Node Type"] != "Seq Scan"
        assert receipt_scans[0]["Actual Loops"] == 1
        assert receipt_scans[0]["Actual Rows"] + receipt_scans[0].get("Rows Removed by Filter", 0) < 4000
        assert any(node.get("Index Name") == "command_receipt_idempotency_uk" for node in _nodes(plan))


def test_malformed_success_receipt_for_completed_work_fails_closed(target_database_url):
    with _health_relations(target_database_url, malformed=True) as connection:
        with pytest.raises(ArtifactIntegrityError, match="research disposition receipt"):
            daily_predictions._research_disposition_counts(connection)


def test_empty_completed_population_keeps_exact_zero_counts(target_database_url):
    with _health_relations(target_database_url) as connection:
        connection.connection.rollback()
        connection.connection.read_only = False
        connection.execute("DELETE FROM mra.runtime_run")
        connection.connection.commit()
        connection.connection.read_only = True
        assert daily_predictions._research_disposition_counts(connection) == (0, 0)
