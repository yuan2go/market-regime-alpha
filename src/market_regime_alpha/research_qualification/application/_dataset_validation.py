"""Decision-input Dataset population and lineage reconciliation."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from market_regime_alpha.research_qualification.domain import (
    DatasetSourceRole,
    DecisionInputDatasetManifest,
    FeatureCellStatus,
    FeatureDefinition,
    FeatureSourceRequirement,
)
from market_regime_alpha.research_qualification.ports import (
    DatasetMarketSourceObservation,
    DatasetPopulationMember,
)
from market_regime_alpha.runtime.errors import (
    ArtifactIntegrityError,
    RuntimeStateConflictError,
)


def validate_population(
    manifest: DecisionInputDatasetManifest,
    expected_population: tuple[DatasetPopulationMember, ...],
) -> None:
    population_sources = tuple(
        source
        for source in manifest.sources
        if source.role is DatasetSourceRole.POPULATION
    )
    actual_population = tuple(
        sorted(
            (
                DatasetPopulationMember(
                    instrument_id=_required_uuid(
                        source.instrument_id,
                        "population instrument",
                    ),
                    universe_member_id=_required_uuid(
                        source.universe_member_id,
                        "population UniverseMember",
                    ),
                    eligibility_assessment_id=_required_uuid(
                        source.eligibility_assessment_id,
                        "population EligibilityAssessment",
                    ),
                )
                for source in population_sources
            ),
            key=lambda item: str(item.instrument_id),
        )
    )
    row_instruments = tuple(row.instrument_id for row in manifest.rows)
    expected_instruments = tuple(item.instrument_id for item in expected_population)
    if (
        actual_population != expected_population
        or row_instruments != expected_instruments
    ):
        raise RuntimeStateConflictError(
            "Decision-input Dataset population must equal the exact INCLUDED and "
            "ELIGIBLE intersection"
        )


def validate_market_lineage(
    manifest: DecisionInputDatasetManifest,
    *,
    features: tuple[FeatureDefinition, ...],
    observations: tuple[DatasetMarketSourceObservation, ...],
    knowledge_cutoff: datetime | None = None,
    simulated_event_cutoff: datetime | None = None,
) -> None:
    source_map = {source.dataset_source_id: source for source in manifest.sources}
    observation_map = {
        observation.dataset_source_id: observation for observation in observations
    }
    if (knowledge_cutoff is None) != (simulated_event_cutoff is None):
        raise ValueError("exploratory Dataset validation requires both clock cutoffs")
    if simulated_event_cutoff is not None and manifest.decision_time.value != simulated_event_cutoff:
        raise RuntimeStateConflictError("Dataset DecisionTime must equal its simulated event cutoff")
    visibility_cutoff = knowledge_cutoff or manifest.decision_time.value
    for observation in observations:
        if observation.decision_visible_at > visibility_cutoff:
            raise RuntimeStateConflictError(
                "Dataset Market source is not visible at DecisionTime"
                if knowledge_cutoff is None
                else "Dataset Market source is not visible at its allowed knowledge cutoff"
            )
        if simulated_event_cutoff is not None and (
            observation.event_cutoff_at is None
            or observation.event_cutoff_at > simulated_event_cutoff
        ):
            raise RuntimeStateConflictError(
                "Exploratory Dataset Market source exceeds simulated event cutoff"
            )
        if not observation.foundation_integrity:
            raise ArtifactIntegrityError(
                "Dataset Market source lacks Foundation Artifact integrity"
            )
    feature_map = {item.feature_definition_id: item for item in features}
    requirement_roles = {
        FeatureSourceRequirement.MARKET_BAR_REVISION: (
            DatasetSourceRole.MARKET_BAR_REVISION
        ),
        FeatureSourceRequirement.INSTRUMENT_FACT_REVISION: (
            DatasetSourceRole.MARKET_INSTRUMENT_FACT_REVISION
        ),
        FeatureSourceRequirement.TRADING_SESSION: (
            DatasetSourceRole.MARKET_TRADING_SESSION
        ),
        FeatureSourceRequirement.UNIVERSE_MEMBER: DatasetSourceRole.POPULATION,
        FeatureSourceRequirement.ELIGIBILITY_ASSESSMENT: (
            DatasetSourceRole.POPULATION
        ),
    }
    for row in manifest.rows:
        for cell in row.cells:
            definition = feature_map[cell.feature_definition_id]
            roles = {source_map[source_id].role for source_id in cell.source_ids}
            roles.add(DatasetSourceRole.POPULATION)
            if cell.status is FeatureCellStatus.AVAILABLE:
                required_roles = {
                    requirement_roles[item]
                    for item in definition.source_requirements
                }
                if not required_roles.issubset(roles):
                    raise RuntimeStateConflictError(
                        "AVAILABLE Feature cell lacks a declared source requirement"
                    )
            for source_id in cell.source_ids:
                cell_observation = observation_map.get(source_id)
                if (
                    cell_observation is not None
                    and cell_observation.instrument_id is not None
                    and cell_observation.instrument_id != row.instrument_id
                ):
                    raise RuntimeStateConflictError(
                        "Dataset Market lineage belongs to a different Instrument"
                    )


def _required_uuid(value: UUID | None, field: str) -> UUID:
    if value is None:
        raise ArtifactIntegrityError(f"Dataset manifest lost {field} identity")
    return value


__all__ = ["validate_market_lineage", "validate_population"]
