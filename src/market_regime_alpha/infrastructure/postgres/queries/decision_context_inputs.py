"""Exact Decision-owned Context inputs; never Outcome or current/latest reads."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import psycopg

from market_regime_alpha.decision_support.domain import (
    ContextMeasure,
    ContextMetricDefinition,
    ContextMissingnessPolicy,
    ContextOperator,
    ContextPolicyPlan,
    ContextReducer,
    ContextSourceKind,
    ContextSourceRole,
    ContextSourceValueStatus,
    DecisionArtifactBinding,
    PreparedContextInputs,
    PreparedContextSource,
)
from market_regime_alpha.decision_support.domain.context import ContextKind
from market_regime_alpha.decision_support.errors import (
    ContextAuthorityIntegrityError,
)
from market_regime_alpha.decision_support.ports import (
    ContextAssessmentRecord,
    ContextPolicyRecord,
)
from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.shared.hashing import canonical_json_sha256


class PostgresContextInputPreparationProvider:
    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool

    def prepare(
        self,
        decision_run_id: UUID,
        context_policy_id: UUID,
    ) -> PreparedContextInputs:
        with self._pool.connection(read_only=True) as connection:
            return _load_context_inputs(
                connection,
                decision_run_id,
                context_policy_id,
                lock=False,
            )


class PostgresContextQueryProvider:
    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool

    def authoritative_time(self) -> datetime:
        with self._pool.connection(read_only=True) as connection:
            row = connection.execute("SELECT clock_timestamp()").fetchone()
        if row is None:
            raise ContextAuthorityIntegrityError(
                "PostgreSQL did not return authoritative time"
            )
        return row[0]

    def find_policy_request(
        self,
        policy_code: str,
        request_identity: str,
    ) -> ContextPolicyRecord | None:
        with self._pool.connection(read_only=True) as connection:
            row = _policy_record_row(
                connection,
                "policy.policy_code = %s AND policy.request_identity = %s",
                (policy_code, request_identity),
                lock=False,
            )
        return None if row is None else _policy_record(row)

    def find_assessment_request(
        self,
        decision_run_id: UUID,
        context_policy_id: UUID,
        request_identity: str,
    ) -> ContextAssessmentRecord | None:
        with self._pool.connection(read_only=True) as connection:
            return _load_assessment_record(
                connection,
                decision_run_id=decision_run_id,
                context_policy_id=context_policy_id,
                request_identity=request_identity,
                assessment_group_id=None,
                lock=False,
            )


class PostgresContextDependencyRepository:
    def __init__(self, connection: psycopg.Connection[Any]) -> None:
        self._connection = connection

    def lock_and_revalidate(self, prepared: PreparedContextInputs) -> None:
        actual = _load_context_inputs(
            self._connection,
            prepared.decision_run_id,
            prepared.policy.context_policy_id,
            lock=True,
        )
        if actual != prepared:
            raise ContextAuthorityIntegrityError(
                "prepared Context inputs changed before Authority closure"
            )


def _load_context_inputs(
    connection: psycopg.Connection[Any],
    decision_run_id: UUID,
    context_policy_id: UUID,
    *,
    lock: bool,
) -> PreparedContextInputs:
    run_suffix = " FOR SHARE OF run" if lock else ""
    run = connection.execute(
        """
        SELECT run.decision_run_id, run.candidate_set_id,
               run.candidate_roster_sha256, run.decision_time,
               run.candidate_count, run.candidate_set_content_sha256
        FROM mra.decision_run AS run
        WHERE run.decision_run_id = %s
        """
        + run_suffix,
        (decision_run_id,),
    ).fetchone()
    if run is None:
        raise ContextAuthorityIntegrityError("Context DecisionRun is absent")
    policy = _load_policy(connection, context_policy_id, lock=lock)
    source_suffix = (
        " FOR SHARE OF candidate, reference, target" if lock else ""
    )
    rows = connection.execute(
        """
        SELECT candidate.candidate_id, candidate.instrument_id,
               reference.decision_reference_observation_id,
               reference.known_at, reference.source_kind,
               reference.value_status, reference.bar_revision_id,
               reference.source_gap_id,
               bar.open_value, bar.close_value, bar.turnover_value
        FROM mra.candidate AS candidate
        JOIN mra.decision_reference_observation AS reference
          ON reference.candidate_set_id = candidate.candidate_set_id
         AND reference.candidate_id = candidate.candidate_id
         AND reference.instrument_id = candidate.instrument_id
         AND reference.decision_run_id = %s
        JOIN mra.decision_run_target AS target
          ON target.decision_run_target_id = reference.decision_run_target_id
         AND target.decision_run_id = reference.decision_run_id
         AND target.ordinal = 1
        LEFT JOIN mra.market_bar_revision AS bar
          ON bar.bar_revision_id = reference.bar_revision_id
        LEFT JOIN mra.source_gap AS gap
          ON gap.gap_id = reference.source_gap_id
        WHERE candidate.candidate_set_id = %s
        ORDER BY candidate.candidate_id
        """
        + source_suffix,
        (decision_run_id, run[1]),
    ).fetchall()
    if len(rows) != int(run[4]):
        raise ContextAuthorityIntegrityError(
            "Context primary Decision reference roster is incomplete or ambiguous"
        )
    sources = tuple(
        _prepared_source(metric, ordinal, row)
        for metric in policy.metrics
        for ordinal, row in enumerate(rows, start=1)
    )
    return PreparedContextInputs(
        decision_run_id=UUID(str(run[0])),
        candidate_set_id=UUID(str(run[1])),
        candidate_set_content_sha256=str(run[5]),
        candidate_roster_sha256=str(run[2]),
        decision_time=run[3],
        candidate_count=int(run[4]),
        policy=policy,
        sources=sources,
    )


def _load_policy(
    connection: psycopg.Connection[Any],
    context_policy_id: UUID,
    *,
    lock: bool,
) -> ContextPolicyPlan:
    suffix = " FOR SHARE OF policy, metric" if lock else ""
    rows = connection.execute(
        """
        SELECT policy.context_policy_id, policy.policy_code, policy.version,
               policy.supersedes_policy_id,
               policy.code_artifact_id, policy.code_content_sha256,
               policy.code_size_bytes, policy.config_artifact_id,
               policy.config_content_sha256, policy.config_size_bytes,
               policy.provenance_sha256,
               metric.context_policy_metric_id, metric.metric_code,
               metric.metric_ordinal, metric.context_kind, metric.measure,
               metric.reducer, metric.qualification_operator,
               metric.lower_threshold, metric.upper_threshold,
               metric.minimum_source_count, metric.minimum_available_count,
               metric.missingness_policy, metric.source_role
        FROM mra.context_policy AS policy
        JOIN mra.context_policy_metric AS metric
          ON metric.context_policy_id = policy.context_policy_id
        WHERE policy.context_policy_id = %s
        ORDER BY metric.metric_ordinal
        """
        + suffix,
        (context_policy_id,),
    ).fetchall()
    if not rows:
        raise ContextAuthorityIntegrityError("ContextPolicy is absent")
    first = rows[0]
    metrics = tuple(
        ContextMetricDefinition(
            context_policy_metric_id=UUID(str(row[11])),
            context_policy_id=UUID(str(row[0])),
            metric_code=str(row[12]),
            ordinal=int(row[13]),
            context_kind=ContextKind(str(row[14])),
            measure=ContextMeasure(str(row[15])),
            reducer=ContextReducer(str(row[16])),
            operator=ContextOperator(str(row[17])),
            lower_threshold=Decimal(row[18]),
            upper_threshold=(Decimal(row[19]) if row[19] is not None else None),
            minimum_source_count=int(row[20]),
            minimum_available_count=int(row[21]),
            missingness_policy=ContextMissingnessPolicy(str(row[22])),
            source_role=ContextSourceRole(str(row[23])),
        )
        for row in rows
    )
    return ContextPolicyPlan(
        context_policy_id=UUID(str(first[0])),
        policy_code=str(first[1]),
        version=int(first[2]),
        supersedes_policy_id=(UUID(str(first[3])) if first[3] is not None else None),
        metrics=metrics,
        code_artifact=DecisionArtifactBinding(
            artifact_id=UUID(str(first[4])),
            content_sha256=str(first[5]),
            size_bytes=int(first[6]),
        ),
        config_artifact=DecisionArtifactBinding(
            artifact_id=UUID(str(first[7])),
            content_sha256=str(first[8]),
            size_bytes=int(first[9]),
        ),
        provenance_sha256=str(first[10]),
    )


def _prepared_source(
    metric: ContextMetricDefinition,
    ordinal: int,
    row,
) -> PreparedContextSource:
    reference_kind = ContextSourceKind(str(row[4]))
    decimal_value: Decimal | None = None
    boolean_value: bool | None = None
    if reference_kind is ContextSourceKind.MARKET_BAR:
        open_value = Decimal(row[8])
        close_value = Decimal(row[9])
        turnover = Decimal(row[10]) if row[10] is not None else None
        if metric.measure is ContextMeasure.RETURN:
            status = ContextSourceValueStatus.AVAILABLE
            decimal_value = close_value / open_value - Decimal("1")
        elif metric.measure is ContextMeasure.ADVANCE_RATE:
            status = ContextSourceValueStatus.AVAILABLE
            boolean_value = close_value >= open_value
        elif metric.measure is ContextMeasure.MEMBER_COVERAGE:
            status = ContextSourceValueStatus.AVAILABLE
            boolean_value = True
        elif turnover is None:
            status = ContextSourceValueStatus.UNAVAILABLE
        elif metric.measure is ContextMeasure.TURNOVER:
            status = ContextSourceValueStatus.AVAILABLE
            decimal_value = turnover
        else:
            status = ContextSourceValueStatus.AVAILABLE
            decimal_value = (
                turnover
                if close_value > open_value
                else -turnover
                if close_value < open_value
                else Decimal("0")
            )
    elif metric.measure is ContextMeasure.MEMBER_COVERAGE:
        status = ContextSourceValueStatus.AVAILABLE
        boolean_value = False
    else:
        status = (
            ContextSourceValueStatus.FAILED
            if str(row[5]) == "FAILED"
            else ContextSourceValueStatus.UNAVAILABLE
        )
    return PreparedContextSource(
        context_policy_metric_id=metric.context_policy_metric_id,
        candidate_id=UUID(str(row[0])),
        instrument_id=UUID(str(row[1])),
        source_kind=reference_kind,
        source_ordinal=ordinal,
        decision_reference_observation_id=UUID(str(row[2])),
        bar_revision_id=UUID(str(row[6])) if row[6] is not None else None,
        source_gap_id=UUID(str(row[7])) if row[7] is not None else None,
        known_at=row[3],
        value_status=status,
        decimal_value=decimal_value,
        boolean_value=boolean_value,
    )


def _policy_record_row(
    connection: psycopg.Connection[Any],
    predicate: str,
    parameters: tuple[object, ...],
    *,
    lock: bool,
):
    suffix = " FOR SHARE OF policy, receipt" if lock else ""
    return connection.execute(
        """
        SELECT policy.context_policy_id, policy.policy_code, policy.version,
               policy.metric_count, policy.kind_count, policy.content_sha256,
               policy.request_identity, policy.request_sha256,
               policy.frozen_at, receipt.receipt_id
        FROM mra.context_policy AS policy
        JOIN mra.command_receipt AS receipt
          ON receipt.command_kind = 'REGISTER_CONTEXT_POLICY'
         AND receipt.scope_id = policy.policy_code
         AND receipt.idempotency_key = policy.request_identity
         AND receipt.request_hash = policy.request_sha256
        WHERE """
        + predicate
        + suffix,
        parameters,
    ).fetchone()


def _policy_record(row) -> ContextPolicyRecord:
    return ContextPolicyRecord(
        context_policy_id=UUID(str(row[0])),
        policy_code=str(row[1]),
        version=int(row[2]),
        metric_count=int(row[3]),
        kind_count=int(row[4]),
        content_sha256=str(row[5]),
        request_identity=str(row[6]),
        request_sha256=str(row[7]),
        frozen_at=row[8],
        receipt_id=UUID(str(row[9])),
    )


def _load_assessment_record(
    connection: psycopg.Connection[Any],
    *,
    decision_run_id: UUID | None,
    context_policy_id: UUID | None,
    request_identity: str | None,
    assessment_group_id: UUID | None,
    lock: bool,
) -> ContextAssessmentRecord | None:
    if assessment_group_id is not None:
        predicate = "assessment.assessment_group_id = %s"
        parameters: tuple[object, ...] = (assessment_group_id,)
    else:
        predicate = """assessment.decision_run_id = %s
          AND assessment.context_policy_id = %s
          AND assessment.request_identity = %s"""
        parameters = (decision_run_id, context_policy_id, request_identity)
    suffix = " FOR SHARE OF assessment, receipt" if lock else ""
    rows = connection.execute(
        """
        SELECT assessment.assessment_group_id, assessment.decision_run_id,
               assessment.context_policy_id, assessment.assessment_count,
               assessment.assessment_roster_sha256,
               assessment.request_identity, assessment.request_sha256,
               assessment.recorded_at, receipt.receipt_id,
               assessment.candidate_set_id,
               assessment.candidate_roster_sha256,
               assessment.candidate_set_content_sha256,
               assessment.candidate_count,
               assessment.context_policy_content_sha256,
               assessment.decision_time
        FROM mra.context_assessment AS assessment
        JOIN mra.command_receipt AS receipt
          ON receipt.command_kind = 'ASSESS_CONTEXT'
         AND receipt.scope_id = assessment.decision_run_id::text || ':' ||
                                assessment.context_policy_id::text
         AND receipt.idempotency_key = assessment.request_identity
         AND receipt.request_hash = assessment.request_sha256
        WHERE """
        + predicate
        + " ORDER BY assessment.assessment_ordinal"
        + suffix,
        parameters,
    ).fetchall()
    if not rows:
        return None
    first = rows[0]
    count_row = connection.execute(
        """
        SELECT count(DISTINCT metric.context_metric_id),
               count(source.context_metric_source_id)
        FROM mra.context_metric AS metric
        LEFT JOIN mra.context_metric_source AS source
          ON source.context_metric_id = metric.context_metric_id
        WHERE metric.assessment_group_id = %s
        """,
        (first[0],),
    ).fetchone()
    if count_row is None:
        raise ContextAuthorityIntegrityError("Context counts are absent")
    metric_count, source_count = count_row
    content_sha256 = canonical_json_sha256(
        {
            "assessment_count": int(first[3]),
            "assessment_group_id": UUID(str(first[0])),
            "assessment_roster_sha256": str(first[4]),
            "candidate_count": int(first[12]),
            "candidate_roster_sha256": str(first[10]),
            "candidate_set_content_sha256": str(first[11]),
            "candidate_set_id": UUID(str(first[9])),
            "context_policy_content_sha256": str(first[13]),
            "context_policy_id": UUID(str(first[2])),
            "decision_run_id": UUID(str(first[1])),
            "decision_time": first[14],
            "metric_count": int(metric_count),
            "request_identity": str(first[5]),
            "request_sha256": str(first[6]),
            "source_count": int(source_count),
        }
    )
    return ContextAssessmentRecord(
        assessment_group_id=UUID(str(first[0])),
        decision_run_id=UUID(str(first[1])),
        context_policy_id=UUID(str(first[2])),
        assessment_count=int(first[3]),
        metric_count=int(metric_count),
        source_count=int(source_count),
        assessment_roster_sha256=str(first[4]),
        content_sha256=content_sha256,
        request_identity=str(first[5]),
        request_sha256=str(first[6]),
        recorded_at=first[7],
        receipt_id=UUID(str(first[8])),
    )


__all__ = [
    "PostgresContextDependencyRepository",
    "PostgresContextInputPreparationProvider",
    "PostgresContextQueryProvider",
]
