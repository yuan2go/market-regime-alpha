"""PostgreSQL writer for append-only Market Target Outcome revisions."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import psycopg

from market_regime_alpha.outcome.domain import (
    MarketTargetOutcomeAuthority,
    OutcomeBarSource,
    OutcomeGapSource,
)
from market_regime_alpha.outcome.ports import OutcomeHead, OutcomeReconciliation


class PostgresOutcomeRepository:
    def __init__(self, connection: psycopg.Connection[Any]) -> None:
        self._connection = connection

    def lock_scope_and_head(self, commitment_id: UUID) -> OutcomeHead | None:
        self._connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"market-target-outcome:commitment:{commitment_id}",),
        )
        row = self._connection.execute(
            """
            SELECT root.market_target_outcome_id,
                   revision.market_target_outcome_revision_id,
                   revision.revision_ordinal
            FROM mra.market_target_outcome AS root
            JOIN mra.market_target_outcome_revision AS revision
              ON revision.market_target_outcome_id = root.market_target_outcome_id
            WHERE root.commitment_id = %s
              AND NOT EXISTS (
                  SELECT 1
                  FROM mra.market_target_outcome_revision AS successor
                  WHERE successor.supersedes_revision_id =
                        revision.market_target_outcome_revision_id
              )
            FOR UPDATE OF root
            """,
            (commitment_id,),
        ).fetchone()
        if row is None:
            return None
        return OutcomeHead(
            market_target_outcome_id=UUID(str(row[0])),
            market_target_outcome_revision_id=UUID(str(row[1])),
            revision_ordinal=int(row[2]),
        )

    def authoritative_settled_at(self):
        row = self._connection.execute("SELECT clock_timestamp()").fetchone()
        if row is None:
            raise RuntimeError("PostgreSQL did not return its authoritative clock")
        return row[0]

    def insert(
        self,
        authority: MarketTargetOutcomeAuthority,
        *,
        create_root: bool,
    ) -> None:
        if create_root:
            self._insert_root(authority)
        self._insert_sources(authority)
        self._insert_observations(authority)
        self._insert_metrics(authority)
        self._insert_reference_dependencies(authority)
        self._insert_observation_dependencies(authority)
        self._insert_reasons(authority)
        self._insert_revision(authority)

    def _insert_root(self, authority: MarketTargetOutcomeAuthority) -> None:
        root = authority.root
        commitment = authority.commitment
        self._connection.execute(
            """
            INSERT INTO mra.market_target_outcome (
                market_target_outcome_id, commitment_id, decision_run_id,
                decision_run_target_id, candidate_set_id, candidate_id,
                target_definition_id, target_version,
                target_definition_sha256, target_checkpoint_id,
                instrument_id, reference_provider_product_id,
                decision_time, runtime_mode, commitment_recorded_at,
                decision_reference_observation_id,
                decision_reference_sha256, created_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            (
                root.market_target_outcome_id,
                commitment.commitment_id,
                commitment.decision_run_id,
                commitment.decision_run_target_id,
                commitment.candidate_set_id,
                commitment.candidate_id,
                commitment.target_definition_id,
                commitment.target_version,
                commitment.target_definition_sha256,
                commitment.target_checkpoint_id,
                commitment.instrument_id,
                commitment.reference_provider_product_id,
                commitment.decision_time,
                commitment.runtime_mode,
                commitment.commitment_recorded_at,
                commitment.decision_reference_observation_id,
                commitment.decision_reference_sha256,
                root.created_at,
            ),
        )

    def _insert_sources(self, authority: MarketTargetOutcomeAuthority) -> None:
        revision = authority.revision
        with self._connection.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO mra.market_target_outcome_source (
                    market_target_outcome_source_id,
                    market_target_outcome_revision_id,
                    market_target_outcome_id, revision_ordinal,
                    source_ordinal, source_role, source_kind,
                    target_definition_id, target_checkpoint_id,
                    provider_product_id, capture_id,
                    session_provider_product_id, session_capture_id,
                    instrument_id, trading_session_id, session_offset,
                    exchange, session_date, timezone_name,
                    session_open_at, session_close_at,
                    timeframe, price_basis, event_start, event_end,
                    source_recorded_at, known_at,
                    session_recorded_at, session_known_at,
                    bar_revision_id, bar_revision, source_gap_id,
                    source_gap_kind, source_gap_reason_code,
                    observation_cutoff, knowledge_cutoff,
                    content_sha256, created_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    _source_parameters(authority, item)
                    for item in revision.sources
                ),
            )

    def _insert_observations(
        self,
        authority: MarketTargetOutcomeAuthority,
    ) -> None:
        revision = authority.revision
        with self._connection.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO mra.market_target_outcome_observation (
                    market_target_outcome_observation_id,
                    market_target_outcome_revision_id,
                    market_target_outcome_id, revision_ordinal,
                    observation_ordinal, target_definition_id,
                    target_checkpoint_id, market_target_outcome_source_id,
                    source_kind, value_status, availability_status,
                    finality_status, selected_value, open_value, high_value,
                    low_value, close_value, event_start, event_end, known_at,
                    observation_cutoff, knowledge_cutoff,
                    content_sha256, created_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s
                )
                """,
                (
                    (
                        item.market_target_outcome_observation_id,
                        revision.market_target_outcome_revision_id,
                        revision.market_target_outcome_id,
                        revision.revision_ordinal,
                        item.ordinal,
                        authority.target.target_definition_id,
                        draft.target_checkpoint_id,
                        item.market_target_outcome_source_id,
                        draft.source_kind.value,
                        draft.status.value,
                        draft.availability_status.value,
                        draft.finality_status.value,
                        draft.selected_value,
                        draft.open_value,
                        draft.high_value,
                        draft.low_value,
                        draft.close_value,
                        draft.event_start,
                        draft.event_end,
                        draft.known_at,
                        revision.draft.observation_cutoff,
                        revision.draft.knowledge_cutoff,
                        item.content_sha256,
                        revision.settled_at,
                    )
                    for item in revision.observations
                    for draft in (revision.draft.observations[item.draft_index],)
                ),
            )

    def _insert_metrics(self, authority: MarketTargetOutcomeAuthority) -> None:
        revision = authority.revision
        definitions = {
            item.target_metric_definition_id: item
            for item in authority.target.metrics
        }
        with self._connection.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO mra.market_target_outcome_metric (
                    market_target_outcome_metric_id,
                    market_target_outcome_revision_id,
                    market_target_outcome_id, revision_ordinal,
                    target_definition_id, target_metric_definition_id,
                    metric_ordinal, metric_code, metric_kind, value_type,
                    unit, completion_rule, barrier_direction,
                    barrier_threshold, value_status, availability_status,
                    finality_status, decimal_value, boolean_value,
                    first_passage_at, algorithm_code, algorithm_version,
                    algorithm_sha256, code_artifact_id,
                    code_content_sha256, code_size_bytes,
                    config_artifact_id, config_content_sha256,
                    config_size_bytes, target_metric_sha256,
                    content_sha256, created_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s
                )
                """,
                (
                    (
                        item.market_target_outcome_metric_id,
                        revision.market_target_outcome_revision_id,
                        revision.market_target_outcome_id,
                        revision.revision_ordinal,
                        authority.target.target_definition_id,
                        draft.target_metric_definition_id,
                        draft.ordinal,
                        draft.metric_code,
                        draft.metric_kind.value,
                        draft.value_type.value,
                        draft.unit,
                        draft.completion_rule.value,
                        (
                            None
                            if definition.barrier_direction is None
                            else definition.barrier_direction.value
                        ),
                        definition.barrier_threshold,
                        draft.status.value,
                        draft.availability_status.value,
                        draft.finality_status.value,
                        draft.decimal_value,
                        draft.boolean_value,
                        draft.first_passage_at,
                        draft.algorithm_code,
                        draft.algorithm_version,
                        draft.algorithm_sha256,
                        draft.code_artifact_id,
                        draft.code_content_sha256,
                        draft.code_size_bytes,
                        draft.config_artifact_id,
                        draft.config_content_sha256,
                        draft.config_size_bytes,
                        draft.target_metric_sha256,
                        item.content_sha256,
                        revision.settled_at,
                    )
                    for item in revision.metrics
                    for draft in (revision.draft.metrics[item.draft_index],)
                    for definition in (
                        definitions[draft.target_metric_definition_id],
                    )
                ),
            )

    def _insert_reference_dependencies(
        self,
        authority: MarketTargetOutcomeAuthority,
    ) -> None:
        revision = authority.revision
        with self._connection.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO mra.market_target_outcome_metric_reference (
                    market_target_outcome_metric_reference_id,
                    market_target_outcome_revision_id,
                    market_target_outcome_id, revision_ordinal,
                    dependency_ordinal, target_definition_id,
                    target_metric_definition_id,
                    market_target_outcome_metric_id,
                    target_metric_dependency_id, target_checkpoint_id,
                    dependency_role, target_dependency_sha256,
                    decision_reference_observation_id,
                    content_sha256, created_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s
                )
                """,
                (
                    (
                        item.market_target_outcome_metric_reference_id,
                        revision.market_target_outcome_revision_id,
                        revision.market_target_outcome_id,
                        revision.revision_ordinal,
                        item.ordinal,
                        authority.target.target_definition_id,
                        draft.target_metric_definition_id,
                        item.market_target_outcome_metric_id,
                        draft.target_metric_dependency_id,
                        draft.target_checkpoint_id,
                        draft.dependency_role.value,
                        item.target_dependency_sha256,
                        draft.decision_reference_observation_id,
                        item.content_sha256,
                        revision.settled_at,
                    )
                    for item in revision.reference_dependencies
                    for draft in (
                        revision.draft.reference_dependencies[item.draft_index],
                    )
                ),
            )

    def _insert_observation_dependencies(
        self,
        authority: MarketTargetOutcomeAuthority,
    ) -> None:
        revision = authority.revision
        with self._connection.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO mra.market_target_outcome_metric_observation (
                    market_target_outcome_metric_observation_id,
                    market_target_outcome_revision_id,
                    market_target_outcome_id, revision_ordinal,
                    dependency_ordinal, target_definition_id,
                    target_metric_definition_id,
                    market_target_outcome_metric_id,
                    target_metric_dependency_id, target_checkpoint_id,
                    dependency_role, target_dependency_sha256,
                    market_target_outcome_observation_id,
                    content_sha256, created_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s
                )
                """,
                (
                    (
                        item.market_target_outcome_metric_observation_id,
                        revision.market_target_outcome_revision_id,
                        revision.market_target_outcome_id,
                        revision.revision_ordinal,
                        item.ordinal,
                        authority.target.target_definition_id,
                        draft.target_metric_definition_id,
                        item.market_target_outcome_metric_id,
                        draft.target_metric_dependency_id,
                        draft.target_checkpoint_id,
                        draft.dependency_role.value,
                        item.target_dependency_sha256,
                        item.market_target_outcome_observation_id,
                        item.content_sha256,
                        revision.settled_at,
                    )
                    for item in revision.observation_dependencies
                    for draft in (
                        revision.draft.observation_dependencies[item.draft_index],
                    )
                ),
            )

    def _insert_reasons(self, authority: MarketTargetOutcomeAuthority) -> None:
        revision = authority.revision
        if not revision.reasons:
            return
        with self._connection.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO mra.market_target_outcome_reason (
                    market_target_outcome_reason_id,
                    market_target_outcome_revision_id,
                    market_target_outcome_id, revision_ordinal,
                    reason_ordinal, reason_dimension, reason_code,
                    market_target_outcome_source_id,
                    market_target_outcome_observation_id,
                    market_target_outcome_metric_id,
                    content_sha256, created_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s
                )
                """,
                (
                    (
                        item.market_target_outcome_reason_id,
                        revision.market_target_outcome_revision_id,
                        revision.market_target_outcome_id,
                        revision.revision_ordinal,
                        item.ordinal,
                        draft.dimension.value,
                        draft.reason_code,
                        item.market_target_outcome_source_id,
                        item.market_target_outcome_observation_id,
                        item.market_target_outcome_metric_id,
                        item.content_sha256,
                        revision.settled_at,
                    )
                    for item in revision.reasons
                    for draft in (revision.draft.reasons[item.draft_index],)
                ),
            )

    def _insert_revision(self, authority: MarketTargetOutcomeAuthority) -> None:
        revision = authority.revision
        draft = revision.draft
        runtime = revision.runtime
        self._connection.execute(
            """
            INSERT INTO mra.market_target_outcome_revision (
                market_target_outcome_revision_id,
                market_target_outcome_id, revision_ordinal,
                supersedes_revision_id, supersedes_revision_ordinal,
                commitment_id, target_definition_id,
                decision_reference_observation_id,
                decision_reference_sha256, observation_cutoff,
                knowledge_cutoff, outcome_status, availability_status,
                finality_status, source_count, source_roster_sha256,
                observation_count, observation_roster_sha256,
                metric_count, metric_roster_sha256,
                reference_dependency_count,
                reference_dependency_roster_sha256,
                observation_dependency_count,
                observation_dependency_roster_sha256,
                reason_count, reason_roster_sha256,
                definition_summary_sha256, request_received_at, settled_at,
                runtime_run_id, runtime_step_id, runtime_attempt_id,
                runtime_fence_token, runtime_step_key, runtime_step_kind,
                runtime_mode, runtime_decision_time, runtime_code_sha,
                runtime_config_artifact_id, runtime_config_hash,
                request_kind, request_scope_id, request_identity,
                request_sha256, command_receipt_id,
                created_by_actor_type, created_by_actor_id,
                creation_reason_code, created_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                'SETTLE_MARKET_TARGET_OUTCOME', %s, %s, %s, %s,
                %s, %s, %s, %s
            )
            """,
            (
                revision.market_target_outcome_revision_id,
                revision.market_target_outcome_id,
                revision.revision_ordinal,
                revision.supersedes_revision_id,
                revision.supersedes_revision_ordinal,
                authority.commitment.commitment_id,
                authority.target.target_definition_id,
                authority.commitment.decision_reference_observation_id,
                authority.commitment.decision_reference_sha256,
                draft.observation_cutoff,
                draft.knowledge_cutoff,
                draft.status.value,
                draft.availability_status.value,
                draft.finality_status.value,
                revision.source_count,
                revision.source_roster_sha256,
                revision.observation_count,
                revision.observation_roster_sha256,
                revision.metric_count,
                revision.metric_roster_sha256,
                revision.reference_dependency_count,
                revision.reference_dependency_roster_sha256,
                revision.observation_dependency_count,
                revision.observation_dependency_roster_sha256,
                revision.reason_count,
                revision.reason_roster_sha256,
                revision.definition_summary_sha256,
                revision.request_received_at,
                revision.settled_at,
                runtime.run_id,
                runtime.step_id,
                runtime.attempt_id,
                runtime.fence_token,
                runtime.step_key,
                runtime.step_kind,
                runtime.runtime_mode,
                runtime.decision_time,
                runtime.code_sha,
                runtime.config_artifact_id,
                runtime.config_hash,
                str(authority.commitment.commitment_id),
                revision.request_identity,
                revision.request_sha256,
                revision.command_receipt_id,
                revision.actor_type,
                revision.actor_id,
                revision.reason_code,
                revision.settled_at,
            ),
        )

    def reconcile(
        self,
        revision_id: UUID,
        *,
        lock: bool,
    ) -> OutcomeReconciliation:
        suffix = " FOR SHARE" if lock else ""
        root = self._connection.execute(
            """
            SELECT source_count, observation_count, metric_count,
                   reference_dependency_count,
                   observation_dependency_count, reason_count,
                   source_roster_sha256, observation_roster_sha256,
                   metric_roster_sha256,
                   reference_dependency_roster_sha256,
                   observation_dependency_roster_sha256,
                   reason_roster_sha256, definition_summary_sha256
            FROM mra.market_target_outcome_revision
            WHERE market_target_outcome_revision_id = %s
            """
            + suffix,
            (revision_id,),
        ).fetchone()
        if root is None:
            return _empty_reconciliation(revision_id)
        rows = self._connection.execute(
            """
            SELECT
              (SELECT count(*) FROM mra.market_target_outcome_source
               WHERE market_target_outcome_revision_id = %(revision_id)s),
              (SELECT count(*) FROM mra.market_target_outcome_observation
               WHERE market_target_outcome_revision_id = %(revision_id)s),
              (SELECT count(*) FROM mra.market_target_outcome_metric
               WHERE market_target_outcome_revision_id = %(revision_id)s),
              (SELECT count(*) FROM mra.market_target_outcome_metric_reference
               WHERE market_target_outcome_revision_id = %(revision_id)s),
              (SELECT count(*) FROM mra.market_target_outcome_metric_observation
               WHERE market_target_outcome_revision_id = %(revision_id)s),
              (SELECT count(*) FROM mra.market_target_outcome_reason
               WHERE market_target_outcome_revision_id = %(revision_id)s),
              (SELECT mra.canonical_sha256(replace(COALESCE(json_agg(
                 json_build_object(
                   'content_sha256', content_sha256,
                   'market_target_outcome_source_id',
                     market_target_outcome_source_id,
                   'ordinal', source_ordinal
                 ) ORDER BY source_ordinal)::text, '[]'), ' ', ''))
               FROM mra.market_target_outcome_source
               WHERE market_target_outcome_revision_id = %(revision_id)s),
              (SELECT mra.canonical_sha256(replace(COALESCE(json_agg(
                 json_build_object(
                   'content_sha256', content_sha256,
                   'market_target_outcome_observation_id',
                     market_target_outcome_observation_id,
                   'ordinal', observation_ordinal
                 ) ORDER BY observation_ordinal)::text, '[]'), ' ', ''))
               FROM mra.market_target_outcome_observation
               WHERE market_target_outcome_revision_id = %(revision_id)s),
              (SELECT mra.canonical_sha256(replace(COALESCE(json_agg(
                 json_build_object(
                   'content_sha256', content_sha256,
                   'market_target_outcome_metric_id',
                     market_target_outcome_metric_id,
                   'ordinal', metric_ordinal
                 ) ORDER BY metric_ordinal)::text, '[]'), ' ', ''))
               FROM mra.market_target_outcome_metric
               WHERE market_target_outcome_revision_id = %(revision_id)s),
              (SELECT mra.canonical_sha256(replace(COALESCE(json_agg(
                 json_build_object(
                   'content_sha256', content_sha256,
                   'market_target_outcome_metric_reference_id',
                     market_target_outcome_metric_reference_id,
                   'ordinal', dependency_ordinal
                 ) ORDER BY dependency_ordinal)::text, '[]'), ' ', ''))
               FROM mra.market_target_outcome_metric_reference
               WHERE market_target_outcome_revision_id = %(revision_id)s),
              (SELECT mra.canonical_sha256(replace(COALESCE(json_agg(
                 json_build_object(
                   'content_sha256', content_sha256,
                   'market_target_outcome_metric_observation_id',
                     market_target_outcome_metric_observation_id,
                   'ordinal', dependency_ordinal
                 ) ORDER BY dependency_ordinal)::text, '[]'), ' ', ''))
               FROM mra.market_target_outcome_metric_observation
               WHERE market_target_outcome_revision_id = %(revision_id)s),
              (SELECT mra.canonical_sha256(replace(COALESCE(json_agg(
                 json_build_object(
                   'content_sha256', content_sha256,
                   'market_target_outcome_reason_id',
                     market_target_outcome_reason_id,
                   'ordinal', reason_ordinal
                 ) ORDER BY reason_ordinal)::text, '[]'), ' ', ''))
               FROM mra.market_target_outcome_reason
               WHERE market_target_outcome_revision_id = %(revision_id)s)
            """,
            {"revision_id": revision_id},
        ).fetchone()
        assert rows is not None
        actual_values = tuple(int(value) for value in rows[:6])
        actual_hashes = tuple(str(value) for value in rows[6:])
        matched = actual_values == tuple(int(value) for value in root[:6]) and (
            actual_hashes == tuple(str(value) for value in root[6:12])
        )
        return OutcomeReconciliation(
            market_target_outcome_revision_id=revision_id,
            source_count=actual_values[0],
            observation_count=actual_values[1],
            metric_count=actual_values[2],
            reference_dependency_count=actual_values[3],
            observation_dependency_count=actual_values[4],
            reason_count=actual_values[5],
            source_roster_sha256=actual_hashes[0],
            observation_roster_sha256=actual_hashes[1],
            metric_roster_sha256=actual_hashes[2],
            reference_dependency_roster_sha256=actual_hashes[3],
            observation_dependency_roster_sha256=actual_hashes[4],
            reason_roster_sha256=actual_hashes[5],
            definition_summary_sha256=str(root[12]),
            matched=matched,
        )


def _source_parameters(authority, item):
    revision = authority.revision
    session = item.session
    source = item.observation_source
    if source is None:
        provider_product_id = session.provider_product_id
        capture_id = session.source_capture_id
        instrument_id = None
        timeframe = None
        price_basis = None
        event_start = None
        event_end = None
        source_recorded_at = session.recorded_at
        known_at = session.known_at
        bar_revision_id = None
        bar_revision = None
        source_gap_id = None
        source_gap_kind = None
        source_gap_reason = None
        source_kind = "TRADING_SESSION"
        source_role = item.source_role.value
    else:
        provider_product_id = source.provider_product_id
        capture_id = source.capture_id
        instrument_id = source.instrument_id
        timeframe = source.timeframe
        price_basis = source.price_basis
        event_start = source.event_start
        event_end = source.event_end
        source_recorded_at = source.recorded_at
        known_at = source.known_at
        source_kind = source.source_kind.value
        source_role = item.source_role.value
        if isinstance(source, OutcomeBarSource):
            bar_revision_id = source.bar_revision_id
            bar_revision = source.revision
            source_gap_id = None
            source_gap_kind = None
            source_gap_reason = None
        else:
            assert isinstance(source, OutcomeGapSource)
            bar_revision_id = None
            bar_revision = None
            source_gap_id = source.gap_id
            source_gap_kind = source.gap_kind.value
            source_gap_reason = source.reason_code
    return (
        item.market_target_outcome_source_id,
        revision.market_target_outcome_revision_id,
        revision.market_target_outcome_id,
        revision.revision_ordinal,
        item.ordinal,
        source_role,
        source_kind,
        authority.target.target_definition_id,
        item.target_checkpoint_id,
        provider_product_id,
        capture_id,
        session.provider_product_id,
        session.source_capture_id,
        instrument_id,
        session.session_id,
        session.session_offset,
        session.exchange,
        session.session_date,
        session.timezone_name,
        session.open_at,
        session.close_at,
        timeframe,
        price_basis,
        event_start,
        event_end,
        source_recorded_at,
        known_at,
        session.recorded_at,
        session.known_at,
        bar_revision_id,
        bar_revision,
        source_gap_id,
        source_gap_kind,
        source_gap_reason,
        revision.draft.observation_cutoff,
        revision.draft.knowledge_cutoff,
        item.content_sha256,
        revision.settled_at,
    )


def _empty_reconciliation(revision_id: UUID) -> OutcomeReconciliation:
    empty = "0" * 64
    return OutcomeReconciliation(
        market_target_outcome_revision_id=revision_id,
        source_count=0,
        observation_count=0,
        metric_count=0,
        reference_dependency_count=0,
        observation_dependency_count=0,
        reason_count=0,
        source_roster_sha256=empty,
        observation_roster_sha256=empty,
        metric_roster_sha256=empty,
        reference_dependency_roster_sha256=empty,
        observation_dependency_roster_sha256=empty,
        reason_roster_sha256=empty,
        definition_summary_sha256=empty,
        matched=False,
    )


__all__ = ["PostgresOutcomeRepository"]
