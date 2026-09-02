"""PostgreSQL Authority adapter for Research Definition aggregates."""

from typing import Any
from uuid import UUID

import psycopg

from market_regime_alpha.research_qualification.domain import (
    ArtifactBinding,
    DatasetSource,
    DatasetSourceRole,
    DecisionInputDatasetDefinition,
    DecisionInputDatasetManifest,
    FeatureAvailabilityRule,
    FeatureDefinition,
    FeatureIntervalUnit,
    FeatureMissingnessPolicy,
    FeatureSourceRequirement,
    FeatureValueType,
    FormalDatasetScope,
)
from market_regime_alpha.research_qualification.domain.exploratory import ExploratoryRetrospectiveDatasetScope
from market_regime_alpha.research_qualification.ports.repository import DatasetRecord
from market_regime_alpha.runtime.errors import (
    ArtifactIntegrityError,
    RuntimeNotFoundError,
)
from market_regime_alpha.shared.hashing import canonical_json_sha256


class PostgresResearchDefinitionRepository:
    """Persist only Dataset, DatasetSource, and FeatureDefinition Authority."""

    def __init__(self, connection: psycopg.Connection[Any]) -> None:
        self._connection = connection

    def insert_feature_definition(self, definition: FeatureDefinition) -> int:
        self._connection.execute(
            """
            INSERT INTO mra.feature_definition (
                feature_definition_id, feature_code, version,
                value_type, value_unit, frequency_value, frequency_unit,
                window_value, window_unit, lookback_value, lookback_unit,
                source_requirements, availability_rule, missingness_policy,
                algorithm_code, algorithm_version, algorithm_sha256,
                code_artifact_id, code_content_sha256, code_size_bytes,
                config_artifact_id, config_content_sha256, config_size_bytes,
                content_sha256
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            (
                definition.feature_definition_id,
                definition.feature_code,
                definition.version,
                definition.value_type.value,
                definition.value_unit,
                definition.frequency_value,
                definition.frequency_unit.value,
                definition.window_value,
                definition.window_unit.value,
                definition.lookback_value,
                definition.lookback_unit.value,
                [item.value for item in definition.source_requirements],
                definition.availability_rule.value,
                definition.missingness_policy.value,
                definition.algorithm_code,
                definition.algorithm_version,
                str(definition.algorithm_sha256),
                definition.code_artifact.artifact_id,
                str(definition.code_artifact.content_sha256),
                definition.code_artifact.size_bytes,
                definition.config_artifact.artifact_id,
                str(definition.config_artifact.content_sha256),
                definition.config_artifact.size_bytes,
                str(definition.content_sha256),
            ),
        )
        return definition.version

    def feature_definitions(
        self,
        feature_definition_ids: tuple[UUID, ...],
        *,
        lock: bool,
    ) -> tuple[FeatureDefinition, ...]:
        if not feature_definition_ids:
            return ()
        suffix = " FOR SHARE" if lock else ""
        rows = self._connection.execute(
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
            """
            + suffix,
            (list(feature_definition_ids),),
        ).fetchall()
        definitions = tuple(_feature_definition(row) for row in rows)
        if tuple(item.feature_definition_id for item in definitions) != tuple(
            sorted(feature_definition_ids, key=str)
        ):
            raise RuntimeNotFoundError(
                "one or more FeatureDefinition identities do not exist"
            )
        return definitions

    def insert_dataset(
        self,
        definition: DecisionInputDatasetDefinition,
        manifest: DecisionInputDatasetManifest,
    ) -> int:
        self._connection.execute(
            """
            INSERT INTO mra.dataset (
                dataset_id, dataset_code, version, dataset_kind,
                decision_time, universe_revision_id, eligibility_policy_id,
                manifest_artifact_id, manifest_content_sha256,
                manifest_size_bytes, code_artifact_id, code_content_sha256,
                code_size_bytes, config_artifact_id, config_content_sha256,
                config_size_bytes, content_sha256, row_count, feature_count,
                source_count, cell_count, available_cell_count,
                missing_cell_count, unknown_cell_count, stale_cell_count,
                conflict_cell_count
            )
            VALUES (
                %s, %s, %s, 'DECISION_INPUT', %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            (
                definition.dataset_id,
                definition.dataset_code,
                definition.version,
                definition.decision_time.value,
                definition.universe_revision_id,
                definition.eligibility_policy_id,
                definition.manifest_artifact.artifact_id,
                str(definition.manifest_artifact.content_sha256),
                definition.manifest_artifact.size_bytes,
                definition.code_artifact.artifact_id,
                str(definition.code_artifact.content_sha256),
                definition.code_artifact.size_bytes,
                definition.config_artifact.artifact_id,
                str(definition.config_artifact.content_sha256),
                definition.config_artifact.size_bytes,
                str(definition.content_sha256),
                manifest.row_count,
                manifest.feature_count,
                manifest.source_count,
                manifest.cell_count,
                manifest.available_cell_count,
                manifest.missing_cell_count,
                manifest.unknown_cell_count,
                manifest.stale_cell_count,
                manifest.conflict_cell_count,
            ),
        )
        with self._connection.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO mra.dataset_source (
                    dataset_source_id, dataset_id, source_role,
                    instrument_id, universe_revision_id, universe_member_id,
                    eligibility_policy_id, eligibility_assessment_id,
                    decision_time, membership_status, eligibility_result,
                    feature_definition_id, market_bar_revision_id,
                    market_instrument_fact_revision_id,
                    market_trading_session_id, market_source_gap_id,
                    market_capture_id
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    _dataset_source_parameters(definition, source)
                    for source in manifest.sources
                ),
            )
        return definition.version

    def dataset_record(self, dataset_id: UUID, *, lock: bool) -> DatasetRecord:
        suffix = " FOR SHARE" if lock else ""
        row = self._connection.execute(
            """
            SELECT dataset_id, version, content_sha256, row_count,
                   feature_count, source_count, cell_count,
                   available_cell_count, missing_cell_count,
                   unknown_cell_count, stale_cell_count, conflict_cell_count
            FROM mra.dataset
            WHERE dataset_id = %s
            """
            + suffix,
            (dataset_id,),
        ).fetchone()
        if row is None:
            raise RuntimeNotFoundError(f"Dataset {dataset_id} does not exist")
        return DatasetRecord(
            dataset_id=UUID(str(row[0])),
            version=int(row[1]),
            content_sha256=str(row[2]),
            row_count=int(row[3]),
            feature_count=int(row[4]),
            source_count=int(row[5]),
            cell_count=int(row[6]),
            available_cell_count=int(row[7]),
            missing_cell_count=int(row[8]),
            unknown_cell_count=int(row[9]),
            stale_cell_count=int(row[10]),
            conflict_cell_count=int(row[11]),
        )

    def dataset_sources(
        self,
        dataset_id: UUID,
        *,
        lock: bool,
    ) -> tuple[DatasetSource, ...]:
        suffix = " FOR SHARE" if lock else ""
        rows = self._connection.execute(
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
        return tuple(_dataset_source(row) for row in rows)

    def bind_formal_dataset(
        self, dataset_id: UUID, scope: FormalDatasetScope
    ) -> str:
        row = self._connection.execute(
            """
            WITH qualified AS (
                SELECT source.dataset_source_id,
                       coalesce(bar.content_sha256, fact.content_sha256,
                                session.content_sha256, gap.content_sha256,
                                capture.content_sha256) AS visibility_sha256
                FROM mra.dataset AS dataset
                JOIN mra.dataset_source AS source
                  ON source.dataset_id = dataset.dataset_id
                LEFT JOIN mra.qualified_market_bar_visibility AS bar
                  ON source.source_role = 'MARKET_BAR_REVISION'
                 AND bar.bar_revision_id = source.market_bar_revision_id
                 AND bar.provider_qualification_decision_id = %s
                 AND bar.qualified_decision_visible_at <= dataset.decision_time
                LEFT JOIN mra.qualified_instrument_fact_visibility AS fact
                  ON source.source_role = 'MARKET_INSTRUMENT_FACT_REVISION'
                 AND fact.fact_revision_id = source.market_instrument_fact_revision_id
                 AND fact.provider_qualification_decision_id = %s
                 AND fact.qualified_decision_visible_at <= dataset.decision_time
                LEFT JOIN mra.qualified_trading_session_visibility AS session
                  ON source.source_role = 'MARKET_TRADING_SESSION'
                 AND session.session_id = source.market_trading_session_id
                 AND session.provider_qualification_decision_id = %s
                 AND session.qualified_decision_visible_at <= dataset.decision_time
                LEFT JOIN mra.qualified_source_gap_visibility AS gap
                  ON source.source_role = 'MARKET_SOURCE_GAP'
                 AND gap.gap_id = source.market_source_gap_id
                 AND gap.provider_qualification_decision_id = %s
                 AND gap.qualified_decision_visible_at <= dataset.decision_time
                LEFT JOIN mra.provider_qualification_capture_member AS capture
                  ON source.source_role = 'MARKET_CAPTURE'
                 AND capture.capture_id = source.market_capture_id
                 AND capture.provider_qualification_decision_id = %s
                 AND capture.source_available_at <= dataset.decision_time
                WHERE dataset.dataset_id = %s
                  AND source.source_role IN (
                      'MARKET_BAR_REVISION', 'MARKET_INSTRUMENT_FACT_REVISION',
                      'MARKET_TRADING_SESSION', 'MARKET_SOURCE_GAP', 'MARKET_CAPTURE'
                  )
            )
            SELECT count(*), mra.canonical_sha256(mra.canonical_json_text(json_agg(json_build_object(
                       'dataset_source_id', dataset_source_id,
                       'visibility_sha256', visibility_sha256
                   ) ORDER BY dataset_source_id)::jsonb))
            FROM qualified WHERE visibility_sha256 IS NOT NULL
            """,
            (
                scope.provider_qualification_decision_id,
                scope.provider_qualification_decision_id,
                scope.provider_qualification_decision_id,
                scope.provider_qualification_decision_id,
                scope.provider_qualification_decision_id,
                dataset_id,
            ),
        ).fetchone()
        if row is None or int(row[0]) < 1 or row[1] is None:
            raise ArtifactIntegrityError("Formal Dataset has no qualified source roster")
        source_count = int(row[0])
        roster_hash = str(row[1])
        content = canonical_json_sha256(
            {
                "dataset_id": dataset_id,
                "formal_research_campaign_id": scope.formal_research_campaign_id,
                "provider_qualification_decision_id": scope.provider_qualification_decision_id,
                "qualified_source_count": source_count,
                "qualified_source_roster_sha256": roster_hash,
            }
        )
        self._connection.execute(
            """
            INSERT INTO mra.formal_research_dataset (
                formal_research_campaign_id, dataset_id,
                provider_qualification_decision_id,
                qualified_source_count, qualified_source_roster_sha256,
                content_sha256
            ) VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                scope.formal_research_campaign_id,
                dataset_id,
                scope.provider_qualification_decision_id,
                source_count,
                roster_hash,
                content,
            ),
        )
        return content

    def formal_dataset_matches(
        self, dataset_id: UUID, scope: FormalDatasetScope
    ) -> bool:
        row = self._connection.execute(
            """
            SELECT 1 FROM mra.formal_research_dataset
            WHERE formal_research_campaign_id = %s
              AND dataset_id = %s
              AND provider_qualification_decision_id = %s
            """,
            (
                scope.formal_research_campaign_id,
                dataset_id,
                scope.provider_qualification_decision_id,
            ),
        ).fetchone()
        return row is not None

    def bind_exploratory_retrospective_dataset(
        self,
        dataset_id: UUID,
        scope: ExploratoryRetrospectiveDatasetScope,
    ) -> str:
        row = self._connection.execute(
            """
            SELECT count(*),
                   mra.canonical_sha256(mra.canonical_json_text(coalesce(jsonb_agg(
                       jsonb_build_object(
                           'dataset_source_id', dataset_source_id,
                           'source_identity', coalesce(
                               market_bar_revision_id,
                               market_instrument_fact_revision_id,
                               market_trading_session_id,
                               market_source_gap_id,
                               market_capture_id
                           ),
                           'source_role', source_role
                       ) ORDER BY dataset_source_id
                   ), '[]'::jsonb)))
            FROM mra.dataset_source
            WHERE dataset_id = %s
              AND source_role IN (
                  'MARKET_BAR_REVISION', 'MARKET_INSTRUMENT_FACT_REVISION',
                  'MARKET_TRADING_SESSION', 'MARKET_SOURCE_GAP', 'MARKET_CAPTURE'
              )
            """,
            (dataset_id,),
        ).fetchone()
        if row is None or int(row[0]) < 1:
            raise ArtifactIntegrityError("Exploratory Dataset has no Market source roster")
        source_count = int(row[0])
        roster_hash = str(row[1])
        content_hash = canonical_json_sha256(
            {
                "dataset_id": dataset_id,
                "evidence_lane": scope.evidence_lane,
                "knowledge_cutoff": scope.knowledge_cutoff,
                "market_archive_id": scope.market_archive_id,
                "market_archive_seal_id": scope.market_archive_seal_id,
                "scope_content_sha256": str(scope.content_sha256),
                "simulated_event_cutoff": scope.simulated_event_cutoff,
                "source_count": source_count,
                "source_roster_sha256": roster_hash,
            }
        )
        self._connection.execute(
            """
            INSERT INTO mra.exploratory_retrospective_dataset (
                dataset_id, market_archive_id, market_archive_seal_id,
                evidence_lane, knowledge_cutoff, simulated_event_cutoff,
                scope_content_sha256, source_count,
                source_roster_sha256, content_sha256
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                dataset_id,
                scope.market_archive_id,
                scope.market_archive_seal_id,
                scope.evidence_lane.value,
                scope.knowledge_cutoff,
                scope.simulated_event_cutoff,
                str(scope.content_sha256),
                source_count,
                roster_hash,
                content_hash,
            ),
        )
        return content_hash

    def exploratory_retrospective_dataset_matches(
        self,
        dataset_id: UUID,
        scope: ExploratoryRetrospectiveDatasetScope,
    ) -> bool:
        row = self._connection.execute(
            """
            SELECT 1 FROM mra.exploratory_retrospective_dataset
            WHERE dataset_id = %s
              AND market_archive_id = %s
              AND market_archive_seal_id = %s
              AND evidence_lane = 'EXPLORATORY_RETROSPECTIVE'
              AND knowledge_cutoff = %s
              AND simulated_event_cutoff = %s
              AND scope_content_sha256 = %s
            """,
            (
                dataset_id,
                scope.market_archive_id,
                scope.market_archive_seal_id,
                scope.knowledge_cutoff,
                scope.simulated_event_cutoff,
                str(scope.content_sha256),
            ),
        ).fetchone()
        return row is not None


def _feature_definition(row: tuple[Any, ...]) -> FeatureDefinition:
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
        code_artifact=ArtifactBinding(
            artifact_id=UUID(str(row[17])),
            content_sha256=str(row[18]),
            size_bytes=int(row[19]),
        ),
        config_artifact=ArtifactBinding(
            artifact_id=UUID(str(row[20])),
            content_sha256=str(row[21]),
            size_bytes=int(row[22]),
        ),
    )
    if str(definition.content_sha256) != str(row[23]):
        raise ArtifactIntegrityError(
            "FeatureDefinition content hash does not reconcile"
        )
    return definition


def _dataset_source_parameters(
    definition: DecisionInputDatasetDefinition,
    source: DatasetSource,
) -> tuple[Any, ...]:
    is_population = source.role is DatasetSourceRole.POPULATION
    return (
        source.dataset_source_id,
        definition.dataset_id,
        source.role.value,
        source.instrument_id,
        definition.universe_revision_id if is_population else None,
        source.universe_member_id,
        definition.eligibility_policy_id if is_population else None,
        source.eligibility_assessment_id,
        definition.decision_time.value if is_population else None,
        "INCLUDED" if is_population else None,
        "ELIGIBLE" if is_population else None,
        source.feature_definition_id,
        source.market_bar_revision_id,
        source.market_instrument_fact_revision_id,
        source.market_trading_session_id,
        source.market_source_gap_id,
        source.market_capture_id,
    )


def _dataset_source(row: tuple[Any, ...]) -> DatasetSource:
    return DatasetSource(
        dataset_source_id=UUID(str(row[0])),
        role=DatasetSourceRole(str(row[1])),
        instrument_id=UUID(str(row[2])) if row[2] is not None else None,
        universe_member_id=UUID(str(row[3])) if row[3] is not None else None,
        eligibility_assessment_id=(
            UUID(str(row[4])) if row[4] is not None else None
        ),
        feature_definition_id=UUID(str(row[5])) if row[5] is not None else None,
        market_bar_revision_id=UUID(str(row[6])) if row[6] is not None else None,
        market_instrument_fact_revision_id=(
            UUID(str(row[7])) if row[7] is not None else None
        ),
        market_trading_session_id=(
            UUID(str(row[8])) if row[8] is not None else None
        ),
        market_source_gap_id=UUID(str(row[9])) if row[9] is not None else None,
        market_capture_id=UUID(str(row[10])) if row[10] is not None else None,
    )


__all__ = ["PostgresResearchDefinitionRepository"]
