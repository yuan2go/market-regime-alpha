"""Exact, read-only preparation of Decision-time Authority inputs."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import psycopg

from market_regime_alpha.decision_support.domain import (
    CandidateDecisionFact,
    CandidateDisposition,
    CandidateSetDecisionSnapshot,
    DecisionReferenceAvailabilityStatus,
    DecisionReferenceFinalityStatus,
    DecisionReferenceSourceKind,
    DecisionReferenceValueStatus,
    DecisionRuntimeMode,
    OpenDecisionRunRequest,
    PreparedDecisionInputs,
    PreparedDecisionReference,
    PreparedResearchQualification,
    ProviderProductDecisionSnapshot,
    RuntimeDecisionSnapshot,
    TargetDecisionSnapshot,
    RequestedResearchQualification,
)
from market_regime_alpha.decision_support.domain.vocabulary import (
    ResearchPurpose,
)
from market_regime_alpha.decision_support.errors import (
    DecisionAuthorityIntegrityError,
    DecisionQualificationResolutionError,
    DecisionReferenceResolutionError,
)
from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.runtime.errors import RuntimeNotFoundError, StaleFenceError
from market_regime_alpha.runtime.ports import AttemptClaim


_MINUTE_WIDTHS = {
    "MINUTE_1": timedelta(minutes=1),
    "MINUTE_5": timedelta(minutes=5),
    "MINUTE_15": timedelta(minutes=15),
    "MINUTE_30": timedelta(minutes=30),
    "MINUTE_60": timedelta(minutes=60),
}


class PostgresDecisionInputPreparationProvider:
    """Resolve exact snapshots before the fenced write transaction begins."""

    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool

    def prepare(
        self,
        request: OpenDecisionRunRequest,
        runtime_claim: AttemptClaim,
    ) -> PreparedDecisionInputs:
        requested_targets = request.validated_targets()
        with self._pool.connection(read_only=True) as connection:
            runtime = _load_runtime(connection, runtime_claim)
            candidate_set = _load_candidate_set(
                connection,
                request.candidate_set_id,
                lock=False,
            )
            targets = tuple(
                _load_target(
                    connection,
                    item.target_definition_id,
                    item.reference_provider_product_id,
                    lock=False,
                )
                for item in requested_targets
            )
            references = tuple(
                reference
                for target in targets
                for reference in _load_target_references(
                    connection,
                    candidate_set,
                    target,
                )
            )
            research_qualifications = _load_research_qualifications(
                connection,
                request,
                decision_time=runtime.decision_time,
                lock=False,
            )
        return PreparedDecisionInputs(
            candidate_set=candidate_set,
            targets=targets,
            references=references,
            runtime=runtime,
            research_qualifications=research_qualifications,
        )


class PostgresDecisionResearchQualificationInputProvider:
    """Exact-ID, cutoff-aware, non-current Qualification read adapter."""

    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool

    def resolve_exact(
        self,
        requested: tuple[RequestedResearchQualification, ...],
        *,
        research_purpose: ResearchPurpose,
        decision_time: datetime,
    ) -> tuple[PreparedResearchQualification, ...]:
        with self._pool.connection(read_only=True) as connection:
            return _load_research_qualifications_from_requested(
                connection,
                requested,
                research_purpose=research_purpose,
                decision_time=decision_time,
                lock=False,
            )


class PostgresDecisionDependencyRepository:
    """Lock prepared identities in the frozen global order and reject drift."""

    def __init__(self, connection: psycopg.Connection[Any]) -> None:
        self._connection = connection

    def lock_and_revalidate(self, prepared: PreparedDecisionInputs) -> None:
        # Runtime is already locked by the application. Immutable dependency
        # locks follow stable kind/UUID order; Candidate rows are deliberately
        # last, matching the canonical cross-context lock order.
        for decision_code in sorted(
            item.decision_code for item in prepared.research_qualifications
        ):
            self._connection.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (f"research-qualification-decision:{decision_code}",),
            )
        actual_qualifications = _load_research_qualifications_from_prepared(
            self._connection,
            prepared.research_qualifications,
            research_purpose=(
                prepared.research_qualifications[0].qualification_purpose
                if prepared.research_qualifications
                else None
            ),
            decision_time=prepared.runtime.decision_time,
            lock=True,
        )
        if actual_qualifications != prepared.research_qualifications:
            raise DecisionAuthorityIntegrityError(
                "prepared Research Qualification changed before Decision closure"
            )

        for target in sorted(
            prepared.targets,
            key=lambda item: str(item.target_definition_id),
        ):
            actual = _load_target(
                self._connection,
                target.target_definition_id,
                target.reference_provider_product.provider_product_id,
                lock=True,
            )
            if actual != target:
                raise DecisionAuthorityIntegrityError(
                    "prepared Target or Provider Product changed before closure"
                )

        _lock_exact_reference_dependencies(self._connection, prepared)

        actual_candidate_set = _load_candidate_set(
            self._connection,
            prepared.candidate_set.candidate_set_id,
            lock=True,
        )
        if actual_candidate_set != prepared.candidate_set:
            raise DecisionAuthorityIntegrityError(
                "prepared CandidateSet changed before Decision closure"
            )


def _load_research_qualifications(
    connection: psycopg.Connection[Any],
    request: OpenDecisionRunRequest,
    *,
    decision_time: datetime,
    lock: bool,
) -> tuple[PreparedResearchQualification, ...]:
    requested = request.validated_research_qualifications()
    return _load_research_qualifications_from_requested(
        connection,
        requested,
        research_purpose=request.research_purpose,
        decision_time=decision_time,
        lock=lock,
    )


def _load_research_qualifications_from_prepared(
    connection: psycopg.Connection[Any],
    prepared: tuple[PreparedResearchQualification, ...],
    *,
    research_purpose: ResearchPurpose | None,
    decision_time: datetime,
    lock: bool,
) -> tuple[PreparedResearchQualification, ...]:
    if not prepared:
        return ()
    if research_purpose is None:
        raise DecisionQualificationResolutionError(
            "Research Qualification purpose is absent"
        )
    requested = tuple(
        RequestedResearchQualification(
            research_qualification_decision_id=(
                item.research_qualification_decision_id
            ),
            role=item.role,
        )
        for item in prepared
    )
    return _load_research_qualifications_from_requested(
        connection,
        requested,
        research_purpose=research_purpose,
        decision_time=decision_time,
        lock=lock,
    )


def _load_research_qualifications_from_requested(
    connection: psycopg.Connection[Any],
    requested,
    *,
    research_purpose: ResearchPurpose,
    decision_time: datetime,
    lock: bool,
) -> tuple[PreparedResearchQualification, ...]:
    rows: list[PreparedResearchQualification] = []
    suffix = " FOR SHARE OF qualification" if lock else ""
    for item in requested:
        row = connection.execute(
            """
            SELECT qualification.research_qualification_decision_id,
                   qualification.decision_code, qualification.revision,
                   qualification.supersedes_decision_id,
                   qualification.research_assessment_id,
                   qualification.research_qualification_policy_id,
                   qualification.experiment_id,
                   qualification.target_definition_id,
                   qualification.qualification_purpose,
                   qualification.source_generation_max_decision_time,
                   qualification.effective_at, qualification.known_at,
                   qualification.content_sha256
            FROM mra.research_qualification_decision AS qualification
            WHERE qualification.research_qualification_decision_id = %s
              AND qualification.decision_status = 'ADMITTED'
              AND qualification.qualification_purpose = %s
              AND qualification.effective_at <= %s
              AND qualification.known_at <= %s
              AND qualification.source_generation_max_decision_time < %s
              AND NOT EXISTS (
                  SELECT 1
                  FROM mra.research_qualification_decision AS successor
                  WHERE successor.supersedes_decision_id =
                        qualification.research_qualification_decision_id
                    AND successor.effective_at <= %s
                    AND successor.known_at <= %s
              )
            """
            + suffix,
            (
                item.research_qualification_decision_id,
                research_purpose.value,
                decision_time,
                decision_time,
                decision_time,
                decision_time,
                decision_time,
            ),
        ).fetchone()
        if row is None:
            raise DecisionQualificationResolutionError(
                "exact admitted Research Qualification is not visible at DecisionTime"
            )
        rows.append(
            PreparedResearchQualification(
                research_qualification_decision_id=UUID(str(row[0])),
                role=item.role,
                decision_code=str(row[1]),
                revision=int(row[2]),
                supersedes_decision_id=(
                    UUID(str(row[3])) if row[3] is not None else None
                ),
                research_assessment_id=UUID(str(row[4])),
                research_qualification_policy_id=UUID(str(row[5])),
                experiment_id=UUID(str(row[6])),
                target_definition_id=UUID(str(row[7])),
                qualification_purpose=ResearchPurpose(str(row[8])),
                source_generation_max_decision_time=row[9],
                effective_at=row[10],
                known_at=row[11],
                content_sha256=str(row[12]),
            )
        )
    return tuple(rows)


def _load_runtime(
    connection: psycopg.Connection[Any],
    claim: AttemptClaim,
) -> RuntimeDecisionSnapshot:
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
        JOIN mra.runtime_attempt AS attempt
          ON attempt.step_id = step.step_id
        WHERE run.run_id = %s
          AND step.step_id = %s
          AND attempt.attempt_id = %s
        """,
        (claim.run_id, claim.step_id, claim.attempt_id),
    ).fetchone()
    if row is None:
        raise RuntimeNotFoundError("OPEN_DECISION_RUN Runtime claim does not exist")
    exact_claim = (
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
        str(row[5]) == "OPEN_DECISION_RUN"
        and str(row[11]) == "RUNNING"
        and str(row[12]) == "RUNNING"
        and str(row[13]) == "RUNNING"
        and row[17] > datetime.now(UTC)
    )
    if not exact_claim or not live:
        raise StaleFenceError("OPEN_DECISION_RUN Runtime claim is no longer live")
    if row[7] is None:
        raise DecisionAuthorityIntegrityError("Decision Runtime has no DecisionTime")
    return RuntimeDecisionSnapshot(
        run_id=UUID(str(row[0])),
        step_id=UUID(str(row[1])),
        attempt_id=UUID(str(row[2])),
        fence_token=int(row[3]),
        step_key=str(row[4]),
        step_kind=str(row[5]),
        runtime_mode=DecisionRuntimeMode(str(row[6])),
        decision_time=row[7],
        code_sha=str(row[8]),
        config_artifact_id=UUID(str(row[9])),
        config_hash=str(row[10]),
    )


def _load_candidate_set(
    connection: psycopg.Connection[Any],
    candidate_set_id: UUID,
    *,
    lock: bool,
) -> CandidateSetDecisionSnapshot:
    suffix = " FOR SHARE" if lock else ""
    root = connection.execute(
        """
        SELECT candidate_set_id, content_sha256, dataset_id,
               candidate_policy_id, decision_time, population_count,
               selected_count, ranked_not_selected_count, unrankable_count
        FROM mra.candidate_set
        WHERE candidate_set_id = %s
        """
        + suffix,
        (candidate_set_id,),
    ).fetchone()
    if root is None:
        raise RuntimeNotFoundError(f"CandidateSet {candidate_set_id} does not exist")
    rows = connection.execute(
        """
        SELECT candidate_id, candidate_set_id, instrument_id, disposition
        FROM mra.candidate
        WHERE candidate_set_id = %s
        ORDER BY candidate_id
        """
        + suffix,
        (candidate_set_id,),
    ).fetchall()
    return CandidateSetDecisionSnapshot(
        candidate_set_id=UUID(str(root[0])),
        content_sha256=str(root[1]),
        dataset_id=UUID(str(root[2])),
        candidate_policy_id=UUID(str(root[3])),
        decision_time=root[4],
        population_count=int(root[5]),
        selected_count=int(root[6]),
        ranked_not_selected_count=int(root[7]),
        unrankable_count=int(root[8]),
        candidates=tuple(
            CandidateDecisionFact(
                candidate_id=UUID(str(row[0])),
                candidate_set_id=UUID(str(row[1])),
                instrument_id=UUID(str(row[2])),
                disposition=CandidateDisposition(str(row[3])),
            )
            for row in rows
        ),
    )


def _load_target(
    connection: psycopg.Connection[Any],
    target_definition_id: UUID,
    provider_product_id: UUID,
    *,
    lock: bool,
) -> TargetDecisionSnapshot:
    suffix = " FOR SHARE OF definition, checkpoint, product" if lock else ""
    row = connection.execute(
        """
        SELECT definition.target_definition_id, definition.target_code,
               definition.version, definition.content_sha256,
               checkpoint.target_checkpoint_id, checkpoint.content_sha256,
               checkpoint.ordinal, checkpoint.timeframe,
               checkpoint.price_basis, checkpoint.value_field,
               checkpoint.reference_rule, checkpoint.availability_rule,
               checkpoint.finality_rule,
               product.provider_product_id, product.provider_id,
               product.product_code, product.revision,
               product.decision_visibility_policy,
               product.source_availability_policy
        FROM mra.target_definition AS definition
        JOIN mra.target_checkpoint AS checkpoint
          ON checkpoint.target_definition_id = definition.target_definition_id
         AND checkpoint.checkpoint_role = 'DECISION_REFERENCE'
        JOIN mra.provider_product AS product
          ON product.provider_product_id = %s
        WHERE definition.target_definition_id = %s
          AND definition.registration_status = 'REGISTERED'
          AND 'MARKET_BAR' = ANY(product.fact_kinds)
          AND checkpoint.timeframe = ANY(product.bar_timeframes)
          AND checkpoint.price_basis = ANY(product.price_bases)
        """
        + suffix,
        (provider_product_id, target_definition_id),
    ).fetchone()
    if row is None:
        raise DecisionReferenceResolutionError(
            "Target, reference checkpoint, or Provider Product capability is absent"
        )
    return TargetDecisionSnapshot(
        target_definition_id=UUID(str(row[0])),
        target_code=str(row[1]),
        version=int(row[2]),
        content_sha256=str(row[3]),
        target_checkpoint_id=UUID(str(row[4])),
        checkpoint_content_sha256=str(row[5]),
        checkpoint_ordinal=int(row[6]),
        timeframe=str(row[7]),
        price_basis=str(row[8]),
        value_field=str(row[9]),
        reference_rule=str(row[10]),
        availability_rule=str(row[11]),
        finality_rule=str(row[12]),
        reference_provider_product=ProviderProductDecisionSnapshot(
            provider_product_id=UUID(str(row[13])),
            provider_id=UUID(str(row[14])),
            product_code=str(row[15]),
            revision=int(row[16]),
            decision_visibility_policy=str(row[17]),
            source_availability_policy=str(row[18]),
        ),
    )


def _load_target_references(
    connection: psycopg.Connection[Any],
    candidate_set: CandidateSetDecisionSnapshot,
    target: TargetDecisionSnapshot,
) -> tuple[PreparedDecisionReference, ...]:
    if not candidate_set.candidates:
        return ()
    checkpoint = connection.execute(
        """
        SELECT local_time, timezone_name
        FROM mra.target_checkpoint
        WHERE target_checkpoint_id = %s
          AND target_definition_id = %s
          AND content_sha256 = %s
        """,
        (
            target.target_checkpoint_id,
            target.target_definition_id,
            target.checkpoint_content_sha256,
        ),
    ).fetchone()
    if checkpoint is None:
        raise DecisionAuthorityIntegrityError("Target checkpoint identity drifted")
    local_time = checkpoint[0]
    timezone_name = str(checkpoint[1])
    zone = ZoneInfo(timezone_name)
    session_date = candidate_set.decision_time.astimezone(zone).date()
    session_rows = connection.execute(
        """
        SELECT candidate.candidate_id, candidate.instrument_id,
               instrument.exchange, instrument.instrument_type,
               session.session_id, session.session_date, session.open_at,
               session.break_start_at, session.break_end_at, session.close_at,
               session.timezone_name
        FROM mra.candidate AS candidate
        JOIN mra.instrument AS instrument
          ON instrument.instrument_id = candidate.instrument_id
        JOIN mra.trading_session AS session
          ON session.exchange = instrument.exchange
         AND session.session_date = %s
         AND session.decision_visible_at <= %s
        WHERE candidate.candidate_set_id = %s
        ORDER BY candidate.candidate_id
        """,
        (session_date, candidate_set.decision_time, candidate_set.candidate_set_id),
    ).fetchall()
    if len(session_rows) != len(candidate_set.candidates):
        raise DecisionReferenceResolutionError(
            "an exact Decision-visible trading session is missing"
        )
    windows = tuple(
        _reference_window(
            row,
            target=target,
            local_time=local_time,
            timezone_name=timezone_name,
            decision_time=candidate_set.decision_time,
        )
        for row in session_rows
    )
    observations = _load_exact_observations(
        connection,
        target=target,
        windows=windows,
        decision_time=candidate_set.decision_time,
    )
    return tuple(
        _select_exact_observation(
            observations.get(window.candidate_id, ()),
            target=target,
            window=window,
            decision_time=candidate_set.decision_time,
        )
        for window in windows
    )


class _ReferenceWindow:
    __slots__ = (
        "candidate_id",
        "instrument_id",
        "session_id",
        "event_start",
        "event_end",
    )

    def __init__(
        self,
        candidate_id: UUID,
        instrument_id: UUID,
        session_id: UUID,
        event_start: datetime,
        event_end: datetime,
    ) -> None:
        self.candidate_id = candidate_id
        self.instrument_id = instrument_id
        self.session_id = session_id
        self.event_start = event_start
        self.event_end = event_end


def _reference_window(
    row: tuple[Any, ...],
    *,
    target: TargetDecisionSnapshot,
    local_time: time,
    timezone_name: str,
    decision_time: datetime,
) -> _ReferenceWindow:
    if str(row[3]) != "EQUITY" or str(row[10]) != timezone_name:
        raise DecisionReferenceResolutionError(
            "Candidate instrument or session is outside Target scope"
        )
    local_date = row[5]
    if not isinstance(local_date, date):
        raise DecisionAuthorityIntegrityError("Trading Session date is invalid")
    event_end = datetime.combine(local_date, local_time, tzinfo=ZoneInfo(timezone_name)).astimezone(UTC)
    if target.timeframe == "DAILY":
        event_start = row[6]
    else:
        event_start = event_end - _MINUTE_WIDTHS[target.timeframe]
    if (
        event_end > decision_time
        or event_start < row[6]
        or event_end > row[9]
        or (
            row[7] is not None
            and row[8] is not None
            and event_start < row[8]
            and event_end > row[7]
        )
    ):
        raise DecisionReferenceResolutionError(
            "Target checkpoint does not identify a complete Decision-visible session bar"
        )
    return _ReferenceWindow(
        UUID(str(row[0])),
        UUID(str(row[1])),
        UUID(str(row[4])),
        event_start,
        event_end,
    )


def _load_exact_observations(
    connection: psycopg.Connection[Any],
    *,
    target: TargetDecisionSnapshot,
    windows: tuple[_ReferenceWindow, ...],
    decision_time: datetime,
) -> dict[UUID, tuple[tuple[Any, ...], ...]]:
    rows = connection.execute(
        """
        WITH requested AS (
            SELECT *
            FROM unnest(
                %s::uuid[], %s::uuid[], %s::uuid[],
                %s::timestamptz[], %s::timestamptz[]
            ) AS item(
                candidate_id, instrument_id, session_id,
                event_start, event_end
            )
        ), exact_observation AS (
            SELECT requested.candidate_id, 'BAR_REVISION'::text AS source_kind,
                   bar.bar_revision_id AS source_id, bar.capture_id,
                   bar.instrument_id, bar.session_id, bar.event_start,
                   bar.event_end, bar.recorded_at, bar.known_at,
                   bar.revision, NULL::text AS gap_kind,
                   NULL::text AS gap_reason_code,
                   CASE %s
                     WHEN 'OPEN' THEN bar.open_value
                     WHEN 'HIGH' THEN bar.high_value
                     WHEN 'LOW' THEN bar.low_value
                     WHEN 'CLOSE' THEN bar.close_value
                   END AS decimal_value,
                   capture.status,
                   mra.market_artifact_is_readable(
                       artifact.integrity_state, artifact.last_verified_at
                   ) AS artifact_readable
            FROM requested
            JOIN mra.market_bar_revision AS bar
              ON bar.provider_product_id = %s
             AND bar.instrument_id = requested.instrument_id
             AND bar.session_id = requested.session_id
             AND bar.timeframe = %s
             AND bar.price_basis = %s
             AND bar.event_start = requested.event_start
             AND bar.event_end = requested.event_end
             AND bar.decision_visible_at <= %s
            JOIN mra.data_capture AS capture
              ON capture.capture_id = bar.capture_id
             AND capture.provider_product_id = bar.provider_product_id
            LEFT JOIN mra.artifact AS artifact
              ON artifact.artifact_id = capture.artifact_id
            UNION ALL
            SELECT requested.candidate_id, 'SOURCE_GAP'::text,
                   gap.gap_id, gap.capture_id, gap.instrument_id,
                   gap.session_id, gap.event_start, gap.event_end,
                   gap.recorded_at, gap.known_at, NULL::integer,
                   gap.gap_kind, gap.reason_code, NULL::numeric,
                   capture.status,
                   CASE
                     WHEN capture.status = 'PROVIDER_FAILURE' THEN true
                     ELSE mra.market_artifact_is_readable(
                         artifact.integrity_state, artifact.last_verified_at
                     )
                   END
            FROM requested
            JOIN mra.source_gap AS gap
              ON gap.provider_product_id = %s
             AND gap.fact_kind = 'MARKET_BAR'
             AND gap.instrument_id = requested.instrument_id
             AND gap.session_id = requested.session_id
             AND gap.timeframe = %s
             AND gap.price_basis = %s
             AND gap.event_start = requested.event_start
             AND gap.event_end = requested.event_end
             AND gap.decision_visible_at <= %s
            JOIN mra.data_capture AS capture
              ON capture.capture_id = gap.capture_id
             AND capture.provider_product_id = gap.provider_product_id
            LEFT JOIN mra.artifact AS artifact
              ON artifact.artifact_id = capture.artifact_id
        )
        SELECT *
        FROM exact_observation
        ORDER BY candidate_id, known_at DESC, source_kind, source_id
        """,
        (
            [item.candidate_id for item in windows],
            [item.instrument_id for item in windows],
            [item.session_id for item in windows],
            [item.event_start for item in windows],
            [item.event_end for item in windows],
            target.value_field,
            target.reference_provider_product.provider_product_id,
            target.timeframe,
            target.price_basis,
            decision_time,
            target.reference_provider_product.provider_product_id,
            target.timeframe,
            target.price_basis,
            decision_time,
        ),
    ).fetchall()
    grouped: defaultdict[UUID, list[tuple[Any, ...]]] = defaultdict(list)
    for row in rows:
        grouped[UUID(str(row[0]))].append(row)
    return {key: tuple(value) for key, value in grouped.items()}


def _select_exact_observation(
    rows: tuple[tuple[Any, ...], ...],
    *,
    target: TargetDecisionSnapshot,
    window: _ReferenceWindow,
    decision_time: datetime,
) -> PreparedDecisionReference:
    if not rows:
        raise DecisionReferenceResolutionError(
            "Market Authority has neither an exact bar revision nor an exact SourceGap"
        )
    newest_known_at = rows[0][9]
    newest = tuple(row for row in rows if row[9] == newest_known_at)
    if len(newest) != 1:
        raise DecisionReferenceResolutionError(
            "Market Authority has ambiguous exact observations at the Decision boundary"
        )
    row = newest[0]
    if row[15] is not True:
        raise DecisionReferenceResolutionError(
            "exact Market reference provenance is not readable"
        )
    source_kind = DecisionReferenceSourceKind(str(row[1]))
    if source_kind is DecisionReferenceSourceKind.BAR_REVISION:
        if str(row[14]) != "CAPTURED":
            raise DecisionReferenceResolutionError(
                "bar revision does not belong to a captured source"
            )
        value_status = DecisionReferenceValueStatus.PRESENT
        availability_status = DecisionReferenceAvailabilityStatus.AVAILABLE
        bar_revision_id = UUID(str(row[2]))
        bar_revision = int(row[10])
        source_gap_id = None
        source_gap_kind = None
        source_gap_reason = None
        decimal_value = Decimal(row[13])
    else:
        source_gap_kind = str(row[11])
        missing = source_gap_kind in {"MISSING", "PLACEHOLDER"}
        value_status = (
            DecisionReferenceValueStatus.UNAVAILABLE
            if missing
            else DecisionReferenceValueStatus.FAILED
        )
        availability_status = (
            DecisionReferenceAvailabilityStatus.UNAVAILABLE
            if missing
            else DecisionReferenceAvailabilityStatus.FAILED
        )
        bar_revision_id = None
        bar_revision = None
        source_gap_id = UUID(str(row[2]))
        source_gap_reason = str(row[12])
        decimal_value = None
    return PreparedDecisionReference(
        candidate_id=window.candidate_id,
        target_definition_id=target.target_definition_id,
        target_checkpoint_id=target.target_checkpoint_id,
        provider_product_id=target.reference_provider_product.provider_product_id,
        provider_id=target.reference_provider_product.provider_id,
        capture_id=UUID(str(row[3])),
        instrument_id=UUID(str(row[4])),
        session_id=UUID(str(row[5])),
        event_start=row[6],
        event_end=row[7],
        observation_time=row[7],
        recorded_at=row[8],
        known_at=row[9],
        timeframe=target.timeframe,
        price_basis=target.price_basis,
        source_kind=source_kind,
        value_status=value_status,
        availability_status=availability_status,
        finality_status=DecisionReferenceFinalityStatus.UNKNOWN,
        value_field=target.value_field,
        decimal_value=decimal_value,
        bar_revision_id=bar_revision_id,
        bar_revision=bar_revision,
        source_gap_id=source_gap_id,
        source_gap_kind=source_gap_kind,
        source_gap_reason_code=source_gap_reason,
    )


def _lock_exact_reference_dependencies(
    connection: psycopg.Connection[Any],
    prepared: PreparedDecisionInputs,
) -> None:
    references = sorted(
        prepared.references,
        key=lambda item: (
            str(item.session_id),
            str(item.bar_revision_id or item.source_gap_id),
        ),
    )
    session_ids = sorted({item.session_id for item in references}, key=str)
    if session_ids:
        rows = connection.execute(
            """
            SELECT session_id
            FROM mra.trading_session
            WHERE session_id = ANY(%s::uuid[])
            ORDER BY session_id
            FOR SHARE
            """,
            (session_ids,),
        ).fetchall()
        if tuple(UUID(str(row[0])) for row in rows) != tuple(session_ids):
            raise DecisionAuthorityIntegrityError("prepared Trading Session is absent")
    capture_ids = sorted({item.capture_id for item in references}, key=str)
    if capture_ids:
        rows = connection.execute(
            """
            SELECT capture_id
            FROM mra.data_capture
            WHERE capture_id = ANY(%s::uuid[])
            ORDER BY capture_id
            FOR SHARE
            """,
            (capture_ids,),
        ).fetchall()
        if tuple(UUID(str(row[0])) for row in rows) != tuple(capture_ids):
            raise DecisionAuthorityIntegrityError("prepared Market Capture is absent")
    for reference in references:
        actual: tuple[object, ...] | None
        expected: tuple[object, ...]
        if reference.source_kind is DecisionReferenceSourceKind.BAR_REVISION:
            row = connection.execute(
                """
                SELECT capture_id, instrument_id, session_id, timeframe,
                       price_basis, event_start, event_end, revision,
                       recorded_at, known_at,
                       CASE %s
                         WHEN 'OPEN' THEN open_value
                         WHEN 'HIGH' THEN high_value
                         WHEN 'LOW' THEN low_value
                         WHEN 'CLOSE' THEN close_value
                       END
                FROM mra.market_bar_revision
                WHERE bar_revision_id = %s
                  AND provider_product_id = %s
                FOR SHARE
                """,
                (
                    reference.value_field,
                    reference.bar_revision_id,
                    reference.provider_product_id,
                ),
            ).fetchone()
            actual = None if row is None else (
                UUID(str(row[0])), UUID(str(row[1])), UUID(str(row[2])),
                str(row[3]), str(row[4]), row[5], row[6], int(row[7]),
                row[8], row[9], Decimal(row[10]),
            )
            expected = (
                reference.capture_id, reference.instrument_id,
                reference.session_id, reference.timeframe,
                reference.price_basis, reference.event_start,
                reference.event_end, reference.bar_revision,
                reference.recorded_at, reference.known_at,
                reference.decimal_value,
            )
        else:
            row = connection.execute(
                """
                SELECT capture_id, instrument_id, session_id, timeframe,
                       price_basis, event_start, event_end, gap_kind,
                       reason_code, recorded_at, known_at
                FROM mra.source_gap
                WHERE gap_id = %s
                  AND provider_product_id = %s
                  AND fact_kind = 'MARKET_BAR'
                FOR SHARE
                """,
                (reference.source_gap_id, reference.provider_product_id),
            ).fetchone()
            actual = None if row is None else (
                UUID(str(row[0])), UUID(str(row[1])), UUID(str(row[2])),
                str(row[3]), str(row[4]), row[5], row[6], str(row[7]),
                str(row[8]), row[9], row[10],
            )
            expected = (
                reference.capture_id, reference.instrument_id,
                reference.session_id, reference.timeframe,
                reference.price_basis, reference.event_start,
                reference.event_end, reference.source_gap_kind,
                reference.source_gap_reason_code, reference.recorded_at,
                reference.known_at,
            )
        if actual != expected:
            raise DecisionAuthorityIntegrityError(
                "prepared exact Market reference changed before closure"
            )
        if reference.known_at > prepared.runtime.decision_time:
            raise DecisionAuthorityIntegrityError(
                "prepared Market reference crossed the DecisionTime boundary"
            )


__all__ = [
    "PostgresDecisionDependencyRepository",
    "PostgresDecisionInputPreparationProvider",
    "PostgresDecisionResearchQualificationInputProvider",
]
