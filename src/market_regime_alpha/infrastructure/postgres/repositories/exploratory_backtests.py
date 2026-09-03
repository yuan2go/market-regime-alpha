"""PostgreSQL writer for immutable exploratory backtest protocol roots."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import psycopg

from market_regime_alpha.research_qualification.domain.exploratory_backtest import (
    ExploratoryBacktestRunPlan,
)
from market_regime_alpha.research_qualification.ports.exploratory_backtest_uow import (
    ExploratoryBacktestRecord,
)
from market_regime_alpha.runtime.errors import (
    RuntimeNotFoundError,
    RuntimeStateConflictError,
)


class PostgresExploratoryBacktestRepository:
    def __init__(self, connection: psycopg.Connection[Any]) -> None:
        self._connection = connection

    def lock_identity(self, run_code: str, generation: int) -> None:
        self._connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"exploratory-backtest:{run_code}:{generation}",),
        )

    def register(
        self,
        plan: ExploratoryBacktestRunPlan,
        *,
        request_identity: str,
        request_sha256: str,
    ) -> ExploratoryBacktestRecord:
        self._require_exact_parents(plan)
        self._connection.execute(
            """
            INSERT INTO mra.exploratory_backtest_run (
                exploratory_backtest_run_id, run_code, generation,
                evidence_lane, market_archive_id, market_archive_seal_id,
                hypothesis, target_definition_id, target_version,
                target_definition_sha256,
                candidate_policy_id, candidate_policy_sha256,
                context_policy_id, context_policy_sha256,
                strategy_version_id, strategy_version_sha256,
                portfolio_policy_id, portfolio_policy_sha256,
                risk_policy_id, risk_policy_sha256,
                feature_count, feature_roster_sha256,
                arm_count, arm_roster_sha256,
                fold_count, fold_roster_sha256, session_count,
                cost_count, cost_roster_sha256, random_seed,
                code_artifact_id, code_content_sha256, code_size_bytes,
                config_artifact_id, config_content_sha256, config_size_bytes,
                provenance_sha256, definition_sha256,
                request_identity, request_sha256
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            (
                plan.exploratory_backtest_run_id,
                plan.run_code,
                plan.generation,
                plan.evidence_lane,
                plan.market_archive_id,
                plan.market_archive_seal_id,
                plan.hypothesis,
                plan.target_definition_id,
                plan.target_version,
                str(plan.target_definition_sha256),
                plan.candidate_policy_id,
                str(plan.candidate_policy_sha256),
                plan.context_policy_id,
                str(plan.context_policy_sha256),
                plan.strategy_version_id,
                str(plan.strategy_version_sha256),
                plan.portfolio_policy_id,
                str(plan.portfolio_policy_sha256),
                plan.risk_policy_id,
                str(plan.risk_policy_sha256),
                len(plan.feature_definitions),
                str(plan.feature_roster_sha256),
                len(plan.arms),
                str(plan.arm_roster_sha256),
                len(plan.folds),
                str(plan.fold_roster_sha256),
                plan.session_count,
                len(plan.cost_assumptions),
                str(plan.cost_roster_sha256),
                plan.random_seed,
                plan.code_artifact.artifact_id,
                str(plan.code_artifact.content_sha256),
                plan.code_artifact.size_bytes,
                plan.config_artifact.artifact_id,
                str(plan.config_artifact.content_sha256),
                plan.config_artifact.size_bytes,
                str(plan.provenance_sha256),
                str(plan.content_sha256),
                request_identity,
                request_sha256,
            ),
        )
        with self._connection.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO mra.exploratory_backtest_feature (
                    exploratory_backtest_run_id, feature_ordinal,
                    feature_definition_id, feature_definition_sha256
                ) VALUES (%s, %s, %s, %s)
                """,
                (
                    (
                        plan.exploratory_backtest_run_id,
                        ordinal,
                        feature_id,
                        str(content_hash),
                    )
                    for ordinal, (feature_id, content_hash) in enumerate(
                        plan.feature_definitions,
                        start=1,
                    )
                ),
            )
            cursor.executemany(
                """
                INSERT INTO mra.exploratory_backtest_arm (
                    exploratory_backtest_arm_id,
                    exploratory_backtest_run_id, ordinal, arm_kind,
                    content_sha256
                ) VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    (
                        arm.exploratory_backtest_arm_id,
                        plan.exploratory_backtest_run_id,
                        arm.ordinal,
                        arm.kind.value,
                        str(arm.content_sha256),
                    )
                    for arm in plan.arms
                ),
            )
            cursor.executemany(
                """
                INSERT INTO mra.exploratory_backtest_fold (
                    exploratory_backtest_fold_id,
                    exploratory_backtest_run_id, ordinal, purpose,
                    exchange_code, purge_sessions, embargo_sessions,
                    evaluation_protocol_id, evaluation_protocol_sha256,
                    session_count, session_roster_sha256, content_sha256
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    (
                        fold.exploratory_backtest_fold_id,
                        plan.exploratory_backtest_run_id,
                        fold.ordinal,
                        fold.purpose.value,
                        fold.exchange_code,
                        fold.purge_sessions,
                        fold.embargo_sessions,
                        fold.evaluation_protocol_id,
                        str(fold.evaluation_protocol_sha256),
                        len(fold.sessions),
                        str(fold.session_roster_sha256),
                        str(fold.content_sha256),
                    )
                    for fold in plan.folds
                ),
            )
            cursor.executemany(
                """
                INSERT INTO mra.exploratory_backtest_fold_session (
                    exploratory_backtest_fold_session_id,
                    exploratory_backtest_fold_id,
                    exploratory_backtest_run_id, ordinal,
                    trading_session_id, session_date, session_role,
                    content_sha256
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    (
                        session.exploratory_backtest_fold_session_id,
                        fold.exploratory_backtest_fold_id,
                        plan.exploratory_backtest_run_id,
                        session.ordinal,
                        session.trading_session_id,
                        session.session_date,
                        session.role.value,
                        str(session.content_sha256),
                    )
                    for fold in plan.folds
                    for session in fold.sessions
                ),
            )
            cursor.executemany(
                """
                INSERT INTO mra.exploratory_backtest_cost_assumption (
                    exploratory_backtest_cost_assumption_id,
                    exploratory_backtest_run_id, ordinal,
                    cost_kind, amount_bps, evidence_class, content_sha256
                ) VALUES (%s, %s, %s, %s, %s, 'ASSUMED_COST', %s)
                """,
                (
                    (
                        cost.exploratory_backtest_cost_assumption_id,
                        plan.exploratory_backtest_run_id,
                        cost.ordinal,
                        cost.cost_kind.value,
                        cost.amount_bps,
                        str(cost.content_sha256),
                    )
                    for cost in plan.cost_assumptions
                ),
            )
        self._connection.execute(
            "SET CONSTRAINTS exploratory_backtest_run_reconcile_guard IMMEDIATE"
        )
        return self.record(plan.exploratory_backtest_run_id, lock=False)

    def _require_exact_parents(self, plan: ExploratoryBacktestRunPlan) -> None:
        root = self._connection.execute(
            """
            SELECT 1
            FROM mra.market_archive AS archive
            JOIN mra.market_archive_seal AS seal
              ON seal.market_archive_id = archive.market_archive_id
             AND seal.market_archive_seal_id = %s
            JOIN mra.target_definition AS target
              ON target.target_definition_id = %s
             AND target.version = %s AND target.content_sha256 = %s
            JOIN mra.candidate_policy AS candidate
              ON candidate.candidate_policy_id = %s
             AND candidate.content_sha256 = %s
            JOIN mra.context_policy AS context
              ON context.context_policy_id = %s AND context.content_sha256 = %s
            JOIN mra.strategy_version AS strategy
              ON strategy.strategy_version_id = %s AND strategy.content_sha256 = %s
            JOIN mra.portfolio_policy AS portfolio
              ON portfolio.portfolio_policy_id = %s AND portfolio.content_sha256 = %s
            JOIN mra.risk_policy AS risk
              ON risk.risk_policy_id = %s AND risk.content_sha256 = %s
            WHERE archive.market_archive_id = %s
              AND archive.lane = 'RETROSPECTIVE_BACKFILL'
              AND archive.evidence_class = 'EXPLORATORY_RETROSPECTIVE'
            FOR SHARE OF archive, seal, target, candidate, context,
                         strategy, portfolio, risk
            """,
            (
                plan.market_archive_seal_id,
                plan.target_definition_id,
                plan.target_version,
                str(plan.target_definition_sha256),
                plan.candidate_policy_id,
                str(plan.candidate_policy_sha256),
                plan.context_policy_id,
                str(plan.context_policy_sha256),
                plan.strategy_version_id,
                str(plan.strategy_version_sha256),
                plan.portfolio_policy_id,
                str(plan.portfolio_policy_sha256),
                plan.risk_policy_id,
                str(plan.risk_policy_sha256),
                plan.market_archive_id,
            ),
        ).fetchone()
        if root is None:
            raise RuntimeStateConflictError(
                "Exploratory backtest parent roster is not exact or archive is not retrospective"
            )
        features = self._connection.execute(
            """
            SELECT feature_definition_id, content_sha256
            FROM mra.feature_definition
            WHERE feature_definition_id = ANY(%s::uuid[])
            FOR SHARE
            """,
            ([item[0] for item in plan.feature_definitions],),
        ).fetchall()
        if {
            (UUID(str(row[0])), str(row[1])) for row in features
        } != {(item[0], str(item[1])) for item in plan.feature_definitions}:
            raise RuntimeStateConflictError(
                "Exploratory backtest Feature roster is not exact"
            )
        for fold in plan.folds:
            protocol = self._connection.execute(
                """
                SELECT 1 FROM mra.evaluation_protocol
                WHERE evaluation_protocol_id = %s
                  AND content_sha256 = %s
                  AND target_definition_id = %s
                  AND applicable_purpose = %s
                FOR SHARE
                """,
                (
                    fold.evaluation_protocol_id,
                    str(fold.evaluation_protocol_sha256),
                    plan.target_definition_id,
                    fold.purpose.value,
                ),
            ).fetchone()
            if protocol is None:
                raise RuntimeStateConflictError(
                    "Exploratory backtest EvaluationProtocol is not exact"
                )
            rows = self._connection.execute(
                """
                SELECT session_id, session_date, exchange
                FROM mra.trading_session
                WHERE session_id = ANY(%s::uuid[])
                FOR SHARE
                """,
                ([item.trading_session_id for item in fold.sessions],),
            ).fetchall()
            actual = {
                (UUID(str(row[0])), row[1], str(row[2])) for row in rows
            }
            expected = {
                (item.trading_session_id, item.session_date, fold.exchange_code)
                for item in fold.sessions
            }
            if actual != expected:
                raise RuntimeStateConflictError(
                    "Exploratory backtest trading-session roster is not exact"
                )

    def record(
        self,
        exploratory_backtest_run_id: UUID,
        *,
        lock: bool,
    ) -> ExploratoryBacktestRecord:
        row = self._connection.execute(
            """
            SELECT exploratory_backtest_run_id, generation,
                   feature_count, feature_roster_sha256,
                   arm_count, arm_roster_sha256,
                   fold_count, fold_roster_sha256, session_count,
                   cost_count, cost_roster_sha256,
                   definition_sha256, registered_at
            FROM mra.exploratory_backtest_run
            WHERE exploratory_backtest_run_id = %s
            """
            + (" FOR SHARE" if lock else ""),
            (exploratory_backtest_run_id,),
        ).fetchone()
        if row is None:
            raise RuntimeNotFoundError(
                f"ExploratoryBacktestRun {exploratory_backtest_run_id} does not exist"
            )
        return ExploratoryBacktestRecord(
            exploratory_backtest_run_id=UUID(str(row[0])),
            generation=int(row[1]),
            feature_count=int(row[2]),
            feature_roster_sha256=str(row[3]),
            arm_count=int(row[4]),
            arm_roster_sha256=str(row[5]),
            fold_count=int(row[6]),
            fold_roster_sha256=str(row[7]),
            session_count=int(row[8]),
            cost_count=int(row[9]),
            cost_roster_sha256=str(row[10]),
            definition_sha256=str(row[11]),
            registered_at=row[12],
        )


__all__ = ["PostgresExploratoryBacktestRepository"]
