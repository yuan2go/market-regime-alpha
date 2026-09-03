"""Typed read-only loader for exact historical Outcome revisions."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from typing import Any
from uuid import UUID

import psycopg

from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.postgres.queries.outcome_inputs import (
    _find_retrospective_scope,
    _load_commitment,
    _load_target,
)
from market_regime_alpha.outcome.domain import (
    MarketTargetOutcomeIdentityPlan,
    OutcomeAvailabilityStatus,
    OutcomeBarSource,
    OutcomeCompletionRule,
    OutcomeDependencyRole,
    OutcomeFinalityStatus,
    OutcomeGapKind,
    OutcomeGapSource,
    OutcomeMetricDraft,
    OutcomeMetricKind,
    OutcomeObservationDependencyDraft,
    OutcomeObservationDraft,
    OutcomeReasonDimension,
    OutcomeReasonDraft,
    OutcomeReferenceDependencyDraft,
    OutcomeRevisionDraft,
    OutcomeRuntimeSnapshot,
    OutcomeSessionSource,
    OutcomeSourceKind,
    OutcomeStatus,
    OutcomeValueType,
    build_market_target_outcome_authority,
)
from market_regime_alpha.outcome.errors import OutcomeAuthorityIntegrityError
from market_regime_alpha.outcome.ports import OutcomeSnapshot


class PostgresOutcomeQueryProvider:
    """Permanent narrow OutcomeReadPort implementation."""

    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool

    def load(self, revision_id: UUID) -> OutcomeSnapshot:
        with self._pool.connection(read_only=True) as connection:
            return _load_snapshot(connection, revision_id)

    def find_by_request(
        self,
        commitment_id: UUID,
        request_identity: str,
    ) -> OutcomeSnapshot | None:
        with self._pool.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT market_target_outcome_revision_id
                FROM mra.market_target_outcome_revision
                WHERE commitment_id = %s AND request_identity = %s
                """,
                (commitment_id, request_identity),
            ).fetchone()
            return (
                None
                if row is None
                else _load_snapshot(
                    connection,
                    UUID(str(row[0])),
                )
            )

    def current_for_commitment(
        self,
        commitment_id: UUID,
    ) -> OutcomeSnapshot | None:
        with self._pool.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT revision.market_target_outcome_revision_id
                FROM mra.market_target_outcome AS root
                JOIN mra.market_target_outcome_revision AS revision
                  ON revision.market_target_outcome_id =
                     root.market_target_outcome_id
                WHERE root.commitment_id = %s
                  AND NOT EXISTS (
                      SELECT 1
                      FROM mra.market_target_outcome_revision AS successor
                      WHERE successor.supersedes_revision_id =
                            revision.market_target_outcome_revision_id
                  )
                """,
                (commitment_id,),
            ).fetchone()
            return (
                None
                if row is None
                else _load_snapshot(
                    connection,
                    UUID(str(row[0])),
                )
            )


def _load_snapshot(
    connection: psycopg.Connection[Any],
    revision_id: UUID,
) -> OutcomeSnapshot:
    try:
        return _reconstruct_snapshot(connection, revision_id)
    except OutcomeAuthorityIntegrityError:
        raise
    except (IndexError, KeyError, StopIteration, TypeError, ValueError) as exc:
        raise OutcomeAuthorityIntegrityError("persisted Outcome snapshot cannot be reconstructed as typed Authority") from exc


def _reconstruct_snapshot(
    connection: psycopg.Connection[Any],
    revision_id: UUID,
) -> OutcomeSnapshot:
    row = connection.execute(
        """
        SELECT revision.market_target_outcome_revision_id,
               revision.market_target_outcome_id,
               revision.revision_ordinal,
               revision.supersedes_revision_id,
               revision.supersedes_revision_ordinal,
               revision.commitment_id, revision.target_definition_id,
               revision.decision_reference_observation_id,
               revision.decision_reference_sha256,
               revision.observation_cutoff, revision.knowledge_cutoff,
               revision.outcome_status, revision.availability_status,
               revision.finality_status,
               revision.source_count, revision.source_roster_sha256,
               revision.observation_count,
               revision.observation_roster_sha256,
               revision.metric_count, revision.metric_roster_sha256,
               revision.reference_dependency_count,
               revision.reference_dependency_roster_sha256,
               revision.observation_dependency_count,
               revision.observation_dependency_roster_sha256,
               revision.reason_count, revision.reason_roster_sha256,
               revision.definition_summary_sha256,
               revision.request_received_at, revision.settled_at,
               revision.runtime_run_id, revision.runtime_step_id,
               revision.runtime_attempt_id, revision.runtime_fence_token,
               revision.runtime_step_key, revision.runtime_step_kind,
               revision.runtime_mode, revision.runtime_decision_time,
               revision.runtime_code_sha,
               revision.runtime_config_artifact_id,
               revision.runtime_config_hash,
               revision.request_identity, revision.request_sha256,
               revision.command_receipt_id,
               revision.created_by_actor_type,
               revision.created_by_actor_id,
               revision.creation_reason_code,
               root.created_at, receipt.result_hash
        FROM mra.market_target_outcome_revision AS revision
        JOIN mra.market_target_outcome AS root
          ON root.market_target_outcome_id = revision.market_target_outcome_id
        JOIN mra.command_receipt AS receipt
          ON receipt.receipt_id = revision.command_receipt_id
         AND receipt.status = 'SUCCEEDED'
        WHERE revision.market_target_outcome_revision_id = %s
        """,
        (revision_id,),
    ).fetchone()
    if row is None or row[47] is None:
        raise OutcomeAuthorityIntegrityError(f"Outcome revision {revision_id} has no successful canonical snapshot")
    commitment_id = UUID(str(row[5]))
    retrospective_scope = _find_retrospective_scope(
        connection,
        commitment_id,
        observation_cutoff=row[9],
        knowledge_cutoff=row[10],
    )
    commitment = _load_commitment(
        connection,
        commitment_id,
        retrospective_scope=retrospective_scope,
    )
    target = _load_target(
        connection,
        UUID(str(row[6])),
        version=commitment.target_version,
        content_sha256=commitment.target_definition_sha256,
    )
    source_rows = connection.execute(
        """
        SELECT market_target_outcome_source_id, source_ordinal,
               source_kind, target_checkpoint_id, provider_product_id,
               capture_id, instrument_id, trading_session_id,
               session_offset, exchange, session_date, timezone_name,
               session_open_at, session_close_at,
               session_provider_product_id, session_capture_id,
               session_recorded_at, session_known_at,
               timeframe, price_basis, event_start, event_end,
               source_recorded_at, known_at, bar_revision_id,
               bar_revision, source_gap_id, source_gap_kind,
               source_gap_reason_code, content_sha256
        FROM mra.market_target_outcome_source
        WHERE market_target_outcome_revision_id = %s
        ORDER BY source_ordinal
        """,
        (revision_id,),
    ).fetchall()
    observation_rows = connection.execute(
        """
        SELECT market_target_outcome_observation_id,
               observation_ordinal, target_checkpoint_id,
               market_target_outcome_source_id, source_kind,
               value_status, availability_status, finality_status,
               selected_value, open_value, high_value, low_value,
               close_value, event_start, event_end, known_at,
               content_sha256
        FROM mra.market_target_outcome_observation
        WHERE market_target_outcome_revision_id = %s
        ORDER BY observation_ordinal
        """,
        (revision_id,),
    ).fetchall()
    metric_rows = connection.execute(
        """
        SELECT market_target_outcome_metric_id, metric_ordinal,
               target_metric_definition_id, metric_code, metric_kind,
               value_type, unit, completion_rule, value_status,
               availability_status, finality_status, decimal_value,
               boolean_value, first_passage_at, algorithm_code,
               algorithm_version, algorithm_sha256, code_artifact_id,
               code_content_sha256, code_size_bytes, config_artifact_id,
               config_content_sha256, config_size_bytes,
               target_metric_sha256, content_sha256
        FROM mra.market_target_outcome_metric
        WHERE market_target_outcome_revision_id = %s
        ORDER BY metric_ordinal
        """,
        (revision_id,),
    ).fetchall()
    reference_rows = connection.execute(
        """
        SELECT market_target_outcome_metric_reference_id,
               dependency_ordinal, target_metric_definition_id,
               market_target_outcome_metric_id,
               target_metric_dependency_id, target_checkpoint_id,
               dependency_role, target_dependency_sha256,
               decision_reference_observation_id, content_sha256
        FROM mra.market_target_outcome_metric_reference
        WHERE market_target_outcome_revision_id = %s
        ORDER BY dependency_ordinal
        """,
        (revision_id,),
    ).fetchall()
    dependency_rows = connection.execute(
        """
        SELECT market_target_outcome_metric_observation_id,
               dependency_ordinal, target_metric_definition_id,
               market_target_outcome_metric_id,
               target_metric_dependency_id, target_checkpoint_id,
               dependency_role, target_dependency_sha256,
               market_target_outcome_observation_id, content_sha256
        FROM mra.market_target_outcome_metric_observation
        WHERE market_target_outcome_revision_id = %s
        ORDER BY dependency_ordinal
        """,
        (revision_id,),
    ).fetchall()
    reason_rows = connection.execute(
        """
        SELECT market_target_outcome_reason_id, reason_ordinal,
               reason_dimension, reason_code,
               market_target_outcome_source_id,
               market_target_outcome_observation_id,
               market_target_outcome_metric_id, content_sha256
        FROM mra.market_target_outcome_reason
        WHERE market_target_outcome_revision_id = %s
        ORDER BY reason_ordinal
        """,
        (revision_id,),
    ).fetchall()

    sessions = tuple(
        OutcomeSessionSource(
            session_id=UUID(str(item[7])),
            session_offset=int(item[8]),
            exchange=str(item[9]),
            session_date=item[10],
            timezone_name=str(item[11]),
            open_at=item[12],
            close_at=item[13],
            source_capture_id=UUID(str(item[15])),
            provider_product_id=UUID(str(item[14])),
            recorded_at=item[16],
            known_at=item[17],
        )
        for item in source_rows
        if str(item[2]) == "TRADING_SESSION"
    )
    observation_by_source = {UUID(str(item[3])): item for item in observation_rows}
    observation_source_rows = tuple(item for item in source_rows if str(item[2]) != "TRADING_SESSION")
    sources = tuple(
        _source_from_row(
            item,
            observation_by_source[UUID(str(item[0]))],
            source_ordinal=index,
        )
        for index, item in enumerate(observation_source_rows, start=1)
    )
    observations = tuple(
        OutcomeObservationDraft(
            target_checkpoint_id=UUID(str(item[2])),
            source_kind=OutcomeSourceKind(str(item[4])),
            source_fact_id=_source_fact_id(
                source_rows,
                UUID(str(item[3])),
            ),
            status=OutcomeStatus(str(item[5])),
            availability_status=OutcomeAvailabilityStatus(str(item[6])),
            finality_status=OutcomeFinalityStatus(str(item[7])),
            selected_value=None if item[8] is None else Decimal(item[8]),
            open_value=None if item[9] is None else Decimal(item[9]),
            high_value=None if item[10] is None else Decimal(item[10]),
            low_value=None if item[11] is None else Decimal(item[11]),
            close_value=None if item[12] is None else Decimal(item[12]),
            event_start=item[13],
            event_end=item[14],
            known_at=item[15],
        )
        for item in observation_rows
    )
    metrics = tuple(
        OutcomeMetricDraft(
            target_metric_definition_id=UUID(str(item[2])),
            ordinal=int(item[1]),
            metric_code=str(item[3]),
            metric_kind=OutcomeMetricKind(str(item[4])),
            value_type=OutcomeValueType(str(item[5])),
            unit=str(item[6]),
            completion_rule=OutcomeCompletionRule(str(item[7])),
            status=OutcomeStatus(str(item[8])),
            availability_status=OutcomeAvailabilityStatus(str(item[9])),
            finality_status=OutcomeFinalityStatus(str(item[10])),
            decimal_value=None if item[11] is None else Decimal(item[11]),
            boolean_value=None if item[12] is None else bool(item[12]),
            first_passage_at=item[13],
            algorithm_code=str(item[14]),
            algorithm_version=str(item[15]),
            algorithm_sha256=str(item[16]),
            code_artifact_id=UUID(str(item[17])),
            code_content_sha256=str(item[18]),
            code_size_bytes=int(item[19]),
            config_artifact_id=UUID(str(item[20])),
            config_content_sha256=str(item[21]),
            config_size_bytes=int(item[22]),
            target_metric_sha256=str(item[23]),
        )
        for item in metric_rows
    )
    reference_dependencies = tuple(
        OutcomeReferenceDependencyDraft(
            target_metric_dependency_id=UUID(str(item[4])),
            target_metric_definition_id=UUID(str(item[2])),
            target_checkpoint_id=UUID(str(item[5])),
            dependency_role=OutcomeDependencyRole(str(item[6])),
            decision_reference_observation_id=UUID(str(item[8])),
        )
        for item in reference_rows
    )
    observation_dependencies = tuple(
        OutcomeObservationDependencyDraft(
            target_metric_dependency_id=UUID(str(item[4])),
            target_metric_definition_id=UUID(str(item[2])),
            target_checkpoint_id=UUID(str(item[5])),
            dependency_role=OutcomeDependencyRole(str(item[6])),
        )
        for item in dependency_rows
    )
    observation_checkpoint_by_id = {UUID(str(item[0])): UUID(str(item[2])) for item in observation_rows}
    metric_definition_by_id = {UUID(str(item[0])): UUID(str(item[2])) for item in metric_rows}
    source_checkpoint_by_id = {UUID(str(item[0])): (None if item[3] is None else UUID(str(item[3]))) for item in source_rows}
    reasons = tuple(
        OutcomeReasonDraft(
            ordinal=int(item[1]),
            dimension=OutcomeReasonDimension(str(item[2])),
            reason_code=str(item[3]),
            target_checkpoint_id=(
                source_checkpoint_by_id[UUID(str(item[4]))]
                if item[4] is not None
                else observation_checkpoint_by_id[UUID(str(item[5]))]
                if item[5] is not None
                else None
            ),
            target_metric_definition_id=(None if item[6] is None else metric_definition_by_id[UUID(str(item[6]))]),
        )
        for item in reason_rows
    )
    draft = OutcomeRevisionDraft(
        target_definition_id=UUID(str(row[6])),
        target_definition_sha256=target.content_sha256,
        decision_reference_observation_id=UUID(str(row[7])),
        decision_reference_sha256=str(row[8]),
        observation_cutoff=row[9],
        knowledge_cutoff=row[10],
        status=OutcomeStatus(str(row[11])),
        availability_status=OutcomeAvailabilityStatus(str(row[12])),
        finality_status=OutcomeFinalityStatus(str(row[13])),
        sessions=sessions,
        sources=sources,
        observations=observations,
        metrics=metrics,
        reference_dependencies=reference_dependencies,
        observation_dependencies=observation_dependencies,
        reasons=reasons,
    )
    identities = MarketTargetOutcomeIdentityPlan(
        market_target_outcome_id=UUID(str(row[1])),
        market_target_outcome_revision_id=UUID(str(row[0])),
        source_ids=tuple(UUID(str(item[0])) for item in source_rows),
        observation_ids=tuple(UUID(str(item[0])) for item in observation_rows),
        metric_ids=tuple(UUID(str(item[0])) for item in metric_rows),
        reference_dependency_ids=tuple(UUID(str(item[0])) for item in reference_rows),
        observation_dependency_ids=tuple(UUID(str(item[0])) for item in dependency_rows),
        reason_ids=tuple(UUID(str(item[0])) for item in reason_rows),
    )
    authority = build_market_target_outcome_authority(
        identities=identities,
        commitment=commitment,
        target=target,
        draft=draft,
        runtime=OutcomeRuntimeSnapshot(
            run_id=UUID(str(row[29])),
            step_id=UUID(str(row[30])),
            attempt_id=UUID(str(row[31])),
            fence_token=int(row[32]),
            step_key=str(row[33]),
            step_kind=str(row[34]),
            runtime_mode=str(row[35]),
            decision_time=row[36],
            code_sha=str(row[37]),
            config_artifact_id=UUID(str(row[38])),
            config_hash=str(row[39]),
        ),
        revision_ordinal=int(row[2]),
        supersedes_revision_id=(None if row[3] is None else UUID(str(row[3]))),
        request_identity=str(row[40]),
        request_sha256=str(row[41]),
        request_received_at=row[27],
        settled_at=row[28],
        command_receipt_id=UUID(str(row[42])),
        actor_type=str(row[43]),
        actor_id=str(row[44]),
        reason_code=str(row[45]),
    )
    authority = replace(
        authority,
        root=replace(authority.root, created_at=row[46]),
    )
    _assert_persisted_snapshot_matches(
        authority,
        row=row,
        source_rows=source_rows,
        observation_rows=observation_rows,
        metric_rows=metric_rows,
        reference_rows=reference_rows,
        dependency_rows=dependency_rows,
        reason_rows=reason_rows,
    )
    return OutcomeSnapshot(
        authority=authority,
        receipt_id=UUID(str(row[42])),
        result_hash=str(row[47]),
    )


def _source_from_row(row, observation, *, source_ordinal: int):
    common = {
        "target_checkpoint_id": UUID(str(row[3])),
        "source_ordinal": source_ordinal,
        "provider_product_id": UUID(str(row[4])),
        "capture_id": UUID(str(row[5])),
        "instrument_id": UUID(str(row[6])),
        "session_id": UUID(str(row[7])),
        "timeframe": str(row[18]),
        "price_basis": str(row[19]),
        "event_start": row[20],
        "event_end": row[21],
        "recorded_at": row[22],
        "known_at": row[23],
    }
    if str(row[2]) == "BAR_REVISION":
        return OutcomeBarSource(
            bar_revision_id=UUID(str(row[24])),
            revision=int(row[25]),
            open_value=Decimal(observation[9]),
            high_value=Decimal(observation[10]),
            low_value=Decimal(observation[11]),
            close_value=Decimal(observation[12]),
            **common,
        )
    return OutcomeGapSource(
        gap_id=UUID(str(row[26])),
        gap_kind=OutcomeGapKind(str(row[27])),
        reason_code=str(row[28]),
        **common,
    )


def _source_fact_id(source_rows, source_id: UUID) -> UUID:
    row = next(item for item in source_rows if UUID(str(item[0])) == source_id)
    return UUID(str(row[24] if row[24] is not None else row[26]))


def _assert_persisted_snapshot_matches(
    authority,
    *,
    row,
    source_rows,
    observation_rows,
    metric_rows,
    reference_rows,
    dependency_rows,
    reason_rows,
) -> None:
    revision = authority.revision
    expected_root = (
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
    )
    persisted_root = (
        int(row[14]),
        str(row[15]),
        int(row[16]),
        str(row[17]),
        int(row[18]),
        str(row[19]),
        int(row[20]),
        str(row[21]),
        int(row[22]),
        str(row[23]),
        int(row[24]),
        str(row[25]),
        str(row[26]),
    )
    expected_children = (
        tuple(item.content_sha256 for item in revision.sources),
        tuple(item.content_sha256 for item in revision.observations),
        tuple(item.content_sha256 for item in revision.metrics),
        tuple(item.content_sha256 for item in revision.reference_dependencies),
        tuple(item.content_sha256 for item in revision.observation_dependencies),
        tuple(item.content_sha256 for item in revision.reasons),
    )
    persisted_children = (
        tuple(str(item[29]) for item in source_rows),
        tuple(str(item[16]) for item in observation_rows),
        tuple(str(item[24]) for item in metric_rows),
        tuple(str(item[9]) for item in reference_rows),
        tuple(str(item[9]) for item in dependency_rows),
        tuple(str(item[7]) for item in reason_rows),
    )
    chain_matches = revision.supersedes_revision_ordinal == (None if row[4] is None else int(row[4]))
    if expected_root != persisted_root or expected_children != persisted_children or not chain_matches:
        raise OutcomeAuthorityIntegrityError("persisted Outcome snapshot differs from canonical reconstruction")


__all__ = ["PostgresOutcomeQueryProvider"]
