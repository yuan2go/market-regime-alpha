PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS pdl_schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS position_books (
    position_book_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    opportunity_id TEXT NOT NULL,
    thesis_id TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('OPEN', 'CLOSED')),
    version INTEGER NOT NULL CHECK (version >= 0),
    aggregate_json TEXT NOT NULL,
    opened_at TEXT NOT NULL,
    closed_at TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS one_open_position_book_per_account_symbol
ON position_books(account_id, symbol)
WHERE state = 'OPEN';

CREATE TABLE IF NOT EXISTS position_book_events (
    position_book_id TEXT NOT NULL,
    sequence INTEGER NOT NULL CHECK (sequence >= 0),
    state TEXT NOT NULL CHECK (state IN ('OPEN', 'CLOSED')),
    aggregate_json TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    PRIMARY KEY (position_book_id, sequence),
    FOREIGN KEY (position_book_id) REFERENCES position_books(position_book_id)
);

CREATE TABLE IF NOT EXISTS traceable_manual_trade_bindings (
    manual_trade_id TEXT PRIMARY KEY,
    position_book_id TEXT NOT NULL,
    opportunity_id TEXT NOT NULL,
    thesis_id TEXT NOT NULL,
    portfolio_decision_id TEXT NOT NULL,
    risk_decision_id TEXT NOT NULL,
    post_trade_snapshot_id TEXT NOT NULL,
    post_trade_snapshot_hash TEXT NOT NULL,
    target_delta_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (manual_trade_id) REFERENCES manual_trade_records(manual_trade_id),
    FOREIGN KEY (position_book_id) REFERENCES position_books(position_book_id)
);

CREATE TRIGGER IF NOT EXISTS traceable_manual_trade_bindings_no_update
BEFORE UPDATE ON traceable_manual_trade_bindings
BEGIN
    SELECT RAISE(ABORT, 'traceable manual trade bindings are append-only');
END;

CREATE TRIGGER IF NOT EXISTS traceable_manual_trade_bindings_no_delete
BEFORE DELETE ON traceable_manual_trade_bindings
BEGIN
    SELECT RAISE(ABORT, 'traceable manual trade bindings are append-only');
END;

INSERT OR IGNORE INTO pdl_schema_migrations(version, applied_at)
VALUES (6, CURRENT_TIMESTAMP);
