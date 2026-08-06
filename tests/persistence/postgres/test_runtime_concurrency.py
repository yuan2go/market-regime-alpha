from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier

import psycopg

from market_regime_alpha.features.materialization_run import (
    FeatureMaterializationExecutionMode,
    FeatureMaterializationTaskSpec,
)
from market_regime_alpha.features.postgres_materialization_run import (
    PostgresFeatureMaterializationRunRepository,
)
from market_regime_alpha.market_data import Timeframe
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
    is_retryable_transaction_error,
)


COMMAND_HASH = "sha256:" + "a" * 64


def _task(symbol: str) -> FeatureMaterializationTaskSpec:
    return FeatureMaterializationTaskSpec(
        symbol=symbol,
        feature_id="price-action-v2",
        timeframe=Timeframe.DAILY,
    )


def test_scoped_advisory_lock_is_transaction_bound(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    with postgres_factory.connection() as connection:
        connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            ("runtime-concurrency:test-scope",),
        )
        held = connection.execute(
            "SELECT COUNT(*) FROM pg_locks WHERE pid = pg_backend_pid() "
            "AND locktype = 'advisory' AND granted"
        ).fetchone()
        assert held is not None
        assert int(held[0]) == 1


def test_transaction_retries_only_postgres_retryable_errors(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    attempts = 0

    def operation(connection: psycopg.Connection[object]) -> int:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            connection.execute("DO $$ BEGIN RAISE EXCEPTION 'retry me' USING ERRCODE = '40001'; END $$")
        row = connection.execute("SELECT 42").fetchone()
        assert row is not None
        return int(row[0])

    assert postgres_factory.run_transaction(operation, max_attempts=2) == 42
    assert attempts == 2
    assert postgres_factory.runtime_metrics.transaction_retries == 1
    assert is_retryable_transaction_error(psycopg.errors.DeadlockDetected("deadlock"))
    assert not is_retryable_transaction_error(ValueError("application conflict"))


def test_feature_workers_claim_disjoint_rows_with_skip_locked(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    repository = PostgresFeatureMaterializationRunRepository(
        postgres_factory,
        clock=lambda: datetime(2026, 8, 5, 6, 55, tzinfo=timezone.utc),
    )
    run = repository.prepare(
        idempotency_key="parallel-feature-claim",
        command_hash=COMMAND_HASH,
        tasks=tuple(_task(symbol) for symbol in ("000001.SZ", "000002.SZ", "600000.SH", "600519.SH")),
        mode=FeatureMaterializationExecutionMode.START_NEW,
    )
    barrier = Barrier(2)

    def claim() -> tuple[str, ...]:
        barrier.wait()
        return tuple(item.task_key for item in repository.claim_batch(run_id=run.run_id, limit=2))

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(claim)
        second_future = executor.submit(claim)
        first = first_future.result(timeout=10)
        second = second_future.result(timeout=10)

    assert len(first) == 2
    assert len(second) == 2
    assert set(first).isdisjoint(second)
    assert set(first) | set(second) == {
        task.task_key
        for task in (
            _task("000001.SZ"),
            _task("000002.SZ"),
            _task("600000.SH"),
            _task("600519.SH"),
        )
    }
