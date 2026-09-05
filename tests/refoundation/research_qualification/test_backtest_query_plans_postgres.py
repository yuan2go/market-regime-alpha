"""Qualification of the SELECT actually issued by the Backtest observer."""
from __future__ import annotations

import ast
from pathlib import Path

from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from tests.refoundation.research_qualification.test_backtest_wp17p_equivalence_postgres import (
    _RUN_ID,
    _historical_environment,
)


def test_fold_metric_state_query_preserves_results_without_observation_product() -> None:
    # Inspect the exact executable query, rather than benchmarking a rewritten
    # test-only approximation or imposing a machine-dependent latency limit.
    path = Path(__file__).parents[3] / "src/market_regime_alpha/infrastructure/postgres/queries/backtest_execution.py"
    statements = [
        node.value for node in ast.walk(ast.parse(path.read_text()))
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        and "SELECT source.exploratory_backtest_fold_id," in node.value
        and "metric.metric_state" in node.value
    ]
    assert len(statements) == 1
    statement = statements[0]
    database_url, _ = _historical_environment()
    pool = TargetPostgresPool(database_url, min_size=0, max_size=2)
    try:
        with pool.connection(read_only=True) as connection:
            actual = connection.execute(statement, (_RUN_ID,)).fetchall()
            expected = connection.execute(
                """
                SELECT DISTINCT source.exploratory_backtest_fold_id, metric.metric_state
                FROM mra.evaluation_backtest_arm_source AS source
                JOIN mra.evaluation_metric AS metric USING (evaluation_run_id)
                WHERE source.exploratory_backtest_run_id = %s
                """, (_RUN_ID,),
            ).fetchall()
            assert sorted(actual) == sorted(expected)
            metric_count = connection.execute(
                """
                SELECT count(*) FROM mra.evaluation_metric AS metric
                WHERE EXISTS (
                    SELECT 1 FROM mra.evaluation_backtest_arm_source AS source
                    WHERE source.exploratory_backtest_run_id = %s
                      AND source.evaluation_run_id = metric.evaluation_run_id
                )
                """, (_RUN_ID,),
            ).fetchone()[0]
            plan = connection.execute(
                "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + statement,
                (_RUN_ID,),
            ).fetchone()[0][0]["Plan"]
    finally:
        pool.close()
    pending = [plan]
    join_rows = []
    while pending:
        node = pending.pop()
        pending.extend(node.get("Plans", ()))
        if "Join Type" in node:
            join_rows.append(node["Actual Rows"] * node["Actual Loops"])
    assert metric_count > 0
    assert join_rows
    # The allowlisted run binds each Evaluation to one fold. Joining its
    # member source rows must not multiply the already-complete metric roster.
    assert max(join_rows) <= metric_count
