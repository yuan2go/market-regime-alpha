-- Phase E2 effective-dated free Research Universe snapshot contract.

ALTER TABLE free_data_research_universe_snapshot
DROP CONSTRAINT free_data_research_universe_snapshot_payload_json_check;

ALTER TABLE free_data_research_universe_snapshot
ADD CONSTRAINT free_data_research_universe_snapshot_payload_json_check CHECK (
    jsonb_typeof(payload_json) = 'object'
    AND payload_json->>'schema_version' IN (
        'free-research-universe-snapshot/v1',
        'free-research-universe-snapshot/v2'
    )
    AND (
        payload_json->>'schema_version' <> 'free-research-universe-snapshot/v2'
        OR (
            payload_json->>'selection_basis' = 'HISTORICAL_CONSTITUENT_SNAPSHOT'
            AND (payload_json->>'constituent_effective_date')::date <= as_of_date
            AND jsonb_typeof(payload_json->'constituent_source_reference') = 'object'
        )
    )
);
