PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS pdl_schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS risk_reducing_decisions (
    decision_id TEXT PRIMARY KEY,
    position_snapshot_id TEXT NOT NULL,
    position_book_id TEXT NOT NULL,
    thesis_id TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('REDUCE', 'EXIT')),
    state TEXT NOT NULL CHECK (state IN (
        'PERMITTED_FOR_MANUAL_CONFIRMATION', 'BLOCKED', 'DATA_INSUFFICIENT'
    )),
    content_hash TEXT NOT NULL UNIQUE,
    position_json TEXT NOT NULL,
    observation_json TEXT NOT NULL,
    configuration_json TEXT NOT NULL,
    decision_json TEXT NOT NULL,
    assessed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS risk_reducing_commands (
    idempotency_key TEXT PRIMARY KEY,
    command_hash TEXT NOT NULL,
    decision_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (decision_id) REFERENCES risk_reducing_decisions(decision_id)
);

CREATE TRIGGER IF NOT EXISTS risk_reducing_decisions_no_update
BEFORE UPDATE ON risk_reducing_decisions
BEGIN
    SELECT RAISE(ABORT, 'risk reducing decisions are append-only');
END;

CREATE TRIGGER IF NOT EXISTS risk_reducing_decisions_no_delete
BEFORE DELETE ON risk_reducing_decisions
BEGIN
    SELECT RAISE(ABORT, 'risk reducing decisions are append-only');
END;

INSERT OR IGNORE INTO pdl_schema_migrations(version, applied_at)
VALUES (7, CURRENT_TIMESTAMP);
