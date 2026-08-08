"""Equivalence-preserving B0/B1 projection into immutable PredictionRuns."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from market_regime_alpha.candidates.dataset import CandidateResearchDataset
from market_regime_alpha.core.identity import (
    ArtifactId,
    ExperimentId,
    FeatureDefinitionId,
    ModelId,
    UniverseId,
)
from market_regime_alpha.evidence.canonical import canonical_hash
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
from market_regime_alpha.platform.runtime_governance import (
    ArtifactLineageReference,
    ModelVersionLineage,
    RuntimeModelLineage,
)


B0_MOMENTUM_MODEL_ID = ModelId("platform-b0-momentum-v1")
B1_BALANCED_MODEL_ID = ModelId("platform-b1-balanced-v1")
DAILY_B0_B1_MODEL_IDS = (B0_MOMENTUM_MODEL_ID, B1_BALANCED_MODEL_ID)
DAILY_CANDIDATE_UNIVERSE_CONTRACT_ID = UniverseId(
    "daily-candidate-universe-contract-v1"
)


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
            universe_id=DAILY_CANDIDATE_UNIVERSE_CONTRACT_ID,
            feature_ids=(b0.feature_id,),
            implementation_ref=(
                "market_regime_alpha.candidates.baselines:"
                "rank_candidates_by_feature"
            ),
            parameter_hash=b0.config_hash,
            decision_time_convention="14:55 Asia/Shanghai",
            horizon="next trading session 10:30",
            supported_data_eligibilities=(DataEligibility.EXPLORATORY,),
            compatibility_refs=("RUNTIME_UNIVERSE_BOUND_BY_SELECTION_LINEAGE",),
        ),
        ModelDefinition(
            model_id=b1.model_id,
            name="B1 Balanced Composite",
            version="1.0.0",
            family="transparent-composite-candidate-baseline",
            role=ModelRole.CANDIDATE,
            target_id=dataset.target_id,
            universe_id=DAILY_CANDIDATE_UNIVERSE_CONTRACT_ID,
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
            compatibility_refs=("RUNTIME_UNIVERSE_BOUND_BY_SELECTION_LINEAGE",),
        ),
    )
    return {definition.model_id: definition for definition in definitions}


def b0_b1_model_version_lineages(
    dataset: CandidateResearchDataset,
    *,
    model_definitions: Mapping[ModelId, ModelDefinition],
    evaluation_protocol_id: EvaluationProtocolId,
    code_revision: str,
    created_at: datetime,
) -> dict[ModelId, ModelVersionLineage]:
    """Build stable Model-version lineage for an explicit governance action."""

    _validate_model_definitions(dataset, _daily_specs(dataset), model_definitions)
    return {
        model_id: ModelVersionLineage.create(
            model_id=definition.model_id,
            model_version=definition.version,
            definition_hash=definition.definition_hash,
            target_id=definition.target_id,
            universe_contract_id=DAILY_CANDIDATE_UNIVERSE_CONTRACT_ID,
            feature_definition_ids=definition.feature_ids,
            model_parameter_hash=definition.parameter_hash,
            configuration=_configuration_reference(definition),
            implementation_ref=definition.implementation_ref,
            code_revision=code_revision,
            code_hash=_code_hash(definition, code_revision),
            validation_protocol_refs=(
                _validation_protocol_reference(evaluation_protocol_id),
            ),
            supported_data_eligibilities=definition.supported_data_eligibilities,
            created_at=created_at,
        )
        for model_id, definition in model_definitions.items()
    }


def b0_b1_runtime_lineages(
    dataset: CandidateResearchDataset,
    *,
    model_definitions: Mapping[ModelId, ModelDefinition],
    evaluation_protocol_id: EvaluationProtocolId,
    code_revision: str,
) -> dict[ModelId, RuntimeModelLineage]:
    """Bind one daily Dataset execution to stable governed model versions."""

    specs = _daily_specs(dataset)
    _validate_model_definitions(dataset, specs, model_definitions)
    materializations = dict(
        zip(
            dataset.feature_definition_ids,
            dataset.feature_materialization_ids,
            strict=True,
        )
    )
    return {
        spec.model_id: RuntimeModelLineage.create(
            model_id=spec.model_id,
            definition_hash=model_definitions[spec.model_id].definition_hash,
            dataset=ArtifactLineageReference(
                reference_kind="CANDIDATE_DATASET",
                artifact_id=ArtifactId(str(dataset.dataset_id)),
                content_hash=_dataset_hash(dataset),
            ),
            universe_id=dataset.universe_id,
            feature_definition_ids=_feature_ids(spec),
            feature_materializations=tuple(
                ArtifactLineageReference(
                    reference_kind="FEATURE_MATERIALIZATION",
                    artifact_id=ArtifactId(str(materializations[feature_id])),
                    content_hash=canonical_hash(
                        {
                            "feature_definition_id": str(feature_id),
                            "feature_materialization_id": str(
                                materializations[feature_id]
                            ),
                            "dataset_id": str(dataset.dataset_id),
                            "universe_id": str(dataset.universe_id),
                        }
                    ),
                )
                for feature_id in _feature_ids(spec)
            ),
            configuration=_configuration_reference(
                model_definitions[spec.model_id]
            ),
            code_revision=code_revision,
            code_hash=_code_hash(model_definitions[spec.model_id], code_revision),
            validation_protocol_refs=(
                _validation_protocol_reference(evaluation_protocol_id),
            ),
            data_eligibility=dataset.data_eligibility,
        )
        for spec in specs
    }


def publish_b0_b1_prediction_runs(
    dataset: CandidateResearchDataset,
    *,
    model_definitions: Mapping[ModelId, ModelDefinition],
    evaluation_protocol_id: EvaluationProtocolId,
    experiment_protocol_ids: Mapping[ModelId, ExperimentId],
    code_revision: str,
    selected_model_ids: tuple[ModelId, ...] = DAILY_B0_B1_MODEL_IDS,
) -> tuple[PredictionRun, ...]:
    """Invoke unchanged B0/B1 rankings and project their complete outputs."""

    if dataset.data_eligibility is not DataEligibility.EXPLORATORY:
        raise ValueError("daily B0/B1 adapter is fixed at EXPLORATORY")
    if not selected_model_ids or not set(selected_model_ids).issubset(
        DAILY_B0_B1_MODEL_IDS
    ):
        raise ValueError("selected_model_ids must be a non-empty B0/B1 subset")
    specs = tuple(
        spec
        for spec in _daily_specs(dataset)
        if spec.model_id in set(selected_model_ids)
    )
    if set(model_definitions) != set(DAILY_B0_B1_MODEL_IDS):
        raise ValueError("model_definitions must exactly bind daily B0/B1")
    if not set(selected_model_ids).issubset(experiment_protocol_ids):
        raise ValueError("experiment_protocol_ids must bind selected daily Models")
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
    return tuple(result)


def _feature_ids(spec: CandidateModelSpec) -> tuple[FeatureDefinitionId, ...]:
    if isinstance(spec, SingleFeatureCandidateModelSpec):
        return (spec.feature_id,)
    return tuple(
        component.feature_id for component in spec.composite.ordered_components
    )


def _validate_model_definitions(
    dataset: CandidateResearchDataset,
    specs: tuple[CandidateModelSpec, ...],
    definitions: Mapping[ModelId, ModelDefinition],
) -> None:
    for spec in specs:
        definition = definitions[spec.model_id]
        if (
            definition.model_id != spec.model_id
            or definition.role is not ModelRole.CANDIDATE
            or definition.target_id != dataset.target_id
            or definition.universe_id != DAILY_CANDIDATE_UNIVERSE_CONTRACT_ID
            or definition.feature_ids != _feature_ids(spec)
            or definition.parameter_hash != spec.config_hash
            or not definition.supports_data_eligibility(
                DataEligibility.EXPLORATORY
            )
        ):
            raise ValueError("ModelDefinition does not match frozen B0/B1 specification")


def _configuration_reference(
    definition: ModelDefinition,
) -> ArtifactLineageReference:
    return ArtifactLineageReference(
        reference_kind="MODEL_CONFIGURATION",
        artifact_id=ArtifactId(f"model-configuration:{definition.model_id}"),
        content_hash=f"sha256:{definition.parameter_hash}",
    )


def _validation_protocol_reference(
    evaluation_protocol_id: EvaluationProtocolId,
) -> ArtifactLineageReference:
    return ArtifactLineageReference(
        reference_kind="VALIDATION_PROTOCOL",
        artifact_id=ArtifactId(str(evaluation_protocol_id)),
        content_hash=canonical_hash(
            {
                "schema_version": "evaluation-protocol-reference-v1",
                "evaluation_protocol_id": str(evaluation_protocol_id),
            }
        ),
    )


def _code_hash(definition: ModelDefinition, code_revision: str) -> str:
    return canonical_hash(
        {
            "schema_version": "model-implementation-binding-v1",
            "implementation_ref": definition.implementation_ref,
            "code_revision": code_revision,
        }
    )


def _dataset_hash(dataset: CandidateResearchDataset) -> str:
    def value(item: Any) -> Any:
        return item.value if hasattr(item, "value") else item

    return canonical_hash(
        {
            "schema_version": "candidate-runtime-dataset-lineage-v1",
            "dataset_id": str(dataset.dataset_id),
            "source_dataset_ids": [str(item) for item in dataset.source_dataset_ids],
            "data_eligibility": dataset.data_eligibility.value,
            "universe_id": str(dataset.universe_id),
            "decision_time": dataset.decision_time.value.isoformat(),
            "population_symbols": list(dataset.population_symbols),
            "target_id": str(dataset.target_id),
            "feature_definition_ids": [
                str(item) for item in dataset.feature_definition_ids
            ],
            "feature_materialization_ids": [
                str(item) for item in dataset.feature_materialization_ids
            ],
            "rows": [
                {
                    "symbol": row.symbol,
                    "features": [
                        {
                            "feature_id": str(cell.feature_id),
                            "status": cell.status.value,
                            "value": value(cell.value),
                        }
                        for cell in row.feature_values
                    ],
                    "target": {
                        "target_id": str(row.target.target_id),
                        "status": row.target.status.value,
                        "value": row.target.value,
                        "observed_at": (
                            None
                            if row.target.observed_at is None
                            else row.target.observed_at.value.isoformat()
                        ),
                    },
                }
                for row in dataset.rows
            ],
            "limitations": list(dataset.limitations),
        }
    )
