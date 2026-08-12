from __future__ import annotations

import psycopg
import pytest

from market_regime_alpha.application.research_validation.formal_execution import (
    FormalExecutionStage,
    FormalExecutionStatus,
)
from market_regime_alpha.application.research_validation.postgres_formal_execution import (
    PostgresFormalExecutionRepository,
)
from tests.application.research_validation.test_formal_execution import _request
from tests.persistence.postgres.conftest import postgres_factory as postgres_factory


def test_current_free_data_formal_execution_is_idempotent_blocked_and_replayable(
    postgres_factory,
) -> None:
    request = _request(None)
    repository = PostgresFormalExecutionRepository(postgres_factory)

    first = repository.assess(request)
    second = repository.assess(request)
    replayed = repository.replay(first.assessment_id)

    assert first == second == replayed
    assert repository.get_request(request.request_id) == request
    assert first.status is FormalExecutionStatus.BLOCKED
    assert first.terminal_stage is FormalExecutionStage.PROVIDER_FACT_QUALIFICATION
    assert first.formal_model_qualified is False
    assert first.formal_oos_alpha_established is False
    assert first.calibrated is False
    assert first.production_authorized is False
    with postgres_factory.connection(read_only=True) as connection:
        row = connection.execute(
            """
            SELECT formal_model_qualified, formal_oos_alpha_established,
                   calibrated, production_authorized
            FROM formal_execution_assessment WHERE assessment_id = %s
            """,
            (str(first.assessment_id),),
        ).fetchone()
    assert row == (False, False, False, False)


def test_formal_execution_journal_is_append_only(postgres_factory) -> None:
    repository = PostgresFormalExecutionRepository(postgres_factory)
    assessment = repository.assess(_request(None))

    with postgres_factory.connection() as connection, pytest.raises(
        psycopg.errors.RaiseException,
        match="formal_execution_assessment is append-only",
    ):
        connection.execute(
            "UPDATE formal_execution_assessment SET payload_json = payload_json WHERE assessment_id = %s",
            (str(assessment.assessment_id),),
        )
