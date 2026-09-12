"""Exact Evaluation-owned forecast/label inputs, not a second raw-price evaluator."""

from uuid import UUID

from psycopg.rows import dict_row

from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.research_qualification.domain.historical_comparison import HistoricalEvaluationPoint
from market_regime_alpha.runtime.errors import ArtifactIntegrityError
from market_regime_alpha.research_qualification.ports.artifacts import ResearchArtifactByteStore


class PostgresHistoricalComparisonInputs:
    def __init__(self, pool: TargetPostgresPool, byte_store: ResearchArtifactByteStore) -> None:
        self._pool, self._bytes = pool, byte_store

    def fitted_diagnostics(self, run_id: UUID) -> tuple[dict, ...]:
        from market_regime_alpha.infrastructure.postgres.queries.historical_fit_diagnostics import historical_fit_diagnostics
        return historical_fit_diagnostics(self._pool,self._bytes,run_id)

    def contiguous_folds(self, run_id: UUID) -> frozenset[UUID]:
        """Only the real Calendar can attest adjacent trading-day blocks."""
        with self._pool.connection(read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT fold.exploratory_backtest_fold_id,
                       array_agg(session.session_date ORDER BY session.session_date),
                       ARRAY(SELECT calendar.session_date FROM mra.trading_session calendar
                           WHERE calendar.exchange=fold.exchange_code
                             AND calendar.session_date BETWEEN min(session.session_date) AND max(session.session_date)
                           ORDER BY calendar.session_date)
                FROM mra.exploratory_backtest_fold fold
                JOIN mra.exploratory_backtest_fold_session session USING(exploratory_backtest_fold_id)
                WHERE fold.exploratory_backtest_run_id=%s AND session.session_role='EVALUATION'
                GROUP BY fold.exploratory_backtest_fold_id,fold.exchange_code
                """,
                (run_id,),
            ).fetchall()
        return frozenset(row[0] for row in rows if row[1] == row[2])

    def load(self, run_id: UUID) -> tuple[HistoricalEvaluationPoint, ...]:
        with self._pool.connection(read_only=True) as connection:
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            closure = connection.execute(
                """
                SELECT requirement.backtest_evaluation_requirement_id,evaluation.status,
                       count(formula.evaluation_protocol_metric_id) FILTER(WHERE formula.formula_code='predictive_mae')
                FROM mra.backtest_evaluation_requirement requirement
                JOIN mra.exploratory_backtest_fold fold USING(exploratory_backtest_fold_id)
                LEFT JOIN mra.backtest_evaluation_execution execution USING(backtest_evaluation_requirement_id)
                LEFT JOIN mra.evaluation_run evaluation USING(evaluation_run_id)
                LEFT JOIN mra.evaluation_protocol_metric metric
                    ON metric.evaluation_protocol_id=requirement.evaluation_protocol_id
                LEFT JOIN mra.evaluation_metric_formula formula USING(evaluation_protocol_metric_id)
                WHERE requirement.exploratory_backtest_run_id=%s AND requirement.scope_kind='FOLD' AND fold.purpose='VALIDATION'
                GROUP BY requirement.backtest_evaluation_requirement_id,evaluation.status
                """,
                (run_id,),
            ).fetchall()
            if not closure or any(row[1] != "COMPLETED" or row[2] != 1 for row in closure):
                raise ArtifactIntegrityError("historical comparison requires completed canonical MAE evaluations")
            with connection.cursor(row_factory=dict_row) as c:
                rows = c.execute(
                    """
                    SELECT requirement.exploratory_backtest_arm_id AS arm_id,
                           requirement.exploratory_backtest_fold_id AS fold_id,
                           dataset.exploratory_backtest_fold_session_id AS session_id,
                           session.session_date, commitment.instrument_id, member.commitment_id,
                           input.evaluation_run_id, input.evaluation_observation_id,
                           input.evaluation_metric_observation_id AS metric_observation_id,
                           input.market_target_outcome_revision_id AS outcome_revision_id,
                           input.source_outcome_metric_id AS outcome_metric_id,
                           dataset.dataset_id, model.model_version_id,
                           input.input_state, input.reason_code,
                           source.forecast_status, input.source_value_status AS label_status,
                           source.point_estimate AS prediction, label.decimal_value AS label,
                           input.content_sha256 AS input_sha256, source.content_sha256 AS source_sha256,
                           source.outcome_decimal_value AS frozen_pair_label
                    FROM mra.backtest_evaluation_requirement requirement
                    JOIN mra.backtest_evaluation_execution execution USING(backtest_evaluation_requirement_id)
                    JOIN mra.evaluation_run evaluation USING(evaluation_run_id)
                    JOIN mra.evaluation_metric_observation input USING(evaluation_run_id)
                    JOIN mra.evaluation_metric_formula formula USING(evaluation_protocol_metric_id)
                    JOIN mra.research_partition_member member USING(research_partition_member_id)
                    JOIN mra.decision_target_commitment commitment USING(commitment_id)
                    JOIN mra.decision_run decision ON decision.decision_run_id=commitment.decision_run_id
                    JOIN mra.exploratory_backtest_dataset dataset ON dataset.dataset_id=decision.dataset_id
                    JOIN mra.exploratory_backtest_fold_session session USING(exploratory_backtest_fold_session_id)
                    JOIN mra.market_target_outcome_metric label
                      ON label.market_target_outcome_metric_id=input.source_outcome_metric_id
                    LEFT JOIN mra.evaluation_forecast_source source USING(evaluation_metric_observation_id)
                    LEFT JOIN mra.forecast_model_binding model ON model.forecast_id=source.forecast_id
                    WHERE requirement.exploratory_backtest_run_id=%s
                      AND requirement.scope_kind='FOLD' AND evaluation.partition_purpose='VALIDATION'
                      AND evaluation.status='COMPLETED' AND formula.formula_code='predictive_mae'
                    ORDER BY requirement.ordinal,session.ordinal,commitment.instrument_id
                    LIMIT 200001
                    """,
                    (run_id,),
                ).fetchall()
        if len(rows) > 200000:
            raise ValueError("historical comparison exceeds 200000 Evaluation inputs; use explicit smaller runs")
        result = []
        for row in rows:
            frozen = row.pop("frozen_pair_label")
            if frozen is not None and frozen != row["label"]:
                raise ArtifactIntegrityError("frozen Evaluation label differs from its exact Outcome metric")
            result.append(HistoricalEvaluationPoint(**row))
        return tuple(result)
