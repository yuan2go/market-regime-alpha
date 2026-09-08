"""Evaluation reads one explicit published model use, without a Backtest arm."""

from typing import Any
from uuid import UUID

import psycopg

from market_regime_alpha.research_qualification.domain.evaluation import ProtocolMetricDefinition


def experimental_metric_sources(
    connection: psycopg.Connection[Any], evaluation_run_id: UUID, metric: ProtocolMetricDefinition
) -> list[tuple[Any, ...]]:
    return connection.execute(
        """
        SELECT observation.evaluation_observation_id, observation.research_partition_member_id,
               observation.market_target_outcome_revision_id, observation.candidate_disposition,
               outcome.market_target_outcome_metric_id, outcome.value_status, outcome.decimal_value,
               outcome.boolean_value, commitment.commitment_id, commitment.decision_run_id,
               commitment.candidate_id, commitment.instrument_id, commitment.decision_time,
               NULL, NULL, NULL, NULL, NULL, forecast.strategy_version_id,
               NULL, NULL, NULL, NULL, NULL,
               signal.signal_id, signal.status, forecast.forecast_id, forecast.status,
               estimate.forecast_estimate_id, estimate.point_estimate,
               NULL, NULL, NULL, NULL, NULL, NULL,
               outcome.value_type, candidate.composite_score, candidate.competition_rank, candidate.candidate_set_id,
               revision.knowledge_cutoff, NULL, NULL, gaps.has_source_gap, gaps.has_missing_gap, binding.experimental_model_use_id
        FROM mra.evaluation_observation observation
        JOIN mra.research_partition_member member USING (research_partition_member_id)
        JOIN mra.decision_target_commitment commitment ON commitment.commitment_id=member.commitment_id
        JOIN mra.candidate candidate ON candidate.candidate_id=commitment.candidate_id AND candidate.instrument_id=commitment.instrument_id
        JOIN mra.market_target_outcome_metric outcome ON outcome.market_target_outcome_revision_id=observation.market_target_outcome_revision_id
          AND outcome.target_metric_definition_id=%s
        JOIN mra.market_target_outcome_revision revision ON revision.market_target_outcome_revision_id=observation.market_target_outcome_revision_id
        LEFT JOIN LATERAL (
            SELECT coalesce(bool_or(source.source_gap_id IS NOT NULL), false) AS has_source_gap,
                   coalesce(bool_or(source.source_gap_id IS NOT NULL AND source.source_gap_kind='MISSING'), false) AS has_missing_gap
            FROM mra.market_target_outcome_metric_observation dependency
            JOIN mra.market_target_outcome_observation point ON point.market_target_outcome_observation_id=dependency.market_target_outcome_observation_id
            JOIN mra.market_target_outcome_source source ON source.market_target_outcome_source_id=point.market_target_outcome_source_id
            WHERE dependency.market_target_outcome_metric_id=outcome.market_target_outcome_metric_id
              AND dependency.market_target_outcome_revision_id=revision.market_target_outcome_revision_id
        ) gaps ON true
        LEFT JOIN mra.forecast_model_binding binding ON binding.decision_run_id=commitment.decision_run_id
          AND binding.commitment_id=commitment.commitment_id AND binding.experimental_model_use_id=%s
        JOIN mra.experimental_model_use usage ON usage.experimental_model_use_id=%s
        LEFT JOIN mra.forecast forecast ON forecast.commitment_id=commitment.commitment_id
          AND forecast.target_definition_id=commitment.target_definition_id
          AND ((%s='MODEL' AND forecast.forecast_id=binding.forecast_id)
            OR (%s='RULE_BASELINE' AND forecast.strategy_version_id=usage.baseline_strategy_version_id
              AND forecast.recorded_at<=binding.forecast_recorded_at))
        LEFT JOIN mra.forecast_estimate estimate ON estimate.forecast_id=forecast.forecast_id AND estimate.target_metric_definition_id=outcome.target_metric_definition_id
        LEFT JOIN mra.signal signal ON signal.signal_id=forecast.signal_id
        WHERE observation.evaluation_run_id=%s
        ORDER BY commitment.decision_time, commitment.instrument_id, observation.research_partition_member_id
        """,
        (
            metric.source_target_metric_definition_id,
            metric.experimental_model_use_id,
            metric.experimental_model_use_id,
            metric.experimental_forecast_role,
            metric.experimental_forecast_role,
            evaluation_run_id,
        ),
    ).fetchall()
