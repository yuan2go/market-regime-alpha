CREATE TABLE etf_theme_reference_snapshot (
    snapshot_id text PRIMARY KEY,
    snapshot_hash text NOT NULL UNIQUE CHECK (
        snapshot_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    reference_version text NOT NULL UNIQUE,
    data_eligibility text NOT NULL CHECK (data_eligibility = 'EXPLORATORY'),
    evidence_ceiling text NOT NULL CHECK (
        evidence_ceiling IN ('FREE_DATA_EXPLORATORY', 'PIT_INCOMPLETE')
    ),
    available_at timestamptz NOT NULL,
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' = 'etf-theme-reference-snapshot/v1'
    ),
    artifact_locator text NOT NULL,
    created_at timestamptz NOT NULL,
    CHECK (created_at >= available_at)
);

CREATE INDEX etf_theme_reference_asof_idx
ON etf_theme_reference_snapshot(available_at, created_at, snapshot_id);

CREATE TRIGGER etf_theme_reference_snapshot_no_update
BEFORE UPDATE OR DELETE ON etf_theme_reference_snapshot
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
