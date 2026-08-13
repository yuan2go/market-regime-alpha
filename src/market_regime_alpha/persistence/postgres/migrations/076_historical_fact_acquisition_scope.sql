-- Phase E3 immutable acquisition scope for corporate-action absence semantics.

ALTER TABLE free_data_historical_security_fact_set
ADD COLUMN acquisition_start_date date,
ADD COLUMN acquisition_end_date date,
ADD COLUMN requested_symbols jsonb,
ADD COLUMN universe_scope_references jsonb;

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
        payload_json->>'schema_version' = 'historical-security-facts-owner/v3'
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
        'historical-security-facts-owner/v3'
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
                'historical-security-facts-owner/v3'
            )
            AND jsonb_array_length(payload_json->'coverage_gaps') = coverage_gap_count
        )
    )
);

COMMENT ON COLUMN free_data_historical_security_fact_set.requested_symbols IS
'Exact symbols queried for the v3 fact owner; absence is meaningful only inside this set.';

COMMENT ON COLUMN free_data_historical_security_fact_set.universe_scope_references IS
'Exact constituent cohort/timeline owners from which the acquisition symbol scope was resolved.';
