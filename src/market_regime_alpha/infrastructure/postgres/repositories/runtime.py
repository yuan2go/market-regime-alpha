"""PostgreSQL owner for the Run/Step/Attempt aggregate and cross-cutting receipts."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import UUID

import psycopg

from market_regime_alpha.runtime.domain import (
    RunSpec,
    ScheduleSpec,
    StepDependency,
    StepSpec,
)
from market_regime_alpha.runtime.errors import (
    CommandInProgressError,
    IdempotencyKeyReusedError,
    RuntimeNotFoundError,
    RuntimeStateConflictError,
    StaleFenceError,
)
from market_regime_alpha.runtime.ports import (
    AttemptClaim,
    ReceiptRecord,
    RecoveryDecision,
    RunTrace,
    StepTrace,
)


_SAFE_RETRY_EFFECTS = frozenset({"NONE", "PURE_READ", "CONTENT_PUT", "OBSERVATION_ONLY"})
_REMOTE_EFFECTS = frozenset(
    {"IDEMPOTENT_REMOTE_COMMAND", "NON_IDEMPOTENT_REMOTE_COMMAND"}
)
_TERMINAL_STEP_STATES = (
    "SUCCEEDED",
    "BLOCKED",
    "FAILED",
    "CANCELLED",
    "SKIPPED",
)


class PostgresRuntimeRepository:
    """Aggregate operations only; transaction ownership remains with the UoW."""

    def __init__(self, connection: psycopg.Connection[Any]) -> None:
        self._connection = connection

    def insert_schedule(self, schedule: ScheduleSpec) -> None:
        self._connection.execute(
            """
            INSERT INTO mra.runtime_schedule (
                schedule_id, schedule_code, revision, runtime_mode,
                schedule_expression, timezone_name, step_catalog_hash,
                enabled, supersedes_schedule_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                schedule.schedule_id,
                schedule.schedule_code,
                schedule.revision,
                schedule.runtime_mode.value,
                schedule.schedule_expression,
                schedule.timezone_name,
                schedule.step_catalog_hash,
                schedule.enabled,
                schedule.supersedes_schedule_id,
            ),
        )

    def insert_run(
        self,
        run: RunSpec,
        steps: tuple[tuple[UUID, StepSpec], ...],
        dependencies: tuple[StepDependency, ...],
    ) -> None:
        schedule = self._connection.execute(
            """
            SELECT runtime_mode, enabled
            FROM mra.runtime_schedule
            WHERE schedule_id = %s
            FOR SHARE
            """,
            (run.schedule_id,),
        ).fetchone()
        if schedule is None:
            raise RuntimeNotFoundError(f"Schedule {run.schedule_id} does not exist")
        if not schedule[1] or schedule[0] != run.runtime_mode.value:
            raise RuntimeStateConflictError(
                "Run requires an enabled Schedule with the same Runtime mode"
            )
        config_artifact = self._connection.execute(
            """
            SELECT content_sha256, integrity_state
            FROM mra.artifact
            WHERE artifact_id = %s
            FOR SHARE
            """,
            (run.config_artifact_id,),
        ).fetchone()
        if config_artifact is None:
            raise RuntimeNotFoundError(
                f"Run config Artifact {run.config_artifact_id} does not exist"
            )
        if config_artifact != (run.config_hash, "AVAILABLE"):
            raise RuntimeStateConflictError(
                "Run config Artifact hash or integrity state does not match"
            )
        self._connection.execute(
            """
            INSERT INTO mra.runtime_run (
                run_id, schedule_id, fire_key, runtime_mode, requested_at,
                decision_time, code_sha, config_artifact_id, config_hash,
                schema_epoch, parent_run_id, original_run_id, state
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s,
                    'MRA_REFOUNDATION_1', %s, %s, 'QUEUED')
            """,
            (
                run.run_id,
                run.schedule_id,
                run.fire_key,
                run.runtime_mode.value,
                run.requested_at,
                run.decision_time,
                run.code_sha,
                run.config_artifact_id,
                run.config_hash,
                run.parent_run_id,
                run.original_run_id,
            ),
        )
        ids_by_key = {step.step_key: step_id for step_id, step in steps}
        for step_id, step in steps:
            backoff_ms = [
                int(delay.total_seconds() * 1_000)
                for delay in step.retry_policy.backoff
            ]
            self._connection.execute(
                """
                INSERT INTO mra.runtime_step (
                    step_id, run_id, step_key, step_kind, implementation,
                    implementation_version, required, ordinal, request_hash,
                    input_evidence_hash, max_attempts, retry_backoff_ms,
                    retryable_error_codes, deadline_at, external_effect_class,
                    state
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, 'PENDING')
                """,
                (
                    step_id,
                    run.run_id,
                    step.step_key,
                    step.step_kind,
                    step.implementation,
                    step.implementation_version,
                    step.required,
                    step.ordinal,
                    step.request_hash,
                    step.input_evidence_hash,
                    step.retry_policy.max_attempts,
                    backoff_ms,
                    sorted(step.retry_policy.retryable_codes),
                    step.retry_policy.deadline,
                    step.external_effect_class.value,
                ),
            )
        for dependency in dependencies:
            self._connection.execute(
                """
                INSERT INTO mra.runtime_step_dependency (
                    run_id, predecessor_step_id, successor_step_id, dependency_kind
                )
                VALUES (%s, %s, %s, %s)
                """,
                (
                    run.run_id,
                    ids_by_key[dependency.predecessor_key],
                    ids_by_key[dependency.successor_key],
                    dependency.dependency_kind,
                ),
            )

    def start_run(self, run_id: UUID) -> int:
        row = self._connection.execute(
            "SELECT state, version FROM mra.runtime_run WHERE run_id = %s FOR UPDATE",
            (run_id,),
        ).fetchone()
        if row is None:
            raise RuntimeNotFoundError(f"Run {run_id} does not exist")
        if row[0] != "QUEUED":
            raise RuntimeStateConflictError(
                f"Run {run_id} must be QUEUED, found {row[0]}"
            )
        updated = self._connection.execute(
            """
            UPDATE mra.runtime_run
            SET state = 'RUNNING', started_at = clock_timestamp(), version = version + 1
            WHERE run_id = %s AND state = 'QUEUED'
            RETURNING version
            """,
            (run_id,),
        ).fetchone()
        if updated is None:
            raise RuntimeStateConflictError(f"Run {run_id} start lost a state race")
        self._connection.execute(
            """
            UPDATE mra.runtime_step AS step
            SET state = 'READY', ready_at = clock_timestamp(), version = version + 1
            WHERE step.run_id = %s
              AND step.state = 'PENDING'
              AND NOT EXISTS (
                  SELECT 1
                  FROM mra.runtime_step_dependency AS dependency
                  WHERE dependency.run_id = step.run_id
                    AND dependency.successor_step_id = step.step_id
              )
            """,
            (run_id,),
        )
        return int(updated[0])

    def claim_next(
        self,
        *,
        attempt_id: UUID,
        worker_id: str,
        lease_duration: timedelta,
    ) -> AttemptClaim | None:
        lease_ms = _lease_milliseconds(lease_duration)
        row = self._connection.execute(
            """
            SELECT
                step.step_id, step.run_id, step.step_key, step.current_fence,
                step.max_attempts, step.external_effect_class,
                COALESCE((
                    SELECT max(attempt.attempt_no)
                    FROM mra.runtime_attempt AS attempt
                    WHERE attempt.step_id = step.step_id
                ), 0) AS prior_attempts
            FROM mra.runtime_step AS step
            JOIN mra.runtime_run AS run ON run.run_id = step.run_id
            WHERE run.state = 'RUNNING'
              AND step.state = 'READY'
              AND step.ready_at <= clock_timestamp()
              AND (step.deadline_at IS NULL OR step.deadline_at > clock_timestamp())
              AND NOT EXISTS (
                  SELECT 1
                  FROM mra.runtime_step AS live_step
                  WHERE live_step.run_id = run.run_id
                    AND live_step.state IN ('CLAIMED', 'RUNNING')
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM mra.runtime_step_dependency AS dependency
                  JOIN mra.runtime_step AS predecessor
                    ON predecessor.step_id = dependency.predecessor_step_id
                  WHERE dependency.run_id = step.run_id
                    AND dependency.successor_step_id = step.step_id
                    AND (
                        (dependency.dependency_kind = 'REQUIRED_SUCCESS'
                         AND predecessor.state NOT IN ('SUCCEEDED', 'SKIPPED'))
                        OR
                        (dependency.dependency_kind = 'TERMINAL'
                         AND predecessor.state NOT IN ('SUCCEEDED', 'BLOCKED', 'FAILED', 'CANCELLED', 'SKIPPED'))
                    )
              )
            ORDER BY run.created_at, step.ordinal, step.step_id
            FOR UPDATE OF run, step SKIP LOCKED
            LIMIT 1
            """
        ).fetchone()
        if row is None:
            return None
        step_id = UUID(str(row[0]))
        run_id = UUID(str(row[1]))
        step_key = str(row[2])
        fence_token = int(row[3]) + 1
        max_attempts = int(row[4])
        effect_class = str(row[5])
        attempt_no = int(row[6]) + 1
        if attempt_no > max_attempts:
            raise RuntimeStateConflictError(
                f"Step {step_id} is READY after exhausting its retry budget"
            )
        attempt_row = self._connection.execute(
            """
            INSERT INTO mra.runtime_attempt (
                attempt_id, step_id, attempt_no, fence_token, lease_owner,
                lease_acquired_at, lease_until, last_heartbeat_at, state,
                external_effect_class
            )
            VALUES (
                %s, %s, %s, %s, %s,
                clock_timestamp(),
                clock_timestamp() + (%s * interval '1 millisecond'),
                clock_timestamp(), 'CLAIMED', %s
            )
            RETURNING lease_until
            """,
            (
                attempt_id,
                step_id,
                attempt_no,
                fence_token,
                worker_id,
                lease_ms,
                effect_class,
            ),
        ).fetchone()
        updated = self._connection.execute(
            """
            UPDATE mra.runtime_step
            SET state = 'CLAIMED', current_fence = %s,
                current_attempt_id = %s, version = version + 1
            WHERE step_id = %s AND state = 'READY'
            RETURNING step_id
            """,
            (fence_token, attempt_id, step_id),
        ).fetchone()
        if updated is None or attempt_row is None:
            raise RuntimeStateConflictError(f"Step {step_id} claim lost a state race")
        return AttemptClaim(
            attempt_id=attempt_id,
            run_id=run_id,
            step_id=step_id,
            step_key=step_key,
            attempt_no=attempt_no,
            fence_token=fence_token,
            lease_owner=worker_id,
            lease_until=attempt_row[0],
        )

    def start_attempt(self, claim: AttemptClaim) -> int:
        self._lock_live_claim(claim, required_attempt_state="CLAIMED")
        attempt = self._connection.execute(
            """
            UPDATE mra.runtime_attempt
            SET state = 'RUNNING', started_at = clock_timestamp()
            WHERE attempt_id = %s AND state = 'CLAIMED'
              AND lease_until > clock_timestamp()
            RETURNING attempt_no
            """,
            (claim.attempt_id,),
        ).fetchone()
        step = self._connection.execute(
            """
            UPDATE mra.runtime_step
            SET state = 'RUNNING', started_at = clock_timestamp(), version = version + 1
            WHERE step_id = %s AND state = 'CLAIMED'
              AND current_attempt_id = %s AND current_fence = %s
            RETURNING version
            """,
            (claim.step_id, claim.attempt_id, claim.fence_token),
        ).fetchone()
        if attempt is None or step is None:
            raise StaleFenceError(f"Attempt {claim.attempt_id} no longer owns its Step")
        return int(step[0])

    def load_claim(self, attempt_id: UUID) -> AttemptClaim:
        row = self._connection.execute(
            """
            SELECT attempt.attempt_id, step.run_id, step.step_id, step.step_key,
                   attempt.attempt_no, attempt.fence_token, attempt.lease_owner,
                   attempt.lease_until
            FROM mra.runtime_attempt AS attempt
            JOIN mra.runtime_step AS step ON step.step_id = attempt.step_id
            WHERE attempt.attempt_id = %s
            """,
            (attempt_id,),
        ).fetchone()
        if row is None:
            raise RuntimeNotFoundError(f"Attempt {attempt_id} does not exist")
        return AttemptClaim(
            attempt_id=UUID(str(row[0])),
            run_id=UUID(str(row[1])),
            step_id=UUID(str(row[2])),
            step_key=str(row[3]),
            attempt_no=int(row[4]),
            fence_token=int(row[5]),
            lease_owner=str(row[6]),
            lease_until=row[7],
        )

    def heartbeat_attempt(
        self,
        claim: AttemptClaim,
        lease_duration: timedelta,
    ) -> Any:
        lease_ms = _lease_milliseconds(lease_duration)
        self._lock_live_claim(claim, required_attempt_state=None)
        row = self._connection.execute(
            """
            UPDATE mra.runtime_attempt
            SET last_heartbeat_at = clock_timestamp(),
                lease_until = GREATEST(
                    lease_until + interval '1 microsecond',
                    clock_timestamp() + (%s * interval '1 millisecond')
                )
            WHERE attempt_id = %s
              AND state IN ('CLAIMED', 'RUNNING')
              AND lease_until > clock_timestamp()
            RETURNING lease_until
            """,
            (lease_ms, claim.attempt_id),
        ).fetchone()
        if row is None:
            raise StaleFenceError(f"Attempt {claim.attempt_id} lease is no longer live")
        return row[0]

    def lock_live_claim(self, claim: AttemptClaim) -> None:
        """Acquire the global Run/Step/Attempt locks before business aggregates."""

        self._lock_live_claim(claim, required_attempt_state="RUNNING")

    def succeed_attempt(
        self,
        claim: AttemptClaim,
        *,
        receipt_id: UUID,
        result_hash: str,
    ) -> tuple[int, int]:
        self._lock_live_claim(claim, required_attempt_state="RUNNING")
        attempt = self._connection.execute(
            """
            UPDATE mra.runtime_attempt
            SET state = 'SUCCEEDED', result_receipt_id = %s,
                result_hash = %s, finished_at = clock_timestamp()
            WHERE attempt_id = %s AND state = 'RUNNING'
              AND lease_until > clock_timestamp()
            RETURNING attempt_no
            """,
            (receipt_id, result_hash, claim.attempt_id),
        ).fetchone()
        step = self._connection.execute(
            """
            UPDATE mra.runtime_step
            SET state = 'SUCCEEDED', current_attempt_id = NULL,
                finished_at = clock_timestamp(), version = version + 1
            WHERE step_id = %s AND state = 'RUNNING'
              AND current_attempt_id = %s AND current_fence = %s
            RETURNING version
            """,
            (claim.step_id, claim.attempt_id, claim.fence_token),
        ).fetchone()
        if attempt is None or step is None:
            raise StaleFenceError(f"Attempt {claim.attempt_id} cannot finalize")
        self._release_ready_successors(claim.run_id)
        run_version = self._finish_run_if_complete(claim.run_id)
        return int(step[0]), run_version

    def fail_attempt(
        self,
        claim: AttemptClaim,
        *,
        receipt_id: UUID,
        error_class: str,
        error_code: str,
    ) -> tuple[str, int, int]:
        row = self._lock_live_claim(claim, required_attempt_state="RUNNING")
        attempt_no = int(row[5])
        max_attempts = int(row[6])
        effect_class = str(row[7])
        retryable_codes = tuple(str(item) for item in row[8])
        backoff_ms = tuple(int(item) for item in row[9])
        if effect_class in _REMOTE_EFFECTS:
            attempt_state = "RECONCILIATION_REQUIRED"
            step_state = "WAITING"
            outcome = "RECONCILIATION_REQUIRED"
        elif error_code in retryable_codes and attempt_no < max_attempts:
            attempt_state = "FAILED_RETRYABLE"
            step_state = "READY"
            outcome = "RETRY_READY"
        else:
            attempt_state = "FAILED_TERMINAL"
            step_state = "FAILED"
            outcome = "FAILED"
        self._connection.execute(
            """
            UPDATE mra.runtime_attempt
            SET state = %s, error_class = %s, error_code = %s,
                result_receipt_id = %s, finished_at = clock_timestamp()
            WHERE attempt_id = %s
            """,
            (attempt_state, error_class, error_code, receipt_id, claim.attempt_id),
        )
        if step_state == "READY":
            delay = backoff_ms[attempt_no - 1] if attempt_no - 1 < len(backoff_ms) else 0
            step = self._connection.execute(
                """
                UPDATE mra.runtime_step
                SET state = 'READY', current_attempt_id = NULL,
                    ready_at = clock_timestamp() + (%s * interval '1 millisecond'),
                    version = version + 1
                WHERE step_id = %s AND current_attempt_id = %s AND current_fence = %s
                RETURNING version
                """,
                (delay, claim.step_id, claim.attempt_id, claim.fence_token),
            ).fetchone()
        else:
            terminal_reason_code = (
                "EXTERNAL_EFFECT_UNKNOWN"
                if step_state == "WAITING"
                else error_code
            )
            step = self._connection.execute(
                """
                UPDATE mra.runtime_step
                SET state = %s, current_attempt_id = NULL,
                    terminal_reason_code = %s,
                    finished_at = CASE WHEN %s = 'FAILED' THEN clock_timestamp() ELSE NULL END,
                    version = version + 1
                WHERE step_id = %s AND current_attempt_id = %s AND current_fence = %s
                RETURNING version
                """,
                (
                    step_state,
                    terminal_reason_code,
                    step_state,
                    claim.step_id,
                    claim.attempt_id,
                    claim.fence_token,
                ),
            ).fetchone()
        if step is None:
            raise StaleFenceError(f"Attempt {claim.attempt_id} cannot fail its Step")
        if step_state == "WAITING":
            run = self._connection.execute(
                """
                UPDATE mra.runtime_run
                SET state = 'WAITING', terminal_reason_code = %s, version = version + 1
                WHERE run_id = %s AND state = 'RUNNING'
                RETURNING version
                """,
                ("EXTERNAL_EFFECT_UNKNOWN", claim.run_id),
            ).fetchone()
        elif step_state == "FAILED":
            run = self._connection.execute(
                """
                UPDATE mra.runtime_run
                SET state = 'FAILED', terminal_reason_code = %s,
                    finished_at = clock_timestamp(), version = version + 1
                WHERE run_id = %s AND state = 'RUNNING'
                RETURNING version
                """,
                (error_code, claim.run_id),
            ).fetchone()
        else:
            run = self._connection.execute(
                "SELECT version FROM mra.runtime_run WHERE run_id = %s",
                (claim.run_id,),
            ).fetchone()
        if run is None:
            raise RuntimeStateConflictError(f"Run {claim.run_id} could not accept failure")
        return outcome, int(step[0]), int(run[0])

    def expired_attempt_ids(self) -> tuple[UUID, ...]:
        rows = self._connection.execute(
            """
            SELECT attempt.attempt_id
            FROM mra.runtime_attempt AS attempt
            JOIN mra.runtime_step AS step ON step.step_id = attempt.step_id
            JOIN mra.runtime_run AS run ON run.run_id = step.run_id
            WHERE attempt.state IN ('CLAIMED', 'RUNNING')
              AND attempt.lease_until <= clock_timestamp()
              AND step.current_attempt_id = attempt.attempt_id
              AND step.current_fence = attempt.fence_token
              AND run.state = 'RUNNING'
            ORDER BY attempt.lease_until, attempt.attempt_id
            """
        ).fetchall()
        return tuple(UUID(str(row[0])) for row in rows)

    def deadline_expired_step_ids(self) -> tuple[UUID, ...]:
        rows = self._connection.execute(
            """
            SELECT step.step_id
            FROM mra.runtime_step AS step
            JOIN mra.runtime_run AS run ON run.run_id = step.run_id
            WHERE run.state = 'RUNNING'
              AND step.state IN ('PENDING', 'READY')
              AND step.deadline_at <= clock_timestamp()
              AND NOT EXISTS (
                  SELECT 1
                  FROM mra.runtime_step AS live_step
                  WHERE live_step.run_id = run.run_id
                    AND live_step.state IN ('CLAIMED', 'RUNNING')
              )
            ORDER BY step.deadline_at, step.step_id
            """
        ).fetchall()
        return tuple(UUID(str(row[0])) for row in rows)

    def recover_expired_attempt(
        self, attempt_id: UUID, *, receipt_id: UUID
    ) -> RecoveryDecision | None:
        row = self._connection.execute(
            """
            SELECT
                run.run_id, run.state, run.version,
                step.step_id, step.state, step.version, step.max_attempts,
                step.current_attempt_id, step.current_fence,
                attempt.state, attempt.attempt_no, attempt.fence_token,
                attempt.external_effect_class
            FROM mra.runtime_attempt AS attempt
            JOIN mra.runtime_step AS step ON step.step_id = attempt.step_id
            JOIN mra.runtime_run AS run ON run.run_id = step.run_id
            WHERE attempt.attempt_id = %s
            FOR UPDATE OF run, step, attempt
            """,
            (attempt_id,),
        ).fetchone()
        if row is None:
            return None
        if (
            row[1] != "RUNNING"
            or row[9] not in ("CLAIMED", "RUNNING")
            or row[7] != attempt_id
            or int(row[8]) != int(row[11])
        ):
            return None
        expired = self._connection.execute(
            "SELECT lease_until <= clock_timestamp() FROM mra.runtime_attempt WHERE attempt_id = %s",
            (attempt_id,),
        ).fetchone()
        if not expired or not expired[0]:
            return None
        run_id = UUID(str(row[0]))
        step_id = UUID(str(row[3]))
        attempt_state = str(row[9])
        attempt_no = int(row[10])
        fence_token = int(row[11])
        effect_class = str(row[12])
        reconcile = attempt_state == "RUNNING" and effect_class in _REMOTE_EFFECTS
        if reconcile:
            new_attempt_state = "RECONCILIATION_REQUIRED"
            new_step_state = "WAITING"
            outcome = "RECONCILIATION_REQUIRED"
        elif attempt_no < int(row[6]):
            new_attempt_state = "ABANDONED"
            new_step_state = "READY"
            outcome = "RETRY_READY"
        else:
            new_attempt_state = "ABANDONED"
            new_step_state = "FAILED"
            outcome = "FAILED"
        self._connection.execute(
            """
            UPDATE mra.runtime_attempt
            SET state = %s, error_class = 'LEASE', error_code = 'LEASE_EXPIRED',
                result_receipt_id = %s, finished_at = clock_timestamp()
            WHERE attempt_id = %s
            """,
            (new_attempt_state, receipt_id, attempt_id),
        )
        if new_step_state == "READY":
            step_row = self._connection.execute(
                """
                UPDATE mra.runtime_step
                SET state = 'READY', current_attempt_id = NULL,
                    ready_at = clock_timestamp(), version = version + 1
                WHERE step_id = %s
                RETURNING version
                """,
                (step_id,),
            ).fetchone()
            run_row = self._connection.execute(
                "SELECT version FROM mra.runtime_run WHERE run_id = %s",
                (run_id,),
            ).fetchone()
        elif new_step_state == "WAITING":
            step_row = self._connection.execute(
                """
                UPDATE mra.runtime_step
                SET state = 'WAITING', current_attempt_id = NULL,
                    terminal_reason_code = 'EXTERNAL_EFFECT_UNKNOWN',
                    version = version + 1
                WHERE step_id = %s
                RETURNING version
                """,
                (step_id,),
            ).fetchone()
            run_row = self._connection.execute(
                """
                UPDATE mra.runtime_run
                SET state = 'WAITING', terminal_reason_code = 'EXTERNAL_EFFECT_UNKNOWN',
                    version = version + 1
                WHERE run_id = %s AND state = 'RUNNING'
                RETURNING version
                """,
                (run_id,),
            ).fetchone()
        else:
            step_row = self._connection.execute(
                """
                UPDATE mra.runtime_step
                SET state = 'FAILED', current_attempt_id = NULL,
                    terminal_reason_code = 'RETRY_BUDGET_EXHAUSTED',
                    finished_at = clock_timestamp(), version = version + 1
                WHERE step_id = %s
                RETURNING version
                """,
                (step_id,),
            ).fetchone()
            run_row = self._connection.execute(
                """
                UPDATE mra.runtime_run
                SET state = 'FAILED', terminal_reason_code = 'RETRY_BUDGET_EXHAUSTED',
                    finished_at = clock_timestamp(), version = version + 1
                WHERE run_id = %s AND state = 'RUNNING'
                RETURNING version
                """,
                (run_id,),
            ).fetchone()
        if step_row is None or run_row is None:
            raise RuntimeStateConflictError("recovery lost the locked Runtime state")
        return RecoveryDecision(
            attempt_id=attempt_id,
            run_id=run_id,
            step_id=step_id,
            fence_token=fence_token,
            outcome=outcome,
            attempt_version=attempt_no,
            step_version=int(step_row[0]),
            run_version=int(run_row[0]),
        )

    def expire_step_deadline(
        self,
        step_id: UUID,
        *,
        attempt_id: UUID,
        receipt_id: UUID,
        lease_owner: str,
    ) -> RecoveryDecision | None:
        row = self._connection.execute(
            """
            SELECT run.run_id, run.state, step.state, step.version,
                   step.current_fence, step.max_attempts,
                   step.external_effect_class,
                   COALESCE((
                       SELECT max(attempt.attempt_no)
                       FROM mra.runtime_attempt AS attempt
                       WHERE attempt.step_id = step.step_id
                   ), 0) AS prior_attempts
            FROM mra.runtime_step AS step
            JOIN mra.runtime_run AS run ON run.run_id = step.run_id
            WHERE step.step_id = %s
              AND run.state = 'RUNNING'
              AND step.state IN ('PENDING', 'READY')
              AND step.deadline_at <= clock_timestamp()
              AND NOT EXISTS (
                  SELECT 1
                  FROM mra.runtime_step AS live_step
                  WHERE live_step.run_id = run.run_id
                    AND live_step.state IN ('CLAIMED', 'RUNNING')
              )
            FOR UPDATE OF run, step
            """,
            (step_id,),
        ).fetchone()
        if row is None:
            return None
        run_id = UUID(str(row[0]))
        step_state = str(row[2])
        fence_token = int(row[4]) + 1
        max_attempts = int(row[5])
        effect_class = str(row[6])
        attempt_no = int(row[7]) + 1
        if attempt_no > max_attempts:
            raise RuntimeStateConflictError(
                f"Step {step_id} exhausted attempts before deadline recovery"
            )
        if step_state == "PENDING":
            made_ready = self._connection.execute(
                """
                UPDATE mra.runtime_step
                SET state = 'READY', ready_at = clock_timestamp(), version = version + 1
                WHERE step_id = %s AND state = 'PENDING'
                RETURNING step_id
                """,
                (step_id,),
            ).fetchone()
            if made_ready is None:
                raise RuntimeStateConflictError("deadline recovery could not ready Step")
        self._connection.execute(
            """
            INSERT INTO mra.runtime_attempt (
                attempt_id, step_id, attempt_no, fence_token, lease_owner,
                lease_acquired_at, lease_until, last_heartbeat_at, state,
                external_effect_class
            )
            VALUES (
                %s, %s, %s, %s, %s, clock_timestamp(),
                clock_timestamp() + interval '1 second', clock_timestamp(),
                'CLAIMED', %s
            )
            """,
            (
                attempt_id,
                step_id,
                attempt_no,
                fence_token,
                lease_owner,
                effect_class,
            ),
        )
        claimed = self._connection.execute(
            """
            UPDATE mra.runtime_step
            SET state = 'CLAIMED', current_fence = %s,
                current_attempt_id = %s, version = version + 1
            WHERE step_id = %s AND state = 'READY'
            RETURNING step_id
            """,
            (fence_token, attempt_id, step_id),
        ).fetchone()
        if claimed is None:
            raise RuntimeStateConflictError("deadline recovery could not claim Step")
        self._connection.execute(
            """
            UPDATE mra.runtime_attempt
            SET state = 'RUNNING', started_at = clock_timestamp()
            WHERE attempt_id = %s AND state = 'CLAIMED'
            """,
            (attempt_id,),
        )
        self._connection.execute(
            """
            UPDATE mra.runtime_step
            SET state = 'RUNNING', started_at = clock_timestamp(), version = version + 1
            WHERE step_id = %s AND state = 'CLAIMED'
              AND current_attempt_id = %s AND current_fence = %s
            """,
            (step_id, attempt_id, fence_token),
        )
        self._connection.execute(
            """
            UPDATE mra.runtime_attempt
            SET state = 'FAILED_TERMINAL', error_class = 'RUNTIME',
                error_code = 'DEADLINE_EXHAUSTED', result_receipt_id = %s,
                finished_at = clock_timestamp()
            WHERE attempt_id = %s AND state = 'RUNNING'
            """,
            (receipt_id, attempt_id),
        )
        step = self._connection.execute(
            """
            UPDATE mra.runtime_step
            SET state = 'FAILED', current_attempt_id = NULL,
                terminal_reason_code = 'DEADLINE_EXHAUSTED',
                finished_at = clock_timestamp(), version = version + 1
            WHERE step_id = %s AND state = 'RUNNING'
              AND current_attempt_id = %s AND current_fence = %s
            RETURNING version
            """,
            (step_id, attempt_id, fence_token),
        ).fetchone()
        run = self._connection.execute(
            """
            UPDATE mra.runtime_run
            SET state = 'FAILED', terminal_reason_code = 'DEADLINE_EXHAUSTED',
                finished_at = clock_timestamp(), version = version + 1
            WHERE run_id = %s AND state = 'RUNNING'
            RETURNING version
            """,
            (run_id,),
        ).fetchone()
        if step is None or run is None:
            raise RuntimeStateConflictError("deadline recovery lost locked Runtime state")
        return RecoveryDecision(
            attempt_id=attempt_id,
            run_id=run_id,
            step_id=step_id,
            fence_token=fence_token,
            outcome="FAILED",
            attempt_version=attempt_no,
            step_version=int(step[0]),
            run_version=int(run[0]),
        )

    def resume_waiting_step(
        self,
        *,
        run_id: UUID,
        step_id: UUID,
        resolution_code: str,
    ) -> tuple[int, int]:
        row = self._connection.execute(
            """
            SELECT run.state, step.state
            FROM mra.runtime_run AS run
            JOIN mra.runtime_step AS step ON step.run_id = run.run_id
            WHERE run.run_id = %s AND step.step_id = %s
            FOR UPDATE OF run, step
            """,
            (run_id, step_id),
        ).fetchone()
        if row is None:
            raise RuntimeNotFoundError("Run or Step does not exist")
        if row != ("WAITING", "WAITING"):
            raise RuntimeStateConflictError(
                f"resume requires WAITING Run/Step, found {row!r}"
            )
        step = self._connection.execute(
            """
            UPDATE mra.runtime_step
            SET state = 'READY', ready_at = clock_timestamp(),
                terminal_reason_code = NULL, version = version + 1
            WHERE step_id = %s
            RETURNING version
            """,
            (step_id,),
        ).fetchone()
        run = self._connection.execute(
            """
            UPDATE mra.runtime_run
            SET state = 'RUNNING', terminal_reason_code = NULL, version = version + 1
            WHERE run_id = %s
            RETURNING version
            """,
            (run_id,),
        ).fetchone()
        if step is None or run is None:
            raise RuntimeStateConflictError(
                f"resolution {resolution_code} could not resume locked Runtime state"
            )
        return int(step[0]), int(run[0])

    def inspect_run(self, run_id: UUID) -> RunTrace:
        run = self._connection.execute(
            "SELECT state, version FROM mra.runtime_run WHERE run_id = %s",
            (run_id,),
        ).fetchone()
        if run is None:
            raise RuntimeNotFoundError(f"Run {run_id} does not exist")
        rows = self._connection.execute(
            """
            SELECT step.step_id, step.step_key, step.state, step.current_fence,
                   step.current_attempt_id,
                   COALESCE(array_agg(attempt.state ORDER BY attempt.attempt_no)
                            FILTER (WHERE attempt.attempt_id IS NOT NULL), ARRAY[]::text[])
            FROM mra.runtime_step AS step
            LEFT JOIN mra.runtime_attempt AS attempt ON attempt.step_id = step.step_id
            WHERE step.run_id = %s
            GROUP BY step.step_id
            ORDER BY step.ordinal
            """,
            (run_id,),
        ).fetchall()
        return RunTrace(
            run_id=run_id,
            run_state=str(run[0]),
            version=int(run[1]),
            steps=tuple(
                StepTrace(
                    step_id=UUID(str(row[0])),
                    step_key=str(row[1]),
                    state=str(row[2]),
                    current_fence=int(row[3]),
                    current_attempt_id=UUID(str(row[4])) if row[4] is not None else None,
                    attempt_states=tuple(str(item) for item in row[5]),
                )
                for row in rows
            ),
        )

    def _lock_live_claim(
        self,
        claim: AttemptClaim,
        *,
        required_attempt_state: str | None,
    ) -> tuple[Any, ...]:
        row = self._connection.execute(
            """
            SELECT
                run.run_id, run.state, step.step_id, step.state,
                attempt.attempt_id, attempt.attempt_no, step.max_attempts,
                attempt.external_effect_class, step.retryable_error_codes,
                step.retry_backoff_ms, attempt.state, attempt.fence_token,
                attempt.lease_owner, attempt.lease_until,
                step.current_attempt_id, step.current_fence
            FROM mra.runtime_run AS run
            JOIN mra.runtime_step AS step ON step.run_id = run.run_id
            JOIN mra.runtime_attempt AS attempt ON attempt.step_id = step.step_id
            WHERE attempt.attempt_id = %s
            FOR UPDATE OF run, step, attempt
            """,
            (claim.attempt_id,),
        ).fetchone()
        expected_attempt_states = (
            (required_attempt_state,)
            if required_attempt_state is not None
            else ("CLAIMED", "RUNNING")
        )
        if (
            row is None
            or UUID(str(row[0])) != claim.run_id
            or row[1] != "RUNNING"
            or UUID(str(row[2])) != claim.step_id
            or UUID(str(row[4])) != claim.attempt_id
            or row[10] not in expected_attempt_states
            or int(row[11]) != claim.fence_token
            or row[12] != claim.lease_owner
            or UUID(str(row[14])) != claim.attempt_id
            or int(row[15]) != claim.fence_token
        ):
            raise StaleFenceError(
                f"Attempt {claim.attempt_id} does not own the current live fence"
            )
        live = self._connection.execute(
            "SELECT lease_until > clock_timestamp() FROM mra.runtime_attempt WHERE attempt_id = %s",
            (claim.attempt_id,),
        ).fetchone()
        if live is None or not live[0]:
            raise StaleFenceError(f"Attempt {claim.attempt_id} lease expired")
        return tuple(row)

    def _release_ready_successors(self, run_id: UUID) -> None:
        self._connection.execute(
            """
            UPDATE mra.runtime_step AS step
            SET state = 'READY', ready_at = clock_timestamp(), version = version + 1
            WHERE step.run_id = %s
              AND step.state = 'PENDING'
              AND EXISTS (
                  SELECT 1 FROM mra.runtime_step_dependency AS dependency
                  WHERE dependency.run_id = step.run_id
                    AND dependency.successor_step_id = step.step_id
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM mra.runtime_step_dependency AS dependency
                  JOIN mra.runtime_step AS predecessor
                    ON predecessor.step_id = dependency.predecessor_step_id
                  WHERE dependency.run_id = step.run_id
                    AND dependency.successor_step_id = step.step_id
                    AND (
                        (dependency.dependency_kind = 'REQUIRED_SUCCESS'
                         AND predecessor.state NOT IN ('SUCCEEDED', 'SKIPPED'))
                        OR
                        (dependency.dependency_kind = 'TERMINAL'
                         AND predecessor.state NOT IN ('SUCCEEDED', 'BLOCKED', 'FAILED', 'CANCELLED', 'SKIPPED'))
                    )
              )
            """,
            (run_id,),
        )

    def _finish_run_if_complete(self, run_id: UUID) -> int:
        row = self._connection.execute(
            """
            SELECT version,
                   NOT EXISTS (
                       SELECT 1 FROM mra.runtime_step
                       WHERE run_id = %s
                         AND state NOT IN ('SUCCEEDED', 'BLOCKED', 'FAILED', 'CANCELLED', 'SKIPPED')
                   ) AS all_terminal,
                   NOT EXISTS (
                       SELECT 1 FROM mra.runtime_step
                       WHERE run_id = %s AND required
                         AND state NOT IN ('SUCCEEDED', 'SKIPPED')
                   ) AS required_succeeded
            FROM mra.runtime_run
            WHERE run_id = %s
            FOR UPDATE
            """,
            (run_id, run_id, run_id),
        ).fetchone()
        if row is None:
            raise RuntimeNotFoundError(f"Run {run_id} does not exist")
        if row[1] and row[2]:
            finished = self._connection.execute(
                """
                UPDATE mra.runtime_run
                SET state = 'SUCCEEDED', finished_at = clock_timestamp(), version = version + 1
                WHERE run_id = %s AND state = 'RUNNING'
                RETURNING version
                """,
                (run_id,),
            ).fetchone()
            if finished is None:
                raise RuntimeStateConflictError(f"Run {run_id} could not finalize")
            return int(finished[0])
        return int(row[0])


class PostgresCommandReceiptRepository:
    def __init__(self, connection: psycopg.Connection[Any]) -> None:
        self._connection = connection

    def start(
        self,
        *,
        receipt_id: UUID,
        command_kind: str,
        scope_id: str,
        idempotency_key: str,
        request_hash: str,
    ) -> ReceiptRecord:
        row = self._connection.execute(
            """
            INSERT INTO mra.command_receipt (
                receipt_id, command_kind, scope_id, idempotency_key,
                request_hash, status
            )
            VALUES (%s, %s, %s, %s, %s, 'PENDING')
            ON CONFLICT (command_kind, scope_id, idempotency_key) DO NOTHING
            RETURNING receipt_id, status, request_hash,
                      result_aggregate_kind, result_aggregate_id,
                      result_aggregate_version, result_hash, error_code
            """,
            (receipt_id, command_kind, scope_id, idempotency_key, request_hash),
        ).fetchone()
        is_new = row is not None
        if row is None:
            row = self._connection.execute(
                """
                SELECT receipt_id, status, request_hash,
                       result_aggregate_kind, result_aggregate_id,
                       result_aggregate_version, result_hash, error_code
                FROM mra.command_receipt
                WHERE command_kind = %s AND scope_id = %s AND idempotency_key = %s
                FOR UPDATE
                """,
                (command_kind, scope_id, idempotency_key),
            ).fetchone()
        if row is None:
            raise RuntimeStateConflictError("idempotency conflict row disappeared")
        if str(row[2]) != request_hash:
            raise IdempotencyKeyReusedError(
                f"{command_kind}/{scope_id}/{idempotency_key} has a different request hash"
            )
        if not is_new and row[1] == "PENDING":
            raise CommandInProgressError(
                f"{command_kind}/{scope_id}/{idempotency_key} is still pending"
            )
        return ReceiptRecord(
            receipt_id=UUID(str(row[0])),
            status=str(row[1]),
            request_hash=str(row[2]),
            result_aggregate_kind=str(row[3]) if row[3] is not None else None,
            result_aggregate_id=str(row[4]) if row[4] is not None else None,
            result_aggregate_version=int(row[5]) if row[5] is not None else None,
            result_hash=str(row[6]) if row[6] is not None else None,
            error_code=str(row[7]) if row[7] is not None else None,
            is_new=is_new,
        )

    def succeed(
        self,
        *,
        receipt_id: UUID,
        aggregate_kind: str,
        aggregate_id: str,
        aggregate_version: int,
        result_hash: str,
        runtime_claim: AttemptClaim | None = None,
    ) -> None:
        row = self._connection.execute(
            """
            UPDATE mra.command_receipt
            SET status = 'SUCCEEDED',
                runtime_step_id = %s,
                runtime_attempt_id = %s,
                fence_token = %s,
                result_aggregate_kind = %s,
                result_aggregate_id = %s,
                result_aggregate_version = %s,
                result_hash = %s,
                completed_at = clock_timestamp()
            WHERE receipt_id = %s AND status = 'PENDING'
            RETURNING receipt_id
            """,
            (
                runtime_claim.step_id if runtime_claim else None,
                runtime_claim.attempt_id if runtime_claim else None,
                runtime_claim.fence_token if runtime_claim else None,
                aggregate_kind,
                aggregate_id,
                aggregate_version,
                result_hash,
                receipt_id,
            ),
        ).fetchone()
        if row is None:
            raise RuntimeStateConflictError(f"Receipt {receipt_id} is not pending")

    def fail(
        self,
        *,
        receipt_id: UUID,
        error_code: str,
        runtime_claim: AttemptClaim | None = None,
    ) -> None:
        row = self._connection.execute(
            """
            UPDATE mra.command_receipt
            SET status = 'FAILED',
                runtime_step_id = %s,
                runtime_attempt_id = %s,
                fence_token = %s,
                error_code = %s,
                completed_at = clock_timestamp()
            WHERE receipt_id = %s AND status = 'PENDING'
            RETURNING receipt_id
            """,
            (
                runtime_claim.step_id if runtime_claim else None,
                runtime_claim.attempt_id if runtime_claim else None,
                runtime_claim.fence_token if runtime_claim else None,
                error_code,
                receipt_id,
            ),
        ).fetchone()
        if row is None:
            raise RuntimeStateConflictError(f"Receipt {receipt_id} is not pending")


class PostgresAuditRepository:
    def __init__(self, connection: psycopg.Connection[Any]) -> None:
        self._connection = connection

    def append(
        self,
        *,
        audit_event_id: UUID,
        receipt_id: UUID | None,
        actor_type: str,
        actor_id: str,
        aggregate_kind: str,
        aggregate_id: str,
        action: str,
        reason_code: str,
        before_version: int | None,
        after_version: int | None,
        runtime_claim: AttemptClaim | None = None,
    ) -> None:
        self._connection.execute(
            """
            INSERT INTO mra.audit_event (
                audit_event_id, command_receipt_id, runtime_step_id,
                fence_token, actor_type, actor_id, aggregate_kind,
                aggregate_id, action, reason_code, event_at,
                before_version, after_version
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    clock_timestamp(), %s, %s)
            """,
            (
                audit_event_id,
                receipt_id,
                runtime_claim.step_id if runtime_claim else None,
                runtime_claim.fence_token if runtime_claim else None,
                actor_type,
                actor_id,
                aggregate_kind,
                aggregate_id,
                action,
                reason_code,
                before_version,
                after_version,
            ),
        )


def _lease_milliseconds(duration: timedelta) -> int:
    milliseconds = int(duration.total_seconds() * 1_000)
    if duration <= timedelta(0) or milliseconds <= 0:
        raise ValueError("lease_duration must be at least one millisecond")
    if duration > timedelta(days=1):
        raise ValueError("lease_duration cannot exceed one day")
    return milliseconds


__all__ = [
    "PostgresAuditRepository",
    "PostgresCommandReceiptRepository",
    "PostgresRuntimeRepository",
]
