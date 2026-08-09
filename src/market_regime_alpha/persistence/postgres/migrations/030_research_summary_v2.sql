ALTER TABLE research_summary_stage
    ADD COLUMN stage_completed_at timestamptz,
    ADD COLUMN result text CHECK (result IN (
        'UNAVAILABLE', 'AVAILABLE', 'EMPTY', 'WATCH', 'RESEARCH_QUALIFIED'
    ));

ALTER TABLE research_summary_stage
    DROP CONSTRAINT research_summary_stage_payload_json_check;

ALTER TABLE research_summary_stage
    ADD CONSTRAINT research_summary_stage_payload_json_check CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' IN (
            'research-stage-evidence/v1', 'research-stage-evidence/v2'
        )
    );

ALTER TABLE research_summary_stage
    ADD CONSTRAINT research_summary_stage_v2_time_check CHECK (
        stage_completed_at IS NULL OR stage_completed_at >= available_at
    );
