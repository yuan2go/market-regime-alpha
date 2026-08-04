PRAGMA foreign_keys = ON;

BEGIN IMMEDIATE;

CREATE TABLE IF NOT EXISTS pdl_schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lifecycle_runs (
    run_id TEXT PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    command_hash TEXT NOT NULL,
    command_json TEXT NOT NULL CHECK (json_valid(command_json)),
    run_type TEXT NOT NULL CHECK (
        run_type IN (
            'CANONICAL_DECISION_LIFECYCLE',
            'RISK_REDUCTION_CONTINUATION',
            'REPLAY'
        )
    ),
    decision_date TEXT NOT NULL CHECK (date(decision_date) = decision_date),
    as_of_time TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN (
            'CREATED',
            'RUNNING',
            'RETRYING',
            'WAITING_FOR_ENTRY_CONFIRMATION',
            'BLOCKED_BY_MODEL_VALIDATION',
            'WAITING_FOR_MANUAL_CONFIRMATION',
            'WAITING_FOR_FILL',
            'POSITION_OPEN',
            'WAITING_FOR_T1',
            'READY_FOR_HOLDING_ASSESSMENT',
            'READY_FOR_EXIT_REVIEW',
            'COMPLETED',
            'FAILED'
        )
    ),
    current_stage TEXT CHECK (
        current_stage IS NULL OR current_stage IN (
            'VERIFY_COMPOSITE_EVIDENCE',
            'PLATFORM_RESEARCH',
            'SIGNAL',
            'PATH_FORECAST',
            'ENTRY_ASSESSMENT',
            'OPPORTUNITY',
            'THESIS',
            'PORTFOLIO_RISK',
            'RISK_REDUCTION',
            'MANUAL_CONFIRMATION',
            'MANUAL_TRADE',
            'FILL_POSITION',
            'THESIS_HEALTH',
            'HOLDING_ASSESSMENT',
            'EXIT_ASSESSMENT',
            'OUTCOME_REVIEW'
        )
    ),
    input_manifest_id TEXT,
    input_content_hash TEXT,
    run_json TEXT NOT NULL CHECK (json_valid(run_json)),
    version INTEGER NOT NULL CHECK (version > 0),
    claim_token INTEGER NOT NULL CHECK (claim_token >= 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    CHECK ((input_manifest_id IS NULL) = (input_content_hash IS NULL)),
    CHECK (
        length(command_hash) = 71
        AND substr(command_hash, 1, 7) = 'sha256:'
        AND substr(command_hash, 8) NOT GLOB '*[^0-9a-f]*'
    ),
    CHECK (
        input_content_hash IS NULL OR (
            length(input_content_hash) = 71
            AND substr(input_content_hash, 1, 7) = 'sha256:'
            AND substr(input_content_hash, 8) NOT GLOB '*[^0-9a-f]*'
        )
    )
);

CREATE TABLE IF NOT EXISTS lifecycle_stages (
    run_id TEXT NOT NULL,
    stage_name TEXT NOT NULL CHECK (
        stage_name IN (
            'VERIFY_COMPOSITE_EVIDENCE',
            'PLATFORM_RESEARCH',
            'SIGNAL',
            'PATH_FORECAST',
            'ENTRY_ASSESSMENT',
            'OPPORTUNITY',
            'THESIS',
            'PORTFOLIO_RISK',
            'RISK_REDUCTION',
            'MANUAL_CONFIRMATION',
            'MANUAL_TRADE',
            'FILL_POSITION',
            'THESIS_HEALTH',
            'HOLDING_ASSESSMENT',
            'EXIT_ASSESSMENT',
            'OUTCOME_REVIEW'
        )
    ),
    stage_status TEXT NOT NULL CHECK (
        stage_status IN (
            'PENDING',
            'RUNNING',
            'COMPLETED',
            'WAITING',
            'BLOCKED',
            'FAILED',
            'SKIPPED_NOT_APPLICABLE'
        )
    ),
    attempt_count INTEGER NOT NULL CHECK (attempt_count >= 0),
    stage_json TEXT NOT NULL CHECK (json_valid(stage_json)),
    version INTEGER NOT NULL CHECK (version > 0),
    PRIMARY KEY (run_id, stage_name),
    FOREIGN KEY (run_id) REFERENCES lifecycle_runs(run_id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS lifecycle_attempts (
    attempt_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    stage_name TEXT NOT NULL,
    attempt_number INTEGER NOT NULL CHECK (attempt_number > 0),
    result TEXT NOT NULL CHECK (
        result IN (
            'RUNNING',
            'COMPLETED',
            'WAITING',
            'BLOCKED',
            'FAILED',
            'SKIPPED_NOT_APPLICABLE'
        )
    ),
    attempt_json TEXT NOT NULL CHECK (json_valid(attempt_json)),
    claim_token INTEGER NOT NULL CHECK (claim_token > 0),
    started_at TEXT NOT NULL,
    completed_at TEXT,
    exception_type TEXT,
    exception_message TEXT,
    UNIQUE (run_id, stage_name, attempt_number),
    UNIQUE (attempt_id, run_id, stage_name),
    FOREIGN KEY (run_id, stage_name)
        REFERENCES lifecycle_stages(run_id, stage_name) ON DELETE RESTRICT,
    CHECK (
        (result = 'RUNNING' AND completed_at IS NULL)
        OR (result != 'RUNNING' AND completed_at IS NOT NULL)
    ),
    CHECK ((exception_type IS NULL) = (exception_message IS NULL)),
    CHECK ((result = 'FAILED') = (exception_type IS NOT NULL))
);

CREATE TABLE IF NOT EXISTS lifecycle_stage_receipts (
    receipt_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    stage_name TEXT NOT NULL,
    attempt_number INTEGER NOT NULL CHECK (attempt_number > 0),
    receipt_hash TEXT NOT NULL,
    receipt_json TEXT NOT NULL CHECK (json_valid(receipt_json)),
    stage_result TEXT NOT NULL CHECK (
        stage_result IN (
            'COMPLETED',
            'WAITING',
            'BLOCKED',
            'SKIPPED_NOT_APPLICABLE'
        )
    ),
    created_at TEXT NOT NULL,
    UNIQUE (run_id, stage_name, receipt_hash),
    UNIQUE (receipt_id, run_id, stage_name),
    FOREIGN KEY (run_id, stage_name, attempt_number)
        REFERENCES lifecycle_attempts(run_id, stage_name, attempt_number)
        ON DELETE RESTRICT,
    CHECK (
        length(receipt_hash) = 71
        AND substr(receipt_hash, 1, 7) = 'sha256:'
        AND substr(receipt_hash, 8) NOT GLOB '*[^0-9a-f]*'
    )
);

CREATE TABLE IF NOT EXISTS lifecycle_events (
    event_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    sequence_number INTEGER NOT NULL CHECK (sequence_number > 0),
    event_type TEXT NOT NULL CHECK (
        event_type IN (
            'RUN_CREATED',
            'RUN_CLAIMED',
            'RUN_STATUS_CHANGED',
            'STAGE_STATUS_CHANGED',
            'ATTEMPT_STARTED',
            'ATTEMPT_FINISHED',
            'RECEIPT_RECORDED'
        )
    ),
    stage_name TEXT CHECK (
        stage_name IS NULL OR stage_name IN (
            'VERIFY_COMPOSITE_EVIDENCE',
            'PLATFORM_RESEARCH',
            'SIGNAL',
            'PATH_FORECAST',
            'ENTRY_ASSESSMENT',
            'OPPORTUNITY',
            'THESIS',
            'PORTFOLIO_RISK',
            'RISK_REDUCTION',
            'MANUAL_CONFIRMATION',
            'MANUAL_TRADE',
            'FILL_POSITION',
            'THESIS_HEALTH',
            'HOLDING_ASSESSMENT',
            'EXIT_ASSESSMENT',
            'OUTCOME_REVIEW'
        )
    ),
    attempt_id TEXT,
    receipt_id TEXT,
    event_json TEXT NOT NULL CHECK (json_valid(event_json)),
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    payload_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    claim_token INTEGER NOT NULL CHECK (claim_token >= 0),
    UNIQUE (run_id, sequence_number),
    FOREIGN KEY (run_id) REFERENCES lifecycle_runs(run_id) ON DELETE RESTRICT,
    FOREIGN KEY (run_id, stage_name)
        REFERENCES lifecycle_stages(run_id, stage_name) ON DELETE RESTRICT,
    FOREIGN KEY (attempt_id, run_id, stage_name)
        REFERENCES lifecycle_attempts(attempt_id, run_id, stage_name)
        ON DELETE RESTRICT,
    FOREIGN KEY (receipt_id, run_id, stage_name)
        REFERENCES lifecycle_stage_receipts(receipt_id, run_id, stage_name)
        ON DELETE RESTRICT,
    CHECK (attempt_id IS NULL OR stage_name IS NOT NULL),
    CHECK (receipt_id IS NULL OR stage_name IS NOT NULL),
    CHECK (
        event_type NOT IN (
            'STAGE_STATUS_CHANGED',
            'ATTEMPT_STARTED',
            'ATTEMPT_FINISHED',
            'RECEIPT_RECORDED'
        ) OR stage_name IS NOT NULL
    ),
    CHECK (
        (event_type IN ('ATTEMPT_STARTED', 'ATTEMPT_FINISHED'))
        = (attempt_id IS NOT NULL)
    ),
    CHECK ((event_type = 'RECEIPT_RECORDED') = (receipt_id IS NOT NULL)),
    CHECK (
        length(payload_hash) = 71
        AND substr(payload_hash, 1, 7) = 'sha256:'
        AND substr(payload_hash, 8) NOT GLOB '*[^0-9a-f]*'
    )
);

CREATE INDEX IF NOT EXISTS lifecycle_runs_status_decision_date_idx
ON lifecycle_runs(status, decision_date, run_id);

CREATE INDEX IF NOT EXISTS lifecycle_stages_status_idx
ON lifecycle_stages(stage_status, stage_name, run_id);

CREATE INDEX IF NOT EXISTS lifecycle_attempts_history_idx
ON lifecycle_attempts(run_id, stage_name, attempt_number);

CREATE INDEX IF NOT EXISTS lifecycle_receipts_history_idx
ON lifecycle_stage_receipts(run_id, created_at, receipt_id);

CREATE INDEX IF NOT EXISTS lifecycle_events_history_idx
ON lifecycle_events(run_id, sequence_number);

CREATE TRIGGER IF NOT EXISTS lifecycle_attempts_no_delete
BEFORE DELETE ON lifecycle_attempts
BEGIN
    SELECT RAISE(ABORT, 'lifecycle attempts are append-only');
END;

CREATE TRIGGER IF NOT EXISTS lifecycle_attempts_terminal_immutable
BEFORE UPDATE ON lifecycle_attempts
WHEN OLD.result != 'RUNNING'
BEGIN
    SELECT RAISE(ABORT, 'settled lifecycle attempts are append-only');
END;

-- An attempt is append-only except for the single assignment that settles its
-- initial RUNNING row. Identity, scope, fencing token and start time cannot
-- change during that assignment; terminal rows reject every later update.
CREATE TRIGGER IF NOT EXISTS lifecycle_attempts_completion_only
BEFORE UPDATE ON lifecycle_attempts
WHEN OLD.result = 'RUNNING' AND (
    NEW.attempt_id != OLD.attempt_id
    OR NEW.run_id != OLD.run_id
    OR NEW.stage_name != OLD.stage_name
    OR NEW.attempt_number != OLD.attempt_number
    OR NEW.claim_token != OLD.claim_token
    OR NEW.started_at != OLD.started_at
    OR NEW.result = 'RUNNING'
    OR NEW.completed_at IS NULL
)
BEGIN
    SELECT RAISE(ABORT, 'lifecycle attempt permits one completion only');
END;

CREATE TRIGGER IF NOT EXISTS lifecycle_stage_receipts_no_update
BEFORE UPDATE ON lifecycle_stage_receipts
BEGIN
    SELECT RAISE(ABORT, 'lifecycle stage receipts are append-only');
END;

CREATE TRIGGER IF NOT EXISTS lifecycle_stage_receipts_no_delete
BEFORE DELETE ON lifecycle_stage_receipts
BEGIN
    SELECT RAISE(ABORT, 'lifecycle stage receipts are append-only');
END;

CREATE TRIGGER IF NOT EXISTS lifecycle_events_no_update
BEFORE UPDATE ON lifecycle_events
BEGIN
    SELECT RAISE(ABORT, 'lifecycle events are append-only');
END;

CREATE TRIGGER IF NOT EXISTS lifecycle_events_no_delete
BEFORE DELETE ON lifecycle_events
BEGIN
    SELECT RAISE(ABORT, 'lifecycle events are append-only');
END;

CREATE TRIGGER IF NOT EXISTS lifecycle_terminal_stages_immutable
BEFORE UPDATE ON lifecycle_stages
WHEN OLD.stage_status IN ('COMPLETED', 'BLOCKED', 'SKIPPED_NOT_APPLICABLE')
BEGIN
    SELECT RAISE(ABORT, 'terminal lifecycle stages are immutable');
END;

CREATE TRIGGER IF NOT EXISTS lifecycle_stages_no_delete
BEFORE DELETE ON lifecycle_stages
BEGIN
    SELECT RAISE(ABORT, 'lifecycle stages cannot be deleted');
END;

CREATE TRIGGER IF NOT EXISTS lifecycle_runs_no_delete
BEFORE DELETE ON lifecycle_runs
BEGIN
    SELECT RAISE(ABORT, 'lifecycle runs cannot be deleted');
END;

CREATE TRIGGER IF NOT EXISTS lifecycle_runs_identity_immutable
BEFORE UPDATE ON lifecycle_runs
WHEN NEW.run_id IS NOT OLD.run_id
    OR NEW.idempotency_key IS NOT OLD.idempotency_key
    OR NEW.command_hash IS NOT OLD.command_hash
    OR NEW.command_json IS NOT OLD.command_json
    OR NEW.run_type IS NOT OLD.run_type
    OR NEW.decision_date IS NOT OLD.decision_date
    OR NEW.as_of_time IS NOT OLD.as_of_time
    OR NEW.input_manifest_id IS NOT OLD.input_manifest_id
    OR NEW.input_content_hash IS NOT OLD.input_content_hash
    OR NEW.created_at IS NOT OLD.created_at
BEGIN
    SELECT RAISE(ABORT, 'lifecycle run command identity is immutable');
END;

INSERT OR IGNORE INTO pdl_schema_migrations(version, applied_at)
VALUES (11, CURRENT_TIMESTAMP);

COMMIT;
