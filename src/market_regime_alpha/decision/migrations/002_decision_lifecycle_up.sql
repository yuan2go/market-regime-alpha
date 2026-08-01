PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS pdl_schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS decision_commands (
    idempotency_key TEXT PRIMARY KEY,
    command_hash TEXT NOT NULL,
    opportunity_id TEXT,
    opportunity_version INTEGER,
    thesis_id TEXT,
    thesis_version INTEGER,
    created_at TEXT NOT NULL,
    CHECK (opportunity_version IS NULL OR opportunity_version >= 0),
    CHECK (thesis_version IS NULL OR thesis_version >= 0)
);

CREATE TABLE IF NOT EXISTS trading_opportunities (
    opportunity_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    state TEXT NOT NULL CHECK (
        state IN ('OPEN', 'CONFIRMED_TO_THESIS', 'REJECTED', 'EXPIRED')
    ),
    valid_until TEXT NOT NULL,
    aggregate_json TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version >= 0)
);

CREATE TABLE IF NOT EXISTS opportunity_events (
    opportunity_id TEXT NOT NULL,
    sequence INTEGER NOT NULL CHECK (sequence >= 0),
    event_type TEXT NOT NULL,
    actor TEXT NOT NULL,
    reason TEXT NOT NULL,
    aggregate_json TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    PRIMARY KEY (opportunity_id, sequence),
    FOREIGN KEY (opportunity_id) REFERENCES trading_opportunities(opportunity_id)
);

CREATE TABLE IF NOT EXISTS trading_theses (
    thesis_id TEXT PRIMARY KEY,
    opportunity_id TEXT NOT NULL UNIQUE,
    symbol TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('APPROVED', 'INVALIDATED', 'CLOSED')),
    time_invalidation TEXT NOT NULL,
    aggregate_json TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version >= 0),
    FOREIGN KEY (opportunity_id) REFERENCES trading_opportunities(opportunity_id)
);

CREATE TABLE IF NOT EXISTS thesis_events (
    thesis_id TEXT NOT NULL,
    sequence INTEGER NOT NULL CHECK (sequence >= 0),
    event_type TEXT NOT NULL,
    actor TEXT NOT NULL,
    reason TEXT NOT NULL,
    aggregate_json TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    PRIMARY KEY (thesis_id, sequence),
    FOREIGN KEY (thesis_id) REFERENCES trading_theses(thesis_id)
);

INSERT OR IGNORE INTO pdl_schema_migrations(version, applied_at)
VALUES (2, CURRENT_TIMESTAMP);
