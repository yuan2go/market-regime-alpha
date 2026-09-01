from __future__ import annotations

from typing import Any, cast

import psycopg
import pytest

from market_regime_alpha.infrastructure.postgres.research_transaction import (
    commit_research_transaction,
)
from market_regime_alpha.research_qualification.application._command_support import (
    retry_transient_transaction,
)
from market_regime_alpha.research_qualification.errors import (
    ResearchUnknownCommitResultError,
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
