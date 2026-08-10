CREATE TABLE free_data_research_universe_snapshot (
    snapshot_id text PRIMARY KEY,
    snapshot_hash text NOT NULL UNIQUE CHECK (
        snapshot_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    as_of_date date NOT NULL,
    known_at timestamptz NOT NULL,
    provider_id text NOT NULL,
    source_manifest_id text NOT NULL,
    source_manifest_hash text NOT NULL CHECK (
        source_manifest_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    raw_archive_id text NOT NULL,
    evidence_origin text NOT NULL CHECK (evidence_origin IN (
        'REAL_FREE_PROVIDER_OBSERVATION', 'ARCHIVED_REPLAY', 'ENGINEERING_FIXTURE'
    )),
    data_eligibility text NOT NULL CHECK (data_eligibility = 'EXPLORATORY'),
    evidence_ceiling text NOT NULL CHECK (evidence_ceiling = 'PIT_INCOMPLETE'),
    formal_pit boolean NOT NULL DEFAULT false CHECK (NOT formal_pit),
    security_master_count integer NOT NULL CHECK (security_master_count > 0),
    included_count integer NOT NULL CHECK (
        included_count >= 0 AND included_count <= security_master_count
    ),
    unknown_count integer NOT NULL CHECK (
        unknown_count >= 0 AND unknown_count <= security_master_count
    ),
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' = 'free-research-universe-snapshot/v1'
    ),
    created_at timestamptz NOT NULL
);

CREATE INDEX free_data_research_universe_asof_idx
ON free_data_research_universe_snapshot(as_of_date, known_at, snapshot_id);

CREATE TABLE free_data_research_universe_member (
    snapshot_id text NOT NULL REFERENCES free_data_research_universe_snapshot(snapshot_id) ON DELETE RESTRICT,
    symbol text NOT NULL,
    membership_status text NOT NULL CHECK (
        membership_status IN ('INCLUDED', 'EXCLUDED', 'UNKNOWN')
    ),
    listing_status text NOT NULL CHECK (
        listing_status IN ('LISTED', 'DELISTED', 'UNKNOWN')
    ),
    payload_json jsonb NOT NULL CHECK (jsonb_typeof(payload_json) = 'object'),
    PRIMARY KEY (snapshot_id, symbol)
);

CREATE TRIGGER free_data_research_universe_snapshot_no_update
BEFORE UPDATE OR DELETE ON free_data_research_universe_snapshot
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER free_data_research_universe_member_no_update
BEFORE UPDATE OR DELETE ON free_data_research_universe_member
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

ALTER TABLE etf_theme_reference_snapshot
DROP CONSTRAINT etf_theme_reference_snapshot_payload_json_check;

ALTER TABLE etf_theme_reference_snapshot
ADD CONSTRAINT etf_theme_reference_snapshot_payload_json_check CHECK (
    jsonb_typeof(payload_json) = 'object'
    AND payload_json->>'schema_version' IN (
        'etf-theme-reference-snapshot/v1',
        'etf-theme-reference-snapshot/v2'
    )
);
