-- Store large immutable Historical component payloads in Artifact Root while
-- retaining PostgreSQL identity, lineage, locator and physical verification.

ALTER TABLE historical_corpus_session_component
ADD COLUMN payload_storage text NOT NULL DEFAULT 'INLINE_JSONB',
ADD COLUMN payload_locator text,
ADD COLUMN payload_physical_hash text,
ADD COLUMN payload_size_bytes bigint,
ADD COLUMN payload_logical_size_bytes bigint;

ALTER TABLE historical_corpus_session_component
ALTER COLUMN payload_storage DROP DEFAULT;

ALTER TABLE historical_corpus_session_component
ADD CONSTRAINT historical_corpus_session_component_payload_storage_check CHECK (
    payload_storage IN ('INLINE_JSONB', 'ARTIFACT_PHYSICAL_V1')
),
ADD CONSTRAINT historical_corpus_session_component_physical_payload_check CHECK (
    (
        payload_storage = 'INLINE_JSONB'
        AND payload_locator IS NULL
        AND payload_physical_hash IS NULL
        AND payload_size_bytes IS NULL
        AND payload_logical_size_bytes IS NULL
    )
    OR
    (
        payload_storage = 'ARTIFACT_PHYSICAL_V1'
        AND payload_locator ~ '^artifact-root-v1/[A-Za-z0-9._/-]+$'
        AND payload_physical_hash ~ '^sha256:[0-9a-f]{64}$'
        AND payload_size_bytes > 0
        AND payload_logical_size_bytes > 0
    )
);

ALTER TABLE historical_corpus_session_component
DROP CONSTRAINT historical_corpus_session_component_payload_projection_check;

ALTER TABLE historical_corpus_session_component
ADD CONSTRAINT historical_corpus_session_component_payload_projection_check CHECK (
    payload_json->>'component_id' = component_id
    AND payload_json->>'component_hash' = component_hash
    AND payload_json->>'run_id' = run_id
    AND payload_json->>'session_id' = session_id
    AND (payload_json->>'trading_date')::date = trading_date
    AND payload_json->>'component_kind' = component_kind
    AND (payload_json->>'source_max_event_time')::timestamptz = source_max_event_time
    AND (payload_json->>'materialized_at')::timestamptz = materialized_at
    AND (
        (
            payload_storage = 'INLINE_JSONB'
            AND payload_json->>'schema_version' = 'historical-session-component/v1'
        )
        OR
        (
            payload_storage = 'ARTIFACT_PHYSICAL_V1'
            AND payload_json->>'schema_version' =
                'historical-session-component-external-projection/v1'
            AND payload_json->>'payload_locator' = payload_locator
            AND payload_json->>'payload_physical_hash' = payload_physical_hash
            AND (payload_json->>'payload_size_bytes')::bigint = payload_size_bytes
            AND (payload_json->>'payload_logical_size_bytes')::bigint =
                payload_logical_size_bytes
        )
    )
);

COMMENT ON COLUMN historical_corpus_session_component.payload_storage IS
'INLINE_JSONB preserves V1 owners; ARTIFACT_PHYSICAL_V1 stores an exact, reversible immutable physical encoding at the PostgreSQL-owned locator.';

COMMENT ON COLUMN historical_corpus_session_component.payload_locator IS
'Exact Artifact Root locator; never discovered through latest-file scans.';
