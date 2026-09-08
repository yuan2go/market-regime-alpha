from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from typing import Any, cast

import psycopg
import pytest

from market_regime_alpha.infrastructure.postgres.research_transaction import (
    classify_research_postgres_error,
    commit_research_transaction,
)
from market_regime_alpha.infrastructure.postgres.schema import SchemaManager
from market_regime_alpha.research_qualification.application._command_support import (
    retry_transient_transaction,
)
from market_regime_alpha.research_qualification.errors import (
    ResearchUnknownCommitResultError,
    ResearchRetryableTransactionError,
)


class _UnknownCommitConnection:
    def commit(self) -> None:
        raise psycopg.OperationalError("commit acknowledgement lost")


def test_connection_loss_during_commit_is_not_classified_as_known_rollback() -> None:
    connection = cast(psycopg.Connection[Any], _UnknownCommitConnection())
    with pytest.raises(ResearchUnknownCommitResultError):
        commit_research_transaction(connection)


def test_unknown_commit_reenters_exact_command_for_receipt_probe() -> None:
    attempts = 0

    @retry_transient_transaction
    def exact_receipt_command() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ResearchUnknownCommitResultError("08006")
        return "receipt-replayed"

    assert exact_receipt_command() == "receipt-replayed"
    assert attempts == 2


def test_real_postgres_serialization_deadlock_and_connection_loss_are_retryable(
    target_database_url: str,
) -> None:
    SchemaManager(target_database_url).bootstrap()
    with psycopg.connect(target_database_url, autocommit=True) as setup:
        setup.execute(
            """
            CREATE TABLE mra.wp11q_transaction_probe (
                probe_id integer PRIMARY KEY,
                value integer NOT NULL
            )
            """
        )
        setup.execute(
            "INSERT INTO mra.wp11q_transaction_probe VALUES (1, 0), (2, 0)"
        )
    try:
        serial_barrier = Barrier(2)

        def serialize(probe_id: int) -> BaseException | None:
            try:
                with psycopg.connect(target_database_url) as connection:
                    connection.execute(
                        "SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"
                    )
                    connection.execute(
                        "SELECT sum(value) FROM mra.wp11q_transaction_probe"
                    ).fetchone()
                    serial_barrier.wait(timeout=10)
                    connection.execute(
                        """
                        UPDATE mra.wp11q_transaction_probe
                        SET value = value + 1 WHERE probe_id = %s
                        """,
                        (probe_id,),
                    )
                    connection.commit()
            except BaseException as exc:
                return exc
            return None

        with ThreadPoolExecutor(max_workers=2) as executor:
            serialization_results = list(executor.map(serialize, (1, 2)))
        serialization_errors = [
            error for error in serialization_results if error is not None
        ]
        assert len(serialization_errors) == 1
        assert isinstance(
            serialization_errors[0], psycopg.errors.SerializationFailure
        )
        assert isinstance(
            classify_research_postgres_error(
                serialization_errors[0], owner="WP11Qualification"
            ),
            ResearchRetryableTransactionError,
        )

        with psycopg.connect(target_database_url, autocommit=True) as reset:
            reset.execute("UPDATE mra.wp11q_transaction_probe SET value = 0")
        deadlock_barrier = Barrier(2)

        def deadlock(first: int, second: int) -> BaseException | None:
            try:
                with psycopg.connect(target_database_url) as connection:
                    connection.execute(
                        """
                        UPDATE mra.wp11q_transaction_probe
                        SET value = value + 1 WHERE probe_id = %s
                        """,
                        (first,),
                    )
                    deadlock_barrier.wait(timeout=10)
                    connection.execute(
                        """
                        UPDATE mra.wp11q_transaction_probe
                        SET value = value + 1 WHERE probe_id = %s
                        """,
                        (second,),
                    )
                    connection.commit()
            except BaseException as exc:
                return exc
            return None

        with ThreadPoolExecutor(max_workers=2) as executor:
            deadlock_results = list(
                executor.map(
                    lambda order: deadlock(*order),
                    ((1, 2), (2, 1)),
                )
            )
        deadlock_errors = [error for error in deadlock_results if error is not None]
        assert len(deadlock_errors) == 1
        assert isinstance(deadlock_errors[0], psycopg.errors.DeadlockDetected)
        assert isinstance(
            classify_research_postgres_error(
                deadlock_errors[0], owner="WP11Qualification"
            ),
            ResearchRetryableTransactionError,
        )

        terminated = psycopg.connect(target_database_url)
        try:
            backend_pid = terminated.info.backend_pid
            with psycopg.connect(target_database_url, autocommit=True) as killer:
                killed = killer.execute(
                    "SELECT pg_terminate_backend(%s)", (backend_pid,)
                ).fetchone()
            assert killed == (True,)
            with pytest.raises(psycopg.OperationalError) as lost:
                terminated.execute("SELECT 1").fetchone()
            assert isinstance(
                classify_research_postgres_error(
                    lost.value, owner="WP11Qualification"
                ),
                ResearchRetryableTransactionError,
            )
        finally:
            terminated.close()
    finally:
        with psycopg.connect(target_database_url, autocommit=True) as cleanup:
            cleanup.execute("DROP TABLE IF EXISTS mra.wp11q_transaction_probe")
