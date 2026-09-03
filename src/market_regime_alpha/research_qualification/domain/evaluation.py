"""Frozen Evaluation Protocol semantics and pure V1 reducers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
import re
from statistics import median
from uuid import UUID

from market_regime_alpha.research_qualification.domain.model import ArtifactBinding
from market_regime_alpha.research_qualification.domain.evaluation_formula import (
    EvaluationFormulaDefinition,
)
from market_regime_alpha.research_qualification.domain.research_vocabulary import PartitionPurpose
from market_regime_alpha.research_qualification.domain.research_vocabulary import (
    AcceptanceOperator,
    AcceptanceState,
    CandidateDisposition,
    EvaluationInclusionPolicy,
    EvaluationInputState,
    EvaluationMetricState,
    EvaluationMissingnessPolicy,
    EvaluationReducer,
    EvaluationRunStatus,
    EvaluationSourceKind,
    EvaluationSourceMeasure,
    EvaluationSliceKind,
    ExploratoryBacktestArmKind,
    MetricDirection,
    SourceMetricValueType,
)
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.identity import ContentHash


_CODE = re.compile(r"^[a-z][a-z0-9_-]{0,99}$")


@dataclass(frozen=True, slots=True)
class EvaluationProtocolPlan:
    evaluation_protocol_id: UUID
    protocol_code: str
    protocol_version: int
    target_definition_id: UUID
    target_version: int
    target_definition_sha256: ContentHash | str
    applicable_purpose: PartitionPurpose
    decision_rule: str
    metrics: tuple[ProtocolMetricDefinition, ...]
    code_artifact: ArtifactBinding
    config_artifact: ArtifactBinding
    provenance_sha256: ContentHash | str
    metric_roster_sha256: ContentHash = field(init=False)
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        if not _CODE.fullmatch(self.protocol_code):
            raise ValueError("protocol_code has an invalid format")
        if not self.decision_rule.strip():
            raise ValueError("decision_rule is required")
        if isinstance(self.protocol_version, bool) or self.protocol_version < 1:
            raise ValueError("protocol_version must be positive")
        if isinstance(self.target_version, bool) or self.target_version < 1:
            raise ValueError("target_version must be positive")
        if not self.metrics:
            raise ValueError("EvaluationProtocol requires metrics")
        if tuple(item.ordinal for item in self.metrics) != tuple(range(1, len(self.metrics) + 1)):
            raise ValueError("Protocol metric ordinals must be contiguous")
        if len({item.metric_code for item in self.metrics}) != len(self.metrics):
            raise ValueError("Protocol metric codes must be unique")
        target_hash = ContentHash(str(self.target_definition_sha256))
        provenance_hash = ContentHash(str(self.provenance_sha256))
        roster_hash = ContentHash(canonical_json_sha256(self.metrics))
        object.__setattr__(self, "target_definition_sha256", target_hash)
        object.__setattr__(self, "provenance_sha256", provenance_hash)
        object.__setattr__(self, "metric_roster_sha256", roster_hash)
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(
                canonical_json_sha256(
                    {
                        "applicable_purpose": self.applicable_purpose,
                        "code_artifact": self.code_artifact,
                        "config_artifact": self.config_artifact,
                        "decision_rule": self.decision_rule,
                        "metric_roster_sha256": roster_hash,
                        "protocol_code": self.protocol_code,
                        "protocol_version": self.protocol_version,
                        "provenance_sha256": provenance_hash,
                        "target_definition_id": self.target_definition_id,
                        "target_definition_sha256": target_hash,
                        "target_version": self.target_version,
                    }
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class EvaluationRunPlan:
    evaluation_run_id: UUID
    experiment_run_id: UUID
    evaluation_protocol_id: UUID
    requested_knowledge_cutoff: datetime
    request_identity: str
    code_artifact: ArtifactBinding
    config_artifact: ArtifactBinding
    provenance_sha256: ContentHash | str
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        if not self.request_identity.strip():
            raise ValueError("request_identity is required")
        provenance_hash = ContentHash(str(self.provenance_sha256))
        object.__setattr__(self, "provenance_sha256", provenance_hash)
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(
                canonical_json_sha256(
                    {
                        "code_artifact": self.code_artifact,
                        "config_artifact": self.config_artifact,
                        "evaluation_protocol_id": self.evaluation_protocol_id,
                        "evaluation_run_id": self.evaluation_run_id,
                        "experiment_run_id": self.experiment_run_id,
                        "provenance_sha256": provenance_hash,
                        "request_identity": self.request_identity,
                        "requested_knowledge_cutoff": self.requested_knowledge_cutoff,
                    }
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class ProtocolMetricDefinition:
    evaluation_protocol_metric_id: UUID
    metric_code: str
    ordinal: int
    source_target_metric_definition_id: UUID
    source_metric_code: str
    source_value_type: SourceMetricValueType
    reducer: EvaluationReducer
    slice_kind: EvaluationSliceKind
    candidate_disposition: CandidateDisposition | None
    direction: MetricDirection
    minimum_estimable_count: int
    acceptance_operator: AcceptanceOperator
    acceptance_threshold: Decimal | None
    backtest_arm_kind: ExploratoryBacktestArmKind | None = None
    inclusion_policy: EvaluationInclusionPolicy = EvaluationInclusionPolicy.COMPLETE_ONLY
    missingness_policy: EvaluationMissingnessPolicy = EvaluationMissingnessPolicy.RETAIN_AND_ESTIMATE
    source_kind: EvaluationSourceKind = EvaluationSourceKind.OUTCOME_METRIC
    source_measure: EvaluationSourceMeasure = EvaluationSourceMeasure.TARGET_VALUE
    formula: EvaluationFormulaDefinition | None = None
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        if not _CODE.fullmatch(self.metric_code) or not _CODE.fullmatch(
            self.source_metric_code
        ):
            raise ValueError("metric_code has an invalid format")
        if isinstance(self.ordinal, bool) or self.ordinal < 1:
            raise ValueError("ordinal must be positive")
        if (
            isinstance(self.minimum_estimable_count, bool)
            or self.minimum_estimable_count < 1
        ):
            raise ValueError("minimum_estimable_count must be positive")
        compatible = {
            EvaluationReducer.MEAN_DECIMAL: SourceMetricValueType.DECIMAL,
            EvaluationReducer.MEDIAN_DECIMAL: SourceMetricValueType.DECIMAL,
            EvaluationReducer.TRUE_RATE: SourceMetricValueType.BOOLEAN,
            EvaluationReducer.SUM_DECIMAL: SourceMetricValueType.DECIMAL,
            EvaluationReducer.ABSOLUTE_MEAN_DECIMAL: SourceMetricValueType.DECIMAL,
            EvaluationReducer.SPEARMAN_RANK_CORRELATION: SourceMetricValueType.DECIMAL,
            EvaluationReducer.MAX_DRAWDOWN: SourceMetricValueType.DECIMAL,
            EvaluationReducer.TOP_BOTTOM_SPREAD: SourceMetricValueType.DECIMAL,
        }
        required = compatible.get(self.reducer)
        if required is not None and self.source_value_type is not required:
            raise ValueError("reducer is incompatible with source metric value type")
        source_measures = {
            EvaluationSourceKind.OUTCOME_METRIC: {
                EvaluationSourceMeasure.TARGET_VALUE,
            },
            EvaluationSourceKind.FORECAST_OUTCOME_PAIR: {
                EvaluationSourceMeasure.FORECAST_POINT_VS_TARGET,
            },
            EvaluationSourceKind.CANDIDATE_DISPOSITION: {
                EvaluationSourceMeasure.CANDIDATE_SELECTED,
            },
            EvaluationSourceKind.SIGNAL_STATUS: {
                EvaluationSourceMeasure.SIGNAL_PRESENT,
            },
            EvaluationSourceKind.PORTFOLIO_LINE: {
                EvaluationSourceMeasure.TARGET_WEIGHT,
                EvaluationSourceMeasure.TURNOVER,
            },
            EvaluationSourceKind.PORTFOLIO_OUTCOME: {
                EvaluationSourceMeasure.GROSS_PORTFOLIO_RETURN,
                EvaluationSourceMeasure.NET_PORTFOLIO_RETURN_ASSUMED_COST,
            },
            EvaluationSourceKind.RISK_DECISION: {
                EvaluationSourceMeasure.RISK_REJECTED,
            },
            EvaluationSourceKind.CANDIDATE_OUTCOME_PAIR: {
                EvaluationSourceMeasure.CANDIDATE_SCORE_VS_TARGET,
                EvaluationSourceMeasure.CANDIDATE_TOP_K_RETURN,
                EvaluationSourceMeasure.CANDIDATE_HIT,
            },
        }
        if self.source_measure not in source_measures[self.source_kind]:
            raise ValueError("source measure is incompatible with source kind")
        source_types = {
            EvaluationSourceKind.FORECAST_OUTCOME_PAIR: SourceMetricValueType.DECIMAL,
            EvaluationSourceKind.CANDIDATE_DISPOSITION: SourceMetricValueType.BOOLEAN,
            EvaluationSourceKind.SIGNAL_STATUS: SourceMetricValueType.BOOLEAN,
            EvaluationSourceKind.PORTFOLIO_LINE: SourceMetricValueType.DECIMAL,
            EvaluationSourceKind.PORTFOLIO_OUTCOME: SourceMetricValueType.DECIMAL,
            EvaluationSourceKind.RISK_DECISION: SourceMetricValueType.BOOLEAN,
        }
        measure_types = {
            EvaluationSourceMeasure.CANDIDATE_SCORE_VS_TARGET: SourceMetricValueType.DECIMAL,
            EvaluationSourceMeasure.CANDIDATE_TOP_K_RETURN: SourceMetricValueType.DECIMAL,
            EvaluationSourceMeasure.CANDIDATE_HIT: SourceMetricValueType.BOOLEAN,
        }
        source_type = source_types.get(self.source_kind)
        source_type = measure_types.get(self.source_measure, source_type)
        if source_type is not None and self.source_value_type is not source_type:
            raise ValueError("source kind is incompatible with source metric value type")
        if (
            self.reducer is EvaluationReducer.SPEARMAN_RANK_CORRELATION
            and self.source_kind not in {
                EvaluationSourceKind.FORECAST_OUTCOME_PAIR,
                EvaluationSourceKind.CANDIDATE_OUTCOME_PAIR,
            }
        ):
            raise ValueError("rank correlation requires FORECAST_OUTCOME_PAIR")
        if (
            self.source_kind in {
                EvaluationSourceKind.FORECAST_OUTCOME_PAIR,
                EvaluationSourceKind.CANDIDATE_OUTCOME_PAIR,
            }
            and self.reducer
            not in {
                EvaluationReducer.SPEARMAN_RANK_CORRELATION,
                EvaluationReducer.ESTIMABLE_RATE,
                EvaluationReducer.TOP_BOTTOM_SPREAD,
                EvaluationReducer.MEAN_DECIMAL,
                EvaluationReducer.TRUE_RATE,
            }
        ):
            raise ValueError("Forecast/Outcome pair reducer is incompatible")
        candidate_reducers = {
            EvaluationSourceMeasure.CANDIDATE_SCORE_VS_TARGET: {
                EvaluationReducer.SPEARMAN_RANK_CORRELATION,
                EvaluationReducer.TOP_BOTTOM_SPREAD,
                EvaluationReducer.ESTIMABLE_RATE,
            },
            EvaluationSourceMeasure.CANDIDATE_TOP_K_RETURN: {
                EvaluationReducer.MEAN_DECIMAL,
                EvaluationReducer.MEDIAN_DECIMAL,
                EvaluationReducer.ESTIMABLE_RATE,
            },
            EvaluationSourceMeasure.CANDIDATE_HIT: {
                EvaluationReducer.TRUE_RATE,
                EvaluationReducer.ESTIMABLE_RATE,
            },
        }
        if (
            self.source_kind is EvaluationSourceKind.CANDIDATE_OUTCOME_PAIR
            and self.reducer not in candidate_reducers[self.source_measure]
        ):
            raise ValueError("Candidate/Outcome measure reducer is incompatible")
        if (
            self.reducer is EvaluationReducer.MAX_DRAWDOWN
            and self.source_measure
            not in {
                EvaluationSourceMeasure.GROSS_PORTFOLIO_RETURN,
                EvaluationSourceMeasure.NET_PORTFOLIO_RETURN_ASSUMED_COST,
            }
        ):
            raise ValueError("maximum drawdown requires portfolio return inputs")
        if self.slice_kind is EvaluationSliceKind.CANDIDATE_DISPOSITION:
            if self.candidate_disposition is None:
                raise ValueError("candidate_disposition is required for this slice")
            if self.backtest_arm_kind is not None:
                raise ValueError("backtest arm is forbidden for candidate slice")
        elif self.slice_kind is EvaluationSliceKind.EXPLORATORY_BACKTEST_ARM:
            if self.backtest_arm_kind is None:
                raise ValueError("backtest_arm_kind is required for this slice")
            if self.candidate_disposition is not None:
                raise ValueError("candidate disposition is forbidden for arm slice")
        elif self.candidate_disposition is not None:
            raise ValueError("candidate_disposition is forbidden for ALL_MEMBERS")
        elif self.backtest_arm_kind is not None:
            raise ValueError("backtest_arm_kind is forbidden for ALL_MEMBERS")
        if self.acceptance_operator is AcceptanceOperator.NONE:
            if self.acceptance_threshold is not None:
                raise ValueError("descriptive metric cannot have acceptance threshold")
        elif self.acceptance_threshold is None:
            raise ValueError("acceptance threshold is required")
        if self.direction is MetricDirection.DESCRIPTIVE and self.acceptance_operator is not AcceptanceOperator.NONE:
            raise ValueError("descriptive direction requires NONE acceptance")
        if (
            self.formula is not None
            and self.formula.evaluation_protocol_metric_id
            != self.evaluation_protocol_metric_id
        ):
            raise ValueError("formula does not belong to this Protocol metric")
        content = {
            "acceptance_operator": self.acceptance_operator,
            "acceptance_threshold": self.acceptance_threshold,
            "backtest_arm_kind": self.backtest_arm_kind,
            "candidate_disposition": self.candidate_disposition,
            "direction": self.direction,
            "inclusion_policy": self.inclusion_policy,
            "metric_code": self.metric_code,
            "minimum_estimable_count": self.minimum_estimable_count,
            "missingness_policy": self.missingness_policy,
            "ordinal": self.ordinal,
            "reducer": self.reducer,
            "slice_kind": self.slice_kind,
            "source_metric_code": self.source_metric_code,
            "source_kind": self.source_kind,
            "source_measure": self.source_measure,
            "source_target_metric_definition_id": self.source_target_metric_definition_id,
            "source_value_type": self.source_value_type,
        }
        # Absence intentionally preserves every historical metric byte/hash.
        if self.formula is not None:
            content["formula_content_sha256"] = str(self.formula.content_sha256)
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(canonical_json_sha256(content)),
        )


@dataclass(frozen=True, slots=True)
class EvaluationInput:
    evaluation_observation_id: UUID
    candidate_disposition: CandidateDisposition
    source_value_status: str
    decimal_value: Decimal | None
    boolean_value: bool | None
    secondary_decimal_value: Decimal | None = None
    backtest_arm_kind: ExploratoryBacktestArmKind | None = None
    group_key: str | None = None


@dataclass(frozen=True, slots=True)
class EvaluationMetricObservationResult:
    evaluation_observation_id: UUID
    state: EvaluationInputState
    reason_code: str


@dataclass(frozen=True, slots=True)
class EvaluationMetricResult:
    state: EvaluationMetricState
    decimal_value: Decimal | None
    boolean_value: bool | None
    estimable_count: int
    acceptance_state: AcceptanceState
    observations: tuple[EvaluationMetricObservationResult, ...]


def transition_evaluation_run(
    current: EvaluationRunStatus,
    target: EvaluationRunStatus,
) -> EvaluationRunStatus:
    allowed = {
        EvaluationRunStatus.OPEN: {
            EvaluationRunStatus.INPUTS_ACQUIRED,
            EvaluationRunStatus.FAILED,
        },
        EvaluationRunStatus.INPUTS_ACQUIRED: {
            EvaluationRunStatus.COMPLETED,
            EvaluationRunStatus.FAILED,
        },
        EvaluationRunStatus.COMPLETED: set(),
        EvaluationRunStatus.FAILED: set(),
    }
    if target not in allowed[current]:
        raise ValueError(f"EvaluationRun transition {current} -> {target} is forbidden")
    return target


def evaluate_metric(
    metric: ProtocolMetricDefinition,
    inputs: tuple[EvaluationInput, ...],
) -> EvaluationMetricResult:
    observations: list[EvaluationMetricObservationResult] = []
    included: list[EvaluationInput] = []
    for item in inputs:
        if (
            metric.slice_kind is EvaluationSliceKind.CANDIDATE_DISPOSITION
            and item.candidate_disposition is not metric.candidate_disposition
        ):
            observations.append(
                EvaluationMetricObservationResult(
                    item.evaluation_observation_id,
                    EvaluationInputState.EXCLUDED,
                    "OUTSIDE_DECLARED_SLICE",
                )
            )
            continue
        if (
            metric.slice_kind is EvaluationSliceKind.EXPLORATORY_BACKTEST_ARM
            and item.backtest_arm_kind is not metric.backtest_arm_kind
        ):
            observations.append(
                EvaluationMetricObservationResult(
                    item.evaluation_observation_id,
                    EvaluationInputState.EXCLUDED,
                    "OUTSIDE_DECLARED_BACKTEST_ARM",
                )
            )
            continue
        requires_pair = (
            metric.source_kind is EvaluationSourceKind.FORECAST_OUTCOME_PAIR
            or (
                metric.source_kind is EvaluationSourceKind.CANDIDATE_OUTCOME_PAIR
                and metric.source_measure
                is EvaluationSourceMeasure.CANDIDATE_SCORE_VS_TARGET
            )
        )
        has_value = (
            item.decimal_value is not None
            and (not requires_pair or item.secondary_decimal_value is not None)
            if metric.source_value_type is SourceMetricValueType.DECIMAL
            else item.boolean_value is not None
        )
        allowed_status = item.source_value_status == "COMPLETE" or (
            metric.inclusion_policy is EvaluationInclusionPolicy.AVAILABLE_VALUE
            and item.source_value_status == "PARTIAL"
        )
        if not has_value or not allowed_status:
            observations.append(
                EvaluationMetricObservationResult(
                    item.evaluation_observation_id,
                    EvaluationInputState.NOT_ESTIMABLE,
                    f"SOURCE_{item.source_value_status}",
                )
            )
            continue
        included.append(item)
        observations.append(
            EvaluationMetricObservationResult(
                item.evaluation_observation_id,
                EvaluationInputState.INCLUDED,
                "INCLUDED_BY_PROTOCOL",
            )
        )
    complete_required = (
        metric.missingness_policy is EvaluationMissingnessPolicy.REQUIRE_COMPLETE_ROSTER
        and any(item.state is EvaluationInputState.NOT_ESTIMABLE for item in observations)
    )
    if len(included) < metric.minimum_estimable_count or complete_required:
        return EvaluationMetricResult(
            EvaluationMetricState.NOT_ESTIMABLE,
            None,
            None,
            len(included),
            AcceptanceState.NOT_ESTIMABLE,
            tuple(observations),
        )
    values: list[Decimal]
    if metric.reducer is EvaluationReducer.MEAN_DECIMAL:
        values = [item.decimal_value for item in included if item.decimal_value is not None]
        value = sum(values, Decimal(0)) / Decimal(len(values))
    elif metric.reducer is EvaluationReducer.MEDIAN_DECIMAL:
        values = [item.decimal_value for item in included if item.decimal_value is not None]
        value = median(values)
    elif metric.reducer is EvaluationReducer.TRUE_RATE:
        value = Decimal(sum(item.boolean_value is True for item in included)) / Decimal(len(included))
    elif metric.reducer is EvaluationReducer.SUM_DECIMAL:
        values = [item.decimal_value for item in included if item.decimal_value is not None]
        value = sum(values, Decimal(0))
    elif metric.reducer is EvaluationReducer.ABSOLUTE_MEAN_DECIMAL:
        values = [abs(item.decimal_value) for item in included if item.decimal_value is not None]
        value = sum(values, Decimal(0)) / Decimal(len(values))
    elif metric.reducer is EvaluationReducer.SPEARMAN_RANK_CORRELATION:
        grouped: dict[str, list[EvaluationInput]] = {}
        for item in included:
            grouped.setdefault(item.group_key or "ALL", []).append(item)
        correlations: list[Decimal] = []
        non_estimable_ids: set[UUID] = set()
        for members in grouped.values():
            pairs = [
                (item.decimal_value, item.secondary_decimal_value)
                for item in members
                if item.decimal_value is not None
                and item.secondary_decimal_value is not None
            ]
            correlation = _spearman(pairs)
            if correlation is None:
                non_estimable_ids.update(item.evaluation_observation_id for item in members)
            else:
                correlations.append(correlation)
        if non_estimable_ids:
            observations = [
                EvaluationMetricObservationResult(
                    item.evaluation_observation_id,
                    EvaluationInputState.NOT_ESTIMABLE,
                    "GROUP_RANK_NOT_ESTIMABLE",
                )
                if item.evaluation_observation_id in non_estimable_ids
                else item
                for item in observations
            ]
            included = [
                item
                for item in included
                if item.evaluation_observation_id not in non_estimable_ids
            ]
        if not correlations or len(included) < metric.minimum_estimable_count:
            return EvaluationMetricResult(
                EvaluationMetricState.NOT_ESTIMABLE,
                None,
                None,
                len(included),
                AcceptanceState.NOT_ESTIMABLE,
                tuple(observations),
            )
        value = sum(correlations, Decimal(0)) / Decimal(len(correlations))
    elif metric.reducer is EvaluationReducer.MAX_DRAWDOWN:
        grouped_values: dict[str, Decimal] = {}
        for item in included:
            assert item.decimal_value is not None
            key = item.group_key or str(item.evaluation_observation_id)
            grouped_values[key] = grouped_values.get(key, Decimal(0)) + item.decimal_value
        values = list(grouped_values.values())
        equity = Decimal(1)
        peak = equity
        value = Decimal(0)
        for period_return in values:
            equity *= Decimal(1) + period_return
            peak = max(peak, equity)
            if peak > 0:
                value = max(value, (peak - equity) / peak)
    elif metric.reducer is EvaluationReducer.TOP_BOTTOM_SPREAD:
        grouped: dict[str, list[EvaluationInput]] = {}
        for item in included:
            grouped.setdefault(item.group_key or "ALL", []).append(item)
        spreads: list[Decimal] = []
        for members in grouped.values():
            ranked = sorted(
                (
                    (item.decimal_value, item.secondary_decimal_value)
                    for item in members
                    if item.decimal_value is not None
                    and item.secondary_decimal_value is not None
                ),
                key=lambda item: item[0],
            )
            if len(ranked) < 2:
                continue
            width = max(1, len(ranked) // 5)
            low = sum((item[1] for item in ranked[:width]), Decimal(0)) / Decimal(width)
            high = sum((item[1] for item in ranked[-width:]), Decimal(0)) / Decimal(width)
            spreads.append(high - low)
        if not spreads:
            return EvaluationMetricResult(
                EvaluationMetricState.NOT_ESTIMABLE,
                None,
                None,
                0,
                AcceptanceState.NOT_ESTIMABLE,
                tuple(observations),
            )
        value = sum(spreads, Decimal(0)) / Decimal(len(spreads))
    else:
        eligible_count = sum(
            item.state is not EvaluationInputState.EXCLUDED for item in observations
        )
        value = Decimal(len(included)) / Decimal(eligible_count) if eligible_count else Decimal(0)
    acceptance = _acceptance(metric, value)
    return EvaluationMetricResult(
        EvaluationMetricState.ESTIMATED,
        value,
        None,
        len(included),
        acceptance,
        tuple(observations),
    )


def _acceptance(metric: ProtocolMetricDefinition, value: Decimal) -> AcceptanceState:
    if metric.acceptance_operator is AcceptanceOperator.NONE:
        return AcceptanceState.NOT_APPLICABLE
    threshold = metric.acceptance_threshold
    assert threshold is not None
    accepted = value >= threshold if metric.acceptance_operator is AcceptanceOperator.AT_LEAST else value <= threshold
    return AcceptanceState.ACCEPTED if accepted else AcceptanceState.REJECTED


def _spearman(
    pairs: list[tuple[Decimal, Decimal]],
) -> Decimal | None:
    if len(pairs) < 2:
        return None
    left = _average_ranks([item[0] for item in pairs])
    right = _average_ranks([item[1] for item in pairs])
    left_mean = sum(left, Decimal(0)) / Decimal(len(left))
    right_mean = sum(right, Decimal(0)) / Decimal(len(right))
    numerator = sum(
        (x - left_mean) * (y - right_mean)
        for x, y in zip(left, right, strict=True)
    )
    left_sum = sum(((item - left_mean) ** 2 for item in left), Decimal(0))
    right_sum = sum(((item - right_mean) ** 2 for item in right), Decimal(0))
    denominator = (left_sum * right_sum).sqrt()
    return None if denominator == 0 else numerator / denominator


def _average_ranks(values: list[Decimal]) -> list[Decimal]:
    ordered = sorted(enumerate(values), key=lambda item: (item[1], item[0]))
    ranks = [Decimal(0)] * len(values)
    cursor = 0
    while cursor < len(ordered):
        end = cursor + 1
        while end < len(ordered) and ordered[end][1] == ordered[cursor][1]:
            end += 1
        rank = (Decimal(cursor + 1) + Decimal(end)) / Decimal(2)
        for index, _ in ordered[cursor:end]:
            ranks[index] = rank
        cursor = end
    return ranks


__all__ = [
    "EvaluationInput",
    "EvaluationMetricObservationResult",
    "EvaluationMetricResult",
    "ProtocolMetricDefinition",
    "EvaluationProtocolPlan",
    "EvaluationRunPlan",
    "evaluate_metric",
    "transition_evaluation_run",
]
