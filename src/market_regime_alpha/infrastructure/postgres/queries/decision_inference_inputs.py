"""Exact immutable Context, Candidate, Commitment, and Strategy inputs."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

import psycopg

from market_regime_alpha.decision_support.domain import (
    CandidateDisposition,
    ContextFailureAction,
    ContextKind,
    ContextMetricStatus,
    ContextState,
    DecisionArtifactBinding,
    ForecastSourceMeasure,
    PreparedForecastCommitment,
    PreparedInferenceInputs,
    PreparedSignalCandidate,
    PreparedSignalContext,
    PreparedSignalInputs,
    SignalStatus,
    StrategyActionPolicy,
    StrategyContextRequirement,
    StrategyForecastRule,
    StrategyPlan,
    StrategySignalRule,
    StrategyVersionPlan,
)
from market_regime_alpha.decision_support.errors import InferenceAuthorityIntegrityError
from market_regime_alpha.decision_support.ports import InferenceRecord
from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.postgres.repositories.decision_inference import (
    _inference_record,
    _inference_record_rows,
)


class PostgresInferenceInputPreparationProvider:
    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool

    def prepare(
        self,
        decision_run_id: UUID,
        strategy_version_id: UUID,
    ) -> PreparedInferenceInputs:
        with self._pool.connection(read_only=True) as connection:
            return _load_inputs(
                connection,
                decision_run_id,
                strategy_version_id,
                lock=False,
            )


class PostgresInferenceQueryProvider:
    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool

    def find_request(
        self,
        decision_run_id: UUID,
        strategy_version_id: UUID,
        request_identity: str,
    ) -> InferenceRecord | None:
        with self._pool.connection(read_only=True) as connection:
            rows = _inference_record_rows(
                connection,
                "signal_run.decision_run_id = %s "
                "AND signal_run.strategy_version_id = %s "
                "AND signal_run.request_identity = %s",
                (decision_run_id, strategy_version_id, request_identity),
                lock=False,
            )
        return None if rows is None else _inference_record(rows)


class PostgresInferenceDependencyRepository:
    def __init__(self, connection: psycopg.Connection[Any]) -> None:
        self._connection = connection

    def lock_and_revalidate(self, prepared: PreparedInferenceInputs) -> None:
        actual = _load_inputs(
            self._connection,
            prepared.signal_inputs.decision_run_id,
            prepared.signal_inputs.strategy_version.strategy_version_id,
            lock=True,
        )
        if actual != prepared:
            raise InferenceAuthorityIntegrityError(
                "prepared inference inputs changed before Authority closure"
            )


def _load_inputs(
    connection: psycopg.Connection[Any],
    decision_run_id: UUID,
    strategy_version_id: UUID,
    *,
    lock: bool,
) -> PreparedInferenceInputs:
    suffix = " FOR SHARE OF run" if lock else ""
    run = connection.execute(
        """
        SELECT run.candidate_set_id, run.candidate_set_content_sha256,
               run.candidate_roster_sha256, run.decision_time,
               run.candidate_count
        FROM mra.decision_run AS run WHERE run.decision_run_id = %s
        """
        + suffix,
        (decision_run_id,),
    ).fetchone()
    if run is None:
        raise InferenceAuthorityIntegrityError("Inference DecisionRun is absent")
    strategy = _load_strategy(connection, strategy_version_id, lock=lock)
    candidate_suffix = " FOR SHARE OF candidate" if lock else ""
    candidate_rows = connection.execute(
        """
        SELECT candidate_id, instrument_id, disposition, composite_score
        FROM mra.candidate AS candidate WHERE candidate_set_id = %s
        ORDER BY candidate_id
        """
        + candidate_suffix,
        (run[0],),
    ).fetchall()
    if len(candidate_rows) != int(run[4]):
        raise InferenceAuthorityIntegrityError("Candidate roster is incomplete")
    assessment_suffix = " FOR SHARE OF assessment" if lock else ""
    contexts: list[PreparedSignalContext] = []
    for requirement in strategy.context_requirements:
        rows = connection.execute(
            """
            SELECT assessment.context_assessment_id,
                   assessment.assessment_group_id,
                   assessment.assessment_status, assessment.assessment_state,
                   assessment.content_sha256, assessment.recorded_at,
                   assessment.context_policy_content_sha256
            FROM mra.context_assessment AS assessment
            WHERE assessment.decision_run_id = %s
              AND assessment.context_policy_id = %s
              AND assessment.context_kind = %s
            """
            + assessment_suffix,
            (
                decision_run_id,
                requirement.context_policy_id,
                requirement.context_kind.value,
            ),
        ).fetchall()
        if len(rows) != 1:
            raise InferenceAuthorityIntegrityError(
                "Strategy Context assessment is missing or ambiguous"
            )
        row = rows[0]
        if str(row[6]) != requirement.context_policy_content_sha256:
            raise InferenceAuthorityIntegrityError(
                "Strategy ContextPolicy binding changed"
            )
        contexts.append(
            PreparedSignalContext(
                strategy_context_requirement_id=(
                    requirement.strategy_context_requirement_id
                ),
                context_policy_id=requirement.context_policy_id,
                context_policy_content_sha256=requirement.context_policy_content_sha256,
                context_assessment_id=UUID(str(row[0])),
                assessment_group_id=UUID(str(row[1])),
                context_kind=requirement.context_kind,
                assessment_status=ContextMetricStatus(str(row[2])),
                assessment_state=ContextState(str(row[3])),
                assessment_content_sha256=str(row[4]),
                recorded_at=row[5],
            )
        )
    context_tuple = tuple(contexts)
    candidates = tuple(
        PreparedSignalCandidate(
            candidate_id=UUID(str(row[0])),
            instrument_id=UUID(str(row[1])),
            disposition=CandidateDisposition(str(row[2])),
            composite_score=(Decimal(row[3]) if row[3] is not None else None),
            contexts=context_tuple,
        )
        for row in candidate_rows
    )
    target_ids = tuple(
        dict.fromkeys(rule.target_definition_id for rule in strategy.forecast_rules)
    )
    commitment_suffix = " FOR SHARE OF commitment, definition, checkpoint" if lock else ""
    commitment_rows = connection.execute(
        """
        SELECT commitment.commitment_id, commitment.candidate_id,
               commitment.instrument_id, commitment.target_definition_id,
               definition.content_sha256, commitment.target_checkpoint_id,
               checkpoint.content_sha256, commitment.content_sha256
        FROM mra.decision_target_commitment AS commitment
        JOIN mra.target_definition AS definition
          ON definition.target_definition_id = commitment.target_definition_id
        JOIN mra.target_checkpoint AS checkpoint
          ON checkpoint.target_checkpoint_id = commitment.target_checkpoint_id
         AND checkpoint.target_definition_id = commitment.target_definition_id
        WHERE commitment.decision_run_id = %s
          AND commitment.target_definition_id = ANY(%s)
        ORDER BY commitment.candidate_id, commitment.target_definition_id
        """
        + commitment_suffix,
        (decision_run_id, list(target_ids)),
    ).fetchall()
    commitments = tuple(
        PreparedForecastCommitment(
            commitment_id=UUID(str(row[0])),
            candidate_id=UUID(str(row[1])),
            instrument_id=UUID(str(row[2])),
            target_definition_id=UUID(str(row[3])),
            target_definition_sha256=str(row[4]),
            target_checkpoint_id=UUID(str(row[5])),
            target_checkpoint_sha256=str(row[6]),
            commitment_content_sha256=str(row[7]),
        )
        for row in commitment_rows
    )
    return PreparedInferenceInputs(
        signal_inputs=PreparedSignalInputs(
            decision_run_id=decision_run_id,
            candidate_set_id=UUID(str(run[0])),
            candidate_set_content_sha256=str(run[1]),
            candidate_roster_sha256=str(run[2]),
            decision_time=run[3],
            strategy_version=strategy,
            candidates=candidates,
        ),
        commitments=commitments,
    )


def _load_strategy(
    connection: psycopg.Connection[Any],
    strategy_version_id: UUID,
    *,
    lock: bool,
) -> StrategyVersionPlan:
    suffix = " FOR SHARE OF version, strategy" if lock else ""
    root = connection.execute(
        """
        SELECT strategy.strategy_id, strategy.strategy_code,
               strategy.objective, version.version,
               version.supersedes_strategy_version_id,
               version.primary_change, version.action_policy,
               version.code_artifact_id, version.code_content_sha256,
               version.code_size_bytes, version.config_artifact_id,
               version.config_content_sha256, version.config_size_bytes,
               version.provenance_sha256, version.content_sha256
        FROM mra.strategy_version AS version
        JOIN mra.strategy AS strategy
          ON strategy.strategy_id = version.strategy_id
        WHERE version.strategy_version_id = %s
        """
        + suffix,
        (strategy_version_id,),
    ).fetchone()
    if root is None:
        raise InferenceAuthorityIntegrityError("StrategyVersion is absent")
    child_suffix = " FOR SHARE" if lock else ""
    context_rows = connection.execute(
        """
        SELECT strategy_context_requirement_id, ordinal,
               context_policy_id, context_policy_content_sha256,
               context_kind, required_state, missing_action
        FROM mra.strategy_context_requirement
        WHERE strategy_version_id = %s ORDER BY ordinal
        """
        + child_suffix,
        (strategy_version_id,),
    ).fetchall()
    signal = connection.execute(
        """
        SELECT strategy_signal_rule_id, eligible_disposition,
               positive_status, negative_status, ineligible_status
        FROM mra.strategy_signal_rule WHERE strategy_version_id = %s
        """
        + child_suffix,
        (strategy_version_id,),
    ).fetchone()
    forecast_rows = connection.execute(
        """
        SELECT strategy_forecast_rule_id, ordinal,
               target_definition_id, target_definition_sha256,
               target_checkpoint_id, target_checkpoint_sha256,
               target_metric_definition_id,
               target_metric_definition_sha256, source_measure,
               coefficient, intercept, lower_offset, upper_offset, value_unit
        FROM mra.strategy_forecast_rule
        WHERE strategy_version_id = %s ORDER BY ordinal
        """
        + child_suffix,
        (strategy_version_id,),
    ).fetchall()
    if not context_rows or signal is None or not forecast_rows:
        raise InferenceAuthorityIntegrityError("StrategyVersion roster is incomplete")
    plan = StrategyVersionPlan(
        strategy=StrategyPlan(
            strategy_id=UUID(str(root[0])),
            strategy_code=str(root[1]),
            objective=str(root[2]),
        ),
        strategy_version_id=strategy_version_id,
        version=int(root[3]),
        supersedes_strategy_version_id=(
            UUID(str(root[4])) if root[4] is not None else None
        ),
        primary_change=str(root[5]),
        action_policy=StrategyActionPolicy(str(root[6])),
        context_requirements=tuple(
            StrategyContextRequirement(
                strategy_context_requirement_id=UUID(str(row[0])),
                strategy_version_id=strategy_version_id,
                ordinal=int(row[1]),
                context_policy_id=UUID(str(row[2])),
                context_policy_content_sha256=str(row[3]),
                context_kind=ContextKind(str(row[4])),
                required_state=ContextState(str(row[5])),
                missing_action=ContextFailureAction(str(row[6])),
            )
            for row in context_rows
        ),
        signal_rule=StrategySignalRule(
            strategy_signal_rule_id=UUID(str(signal[0])),
            strategy_version_id=strategy_version_id,
            eligible_disposition=CandidateDisposition(str(signal[1])),
            positive_status=SignalStatus(str(signal[2])),
            negative_status=SignalStatus(str(signal[3])),
            ineligible_status=SignalStatus(str(signal[4])),
        ),
        forecast_rules=tuple(
            StrategyForecastRule(
                strategy_forecast_rule_id=UUID(str(row[0])),
                strategy_version_id=strategy_version_id,
                ordinal=int(row[1]),
                target_definition_id=UUID(str(row[2])),
                target_definition_sha256=str(row[3]),
                target_checkpoint_id=UUID(str(row[4])),
                target_checkpoint_sha256=str(row[5]),
                target_metric_definition_id=UUID(str(row[6])),
                target_metric_definition_sha256=str(row[7]),
                source_measure=ForecastSourceMeasure(str(row[8])),
                coefficient=Decimal(row[9]),
                intercept=Decimal(row[10]),
                lower_offset=Decimal(row[11]),
                upper_offset=Decimal(row[12]),
                value_unit=str(row[13]),
            )
            for row in forecast_rows
        ),
        code_artifact=DecisionArtifactBinding(
            artifact_id=UUID(str(root[7])),
            content_sha256=str(root[8]),
            size_bytes=int(root[9]),
        ),
        config_artifact=DecisionArtifactBinding(
            artifact_id=UUID(str(root[10])),
            content_sha256=str(root[11]),
            size_bytes=int(root[12]),
        ),
        provenance_sha256=str(root[13]),
    )
    if plan.content_sha256 != str(root[14]):
        raise InferenceAuthorityIntegrityError("StrategyVersion content is corrupt")
    return plan


__all__ = [
    "PostgresInferenceDependencyRepository",
    "PostgresInferenceInputPreparationProvider",
    "PostgresInferenceQueryProvider",
]
