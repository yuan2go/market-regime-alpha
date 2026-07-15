from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from market_regime_alpha.candidates.contracts import (
    CandidateExpiryTime,
    CandidatePrediction,
    TargetContract,
    build_candidate_population,
)
from market_regime_alpha.core.identity import (
    ArtifactId,
    DatasetId,
    FeatureDefinitionId,
    FeatureMaterializationId,
    ModelId,
    ProviderId,
    TargetId,
    UniverseId,
)
from market_regime_alpha.core.status import InputAvailabilityStatus
from market_regime_alpha.core.time import AsOfTime, DecisionTime
from market_regime_alpha.data.contracts import DataEligibility, DatasetContract, ProviderReference
from market_regime_alpha.features.contracts import (
    FeatureDefinition,
    FeatureMaterialization,
    FeatureObservation,
    FeatureRegistry,
)
from market_regime_alpha.research.experiment_identity import ExperimentIdentity
from market_regime_alpha.universe.contracts import (
    PITUniverseSnapshot,
    TradingEligibilityRecord,
    TradingEligibilitySnapshot,
    TradingEligibilityStatus,
    UniverseMembershipRecord,
)


DECISION_AT = datetime(2026, 7, 15, 6, 55, tzinfo=timezone.utc)


def test_minimal_data_universe_feature_candidate_research_spine() -> None:
    dataset = DatasetContract(
        dataset_id=DatasetId("dataset-candidate-rehearsal-v1"),
        schema_version="dataset-contract-v1",
        eligibility=DataEligibility.REHEARSAL,
        manifest_artifact_id=ArtifactId("manifest-candidate-rehearsal-v1"),
        provider_references=(
            ProviderReference(
                provider_id=ProviderId("provider-controlled-fixture"),
                product="bars-and-eligibility",
                contract_version="v1",
            ),
        ),
        pit_correct_for_scope=True,
        scope="candidate-rehearsal",
        limitations=("rehearsal only; not formal Alpha evidence",),
    )

    universe = PITUniverseSnapshot(
        universe_id=UniverseId("universe-liquid-a-share-v1"),
        as_of=AsOfTime(DECISION_AT),
        source_dataset_id=dataset.dataset_id,
        evidence_artifact_id=ArtifactId("universe-artifact-v1"),
        method_version="liquid-a-share-v1",
        records=(
            UniverseMembershipRecord("000001.SZ", True),
            UniverseMembershipRecord("000002.SZ", True),
            UniverseMembershipRecord("000003.SZ", False),
        ),
    )
    eligibility = TradingEligibilitySnapshot(
        as_of=AsOfTime(DECISION_AT),
        source_dataset_id=dataset.dataset_id,
        evidence_artifact_id=ArtifactId("eligibility-artifact-v1"),
        records=(
            TradingEligibilityRecord("000001.SZ", TradingEligibilityStatus.ELIGIBLE),
            TradingEligibilityRecord("000002.SZ", TradingEligibilityStatus.ELIGIBLE),
            TradingEligibilityRecord("000003.SZ", TradingEligibilityStatus.INELIGIBLE),
        ),
    )
    population = build_candidate_population(
        universe,
        eligibility,
        decision_time=DecisionTime(DECISION_AT),
    )

    feature = FeatureDefinition(
        feature_id=FeatureDefinitionId("feature-relative-strength-20d-v1"),
        name="20D Relative Strength",
        semantic_family="Relative Strength",
        source_information_families=("PRICE_ONLY",),
        representation_method="relative-return",
        parameters=(("window", "20"),),
    )
    registry = FeatureRegistry()
    registry.register(feature)
    materialization = FeatureMaterialization(
        materialization_id=FeatureMaterializationId("fm-rs20-20260715-v1"),
        definition_id=feature.feature_id,
        dataset_id=dataset.dataset_id,
        universe_id=universe.universe_id,
        as_of=AsOfTime(DECISION_AT),
        code_revision="abc123",
        config_hash="feature-config-v1",
        observations=(
            FeatureObservation("000001.SZ", InputAvailabilityStatus.AVAILABLE, 0.12),
            FeatureObservation("000002.SZ", InputAvailabilityStatus.AVAILABLE, 0.08),
        ),
    )

    target = TargetContract(
        target_id=TargetId("target-next-session-return-v1"),
        name="Next Session Return",
        horizon="next-session",
        outcome="return",
        price_convention="next-eligible-open-to-close",
        decision_time_convention="14:55 Asia/Shanghai closed information only",
        population_scope="eligible A-share Candidate Population",
        version="v1",
    )
    model_id = ModelId("candidate-baseline-rank-v1")
    experiment = ExperimentIdentity(
        code_revision="abc123",
        dataset_id=dataset.dataset_id,
        config_hash="candidate-experiment-config-v1",
        universe_id=universe.universe_id,
        target_id=target.target_id,
        feature_definition_ids=(feature.feature_id,),
        feature_materialization_ids=(materialization.materialization_id,),
        model_id=model_id,
    )
    prediction = CandidatePrediction(
        symbol="000001.SZ",
        universe_id=universe.universe_id,
        model_id=model_id,
        target_id=target.target_id,
        decision_time=DecisionTime(DECISION_AT),
        experiment_id=experiment.experiment_id,
        population_size=len(population.symbols),
        model_score=0.12,
        rank=1,
        percentile=1.0,
        expires_at=CandidateExpiryTime(DECISION_AT + timedelta(days=1)),
    )

    assert dataset.eligibility is DataEligibility.REHEARSAL
    assert population.symbols == ("000001.SZ", "000002.SZ")
    assert materialization.available_symbols == population.symbols
    assert prediction.rank == 1
    assert prediction.calibrated_probability is None
    assert prediction.experiment_id == experiment.experiment_id


def test_score_cannot_be_laundered_into_invalid_probability_semantics() -> None:
    with pytest.raises(ValueError, match="calibrated_probability must be in \[0, 1\]"):
        CandidatePrediction(
            symbol="000001.SZ",
            universe_id=UniverseId("universe-v1"),
            model_id=ModelId("model-v1"),
            target_id=TargetId("target-v1"),
            decision_time=DecisionTime(DECISION_AT),
            experiment_id=ExperimentIdentity(
                code_revision="abc123",
                dataset_id=DatasetId("dataset-v1"),
                config_hash="config-v1",
            ).experiment_id,
            model_score=82.0,
            calibrated_probability=82.0,
        )
