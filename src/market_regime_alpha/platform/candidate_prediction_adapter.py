"""Equivalence-preserving B0/B1 projection into immutable PredictionRuns."""

from __future__ import annotations

from typing import Mapping

from market_regime_alpha.candidates.dataset import CandidateResearchDataset
from market_regime_alpha.core.identity import (
    ExperimentId,
    FeatureDefinitionId,
    ModelId,
)
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.features.rehearsal_baselines import (
    LIQUIDITY_20S_ID,
    MOMENTUM_5S_ID,
    VOLATILITY_20S_ID,
)
from market_regime_alpha.platform.contracts import (
    EvidenceLevel,
    EvaluationProtocolId,
    ModelDefinition,
    ModelRole,
)
from market_regime_alpha.platform.multi_model_slice import (
    CandidateModelSpec,
    CompositeCandidateModelSpec,
    SingleFeatureCandidateModelSpec,
    build_default_candidate_slice_specs,
    run_multi_model_candidate_slice,
)
from market_regime_alpha.platform.prediction_run import PredictionRun


B0_MOMENTUM_MODEL_ID = ModelId("platform-b0-momentum-v1")
B1_BALANCED_MODEL_ID = ModelId("platform-b1-balanced-v1")
DAILY_B0_B1_MODEL_IDS = (B0_MOMENTUM_MODEL_ID, B1_BALANCED_MODEL_ID)


def _daily_specs(
    dataset: CandidateResearchDataset,
) -> tuple[CandidateModelSpec, CandidateModelSpec]:
    required = (MOMENTUM_5S_ID, LIQUIDITY_20S_ID, VOLATILITY_20S_ID)
    if any(feature_id not in dataset.feature_definition_ids for feature_id in required):
        raise ValueError("daily B0/B1 adapter requires the frozen baseline Features")
    specs = build_default_candidate_slice_specs(
        momentum_feature_id=MOMENTUM_5S_ID,
        volume_feature_id=LIQUIDITY_20S_ID,
        volatility_feature_id=VOLATILITY_20S_ID,
    )
    if tuple(spec.model_id for spec in specs[:2]) != DAILY_B0_B1_MODEL_IDS:
        raise ValueError("frozen B0/B1 model identities changed")
    return specs[0], specs[1]


def b0_b1_model_definitions(
    dataset: CandidateResearchDataset,
) -> dict[ModelId, ModelDefinition]:
    """Materialize ModelDefinitions for the existing B0/B1 model identities."""

    b0, b1 = _daily_specs(dataset)
    if not isinstance(b0, SingleFeatureCandidateModelSpec):
        raise TypeError("frozen B0 specification changed type")
    if not isinstance(b1, CompositeCandidateModelSpec):
        raise TypeError("frozen B1 specification changed type")
    definitions = (
        ModelDefinition(
            model_id=b0.model_id,
            name="B0 Momentum",
            version="1.0.0",
            family="single-feature-candidate-baseline",
            role=ModelRole.CANDIDATE,
            target_id=dataset.target_id,
            universe_id=dataset.universe_id,
            feature_ids=(b0.feature_id,),
            implementation_ref=(
                "market_regime_alpha.candidates.baselines:"
                "rank_candidates_by_feature"
            ),
            parameter_hash=b0.config_hash,
            decision_time_convention="14:55 Asia/Shanghai",
            horizon="next trading session 10:30",
            supported_data_eligibilities=(DataEligibility.EXPLORATORY,),
        ),
        ModelDefinition(
            model_id=b1.model_id,
            name="B1 Balanced Composite",
            version="1.0.0",
            family="transparent-composite-candidate-baseline",
            role=ModelRole.CANDIDATE,
            target_id=dataset.target_id,
            universe_id=dataset.universe_id,
            feature_ids=tuple(
                component.feature_id for component in b1.composite.ordered_components
            ),
            implementation_ref=(
                "market_regime_alpha.candidates.composite_baseline:"
                "rank_candidates_by_transparent_composite"
            ),
            parameter_hash=b1.config_hash,
            decision_time_convention="14:55 Asia/Shanghai",
            horizon="next trading session 10:30",
            supported_data_eligibilities=(DataEligibility.EXPLORATORY,),
        ),
    )
    return {definition.model_id: definition for definition in definitions}


def publish_b0_b1_prediction_runs(
    dataset: CandidateResearchDataset,
    *,
    model_definitions: Mapping[ModelId, ModelDefinition],
    evaluation_protocol_id: EvaluationProtocolId,
    experiment_protocol_ids: Mapping[ModelId, ExperimentId],
    code_revision: str,
) -> tuple[PredictionRun, PredictionRun]:
    """Invoke unchanged B0/B1 rankings and project their complete outputs."""

    if dataset.data_eligibility is not DataEligibility.EXPLORATORY:
        raise ValueError("daily B0/B1 adapter is fixed at EXPLORATORY")
    specs = _daily_specs(dataset)
    if set(model_definitions) != set(DAILY_B0_B1_MODEL_IDS):
        raise ValueError("model_definitions must exactly bind daily B0/B1")
    if set(experiment_protocol_ids) != set(DAILY_B0_B1_MODEL_IDS):
        raise ValueError("experiment_protocol_ids must exactly bind daily B0/B1")
    _validate_model_definitions(dataset, specs, model_definitions)
    slice_run = run_multi_model_candidate_slice(
        dataset,
        model_specs=specs,
        code_revision=code_revision,
        top_k_values=(5,),
    )
    result: list[PredictionRun] = []
    for spec, ranking in zip(specs, slice_run.results, strict=True):
        feature_ids = _feature_ids(spec)
        materialization_ids = tuple(
            dataset.feature_materialization_ids[
                dataset.feature_definition_ids.index(feature_id)
            ]
            for feature_id in feature_ids
        )
        result.append(
            PredictionRun(
                model_id=ranking.model_id,
                model_definition_hash=model_definitions[
                    ranking.model_id
                ].definition_hash,
                target_id=dataset.target_id,
                evaluation_protocol_id=evaluation_protocol_id,
                experiment_protocol_id=experiment_protocol_ids[ranking.model_id],
                dataset_id=dataset.dataset_id,
                universe_id=dataset.universe_id,
                decision_time=dataset.decision_time,
                feature_definition_ids=feature_ids,
                feature_materialization_ids=materialization_ids,
                code_revision=code_revision,
                configuration_hash=ranking.config_hash,
                predictions=ranking.predictions,
                rejections=ranking.rejections,
                population_size=slice_run.population_size,
                ranking_coverage=ranking.ranking_coverage,
                data_eligibility=DataEligibility.EXPLORATORY,
                evidence_level=EvidenceLevel.EXPLORATORY,
            )
        )
    return result[0], result[1]


def _feature_ids(spec: CandidateModelSpec) -> tuple[FeatureDefinitionId, ...]:
    if isinstance(spec, SingleFeatureCandidateModelSpec):
        return (spec.feature_id,)
    return tuple(
        component.feature_id for component in spec.composite.ordered_components
    )


def _validate_model_definitions(
    dataset: CandidateResearchDataset,
    specs: tuple[CandidateModelSpec, CandidateModelSpec],
    definitions: Mapping[ModelId, ModelDefinition],
) -> None:
    for spec in specs:
        definition = definitions[spec.model_id]
        if (
            definition.model_id != spec.model_id
            or definition.role is not ModelRole.CANDIDATE
            or definition.target_id != dataset.target_id
            or definition.universe_id != dataset.universe_id
            or definition.feature_ids != _feature_ids(spec)
            or definition.parameter_hash != spec.config_hash
            or not definition.supports_data_eligibility(
                DataEligibility.EXPLORATORY
            )
        ):
            raise ValueError("ModelDefinition does not match frozen B0/B1 specification")
