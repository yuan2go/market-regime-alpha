"""Exact complete Validation parent; never infer a path from acquired subsets."""

from datetime import date
from typing import Any
from uuid import UUID

import psycopg

from market_regime_alpha.research_qualification.errors import EvaluationReconciliationError


def require_episode_parent(
    connection: psycopg.Connection[Any], evaluation_id: UUID, sources: list[tuple[Any, ...]]
) -> tuple[tuple[UUID, date], ...]:
    scope = connection.execute(
        """SELECT p.source_backtest_run_id, p.source_backtest_arm_id,
                  p.source_backtest_sha256, p.target_definition_id,
                  p.source_backtest_fold_id, p.source_context_kind,
                  p.source_context_state, p.purpose
           FROM mra.evaluation_run e JOIN mra.research_partition p USING (research_partition_id)
           WHERE e.evaluation_run_id = %s""",
        (evaluation_id,),
    ).fetchone()
    if (
        scope is None
        or any(value is None for value in scope[:4])
        or any(value is not None for value in scope[4:7])
        or scope[7] != "VALIDATION"
        or not sources
        or {(row[13], row[14]) for row in sources} != {(scope[0], scope[1])}
    ):
        raise EvaluationReconciliationError("V2 requires one unfiltered complete Validation parent run/arm")
    slots = connection.execute(
        """SELECT session.exploratory_backtest_fold_session_id, session.session_date,
                  decision.decision_run_id
           FROM mra.backtest_arm_fold binding
           JOIN mra.exploratory_backtest_run run USING (exploratory_backtest_run_id)
           JOIN mra.exploratory_backtest_fold fold USING (exploratory_backtest_fold_id, exploratory_backtest_run_id)
           JOIN mra.exploratory_backtest_fold_session session USING (exploratory_backtest_fold_id, exploratory_backtest_run_id)
           LEFT JOIN mra.exploratory_retrospective_decision_run decision
             ON decision.exploratory_backtest_run_id = binding.exploratory_backtest_run_id
            AND decision.exploratory_backtest_arm_id = binding.exploratory_backtest_arm_id
            AND decision.exploratory_backtest_fold_session_id = session.exploratory_backtest_fold_session_id
           WHERE binding.exploratory_backtest_run_id = %s
             AND binding.exploratory_backtest_arm_id = %s AND binding.specification_sha256 = %s
             AND run.current_specification_sha256 = binding.specification_sha256
             AND fold.purpose = 'VALIDATION' AND session.session_role = 'EVALUATION'
           ORDER BY session.session_date, session.exploratory_backtest_fold_session_id""",
        scope[:3],
    ).fetchall()
    if not slots or any(row[2] is None for row in slots):
        raise EvaluationReconciliationError("complete Validation parent has missing Decision slots")
    commitments = connection.execute(
        """SELECT commitment_id, decision_run_id FROM mra.decision_target_commitment
           WHERE decision_run_id = ANY(%s) AND target_definition_id = %s""",
        ([row[2] for row in slots], scope[3]),
    ).fetchall()
    if (
        not commitments
        or {row[1] for row in commitments} != {row[2] for row in slots}
        or {row[0] for row in commitments} != {row[8] for row in sources}
        or len(commitments) != len(sources)
    ):
        raise EvaluationReconciliationError("Evaluation differs from complete Validation commitment roster")
    costs = connection.execute(
        """SELECT cost.cost_kind, cost.amount_bps FROM mra.exploratory_backtest_cost_assumption cost
           JOIN mra.backtest_arm_specification arm ON arm.exploratory_backtest_run_id = cost.exploratory_backtest_run_id
           WHERE arm.exploratory_backtest_run_id = %s AND arm.exploratory_backtest_arm_id = %s
             AND arm.specification_sha256 = %s
             AND cost.exploratory_backtest_arm_id IS NOT DISTINCT FROM
                 CASE WHEN arm.cost_binding_source = 'ARM_OVERRIDE'
                      THEN arm.exploratory_backtest_arm_id ELSE NULL::uuid END""",
        scope[:3],
    ).fetchall()
    if any(row[0] == "SLIPPAGE_BPS" and row[1] != 0 for row in costs):
        raise EvaluationReconciliationError("V2 does not support nonzero slippage assumptions")
    return tuple((row[0], row[1]) for row in slots)
