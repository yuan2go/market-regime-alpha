"""R5 Candidate target materialization and research-panel construction.

The builder preserves the complete Candidate Population. Missing features and unresolved
targets remain explicit cells; no row is silently removed or imputed.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
import math
from typing import Any

from market_regime_alpha.candidates.contracts import CandidatePopulation, TargetContract
from market_regime_alpha.core.identity import (
    ArtifactId,
    DatasetId,
    FeatureDefinitionId,
    FeatureMaterializationId,
    TargetId,
    UniverseId,
)
from market_regime_alpha.core.status import InputAvailabilityStatus
from market_regime_alpha.core.time import AsOfTime, AvailabilityTime, DecisionTime
from market_regime_alpha.data.contracts import DataEligibility, DatasetContract
from market_regime_alpha.features.contracts import FeatureDefinition, FeatureMaterialization


_DATA_ELIGIBILITY_ORDER = {
    DataEligibility.UNQUALIFIED: 0,
    DataEligibility.EXPLORATORY: 1,
    DataEligibility.REHEARSAL: 2,
    DataEligibility.FORMAL_RESEARCH: 3,
}


def _require_non_empty(label: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{label} must be a non-empty trimmed string")


def _require_finite(label: str, value: float | None) -> None:
    if value is not None and not math.isfinite(float(value)):
        raise ValueError(f"{label} must be finite when present")


class TargetObservationStatus(str, Enum):
    """Observation state of a future Candidate target."""

    AVAILABLE = "AVAILABLE"
    NOT_YET_OBSERVED = "NOT_YET_OBSERVED"
    MISSING = "MISSING"
    INVALID = "INVALID"


@dataclass(frozen=True, slots=True)
class TargetObservation:
    """Realized or unresolved target state for one Candidate symbol."""

    symbol: str
    status: TargetObservationStatus
    value: float | None
    observed_at: AvailabilityTime | None = None

    def __post_init__(self) -> None:
        _require_non_empty("symbol", self.symbol)
        if not isinstance(self.status, TargetObservationStatus):
            raise TypeError("status must be a TargetObservationStatus")
        _require_finite("target value", self.value)
        if self.status is TargetObservationStatus.AVAILABLE:
            if self.value is None or self.observed_at is None:
                raise ValueError("AVAILABLE target requires value and observed_at")
        elif self.value is not None:
            raise ValueError("non-available target must not carry a usable value")
        if self.status is TargetObservationStatus.NOT_YET_OBSERVED and self.observed_at is not None:
            raise ValueError("NOT_YET_OBSERVED target must not carry observed_at")


@dataclass(frozen=True, slots=True)
class TargetMaterialization:
    """Versioned materialization of one Target Contract for one decision cross-section."""

    artifact_id: ArtifactId
    target_id: TargetId
    source_dataset_id: DatasetId
    universe_id: UniverseId
    decision_time: DecisionTime
    materialized_at: AsOfTime
    code_revision: str
    config_hash: str
    observations: tuple[TargetObservation, ...]

    def __post_init__(self) -> None:
        _require_non_empty("code_revision", self.code_revision)
        _require_non_empty("config_hash", self.config_hash)
        if self.materialized_at.value < self.decision_time.value:
            raise ValueError("target materialization cannot precede decision_time")
        symbols = [observation.symbol for observation in self.observations]
        if len(symbols) != len(set(symbols)):
            raise ValueError("target observations must have unique symbols")
        for observation in self.observations:
            if observation.observed_at is None:
                continue
            if observation.observed_at.value <= self.decision_time.value:
                raise ValueError("future target observation must occur after decision_time")
            if observation.observed_at.value > self.materialized_at.value:
                raise ValueError("target observed_at must not be after materialized_at")


@dataclass(frozen=True, slots=True)
class CandidateFeatureValue:
    """One registered feature cell retained in the Candidate research panel."""

    feature_id: FeatureDefinitionId
    status: InputAvailabilityStatus
    value: Any | None

    def __post_init__(self) -> None:
        if not isinstance(self.status, InputAvailabilityStatus):
            raise TypeError("status must be an InputAvailabilityStatus")
        if self.status is InputAvailabilityStatus.AVAILABLE and self.value is None:
            raise ValueError("AVAILABLE Candidate feature requires a value")
        if self.status is not InputAvailabilityStatus.AVAILABLE and self.value is not None:
            raise ValueError("unavailable Candidate feature must not carry a usable value")


@dataclass(frozen=True, slots=True)
class CandidateTargetValue:
    """Target cell retained in the Candidate research panel."""

    target_id: TargetId
    status: TargetObservationStatus
    value: float | None
    observed_at: AvailabilityTime | None = None


@dataclass(frozen=True, slots=True)
class CandidateDatasetRow:
    """One Decision Time × Candidate Symbol row."""

    symbol: str
    feature_values: tuple[CandidateFeatureValue, ...]
    target: CandidateTargetValue

    def __post_init__(self) -> None:
        _require_non_empty("symbol", self.symbol)
        feature_ids = [cell.feature_id for cell in self.feature_values]
        if len(feature_ids) != len(set(feature_ids)):
            raise ValueError("Candidate row feature identities must be unique")


@dataclass(frozen=True, slots=True)
class CandidateResearchDataset:
    """Reproducible Candidate panel for one decision cross-section and one target."""

    dataset_id: DatasetId
    source_dataset_ids: tuple[DatasetId, ...]
    data_eligibility: DataEligibility
    universe_id: UniverseId
    decision_time: DecisionTime
    target_id: TargetId
    target_materialization_artifact_id: ArtifactId
    feature_definition_ids: tuple[FeatureDefinitionId, ...]
    feature_materialization_ids: tuple[FeatureMaterializationId, ...]
    rows: tuple[CandidateDatasetRow, ...]
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.data_eligibility, DataEligibility):
            raise TypeError("data_eligibility must be a DataEligibility")
        if not self.source_dataset_ids:
            raise ValueError("Candidate research dataset requires source dataset identities")
        if len(self.source_dataset_ids) != len(set(self.source_dataset_ids)):
            raise ValueError("source_dataset_ids must be unique")
        if len(self.feature_definition_ids) != len(set(self.feature_definition_ids)):
            raise ValueError("feature_definition_ids must be unique")
        if len(self.feature_materialization_ids) != len(set(self.feature_materialization_ids)):
            raise ValueError("feature_materialization_ids must be unique")
        symbols = [row.symbol for row in self.rows]
        if len(symbols) != len(set(symbols)):
            raise ValueError("Candidate research dataset rows must have unique symbols")
        if tuple(sorted(symbols)) != tuple(symbols):
            raise ValueError("Candidate research dataset rows must be symbol-sorted")
        for row in self.rows:
            if tuple(cell.feature_id for cell in row.feature_values) != self.feature_definition_ids:
                raise ValueError("Candidate row feature order must match feature_definition_ids")
            if row.target.target_id != self.target_id:
                raise ValueError("Candidate row target identity mismatch")

    @property
    def row_count(self) -> int:
        return len(self.rows)


def build_candidate_research_dataset(
    *,
    population: CandidatePopulation,
    dataset_contracts: tuple[DatasetContract, ...],
    feature_definitions: tuple[FeatureDefinition, ...],
    feature_materializations: tuple[FeatureMaterialization, ...],
    target_contract: TargetContract,
    target_materialization: TargetMaterialization,
    limitations: tuple[str, ...] = (),
) -> CandidateResearchDataset:
    """Build one complete Candidate panel without filtering on feature or target availability."""

    if not feature_definitions:
        raise ValueError("Candidate dataset requires at least one Feature Definition")

    dataset_by_id = {contract.dataset_id: contract for contract in dataset_contracts}
    if len(dataset_by_id) != len(dataset_contracts):
        raise ValueError("dataset_contracts must have unique Dataset identities")

    definition_by_id = {definition.feature_id: definition for definition in feature_definitions}
    if len(definition_by_id) != len(feature_definitions):
        raise ValueError("feature_definitions must have unique Feature identities")

    materialization_by_definition = {
        materialization.definition_id: materialization
        for materialization in feature_materializations
    }
    if len(materialization_by_definition) != len(feature_materializations):
        raise ValueError("feature_materializations must have unique definition identities")
    if set(materialization_by_definition) != set(definition_by_id):
        raise ValueError("every Feature Definition requires exactly one matching materialization")

    if target_materialization.target_id != target_contract.target_id:
        raise ValueError("target materialization does not match Target Contract")
    if target_materialization.universe_id != population.universe_id:
        raise ValueError("target materialization universe does not match Candidate Population")
    if target_materialization.decision_time != population.decision_time:
        raise ValueError("target materialization decision_time does not match Candidate Population")

    required_dataset_ids: set[DatasetId] = set(population.source_dataset_ids)
    required_dataset_ids.add(target_materialization.source_dataset_id)

    for materialization in feature_materializations:
        if materialization.universe_id != population.universe_id:
            raise ValueError("feature materialization universe does not match Candidate Population")
        if materialization.as_of.value > population.decision_time.value:
            raise ValueError("feature materialization must not be from the future")
        required_dataset_ids.add(materialization.dataset_id)

    missing_contracts = sorted(str(dataset_id) for dataset_id in required_dataset_ids if dataset_id not in dataset_by_id)
    if missing_contracts:
        raise ValueError(f"dataset contracts missing for: {','.join(missing_contracts)}")

    source_dataset_ids = tuple(sorted(required_dataset_ids, key=str))
    data_eligibility = min(
        (dataset_by_id[dataset_id].eligibility for dataset_id in source_dataset_ids),
        key=_DATA_ELIGIBILITY_ORDER.__getitem__,
    )

    feature_maps = {
        definition_id: {observation.symbol: observation for observation in materialization.observations}
        for definition_id, materialization in materialization_by_definition.items()
    }
    target_map = {observation.symbol: observation for observation in target_materialization.observations}
    feature_definition_ids = tuple(definition.feature_id for definition in feature_definitions)
    feature_materialization_ids = tuple(
        materialization_by_definition[feature_id].materialization_id
        for feature_id in feature_definition_ids
    )

    rows: list[CandidateDatasetRow] = []
    for symbol in population.symbols:
        feature_values: list[CandidateFeatureValue] = []
        for feature_id in feature_definition_ids:
            observation = feature_maps[feature_id].get(symbol)
            if observation is None:
                feature_values.append(
                    CandidateFeatureValue(
                        feature_id=feature_id,
                        status=InputAvailabilityStatus.MISSING,
                        value=None,
                    )
                )
            else:
                feature_values.append(
                    CandidateFeatureValue(
                        feature_id=feature_id,
                        status=observation.status,
                        value=observation.value,
                    )
                )

        target_observation = target_map.get(symbol)
        if target_observation is None:
            target_value = CandidateTargetValue(
                target_id=target_contract.target_id,
                status=TargetObservationStatus.NOT_YET_OBSERVED,
                value=None,
                observed_at=None,
            )
        else:
            target_value = CandidateTargetValue(
                target_id=target_contract.target_id,
                status=target_observation.status,
                value=target_observation.value,
                observed_at=target_observation.observed_at,
            )

        rows.append(
            CandidateDatasetRow(
                symbol=symbol,
                feature_values=tuple(feature_values),
                target=target_value,
            )
        )

    dataset_id = _candidate_dataset_id(
        source_dataset_ids=source_dataset_ids,
        universe_id=population.universe_id,
        decision_time=population.decision_time,
        target_id=target_contract.target_id,
        target_materialization_artifact_id=target_materialization.artifact_id,
        feature_definition_ids=feature_definition_ids,
        feature_materialization_ids=feature_materialization_ids,
        population_symbols=population.symbols,
    )

    return CandidateResearchDataset(
        dataset_id=dataset_id,
        source_dataset_ids=source_dataset_ids,
        data_eligibility=data_eligibility,
        universe_id=population.universe_id,
        decision_time=population.decision_time,
        target_id=target_contract.target_id,
        target_materialization_artifact_id=target_materialization.artifact_id,
        feature_definition_ids=feature_definition_ids,
        feature_materialization_ids=feature_materialization_ids,
        rows=tuple(rows),
        limitations=limitations,
    )


def _candidate_dataset_id(
    *,
    source_dataset_ids: tuple[DatasetId, ...],
    universe_id: UniverseId,
    decision_time: DecisionTime,
    target_id: TargetId,
    target_materialization_artifact_id: ArtifactId,
    feature_definition_ids: tuple[FeatureDefinitionId, ...],
    feature_materialization_ids: tuple[FeatureMaterializationId, ...],
    population_symbols: tuple[str, ...],
) -> DatasetId:
    payload = {
        "schema_version": "candidate-research-dataset-v1",
        "source_dataset_ids": [str(value) for value in source_dataset_ids],
        "universe_id": str(universe_id),
        "decision_time": decision_time.isoformat(),
        "target_id": str(target_id),
        "target_materialization_artifact_id": str(target_materialization_artifact_id),
        "feature_definition_ids": [str(value) for value in feature_definition_ids],
        "feature_materialization_ids": [str(value) for value in feature_materialization_ids],
        "population_symbols": list(population_symbols),
    }
    canonical = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    digest = sha256(canonical.encode("utf-8")).hexdigest()
    return DatasetId(f"candidate-dataset-{digest[:24]}")
