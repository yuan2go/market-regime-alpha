ALTER TABLE continuous_child_run
DROP CONSTRAINT continuous_child_run_child_kind_check;

ALTER TABLE continuous_child_run
ADD CONSTRAINT continuous_child_run_child_kind_check
CHECK (
    child_kind IN (
        'DAILY_DATASET',
        'FEATURE_MATERIALIZATION',
        'STATE_SYSTEM',
        'CONTROLLED_OPERATION',
        'CANONICAL_LIFECYCLE',
        'DECISION_SYSTEM'
    )
);

CREATE TABLE manual_account_observation (
    observation_id text PRIMARY KEY,
    content_hash text NOT NULL CHECK (content_hash ~ '^sha256:[0-9a-f]{64}$'),
    account_id text NOT NULL,
    trading_date date NOT NULL,
    as_of_time timestamptz NOT NULL,
    total_equity numeric(24, 6) NOT NULL CHECK (total_equity >= 0),
    available_cash numeric(24, 6) NOT NULL CHECK (available_cash >= 0),
    frozen_cash numeric(24, 6) NOT NULL CHECK (frozen_cash >= 0),
    source text NOT NULL,
    actor text NOT NULL,
    reason text NOT NULL,
    notes text NOT NULL,
    idempotency_key text NOT NULL UNIQUE,
    command_hash text NOT NULL CHECK (command_hash ~ '^sha256:[0-9a-f]{64}$'),
    revision bigint NOT NULL CHECK (revision >= 1),
    previous_observation_id text REFERENCES manual_account_observation(observation_id),
    payload_json jsonb NOT NULL CHECK (jsonb_typeof(payload_json) = 'object'),
    created_at timestamptz NOT NULL,
    UNIQUE (account_id, trading_date, revision),
    CHECK ((revision = 1) = (previous_observation_id IS NULL)),
    CHECK (available_cash + frozen_cash <= total_equity)
);

CREATE INDEX manual_account_observation_account_date_idx
ON manual_account_observation(account_id, trading_date, revision DESC);
CREATE INDEX manual_account_observation_previous_idx
ON manual_account_observation(previous_observation_id);

CREATE TABLE manual_position_observation (
    observation_id text NOT NULL REFERENCES manual_account_observation(observation_id),
    symbol text NOT NULL,
    total_quantity bigint NOT NULL CHECK (total_quantity >= 0),
    available_quantity bigint NOT NULL CHECK (available_quantity >= 0),
    frozen_quantity bigint NOT NULL CHECK (frozen_quantity >= 0),
    average_cost numeric(24, 6),
    observed_market_value numeric(24, 6) NOT NULL CHECK (observed_market_value >= 0),
    notes text NOT NULL,
    payload_json jsonb NOT NULL CHECK (jsonb_typeof(payload_json) = 'object'),
    PRIMARY KEY (observation_id, symbol),
    CHECK (available_quantity + frozen_quantity = total_quantity),
    CHECK ((total_quantity = 0) = (average_cost IS NULL))
);

CREATE TABLE account_reconciliation (
    reconciliation_id text PRIMARY KEY,
    content_hash text NOT NULL CHECK (content_hash ~ '^sha256:[0-9a-f]{64}$'),
    account_id text NOT NULL,
    trading_date date NOT NULL,
    as_of_time timestamptz NOT NULL,
    manual_observation_id text NOT NULL REFERENCES manual_account_observation(observation_id),
    position_snapshot_ids_json jsonb NOT NULL CHECK (jsonb_typeof(position_snapshot_ids_json) = 'array'),
    fill_ledger_head text NOT NULL,
    fill_ledger_complete boolean NOT NULL,
    tolerance_configuration_id text NOT NULL,
    tolerance_configuration_hash text NOT NULL CHECK (tolerance_configuration_hash ~ '^sha256:[0-9a-f]{64}$'),
    status text NOT NULL CHECK (status IN (
        'RECONCILED', 'RECONCILIATION_REQUIRED',
        'DATA_INSUFFICIENT', 'MANUAL_REVIEW_REQUIRED'
    )),
    reason_codes_json jsonb NOT NULL CHECK (jsonb_typeof(reason_codes_json) = 'array'),
    revision bigint NOT NULL CHECK (revision >= 1),
    previous_reconciliation_id text REFERENCES account_reconciliation(reconciliation_id),
    idempotency_key text NOT NULL UNIQUE,
    command_hash text NOT NULL CHECK (command_hash ~ '^sha256:[0-9a-f]{64}$'),
    run_id text NOT NULL,
    tick_id text NOT NULL,
    claim_id text NOT NULL,
    fencing_token bigint NOT NULL CHECK (fencing_token >= 1),
    tick_version bigint NOT NULL CHECK (tick_version >= 1),
    payload_json jsonb NOT NULL CHECK (jsonb_typeof(payload_json) = 'object'),
    created_at timestamptz NOT NULL,
    UNIQUE (account_id, trading_date, revision),
    FOREIGN KEY (run_id, tick_id)
        REFERENCES continuous_runtime_tick(run_id, tick_id),
    CHECK ((revision = 1) = (previous_reconciliation_id IS NULL))
);

CREATE TABLE reconciliation_difference (
    reconciliation_id text NOT NULL REFERENCES account_reconciliation(reconciliation_id),
    difference_index bigint NOT NULL CHECK (difference_index >= 1),
    difference_type text NOT NULL,
    symbol text,
    expected_value numeric(24, 6),
    observed_value numeric(24, 6),
    absolute_difference numeric(24, 6),
    reason_code text NOT NULL,
    payload_json jsonb NOT NULL CHECK (jsonb_typeof(payload_json) = 'object'),
    PRIMARY KEY (reconciliation_id, difference_index)
);

CREATE TABLE daily_decision_summary (
    summary_id text PRIMARY KEY,
    content_hash text NOT NULL CHECK (content_hash ~ '^sha256:[0-9a-f]{64}$'),
    account_id text NOT NULL,
    trading_date date NOT NULL,
    strategy_configuration_id text NOT NULL,
    strategy_configuration_hash text NOT NULL CHECK (strategy_configuration_hash ~ '^sha256:[0-9a-f]{64}$'),
    as_of_time timestamptz NOT NULL,
    available_at timestamptz NOT NULL,
    lifecycle_state text NOT NULL CHECK (lifecycle_state IN (
        'WINDOW_NOT_OPEN', 'PREVIEW_AVAILABLE',
        'WAITING_FOR_REQUIRED_EVIDENCE', 'FINALIZING',
        'FINALIZED', 'BLOCKED', 'CORRECTED'
    )),
    outcome text NOT NULL CHECK (outcome IN (
        'NO_ACTION', 'WATCH', 'RESEARCH_BUY_CANDIDATE',
        'DATA_INSUFFICIENT', 'ACCOUNT_NOT_CALIBRATED',
        'RECONCILIATION_REQUIRED', 'RISK_BLOCKED',
        'MODEL_NOT_QUALIFIED'
    )),
    manual_observation_id text NOT NULL REFERENCES manual_account_observation(observation_id),
    reconciliation_id text NOT NULL REFERENCES account_reconciliation(reconciliation_id),
    revision bigint NOT NULL CHECK (revision >= 1),
    previous_summary_id text REFERENCES daily_decision_summary(summary_id),
    correction_of_summary_id text REFERENCES daily_decision_summary(summary_id),
    idempotency_key text NOT NULL UNIQUE,
    command_hash text NOT NULL CHECK (command_hash ~ '^sha256:[0-9a-f]{64}$'),
    run_id text NOT NULL,
    tick_id text NOT NULL,
    claim_id text NOT NULL,
    fencing_token bigint NOT NULL CHECK (fencing_token >= 1),
    tick_version bigint NOT NULL CHECK (tick_version >= 1),
    lineage_json jsonb NOT NULL CHECK (jsonb_typeof(lineage_json) = 'object'),
    payload_json jsonb NOT NULL CHECK (jsonb_typeof(payload_json) = 'object'),
    created_at timestamptz NOT NULL,
    FOREIGN KEY (run_id, tick_id)
        REFERENCES continuous_runtime_tick(run_id, tick_id),
    CHECK (available_at <= as_of_time),
    CHECK ((revision = 1) = (previous_summary_id IS NULL)),
    CHECK (lifecycle_state != 'CORRECTED' OR correction_of_summary_id IS NOT NULL)
);

CREATE UNIQUE INDEX daily_decision_one_original_terminal_idx
ON daily_decision_summary(account_id, trading_date, strategy_configuration_id)
WHERE lifecycle_state IN ('FINALIZED', 'BLOCKED')
  AND correction_of_summary_id IS NULL;

CREATE TABLE daily_summary_candidate (
    summary_id text NOT NULL REFERENCES daily_decision_summary(summary_id),
    symbol text NOT NULL,
    candidate_rank bigint NOT NULL CHECK (candidate_rank >= 1),
    candidate_score numeric(24, 10) NOT NULL,
    current_quantity bigint NOT NULL CHECK (current_quantity >= 0),
    research_exposure_ceiling numeric(12, 8) NOT NULL CHECK (
        research_exposure_ceiling >= 0 AND research_exposure_ceiling <= 1
    ),
    payload_json jsonb NOT NULL CHECK (jsonb_typeof(payload_json) = 'object'),
    PRIMARY KEY (summary_id, symbol),
    UNIQUE (summary_id, candidate_rank)
);

CREATE TABLE research_portfolio_proposal (
    proposal_id text PRIMARY KEY,
    content_hash text NOT NULL CHECK (content_hash ~ '^sha256:[0-9a-f]{64}$'),
    account_id text NOT NULL,
    trading_date date NOT NULL,
    as_of_time timestamptz NOT NULL,
    summary_id text NOT NULL REFERENCES daily_decision_summary(summary_id),
    manual_observation_id text NOT NULL REFERENCES manual_account_observation(observation_id),
    reconciliation_id text NOT NULL REFERENCES account_reconciliation(reconciliation_id),
    risk_configuration_id text NOT NULL,
    risk_configuration_hash text NOT NULL CHECK (risk_configuration_hash ~ '^sha256:[0-9a-f]{64}$'),
    status text NOT NULL CHECK (status IN (
        'PROPOSED', 'NO_ACTION', 'DATA_INSUFFICIENT',
        'MODEL_NOT_QUALIFIED', 'ORDERABILITY_UNKNOWN',
        'RECONCILIATION_REQUIRED'
    )),
    reason_codes_json jsonb NOT NULL CHECK (jsonb_typeof(reason_codes_json) = 'array'),
    idempotency_key text NOT NULL UNIQUE,
    command_hash text NOT NULL CHECK (command_hash ~ '^sha256:[0-9a-f]{64}$'),
    run_id text NOT NULL,
    tick_id text NOT NULL,
    claim_id text NOT NULL,
    fencing_token bigint NOT NULL CHECK (fencing_token >= 1),
    tick_version bigint NOT NULL CHECK (tick_version >= 1),
    payload_json jsonb NOT NULL CHECK (jsonb_typeof(payload_json) = 'object'),
    created_at timestamptz NOT NULL,
    FOREIGN KEY (run_id, tick_id)
        REFERENCES continuous_runtime_tick(run_id, tick_id)
);

CREATE TABLE research_portfolio_line (
    proposal_id text NOT NULL REFERENCES research_portfolio_proposal(proposal_id),
    symbol text NOT NULL,
    current_weight numeric(12, 8) NOT NULL CHECK (current_weight >= 0 AND current_weight <= 1),
    proposed_research_weight numeric(12, 8) NOT NULL CHECK (proposed_research_weight >= 0 AND proposed_research_weight <= 1),
    weight_delta numeric(12, 8) NOT NULL,
    research_amount numeric(24, 6) NOT NULL CHECK (research_amount >= 0),
    payload_json jsonb NOT NULL CHECK (jsonb_typeof(payload_json) = 'object'),
    PRIMARY KEY (proposal_id, symbol)
);

CREATE TABLE independent_risk_decision (
    risk_decision_id text PRIMARY KEY,
    content_hash text NOT NULL CHECK (content_hash ~ '^sha256:[0-9a-f]{64}$'),
    proposal_id text NOT NULL REFERENCES research_portfolio_proposal(proposal_id),
    account_id text NOT NULL,
    trading_date date NOT NULL,
    as_of_time timestamptz NOT NULL,
    result text NOT NULL CHECK (result IN (
        'RESEARCH_APPROVED', 'RESEARCH_REDUCED', 'RISK_BLOCKED',
        'DATA_INSUFFICIENT', 'ACCOUNT_NOT_CALIBRATED',
        'RECONCILIATION_REQUIRED', 'MODEL_NOT_QUALIFIED',
        'ORDERABILITY_UNKNOWN'
    )),
    approved_research_weight numeric(12, 8) NOT NULL CHECK (
        approved_research_weight >= 0 AND approved_research_weight <= 1
    ),
    reason_codes_json jsonb NOT NULL CHECK (jsonb_typeof(reason_codes_json) = 'array'),
    risk_configuration_id text NOT NULL,
    risk_configuration_hash text NOT NULL CHECK (risk_configuration_hash ~ '^sha256:[0-9a-f]{64}$'),
    idempotency_key text NOT NULL UNIQUE,
    command_hash text NOT NULL CHECK (command_hash ~ '^sha256:[0-9a-f]{64}$'),
    run_id text NOT NULL,
    tick_id text NOT NULL,
    claim_id text NOT NULL,
    fencing_token bigint NOT NULL CHECK (fencing_token >= 1),
    tick_version bigint NOT NULL CHECK (tick_version >= 1),
    payload_json jsonb NOT NULL CHECK (jsonb_typeof(payload_json) = 'object'),
    created_at timestamptz NOT NULL,
    FOREIGN KEY (run_id, tick_id)
        REFERENCES continuous_runtime_tick(run_id, tick_id)
);

CREATE TABLE decision_runtime_receipt (
    receipt_id text PRIMARY KEY,
    receipt_hash text NOT NULL CHECK (receipt_hash ~ '^sha256:[0-9a-f]{64}$'),
    run_id text NOT NULL,
    tick_id text NOT NULL,
    claim_id text NOT NULL,
    fencing_token bigint NOT NULL CHECK (fencing_token >= 1),
    tick_version bigint NOT NULL CHECK (tick_version >= 1),
    state_receipt_id text NOT NULL,
    state_receipt_hash text NOT NULL CHECK (state_receipt_hash ~ '^sha256:[0-9a-f]{64}$'),
    reconciliation_id text REFERENCES account_reconciliation(reconciliation_id),
    summary_id text REFERENCES daily_decision_summary(summary_id),
    proposal_id text REFERENCES research_portfolio_proposal(proposal_id),
    risk_decision_id text REFERENCES independent_risk_decision(risk_decision_id),
    status text NOT NULL CHECK (status IN ('COMPLETED', 'BLOCKED')),
    stage_receipts_json jsonb NOT NULL CHECK (jsonb_typeof(stage_receipts_json) = 'array'),
    payload_json jsonb NOT NULL CHECK (jsonb_typeof(payload_json) = 'object'),
    created_at timestamptz NOT NULL,
    UNIQUE (run_id, tick_id),
    FOREIGN KEY (run_id, tick_id)
        REFERENCES continuous_runtime_tick(run_id, tick_id)
);

CREATE INDEX account_reconciliation_manual_observation_idx
ON account_reconciliation(manual_observation_id);
CREATE INDEX account_reconciliation_previous_idx
ON account_reconciliation(previous_reconciliation_id);
CREATE INDEX account_reconciliation_tick_idx
ON account_reconciliation(run_id, tick_id);
CREATE INDEX daily_decision_summary_manual_observation_idx
ON daily_decision_summary(manual_observation_id);
CREATE INDEX daily_decision_summary_reconciliation_idx
ON daily_decision_summary(reconciliation_id);
CREATE INDEX daily_decision_summary_previous_idx
ON daily_decision_summary(previous_summary_id);
CREATE INDEX daily_decision_summary_correction_idx
ON daily_decision_summary(correction_of_summary_id);
CREATE INDEX daily_decision_summary_tick_idx
ON daily_decision_summary(run_id, tick_id);
CREATE INDEX research_portfolio_summary_idx
ON research_portfolio_proposal(summary_id);
CREATE INDEX research_portfolio_manual_observation_idx
ON research_portfolio_proposal(manual_observation_id);
CREATE INDEX research_portfolio_reconciliation_idx
ON research_portfolio_proposal(reconciliation_id);
CREATE INDEX research_portfolio_tick_idx
ON research_portfolio_proposal(run_id, tick_id);
CREATE INDEX independent_risk_proposal_idx
ON independent_risk_decision(proposal_id);
CREATE INDEX independent_risk_tick_idx
ON independent_risk_decision(run_id, tick_id);
CREATE INDEX decision_runtime_reconciliation_idx
ON decision_runtime_receipt(reconciliation_id);
CREATE INDEX decision_runtime_summary_idx
ON decision_runtime_receipt(summary_id);
CREATE INDEX decision_runtime_proposal_idx
ON decision_runtime_receipt(proposal_id);
CREATE INDEX decision_runtime_risk_idx
ON decision_runtime_receipt(risk_decision_id);

CREATE TRIGGER manual_account_observation_no_update
BEFORE UPDATE ON manual_account_observation
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER manual_account_observation_no_delete
BEFORE DELETE ON manual_account_observation
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER manual_position_observation_no_update
BEFORE UPDATE ON manual_position_observation
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER manual_position_observation_no_delete
BEFORE DELETE ON manual_position_observation
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER account_reconciliation_no_update
BEFORE UPDATE ON account_reconciliation
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER account_reconciliation_no_delete
BEFORE DELETE ON account_reconciliation
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER reconciliation_difference_no_update
BEFORE UPDATE ON reconciliation_difference
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER reconciliation_difference_no_delete
BEFORE DELETE ON reconciliation_difference
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER daily_decision_summary_no_update
BEFORE UPDATE ON daily_decision_summary
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER daily_decision_summary_no_delete
BEFORE DELETE ON daily_decision_summary
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER daily_summary_candidate_no_update
BEFORE UPDATE ON daily_summary_candidate
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER daily_summary_candidate_no_delete
BEFORE DELETE ON daily_summary_candidate
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER research_portfolio_proposal_no_update
BEFORE UPDATE ON research_portfolio_proposal
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER research_portfolio_proposal_no_delete
BEFORE DELETE ON research_portfolio_proposal
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER research_portfolio_line_no_update
BEFORE UPDATE ON research_portfolio_line
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER research_portfolio_line_no_delete
BEFORE DELETE ON research_portfolio_line
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER independent_risk_decision_no_update
BEFORE UPDATE ON independent_risk_decision
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER independent_risk_decision_no_delete
BEFORE DELETE ON independent_risk_decision
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER decision_runtime_receipt_no_update
BEFORE UPDATE ON decision_runtime_receipt
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER decision_runtime_receipt_no_delete
BEFORE DELETE ON decision_runtime_receipt
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
