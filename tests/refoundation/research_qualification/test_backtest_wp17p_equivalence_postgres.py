from __future__ import annotations

import os
from collections import Counter
from contextlib import contextmanager
from dataclasses import fields
from pathlib import Path
from threading import Barrier, Lock, get_ident
from uuid import UUID

import pytest
from psycopg.rows import dict_row

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


def test_outcome_batch_reconciles_exact_history_and_missing_rows_without_cached_results() -> None:
    from market_regime_alpha.infrastructure.postgres.queries.outcome_verification import PostgresOutcomeVerificationProvider
    from market_regime_alpha.outcome.domain import OutcomeMismatchKind

    class MeasuredPool(TargetPostgresPool):
        leases = 0

        @contextmanager
        def connection(self, *, read_only=False):
            assert read_only
            self.leases += 1
            with super().connection(read_only=True) as connection:
                yield connection

    url, _ = _historical_environment()
    pool = MeasuredPool(url, min_size=0, max_size=2)
    try:
        before = _authority_digest(pool)
        with pool.connection(read_only=True) as connection:
            ids = tuple(row[0] for row in connection.execute(
                """
                SELECT outcome.market_target_outcome_revision_id
                FROM mra.market_target_outcome_revision AS outcome
                JOIN mra.decision_target_commitment USING (commitment_id)
                JOIN mra.exploratory_retrospective_decision_run AS backtest USING (decision_run_id)
                WHERE backtest.exploratory_backtest_run_id = %s
                ORDER BY outcome.market_target_outcome_revision_id LIMIT 32
                """,
                (_RUN_ID,),
            ).fetchall())
        assert len(ids) == 32
        absent = UUID("00000000-0000-4000-8000-000000009999")
        provider = PostgresOutcomeVerificationProvider(pool)
        pool.leases = 0
        result = provider.inspect_many((*ids, absent, ids[0]))
        assert set(result) == {*ids, absent}
        assert all(result[identity] == () for identity in ids)
        assert len(result[absent]) == 1
        assert result[absent][0].kind is OutcomeMismatchKind.MISSING_ROW
        assert pool.leases == 1
        assert provider.inspect_many((*ids, absent)) == result
        assert pool.leases == 2
        assert _authority_digest(pool) == before
    finally:
        pool.close()


def test_training_reloads_each_distinct_dataset_once_per_preparation(monkeypatch) -> None:
    from market_regime_alpha.infrastructure.postgres.queries import model_training_inputs as inputs
    from market_regime_alpha.research_qualification.domain.model import ArtifactBinding
    from market_regime_alpha.research_qualification.ports.model_inputs import OpenModelTrainingRunRequest

    url, artifact_root = _historical_environment()
    pool = TargetPostgresPool(url, min_size=0, max_size=2)
    store = LocalArtifactStore(artifact_root)
    loads: Counter[UUID] = Counter()
    original = inputs.load_research_dataset_definition

    def measured(connection, *, dataset_id):
        loads[dataset_id] += 1
        return original(connection, dataset_id=dataset_id)

    monkeypatch.setattr(inputs, "load_research_dataset_definition", measured)
    try:
        before = _authority_digest(pool)
        with pool.connection(read_only=True) as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                row = cursor.execute(
                    "SELECT * FROM mra.model_training_run WHERE model_training_run_id = %s",
                    (UUID("d68c200e-2426-5124-bd52-e6d38ceb3cfd"),),
                ).fetchone()
        assert row is not None
        arguments = {
            field.name: row[field.name]
            for field in fields(OpenModelTrainingRunRequest)
            if field.name not in {"code_artifact", "config_artifact"}
        }
        for prefix in ("code", "config"):
            arguments[prefix + "_artifact"] = ArtifactBinding(
                row[prefix + "_artifact_id"], row[prefix + "_content_sha256"],
                row[prefix + "_size_bytes"],
            )
        provider = inputs.PostgresModelTrainingInputProvider(pool, store)
        request = OpenModelTrainingRunRequest(**arguments)
        prepared = provider.prepare(request)
        registered_bytes = store.read_bytes(
            row["training_input_content_sha256"],
            expected_size=row["training_input_size_bytes"],
        )
        assert len(prepared.samples) == 32
        assert prepared.training_input_content == registered_bytes
        assert prepared.linear_rows == provider.load_registered(row["model_training_run_id"]).linear_rows
        assert loads == Counter({UUID("a3f34d1b-f8c2-5026-93a7-f939a14dae36"): 1})
        assert provider.prepare(request) == prepared
        assert loads == Counter({UUID("a3f34d1b-f8c2-5026-93a7-f939a14dae36"): 2})
        assert _authority_digest(pool) == before
    finally:
        pool.close()


def test_owner_observation_uses_bounded_concurrent_reads_without_changing_replay(monkeypatch) -> None:
    from market_regime_alpha.infrastructure.postgres.queries.outcome_verification import PostgresOutcomeVerificationProvider

    def reject_per_row_inspection(self, revision_id):
        raise AssertionError("Backtest must reconcile the action's Outcome roster as a batch")

    monkeypatch.setattr(PostgresOutcomeVerificationProvider, "inspect", reject_per_row_inspection)

    class ObservedPool(TargetPostgresPool):
        def __init__(self, url):
            super().__init__(url, min_size=0, max_size=2)
            self.main_thread = get_ident()
            self.threads = set()
            self.lock = Lock()
            self.barrier = Barrier(4, timeout=5)

        @contextmanager
        def connection(self, *, read_only=False):
            thread = get_ident()
            with self.lock:
                first = thread not in self.threads
                self.threads.add(thread)
            if thread != self.main_thread and first:
                self.barrier.wait()
            assert read_only
            with super().connection(read_only=True) as connection:
                yield connection

    url, _ = _historical_environment()
    pool = ObservedPool(url)
    try:
        before = _authority_digest(pool)
        run = PostgresExactHistoricalBacktestQueryPort(pool).load(_RUN_ID).run
        planner = BacktestExecutionPlanner()
        expected = planner.compile(run).expected_actions
        observed = PostgresBacktestExecutionObservationPort(pool).observe(run, expected)
        assert len(pool.threads - {pool.main_thread}) == 4
        assert tuple(item.action_id for item in observed) == tuple(item.action_id for item in expected)
        assert planner.compile(run, observed).execution_state is BacktestExecutionState.COMPLETED
        assert _authority_digest(pool) == before
    finally:
        pool.close()


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
