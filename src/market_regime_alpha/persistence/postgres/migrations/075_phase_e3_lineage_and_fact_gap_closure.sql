-- Phase E3 exact hash-pair lineage and fail-closed corporate-action gaps.

ALTER TABLE free_data_research_universe_snapshot
ADD CONSTRAINT free_data_research_universe_snapshot_id_hash_key
UNIQUE (snapshot_id, snapshot_hash);

ALTER TABLE free_data_historical_constituent_timeline_cohort
ADD CONSTRAINT free_data_historical_constituent_timeline_cohort_snapshot_owner_fk
FOREIGN KEY (snapshot_id, snapshot_hash)
REFERENCES free_data_research_universe_snapshot(snapshot_id, snapshot_hash)
ON DELETE RESTRICT;

ALTER TABLE historical_corpus_outcome_label
ADD CONSTRAINT historical_corpus_outcome_label_component_owner_fk
FOREIGN KEY (component_id, component_hash)
REFERENCES historical_corpus_session_component(component_id, component_hash)
ON DELETE RESTRICT;

ALTER TABLE free_data_historical_security_fact_set
ADD COLUMN coverage_gap_count integer NOT NULL DEFAULT 0
CHECK (coverage_gap_count >= 0);

ALTER TABLE free_data_historical_security_fact_set
ALTER COLUMN coverage_gap_count DROP DEFAULT;

ALTER TABLE free_data_historical_security_fact_set
DROP CONSTRAINT free_data_historical_security_fact_set_check;

ALTER TABLE free_data_historical_security_fact_set
ADD CONSTRAINT free_data_historical_security_fact_set_payload_json_check CHECK (
    jsonb_typeof(payload_json) = 'object'
    AND payload_json->>'schema_version' IN (
        'historical-security-facts-owner/v1',
        'historical-security-facts-owner/v2'
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
            payload_json->>'schema_version' = 'historical-security-facts-owner/v2'
            AND jsonb_array_length(payload_json->'coverage_gaps') = coverage_gap_count
        )
    )
);

CREATE TABLE free_data_historical_security_fact_coverage_gap (
    owner_id text NOT NULL,
    owner_hash text NOT NULL CHECK (owner_hash ~ '^sha256:[0-9a-f]{64}$'),
    gap_id text NOT NULL CHECK (btrim(gap_id) <> ''),
    gap_hash text NOT NULL CHECK (gap_hash ~ '^sha256:[0-9a-f]{64}$'),
    symbol text NOT NULL CHECK (btrim(symbol) <> ''),
    fact_kind text NOT NULL CHECK (fact_kind IN (
        'ADJUSTMENT_EVENT', 'DIVIDEND_EVENT'
    )),
    coverage_start date NOT NULL,
    coverage_end date NOT NULL,
    source_artifact_kind text NOT NULL CHECK (btrim(source_artifact_kind) <> ''),
    source_artifact_id text NOT NULL CHECK (btrim(source_artifact_id) <> ''),
    source_content_hash text NOT NULL CHECK (
        source_content_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' = 'historical-security-fact-coverage-gap/v1'
        AND payload_json->>'gap_id' = gap_id
        AND payload_json->>'gap_hash' = gap_hash
        AND payload_json->>'symbol' = symbol
        AND payload_json->>'fact_kind' = fact_kind
        AND (payload_json->>'coverage_start')::date = coverage_start
        AND (payload_json->>'coverage_end')::date = coverage_end
    ),
    PRIMARY KEY (owner_id, gap_id),
    UNIQUE (owner_id, gap_hash),
    FOREIGN KEY (owner_id, owner_hash)
        REFERENCES free_data_historical_security_fact_set(owner_id, owner_hash)
        ON DELETE RESTRICT,
    CHECK (coverage_start <= coverage_end)
);

CREATE INDEX free_data_historical_security_fact_gap_lookup_idx
ON free_data_historical_security_fact_coverage_gap(
    owner_id, symbol, coverage_start, coverage_end, fact_kind, gap_id
);

CREATE INDEX free_data_historical_security_fact_gap_owner_fk_idx
ON free_data_historical_security_fact_coverage_gap(owner_id, owner_hash);

CREATE INDEX free_data_historical_constituent_timeline_cohort_snapshot_owner_fk_idx
ON free_data_historical_constituent_timeline_cohort(snapshot_id, snapshot_hash);

CREATE INDEX historical_corpus_outcome_label_component_owner_fk_idx
ON historical_corpus_outcome_label(component_id, component_hash);

CREATE TRIGGER free_data_historical_security_fact_gap_no_update
BEFORE UPDATE OR DELETE ON free_data_historical_security_fact_coverage_gap
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

COMMENT ON TABLE free_data_historical_security_fact_coverage_gap IS
'Immutable unresolved corporate-action provider rows; overlapping raw-return labels fail closed.';
