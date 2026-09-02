"""Exact read-only completion probe for WP-17P exploratory campaigns."""

from __future__ import annotations

from uuid import UUID, uuid5

from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.research_qualification.ports.exploratory_campaign import (
    CompletedExploratoryCampaign,
    ExploratoryCampaignReadPort,
)
from market_regime_alpha.runtime.errors import ArtifactIntegrityError
from market_regime_alpha.shared.identity import ContentHash


class PostgresExploratoryCampaignReadPort(ExploratoryCampaignReadPort):
    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool

    def completed(
        self,
        exploratory_backtest_run_id: UUID,
        *,
        expected_definition_sha256: str,
    ) -> CompletedExploratoryCampaign | None:
        ContentHash(expected_definition_sha256)
        fit_experiment_id = uuid5(
            exploratory_backtest_run_id,
            "experiment:" + str(_fold_id(self._pool, exploratory_backtest_run_id, "FIT")),
        )
        validation_experiment_id = uuid5(
            exploratory_backtest_run_id,
            "experiment:"
            + str(_fold_id(self._pool, exploratory_backtest_run_id, "VALIDATION")),
        )
        with self._pool.connection(read_only=True) as connection:
            root = connection.execute(
                """
                SELECT definition_sha256
                FROM mra.exploratory_backtest_run
                WHERE exploratory_backtest_run_id = %s
                """,
                (exploratory_backtest_run_id,),
            ).fetchone()
            if root is None:
                return None
            if str(root[0]) != expected_definition_sha256:
                raise ArtifactIntegrityError(
                    "exploratory campaign definition differs from replay request"
                )
            datasets = connection.execute(
                """
                SELECT dataset.dataset_id, arm.arm_kind, fold.purpose,
                       member.session_role, decision.decision_run_id
                FROM mra.exploratory_backtest_dataset AS dataset
                JOIN mra.exploratory_backtest_arm AS arm
                  ON arm.exploratory_backtest_arm_id =
                     dataset.exploratory_backtest_arm_id
                 AND arm.exploratory_backtest_run_id =
                     dataset.exploratory_backtest_run_id
                JOIN mra.exploratory_backtest_fold AS fold
                  ON fold.exploratory_backtest_fold_id =
                     dataset.exploratory_backtest_fold_id
                 AND fold.exploratory_backtest_run_id =
                     dataset.exploratory_backtest_run_id
                JOIN mra.exploratory_backtest_fold_session AS member
                  ON member.exploratory_backtest_fold_session_id =
                     dataset.exploratory_backtest_fold_session_id
                 AND member.exploratory_backtest_fold_id =
                     dataset.exploratory_backtest_fold_id
                LEFT JOIN mra.exploratory_retrospective_decision_run AS decision
                  ON decision.dataset_id = dataset.dataset_id
                 AND decision.exploratory_backtest_run_id =
                     dataset.exploratory_backtest_run_id
                WHERE dataset.exploratory_backtest_run_id = %s
                ORDER BY fold.ordinal, arm.ordinal
                """,
                (exploratory_backtest_run_id,),
            ).fetchall()
            expected_shape = (
                ("MODEL_CHALLENGER", "FIT", "FIT_INPUT"),
                ("RULE_BASELINE", "VALIDATION", "EVALUATION"),
                ("MODEL_CHALLENGER", "VALIDATION", "EVALUATION"),
            )
            if len(datasets) < len(expected_shape):
                return None
            observed_shape = tuple(
                (str(row[1]), str(row[2]), str(row[3])) for row in datasets
            )
            if len(datasets) != len(expected_shape) or observed_shape != expected_shape:
                raise ArtifactIntegrityError(
                    "exploratory campaign Dataset roster is not the frozen shape"
                )
            if any(row[4] is None for row in datasets):
                return None
            evaluations = connection.execute(
                """
                SELECT experiment_id, evaluation_run_id, status
                FROM mra.evaluation_run
                WHERE experiment_id IN (%s, %s)
                ORDER BY experiment_id
                """,
                (fit_experiment_id, validation_experiment_id),
            ).fetchall()
            if len(evaluations) < 2 or any(str(row[2]) != "COMPLETED" for row in evaluations):
                return None
            if len(evaluations) != 2:
                raise ArtifactIntegrityError(
                    "exploratory campaign Evaluation roster is ambiguous"
                )
            evaluation_by_experiment = {
                UUID(str(row[0])): UUID(str(row[1])) for row in evaluations
            }
            model_versions = connection.execute(
                """
                SELECT version.model_version_id
                FROM mra.model_version AS version
                JOIN mra.model_training_run AS training
                  ON training.model_training_run_id = version.model_training_run_id
                WHERE training.exploratory_backtest_run_id = %s
                  AND training.evaluation_run_id = %s
                """,
                (
                    exploratory_backtest_run_id,
                    evaluation_by_experiment[fit_experiment_id],
                ),
            ).fetchall()
            if not model_versions:
                return None
            if len(model_versions) != 1:
                raise ArtifactIntegrityError(
                    "exploratory campaign ModelVersion roster is ambiguous"
                )
        return CompletedExploratoryCampaign(
            exploratory_backtest_run_id=exploratory_backtest_run_id,
            fit_dataset_id=UUID(str(datasets[0][0])),
            fit_decision_run_id=UUID(str(datasets[0][4])),
            fit_evaluation_run_id=evaluation_by_experiment[fit_experiment_id],
            model_version_id=UUID(str(model_versions[0][0])),
            validation_dataset_ids=tuple(UUID(str(row[0])) for row in datasets[1:]),
            validation_decision_run_ids=tuple(
                UUID(str(row[4])) for row in datasets[1:]
            ),
            validation_evaluation_run_id=evaluation_by_experiment[
                validation_experiment_id
            ],
        )


def _fold_id(
    pool: TargetPostgresPool,
    exploratory_backtest_run_id: UUID,
    purpose: str,
) -> UUID:
    with pool.connection(read_only=True) as connection:
        rows = connection.execute(
            """
            SELECT exploratory_backtest_fold_id
            FROM mra.exploratory_backtest_fold
            WHERE exploratory_backtest_run_id = %s AND purpose = %s
            """,
            (exploratory_backtest_run_id, purpose),
        ).fetchall()
    if len(rows) != 1:
        raise ArtifactIntegrityError(
            f"exploratory campaign requires exactly one {purpose} fold"
        )
    return UUID(str(rows[0][0]))


__all__ = ["PostgresExploratoryCampaignReadPort"]
