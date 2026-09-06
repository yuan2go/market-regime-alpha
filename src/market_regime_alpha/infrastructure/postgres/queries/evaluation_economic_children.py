"""Verify V2 persisted child bytes using the writer's serialization contract."""

from typing import Any
from uuid import UUID, uuid4

import psycopg

from market_regime_alpha.infrastructure.postgres.repositories.research_evaluations import (
    PostgresEvaluationRepository, _metric_observation_values,
    _portfolio_source_values, _portfolio_cost_values,
)
from market_regime_alpha.research_qualification.domain.evaluation_computation import ComputedEvaluationMetric
from market_regime_alpha.research_qualification.domain.research_vocabulary import EvaluationSourceMeasure
from market_regime_alpha.shared.hashing import canonical_json_sha256


def economic_children_match(connection: psycopg.Connection[Any], evaluation_id: UUID,
                            computations: tuple[ComputedEvaluationMetric, ...]) -> bool:
    repository = PostgresEvaluationRepository(connection, id_factory=uuid4)
    costs = {}
    for computation in computations:
        metric = computation.inputs.metric
        rows = connection.execute(
            """SELECT evaluation_metric_observation_id, evaluation_metric_id,
                      evaluation_run_id, evaluation_protocol_metric_id,
                      evaluation_observation_id, research_partition_member_id,
                      market_target_outcome_revision_id, source_outcome_metric_id,
                      source_target_metric_definition_id, source_value_type,
                      source_value_status, input_state, reason_code, content_sha256
               FROM mra.evaluation_metric_observation
               WHERE evaluation_run_id = %s AND evaluation_protocol_metric_id = %s""",
            (evaluation_id, metric.evaluation_protocol_metric_id),
        ).fetchall()
        by_observation = {row[4]: row for row in rows}
        if len(rows) != len(computation.resolved) or set(by_observation) != {item.input.evaluation_observation_id for item in computation.resolved}:
            return False
        classifications = {item.evaluation_observation_id: item for item in computation.result.observations}
        expected_portfolio: list[tuple[Any, ...]] = []
        expected_costs: list[tuple[Any, ...]] = []
        for item in computation.resolved:
            row = by_observation[item.input.evaluation_observation_id]
            if tuple(row) != _metric_observation_values(row[0], row[1], evaluation_id, metric,
                                                       item.source, classifications[row[4]]):
                return False
            values = _portfolio_source_values(item)
            expected_portfolio.append((row[0], evaluation_id, metric.evaluation_protocol_metric_id,
                                       metric.source_measure.value, *values,
                                       canonical_json_sha256({"input": row[0], "measure": metric.source_measure, "source": values})))
            if metric.source_measure is EvaluationSourceMeasure.NET_PORTFOLIO_RETURN_ASSUMED_COST:
                key = item.source[13], item.source[14]
                if key not in costs:
                    costs[key] = repository._effective_cost_rows(*key)
                expected_costs.extend(_portfolio_cost_values(row[0], key[0], cost) for cost in costs[key])
        portfolio = connection.execute(
            """SELECT evaluation_metric_observation_id, evaluation_run_id,
                      evaluation_protocol_metric_id, source_measure,
                      decision_run_id, candidate_id, portfolio_proposal_id, portfolio_line_id,
                      risk_decision_id, line_status, risk_status, proposed_weight, turnover,
                      effective_weight, gross_return, net_return, source_status, cost_count,
                      cost_roster_sha256, content_sha256
               FROM mra.evaluation_portfolio_source
               WHERE evaluation_run_id = %s AND evaluation_protocol_metric_id = %s""",
            (evaluation_id, metric.evaluation_protocol_metric_id),
        ).fetchall()
        persisted_costs = connection.execute(
            """SELECT cost.evaluation_metric_observation_id, exploratory_backtest_cost_assumption_id,
                      exploratory_backtest_run_id, ordinal, cost_kind, amount_bps,
                      evidence_class, assumption_content_sha256, cost.content_sha256
               FROM mra.evaluation_portfolio_cost_source cost
               JOIN mra.evaluation_metric_observation input USING (evaluation_metric_observation_id)
               WHERE input.evaluation_run_id = %s AND input.evaluation_protocol_metric_id = %s""",
            (evaluation_id, metric.evaluation_protocol_metric_id),
        ).fetchall()
        if (set(portfolio) != set(expected_portfolio) or len(portfolio) != len(expected_portfolio)
                or set(persisted_costs) != set(expected_costs) or len(persisted_costs) != len(expected_costs)):
            return False
    return True
