CREATE TABLE complete_account_risk_commands (
    idempotency_key text PRIMARY KEY,
    command_hash text NOT NULL,
    account_snapshot_id text NOT NULL,
    portfolio_decision_id text NOT NULL,
    risk_decision_id text NOT NULL,
    created_at timestamptz NOT NULL
);

CREATE TABLE authoritative_account_portfolio_snapshots (
    account_snapshot_id text PRIMARY KEY,
    account_id text NOT NULL,
    as_of timestamptz NOT NULL,
    source_reference text NOT NULL,
    completeness text NOT NULL CHECK (
        completeness IN ('COMPLETE_ACCOUNT', 'PARTIAL')
    ),
    reconciliation_state text NOT NULL CHECK (
        reconciliation_state IN (
            'RECONCILED', 'RECONCILIATION_REQUIRED', 'UNKNOWN'
        )
    ),
    version bigint NOT NULL CHECK (version >= 0),
    content_hash text NOT NULL UNIQUE,
    snapshot_json text NOT NULL CHECK (snapshot_json IS JSON),
    UNIQUE (account_id, as_of, version)
);

CREATE TABLE complete_account_portfolio_decisions (
    portfolio_decision_id text PRIMARY KEY,
    account_snapshot_id text NOT NULL,
    post_trade_snapshot_id text NOT NULL UNIQUE,
    post_trade_content_hash text NOT NULL UNIQUE,
    configuration_id text NOT NULL,
    configuration_hash text NOT NULL,
    mode text NOT NULL CHECK (mode IN ('SIMULATION', 'MANUAL_CONFIRMATION')),
    version bigint NOT NULL CHECK (version = 0),
    decision_json text NOT NULL CHECK (decision_json IS JSON),
    created_at timestamptz NOT NULL,
    FOREIGN KEY (account_snapshot_id)
        REFERENCES authoritative_account_portfolio_snapshots(account_snapshot_id)
);

CREATE INDEX complete_account_portfolio_decisions_snapshot_idx
ON complete_account_portfolio_decisions(account_snapshot_id);

CREATE TABLE complete_account_risk_decisions (
    risk_decision_id text PRIMARY KEY,
    portfolio_decision_id text NOT NULL UNIQUE,
    post_trade_snapshot_id text NOT NULL UNIQUE,
    state text NOT NULL CHECK (
        state IN ('APPROVED', 'REJECTED', 'TIMEOUT', 'DATA_INSUFFICIENT')
    ),
    version bigint NOT NULL CHECK (version = 0),
    decision_json text NOT NULL CHECK (decision_json IS JSON),
    created_at timestamptz NOT NULL,
    FOREIGN KEY (portfolio_decision_id)
        REFERENCES complete_account_portfolio_decisions(portfolio_decision_id)
);
