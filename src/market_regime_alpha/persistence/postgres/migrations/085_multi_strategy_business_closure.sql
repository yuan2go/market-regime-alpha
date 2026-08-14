-- Canonical multi-Strategy business facts behind the existing Runtime and PostgreSQL authority.

CREATE TABLE strategy_contract (
    contract_id text PRIMARY KEY,
    contract_hash text NOT NULL CHECK (contract_hash ~ '^sha256:[0-9a-f]{64}$'),
    strategy_id text NOT NULL,
    family text NOT NULL CHECK (family IN ('OVERNIGHT', 'SWING_STATE')),
    semantic_version text NOT NULL,
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' = 'strategy-contract/v1'
    ),
    created_at timestamptz NOT NULL,
    UNIQUE (contract_id, contract_hash),
    UNIQUE (strategy_id, semantic_version)
);

CREATE TABLE strategy_version (
    version_id text PRIMARY KEY,
    version_hash text NOT NULL CHECK (version_hash ~ '^sha256:[0-9a-f]{64}$'),
    contract_id text NOT NULL,
    contract_hash text NOT NULL,
    strategy_id text NOT NULL,
    family text NOT NULL CHECK (family IN ('OVERNIGHT', 'SWING_STATE')),
    semantic_version text NOT NULL,
    lifecycle_status text NOT NULL CHECK (
        lifecycle_status IN ('ACTIVE', 'SUSPENDED', 'RETIRED')
    ),
    research_status text NOT NULL CHECK (
        research_status IN ('EXPLORATORY', 'QUALIFICATION_BLOCKED')
    ),
    production_authorized boolean NOT NULL DEFAULT false
        CHECK (NOT production_authorized),
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' = 'strategy-version/v1'
    ),
    created_at timestamptz NOT NULL,
    UNIQUE (version_id, version_hash),
    FOREIGN KEY (contract_id, contract_hash)
        REFERENCES strategy_contract(contract_id, contract_hash) ON DELETE RESTRICT
);

CREATE INDEX strategy_version_contract_idx
ON strategy_version(contract_id, contract_hash);

CREATE UNIQUE INDEX strategy_version_one_active_idx
ON strategy_version(strategy_id)
WHERE lifecycle_status = 'ACTIVE';

CREATE TABLE multi_strategy_cycle (
    cycle_id text PRIMARY KEY,
    cycle_hash text NOT NULL CHECK (cycle_hash ~ '^sha256:[0-9a-f]{64}$'),
    origin text NOT NULL CHECK (origin IN ('CONTINUOUS', 'HISTORICAL', 'REPLAY')),
    authority_mode text NOT NULL CHECK (authority_mode IN ('RESEARCH', 'SHADOW')),
    parent_run_id text NOT NULL,
    parent_run_hash text NOT NULL CHECK (parent_run_hash ~ '^sha256:[0-9a-f]{64}$'),
    parent_tick_id text NOT NULL,
    parent_tick_hash text NOT NULL CHECK (parent_tick_hash ~ '^sha256:[0-9a-f]{64}$'),
    candidate_artifact_id text NOT NULL,
    candidate_artifact_hash text NOT NULL CHECK (
        candidate_artifact_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    dataset_id text NOT NULL,
    dataset_hash text NOT NULL CHECK (dataset_hash ~ '^sha256:[0-9a-f]{64}$'),
    decision_time timestamptz NOT NULL,
    input_hash text NOT NULL CHECK (input_hash ~ '^sha256:[0-9a-f]{64}$'),
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' = 'multi-strategy-cycle/v1'
    ),
    created_at timestamptz NOT NULL,
    UNIQUE (cycle_id, cycle_hash)
);

CREATE INDEX multi_strategy_cycle_parent_idx
ON multi_strategy_cycle(parent_run_id, parent_tick_id, decision_time);

CREATE TABLE strategy_run (
    run_id text PRIMARY KEY,
    run_hash text NOT NULL CHECK (run_hash ~ '^sha256:[0-9a-f]{64}$'),
    cycle_id text NOT NULL,
    cycle_hash text NOT NULL,
    strategy_version_id text NOT NULL,
    strategy_version_hash text NOT NULL,
    status text NOT NULL CHECK (status IN ('COMPLETED', 'DATA_INSUFFICIENT')),
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' = 'strategy-run/v1'
    ),
    created_at timestamptz NOT NULL,
    UNIQUE (run_id, run_hash),
    UNIQUE (cycle_id, strategy_version_id),
    FOREIGN KEY (cycle_id, cycle_hash)
        REFERENCES multi_strategy_cycle(cycle_id, cycle_hash) ON DELETE RESTRICT,
    FOREIGN KEY (strategy_version_id, strategy_version_hash)
        REFERENCES strategy_version(version_id, version_hash) ON DELETE RESTRICT
);

CREATE INDEX strategy_run_cycle_idx
ON strategy_run(cycle_id, cycle_hash);

CREATE INDEX strategy_run_version_idx
ON strategy_run(strategy_version_id, strategy_version_hash, created_at);

CREATE TABLE strategy_gate_attribution (
    gate_id text PRIMARY KEY,
    run_id text NOT NULL,
    symbol text NOT NULL,
    eligibility_status text NOT NULL CHECK (
        eligibility_status IN ('ELIGIBLE', 'INELIGIBLE', 'NOT_ESTIMABLE')
    ),
    candidate_status text NOT NULL,
    action text NOT NULL CHECK (
        action IN ('NO_ACTION', 'ENTER', 'HOLD', 'ADD', 'REDUCE', 'ROTATE', 'EXIT')
    ),
    payload_json jsonb NOT NULL CHECK (jsonb_typeof(payload_json) = 'object'),
    created_at timestamptz NOT NULL,
    UNIQUE (run_id, symbol),
    FOREIGN KEY (run_id) REFERENCES strategy_run(run_id) ON DELETE RESTRICT
);

CREATE INDEX strategy_gate_attribution_run_idx
ON strategy_gate_attribution(run_id, eligibility_status, action);

CREATE TABLE strategy_proposal (
    proposal_id text PRIMARY KEY,
    proposal_hash text NOT NULL CHECK (proposal_hash ~ '^sha256:[0-9a-f]{64}$'),
    run_id text NOT NULL,
    strategy_version_id text NOT NULL,
    strategy_version_hash text NOT NULL,
    symbol text NOT NULL,
    action text NOT NULL CHECK (
        action IN ('ENTER', 'ADD', 'REDUCE', 'ROTATE', 'EXIT')
    ),
    desired_weight numeric NOT NULL CHECK (desired_weight BETWEEN -1 AND 1),
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' = 'strategy-proposal/v1'
    ),
    created_at timestamptz NOT NULL,
    UNIQUE (proposal_id, proposal_hash),
    FOREIGN KEY (run_id) REFERENCES strategy_run(run_id) ON DELETE RESTRICT,
    FOREIGN KEY (strategy_version_id, strategy_version_hash)
        REFERENCES strategy_version(version_id, version_hash) ON DELETE RESTRICT
);

CREATE INDEX strategy_proposal_run_idx
ON strategy_proposal(run_id, symbol);

CREATE INDEX strategy_proposal_version_idx
ON strategy_proposal(strategy_version_id, strategy_version_hash, created_at);

CREATE TABLE cross_strategy_portfolio_decision (
    decision_id text PRIMARY KEY,
    decision_hash text NOT NULL CHECK (decision_hash ~ '^sha256:[0-9a-f]{64}$'),
    cycle_id text NOT NULL,
    cycle_hash text NOT NULL,
    status text NOT NULL CHECK (status IN ('ACCEPTED', 'PARTIAL', 'NO_ACTION')),
    gross_accepted_weight numeric NOT NULL CHECK (
        gross_accepted_weight BETWEEN 0 AND 1
    ),
    production_authorized boolean NOT NULL DEFAULT false
        CHECK (NOT production_authorized),
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' = 'cross-strategy-portfolio-decision/v1'
    ),
    created_at timestamptz NOT NULL,
    UNIQUE (decision_id, decision_hash),
    UNIQUE (cycle_id),
    FOREIGN KEY (cycle_id, cycle_hash)
        REFERENCES multi_strategy_cycle(cycle_id, cycle_hash) ON DELETE RESTRICT
);

CREATE INDEX cross_strategy_portfolio_cycle_idx
ON cross_strategy_portfolio_decision(cycle_id, cycle_hash);

CREATE TABLE cross_strategy_portfolio_line (
    line_id text PRIMARY KEY,
    decision_id text NOT NULL,
    proposal_id text NOT NULL,
    proposal_hash text NOT NULL,
    strategy_version_id text NOT NULL,
    symbol text NOT NULL,
    requested_weight numeric NOT NULL,
    accepted_weight numeric NOT NULL,
    payload_json jsonb NOT NULL CHECK (jsonb_typeof(payload_json) = 'object'),
    created_at timestamptz NOT NULL,
    UNIQUE (decision_id, proposal_id),
    FOREIGN KEY (decision_id)
        REFERENCES cross_strategy_portfolio_decision(decision_id) ON DELETE RESTRICT,
    FOREIGN KEY (proposal_id, proposal_hash)
        REFERENCES strategy_proposal(proposal_id, proposal_hash) ON DELETE RESTRICT
);

CREATE INDEX cross_strategy_portfolio_line_decision_idx
ON cross_strategy_portfolio_line(decision_id, symbol);

CREATE INDEX cross_strategy_portfolio_line_proposal_idx
ON cross_strategy_portfolio_line(proposal_id, proposal_hash);

CREATE TABLE strategy_fill_allocation_batch (
    batch_id text PRIMARY KEY,
    batch_hash text NOT NULL CHECK (batch_hash ~ '^sha256:[0-9a-f]{64}$'),
    source_fill_id text NOT NULL UNIQUE,
    source_fill_hash text NOT NULL CHECK (source_fill_hash ~ '^sha256:[0-9a-f]{64}$'),
    correction_of_fill_id text,
    account_id text NOT NULL,
    symbol text NOT NULL,
    side text NOT NULL CHECK (side IN ('BUY', 'SELL')),
    quantity bigint NOT NULL CHECK (quantity > 0),
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' = 'strategy-fill-allocation-batch/v1'
    ),
    created_at timestamptz NOT NULL,
    UNIQUE (batch_id, batch_hash),
    FOREIGN KEY (source_fill_id) REFERENCES manual_fills(fill_id) ON DELETE RESTRICT,
    FOREIGN KEY (correction_of_fill_id) REFERENCES manual_fills(fill_id) ON DELETE RESTRICT
);

CREATE INDEX strategy_fill_allocation_fill_idx
ON strategy_fill_allocation_batch(source_fill_id);

CREATE INDEX strategy_fill_allocation_correction_idx
ON strategy_fill_allocation_batch(correction_of_fill_id)
WHERE correction_of_fill_id IS NOT NULL;

CREATE TABLE strategy_fill_allocation (
    allocation_id text PRIMARY KEY,
    allocation_hash text NOT NULL CHECK (allocation_hash ~ '^sha256:[0-9a-f]{64}$'),
    batch_id text NOT NULL,
    strategy_version_id text NOT NULL,
    strategy_version_hash text NOT NULL,
    proposal_id text NOT NULL,
    proposal_hash text NOT NULL,
    allocated_quantity bigint NOT NULL CHECK (allocated_quantity > 0),
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' = 'strategy-fill-allocation/v1'
    ),
    created_at timestamptz NOT NULL,
    UNIQUE (batch_id, strategy_version_id, proposal_id),
    FOREIGN KEY (batch_id)
        REFERENCES strategy_fill_allocation_batch(batch_id) ON DELETE RESTRICT,
    FOREIGN KEY (strategy_version_id, strategy_version_hash)
        REFERENCES strategy_version(version_id, version_hash) ON DELETE RESTRICT,
    FOREIGN KEY (proposal_id, proposal_hash)
        REFERENCES strategy_proposal(proposal_id, proposal_hash) ON DELETE RESTRICT
);

CREATE INDEX strategy_fill_allocation_batch_idx
ON strategy_fill_allocation(batch_id);

CREATE INDEX strategy_fill_allocation_version_idx
ON strategy_fill_allocation(strategy_version_id, strategy_version_hash);

CREATE INDEX strategy_fill_allocation_proposal_idx
ON strategy_fill_allocation(proposal_id, proposal_hash);

CREATE TABLE strategy_path_outcome (
    outcome_id text PRIMARY KEY,
    outcome_hash text NOT NULL CHECK (outcome_hash ~ '^sha256:[0-9a-f]{64}$'),
    strategy_run_id text NOT NULL,
    strategy_run_hash text NOT NULL,
    strategy_version_id text NOT NULL,
    strategy_version_hash text NOT NULL,
    dataset_id text NOT NULL,
    dataset_hash text NOT NULL CHECK (dataset_hash ~ '^sha256:[0-9a-f]{64}$'),
    target_id text NOT NULL,
    target_hash text NOT NULL CHECK (target_hash ~ '^sha256:[0-9a-f]{64}$'),
    symbol text NOT NULL,
    decision_time timestamptz NOT NULL,
    horizon_sessions integer NOT NULL CHECK (horizon_sessions > 0),
    mfe numeric NOT NULL CHECK (mfe >= 0),
    mae numeric NOT NULL CHECK (mae <= 0),
    barrier_ordering text NOT NULL CHECK (
        barrier_ordering IN (
            'TARGET_BEFORE_STOP', 'STOP_BEFORE_TARGET', 'NEITHER', 'NOT_OBSERVABLE'
        )
    ),
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' = 'strategy-path-outcome/v1'
    ),
    created_at timestamptz NOT NULL,
    UNIQUE (outcome_id, outcome_hash),
    UNIQUE (strategy_run_id, target_id, symbol),
    FOREIGN KEY (strategy_run_id, strategy_run_hash)
        REFERENCES strategy_run(run_id, run_hash) ON DELETE RESTRICT,
    FOREIGN KEY (strategy_version_id, strategy_version_hash)
        REFERENCES strategy_version(version_id, version_hash) ON DELETE RESTRICT
);

CREATE INDEX strategy_path_outcome_run_idx
ON strategy_path_outcome(strategy_run_id, strategy_run_hash);

CREATE INDEX strategy_path_outcome_version_idx
ON strategy_path_outcome(strategy_version_id, strategy_version_hash, horizon_sessions);

CREATE TABLE strategy_feedback_artifact (
    artifact_id text PRIMARY KEY,
    artifact_hash text NOT NULL CHECK (artifact_hash ~ '^sha256:[0-9a-f]{64}$'),
    artifact_kind text NOT NULL CHECK (
        artifact_kind IN ('ATTRIBUTION', 'CHALLENGER_EVALUATION', 'QUALIFICATION_DECISION')
    ),
    strategy_version_id text NOT NULL,
    strategy_version_hash text NOT NULL,
    source_artifact_ids text[] NOT NULL CHECK (cardinality(source_artifact_ids) > 0),
    status text NOT NULL CHECK (
        status IN ('EXPLORATORY', 'NOT_ESTIMABLE', 'NOT_QUALIFIED')
    ),
    production_authorized boolean NOT NULL DEFAULT false
        CHECK (NOT production_authorized),
    payload_json jsonb NOT NULL CHECK (jsonb_typeof(payload_json) = 'object'),
    created_at timestamptz NOT NULL,
    UNIQUE (artifact_id, artifact_hash),
    FOREIGN KEY (strategy_version_id, strategy_version_hash)
        REFERENCES strategy_version(version_id, version_hash) ON DELETE RESTRICT
);

CREATE INDEX strategy_feedback_version_idx
ON strategy_feedback_artifact(strategy_version_id, strategy_version_hash, artifact_kind);

CREATE INDEX strategy_feedback_source_idx
ON strategy_feedback_artifact USING gin(source_artifact_ids);

CREATE TRIGGER strategy_contract_no_update
BEFORE UPDATE OR DELETE ON strategy_contract
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER strategy_version_no_update
BEFORE UPDATE OR DELETE ON strategy_version
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER multi_strategy_cycle_no_update
BEFORE UPDATE OR DELETE ON multi_strategy_cycle
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER strategy_run_no_update
BEFORE UPDATE OR DELETE ON strategy_run
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER strategy_gate_attribution_no_update
BEFORE UPDATE OR DELETE ON strategy_gate_attribution
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER strategy_proposal_no_update
BEFORE UPDATE OR DELETE ON strategy_proposal
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER cross_strategy_portfolio_decision_no_update
BEFORE UPDATE OR DELETE ON cross_strategy_portfolio_decision
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER cross_strategy_portfolio_line_no_update
BEFORE UPDATE OR DELETE ON cross_strategy_portfolio_line
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER strategy_fill_allocation_batch_no_update
BEFORE UPDATE OR DELETE ON strategy_fill_allocation_batch
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER strategy_fill_allocation_no_update
BEFORE UPDATE OR DELETE ON strategy_fill_allocation
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER strategy_path_outcome_no_update
BEFORE UPDATE OR DELETE ON strategy_path_outcome
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER strategy_feedback_artifact_no_update
BEFORE UPDATE OR DELETE ON strategy_feedback_artifact
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

COMMENT ON TABLE strategy_fill_allocation_batch IS
'Observed manual Fill allocation only; this table cannot create or mutate a physical Position.';

COMMENT ON TABLE strategy_feedback_artifact IS
'Strategy-scoped feedback evidence; production authorization remains forced false.';
