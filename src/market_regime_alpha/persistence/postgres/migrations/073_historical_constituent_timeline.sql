CREATE TABLE free_data_historical_constituent_timeline (
    timeline_id text PRIMARY KEY,
    timeline_hash text NOT NULL CHECK (timeline_hash ~ '^sha256:[0-9a-f]{64}$'),
    start_date date NOT NULL,
    end_date date NOT NULL,
    known_at timestamptz NOT NULL,
    scan_source_manifest_id text NOT NULL,
    scan_source_manifest_hash text NOT NULL CHECK (scan_source_manifest_hash ~ '^sha256:[0-9a-f]{64}$'),
    raw_archive_id text NOT NULL,
    cohort_count integer NOT NULL CHECK (cohort_count > 0),
    query_session_count integer NOT NULL CHECK (query_session_count > 0),
    payload_json jsonb NOT NULL,
    created_at timestamptz NOT NULL,
    CHECK (start_date <= end_date),
    CHECK (payload_json->>'timeline_id' = timeline_id),
    CHECK (payload_json->>'timeline_hash' = timeline_hash),
    CHECK (payload_json->>'schema_version' = 'historical-constituent-timeline/v1')
);

CREATE TABLE free_data_historical_constituent_timeline_cohort (
    timeline_id text NOT NULL REFERENCES free_data_historical_constituent_timeline(timeline_id) ON DELETE RESTRICT,
    ordinal integer NOT NULL CHECK (ordinal > 0),
    effective_date date NOT NULL,
    snapshot_id text NOT NULL REFERENCES free_data_research_universe_snapshot(snapshot_id) ON DELETE RESTRICT,
    snapshot_hash text NOT NULL CHECK (snapshot_hash ~ '^sha256:[0-9a-f]{64}$'),
    PRIMARY KEY (timeline_id, ordinal),
    UNIQUE (timeline_id, effective_date),
    UNIQUE (timeline_id, snapshot_id)
);

CREATE INDEX free_data_historical_constituent_timeline_range_idx
ON free_data_historical_constituent_timeline(start_date, end_date, timeline_id);

CREATE INDEX free_data_historical_constituent_timeline_cohort_date_idx
ON free_data_historical_constituent_timeline_cohort(timeline_id, effective_date);

CREATE INDEX free_data_historical_constituent_timeline_cohort_snapshot_idx
ON free_data_historical_constituent_timeline_cohort(snapshot_id);

CREATE TRIGGER free_data_historical_constituent_timeline_no_update
BEFORE UPDATE OR DELETE ON free_data_historical_constituent_timeline
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER free_data_historical_constituent_timeline_cohort_no_update
BEFORE UPDATE OR DELETE ON free_data_historical_constituent_timeline_cohort
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
