"""Exact read-only inputs for generic Backtest canonical actions."""

from __future__ import annotations

from uuid import UUID

from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.research_qualification.domain.backtest import (
    BacktestSpecification,
)
from market_regime_alpha.research_qualification.domain.exploratory import (
    ExploratoryRetrospectiveDatasetScope,
)
from market_regime_alpha.research_qualification.ports.backtest_actions import (
    BacktestArchiveSeal,
    BacktestDatasetExecution,
    BacktestFeatureExecutionDefinition,
    BacktestPopulationMember,
    BacktestTargetCheckpoint,
    BacktestTradingSession,
    BacktestUniverseTemplate,
)
from market_regime_alpha.runtime.errors import (
    ArtifactIntegrityError,
    RuntimeNotFoundError,
)
from market_regime_alpha.shared.identity import InstrumentId


class PostgresBacktestActionReadPort:
    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool

    def archive_seal(
        self, specification: BacktestSpecification
    ) -> BacktestArchiveSeal:
        with self._pool.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT seal.knowledge_cutoff, seal.content_sha256,
                       archive.content_sha256, archive.lane,
                       archive.evidence_class
                FROM mra.market_archive AS archive
                JOIN mra.market_archive_seal AS seal
                  ON seal.market_archive_id = archive.market_archive_id
                WHERE archive.market_archive_id = %s
                  AND seal.market_archive_seal_id = %s
                """,
                (
                    specification.market_archive.authority_id,
                    specification.market_archive_seal.authority_id,
                ),
            ).fetchone()
        if row is None:
            raise RuntimeNotFoundError("Backtest Archive seal does not exist")
        if (
            str(row[1]) != str(specification.market_archive_seal.content_sha256)
            or str(row[2]) != str(specification.market_archive.content_sha256)
            or row[3] != "RETROSPECTIVE_BACKFILL"
            or row[4] != "EXPLORATORY_RETROSPECTIVE"
        ):
            raise ArtifactIntegrityError("Backtest Archive seal differs from specification")
        return BacktestArchiveSeal(row[0])

    def universe_template(
        self, specification: BacktestSpecification
    ) -> BacktestUniverseTemplate:
        with self._pool.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT revision.universe_id,
                       revision.market_provider_product_id,
                       revision.classification_scheme,
                       revision.classification_code,
                       revision.scope_content_sha256
                FROM mra.universe_revision AS revision
                WHERE revision.universe_revision_id = %s
                """,
                (specification.universe_revision.authority_id,),
            ).fetchone()
        if row is None:
            raise RuntimeNotFoundError("Backtest UniverseRevision does not exist")
        if str(row[4]) != str(specification.universe_revision.content_sha256):
            raise ArtifactIntegrityError(
                "Backtest UniverseRevision scope differs from specification"
            )
        return BacktestUniverseTemplate(row[0], row[1], row[2], row[3])

    def trading_session(
        self,
        specification: BacktestSpecification,
        trading_session_id: UUID,
    ) -> BacktestTradingSession:
        with self._pool.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT session_id, exchange, session_date, timezone_name,
                       open_at, close_at
                FROM mra.trading_session
                WHERE session_id = %s
                """,
                (trading_session_id,),
            ).fetchone()
        if row is None:
            raise RuntimeNotFoundError("Backtest TradingSession does not exist")
        if row[1] != specification.exchange_code:
            raise ArtifactIntegrityError("Backtest TradingSession exchange differs")
        return BacktestTradingSession(*row)

    def target_checkpoints(
        self, specification: BacktestSpecification
    ) -> tuple[BacktestTargetCheckpoint, ...]:
        with self._pool.connection(read_only=True) as connection:
            target = connection.execute(
                """
                SELECT version, content_sha256
                FROM mra.target_definition
                WHERE target_definition_id = %s
                """,
                (specification.target.authority_id,),
            ).fetchone()
            rows = connection.execute(
                """
                SELECT target_checkpoint_id, checkpoint_role, session_offset,
                       local_time, timezone_name
                FROM mra.target_checkpoint
                WHERE target_definition_id = %s
                ORDER BY ordinal
                """,
                (specification.target.authority_id,),
            ).fetchall()
        if target is None or (
            int(target[0]) != specification.target.version
            or str(target[1]) != str(specification.target.content_sha256)
        ):
            raise ArtifactIntegrityError("Backtest Target differs from specification")
        return tuple(BacktestTargetCheckpoint(*row) for row in rows)

    def feature_definitions(
        self, specification: BacktestSpecification
    ) -> tuple[BacktestFeatureExecutionDefinition, ...]:
        expected = {
            item.authority_id: str(item.content_sha256)
            for item in specification.feature_definitions
        }
        with self._pool.connection(read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT feature_definition_id, content_sha256, feature_code,
                       algorithm_code, algorithm_version, algorithm_sha256
                FROM mra.feature_definition
                WHERE feature_definition_id = ANY(%s)
                ORDER BY feature_definition_id
                """,
                (list(expected),),
            ).fetchall()
        actual = {row[0]: str(row[1]) for row in rows}
        if actual != expected:
            raise ArtifactIntegrityError(
                "Backtest FeatureDefinition roster differs from specification"
            )
        return tuple(BacktestFeatureExecutionDefinition(*row) for row in rows)

    def retrospective_universe_id(
        self,
        *,
        specification: BacktestSpecification,
        decision_time,
        scope_content_sha256: str,
    ) -> UUID:
        template = self.universe_template(specification)
        seal = self.archive_seal(specification)
        with self._pool.connection(read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT revision.universe_revision_id
                FROM mra.universe_revision AS revision
                JOIN mra.exploratory_retrospective_universe_revision AS scope
                  USING (universe_revision_id)
                WHERE revision.universe_id = %s
                  AND revision.decision_time = %s
                  AND revision.scope_content_sha256 = %s
                  AND scope.market_archive_id = %s
                  AND scope.market_archive_seal_id = %s
                  AND scope.knowledge_cutoff = %s
                  AND scope.simulated_event_cutoff = %s
                """,
                (
                    template.universe_id,
                    decision_time,
                    scope_content_sha256,
                    specification.market_archive.authority_id,
                    specification.market_archive_seal.authority_id,
                    seal.knowledge_cutoff,
                    decision_time,
                ),
            ).fetchall()
        if len(rows) != 1:
            raise RuntimeNotFoundError(
                "Backtest retrospective UniverseRevision is absent or ambiguous"
            )
        return UUID(str(rows[0][0]))

    def eligible_population(
        self,
        *,
        universe_revision_id: UUID,
        eligibility_policy_id: UUID,
    ) -> tuple[BacktestPopulationMember, ...]:
        with self._pool.connection(read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT assessment.instrument_id, member.universe_member_id,
                       assessment.eligibility_assessment_id
                FROM mra.universe_member AS member
                JOIN mra.eligibility_assessment AS assessment
                  ON assessment.universe_member_id = member.universe_member_id
                 AND assessment.universe_revision_id = member.universe_revision_id
                 AND assessment.instrument_id = member.instrument_id
                WHERE member.universe_revision_id = %s
                  AND assessment.eligibility_policy_id = %s
                  AND member.membership_status = 'INCLUDED'
                  AND assessment.result = 'ELIGIBLE'
                ORDER BY assessment.instrument_id
                """,
                (universe_revision_id, eligibility_policy_id),
            ).fetchall()
        return tuple(
            BacktestPopulationMember(InstrumentId.parse(row[0]), row[1], row[2])
            for row in rows
        )

    def dataset_execution(
        self,
        *,
        exploratory_backtest_run_id: UUID,
        arm_id: UUID,
        fold_session_id: UUID,
    ) -> BacktestDatasetExecution:
        with self._pool.connection(read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT dataset.dataset_id, dataset.universe_revision_id,
                       dataset.eligibility_policy_id,
                       retrospective.market_archive_id,
                       retrospective.market_archive_seal_id,
                       retrospective.knowledge_cutoff,
                       retrospective.simulated_event_cutoff
                FROM mra.exploratory_backtest_dataset AS backtest
                JOIN mra.dataset AS dataset USING (dataset_id)
                JOIN mra.exploratory_retrospective_dataset AS retrospective
                  USING (dataset_id)
                WHERE backtest.exploratory_backtest_run_id = %s
                  AND backtest.exploratory_backtest_arm_id = %s
                  AND backtest.exploratory_backtest_fold_session_id = %s
                """,
                (exploratory_backtest_run_id, arm_id, fold_session_id),
            ).fetchall()
        if len(rows) != 1:
            raise RuntimeNotFoundError(
                "Backtest Dataset execution is absent or ambiguous"
            )
        row = rows[0]
        return BacktestDatasetExecution(
            dataset_id=row[0],
            universe_revision_id=row[1],
            eligibility_policy_id=row[2],
            retrospective_scope=ExploratoryRetrospectiveDatasetScope(
                row[3], row[4], row[5], row[6]
            ),
        )

    def candidate_set_id(
        self,
        *,
        dataset_id: UUID,
        candidate_policy_id: UUID,
    ) -> UUID:
        with self._pool.connection(read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT candidate_set_id FROM mra.candidate_set
                WHERE dataset_id = %s AND candidate_policy_id = %s
                """,
                (dataset_id, candidate_policy_id),
            ).fetchall()
        if len(rows) != 1:
            raise RuntimeNotFoundError("Backtest CandidateSet is absent or ambiguous")
        return UUID(str(rows[0][0]))

    def decision_run_id(self, *, dataset_id: UUID) -> UUID:
        with self._pool.connection(read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT decision_run_id
                FROM mra.exploratory_retrospective_decision_run
                WHERE dataset_id = %s
                """,
                (dataset_id,),
            ).fetchall()
        if len(rows) != 1:
            raise RuntimeNotFoundError("Backtest DecisionRun is absent or ambiguous")
        return UUID(str(rows[0][0]))

    def decision_commitment_ids(
        self,
        *,
        exploratory_backtest_run_id: UUID,
        arm_id: UUID,
        fold_id: UUID,
        fold_session_id: UUID,
        target_definition_id: UUID,
    ) -> tuple[UUID, ...]:
        with self._pool.connection(read_only=True) as connection:
            decision_rows = connection.execute(
                """
                SELECT decision_run_id
                FROM mra.exploratory_retrospective_decision_run
                WHERE exploratory_backtest_run_id = %s
                  AND exploratory_backtest_arm_id = %s
                  AND exploratory_backtest_fold_id = %s
                  AND exploratory_backtest_fold_session_id = %s
                """,
                (
                    exploratory_backtest_run_id,
                    arm_id,
                    fold_id,
                    fold_session_id,
                ),
            ).fetchall()
            if len(decision_rows) != 1:
                raise RuntimeNotFoundError(
                    "Backtest DecisionRun is absent or ambiguous"
                )
            rows = connection.execute(
                """
                SELECT commitment.commitment_id
                FROM mra.decision_target_commitment AS commitment
                WHERE commitment.decision_run_id = %s
                  AND commitment.target_definition_id = %s
                ORDER BY commitment.instrument_id, commitment.commitment_id
                """,
                (decision_rows[0][0], target_definition_id),
            ).fetchall()
        return tuple(UUID(str(row[0])) for row in rows)

    def model_version_id(
        self,
        *,
        exploratory_backtest_run_id: UUID,
        model_training_requirement_id: UUID,
    ) -> UUID:
        with self._pool.connection(read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT model_version_id FROM mra.backtest_model_lineage
                WHERE exploratory_backtest_run_id = %s
                  AND model_training_requirement_id = %s
                """,
                (
                    exploratory_backtest_run_id,
                    model_training_requirement_id,
                ),
            ).fetchall()
        if len(rows) != 1:
            raise RuntimeNotFoundError(
                "Backtest ModelVersion lineage is absent or ambiguous"
            )
        return UUID(str(rows[0][0]))


__all__ = ["PostgresBacktestActionReadPort"]
