CREATE TABLE research_daily_summary (
    summary_id text PRIMARY KEY,
    content_hash text NOT NULL UNIQUE
        CHECK (content_hash ~ '^sha256:[0-9a-f]{64}$'),
    runtime_mode text NOT NULL CHECK (runtime_mode IN ('RESEARCH', 'SHADOW')),
    run_id text NOT NULL,
    tick_id text NOT NULL,
    trading_date date NOT NULL,
    decision_time timestamptz NOT NULL,
    provider_profile_id text NOT NULL,
    source_manifest_id text NOT NULL,
    source_manifest_hash text NOT NULL
        CHECK (source_manifest_hash ~ '^sha256:[0-9a-f]{64}$'),
    dataset_id text NOT NULL,
    dataset_hash text NOT NULL CHECK (dataset_hash ~ '^sha256:[0-9a-f]{64}$'),
    feature_bundle_id text NOT NULL,
    feature_bundle_hash text NOT NULL
        CHECK (feature_bundle_hash ~ '^sha256:[0-9a-f]{64}$'),
    data_eligibility text NOT NULL CHECK (data_eligibility IN (
        'UNQUALIFIED', 'EXPLORATORY', 'REHEARSAL', 'FORMAL_RESEARCH'
    )),
    evidence_ceiling text NOT NULL CHECK (evidence_ceiling IN (
        'FIXTURE', 'REPLAY', 'FREE_DATA_EXPLORATORY', 'PIT_INCOMPLETE',
        'FORMAL_PIT_CANDIDATE', 'FORMAL_PIT_PROVIDER'
    )),
    outcome text NOT NULL CHECK (outcome IN (
        'NO_ACTION', 'WATCH', 'RESEARCH_CANDIDATE', 'DATA_INSUFFICIENT',
        'MODEL_NOT_QUALIFIED_FOR_MODE'
    )),
    revision bigint NOT NULL CHECK (revision >= 1),
    previous_summary_id text REFERENCES research_daily_summary(summary_id),
    correction_of_summary_id text REFERENCES research_daily_summary(summary_id),
    idempotency_key text NOT NULL UNIQUE,
    run_claim_id text NOT NULL,
    fencing_token bigint NOT NULL CHECK (fencing_token >= 1),
    tick_version bigint NOT NULL CHECK (tick_version >= 1),
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' = 'research-daily-summary/v1'
    ),
    created_at timestamptz NOT NULL,
    FOREIGN KEY (run_id, tick_id)
        REFERENCES continuous_runtime_tick(run_id, tick_id) ON DELETE RESTRICT,
    CHECK ((revision = 1) = (previous_summary_id IS NULL)),
    CHECK ((revision = 1) = (correction_of_summary_id IS NULL)),
    CHECK (created_at >= decision_time)
);

CREATE UNIQUE INDEX research_daily_summary_original_tick_mode_idx
ON research_daily_summary(run_id, tick_id, runtime_mode)
WHERE correction_of_summary_id IS NULL;

CREATE INDEX research_daily_summary_date_mode_idx
ON research_daily_summary(trading_date, runtime_mode, decision_time);

CREATE INDEX research_daily_summary_previous_idx
ON research_daily_summary(previous_summary_id);

CREATE INDEX research_daily_summary_correction_idx
ON research_daily_summary(correction_of_summary_id);

CREATE TABLE research_summary_stage (
    summary_id text NOT NULL REFERENCES research_daily_summary(summary_id),
    stage text NOT NULL CHECK (stage IN (
        'OBSERVATION', 'MARKET_REGIME', 'ETF_ROTATION', 'THEME_ROTATION',
        'CAPITAL_STATE', 'DYNAMIC_POOL', 'CANDIDATE', 'SIGNAL', 'FORECAST'
    )),
    stage_index bigint NOT NULL CHECK (stage_index BETWEEN 1 AND 9),
    evidence_id text NOT NULL,
    evidence_hash text NOT NULL CHECK (evidence_hash ~ '^sha256:[0-9a-f]{64}$'),
    status text NOT NULL CHECK (status IN (
        'COMPLETED', 'DATA_INSUFFICIENT', 'MODEL_NOT_QUALIFIED_FOR_MODE'
    )),
    output_artifact_id text,
    output_artifact_hash text,
    selection_receipt_id text,
    selection_receipt_hash text,
    available_at timestamptz NOT NULL,
    data_eligibility text NOT NULL CHECK (data_eligibility IN (
        'UNQUALIFIED', 'EXPLORATORY', 'REHEARSAL', 'FORMAL_RESEARCH'
    )),
    evidence_ceiling text NOT NULL CHECK (evidence_ceiling IN (
        'FIXTURE', 'REPLAY', 'FREE_DATA_EXPLORATORY', 'PIT_INCOMPLETE',
        'FORMAL_PIT_CANDIDATE', 'FORMAL_PIT_PROVIDER'
    )),
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' = 'research-stage-evidence/v1'
    ),
    PRIMARY KEY (summary_id, stage),
    UNIQUE (summary_id, stage_index),
    CHECK ((output_artifact_id IS NULL) = (output_artifact_hash IS NULL)),
    CHECK (
        output_artifact_hash IS NULL
        OR output_artifact_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    CHECK ((selection_receipt_id IS NULL) = (selection_receipt_hash IS NULL)),
    CHECK (
        selection_receipt_hash IS NULL
        OR selection_receipt_hash ~ '^sha256:[0-9a-f]{64}$'
    )
);

CREATE INDEX research_summary_stage_status_idx
ON research_summary_stage(status, stage);

CREATE TRIGGER research_daily_summary_no_update
BEFORE UPDATE ON research_daily_summary
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER research_daily_summary_no_delete
BEFORE DELETE ON research_daily_summary
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER research_summary_stage_no_update
BEFORE UPDATE ON research_summary_stage
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER research_summary_stage_no_delete
BEFORE DELETE ON research_summary_stage
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
