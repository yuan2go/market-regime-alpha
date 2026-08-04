PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS feature_materialization_run (
    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    schema_version TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    command_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    version INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS feature_materialization_task (
    run_id INTEGER NOT NULL,
    task_key TEXT NOT NULL,
    symbol TEXT NOT NULL,
    feature_id TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    status TEXT NOT NULL,
    version INTEGER NOT NULL,
    claim_token TEXT,
    claimed_at TEXT,
    artifact_id TEXT,
    artifact_hash TEXT,
    last_error TEXT,
    PRIMARY KEY(run_id, task_key),
    FOREIGN KEY(run_id) REFERENCES feature_materialization_run(run_id)
);

CREATE TABLE IF NOT EXISTS feature_materialization_attempt (
    attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    task_key TEXT NOT NULL,
    attempt_number INTEGER NOT NULL,
    claim_token TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL,
    error_message TEXT,
    UNIQUE(run_id, task_key, attempt_number),
    FOREIGN KEY(run_id, task_key)
        REFERENCES feature_materialization_task(run_id, task_key)
);

CREATE TABLE IF NOT EXISTS feature_materialization_receipt (
    run_id INTEGER PRIMARY KEY,
    receipt_id TEXT NOT NULL UNIQUE,
    receipt_hash TEXT NOT NULL,
    receipt_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES feature_materialization_run(run_id)
);

CREATE TABLE IF NOT EXISTS feature_materialization_event (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    task_key TEXT,
    event_type TEXT NOT NULL,
    event_time TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES feature_materialization_run(run_id)
);
