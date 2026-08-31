"""PIT-safe preparation and locked revalidation of Outcome inputs."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import psycopg

from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.outcome.domain import (
    FrozenDecisionReference,
    OutcomeAvailabilityStatus,
    OutcomeBarSource,
    OutcomeBarrierDirection,
    OutcomeCheckpoint,
    OutcomeCommitmentSnapshot,
    OutcomeCompletionRule,
    OutcomeDependencyRole,
    OutcomeFinalityStatus,
    OutcomeGapKind,
    OutcomeGapSource,
    OutcomeMetricDefinition,
    OutcomeMetricDependency,
    OutcomeMetricKind,
    OutcomeReferenceValueStatus,
    OutcomeRuntimeSnapshot,
    OutcomeSessionSource,
    OutcomeTargetDefinition,
    OutcomeValueField,
    OutcomeValueType,
    PreparedOutcomeInputs,
)
from market_regime_alpha.outcome.errors import (
    OutcomeAuthorityIntegrityError,
    OutcomeInputResolutionError,
)
from market_regime_alpha.outcome.ports import OutcomeSettlementRequest
from market_regime_alpha.runtime.errors import RuntimeNotFoundError, StaleFenceError
from market_regime_alpha.runtime.ports import AttemptClaim


_MINUTE_WIDTHS = {
    "MINUTE_1": timedelta(minutes=1),
    "MINUTE_5": timedelta(minutes=5),
    "MINUTE_15": timedelta(minutes=15),
    "MINUTE_30": timedelta(minutes=30),
    "MINUTE_60": timedelta(minutes=60),
}


class PostgresOutcomeInputPreparationProvider:
    """Resolve exact Target, commitment, Session, and Market revisions."""

    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool

    def prepare(
        self,
        request: OutcomeSettlementRequest,
        runtime_claim: AttemptClaim,
    ) -> PreparedOutcomeInputs:
        with self._pool.connection(read_only=True) as connection:
            runtime = _load_runtime(connection, runtime_claim)
            commitment = _load_commitment(
                connection,
                request.commitment_id,
            )
            target = _load_target(
                connection,
                commitment.target_definition_id,
                version=commitment.target_version,
                content_sha256=commitment.target_definition_sha256,
            )
            sessions = _load_sessions(
                connection,
                commitment=commitment,
                target=target,
                knowledge_cutoff=request.knowledge_cutoff,
            )
            due_at = _due_at(target, sessions)
            is_due = request.observation_cutoff >= due_at
            sources = (
                _load_sources(
                    connection,
                    commitment=commitment,
                    target=target,
                    sessions=sessions,
                    observation_cutoff=request.observation_cutoff,
                    knowledge_cutoff=request.knowledge_cutoff,
                )
                if is_due
                else ()
            )
        return PreparedOutcomeInputs(
            commitment=commitment,
            target=target,
            runtime=runtime,
            observation_cutoff=request.observation_cutoff,
            knowledge_cutoff=request.knowledge_cutoff,
            due_at=due_at,
            sessions=sessions,
            sources=sources,
            is_due=is_due,
        )


class PostgresOutcomeDependencyRepository:
    """Lock in global order and reject any prepared identity drift."""

    def __init__(self, connection: psycopg.Connection[Any]) -> None:
        self._connection = connection

    def lock_and_revalidate(self, prepared: PreparedOutcomeInputs) -> None:
        self._lock_artifacts(prepared)
        self._lock_target(prepared)
        self._lock_market(prepared)
        self._lock_candidate_and_decision(prepared)

        commitment = _load_commitment(
            self._connection,
            prepared.commitment.commitment_id,
        )
        target = _load_target(
            self._connection,
            prepared.target.target_definition_id,
            version=prepared.target.version,
            content_sha256=prepared.target.content_sha256,
        )
        sessions = _load_sessions(
            self._connection,
            commitment=commitment,
            target=target,
            knowledge_cutoff=prepared.knowledge_cutoff,
        )
        sources = (
            _load_sources(
                self._connection,
                commitment=commitment,
                target=target,
                sessions=sessions,
                observation_cutoff=prepared.observation_cutoff,
                knowledge_cutoff=prepared.knowledge_cutoff,
            )
            if prepared.is_due
            else ()
        )
        if (
            commitment != prepared.commitment
            or target != prepared.target
            or sessions != prepared.sessions
            or sources != prepared.sources
            or _due_at(target, sessions) != prepared.due_at
        ):
            raise OutcomeAuthorityIntegrityError(
                "prepared Outcome dependencies changed before closure"
            )

    def _lock_artifacts(self, prepared: PreparedOutcomeInputs) -> None:
        artifact_ids = {
            prepared.runtime.config_artifact_id,
            prepared.target.code_artifact_id,
            prepared.target.config_artifact_id,
            *(metric.code_artifact_id for metric in prepared.target.metrics),
            *(metric.config_artifact_id for metric in prepared.target.metrics),
        }
        rows = self._connection.execute(
            """
            SELECT artifact_id
            FROM mra.artifact
            WHERE artifact_id = ANY(%s::uuid[])
              AND mra.market_artifact_is_readable(
                  integrity_state, last_verified_at
              )
            ORDER BY artifact_id
            FOR SHARE
            """,
            (sorted(artifact_ids, key=str),),
        ).fetchall()
        if tuple(UUID(str(row[0])) for row in rows) != tuple(
            sorted(artifact_ids, key=str)
        ):
            raise OutcomeAuthorityIntegrityError(
                "Outcome algorithm/Runtime Artifact is not readable"
            )

    def _lock_target(self, prepared: PreparedOutcomeInputs) -> None:
        target_id = prepared.target.target_definition_id
        for table in (
            "target_definition",
            "target_checkpoint",
            "target_metric_definition",
            "target_metric_dependency",
        ):
            rows = self._connection.execute(
                f"""
                SELECT target_definition_id
                FROM mra.{table}
                WHERE target_definition_id = %s
                ORDER BY target_definition_id
                FOR SHARE
                """,
                (target_id,),
            ).fetchall()
            if not rows:
                raise OutcomeAuthorityIntegrityError(
                    f"Outcome Target dependency {table} is absent"
                )

    def _lock_market(self, prepared: PreparedOutcomeInputs) -> None:
        capture_ids = {
            prepared.commitment.reference_capture_id,
            *(item.source_capture_id for item in prepared.sessions),
            *(item.capture_id for item in prepared.sources),
        }
        self._connection.execute(
            """
            SELECT capture_id
            FROM mra.data_capture
            WHERE capture_id = ANY(%s::uuid[])
            ORDER BY capture_id
            FOR SHARE
            """,
            (sorted(capture_ids, key=str),),
        ).fetchall()
        session_ids = {
            prepared.commitment.reference_session_id,
            *(item.session_id for item in prepared.sessions),
        }
        self._connection.execute(
            """
            SELECT session_id
            FROM mra.trading_session
            WHERE session_id = ANY(%s::uuid[])
            ORDER BY session_id
            FOR SHARE
            """,
            (sorted(session_ids, key=str),),
        ).fetchall()
        bar_ids = sorted(
            (
                item.bar_revision_id
                for item in prepared.sources
                if isinstance(item, OutcomeBarSource)
            ),
            key=str,
        )
        if bar_ids:
            self._connection.execute(
                """
                SELECT bar_revision_id
                FROM mra.market_bar_revision
                WHERE bar_revision_id = ANY(%s::uuid[])
                ORDER BY bar_revision_id
                FOR SHARE
                """,
                (bar_ids,),
            ).fetchall()
        gap_ids = sorted(
            (
                item.gap_id
                for item in prepared.sources
                if isinstance(item, OutcomeGapSource)
            ),
            key=str,
        )
        if gap_ids:
            self._connection.execute(
                """
                SELECT gap_id
                FROM mra.source_gap
                WHERE gap_id = ANY(%s::uuid[])
                ORDER BY gap_id
                FOR SHARE
                """,
                (gap_ids,),
            ).fetchall()

    def _lock_candidate_and_decision(self, prepared: PreparedOutcomeInputs) -> None:
        commitment = prepared.commitment
        self._connection.execute(
            """
            SELECT candidate_set_id
            FROM mra.candidate_set
            WHERE candidate_set_id = %s
            FOR SHARE
            """,
            (commitment.candidate_set_id,),
        ).fetchone()
        self._connection.execute(
            """
            SELECT candidate_id
            FROM mra.candidate
            WHERE candidate_id = %s AND candidate_set_id = %s
            FOR SHARE
            """,
            (commitment.candidate_id, commitment.candidate_set_id),
        ).fetchone()
        self._connection.execute(
            """
            SELECT decision_run_id
            FROM mra.decision_run
            WHERE decision_run_id = %s
            FOR SHARE
            """,
            (commitment.decision_run_id,),
        ).fetchone()
        self._connection.execute(
            """
            SELECT decision_run_target_id
            FROM mra.decision_run_target
            WHERE decision_run_target_id = %s
              AND decision_run_id = %s
            FOR SHARE
            """,
            (commitment.decision_run_target_id, commitment.decision_run_id),
        ).fetchone()
        self._connection.execute(
            """
            SELECT commitment_id
            FROM mra.decision_target_commitment
            WHERE commitment_id = %s
            FOR SHARE
            """,
            (commitment.commitment_id,),
        ).fetchone()
        self._connection.execute(
            """
            SELECT decision_reference_observation_id
            FROM mra.decision_reference_observation
            WHERE decision_reference_observation_id = %s
              AND content_sha256 = %s
            FOR SHARE
            """,
            (
                commitment.decision_reference_observation_id,
                commitment.decision_reference_sha256,
            ),
        ).fetchone()


def _load_runtime(
    connection: psycopg.Connection[Any],
    claim: AttemptClaim,
) -> OutcomeRuntimeSnapshot:
    row = connection.execute(
        """
        SELECT run.run_id, step.step_id, attempt.attempt_id,
               attempt.fence_token, step.step_key, step.step_kind,
               run.runtime_mode, run.decision_time, run.code_sha,
               run.config_artifact_id, run.config_hash,
               run.state, step.state, attempt.state,
               step.current_attempt_id, step.current_fence,
               attempt.lease_owner, attempt.lease_until
        FROM mra.runtime_run AS run
        JOIN mra.runtime_step AS step ON step.run_id = run.run_id
        JOIN mra.runtime_attempt AS attempt ON attempt.step_id = step.step_id
        WHERE run.run_id = %s AND step.step_id = %s AND attempt.attempt_id = %s
        """,
        (claim.run_id, claim.step_id, claim.attempt_id),
    ).fetchone()
    if row is None:
        raise RuntimeNotFoundError("SETTLE_OUTCOME Runtime claim does not exist")
    exact = (
        UUID(str(row[0])) == claim.run_id
        and UUID(str(row[1])) == claim.step_id
        and UUID(str(row[2])) == claim.attempt_id
        and int(row[3]) == claim.fence_token
        and str(row[4]) == claim.step_key
        and UUID(str(row[14])) == claim.attempt_id
        and int(row[15]) == claim.fence_token
        and str(row[16]) == claim.lease_owner
    )
    live = (
        str(row[5]) == "SETTLE_OUTCOME"
        and str(row[11]) == "RUNNING"
        and str(row[12]) == "RUNNING"
        and str(row[13]) == "RUNNING"
        and row[17] > datetime.now(UTC)
    )
    if not exact or not live:
        raise StaleFenceError("SETTLE_OUTCOME Runtime claim is no longer live")
    if row[7] is None:
        raise OutcomeAuthorityIntegrityError(
            "Outcome Runtime requires a canonical DecisionTime"
        )
    return OutcomeRuntimeSnapshot(
        run_id=UUID(str(row[0])),
        step_id=UUID(str(row[1])),
        attempt_id=UUID(str(row[2])),
        fence_token=int(row[3]),
        step_key=str(row[4]),
        step_kind=str(row[5]),
        runtime_mode=str(row[6]),
        decision_time=row[7],
        code_sha=str(row[8]),
        config_artifact_id=UUID(str(row[9])),
        config_hash=str(row[10]),
    )


def _load_commitment(
    connection: psycopg.Connection[Any],
    commitment_id: UUID,
) -> OutcomeCommitmentSnapshot:
    row = connection.execute(
        """
        SELECT commitment.commitment_id, commitment.decision_run_id,
               commitment.decision_run_target_id,
               commitment.candidate_set_id, commitment.candidate_id,
               commitment.instrument_id, commitment.target_definition_id,
               target.target_version, target.target_definition_sha256,
               commitment.target_checkpoint_id,
               commitment.reference_provider_product_id,
               reference.capture_id, reference.session_id,
               reference.source_kind,
               COALESCE(reference.bar_revision_id, reference.source_gap_id),
               reference.known_at, commitment.decision_time,
               commitment.runtime_mode, commitment.commitment_recorded_at,
               reference.decision_reference_observation_id,
               reference.content_sha256, reference.value_status,
               reference.availability_status, reference.finality_status,
               reference.decimal_value
        FROM mra.decision_target_commitment AS commitment
        JOIN mra.decision_run_target AS target
          ON target.decision_run_target_id = commitment.decision_run_target_id
         AND target.decision_run_id = commitment.decision_run_id
        JOIN mra.decision_reference_observation AS reference
          ON reference.decision_reference_observation_id =
             commitment.decision_reference_observation_id
         AND reference.commitment_id = commitment.commitment_id
        WHERE commitment.commitment_id = %s
        """,
        (commitment_id,),
    ).fetchone()
    if row is None:
        raise OutcomeInputResolutionError(
            f"DecisionTargetCommitment {commitment_id} does not exist"
        )
    return OutcomeCommitmentSnapshot(
        commitment_id=UUID(str(row[0])),
        decision_run_id=UUID(str(row[1])),
        decision_run_target_id=UUID(str(row[2])),
        candidate_set_id=UUID(str(row[3])),
        candidate_id=UUID(str(row[4])),
        instrument_id=UUID(str(row[5])),
        target_definition_id=UUID(str(row[6])),
        target_version=int(row[7]),
        target_definition_sha256=str(row[8]),
        target_checkpoint_id=UUID(str(row[9])),
        reference_provider_product_id=UUID(str(row[10])),
        reference_capture_id=UUID(str(row[11])),
        reference_session_id=UUID(str(row[12])),
        reference_source_kind=str(row[13]),
        reference_fact_id=UUID(str(row[14])),
        reference_known_at=row[15],
        decision_time=row[16],
        runtime_mode=str(row[17]),
        commitment_recorded_at=row[18],
        reference=FrozenDecisionReference(
            decision_reference_observation_id=UUID(str(row[19])),
            content_sha256=str(row[20]),
            value_status=OutcomeReferenceValueStatus(str(row[21])),
            availability_status=OutcomeAvailabilityStatus(str(row[22])),
            finality_status=OutcomeFinalityStatus(str(row[23])),
            decimal_value=None if row[24] is None else Decimal(row[24]),
        ),
    )


def _load_target(
    connection: psycopg.Connection[Any],
    target_definition_id: UUID,
    *,
    version: int,
    content_sha256: str,
) -> OutcomeTargetDefinition:
    root = connection.execute(
        """
        SELECT target_code, version, content_sha256,
               algorithm_code, algorithm_version, algorithm_sha256,
               code_artifact_id, code_content_sha256, code_size_bytes,
               config_artifact_id, config_content_sha256, config_size_bytes
        FROM mra.target_definition
        WHERE target_definition_id = %s
          AND version = %s AND content_sha256 = %s
          AND registration_status = 'REGISTERED'
        """,
        (target_definition_id, version, content_sha256),
    ).fetchone()
    if root is None:
        raise OutcomeInputResolutionError("exact committed Target version is absent")
    checkpoint_rows = connection.execute(
        """
        SELECT target_checkpoint_id, content_sha256, ordinal,
               checkpoint_code, checkpoint_role, session_offset,
               local_time, timezone_name, timeframe, price_basis, value_field
        FROM mra.target_checkpoint
        WHERE target_definition_id = %s
        ORDER BY ordinal
        """,
        (target_definition_id,),
    ).fetchall()
    references = tuple(row for row in checkpoint_rows if str(row[4]) == "DECISION_REFERENCE")
    outcomes = tuple(row for row in checkpoint_rows if str(row[4]) == "OUTCOME_OBSERVATION")
    if len(references) != 1 or not outcomes:
        raise OutcomeAuthorityIntegrityError("Target checkpoint roles are incomplete")
    metric_rows = connection.execute(
        """
        SELECT target_metric_definition_id, ordinal, metric_code,
               metric_kind, value_type, unit, completion_rule,
               algorithm_code, algorithm_version, algorithm_sha256,
               code_artifact_id, code_content_sha256, code_size_bytes,
               config_artifact_id, config_content_sha256, config_size_bytes,
               content_sha256, barrier_direction, barrier_threshold
        FROM mra.target_metric_definition
        WHERE target_definition_id = %s
        ORDER BY ordinal
        """,
        (target_definition_id,),
    ).fetchall()
    dependency_rows = connection.execute(
        """
        SELECT target_metric_dependency_id, ordinal,
               target_metric_definition_id, target_checkpoint_id,
               dependency_role, content_sha256
        FROM mra.target_metric_dependency
        WHERE target_definition_id = %s
        ORDER BY ordinal
        """,
        (target_definition_id,),
    ).fetchall()
    return OutcomeTargetDefinition(
        target_definition_id=target_definition_id,
        target_code=str(root[0]),
        version=int(root[1]),
        content_sha256=str(root[2]),
        reference_checkpoint_id=UUID(str(references[0][0])),
        algorithm_code=str(root[3]),
        algorithm_version=str(root[4]),
        algorithm_sha256=str(root[5]),
        code_artifact_id=UUID(str(root[6])),
        code_content_sha256=str(root[7]),
        code_size_bytes=int(root[8]),
        config_artifact_id=UUID(str(root[9])),
        config_content_sha256=str(root[10]),
        config_size_bytes=int(root[11]),
        checkpoints=tuple(
            OutcomeCheckpoint(
                target_checkpoint_id=UUID(str(row[0])),
                content_sha256=str(row[1]),
                ordinal=int(row[2]),
                checkpoint_code=str(row[3]),
                session_offset=int(row[5]),
                local_time=row[6],
                timezone_name=str(row[7]),
                timeframe=str(row[8]),
                price_basis=str(row[9]),
                value_field=OutcomeValueField(str(row[10])),
            )
            for row in outcomes
        ),
        metrics=tuple(
            OutcomeMetricDefinition(
                target_metric_definition_id=UUID(str(row[0])),
                ordinal=int(row[1]),
                metric_code=str(row[2]),
                metric_kind=OutcomeMetricKind(str(row[3])),
                value_type=OutcomeValueType(str(row[4])),
                unit=str(row[5]),
                completion_rule=OutcomeCompletionRule(str(row[6])),
                algorithm_code=str(row[7]),
                algorithm_version=str(row[8]),
                algorithm_sha256=str(row[9]),
                code_artifact_id=UUID(str(row[10])),
                code_content_sha256=str(row[11]),
                code_size_bytes=int(row[12]),
                config_artifact_id=UUID(str(row[13])),
                config_content_sha256=str(row[14]),
                config_size_bytes=int(row[15]),
                content_sha256=str(row[16]),
                barrier_direction=(
                    None
                    if row[17] is None
                    else OutcomeBarrierDirection(str(row[17]))
                ),
                barrier_threshold=(
                    None if row[18] is None else Decimal(row[18])
                ),
            )
            for row in metric_rows
        ),
        dependencies=tuple(
            OutcomeMetricDependency(
                target_metric_dependency_id=UUID(str(row[0])),
                ordinal=int(row[1]),
                target_metric_definition_id=UUID(str(row[2])),
                target_checkpoint_id=UUID(str(row[3])),
                role=OutcomeDependencyRole(str(row[4])),
                content_sha256=str(row[5]),
            )
            for row in dependency_rows
        ),
    )


def _load_sessions(
    connection: psycopg.Connection[Any],
    *,
    commitment: OutcomeCommitmentSnapshot,
    target: OutcomeTargetDefinition,
    knowledge_cutoff: datetime,
) -> tuple[OutcomeSessionSource, ...]:
    reference = connection.execute(
        """
        SELECT exchange, session_date
        FROM mra.trading_session
        WHERE session_id = %s AND known_at <= %s
        """,
        (commitment.reference_session_id, knowledge_cutoff),
    ).fetchone()
    if reference is None:
        raise OutcomeInputResolutionError("Decision reference Session is unavailable")
    offsets = tuple(sorted({item.session_offset for item in target.checkpoints}))
    maximum = max(offsets)
    rows = connection.execute(
        """
        SELECT session.session_id, session.exchange, session.session_date,
               session.timezone_name, session.open_at, session.close_at,
               session.source_capture_id, capture.provider_product_id,
               session.recorded_at, session.known_at
        FROM mra.trading_session AS session
        JOIN mra.data_capture AS capture
          ON capture.capture_id = session.source_capture_id
        WHERE session.exchange = %s
          AND session.session_date > %s
          AND session.known_at <= %s
        ORDER BY session.session_date, session.session_id
        LIMIT %s
        """,
        (str(reference[0]), reference[1], knowledge_cutoff, maximum),
    ).fetchall()
    if len(rows) < maximum:
        raise OutcomeInputResolutionError(
            "exact future TradingSession roster is incomplete"
        )
    return tuple(
        OutcomeSessionSource(
            session_id=UUID(str(rows[offset - 1][0])),
            session_offset=offset,
            exchange=str(rows[offset - 1][1]),
            session_date=rows[offset - 1][2],
            timezone_name=str(rows[offset - 1][3]),
            open_at=rows[offset - 1][4],
            close_at=rows[offset - 1][5],
            source_capture_id=UUID(str(rows[offset - 1][6])),
            provider_product_id=UUID(str(rows[offset - 1][7])),
            recorded_at=rows[offset - 1][8],
            known_at=rows[offset - 1][9],
        )
        for offset in offsets
    )


def _due_at(
    target: OutcomeTargetDefinition,
    sessions: tuple[OutcomeSessionSource, ...],
) -> datetime:
    by_offset = {item.session_offset: item for item in sessions}
    return max(
        datetime.combine(
            by_offset[checkpoint.session_offset].session_date,
            checkpoint.local_time,
            ZoneInfo(checkpoint.timezone_name),
        ).astimezone(UTC)
        for checkpoint in target.checkpoints
    )


def _load_sources(
    connection: psycopg.Connection[Any],
    *,
    commitment: OutcomeCommitmentSnapshot,
    target: OutcomeTargetDefinition,
    sessions: tuple[OutcomeSessionSource, ...],
    observation_cutoff: datetime,
    knowledge_cutoff: datetime,
) -> tuple[OutcomeBarSource | OutcomeGapSource, ...]:
    by_offset = {item.session_offset: item for item in sessions}
    values: list[OutcomeBarSource | OutcomeGapSource] = []
    for source_ordinal, checkpoint in enumerate(target.checkpoints, start=1):
        session = by_offset[checkpoint.session_offset]
        event_end = datetime.combine(
            session.session_date,
            checkpoint.local_time,
            ZoneInfo(checkpoint.timezone_name),
        ).astimezone(UTC)
        event_start = (
            session.open_at
            if checkpoint.timeframe == "DAILY"
            else event_end - _MINUTE_WIDTHS[checkpoint.timeframe]
        )
        if event_start < session.open_at or event_end > session.close_at:
            raise OutcomeInputResolutionError(
                "Target Outcome checkpoint falls outside exact Session"
            )
        rows = connection.execute(
            """
            WITH exact AS (
                SELECT 'BAR_REVISION'::text AS source_kind,
                       bar.bar_revision_id AS source_id,
                       bar.provider_product_id, bar.capture_id,
                       bar.instrument_id, bar.session_id, bar.timeframe,
                       bar.price_basis, bar.event_start, bar.event_end,
                       bar.revision, bar.recorded_at, bar.known_at,
                       bar.open_value, bar.high_value, bar.low_value,
                       bar.close_value, NULL::text AS gap_kind,
                       NULL::text AS reason_code, capture.status,
                       mra.market_artifact_is_readable(
                           artifact.integrity_state, artifact.last_verified_at
                       ) AS readable
                FROM mra.market_bar_revision AS bar
                JOIN mra.data_capture AS capture
                  ON capture.capture_id = bar.capture_id
                 AND capture.provider_product_id = bar.provider_product_id
                LEFT JOIN mra.artifact AS artifact
                  ON artifact.artifact_id = capture.artifact_id
                WHERE bar.provider_product_id = %(product_id)s
                  AND bar.instrument_id = %(instrument_id)s
                  AND bar.session_id = %(session_id)s
                  AND bar.timeframe = %(timeframe)s
                  AND bar.price_basis = %(price_basis)s
                  AND bar.event_start = %(event_start)s
                  AND bar.event_end = %(event_end)s
                  AND bar.event_end <= %(observation_cutoff)s
                  AND bar.known_at <= %(knowledge_cutoff)s
                UNION ALL
                SELECT 'SOURCE_GAP'::text, gap.gap_id,
                       gap.provider_product_id, gap.capture_id,
                       gap.instrument_id, gap.session_id, gap.timeframe,
                       gap.price_basis, gap.event_start, gap.event_end,
                       NULL::integer, gap.recorded_at, gap.known_at,
                       NULL::numeric, NULL::numeric, NULL::numeric,
                       NULL::numeric, gap.gap_kind, gap.reason_code,
                       capture.status,
                       CASE WHEN capture.status = 'PROVIDER_FAILURE' THEN true
                            ELSE mra.market_artifact_is_readable(
                                artifact.integrity_state,
                                artifact.last_verified_at
                            ) END
                FROM mra.source_gap AS gap
                JOIN mra.data_capture AS capture
                  ON capture.capture_id = gap.capture_id
                 AND capture.provider_product_id = gap.provider_product_id
                LEFT JOIN mra.artifact AS artifact
                  ON artifact.artifact_id = capture.artifact_id
                WHERE gap.provider_product_id = %(product_id)s
                  AND gap.fact_kind = 'MARKET_BAR'
                  AND gap.instrument_id = %(instrument_id)s
                  AND gap.session_id = %(session_id)s
                  AND gap.timeframe = %(timeframe)s
                  AND gap.price_basis = %(price_basis)s
                  AND gap.event_start = %(event_start)s
                  AND gap.event_end = %(event_end)s
                  AND gap.event_end <= %(observation_cutoff)s
                  AND gap.known_at <= %(knowledge_cutoff)s
            )
            SELECT * FROM exact
            ORDER BY known_at DESC, source_kind, source_id
            """,
            {
                "product_id": commitment.reference_provider_product_id,
                "instrument_id": commitment.instrument_id,
                "session_id": session.session_id,
                "timeframe": checkpoint.timeframe,
                "price_basis": checkpoint.price_basis,
                "event_start": event_start,
                "event_end": event_end,
                "observation_cutoff": observation_cutoff,
                "knowledge_cutoff": knowledge_cutoff,
            },
        ).fetchall()
        if not rows:
            raise OutcomeInputResolutionError(
                "Market Authority has neither exact bar nor exact SourceGap"
            )
        newest = tuple(row for row in rows if row[12] == rows[0][12])
        if len(newest) != 1:
            raise OutcomeInputResolutionError(
                "Market Authority has ambiguous exact Outcome observations"
            )
        row = newest[0]
        if row[20] is not True:
            raise OutcomeInputResolutionError(
                "Outcome source provenance is not readable"
            )
        common = {
            "target_checkpoint_id": checkpoint.target_checkpoint_id,
            "source_ordinal": source_ordinal,
            "provider_product_id": UUID(str(row[2])),
            "capture_id": UUID(str(row[3])),
            "instrument_id": UUID(str(row[4])),
            "session_id": UUID(str(row[5])),
            "timeframe": str(row[6]),
            "price_basis": str(row[7]),
            "event_start": row[8],
            "event_end": row[9],
            "recorded_at": row[11],
            "known_at": row[12],
        }
        if str(row[0]) == "BAR_REVISION":
            if str(row[19]) != "CAPTURED":
                raise OutcomeInputResolutionError(
                    "Outcome bar does not belong to a captured source"
                )
            values.append(
                OutcomeBarSource(
                    bar_revision_id=UUID(str(row[1])),
                    revision=int(row[10]),
                    open_value=Decimal(row[13]),
                    high_value=Decimal(row[14]),
                    low_value=Decimal(row[15]),
                    close_value=Decimal(row[16]),
                    **common,
                )
            )
        else:
            values.append(
                OutcomeGapSource(
                    gap_id=UUID(str(row[1])),
                    gap_kind=OutcomeGapKind(str(row[17])),
                    reason_code=str(row[18]),
                    **common,
                )
            )
    return tuple(values)


__all__ = [
    "PostgresOutcomeDependencyRepository",
    "PostgresOutcomeInputPreparationProvider",
]
