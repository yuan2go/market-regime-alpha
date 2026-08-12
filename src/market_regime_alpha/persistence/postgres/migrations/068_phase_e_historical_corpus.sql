-- Phase E historical corpus owners, bounded batch journal and research evidence.
-- PostgreSQL owns identity and lineage; Artifact Root stores immutable bytes only.

CREATE TABLE historical_corpus_owner (
    owner_id text PRIMARY KEY CHECK (btrim(owner_id) <> ''),
    content_hash text NOT NULL CHECK (content_hash ~ '^sha256:[0-9a-f]{64}$'),
    artifact_kind text NOT NULL CHECK (artifact_kind IN (
        'RAW_PROVIDER_ARCHIVE',
        'NORMALIZED_DATASET',
        'RESEARCH_MATERIALIZATION'
    )),
    provider_id text NOT NULL CHECK (btrim(provider_id) <> ''),
    schema_version text NOT NULL CHECK (btrim(schema_version) <> ''),
    normalization_version text,
    parent_owner_id text,
    parent_owner_hash text CHECK (
        parent_owner_hash IS NULL OR parent_owner_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    package_locator text NOT NULL UNIQUE CHECK (
        package_locator ~ '^artifact-root-v1/[A-Za-z0-9._=/-]+$'
        AND package_locator NOT LIKE '%..%'
    ),
    physical_hash text NOT NULL CHECK (physical_hash ~ '^sha256:[0-9a-f]{64}$'),
    availability_basis text NOT NULL CHECK (
        availability_basis = 'RETROSPECTIVE_EVENT_TIME'
    ),
    data_eligibility text NOT NULL CHECK (data_eligibility = 'EXPLORATORY'),
    formal_pit_status text NOT NULL CHECK (formal_pit_status = 'PIT_INCOMPLETE'),
    first_market_date date NOT NULL,
    last_market_date date NOT NULL,
    retrieved_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL,
    coverage_json jsonb NOT NULL CHECK (jsonb_typeof(coverage_json) = 'object'),
    manifest_json jsonb NOT NULL CHECK (
        jsonb_typeof(manifest_json) = 'object'
        AND manifest_json->>'owner_id' = owner_id
        AND manifest_json->>'content_hash' = content_hash
        AND manifest_json->>'artifact_kind' = artifact_kind
        AND manifest_json->>'schema_version' = schema_version
        AND manifest_json->>'availability_basis' = availability_basis
        AND manifest_json->>'data_eligibility' = data_eligibility
        AND manifest_json->>'formal_pit_status' = formal_pit_status
    ),
    UNIQUE (owner_id, content_hash),
    CONSTRAINT historical_corpus_owner_date_check CHECK (
        first_market_date <= last_market_date
    ),
    CONSTRAINT historical_corpus_owner_time_check CHECK (created_at >= retrieved_at),
    CONSTRAINT historical_corpus_owner_parent_pair_check CHECK (
        (parent_owner_id IS NULL) = (parent_owner_hash IS NULL)
    ),
    CONSTRAINT historical_corpus_owner_layer_check CHECK (
        (
            artifact_kind = 'RAW_PROVIDER_ARCHIVE'
            AND parent_owner_id IS NULL
            AND normalization_version IS NULL
        ) OR (
            artifact_kind = 'NORMALIZED_DATASET'
            AND parent_owner_id IS NOT NULL
            AND normalization_version IS NOT NULL
            AND btrim(normalization_version) <> ''
        ) OR (
            artifact_kind = 'RESEARCH_MATERIALIZATION'
            AND parent_owner_id IS NOT NULL
        )
    ),
    FOREIGN KEY (parent_owner_id, parent_owner_hash)
        REFERENCES historical_corpus_owner(owner_id, content_hash)
        ON DELETE RESTRICT
);

CREATE INDEX historical_corpus_owner_parent_idx
ON historical_corpus_owner(parent_owner_id, parent_owner_hash, artifact_kind)
WHERE parent_owner_id IS NOT NULL;

CREATE INDEX historical_corpus_owner_scope_idx
ON historical_corpus_owner(
    artifact_kind, first_market_date, last_market_date, owner_id, content_hash
);

CREATE TABLE historical_corpus_partition (
    owner_id text NOT NULL,
    owner_hash text NOT NULL CHECK (owner_hash ~ '^sha256:[0-9a-f]{64}$'),
    ordinal integer NOT NULL CHECK (ordinal > 0),
    partition_id text NOT NULL CHECK (btrim(partition_id) <> ''),
    partition_hash text NOT NULL CHECK (partition_hash ~ '^sha256:[0-9a-f]{64}$'),
    timeframe text NOT NULL CHECK (timeframe IN (
        'DAILY', 'MINUTE_1', 'MINUTE_5', 'MINUTE_15', 'MINUTE_30', 'MINUTE_60'
    )),
    first_market_date date NOT NULL,
    last_market_date date NOT NULL,
    symbol_bucket integer NOT NULL CHECK (symbol_bucket >= 0),
    bucket_count integer NOT NULL CHECK (bucket_count > 0),
    row_count bigint NOT NULL CHECK (row_count > 0),
    symbol_count integer NOT NULL CHECK (symbol_count > 0),
    relative_path text NOT NULL CHECK (
        relative_path ~ '^[A-Za-z0-9._=/-]+[.]parquet$'
        AND relative_path NOT LIKE '%..%'
    ),
    physical_checksum text NOT NULL CHECK (
        physical_checksum ~ '^sha256:[0-9a-f]{64}$'
    ),
    partition_json jsonb NOT NULL CHECK (jsonb_typeof(partition_json) = 'object'),
    PRIMARY KEY (owner_id, ordinal),
    UNIQUE (owner_id, partition_id, partition_hash),
    UNIQUE (owner_id, relative_path),
    FOREIGN KEY (owner_id, owner_hash)
        REFERENCES historical_corpus_owner(owner_id, content_hash)
        ON DELETE RESTRICT,
    CHECK (symbol_bucket < bucket_count),
    CHECK (first_market_date <= last_market_date)
);

CREATE INDEX historical_corpus_partition_read_idx
ON historical_corpus_partition(
    owner_id, timeframe, first_market_date, last_market_date, symbol_bucket
);

CREATE INDEX historical_corpus_partition_owner_fk_idx
ON historical_corpus_partition(owner_id, owner_hash);

CREATE TABLE historical_corpus_command (
    corpus_id text PRIMARY KEY CHECK (btrim(corpus_id) <> ''),
    command_hash text NOT NULL CHECK (command_hash ~ '^sha256:[0-9a-f]{64}$'),
    idempotency_key text NOT NULL UNIQUE CHECK (btrim(idempotency_key) <> ''),
    normalized_dataset_id text NOT NULL,
    normalized_dataset_hash text NOT NULL CHECK (
        normalized_dataset_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    experiment_id text NOT NULL CHECK (btrim(experiment_id) <> ''),
    experiment_hash text NOT NULL CHECK (experiment_hash ~ '^sha256:[0-9a-f]{64}$'),
    start_date date NOT NULL,
    end_date date NOT NULL,
    decision_local_time time NOT NULL,
    timezone_name text NOT NULL CHECK (btrim(timezone_name) <> ''),
    code_revision text NOT NULL CHECK (btrim(code_revision) <> ''),
    status text NOT NULL CHECK (status IN (
        'CREATED', 'RUNNING', 'PARTIAL', 'COMPLETED', 'FAILED'
    )),
    command_json jsonb NOT NULL CHECK (
        jsonb_typeof(command_json) = 'object'
        AND command_json->>'corpus_id' = corpus_id
        AND command_json->>'command_hash' = command_hash
    ),
    revision bigint NOT NULL DEFAULT 0 CHECK (revision >= 0),
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    UNIQUE (corpus_id, command_hash),
    FOREIGN KEY (normalized_dataset_id, normalized_dataset_hash)
        REFERENCES historical_corpus_owner(owner_id, content_hash)
        ON DELETE RESTRICT,
    CHECK (start_date <= end_date),
    CHECK (updated_at >= created_at)
);

CREATE INDEX historical_corpus_command_dataset_idx
ON historical_corpus_command(
    normalized_dataset_id, normalized_dataset_hash, experiment_id, experiment_hash,
    start_date, end_date
);

CREATE TABLE historical_corpus_session (
    corpus_id text NOT NULL,
    command_hash text NOT NULL CHECK (command_hash ~ '^sha256:[0-9a-f]{64}$'),
    trading_date date NOT NULL,
    decision_time timestamptz NOT NULL,
    status text NOT NULL CHECK (status IN (
        'PENDING', 'RUNNING', 'COMPLETED', 'BLOCKED', 'FAILED'
    )),
    claim_token bigint NOT NULL DEFAULT 0 CHECK (claim_token >= 0),
    lease_owner text,
    lease_expires_at timestamptz,
    attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    materialization_owner_id text,
    materialization_owner_hash text CHECK (
        materialization_owner_hash IS NULL
        OR materialization_owner_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    coverage_json jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (
        jsonb_typeof(coverage_json) = 'object'
    ),
    reason_codes_json jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (
        jsonb_typeof(reason_codes_json) = 'array'
    ),
    revision bigint NOT NULL DEFAULT 0 CHECK (revision >= 0),
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    PRIMARY KEY (corpus_id, trading_date),
    FOREIGN KEY (corpus_id, command_hash)
        REFERENCES historical_corpus_command(corpus_id, command_hash)
        ON DELETE RESTRICT,
    FOREIGN KEY (materialization_owner_id, materialization_owner_hash)
        REFERENCES historical_corpus_owner(owner_id, content_hash)
        ON DELETE RESTRICT,
    CHECK ((lease_owner IS NULL) = (lease_expires_at IS NULL)),
    CHECK ((materialization_owner_id IS NULL) = (materialization_owner_hash IS NULL)),
    CHECK (updated_at >= created_at)
);

CREATE INDEX historical_corpus_session_claim_idx
ON historical_corpus_session(corpus_id, status, trading_date, lease_expires_at);

CREATE INDEX historical_corpus_session_command_fk_idx
ON historical_corpus_session(corpus_id, command_hash);

CREATE INDEX historical_corpus_session_owner_idx
ON historical_corpus_session(
    materialization_owner_id, materialization_owner_hash, corpus_id, trading_date
)
WHERE materialization_owner_id IS NOT NULL;

CREATE TABLE historical_corpus_session_component (
    component_id text PRIMARY KEY CHECK (btrim(component_id) <> ''),
    component_hash text NOT NULL CHECK (component_hash ~ '^sha256:[0-9a-f]{64}$'),
    corpus_id text NOT NULL,
    trading_date date NOT NULL,
    ordinal integer NOT NULL CHECK (ordinal > 0),
    component_kind text NOT NULL CHECK (component_kind IN (
        'FEATURE', 'MARKET_REGIME', 'ETF', 'THEME', 'CAPITAL', 'DYNAMIC_POOL',
        'CANDIDATE', 'SIGNAL', 'FORECAST', 'OUTCOME', 'RESEARCH_PANEL'
    )),
    source_max_event_time timestamptz NOT NULL,
    materialized_at timestamptz NOT NULL,
    payload_json jsonb NOT NULL CHECK (jsonb_typeof(payload_json) = 'object'),
    created_at timestamptz NOT NULL,
    UNIQUE (component_id, component_hash),
    UNIQUE (corpus_id, trading_date, component_kind),
    UNIQUE (corpus_id, trading_date, ordinal),
    FOREIGN KEY (corpus_id, trading_date)
        REFERENCES historical_corpus_session(corpus_id, trading_date)
        ON DELETE RESTRICT,
    CHECK (materialized_at >= source_max_event_time),
    CHECK (created_at >= materialized_at)
);

CREATE INDEX historical_corpus_component_replay_idx
ON historical_corpus_session_component(
    corpus_id, trading_date, ordinal, component_id, component_hash
);

CREATE TABLE historical_corpus_component_source_binding (
    component_id text NOT NULL,
    component_hash text NOT NULL CHECK (component_hash ~ '^sha256:[0-9a-f]{64}$'),
    ordinal integer NOT NULL CHECK (ordinal > 0),
    artifact_kind text NOT NULL CHECK (btrim(artifact_kind) <> ''),
    artifact_id text NOT NULL CHECK (btrim(artifact_id) <> ''),
    content_hash text NOT NULL CHECK (content_hash ~ '^sha256:[0-9a-f]{64}$'),
    PRIMARY KEY (component_id, ordinal),
    UNIQUE (component_id, artifact_kind, artifact_id, content_hash),
    FOREIGN KEY (component_id, component_hash)
        REFERENCES historical_corpus_session_component(component_id, component_hash)
        ON DELETE RESTRICT
);

CREATE INDEX historical_corpus_component_source_idx
ON historical_corpus_component_source_binding(
    artifact_kind, artifact_id, content_hash, component_id
);

CREATE INDEX historical_corpus_component_source_fk_idx
ON historical_corpus_component_source_binding(component_id, component_hash);

CREATE TABLE historical_research_evidence (
    evidence_id text PRIMARY KEY CHECK (btrim(evidence_id) <> ''),
    evidence_hash text NOT NULL CHECK (evidence_hash ~ '^sha256:[0-9a-f]{64}$'),
    corpus_id text NOT NULL,
    command_hash text NOT NULL CHECK (command_hash ~ '^sha256:[0-9a-f]{64}$'),
    experiment_id text NOT NULL CHECK (btrim(experiment_id) <> ''),
    experiment_hash text NOT NULL CHECK (experiment_hash ~ '^sha256:[0-9a-f]{64}$'),
    evidence_kind text NOT NULL CHECK (evidence_kind IN (
        'CORPUS_SUMMARY', 'ALPHA_ABLATION', 'STRATEGY_ECONOMICS',
        'PORTFOLIO_PERFORMANCE', 'EXPLORATORY_MODEL'
    )),
    research_question text NOT NULL CHECK (btrim(research_question) <> ''),
    classification text NOT NULL CHECK (classification IN (
        'POSITIVE', 'NEGATIVE', 'INCONCLUSIVE', 'NOT_ESTIMABLE'
    )),
    rationale text NOT NULL CHECK (btrim(rationale) <> ''),
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'evidence_id' = evidence_id
        AND payload_json->>'evidence_hash' = evidence_hash
        AND payload_json->>'classification' = classification
    ),
    created_at timestamptz NOT NULL,
    UNIQUE (evidence_id, evidence_hash),
    UNIQUE (corpus_id, experiment_id, experiment_hash, evidence_kind),
    FOREIGN KEY (corpus_id, command_hash)
        REFERENCES historical_corpus_command(corpus_id, command_hash)
        ON DELETE RESTRICT
);

CREATE INDEX historical_research_evidence_query_idx
ON historical_research_evidence(
    corpus_id, experiment_id, experiment_hash, evidence_kind, classification
);

CREATE INDEX historical_research_evidence_command_fk_idx
ON historical_research_evidence(corpus_id, command_hash);

CREATE TABLE historical_research_evidence_metric (
    evidence_id text NOT NULL,
    evidence_hash text NOT NULL CHECK (evidence_hash ~ '^sha256:[0-9a-f]{64}$'),
    ordinal integer NOT NULL CHECK (ordinal > 0),
    variant_id text NOT NULL CHECK (btrim(variant_id) <> ''),
    slice_kind text NOT NULL CHECK (btrim(slice_kind) <> ''),
    slice_value text NOT NULL CHECK (btrim(slice_value) <> ''),
    metric_name text NOT NULL CHECK (btrim(metric_name) <> ''),
    metric_value numeric,
    metric_status text NOT NULL CHECK (metric_status IN (
        'AVAILABLE', 'NOT_ESTIMABLE'
    )),
    assumption_status text NOT NULL CHECK (assumption_status IN (
        'EMPIRICAL', 'ENGINEERING_ASSUMPTION', 'NOT_APPLICABLE'
    )),
    PRIMARY KEY (evidence_id, ordinal),
    UNIQUE (
        evidence_id, variant_id, slice_kind, slice_value, metric_name
    ),
    FOREIGN KEY (evidence_id, evidence_hash)
        REFERENCES historical_research_evidence(evidence_id, evidence_hash)
        ON DELETE RESTRICT,
    CHECK ((metric_status = 'AVAILABLE') = (metric_value IS NOT NULL))
);

CREATE INDEX historical_research_metric_query_idx
ON historical_research_evidence_metric(
    variant_id, slice_kind, slice_value, metric_name, evidence_id
);

CREATE INDEX historical_research_metric_evidence_fk_idx
ON historical_research_evidence_metric(evidence_id, evidence_hash);

CREATE TRIGGER historical_corpus_owner_no_update
BEFORE UPDATE OR DELETE ON historical_corpus_owner
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER historical_corpus_partition_no_update
BEFORE UPDATE OR DELETE ON historical_corpus_partition
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER historical_corpus_session_component_no_update
BEFORE UPDATE OR DELETE ON historical_corpus_session_component
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER historical_corpus_component_source_binding_no_update
BEFORE UPDATE OR DELETE ON historical_corpus_component_source_binding
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER historical_research_evidence_no_update
BEFORE UPDATE OR DELETE ON historical_research_evidence
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER historical_research_evidence_metric_no_update
BEFORE UPDATE OR DELETE ON historical_research_evidence_metric
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE FUNCTION guard_historical_corpus_command_update() RETURNS trigger AS $$
BEGIN
    IF NEW.corpus_id <> OLD.corpus_id
       OR NEW.command_hash <> OLD.command_hash
       OR NEW.idempotency_key <> OLD.idempotency_key
       OR NEW.normalized_dataset_id <> OLD.normalized_dataset_id
       OR NEW.normalized_dataset_hash <> OLD.normalized_dataset_hash
       OR NEW.experiment_id <> OLD.experiment_id
       OR NEW.experiment_hash <> OLD.experiment_hash
       OR NEW.start_date <> OLD.start_date
       OR NEW.end_date <> OLD.end_date
       OR NEW.decision_local_time <> OLD.decision_local_time
       OR NEW.timezone_name <> OLD.timezone_name
       OR NEW.code_revision <> OLD.code_revision
       OR NEW.command_json <> OLD.command_json
       OR NEW.created_at <> OLD.created_at
       OR NEW.revision <> OLD.revision + 1
       OR NEW.updated_at < OLD.updated_at THEN
        RAISE EXCEPTION 'Historical Corpus command identity/CAS violation';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER historical_corpus_command_identity_immutable
BEFORE UPDATE ON historical_corpus_command
FOR EACH ROW EXECUTE FUNCTION guard_historical_corpus_command_update();

CREATE TRIGGER historical_corpus_command_no_delete
BEFORE DELETE ON historical_corpus_command
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE FUNCTION guard_historical_corpus_session_update() RETURNS trigger AS $$
BEGIN
    IF NEW.corpus_id <> OLD.corpus_id
       OR NEW.command_hash <> OLD.command_hash
       OR NEW.trading_date <> OLD.trading_date
       OR NEW.decision_time <> OLD.decision_time
       OR NEW.created_at <> OLD.created_at
       OR NEW.claim_token < OLD.claim_token
       OR NEW.attempt_count < OLD.attempt_count
       OR NEW.revision <> OLD.revision + 1
       OR NEW.updated_at < OLD.updated_at THEN
        RAISE EXCEPTION 'Historical Corpus session identity/CAS violation';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER historical_corpus_session_identity_immutable
BEFORE UPDATE ON historical_corpus_session
FOR EACH ROW EXECUTE FUNCTION guard_historical_corpus_session_update();

CREATE TRIGGER historical_corpus_session_no_delete
BEFORE DELETE ON historical_corpus_session
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

COMMENT ON TABLE historical_corpus_owner IS
'PostgreSQL owner for exact immutable Phase E packages. Artifact Root bytes are not Authority.';

COMMENT ON COLUMN historical_corpus_owner.availability_basis IS
'Free historical evidence uses event-time retrospective slicing; retrieved_at is never rewritten as historical available_at.';

COMMENT ON TABLE historical_research_evidence IS
'Append-only exploratory findings. NEGATIVE, INCONCLUSIVE and NOT_ESTIMABLE are first-class durable classifications.';
