"""PostgreSQL adapter from Research Dataset Authority to Candidate input DTOs."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

import psycopg

from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.research_qualification.domain import (
    ArtifactBinding,
    DatasetSource,
    DecisionInputDatasetDefinition,
    DecisionInputDatasetManifest,
    FeatureAvailabilityRule,
    FeatureCell,
    FeatureDefinition,
    FeatureIntervalUnit,
    FeatureMissingnessPolicy,
    FeatureSourceRequirement,
    FeatureValueType,
    parse_decision_input_dataset_manifest,
)
from market_regime_alpha.runtime.errors import (
    ArtifactIntegrityError,
    RuntimeNotFoundError,
)
from market_regime_alpha.selection.domain import (
    CandidateArtifactBinding,
    CandidateCellStatus,
    CandidateDatasetPopulation,
    CandidatePopulationCell,
    CandidatePopulationRow,
)
from market_regime_alpha.selection.ports.candidate_artifacts import (
    CandidateArtifactByteStore,
)
from market_regime_alpha.selection.ports.research_inputs import (
    CandidateDatasetDependency,
    CandidateFeatureDependency,
    CandidatePopulationDependency,
    CandidatePreparedResearchInput,
    CandidateResearchDependencySnapshot,
)
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.identity import ContentHash
from market_regime_alpha.shared.time import DecisionTime


def candidate_population_from_manifest(
    manifest: DecisionInputDatasetManifest,
    *,
    dataset: CandidateDatasetDependency,
    required_features: tuple[CandidateFeatureDependency, ...],
    dependency_sha256: str,
) -> CandidateDatasetPopulation:
    """Translate only required cells; lineage identities remain hashed."""

    if (
        manifest.dataset_id != dataset.dataset_id
        or manifest.decision_time != dataset.decision_time
        or manifest.universe_revision_id != dataset.universe_revision_id
        or manifest.eligibility_policy_id != dataset.eligibility_policy_id
    ):
        raise ArtifactIntegrityError(
            "Candidate Dataset manifest scope does not match PostgreSQL Authority"
        )
    if manifest.row_count != dataset.row_count:
        raise ArtifactIntegrityError(
            "Candidate Dataset manifest population count does not reconcile"
        )
    manifest_counts = (
        manifest.feature_count,
        manifest.source_count,
        manifest.cell_count,
        manifest.available_cell_count,
        manifest.missing_cell_count,
        manifest.unknown_cell_count,
        manifest.stale_cell_count,
        manifest.conflict_cell_count,
    )
    authority_counts = (
        dataset.feature_count,
        dataset.source_count,
        dataset.cell_count,
        dataset.available_cell_count,
        dataset.missing_cell_count,
        dataset.unknown_cell_count,
        dataset.stale_cell_count,
        dataset.conflict_cell_count,
    )
    if manifest_counts != authority_counts:
        raise ArtifactIntegrityError(
            "Candidate Dataset manifest counts do not match PostgreSQL Authority"
        )
    if (
        dataset_source_lineage_sha256(manifest.sources)
        != dataset.dataset_source_lineage_sha256
    ):
        raise ArtifactIntegrityError(
            "Candidate Dataset manifest lineage differs from DatasetSource Authority"
        )
    required_ids = tuple(item.feature_definition_id for item in required_features)
    if len(set(required_ids)) != len(required_ids):
        raise ValueError("Candidate required Feature dependencies must be unique")
    if not set(required_ids).issubset(manifest.feature_definition_ids):
        raise ArtifactIntegrityError(
            "Candidate policy requires a Feature absent from the Dataset"
        )
    feature_types = {
        item.feature_definition_id: item.value_type for item in required_features
    }
    rows: list[CandidatePopulationRow] = []
    for row in manifest.rows:
        cells = {item.feature_definition_id: item for item in row.cells}
        translated: list[CandidatePopulationCell] = []
        for feature_id in required_ids:
            try:
                cell = cells[feature_id]
            except KeyError as exc:
                raise ArtifactIntegrityError(
                    "Candidate Dataset row is missing a required Feature cell"
                ) from exc
            value = _candidate_numeric_value(
                cell,
                value_type=feature_types[feature_id],
            )
            translated.append(
                CandidatePopulationCell(
                    feature_definition_id=feature_id,
                    status=CandidateCellStatus(cell.status.value),
                    value=value,
                    reason_code=cell.reason_code,
                    cell_source_lineage_hash=ContentHash(
                        canonical_json_sha256(
                            {
                                "dataset_id": dataset.dataset_id,
                                "feature_definition_id": feature_id,
                                "instrument_id": row.instrument_id,
                                "reason_code": cell.reason_code,
                                "source_ids": tuple(sorted(cell.source_ids, key=str)),
                                "status": cell.status.value,
                                "value": value,
                            }
                        )
                    ),
                )
            )
        rows.append(
            CandidatePopulationRow(
                instrument_id=row.instrument_id,
                dataset_population_source_id=row.population_source_id,
                cells=tuple(translated),
            )
        )
    return CandidateDatasetPopulation(
        dataset_id=dataset.dataset_id,
        dataset_content_sha256=dataset.content_sha256,
        decision_time=dataset.decision_time,
        universe_revision_id=dataset.universe_revision_id,
        eligibility_policy_id=dataset.eligibility_policy_id,
        rows=tuple(rows),
        dependency_sha256=dependency_sha256,
    )


class PostgresCandidateResearchDependencyQueries:
    """Exact connection-bound Dataset and Feature dependency reads."""

    def __init__(self, connection: psycopg.Connection[Any]) -> None:
        self._connection = connection

    def feature_dependencies(
        self,
        required_features: tuple[CandidateFeatureDependency, ...],
        *,
        lock: bool,
    ) -> tuple[CandidateFeatureDependency, ...]:
        if not required_features:
            return ()
        requested_ids = tuple(item.feature_definition_id for item in required_features)
        if len(set(requested_ids)) != len(requested_ids):
            raise ValueError("Candidate required Feature dependencies must be unique")
        suffix = " FOR SHARE" if lock else ""
        rows = self._connection.execute(
            """
            SELECT feature_definition_id, content_sha256, value_type
            FROM mra.feature_definition
            WHERE feature_definition_id = ANY(%s)
            """
            + suffix,
            (list(requested_ids),),
        ).fetchall()
        actual_by_id = {
            UUID(str(row[0])): CandidateFeatureDependency(
                feature_definition_id=UUID(str(row[0])),
                content_sha256=str(row[1]),
                value_type=str(row[2]),
            )
            for row in rows
        }
        try:
            actual = tuple(actual_by_id[item] for item in requested_ids)
        except KeyError as exc:
            raise RuntimeNotFoundError(
                "one or more Candidate FeatureDefinition dependencies do not exist"
            ) from exc
        if actual != required_features:
            raise ArtifactIntegrityError(
                "Candidate FeatureDefinition dependency does not match Authority"
            )
        return actual

    def snapshot(
        self,
        *,
        dataset_id: UUID,
        required_features: tuple[CandidateFeatureDependency, ...],
        lock: bool,
    ) -> CandidateResearchDependencySnapshot:
        dataset = self._dataset_dependency(dataset_id, lock=lock)
        features = self.feature_dependencies(required_features, lock=lock)
        suffix = " FOR SHARE" if lock else ""
        feature_rows = self._connection.execute(
            """
            SELECT feature_definition_id
            FROM mra.dataset_source
            WHERE dataset_id = %s
              AND source_role = 'FEATURE_DEFINITION'
              AND feature_definition_id = ANY(%s)
            """
            + suffix,
            (dataset_id, [item.feature_definition_id for item in features]),
        ).fetchall()
        bound_features = {UUID(str(row[0])) for row in feature_rows}
        if bound_features != {item.feature_definition_id for item in features}:
            raise ArtifactIntegrityError(
                "Candidate FeatureDefinition is not bound to the Dataset"
            )
        population_rows = self._connection.execute(
            """
            SELECT dataset_source_id, instrument_id
            FROM mra.dataset_source
            WHERE dataset_id = %s
              AND source_role = 'POPULATION'
            ORDER BY instrument_id, dataset_source_id
            """
            + suffix,
            (dataset_id,),
        ).fetchall()
        population = tuple(
            CandidatePopulationDependency(
                population_dataset_source_id=UUID(str(row[0])),
                instrument_id=UUID(str(row[1])),
            )
            for row in population_rows
        )
        if len(population) != dataset.row_count:
            raise ArtifactIntegrityError(
                "Candidate Dataset population sources do not reconcile with row_count"
            )
        dependency_sha256 = canonical_json_sha256(
            {
                "dataset": dataset,
                "features": tuple(sorted(features, key=lambda item: str(item.feature_definition_id))),
                "population": population,
            }
        )
        return CandidateResearchDependencySnapshot(
            dataset=dataset,
            features=features,
            population=population,
            dependency_sha256=dependency_sha256,
        )

    def _dataset_dependency(
        self,
        dataset_id: UUID,
        *,
        lock: bool,
    ) -> CandidateDatasetDependency:
        suffix = " FOR SHARE" if lock else ""
        row = self._connection.execute(
            """
            SELECT dataset_id, dataset_kind, content_sha256, decision_time,
                   universe_revision_id, eligibility_policy_id, row_count,
                   feature_count, source_count, cell_count,
                   available_cell_count, missing_cell_count,
                   unknown_cell_count, stale_cell_count, conflict_cell_count,
                   manifest_artifact_id, manifest_content_sha256,
                   manifest_size_bytes, code_artifact_id,
                   code_content_sha256, code_size_bytes,
                   config_artifact_id, config_content_sha256,
                   config_size_bytes
            FROM mra.dataset
            WHERE dataset_id = %s
            """
            + suffix,
            (dataset_id,),
        ).fetchone()
        if row is None:
            raise RuntimeNotFoundError(f"Dataset {dataset_id} does not exist")
        if str(row[1]) != "DECISION_INPUT":
            raise ArtifactIntegrityError("Candidate requires a DECISION_INPUT Dataset")
        source_rows = self._connection.execute(
            """
            SELECT dataset_source_id, source_role, instrument_id,
                   universe_member_id, eligibility_assessment_id,
                   feature_definition_id, market_bar_revision_id,
                   market_instrument_fact_revision_id,
                   market_trading_session_id, market_source_gap_id,
                   market_capture_id
            FROM mra.dataset_source
            WHERE dataset_id = %s
            ORDER BY dataset_source_id
            """
            + suffix,
            (dataset_id,),
        ).fetchall()
        if len(source_rows) != int(row[8]):
            raise ArtifactIntegrityError(
                "Candidate DatasetSource count does not match Dataset Authority"
            )
        return CandidateDatasetDependency(
            dataset_id=UUID(str(row[0])),
            content_sha256=str(row[2]),
            decision_time=DecisionTime(row[3]),
            universe_revision_id=UUID(str(row[4])),
            eligibility_policy_id=UUID(str(row[5])),
            row_count=int(row[6]),
            feature_count=int(row[7]),
            source_count=int(row[8]),
            cell_count=int(row[9]),
            available_cell_count=int(row[10]),
            missing_cell_count=int(row[11]),
            unknown_cell_count=int(row[12]),
            stale_cell_count=int(row[13]),
            conflict_cell_count=int(row[14]),
            dataset_source_lineage_sha256=canonical_json_sha256(
                tuple(_database_source_payload(item) for item in source_rows)
            ),
            manifest_artifact=_candidate_artifact(row[15:18]),
            code_artifact=_candidate_artifact(row[18:21]),
            config_artifact=_candidate_artifact(row[21:24]),
        )


class PostgresCandidateResearchInputLoader:
    """Read and parse immutable Dataset bytes outside Candidate write UoWs."""

    def __init__(
        self,
        pool: TargetPostgresPool,
        byte_store: CandidateArtifactByteStore,
    ) -> None:
        self._pool = pool
        self._byte_store = byte_store

    def prepare(
        self,
        *,
        dataset_id: UUID,
        required_features: tuple[CandidateFeatureDependency, ...],
    ) -> CandidatePreparedResearchInput:
        with self._pool.connection(read_only=True) as connection:
            queries = PostgresCandidateResearchDependencyQueries(connection)
            snapshot = queries.snapshot(
                dataset_id=dataset_id,
                required_features=required_features,
                lock=False,
            )
            definition, feature_definitions = _research_dataset_definition(
                connection,
                dataset_id=dataset_id,
            )
        binding = snapshot.dataset.manifest_artifact
        verification = self._byte_store.verify(
            str(binding.content_sha256),
            expected_size=binding.size_bytes,
        )
        if verification.result != "VERIFIED":
            raise ArtifactIntegrityError(
                "Candidate Dataset manifest bytes failed exact verification"
            )
        content = self._byte_store.read_bytes(
            str(binding.content_sha256),
            expected_size=binding.size_bytes,
        )
        manifest = parse_decision_input_dataset_manifest(
            content,
            dataset=definition,
            feature_definitions=feature_definitions,
        )
        if str(manifest.content_sha256) != str(binding.content_sha256):
            raise ArtifactIntegrityError(
                "Candidate Dataset manifest hash does not match its binding"
            )
        population = candidate_population_from_manifest(
            manifest,
            dataset=snapshot.dataset,
            required_features=snapshot.features,
            dependency_sha256=snapshot.dependency_sha256,
        )
        prepared_population = tuple(
            CandidatePopulationDependency(
                population_dataset_source_id=row.dataset_population_source_id,
                instrument_id=row.instrument_id,
            )
            for row in population.rows
        )
        if prepared_population != snapshot.population:
            raise ArtifactIntegrityError(
                "Candidate manifest population differs from DatasetSource Authority"
            )
        return CandidatePreparedResearchInput(
            dataset=snapshot.dataset,
            features=snapshot.features,
            population=snapshot.population,
            rows=population.rows,
            manifest_verification=verification,
            dependency_sha256=snapshot.dependency_sha256,
        )


def _research_dataset_definition(
    connection: psycopg.Connection[Any],
    *,
    dataset_id: UUID,
) -> tuple[DecisionInputDatasetDefinition, tuple[FeatureDefinition, ...]]:
    row = connection.execute(
        """
        SELECT dataset_id, dataset_code, version, dataset_kind, decision_time,
               universe_revision_id, eligibility_policy_id,
               manifest_artifact_id, manifest_content_sha256,
               manifest_size_bytes, code_artifact_id, code_content_sha256,
               code_size_bytes, config_artifact_id, config_content_sha256,
               config_size_bytes, content_sha256
        FROM mra.dataset
        WHERE dataset_id = %s
        """,
        (dataset_id,),
    ).fetchone()
    if row is None:
        raise RuntimeNotFoundError(f"Dataset {dataset_id} does not exist")
    if str(row[3]) != "DECISION_INPUT":
        raise ArtifactIntegrityError("Candidate requires a DECISION_INPUT Dataset")
    feature_rows = connection.execute(
        """
        SELECT feature_definition_id
        FROM mra.dataset_source
        WHERE dataset_id = %s
          AND source_role = 'FEATURE_DEFINITION'
        ORDER BY feature_definition_id
        """,
        (dataset_id,),
    ).fetchall()
    feature_ids = tuple(UUID(str(item[0])) for item in feature_rows)
    definition = DecisionInputDatasetDefinition(
        dataset_id=UUID(str(row[0])),
        dataset_code=str(row[1]),
        version=int(row[2]),
        decision_time=DecisionTime(row[4]),
        universe_revision_id=UUID(str(row[5])),
        eligibility_policy_id=UUID(str(row[6])),
        feature_definition_ids=feature_ids,
        manifest_artifact=_research_artifact(row[7:10]),
        code_artifact=_research_artifact(row[10:13]),
        config_artifact=_research_artifact(row[13:16]),
    )
    if str(definition.content_sha256) != str(row[16]):
        raise ArtifactIntegrityError(
            "Candidate Dataset definition content hash does not reconcile"
        )
    features = _read_parser_feature_definitions(connection, feature_ids)
    return definition, features


def _read_parser_feature_definitions(
    connection: psycopg.Connection[Any],
    feature_definition_ids: tuple[UUID, ...],
) -> tuple[FeatureDefinition, ...]:
    """Map immutable parser facts without borrowing a Research repository."""

    if not feature_definition_ids:
        return ()
    rows = connection.execute(
        """
        SELECT feature_definition_id, feature_code, version,
               value_type, value_unit, frequency_value, frequency_unit,
               window_value, window_unit, lookback_value, lookback_unit,
               source_requirements, availability_rule, missingness_policy,
               algorithm_code, algorithm_version, algorithm_sha256,
               code_artifact_id, code_content_sha256, code_size_bytes,
               config_artifact_id, config_content_sha256,
               config_size_bytes, content_sha256
        FROM mra.feature_definition
        WHERE feature_definition_id = ANY(%s)
        ORDER BY feature_definition_id
        """,
        (list(feature_definition_ids),),
    ).fetchall()
    definitions = tuple(_parser_feature_definition(row) for row in rows)
    expected_ids = tuple(sorted(feature_definition_ids, key=str))
    if tuple(item.feature_definition_id for item in definitions) != expected_ids:
        raise RuntimeNotFoundError(
            "one or more Candidate parser FeatureDefinitions do not exist"
        )
    return definitions


def _parser_feature_definition(row: tuple[Any, ...]) -> FeatureDefinition:
    definition = FeatureDefinition(
        feature_definition_id=UUID(str(row[0])),
        feature_code=str(row[1]),
        version=int(row[2]),
        value_type=FeatureValueType(str(row[3])),
        value_unit=str(row[4]),
        frequency_value=int(row[5]),
        frequency_unit=FeatureIntervalUnit(str(row[6])),
        window_value=int(row[7]),
        window_unit=FeatureIntervalUnit(str(row[8])),
        lookback_value=int(row[9]),
        lookback_unit=FeatureIntervalUnit(str(row[10])),
        source_requirements=tuple(
            FeatureSourceRequirement(str(item)) for item in row[11]
        ),
        availability_rule=FeatureAvailabilityRule(str(row[12])),
        missingness_policy=FeatureMissingnessPolicy(str(row[13])),
        algorithm_code=str(row[14]),
        algorithm_version=str(row[15]),
        algorithm_sha256=str(row[16]),
        code_artifact=_research_artifact(row[17:20]),
        config_artifact=_research_artifact(row[20:23]),
    )
    if str(definition.content_sha256) != str(row[23]):
        raise ArtifactIntegrityError(
            "Candidate parser FeatureDefinition content hash does not reconcile"
        )
    return definition


def _candidate_numeric_value(
    cell: FeatureCell,
    *,
    value_type: str,
) -> Decimal | int | None:
    if value_type not in {"DECIMAL", "INTEGER"}:
        raise ArtifactIntegrityError(
            "Candidate V1 requires DECIMAL or INTEGER FeatureDefinitions"
        )
    if cell.status.value != "AVAILABLE":
        return None
    if value_type == "DECIMAL" and not isinstance(cell.value, Decimal):
        raise ArtifactIntegrityError("DECIMAL Candidate cell is not Decimal")
    if value_type == "INTEGER" and (
        isinstance(cell.value, bool) or not isinstance(cell.value, int)
    ):
        raise ArtifactIntegrityError("INTEGER Candidate cell is not an integer")
    if isinstance(cell.value, (Decimal, int)) and not isinstance(cell.value, bool):
        return cell.value
    raise ArtifactIntegrityError("Candidate cell does not contain exact numeric data")


def dataset_source_lineage_sha256(sources: tuple[DatasetSource, ...]) -> str:
    """Fingerprint full manifest lineage without creating another Authority."""

    return canonical_json_sha256(
        tuple(_manifest_source_payload(item) for item in sources)
    )


def _manifest_source_payload(source: DatasetSource) -> dict[str, object]:
    return {
        "dataset_source_id": source.dataset_source_id,
        "source_role": source.role.value,
        "instrument_id": source.instrument_id,
        "universe_member_id": source.universe_member_id,
        "eligibility_assessment_id": source.eligibility_assessment_id,
        "feature_definition_id": source.feature_definition_id,
        "market_bar_revision_id": source.market_bar_revision_id,
        "market_instrument_fact_revision_id": (
            source.market_instrument_fact_revision_id
        ),
        "market_trading_session_id": source.market_trading_session_id,
        "market_source_gap_id": source.market_source_gap_id,
        "market_capture_id": source.market_capture_id,
    }


def _database_source_payload(row: tuple[Any, ...]) -> dict[str, object]:
    return {
        "dataset_source_id": UUID(str(row[0])),
        "source_role": str(row[1]),
        "instrument_id": _optional_uuid(row[2]),
        "universe_member_id": _optional_uuid(row[3]),
        "eligibility_assessment_id": _optional_uuid(row[4]),
        "feature_definition_id": _optional_uuid(row[5]),
        "market_bar_revision_id": _optional_uuid(row[6]),
        "market_instrument_fact_revision_id": _optional_uuid(row[7]),
        "market_trading_session_id": _optional_uuid(row[8]),
        "market_source_gap_id": _optional_uuid(row[9]),
        "market_capture_id": _optional_uuid(row[10]),
    }


def _optional_uuid(value: object | None) -> UUID | None:
    return None if value is None else UUID(str(value))


def _candidate_artifact(values: tuple[Any, ...]) -> CandidateArtifactBinding:
    return CandidateArtifactBinding(
        artifact_id=UUID(str(values[0])),
        content_sha256=str(values[1]),
        size_bytes=int(values[2]),
    )


def _research_artifact(values: tuple[Any, ...]) -> ArtifactBinding:
    return ArtifactBinding(
        artifact_id=UUID(str(values[0])),
        content_sha256=str(values[1]),
        size_bytes=int(values[2]),
    )


__all__ = [
    "PostgresCandidateResearchDependencyQueries",
    "PostgresCandidateResearchInputLoader",
    "candidate_population_from_manifest",
    "dataset_source_lineage_sha256",
]
