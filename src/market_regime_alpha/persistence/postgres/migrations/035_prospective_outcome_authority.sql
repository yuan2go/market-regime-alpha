CREATE TABLE prospective_outcome_settlement (
    settlement_id text PRIMARY KEY,
    settlement_hash text NOT NULL UNIQUE CHECK (
        settlement_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    shadow_decision_id text NOT NULL UNIQUE
        REFERENCES shadow_research_decision(decision_id) ON DELETE RESTRICT,
    shadow_session_id text NOT NULL
        REFERENCES shadow_research_session(session_id) ON DELETE RESTRICT,
    run_id text NOT NULL,
    tick_id text NOT NULL,
    summary_id text NOT NULL
        REFERENCES research_daily_summary(summary_id) ON DELETE RESTRICT,
    next_session_date date NOT NULL,
    source_archive_id text NOT NULL,
    source_archive_hash text NOT NULL CHECK (
        source_archive_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    source_dataset_id text NOT NULL,
    source_dataset_hash text NOT NULL CHECK (
        source_dataset_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    factual_evidence_id text NOT NULL,
    factual_evidence_hash text NOT NULL CHECK (
        factual_evidence_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    availability_status text NOT NULL CHECK (
        availability_status IN ('COMPLETE', 'PARTIAL', 'UNAVAILABLE')
    ),
    outcome_available_at timestamptz NOT NULL,
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' = 'prospective-shadow-outcome/v1'
    ),
    created_at timestamptz NOT NULL,
    FOREIGN KEY (run_id, tick_id)
        REFERENCES continuous_runtime_tick(run_id, tick_id) ON DELETE RESTRICT,
    CHECK (created_at >= outcome_available_at)
);

CREATE INDEX prospective_outcome_session_idx
ON prospective_outcome_settlement(shadow_session_id);

CREATE INDEX prospective_outcome_tick_idx
ON prospective_outcome_settlement(run_id, tick_id);

CREATE INDEX prospective_outcome_summary_idx
ON prospective_outcome_settlement(summary_id);

CREATE TRIGGER prospective_outcome_settlement_no_update
BEFORE UPDATE OR DELETE ON prospective_outcome_settlement
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
