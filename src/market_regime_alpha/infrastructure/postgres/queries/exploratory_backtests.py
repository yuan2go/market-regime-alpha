"""Read-only exact-roster verification for exploratory backtests."""

from __future__ import annotations

from uuid import UUID

from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.research_qualification.ports.exploratory_backtest_queries import (
    ExploratoryBacktestVerification,
)
from market_regime_alpha.runtime.errors import RuntimeNotFoundError


class PostgresExploratoryBacktestVerificationPort:
    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool

    def verify(
        self,
        exploratory_backtest_run_id: UUID,
    ) -> ExploratoryBacktestVerification:
        with self._pool.connection(read_only=True) as connection:
            root = connection.execute(
                """
                SELECT feature_count, feature_roster_sha256,
                       arm_count, arm_roster_sha256,
                       fold_count, fold_roster_sha256, session_count,
                       cost_count, cost_roster_sha256,
                       request_identity, request_sha256
                FROM mra.exploratory_backtest_run
                WHERE exploratory_backtest_run_id = %s
                """,
                (exploratory_backtest_run_id,),
            ).fetchone()
            if root is None:
                raise RuntimeNotFoundError(f"ExploratoryBacktestRun {exploratory_backtest_run_id} does not exist")
            actual = connection.execute(
                """
                SELECT
                  (SELECT count(*) FROM mra.exploratory_backtest_feature
                   WHERE exploratory_backtest_run_id = %s),
                  (SELECT mra.canonical_sha256(mra.canonical_json_text(coalesce(jsonb_agg(
                       jsonb_build_object(
                           'feature_definition_id', feature_definition_id,
                           'feature_definition_sha256', feature_definition_sha256,
                           'ordinal', feature_ordinal)
                       ORDER BY feature_ordinal), '[]'::jsonb)))
                   FROM mra.exploratory_backtest_feature
                   WHERE exploratory_backtest_run_id = %s),
                  (SELECT count(*) FROM mra.exploratory_backtest_arm
                   WHERE exploratory_backtest_run_id = %s),
                  (SELECT mra.canonical_sha256(mra.canonical_json_text(coalesce(jsonb_agg(
                       jsonb_build_object('content_sha256', content_sha256,
                           'exploratory_backtest_arm_id', exploratory_backtest_arm_id,
                           'ordinal', ordinal) ORDER BY ordinal), '[]'::jsonb)))
                   FROM mra.exploratory_backtest_arm
                   WHERE exploratory_backtest_run_id = %s),
                  (SELECT count(*) FROM mra.exploratory_backtest_fold
                   WHERE exploratory_backtest_run_id = %s),
                  (SELECT mra.canonical_sha256(mra.canonical_json_text(coalesce(jsonb_agg(
                       jsonb_build_object('content_sha256', content_sha256,
                           'exploratory_backtest_fold_id', exploratory_backtest_fold_id,
                           'ordinal', ordinal) ORDER BY ordinal), '[]'::jsonb)))
                   FROM mra.exploratory_backtest_fold
                   WHERE exploratory_backtest_run_id = %s),
                  (SELECT count(*) FROM mra.exploratory_backtest_fold_session
                   WHERE exploratory_backtest_run_id = %s),
                  (SELECT count(*) FROM mra.exploratory_backtest_cost_assumption
                   WHERE exploratory_backtest_run_id = %s),
                  (SELECT mra.canonical_sha256(mra.canonical_json_text(coalesce(jsonb_agg(
                       jsonb_build_object('content_sha256', content_sha256,
                           'exploratory_backtest_cost_assumption_id', exploratory_backtest_cost_assumption_id,
                           'ordinal', ordinal) ORDER BY ordinal), '[]'::jsonb)))
                   FROM mra.exploratory_backtest_cost_assumption
                   WHERE exploratory_backtest_run_id = %s)
                """,
                (exploratory_backtest_run_id,) * 9,
            ).fetchone()
            assert actual is not None
            mismatches: list[str] = []
            labels = (
                "FEATURE_COUNT",
                "FEATURE_ROSTER",
                "ARM_COUNT",
                "ARM_ROSTER",
                "FOLD_COUNT",
                "FOLD_ROSTER",
                "SESSION_COUNT",
                "COST_COUNT",
                "COST_ROSTER",
            )
            for label, expected, observed in zip(
                labels,
                root[:9],
                actual,
                strict=True,
            ):
                if expected != observed:
                    mismatches.append(label)
            integrity = connection.execute(
                """
                SELECT
                  (SELECT array_agg(arm_kind ORDER BY ordinal)
                   FROM mra.exploratory_backtest_arm
                   WHERE exploratory_backtest_run_id = root.exploratory_backtest_run_id)
                    = ARRAY['RULE_BASELINE', 'MODEL_CHALLENGER']::text[],
                  NOT EXISTS (
                    SELECT 1 FROM mra.exploratory_backtest_fold AS fold
                    LEFT JOIN mra.evaluation_protocol AS protocol
                      ON protocol.evaluation_protocol_id = fold.evaluation_protocol_id
                     AND protocol.content_sha256 = fold.evaluation_protocol_sha256
                     AND protocol.target_definition_id = root.target_definition_id
                     AND protocol.applicable_purpose = fold.purpose
                    WHERE fold.exploratory_backtest_run_id = root.exploratory_backtest_run_id
                      AND protocol.evaluation_protocol_id IS NULL
                  ),
                  NOT EXISTS (
                    SELECT 1 FROM mra.exploratory_backtest_fold_session AS member
                    JOIN mra.exploratory_backtest_fold AS fold
                      ON fold.exploratory_backtest_fold_id = member.exploratory_backtest_fold_id
                    LEFT JOIN mra.trading_session AS session
                      ON session.session_id = member.trading_session_id
                     AND session.session_date = member.session_date
                     AND session.exchange = fold.exchange_code
                    WHERE member.exploratory_backtest_run_id = root.exploratory_backtest_run_id
                      AND session.session_id IS NULL
                  ),
                  EXISTS (
                    SELECT 1 FROM mra.command_receipt AS receipt
                    JOIN mra.audit_event AS audit ON audit.command_receipt_id = receipt.receipt_id
                    WHERE receipt.command_kind = 'REGISTER_EXPLORATORY_BACKTEST_RUN'
                      AND receipt.scope_id = root.run_code || ':' || root.generation::text
                      AND receipt.request_hash = root.request_sha256
                      AND receipt.status = 'SUCCEEDED'
                      AND receipt.result_aggregate_id = root.exploratory_backtest_run_id::text
                      AND audit.aggregate_kind = 'EXPLORATORY_BACKTEST_RUN'
                      AND audit.aggregate_id = root.exploratory_backtest_run_id::text
                  )
                FROM mra.exploratory_backtest_run AS root
                WHERE root.exploratory_backtest_run_id = %s
                """,
                (exploratory_backtest_run_id,),
            ).fetchone()
            assert integrity is not None
            for label, valid in zip(
                ("ARM_SEMANTICS", "PROTOCOL_BINDINGS", "SESSION_BINDINGS", "RECEIPT_AUDIT"),
                integrity,
                strict=True,
            ):
                if valid is not True:
                    mismatches.append(label)
        return ExploratoryBacktestVerification(
            exploratory_backtest_run_id,
            not mismatches,
            tuple(mismatches),
        )


__all__ = ["PostgresExploratoryBacktestVerificationPort"]
