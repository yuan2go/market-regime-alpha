-- Additive Target v3 and correctness failure-detail projections. Existing
-- labels and Evidence remain immutable and are never reinterpreted in place.

ALTER TABLE historical_corpus_outcome_label
ADD COLUMN label_schema_version text
GENERATED ALWAYS AS (payload_json->>'schema_version') STORED,
ADD COLUMN semantic_specification_id text
GENERATED ALWAYS AS (
    payload_json->'semantic_result'->'semantic_specification'->>'artifact_id'
) STORED,
ADD COLUMN decision_reference_status text
GENERATED ALWAYS AS (
    payload_json->'semantic_result'->>'decision_reference_status'
) STORED,
ADD COLUMN outcome_window_status text
GENERATED ALWAYS AS (
    payload_json->'semantic_result'->>'outcome_window_status'
) STORED,
ADD COLUMN checkpoint_observation_status text
GENERATED ALWAYS AS (
    payload_json->'semantic_result'->>'checkpoint_observation_status'
) STORED,
ADD COLUMN checkpoint_return_status text
GENERATED ALWAYS AS (
    payload_json->'semantic_result'->>'checkpoint_return_status'
) STORED,
ADD COLUMN mfe_status text
GENERATED ALWAYS AS (payload_json->'semantic_result'->>'mfe_status') STORED,
ADD COLUMN mae_status text
GENERATED ALWAYS AS (payload_json->'semantic_result'->>'mae_status') STORED,
ADD COLUMN barrier_status text
GENERATED ALWAYS AS (payload_json->'semantic_result'->>'barrier_status') STORED;

ALTER TABLE historical_corpus_outcome_label
ADD CONSTRAINT historical_corpus_outcome_label_v3_semantics_check CHECK (
    label_schema_version IN (
        'target-outcome-label/v1',
        'target-outcome-label/v2'
    )
    OR (
        label_schema_version = 'target-outcome-label/v3'
        AND semantic_specification_id IS NOT NULL
        AND decision_reference_status IN (
            'COMPLETE', 'PARTIAL', 'UNAVAILABLE', 'FAILED'
        )
        AND outcome_window_status IN (
            'COMPLETE', 'PARTIAL', 'UNAVAILABLE', 'FAILED'
        )
        AND checkpoint_observation_status IN (
            'COMPLETE', 'PARTIAL', 'UNAVAILABLE', 'FAILED'
        )
        AND checkpoint_return_status IN (
            'COMPLETE', 'PARTIAL', 'UNAVAILABLE', 'FAILED'
        )
        AND mfe_status IN ('COMPLETE', 'PARTIAL', 'UNAVAILABLE', 'FAILED')
        AND mae_status IN ('COMPLETE', 'PARTIAL', 'UNAVAILABLE', 'FAILED')
        AND barrier_status IN ('COMPLETE', 'PARTIAL', 'UNAVAILABLE', 'FAILED')
    )
);

CREATE INDEX historical_corpus_outcome_label_v3_status_idx
ON historical_corpus_outcome_label(
    label_schema_version,
    decision_reference_status,
    outcome_window_status,
    checkpoint_return_status,
    barrier_status,
    trading_date,
    symbol
);

ALTER TABLE historical_research_run
ADD CONSTRAINT historical_research_run_identity_pair
UNIQUE (run_id, command_hash);

CREATE TABLE alpha_correctness_failure_index (
    index_id text PRIMARY KEY CHECK (btrim(index_id) <> ''),
    index_hash text NOT NULL CHECK (index_hash ~ '^sha256:[0-9a-f]{64}$'),
    source_run_id text NOT NULL REFERENCES historical_research_run(run_id)
        ON DELETE RESTRICT,
    source_command_hash text NOT NULL
        CHECK (source_command_hash ~ '^sha256:[0-9a-f]{64}$'),
    source_evidence_id text NOT NULL,
    source_evidence_hash text NOT NULL
        CHECK (source_evidence_hash ~ '^sha256:[0-9a-f]{64}$'),
    experiment_id text NOT NULL CHECK (btrim(experiment_id) <> ''),
    experiment_hash text NOT NULL
        CHECK (experiment_hash ~ '^sha256:[0-9a-f]{64}$'),
    target_protocol_id text NOT NULL
        REFERENCES outcome_target_protocol(protocol_id) ON DELETE RESTRICT,
    target_protocol_hash text NOT NULL
        CHECK (target_protocol_hash ~ '^sha256:[0-9a-f]{64}$'),
    calendar_id text NOT NULL CHECK (btrim(calendar_id) <> ''),
    calendar_hash text NOT NULL
        CHECK (calendar_hash ~ '^sha256:[0-9a-f]{64}$'),
    raw_owner_id text NOT NULL CHECK (btrim(raw_owner_id) <> ''),
    raw_owner_hash text NOT NULL
        CHECK (raw_owner_hash ~ '^sha256:[0-9a-f]{64}$'),
    normalized_owner_id text NOT NULL CHECK (btrim(normalized_owner_id) <> ''),
    normalized_owner_hash text NOT NULL
        CHECK (normalized_owner_hash ~ '^sha256:[0-9a-f]{64}$'),
    normalization_revision text NOT NULL
        CHECK (btrim(normalization_revision) <> ''),
    analysis_code_sha text NOT NULL
        CHECK (analysis_code_sha ~ '^[0-9a-f]{40}$'),
    semantic_revision text NOT NULL CHECK (btrim(semantic_revision) <> ''),
    detail_count integer NOT NULL CHECK (detail_count >= 0),
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'index_id' = index_id
        AND payload_json->>'index_hash' = index_hash
        AND (payload_json->>'detail_count')::integer = detail_count
        AND jsonb_array_length(payload_json->'details') = detail_count
    ),
    created_at timestamptz NOT NULL,
    UNIQUE (index_id, index_hash),
    UNIQUE (source_run_id, source_evidence_id, semantic_revision),
    FOREIGN KEY (source_evidence_id, source_evidence_hash)
        REFERENCES historical_research_evidence(evidence_id, evidence_hash)
        ON DELETE RESTRICT,
    FOREIGN KEY (source_run_id, source_command_hash)
        REFERENCES historical_research_run(run_id, command_hash)
        ON DELETE RESTRICT
);

CREATE TABLE alpha_correctness_failure_detail (
    index_id text NOT NULL,
    index_hash text NOT NULL CHECK (index_hash ~ '^sha256:[0-9a-f]{64}$'),
    ordinal integer NOT NULL CHECK (ordinal > 0),
    detail_id text NOT NULL CHECK (btrim(detail_id) <> ''),
    detail_hash text NOT NULL CHECK (detail_hash ~ '^sha256:[0-9a-f]{64}$'),
    decision_session date NOT NULL,
    decision_time timestamptz NOT NULL,
    target_session date NOT NULL,
    target_window_end timestamptz NOT NULL,
    symbol text NOT NULL CHECK (btrim(symbol) <> ''),
    classification text NOT NULL CHECK (btrim(classification) <> ''),
    discrepancy_code text NOT NULL CHECK (btrim(discrepancy_code) <> ''),
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'detail_id' = detail_id
        AND payload_json->>'detail_hash' = detail_hash
        AND payload_json->>'symbol' = symbol
        AND payload_json->>'classification' = classification
        AND payload_json->>'discrepancy_code' = discrepancy_code
    ),
    PRIMARY KEY (index_id, ordinal),
    UNIQUE (detail_id, detail_hash),
    UNIQUE (index_id, decision_session, symbol),
    FOREIGN KEY (index_id, index_hash)
        REFERENCES alpha_correctness_failure_index(index_id, index_hash)
        ON DELETE RESTRICT,
    CHECK (target_session > decision_session),
    CHECK (target_window_end > decision_time)
);

CREATE TABLE alpha_correctness_failure_source_binding (
    detail_id text NOT NULL,
    detail_hash text NOT NULL CHECK (detail_hash ~ '^sha256:[0-9a-f]{64}$'),
    ordinal integer NOT NULL CHECK (ordinal > 0),
    source_role text NOT NULL CHECK (btrim(source_role) <> ''),
    artifact_kind text NOT NULL CHECK (btrim(artifact_kind) <> ''),
    artifact_id text NOT NULL CHECK (btrim(artifact_id) <> ''),
    content_hash text NOT NULL CHECK (content_hash ~ '^sha256:[0-9a-f]{64}$'),
    PRIMARY KEY (detail_id, ordinal),
    UNIQUE (
        detail_id, source_role, artifact_kind, artifact_id, content_hash
    ),
    FOREIGN KEY (detail_id, detail_hash)
        REFERENCES alpha_correctness_failure_detail(detail_id, detail_hash)
        ON DELETE RESTRICT
);

CREATE INDEX alpha_correctness_failure_lookup_idx
ON alpha_correctness_failure_detail(
    decision_session, symbol, classification, index_id
);

CREATE INDEX alpha_correctness_failure_index_target_protocol_fk_idx
ON alpha_correctness_failure_index(target_protocol_id);

CREATE INDEX alpha_correctness_failure_index_source_evidence_fk_idx
ON alpha_correctness_failure_index(source_evidence_id, source_evidence_hash);

CREATE INDEX alpha_correctness_failure_index_source_run_fk_idx
ON alpha_correctness_failure_index(source_run_id, source_command_hash);

CREATE INDEX alpha_correctness_failure_detail_index_fk_idx
ON alpha_correctness_failure_detail(index_id, index_hash);

CREATE INDEX alpha_correctness_failure_source_lookup_idx
ON alpha_correctness_failure_source_binding(
    artifact_kind, artifact_id, content_hash, detail_id
);

CREATE INDEX alpha_correctness_failure_source_detail_fk_idx
ON alpha_correctness_failure_source_binding(detail_id, detail_hash);

CREATE TRIGGER alpha_correctness_failure_index_no_update
BEFORE UPDATE OR DELETE ON alpha_correctness_failure_index
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER alpha_correctness_failure_detail_no_update
BEFORE UPDATE OR DELETE ON alpha_correctness_failure_detail
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER alpha_correctness_failure_source_binding_no_update
BEFORE UPDATE OR DELETE ON alpha_correctness_failure_source_binding
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

COMMENT ON TABLE alpha_correctness_failure_index IS
'Typed append-only failure index under existing Historical Evidence authority; it grants no Alpha, OOS, Provider, trading or Production qualification.';

COMMENT ON TABLE alpha_correctness_failure_detail IS
'Owner-reloadable row detail for Alpha correctness discrepancies, including unavailable and negative outcomes.';
