from __future__ import annotations

from datetime import timedelta

import psycopg
import pytest

from market_regime_alpha.application.research_validation.postgres_research_model import (
    PostgresResearchModelRepository,
)
from market_regime_alpha.application.research_validation.research_model import (
    ResearchInferenceRequest,
    ResearchModelInferenceReceipt,
    ResearchModelStatus,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId
from tests.application.research_validation.test_research_model import (
    NOW,
    _request,
    _v2_request,
)
from tests.persistence.postgres.conftest import postgres_factory as postgres_factory


def test_research_model_training_inference_and_replay_are_idempotent(
    postgres_factory,
) -> None:
    request = _request()
    repository = PostgresResearchModelRepository(postgres_factory)

    first = repository.train_exploratory(request, trained_at=NOW)
    second = repository.train_exploratory(request, trained_at=NOW)
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
    stored_request = repository.get_request(first.request_reference.artifact_id)
    assert "EXPLORATORY_CALLER_PAYLOAD" in stored_request.limitations
    assert first.status is ResearchModelStatus.AVAILABLE
    assert receipt.result.research_model_available is True
    assert receipt.result.formal_model_qualified is False
    assert receipt.result.formal_oos is False
    assert receipt.result.calibrated is False
    assert receipt.result.barrier_scores_are_probabilities is False
    assert repository.get_inference(receipt.receipt_id) == receipt


def test_research_model_owner_rows_are_append_only(postgres_factory) -> None:
    repository = PostgresResearchModelRepository(postgres_factory)
    artifact = repository.train_exploratory(_request(), trained_at=NOW)

    with postgres_factory.connection() as connection, pytest.raises(
        psycopg.errors.RaiseException,
        match="research_model_artifact is append-only",
    ):
        connection.execute(
            "UPDATE research_model_artifact SET payload_json = payload_json WHERE artifact_id = %s",
            (str(artifact.artifact_id),),
        )


def test_v2_parameter_owner_is_content_addressed_and_formal_flags_stay_closed(
    postgres_factory,
) -> None:
    repository = PostgresResearchModelRepository(postgres_factory)
    request = _v2_request()
    artifact = repository.train_exploratory(request, trained_at=NOW)

    assert artifact.model_parameter_hash is not None
    loaded_artifact, loaded_request = repository.get_executable_by_parameter_hash(
        artifact.model_parameter_hash
    )

    assert loaded_artifact == artifact
    assert loaded_request.request_id == artifact.request_reference.artifact_id
    assert loaded_artifact.research_model_available is True
    assert loaded_artifact.formal_model_qualified is False
    assert loaded_artifact.formal_oos is False
    assert loaded_artifact.calibrated is False
    assert "EXPLORATORY_CALLER_PAYLOAD" in loaded_request.limitations


def test_formal_training_rejects_caller_supplied_payload_without_owner_resolution(
    postgres_factory,
) -> None:
    repository = PostgresResearchModelRepository(postgres_factory)

    with pytest.raises(ValueError, match="Model Definition must resolve"):
        repository.train(_v2_request(), trained_at=NOW)


def test_inference_publish_rejects_correct_model_id_with_wrong_hash(
    postgres_factory,
) -> None:
    repository = PostgresResearchModelRepository(postgres_factory)
    request = _request()
    artifact = repository.train_exploratory(request, trained_at=NOW)
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
    result = repository.execute(
        artifact_id=artifact.artifact_id,
        request=inference,
        executed_at=NOW,
    ).result
    forged = ResearchModelInferenceReceipt.create(
        model_reference=ValidationArtifactReference(
            "RESEARCH_MODEL_ARTIFACT",
            artifact.artifact_id,
            "sha256:" + "0" * 64,
        ),
        request=inference,
        result=result,
        executed_at=NOW,
    )

    with pytest.raises(ValueError, match="Model owner identity mismatch"):
        repository.publish_inference(forged)


def test_inference_cannot_execute_before_model_or_features_are_available(
    postgres_factory,
) -> None:
    repository = PostgresResearchModelRepository(postgres_factory)
    request = _request()
    artifact = repository.train_exploratory(request, trained_at=NOW)
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

    with pytest.raises(ValueError, match="predates required input availability"):
        repository.execute(
            artifact_id=ArtifactId(str(artifact.artifact_id)),
            request=inference,
            executed_at=NOW - timedelta(seconds=1),
        )
