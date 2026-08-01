PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS pdl_schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS complete_account_risk_commands (
    idempotency_key TEXT PRIMARY KEY,
    command_hash TEXT NOT NULL,
    account_snapshot_id TEXT NOT NULL,
    portfolio_decision_id TEXT NOT NULL,
    risk_decision_id TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS authoritative_account_portfolio_snapshots (
    account_snapshot_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    as_of TEXT NOT NULL,
    source_reference TEXT NOT NULL,
    completeness TEXT NOT NULL CHECK (
        completeness IN ('COMPLETE_ACCOUNT', 'PARTIAL')
    ),
    reconciliation_state TEXT NOT NULL CHECK (
        reconciliation_state IN (
            'RECONCILED', 'RECONCILIATION_REQUIRED', 'UNKNOWN'
        )
    ),
    version INTEGER NOT NULL CHECK (version >= 0),
    content_hash TEXT NOT NULL UNIQUE,
    snapshot_json TEXT NOT NULL,
    UNIQUE (account_id, as_of, version)
);

CREATE TABLE IF NOT EXISTS complete_account_portfolio_decisions (
    portfolio_decision_id TEXT PRIMARY KEY,
    account_snapshot_id TEXT NOT NULL,
    post_trade_snapshot_id TEXT NOT NULL UNIQUE,
    post_trade_content_hash TEXT NOT NULL UNIQUE,
    configuration_id TEXT NOT NULL,
    configuration_hash TEXT NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('SIMULATION', 'MANUAL_CONFIRMATION')),
    version INTEGER NOT NULL CHECK (version = 0),
    decision_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (account_snapshot_id)
        REFERENCES authoritative_account_portfolio_snapshots(account_snapshot_id)
);

CREATE TABLE IF NOT EXISTS complete_account_risk_decisions (
    risk_decision_id TEXT PRIMARY KEY,
    portfolio_decision_id TEXT NOT NULL UNIQUE,
    post_trade_snapshot_id TEXT NOT NULL UNIQUE,
    state TEXT NOT NULL CHECK (
        state IN ('APPROVED', 'REJECTED', 'TIMEOUT', 'DATA_INSUFFICIENT')
    ),
    version INTEGER NOT NULL CHECK (version = 0),
    decision_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (portfolio_decision_id)
        REFERENCES complete_account_portfolio_decisions(portfolio_decision_id)
);

INSERT OR IGNORE INTO pdl_schema_migrations(version, applied_at)
VALUES (5, CURRENT_TIMESTAMP);
