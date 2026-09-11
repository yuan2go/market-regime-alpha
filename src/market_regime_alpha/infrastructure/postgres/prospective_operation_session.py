"""Session lock and short read-only SQL for the prospective process guard."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
import re
from typing import TYPE_CHECKING, Any, Iterator, cast
from uuid import UUID, uuid5

import psycopg
from psycopg.rows import dict_row

if TYPE_CHECKING:
    from market_regime_alpha.market.application.prospective_runtime import (
        ProspectiveRuntimeAdmission,
    )

_ADMISSION_KEY = "runtime:prospective-operation-admission"
_DATABASE_WRITER_KEY = "operator:prospective-database-writer"
_DELIVERY_CHANNEL = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
_operation_session: ContextVar[PostgresProspectiveOperationSession | None] = ContextVar(
    "prospective_operation_session", default=None,
)


def _admission_lock(connection: psycopg.Connection[Any]) -> None:
    # All target Runtime Attempt creation paths and supervisor acquisition use
    # this same transaction lock. It is never held over Provider I/O.
    connection.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (_ADMISSION_KEY,))


def _writer_pid(connection: psycopg.Connection[Any]) -> int | None:
    row = connection.execute(
        """WITH intent AS (SELECT hashtextextended(%s,0) AS key)
           SELECT pid FROM pg_locks, intent
           WHERE locktype='advisory' AND granted AND mode='ExclusiveLock'
             AND database=(SELECT oid FROM pg_database WHERE datname=current_database())
             AND classid::bigint=((intent.key >> 32) & 4294967295)
             AND objid::bigint=(intent.key & 4294967295) AND objsubid=1""",
        (_DATABASE_WRITER_KEY,),
    ).fetchone()
    return None if row is None else int(row[0])


@contextmanager
def canonical_writer_admission(connection: psycopg.Connection[Any]) -> Iterator[None]:
    """Cover owner commands that do not create a Runtime Attempt.

    Unsupervised narrow connections hold shared reservation until returned, so
    supervisor startup cannot race an already admitted transaction. Supervised
    connections require the authentic database-bound reservation instead. The
    short probe commits before owner SQL; nested UoWs and explicit isolation
    remain legal. Runtime claim/fence checks still own business admission.
    """
    session = _operation_session.get()
    locked = False
    try:
        if session is None:
            locked = connection.execute(
                "SELECT pg_try_advisory_lock_shared(hashtextextended(%s,0))",
                (_DATABASE_WRITER_KEY,),
            ).fetchone() == (True,)
            if not locked:
                raise ValueError("OPERATION_CANONICAL_WRITER_ADMISSION_CONFLICT")
        else:
            session.require_supervisor_lock(session.series_code)
            identity = connection.execute(
                "SELECT oid::bigint, (pg_control_system()).system_identifier::text "
                "FROM pg_database WHERE datname=current_database()",
            ).fetchone()
            if identity != (session.database_oid, session.cluster_identity):
                raise ValueError("OPERATION_CANONICAL_WRITER_SCOPE_MISMATCH")
        connection.commit()
        yield
    finally:
        if locked and not connection.closed:
            connection.rollback()
            connection.execute(
                "SELECT pg_advisory_unlock_shared(hashtextextended(%s,0))",
                (_DATABASE_WRITER_KEY,),
            )
            connection.commit()


@contextmanager
def retained_writer_admission(connection: psycopg.Connection[Any]) -> Iterator[None]:
    """Keep retained connections outside canonical claims without owning facts.

    Shared session admission permits existing nested connections and explicit
    transaction isolation. The admission probe commits before the owner begins
    its transaction; the lock survives owner commits until the connection is
    returned. No business I/O is placed inside the probe transaction.
    """
    locked = False
    try:
        connection.execute("SELECT pg_advisory_lock_shared(hashtextextended(%s,0))", (_ADMISSION_KEY,))
        locked = True
        if _writer_pid(connection) is not None:
            raise ValueError("OPERATION_RETAINED_WRITER_ADMISSION_CONFLICT")
        if connection.execute("SELECT to_regclass('mra.runtime_attempt')").fetchone() != (None,):
            if connection.execute(
                "SELECT EXISTS(SELECT 1 FROM mra.runtime_attempt WHERE state IN ('CLAIMED','RUNNING'))"
            ).fetchone() != (False,):
                raise ValueError("OPERATION_RETAINED_WRITER_ADMISSION_CONFLICT")
        connection.commit()
        yield
    finally:
        if locked and not connection.closed:
            # Caller commits/rolls back its business transaction before this
            # scope exits. Refusal in the probe must also leave a clean session.
            connection.rollback()
            connection.execute("SELECT pg_advisory_unlock_shared(hashtextextended(%s,0))", (_ADMISSION_KEY,))
            connection.commit()


def admit_runtime_attempt(connection: psycopg.Connection[Any], *, run_id: UUID | None,
                          step_id: UUID | None = None) -> None:
    """Atomic operational exclusion shared by every current target Runtime claim.

    This is process admission, not a new lease/Authority. Current Runtime still
    owns the Attempt/fence and result transaction. Old/nonparticipating clients
    must be excluded by deployment preflight; advisory locks do not fence SQL
    issued by arbitrary database credentials.
    """
    _admission_lock(connection)
    owner = _writer_pid(connection)
    session = _operation_session.get()
    if session is None:
        if owner is not None:
            raise ValueError("OPERATION_RUNTIME_ADMISSION_CONFLICT")
        return
    session.require_supervisor_lock(session.series_code)
    if owner != session.connection.info.backend_pid:
        raise ValueError("OPERATION_RUNTIME_ADMISSION_CONFLICT")
    scope = connection.execute(
        "SELECT oid::bigint, (pg_control_system()).system_identifier::text "
        "FROM pg_database WHERE datname=current_database()",
    ).fetchone()
    if scope != (session.database_oid, session.cluster_identity):
        raise ValueError("OPERATION_RUNTIME_ADMISSION_SCOPE_MISMATCH")
    if run_id is None and step_id is not None:
        row = connection.execute("SELECT run_id FROM mra.runtime_step WHERE step_id=%s", (step_id,)).fetchone()
        run_id = None if row is None else row[0]
    if (
        not session.prospective_run_matches(connection, run_id)
        and not session.daily_run_matches(connection, run_id)
        and not session.daily_delivery_run_matches(connection, run_id)
        and not session.backtest_run_matches(connection, run_id)
    ):
        raise ValueError("OPERATION_RUNTIME_RUN_OUTSIDE_SERIES")
    if session.has_conflicting_attempts(session.series_code):
        raise ValueError("OPERATION_ACTIVE_ATTEMPT_CONFLICT")


def remember_operational_attempt(attempt_id: UUID) -> None:
    session = _operation_session.get()
    if session is not None:
        # IDs are generated by the canonical Runtime writer, never by worker-id
        # text. Rolled-back IDs match no row; commit-unknown is owner-reconciled.
        session.own_attempt_ids.add(attempt_id)


class PostgresProspectiveOperationSession:
    def __init__(self, connection: psycopg.Connection[Any]) -> None:
        self.connection = connection
        self.series_code = ""
        self.database_oid = 0
        self.cluster_identity = ""
        self.own_attempt_ids: set[UUID] = set()
        self.daily_scope: tuple[UUID,str,str,str | None,int] | None = None
        self.backtest_scope: tuple[UUID,str] | None = None
        self.daily_recovery_scope: tuple[UUID, str] | None = None
        self.frozen_daily_recovery: set[tuple[UUID, str, str]] = set()
        self.daily_delivery_scope: tuple[UUID, UUID, str, str, str] | None = None
        self.prospective_scope: ProspectiveRuntimeAdmission | None = None
        self.prospective_recovery_scopes: tuple[ProspectiveRuntimeAdmission, ...] = ()

    def allow_prospective_recovery(
        self, scopes: tuple[ProspectiveRuntimeAdmission, ...]
    ) -> None:
        """Freeze the exact manifest-derived Run roster allowed at startup."""

        self.require_supervisor_lock(self.series_code)
        if any(scope.series_code != self.series_code for scope in scopes):
            raise ValueError("OPERATION_RUNTIME_RUN_OUTSIDE_SERIES")
        self.prospective_recovery_scopes = scopes

    def prospective_run_matches(
        self, connection: psycopg.Connection[Any], run_id: UUID | None
    ) -> bool:
        """Verify an exact persisted Runtime against positive frozen series intent."""

        scope = self.prospective_scope
        if scope is None or run_id is None:
            return False
        run_scope = next((item for item in scope.runs if item.run_id == run_id), None)
        if run_scope is None:
            return False
        row = connection.execute(
            """
            SELECT run.schedule_id, schedule.schedule_code, schedule.revision,
                   schedule.runtime_mode, schedule.step_catalog_hash,
                   run.fire_key, run.runtime_mode, run.code_sha, run.config_hash,
                   artifact.content_sha256, artifact.size_bytes
            FROM mra.runtime_run AS run
            JOIN mra.runtime_schedule AS schedule USING (schedule_id)
            JOIN mra.artifact AS artifact
              ON artifact.artifact_id = run.config_artifact_id
             AND artifact.content_sha256 = run.config_hash
            WHERE run.run_id = %s AND schedule.enabled
            """,
            (run_id,),
        ).fetchone()
        if row != (
            scope.schedule_id,
            "prospective-archive",
            scope.schedule_revision,
            "PROSPECTIVE",
            scope.step_catalog_hash,
            run_scope.fire_key,
            "PROSPECTIVE",
            scope.code_sha,
            scope.config_sha256,
            scope.config_sha256,
            scope.config_size_bytes,
        ):
            return False
        step_rows = connection.execute(
            """
            SELECT step_key, step_kind, implementation, implementation_version,
                   ordinal, required, request_hash, input_evidence_hash,
                   max_attempts, retry_backoff_ms, retryable_error_codes,
                   deadline_at, external_effect_class
            FROM mra.runtime_step
            WHERE run_id = %s
            ORDER BY ordinal
            """,
            (run_id,),
        ).fetchall()
        actual_steps = tuple(
            (
                str(item[0]), str(item[1]), str(item[2]), str(item[3]),
                int(item[4]), bool(item[5]), str(item[6]),
                None if item[7] is None else str(item[7]), int(item[8]),
                tuple(int(value) for value in item[9]),
                tuple(sorted(str(value) for value in item[10])), item[11],
                str(item[12]),
            )
            for item in step_rows
        )
        if actual_steps != run_scope.step_roster:
            return False
        generation = connection.execute(
            """
            SELECT generation.series_code, generation.generation,
                   generation.predecessor_market_archive_id,
                   generation.target_definition_id, generation.target_version,
                   generation.target_definition_sha256,
                   generation.content_sha256, archive.request_sha256,
                   archive.lane
            FROM mra.prospective_archive_generation AS generation
            JOIN mra.market_archive AS archive USING (market_archive_id)
            WHERE generation.market_archive_id = %s
            """,
            (scope.market_archive_id,),
        ).fetchone()
        if generation is not None:
            return generation == (
                scope.series_code,
                scope.generation,
                scope.predecessor_market_archive_id,
                scope.target_definition_id,
                scope.target_version,
                scope.target_definition_sha256,
                scope.generation_sha256,
                scope.archive_request_sha256,
                "PROSPECTIVE_CONTEMPORANEOUS",
            )
        # Before the first command commits there is no Archive row to query.
        # Positive identity is the exact frozen config + persisted Run above and
        # the supervisor-bound series capability. Only that predeclare Run may
        # create the initial canonical Archive/generation atomically.
        if run_id != scope.predeclare_run_id:
            return False
        if connection.execute(
            "SELECT EXISTS(SELECT 1 FROM mra.market_archive WHERE market_archive_id=%s)",
            (scope.market_archive_id,),
        ).fetchone() != (False,):
            return False
        same_slot = connection.execute(
            """
            SELECT market_archive_id
            FROM mra.prospective_archive_generation
            WHERE series_code = %s AND generation = %s
            """,
            (scope.series_code, scope.generation),
        ).fetchone()
        if same_slot is not None:
            return False
        if scope.generation == 1:
            return scope.predecessor_market_archive_id is None
        predecessor = connection.execute(
            """
            SELECT series_code, generation
            FROM mra.prospective_archive_generation
            WHERE market_archive_id = %s
            """,
            (scope.predecessor_market_archive_id,),
        ).fetchone()
        return predecessor == (scope.series_code, scope.generation - 1)

    def allow_expired_daily_recovery(self, use_id: UUID, code_sha: str) -> None:
        """Called only after the operator template's canonical model/config checks.

        This admits inspection/recovery of expired safe-effect steps; it grants
        no claim capability. Each new claim still needs its exact daily handoff.
        """
        self.require_supervisor_lock(self.series_code)
        self.daily_recovery_scope = (use_id, code_sha)

    def allow_frozen_daily_recovery(self, *, prediction_id: UUID, code_sha: str, config_sha256: str) -> None:
        """Only owner-reloaded immutable plans may extend startup recovery scope.

        This permits expired safe-effect reconciliation, never a new claim.
        Claiming still requires the sequential exact-plan handoff.
        """
        self.require_supervisor_lock(self.series_code)
        self.frozen_daily_recovery.add((prediction_id, code_sha, config_sha256))

    def daily_recovery_run_matches(
        self, connection: psycopg.Connection[Any], run_id: UUID
    ) -> bool:
        for prediction_id, code_sha, config_sha256 in self.frozen_daily_recovery:
            if run_id != uuid5(prediction_id, "outcome-evaluation-runtime"):
                continue
            if connection.execute(
                """SELECT EXISTS(SELECT 1 FROM mra.runtime_run run
                   JOIN mra.artifact artifact ON artifact.artifact_id=run.config_artifact_id
                   WHERE run.run_id=%s AND run.code_sha=%s AND run.config_hash=%s
                     AND artifact.content_sha256=run.config_hash
                     AND run.parent_run_id=%s AND run.fire_key=%s AND run.runtime_mode='SHADOW'
                     AND EXISTS(SELECT 1 FROM mra.runtime_step step WHERE step.run_id=run.run_id)
                     AND NOT EXISTS(SELECT 1 FROM mra.runtime_step step WHERE step.run_id=run.run_id
                       AND (step.implementation NOT LIKE 'research.daily_outcome.%%'
                            OR step.external_effect_class NOT IN ('NONE','CONTENT_PUT'))))""",
                (run_id, code_sha, config_sha256, uuid5(prediction_id, "prediction-runtime"),
                 "daily-outcome:" + str(prediction_id)),
            ).fetchone() == (True,):
                return True
        if self.daily_recovery_scope is None:
            return False
        use_id, code_sha = self.daily_recovery_scope
        schedules = (
            "daily-model-" + use_id.hex,
            "daily-outcome-" + use_id.hex,
            "daily-abstention-" + use_id.hex,
            "daily-input-collection-" + use_id.hex,
            "daily-outcome-collection-" + use_id.hex,
            "daily-population-collection-" + use_id.hex,
        )
        return connection.execute(
            """
            SELECT EXISTS(
              SELECT 1
              FROM mra.runtime_run AS run
              JOIN mra.runtime_schedule AS schedule USING (schedule_id)
              WHERE run.run_id = %s
                AND run.runtime_mode = 'SHADOW'
                AND run.code_sha = %s
                AND schedule.schedule_code = ANY(%s::text[])
                AND EXISTS(
                  SELECT 1 FROM mra.runtime_step AS step
                  WHERE step.run_id = run.run_id
                )
                AND NOT EXISTS(
                  SELECT 1 FROM mra.runtime_step AS step
                  WHERE step.run_id = run.run_id
                    AND step.external_effect_class NOT IN ('NONE', 'CONTENT_PUT')
                )
                AND NOT EXISTS(
                  SELECT 1 FROM mra.runtime_step AS step
                  WHERE step.run_id = run.run_id
                    AND NOT (
                      step.implementation LIKE 'research.daily_prediction.%%'
                      OR step.implementation LIKE 'research.daily_outcome.%%'
                      OR step.implementation = 'research.daily_abstention.record'
                      OR step.implementation LIKE 'market.daily_research.input.%%'
                      OR step.implementation LIKE 'market.daily_research.outcome.%%'
                      OR step.implementation LIKE 'market.daily_research.population.%%'
                    )
                )
            )
            """,
            (run_id, code_sha, list(schedules)),
        ).fetchone() == (True,)

    def backtest_run_matches(self, connection: psycopg.Connection[Any], run_id: UUID | None) -> bool:
        if self.backtest_scope is None or run_id is None:
            return False
        identity, digest = self.backtest_scope
        return connection.execute("""SELECT EXISTS(SELECT 1 FROM mra.backtest_runtime_binding binding
            JOIN mra.exploratory_backtest_run backtest USING(exploratory_backtest_run_id)
            JOIN mra.runtime_run run ON run.run_id=binding.runtime_run_id
            WHERE run.run_id=%s AND binding.exploratory_backtest_run_id=%s
              AND binding.specification_sha256=%s AND backtest.current_specification_sha256=%s
              AND run.runtime_mode='HISTORICAL'
              AND NOT EXISTS(SELECT 1 FROM mra.runtime_step step WHERE step.run_id=run.run_id
                AND step.implementation<>%s))""", (run_id,identity,digest,digest,
                'market_regime_alpha.research_qualification.application.backtest_runtime:BacktestRuntimeActionExecutor')).fetchone()==(True,)

    def daily_run_matches(self, connection: psycopg.Connection[Any], run_id: UUID | None) -> bool:
        if self.daily_scope is None or run_id is None:
            return False
        identity,code,config,phase,round_no=self.daily_scope
        allowed={uuid5(identity,'prediction-runtime'):('daily:'+str(identity),'research.daily_prediction.'),
                 uuid5(identity,'outcome-evaluation-runtime'):('daily-outcome:'+str(identity),'research.daily_outcome.'),
                 uuid5(identity,'abstention-runtime'):('daily-abstention:'+str(identity),'research.daily_abstention.')}
        if phase is not None:
            allowed={uuid5(identity,phase+'-collection:'+str(round_no)):
                ('daily-'+phase+':'+str(identity)+':round:'+str(round_no),'market.daily_research.'+phase+'.')}
        if run_id not in allowed:
            return False
        fire,prefix=allowed[run_id]
        return connection.execute("""SELECT EXISTS(SELECT 1 FROM mra.runtime_run run
            WHERE run.run_id=%s AND run.runtime_mode='SHADOW' AND run.fire_key=%s AND run.code_sha=%s AND run.config_hash=%s
              AND EXISTS(SELECT 1 FROM mra.runtime_step step WHERE step.run_id=run.run_id)
              AND NOT EXISTS(SELECT 1 FROM mra.runtime_step step WHERE step.run_id=run.run_id
                AND step.implementation NOT LIKE %s))""",(run_id,fire,code,config,prefix+'%')).fetchone()==(True,)

    def daily_delivery_run_matches(
        self, connection: psycopg.Connection[Any], run_id: UUID | None
    ) -> bool:
        if self.daily_delivery_scope is None or run_id is None:
            return False
        prediction_id, use_id, code_sha, config_sha256, channel = (
            self.daily_delivery_scope
        )
        expected_run_id = uuid5(prediction_id, "report-delivery:" + channel)
        expected_schedule_id = uuid5(
            use_id, "daily-delivery-schedule:" + channel
        )
        if run_id != expected_run_id:
            return False
        return connection.execute(
            """
            SELECT EXISTS(
              SELECT 1
              FROM mra.runtime_run AS run
              JOIN mra.runtime_schedule AS schedule USING (schedule_id)
              WHERE run.run_id = %s
                AND run.schedule_id = %s
                AND schedule.schedule_code = %s
                AND schedule.runtime_mode = 'SHADOW'
                AND run.runtime_mode = 'SHADOW'
                AND run.fire_key = %s
                AND run.code_sha = %s
                AND run.config_hash = %s
                AND (SELECT count(*) FROM mra.runtime_step AS step
                     WHERE step.run_id = run.run_id) = 1
                AND EXISTS(
                  SELECT 1 FROM mra.runtime_step AS step
                  WHERE step.run_id = run.run_id
                    AND step.step_key = 'deliver-report'
                    AND step.implementation = 'research.daily_delivery.deliver-report'
                    AND step.external_effect_class = 'IDEMPOTENT_REMOTE_COMMAND'
                )
            )
            """,
            (
                run_id,
                expected_schedule_id,
                "daily-delivery-" + use_id.hex + "-" + channel,
                "daily-delivery:" + str(prediction_id) + ":" + channel,
                code_sha,
                config_sha256,
            ),
        ).fetchone() == (True,)

    def snapshot(self) -> dict[str, Any]:
        from market_regime_alpha.infrastructure.postgres.queries.evidence import read_evidence_snapshot

        with self.connection.transaction():
            self.connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            return read_evidence_snapshot(self.connection)

    def require_supervisor_lock(self, series_code: str) -> None:
        if self.connection.closed:
            raise ValueError("OPERATION_SUPERVISOR_CONNECTION_LOST")
        try:
            row = self.connection.execute(
                """WITH intent AS (SELECT hashtextextended(%s,0) AS key)
                   SELECT EXISTS (SELECT 1 FROM pg_locks, intent
                     WHERE pid=pg_backend_pid() AND locktype='advisory' AND granted
                       AND classid::bigint=((intent.key >> 32) & 4294967295)
                       AND objid::bigint=(intent.key & 4294967295) AND objsubid=1)""",
                ("operator:prospective-series:" + series_code,),
            ).fetchone()
        except psycopg.Error as exc:
            raise ValueError("OPERATION_SUPERVISOR_CONNECTION_LOST") from exc
        if row != (True,):
            raise ValueError("OPERATION_SUPERVISOR_LOCK_LOST")
        if _writer_pid(self.connection) != self.connection.info.backend_pid:
            raise ValueError("OPERATION_SUPERVISOR_LOCK_LOST")

    def has_conflicting_attempts(self, series_code: str) -> bool:
        self.require_supervisor_lock(series_code)
        rows = self.connection.execute(
            """SELECT attempt.attempt_id, step.run_id,
                      attempt.lease_until > clock_timestamp() AS lease_live
               FROM mra.runtime_attempt AS attempt
               JOIN mra.runtime_step AS step USING (step_id)
               WHERE attempt.state IN ('CLAIMED','RUNNING')
                 AND NOT (attempt.attempt_id = ANY(%s::uuid[]))
               ORDER BY attempt.attempt_id
            """,
            (list(self.own_attempt_ids),),
        ).fetchall()
        admitted_prospective_run_ids = {
            run.run_id
            for scope in self.prospective_recovery_scopes
            for run in scope.runs
        }
        for _attempt_id, run_id, lease_live in rows:
            if lease_live:
                return True
            if run_id in admitted_prospective_run_ids:
                continue
            if self.daily_run_matches(self.connection, run_id):
                continue
            if self.daily_delivery_run_matches(self.connection, run_id):
                continue
            if self.daily_recovery_run_matches(self.connection, run_id):
                continue
            return True
        return False

    def clock(self) -> datetime:
        row = self.connection.execute("SELECT clock_timestamp()").fetchone()
        if row is None:
            raise ValueError("OPERATION_DATABASE_CLOCK_UNAVAILABLE")
        return cast(datetime, row[0])

    def generations(self, series_code: str) -> list[dict[str, Any]]:
        with self.connection.transaction(), self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute("SET TRANSACTION READ ONLY")
            return cursor.execute(
                "SELECT * FROM mra.prospective_archive_generation WHERE series_code=%s ORDER BY generation",
                (series_code,),
            ).fetchall()


@contextmanager
def prospective_operation_session(
    database_url: str, *, database_name: str, database_oid: int,
    cluster_identity: str, series_code: str,
) -> Iterator[PostgresProspectiveOperationSession]:
    """Bind one advisory lock to one session without spanning a transaction."""
    with psycopg.connect(database_url, autocommit=True,
                         application_name="mra-prospective-supervisor") as connection:
        row = connection.execute(
            "SELECT current_database(), oid::bigint, (pg_control_system()).system_identifier::text "
            "FROM pg_database WHERE datname=current_database()",
        ).fetchone()
        if row != (database_name, database_oid, cluster_identity):
            raise ValueError("OPERATION_DATABASE_IDENTITY_MISMATCH")
        key = "operator:prospective-series:" + series_code
        with connection.transaction():
            _admission_lock(connection)
            locked = connection.execute("SELECT pg_try_advisory_lock(hashtextextended(%s,0))", (key,)).fetchone()
            database_locked = connection.execute(
                "SELECT pg_try_advisory_lock(hashtextextended(%s,0))", (_DATABASE_WRITER_KEY,),
            ).fetchone()
            if locked != (True,) or database_locked != (True,):
                raise ValueError("OPERATION_DUPLICATE_SUPERVISOR")
        session = PostgresProspectiveOperationSession(connection)
        session.series_code, session.database_oid, session.cluster_identity = series_code, database_oid, cluster_identity
        token = _operation_session.set(session)
        try:
            yield session
        finally:
            _operation_session.reset(token)
            if not connection.closed:
                connection.execute("SELECT pg_advisory_unlock(hashtextextended(%s,0))", (key,))
                connection.execute("SELECT pg_advisory_unlock(hashtextextended(%s,0))", (_DATABASE_WRITER_KEY,))


@contextmanager
def prospective_series_admission(
    scope: ProspectiveRuntimeAdmission,
) -> Iterator[None]:
    """Bind exact frozen prospective intent to the current supervisor briefly."""

    session = _operation_session.get()
    if session is None:
        yield
        return
    session.require_supervisor_lock(session.series_code)
    if scope.series_code != session.series_code:
        raise ValueError("OPERATION_RUNTIME_RUN_OUTSIDE_SERIES")
    if (
        session.prospective_scope is not None
        or session.daily_scope is not None
        or session.daily_delivery_scope is not None
        or session.backtest_scope is not None
    ):
        raise ValueError("OPERATION_NESTED_RUNTIME_ADMISSION")
    with session.connection.transaction():
        _admission_lock(session.connection)
        session.prospective_scope = scope
    try:
        if session.has_conflicting_attempts(session.series_code):
            raise ValueError("OPERATION_ACTIVE_ATTEMPT_CONFLICT")
        yield
    finally:
        session.prospective_scope = None


@contextmanager
def daily_research_admission(*, prediction_id: UUID, code_sha: str, config_sha256: str, collection_phase: str | None=None, collection_round: int=1) -> Iterator[None]:
    """Sequential handoff inside the existing supervisor, bound to two exact Runs.

    No lock is released; other Runtime workers remain excluded by atomic admission.
    This process capability is not a business registration or execution Authority.
    """
    if collection_phase not in {None,'input','outcome','population','calendar'} or not 1<=collection_round<=16 or collection_phase == 'calendar' and collection_round != 1:
        raise ValueError('DAILY_OPERATION_SCOPE_INVALID')
    session=_operation_session.get()
    if session is None:
        raise ValueError('DAILY_OPERATION_REQUIRES_SUPERVISOR')
    session.require_supervisor_lock(session.series_code)
    if session.prospective_scope is not None or session.daily_scope is not None or session.daily_delivery_scope is not None or session.backtest_scope is not None:
        raise ValueError('DAILY_OPERATION_NESTED_HANDOFF')
    with session.connection.transaction():
        _admission_lock(session.connection)
        if session.connection.execute("SELECT EXISTS(SELECT 1 FROM mra.runtime_attempt WHERE state IN ('CLAIMED','RUNNING') AND lease_until>clock_timestamp())").fetchone()!=(False,):
            raise ValueError('OPERATION_ACTIVE_ATTEMPT_CONFLICT')
        session.daily_scope=(prediction_id,code_sha,config_sha256,collection_phase,collection_round)
    try:
        if session.has_conflicting_attempts(session.series_code):
            raise ValueError('OPERATION_ACTIVE_ATTEMPT_CONFLICT')
        yield
    finally:
        session.daily_scope=None


@contextmanager
def daily_delivery_admission(
    *,
    prediction_id: UUID,
    experimental_model_use_id: UUID,
    code_sha: str,
    config_sha256: str,
    channel: str,
) -> Iterator[None]:
    """Bind one exact report/channel delivery Run to the existing supervisor."""

    if not _DELIVERY_CHANNEL.fullmatch(channel):
        raise ValueError("DAILY_DELIVERY_CHANNEL_INVALID")
    session = _operation_session.get()
    if session is None:
        raise ValueError("DAILY_DELIVERY_REQUIRES_SUPERVISOR")
    session.require_supervisor_lock(session.series_code)
    if (
        session.prospective_scope is not None
        or session.daily_scope is not None
        or session.daily_delivery_scope is not None
        or session.backtest_scope is not None
    ):
        raise ValueError("DAILY_OPERATION_NESTED_HANDOFF")
    with session.connection.transaction():
        _admission_lock(session.connection)
        if session.connection.execute(
            """
            SELECT EXISTS(
              SELECT 1 FROM mra.runtime_attempt
              WHERE state IN ('CLAIMED', 'RUNNING')
                AND lease_until > clock_timestamp()
            )
            """
        ).fetchone() != (False,):
            raise ValueError("OPERATION_ACTIVE_ATTEMPT_CONFLICT")
        session.daily_delivery_scope = (
            prediction_id,
            experimental_model_use_id,
            code_sha,
            config_sha256,
            channel,
        )
    try:
        if session.has_conflicting_attempts(session.series_code):
            raise ValueError("OPERATION_ACTIVE_ATTEMPT_CONFLICT")
        yield
    finally:
        session.daily_delivery_scope = None


@contextmanager
def backtest_research_admission(*, backtest_run_id: UUID, specification_sha256: str) -> Iterator[None]:
    """Planned Generic research uses the same reservation during collection pause."""
    session = _operation_session.get()
    if session is None:
        raise ValueError('BACKTEST_OPERATION_REQUIRES_SUPERVISOR')
    session.require_supervisor_lock(session.series_code)
    if session.prospective_scope is not None or session.daily_scope is not None or session.daily_delivery_scope is not None or session.backtest_scope is not None:
        raise ValueError('BACKTEST_OPERATION_NESTED_HANDOFF')
    with session.connection.transaction():
        _admission_lock(session.connection)
        if session.connection.execute("SELECT EXISTS(SELECT 1 FROM mra.runtime_attempt WHERE state IN ('CLAIMED','RUNNING'))").fetchone()!=(False,):
            raise ValueError('OPERATION_ACTIVE_ATTEMPT_CONFLICT')
        if session.connection.execute('SELECT current_specification_sha256 FROM mra.exploratory_backtest_run WHERE exploratory_backtest_run_id=%s', (backtest_run_id,)).fetchone()!=(specification_sha256,):
            raise ValueError('BACKTEST_OPERATION_SPECIFICATION_MISMATCH')
        session.backtest_scope=(backtest_run_id,specification_sha256)
    try:
        yield
    finally:
        session.backtest_scope=None
