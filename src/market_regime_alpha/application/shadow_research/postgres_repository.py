"""PostgreSQL Shadow Session authority referencing the Canonical Runtime."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from typing import Any, Callable

import psycopg
from psycopg.types.json import Jsonb

from market_regime_alpha.application.continuous_research.contracts import (
    ContinuousResearchCommand,
)
from market_regime_alpha.application.continuous_research.journal import (
    ContinuousChildKind,
    RuntimeArtifactReference,
)
from market_regime_alpha.application.continuous_research.postgres_journal import (
    PostgresContinuousResearchJournal,
)
from market_regime_alpha.application.decision_system.postgres_repository import (
    PostgresDecisionSystemRepository,
)
from market_regime_alpha.application.shadow_research.contracts import (
    ShadowDecision,
    ShadowOutcomeStatus,
    ShadowSessionCommand,
    ShadowSessionSnapshot,
    ShadowSessionStatus,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_datetime
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.postgres.migrator import PostgresMigrator
from market_regime_alpha.platform.runtime_governance import RuntimeAuthorityMode


Clock = Callable[[], datetime]


class ShadowResearchConflict(ValueError):
    """Idempotency, lineage, state-transition or CAS conflict."""


class ShadowResearchIntegrityError(ValueError):
    """Persisted Shadow evidence failed canonical restoration or replay."""


def _now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


class PostgresShadowResearchRepository:
    """Sole writer for Shadow lifecycle facts; it has no trading adapters."""

    def __init__(
        self,
        factory: PostgresConnectionFactory,
        *,
        clock: Clock = _now,
        apply_migrations: bool = True,
    ) -> None:
        if not isinstance(factory, PostgresConnectionFactory):
            raise TypeError("factory must be PostgresConnectionFactory")
        if not callable(clock):
            raise TypeError("clock must be callable")
        self._factory = factory
        self._clock = clock
        self._decisions = PostgresDecisionSystemRepository(factory, clock=clock)
        self._continuous = PostgresContinuousResearchJournal(
            factory, clock=clock, apply_migrations=False
        )
        if apply_migrations:
            PostgresMigrator().apply_all(factory)

    def schedule(self, command: ShadowSessionCommand) -> ShadowSessionSnapshot:
        if not isinstance(command, ShadowSessionCommand):
            raise TypeError("command must be ShadowSessionCommand")
        self._validate_run(command)

        def operation(connection: psycopg.Connection[Any]) -> None:
            try:
                inserted = connection.execute(
                    """
                    INSERT INTO shadow_research_session(
                        session_id, session_hash, idempotency_key, run_id,
                        trading_date, runtime_mode, command_json, status,
                        outcome_status, decision_id, version,
                        reason_codes_json, created_at, updated_at, finished_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, 'SHADOW', %s,
                        'SCHEDULED', 'NOT_EXPECTED', NULL, 1, %s, %s, %s, NULL
                    )
                    ON CONFLICT (idempotency_key) DO NOTHING
                    """,
                    (
                        str(command.session_id),
                        command.session_hash,
                        command.idempotency_key,
                        str(command.run_id),
                        command.trading_date,
                        Jsonb(command.to_canonical_dict()),
                        Jsonb(["SHADOW_ENGINEERING_ONLY"]),
                        command.scheduled_at,
                        command.scheduled_at,
                    ),
                ).rowcount
            except psycopg.IntegrityError as exc:
                raise ShadowResearchConflict(
                    "one Shadow Session is allowed per Canonical run"
                ) from exc
            row = connection.execute(
                """
                SELECT session_id, session_hash, command_json
                FROM shadow_research_session WHERE idempotency_key = %s
                FOR UPDATE
                """,
                (command.idempotency_key,),
            ).fetchone()
            if row is None:
                raise RuntimeError("Shadow Session was not durable")
            if (
                str(row[0]) != str(command.session_id)
                or str(row[1]) != command.session_hash
                or _json_object(row[2]) != command.to_canonical_dict()
            ):
                raise ShadowResearchConflict("Shadow Session idempotency conflict")
            if inserted:
                self._insert_event(
                    connection,
                    session_id=command.session_id,
                    decision_id=None,
                    event_type="SESSION_SCHEDULED",
                    from_status=None,
                    to_status=ShadowSessionStatus.SCHEDULED,
                    expected_version=None,
                    resulting_version=1,
                    reason_codes=("SHADOW_ENGINEERING_ONLY",),
                    event_time=command.scheduled_at,
                    payload={"session_hash": command.session_hash},
                )

        self._factory.run_transaction(operation)
        return self.get_session(command.session_id)

    def mark_running(
        self,
        session_id: ArtifactId,
        *,
        expected_version: int,
        recovered: bool = False,
    ) -> ShadowSessionSnapshot:
        snapshot = self.get_session(session_id)
        expected_status = (
            ShadowSessionStatus.FAILED
            if recovered
            else ShadowSessionStatus.SCHEDULED
        )
        if snapshot.status is not expected_status:
            raise ShadowResearchConflict("Shadow Session is not startable")
        return self._transition(
            session_id,
            expected_version=expected_version,
            from_status=expected_status,
            to_status=ShadowSessionStatus.RUNNING,
            outcome_status=ShadowOutcomeStatus.NOT_EXPECTED,
            event_type="SESSION_RECOVERED" if recovered else "SESSION_RUNNING",
            reason_codes=(
                "SHADOW_SESSION_RECOVERED" if recovered else "SHADOW_SESSION_RUNNING",
            ),
        )

    def freeze(
        self,
        session_id: ArtifactId,
        *,
        summary_id: ArtifactId,
        decision_frozen_at: datetime,
        expected_version: int,
    ) -> ShadowDecision:
        snapshot = self.get_session(session_id)
        if snapshot.status is not ShadowSessionStatus.RUNNING:
            try:
                stored = self.get_decision_for_session(session_id)
            except KeyError as exc:
                raise ShadowResearchConflict(
                    "Shadow Session is not running"
                ) from exc
            if (
                stored.summary.artifact_id == summary_id
                and stored.decision_frozen_at == decision_frozen_at
            ):
                return stored
            raise ShadowResearchConflict("frozen Shadow Decision is immutable")
        summary = self._decisions.get_research_summary(summary_id)
        controlled_operation = self._controlled_operation_reference(
            summary.run_id, summary.tick_id
        )
        decision = ShadowDecision.from_summary(
            session=snapshot.command,
            summary=summary,
            controlled_operation=controlled_operation,
            decision_frozen_at=decision_frozen_at,
        )
        if summary.runtime_mode is not RuntimeAuthorityMode.SHADOW:
            raise ShadowResearchConflict("only SHADOW Summary can freeze")

        def operation(connection: psycopg.Connection[Any]) -> None:
            row = connection.execute(
                """
                SELECT status, version, decision_id
                FROM shadow_research_session
                WHERE session_id = %s FOR UPDATE
                """,
                (str(session_id),),
            ).fetchone()
            if row is None:
                raise KeyError(str(session_id))
            if str(row[0]) != "RUNNING" or int(row[1]) != expected_version:
                raise ShadowResearchConflict(
                    "Shadow freeze rejected by status/version CAS"
                )
            if row[2] is not None:
                raise ShadowResearchConflict("Shadow Decision already exists")
            connection.execute(
                """
                INSERT INTO shadow_research_decision(
                    decision_id, decision_hash, session_id, run_id, tick_id,
                    summary_id, summary_hash, decision_time,
                    decision_frozen_at, payload_json, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    str(decision.decision_id),
                    decision.decision_hash,
                    str(decision.session_id),
                    str(decision.run_id),
                    str(decision.tick_id),
                    str(decision.summary.artifact_id),
                    decision.summary.content_hash,
                    decision.decision_time,
                    decision.decision_frozen_at,
                    Jsonb(decision.to_canonical_dict()),
                    decision.decision_frozen_at,
                ),
            )
            updated = connection.execute(
                """
                UPDATE shadow_research_session
                SET status = 'FROZEN', outcome_status = 'PENDING',
                    decision_id = %s, version = version + 1,
                    reason_codes_json = %s, updated_at = %s
                WHERE session_id = %s AND status = 'RUNNING' AND version = %s
                """,
                (
                    str(decision.decision_id),
                    Jsonb(list(decision.reason_codes)),
                    decision.decision_frozen_at,
                    str(session_id),
                    expected_version,
                ),
            ).rowcount
            if updated != 1:
                raise ShadowResearchConflict("Shadow freeze lost CAS")
            self._insert_event(
                connection,
                session_id=session_id,
                decision_id=decision.decision_id,
                event_type="DECISION_FROZEN",
                from_status=ShadowSessionStatus.RUNNING,
                to_status=ShadowSessionStatus.FROZEN,
                expected_version=expected_version,
                resulting_version=expected_version + 1,
                reason_codes=decision.reason_codes,
                event_time=decision.decision_frozen_at,
                payload={
                    "decision_hash": decision.decision_hash,
                    "summary_id": str(summary_id),
                },
            )

        self._factory.run_transaction(operation)
        return self.get_decision(decision.decision_id)

    def mark_outcome_pending(
        self, session_id: ArtifactId, *, expected_version: int
    ) -> ShadowSessionSnapshot:
        return self._transition(
            session_id,
            expected_version=expected_version,
            from_status=ShadowSessionStatus.FROZEN,
            to_status=ShadowSessionStatus.OUTCOME_PENDING,
            outcome_status=ShadowOutcomeStatus.PENDING,
            event_type="OUTCOME_PENDING",
            reason_codes=("T_PLUS_ONE_OUTCOME_PENDING",),
        )

    def fail(
        self,
        session_id: ArtifactId,
        *,
        expected_version: int,
        reason_codes: tuple[str, ...],
    ) -> ShadowSessionSnapshot:
        snapshot = self.get_session(session_id)
        if snapshot.status not in {
            ShadowSessionStatus.SCHEDULED,
            ShadowSessionStatus.RUNNING,
            ShadowSessionStatus.OUTCOME_PENDING,
        }:
            raise ShadowResearchConflict("Shadow Session cannot fail from this state")
        return self._transition(
            session_id,
            expected_version=expected_version,
            from_status=snapshot.status,
            to_status=ShadowSessionStatus.FAILED,
            outcome_status=snapshot.outcome_status,
            event_type="SESSION_FAILED",
            reason_codes=reason_codes,
        )

    def invalidate(
        self,
        session_id: ArtifactId,
        *,
        expected_version: int,
        reason_codes: tuple[str, ...],
    ) -> ShadowSessionSnapshot:
        snapshot = self.get_session(session_id)
        if snapshot.status in {
            ShadowSessionStatus.SETTLED,
            ShadowSessionStatus.INVALIDATED,
        }:
            raise ShadowResearchConflict("terminal Shadow Session is immutable")
        return self._transition(
            session_id,
            expected_version=expected_version,
            from_status=snapshot.status,
            to_status=ShadowSessionStatus.INVALIDATED,
            outcome_status=ShadowOutcomeStatus.INVALIDATED,
            event_type="SESSION_INVALIDATED",
            reason_codes=reason_codes,
        )

    def mark_settled(
        self,
        session_id: ArtifactId,
        *,
        expected_version: int,
        outcome_available: bool,
        reason_codes: tuple[str, ...],
    ) -> ShadowSessionSnapshot:
        return self._transition(
            session_id,
            expected_version=expected_version,
            from_status=ShadowSessionStatus.OUTCOME_PENDING,
            to_status=ShadowSessionStatus.SETTLED,
            outcome_status=(
                ShadowOutcomeStatus.SETTLED
                if outcome_available
                else ShadowOutcomeStatus.UNAVAILABLE
            ),
            event_type="SESSION_SETTLED",
            reason_codes=reason_codes,
        )

    def get_session(self, session_id: ArtifactId) -> ShadowSessionSnapshot:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT command_json, status, outcome_status, decision_id,
                       version, reason_codes_json, created_at, updated_at,
                       finished_at
                FROM shadow_research_session WHERE session_id = %s
                """,
                (str(session_id),),
            ).fetchone()
        if row is None:
            raise KeyError(str(session_id))
        try:
            return ShadowSessionSnapshot(
                command=ShadowSessionCommand.from_canonical_dict(
                    _json_object(row[0])
                ),
                status=ShadowSessionStatus(str(row[1])),
                outcome_status=ShadowOutcomeStatus(str(row[2])),
                decision_id=(
                    None if row[3] is None else ArtifactId(str(row[3]))
                ),
                version=int(row[4]),
                reason_codes=tuple(str(item) for item in _json_array(row[5])),
                created_at=row[6],
                updated_at=row[7],
                finished_at=row[8],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ShadowResearchIntegrityError(
                "Shadow Session failed canonical restoration"
            ) from exc

    def get_decision(self, decision_id: ArtifactId) -> ShadowDecision:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT payload_json, decision_hash, summary_id, summary_hash
                FROM shadow_research_decision WHERE decision_id = %s
                """,
                (str(decision_id),),
            ).fetchone()
        if row is None:
            raise KeyError(str(decision_id))
        try:
            decision = ShadowDecision.from_canonical_dict(_json_object(row[0]))
        except (KeyError, TypeError, ValueError) as exc:
            raise ShadowResearchIntegrityError(
                "Shadow Decision failed canonical restoration"
            ) from exc
        if (
            decision.decision_hash != str(row[1])
            or str(decision.summary.artifact_id) != str(row[2])
            or decision.summary.content_hash != str(row[3])
        ):
            raise ShadowResearchIntegrityError("Shadow Decision owner lineage drift")
        return decision

    def get_decision_for_session(self, session_id: ArtifactId) -> ShadowDecision:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT decision_id FROM shadow_research_decision
                WHERE session_id = %s
                """,
                (str(session_id),),
            ).fetchone()
        if row is None:
            raise KeyError(str(session_id))
        return self.get_decision(ArtifactId(str(row[0])))

    def replay(self, decision_id: ArtifactId) -> ShadowDecision:
        stored = self.get_decision(decision_id)
        session = self.get_session(stored.session_id)
        summary = self._decisions.get_research_summary(stored.summary.artifact_id)
        rebuilt = ShadowDecision.from_summary(
            session=session.command,
            summary=summary,
            controlled_operation=self._controlled_operation_reference(
                stored.run_id, stored.tick_id
            ),
            decision_frozen_at=stored.decision_frozen_at,
        )
        if rebuilt != stored:
            raise ShadowResearchIntegrityError(
                "Shadow Decision did not replay deterministically"
            )
        return rebuilt

    def events(self, session_id: ArtifactId) -> tuple[dict[str, Any], ...]:
        with self._factory.connection(read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT event_id, decision_id, event_type, from_status,
                       to_status, expected_version, resulting_version,
                       reason_codes_json, event_time, payload_json
                FROM shadow_research_event WHERE session_id = %s
                ORDER BY event_id
                """,
                (str(session_id),),
            ).fetchall()
        return tuple(
            {
                "event_id": int(row[0]),
                "session_id": str(session_id),
                "decision_id": None if row[1] is None else str(row[1]),
                "event_type": str(row[2]),
                "from_status": None if row[3] is None else str(row[3]),
                "to_status": str(row[4]),
                "expected_version": None if row[5] is None else int(row[5]),
                "resulting_version": int(row[6]),
                "reason_codes": [str(item) for item in _json_array(row[7])],
                "event_time": canonical_datetime(row[8]),
                "payload": _json_object(row[9]),
            }
            for row in rows
        )

    def _validate_run(self, command: ShadowSessionCommand) -> None:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT command_json FROM continuous_research_run WHERE run_id = %s
                """,
                (str(command.run_id),),
            ).fetchone()
        if row is None:
            raise ShadowResearchConflict("Canonical Runtime run does not exist")
        run = ContinuousResearchCommand.from_canonical_dict(_json_object(row[0]))
        if (
            run.authority_mode is not RuntimeAuthorityMode.SHADOW
            or run.trading_date != command.trading_date
        ):
            raise ShadowResearchConflict("Shadow Session run lineage mismatch")

    def _controlled_operation_reference(
        self, run_id: ArtifactId, tick_id: ArtifactId
    ) -> RuntimeArtifactReference:
        references = self._continuous.get_child_references(run_id, tick_id)
        controlled = tuple(
            item
            for item in references
            if item.child_kind is ContinuousChildKind.CONTROLLED_OPERATION
        )
        if len(controlled) != 1:
            raise ShadowResearchConflict(
                "Shadow Decision requires one Controlled Operation owner"
            )
        child = controlled[0]
        return RuntimeArtifactReference(
            reference_kind="CONTROLLED_OPERATION",
            artifact_id=child.child_artifact_id or child.child_receipt_id,
            content_hash=child.child_artifact_hash or child.child_receipt_hash,
        )

    def _transition(
        self,
        session_id: ArtifactId,
        *,
        expected_version: int,
        from_status: ShadowSessionStatus,
        to_status: ShadowSessionStatus,
        outcome_status: ShadowOutcomeStatus,
        event_type: str,
        reason_codes: tuple[str, ...],
    ) -> ShadowSessionSnapshot:
        reasons = tuple(sorted(set(reason_codes)))
        if not reasons:
            raise ValueError("Shadow transition requires reason codes")
        event_time = self._clock()

        def operation(connection: psycopg.Connection[Any]) -> None:
            terminal = to_status in {
                ShadowSessionStatus.SETTLED,
                ShadowSessionStatus.FAILED,
                ShadowSessionStatus.INVALIDATED,
            }
            updated = connection.execute(
                """
                UPDATE shadow_research_session
                SET status = %s, outcome_status = %s, version = version + 1,
                    reason_codes_json = %s, updated_at = %s, finished_at = %s
                WHERE session_id = %s AND status = %s AND version = %s
                """,
                (
                    to_status.value,
                    outcome_status.value,
                    Jsonb(list(reasons)),
                    event_time,
                    event_time if terminal else None,
                    str(session_id),
                    from_status.value,
                    expected_version,
                ),
            ).rowcount
            if updated != 1:
                raise ShadowResearchConflict(
                    "Shadow transition rejected by status/version CAS"
                )
            decision_row = connection.execute(
                """
                SELECT decision_id FROM shadow_research_session
                WHERE session_id = %s
                """,
                (str(session_id),),
            ).fetchone()
            if decision_row is None:
                raise RuntimeError("Shadow Session disappeared during transition")
            decision_id = (
                None
                if decision_row[0] is None
                else ArtifactId(str(decision_row[0]))
            )
            self._insert_event(
                connection,
                session_id=session_id,
                decision_id=decision_id,
                event_type=event_type,
                from_status=from_status,
                to_status=to_status,
                expected_version=expected_version,
                resulting_version=expected_version + 1,
                reason_codes=reasons,
                event_time=event_time,
                payload={"outcome_status": outcome_status.value},
            )

        self._factory.run_transaction(operation)
        return self.get_session(session_id)

    def _insert_event(
        self,
        connection: psycopg.Connection[Any],
        *,
        session_id: ArtifactId,
        decision_id: ArtifactId | None,
        event_type: str,
        from_status: ShadowSessionStatus | None,
        to_status: ShadowSessionStatus,
        expected_version: int | None,
        resulting_version: int,
        reason_codes: tuple[str, ...],
        event_time: datetime,
        payload: dict[str, Any],
    ) -> None:
        connection.execute(
            """
            INSERT INTO shadow_research_event(
                session_id, decision_id, event_type, from_status, to_status,
                expected_version, resulting_version, reason_codes_json,
                event_time, payload_json
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                str(session_id),
                None if decision_id is None else str(decision_id),
                event_type,
                None if from_status is None else from_status.value,
                to_status.value,
                expected_version,
                resulting_version,
                Jsonb(list(reason_codes)),
                event_time,
                Jsonb(payload),
            ),
        )


def _json_object(value: object) -> dict[str, Any]:
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, dict):
        raise ShadowResearchIntegrityError("stored Shadow payload is not an object")
    return value


def _json_array(value: object) -> list[Any]:
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, list):
        raise ShadowResearchIntegrityError("stored Shadow payload is not an array")
    return value


__all__ = [
    "PostgresShadowResearchRepository",
    "ShadowResearchConflict",
    "ShadowResearchIntegrityError",
]
