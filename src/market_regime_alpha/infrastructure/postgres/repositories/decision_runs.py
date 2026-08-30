"""PostgreSQL persistence for the immutable Decision Run aggregate."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import psycopg

from market_regime_alpha.decision_support.domain import DecisionRunAuthority
from market_regime_alpha.decision_support.ports import DecisionRunReconciliation


class PostgresDecisionRunRepository:
    def __init__(self, connection: psycopg.Connection[Any]) -> None:
        self._connection = connection

    def lock_candidate_set_identity(self, candidate_set_id: UUID) -> None:
        self._connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"decision-run:candidate-set:{candidate_set_id}",),
        )

    def authoritative_recorded_at(self):
        row = self._connection.execute("SELECT clock_timestamp()").fetchone()
        if row is None:
            raise RuntimeError("PostgreSQL did not return its authoritative clock")
        return row[0]

    def insert(self, authority: DecisionRunAuthority) -> None:
        with self._connection.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO mra.decision_run_target (
                    decision_run_target_id, decision_run_id, ordinal,
                    target_definition_id, target_code, target_version,
                    target_definition_sha256, target_checkpoint_id,
                    target_checkpoint_sha256, target_checkpoint_ordinal,
                    target_checkpoint_role, timeframe, price_basis,
                    value_field, reference_rule, availability_rule,
                    finality_rule, reference_provider_product_id,
                    reference_provider_id, reference_provider_product_code,
                    reference_provider_product_revision,
                    decision_visibility_policy, source_availability_policy,
                    commitment_recorded_at, content_sha256, created_at
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    'DECISION_REFERENCE', %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    (
                        item.decision_run_target_id,
                        authority.decision_run_id,
                        item.ordinal,
                        item.target.target_definition_id,
                        item.target.target_code,
                        item.target.version,
                        item.target.content_sha256,
                        item.target.target_checkpoint_id,
                        item.target.checkpoint_content_sha256,
                        item.target.checkpoint_ordinal,
                        item.target.timeframe,
                        item.target.price_basis,
                        item.target.value_field,
                        item.target.reference_rule,
                        item.target.availability_rule,
                        item.target.finality_rule,
                        item.target.reference_provider_product.provider_product_id,
                        item.target.reference_provider_product.provider_id,
                        item.target.reference_provider_product.product_code,
                        item.target.reference_provider_product.revision,
                        item.target.reference_provider_product.decision_visibility_policy,
                        item.target.reference_provider_product.source_availability_policy,
                        authority.commitment_recorded_at,
                        item.content_sha256,
                        authority.commitment_recorded_at,
                    )
                    for item in authority.targets
                ),
            )
            cursor.executemany(
                """
                INSERT INTO mra.decision_target_commitment (
                    commitment_id, decision_run_id, decision_run_target_id,
                    candidate_set_id, candidate_id, instrument_id,
                    candidate_disposition, target_definition_id,
                    target_checkpoint_id, reference_provider_product_id,
                    decision_time, runtime_mode, commitment_recorded_at,
                    decision_reference_observation_id,
                    decision_reference_sha256, content_sha256, created_at
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    (
                        item.commitment_id,
                        authority.decision_run_id,
                        item.decision_run_target_id,
                        item.candidate_set_id,
                        item.candidate_id,
                        item.instrument_id,
                        item.candidate_disposition.value,
                        item.target_definition_id,
                        item.reference.target_checkpoint_id,
                        item.reference.prepared.provider_product_id,
                        item.decision_time,
                        item.runtime_mode.value,
                        item.commitment_recorded_at,
                        item.reference.decision_reference_observation_id,
                        item.reference.content_sha256,
                        item.content_sha256,
                        item.commitment_recorded_at,
                    )
                    for item in authority.commitments
                ),
            )
            cursor.executemany(
                """
                INSERT INTO mra.decision_reference_observation (
                    decision_reference_observation_id, commitment_id,
                    decision_run_id, decision_run_target_id,
                    candidate_set_id, candidate_id, target_definition_id,
                    target_checkpoint_id, instrument_id,
                    reference_provider_product_id, reference_provider_id,
                    capture_id, session_id, timeframe, price_basis,
                    value_field, event_start, event_end, observation_time,
                    source_recorded_at, known_at, decision_time, runtime_mode,
                    commitment_recorded_at, source_kind, value_status,
                    availability_status, finality_status, decimal_value,
                    bar_revision_id, bar_revision, source_gap_id,
                    source_gap_kind, source_gap_reason_code, content_sha256,
                    created_at
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    _reference_parameters(item, authority)
                    for item in authority.commitments
                ),
            )

        candidate = authority.candidate_set
        runtime = authority.runtime
        self._connection.execute(
            """
            INSERT INTO mra.decision_run (
                decision_run_id, status, candidate_set_id,
                candidate_set_content_sha256, dataset_id,
                candidate_policy_id, candidate_count, selected_count,
                ranked_not_selected_count, unrankable_count,
                candidate_roster_sha256, target_count,
                target_roster_sha256, commitment_count, reference_count,
                commitment_roster_sha256, runtime_mode, decision_time,
                commitment_recorded_at, request_received_at,
                runtime_run_id, runtime_step_id, runtime_attempt_id,
                runtime_fence_token, runtime_step_key, runtime_step_kind,
                code_sha, config_artifact_id, config_hash,
                request_kind, request_scope_id, request_identity,
                request_sha256, command_receipt_id,
                created_by_actor_type, created_by_actor_id,
                creation_reason_code, definition_summary_sha256, created_at
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s,
                'OPEN_DECISION_RUN', %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            (
                authority.decision_run_id,
                authority.status.value,
                candidate.candidate_set_id,
                candidate.content_sha256,
                candidate.dataset_id,
                candidate.candidate_policy_id,
                authority.candidate_count,
                candidate.selected_count,
                candidate.ranked_not_selected_count,
                candidate.unrankable_count,
                authority.candidate_roster_sha256,
                authority.target_count,
                authority.target_roster_sha256,
                authority.commitment_count,
                authority.reference_count,
                authority.commitment_roster_sha256,
                runtime.runtime_mode.value,
                runtime.decision_time,
                authority.commitment_recorded_at,
                authority.request_received_at,
                runtime.run_id,
                runtime.step_id,
                runtime.attempt_id,
                runtime.fence_token,
                runtime.step_key,
                runtime.step_kind,
                runtime.code_sha,
                runtime.config_artifact_id,
                runtime.config_hash,
                str(candidate.candidate_set_id),
                authority.request_identity,
                authority.request_sha256,
                authority.command_receipt_id,
                authority.actor_type,
                authority.actor_id,
                authority.reason_code,
                authority.definition_summary_sha256,
                authority.commitment_recorded_at,
            ),
        )

    def reconcile(
        self,
        decision_run_id: UUID,
        *,
        lock: bool,
    ) -> DecisionRunReconciliation:
        suffix = " FOR SHARE" if lock else ""
        root = self._connection.execute(
            """
            SELECT candidate_set_id, target_count, commitment_count,
                   reference_count, candidate_roster_sha256,
                   target_roster_sha256, commitment_roster_sha256
            FROM mra.decision_run
            WHERE decision_run_id = %s
            """
            + suffix,
            (decision_run_id,),
        ).fetchone()
        if root is None:
            return DecisionRunReconciliation(
                decision_run_id=decision_run_id,
                actual_target_count=0,
                actual_commitment_count=0,
                actual_reference_count=0,
                missing_commitment_count=0,
                extra_commitment_count=0,
                candidate_roster_sha256="0" * 64,
                target_roster_sha256="0" * 64,
                commitment_roster_sha256="0" * 64,
                matched=False,
            )
        actual = self._connection.execute(
            """
            WITH actual_counts AS (
                SELECT
                  (SELECT count(*) FROM mra.decision_run_target
                   WHERE decision_run_id = %(decision_run_id)s) AS target_count,
                  (SELECT count(*) FROM mra.decision_target_commitment
                   WHERE decision_run_id = %(decision_run_id)s) AS commitment_count,
                  (SELECT count(*) FROM mra.decision_reference_observation
                   WHERE decision_run_id = %(decision_run_id)s) AS reference_count
            ), missing AS (
                SELECT count(*) AS count
                FROM mra.candidate AS candidate
                CROSS JOIN mra.decision_run_target AS target
                LEFT JOIN mra.decision_target_commitment AS commitment
                  ON commitment.decision_run_id = target.decision_run_id
                 AND commitment.decision_run_target_id =
                     target.decision_run_target_id
                 AND commitment.candidate_id = candidate.candidate_id
                WHERE candidate.candidate_set_id = %(candidate_set_id)s
                  AND target.decision_run_id = %(decision_run_id)s
                  AND commitment.commitment_id IS NULL
            ), extra AS (
                SELECT count(*) AS count
                FROM mra.decision_target_commitment AS commitment
                LEFT JOIN mra.candidate AS candidate
                  ON candidate.candidate_id = commitment.candidate_id
                 AND candidate.candidate_set_id = %(candidate_set_id)s
                LEFT JOIN mra.decision_run_target AS target
                  ON target.decision_run_target_id =
                     commitment.decision_run_target_id
                 AND target.decision_run_id = %(decision_run_id)s
                WHERE commitment.decision_run_id = %(decision_run_id)s
                  AND (candidate.candidate_id IS NULL
                       OR target.decision_run_target_id IS NULL)
            ), hashes AS (
                SELECT
                  (SELECT mra.canonical_sha256(
                      replace(COALESCE(json_agg(json_build_object(
                        'candidate_id', candidate_id,
                        'disposition', disposition,
                        'instrument_id', instrument_id
                      ) ORDER BY candidate_id)::text, '[]'), ' ', ''))
                   FROM mra.candidate
                   WHERE candidate_set_id = %(candidate_set_id)s)
                    AS candidate_hash,
                  (SELECT mra.canonical_sha256(
                      replace(json_agg(json_build_object(
                        'content_sha256', content_sha256,
                        'decision_run_target_id', decision_run_target_id,
                        'ordinal', ordinal
                      ) ORDER BY ordinal)::text, ' ', ''))
                   FROM mra.decision_run_target
                   WHERE decision_run_id = %(decision_run_id)s)
                    AS target_hash,
                  (SELECT mra.canonical_sha256(
                      replace(COALESCE(json_agg(json_build_object(
                        'commitment_id', commitment.commitment_id,
                        'content_sha256', commitment.content_sha256,
                        'decision_run_target_id',
                          commitment.decision_run_target_id
                      ) ORDER BY target.ordinal, commitment.candidate_id)::text,
                      '[]'), ' ', ''))
                   FROM mra.decision_target_commitment AS commitment
                   JOIN mra.decision_run_target AS target
                     ON target.decision_run_target_id =
                        commitment.decision_run_target_id
                   WHERE commitment.decision_run_id = %(decision_run_id)s)
                    AS commitment_hash
            )
            SELECT actual_counts.target_count,
                   actual_counts.commitment_count,
                   actual_counts.reference_count,
                   missing.count, extra.count,
                   hashes.candidate_hash, hashes.target_hash,
                   hashes.commitment_hash
            FROM actual_counts, missing, extra, hashes
            """,
            {
                "decision_run_id": decision_run_id,
                "candidate_set_id": UUID(str(root[0])),
            },
        ).fetchone()
        assert actual is not None
        matched = (
            int(actual[0]) == int(root[1])
            and int(actual[1]) == int(root[2])
            and int(actual[2]) == int(root[3])
            and int(actual[3]) == 0
            and int(actual[4]) == 0
            and str(actual[5]) == str(root[4])
            and str(actual[6]) == str(root[5])
            and str(actual[7]) == str(root[6])
        )
        return DecisionRunReconciliation(
            decision_run_id=decision_run_id,
            actual_target_count=int(actual[0]),
            actual_commitment_count=int(actual[1]),
            actual_reference_count=int(actual[2]),
            missing_commitment_count=int(actual[3]),
            extra_commitment_count=int(actual[4]),
            candidate_roster_sha256=str(actual[5]),
            target_roster_sha256=str(actual[6]),
            commitment_roster_sha256=str(actual[7]),
            matched=matched,
        )


def _reference_parameters(item, authority: DecisionRunAuthority):
    reference = item.reference
    source = reference.prepared
    return (
        reference.decision_reference_observation_id,
        item.commitment_id,
        authority.decision_run_id,
        item.decision_run_target_id,
        item.candidate_set_id,
        item.candidate_id,
        item.target_definition_id,
        reference.target_checkpoint_id,
        item.instrument_id,
        source.provider_product_id,
        source.provider_id,
        source.capture_id,
        source.session_id,
        source.timeframe,
        source.price_basis,
        source.value_field,
        source.event_start,
        source.event_end,
        source.observation_time,
        source.recorded_at,
        source.known_at,
        item.decision_time,
        item.runtime_mode.value,
        item.commitment_recorded_at,
        source.source_kind.value,
        source.value_status.value,
        source.availability_status.value,
        source.finality_status.value,
        source.decimal_value,
        source.bar_revision_id,
        source.bar_revision,
        source.source_gap_id,
        source.source_gap_kind,
        source.source_gap_reason_code,
        reference.content_sha256,
        item.commitment_recorded_at,
    )


__all__ = ["PostgresDecisionRunRepository"]
