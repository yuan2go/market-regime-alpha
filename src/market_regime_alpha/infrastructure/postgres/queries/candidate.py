"""Read-only PostgreSQL projections for Candidate funnel and dossier views."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.runtime.errors import (
    ArtifactIntegrityError,
    RuntimeNotFoundError,
)
from market_regime_alpha.selection.ports.candidate_queries import (
    CandidateDatasetSourceLineage,
    CandidateDossierComponent,
    CandidateDossierRecord,
    CandidateFunnelComponentDiagnostic,
    CandidateFunnelRecord,
)


class PostgresCandidateQueryProvider:
    """Serve immutable Candidate explanations without acquiring write authority."""

    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool

    def funnel(self, candidate_set_id: UUID) -> CandidateFunnelRecord:
        with self._pool.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT candidate_set_id, candidate_policy_id, dataset_id,
                       dataset_population_count, population_count,
                       rankable_count, unrankable_count, selected_count,
                       ranked_not_selected_count, score_component_count,
                       ranking_status, composite_distinct_count,
                       requested_top_k, boundary_score, boundary_rank,
                       strictly_above_boundary_count, boundary_group_count,
                       selected_overflow_count, boundary_has_tie,
                       boundary_tie_expanded, actual_population_count,
                       actual_selected_count,
                       actual_ranked_not_selected_count,
                       actual_unrankable_count,
                       strict_complete_case_unrankable_count,
                       actual_score_component_count, population_reconciled,
                       rankable_reconciled, score_matrix_reconciled
                FROM mra.candidate_funnel
                WHERE candidate_set_id = %s
                """,
                (candidate_set_id,),
            ).fetchone()
            if row is None:
                raise RuntimeNotFoundError(
                    f"CandidateSet {candidate_set_id} does not exist"
                )
            ranking_row = connection.execute(
                """
                SELECT
                    candidate_set.composite_distinct_count =
                        ranking_facts.actual_composite_distinct_count
                    AND NOT EXISTS (
                        SELECT 1
                        FROM (
                            SELECT ranked.competition_rank,
                                   rank() OVER (
                                       ORDER BY ranked.composite_score DESC
                                   ) AS computed_competition_rank
                            FROM mra.candidate AS ranked
                            WHERE ranked.candidate_set_id =
                                  candidate_set.candidate_set_id
                              AND ranked.disposition <> 'UNRANKABLE'
                        ) AS ranked_facts
                        WHERE ranked_facts.competition_rank IS DISTINCT FROM
                              ranked_facts.computed_competition_rank
                    )
                    AND (
                        (
                            candidate_set.rankable_count = 0
                            AND ranking_facts.actual_boundary_score IS NULL
                            AND ranking_facts.actual_strictly_above_count = 0
                            AND ranking_facts.actual_boundary_group_count = 0
                        )
                        OR
                        (
                            candidate_set.rankable_count > 0
                            AND ranking_facts.actual_boundary_score
                                IS NOT DISTINCT FROM
                                candidate_set.boundary_score
                            AND ranking_facts.actual_strictly_above_count =
                                candidate_set.strictly_above_boundary_count
                            AND ranking_facts.actual_boundary_group_count =
                                candidate_set.boundary_group_count
                            AND ranking_facts.invalid_selected_count = 0
                            AND ranking_facts.invalid_excluded_count = 0
                        )
                    ) AS ranking_reconciled,
                    candidate_set.component_count
                FROM mra.candidate_set AS candidate_set
                CROSS JOIN LATERAL (
                    SELECT
                        count(DISTINCT candidate.composite_score) FILTER (
                            WHERE candidate.disposition <> 'UNRANKABLE'
                        ) AS actual_composite_distinct_count,
                        min(candidate.composite_score) FILTER (
                            WHERE candidate.disposition = 'SELECTED'
                        ) AS actual_boundary_score,
                        count(*) FILTER (
                            WHERE candidate.disposition <> 'UNRANKABLE'
                              AND candidate.composite_score >
                                  candidate_set.boundary_score
                        ) AS actual_strictly_above_count,
                        count(*) FILTER (
                            WHERE candidate.disposition <> 'UNRANKABLE'
                              AND candidate.composite_score =
                                  candidate_set.boundary_score
                        ) AS actual_boundary_group_count,
                        count(*) FILTER (
                            WHERE candidate.disposition = 'SELECTED'
                              AND candidate.composite_score <
                                  candidate_set.boundary_score
                        ) AS invalid_selected_count,
                        count(*) FILTER (
                            WHERE candidate.disposition =
                                  'RANKED_NOT_SELECTED'
                              AND candidate.composite_score >=
                                  candidate_set.boundary_score
                        ) AS invalid_excluded_count
                    FROM mra.candidate AS candidate
                    WHERE candidate.candidate_set_id =
                          candidate_set.candidate_set_id
                ) AS ranking_facts
                WHERE candidate_set.candidate_set_id = %s
                """,
                (candidate_set_id,),
            ).fetchone()
            diagnostic_rows = connection.execute(
                """
                SELECT diagnostic.candidate_policy_component_id,
                       diagnostic.feature_definition_id,
                       diagnostic.observed_count,
                       diagnostic.distinct_count,
                       diagnostic.raw_available_count,
                       diagnostic.missing_count,
                       diagnostic.unknown_count,
                       diagnostic.stale_count,
                       diagnostic.conflict_count,
                       diagnostic.available_but_not_observed_count,
                       diagnostic.rank_information_status
                FROM mra.candidate_component_diagnostic AS diagnostic
                JOIN mra.candidate_set AS candidate_set
                  ON candidate_set.candidate_set_id =
                     diagnostic.candidate_set_id
                JOIN mra.candidate_policy_component AS component
                  ON component.candidate_policy_id =
                     candidate_set.candidate_policy_id
                 AND component.candidate_policy_component_id =
                     diagnostic.candidate_policy_component_id
                 AND component.feature_definition_id =
                     diagnostic.feature_definition_id
                WHERE diagnostic.candidate_set_id = %s
                ORDER BY component.ordinal
                """,
                (candidate_set_id,),
            ).fetchall()
        if ranking_row is None:
            raise ArtifactIntegrityError(
                "Candidate funnel lost its CandidateSet ranking facts"
            )
        if len(diagnostic_rows) != int(ranking_row[1]):
            raise ArtifactIntegrityError(
                "Candidate funnel component diagnostics do not reconcile with its Policy"
            )
        return _funnel_record(
            row,
            ranking_reconciled=bool(ranking_row[0]),
            component_diagnostics=tuple(
                _funnel_component_diagnostic(item) for item in diagnostic_rows
            ),
        )

    def dossier(
        self,
        *,
        candidate_set_id: UUID,
        instrument_id: UUID,
    ) -> CandidateDossierRecord:
        with self._pool.connection(read_only=True) as connection:
            header = connection.execute(
                """
                SELECT candidate_set.candidate_set_id,
                       candidate.candidate_id,
                       candidate_set.candidate_policy_id,
                       dataset.dataset_id, dataset.content_sha256,
                       dataset.manifest_artifact_id,
                       dataset.manifest_content_sha256,
                       dataset.manifest_size_bytes,
                       candidate.instrument_id,
                       population_source.dataset_source_id,
                       population_source.universe_member_id,
                       population_source.eligibility_assessment_id,
                       candidate.disposition, candidate.reason_code,
                       candidate.composite_score, candidate.competition_rank,
                       dataset.source_count,
                       candidate_set.component_count
                FROM mra.candidate AS candidate
                JOIN mra.candidate_set AS candidate_set
                  ON candidate_set.candidate_set_id = candidate.candidate_set_id
                 AND candidate_set.candidate_policy_id =
                     candidate.candidate_policy_id
                 AND candidate_set.dataset_id = candidate.dataset_id
                JOIN mra.dataset AS dataset
                  ON dataset.dataset_id = candidate_set.dataset_id
                 AND dataset.content_sha256 =
                     candidate_set.dataset_content_sha256
                JOIN mra.artifact AS manifest_artifact
                  ON manifest_artifact.artifact_id =
                     dataset.manifest_artifact_id
                 AND manifest_artifact.content_sha256 =
                     dataset.manifest_content_sha256
                 AND manifest_artifact.size_bytes =
                     dataset.manifest_size_bytes
                JOIN mra.dataset_source AS population_source
                  ON population_source.dataset_source_id =
                     candidate.dataset_population_source_id
                 AND population_source.dataset_id = candidate_set.dataset_id
                 AND population_source.instrument_id = candidate.instrument_id
                 AND population_source.source_role = 'POPULATION'
                WHERE candidate.candidate_set_id = %s
                  AND candidate.instrument_id = %s
                """,
                (candidate_set_id, instrument_id),
            ).fetchone()
            if header is None:
                raise RuntimeNotFoundError(
                    "Candidate dossier does not exist for the exact "
                    f"CandidateSet/Instrument identity {candidate_set_id}/{instrument_id}"
                )
            dataset_source_rows = connection.execute(
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
                """,
                (UUID(str(header[3])),),
            ).fetchall()
            component_rows = connection.execute(
                """
                SELECT
                    component.candidate_policy_component_id,
                    feature.feature_definition_id,
                    feature.content_sha256,
                    feature.value_type,
                    feature_source.dataset_source_id,
                    component.direction,
                    component.declared_weight,
                    score.raw_status,
                    score.raw_decimal_value,
                    score.raw_integer_value,
                    score.raw_reason_code,
                    score.percentile,
                    score.normalized_weight,
                    score.contribution,
                    score.cell_source_lineage_hash,
                    diagnostic.observed_count,
                    diagnostic.distinct_count,
                    diagnostic.missing_count,
                    diagnostic.unknown_count,
                    diagnostic.stale_count,
                    diagnostic.conflict_count,
                    diagnostic.raw_available_count,
                    diagnostic.available_but_not_observed_count,
                    diagnostic.rank_information_status
                FROM mra.candidate_score_component AS score
                JOIN mra.candidate_policy_component AS component
                  ON component.candidate_policy_component_id =
                     score.candidate_policy_component_id
                 AND component.candidate_policy_id =
                     score.candidate_policy_id
                 AND component.feature_definition_id =
                     score.feature_definition_id
                 AND component.feature_content_sha256 =
                     score.feature_content_sha256
                 AND component.feature_value_type = score.feature_value_type
                JOIN mra.feature_definition AS feature
                  ON feature.feature_definition_id =
                     score.feature_definition_id
                 AND feature.content_sha256 = score.feature_content_sha256
                 AND feature.value_type = score.feature_value_type
                JOIN mra.dataset_source AS feature_source
                  ON feature_source.dataset_id = score.dataset_id
                 AND feature_source.feature_definition_id =
                     score.feature_definition_id
                 AND feature_source.source_role = 'FEATURE_DEFINITION'
                JOIN mra.candidate_component_diagnostic AS diagnostic
                  ON diagnostic.candidate_set_id = score.candidate_set_id
                 AND diagnostic.candidate_policy_component_id =
                     score.candidate_policy_component_id
                 AND diagnostic.feature_definition_id =
                     score.feature_definition_id
                WHERE score.candidate_id = %s
                  AND score.candidate_set_id = %s
                ORDER BY component.ordinal
                """,
                (UUID(str(header[1])), candidate_set_id),
            ).fetchall()
        expected_source_count = int(header[16])
        if len(dataset_source_rows) != expected_source_count:
            raise ArtifactIntegrityError(
                "Candidate dossier DatasetSource lineage does not reconcile "
                "with its immutable Dataset"
            )
        expected_component_count = int(header[17])
        if len(component_rows) != expected_component_count:
            raise ArtifactIntegrityError(
                "Candidate dossier component matrix does not reconcile with its Policy"
            )
        return CandidateDossierRecord(
            candidate_set_id=UUID(str(header[0])),
            candidate_id=UUID(str(header[1])),
            candidate_policy_id=UUID(str(header[2])),
            dataset_id=UUID(str(header[3])),
            dataset_content_sha256=str(header[4]),
            dataset_manifest_artifact_id=UUID(str(header[5])),
            dataset_manifest_content_sha256=str(header[6]),
            dataset_manifest_size_bytes=int(header[7]),
            instrument_id=UUID(str(header[8])),
            population_dataset_source_id=UUID(str(header[9])),
            population_universe_member_id=UUID(str(header[10])),
            population_eligibility_assessment_id=UUID(str(header[11])),
            dataset_sources=tuple(
                _dataset_source_lineage(row) for row in dataset_source_rows
            ),
            disposition=str(header[12]),
            reason_code=str(header[13]),
            composite_score=_decimal_or_none(header[14]),
            competition_rank=(
                int(header[15]) if header[15] is not None else None
            ),
            components=tuple(_dossier_component(row) for row in component_rows),
        )


def _funnel_record(
    row: tuple[Any, ...],
    *,
    ranking_reconciled: bool,
    component_diagnostics: tuple[CandidateFunnelComponentDiagnostic, ...],
) -> CandidateFunnelRecord:
    return CandidateFunnelRecord(
        candidate_set_id=UUID(str(row[0])),
        candidate_policy_id=UUID(str(row[1])),
        dataset_id=UUID(str(row[2])),
        dataset_population_count=int(row[3]),
        population_count=int(row[4]),
        rankable_count=int(row[5]),
        unrankable_count=int(row[6]),
        selected_count=int(row[7]),
        ranked_not_selected_count=int(row[8]),
        score_component_count=int(row[9]),
        ranking_status=str(row[10]),
        composite_distinct_count=int(row[11]),
        requested_top_k=int(row[12]),
        boundary_score=_decimal_or_none(row[13]),
        boundary_rank=int(row[14]) if row[14] is not None else None,
        strictly_above_boundary_count=int(row[15]),
        boundary_group_count=int(row[16]),
        selected_overflow_count=int(row[17]),
        boundary_has_tie=bool(row[18]),
        boundary_tie_expanded=bool(row[19]),
        actual_population_count=int(row[20]),
        actual_selected_count=int(row[21]),
        actual_ranked_not_selected_count=int(row[22]),
        actual_unrankable_count=int(row[23]),
        strict_complete_case_unrankable_count=int(row[24]),
        actual_score_component_count=int(row[25]),
        population_reconciled=bool(row[26]),
        rankable_reconciled=bool(row[27]),
        component_matrix_reconciled=bool(row[28]),
        ranking_reconciled=ranking_reconciled,
        component_diagnostics=component_diagnostics,
    )


def _funnel_component_diagnostic(
    row: tuple[Any, ...],
) -> CandidateFunnelComponentDiagnostic:
    return CandidateFunnelComponentDiagnostic(
        candidate_policy_component_id=UUID(str(row[0])),
        feature_definition_id=UUID(str(row[1])),
        observed_count=int(row[2]),
        distinct_count=int(row[3]),
        raw_available_count=int(row[4]),
        missing_count=int(row[5]),
        unknown_count=int(row[6]),
        stale_count=int(row[7]),
        conflict_count=int(row[8]),
        available_but_not_observed_count=int(row[9]),
        rank_information_status=str(row[10]),
    )


def _dossier_component(row: tuple[Any, ...]) -> CandidateDossierComponent:
    return CandidateDossierComponent(
        candidate_policy_component_id=UUID(str(row[0])),
        feature_definition_id=UUID(str(row[1])),
        feature_content_sha256=str(row[2]),
        feature_value_type=str(row[3]),
        dataset_feature_source_id=UUID(str(row[4])),
        direction=str(row[5]),
        declared_weight=Decimal(row[6]),
        raw_cell_status=str(row[7]),
        raw_decimal_value=_decimal_or_none(row[8]),
        raw_integer_value=int(row[9]) if row[9] is not None else None,
        raw_reason_code=str(row[10]),
        percentile=_decimal_or_none(row[11]),
        projected_normalized_weight=Decimal(row[12]),
        contribution=_decimal_or_none(row[13]),
        cell_source_lineage_hash=str(row[14]),
        observed_count=int(row[15]),
        distinct_count=int(row[16]),
        missing_count=int(row[17]),
        unknown_count=int(row[18]),
        stale_count=int(row[19]),
        conflict_count=int(row[20]),
        raw_available_count=int(row[21]),
        available_but_not_observed_count=int(row[22]),
        rank_information_status=str(row[23]),
    )


def _dataset_source_lineage(
    row: tuple[Any, ...],
) -> CandidateDatasetSourceLineage:
    return CandidateDatasetSourceLineage(
        dataset_source_id=UUID(str(row[0])),
        source_role=str(row[1]),
        instrument_id=_uuid_or_none(row[2]),
        universe_member_id=_uuid_or_none(row[3]),
        eligibility_assessment_id=_uuid_or_none(row[4]),
        feature_definition_id=_uuid_or_none(row[5]),
        market_bar_revision_id=_uuid_or_none(row[6]),
        market_instrument_fact_revision_id=_uuid_or_none(row[7]),
        market_trading_session_id=_uuid_or_none(row[8]),
        market_source_gap_id=_uuid_or_none(row[9]),
        market_capture_id=_uuid_or_none(row[10]),
    )


def _uuid_or_none(value: Any) -> UUID | None:
    return UUID(str(value)) if value is not None else None


def _decimal_or_none(value: Any) -> Decimal | None:
    return Decimal(value) if value is not None else None


__all__ = ["PostgresCandidateQueryProvider"]
