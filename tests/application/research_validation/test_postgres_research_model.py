from __future__ import annotations

import psycopg
import pytest

from market_regime_alpha.application.research_validation.postgres_research_model import (
    PostgresResearchModelRepository,
)
from market_regime_alpha.application.research_validation.research_model import (
    ResearchInferenceRequest,
    ResearchModelStatus,
)
from tests.application.research_validation.test_research_model import NOW, _request
from tests.persistence.postgres.conftest import postgres_factory as postgres_factory


def test_research_model_training_inference_and_replay_are_idempotent(
    postgres_factory,
) -> None:
    request = _request()
    repository = PostgresResearchModelRepository(postgres_factory)

    first = repository.train(request, trained_at=NOW)
    second = repository.train(request, trained_at=NOW)
    replayed = repository.replay(first.artifact_id)
    sample = request.samples[-1]
    inference = ResearchInferenceRequest(
        symbol=sample.symbol,
        decision_time=sample.decision_time,
        features=sample.features,
        model_definition_hash=request.model_definition_reference.content_hash,
        configuration_hash=request.configuration_reference.content_hash,
        code_revision=request.code_revision,
        code_hash=request.code_hash,
    )
    receipt = repository.execute(
        artifact_id=first.artifact_id,
        request=inference,
        executed_at=NOW,
    )

    assert first == second == replayed
    assert repository.get_request(request.request_id) == request
    assert first.status is ResearchModelStatus.AVAILABLE
    assert receipt.result.research_model_available is True
    assert receipt.result.formal_model_qualified is False
    assert receipt.result.formal_oos is False
    assert receipt.result.calibrated is False
    assert receipt.result.barrier_scores_are_probabilities is False
    assert repository.get_inference(receipt.receipt_id) == receipt


def test_research_model_owner_rows_are_append_only(postgres_factory) -> None:
    repository = PostgresResearchModelRepository(postgres_factory)
    artifact = repository.train(_request(), trained_at=NOW)

    with postgres_factory.connection() as connection, pytest.raises(
        psycopg.errors.RaiseException,
        match="research_model_artifact is append-only",
    ):
        connection.execute(
            "UPDATE research_model_artifact SET payload_json = payload_json WHERE artifact_id = %s",
            (str(artifact.artifact_id),),
        )
