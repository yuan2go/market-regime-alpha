CREATE TABLE state_runtime_candidate_artifact (
    run_id text NOT NULL,
    tick_id text NOT NULL,
    candidate_id text NOT NULL,
    candidate_hash text NOT NULL CHECK (candidate_hash ~ '^sha256:[0-9a-f]{64}$'),
    stage_artifact_id text NOT NULL,
    stage_artifact_hash text NOT NULL CHECK (stage_artifact_hash ~ '^sha256:[0-9a-f]{64}$'),
    payload_json jsonb NOT NULL CHECK (jsonb_typeof(payload_json) = 'object'),
    created_at timestamptz NOT NULL,
    PRIMARY KEY (run_id, tick_id),
    FOREIGN KEY (run_id, tick_id)
        REFERENCES continuous_runtime_tick(run_id, tick_id)
        ON DELETE RESTRICT
);

ALTER TABLE state_research_stage_authority
    ADD COLUMN reason_codes_json jsonb CHECK (
        reason_codes_json IS NULL OR jsonb_typeof(reason_codes_json) = 'array'
    );

CREATE TRIGGER state_runtime_candidate_artifact_no_update
BEFORE UPDATE ON state_runtime_candidate_artifact
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER state_runtime_candidate_artifact_no_delete
BEFORE DELETE ON state_runtime_candidate_artifact
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

ALTER TABLE research_daily_summary
    DROP CONSTRAINT research_daily_summary_payload_json_check;

ALTER TABLE research_daily_summary
    ADD CONSTRAINT research_daily_summary_payload_json_check CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' IN (
            'research-daily-summary/v1',
            'research-daily-summary/v2',
            'research-daily-summary/v3'
        )
    );
