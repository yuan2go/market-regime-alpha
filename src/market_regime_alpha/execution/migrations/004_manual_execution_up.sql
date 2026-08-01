PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS pdl_schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS execution_commands (
    idempotency_key TEXT PRIMARY KEY,
    command_hash TEXT NOT NULL,
    manual_trade_id TEXT NOT NULL,
    fill_id TEXT,
    result_version INTEGER NOT NULL CHECK (result_version >= 0),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS manual_trade_records (
    manual_trade_id TEXT PRIMARY KEY,
    risk_decision_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
    state TEXT NOT NULL,
    filled_quantity INTEGER NOT NULL CHECK (filled_quantity >= 0),
    aggregate_json TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version >= 0)
);

CREATE TABLE IF NOT EXISTS manual_trade_events (
    manual_trade_id TEXT NOT NULL,
    sequence INTEGER NOT NULL CHECK (sequence >= 0),
    state TEXT NOT NULL,
    aggregate_json TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    PRIMARY KEY (manual_trade_id, sequence),
    FOREIGN KEY (manual_trade_id) REFERENCES manual_trade_records(manual_trade_id)
);

CREATE TABLE IF NOT EXISTS manual_fills (
    fill_id TEXT PRIMARY KEY,
    external_fill_id TEXT NOT NULL UNIQUE,
    manual_trade_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    fill_kind TEXT NOT NULL CHECK (fill_kind IN ('EXECUTION', 'CORRECTION')),
    correction_of_fill_id TEXT UNIQUE,
    fill_json TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    FOREIGN KEY (manual_trade_id) REFERENCES manual_trade_records(manual_trade_id),
    FOREIGN KEY (correction_of_fill_id) REFERENCES manual_fills(fill_id)
);

CREATE TRIGGER IF NOT EXISTS manual_fills_no_update
BEFORE UPDATE ON manual_fills
BEGIN
    SELECT RAISE(ABORT, 'manual_fills are append-only');
END;

CREATE TRIGGER IF NOT EXISTS manual_fills_no_delete
BEFORE DELETE ON manual_fills
BEGIN
    SELECT RAISE(ABORT, 'manual_fills are append-only');
END;

INSERT OR IGNORE INTO pdl_schema_migrations(version, applied_at)
VALUES (4, CURRENT_TIMESTAMP);
