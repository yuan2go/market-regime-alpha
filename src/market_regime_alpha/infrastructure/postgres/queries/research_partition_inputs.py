"""PostgreSQL derivation of ex-ante Partition members and session protection."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import psycopg

from market_regime_alpha.research_qualification.domain.partition import ResearchPartitionPlan
from market_regime_alpha.research_qualification.errors import PartitionInputError
from market_regime_alpha.research_qualification.ports.partition_inputs import (
    DerivedPartitionMember,
    PartitionCalendarBounds,
)


class PostgresPartitionInputQueries:
    """Uses frozen Decision commitments and exact TradingSession rows only."""

    def __init__(self, connection: psycopg.Connection[Any]) -> None:
        self._connection = connection

    def lock_target_and_calendar(
        self, plan: ResearchPartitionPlan
    ) -> PartitionCalendarBounds:
        if plan.backtest_source is not None:
            source = plan.backtest_source
            exact_source = self._connection.execute(
                """
                SELECT specification.specification_sha256
                FROM mra.backtest_specification AS specification
                JOIN mra.exploratory_backtest_run AS root
                  ON root.exploratory_backtest_run_id =
                     specification.exploratory_backtest_run_id
                 AND root.current_specification_sha256 =
                     specification.specification_sha256
                JOIN mra.backtest_arm_specification AS arm
                  ON arm.exploratory_backtest_run_id =
                     specification.exploratory_backtest_run_id
                 AND arm.specification_sha256 =
                     specification.specification_sha256
                 AND arm.exploratory_backtest_arm_id = %s
                LEFT JOIN mra.exploratory_backtest_fold AS fold
                  ON fold.exploratory_backtest_run_id =
                     specification.exploratory_backtest_run_id
                 AND fold.specification_sha256 =
                     specification.specification_sha256
                 AND fold.exploratory_backtest_fold_id = %s
                WHERE specification.exploratory_backtest_run_id = %s
                  AND (%s::uuid IS NULL
                       OR fold.exploratory_backtest_fold_id IS NOT NULL)
                """,
                (
                    source.exploratory_backtest_arm_id,
                    source.exploratory_backtest_fold_id,
                    source.exploratory_backtest_run_id,
                    source.exploratory_backtest_fold_id,
                ),
            ).fetchall()
            if len(exact_source) != 1:
                raise PartitionInputError(
                    "exact current Backtest Partition source does not exist"
                )
        target = self._connection.execute(
            """
            SELECT target_definition_id
            FROM mra.target_definition
            WHERE target_definition_id = %s
              AND version = %s
              AND content_sha256 = %s
            FOR SHARE
            """,
            (
                plan.target_definition_id,
                plan.target_version,
                str(plan.target_definition_sha256),
            ),
        ).fetchone()
        if target is None:
            raise PartitionInputError("exact registered Target does not exist")
        horizon_row = self._connection.execute(
            """
            SELECT max(session_offset)
            FROM mra.target_checkpoint
            WHERE target_definition_id = %s
              AND checkpoint_role = 'OUTCOME_OBSERVATION'
            """,
            (plan.target_definition_id,),
        ).fetchone()
        if horizon_row is None or horizon_row[0] is None:
            raise PartitionInputError("Target Outcome horizon is absent")
        horizon = int(horizon_row[0])
        session_rows = self._connection.execute(
            """
            SELECT session_id, exchange, session_date, timezone_name
            FROM mra.trading_session
            WHERE session_id IN (%s, %s)
            ORDER BY session_date, session_id
            FOR SHARE
            """,
            (plan.decision_start_session_id, plan.decision_end_session_id),
        ).fetchall()
        by_id = {UUID(str(row[0])): row for row in session_rows}
        if {
            plan.decision_start_session_id,
            plan.decision_end_session_id,
        } - set(by_id):
            raise PartitionInputError("Decision window Session identity is incomplete")
        start = by_id[plan.decision_start_session_id]
        end = by_id[plan.decision_end_session_id]
        if (
            str(start[1]) != plan.exchange_code
            or str(end[1]) != plan.exchange_code
            or start[3] != end[3]
            or start[2] > end[2]
        ):
            raise PartitionInputError(
                "Decision window must be ordered on the declared exchange calendar"
            )
        exchange = str(start[1])
        start_shift = plan.purge_before_sessions
        end_shift = horizon + plan.purge_after_sessions + plan.embargo_sessions
        protected_start = self._connection.execute(
            """
            SELECT session_id, session_date
            FROM mra.trading_session
            WHERE exchange = %s AND session_date <= %s
            ORDER BY session_date DESC, session_id DESC
            OFFSET %s LIMIT 1
            """,
            (exchange, start[2], start_shift),
        ).fetchone()
        protected_end = self._connection.execute(
            """
            SELECT session_id, session_date
            FROM mra.trading_session
            WHERE exchange = %s AND session_date >= %s
            ORDER BY session_date, session_id
            OFFSET %s LIMIT 1
            """,
            (exchange, end[2], end_shift),
        ).fetchone()
        if protected_start is None or protected_end is None:
            raise PartitionInputError(
                "exact TradingSession roster cannot satisfy purge/horizon/embargo"
            )
        calendar_rows = self._connection.execute(
            """
            SELECT session_id
            FROM mra.trading_session
            WHERE exchange = %s
              AND session_date BETWEEN %s AND %s
            ORDER BY session_date, session_id
            FOR SHARE
            """,
            (exchange, protected_start[1], protected_end[1]),
        ).fetchall()
        calendar_identity = self._connection.execute(
            """
            SELECT count(*),
                   mra.canonical_sha256(
                       replace(
                           json_agg(
                               json_build_object(
                                   'break_end_at', break_end_at,
                                   'break_start_at', break_start_at,
                                   'close_at', close_at,
                                   'decision_reference_at', decision_reference_at,
                                   'decision_visible_at', decision_visible_at,
                                   'exchange_code', exchange,
                                   'known_at', known_at,
                                   'open_at', open_at,
                                   'recorded_at', recorded_at,
                                   'session_date', session_date,
                                   'session_id', session_id,
                                   'source_capture_id', source_capture_id,
                                   'timezone_name', timezone_name
                               ) ORDER BY session_date, session_id
                           )::text,
                           ' ',
                           ''
                       )
                   )
            FROM mra.trading_session
            WHERE exchange = %s
              AND session_date BETWEEN %s AND %s
            """,
            (exchange, protected_start[1], protected_end[1]),
        ).fetchone()
        if (
            calendar_identity is None
            or not calendar_rows
            or int(calendar_identity[0]) != len(calendar_rows)
            or calendar_identity[1] is None
        ):
            raise PartitionInputError("declared exchange calendar roster is incomplete")
        return PartitionCalendarBounds(
            exchange_code=exchange,
            timezone_name=str(start[3]),
            decision_start_date=start[2],
            decision_end_date=end[2],
            protected_start_session_id=UUID(str(protected_start[0])),
            protected_end_session_id=UUID(str(protected_end[0])),
            protected_start_date=protected_start[1],
            protected_end_date=protected_end[1],
            outcome_horizon_sessions=horizon,
            calendar_session_count=int(calendar_identity[0]),
            calendar_roster_sha256=str(calendar_identity[1]),
        )

    def derive_complete_roster(
        self, plan: ResearchPartitionPlan
    ) -> tuple[DerivedPartitionMember, ...]:
        # Serialize the snapshot with Decision commitment insertion. The
        # deferred database closure takes the same lock, so raw SQL cannot
        # bypass complete-population derivation.
        self._connection.execute(
            "LOCK TABLE mra.decision_target_commitment IN SHARE MODE"
        )
        disposition = (
            None
            if plan.population_scope.value == "ALL_COMMITMENTS"
            else plan.population_scope.value
        )
        source = plan.backtest_source
        source_values = (
            None if source is None else source.exploratory_backtest_run_id,
            None if source is None else source.exploratory_backtest_run_id,
            None if source is None else source.exploratory_backtest_arm_id,
            None if source is None else source.exploratory_backtest_fold_id,
            None if source is None else source.exploratory_backtest_fold_id,
            None if source is None else source.exploratory_backtest_fold_id,
            None if source is None else source.exploratory_backtest_run_id,
        )
        base_count = self._connection.execute(
            """
            SELECT count(*)
            FROM mra.decision_target_commitment AS commitment
            JOIN mra.decision_reference_observation AS reference
              ON reference.decision_reference_observation_id =
                 commitment.decision_reference_observation_id
            JOIN mra.trading_session AS decision_session
              ON decision_session.session_id = reference.session_id
            LEFT JOIN mra.exploratory_retrospective_decision_run AS backtest
              ON backtest.decision_run_id = commitment.decision_run_id
            JOIN mra.trading_session AS start_session
              ON start_session.session_id = %s
            JOIN mra.trading_session AS end_session
              ON end_session.session_id = %s
            WHERE commitment.target_definition_id = %s
              AND decision_session.exchange = %s
              AND start_session.exchange = %s
              AND end_session.exchange = %s
              AND decision_session.session_date BETWEEN
                  start_session.session_date AND end_session.session_date
              AND (%s::text IS NULL OR commitment.candidate_disposition = %s)
              AND (%s::uuid IS NULL OR (
                    backtest.exploratory_backtest_run_id = %s
                AND backtest.exploratory_backtest_arm_id = %s
                AND ((%s::uuid IS NOT NULL AND
                      backtest.exploratory_backtest_fold_id = %s)
                  OR (%s::uuid IS NULL AND EXISTS (
                      SELECT 1
                      FROM mra.exploratory_backtest_fold AS source_fold
                      WHERE source_fold.exploratory_backtest_fold_id =
                            backtest.exploratory_backtest_fold_id
                        AND source_fold.exploratory_backtest_run_id = %s
                        AND source_fold.purpose = 'VALIDATION'
                  )))))
            """,
            (
                plan.decision_start_session_id,
                plan.decision_end_session_id,
                plan.target_definition_id,
                plan.exchange_code,
                plan.exchange_code,
                plan.exchange_code,
                disposition,
                disposition,
                *source_values,
            ),
        ).fetchone()
        assert base_count is not None
        rows = self._connection.execute(
            """
            WITH base AS (
                SELECT commitment.commitment_id,
                       reference.decision_reference_observation_id,
                       commitment.target_definition_id,
                       commitment.decision_time,
                       commitment.candidate_disposition,
                       commitment.commitment_recorded_at,
                       commitment.runtime_mode,
                       reference.session_id AS decision_session_id,
                       decision_session.exchange,
                       decision_session.session_date,
                       decision_session.timezone_name
                FROM mra.decision_target_commitment AS commitment
                JOIN mra.decision_reference_observation AS reference
                  ON reference.decision_reference_observation_id =
                     commitment.decision_reference_observation_id
                JOIN mra.trading_session AS decision_session
                  ON decision_session.session_id = reference.session_id
                LEFT JOIN mra.exploratory_retrospective_decision_run AS backtest
                  ON backtest.decision_run_id = commitment.decision_run_id
                JOIN mra.trading_session AS start_session
                  ON start_session.session_id = %s
                JOIN mra.trading_session AS end_session
                  ON end_session.session_id = %s
                WHERE commitment.target_definition_id = %s
                  AND decision_session.exchange = %s
                  AND start_session.exchange = %s
                  AND end_session.exchange = %s
                  AND decision_session.session_date BETWEEN
                      start_session.session_date AND end_session.session_date
                  AND (%s::text IS NULL OR commitment.candidate_disposition = %s)
                  AND (%s::uuid IS NULL OR (
                        backtest.exploratory_backtest_run_id = %s
                    AND backtest.exploratory_backtest_arm_id = %s
                    AND ((%s::uuid IS NOT NULL AND
                          backtest.exploratory_backtest_fold_id = %s)
                      OR (%s::uuid IS NULL AND EXISTS (
                          SELECT 1
                          FROM mra.exploratory_backtest_fold AS source_fold
                          WHERE source_fold.exploratory_backtest_fold_id =
                                backtest.exploratory_backtest_fold_id
                            AND source_fold.exploratory_backtest_run_id = %s
                            AND source_fold.purpose = 'VALIDATION'
                      )))))
            )
            SELECT base.commitment_id,
                   base.decision_reference_observation_id,
                   base.target_definition_id,
                   base.decision_time, base.candidate_disposition,
                   base.commitment_recorded_at, base.runtime_mode,
                   base.decision_session_id,
                   base.session_date,
                   base.exchange,
                   base.timezone_name,
                   min((future.session_date + checkpoint.local_time)
                       AT TIME ZONE checkpoint.timezone_name),
                   max((future.session_date + checkpoint.local_time)
                       AT TIME ZONE checkpoint.timezone_name)
            FROM base
            JOIN mra.target_checkpoint AS checkpoint
              ON checkpoint.target_definition_id = base.target_definition_id
             AND checkpoint.checkpoint_role = 'OUTCOME_OBSERVATION'
            JOIN LATERAL (
                SELECT session.session_date
                FROM mra.trading_session AS session
                WHERE session.exchange = base.exchange
                  AND session.session_date > base.session_date
                ORDER BY session.session_date, session.session_id
                OFFSET checkpoint.session_offset - 1 LIMIT 1
            ) AS future ON true
            GROUP BY base.commitment_id,
                     base.decision_reference_observation_id,
                     base.target_definition_id,
                     base.decision_time, base.candidate_disposition,
                     base.commitment_recorded_at, base.runtime_mode,
                     base.decision_session_id, base.session_date,
                     base.exchange, base.timezone_name
            ORDER BY base.decision_time, base.commitment_id
            """,
            (
                plan.decision_start_session_id,
                plan.decision_end_session_id,
                plan.target_definition_id,
                plan.exchange_code,
                plan.exchange_code,
                plan.exchange_code,
                disposition,
                disposition,
                *source_values,
            ),
        ).fetchall()
        if not rows and plan.backtest_source is None:
            raise PartitionInputError("declared Partition population is empty")
        if len(rows) != int(base_count[0]):
            raise PartitionInputError(
                "exact future TradingSession roster is incomplete for a commitment"
            )
        result = tuple(
            DerivedPartitionMember(
                commitment_id=UUID(str(row[0])),
                decision_reference_observation_id=UUID(str(row[1])),
                target_definition_id=UUID(str(row[2])),
                decision_time=row[3],
                candidate_disposition=str(row[4]),
                commitment_recorded_at=row[5],
                runtime_mode=str(row[6]),
                decision_session_id=UUID(str(row[7])),
                decision_session_date=row[8],
                exchange_code=str(row[9]),
                timezone_name=str(row[10]),
                earliest_outcome_event_at=row[11],
                outcome_due_at=row[12],
            )
            for row in rows
        )
        if plan.purpose.value == "PROSPECTIVE" and any(
            item.commitment_recorded_at >= item.earliest_outcome_event_at
            for item in result
        ):
            raise PartitionInputError(
                "commitment was not recorded before its earliest Outcome event"
            )
        return result

    def require_canonical_live_clock(
        self, members: tuple[DerivedPartitionMember, ...]
    ) -> None:
        if not members:
            raise PartitionInputError("Prospective Partition roster is empty")
        commitment_ids = [item.commitment_id for item in members]
        rows = self._connection.execute(
            """
            WITH RECURSIVE roots AS (
                SELECT commitment.commitment_id, runtime.run_id,
                       runtime.runtime_mode, runtime.requested_at,
                       runtime.created_at, runtime.decision_time,
                       runtime.parent_run_id, runtime.original_run_id
                FROM mra.decision_target_commitment AS commitment
                JOIN mra.decision_run AS decision
                  ON decision.decision_run_id = commitment.decision_run_id
                JOIN mra.runtime_run AS runtime
                  ON runtime.run_id = decision.runtime_run_id
                WHERE commitment.commitment_id = ANY(%s::uuid[])
            ), lineage AS (
                SELECT commitment_id, run_id, runtime_mode,
                       requested_at, created_at, decision_time,
                       parent_run_id, original_run_id
                FROM roots
                UNION
                SELECT lineage.commitment_id, ancestor.run_id,
                       ancestor.runtime_mode, ancestor.requested_at,
                       ancestor.created_at, ancestor.decision_time,
                       ancestor.parent_run_id, ancestor.original_run_id
                FROM lineage
                JOIN mra.runtime_run AS ancestor
                  ON ancestor.run_id IN (lineage.parent_run_id, lineage.original_run_id)
            )
            SELECT commitment_id,
                   bool_and(runtime_mode NOT IN ('HISTORICAL', 'REPLAY')
                            AND requested_at <= decision_time
                            AND created_at <= decision_time) AS live_clock
            FROM lineage
            GROUP BY commitment_id
            """,
            (commitment_ids,),
        ).fetchall()
        eligibility = {UUID(str(row[0])): bool(row[1]) for row in rows}
        if len(eligibility) != len(members) or not all(eligibility.values()):
            raise PartitionInputError(
                "Prospective Partition requires canonical live-clock Runtime lineage"
            )
        if any(
            item.runtime_mode in {"HISTORICAL", "REPLAY"}
            for item in members
        ):
            raise PartitionInputError(
                "HISTORICAL/REPLAY commitment cannot be Prospective"
            )


__all__ = ["PostgresPartitionInputQueries"]
