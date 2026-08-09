ALTER TABLE research_daily_summary
    DROP CONSTRAINT research_daily_summary_payload_json_check;

ALTER TABLE research_daily_summary
    ADD CONSTRAINT research_daily_summary_payload_json_check CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' IN (
            'research-daily-summary/v1', 'research-daily-summary/v2'
        )
    );
