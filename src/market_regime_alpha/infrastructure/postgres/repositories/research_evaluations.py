"""PostgreSQL Evaluation Protocol/Run and pure completion writer."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable
from uuid import UUID

import psycopg

from market_regime_alpha.research_qualification.domain.evaluation import (
    EvaluationInput,
    EvaluationProtocolPlan,
    EvaluationRunPlan,
    ProtocolMetricDefinition,
    evaluate_metric,
)
from market_regime_alpha.research_qualification.domain.research_vocabulary import (
    AcceptanceOperator,
    CandidateDisposition,
    EvaluationInclusionPolicy,
    EvaluationMissingnessPolicy,
    EvaluationReducer,
    EvaluationSourceKind,
    EvaluationSourceMeasure,
    EvaluationSliceKind,
    ExploratoryBacktestArmKind,
    MetricDirection,
    SourceMetricValueType,
)
from market_regime_alpha.research_qualification.errors import (
    EvaluationProtocolError,
    EvaluationReconciliationError,
)
from market_regime_alpha.research_qualification.ports.evaluation_uow import (
    EvaluationCompletionResult,
    EvaluationProtocolRecord,
    EvaluationRunRecord,
)
from market_regime_alpha.runtime.errors import RuntimeNotFoundError, RuntimeStateConflictError
from market_regime_alpha.shared.hashing import canonical_json_sha256


@dataclass(frozen=True, slots=True)
class _ResolvedMetricInput:
    source: tuple[Any, ...]
    input: EvaluationInput
    turnover: Decimal | None = None
    effective_weight: Decimal | None = None
    gross_return: Decimal | None = None
    net_return: Decimal | None = None


class PostgresEvaluationRepository:
    def __init__(self, connection: psycopg.Connection[Any], *, id_factory: Callable[[], UUID]) -> None:
        self._connection = connection
        self._id_factory = id_factory

    def lock_protocol_identity(self, protocol_code: str) -> None:
        self._connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"evaluation-protocol:{protocol_code}",),
        )

    def register_protocol(
        self,
        plan: EvaluationProtocolPlan,
        *,
        request_identity: str,
        request_sha256: str,
    ) -> EvaluationProtocolRecord:
        with self._connection.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO mra.evaluation_protocol_metric (
                    evaluation_protocol_metric_id, evaluation_protocol_id,
                    target_definition_id, ordinal, metric_code,
                    source_target_metric_definition_id, source_metric_code,
                    source_value_type, source_kind, source_measure,
                    reducer, slice_kind, candidate_disposition,
                    backtest_arm_kind, direction, inclusion_policy,
                    missingness_policy, minimum_estimable_count,
                    acceptance_operator, acceptance_threshold, content_sha256
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s
                )
                """,
                (
                    (
                        metric.evaluation_protocol_metric_id,
                        plan.evaluation_protocol_id,
                        plan.target_definition_id,
                        metric.ordinal,
                        metric.metric_code,
                        metric.source_target_metric_definition_id,
                        metric.source_metric_code,
                        metric.source_value_type.value,
                        metric.source_kind.value,
                        metric.source_measure.value,
                        metric.reducer.value,
                        metric.slice_kind.value,
                        metric.candidate_disposition.value if metric.candidate_disposition else None,
                        metric.backtest_arm_kind.value if metric.backtest_arm_kind else None,
                        metric.direction.value,
                        metric.inclusion_policy.value,
                        metric.missingness_policy.value,
                        metric.minimum_estimable_count,
                        metric.acceptance_operator.value,
                        metric.acceptance_threshold,
                        str(metric.content_sha256),
                    )
                    for metric in plan.metrics
                ),
            )
        self._connection.execute(
            """
            INSERT INTO mra.evaluation_protocol (
                evaluation_protocol_id, protocol_code, protocol_version, status,
                target_definition_id, target_version,
                target_definition_sha256, applicable_purpose,
                decision_rule, metric_count, metric_roster_sha256,
                code_artifact_id, code_content_sha256, code_size_bytes,
                config_artifact_id, config_content_sha256, config_size_bytes,
                provenance_sha256, content_sha256,
                request_identity, request_sha256
            ) VALUES (
                %s, %s, %s, 'FROZEN', %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            (
                plan.evaluation_protocol_id, plan.protocol_code, plan.protocol_version,
                plan.target_definition_id, plan.target_version,
                str(plan.target_definition_sha256), plan.applicable_purpose.value,
                plan.decision_rule, len(plan.metrics), str(plan.metric_roster_sha256),
                plan.code_artifact.artifact_id, str(plan.code_artifact.content_sha256),
                plan.code_artifact.size_bytes, plan.config_artifact.artifact_id,
                str(plan.config_artifact.content_sha256), plan.config_artifact.size_bytes,
                str(plan.provenance_sha256), str(plan.content_sha256),
                request_identity, request_sha256,
            ),
        )
        record = self.protocol_record(plan.evaluation_protocol_id, lock=False)
        if not self._protocol_reconciles(record):
            raise EvaluationReconciliationError("EvaluationProtocol metric roster does not reconcile")
        return record

    def open_run(
        self, plan: EvaluationRunPlan, *, request_sha256: str
    ) -> EvaluationRunRecord:
        binding = self._connection.execute(
            """
            SELECT run.experiment_id, run.experiment_partition_id,
                   run.research_partition_id, binding.target_definition_id,
                   binding.partition_purpose, partition.member_count,
                   protocol.metric_count
            FROM mra.experiment_run AS run
            JOIN mra.experiment_partition AS binding
              ON binding.experiment_partition_id = run.experiment_partition_id
            JOIN mra.research_partition AS partition
              ON partition.research_partition_id = run.research_partition_id
            JOIN mra.evaluation_protocol AS protocol
              ON protocol.evaluation_protocol_id = %s
             AND protocol.target_definition_id = binding.target_definition_id
             AND protocol.applicable_purpose = binding.partition_purpose
            WHERE run.experiment_run_id = %s
              AND run.status = 'OPENED'
              AND partition.status = 'FROZEN'
            FOR SHARE OF run, binding, partition, protocol
            """,
            (plan.evaluation_protocol_id, plan.experiment_run_id),
        ).fetchone()
        if binding is None:
            raise EvaluationProtocolError(
                "EvaluationRun requires exact Experiment/Partition/Protocol binding"
            )
        member_count = self._connection.execute(
            "SELECT count(*) FROM mra.research_partition_member WHERE research_partition_id = %s",
            (binding[2],),
        ).fetchone()
        assert member_count is not None
        if int(member_count[0]) != int(binding[5]):
            raise EvaluationReconciliationError("Partition member roster is incomplete")
        self._connection.execute(
            """
            INSERT INTO mra.evaluation_run (
                evaluation_run_id, experiment_run_id, experiment_id,
                experiment_partition_id, research_partition_id,
                evaluation_protocol_id, target_definition_id,
                partition_purpose, requested_knowledge_cutoff,
                expected_member_count, expected_protocol_metric_count,
                code_artifact_id, code_content_sha256, code_size_bytes,
                config_artifact_id, config_content_sha256, config_size_bytes,
                provenance_sha256, content_sha256,
                status, request_identity, request_sha256
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                'OPEN', %s, %s
            )
            """,
            (
                plan.evaluation_run_id, plan.experiment_run_id,
                binding[0], binding[1], binding[2], plan.evaluation_protocol_id,
                binding[3], binding[4], plan.requested_knowledge_cutoff,
                binding[5], binding[6],
                plan.code_artifact.artifact_id,
                str(plan.code_artifact.content_sha256),
                plan.code_artifact.size_bytes,
                plan.config_artifact.artifact_id,
                str(plan.config_artifact.content_sha256),
                plan.config_artifact.size_bytes,
                str(plan.provenance_sha256), str(plan.content_sha256),
                plan.request_identity, request_sha256,
            ),
        )
        return self.run_record(plan.evaluation_run_id, lock=False)

    def complete(self, evaluation_run_id: UUID) -> EvaluationCompletionResult:
        run = self._connection.execute(
            """
            SELECT evaluation_protocol_id, expected_member_count,
                   expected_protocol_metric_count, observation_count,
                   status, metric_count, metric_observation_count,
                   metric_roster_sha256
            FROM mra.evaluation_run
            WHERE evaluation_run_id = %s
            FOR UPDATE
            """,
            (evaluation_run_id,),
        ).fetchone()
        if run is None:
            raise RuntimeNotFoundError(f"EvaluationRun {evaluation_run_id} does not exist")
        if run[4] == "COMPLETED":
            if run[7] is None:
                raise EvaluationReconciliationError("completed EvaluationRun has no metric roster hash")
            return EvaluationCompletionResult(
                evaluation_run_id, int(run[5]), int(run[6]), str(run[7])
            )
        if run[4] != "INPUTS_ACQUIRED":
            raise RuntimeStateConflictError("EvaluationRun is not INPUTS_ACQUIRED")
        if int(run[1]) != int(run[3]):
            raise EvaluationReconciliationError("EvaluationObservation roster is incomplete")
        metric_rows = self._connection.execute(
            """
            SELECT evaluation_protocol_metric_id, metric_code, ordinal,
                   source_target_metric_definition_id, source_metric_code,
                   source_value_type, source_kind, source_measure,
                   reducer, slice_kind, candidate_disposition,
                   backtest_arm_kind, direction,
                   minimum_estimable_count, acceptance_operator,
                   acceptance_threshold, inclusion_policy,
                   missingness_policy
            FROM mra.evaluation_protocol_metric
            WHERE evaluation_protocol_id = %s
            ORDER BY ordinal
            FOR SHARE
            """,
            (run[0],),
        ).fetchall()
        if len(metric_rows) != int(run[2]):
            raise EvaluationReconciliationError("Protocol metric roster is incomplete")
        output_hashes: list[tuple[UUID, str]] = []
        total_inputs = 0
        for row in metric_rows:
            metric = _protocol_metric(row)
            source_rows = self._metric_source_rows(evaluation_run_id, metric)
            if len(source_rows) != int(run[1]):
                raise EvaluationReconciliationError(
                    "exact canonical metric input roster is incomplete or ambiguous"
                )
            resolved = self._resolve_metric_inputs(metric, source_rows)
            inputs = tuple(item.input for item in resolved)
            result = evaluate_metric(metric, inputs)
            evaluation_metric_id = self._id_factory()
            result_hash = canonical_json_sha256(
                {"metric": metric.content_sha256, "result": result}
            )
            self._connection.execute(
                """
                INSERT INTO mra.evaluation_metric (
                    evaluation_metric_id, evaluation_run_id,
                    evaluation_protocol_metric_id,
                    evaluation_protocol_id, metric_state,
                    decimal_value, boolean_value, estimable_count,
                    acceptance_state, content_sha256
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    evaluation_metric_id, evaluation_run_id,
                    metric.evaluation_protocol_metric_id, run[0],
                    result.state.value, result.decimal_value,
                    result.boolean_value, result.estimable_count,
                    result.acceptance_state.value, result_hash,
                ),
            )
            classifications = {
                item.evaluation_observation_id: item for item in result.observations
            }
            input_ids = {
                item.input.evaluation_observation_id: self._id_factory()
                for item in resolved
            }
            with self._connection.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO mra.evaluation_metric_observation (
                        evaluation_metric_observation_id,
                        evaluation_metric_id, evaluation_run_id,
                        evaluation_protocol_metric_id,
                        evaluation_observation_id,
                        research_partition_member_id,
                        market_target_outcome_revision_id,
                        source_outcome_metric_id,
                        source_target_metric_definition_id,
                        source_value_type, source_value_status,
                        input_state, reason_code, content_sha256
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s
                    )
                    """,
                    (
                        _metric_observation_values(
                            input_ids[item.input.evaluation_observation_id],
                            evaluation_metric_id, evaluation_run_id, metric,
                            item.source,
                            classifications[item.input.evaluation_observation_id],
                        )
                        for item in resolved
                    ),
                )
            self._insert_canonical_sources(
                evaluation_run_id,
                metric,
                resolved,
                input_ids,
            )
            total_inputs += len(source_rows)
            output_hashes.append((evaluation_metric_id, result_hash))
        expected_inputs = int(run[1]) * int(run[2])
        actual = self._connection.execute(
            """
            SELECT count(DISTINCT metric.evaluation_metric_id),
                   count(input.evaluation_metric_observation_id)
            FROM mra.evaluation_metric AS metric
            LEFT JOIN mra.evaluation_metric_observation AS input
              ON input.evaluation_metric_id = metric.evaluation_metric_id
            WHERE metric.evaluation_run_id = %s
            """,
            (evaluation_run_id,),
        ).fetchone()
        assert actual is not None
        if int(actual[0]) != int(run[2]) or int(actual[1]) != expected_inputs or total_inputs != expected_inputs:
            raise EvaluationReconciliationError("Evaluation metric Cartesian roster is incomplete")
        roster_hash = canonical_json_sha256(tuple(output_hashes))
        self._connection.execute(
            """
            UPDATE mra.evaluation_run
            SET status = 'COMPLETED', completed_at = clock_timestamp(),
                metric_count = %s, metric_observation_count = %s,
                metric_roster_sha256 = %s, version = version + 1
            WHERE evaluation_run_id = %s AND status = 'INPUTS_ACQUIRED'
            """,
            (len(metric_rows), expected_inputs, roster_hash, evaluation_run_id),
        )
        return EvaluationCompletionResult(
            evaluation_run_id, len(metric_rows), expected_inputs, roster_hash
        )

    def _metric_source_rows(
        self,
        evaluation_run_id: UUID,
        metric: ProtocolMetricDefinition,
    ) -> list[tuple[Any, ...]]:
        return self._connection.execute(
            """
            SELECT observation.evaluation_observation_id,
                   observation.research_partition_member_id,
                   observation.market_target_outcome_revision_id,
                   observation.candidate_disposition,
                   outcome_metric.market_target_outcome_metric_id,
                   outcome_metric.value_status,
                   outcome_metric.decimal_value,
                   outcome_metric.boolean_value,
                   member.commitment_id,
                   commitment.decision_run_id,
                   commitment.candidate_id,
                   commitment.instrument_id,
                   commitment.decision_time,
                   retrospective.exploratory_backtest_run_id,
                   retrospective.exploratory_backtest_arm_id,
                   retrospective.exploratory_backtest_fold_id,
                   retrospective.exploratory_backtest_fold_session_id,
                   arm.arm_kind,
                   backtest.strategy_version_id,
                   backtest.portfolio_policy_id,
                   backtest.risk_policy_id,
                   backtest.cost_count,
                   backtest.cost_roster_sha256,
                   (SELECT sum(cost.amount_bps)
                      FROM mra.exploratory_backtest_cost_assumption AS cost
                     WHERE cost.exploratory_backtest_run_id =
                           backtest.exploratory_backtest_run_id),
                   signal.signal_id,
                   signal.status,
                   forecast.forecast_id,
                   forecast.status,
                   estimate.forecast_estimate_id,
                   estimate.point_estimate,
                   proposal.portfolio_proposal_id,
                   line.portfolio_line_id,
                   line.status,
                   line.proposed_weight,
                   risk.risk_decision_id,
                   risk.status,
                   outcome_metric.value_type
            FROM mra.evaluation_observation AS observation
            JOIN mra.research_partition_member AS member
              ON member.research_partition_member_id =
                 observation.research_partition_member_id
            JOIN mra.decision_target_commitment AS commitment
              ON commitment.commitment_id = member.commitment_id
            JOIN mra.market_target_outcome_metric AS outcome_metric
              ON outcome_metric.market_target_outcome_revision_id =
                 observation.market_target_outcome_revision_id
             AND outcome_metric.target_metric_definition_id = %s
            LEFT JOIN mra.exploratory_retrospective_decision_run AS retrospective
              ON retrospective.decision_run_id = commitment.decision_run_id
            LEFT JOIN mra.exploratory_backtest_arm AS arm
              ON arm.exploratory_backtest_arm_id =
                 retrospective.exploratory_backtest_arm_id
             AND arm.exploratory_backtest_run_id =
                 retrospective.exploratory_backtest_run_id
            LEFT JOIN mra.exploratory_backtest_run AS backtest
              ON backtest.exploratory_backtest_run_id =
                 retrospective.exploratory_backtest_run_id
            LEFT JOIN mra.signal AS signal
              ON signal.decision_run_id = commitment.decision_run_id
             AND signal.candidate_id = commitment.candidate_id
             AND signal.strategy_version_id = backtest.strategy_version_id
            LEFT JOIN mra.forecast AS forecast
              ON forecast.decision_run_id = commitment.decision_run_id
             AND forecast.candidate_id = commitment.candidate_id
             AND forecast.commitment_id = commitment.commitment_id
             AND forecast.strategy_version_id = backtest.strategy_version_id
            LEFT JOIN mra.forecast_estimate AS estimate
              ON estimate.forecast_id = forecast.forecast_id
             AND estimate.target_metric_definition_id = %s
            LEFT JOIN mra.portfolio_proposal AS proposal
              ON proposal.decision_run_id = commitment.decision_run_id
             AND proposal.strategy_version_id = backtest.strategy_version_id
             AND proposal.portfolio_policy_id = backtest.portfolio_policy_id
            LEFT JOIN mra.portfolio_line AS line
              ON line.portfolio_proposal_id = proposal.portfolio_proposal_id
             AND line.candidate_id = commitment.candidate_id
             AND line.instrument_id = commitment.instrument_id
             AND line.target_definition_id = commitment.target_definition_id
            LEFT JOIN mra.risk_decision AS risk
              ON risk.portfolio_proposal_id = proposal.portfolio_proposal_id
             AND risk.risk_policy_id = backtest.risk_policy_id
            WHERE observation.evaluation_run_id = %s
            ORDER BY commitment.decision_time, arm.ordinal NULLS FIRST,
                     commitment.instrument_id,
                     observation.research_partition_member_id
            """,
            (
                metric.source_target_metric_definition_id,
                metric.source_target_metric_definition_id,
                evaluation_run_id,
            ),
        ).fetchall()

    def _resolve_metric_inputs(
        self,
        metric: ProtocolMetricDefinition,
        source_rows: list[tuple[Any, ...]],
    ) -> tuple[_ResolvedMetricInput, ...]:
        resolved: list[_ResolvedMetricInput] = []
        previous_weights: dict[tuple[object, object], Decimal] = {}
        for source in source_rows:
            arm_kind = (
                ExploratoryBacktestArmKind(str(source[17]))
                if source[17] is not None
                else None
            )
            if (
                metric.slice_kind is EvaluationSliceKind.EXPLORATORY_BACKTEST_ARM
                or metric.source_kind is not EvaluationSourceKind.OUTCOME_METRIC
            ) and arm_kind is None:
                raise EvaluationReconciliationError(
                    "exploratory metric source lacks exact Backtest arm lineage"
                )
            value_status = str(source[5])
            decimal_value = source[6]
            boolean_value = source[7]
            secondary_decimal_value: Decimal | None = None
            turnover: Decimal | None = None
            effective_weight: Decimal | None = None
            gross_return: Decimal | None = None
            net_return: Decimal | None = None
            if metric.source_kind is EvaluationSourceKind.CANDIDATE_DISPOSITION:
                decimal_value = None
                boolean_value = str(source[3]) == CandidateDisposition.SELECTED.value
                value_status = "COMPLETE"
            elif metric.source_kind is EvaluationSourceKind.SIGNAL_STATUS:
                if source[24] is None:
                    raise EvaluationReconciliationError("Signal source is absent")
                signal_status = str(source[25])
                if signal_status in {"UNKNOWN", "NOT_ESTIMABLE"}:
                    boolean_value = None
                    value_status = "UNAVAILABLE"
                else:
                    boolean_value = signal_status == "PRESENT"
                    value_status = "COMPLETE"
                decimal_value = None
            elif metric.source_kind is EvaluationSourceKind.FORECAST_OUTCOME_PAIR:
                if source[26] is None or source[28] is None:
                    raise EvaluationReconciliationError("Forecast source is absent or ambiguous")
                decimal_value = source[29]
                secondary_decimal_value = source[6]
                boolean_value = None
                if (
                    str(source[27]) != "AVAILABLE"
                    or decimal_value is None
                    or secondary_decimal_value is None
                    or str(source[5]) not in {"COMPLETE", "PARTIAL"}
                ):
                    value_status = "UNAVAILABLE"
                else:
                    value_status = str(source[5])
            elif metric.source_kind in {
                EvaluationSourceKind.PORTFOLIO_LINE,
                EvaluationSourceKind.PORTFOLIO_OUTCOME,
            }:
                if source[30] is None or source[31] is None or source[34] is None:
                    raise EvaluationReconciliationError("Portfolio source is absent or ambiguous")
                proposed_weight = Decimal(source[33])
                weight_key = (source[14], source[11])
                prior = previous_weights.get(weight_key, Decimal(0))
                turnover = abs(proposed_weight - prior)
                previous_weights[weight_key] = proposed_weight
                if metric.source_kind is EvaluationSourceKind.PORTFOLIO_LINE:
                    decimal_value = (
                        proposed_weight
                        if metric.source_measure is EvaluationSourceMeasure.TARGET_WEIGHT
                        else turnover
                    )
                    boolean_value = None
                    value_status = "COMPLETE"
                else:
                    if source[34] is None:
                        raise EvaluationReconciliationError("Risk Gate source is absent")
                    risk_status = str(source[35])
                    if risk_status == "UNKNOWN":
                        decimal_value = None
                        value_status = "UNAVAILABLE"
                    elif source[6] is None or str(source[5]) not in {"COMPLETE", "PARTIAL"}:
                        decimal_value = None
                        value_status = "UNAVAILABLE"
                    else:
                        effective_weight = (
                            proposed_weight if risk_status == "AUTHORIZED" else Decimal(0)
                        )
                        gross_return = effective_weight * Decimal(source[6])
                        if source[21] is None or source[23] is None:
                            raise EvaluationReconciliationError(
                                "assumed-cost roster is absent"
                            )
                        net_return = gross_return - (
                            turnover * Decimal(source[23]) / Decimal(10_000)
                        )
                        decimal_value = (
                            gross_return
                            if metric.source_measure
                            is EvaluationSourceMeasure.GROSS_PORTFOLIO_RETURN
                            else net_return
                        )
                        value_status = str(source[5])
                    boolean_value = None
            elif metric.source_kind is EvaluationSourceKind.RISK_DECISION:
                if source[34] is None:
                    raise EvaluationReconciliationError("Risk source is absent")
                risk_status = str(source[35])
                if risk_status == "UNKNOWN":
                    boolean_value = None
                    value_status = "UNAVAILABLE"
                else:
                    boolean_value = risk_status == "REJECTED"
                    value_status = "COMPLETE"
                decimal_value = None
            group_key = f"{arm_kind or 'UNBOUND'}:{source[12].isoformat()}"
            item = EvaluationInput(
                evaluation_observation_id=UUID(str(source[0])),
                candidate_disposition=CandidateDisposition(str(source[3])),
                source_value_status=value_status,
                decimal_value=decimal_value,
                boolean_value=boolean_value,
                secondary_decimal_value=secondary_decimal_value,
                backtest_arm_kind=arm_kind,
                group_key=group_key,
            )
            resolved.append(
                _ResolvedMetricInput(
                    source=source,
                    input=item,
                    turnover=turnover,
                    effective_weight=effective_weight,
                    gross_return=gross_return,
                    net_return=net_return,
                )
            )
        return tuple(resolved)

    def _insert_canonical_sources(
        self,
        evaluation_run_id: UUID,
        metric: ProtocolMetricDefinition,
        resolved: tuple[_ResolvedMetricInput, ...],
        input_ids: dict[UUID, UUID],
    ) -> None:
        if (
            metric.slice_kind is EvaluationSliceKind.EXPLORATORY_BACKTEST_ARM
            or metric.source_kind is not EvaluationSourceKind.OUTCOME_METRIC
        ):
            self._insert_backtest_arm_sources(evaluation_run_id, metric, resolved, input_ids)
        table = {
            EvaluationSourceKind.CANDIDATE_DISPOSITION: "candidate",
            EvaluationSourceKind.SIGNAL_STATUS: "signal",
            EvaluationSourceKind.FORECAST_OUTCOME_PAIR: "forecast",
            EvaluationSourceKind.PORTFOLIO_LINE: "portfolio",
            EvaluationSourceKind.PORTFOLIO_OUTCOME: "portfolio",
            EvaluationSourceKind.RISK_DECISION: "risk",
        }.get(metric.source_kind)
        if table is None:
            return
        getattr(self, f"_insert_{table}_sources")(
            evaluation_run_id, metric, resolved, input_ids
        )

    def _insert_backtest_arm_sources(
        self,
        evaluation_run_id: UUID,
        metric: ProtocolMetricDefinition,
        resolved: tuple[_ResolvedMetricInput, ...],
        input_ids: dict[UUID, UUID],
    ) -> None:
        with self._connection.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO mra.evaluation_backtest_arm_source (
                    evaluation_metric_observation_id, evaluation_run_id,
                    evaluation_protocol_metric_id, decision_run_id,
                    exploratory_backtest_run_id, exploratory_backtest_arm_id,
                    exploratory_backtest_fold_id,
                    exploratory_backtest_fold_session_id, arm_kind,
                    content_sha256
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    (
                        input_ids[item.input.evaluation_observation_id],
                        evaluation_run_id,
                        metric.evaluation_protocol_metric_id,
                        item.source[9], item.source[13], item.source[14],
                        item.source[15], item.source[16], item.source[17],
                        canonical_json_sha256(
                            {
                                "arm": item.source[14],
                                "decision_run": item.source[9],
                                "fold": item.source[15],
                                "fold_session": item.source[16],
                                "input": input_ids[item.input.evaluation_observation_id],
                                "run": item.source[13],
                            }
                        ),
                    )
                    for item in resolved
                ),
            )

    def _insert_candidate_sources(
        self, evaluation_run_id: UUID, metric: ProtocolMetricDefinition,
        resolved: tuple[_ResolvedMetricInput, ...], input_ids: dict[UUID, UUID],
    ) -> None:
        self._insert_simple_sources(
            "evaluation_candidate_source",
            "commitment_id, candidate_id, disposition, boolean_value",
            evaluation_run_id, metric, resolved, input_ids,
            lambda item: (
                item.source[8], item.source[10], item.source[3],
                item.input.boolean_value,
            ),
        )

    def _insert_signal_sources(
        self, evaluation_run_id: UUID, metric: ProtocolMetricDefinition,
        resolved: tuple[_ResolvedMetricInput, ...], input_ids: dict[UUID, UUID],
    ) -> None:
        self._insert_simple_sources(
            "evaluation_signal_source",
            "decision_run_id, candidate_id, signal_id, signal_status, boolean_value, source_status",
            evaluation_run_id, metric, resolved, input_ids,
            lambda item: (
                item.source[9], item.source[10], item.source[24], item.source[25],
                item.input.boolean_value, item.input.source_value_status,
            ),
        )

    def _insert_forecast_sources(
        self, evaluation_run_id: UUID, metric: ProtocolMetricDefinition,
        resolved: tuple[_ResolvedMetricInput, ...], input_ids: dict[UUID, UUID],
    ) -> None:
        self._insert_simple_sources(
            "evaluation_forecast_source",
            "commitment_id, decision_run_id, forecast_id, forecast_estimate_id, forecast_status, point_estimate, outcome_decimal_value, source_status",
            evaluation_run_id, metric, resolved, input_ids,
            lambda item: (
                item.source[8], item.source[9], item.source[26], item.source[28],
                item.source[27], item.input.decimal_value,
                item.input.secondary_decimal_value, item.input.source_value_status,
            ),
        )

    def _insert_portfolio_sources(
        self, evaluation_run_id: UUID, metric: ProtocolMetricDefinition,
        resolved: tuple[_ResolvedMetricInput, ...], input_ids: dict[UUID, UUID],
    ) -> None:
        self._insert_simple_sources(
            "evaluation_portfolio_source",
            "decision_run_id, candidate_id, portfolio_proposal_id, portfolio_line_id, risk_decision_id, line_status, risk_status, proposed_weight, turnover, effective_weight, gross_return, net_return, source_status, cost_count, cost_roster_sha256",
            evaluation_run_id, metric, resolved, input_ids,
            lambda item: (
                item.source[9], item.source[10], item.source[30], item.source[31],
                item.source[34], item.source[32], item.source[35], item.source[33],
                item.turnover, item.effective_weight, item.gross_return,
                item.net_return, item.input.source_value_status,
                item.source[21], item.source[22],
            ),
        )
        if metric.source_measure is EvaluationSourceMeasure.NET_PORTFOLIO_RETURN_ASSUMED_COST:
            with self._connection.cursor() as cursor:
                for item in resolved:
                    cost_rows = self._connection.execute(
                        """
                        SELECT exploratory_backtest_cost_assumption_id,
                               ordinal, cost_kind, amount_bps,
                               evidence_class, content_sha256
                        FROM mra.exploratory_backtest_cost_assumption
                        WHERE exploratory_backtest_run_id = %s
                        ORDER BY ordinal
                        """,
                        (item.source[13],),
                    ).fetchall()
                    cursor.executemany(
                        """
                        INSERT INTO mra.evaluation_portfolio_cost_source (
                            evaluation_metric_observation_id,
                            exploratory_backtest_cost_assumption_id,
                            exploratory_backtest_run_id, ordinal,
                            cost_kind, amount_bps, evidence_class,
                            assumption_content_sha256, content_sha256
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            (
                                input_ids[item.input.evaluation_observation_id],
                                cost[0], item.source[13], cost[1], cost[2], cost[3],
                                cost[4], cost[5],
                                canonical_json_sha256(
                                    {
                                        "assumption": cost[0],
                                        "assumption_content": cost[5],
                                        "input": input_ids[item.input.evaluation_observation_id],
                                    }
                                ),
                            )
                            for cost in cost_rows
                        ),
                    )

    def _insert_risk_sources(
        self, evaluation_run_id: UUID, metric: ProtocolMetricDefinition,
        resolved: tuple[_ResolvedMetricInput, ...], input_ids: dict[UUID, UUID],
    ) -> None:
        self._insert_simple_sources(
            "evaluation_risk_source",
            "decision_run_id, portfolio_proposal_id, risk_decision_id, risk_status, boolean_value, source_status",
            evaluation_run_id, metric, resolved, input_ids,
            lambda item: (
                item.source[9], item.source[30], item.source[34], item.source[35],
                item.input.boolean_value, item.input.source_value_status,
            ),
        )

    def _insert_simple_sources(
        self,
        table: str,
        columns: str,
        evaluation_run_id: UUID,
        metric: ProtocolMetricDefinition,
        resolved: tuple[_ResolvedMetricInput, ...],
        input_ids: dict[UUID, UUID],
        values: Callable[[_ResolvedMetricInput], tuple[Any, ...]],
    ) -> None:
        column_count = len(columns.split(","))
        placeholders = ", ".join("%s" for _ in range(4 + column_count))
        statement = (
            f"INSERT INTO mra.{table} ("  # noqa: S608 -- table is closed vocabulary above
            "evaluation_metric_observation_id, evaluation_run_id, "
            f"evaluation_protocol_metric_id, source_measure, {columns}, content_sha256) "
            f"VALUES ({placeholders}, %s)"
        )
        with self._connection.cursor() as cursor:
            cursor.executemany(
                statement,
                (
                    (
                        input_ids[item.input.evaluation_observation_id],
                        evaluation_run_id,
                        metric.evaluation_protocol_metric_id,
                        metric.source_measure.value,
                        *values(item),
                        canonical_json_sha256(
                            {
                                "input": input_ids[item.input.evaluation_observation_id],
                                "measure": metric.source_measure,
                                "source": values(item),
                            }
                        ),
                    )
                    for item in resolved
                ),
            )

    def fail(
        self,
        evaluation_run_id: UUID,
        reason_code: str,
    ) -> EvaluationRunRecord:
        changed = self._connection.execute(
            """
            UPDATE mra.evaluation_run
            SET status = 'FAILED', failed_at = clock_timestamp(),
                failure_reason_code = %s, version = version + 1
            WHERE evaluation_run_id = %s
              AND status IN ('OPEN', 'INPUTS_ACQUIRED')
            """,
            (reason_code, evaluation_run_id),
        ).rowcount
        if changed != 1:
            raise RuntimeStateConflictError("EvaluationRun cannot transition to FAILED")
        return self.run_record(evaluation_run_id, lock=False)

    def protocol_record(self, evaluation_protocol_id: UUID, *, lock: bool) -> EvaluationProtocolRecord:
        row = self._connection.execute(
            """
            SELECT evaluation_protocol_id, target_definition_id,
                   applicable_purpose, metric_count,
                   metric_roster_sha256, frozen_at
            FROM mra.evaluation_protocol
            WHERE evaluation_protocol_id = %s
            """ + (" FOR SHARE" if lock else ""),
            (evaluation_protocol_id,),
        ).fetchone()
        if row is None:
            raise RuntimeNotFoundError(f"EvaluationProtocol {evaluation_protocol_id} does not exist")
        return EvaluationProtocolRecord(
            UUID(str(row[0])), UUID(str(row[1])), str(row[2]),
            int(row[3]), str(row[4]), row[5],
        )

    def run_record(self, evaluation_run_id: UUID, *, lock: bool) -> EvaluationRunRecord:
        row = self._connection.execute(
            """
            SELECT evaluation_run_id, experiment_run_id,
                   research_partition_id, evaluation_protocol_id,
                   status, opened_at, content_sha256, version
            FROM mra.evaluation_run WHERE evaluation_run_id = %s
            """ + (" FOR SHARE" if lock else ""),
            (evaluation_run_id,),
        ).fetchone()
        if row is None:
            raise RuntimeNotFoundError(f"EvaluationRun {evaluation_run_id} does not exist")
        return EvaluationRunRecord(
            UUID(str(row[0])), UUID(str(row[1])), UUID(str(row[2])),
            UUID(str(row[3])), str(row[4]), row[5], str(row[6]), int(row[7]),
        )

    def _protocol_reconciles(self, record: EvaluationProtocolRecord) -> bool:
        rows = self._connection.execute(
            """
            SELECT evaluation_protocol_metric_id, metric_code, ordinal,
                   source_target_metric_definition_id, source_metric_code,
                   source_value_type, source_kind, source_measure,
                   reducer, slice_kind, candidate_disposition,
                   backtest_arm_kind, direction,
                   minimum_estimable_count, acceptance_operator,
                   acceptance_threshold, inclusion_policy, missingness_policy
            FROM mra.evaluation_protocol_metric
            WHERE evaluation_protocol_id = %s ORDER BY ordinal
            """,
            (record.evaluation_protocol_id,),
        ).fetchall()
        metrics = tuple(_protocol_metric(row) for row in rows)
        return len(metrics) == record.metric_count and canonical_json_sha256(metrics) == record.metric_roster_sha256


def _protocol_metric(row: tuple[Any, ...]) -> ProtocolMetricDefinition:
    return ProtocolMetricDefinition(
        evaluation_protocol_metric_id=UUID(str(row[0])), metric_code=str(row[1]),
        ordinal=int(row[2]), source_target_metric_definition_id=UUID(str(row[3])),
        source_metric_code=str(row[4]), source_value_type=SourceMetricValueType(str(row[5])),
        source_kind=EvaluationSourceKind(str(row[6])),
        source_measure=EvaluationSourceMeasure(str(row[7])),
        reducer=EvaluationReducer(str(row[8])), slice_kind=EvaluationSliceKind(str(row[9])),
        candidate_disposition=CandidateDisposition(str(row[10])) if row[10] is not None else None,
        backtest_arm_kind=ExploratoryBacktestArmKind(str(row[11])) if row[11] is not None else None,
        direction=MetricDirection(str(row[12])), minimum_estimable_count=int(row[13]),
        acceptance_operator=AcceptanceOperator(str(row[14])), acceptance_threshold=row[15],
        inclusion_policy=EvaluationInclusionPolicy(str(row[16])),
        missingness_policy=EvaluationMissingnessPolicy(str(row[17])),
    )


def _metric_observation_values(
    identity: UUID,
    evaluation_metric_id: UUID,
    evaluation_run_id: UUID,
    metric: ProtocolMetricDefinition,
    source: tuple[Any, ...],
    classification: Any,
) -> tuple[Any, ...]:
    content_hash = canonical_json_sha256(
        {
            "evaluation_metric_id": evaluation_metric_id,
            "evaluation_observation_id": source[0],
            "input_state": classification.state,
            "reason_code": classification.reason_code,
            "source_outcome_metric_id": source[4],
        }
    )
    return (
        identity, evaluation_metric_id, evaluation_run_id,
        metric.evaluation_protocol_metric_id, source[0], source[1], source[2],
        source[4], metric.source_target_metric_definition_id,
        source[36], source[5], classification.state.value,
        classification.reason_code, content_hash,
    )


__all__ = ["PostgresEvaluationRepository"]
