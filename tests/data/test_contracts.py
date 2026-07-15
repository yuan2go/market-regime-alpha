from __future__ import annotations

from datetime import datetime, timezone

import pytest

from market_regime_alpha.core.identity import ArtifactId, DatasetId, ProviderId
from market_regime_alpha.core.time import RetrievedAt
from market_regime_alpha.data.contracts import (
    DataEligibility,
    DatasetContract,
    ProviderReference,
    SourceArtifactReference,
)


def test_formal_research_dataset_requires_pit_correct_scope() -> None:
    provider = ProviderReference(ProviderId("provider-fixture"), "bars", "v1")

    with pytest.raises(ValueError, match="FORMAL_RESEARCH requires pit_correct_for_scope"):
        DatasetContract(
            dataset_id=DatasetId("dataset-formal-v1"),
            schema_version="dataset-contract-v1",
            eligibility=DataEligibility.FORMAL_RESEARCH,
            manifest_artifact_id=ArtifactId("manifest-1"),
            provider_references=(provider,),
            pit_correct_for_scope=False,
            scope="candidate-formal-research",
        )


def test_dataset_contract_rejects_string_eligibility_that_could_bypass_formal_gate() -> None:
    provider = ProviderReference(ProviderId("provider-fixture"), "bars", "v1")

    with pytest.raises(TypeError, match="DataEligibility"):
        DatasetContract(
            dataset_id=DatasetId("dataset-formal-v1"),
            schema_version="dataset-contract-v1",
            eligibility="FORMAL_RESEARCH",  # type: ignore[arg-type]
            manifest_artifact_id=ArtifactId("manifest-1"),
            provider_references=(provider,),
            pit_correct_for_scope=False,
            scope="candidate-formal-research",
        )


def test_dataset_contract_requires_boolean_pit_scope_flag() -> None:
    provider = ProviderReference(ProviderId("provider-fixture"), "bars", "v1")

    with pytest.raises(TypeError, match="pit_correct_for_scope must be boolean"):
        DatasetContract(
            dataset_id=DatasetId("dataset-rehearsal-v1"),
            schema_version="dataset-contract-v1",
            eligibility=DataEligibility.REHEARSAL,
            manifest_artifact_id=ArtifactId("manifest-1"),
            provider_references=(provider,),
            pit_correct_for_scope=1,  # type: ignore[arg-type]
            scope="candidate-rehearsal",
        )


def test_dataset_contract_keeps_provider_and_dataset_identity_separate() -> None:
    first = ProviderReference(ProviderId("provider-a"), "bars", "v1")
    second = ProviderReference(ProviderId("provider-a"), "corporate-actions", "v1")

    dataset = DatasetContract(
        dataset_id=DatasetId("dataset-rehearsal-v1"),
        schema_version="dataset-contract-v1",
        eligibility=DataEligibility.REHEARSAL,
        manifest_artifact_id=ArtifactId("manifest-rehearsal-v1"),
        provider_references=(first, second),
        pit_correct_for_scope=True,
        scope="candidate-rehearsal",
        limitations=("not formal Alpha evidence",),
    )

    assert dataset.dataset_id != first.provider_id
    assert dataset.eligibility is DataEligibility.REHEARSAL
    assert len(dataset.provider_references) == 2


def test_source_artifact_requires_explicit_retrieval_time_and_content_hash() -> None:
    artifact = SourceArtifactReference(
        artifact_id=ArtifactId("source-artifact-1"),
        provider_id=ProviderId("provider-a"),
        retrieved_at=RetrievedAt(datetime(2026, 7, 15, 7, 0, tzinfo=timezone.utc)),
        content_hash="sha256:abc123",
        locator="provider://bars/2026-07-15",
    )

    assert artifact.retrieved_at.value.tzinfo is not None
    assert artifact.content_hash == "sha256:abc123"
