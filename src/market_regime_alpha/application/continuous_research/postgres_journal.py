"""Native PostgreSQL Continuous Research run/tick Journal."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from typing import TYPE_CHECKING, Any, Callable, Mapping
from uuid import uuid4

import psycopg

from market_regime_alpha.application.continuous_research.change_detection import (
    ChangeDecision,
    RecordedChangeDecision,
)
from market_regime_alpha.application.continuous_research.children import (
    ContinuousChildReference,
)
from market_regime_alpha.application.continuous_research.contracts import (
    ContinuousResearchCommand,
    RuntimeTickCommand,
)
from market_regime_alpha.application.continuous_research.evidence import (
    CurrentEvidenceSnapshot,
    EvidenceCommit,
    EvidenceCommitResult,
    ProviderAttemptOutcome,
    ProviderAttemptSnapshot,
    StartedProviderAttempt,
)
from market_regime_alpha.application.continuous_research.journal import (
    ClaimedRuntimeTick,
    ContinuousRunSnapshot,
    ContinuousRuntimeEvent,
    ContinuousTickSnapshot,
    ContinuousTickStatus,
    ProviderAttemptStatus,
    RuntimeTickReceipt,
)
from market_regime_alpha.application.continuous_research.policy import (
    ContinuousRunState,
    ContinuousSessionPhase,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import (
    canonical_json,
    require_sha256,
    require_text,
)
from market_regime_alpha.market_data.contracts import require_utc_second
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.postgres.migrator import PostgresMigrator
from market_regime_alpha.persistence.postgres.schema import (
    verify_postgres_authority_schema,
)

if TYPE_CHECKING:
    from market_regime_alpha.application.continuous_research.scheduler import (
        ContinuousScheduleSnapshot,
        TradingDayAssessment,
    )


Clock = Callable[[], datetime]
ClaimIdFactory = Callable[[], str]
DEFAULT_CONTINUOUS_TICK_LEASE = timedelta(seconds=30)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


class ContinuousResearchConflict(ValueError):
    """Raised when an idempotency identity resolves to different content."""


class ContinuousResearchClaimRejected(RuntimeError):
    """Raised when a worker does not hold the active tick Lease/fence."""


class ContinuousResearchNotFound(KeyError):
    """Raised when a run or tick does not exist in the selected authority."""


class PostgresContinuousResearchJournal:
    """Sole PostgreSQL writer for Continuous Research run and tick state."""

    def __init__(
        self,
        factory: PostgresConnectionFactory,
        *,
        clock: Clock = _utc_now,
        lease_duration: timedelta = DEFAULT_CONTINUOUS_TICK_LEASE,
        claim_id_factory: ClaimIdFactory | None = None,
        apply_migrations: bool = True,
    ) -> None:
        if not isinstance(factory, PostgresConnectionFactory):
            raise TypeError("factory must be a PostgresConnectionFactory")
        if not callable(clock):
            raise TypeError("clock must be callable")
        if lease_duration <= timedelta(0):
            raise ValueError("lease_duration must be positive")
        if claim_id_factory is not None and not callable(claim_id_factory):
            raise TypeError("claim_id_factory must be callable")
        if not isinstance(apply_migrations, bool):
            raise TypeError("apply_migrations must be bool")
        self._factory = factory
        self._clock = clock
        self._lease_duration = lease_duration
        self._claim_id_factory = claim_id_factory or (
            lambda: f"continuous-claim-{uuid4().hex}"
        )
        if apply_migrations:
            PostgresMigrator().apply_all(factory)
        with factory.connection(read_only=True) as connection:
            verify_postgres_authority_schema(connection)

    def create_or_get(
        self, command: ContinuousResearchCommand
    ) -> ContinuousRunSnapshot:
        if not isinstance(command, ContinuousResearchCommand):
            raise TypeError("command must be a ContinuousResearchCommand")
        now = self._now()

        def operation(connection: psycopg.Connection[Any]) -> None:
            same_date = connection.execute(
                """
                SELECT run_id, command_hash, idempotency_key
                FROM continuous_research_run
                WHERE trading_date = %s
                FOR UPDATE
                """,
                (command.trading_date,),
            ).fetchone()
            if (
                same_date is not None
                and str(same_date[2]) != command.idempotency_key
                and (
                    str(same_date[0]) != str(command.run_id)
                    or str(same_date[1]) != command.command_hash
                )
            ):
                raise ContinuousResearchConflict(
                    "only one Continuous parent is allowed per trading date"
                )
            inserted = connection.execute(
                """
                INSERT INTO continuous_research_run(
                    run_id, idempotency_key, command_hash, command_json,
                    trading_date, request_scope_hash, policy_id, policy_hash,
                    provider_configuration_id, provider_configuration_hash,
                    research_configuration_id, research_configuration_hash,
                    status, current_tick_sequence, version, created_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    'CREATED', 0, 1, %s, %s
                )
                ON CONFLICT (idempotency_key) DO NOTHING
                """,
                (
                    str(command.run_id),
                    command.idempotency_key,
                    command.command_hash,
                    canonical_json(command.to_canonical_dict()),
                    command.trading_date,
                    command.request_scope_hash,
                    str(command.policy_id),
                    command.policy_hash,
                    str(command.provider_configuration_id),
                    command.provider_configuration_hash,
                    str(command.research_configuration_id),
                    command.research_configuration_hash,
                    now,
                    now,
                ),
            ).rowcount
            row = connection.execute(
                """
                SELECT run_id, command_hash
                FROM continuous_research_run
                WHERE idempotency_key = %s
                FOR UPDATE
                """,
                (command.idempotency_key,),
            ).fetchone()
            if row is None:
                raise RuntimeError("Continuous Research run was not durable")
            if str(row[0]) != str(command.run_id) or str(row[1]) != command.command_hash:
                raise ContinuousResearchConflict(
                    "Continuous Research run idempotency conflict"
                )
            if inserted:
                self._insert_event(
                    connection,
                    run_id=command.run_id,
                    tick_id=None,
                    event_type="RUN_CREATED",
                    event_time=now,
                    fencing_token=None,
                    payload={"command_hash": command.command_hash},
                )

        self._factory.run_transaction(operation)
        return self.get_run(command.run_id)

    def initialize_schedule(
        self,
        *,
        run_command: ContinuousResearchCommand,
        policy: object,
        trading_day: TradingDayAssessment,
        initial_tick_at: datetime,
    ) -> ContinuousScheduleSnapshot:
        from market_regime_alpha.application.continuous_research.policy import (
            ContinuousDecisionWindowPolicy,
        )
        from market_regime_alpha.application.continuous_research.scheduler import (
            ContinuousScheduleStatus,
            TradingDayAssessment as TradingDayAssessmentContract,
            schedule_identity,
        )

        if not isinstance(policy, ContinuousDecisionWindowPolicy):
            raise TypeError("policy must be ContinuousDecisionWindowPolicy")
        if not isinstance(trading_day, TradingDayAssessmentContract):
            raise TypeError("trading_day must be TradingDayAssessment")
        require_utc_second("initial_tick_at", initial_tick_at)
        if (
            run_command.policy_id != policy.policy_id
            or run_command.policy_hash != policy.content_hash
            or run_command.trading_date != trading_day.trading_date
            or run_command.trading_calendar_id != trading_day.trading_calendar_id
            or run_command.trading_calendar_hash != trading_day.trading_calendar_hash
        ):
            raise ContinuousResearchConflict(
                "Continuous schedule inputs do not match the parent run"
            )
        schedule_id, schedule_hash = schedule_identity(
            run_command=run_command,
            policy=policy,
            trading_day=trading_day,
        )
        now = self._now()
        status = (
            ContinuousScheduleStatus.ACTIVE
            if trading_day.is_trading_day
            else ContinuousScheduleStatus.NON_TRADING_DAY
        )

        def operation(connection: psycopg.Connection[Any]) -> None:
            connection.execute(
                """
                INSERT INTO continuous_runtime_schedule(
                    schedule_id, schedule_hash, run_id, policy_id, policy_hash,
                    trading_calendar_id, trading_calendar_hash, status,
                    next_tick_at, last_reserved_tick_id, last_reserved_at,
                    version, created_at, updated_at, closed_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    NULL, NULL, 1, %s, %s, NULL
                )
                ON CONFLICT (run_id) DO NOTHING
                """,
                (
                    str(schedule_id),
                    schedule_hash,
                    str(run_command.run_id),
                    str(policy.policy_id),
                    policy.content_hash,
                    str(trading_day.trading_calendar_id),
                    trading_day.trading_calendar_hash,
                    status.value,
                    initial_tick_at if trading_day.is_trading_day else None,
                    now,
                    now,
                ),
            )
            durable = connection.execute(
                """
                SELECT schedule_id, schedule_hash
                FROM continuous_runtime_schedule
                WHERE run_id = %s
                FOR UPDATE
                """,
                (str(run_command.run_id),),
            ).fetchone()
            if (
                durable is None
                or str(durable[0]) != str(schedule_id)
                or str(durable[1]) != schedule_hash
            ):
                raise ContinuousResearchConflict(
                    "Continuous schedule identity conflict"
                )

        self._factory.run_transaction(operation)
        return self.get_schedule(run_command.run_id)

    def reserve_due_tick(
        self,
        *,
        run_command: ContinuousResearchCommand,
        policy: object,
        now: datetime,
    ) -> ContinuousTickSnapshot | None:
        from market_regime_alpha.application.continuous_research.policy import (
            ContinuousDecisionWindowPolicy,
        )
        from market_regime_alpha.application.continuous_research.scheduler import (
            ContinuousScheduleStatus,
        )

        if not isinstance(policy, ContinuousDecisionWindowPolicy):
            raise TypeError("policy must be ContinuousDecisionWindowPolicy")
        require_utc_second("now", now)
        reserved_tick_id: ArtifactId | None = None

        def operation(connection: psycopg.Connection[Any]) -> None:
            nonlocal reserved_tick_id
            schedule = connection.execute(
                """
                SELECT status, next_tick_at, version
                FROM continuous_runtime_schedule
                WHERE run_id = %s
                FOR UPDATE
                """,
                (str(run_command.run_id),),
            ).fetchone()
            if schedule is None:
                raise ContinuousResearchNotFound(
                    f"schedule:{run_command.run_id}"
                )
            status = ContinuousScheduleStatus(str(schedule[0]))
            scheduled_at = _optional_datetime(schedule[1])
            schedule_version = int(schedule[2])
            if (
                status is not ContinuousScheduleStatus.ACTIVE
                or scheduled_at is None
                or scheduled_at > now
            ):
                return
            assessment = policy.assess(
                trading_date=run_command.trading_date,
                observed_at=scheduled_at,
            )
            command = RuntimeTickCommand.create(
                idempotency_key=(
                    f"scheduled:{run_command.run_id}:"
                    f"{scheduled_at.isoformat()}"
                ),
                run_id=run_command.run_id,
                trading_date=run_command.trading_date,
                observed_at=scheduled_at,
                request_scope_hash=run_command.request_scope_hash,
                provider_configuration_id=run_command.provider_configuration_id,
                provider_configuration_hash=(
                    run_command.provider_configuration_hash
                ),
                research_configuration_id=run_command.research_configuration_id,
                research_configuration_hash=(
                    run_command.research_configuration_hash
                ),
                authority_mode=run_command.authority_mode,
            )
            run = connection.execute(
                """
                SELECT current_tick_sequence
                FROM continuous_research_run
                WHERE run_id = %s
                FOR UPDATE
                """,
                (str(run_command.run_id),),
            ).fetchone()
            if run is None:
                raise ContinuousResearchNotFound(str(run_command.run_id))
            sequence = int(run[0]) + 1
            connection.execute(
                """
                INSERT INTO continuous_runtime_tick(
                    run_id, tick_id, idempotency_key, tick_hash, tick_json,
                    tick_sequence, observed_at, session_phase, status, version,
                    fencing_token, created_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s,
                    'PENDING', 1, 0, %s, %s
                )
                """,
                (
                    str(command.run_id),
                    str(command.tick_id),
                    command.idempotency_key,
                    command.tick_hash,
                    canonical_json(command.to_canonical_dict()),
                    sequence,
                    command.observed_at,
                    assessment.session_phase.value,
                    now,
                    now,
                ),
            )
            run_state = _state_for_phase(assessment.session_phase)
            connection.execute(
                """
                UPDATE continuous_research_run
                SET status = %s, current_tick_sequence = %s,
                    version = version + 1, updated_at = %s,
                    closed_at = CASE
                        WHEN %s = 'MARKET_CLOSED' THEN COALESCE(closed_at, %s)
                        ELSE closed_at
                    END
                WHERE run_id = %s
                """,
                (
                    run_state.value,
                    sequence,
                    now,
                    run_state.value,
                    now,
                    str(run_command.run_id),
                ),
            )
            next_tick_at = policy.next_tick_after(
                trading_date=run_command.trading_date,
                observed_at=scheduled_at,
            )
            next_status = (
                ContinuousScheduleStatus.CLOSED
                if next_tick_at is None
                else ContinuousScheduleStatus.ACTIVE
            )
            connection.execute(
                """
                UPDATE continuous_runtime_schedule
                SET status = %s, next_tick_at = %s,
                    last_reserved_tick_id = %s, last_reserved_at = %s,
                    version = version + 1, updated_at = %s,
                    closed_at = CASE WHEN %s = 'CLOSED' THEN %s ELSE NULL END
                WHERE run_id = %s AND version = %s
                """,
                (
                    next_status.value,
                    next_tick_at,
                    str(command.tick_id),
                    now,
                    now,
                    next_status.value,
                    now,
                    str(run_command.run_id),
                    schedule_version,
                ),
            )
            self._insert_event(
                connection,
                run_id=run_command.run_id,
                tick_id=command.tick_id,
                event_type="TICK_ADMITTED",
                event_time=now,
                fencing_token=None,
                payload={
                    "session_phase": assessment.session_phase.value,
                    "tick_hash": command.tick_hash,
                    "tick_sequence": sequence,
                    "scheduled": True,
                },
            )
            reserved_tick_id = command.tick_id

        self._factory.run_transaction(operation)
        if reserved_tick_id is None:
            return None
        return self.get_tick(run_command.run_id, reserved_tick_id)

    def get_schedule(self, run_id: ArtifactId) -> ContinuousScheduleSnapshot:
        from market_regime_alpha.application.continuous_research.scheduler import (
            ContinuousScheduleSnapshot,
            ContinuousScheduleStatus,
        )

        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT schedule_id, schedule_hash, run_id, status,
                       next_tick_at, last_reserved_tick_id, last_reserved_at,
                       version, created_at, updated_at, closed_at
                FROM continuous_runtime_schedule
                WHERE run_id = %s
                """,
                (str(run_id),),
            ).fetchone()
        if row is None:
            raise ContinuousResearchNotFound(f"schedule:{run_id}")
        return ContinuousScheduleSnapshot(
            schedule_id=ArtifactId(str(row[0])),
            schedule_hash=str(row[1]),
            run_id=ArtifactId(str(row[2])),
            status=ContinuousScheduleStatus(str(row[3])),
            next_tick_at=_optional_datetime(row[4]),
            last_reserved_tick_id=(
                None if row[5] is None else ArtifactId(str(row[5]))
            ),
            last_reserved_at=_optional_datetime(row[6]),
            version=int(row[7]),
            created_at=_datetime(row[8]),
            updated_at=_datetime(row[9]),
            closed_at=_optional_datetime(row[10]),
        )

    def get_recoverable_tick(
        self,
        run_id: ArtifactId,
        *,
        now: datetime,
    ) -> ContinuousTickSnapshot | None:
        require_utc_second("now", now)
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT tick_id
                FROM continuous_runtime_tick
                WHERE run_id = %s
                  AND (
                    (status = 'PENDING' AND (retry_at IS NULL OR retry_at <= %s))
                    OR (status = 'IN_PROGRESS' AND lease_expires_at <= %s)
                  )
                ORDER BY tick_sequence
                LIMIT 1
                """,
                (str(run_id), now, now),
            ).fetchone()
        if row is None:
            return None
        return self.get_tick(run_id, ArtifactId(str(row[0])))

    def admit_tick(
        self,
        command: RuntimeTickCommand,
        *,
        session_phase: ContinuousSessionPhase,
    ) -> ContinuousTickSnapshot:
        if not isinstance(command, RuntimeTickCommand):
            raise TypeError("command must be a RuntimeTickCommand")
        if not isinstance(session_phase, ContinuousSessionPhase):
            raise TypeError("session_phase must be a ContinuousSessionPhase")
        now = self._now()

        def operation(connection: psycopg.Connection[Any]) -> None:
            existing = connection.execute(
                """
                SELECT run_id, tick_id, tick_hash, session_phase
                FROM continuous_runtime_tick
                WHERE idempotency_key = %s
                FOR UPDATE
                """,
                (command.idempotency_key,),
            ).fetchone()
            if existing is not None:
                if (
                    str(existing[0]) != str(command.run_id)
                    or str(existing[1]) != str(command.tick_id)
                    or str(existing[2]) != command.tick_hash
                    or str(existing[3]) != session_phase.value
                ):
                    raise ContinuousResearchConflict(
                        "Continuous Runtime tick idempotency conflict"
                    )
                return
            run = connection.execute(
                """
                SELECT request_scope_hash, provider_configuration_hash,
                       research_configuration_hash, current_tick_sequence
                FROM continuous_research_run
                WHERE run_id = %s
                FOR UPDATE
                """,
                (str(command.run_id),),
            ).fetchone()
            if run is None:
                raise ContinuousResearchNotFound(str(command.run_id))
            if (
                str(run[0]) != command.request_scope_hash
                or str(run[1]) != command.provider_configuration_hash
                or str(run[2]) != command.research_configuration_hash
            ):
                raise ContinuousResearchConflict(
                    "Runtime Tick command does not match its parent run"
                )
            sequence = int(run[3]) + 1
            connection.execute(
                """
                INSERT INTO continuous_runtime_tick(
                    run_id, tick_id, idempotency_key, tick_hash, tick_json,
                    tick_sequence, observed_at, session_phase, status, version,
                    fencing_token, created_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s,
                    'PENDING', 1, 0, %s, %s
                )
                """,
                (
                    str(command.run_id),
                    str(command.tick_id),
                    command.idempotency_key,
                    command.tick_hash,
                    canonical_json(command.to_canonical_dict()),
                    sequence,
                    command.observed_at,
                    session_phase.value,
                    now,
                    now,
                ),
            )
            run_state = _state_for_phase(session_phase)
            connection.execute(
                """
                UPDATE continuous_research_run
                SET status = %s,
                    current_tick_sequence = %s,
                    version = version + 1,
                    updated_at = %s,
                    closed_at = CASE
                        WHEN %s = 'MARKET_CLOSED' THEN COALESCE(closed_at, %s)
                        ELSE closed_at
                    END
                WHERE run_id = %s
                """,
                (
                    run_state.value,
                    sequence,
                    now,
                    run_state.value,
                    now,
                    str(command.run_id),
                ),
            )
            self._insert_event(
                connection,
                run_id=command.run_id,
                tick_id=command.tick_id,
                event_type="TICK_ADMITTED",
                event_time=now,
                fencing_token=None,
                payload={
                    "session_phase": session_phase.value,
                    "tick_hash": command.tick_hash,
                    "tick_sequence": sequence,
                },
            )

        self._factory.run_transaction(operation)
        return self.get_tick(command.run_id, command.tick_id)

    def claim_next(self, run_id: ArtifactId) -> ClaimedRuntimeTick:
        now = self._now()

        def operation(
            connection: psycopg.Connection[Any],
        ) -> ClaimedRuntimeTick:
            row = connection.execute(
                """
                SELECT tick_id, tick_sequence, version, fencing_token
                FROM continuous_runtime_tick
                WHERE run_id = %s
                  AND status = 'PENDING'
                  AND (retry_at IS NULL OR retry_at <= %s)
                ORDER BY tick_sequence
                LIMIT 1
                FOR UPDATE SKIP LOCKED
                """,
                (str(run_id), now),
            ).fetchone()
            if row is None:
                raise ContinuousResearchClaimRejected("no claimable Continuous tick")
            return self._claim_locked(
                connection,
                run_id=run_id,
                tick_id=ArtifactId(str(row[0])),
                tick_sequence=int(row[1]),
                version=int(row[2]),
                fencing_token=int(row[3]),
                now=now,
            )

        return self._factory.run_transaction(operation)

    def claim_tick(
        self, *, run_id: ArtifactId, tick_id: ArtifactId
    ) -> ClaimedRuntimeTick:
        now = self._now()

        def operation(
            connection: psycopg.Connection[Any],
        ) -> ClaimedRuntimeTick:
            row = connection.execute(
                """
                SELECT status, tick_sequence, version, fencing_token,
                       lease_expires_at, retry_at
                FROM continuous_runtime_tick
                WHERE run_id = %s AND tick_id = %s
                FOR UPDATE
                """,
                (str(run_id), str(tick_id)),
            ).fetchone()
            if row is None:
                raise ContinuousResearchNotFound(f"{run_id}/{tick_id}")
            status = ContinuousTickStatus(str(row[0]))
            sequence = int(row[1])
            version = int(row[2])
            fencing_token = int(row[3])
            lease_expires_at = _optional_datetime(row[4])
            retry_at = _optional_datetime(row[5])
            if status is ContinuousTickStatus.IN_PROGRESS:
                if lease_expires_at is not None and lease_expires_at > now:
                    raise ContinuousResearchClaimRejected(
                        "Continuous tick has an active lease"
                    )
                connection.execute(
                    """
                    UPDATE continuous_runtime_tick
                    SET status = 'PENDING', version = version + 1,
                        claim_id = NULL, lease_acquired_at = NULL,
                        lease_expires_at = NULL, heartbeat_at = NULL,
                        last_error = 'LEASE_EXPIRED', retry_at = NULL,
                        updated_at = %s
                    WHERE run_id = %s AND tick_id = %s AND version = %s
                    """,
                    (now, str(run_id), str(tick_id), version),
                )
                self._insert_event(
                    connection,
                    run_id=run_id,
                    tick_id=tick_id,
                    event_type="LEASE_EXPIRED",
                    event_time=now,
                    fencing_token=fencing_token,
                    payload={"expired_fencing_token": fencing_token},
                )
                status = ContinuousTickStatus.PENDING
                version += 1
            if status is not ContinuousTickStatus.PENDING:
                raise ContinuousResearchClaimRejected(
                    "Continuous tick is terminal and cannot be claimed"
                )
            if retry_at is not None and retry_at > now:
                raise ContinuousResearchClaimRejected("Continuous tick retry is not due")
            return self._claim_locked(
                connection,
                run_id=run_id,
                tick_id=tick_id,
                tick_sequence=sequence,
                version=version,
                fencing_token=fencing_token,
                now=now,
            )

        return self._factory.run_transaction(operation)

    def heartbeat(self, claim: ClaimedRuntimeTick) -> ClaimedRuntimeTick:
        self._require_claim(claim)
        now = self._now()
        lease_expires_at = now + self._lease_duration

        def operation(
            connection: psycopg.Connection[Any],
        ) -> ClaimedRuntimeTick:
            row = connection.execute(
                """
                UPDATE continuous_runtime_tick
                SET heartbeat_at = %s, lease_expires_at = %s,
                    version = version + 1, updated_at = %s
                WHERE run_id = %s AND tick_id = %s
                  AND status = 'IN_PROGRESS'
                  AND claim_id = %s AND fencing_token = %s AND version = %s
                  AND lease_expires_at > %s
                RETURNING version
                """,
                (
                    now,
                    lease_expires_at,
                    now,
                    str(claim.run_id),
                    str(claim.tick_id),
                    claim.claim_id,
                    claim.fencing_token,
                    claim.tick_version,
                    now,
                ),
            ).fetchone()
            if row is None:
                raise ContinuousResearchClaimRejected(
                    "Continuous tick heartbeat rejected by fencing"
                )
            self._insert_event(
                connection,
                run_id=claim.run_id,
                tick_id=claim.tick_id,
                event_type="TICK_HEARTBEAT",
                event_time=now,
                fencing_token=claim.fencing_token,
                payload={"tick_version": int(row[0])},
            )
            return replace(
                claim,
                tick_version=int(row[0]),
                heartbeat_at=now,
                lease_expires_at=lease_expires_at,
            )

        return self._factory.run_transaction(operation)

    def assert_claim_active(self, claim: ClaimedRuntimeTick) -> None:
        """Authorize a child final-write transaction against the active fence."""

        self._require_claim(claim)
        now = self._now()
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT 1
                FROM continuous_runtime_tick
                WHERE run_id = %s AND tick_id = %s
                  AND status = 'IN_PROGRESS'
                  AND claim_id = %s AND fencing_token = %s AND version = %s
                  AND lease_expires_at > %s
                """,
                (
                    str(claim.run_id),
                    str(claim.tick_id),
                    claim.claim_id,
                    claim.fencing_token,
                    claim.tick_version,
                    now,
                ),
            ).fetchone()
        if row is None:
            raise ContinuousResearchClaimRejected(
                "child final write rejected by Continuous fencing"
            )

    def complete_tick(
        self,
        *,
        claim: ClaimedRuntimeTick,
        receipt: RuntimeTickReceipt,
        run_state: ContinuousRunState,
    ) -> ContinuousTickSnapshot:
        self._require_claim(claim)
        if not isinstance(receipt, RuntimeTickReceipt):
            raise TypeError("receipt must be a RuntimeTickReceipt")
        if not isinstance(run_state, ContinuousRunState):
            raise TypeError("run_state must be a ContinuousRunState")
        receipt.verify_identity()
        if (
            receipt.run_id != claim.run_id
            or receipt.tick_id != claim.tick_id
            or receipt.tick_sequence != claim.tick_sequence
            or receipt.claim_id != claim.claim_id
            or receipt.fencing_token != claim.fencing_token
        ):
            raise ContinuousResearchClaimRejected(
                "Runtime Tick receipt does not match active fencing"
            )
        now = self._now()

        def operation(connection: psycopg.Connection[Any]) -> None:
            row = connection.execute(
                """
                UPDATE continuous_runtime_tick
                SET status = 'COMPLETED', version = version + 1,
                    claim_id = NULL, lease_acquired_at = NULL,
                    lease_expires_at = NULL, heartbeat_at = NULL,
                    receipt_id = %s, receipt_hash = %s, receipt_json = %s,
                    last_error = NULL, retry_at = NULL,
                    updated_at = %s, completed_at = %s
                WHERE run_id = %s AND tick_id = %s
                  AND status = 'IN_PROGRESS'
                  AND claim_id = %s AND fencing_token = %s AND version = %s
                  AND lease_expires_at > %s
                RETURNING version
                """,
                (
                    str(receipt.receipt_id),
                    receipt.receipt_hash,
                    canonical_json(receipt.to_canonical_dict()),
                    now,
                    now,
                    str(claim.run_id),
                    str(claim.tick_id),
                    claim.claim_id,
                    claim.fencing_token,
                    claim.tick_version,
                    now,
                ),
            ).fetchone()
            if row is None:
                raise ContinuousResearchClaimRejected(
                    "Continuous tick completion rejected by fencing"
                )
            self._update_run_state(connection, claim.run_id, run_state, now)
            self._insert_event(
                connection,
                run_id=claim.run_id,
                tick_id=claim.tick_id,
                event_type="TICK_COMPLETED",
                event_time=now,
                fencing_token=claim.fencing_token,
                payload={
                    "receipt_hash": receipt.receipt_hash,
                    "run_state": run_state.value,
                },
            )

        self._factory.run_transaction(operation)
        return self.get_tick(claim.run_id, claim.tick_id)

    def fail_tick(
        self,
        *,
        claim: ClaimedRuntimeTick,
        error: str,
        retryable: bool,
        retry_at: datetime | None,
    ) -> ContinuousTickSnapshot:
        self._require_claim(claim)
        require_text("error", error)
        if not isinstance(retryable, bool):
            raise TypeError("retryable must be a bool")
        if retry_at is not None:
            require_utc_second("retry_at", retry_at)
        if retryable and retry_at is None:
            raise ValueError("retryable failure requires retry_at")
        now = self._now()
        tick_status = (
            ContinuousTickStatus.PENDING
            if retryable
            else ContinuousTickStatus.FAILED
        )
        run_state = (
            ContinuousRunState.RETRYING if retryable else ContinuousRunState.FAILED
        )

        def operation(connection: psycopg.Connection[Any]) -> None:
            row = connection.execute(
                """
                UPDATE continuous_runtime_tick
                SET status = %s, version = version + 1,
                    claim_id = NULL, lease_acquired_at = NULL,
                    lease_expires_at = NULL, heartbeat_at = NULL,
                    last_error = %s, retry_at = %s,
                    updated_at = %s,
                    completed_at = CASE WHEN %s = 'FAILED' THEN %s ELSE NULL END
                WHERE run_id = %s AND tick_id = %s
                  AND status = 'IN_PROGRESS'
                  AND claim_id = %s AND fencing_token = %s AND version = %s
                  AND lease_expires_at > %s
                RETURNING version
                """,
                (
                    tick_status.value,
                    error,
                    retry_at,
                    now,
                    tick_status.value,
                    now,
                    str(claim.run_id),
                    str(claim.tick_id),
                    claim.claim_id,
                    claim.fencing_token,
                    claim.tick_version,
                    now,
                ),
            ).fetchone()
            if row is None:
                raise ContinuousResearchClaimRejected(
                    "Continuous tick failure rejected by fencing"
                )
            self._update_run_state(connection, claim.run_id, run_state, now)
            self._insert_event(
                connection,
                run_id=claim.run_id,
                tick_id=claim.tick_id,
                event_type="TICK_FAILED",
                event_time=now,
                fencing_token=claim.fencing_token,
                payload={"error": error, "retryable": retryable},
            )

        self._factory.run_transaction(operation)
        return self.get_tick(claim.run_id, claim.tick_id)

    def start_provider_attempt(
        self,
        *,
        claim: ClaimedRuntimeTick,
        provider_id: str,
        product: str,
        request_hash: str,
        provider_revision: str | None,
    ) -> StartedProviderAttempt:
        self._require_claim(claim)
        require_text("provider_id", provider_id)
        require_text("product", product)
        if provider_revision is not None:
            require_text("provider_revision", provider_revision)
        require_sha256("request_hash", request_hash)
        now = self._now()

        def operation(
            connection: psycopg.Connection[Any],
        ) -> tuple[int, int]:
            active = connection.execute(
                """
                SELECT COALESCE(MAX(attempt_number), 0)
                FROM continuous_provider_attempt
                WHERE run_id = %s AND tick_id = %s
                """,
                (str(claim.run_id), str(claim.tick_id)),
            ).fetchone()
            attempt_number = 1 if active is None else int(active[0]) + 1
            attempt_row = connection.execute(
                """
                INSERT INTO continuous_provider_attempt(
                    run_id, tick_id, attempt_number, claim_id, fencing_token,
                    tick_version, provider_id, product, request_hash,
                    started_at, lease_expires_at, heartbeat_at, status,
                    reason_codes_json, provider_revision, attempt_json
                )
                SELECT %s, %s, %s, %s, %s, %s, %s, %s, %s,
                       %s, lease_expires_at, heartbeat_at, 'STARTED',
                       '[]', %s, %s
                FROM continuous_runtime_tick
                WHERE run_id = %s AND tick_id = %s
                  AND status = 'IN_PROGRESS'
                  AND claim_id = %s AND fencing_token = %s AND version = %s
                  AND lease_expires_at > %s
                RETURNING attempt_id
                """,
                (
                    str(claim.run_id),
                    str(claim.tick_id),
                    attempt_number,
                    claim.claim_id,
                    claim.fencing_token,
                    claim.tick_version,
                    provider_id,
                    product,
                    request_hash,
                    now,
                    provider_revision,
                    canonical_json(
                        {
                            "schema_version": "continuous-provider-attempt-v1",
                            "status": ProviderAttemptStatus.STARTED.value,
                        }
                    ),
                    str(claim.run_id),
                    str(claim.tick_id),
                    claim.claim_id,
                    claim.fencing_token,
                    claim.tick_version,
                    now,
                ),
            ).fetchone()
            if attempt_row is None:
                raise ContinuousResearchClaimRejected(
                    "Provider Attempt start rejected by fencing"
                )
            attempt_id = int(attempt_row[0])
            tick_row = connection.execute(
                """
                UPDATE continuous_runtime_tick
                SET provider_attempt_id = %s, version = version + 1,
                    updated_at = %s
                WHERE run_id = %s AND tick_id = %s
                  AND status = 'IN_PROGRESS'
                  AND claim_id = %s AND fencing_token = %s AND version = %s
                  AND lease_expires_at > %s
                RETURNING version
                """,
                (
                    attempt_id,
                    now,
                    str(claim.run_id),
                    str(claim.tick_id),
                    claim.claim_id,
                    claim.fencing_token,
                    claim.tick_version,
                    now,
                ),
            ).fetchone()
            if tick_row is None:
                raise ContinuousResearchClaimRejected(
                    "Provider Attempt pointer rejected by fencing"
                )
            self._insert_event(
                connection,
                run_id=claim.run_id,
                tick_id=claim.tick_id,
                event_type="PROVIDER_ATTEMPT_STARTED",
                event_time=now,
                fencing_token=claim.fencing_token,
                payload={
                    "attempt_id": attempt_id,
                    "attempt_number": attempt_number,
                    "provider_id": provider_id,
                    "product": product,
                },
            )
            return attempt_id, int(tick_row[0])

        attempt_id, tick_version = self._factory.run_transaction(operation)
        return StartedProviderAttempt(
            attempt=self.get_provider_attempt(attempt_id),
            claim=replace(claim, tick_version=tick_version),
        )

    def complete_provider_attempt(
        self,
        *,
        claim: ClaimedRuntimeTick,
        attempt_id: int,
        outcome: ProviderAttemptOutcome,
    ) -> ProviderAttemptSnapshot:
        self._require_claim(claim)
        if (
            isinstance(attempt_id, bool)
            or not isinstance(attempt_id, int)
            or attempt_id < 1
        ):
            raise ValueError("attempt_id must be positive")
        if not isinstance(outcome, ProviderAttemptOutcome):
            raise TypeError("outcome must be a ProviderAttemptOutcome")
        now = self._now()

        def operation(connection: psycopg.Connection[Any]) -> None:
            active = connection.execute(
                """
                SELECT 1
                FROM continuous_runtime_tick
                WHERE run_id = %s AND tick_id = %s
                  AND status = 'IN_PROGRESS'
                  AND claim_id = %s AND fencing_token = %s AND version = %s
                  AND lease_expires_at > %s
                FOR UPDATE
                """,
                (
                    str(claim.run_id),
                    str(claim.tick_id),
                    claim.claim_id,
                    claim.fencing_token,
                    claim.tick_version,
                    now,
                ),
            ).fetchone()
            if active is None:
                raise ContinuousResearchClaimRejected(
                    "Provider Attempt completion rejected by fencing"
                )
            row = connection.execute(
                """
                UPDATE continuous_provider_attempt
                SET completed_at = %s, status = %s,
                    raw_response_hash = %s,
                    source_manifest_id = %s, source_manifest_hash = %s,
                    error_code = %s, error_message = %s,
                    reason_codes_json = %s, retry_at = %s,
                    attempt_json = %s
                WHERE attempt_id = %s AND run_id = %s AND tick_id = %s
                  AND claim_id = %s AND fencing_token = %s
                  AND status = 'STARTED'
                  AND started_at <= %s
                RETURNING attempt_id
                """,
                (
                    outcome.completed_at,
                    outcome.status.value,
                    outcome.raw_response_hash,
                    (
                        None
                        if outcome.source_manifest_id is None
                        else str(outcome.source_manifest_id)
                    ),
                    outcome.source_manifest_hash,
                    outcome.error_code,
                    outcome.error_message,
                    _json_array(outcome.reason_codes),
                    outcome.retry_at,
                    canonical_json(
                        {
                            "schema_version": "continuous-provider-attempt-v1",
                            "outcome": outcome.to_canonical_dict(),
                        }
                    ),
                    attempt_id,
                    str(claim.run_id),
                    str(claim.tick_id),
                    claim.claim_id,
                    claim.fencing_token,
                    outcome.completed_at,
                ),
            ).fetchone()
            if row is None:
                raise ContinuousResearchClaimRejected(
                    "Provider Attempt completion rejected by identity fencing"
                )
            self._insert_event(
                connection,
                run_id=claim.run_id,
                tick_id=claim.tick_id,
                event_type="PROVIDER_ATTEMPT_COMPLETED",
                event_time=now,
                fencing_token=claim.fencing_token,
                payload={"attempt_id": attempt_id, "status": outcome.status.value},
            )

        self._factory.run_transaction(operation)
        return self.get_provider_attempt(attempt_id)

    def commit_evidence(
        self,
        *,
        claim: ClaimedRuntimeTick,
        attempt: ProviderAttemptSnapshot,
        evidence: EvidenceCommit,
    ) -> EvidenceCommitResult:
        self._require_claim(claim)
        if not isinstance(attempt, ProviderAttemptSnapshot):
            raise TypeError("attempt must be a ProviderAttemptSnapshot")
        if not isinstance(evidence, EvidenceCommit):
            raise TypeError("evidence must be an EvidenceCommit")
        evidence.verify_identity()
        if (
            attempt.status is not ProviderAttemptStatus.SUCCEEDED
            or attempt.attempt_id != evidence.attempt_id
            or attempt.run_id != claim.run_id
            or attempt.tick_id != claim.tick_id
            or evidence.run_id != claim.run_id
            or evidence.tick_id != claim.tick_id
            or attempt.source_manifest_id != evidence.source_manifest_id
            or attempt.source_manifest_hash != evidence.source_manifest_hash
        ):
            raise ContinuousResearchConflict(
                "Evidence does not match a successful validated Provider Attempt"
            )
        now = self._now()

        def operation(
            connection: psycopg.Connection[Any],
        ) -> tuple[bool, int]:
            active = connection.execute(
                """
                SELECT 1
                FROM continuous_runtime_tick
                WHERE run_id = %s AND tick_id = %s
                  AND status = 'IN_PROGRESS'
                  AND claim_id = %s AND fencing_token = %s AND version = %s
                  AND lease_expires_at > %s
                FOR UPDATE
                """,
                (
                    str(claim.run_id),
                    str(claim.tick_id),
                    claim.claim_id,
                    claim.fencing_token,
                    claim.tick_version,
                    now,
                ),
            ).fetchone()
            if active is None:
                raise ContinuousResearchClaimRejected(
                    "Evidence commit rejected by fencing"
                )
            authoritative_attempt = connection.execute(
                """
                SELECT status, source_manifest_id, source_manifest_hash
                FROM continuous_provider_attempt
                WHERE attempt_id = %s AND run_id = %s AND tick_id = %s
                FOR UPDATE
                """,
                (attempt.attempt_id, str(claim.run_id), str(claim.tick_id)),
            ).fetchone()
            if authoritative_attempt is None or str(authoritative_attempt[0]) != "SUCCEEDED":
                raise ContinuousResearchConflict(
                    "Evidence requires a durable successful Provider Attempt"
                )
            if (
                str(authoritative_attempt[1]) != str(evidence.source_manifest_id)
                or str(authoritative_attempt[2]) != evidence.source_manifest_hash
            ):
                raise ContinuousResearchConflict(
                    "Evidence SourceManifest differs from Provider Attempt"
                )
            connection.execute(
                """
                INSERT INTO continuous_evidence_commit(
                    evidence_commit_id, commit_hash, run_id, tick_id, attempt_id,
                    evidence_scope, trading_date, request_scope_hash,
                    source_manifest_id, source_manifest_hash,
                    raw_artifact_id, raw_artifact_hash,
                    evidence_artifact_id, evidence_artifact_hash,
                    material_identity_hash,
                    provider_configuration_id, provider_configuration_hash,
                    effective_at, retrieved_at, available_at, as_of_time,
                    quality_status, evidence_qualification, evidence_json,
                    created_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s
                )
                ON CONFLICT (attempt_id) DO NOTHING
                """,
                (
                    str(evidence.evidence_commit_id),
                    evidence.commit_hash,
                    str(evidence.run_id),
                    str(evidence.tick_id),
                    evidence.attempt_id,
                    evidence.evidence_scope,
                    evidence.trading_date,
                    evidence.request_scope_hash,
                    str(evidence.source_manifest_id),
                    evidence.source_manifest_hash,
                    (
                        None
                        if evidence.raw_artifact_id is None
                        else str(evidence.raw_artifact_id)
                    ),
                    evidence.raw_artifact_hash,
                    str(evidence.evidence_artifact_id),
                    evidence.evidence_artifact_hash,
                    evidence.material_identity_hash,
                    str(evidence.provider_configuration_id),
                    evidence.provider_configuration_hash,
                    evidence.effective_at,
                    evidence.retrieved_at,
                    evidence.available_at,
                    evidence.as_of_time,
                    evidence.quality_status.value,
                    evidence.evidence_qualification,
                    canonical_json(evidence.to_canonical_dict()),
                    now,
                ),
            )
            durable = connection.execute(
                """
                SELECT evidence_commit_id, commit_hash
                FROM continuous_evidence_commit
                WHERE attempt_id = %s
                """,
                (evidence.attempt_id,),
            ).fetchone()
            if (
                durable is None
                or str(durable[0]) != str(evidence.evidence_commit_id)
                or str(durable[1]) != evidence.commit_hash
            ):
                raise ContinuousResearchConflict("Evidence Attempt idempotency conflict")
            current = connection.execute(
                """
                SELECT evidence_commit_id, material_identity_hash, version
                FROM continuous_current_evidence
                WHERE run_id = %s AND evidence_scope = %s
                FOR UPDATE
                """,
                (str(claim.run_id), evidence.evidence_scope),
            ).fetchone()
            current_advanced = False
            if current is None:
                connection.execute(
                    """
                    INSERT INTO continuous_current_evidence(
                        run_id, evidence_scope, evidence_commit_id,
                        evidence_commit_hash, material_identity_hash,
                        version, last_accepted_fencing_token, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, 1, %s, %s)
                    """,
                    (
                        str(claim.run_id),
                        evidence.evidence_scope,
                        str(evidence.evidence_commit_id),
                        evidence.commit_hash,
                        evidence.material_identity_hash,
                        claim.fencing_token,
                        now,
                    ),
                )
                current_advanced = True
            elif str(current[1]) != evidence.material_identity_hash:
                updated = connection.execute(
                    """
                    UPDATE continuous_current_evidence
                    SET evidence_commit_id = %s, evidence_commit_hash = %s,
                        material_identity_hash = %s, version = version + 1,
                        last_accepted_fencing_token = %s, updated_at = %s
                    WHERE run_id = %s AND evidence_scope = %s AND version = %s
                    RETURNING version
                    """,
                    (
                        str(evidence.evidence_commit_id),
                        evidence.commit_hash,
                        evidence.material_identity_hash,
                        claim.fencing_token,
                        now,
                        str(claim.run_id),
                        evidence.evidence_scope,
                        int(current[2]),
                    ),
                ).fetchone()
                if updated is None:
                    raise ContinuousResearchConflict("Current Evidence CAS conflict")
                current_advanced = True
            tick = connection.execute(
                """
                UPDATE continuous_runtime_tick
                SET evidence_commit_id = %s, version = version + 1,
                    updated_at = %s
                WHERE run_id = %s AND tick_id = %s
                  AND status = 'IN_PROGRESS'
                  AND claim_id = %s AND fencing_token = %s AND version = %s
                  AND lease_expires_at > %s
                RETURNING version
                """,
                (
                    str(evidence.evidence_commit_id),
                    now,
                    str(claim.run_id),
                    str(claim.tick_id),
                    claim.claim_id,
                    claim.fencing_token,
                    claim.tick_version,
                    now,
                ),
            ).fetchone()
            if tick is None:
                raise ContinuousResearchClaimRejected(
                    "Evidence pointer rejected by tick fencing"
                )
            self._insert_event(
                connection,
                run_id=claim.run_id,
                tick_id=claim.tick_id,
                event_type="EVIDENCE_COMMITTED",
                event_time=now,
                fencing_token=claim.fencing_token,
                payload={
                    "current_advanced": current_advanced,
                    "evidence_commit_id": str(evidence.evidence_commit_id),
                    "material_identity_hash": evidence.material_identity_hash,
                },
            )
            if current_advanced:
                self._insert_event(
                    connection,
                    run_id=claim.run_id,
                    tick_id=claim.tick_id,
                    event_type="CURRENT_EVIDENCE_CHANGED",
                    event_time=now,
                    fencing_token=claim.fencing_token,
                    payload={"evidence_scope": evidence.evidence_scope},
                )
            return current_advanced, int(tick[0])

        current_advanced, tick_version = self._factory.run_transaction(operation)
        current = self.get_current_evidence(claim.run_id, evidence.evidence_scope)
        if current is None:
            raise RuntimeError("Current Evidence was not durable")
        return EvidenceCommitResult(
            evidence=self.get_evidence_commit(evidence.evidence_commit_id),
            current=current,
            claim=replace(claim, tick_version=tick_version),
            current_advanced=current_advanced,
        )

    def get_provider_attempt(self, attempt_id: int) -> ProviderAttemptSnapshot:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                _ATTEMPT_SELECT + " WHERE attempt_id = %s",
                (attempt_id,),
            ).fetchone()
        if row is None:
            raise ContinuousResearchNotFound(f"Provider Attempt {attempt_id}")
        return _attempt_from_row(row)

    def get_evidence_commit(self, evidence_commit_id: ArtifactId) -> EvidenceCommit:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT evidence_json
                FROM continuous_evidence_commit
                WHERE evidence_commit_id = %s
                """,
                (str(evidence_commit_id),),
            ).fetchone()
        if row is None:
            raise ContinuousResearchNotFound(str(evidence_commit_id))
        return EvidenceCommit.from_canonical_dict(
            _json_object(row[0], "evidence_json")
        )

    def get_prior_evidence_commit(
        self,
        *,
        run_id: ArtifactId,
        tick_id: ArtifactId,
        evidence_scope: str,
    ) -> EvidenceCommit | None:
        require_text("evidence_scope", evidence_scope)
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT e.evidence_json
                FROM continuous_evidence_commit e
                JOIN continuous_runtime_tick prior_tick
                  ON prior_tick.run_id = e.run_id
                 AND prior_tick.tick_id = e.tick_id
                JOIN continuous_runtime_tick current_tick
                  ON current_tick.run_id = prior_tick.run_id
                WHERE e.run_id = %s AND current_tick.tick_id = %s
                  AND e.evidence_scope = %s
                  AND prior_tick.tick_sequence < current_tick.tick_sequence
                ORDER BY prior_tick.tick_sequence DESC, e.created_at DESC
                LIMIT 1
                """,
                (str(run_id), str(tick_id), evidence_scope),
            ).fetchone()
        if row is None:
            return None
        return EvidenceCommit.from_canonical_dict(
            _json_object(row[0], "evidence_json")
        )

    def get_current_evidence(
        self, run_id: ArtifactId, evidence_scope: str
    ) -> CurrentEvidenceSnapshot | None:
        require_text("evidence_scope", evidence_scope)
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT evidence_commit_id, evidence_commit_hash,
                       material_identity_hash, version,
                       last_accepted_fencing_token, updated_at
                FROM continuous_current_evidence
                WHERE run_id = %s AND evidence_scope = %s
                """,
                (str(run_id), evidence_scope),
            ).fetchone()
        if row is None:
            return None
        return CurrentEvidenceSnapshot(
            run_id=run_id,
            evidence_scope=evidence_scope,
            evidence_commit_id=ArtifactId(str(row[0])),
            evidence_commit_hash=str(row[1]),
            material_identity_hash=str(row[2]),
            version=int(row[3]),
            last_accepted_fencing_token=int(row[4]),
            updated_at=_datetime(row[5]),
        )

    def record_change_decision(
        self,
        *,
        claim: ClaimedRuntimeTick,
        decision: ChangeDecision,
    ) -> RecordedChangeDecision:
        self._require_claim(claim)
        if not isinstance(decision, ChangeDecision):
            raise TypeError("decision must be a ChangeDecision")
        decision.verify_identity()
        if decision.run_id != claim.run_id or decision.tick_id != claim.tick_id:
            raise ContinuousResearchConflict(
                "Change Decision does not belong to the claimed tick"
            )
        now = self._now()

        def operation(connection: psycopg.Connection[Any]) -> int:
            active = connection.execute(
                """
                SELECT version, change_decision_id
                FROM continuous_runtime_tick
                WHERE run_id = %s AND tick_id = %s
                  AND status = 'IN_PROGRESS'
                  AND claim_id = %s AND fencing_token = %s
                  AND lease_expires_at > %s
                FOR UPDATE
                """,
                (
                    str(claim.run_id),
                    str(claim.tick_id),
                    claim.claim_id,
                    claim.fencing_token,
                    now,
                ),
            ).fetchone()
            if active is None:
                raise ContinuousResearchClaimRejected(
                    "Change Decision rejected by fencing"
                )
            active_version = int(active[0])
            if active[1] is not None:
                if (
                    str(active[1]) == str(decision.decision_id)
                    and active_version in {claim.tick_version, claim.tick_version + 1}
                ):
                    return active_version
                raise ContinuousResearchConflict(
                    "tick already has a different Change Decision"
                )
            if active_version != claim.tick_version:
                raise ContinuousResearchClaimRejected(
                    "Change Decision rejected by tick version fencing"
                )
            evidence_row = connection.execute(
                """
                SELECT commit_hash, attempt_id, material_identity_hash,
                       evidence_scope
                FROM continuous_evidence_commit
                WHERE evidence_commit_id = %s AND run_id = %s AND tick_id = %s
                FOR SHARE
                """,
                (
                    str(decision.evidence_commit_id),
                    str(decision.run_id),
                    str(decision.tick_id),
                ),
            ).fetchone()
            if (
                evidence_row is None
                or str(evidence_row[0]) != decision.evidence_commit_hash
                or int(evidence_row[1]) != decision.provider_attempt_id
                or str(evidence_row[2])
                != decision.current_material_identity_hash
            ):
                raise ContinuousResearchConflict(
                    "Change Decision current Evidence lineage is not durable"
                )
            if decision.previous_evidence_commit_id is not None:
                previous_row = connection.execute(
                    """
                    SELECT commit_hash, material_identity_hash
                    FROM continuous_evidence_commit
                    WHERE evidence_commit_id = %s AND run_id = %s
                    FOR SHARE
                    """,
                    (
                        str(decision.previous_evidence_commit_id),
                        str(decision.run_id),
                    ),
                ).fetchone()
                if (
                    previous_row is None
                    or str(previous_row[0])
                    != decision.previous_evidence_commit_hash
                    or str(previous_row[1])
                    != decision.previous_material_identity_hash
                ):
                    raise ContinuousResearchConflict(
                        "Change Decision previous Evidence lineage is not durable"
                    )
            current_row = connection.execute(
                """
                SELECT evidence_commit_id, material_identity_hash
                FROM continuous_current_evidence
                WHERE run_id = %s AND evidence_scope = %s
                FOR SHARE
                """,
                (str(decision.run_id), str(evidence_row[3])),
            ).fetchone()
            if current_row is None:
                raise ContinuousResearchConflict(
                    "Change Decision requires current validated Evidence"
                )
            if decision.decision_type.value == "NO_MATERIAL_CHANGE":
                if (
                    str(current_row[0])
                    != str(decision.previous_evidence_commit_id)
                    or str(current_row[1])
                    != decision.current_material_identity_hash
                ):
                    raise ContinuousResearchConflict(
                        "NO_MATERIAL_CHANGE must preserve the previous Evidence pointer"
                    )
            elif str(current_row[1]) != decision.current_material_identity_hash:
                raise ContinuousResearchConflict(
                    "Change Decision material identity differs from current Evidence"
                )
            connection.execute(
                """
                INSERT INTO continuous_change_decision(
                    decision_id, decision_hash, run_id, tick_id,
                    provider_attempt_id, evidence_commit_id,
                    previous_evidence_commit_id, decision_type,
                    previous_material_identity_hash,
                    current_material_identity_hash,
                    reason_codes_json, decision_json, created_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT (run_id, tick_id) DO NOTHING
                """,
                (
                    str(decision.decision_id),
                    decision.decision_hash,
                    str(decision.run_id),
                    str(decision.tick_id),
                    decision.provider_attempt_id,
                    str(decision.evidence_commit_id),
                    (
                        None
                        if decision.previous_evidence_commit_id is None
                        else str(decision.previous_evidence_commit_id)
                    ),
                    decision.decision_type.value,
                    decision.previous_material_identity_hash,
                    decision.current_material_identity_hash,
                    _json_array(decision.reason_codes),
                    canonical_json(decision.to_canonical_dict()),
                    decision.created_at,
                ),
            )
            durable = connection.execute(
                """
                SELECT decision_id, decision_hash
                FROM continuous_change_decision
                WHERE run_id = %s AND tick_id = %s
                """,
                (str(decision.run_id), str(decision.tick_id)),
            ).fetchone()
            if (
                durable is None
                or str(durable[0]) != str(decision.decision_id)
                or str(durable[1]) != decision.decision_hash
            ):
                raise ContinuousResearchConflict(
                    "Change Decision tick idempotency conflict"
                )
            tick = connection.execute(
                """
                UPDATE continuous_runtime_tick
                SET change_decision_id = %s, version = version + 1,
                    updated_at = %s
                WHERE run_id = %s AND tick_id = %s
                  AND status = 'IN_PROGRESS'
                  AND claim_id = %s AND fencing_token = %s AND version = %s
                  AND lease_expires_at > %s
                RETURNING version
                """,
                (
                    str(decision.decision_id),
                    now,
                    str(claim.run_id),
                    str(claim.tick_id),
                    claim.claim_id,
                    claim.fencing_token,
                    claim.tick_version,
                    now,
                ),
            ).fetchone()
            if tick is None:
                raise ContinuousResearchClaimRejected(
                    "Change Decision pointer rejected by fencing"
                )
            self._insert_event(
                connection,
                run_id=claim.run_id,
                tick_id=claim.tick_id,
                event_type="CHANGE_DECIDED",
                event_time=now,
                fencing_token=claim.fencing_token,
                payload={
                    "decision_id": str(decision.decision_id),
                    "decision_type": decision.decision_type.value,
                },
            )
            return int(tick[0])

        tick_version = self._factory.run_transaction(operation)
        return RecordedChangeDecision(
            decision=self.get_change_decision(decision.decision_id),
            claim=replace(claim, tick_version=tick_version),
        )

    def get_change_decision(self, decision_id: ArtifactId) -> ChangeDecision:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT decision_json
                FROM continuous_change_decision
                WHERE decision_id = %s
                """,
                (str(decision_id),),
            ).fetchone()
        if row is None:
            raise ContinuousResearchNotFound(str(decision_id))
        return ChangeDecision.from_canonical_dict(
            _json_object(row[0], "decision_json")
        )

    def record_child_reference(
        self,
        *,
        claim: ClaimedRuntimeTick,
        reference: ContinuousChildReference,
    ) -> ContinuousChildReference:
        self._require_claim(claim)
        if not isinstance(reference, ContinuousChildReference):
            raise TypeError("reference must be a ContinuousChildReference")
        reference.verify_identity()
        if reference.run_id != claim.run_id or reference.tick_id != claim.tick_id:
            raise ContinuousResearchConflict(
                "Child Reference does not belong to the claimed tick"
            )
        if reference.tick_sequence != claim.tick_sequence:
            raise ContinuousResearchConflict(
                "Child Reference tick sequence does not match the claim"
            )
        now = self._now()

        def operation(connection: psycopg.Connection[Any]) -> None:
            active = connection.execute(
                """
                SELECT 1
                FROM continuous_runtime_tick
                WHERE run_id = %s AND tick_id = %s
                  AND status = 'IN_PROGRESS'
                  AND claim_id = %s AND fencing_token = %s AND version = %s
                  AND lease_expires_at > %s
                FOR UPDATE
                """,
                (
                    str(claim.run_id),
                    str(claim.tick_id),
                    claim.claim_id,
                    claim.fencing_token,
                    claim.tick_version,
                    now,
                ),
            ).fetchone()
            if active is None:
                raise ContinuousResearchClaimRejected(
                    "Child Reference rejected by fencing"
                )
            lineage = connection.execute(
                """
                SELECT d.decision_hash, d.provider_attempt_id,
                       e.commit_hash, e.source_manifest_id,
                       e.source_manifest_hash
                FROM continuous_change_decision d
                JOIN continuous_evidence_commit e
                  ON e.evidence_commit_id = d.evidence_commit_id
                 AND e.run_id = d.run_id AND e.tick_id = d.tick_id
                WHERE d.decision_id = %s AND d.run_id = %s AND d.tick_id = %s
                FOR SHARE OF d, e
                """,
                (
                    str(reference.decision_id),
                    str(reference.run_id),
                    str(reference.tick_id),
                ),
            ).fetchone()
            if (
                lineage is None
                or str(lineage[0]) != reference.decision_hash
                or int(lineage[1]) != reference.provider_attempt_id
                or str(lineage[2]) != reference.evidence_commit_hash
                or str(lineage[3]) != str(reference.source_manifest_id)
                or str(lineage[4]) != reference.source_manifest_hash
            ):
                raise ContinuousResearchConflict(
                    "Child Reference parent lineage is not durable"
                )
            connection.execute(
                """
                INSERT INTO continuous_child_run(
                    run_id, tick_id, decision_id, child_kind,
                    reference_disposition, child_run_id, child_receipt_id,
                    child_receipt_hash, child_artifact_id, child_artifact_hash,
                    source_manifest_id, source_manifest_hash,
                    aggregate_input_hash, configuration_set_hash,
                    child_reference_json, created_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT (run_id, tick_id, child_kind) DO NOTHING
                """,
                (
                    str(reference.run_id),
                    str(reference.tick_id),
                    str(reference.decision_id),
                    reference.child_kind.value,
                    reference.reference_disposition.value,
                    str(reference.child_run_id),
                    str(reference.child_receipt_id),
                    reference.child_receipt_hash,
                    (
                        None
                        if reference.child_artifact_id is None
                        else str(reference.child_artifact_id)
                    ),
                    reference.child_artifact_hash,
                    str(reference.source_manifest_id),
                    reference.source_manifest_hash,
                    reference.aggregate_input_hash,
                    reference.configuration_set_hash,
                    canonical_json(reference.to_canonical_dict()),
                    reference.created_at,
                ),
            )
            durable = connection.execute(
                """
                SELECT child_reference_json
                FROM continuous_child_run
                WHERE run_id = %s AND tick_id = %s AND child_kind = %s
                """,
                (
                    str(reference.run_id),
                    str(reference.tick_id),
                    reference.child_kind.value,
                ),
            ).fetchone()
            if durable is None or _json_object(
                durable[0], "child_reference_json"
            ) != reference.to_canonical_dict():
                raise ContinuousResearchConflict(
                    "Child Reference tick/kind idempotency conflict"
                )
            self._insert_event(
                connection,
                run_id=claim.run_id,
                tick_id=claim.tick_id,
                event_type="CHILD_RECORDED",
                event_time=now,
                fencing_token=claim.fencing_token,
                payload={
                    "child_kind": reference.child_kind.value,
                    "disposition": reference.reference_disposition.value,
                },
            )

        self._factory.run_transaction(operation)
        return reference

    def get_child_references(
        self, run_id: ArtifactId, tick_id: ArtifactId
    ) -> tuple[ContinuousChildReference, ...]:
        with self._factory.connection(read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT child_reference_json
                FROM continuous_child_run
                WHERE run_id = %s AND tick_id = %s
                ORDER BY child_kind
                """,
                (str(run_id), str(tick_id)),
            ).fetchall()
        return tuple(
            ContinuousChildReference.from_canonical_dict(
                _json_object(row[0], "child_reference_json")
            )
            for row in rows
        )

    def get_latest_child_references(
        self, *, run_id: ArtifactId, before_tick_sequence: int
    ) -> tuple[ContinuousChildReference, ...]:
        if (
            isinstance(before_tick_sequence, bool)
            or not isinstance(before_tick_sequence, int)
            or before_tick_sequence < 1
        ):
            raise ValueError("before_tick_sequence must be positive")
        with self._factory.connection(read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT ON (child.child_kind)
                       child.child_reference_json
                FROM continuous_child_run child
                JOIN continuous_runtime_tick tick
                  ON tick.run_id = child.run_id AND tick.tick_id = child.tick_id
                WHERE child.run_id = %s AND tick.tick_sequence < %s
                ORDER BY child.child_kind, tick.tick_sequence DESC
                """,
                (str(run_id), before_tick_sequence),
            ).fetchall()
        references = tuple(
            ContinuousChildReference.from_canonical_dict(
                _json_object(row[0], "child_reference_json")
            )
            for row in rows
        )
        return tuple(sorted(references, key=lambda item: item.child_kind.value))

    def resume(self, run_id: ArtifactId) -> ContinuousRunSnapshot:
        now = self._now()

        def operation(connection: psycopg.Connection[Any]) -> None:
            rows = connection.execute(
                """
                SELECT tick_id, version, fencing_token
                FROM continuous_runtime_tick
                WHERE run_id = %s AND status = 'IN_PROGRESS'
                  AND lease_expires_at <= %s
                ORDER BY tick_sequence
                FOR UPDATE
                """,
                (str(run_id), now),
            ).fetchall()
            for row in rows:
                tick_id = ArtifactId(str(row[0]))
                connection.execute(
                    """
                    UPDATE continuous_provider_attempt
                    SET completed_at = %s, status = 'LEASE_EXPIRED',
                        error_code = 'LEASE_EXPIRED',
                        error_message = 'Provider Attempt lease expired',
                        reason_codes_json = '["LEASE_EXPIRED"]',
                        attempt_json = %s
                    WHERE run_id = %s AND tick_id = %s
                      AND fencing_token = %s AND status = 'STARTED'
                    """,
                    (
                        now,
                        canonical_json(
                            {
                                "schema_version": "continuous-provider-attempt-v1",
                                "status": ProviderAttemptStatus.LEASE_EXPIRED.value,
                            }
                        ),
                        str(run_id),
                        str(tick_id),
                        int(row[2]),
                    ),
                )
                connection.execute(
                    """
                    UPDATE continuous_runtime_tick
                    SET status = 'PENDING', version = version + 1,
                        claim_id = NULL, lease_acquired_at = NULL,
                        lease_expires_at = NULL, heartbeat_at = NULL,
                        last_error = 'LEASE_EXPIRED', retry_at = NULL,
                        updated_at = %s
                    WHERE run_id = %s AND tick_id = %s AND version = %s
                    """,
                    (now, str(run_id), str(tick_id), int(row[1])),
                )
                self._insert_event(
                    connection,
                    run_id=run_id,
                    tick_id=tick_id,
                    event_type="LEASE_EXPIRED",
                    event_time=now,
                    fencing_token=int(row[2]),
                    payload={"expired_fencing_token": int(row[2])},
                )
            if rows:
                self._update_run_state(
                    connection, run_id, ContinuousRunState.RETRYING, now
                )
                self._insert_event(
                    connection,
                    run_id=run_id,
                    tick_id=None,
                    event_type="RUN_RECOVERED",
                    event_time=now,
                    fencing_token=None,
                    payload={"recovered_tick_count": len(rows)},
                )

        self._factory.run_transaction(operation)
        return self.get_run(run_id)

    def get_run(self, run_id: ArtifactId) -> ContinuousRunSnapshot:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT command_json, status, current_tick_sequence, version,
                       created_at, updated_at, closed_at, archived_at
                FROM continuous_research_run
                WHERE run_id = %s
                """,
                (str(run_id),),
            ).fetchone()
            if row is None:
                raise ContinuousResearchNotFound(str(run_id))
            ticks = tuple(
                self._tick_from_row(item)
                for item in connection.execute(
                    _TICK_SELECT
                    + " WHERE run_id = %s ORDER BY tick_sequence",
                    (str(run_id),),
                ).fetchall()
            )
            events = tuple(
                ContinuousRuntimeEvent(
                    event_id=int(item[0]),
                    event_type=str(item[1]),
                    event_time=_datetime(item[2]),
                    tick_id=(None if item[3] is None else ArtifactId(str(item[3]))),
                    fencing_token=(None if item[4] is None else int(item[4])),
                    payload_json=str(item[5]),
                )
                for item in connection.execute(
                    """
                    SELECT event_id, event_type, event_time, tick_id,
                           fencing_token, payload_json
                    FROM continuous_runtime_event
                    WHERE run_id = %s
                    ORDER BY event_id
                    """,
                    (str(run_id),),
                ).fetchall()
            )
        return ContinuousRunSnapshot(
            command=ContinuousResearchCommand.from_canonical_dict(
                _json_object(row[0], "command_json")
            ),
            status=ContinuousRunState(str(row[1])),
            current_tick_sequence=int(row[2]),
            version=int(row[3]),
            created_at=_datetime(row[4]),
            updated_at=_datetime(row[5]),
            closed_at=_optional_datetime(row[6]),
            archived_at=_optional_datetime(row[7]),
            ticks=ticks,
            events=events,
        )

    def get_tick(
        self, run_id: ArtifactId, tick_id: ArtifactId
    ) -> ContinuousTickSnapshot:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                _TICK_SELECT + " WHERE run_id = %s AND tick_id = %s",
                (str(run_id), str(tick_id)),
            ).fetchone()
        if row is None:
            raise ContinuousResearchNotFound(f"{run_id}/{tick_id}")
        return self._tick_from_row(row)

    def _claim_locked(
        self,
        connection: psycopg.Connection[Any],
        *,
        run_id: ArtifactId,
        tick_id: ArtifactId,
        tick_sequence: int,
        version: int,
        fencing_token: int,
        now: datetime,
    ) -> ClaimedRuntimeTick:
        claim_id = self._claim_id_factory()
        require_text("claim_id", claim_id)
        lease_expires_at = now + self._lease_duration
        row = connection.execute(
            """
            UPDATE continuous_runtime_tick
            SET status = 'IN_PROGRESS', version = version + 1,
                claim_id = %s, fencing_token = fencing_token + 1,
                lease_acquired_at = %s, lease_expires_at = %s,
                heartbeat_at = %s, retry_at = NULL, updated_at = %s
            WHERE run_id = %s AND tick_id = %s
              AND status = 'PENDING' AND version = %s
            RETURNING version, fencing_token
            """,
            (
                claim_id,
                now,
                lease_expires_at,
                now,
                now,
                str(run_id),
                str(tick_id),
                version,
            ),
        ).fetchone()
        if row is None:
            raise ContinuousResearchClaimRejected(
                "Continuous tick claim rejected by version fencing"
            )
        claim = ClaimedRuntimeTick(
            run_id=run_id,
            tick_id=tick_id,
            tick_sequence=tick_sequence,
            claim_id=claim_id,
            fencing_token=int(row[1]),
            tick_version=int(row[0]),
            lease_acquired_at=now,
            lease_expires_at=lease_expires_at,
            heartbeat_at=now,
        )
        self._insert_event(
            connection,
            run_id=run_id,
            tick_id=tick_id,
            event_type="TICK_CLAIMED",
            event_time=now,
            fencing_token=claim.fencing_token,
            payload={"claim_id": claim_id, "tick_version": claim.tick_version},
        )
        return claim

    def _update_run_state(
        self,
        connection: psycopg.Connection[Any],
        run_id: ArtifactId,
        run_state: ContinuousRunState,
        now: datetime,
    ) -> None:
        row = connection.execute(
            """
            UPDATE continuous_research_run
            SET status = %s, version = version + 1, updated_at = %s,
                closed_at = CASE
                    WHEN %s IN ('MARKET_CLOSED', 'ARCHIVED')
                    THEN COALESCE(closed_at, %s)
                    ELSE closed_at
                END,
                archived_at = CASE
                    WHEN %s = 'ARCHIVED' THEN %s
                    ELSE archived_at
                END
            WHERE run_id = %s
            RETURNING version
            """,
            (
                run_state.value,
                now,
                run_state.value,
                now,
                run_state.value,
                now,
                str(run_id),
            ),
        ).fetchone()
        if row is None:
            raise ContinuousResearchNotFound(str(run_id))
        self._insert_event(
            connection,
            run_id=run_id,
            tick_id=None,
            event_type="RUN_STATUS_CHANGED",
            event_time=now,
            fencing_token=None,
            payload={"run_state": run_state.value, "version": int(row[0])},
        )

    def _insert_event(
        self,
        connection: psycopg.Connection[Any],
        *,
        run_id: ArtifactId,
        tick_id: ArtifactId | None,
        event_type: str,
        event_time: datetime,
        fencing_token: int | None,
        payload: Mapping[str, Any],
    ) -> None:
        connection.execute(
            """
            INSERT INTO continuous_runtime_event(
                run_id, tick_id, event_type, event_time,
                fencing_token, payload_json
            ) VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                str(run_id),
                None if tick_id is None else str(tick_id),
                event_type,
                event_time,
                fencing_token,
                canonical_json(payload),
            ),
        )

    def _tick_from_row(self, row: tuple[Any, ...]) -> ContinuousTickSnapshot:
        receipt = (
            None
            if row[14] is None
            else RuntimeTickReceipt.from_canonical_dict(
                _json_object(row[14], "receipt_json")
            )
        )
        return ContinuousTickSnapshot(
            command=RuntimeTickCommand.from_canonical_dict(
                _json_object(row[0], "tick_json")
            ),
            tick_sequence=int(row[1]),
            session_phase=ContinuousSessionPhase(str(row[2])),
            status=ContinuousTickStatus(str(row[3])),
            version=int(row[4]),
            claim_id=None if row[5] is None else str(row[5]),
            fencing_token=int(row[6]),
            lease_acquired_at=_optional_datetime(row[7]),
            lease_expires_at=_optional_datetime(row[8]),
            heartbeat_at=_optional_datetime(row[9]),
            provider_attempt_id=None if row[10] is None else int(row[10]),
            evidence_commit_id=(
                None if row[11] is None else ArtifactId(str(row[11]))
            ),
            change_decision_id=(
                None if row[12] is None else ArtifactId(str(row[12]))
            ),
            receipt=receipt,
            last_error=None if row[15] is None else str(row[15]),
            retry_at=_optional_datetime(row[16]),
            created_at=_datetime(row[17]),
            updated_at=_datetime(row[18]),
            completed_at=_optional_datetime(row[19]),
        )

    def _require_claim(self, claim: ClaimedRuntimeTick) -> None:
        if not isinstance(claim, ClaimedRuntimeTick):
            raise TypeError("claim must be a ClaimedRuntimeTick")

    def _now(self) -> datetime:
        value = self._clock()
        require_utc_second("clock", value)
        return value


_TICK_SELECT = """
SELECT tick_json, tick_sequence, session_phase, status, version,
       claim_id, fencing_token, lease_acquired_at, lease_expires_at,
       heartbeat_at, provider_attempt_id, evidence_commit_id,
       change_decision_id, receipt_id, receipt_json, last_error,
       retry_at, created_at, updated_at, completed_at
FROM continuous_runtime_tick
"""

_ATTEMPT_SELECT = """
SELECT attempt_id, run_id, tick_id, attempt_number, claim_id, fencing_token,
       tick_version, provider_id, product, request_hash, started_at,
       completed_at, lease_expires_at, heartbeat_at, status,
       raw_response_hash, source_manifest_id, source_manifest_hash,
       error_code, error_message, reason_codes_json, retry_at,
       provider_revision
FROM continuous_provider_attempt
"""


def _state_for_phase(phase: ContinuousSessionPhase) -> ContinuousRunState:
    return {
        ContinuousSessionPhase.PRE_MARKET: ContinuousRunState.PREPARING,
        ContinuousSessionPhase.MORNING_SESSION: ContinuousRunState.MONITORING,
        ContinuousSessionPhase.MIDDAY_RECESS: ContinuousRunState.WAITING_FOR_NEW_DATA,
        ContinuousSessionPhase.AFTERNOON_SESSION: ContinuousRunState.MONITORING,
        ContinuousSessionPhase.DECISION_WINDOW: ContinuousRunState.DECISION_WINDOW_OPEN,
        ContinuousSessionPhase.MARKET_CLOSED: ContinuousRunState.MARKET_CLOSED,
    }[phase]


def _json_object(value: object, label: str) -> Mapping[str, Any]:
    try:
        payload = json.loads(str(value))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return payload


def _json_array(values: tuple[str, ...]) -> str:
    return json.dumps(
        list(values),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _attempt_from_row(row: tuple[Any, ...]) -> ProviderAttemptSnapshot:
    reasons_payload = json.loads(str(row[20]))
    if not isinstance(reasons_payload, list) or any(
        not isinstance(item, str) for item in reasons_payload
    ):
        raise ValueError("Provider Attempt reasons row is invalid")
    return ProviderAttemptSnapshot(
        attempt_id=int(row[0]),
        run_id=ArtifactId(str(row[1])),
        tick_id=ArtifactId(str(row[2])),
        attempt_number=int(row[3]),
        claim_id=str(row[4]),
        fencing_token=int(row[5]),
        tick_version=int(row[6]),
        provider_id=str(row[7]),
        product=str(row[8]),
        request_hash=str(row[9]),
        started_at=_datetime(row[10]),
        completed_at=_optional_datetime(row[11]),
        lease_expires_at=_datetime(row[12]),
        heartbeat_at=_datetime(row[13]),
        status=ProviderAttemptStatus(str(row[14])),
        raw_response_hash=(None if row[15] is None else str(row[15])),
        source_manifest_id=(
            None if row[16] is None else ArtifactId(str(row[16]))
        ),
        source_manifest_hash=(None if row[17] is None else str(row[17])),
        error_code=None if row[18] is None else str(row[18]),
        error_message=None if row[19] is None else str(row[19]),
        reason_codes=tuple(reasons_payload),
        retry_at=_optional_datetime(row[21]),
        provider_revision=None if row[22] is None else str(row[22]),
    )


def _datetime(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError("PostgreSQL timestamp row is invalid")
    normalized = value.astimezone(timezone.utc).replace(microsecond=0)
    require_utc_second("PostgreSQL timestamp", normalized)
    return normalized


def _optional_datetime(value: object) -> datetime | None:
    return None if value is None else _datetime(value)


__all__ = [
    "DEFAULT_CONTINUOUS_TICK_LEASE",
    "ContinuousResearchClaimRejected",
    "ContinuousResearchConflict",
    "ContinuousResearchNotFound",
    "PostgresContinuousResearchJournal",
]
