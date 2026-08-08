ALTER TABLE decision_runtime_receipt
ADD COLUMN lease_expires_at timestamptz;

ALTER TABLE decision_runtime_receipt
DROP CONSTRAINT decision_runtime_receipt_payload_json_check;

ALTER TABLE decision_runtime_receipt
ADD CONSTRAINT decision_runtime_receipt_payload_json_check CHECK (
    jsonb_typeof(payload_json) = 'object'
    AND (
        payload_json->>'schema_version' = 'decision_runtime_receipt/v2'
        OR payload_json->>'schema_version' IS NULL
    )
);

ALTER TABLE decision_runtime_receipt
ADD CONSTRAINT decision_runtime_receipt_lease_window_check CHECK (
    (payload_json->>'schema_version' IS NULL AND lease_expires_at IS NULL)
    OR (
        payload_json->>'schema_version' = 'decision_runtime_receipt/v2'
        AND lease_expires_at > created_at
    )
);

CREATE FUNCTION enforce_decision_runtime_receipt_v2_insert()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.payload_json->>'schema_version'
            IS DISTINCT FROM 'decision_runtime_receipt/v2'
       OR NEW.lease_expires_at IS NULL THEN
        RAISE EXCEPTION
            'new Decision Runtime receipts require v2 payload and lease authority'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER decision_runtime_receipt_v2_insert_guard
BEFORE INSERT ON decision_runtime_receipt
FOR EACH ROW EXECUTE FUNCTION enforce_decision_runtime_receipt_v2_insert();

ALTER TABLE daily_decision_summary
DROP CONSTRAINT daily_decision_summary_lifecycle_state_check;

ALTER TABLE daily_decision_summary
ADD CONSTRAINT daily_decision_summary_lifecycle_state_check CHECK (
    lifecycle_state IN (
        'WINDOW_NOT_OPEN', 'PREVIEW_AVAILABLE',
        'WAITING_FOR_REQUIRED_EVIDENCE', 'FINALIZING',
        'FINALIZED', 'BLOCKED', 'CORRECTED'
    )
);

CREATE TABLE state_research_stage_authority (
    run_id text NOT NULL,
    tick_id text NOT NULL,
    state_receipt_id text NOT NULL REFERENCES state_runtime_receipt(receipt_id),
    stage text NOT NULL CHECK (stage IN (
        'OBSERVATION', 'MARKET_REGIME', 'ETF_ROTATION', 'THEME_ROTATION',
        'CAPITAL_STATE', 'DYNAMIC_POOL', 'CANDIDATE', 'SIGNAL', 'FORECAST'
    )),
    artifact_id text NOT NULL,
    artifact_hash text NOT NULL CHECK (artifact_hash ~ '^sha256:[0-9a-f]{64}$'),
    available_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL,
    PRIMARY KEY (run_id, tick_id, stage),
    FOREIGN KEY (run_id, tick_id)
        REFERENCES continuous_runtime_tick(run_id, tick_id) ON DELETE RESTRICT,
    CHECK (available_at <= created_at)
);

CREATE INDEX state_research_stage_authority_receipt_idx
ON state_research_stage_authority(state_receipt_id);

CREATE TABLE reconciliation_tolerance_configuration (
    configuration_id text PRIMARY KEY,
    configuration_hash text NOT NULL UNIQUE
        CHECK (configuration_hash ~ '^sha256:[0-9a-f]{64}$'),
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' = 'reconciliation_tolerance/v1'
    ),
    created_at timestamptz NOT NULL
);

CREATE TABLE decision_risk_configuration (
    configuration_id text PRIMARY KEY,
    configuration_hash text NOT NULL UNIQUE
        CHECK (configuration_hash ~ '^sha256:[0-9a-f]{64}$'),
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' = 'decision_risk_configuration/v1'
    ),
    created_at timestamptz NOT NULL
);

ALTER TABLE account_reconciliation
ADD CONSTRAINT account_reconciliation_tolerance_configuration_fk
FOREIGN KEY (tolerance_configuration_id)
REFERENCES reconciliation_tolerance_configuration(configuration_id)
NOT VALID;

ALTER TABLE research_portfolio_proposal
ADD CONSTRAINT research_portfolio_risk_configuration_fk
FOREIGN KEY (risk_configuration_id)
REFERENCES decision_risk_configuration(configuration_id)
NOT VALID;

ALTER TABLE independent_risk_decision
ADD CONSTRAINT independent_risk_configuration_fk
FOREIGN KEY (risk_configuration_id)
REFERENCES decision_risk_configuration(configuration_id)
NOT VALID;

CREATE INDEX account_reconciliation_tolerance_configuration_idx
ON account_reconciliation(tolerance_configuration_id);
CREATE INDEX research_portfolio_risk_configuration_idx
ON research_portfolio_proposal(risk_configuration_id);
CREATE INDEX independent_risk_configuration_idx
ON independent_risk_decision(risk_configuration_id);

CREATE TABLE decision_position_settlement_evidence (
    evidence_id text PRIMARY KEY,
    content_hash text NOT NULL UNIQUE
        CHECK (content_hash ~ '^sha256:[0-9a-f]{64}$'),
    account_id text NOT NULL,
    as_of_time timestamptz NOT NULL,
    run_id text NOT NULL,
    tick_id text NOT NULL,
    claim_id text NOT NULL,
    fencing_token bigint NOT NULL CHECK (fencing_token >= 1),
    tick_version bigint NOT NULL CHECK (tick_version >= 1),
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' = 'position_settlement_evidence/v1'
    ),
    created_at timestamptz NOT NULL,
    UNIQUE (account_id, as_of_time),
    FOREIGN KEY (run_id, tick_id)
        REFERENCES continuous_runtime_tick(run_id, tick_id)
);

CREATE INDEX decision_position_settlement_evidence_tick_idx
ON decision_position_settlement_evidence(run_id, tick_id);

CREATE TABLE decision_fill_account_authority (
    authority_id text PRIMARY KEY,
    content_hash text NOT NULL UNIQUE
        CHECK (content_hash ~ '^sha256:[0-9a-f]{64}$'),
    account_id text NOT NULL,
    as_of_time timestamptz NOT NULL,
    fill_ledger_head text NOT NULL
        CHECK (fill_ledger_head ~ '^sha256:[0-9a-f]{64}$'),
    fill_ledger_complete boolean NOT NULL,
    run_id text NOT NULL,
    tick_id text NOT NULL,
    claim_id text NOT NULL,
    fencing_token bigint NOT NULL CHECK (fencing_token >= 1),
    tick_version bigint NOT NULL CHECK (tick_version >= 1),
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' = 'fill_derived_account_authority/v2'
    ),
    created_at timestamptz NOT NULL,
    UNIQUE (account_id, as_of_time),
    FOREIGN KEY (run_id, tick_id)
        REFERENCES continuous_runtime_tick(run_id, tick_id)
);

CREATE INDEX decision_fill_account_authority_tick_idx
ON decision_fill_account_authority(run_id, tick_id);

CREATE TABLE decision_replay_import (
    replay_session_id text NOT NULL,
    artifact_kind text NOT NULL CHECK (artifact_kind IN (
        'RUNTIME_INPUT', 'MANUAL_OBSERVATION', 'FILL_AUTHORITY',
        'RECONCILIATION', 'PREVIEW_SUMMARY', 'PORTFOLIO_PROPOSAL',
        'RISK_DECISION', 'TERMINAL_SUMMARY', 'RUNTIME_RECEIPT',
        'RISK_CONFIGURATION', 'RECONCILIATION_TOLERANCE',
        'SETTLEMENT_EVIDENCE'
    )),
    artifact_id text NOT NULL,
    content_hash text NOT NULL CHECK (content_hash ~ '^sha256:[0-9a-f]{64}$'),
    payload_json jsonb NOT NULL CHECK (jsonb_typeof(payload_json) = 'object'),
    imported_at timestamptz NOT NULL,
    PRIMARY KEY (replay_session_id, artifact_kind, artifact_id)
);

CREATE TRIGGER state_research_stage_authority_no_update
BEFORE UPDATE ON state_research_stage_authority
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER state_research_stage_authority_no_delete
BEFORE DELETE ON state_research_stage_authority
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER reconciliation_tolerance_configuration_no_update
BEFORE UPDATE ON reconciliation_tolerance_configuration
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER reconciliation_tolerance_configuration_no_delete
BEFORE DELETE ON reconciliation_tolerance_configuration
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER decision_risk_configuration_no_update
BEFORE UPDATE ON decision_risk_configuration
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER decision_risk_configuration_no_delete
BEFORE DELETE ON decision_risk_configuration
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER decision_position_settlement_evidence_no_update
BEFORE UPDATE ON decision_position_settlement_evidence
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER decision_position_settlement_evidence_no_delete
BEFORE DELETE ON decision_position_settlement_evidence
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER decision_fill_account_authority_no_update
BEFORE UPDATE ON decision_fill_account_authority
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER decision_fill_account_authority_no_delete
BEFORE DELETE ON decision_fill_account_authority
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER decision_replay_import_no_update
BEFORE UPDATE ON decision_replay_import
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER decision_replay_import_no_delete
BEFORE DELETE ON decision_replay_import
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
