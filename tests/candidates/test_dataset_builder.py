from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from market_regime_alpha.candidates.contracts import CandidatePopulation, TargetContract
from market_regime_alpha.candidates.dataset import (
    TargetMaterialization,
    TargetObservation,
    TargetObservationStatus,
    build_candidate_research_dataset,
)
from market_regime_alpha.core.identity import (
    ArtifactId,
    DatasetId,
    FeatureDefinitionId,
    FeatureMaterializationId,
    ProviderId,
    TargetId,
    UniverseId,
)
from market_regime_alpha.core.status import InputAvailabilityStatus
from market_regime_alpha.core.time import AsOfTime, AvailabilityTime, DecisionTime
from market_regime_alpha.data.contracts import DataEligibility, DatasetContract, ProviderReference
from market_regime_alpha.features.contracts import (
    FeatureDefinition,
    FeatureMaterialization,
    FeatureObservation,
)


DECISION_AT = datetime(2026, 7, 15, 6, 55, tzinfo=timezone.utc)
TARGET_OBSERVED_AT = DECISION_AT + timedelta(days=1, hours=8)
MATERIALIZED_AT = TARGET_OBSERVED_AT + timedelta(hours=1)


def _dataset(dataset_id: str, eligibility: DataEligibility) -> DatasetContract:
    return DatasetContract(
        dataset_id=DatasetId(dataset_id),
        schema_version="dataset-contract-v1",
        eligibility=eligibility,
        manifest_artifact_id=ArtifactId(f"manifest:{dataset_id}"),
        provider_references=(
            ProviderReference(
                provider_id=ProviderId("provider-controlled-fixture"),
                product="candidate-fixture",
                contract_version="v1",
            ),
        ),
        pit_correct_for_scope=True,
        scope="R5 Candidate rehearsal fixture",
        limitations=("fixture/rehearsal evidence only",),
    )


def _feature() -> FeatureDefinition:
    return FeatureDefinition(
        feature_id=FeatureDefinitionId("feature-relative-strength-20d-v1"),
        name="20D Relative Strength",
        semantic_family="Relative Strength",
        source_information_families=("PRICE_ONLY",),
        representation_method="relative-return",
        source_fields=("close",),
        frequency="1d",
        lookback="20 finalized trading bars",
        availability_rule="available after the current daily bar is finalized",
        missingness_policy="MISSING when required history is incomplete",
        research_status="EXPLORATORY_BASELINE",
        parameters=(("window", "20"),),
    )


def _target() -> TargetContract:
    return TargetContract(
        target_id=TargetId("target-decision-to-next-session-close-return-v1"),
        name="Decision Reference to Next Session Close Return",
        horizon="next-session",
        outcome="forward return",
        price_convention="next-session-close / finalized-decision-bar-close - 1",
        decision_time_convention="14:55 Asia/Shanghai; finalized and available information only",
        population_scope="complete eligible A-share Candidate Population",
        version="v1",
    )


def test_builder_preserves_full_population_and_explicit_missingness() -> None:
    universe_dataset = _dataset("dataset-universe-rehearsal-v1", DataEligibility.REHEARSAL)
    market_dataset = _dataset("dataset-market-exploratory-v1", DataEligibility.EXPLORATORY)
    population = CandidatePopulation(
        universe_id=UniverseId("universe-liquid-a-share-v1"),
        decision_time=DecisionTime(DECISION_AT),
        symbols=("000001.SZ", "000002.SZ", "000003.SZ"),
        source_dataset_ids=(universe_dataset.dataset_id,),
    )
    feature = _feature()
    materialization = FeatureMaterialization(
        materialization_id=FeatureMaterializationId("fm-rs20-20260715-v1"),
        definition_id=feature.feature_id,
        dataset_id=market_dataset.dataset_id,
        universe_id=population.universe_id,
        as_of=AsOfTime(DECISION_AT),
        code_revision="abc123",
        config_hash="feature-config-v1",
        observations=(
            FeatureObservation("000001.SZ", InputAvailabilityStatus.AVAILABLE, 0.12),
            FeatureObservation("000002.SZ", InputAvailabilityStatus.MISSING, None),
        ),
    )
    target = _target()
    target_materialization = TargetMaterialization(
        artifact_id=ArtifactId("target-materialization-20260715-v1"),
        target_id=target.target_id,
        source_dataset_id=market_dataset.dataset_id,
        universe_id=population.universe_id,
        decision_time=population.decision_time,
        materialized_at=AsOfTime(MATERIALIZED_AT),
        code_revision="abc123",
        config_hash="target-config-v1",
        observations=(
            TargetObservation(
                "000001.SZ",
                TargetObservationStatus.AVAILABLE,
                0.025,
                AvailabilityTime(TARGET_OBSERVED_AT),
            ),
            TargetObservation(
                "000002.SZ",
                TargetObservationStatus.MISSING,
                None,
                AvailabilityTime(TARGET_OBSERVED_AT),
            ),
        ),
    )

    result = build_candidate_research_dataset(
        population=population,
        dataset_contracts=(universe_dataset, market_dataset),
        feature_definitions=(feature,),
        feature_materializations=(materialization,),
        target_contract=target,
        target_materialization=target_materialization,
        limitations=("R5 rehearsal only",),
    )
    repeated = build_candidate_research_dataset(
        population=population,
        dataset_contracts=(market_dataset, universe_dataset),
        feature_definitions=(feature,),
        feature_materializations=(materialization,),
        target_contract=target,
        target_materialization=target_materialization,
        limitations=("R5 rehearsal only",),
    )

    assert result.dataset_id == repeated.dataset_id
    assert result.data_eligibility is DataEligibility.EXPLORATORY
    assert result.row_count == 3
    assert tuple(row.symbol for row in result.rows) == population.symbols

    first, second, third = result.rows
    assert first.feature_values[0].status is InputAvailabilityStatus.AVAILABLE
    assert first.feature_values[0].value == pytest.approx(0.12)
    assert first.target.status is TargetObservationStatus.AVAILABLE
    assert first.target.value == pytest.approx(0.025)

    assert second.feature_values[0].status is InputAvailabilityStatus.MISSING
    assert second.feature_values[0].value is None
    assert second.target.status is TargetObservationStatus.MISSING
    assert second.target.value is None

    assert third.feature_values[0].status is InputAvailabilityStatus.MISSING
    assert third.feature_values[0].value is None
    assert third.target.status is TargetObservationStatus.NOT_YET_OBSERVED
    assert third.target.value is None


def test_builder_rejects_future_feature_materialization() -> None:
    source = _dataset("dataset-rehearsal-v1", DataEligibility.REHEARSAL)
    population = CandidatePopulation(
        universe_id=UniverseId("universe-v1"),
        decision_time=DecisionTime(DECISION_AT),
        symbols=("000001.SZ",),
        source_dataset_ids=(source.dataset_id,),
    )
    feature = _feature()
    future_feature = FeatureMaterialization(
        materialization_id=FeatureMaterializationId("fm-future-v1"),
        definition_id=feature.feature_id,
        dataset_id=source.dataset_id,
        universe_id=population.universe_id,
        as_of=AsOfTime(DECISION_AT + timedelta(minutes=5)),
        code_revision="abc123",
        config_hash="feature-config-v1",
        observations=(FeatureObservation("000001.SZ", InputAvailabilityStatus.AVAILABLE, 0.12),),
    )
    target = _target()
    target_materialization = TargetMaterialization(
        artifact_id=ArtifactId("target-materialization-v1"),
        target_id=target.target_id,
        source_dataset_id=source.dataset_id,
        universe_id=population.universe_id,
        decision_time=population.decision_time,
        materialized_at=AsOfTime(MATERIALIZED_AT),
        code_revision="abc123",
        config_hash="target-config-v1",
        observations=(),
    )

    with pytest.raises(ValueError, match="feature materialization must not be from the future"):
        build_candidate_research_dataset(
            population=population,
            dataset_contracts=(source,),
            feature_definitions=(feature,),
            feature_materializations=(future_feature,),
            target_contract=target,
            target_materialization=target_materialization,
        )


def test_target_materialization_rejects_observation_at_or_before_decision_time() -> None:
    with pytest.raises(ValueError, match="future target observation must occur after decision_time"):
        TargetMaterialization(
            artifact_id=ArtifactId("target-materialization-invalid-v1"),
            target_id=TargetId("target-v1"),
            source_dataset_id=DatasetId("dataset-v1"),
            universe_id=UniverseId("universe-v1"),
            decision_time=DecisionTime(DECISION_AT),
            materialized_at=AsOfTime(DECISION_AT + timedelta(hours=1)),
            code_revision="abc123",
            config_hash="target-config-v1",
            observations=(
                TargetObservation(
                    "000001.SZ",
                    TargetObservationStatus.AVAILABLE,
                    0.01,
                    AvailabilityTime(DECISION_AT),
                ),
            ),
        )


def test_builder_rejects_unidentified_source_dataset() -> None:
    universe_source = _dataset("dataset-universe-v1", DataEligibility.REHEARSAL)
    market_source = _dataset("dataset-market-v1", DataEligibility.REHEARSAL)
    population = CandidatePopulation(
        universe_id=UniverseId("universe-v1"),
        decision_time=DecisionTime(DECISION_AT),
        symbols=("000001.SZ",),
        source_dataset_ids=(universe_source.dataset_id,),
    )
    feature = _feature()
    materialization = FeatureMaterialization(
        materialization_id=FeatureMaterializationId("fm-rs20-v1"),
        definition_id=feature.feature_id,
        dataset_id=market_source.dataset_id,
        universe_id=population.universe_id,
        as_of=AsOfTime(DECISION_AT),
        code_revision="abc123",
        config_hash="feature-config-v1",
        observations=(FeatureObservation("000001.SZ", InputAvailabilityStatus.AVAILABLE, 0.12),),
    )
    target = _target()
    target_materialization = TargetMaterialization(
        artifact_id=ArtifactId("target-materialization-v1"),
        target_id=target.target_id,
        source_dataset_id=market_source.dataset_id,
        universe_id=population.universe_id,
        decision_time=population.decision_time,
        materialized_at=AsOfTime(MATERIALIZED_AT),
        code_revision="abc123",
        config_hash="target-config-v1",
        observations=(),
    )

    with pytest.raises(ValueError, match="dataset contracts missing for"):
        build_candidate_research_dataset(
            population=population,
            dataset_contracts=(universe_source,),
            feature_definitions=(feature,),
            feature_materializations=(materialization,),
            target_contract=target,
            target_materialization=target_materialization,
        )
