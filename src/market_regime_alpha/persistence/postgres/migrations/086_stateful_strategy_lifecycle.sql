-- Fill-derived Strategy Outcome for the existing Strategy Shadow lifecycle owner.
-- Position continuity itself remains a deterministic projection of immutable
-- Fill allocations, manual account observations, and frozen Strategy cycles.

CREATE TABLE strategy_realized_outcome (
    outcome_id text PRIMARY KEY,
    outcome_hash text NOT NULL CHECK (outcome_hash ~ '^sha256:[0-9a-f]{64}$'),
    account_id text NOT NULL,
    strategy_version_id text NOT NULL,
    strategy_version_hash text NOT NULL,
    entry_proposal_id text NOT NULL,
    entry_proposal_hash text NOT NULL,
    exit_proposal_id text NOT NULL,
    exit_proposal_hash text NOT NULL,
    pre_exit_state_id text NOT NULL,
    pre_exit_state_hash text NOT NULL CHECK (
        pre_exit_state_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    symbol text NOT NULL,
    opened_at timestamptz NOT NULL,
    closed_at timestamptz NOT NULL,
    invested_notional numeric NOT NULL CHECK (invested_notional > 0),
    gross_pnl numeric NOT NULL,
    total_cost numeric NOT NULL CHECK (total_cost >= 0),
    net_pnl numeric NOT NULL,
    net_return numeric NOT NULL,
    source_allocation_ids text[] NOT NULL CHECK (
        cardinality(source_allocation_ids) > 0
    ),
    source_fill_ids text[] NOT NULL CHECK (cardinality(source_fill_ids) > 0),
    production_authorized boolean NOT NULL DEFAULT false
        CHECK (NOT production_authorized),
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' = 'fill-derived-strategy-outcome/v1'
    ),
    created_at timestamptz NOT NULL,
    UNIQUE (outcome_id, outcome_hash),
    UNIQUE (
        account_id, strategy_version_id, symbol, entry_proposal_id
    ),
    CHECK (opened_at < closed_at AND closed_at <= created_at),
    CHECK (net_pnl = gross_pnl - total_cost),
    FOREIGN KEY (strategy_version_id, strategy_version_hash)
        REFERENCES strategy_version(version_id, version_hash) ON DELETE RESTRICT,
    FOREIGN KEY (
        entry_proposal_id, entry_proposal_hash,
        strategy_version_id, strategy_version_hash
    ) REFERENCES strategy_proposal(
        proposal_id, proposal_hash,
        strategy_version_id, strategy_version_hash
    ) ON DELETE RESTRICT,
    FOREIGN KEY (
        exit_proposal_id, exit_proposal_hash,
        strategy_version_id, strategy_version_hash
    ) REFERENCES strategy_proposal(
        proposal_id, proposal_hash,
        strategy_version_id, strategy_version_hash
    ) ON DELETE RESTRICT
);

CREATE INDEX strategy_realized_outcome_scope_idx
ON strategy_realized_outcome(
    account_id, strategy_version_id, symbol, closed_at
);

CREATE INDEX strategy_realized_outcome_version_fk_idx
ON strategy_realized_outcome(strategy_version_id, strategy_version_hash);

CREATE INDEX strategy_realized_outcome_entry_fk_idx
ON strategy_realized_outcome(
    entry_proposal_id, entry_proposal_hash,
    strategy_version_id, strategy_version_hash
);

CREATE INDEX strategy_realized_outcome_exit_fk_idx
ON strategy_realized_outcome(
    exit_proposal_id, exit_proposal_hash,
    strategy_version_id, strategy_version_hash
);

CREATE INDEX strategy_realized_outcome_allocation_idx
ON strategy_realized_outcome USING gin(source_allocation_ids);

CREATE INDEX strategy_realized_outcome_fill_idx
ON strategy_realized_outcome USING gin(source_fill_ids);

CREATE TRIGGER strategy_realized_outcome_no_update
BEFORE UPDATE OR DELETE ON strategy_realized_outcome
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

COMMENT ON TABLE strategy_realized_outcome IS
'Strategy-scoped realized economics derived only after observed allocated Fills close a sleeve; market Path Outcome remains separate.';
