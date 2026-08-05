CREATE TABLE portfolio_risk_commands (
    idempotency_key text PRIMARY KEY,
    command_hash text NOT NULL,
    result_type text NOT NULL CHECK (result_type IN ('PORTFOLIO', 'RISK')),
    result_id text NOT NULL,
    created_at timestamptz NOT NULL
);

CREATE TABLE portfolio_decisions (
    portfolio_decision_id text PRIMARY KEY,
    version bigint NOT NULL CHECK (version = 0),
    mode text NOT NULL CHECK (mode IN ('SIMULATION', 'MANUAL_CONFIRMATION')),
    state text NOT NULL,
    risk_budget_id text NOT NULL,
    risk_budget_hash text NOT NULL,
    decision_json text NOT NULL CHECK (decision_json IS JSON),
    created_at timestamptz NOT NULL
);

CREATE TABLE risk_decisions (
    risk_decision_id text PRIMARY KEY,
    portfolio_decision_id text NOT NULL UNIQUE,
    portfolio_decision_version bigint NOT NULL
        CHECK (portfolio_decision_version = 0),
    version bigint NOT NULL CHECK (version = 0),
    state text NOT NULL CHECK (
        state IN ('APPROVED', 'REJECTED', 'TIMEOUT', 'DATA_INSUFFICIENT')
    ),
    decision_json text NOT NULL CHECK (decision_json IS JSON),
    created_at timestamptz NOT NULL,
    FOREIGN KEY (portfolio_decision_id)
        REFERENCES portfolio_decisions(portfolio_decision_id)
);
