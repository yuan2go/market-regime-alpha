-- Phase E3 content-verifiable lightweight identity envelope for fact-set reads.

ALTER TABLE free_data_historical_security_fact_set
DROP CONSTRAINT free_data_historical_security_fact_set_acquisition_scope_check;

ALTER TABLE free_data_historical_security_fact_set
ADD CONSTRAINT free_data_historical_security_fact_set_acquisition_scope_check CHECK (
    (
        payload_json->>'schema_version' IN (
            'historical-security-facts-owner/v1',
            'historical-security-facts-owner/v2'
        )
        AND acquisition_start_date IS NULL
        AND acquisition_end_date IS NULL
        AND requested_symbols IS NULL
        AND universe_scope_references IS NULL
    )
    OR (
        payload_json->>'schema_version' IN (
            'historical-security-facts-owner/v3',
            'historical-security-facts-owner/v4'
        )
        AND acquisition_start_date IS NOT NULL
        AND acquisition_end_date IS NOT NULL
        AND acquisition_start_date <= acquisition_end_date
        AND jsonb_typeof(requested_symbols) = 'array'
        AND jsonb_array_length(requested_symbols) > 0
        AND jsonb_typeof(universe_scope_references) = 'array'
        AND jsonb_array_length(universe_scope_references) > 0
        AND (payload_json->>'acquisition_start_date')::date = acquisition_start_date
        AND (payload_json->>'acquisition_end_date')::date = acquisition_end_date
        AND payload_json->'requested_symbols' = requested_symbols
        AND payload_json->'universe_scope_references' = universe_scope_references
    )
);

ALTER TABLE free_data_historical_security_fact_set
DROP CONSTRAINT free_data_historical_security_fact_set_payload_json_check;

ALTER TABLE free_data_historical_security_fact_set
ADD CONSTRAINT free_data_historical_security_fact_set_payload_json_check CHECK (
    jsonb_typeof(payload_json) = 'object'
    AND payload_json->>'schema_version' IN (
        'historical-security-facts-owner/v1',
        'historical-security-facts-owner/v2',
        'historical-security-facts-owner/v3',
        'historical-security-facts-owner/v4'
    )
    AND payload_json->>'owner_id' = owner_id
    AND payload_json->>'owner_hash' = owner_hash
    AND jsonb_array_length(payload_json->'facts') = fact_count
    AND (
        (
            payload_json->>'schema_version' = 'historical-security-facts-owner/v1'
            AND coverage_gap_count = 0
        )
        OR (
            payload_json->>'schema_version' IN (
                'historical-security-facts-owner/v2',
                'historical-security-facts-owner/v3',
                'historical-security-facts-owner/v4'
            )
            AND jsonb_array_length(payload_json->'coverage_gaps') = coverage_gap_count
        )
    )
    AND (
        payload_json->>'schema_version' <> 'historical-security-facts-owner/v4'
        OR (
            (payload_json->>'fact_count')::integer = fact_count
            AND (payload_json->>'coverage_gap_count')::integer = coverage_gap_count
            AND payload_json->>'facts_hash' ~ '^sha256:[0-9a-f]{64}$'
            AND payload_json->>'coverage_gaps_hash' ~ '^sha256:[0-9a-f]{64}$'
        )
    )
);

COMMENT ON TABLE free_data_historical_security_fact_set IS
'Immutable exploratory historical fact owner; v4 binds a small identity envelope plus exact record-set digests for bounded Decision reads.';
