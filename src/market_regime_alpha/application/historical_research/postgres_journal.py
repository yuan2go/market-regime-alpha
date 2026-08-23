"""Lease/fence/CAS PostgreSQL journal for Historical Research sessions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable
from uuid import uuid4

from psycopg.types.json import Jsonb

from market_regime_alpha.application.historical_research.contracts import (
    E3_HISTORICAL_RUNTIME_CONTRACT,
    HistoricalResearchCommand,
    PRE_E3_HISTORICAL_RUNTIME_CONTRACT,
)
from market_regime_alpha.application.research_session.contracts import (
    ResearchDecisionSessionRequest,
)
from market_regime_alpha.application.research_session.kernel import (
    ResearchSessionStage,
    ResearchSessionStageReceipt,
    SessionStageStatus,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import normalize_canonical_datetime
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.postgres.migrator import PostgresMigrator


DEFAULT_HISTORICAL_STAGE_LEASE = timedelta(minutes=10)
PRE_E3_RUNTIME_CONTRACT = PRE_E3_HISTORICAL_RUNTIME_CONTRACT
E3_LONGITUDINAL_RUNTIME_CONTRACT = E3_HISTORICAL_RUNTIME_CONTRACT
Clock = Callable[[], datetime]


class HistoricalResearchConflict(RuntimeError):
    """A command, claim or durable projection conflicts with owner state."""


class HistoricalRunStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETE = "COMPLETE"
    COMPLETE_WITH_BLOCKS = "COMPLETE_WITH_BLOCKS"
    FAILED = "FAILED"


class HistoricalSessionStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETE = "COMPLETE"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class HistoricalStageClaim:
    run_id: ArtifactId
    session_id: ArtifactId
    session_hash: str
    trading_date: date
    stage: ResearchSessionStage
    claim_id: str
    attempt_number: int
    fencing_token: int
    session_version: int
    lease_acquired_at: datetime
    lease_expires_at: datetime
    completed_prefix: tuple[ResearchSessionStageReceipt, ...]


@dataclass(frozen=True, slots=True)
class HistoricalSessionSnapshot:
    request: ResearchDecisionSessionRequest
    ordinal: int
    status: HistoricalSessionStatus
    next_stage: ResearchSessionStage
    version: int
    fencing_token: int
    receipts: tuple[ResearchSessionStageReceipt, ...]


@dataclass(frozen=True, slots=True)
class HistoricalRunSnapshot:
    command: HistoricalResearchCommand
    runtime_contract_version: str
    status: HistoricalRunStatus
    version: int
    sessions: tuple[HistoricalSessionSnapshot, ...]

    @property
    def completed_sessions(self) -> int:
        return sum(
            item.status
            in {HistoricalSessionStatus.COMPLETE, HistoricalSessionStatus.BLOCKED}
            for item in self.sessions
        )


class PostgresHistoricalResearchJournal:
    def __init__(
        self,
        factory: PostgresConnectionFactory,
        *,
        clock: Clock | None = None,
        lease_duration: timedelta = DEFAULT_HISTORICAL_STAGE_LEASE,
        apply_migrations: bool = False,
    ) -> None:
        if lease_duration <= timedelta(0):
            raise ValueError("Historical stage lease must be positive")
        self._factory = factory
        self._clock = clock or _utc_now
        self._lease_duration = lease_duration
        if apply_migrations:
            PostgresMigrator().apply_all(factory)

    def create_or_get(
        self, command: HistoricalResearchCommand
    ) -> HistoricalRunSnapshot:
        now = self._now()

        def operation(connection: Any) -> None:
            connection.execute(
                """
                INSERT INTO historical_research_run(
                    run_id, command_hash, idempotency_key, start_date, end_date,
                    trading_calendar_id, trading_calendar_hash,
                    runtime_scope_policy_id, runtime_scope_policy_hash,
                    target_protocol_id, target_protocol_hash,
                    experiment_definition_id, experiment_definition_hash,
                    data_authority_mode, evidence_qualification,
                    runtime_contract_version, status, version,
                    command_json, created_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    'PENDING', 1, %s, %s, %s
                ) ON CONFLICT DO NOTHING
                """,
                (
                    str(command.run_id),
                    command.command_hash,
                    command.idempotency_key,
                    command.start_date,
                    command.end_date,
                    str(command.trading_calendar_id),
                    command.trading_calendar_hash,
                    str(command.runtime_scope_policy_id),
                    command.runtime_scope_policy_hash,
                    str(command.target_protocol_reference.artifact_id),
                    command.target_protocol_reference.content_hash,
                    str(command.experiment_definition_reference.artifact_id),
                    command.experiment_definition_reference.content_hash,
                    command.data_authority_mode.value,
                    command.evidence_qualification.value,
                    command.runtime_contract_version,
                    Jsonb(command.to_canonical_dict()),
                    command.created_at,
                    now,
                ),
            )
            durable = connection.execute(
                """
                SELECT run_id, command_hash
                FROM historical_research_run
                WHERE idempotency_key = %s
                """,
                (command.idempotency_key,),
            ).fetchone()
            if durable is None or (
                str(durable[0]), str(durable[1])
            ) != (str(command.run_id), command.command_hash):
                raise HistoricalResearchConflict(
                    "Historical Research idempotency identity conflict"
                )
            for ordinal, trading_date in enumerate(command.trading_sessions, start=1):
                request = command.session_request(trading_date)
                connection.execute(
                    """
                    INSERT INTO historical_research_session(
                        run_id, session_id, session_hash, session_ordinal,
                        trading_date, status, next_stage_ordinal, version,
                        fencing_token, session_json, created_at, updated_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, 'PENDING', 1, 1, 0, %s, %s, %s
                    ) ON CONFLICT (run_id, session_id) DO NOTHING
                    """,
                    (
                        str(command.run_id),
                        str(request.session_id),
                        request.session_hash,
                        ordinal,
                        trading_date,
                        Jsonb(request.to_canonical_dict()),
                        command.created_at,
                        now,
                    ),
                )
            count = connection.execute(
                "SELECT count(*) FROM historical_research_session WHERE run_id = %s",
                (str(command.run_id),),
            ).fetchone()
            if count is None or int(count[0]) != command.session_count:
                raise HistoricalResearchConflict(
                    "Historical Research session set is incomplete"
                )

        self._factory.run_transaction(operation)
        return self.get_run(command.run_id)

    def claim_next(self, run_id: ArtifactId) -> HistoricalStageClaim | None:
        now = self._now()
        lease_expires_at = now + self._lease_duration
        result: HistoricalStageClaim | None = None

        def operation(connection: Any) -> None:
            nonlocal result
            run = connection.execute(
                "SELECT status FROM historical_research_run WHERE run_id = %s FOR UPDATE",
                (str(run_id),),
            ).fetchone()
            if run is None:
                raise KeyError(str(run_id))
            if HistoricalRunStatus(str(run[0])) in {
                HistoricalRunStatus.COMPLETE,
                HistoricalRunStatus.COMPLETE_WITH_BLOCKS,
                HistoricalRunStatus.FAILED,
            }:
                return
            row = connection.execute(
                """
                SELECT session_id, session_hash, trading_date, status,
                       next_stage_ordinal, version, fencing_token,
                       active_claim_id, lease_expires_at
                FROM historical_research_session
                WHERE run_id = %s AND status IN ('PENDING', 'RUNNING')
                ORDER BY session_ordinal
                LIMIT 1
                FOR UPDATE
                """,
                (str(run_id),),
            ).fetchone()
            if row is None:
                self._finish_run(connection, run_id, now)
                return
            session_id = ArtifactId(str(row[0]))
            status = HistoricalSessionStatus(str(row[3]))
            if status is HistoricalSessionStatus.RUNNING:
                expires = row[8]
                if expires is not None and expires > now:
                    return
                connection.execute(
                    """
                    UPDATE historical_research_attempt
                    SET status = 'EXPIRED', completed_at = %s,
                        error_code = 'LEASE_EXPIRED'
                    WHERE claim_id = %s AND status = 'ACTIVE'
                    """,
                    (now, str(row[7])),
                )
            stage = tuple(ResearchSessionStage)[int(row[4]) - 1]
            attempt_row = connection.execute(
                "SELECT count(*) FROM historical_research_attempt "
                "WHERE run_id = %s AND session_id = %s",
                (str(run_id), str(session_id)),
            ).fetchone()
            attempt_number = 1 if attempt_row is None else int(attempt_row[0]) + 1
            claim_id = str(uuid4())
            fencing_token = int(row[6]) + 1
            version = int(row[5]) + 1
            connection.execute(
                """
                UPDATE historical_research_session
                SET status = 'RUNNING', version = %s, fencing_token = %s,
                    active_claim_id = %s, lease_acquired_at = %s,
                    lease_expires_at = %s, heartbeat_at = %s, updated_at = %s
                WHERE run_id = %s AND session_id = %s
                """,
                (
                    version,
                    fencing_token,
                    claim_id,
                    now,
                    lease_expires_at,
                    now,
                    now,
                    str(run_id),
                    str(session_id),
                ),
            )
            connection.execute(
                """
                INSERT INTO historical_research_attempt(
                    run_id, session_id, attempt_number, claim_id, stage,
                    stage_ordinal, fencing_token, status, started_at,
                    lease_expires_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'ACTIVE', %s, %s)
                """,
                (
                    str(run_id),
                    str(session_id),
                    attempt_number,
                    claim_id,
                    stage.value,
                    stage.ordinal,
                    fencing_token,
                    now,
                    lease_expires_at,
                ),
            )
            connection.execute(
                """
                UPDATE historical_research_run
                SET status = 'RUNNING', version = version + 1, updated_at = %s
                WHERE run_id = %s
                """,
                (now, str(run_id)),
            )
            prefix = self._load_receipts(connection, run_id, session_id)
            result = HistoricalStageClaim(
                run_id=run_id,
                session_id=session_id,
                session_hash=str(row[1]),
                trading_date=row[2],
                stage=stage,
                claim_id=claim_id,
                attempt_number=attempt_number,
                fencing_token=fencing_token,
                session_version=version,
                lease_acquired_at=now,
                lease_expires_at=lease_expires_at,
                completed_prefix=prefix,
            )

        self._factory.run_transaction(operation)
        return result

    def record_stage(
        self,
        *,
        claim: HistoricalStageClaim,
        receipt: ResearchSessionStageReceipt,
    ) -> HistoricalSessionSnapshot:
        now = self._now()
        if (
            receipt.session_id != claim.session_id
            or receipt.session_hash != claim.session_hash
            or receipt.stage is not claim.stage
            or receipt.predecessor_receipt_ids
            != tuple(item.receipt_id for item in claim.completed_prefix)
        ):
            raise HistoricalResearchConflict(
                "Historical stage receipt does not bind the active claim"
            )

        def operation(connection: Any) -> None:
            row = connection.execute(
                """
                SELECT status, version, fencing_token, active_claim_id,
                       lease_expires_at
                FROM historical_research_session
                WHERE run_id = %s AND session_id = %s
                FOR UPDATE
                """,
                (str(claim.run_id), str(claim.session_id)),
            ).fetchone()
            if row is None:
                raise KeyError(str(claim.session_id))
            if (
                str(row[0]) != HistoricalSessionStatus.RUNNING.value
                or int(row[1]) != claim.session_version
                or int(row[2]) != claim.fencing_token
                or str(row[3]) != claim.claim_id
                or row[4] is None
                or row[4] <= now
            ):
                raise HistoricalResearchConflict("stale Historical stage claim")
            connection.execute(
                """
                INSERT INTO historical_research_stage_receipt(
                    receipt_id, receipt_hash, run_id, session_id, stage,
                    stage_ordinal, status, payload_json, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    str(receipt.receipt_id),
                    receipt.receipt_hash,
                    str(claim.run_id),
                    str(claim.session_id),
                    receipt.stage.value,
                    receipt.stage.ordinal,
                    receipt.status.value,
                    Jsonb(receipt.to_canonical_dict()),
                    receipt.completed_at,
                ),
            )
            terminal_stage = receipt.stage is ResearchSessionStage.PERFORMANCE
            if receipt.status is SessionStageStatus.COMPLETE and not terminal_stage:
                status = HistoricalSessionStatus.PENDING
                next_stage_ordinal = receipt.stage.ordinal + 1
                completed_at = None
            elif receipt.status is SessionStageStatus.COMPLETE:
                status = HistoricalSessionStatus.COMPLETE
                next_stage_ordinal = receipt.stage.ordinal
                completed_at = now
            else:
                status = HistoricalSessionStatus.BLOCKED
                next_stage_ordinal = receipt.stage.ordinal
                completed_at = now
            connection.execute(
                """
                UPDATE historical_research_session
                SET status = %s, next_stage_ordinal = %s,
                    version = version + 1, active_claim_id = NULL,
                    lease_acquired_at = NULL, lease_expires_at = NULL,
                    heartbeat_at = NULL, updated_at = %s, completed_at = %s
                WHERE run_id = %s AND session_id = %s
                """,
                (
                    status.value,
                    next_stage_ordinal,
                    now,
                    completed_at,
                    str(claim.run_id),
                    str(claim.session_id),
                ),
            )
            connection.execute(
                """
                UPDATE historical_research_attempt
                SET status = 'COMPLETED', completed_at = %s
                WHERE claim_id = %s AND status = 'ACTIVE'
                """,
                (now, claim.claim_id),
            )
            connection.execute(
                """
                INSERT INTO historical_research_event(
                    run_id, session_id, event_type, event_json, created_at
                ) VALUES (%s, %s, 'STAGE_RECORDED', %s, %s)
                """,
                (
                    str(claim.run_id),
                    str(claim.session_id),
                    Jsonb(
                        {
                            "receipt_id": str(receipt.receipt_id),
                            "receipt_hash": receipt.receipt_hash,
                            "stage": receipt.stage.value,
                            "status": receipt.status.value,
                            "fencing_token": claim.fencing_token,
                        }
                    ),
                    now,
                ),
            )
            self._finish_run(connection, claim.run_id, now)

        self._factory.run_transaction(operation)
        return self.get_session(claim.run_id, claim.session_id)

    def get_run(self, run_id: ArtifactId) -> HistoricalRunSnapshot:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                "SELECT command_hash, runtime_contract_version, status, "
                "version, command_json "
                "FROM historical_research_run WHERE run_id = %s",
                (str(run_id),),
            ).fetchone()
            session_rows = connection.execute(
                """
                SELECT session_id, session_hash, session_ordinal, status,
                       next_stage_ordinal, version, fencing_token, session_json
                FROM historical_research_session
                WHERE run_id = %s ORDER BY session_ordinal
                """,
                (str(run_id),),
            ).fetchall()
            receipt_rows = connection.execute(
                """
                SELECT session_id, receipt_hash, payload_json
                FROM historical_research_stage_receipt
                WHERE run_id = %s
                ORDER BY session_id, stage_ordinal
                """,
                (str(run_id),),
            ).fetchall()
        if row is None or not isinstance(row[4], dict):
            raise KeyError(str(run_id))
        command = HistoricalResearchCommand.from_canonical_dict(row[4])
        if str(row[0]) != command.command_hash or command.run_id != run_id:
            raise HistoricalResearchConflict("Historical run owner hash diverged")
        if str(row[1]) != command.runtime_contract_version:
            raise HistoricalResearchConflict(
                "Historical run contract projection diverged from command identity"
            )
        receipts_by_session: dict[
            ArtifactId, list[ResearchSessionStageReceipt]
        ] = {}
        for receipt_row in receipt_rows:
            session_id = ArtifactId(str(receipt_row[0]))
            receipts_by_session.setdefault(session_id, []).append(
                self._restore_receipt(receipt_row[1], receipt_row[2])
            )
        sessions = tuple(
            self._restore_session(
                run_id=run_id,
                row=item,
                receipts=tuple(
                    receipts_by_session.get(ArtifactId(str(item[0])), ())
                ),
            )
            for item in session_rows
        )
        if len(sessions) != command.session_count:
            raise HistoricalResearchConflict("Historical session projection diverged")
        return HistoricalRunSnapshot(
            command=command,
            runtime_contract_version=str(row[1]),
            status=HistoricalRunStatus(str(row[2])),
            version=int(row[3]),
            sessions=sessions,
        )

    def get_session(
        self, run_id: ArtifactId, session_id: ArtifactId
    ) -> HistoricalSessionSnapshot:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT session_hash, session_ordinal, status,
                       next_stage_ordinal, version, fencing_token, session_json
                FROM historical_research_session
                WHERE run_id = %s AND session_id = %s
                """,
                (str(run_id), str(session_id)),
            ).fetchone()
            receipts = self._load_receipts(connection, run_id, session_id)
        if row is None:
            raise KeyError(str(session_id))
        return self._restore_session(
            run_id=run_id,
            row=(session_id, *row),
            receipts=receipts,
        )

    @staticmethod
    def _restore_session(
        *,
        run_id: ArtifactId,
        row: Any,
        receipts: tuple[ResearchSessionStageReceipt, ...],
    ) -> HistoricalSessionSnapshot:
        session_id = ArtifactId(str(row[0]))
        if not isinstance(row[7], dict):
            raise HistoricalResearchConflict("Historical session payload is invalid")
        request = ResearchDecisionSessionRequest.from_canonical_dict(row[7])
        if (
            str(row[1]) != request.session_hash
            or request.session_id != session_id
        ):
            raise HistoricalResearchConflict("Historical session owner hash diverged")
        if tuple(item.stage for item in receipts) != tuple(ResearchSessionStage)[
            : len(receipts)
        ]:
            raise HistoricalResearchConflict("Historical stage projection diverged")
        return HistoricalSessionSnapshot(
            request=request,
            ordinal=int(row[2]),
            status=HistoricalSessionStatus(str(row[3])),
            next_stage=tuple(ResearchSessionStage)[int(row[4]) - 1],
            version=int(row[5]),
            fencing_token=int(row[6]),
            receipts=receipts,
        )

    @staticmethod
    def _load_receipts(
        connection: Any, run_id: ArtifactId, session_id: ArtifactId
    ) -> tuple[ResearchSessionStageReceipt, ...]:
        rows = connection.execute(
            """
            SELECT receipt_hash, payload_json
            FROM historical_research_stage_receipt
            WHERE run_id = %s AND session_id = %s
            ORDER BY stage_ordinal
            """,
            (str(run_id), str(session_id)),
        ).fetchall()
        receipts: list[ResearchSessionStageReceipt] = []
        for row in rows:
            receipts.append(
                PostgresHistoricalResearchJournal._restore_receipt(row[0], row[1])
            )
        return tuple(receipts)

    @staticmethod
    def _restore_receipt(
        receipt_hash: object,
        payload: object,
    ) -> ResearchSessionStageReceipt:
        if not isinstance(payload, dict):
            raise HistoricalResearchConflict("Historical receipt payload is invalid")
        receipt = ResearchSessionStageReceipt.from_canonical_dict(payload)
        if str(receipt_hash) != receipt.receipt_hash:
            raise HistoricalResearchConflict("Historical receipt hash diverged")
        return receipt

    @staticmethod
    def _finish_run(connection: Any, run_id: ArtifactId, now: datetime) -> None:
        counts = connection.execute(
            """
            SELECT count(*) FILTER (WHERE status IN ('PENDING', 'RUNNING')),
                   count(*) FILTER (WHERE status = 'BLOCKED'),
                   count(*) FILTER (WHERE status = 'FAILED')
            FROM historical_research_session WHERE run_id = %s
            """,
            (str(run_id),),
        ).fetchone()
        if counts is None:
            raise KeyError(str(run_id))
        active, blocked, failed = (int(item) for item in counts)
        if active:
            status = HistoricalRunStatus.RUNNING
            completed_at = None
        elif failed:
            status = HistoricalRunStatus.FAILED
            completed_at = now
        elif blocked:
            status = HistoricalRunStatus.COMPLETE_WITH_BLOCKS
            completed_at = now
        else:
            status = HistoricalRunStatus.COMPLETE
            completed_at = now
        connection.execute(
            """
            UPDATE historical_research_run
            SET status = %s, version = version + 1,
                updated_at = %s, completed_at = %s
            WHERE run_id = %s
            """,
            (status.value, now, completed_at, str(run_id)),
        )

    def _now(self) -> datetime:
        return normalize_canonical_datetime(self._clock())


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


__all__ = [
    "DEFAULT_HISTORICAL_STAGE_LEASE",
    "E3_LONGITUDINAL_RUNTIME_CONTRACT",
    "HistoricalResearchConflict",
    "HistoricalRunSnapshot",
    "HistoricalRunStatus",
    "HistoricalSessionSnapshot",
    "HistoricalSessionStatus",
    "HistoricalStageClaim",
    "PRE_E3_RUNTIME_CONTRACT",
    "PostgresHistoricalResearchJournal",
]
