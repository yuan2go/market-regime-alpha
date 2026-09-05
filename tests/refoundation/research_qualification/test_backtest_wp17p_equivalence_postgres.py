from __future__ import annotations

import os
from pathlib import Path
from uuid import UUID

import pytest

from market_regime_alpha.infrastructure.artifacts import LocalArtifactStore
from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.postgres.queries.backtest_history import (
    PostgresExactHistoricalBacktestQueryPort,
)
from market_regime_alpha.infrastructure.postgres.queries.backtest_execution import (
    PostgresBacktestExecutionObservationPort,
    _FOLD_METRIC_STATES_SQL,
)
from market_regime_alpha.infrastructure.postgres.queries.exploratory_backtests import (
    PostgresExploratoryBacktestVerificationPort,
)
from market_regime_alpha.research_qualification.application.backtest_replay import (
    BacktestReplayApplication,
)
from market_regime_alpha.research_qualification.application.backtest_execution import (
    BacktestExecutionPlanner,
)
from market_regime_alpha.research_qualification.domain.backtest import (
    FrozenBacktestEvidence,
    FrozenBacktestSource,
)
from market_regime_alpha.research_qualification.domain.backtest_execution import (
    BacktestExecutionState,
    BacktestResearchState,
)


_RUN_ID = UUID("8f7b6def-9c63-533e-9777-a5a6c57866e0")
_DEFINITION_SHA256 = (
    "ac2686e2ef3105e8a5ca5a2a2ece6cfd7821ea84d56ae7611eb1e9b0e7305d78"
)


def _historical_environment() -> tuple[str, Path]:
    database_url = os.getenv("MRA_WP17P_HISTORICAL_DATABASE_URL")
    artifact_root = os.getenv("MRA_WP17P_HISTORICAL_ARTIFACT_ROOT")
    if not database_url or not artifact_root:
        pytest.skip("exact WP-17P historical database and Artifact root are not configured")
    return database_url, Path(artifact_root)


def _authority_digest(pool: TargetPostgresPool) -> str:
    with pool.connection(read_only=True) as connection:
        row = connection.execute(
            """
            SELECT mra.canonical_sha256(mra.canonical_json_text(
                jsonb_build_object(
                    'root', (SELECT to_jsonb(root)
                               FROM mra.exploratory_backtest_run AS root
                              WHERE root.exploratory_backtest_run_id = %s),
                    'features', (SELECT coalesce(jsonb_agg(to_jsonb(feature)
                                                ORDER BY feature.feature_ordinal),
                                                 '[]'::jsonb)
                                   FROM mra.exploratory_backtest_feature AS feature
                                  WHERE feature.exploratory_backtest_run_id = %s),
                    'arms', (SELECT coalesce(jsonb_agg(to_jsonb(arm)
                                            ORDER BY arm.ordinal), '[]'::jsonb)
                               FROM mra.exploratory_backtest_arm AS arm
                              WHERE arm.exploratory_backtest_run_id = %s),
                    'folds', (SELECT coalesce(jsonb_agg(to_jsonb(fold)
                                             ORDER BY fold.ordinal), '[]'::jsonb)
                                FROM mra.exploratory_backtest_fold AS fold
                               WHERE fold.exploratory_backtest_run_id = %s),
                    'sessions', (SELECT coalesce(jsonb_agg(to_jsonb(member)
                                                ORDER BY member.exploratory_backtest_fold_id,
                                                         member.ordinal), '[]'::jsonb)
                                   FROM mra.exploratory_backtest_fold_session AS member
                                  WHERE member.exploratory_backtest_run_id = %s),
                    'costs', (SELECT coalesce(jsonb_agg(to_jsonb(cost)
                                             ORDER BY cost.ordinal), '[]'::jsonb)
                                FROM mra.exploratory_backtest_cost_assumption AS cost
                               WHERE cost.exploratory_backtest_run_id = %s),
                    'models', (SELECT coalesce(jsonb_agg(to_jsonb(model)
                                              ORDER BY model.model_id), '[]'::jsonb)
                                 FROM mra.model AS model
                                WHERE model.model_id IN (
                                    SELECT training.model_id
                                      FROM mra.model_training_run AS training
                                     WHERE training.exploratory_backtest_run_id = %s
                                )),
                    'artifacts', (SELECT coalesce(jsonb_agg(to_jsonb(artifact)
                                                 ORDER BY artifact.artifact_id),
                                                  '[]'::jsonb)
                                    FROM mra.artifact AS artifact
                                   WHERE artifact.artifact_id IN (
                                       SELECT root.code_artifact_id
                                         FROM mra.exploratory_backtest_run AS root
                                        WHERE root.exploratory_backtest_run_id = %s
                                       UNION
                                       SELECT root.config_artifact_id
                                         FROM mra.exploratory_backtest_run AS root
                                        WHERE root.exploratory_backtest_run_id = %s
                                   ))
                )
            ))
            """,
            (_RUN_ID,) * 9,
        ).fetchone()
    assert row is not None
    return str(row[0])


def test_completed_wp17p_has_zero_write_generic_exact_equivalence() -> None:
    database_url, artifact_root = _historical_environment()
    pool = TargetPostgresPool(database_url, min_size=0, max_size=2)
    try:
        before = _authority_digest(pool)
        authority_query = PostgresExactHistoricalBacktestQueryPort(pool)
        snapshot = authority_query.load(_RUN_ID)
        expected = BacktestExecutionPlanner().compile(snapshot.run)
        observations = PostgresBacktestExecutionObservationPort(pool).observe(
            snapshot.run,
            expected.expected_actions,
        )
        execution_replay = BacktestExecutionPlanner().compile(
            snapshot.run,
            observations,
        )
        result = BacktestReplayApplication(
            authority_query,
            LocalArtifactStore(artifact_root),
            PostgresBacktestExecutionObservationPort(pool),
        ).verify(_RUN_ID)
        old_verification = PostgresExploratoryBacktestVerificationPort(pool).verify(
            _RUN_ID
        )
        after = _authority_digest(pool)
    finally:
        pool.close()

    assert before == after
    assert snapshot.run.source is FrozenBacktestSource.HISTORICAL_EXACT
    assert snapshot.run.evidence is FrozenBacktestEvidence.COMPLETED_ZERO_WRITE
    assert str(snapshot.run.definition_sha256) == _DEFINITION_SHA256
    assert len(snapshot.artifact_bindings) == 2
    assert len(expected.expected_actions) == 12
    assert execution_replay.execution_state is BacktestExecutionState.COMPLETED
    assert execution_replay.research_state is BacktestResearchState.ESTIMABLE
    assert execution_replay.ready_actions == ()
    assert result.matched is True
    assert result.mismatch_count == 0
    assert old_verification.matched is True
    assert old_verification.mismatch_count == 0


def test_historical_metric_state_plan_does_not_multiply_source_observations() -> None:
    database_url, _ = _historical_environment()
    pool = TargetPostgresPool(database_url, min_size=0, max_size=2)
    try:
        with pool.connection(read_only=True) as connection:
            expected = connection.execute(
                """
                SELECT DISTINCT source.exploratory_backtest_fold_id, metric.metric_state
                FROM mra.evaluation_backtest_arm_source AS source
                JOIN mra.evaluation_metric AS metric
                  ON metric.evaluation_run_id = source.evaluation_run_id
                WHERE source.exploratory_backtest_run_id = %s
                """,
                (_RUN_ID,),
            ).fetchall()
            actual = connection.execute(_FOLD_METRIC_STATES_SQL, (_RUN_ID,)).fetchall()
            assert sorted(actual) == sorted(expected)
            metric_count = connection.execute(
                """
                SELECT count(*) FROM mra.evaluation_metric AS metric
                WHERE EXISTS (
                    SELECT 1 FROM mra.evaluation_backtest_arm_source AS source
                    WHERE source.exploratory_backtest_run_id = %s
                      AND source.evaluation_run_id = metric.evaluation_run_id
                )
                """,
                (_RUN_ID,),
            ).fetchone()[0]
            plan = connection.execute(
                "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + _FOLD_METRIC_STATES_SQL,
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
    # This exact historical run binds each Evaluation to one fold. Work must
    # scale with its metric roster, not source-observation x metric products.
    assert max(join_rows) <= metric_count
