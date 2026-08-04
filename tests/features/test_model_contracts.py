from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from market_regime_alpha.core.identity import (
    ArtifactId,
    DatasetId,
    FeatureDefinitionId,
    ModelId,
)
from market_regime_alpha.core.status import InputAvailabilityStatus
from market_regime_alpha.features import model_contracts
from market_regime_alpha.features.model_contracts import (
    FeatureArtifact,
    FeatureComputationRequest,
    FeatureComputer,
)


HASH_A = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64
AS_OF = datetime(2026, 8, 4, 7, 0, tzinfo=timezone.utc)
CREATED_AT = datetime(2026, 8, 4, 7, 1, tzinfo=timezone.utc)


def _request(**changes: object) -> FeatureComputationRequest:
    request = FeatureComputationRequest(
        dataset_id=DatasetId("dataset-1"),
        as_of_time=AS_OF,
        created_at=CREATED_AT,
        data_availability=InputAvailabilityStatus.AVAILABLE,
        configuration_id=ArtifactId("configuration-1"),
        configuration_version="1.0.0",
        configuration_hash=HASH_A,
        input_artifact_ids=(ArtifactId("input-a"), ArtifactId("input-b")),
        input_hashes=(HASH_A, HASH_B),
        normalized_data=("bar-1", "bar-2"),
        configuration=(("window", "3"),),
    )
    return replace(request, **changes)


def _artifact(**changes: object) -> FeatureArtifact:
    artifact = FeatureArtifact(
        artifact_id=ArtifactId("feature-artifact-1"),
        content_hash=HASH_A,
        feature_id=FeatureDefinitionId("technical.simple-moving-average"),
        dataset_id=DatasetId("dataset-1"),
        model_id=ModelId("technical.simple-moving-average"),
        model_version="1.0.0",
        configuration_id=ArtifactId("configuration-1"),
        configuration_version="1.0.0",
        configuration_hash=HASH_A,
        input_artifact_ids=(ArtifactId("input-a"), ArtifactId("input-b")),
        input_hashes=(HASH_A, HASH_B),
        as_of_time=AS_OF,
        created_at=CREATED_AT,
        data_availability=InputAvailabilityStatus.AVAILABLE,
        state="AVAILABLE",
        score=Decimal("11.00"),
        reason_codes=("FEATURE_COMPUTED",),
        limitations=("RESEARCH_ONLY",),
        validation_status="UNVALIDATED",
        observations=("observation-1",),
    )
    return replace(artifact, **changes)


class _FeatureStub:
    feature_id = FeatureDefinitionId("feature-stub")
    model_version = "1.0.0"

    def compute(self, request: FeatureComputationRequest) -> FeatureArtifact:
        return _artifact()


class _ResearchLikeStub:
    model_id = ModelId("research-stub")
    model_version = "1.0.0"
    research_domain = "MARKET_REGIME"

    def run(self, request: object) -> object:
        return request


def test_feature_computer_is_an_independent_runtime_protocol() -> None:
    assert isinstance(_FeatureStub(), FeatureComputer)
    assert not isinstance(_ResearchLikeStub(), FeatureComputer)
    assert not hasattr(model_contracts, "Model")


def test_feature_request_is_frozen_and_requires_traceable_inputs() -> None:
    request = _request()

    with pytest.raises(FrozenInstanceError):
        setattr(request, "configuration_hash", HASH_B)
    with pytest.raises(ValueError, match="align"):
        _request(input_hashes=(HASH_A,))
    with pytest.raises(ValueError, match="sorted"):
        _request(
            input_artifact_ids=(ArtifactId("input-b"), ArtifactId("input-a"))
        )
    with pytest.raises(ValueError, match="unique"):
        _request(
            input_artifact_ids=(ArtifactId("input-a"), ArtifactId("input-a"))
        )
    with pytest.raises(ValueError, match="configuration_hash"):
        _request(configuration_hash="not-a-hash")
    with pytest.raises(ValueError, match="configuration_version"):
        _request(configuration_version=" 1.0.0")


def test_feature_request_requires_explicit_semantic_time_and_availability() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        _request(as_of_time=datetime(2026, 8, 4, 7, 0))
    with pytest.raises(ValueError, match="cannot precede"):
        _request(created_at=datetime(2026, 8, 4, 6, 59, tzinfo=timezone.utc))
    with pytest.raises(TypeError, match="InputAvailabilityStatus"):
        _request(data_availability="AVAILABLE")


def test_feature_artifact_rejects_float_non_finite_and_unsorted_explanations() -> None:
    with pytest.raises(TypeError, match="Decimal"):
        _artifact(score=11.0)
    with pytest.raises(ValueError, match="finite"):
        _artifact(score=Decimal("NaN"))
    with pytest.raises(ValueError, match="sorted"):
        _artifact(reason_codes=("Z_REASON", "A_REASON"))
    with pytest.raises(ValueError, match="unique"):
        _artifact(limitations=("SAME", "SAME"))
