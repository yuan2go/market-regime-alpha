"""Exact writer-owned metric fields; no financial calculation or new identity."""

from decimal import Decimal
from typing import NamedTuple
from uuid import UUID

from market_regime_alpha.research_qualification.domain.evaluation_computation import ComputedEvaluationMetric


class EvaluationMetricRecord(NamedTuple):
    evaluation_metric_id: UUID
    evaluation_run_id: UUID
    evaluation_protocol_metric_id: UUID
    evaluation_protocol_id: UUID
    metric_state: str
    decimal_value: Decimal | None
    boolean_value: bool | None
    estimable_count: int
    acceptance_state: str
    reason_code: str | None
    content_sha256: str

    @classmethod
    def from_computation(
        cls, metric_id: UUID, run_id: UUID, protocol_id: UUID, computation: ComputedEvaluationMetric
    ) -> "EvaluationMetricRecord":
        result = computation.result
        return cls(
            metric_id,
            run_id,
            computation.inputs.metric.evaluation_protocol_metric_id,
            protocol_id,
            result.state.value,
            result.decimal_value,
            result.boolean_value,
            result.estimable_count,
            result.acceptance_state.value,
            computation.reason_code,
            computation.result_sha256,
        )
