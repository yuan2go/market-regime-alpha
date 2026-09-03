"""Read-only standard Backtest report projection from canonical Authorities."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from psycopg.rows import dict_row

from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.postgres.queries.backtests import (
    PostgresBacktestQueryPort,
)
from market_regime_alpha.research_qualification.domain.backtest import (
    AuthorityBinding,
    BacktestWalkForwardMode,
    BacktestWalkForwardPolicy,
    VersionedAuthorityBinding,
)
from market_regime_alpha.research_qualification.domain.backtest_report import (
    BacktestReportConfiguration,
    BacktestReportMetric,
    BacktestReportModel,
    BacktestReportSource,
)
from market_regime_alpha.research_qualification.domain.evaluation_formula import (
    BacktestFormulaCode,
    BacktestMetricSurface,
    FormulaResultState,
)
from market_regime_alpha.research_qualification.errors import (
    BacktestReportIntegrityError,
)
from market_regime_alpha.shared.hashing import canonical_json_sha256


class PostgresBacktestReportSourcePort:
    """Load a deterministic projection; deliberately has no Market-bar query."""

    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool
        self._backtests = PostgresBacktestQueryPort(pool)

    def load(self, exploratory_backtest_run_id: UUID) -> BacktestReportSource:
        run = self._backtests.load(exploratory_backtest_run_id)
        if not run.evaluation_requirements:
            raise BacktestReportIntegrityError("standard reports require a current relational specification")
        with self._pool.connection(read_only=True) as connection:
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            with connection.cursor(row_factory=dict_row) as cursor:
                root = cursor.execute(
                    """
                    SELECT root.market_archive_id,
                           archive.content_sha256 AS market_archive_sha256,
                           root.market_archive_seal_id,
                           seal.content_sha256 AS market_archive_seal_sha256,
                           specification.universe_revision_id,
                           specification.universe_scope_sha256,
                           specification.sample_algorithm_code,
                           specification.sample_roster_sha256,
                           root.feature_roster_sha256,
                           root.target_definition_id, root.target_version,
                           root.target_definition_sha256,
                           specification.walk_forward_policy_code,
                           specification.walk_forward_policy_version,
                           specification.walk_forward_mode,
                           specification.minimum_fit_sessions,
                           specification.minimum_validation_sessions,
                           specification.step_sessions,
                           root.fold_roster_sha256,
                           specification.fold_dependency_roster_sha256,
                           root.cost_roster_sha256,
                           root.code_content_sha256,
                           root.config_content_sha256,
                           first_session.session_date AS first_session_date,
                           last_session.session_date AS last_session_date,
                           specification.distinct_trading_session_count,
                           specification.fold_session_binding_count,
                           specification.sample_member_count
                    FROM mra.exploratory_backtest_run AS root
                    JOIN mra.backtest_specification AS specification
                      USING (exploratory_backtest_run_id)
                    JOIN mra.market_archive AS archive
                      ON archive.market_archive_id = root.market_archive_id
                    JOIN mra.market_archive_seal AS seal
                      ON seal.market_archive_seal_id =
                         root.market_archive_seal_id
                    JOIN mra.trading_session AS first_session
                      ON first_session.session_id =
                         specification.first_trading_session_id
                    JOIN mra.trading_session AS last_session
                      ON last_session.session_id =
                         specification.last_trading_session_id
                    WHERE root.exploratory_backtest_run_id = %s
                      AND root.current_specification_sha256 =
                          specification.specification_sha256
                    """,
                    (exploratory_backtest_run_id,),
                ).fetchone()
                evaluation_rows = cursor.execute(
                    """
                    SELECT requirement.ordinal AS requirement_ordinal,
                           requirement.backtest_evaluation_requirement_id,
                           requirement.scope_kind,
                           requirement.exploratory_backtest_arm_id,
                           requirement.exploratory_backtest_fold_id,
                           requirement.slice_key,
                           execution.evaluation_run_id,
                           evaluation.completed_at,
                           metric.evaluation_metric_id,
                           metric.evaluation_protocol_metric_id,
                           metric.metric_state, metric.decimal_value,
                           metric.estimable_count, metric.reason_code,
                           metric.acceptance_state,
                           protocol.ordinal AS metric_ordinal,
                           protocol.metric_code,
                           formula.surface_code, formula.formula_code,
                           formula.formula_version,
                           formula.content_sha256 AS formula_content_sha256
                    FROM mra.backtest_evaluation_requirement AS requirement
                    JOIN mra.backtest_evaluation_execution AS execution
                      ON execution.backtest_evaluation_requirement_id =
                         requirement.backtest_evaluation_requirement_id
                     AND execution.exploratory_backtest_run_id =
                         requirement.exploratory_backtest_run_id
                     AND execution.specification_sha256 =
                         requirement.specification_sha256
                    JOIN mra.evaluation_run AS evaluation
                      ON evaluation.evaluation_run_id =
                         execution.evaluation_run_id
                     AND evaluation.status = 'COMPLETED'
                     AND evaluation.evaluation_protocol_id =
                         requirement.evaluation_protocol_id
                    JOIN mra.evaluation_metric AS metric
                      ON metric.evaluation_run_id = evaluation.evaluation_run_id
                    JOIN mra.evaluation_protocol_metric AS protocol
                      ON protocol.evaluation_protocol_metric_id =
                         metric.evaluation_protocol_metric_id
                     AND protocol.evaluation_protocol_id =
                         requirement.evaluation_protocol_id
                    JOIN mra.evaluation_metric_formula AS formula
                      ON formula.evaluation_protocol_metric_id =
                         protocol.evaluation_protocol_metric_id
                     AND formula.evaluation_protocol_id =
                         protocol.evaluation_protocol_id
                    WHERE requirement.exploratory_backtest_run_id = %s
                    ORDER BY requirement.ordinal, protocol.ordinal
                    """,
                    (exploratory_backtest_run_id,),
                ).fetchall()
                model_rows = cursor.execute(
                    """
                    SELECT requirement.exploratory_backtest_arm_id,
                           requirement.model_id, requirement.model_sha256,
                           requirement.fit_fold_id,
                           requirement.validation_fold_id,
                           training.model_training_run_id,
                           version.model_version_id
                    FROM mra.backtest_model_training_requirement AS requirement
                    LEFT JOIN mra.model_training_run AS training
                      ON training.exploratory_backtest_run_id =
                         requirement.exploratory_backtest_run_id
                     AND training.exploratory_backtest_arm_id =
                         requirement.exploratory_backtest_arm_id
                     AND training.exploratory_backtest_fold_id =
                         requirement.fit_fold_id
                     AND training.model_id = requirement.model_id
                    LEFT JOIN mra.model_version AS version
                      ON version.model_training_run_id =
                         training.model_training_run_id
                     AND version.model_id = training.model_id
                    WHERE requirement.exploratory_backtest_run_id = %s
                    ORDER BY requirement.ordinal
                    """,
                    (exploratory_backtest_run_id,),
                ).fetchall()
        if root is None:
            raise BacktestReportIntegrityError("Backtest report configuration is absent")
        requirement_ids = {UUID(str(row["backtest_evaluation_requirement_id"])) for row in evaluation_rows}
        expected_requirement_ids = {item.requirement_id for item in run.evaluation_requirements}
        if requirement_ids != expected_requirement_ids:
            raise BacktestReportIntegrityError("Backtest report Evaluation execution roster is incomplete")
        metrics = tuple(_metric(row) for row in evaluation_rows)
        evaluation_ids = tuple(dict.fromkeys(UUID(str(row["evaluation_run_id"])) for row in evaluation_rows))
        completion_times = tuple(row["completed_at"] for row in evaluation_rows)
        if not completion_times or any(not isinstance(value, datetime) for value in completion_times):
            raise BacktestReportIntegrityError("Backtest report lacks canonical Evaluation completion time")
        formula_roster_hash = _formula_roster_hash(evaluation_rows)
        effective_policy_hash = canonical_json_sha256(
            tuple(
                {
                    "arm_id": arm.exploratory_backtest_arm_id,
                    "candidate_sha256": str(arm.candidate.content_sha256),
                    "context_sha256": str(arm.context.content_sha256),
                    "cost_sha256": str(arm.effective_cost_roster_sha256),
                    "portfolio_sha256": str(arm.portfolio.content_sha256),
                    "risk_sha256": str(arm.risk.content_sha256),
                    "strategy_sha256": str(arm.strategy.content_sha256),
                }
                for arm in run.arms
            )
        )
        walk_forward = BacktestWalkForwardPolicy(
            str(root["walk_forward_policy_code"]),
            int(root["walk_forward_policy_version"]),
            BacktestWalkForwardMode(str(root["walk_forward_mode"])),
            int(root["minimum_fit_sessions"]),
            int(root["minimum_validation_sessions"]),
            int(root["step_sessions"]),
        )
        configuration = BacktestReportConfiguration(
            market_archive=AuthorityBinding(
                UUID(str(root["market_archive_id"])),
                str(root["market_archive_sha256"]),
            ),
            market_archive_seal=AuthorityBinding(
                UUID(str(root["market_archive_seal_id"])),
                str(root["market_archive_seal_sha256"]),
            ),
            universe_revision=AuthorityBinding(
                UUID(str(root["universe_revision_id"])),
                str(root["universe_scope_sha256"]),
            ),
            sample_scope_code=str(root["sample_algorithm_code"]),
            sample_roster_sha256=str(root["sample_roster_sha256"]),
            feature_roster_sha256=str(root["feature_roster_sha256"]),
            target=VersionedAuthorityBinding(
                UUID(str(root["target_definition_id"])),
                int(root["target_version"]),
                str(root["target_definition_sha256"]),
            ),
            walk_forward_policy_sha256=walk_forward.content_sha256,
            fold_roster_sha256=str(root["fold_roster_sha256"]),
            dependency_roster_sha256=str(root["fold_dependency_roster_sha256"]),
            cost_roster_sha256=str(root["cost_roster_sha256"]),
            effective_policy_roster_sha256=effective_policy_hash,
            evaluation_formula_roster_sha256=formula_roster_hash,
            code_content_sha256=str(root["code_content_sha256"]),
            config_content_sha256=str(root["config_content_sha256"]),
            first_session_date=root["first_session_date"].isoformat(),
            last_session_date=root["last_session_date"].isoformat(),
            distinct_trading_session_count=int(root["distinct_trading_session_count"]),
            fold_session_binding_count=int(root["fold_session_binding_count"]),
            sample_member_count=int(root["sample_member_count"]),
        )
        return BacktestReportSource(
            run=run,
            configuration=configuration,
            canonical_completed_at=max(completion_times),
            evaluation_run_ids=evaluation_ids,
            metrics=metrics,
            models=tuple(_model(row) for row in model_rows),
            limitations=(
                "Retrospective exploratory evidence only.",
                "Formal Provider and PIT evidence are blocked.",
            ),
            recommended_next_experiment=("Collect target-aligned prospective evidence without promoting Alpha."),
        )


def _metric(row: dict[str, Any]) -> BacktestReportMetric:
    state = FormulaResultState.ESTIMABLE if str(row["metric_state"]) == "ESTIMATED" else FormulaResultState.NOT_ESTIMABLE
    return BacktestReportMetric(
        evaluation_metric_id=UUID(str(row["evaluation_metric_id"])),
        evaluation_run_id=UUID(str(row["evaluation_run_id"])),
        evaluation_requirement_id=UUID(str(row["backtest_evaluation_requirement_id"])),
        protocol_metric_id=UUID(str(row["evaluation_protocol_metric_id"])),
        arm_id=UUID(str(row["exploratory_backtest_arm_id"])),
        fold_id=(None if row["exploratory_backtest_fold_id"] is None else UUID(str(row["exploratory_backtest_fold_id"]))),
        scope_kind=str(row["scope_kind"]),
        slice_key=None if row["slice_key"] is None else str(row["slice_key"]),
        surface=BacktestMetricSurface(str(row["surface_code"])),
        metric_code=str(row["metric_code"]),
        formula_code=BacktestFormulaCode(str(row["formula_code"])),
        formula_version=int(row["formula_version"]),
        formula_content_sha256=str(row["formula_content_sha256"]),
        result_state=state,
        decimal_value=(None if row["decimal_value"] is None else Decimal(str(row["decimal_value"]))),
        estimable_count=int(row["estimable_count"]),
        reason_code=str(row["reason_code"]),
        acceptance_state=str(row["acceptance_state"]),
    )


def _model(row: dict[str, Any]) -> BacktestReportModel:
    training_id = None if row["model_training_run_id"] is None else UUID(str(row["model_training_run_id"]))
    version_id = None if row["model_version_id"] is None else UUID(str(row["model_version_id"]))
    if training_id is None:
        state, reason = "PLANNED", "MODEL_TRAINING_NOT_RUN"
    elif version_id is None:
        state, reason = "RUNNING", "MODEL_VERSION_NOT_REGISTERED"
    else:
        state, reason = "COMPLETED", "MODEL_LINEAGE_COMPLETE"
    return BacktestReportModel(
        arm_id=UUID(str(row["exploratory_backtest_arm_id"])),
        model_definition=AuthorityBinding(UUID(str(row["model_id"])), str(row["model_sha256"])),
        fit_fold_id=UUID(str(row["fit_fold_id"])),
        validation_fold_id=UUID(str(row["validation_fold_id"])),
        model_training_run_id=training_id,
        model_version_id=version_id,
        state=state,
        reason_code=reason,
    )


def _formula_roster_hash(rows: list[dict[str, Any]]) -> str:
    unique: dict[tuple[UUID, UUID], dict[str, object]] = {}
    for row in rows:
        key = (
            UUID(str(row["backtest_evaluation_requirement_id"])),
            UUID(str(row["evaluation_protocol_metric_id"])),
        )
        unique[key] = {
            "evaluation_requirement_id": key[0],
            "formula_content_sha256": str(row["formula_content_sha256"]),
            "protocol_metric_id": key[1],
        }
    return canonical_json_sha256(tuple(unique[key] for key in sorted(unique, key=str)))


__all__ = ["PostgresBacktestReportSourcePort"]
