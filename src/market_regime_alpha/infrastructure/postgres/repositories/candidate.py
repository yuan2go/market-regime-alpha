"""PostgreSQL Authority adapter for Selection-owned Candidate aggregates."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

import psycopg

from market_regime_alpha.runtime.errors import (
    ArtifactIntegrityError,
    RuntimeNotFoundError,
)
from market_regime_alpha.selection.domain import (
    CandidateArtifactBinding,
    CandidateCellStatus,
    CandidateComponentDiagnostic,
    CandidateDisposition,
    CandidateFeatureValueType,
    CandidatePolicy,
    CandidatePolicyComponent,
    CandidateRankingPlan,
    CandidateRankingStatus,
    CandidateRecord,
    CandidateScoreComponentRecord,
    CandidateSetResult,
    DesirabilityDirection,
)
from market_regime_alpha.selection.ports.candidate_repository import (
    CandidatePersistenceReconciliation,
    CandidateSetBinding,
)
from market_regime_alpha.shared.identity import ContentHash
from market_regime_alpha.shared.time import DecisionTime


class PostgresCandidateRepository:
    """Persist Candidate policy and ranking Authority in the caller transaction."""

    def __init__(self, connection: psycopg.Connection[Any]) -> None:
        self._connection = connection

    def insert_policy(self, policy: CandidatePolicy) -> None:
        self._connection.execute(
            """
            INSERT INTO mra.candidate_policy (
                candidate_policy_id, policy_code, version, content_sha256,
                normalization_method, rank_method, missing_policy,
                selection_method, tie_policy, score_semantics,
                decimal_projection_method, decimal_projection_version,
                requested_top_k, component_count,
                code_artifact_id, code_content_sha256, code_size_bytes,
                config_artifact_id, config_content_sha256, config_size_bytes
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            (
                policy.candidate_policy_id,
                policy.policy_code,
                policy.version,
                str(policy.content_sha256),
                policy.normalization_method,
                policy.rank_method,
                policy.missing_policy,
                policy.selection_method,
                policy.tie_policy,
                policy.score_semantics,
                policy.decimal_projection_method,
                policy.decimal_projection_version,
                policy.requested_top_k,
                policy.component_count,
                policy.code_artifact.artifact_id,
                str(policy.code_artifact.content_sha256),
                policy.code_artifact.size_bytes,
                policy.config_artifact.artifact_id,
                str(policy.config_artifact.content_sha256),
                policy.config_artifact.size_bytes,
            ),
        )
        with self._connection.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO mra.candidate_policy_component (
                    candidate_policy_component_id, candidate_policy_id,
                    component_code, ordinal, feature_definition_id,
                    feature_content_sha256, feature_value_type, direction,
                    declared_weight
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    (
                        component.candidate_policy_component_id,
                        component.candidate_policy_id,
                        component.component_code,
                        component.ordinal,
                        component.feature_definition_id,
                        str(component.feature_content_sha256),
                        component.feature_value_type.value,
                        component.direction.value,
                        component.declared_weight,
                    )
                    for component in policy.components
                ),
            )

    def policy(self, candidate_policy_id: UUID, *, lock: bool) -> CandidatePolicy:
        suffix = " FOR SHARE" if lock else ""
        row = self._connection.execute(
            """
            SELECT candidate_policy_id, policy_code, version, content_sha256,
                   normalization_method, rank_method, missing_policy,
                   selection_method, tie_policy, score_semantics,
                   decimal_projection_method, decimal_projection_version,
                   requested_top_k, component_count,
                   code_artifact_id, code_content_sha256, code_size_bytes,
                   config_artifact_id, config_content_sha256, config_size_bytes
            FROM mra.candidate_policy
            WHERE candidate_policy_id = %s
            """
            + suffix,
            (candidate_policy_id,),
        ).fetchone()
        if row is None:
            raise RuntimeNotFoundError(
                f"CandidatePolicy {candidate_policy_id} does not exist"
            )
        component_rows = self._connection.execute(
            """
            SELECT candidate_policy_component_id, candidate_policy_id,
                   component_code, ordinal, feature_definition_id,
                   feature_content_sha256, feature_value_type, direction,
                   declared_weight
            FROM mra.candidate_policy_component
            WHERE candidate_policy_id = %s
            ORDER BY ordinal
            """
            + suffix,
            (candidate_policy_id,),
        ).fetchall()
        if len(component_rows) != int(row[13]):
            raise ArtifactIntegrityError(
                "CandidatePolicy component count does not reconcile"
            )
        policy = CandidatePolicy(
            candidate_policy_id=UUID(str(row[0])),
            policy_code=str(row[1]),
            version=int(row[2]),
            code_artifact=CandidateArtifactBinding(
                artifact_id=UUID(str(row[14])),
                content_sha256=str(row[15]),
                size_bytes=int(row[16]),
            ),
            config_artifact=CandidateArtifactBinding(
                artifact_id=UUID(str(row[17])),
                content_sha256=str(row[18]),
                size_bytes=int(row[19]),
            ),
            requested_top_k=int(row[12]),
            components=tuple(_policy_component(item) for item in component_rows),
            normalization_method=str(row[4]),
            rank_method=str(row[5]),
            missing_policy=str(row[6]),
            selection_method=str(row[7]),
            tie_policy=str(row[8]),
            score_semantics=str(row[9]),
            decimal_projection_method=str(row[10]),
            decimal_projection_version=int(row[11]),
        )
        if str(policy.content_sha256) != str(row[3]):
            raise ArtifactIntegrityError(
                "CandidatePolicy content hash does not reconcile"
            )
        return policy

    def lock_candidate_set_identity(self, candidate_set_id: UUID) -> None:
        """Serialize one build identity before dependency row locks are taken."""

        self._connection.execute(
            "SELECT pg_advisory_xact_lock(%s)",
            (_candidate_set_lock_key(candidate_set_id),),
        )

    def insert_candidate_set(self, plan: CandidateRankingPlan) -> None:
        candidate_set = plan.candidate_set
        # One deterministic identity can hit several unique indexes. Serialize
        # that identity before speculative insertion so concurrent exact builds
        # converge through the ordinary unique-conflict replay contract instead
        # of forming a PostgreSQL speculative-insert deadlock.
        self.lock_candidate_set_identity(candidate_set.candidate_set_id)
        self._connection.execute(
            """
            INSERT INTO mra.candidate_set (
                candidate_set_id, candidate_policy_id,
                candidate_policy_content_sha256, dataset_id,
                dataset_content_sha256, universe_revision_id,
                eligibility_policy_id, decision_time, requested_top_k,
                component_count, decimal_projection_precision,
                population_count, rankable_count, unrankable_count,
                selected_count, ranked_not_selected_count,
                score_component_count, available_component_count,
                constant_component_count, not_estimable_component_count,
                ranking_status, composite_distinct_count, boundary_score,
                boundary_rank, strictly_above_boundary_count,
                boundary_group_count, selected_overflow_count,
                boundary_has_tie, boundary_tie_expanded, dependency_sha256,
                content_sha256
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            (
                candidate_set.candidate_set_id,
                candidate_set.candidate_policy_id,
                str(candidate_set.candidate_policy_content_sha256),
                candidate_set.dataset_id,
                str(candidate_set.dataset_content_sha256),
                candidate_set.universe_revision_id,
                candidate_set.eligibility_policy_id,
                candidate_set.decision_time.value,
                candidate_set.requested_top_k,
                candidate_set.component_count,
                candidate_set.decimal_projection_precision,
                candidate_set.population_count,
                candidate_set.rankable_count,
                candidate_set.unrankable_count,
                candidate_set.selected_count,
                candidate_set.ranked_not_selected_count,
                candidate_set.score_component_count,
                candidate_set.available_component_count,
                candidate_set.constant_component_count,
                candidate_set.not_estimable_component_count,
                candidate_set.ranking_status.value,
                candidate_set.composite_distinct_count,
                candidate_set.boundary_score,
                candidate_set.boundary_rank,
                candidate_set.strictly_above_boundary_count,
                candidate_set.boundary_group_count,
                candidate_set.selected_overflow_count,
                candidate_set.boundary_has_tie,
                candidate_set.boundary_tie_expanded,
                str(candidate_set.dependency_sha256),
                str(candidate_set.content_sha256),
            ),
        )
        with self._connection.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO mra.candidate (
                    candidate_id, candidate_set_id, candidate_policy_id,
                    dataset_id, dataset_population_source_id,
                    dataset_source_role, instrument_id, disposition,
                    composite_score, competition_rank, reason_code
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    (
                        candidate.candidate_id,
                        candidate.candidate_set_id,
                        candidate.candidate_policy_id,
                        candidate.dataset_id,
                        candidate.dataset_population_source_id,
                        candidate.dataset_source_role,
                        candidate.instrument_id,
                        candidate.disposition.value,
                        candidate.composite_score,
                        candidate.competition_rank,
                        candidate.reason_code,
                    )
                    for candidate in plan.candidates
                ),
            )
            cursor.executemany(
                """
                INSERT INTO mra.candidate_score_component (
                    candidate_score_component_id, candidate_id,
                    candidate_set_id, candidate_policy_id, dataset_id,
                    instrument_id, candidate_disposition,
                    candidate_policy_component_id, feature_definition_id,
                    feature_content_sha256, feature_value_type, raw_status,
                    raw_decimal_value, raw_integer_value, raw_reason_code,
                    cell_source_lineage_hash, normalized_weight, percentile,
                    contribution
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    (
                        score.candidate_score_component_id,
                        score.candidate_id,
                        score.candidate_set_id,
                        score.candidate_policy_id,
                        score.dataset_id,
                        score.instrument_id,
                        score.candidate_disposition.value,
                        score.candidate_policy_component_id,
                        score.feature_definition_id,
                        str(score.feature_content_sha256),
                        score.feature_value_type.value,
                        score.raw_status.value,
                        score.raw_decimal_value,
                        score.raw_integer_value,
                        score.raw_reason_code,
                        str(score.cell_source_lineage_hash),
                        score.normalized_weight,
                        score.percentile,
                        score.contribution,
                    )
                    for score in plan.score_components
                ),
            )

    def candidate_set_binding(
        self,
        *,
        candidate_policy_id: UUID,
        dataset_id: UUID,
        lock: bool,
    ) -> CandidateSetBinding | None:
        """Load only the immutable CandidateSet identity/hash binding."""

        suffix = " FOR SHARE" if lock else ""
        row = self._connection.execute(
            """
            SELECT candidate_set_id, candidate_policy_id,
                   candidate_policy_content_sha256, dataset_id,
                   dataset_content_sha256, dependency_sha256,
                   content_sha256
            FROM mra.candidate_set
            WHERE candidate_policy_id = %s AND dataset_id = %s
            """
            + suffix,
            (candidate_policy_id, dataset_id),
        ).fetchone()
        if row is None:
            return None
        return CandidateSetBinding(
            candidate_set_id=UUID(str(row[0])),
            candidate_policy_id=UUID(str(row[1])),
            candidate_policy_content_sha256=str(row[2]),
            dataset_id=UUID(str(row[3])),
            dataset_content_sha256=str(row[4]),
            dependency_sha256=str(row[5]),
            result_sha256=str(row[6]),
        )

    def persisted_candidate_set(
        self,
        *,
        candidate_policy_id: UUID,
        dataset_id: UUID,
        lock: bool,
    ) -> CandidateRankingPlan | None:
        """Load immutable Candidate Authority facts without ranking computation."""

        suffix = " FOR SHARE" if lock else ""
        candidate_set_row = self._connection.execute(
            """
            SELECT candidate_set_id, candidate_policy_id,
                   candidate_policy_content_sha256, dataset_id,
                   dataset_content_sha256, universe_revision_id,
                   eligibility_policy_id, decision_time, requested_top_k,
                   component_count, decimal_projection_precision,
                   population_count, rankable_count, unrankable_count,
                   selected_count, ranked_not_selected_count,
                   score_component_count, available_component_count,
                   constant_component_count, not_estimable_component_count,
                   ranking_status, composite_distinct_count, boundary_score,
                   boundary_rank, strictly_above_boundary_count,
                   boundary_group_count, selected_overflow_count,
                   boundary_has_tie, boundary_tie_expanded,
                   dependency_sha256, content_sha256
            FROM mra.candidate_set
            WHERE candidate_policy_id = %s AND dataset_id = %s
            """
            + suffix,
            (candidate_policy_id, dataset_id),
        ).fetchone()
        if candidate_set_row is None:
            return None
        persisted_set = _candidate_set_result(candidate_set_row)
        persisted_candidates = tuple(
            _candidate_record(row)
            for row in self._connection.execute(
                """
                SELECT candidate_id, candidate_set_id, candidate_policy_id,
                       dataset_id, instrument_id,
                       dataset_population_source_id, dataset_source_role,
                       disposition, composite_score, competition_rank,
                       reason_code
                FROM mra.candidate
                WHERE candidate_set_id = %s
                ORDER BY instrument_id
                """
                + suffix,
                (persisted_set.candidate_set_id,),
            ).fetchall()
        )
        persisted_scores = tuple(
            _candidate_score_component(row)
            for row in self._connection.execute(
                """
                SELECT score.candidate_score_component_id,
                       score.candidate_id, score.candidate_set_id,
                       score.candidate_policy_id,
                       score.candidate_policy_component_id,
                       score.feature_definition_id,
                       score.feature_content_sha256,
                       score.feature_value_type, score.dataset_id,
                       score.instrument_id, score.raw_status,
                       score.raw_decimal_value, score.raw_integer_value,
                       score.raw_reason_code, score.cell_source_lineage_hash,
                       score.normalized_weight, score.percentile,
                       score.contribution, score.candidate_disposition
                FROM mra.candidate_score_component AS score
                JOIN mra.candidate AS candidate
                  ON candidate.candidate_id = score.candidate_id
                JOIN mra.candidate_policy_component AS component
                  ON component.candidate_policy_component_id =
                     score.candidate_policy_component_id
                WHERE score.candidate_set_id = %s
                ORDER BY candidate.instrument_id, component.ordinal
                """
                + suffix,
                (persisted_set.candidate_set_id,),
            ).fetchall()
        )
        persisted_diagnostics = tuple(
            _candidate_component_diagnostic(row)
            for row in self._connection.execute(
                """
                SELECT diagnostic.candidate_policy_component_id,
                       diagnostic.feature_definition_id,
                       diagnostic.observed_count,
                       diagnostic.distinct_count,
                       diagnostic.raw_available_count,
                       diagnostic.available_but_not_observed_count,
                       diagnostic.missing_count, diagnostic.unknown_count,
                       diagnostic.stale_count, diagnostic.conflict_count,
                       diagnostic.rank_information_status
                FROM mra.candidate_component_diagnostic AS diagnostic
                JOIN mra.candidate_policy_component AS component
                  ON component.candidate_policy_component_id =
                     diagnostic.candidate_policy_component_id
                WHERE diagnostic.candidate_set_id = %s
                ORDER BY component.ordinal
                """,
                (persisted_set.candidate_set_id,),
            ).fetchall()
        )
        return CandidateRankingPlan(
            candidate_set=persisted_set,
            candidates=persisted_candidates,
            score_components=persisted_scores,
            component_diagnostics=persisted_diagnostics,
        )

    def reconciliation(
        self,
        candidate_set_id: UUID,
    ) -> CandidatePersistenceReconciliation:
        row = self._connection.execute(
            """
            SELECT actual_population_count, actual_selected_count,
                   actual_ranked_not_selected_count,
                   actual_unrankable_count, actual_score_component_count,
                   population_reconciled, rankable_reconciled,
                   score_matrix_reconciled,
                   NOT EXISTS (
                       SELECT 1
                       FROM mra.candidate AS ranked
                       WHERE ranked.candidate_set_id = funnel.candidate_set_id
                         AND ranked.competition_rank IS NOT NULL
                         AND ranked.competition_rank <> 1 + (
                             SELECT count(*)
                             FROM mra.candidate AS better
                             WHERE better.candidate_set_id = ranked.candidate_set_id
                               AND better.composite_score > ranked.composite_score
                         )
                   )
                   AND NOT EXISTS (
                       SELECT 1
                       FROM mra.candidate AS selected
                       WHERE selected.candidate_set_id = funnel.candidate_set_id
                         AND selected.disposition = 'SELECTED'
                         AND selected.composite_score < funnel.boundary_score
                   )
                   AND NOT EXISTS (
                       SELECT 1
                       FROM mra.candidate AS rejected
                       WHERE rejected.candidate_set_id = funnel.candidate_set_id
                         AND rejected.disposition = 'RANKED_NOT_SELECTED'
                         AND rejected.composite_score >= funnel.boundary_score
                   )
                   AND NOT EXISTS (
                       SELECT 1
                       FROM mra.candidate AS unrankable
                       WHERE unrankable.candidate_set_id = funnel.candidate_set_id
                         AND unrankable.disposition = 'UNRANKABLE'
                         AND NOT EXISTS (
                             SELECT 1
                             FROM mra.candidate_score_component AS score
                             WHERE score.candidate_id = unrankable.candidate_id
                               AND score.raw_status <> 'AVAILABLE'
                         )
                   )
                   AND NOT EXISTS (
                       SELECT 1
                       FROM mra.candidate AS rankable
                       WHERE rankable.candidate_set_id =
                           funnel.candidate_set_id
                         AND rankable.disposition <> 'UNRANKABLE'
                         AND EXISTS (
                             SELECT 1
                             FROM mra.candidate_score_component AS score
                             WHERE score.candidate_id = rankable.candidate_id
                               AND score.raw_status <> 'AVAILABLE'
                         )
                   )
                   AND authority.composite_distinct_count = (
                       SELECT count(DISTINCT candidate.composite_score)
                       FROM mra.candidate AS candidate
                       WHERE candidate.candidate_set_id =
                           funnel.candidate_set_id
                         AND candidate.disposition <> 'UNRANKABLE'
                   )
                   AND (
                       (
                           authority.rankable_count = 0
                           AND authority.boundary_score IS NULL
                           AND authority.boundary_rank IS NULL
                           AND authority.strictly_above_boundary_count = 0
                           AND authority.boundary_group_count = 0
                       )
                       OR
                       (
                           authority.rankable_count > 0
                           AND authority.boundary_score IS NOT DISTINCT FROM (
                               SELECT min(candidate.composite_score)
                               FROM mra.candidate AS candidate
                               WHERE candidate.candidate_set_id =
                                   funnel.candidate_set_id
                                 AND candidate.disposition = 'SELECTED'
                           )
                           AND authority.boundary_rank = 1 + (
                               SELECT count(*)
                               FROM mra.candidate AS candidate
                               WHERE candidate.candidate_set_id =
                                   funnel.candidate_set_id
                                 AND candidate.disposition <> 'UNRANKABLE'
                                 AND candidate.composite_score >
                                     authority.boundary_score
                           )
                           AND authority.strictly_above_boundary_count = (
                               SELECT count(*)
                               FROM mra.candidate AS candidate
                               WHERE candidate.candidate_set_id =
                                   funnel.candidate_set_id
                                 AND candidate.disposition <> 'UNRANKABLE'
                                 AND candidate.composite_score >
                                     authority.boundary_score
                           )
                           AND authority.boundary_group_count = (
                               SELECT count(*)
                               FROM mra.candidate AS candidate
                               WHERE candidate.candidate_set_id =
                                   funnel.candidate_set_id
                                 AND candidate.disposition <> 'UNRANKABLE'
                                 AND candidate.composite_score =
                                     authority.boundary_score
                           )
                       )
                   )
                   AND (
                       SELECT
                           count(*) = authority.component_count
                           AND count(*) FILTER (
                               WHERE diagnostic.rank_information_status =
                                   'AVAILABLE'
                           ) = authority.available_component_count
                           AND count(*) FILTER (
                               WHERE diagnostic.rank_information_status =
                                   'CONSTANT'
                           ) = authority.constant_component_count
                           AND count(*) FILTER (
                               WHERE diagnostic.rank_information_status =
                                   'NOT_ESTIMABLE'
                           ) = authority.not_estimable_component_count
                           AND COALESCE(bool_and(
                               diagnostic.observed_count =
                                   authority.rankable_count
                           ), true)
                           AND COALESCE(bool_and(
                               diagnostic.raw_available_count
                               + diagnostic.missing_count
                               + diagnostic.unknown_count
                               + diagnostic.stale_count
                               + diagnostic.conflict_count =
                                   authority.population_count
                           ), true)
                       FROM mra.candidate_component_diagnostic AS diagnostic
                       WHERE diagnostic.candidate_set_id =
                           funnel.candidate_set_id
                   ) AS ranking_reconciled
            FROM mra.candidate_funnel AS funnel
            JOIN mra.candidate_set AS authority
              ON authority.candidate_set_id = funnel.candidate_set_id
            WHERE funnel.candidate_set_id = %s
            """,
            (candidate_set_id,),
        ).fetchone()
        if row is None:
            raise RuntimeNotFoundError(
                f"CandidateSet {candidate_set_id} does not exist"
            )
        return CandidatePersistenceReconciliation(
            population_count=int(row[0]),
            selected_count=int(row[1]),
            ranked_not_selected_count=int(row[2]),
            unrankable_count=int(row[3]),
            score_component_count=int(row[4]),
            population_reconciled=bool(row[5]),
            rankable_reconciled=bool(row[6]),
            component_matrix_reconciled=bool(row[7]),
            ranking_reconciled=bool(row[8]),
        )


def _candidate_set_result(row: tuple[Any, ...]) -> CandidateSetResult:
    return CandidateSetResult(
        candidate_set_id=UUID(str(row[0])),
        candidate_policy_id=UUID(str(row[1])),
        candidate_policy_content_sha256=ContentHash(str(row[2])),
        dataset_id=UUID(str(row[3])),
        dataset_content_sha256=ContentHash(str(row[4])),
        universe_revision_id=UUID(str(row[5])),
        eligibility_policy_id=UUID(str(row[6])),
        decision_time=DecisionTime(row[7]),
        requested_top_k=int(row[8]),
        component_count=int(row[9]),
        decimal_projection_precision=int(row[10]),
        population_count=int(row[11]),
        rankable_count=int(row[12]),
        unrankable_count=int(row[13]),
        selected_count=int(row[14]),
        ranked_not_selected_count=int(row[15]),
        score_component_count=int(row[16]),
        available_component_count=int(row[17]),
        constant_component_count=int(row[18]),
        not_estimable_component_count=int(row[19]),
        ranking_status=CandidateRankingStatus(str(row[20])),
        composite_distinct_count=int(row[21]),
        boundary_score=Decimal(row[22]) if row[22] is not None else None,
        boundary_rank=int(row[23]) if row[23] is not None else None,
        strictly_above_boundary_count=int(row[24]),
        boundary_group_count=int(row[25]),
        selected_overflow_count=int(row[26]),
        boundary_has_tie=bool(row[27]),
        boundary_tie_expanded=bool(row[28]),
        dependency_sha256=ContentHash(str(row[29])),
        content_sha256=ContentHash(str(row[30])),
    )


def _candidate_set_lock_key(candidate_set_id: UUID) -> int:
    key = candidate_set_id.int >> 64
    return key if key < 2**63 else key - 2**64


def _candidate_record(row: tuple[Any, ...]) -> CandidateRecord:
    return CandidateRecord(
        candidate_id=UUID(str(row[0])),
        candidate_set_id=UUID(str(row[1])),
        candidate_policy_id=UUID(str(row[2])),
        dataset_id=UUID(str(row[3])),
        instrument_id=UUID(str(row[4])),
        dataset_population_source_id=UUID(str(row[5])),
        dataset_source_role=str(row[6]),
        disposition=CandidateDisposition(str(row[7])),
        composite_score=Decimal(row[8]) if row[8] is not None else None,
        competition_rank=int(row[9]) if row[9] is not None else None,
        reason_code=str(row[10]),
    )


def _candidate_score_component(
    row: tuple[Any, ...],
) -> CandidateScoreComponentRecord:
    raw_integer = None
    if row[12] is not None:
        raw_integer = int(row[12])
    return CandidateScoreComponentRecord(
        candidate_score_component_id=UUID(str(row[0])),
        candidate_id=UUID(str(row[1])),
        candidate_set_id=UUID(str(row[2])),
        candidate_policy_id=UUID(str(row[3])),
        candidate_policy_component_id=UUID(str(row[4])),
        feature_definition_id=UUID(str(row[5])),
        feature_content_sha256=ContentHash(str(row[6])),
        feature_value_type=CandidateFeatureValueType(str(row[7])),
        dataset_id=UUID(str(row[8])),
        instrument_id=UUID(str(row[9])),
        raw_status=CandidateCellStatus(str(row[10])),
        raw_decimal_value=(
            Decimal(row[11]) if row[11] is not None else None
        ),
        raw_integer_value=raw_integer,
        raw_reason_code=str(row[13]),
        cell_source_lineage_hash=ContentHash(str(row[14])),
        normalized_weight=Decimal(row[15]),
        percentile=Decimal(row[16]) if row[16] is not None else None,
        contribution=Decimal(row[17]) if row[17] is not None else None,
        candidate_disposition=CandidateDisposition(str(row[18])),
    )


def _candidate_component_diagnostic(
    row: tuple[Any, ...],
) -> CandidateComponentDiagnostic:
    return CandidateComponentDiagnostic(
        candidate_policy_component_id=UUID(str(row[0])),
        feature_definition_id=UUID(str(row[1])),
        observed_count=int(row[2]),
        distinct_count=int(row[3]),
        raw_available_count=int(row[4]),
        available_but_not_observed_count=int(row[5]),
        missing_count=int(row[6]),
        unknown_count=int(row[7]),
        stale_count=int(row[8]),
        conflict_count=int(row[9]),
        rank_information_status=CandidateRankingStatus(str(row[10])),
    )


def _policy_component(row: tuple[Any, ...]) -> CandidatePolicyComponent:
    return CandidatePolicyComponent(
        candidate_policy_component_id=UUID(str(row[0])),
        candidate_policy_id=UUID(str(row[1])),
        component_code=str(row[2]),
        ordinal=int(row[3]),
        feature_definition_id=UUID(str(row[4])),
        feature_content_sha256=str(row[5]),
        feature_value_type=CandidateFeatureValueType(str(row[6])),
        direction=DesirabilityDirection(str(row[7])),
        declared_weight=Decimal(row[8]),
    )


__all__ = ["PostgresCandidateRepository"]
