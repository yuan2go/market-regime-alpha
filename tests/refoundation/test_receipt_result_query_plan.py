from uuid import UUID

import psycopg

from market_regime_alpha.infrastructure.postgres.schema import SchemaManager


def test_successful_result_receipt_lookup_is_bounded_and_keeps_first_receipt(target_database_url):
    SchemaManager(target_database_url).bootstrap()
    with psycopg.connect(target_database_url) as connection:
        connection.execute("""
            INSERT INTO mra.command_receipt (
                receipt_id, command_kind, scope_id, idempotency_key, request_hash,
                status, result_aggregate_kind, result_aggregate_id,
                result_aggregate_version, result_hash, completed_at
            )
            SELECT ('00000000-0000-0000-0000-' || lpad(to_hex(n), 12, '0'))::uuid,
                   'QUERY_PLAN_FIXTURE', 'fixture', 'receipt:' || n, repeat('a', 64),
                   'SUCCEEDED', 'UNIVERSE_REVISION',
                   CASE WHEN n <= 3 THEN 'target' ELSE 'other:' || n END,
                   1, repeat('b', 64),
                   '2026-01-01 00:00:00+00'::timestamptz
                       + CASE WHEN n = 3 THEN interval '1 second' ELSE interval '0 seconds' END
            FROM generate_series(1, 10000) AS n
        """)
        connection.execute("ANALYZE mra.command_receipt")
        query = """
            SELECT receipt_id, result_hash FROM mra.command_receipt
            WHERE status = 'SUCCEEDED' AND result_aggregate_kind = %s
              AND result_aggregate_id = %s
            ORDER BY completed_at, receipt_id LIMIT 1
        """
        parameters = ("UNIVERSE_REVISION", "target")
        assert connection.execute(query, parameters).fetchone() == (UUID(int=1), "b" * 64)
        plan = connection.execute(
            "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + query, parameters
        ).fetchone()[0][0]["Plan"]

        def nodes(node):
            yield node
            for child in node.get("Plans", ()):
                yield from nodes(child)

        scans = [node for node in nodes(plan) if node.get("Relation Name") == "command_receipt"]
        assert scans
        assert all(node["Node Type"] in {"Index Scan", "Index Only Scan"} for node in scans)
        assert sum(node["Actual Rows"] * node["Actual Loops"] for node in scans) == 1
        assert connection.execute(query, ("UNIVERSE_REVISION", "missing")).fetchone() is None
