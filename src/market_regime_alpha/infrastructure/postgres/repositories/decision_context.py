"""PostgreSQL persistence for immutable Context Authority."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import psycopg

from market_regime_alpha.decision_support.domain import (
    ContextAssessmentAuthority,
    ContextPolicyPlan,
)
from market_regime_alpha.decision_support.errors import (
    ContextAuthorityIntegrityError,
)
from market_regime_alpha.decision_support.ports import (
    ContextAssessmentRecord,
    ContextPolicyRecord,
    ContextReconciliation,
)
from market_regime_alpha.infrastructure.postgres.queries.decision_context_inputs import (
    _load_assessment_record,
    _policy_record,
    _policy_record_row,
)
from market_regime_alpha.shared.hashing import canonical_json_sha256


class PostgresContextRepository:
    def __init__(self, connection: psycopg.Connection[Any]) -> None:
        self._connection = connection

    def lock_policy_identity(self, policy_code: str) -> None:
        self._connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"context-policy:{policy_code}",),
        )

    def lock_assessment_identity(
        self,
        decision_run_id: UUID,
        context_policy_id: UUID,
    ) -> None:
        self._connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"context-assessment:{decision_run_id}:{context_policy_id}",),
        )

    def authoritative_recorded_at(self):
        row = self._connection.execute("SELECT clock_timestamp()").fetchone()
        if row is None:
            raise ContextAuthorityIntegrityError(
                "PostgreSQL did not return authoritative time"
            )
        return row[0]

    def register_policy(
        self,
        plan: ContextPolicyPlan,
        *,
        request_identity: str,
        request_sha256: str,
    ) -> ContextPolicyRecord:
        self._connection.cursor().executemany(
            """
            INSERT INTO mra.context_policy_metric (
                context_policy_metric_id, context_policy_id,
                metric_code, metric_ordinal, context_kind, measure,
                reducer, qualification_operator, lower_threshold,
                upper_threshold, minimum_source_count,
                minimum_available_count, missingness_policy,
                source_role, content_sha256
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s
            )
            """,
            (
                (
                    metric.context_policy_metric_id,
                    metric.context_policy_id,
                    metric.metric_code,
                    metric.ordinal,
                    metric.context_kind.value,
                    metric.measure.value,
                    metric.reducer.value,
                    metric.operator.value,
                    metric.lower_threshold,
                    metric.upper_threshold,
                    metric.minimum_source_count,
                    metric.minimum_available_count,
                    metric.missingness_policy.value,
                    metric.source_role.value,
                    metric.content_sha256,
                )
                for metric in plan.metrics
            ),
        )
        row = self._connection.execute(
            """
            INSERT INTO mra.context_policy (
                context_policy_id, policy_code, version,
                supersedes_policy_id, metric_count, kind_count,
                metric_roster_sha256, kind_roster_sha256,
                code_artifact_id, code_content_sha256, code_size_bytes,
                config_artifact_id, config_content_sha256,
                config_size_bytes, provenance_sha256, content_sha256,
                request_identity, request_sha256
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            RETURNING frozen_at
            """,
            (
                plan.context_policy_id,
                plan.policy_code,
                plan.version,
                plan.supersedes_policy_id,
                plan.metric_count,
                plan.kind_count,
                plan.metric_roster_sha256,
                plan.kind_roster_sha256,
                plan.code_artifact.artifact_id,
                plan.code_artifact.content_sha256,
                plan.code_artifact.size_bytes,
                plan.config_artifact.artifact_id,
                plan.config_artifact.content_sha256,
                plan.config_artifact.size_bytes,
                plan.provenance_sha256,
                plan.content_sha256,
                request_identity,
                request_sha256,
            ),
        ).fetchone()
        if row is None:
            raise ContextAuthorityIntegrityError("ContextPolicy insert returned no time")
        receipt = self._connection.execute(
            """
            SELECT receipt_id FROM mra.command_receipt
            WHERE command_kind = 'REGISTER_CONTEXT_POLICY'
              AND scope_id = %s AND idempotency_key = %s
              AND request_hash = %s
            """,
            (plan.policy_code, request_identity, request_sha256),
        ).fetchone()
        if receipt is None:
            raise ContextAuthorityIntegrityError("ContextPolicy receipt is absent")
        return ContextPolicyRecord(
            context_policy_id=plan.context_policy_id,
            policy_code=plan.policy_code,
            version=plan.version,
            metric_count=plan.metric_count,
            kind_count=plan.kind_count,
            content_sha256=plan.content_sha256,
            request_identity=request_identity,
            request_sha256=request_sha256,
            frozen_at=row[0],
            receipt_id=UUID(str(receipt[0])),
        )

    def policy_record(
        self,
        context_policy_id: UUID,
        *,
        lock: bool,
    ) -> ContextPolicyRecord:
        row = _policy_record_row(
            self._connection,
            "policy.context_policy_id = %s",
            (context_policy_id,),
            lock=lock,
        )
        if row is None:
            raise ContextAuthorityIntegrityError("ContextPolicy record is absent")
        return _policy_record(row)

    def insert_assessment(
        self,
        authority: ContextAssessmentAuthority,
    ) -> ContextAssessmentRecord:
        policy_row = self._connection.execute(
            """
            SELECT kind_count, kind_roster_sha256
            FROM mra.context_policy
            WHERE context_policy_id = %s AND content_sha256 = %s
            FOR SHARE
            """,
            (
                authority.context_policy_id,
                authority.context_policy_content_sha256,
            ),
        ).fetchone()
        if policy_row is None:
            raise ContextAuthorityIntegrityError(
                "exact ContextPolicy is absent during assessment"
            )
        with self._connection.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO mra.context_metric_source (
                    context_metric_source_id, context_metric_id,
                    context_assessment_id, context_policy_metric_id,
                    decision_run_id, candidate_set_id, candidate_id,
                    instrument_id, source_ordinal, source_role,
                    decision_reference_observation_id,
                    reference_known_at, reference_source_kind,
                    bar_revision_id, source_gap_id, value_status,
                    decimal_value, boolean_value, content_sha256,
                    created_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    (
                        source.context_metric_source_id,
                        metric.context_metric_id,
                        assessment.context_assessment_id,
                        metric.definition.context_policy_metric_id,
                        authority.decision_run_id,
                        authority.candidate_set_id,
                        source.source.candidate_id,
                        source.source.instrument_id,
                        source.source.source_ordinal,
                        metric.definition.source_role.value,
                        source.source.decision_reference_observation_id,
                        source.source.known_at,
                        source.source.source_kind.value,
                        source.source.bar_revision_id,
                        source.source.source_gap_id,
                        source.source.value_status.value,
                        source.source.decimal_value,
                        source.source.boolean_value,
                        source.content_sha256,
                        authority.recorded_at,
                    )
                    for assessment in authority.assessments
                    for metric in assessment.metrics
                    for source in metric.sources
                ),
            )
            cursor.executemany(
                """
                INSERT INTO mra.context_metric (
                    context_metric_id, context_assessment_id,
                    assessment_group_id, decision_run_id,
                    candidate_set_id, context_policy_id, context_kind,
                    context_policy_metric_id, definition_measure,
                    definition_reducer, definition_source_role,
                    definition_content_sha256, metric_status,
                    metric_state, decimal_value, source_count,
                    available_count, unavailable_count, failed_count,
                    source_roster_sha256, content_sha256, created_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    (
                        metric.context_metric_id,
                        assessment.context_assessment_id,
                        authority.assessment_group_id,
                        authority.decision_run_id,
                        authority.candidate_set_id,
                        authority.context_policy_id,
                        assessment.context_kind.value,
                        metric.definition.context_policy_metric_id,
                        metric.definition.measure.value,
                        metric.definition.reducer.value,
                        metric.definition.source_role.value,
                        metric.definition.content_sha256,
                        metric.status.value,
                        metric.state.value,
                        metric.decimal_value,
                        metric.source_count,
                        metric.available_count,
                        metric.unavailable_count,
                        metric.failed_count,
                        metric.source_roster_sha256,
                        metric.content_sha256,
                        authority.recorded_at,
                    )
                    for assessment in authority.assessments
                    for metric in assessment.metrics
                ),
            )
            cursor.executemany(
                """
                INSERT INTO mra.context_assessment (
                    context_assessment_id, assessment_group_id,
                    assessment_ordinal, assessment_count,
                    assessment_roster_sha256, decision_run_id,
                    candidate_set_id, candidate_set_content_sha256,
                    candidate_roster_sha256, decision_time,
                    candidate_count, context_policy_id,
                    context_policy_content_sha256, policy_kind_count,
                    policy_kind_roster_sha256, context_kind,
                    assessment_status, assessment_state, metric_count,
                    source_count, metric_roster_sha256,
                    request_identity, request_sha256, content_sha256,
                    recorded_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s
                )
                """,
                (
                    (
                        assessment.context_assessment_id,
                        authority.assessment_group_id,
                        assessment.ordinal,
                        authority.assessment_count,
                        authority.assessment_roster_sha256,
                        authority.decision_run_id,
                        authority.candidate_set_id,
                        authority.candidate_set_content_sha256,
                        authority.candidate_roster_sha256,
                        authority.decision_time,
                        authority.candidate_count,
                        authority.context_policy_id,
                        authority.context_policy_content_sha256,
                        int(policy_row[0]),
                        str(policy_row[1]),
                        assessment.context_kind.value,
                        assessment.status.value,
                        assessment.state.value,
                        assessment.metric_count,
                        sum(len(metric.sources) for metric in assessment.metrics),
                        assessment.metric_roster_sha256,
                        authority.request_identity,
                        authority.request_sha256,
                        assessment.content_sha256,
                        authority.recorded_at,
                    )
                    for assessment in authority.assessments
                ),
            )
        return ContextAssessmentRecord(
            assessment_group_id=authority.assessment_group_id,
            decision_run_id=authority.decision_run_id,
            context_policy_id=authority.context_policy_id,
            assessment_count=authority.assessment_count,
            metric_count=authority.metric_count,
            source_count=authority.source_count,
            assessment_roster_sha256=authority.assessment_roster_sha256,
            content_sha256=authority.content_sha256,
            request_identity=authority.request_identity,
            request_sha256=authority.request_sha256,
            recorded_at=authority.recorded_at,
            receipt_id=authority.command_receipt_id,
        )

    def assessment_record(
        self,
        assessment_group_id: UUID,
        *,
        lock: bool,
    ) -> ContextAssessmentRecord:
        record = _load_assessment_record(
            self._connection,
            decision_run_id=None,
            context_policy_id=None,
            request_identity=None,
            assessment_group_id=assessment_group_id,
            lock=lock,
        )
        if record is None:
            raise ContextAuthorityIntegrityError("ContextAssessment record is absent")
        return record

    def reconcile(
        self,
        assessment_group_id: UUID,
        *,
        lock: bool,
    ) -> ContextReconciliation:
        suffix = " FOR SHARE" if lock else ""
        roots = self._connection.execute(
            """
            SELECT context_assessment_id, assessment_ordinal,
                   assessment_count, assessment_roster_sha256,
                   content_sha256, metric_count, source_count
            FROM mra.context_assessment
            WHERE assessment_group_id = %s
            ORDER BY assessment_ordinal
            """
            + suffix,
            (assessment_group_id,),
        ).fetchall()
        if not roots:
            return ContextReconciliation(
                assessment_group_id=assessment_group_id,
                actual_assessment_count=0,
                actual_metric_count=0,
                actual_source_count=0,
                assessment_roster_sha256="0" * 64,
                matched=False,
            )
        roster_hash = canonical_json_sha256(
            tuple(
                {
                    "content_sha256": str(row[4]),
                    "context_assessment_id": UUID(str(row[0])),
                    "ordinal": int(row[1]),
                }
                for row in roots
            )
        )
        count_row = self._connection.execute(
            """
            SELECT count(DISTINCT metric.context_metric_id),
                   count(source.context_metric_source_id)
            FROM mra.context_metric AS metric
            LEFT JOIN mra.context_metric_source AS source
              ON source.context_metric_id = metric.context_metric_id
            WHERE metric.assessment_group_id = %s
            """,
            (assessment_group_id,),
        ).fetchone()
        if count_row is None:
            raise ContextAuthorityIntegrityError("Context counts are absent")
        metric_count, source_count = count_row
        matched = (
            len(roots) == int(roots[0][2])
            and tuple(int(row[1]) for row in roots)
            == tuple(range(1, len(roots) + 1))
            and all(str(row[3]) == roster_hash for row in roots)
            and sum(int(row[5]) for row in roots) == int(metric_count)
            and sum(int(row[6]) for row in roots) == int(source_count)
        )
        return ContextReconciliation(
            assessment_group_id=assessment_group_id,
            actual_assessment_count=len(roots),
            actual_metric_count=int(metric_count),
            actual_source_count=int(source_count),
            assessment_roster_sha256=roster_hash,
            matched=matched,
        )


__all__ = ["PostgresContextRepository"]
