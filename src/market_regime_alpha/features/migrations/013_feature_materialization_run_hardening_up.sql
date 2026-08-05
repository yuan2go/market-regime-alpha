PRAGMA foreign_keys=OFF;

BEGIN IMMEDIATE;

CREATE TABLE IF NOT EXISTS feature_materialization_schema_migration (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE feature_materialization_run_013 (
    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    schema_version TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    command_hash TEXT NOT NULL CHECK (
        length(command_hash) = 71
        AND substr(command_hash, 1, 7) = 'sha256:'
        AND substr(command_hash, 8) NOT GLOB '*[^0-9a-f]*'
    ),
    status TEXT NOT NULL CHECK (status IN ('RUNNING', 'FAILED', 'COMPLETE')),
    version INTEGER NOT NULL CHECK (version >= 1),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

INSERT INTO feature_materialization_run_013
SELECT run_id, schema_version, idempotency_key, command_hash, status, version,
       created_at, updated_at
FROM feature_materialization_run;

CREATE TABLE feature_materialization_task_013 (
    run_id INTEGER NOT NULL,
    task_key TEXT NOT NULL,
    symbol TEXT NOT NULL,
    feature_id TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('PENDING', 'IN_PROGRESS', 'FAILED', 'COMPLETE')
    ),
    version INTEGER NOT NULL CHECK (version >= 1),
    claim_token TEXT,
    claim_epoch INTEGER NOT NULL DEFAULT 0 CHECK (claim_epoch >= 0),
    claimed_at TEXT,
    lease_acquired_at TEXT,
    lease_expires_at TEXT,
    heartbeat_at TEXT,
    artifact_id TEXT,
    artifact_hash TEXT CHECK (
        artifact_hash IS NULL OR (
            length(artifact_hash) = 71
            AND substr(artifact_hash, 1, 7) = 'sha256:'
            AND substr(artifact_hash, 8) NOT GLOB '*[^0-9a-f]*'
        )
    ),
    last_error TEXT,
    PRIMARY KEY(run_id, task_key),
    FOREIGN KEY(run_id) REFERENCES feature_materialization_run_013(run_id),
    CHECK (
        (
            status = 'IN_PROGRESS'
            AND claim_token IS NOT NULL
            AND claimed_at IS NOT NULL
            AND lease_acquired_at IS NOT NULL
            AND lease_expires_at IS NOT NULL
            AND heartbeat_at IS NOT NULL
            AND claim_epoch >= 1
        ) OR (
            status != 'IN_PROGRESS'
            AND claim_token IS NULL
            AND claimed_at IS NULL
            AND lease_acquired_at IS NULL
            AND lease_expires_at IS NULL
            AND heartbeat_at IS NULL
        )
    ),
    CHECK (
        (status = 'COMPLETE' AND artifact_id IS NOT NULL AND artifact_hash IS NOT NULL)
        OR (status != 'COMPLETE' AND artifact_id IS NULL AND artifact_hash IS NULL)
    )
);

INSERT INTO feature_materialization_task_013 (
    run_id, task_key, symbol, feature_id, timeframe, status, version,
    claim_token, claim_epoch, claimed_at, lease_acquired_at, lease_expires_at,
    heartbeat_at, artifact_id, artifact_hash, last_error
)
SELECT run_id, task_key, symbol, feature_id, timeframe,
       CASE WHEN status = 'IN_PROGRESS' THEN 'FAILED' ELSE status END,
       version + CASE WHEN status = 'IN_PROGRESS' THEN 1 ELSE 0 END,
       NULL, 0, NULL, NULL, NULL, NULL, artifact_id, artifact_hash,
       CASE WHEN status = 'IN_PROGRESS' THEN 'MIGRATION_013_RECOVERED_LEGACY_CLAIM'
            ELSE last_error END
FROM feature_materialization_task;

CREATE TABLE feature_materialization_attempt_013 (
    attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    task_key TEXT NOT NULL,
    attempt_number INTEGER NOT NULL CHECK (attempt_number >= 1),
    claim_token TEXT NOT NULL,
    claim_epoch INTEGER NOT NULL CHECK (claim_epoch >= 1),
    task_version INTEGER NOT NULL CHECK (task_version >= 2),
    started_at TEXT NOT NULL,
    lease_expires_at TEXT NOT NULL,
    heartbeat_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL CHECK (
        status IN ('STARTED', 'COMPLETE', 'FAILED', 'LEASE_EXPIRED')
    ),
    error_message TEXT,
    UNIQUE(run_id, task_key, attempt_number),
    UNIQUE(run_id, task_key, claim_epoch),
    FOREIGN KEY(run_id, task_key)
        REFERENCES feature_materialization_task_013(run_id, task_key),
    CHECK (
        (status = 'STARTED' AND completed_at IS NULL)
        OR (status != 'STARTED' AND completed_at IS NOT NULL)
    )
);

INSERT INTO feature_materialization_attempt_013 (
    attempt_id, run_id, task_key, attempt_number, claim_token, claim_epoch,
    task_version, started_at, lease_expires_at, heartbeat_at, completed_at,
    status, error_message
)
SELECT attempt_id, run_id, task_key, attempt_number, claim_token, attempt_number,
       2, started_at, started_at, started_at,
       COALESCE(completed_at, started_at),
       CASE WHEN status = 'STARTED' THEN 'LEASE_EXPIRED' ELSE status END,
       CASE WHEN status = 'STARTED' THEN 'MIGRATION_013_RECOVERED_LEGACY_CLAIM'
            ELSE error_message END
FROM feature_materialization_attempt;

CREATE TABLE feature_materialization_receipt_013 (
    run_id INTEGER PRIMARY KEY,
    receipt_id TEXT NOT NULL UNIQUE,
    receipt_hash TEXT NOT NULL CHECK (
        length(receipt_hash) = 71
        AND substr(receipt_hash, 1, 7) = 'sha256:'
        AND substr(receipt_hash, 8) NOT GLOB '*[^0-9a-f]*'
    ),
    receipt_json TEXT NOT NULL CHECK (
        json_valid(receipt_json) AND json_type(receipt_json) = 'object'
    ),
    created_at TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES feature_materialization_run_013(run_id)
);

INSERT INTO feature_materialization_receipt_013
SELECT run_id, receipt_id, receipt_hash, receipt_json, created_at
FROM feature_materialization_receipt;

CREATE TABLE feature_materialization_event_013 (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    task_key TEXT,
    event_type TEXT NOT NULL,
    event_time TEXT NOT NULL,
    payload_json TEXT NOT NULL CHECK (
        json_valid(payload_json) AND json_type(payload_json) = 'object'
    ),
    FOREIGN KEY(run_id) REFERENCES feature_materialization_run_013(run_id),
    FOREIGN KEY(run_id, task_key)
        REFERENCES feature_materialization_task_013(run_id, task_key)
);

INSERT INTO feature_materialization_event_013
SELECT event_id, run_id, task_key, event_type, event_time, payload_json
FROM feature_materialization_event;

DROP TABLE feature_materialization_event;
DROP TABLE feature_materialization_receipt;
DROP TABLE feature_materialization_attempt;
DROP TABLE feature_materialization_task;
DROP TABLE feature_materialization_run;

ALTER TABLE feature_materialization_run_013 RENAME TO feature_materialization_run;
ALTER TABLE feature_materialization_task_013 RENAME TO feature_materialization_task;
ALTER TABLE feature_materialization_attempt_013 RENAME TO feature_materialization_attempt;
ALTER TABLE feature_materialization_receipt_013 RENAME TO feature_materialization_receipt;
ALTER TABLE feature_materialization_event_013 RENAME TO feature_materialization_event;

CREATE INDEX feature_materialization_task_claimable_idx
    ON feature_materialization_task(run_id, status, task_key);
CREATE INDEX feature_materialization_task_lease_idx
    ON feature_materialization_task(run_id, status, lease_expires_at);
CREATE INDEX feature_materialization_attempt_task_idx
    ON feature_materialization_attempt(run_id, task_key, attempt_number);
CREATE INDEX feature_materialization_event_run_idx
    ON feature_materialization_event(run_id, event_id);

CREATE TRIGGER feature_materialization_events_no_update
BEFORE UPDATE ON feature_materialization_event
BEGIN
    SELECT RAISE(ABORT, 'Feature materialization events are append-only');
END;

CREATE TRIGGER feature_materialization_events_no_delete
BEFORE DELETE ON feature_materialization_event
BEGIN
    SELECT RAISE(ABORT, 'Feature materialization events are append-only');
END;

CREATE TRIGGER feature_materialization_receipts_no_update
BEFORE UPDATE ON feature_materialization_receipt
BEGIN
    SELECT RAISE(ABORT, 'Feature materialization receipts are immutable');
END;

CREATE TRIGGER feature_materialization_receipts_no_delete
BEFORE DELETE ON feature_materialization_receipt
BEGIN
    SELECT RAISE(ABORT, 'Feature materialization receipts are immutable');
END;

CREATE TRIGGER feature_materialization_attempts_no_delete
BEFORE DELETE ON feature_materialization_attempt
BEGIN
    SELECT RAISE(ABORT, 'Feature materialization attempts are immutable history');
END;

CREATE TRIGGER feature_materialization_settled_attempts_no_update
BEFORE UPDATE ON feature_materialization_attempt
WHEN OLD.status != 'STARTED'
BEGIN
    SELECT RAISE(ABORT, 'Settled Feature materialization attempt is immutable');
END;

CREATE TRIGGER feature_materialization_attempt_transition_guard
BEFORE UPDATE ON feature_materialization_attempt
WHEN OLD.status = 'STARTED' AND NEW.status = 'STARTED' AND (
    NEW.run_id != OLD.run_id
    OR NEW.task_key != OLD.task_key
    OR NEW.attempt_number != OLD.attempt_number
    OR NEW.claim_token != OLD.claim_token
    OR NEW.claim_epoch != OLD.claim_epoch
)
BEGIN
    SELECT RAISE(ABORT, 'Feature materialization attempt identity is immutable');
END;

CREATE TRIGGER feature_materialization_tasks_no_delete
BEFORE DELETE ON feature_materialization_task
BEGIN
    SELECT RAISE(ABORT, 'Feature materialization tasks cannot be deleted');
END;

CREATE TRIGGER feature_materialization_completed_tasks_immutable
BEFORE UPDATE ON feature_materialization_task
WHEN OLD.status = 'COMPLETE'
BEGIN
    SELECT RAISE(ABORT, 'Completed Feature materialization task is immutable');
END;

CREATE TRIGGER feature_materialization_claim_owner_guard
BEFORE UPDATE ON feature_materialization_task
WHEN OLD.status = 'IN_PROGRESS' AND NEW.status = 'IN_PROGRESS' AND (
    NEW.claim_token != OLD.claim_token OR NEW.claim_epoch != OLD.claim_epoch
)
BEGIN
    SELECT RAISE(ABORT, 'Active Feature materialization claim owner cannot be overwritten');
END;

CREATE TRIGGER feature_materialization_runs_no_delete
BEFORE DELETE ON feature_materialization_run
BEGIN
    SELECT RAISE(ABORT, 'Feature materialization runs cannot be deleted');
END;

CREATE TRIGGER feature_materialization_run_identity_immutable
BEFORE UPDATE ON feature_materialization_run
WHEN NEW.schema_version != OLD.schema_version
    OR NEW.idempotency_key != OLD.idempotency_key
    OR NEW.command_hash != OLD.command_hash
    OR NEW.created_at != OLD.created_at
BEGIN
    SELECT RAISE(ABORT, 'Feature materialization run command identity is immutable');
END;

INSERT INTO feature_materialization_schema_migration(version, applied_at)
VALUES (13, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));

COMMIT;

PRAGMA foreign_keys=ON;
