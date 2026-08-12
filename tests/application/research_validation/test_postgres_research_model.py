from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

import psycopg
import pytest

import market_regime_alpha.application.research_validation.postgres_research_model as model_repository_module
from market_regime_alpha.application.research_validation.postgres_research_model import (
    PostgresResearchModelRepository,
)
from market_regime_alpha.application.research_validation.research_model import (
    ResearchInferenceRequest,
    ResearchModelInferenceReceipt,
    ResearchModelStatus,
    TimedResearchTarget,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.application.research_validation.formal_evaluation import (
    EvaluationPartition,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.core.identity import TargetId
from market_regime_alpha.core.time import AvailabilityTime, DecisionTime
from market_regime_alpha.application.research_validation.samples import (
    HistoricalPathSampleRecord,
    HistoricalSampleDataset,
)
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.forecasting.path import (
    PATH_FORECAST_SAMPLE_SCHEMA,
    PathForecastSample,
)
from market_regime_alpha.strategies.entry.contracts import (
    EntryPathObservationStatus,
    EntryPathReasonCode,
)
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


def test_formal_matrix_builder_uses_frozen_owners_not_caller_samples(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _v2_request()
    binding = request.measure_bindings[0]
    decision_time = request.samples[0].decision_time
    pit_reference = ValidationArtifactReference(
        "PIT_FACT_REVISION",
        ArtifactId("pit-fact:owner-vector"),
        canonical_hash({"pit": "owner-vector"}),
    )
    path_sample = PathForecastSample(
        sample_id=ArtifactId("owner-path-sample"),
        source_artifact_id=ArtifactId("owner-targeted-outcome"),
        source_content_hash=canonical_hash({"outcome": "owner"}),
        symbol="000001.SZ",
        target_id=TargetId(str(binding.target_reference.artifact_id)),
        sample_decision_time=DecisionTime(decision_time),
        available_at=AvailabilityTime(decision_time + timedelta(days=1)),
        observation_status=EntryPathObservationStatus.AVAILABLE,
        observation_reason_code=EntryPathReasonCode.OUTCOME_RESOLVED,
        realized_mfe=0.04,
        realized_mae=-0.02,
        realized_return=0.03,
        schema_version=PATH_FORECAST_SAMPLE_SCHEMA,
    )
    record = HistoricalPathSampleRecord.register_unqualified(
        sample=path_sample,
        target_reference=binding.target_reference,
        outcome_reference=ValidationArtifactReference(
            "TARGET_OUTCOME_LABEL",
            ArtifactId("owner-target-label"),
            canonical_hash({"label": "owner"}),
        ),
        pit_lineage=(pit_reference,),
        registered_at=decision_time + timedelta(days=1),
    )
    dataset = HistoricalSampleDataset.create(
        registry_version="owner-derived-training-v1",
        target_reference=binding.target_reference,
        records=(record,),
        available_at=decision_time + timedelta(days=1),
    )
    evidence = SimpleNamespace(
        evidence_id=ArtifactId("formal-pit-owner"),
        recorded_at=decision_time + timedelta(hours=1),
        selected_fact_authorities=(
            SimpleNamespace(
                fact_id=pit_reference.artifact_id,
                fact_hash=pit_reference.content_hash,
            ),
        ),
    )
    qualification = SimpleNamespace(evaluated_at=decision_time + timedelta(days=1))
    owner_features = tuple(
        replace(item, value=Decimal("999")) for item in request.samples[0].features
    )
    def owner_target(owner_binding) -> TimedResearchTarget:
        return TimedResearchTarget(
            name=owner_binding.training_target_name,
            value=(
                Decimal("0.123")
                if owner_binding.training_target_name == "expected_return"
                else True
            ),
            available_at=decision_time + timedelta(days=1),
            source_reference=record.outcome_reference,
            source_value_path=f"owner.{owner_binding.training_target_name}",
        )
    monkeypatch.setattr(
        model_repository_module,
        "_load_qualified_historical_dataset_owner",
        lambda *_args, **_kwargs: qualification,
    )
    monkeypatch.setattr(
        model_repository_module,
        "_load_qualified_pit_evidence_set",
        lambda *_args, **_kwargs: {decision_time: evidence},
    )
    monkeypatch.setattr(
        model_repository_module,
        "_formal_pit_symbols",
        lambda *_args, **_kwargs: (record.sample.symbol,),
    )
    monkeypatch.setattr(
        model_repository_module,
        "_load_feature_vector",
        lambda *_args, **_kwargs: owner_features,
    )
    monkeypatch.setattr(
        model_repository_module,
        "_load_training_target",
        lambda *_args, **kwargs: owner_target(kwargs["binding"]),
    )

    samples = model_repository_module._build_owner_training_samples(
        object(),
        request=request,
        feature_set=SimpleNamespace(
            definitions=(
                SimpleNamespace(feature_id="momentum"),
                SimpleNamespace(feature_id="value"),
            )
        ),
        datasets=(dataset,),
        formal_protocol_reference=ValidationArtifactReference(
            "FORMAL_RESEARCH_PROTOCOL",
            ArtifactId("formal-protocol-owner"),
            canonical_hash({"protocol": "owner"}),
        ),
    )

    assert len(samples) == 1
    assert tuple(item.value for item in samples[0].features) == (
        Decimal("999"),
        Decimal("999"),
    )
    assert samples[0].targets == tuple(
        sorted(
            (owner_target(item) for item in request.measure_bindings),
            key=lambda item: item.name,
        )
    )
    assert samples[0].sample_id not in {item.sample_id for item in request.samples}


def test_owner_walk_forward_folds_purge_and_embargo_canonical_sessions() -> None:
    request = _v2_request()
    evaluation = SimpleNamespace(
        windows=(
            SimpleNamespace(
                fold=1,
                partition=EvaluationPartition.TRAIN,
                start_date=date(2026, 7, 1),
                end_date=date(2026, 7, 4),
            ),
            SimpleNamespace(
                fold=1,
                partition=EvaluationPartition.VALIDATION,
                start_date=date(2026, 7, 5),
                end_date=date(2026, 7, 7),
            ),
            SimpleNamespace(
                fold=1,
                partition=EvaluationPartition.LOCKED_OOS,
                start_date=date(2026, 7, 10),
                end_date=date(2026, 7, 10),
            ),
        ),
        embargo_sessions=2,
    )

    folds = model_repository_module._build_owner_walk_forward_folds(
        samples=request.samples,
        evaluation=evaluation,
        oos_start_date=date(2026, 7, 10),
        session_sequence=request.session_sequence,
    )
    samples_by_id = {item.sample_id: item.trading_date.day for item in request.samples}

    assert {samples_by_id[item] for item in folds[0].train_sample_ids} == {1, 2}
    assert {samples_by_id[item] for item in folds[0].validation_sample_ids} == {
        5,
        7,
    }
    assert folds[0].purge_sessions == folds[0].embargo_sessions == 2


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
