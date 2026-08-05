"""Native PostgreSQL Continuous Research run/tick Journal."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from typing import Any, Callable, Mapping
from uuid import uuid4

import psycopg

from market_regime_alpha.application.continuous_research.contracts import (
    ContinuousResearchCommand,
    RuntimeTickCommand,
)
from market_regime_alpha.application.continuous_research.journal import (
    ClaimedRuntimeTick,
    ContinuousRunSnapshot,
    ContinuousRuntimeEvent,
    ContinuousTickSnapshot,
    ContinuousTickStatus,
    RuntimeTickReceipt,
)
from market_regime_alpha.application.continuous_research.policy import (
    ContinuousRunState,
    ContinuousSessionPhase,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_json, require_text
from market_regime_alpha.market_data.contracts import require_utc_second
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.postgres.migrator import PostgresMigrator
from market_regime_alpha.persistence.postgres.schema import (
    verify_postgres_authority_schema,
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
    ) -> None:
        if not isinstance(factory, PostgresConnectionFactory):
            raise TypeError("factory must be a PostgresConnectionFactory")
        if not callable(clock):
            raise TypeError("clock must be callable")
        if lease_duration <= timedelta(0):
            raise ValueError("lease_duration must be positive")
        if claim_id_factory is not None and not callable(claim_id_factory):
            raise TypeError("claim_id_factory must be callable")
        self._factory = factory
        self._clock = clock
        self._lease_duration = lease_duration
        self._claim_id_factory = claim_id_factory or (
            lambda: f"continuous-claim-{uuid4().hex}"
        )
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
