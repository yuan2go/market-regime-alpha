PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS pdl_schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS portfolio_risk_commands (
    idempotency_key TEXT PRIMARY KEY,
    command_hash TEXT NOT NULL,
    result_type TEXT NOT NULL CHECK (result_type IN ('PORTFOLIO', 'RISK')),
    result_id TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS portfolio_decisions (
    portfolio_decision_id TEXT PRIMARY KEY,
    version INTEGER NOT NULL CHECK (version = 0),
    mode TEXT NOT NULL CHECK (mode IN ('SIMULATION', 'MANUAL_CONFIRMATION')),
    state TEXT NOT NULL,
    risk_budget_id TEXT NOT NULL,
    risk_budget_hash TEXT NOT NULL,
    decision_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS risk_decisions (
    risk_decision_id TEXT PRIMARY KEY,
    portfolio_decision_id TEXT NOT NULL UNIQUE,
    portfolio_decision_version INTEGER NOT NULL CHECK (portfolio_decision_version = 0),
    version INTEGER NOT NULL CHECK (version = 0),
    state TEXT NOT NULL CHECK (state IN ('APPROVED', 'REJECTED', 'TIMEOUT', 'DATA_INSUFFICIENT')),
    decision_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (portfolio_decision_id) REFERENCES portfolio_decisions(portfolio_decision_id)
);

INSERT OR IGNORE INTO pdl_schema_migrations(version, applied_at)
VALUES (3, CURRENT_TIMESTAMP);
