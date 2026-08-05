PRAGMA foreign_keys = ON;

BEGIN IMMEDIATE;

CREATE TABLE IF NOT EXISTS controlled_operation_schema_migration (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS controlled_operation_run (
    run_id TEXT PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    command_hash TEXT NOT NULL CHECK (
        length(command_hash) = 71
        AND substr(command_hash, 1, 7) = 'sha256:'
        AND substr(command_hash, 8) NOT GLOB '*[^0-9a-f]*'
    ),
    command_json TEXT NOT NULL CHECK (
        json_valid(command_json) AND json_type(command_json) = 'object'
    ),
    decision_date TEXT NOT NULL CHECK (date(decision_date) = decision_date),
    status TEXT NOT NULL CHECK (status IN (
        'CREATED', 'WAITING_FOR_STATIC_INPUTS', 'STATIC_READY',
        'WAITING_FOR_DECISION_WINDOW', 'DECISION_WINDOW_RUNNING',
        'DATA_BLOCKED', 'DEADLINE_MISSED', 'OUTCOME_PENDING',
        'SETTLED', 'FAILED'
    )),
    current_stage TEXT,
    version INTEGER NOT NULL CHECK (version >= 1),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    settled_at TEXT,
    CHECK (current_stage IS NULL OR current_stage IN (
        'CALENDAR_UNIVERSE_FREEZE', 'DAILY_SOURCE_FREEZE', 'DAILY_DATASET',
        'STATIC_FEATURES', 'OPERATIONAL_RESEARCH', 'CANDIDATE_SET',
        'CANDIDATE_MINUTE_ACQUISITION', 'INTRADAY_DATASET',
        'INTRADAY_FEATURE_OVERLAY', 'SIGNAL', 'PATH_FORECAST',
        'ENTRY_ASSESSMENT', 'OPERATION_PACKAGE', 'OUTCOME_SETTLEMENT'
    )),
    CHECK ((status = 'SETTLED') = (settled_at IS NOT NULL))
);

CREATE TABLE IF NOT EXISTS controlled_operation_stage (
    run_id TEXT NOT NULL,
    stage_name TEXT NOT NULL CHECK (stage_name IN (
        'CALENDAR_UNIVERSE_FREEZE', 'DAILY_SOURCE_FREEZE', 'DAILY_DATASET',
        'STATIC_FEATURES', 'OPERATIONAL_RESEARCH', 'CANDIDATE_SET',
        'CANDIDATE_MINUTE_ACQUISITION', 'INTRADAY_DATASET',
        'INTRADAY_FEATURE_OVERLAY', 'SIGNAL', 'PATH_FORECAST',
        'ENTRY_ASSESSMENT', 'OPERATION_PACKAGE', 'OUTCOME_SETTLEMENT'
    )),
    status TEXT NOT NULL CHECK (status IN (
        'PENDING', 'IN_PROGRESS', 'FAILED', 'COMPLETED'
    )),
    version INTEGER NOT NULL CHECK (version >= 1),
    claim_id TEXT,
    claim_epoch INTEGER NOT NULL DEFAULT 0 CHECK (claim_epoch >= 0),
    lease_acquired_at TEXT,
    lease_expires_at TEXT,
    heartbeat_at TEXT,
    receipt_id TEXT,
    receipt_hash TEXT CHECK (
        receipt_hash IS NULL OR (
            length(receipt_hash) = 71
            AND substr(receipt_hash, 1, 7) = 'sha256:'
            AND substr(receipt_hash, 8) NOT GLOB '*[^0-9a-f]*'
        )
    ),
    last_error TEXT,
    PRIMARY KEY (run_id, stage_name),
    FOREIGN KEY (run_id) REFERENCES controlled_operation_run(run_id) ON DELETE RESTRICT,
    UNIQUE (receipt_id),
    CHECK ((receipt_id IS NULL) = (receipt_hash IS NULL)),
    CHECK (
        (status = 'IN_PROGRESS'
            AND claim_id IS NOT NULL
            AND claim_epoch >= 1
            AND lease_acquired_at IS NOT NULL
            AND lease_expires_at IS NOT NULL
            AND heartbeat_at IS NOT NULL
            AND receipt_id IS NULL)
        OR
        (status != 'IN_PROGRESS'
            AND claim_id IS NULL
            AND lease_acquired_at IS NULL
            AND lease_expires_at IS NULL
            AND heartbeat_at IS NULL)
    ),
    CHECK (
        (status = 'COMPLETED' AND receipt_id IS NOT NULL)
        OR (status != 'COMPLETED' AND receipt_id IS NULL)
    )
);

CREATE TABLE IF NOT EXISTS controlled_operation_attempt (
    attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    stage_name TEXT NOT NULL,
    attempt_number INTEGER NOT NULL CHECK (attempt_number >= 1),
    claim_id TEXT NOT NULL,
    claim_epoch INTEGER NOT NULL CHECK (claim_epoch >= 1),
    stage_version INTEGER NOT NULL CHECK (stage_version >= 2),
    started_at TEXT NOT NULL,
    lease_expires_at TEXT NOT NULL,
    heartbeat_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL CHECK (status IN (
        'STARTED', 'COMPLETED', 'FAILED', 'LEASE_EXPIRED'
    )),
    error_message TEXT,
    UNIQUE (run_id, stage_name, attempt_number),
    UNIQUE (run_id, stage_name, claim_epoch),
    FOREIGN KEY (run_id, stage_name)
        REFERENCES controlled_operation_stage(run_id, stage_name) ON DELETE RESTRICT,
    CHECK (
        (status = 'STARTED' AND completed_at IS NULL)
        OR (status != 'STARTED' AND completed_at IS NOT NULL)
    )
);

CREATE TABLE IF NOT EXISTS controlled_operation_receipt (
    receipt_id TEXT PRIMARY KEY,
    receipt_hash TEXT NOT NULL CHECK (
        length(receipt_hash) = 71
        AND substr(receipt_hash, 1, 7) = 'sha256:'
        AND substr(receipt_hash, 8) NOT GLOB '*[^0-9a-f]*'
    ),
    run_id TEXT NOT NULL,
    stage_name TEXT NOT NULL,
    attempt_number INTEGER NOT NULL CHECK (attempt_number >= 1),
    receipt_json TEXT NOT NULL CHECK (
        json_valid(receipt_json) AND json_type(receipt_json) = 'object'
    ),
    created_at TEXT NOT NULL,
    UNIQUE (run_id, stage_name),
    UNIQUE (run_id, stage_name, receipt_hash),
    UNIQUE (receipt_id, run_id, stage_name),
    FOREIGN KEY (run_id, stage_name, attempt_number)
        REFERENCES controlled_operation_attempt(run_id, stage_name, attempt_number)
        ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS controlled_operation_child_run (
    run_id TEXT NOT NULL,
    stage_name TEXT NOT NULL,
    reference_kind TEXT NOT NULL CHECK (reference_kind IN (
        'DAILY_ACQUISITION_RUN', 'STATIC_FEATURE_RUN',
        'MINUTE_ACQUISITION_BATCH', 'INTRADAY_FEATURE_RUN',
        'CANONICAL_LIFECYCLE_RUN', 'OUTCOME_RUN'
    )),
    child_run_id TEXT NOT NULL,
    child_receipt_hash TEXT NOT NULL CHECK (
        length(child_receipt_hash) = 71
        AND substr(child_receipt_hash, 1, 7) = 'sha256:'
        AND substr(child_receipt_hash, 8) NOT GLOB '*[^0-9a-f]*'
    ),
    receipt_id TEXT NOT NULL,
    PRIMARY KEY (run_id, reference_kind, child_run_id),
    FOREIGN KEY (receipt_id, run_id, stage_name)
        REFERENCES controlled_operation_receipt(receipt_id, run_id, stage_name)
        ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS controlled_operation_event (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    stage_name TEXT,
    event_type TEXT NOT NULL CHECK (event_type IN (
        'RUN_CREATED', 'RUN_RESUMED', 'RUN_STATUS_CHANGED',
        'STAGE_CLAIMED', 'STAGE_HEARTBEAT', 'STAGE_COMPLETED',
        'STAGE_FAILED', 'LEASE_EXPIRED', 'RECEIPT_RECORDED'
    )),
    event_time TEXT NOT NULL,
    payload_json TEXT NOT NULL CHECK (
        json_valid(payload_json) AND json_type(payload_json) = 'object'
    ),
    FOREIGN KEY (run_id) REFERENCES controlled_operation_run(run_id) ON DELETE RESTRICT,
    FOREIGN KEY (run_id, stage_name)
        REFERENCES controlled_operation_stage(run_id, stage_name) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS controlled_operation_run_status_date_idx
    ON controlled_operation_run(status, decision_date, run_id);
CREATE INDEX IF NOT EXISTS controlled_operation_stage_claimable_idx
    ON controlled_operation_stage(run_id, status, stage_name);
CREATE INDEX IF NOT EXISTS controlled_operation_stage_lease_idx
    ON controlled_operation_stage(run_id, status, lease_expires_at);
CREATE INDEX IF NOT EXISTS controlled_operation_attempt_history_idx
    ON controlled_operation_attempt(run_id, stage_name, attempt_number);
CREATE INDEX IF NOT EXISTS controlled_operation_event_history_idx
    ON controlled_operation_event(run_id, event_id);
CREATE INDEX IF NOT EXISTS controlled_operation_child_run_lookup_idx
    ON controlled_operation_child_run(reference_kind, child_run_id, run_id);

CREATE TRIGGER IF NOT EXISTS controlled_operation_events_no_update
BEFORE UPDATE ON controlled_operation_event BEGIN
    SELECT RAISE(ABORT, 'Controlled operation events are append-only');
END;
CREATE TRIGGER IF NOT EXISTS controlled_operation_events_no_delete
BEFORE DELETE ON controlled_operation_event BEGIN
    SELECT RAISE(ABORT, 'Controlled operation events are append-only');
END;
CREATE TRIGGER IF NOT EXISTS controlled_operation_receipts_no_update
BEFORE UPDATE ON controlled_operation_receipt BEGIN
    SELECT RAISE(ABORT, 'Controlled operation receipts are append-only');
END;
CREATE TRIGGER IF NOT EXISTS controlled_operation_receipts_no_delete
BEFORE DELETE ON controlled_operation_receipt BEGIN
    SELECT RAISE(ABORT, 'Controlled operation receipts are append-only');
END;
CREATE TRIGGER IF NOT EXISTS controlled_operation_child_runs_no_update
BEFORE UPDATE ON controlled_operation_child_run BEGIN
    SELECT RAISE(ABORT, 'Controlled operation child references are append-only');
END;
CREATE TRIGGER IF NOT EXISTS controlled_operation_child_runs_no_delete
BEFORE DELETE ON controlled_operation_child_run BEGIN
    SELECT RAISE(ABORT, 'Controlled operation child references are append-only');
END;
CREATE TRIGGER IF NOT EXISTS controlled_operation_attempts_no_delete
BEFORE DELETE ON controlled_operation_attempt BEGIN
    SELECT RAISE(ABORT, 'Controlled operation attempts are append-only');
END;
CREATE TRIGGER IF NOT EXISTS controlled_operation_settled_attempts_no_update
BEFORE UPDATE ON controlled_operation_attempt
WHEN OLD.status != 'STARTED' BEGIN
    SELECT RAISE(ABORT, 'Settled Controlled operation attempts are immutable');
END;
CREATE TRIGGER IF NOT EXISTS controlled_operation_attempt_identity_guard
BEFORE UPDATE ON controlled_operation_attempt
WHEN OLD.status = 'STARTED' AND (
    NEW.run_id != OLD.run_id OR NEW.stage_name != OLD.stage_name
    OR NEW.attempt_number != OLD.attempt_number
    OR NEW.claim_id != OLD.claim_id OR NEW.claim_epoch != OLD.claim_epoch
    OR NEW.stage_version != OLD.stage_version OR NEW.started_at != OLD.started_at
) BEGIN
    SELECT RAISE(ABORT, 'Controlled operation attempt identity is immutable');
END;
CREATE TRIGGER IF NOT EXISTS controlled_operation_stages_no_delete
BEFORE DELETE ON controlled_operation_stage BEGIN
    SELECT RAISE(ABORT, 'Controlled operation stages cannot be deleted');
END;
CREATE TRIGGER IF NOT EXISTS controlled_operation_completed_stage_immutable
BEFORE UPDATE ON controlled_operation_stage
WHEN OLD.status = 'COMPLETED' BEGIN
    SELECT RAISE(ABORT, 'Completed Controlled operation stage is immutable');
END;
CREATE TRIGGER IF NOT EXISTS controlled_operation_claim_owner_guard
BEFORE UPDATE ON controlled_operation_stage
WHEN OLD.status = 'IN_PROGRESS' AND NEW.status = 'IN_PROGRESS' AND (
    NEW.claim_id != OLD.claim_id OR NEW.claim_epoch != OLD.claim_epoch
) BEGIN
    SELECT RAISE(ABORT, 'Active Controlled operation claim cannot be overwritten');
END;
CREATE TRIGGER IF NOT EXISTS controlled_operation_runs_no_delete
BEFORE DELETE ON controlled_operation_run BEGIN
    SELECT RAISE(ABORT, 'Controlled operation runs cannot be deleted');
END;
CREATE TRIGGER IF NOT EXISTS controlled_operation_run_identity_immutable
BEFORE UPDATE ON controlled_operation_run
WHEN NEW.run_id != OLD.run_id
    OR NEW.idempotency_key != OLD.idempotency_key
    OR NEW.command_hash != OLD.command_hash
    OR NEW.command_json != OLD.command_json
    OR NEW.decision_date != OLD.decision_date
    OR NEW.created_at != OLD.created_at
BEGIN
    SELECT RAISE(ABORT, 'Controlled operation command identity is immutable');
END;

INSERT OR IGNORE INTO controlled_operation_schema_migration(version, applied_at)
VALUES (14, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));

COMMIT;
