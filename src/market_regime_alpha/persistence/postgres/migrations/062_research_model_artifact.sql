CREATE TABLE research_model_training_request (
    request_id text PRIMARY KEY,
    request_hash text NOT NULL UNIQUE CHECK (request_hash ~ '^sha256:[0-9a-f]{64}$'),
    model_definition_id text NOT NULL,
    model_definition_hash text NOT NULL CHECK (model_definition_hash ~ '^sha256:[0-9a-f]{64}$'),
    configuration_id text NOT NULL,
    configuration_hash text NOT NULL CHECK (configuration_hash ~ '^sha256:[0-9a-f]{64}$'),
    feature_catalog_id text NOT NULL,
    target_protocol_id text NOT NULL,
    locked_oos_partition_id text NOT NULL,
    locked_oos_partition_hash text NOT NULL CHECK (locked_oos_partition_hash ~ '^sha256:[0-9a-f]{64}$'),
    oos_start_date date NOT NULL,
    fold_seed bigint NOT NULL,
    code_revision text NOT NULL CHECK (btrim(code_revision) <> ''),
    code_hash text NOT NULL CHECK (code_hash ~ '^sha256:[0-9a-f]{64}$'),
    formal_pit boolean NOT NULL CHECK (NOT formal_pit),
    formal_oos boolean NOT NULL CHECK (NOT formal_oos),
    calibrated boolean NOT NULL CHECK (NOT calibrated),
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' = 'research-model-training-request/v1'
    ),
    requested_at timestamptz NOT NULL
);

CREATE TABLE research_model_training_sample (
    request_id text NOT NULL REFERENCES research_model_training_request(request_id) ON DELETE RESTRICT,
    ordinal integer NOT NULL CHECK (ordinal > 0),
    sample_id text NOT NULL,
    sample_hash text NOT NULL CHECK (sample_hash ~ '^sha256:[0-9a-f]{64}$'),
    symbol text NOT NULL,
    trading_date date NOT NULL,
    decision_time timestamptz NOT NULL,
    payload_json jsonb NOT NULL CHECK (jsonb_typeof(payload_json) = 'object'),
    PRIMARY KEY (request_id, ordinal),
    UNIQUE (request_id, sample_id)
);

CREATE INDEX research_model_training_sample_request_idx
ON research_model_training_sample(request_id, trading_date, sample_id);

CREATE TABLE research_model_training_feature (
    request_id text NOT NULL,
    sample_id text NOT NULL,
    feature_name text NOT NULL,
    available_at timestamptz NOT NULL,
    source_artifact_id text NOT NULL,
    source_content_hash text NOT NULL CHECK (source_content_hash ~ '^sha256:[0-9a-f]{64}$'),
    payload_json jsonb NOT NULL CHECK (jsonb_typeof(payload_json) = 'object'),
    PRIMARY KEY (request_id, sample_id, feature_name),
    FOREIGN KEY (request_id, sample_id)
        REFERENCES research_model_training_sample(request_id, sample_id) ON DELETE RESTRICT
);

CREATE TABLE research_model_training_target (
    request_id text NOT NULL,
    sample_id text NOT NULL,
    target_name text NOT NULL,
    available_at timestamptz NOT NULL,
    source_artifact_id text NOT NULL,
    source_content_hash text NOT NULL CHECK (source_content_hash ~ '^sha256:[0-9a-f]{64}$'),
    payload_json jsonb NOT NULL CHECK (jsonb_typeof(payload_json) = 'object'),
    PRIMARY KEY (request_id, sample_id, target_name),
    FOREIGN KEY (request_id, sample_id)
        REFERENCES research_model_training_sample(request_id, sample_id) ON DELETE RESTRICT
);

CREATE TABLE research_model_walk_forward_fold (
    request_id text NOT NULL REFERENCES research_model_training_request(request_id) ON DELETE RESTRICT,
    fold_name text NOT NULL,
    payload_json jsonb NOT NULL CHECK (jsonb_typeof(payload_json) = 'object'),
    PRIMARY KEY (request_id, fold_name)
);

CREATE TABLE research_model_training_source_binding (
    request_id text NOT NULL REFERENCES research_model_training_request(request_id) ON DELETE RESTRICT,
    ordinal integer NOT NULL CHECK (ordinal > 0),
    artifact_kind text NOT NULL,
    artifact_id text NOT NULL,
    content_hash text NOT NULL CHECK (content_hash ~ '^sha256:[0-9a-f]{64}$'),
    PRIMARY KEY (request_id, ordinal),
    UNIQUE (request_id, artifact_kind, artifact_id, content_hash)
);

CREATE INDEX research_model_training_source_owner_idx
ON research_model_training_source_binding(artifact_kind, artifact_id);

CREATE TABLE research_model_artifact (
    artifact_id text PRIMARY KEY,
    artifact_hash text NOT NULL UNIQUE CHECK (artifact_hash ~ '^sha256:[0-9a-f]{64}$'),
    request_id text NOT NULL UNIQUE REFERENCES research_model_training_request(request_id) ON DELETE RESTRICT,
    status text NOT NULL CHECK (status IN ('AVAILABLE', 'NOT_ESTIMABLE')),
    selected_penalty numeric,
    research_model_available boolean NOT NULL,
    runtime_role text NOT NULL CHECK (runtime_role = 'RESEARCH_CHALLENGER'),
    formal_model_qualified boolean NOT NULL CHECK (NOT formal_model_qualified),
    formal_oos boolean NOT NULL CHECK (NOT formal_oos),
    calibrated boolean NOT NULL CHECK (NOT calibrated),
    production_authorized boolean NOT NULL CHECK (NOT production_authorized),
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' = 'research-model-artifact/v1'
    ),
    trained_at timestamptz NOT NULL,
    CHECK (research_model_available = (status = 'AVAILABLE'))
);

CREATE INDEX research_model_artifact_request_idx
ON research_model_artifact(request_id);

CREATE TABLE research_model_candidate_diagnostic (
    artifact_id text NOT NULL REFERENCES research_model_artifact(artifact_id) ON DELETE RESTRICT,
    penalty numeric NOT NULL CHECK (penalty > 0),
    status text NOT NULL CHECK (status IN ('AVAILABLE', 'NOT_ESTIMABLE')),
    aggregate_loss numeric,
    payload_json jsonb NOT NULL CHECK (jsonb_typeof(payload_json) = 'object'),
    PRIMARY KEY (artifact_id, penalty)
);

CREATE TABLE research_model_coefficient_head (
    artifact_id text NOT NULL REFERENCES research_model_artifact(artifact_id) ON DELETE RESTRICT,
    target_name text NOT NULL,
    head_kind text NOT NULL CHECK (head_kind IN ('RIDGE', 'LOGISTIC_RAW_LOGIT')),
    payload_json jsonb NOT NULL CHECK (jsonb_typeof(payload_json) = 'object'),
    PRIMARY KEY (artifact_id, target_name)
);

CREATE TABLE research_model_inference_receipt (
    receipt_id text PRIMARY KEY,
    receipt_hash text NOT NULL UNIQUE CHECK (receipt_hash ~ '^sha256:[0-9a-f]{64}$'),
    artifact_id text NOT NULL REFERENCES research_model_artifact(artifact_id) ON DELETE RESTRICT,
    symbol text NOT NULL,
    decision_time timestamptz NOT NULL,
    status text NOT NULL CHECK (status IN ('AVAILABLE', 'NOT_ESTIMABLE')),
    formal_model_qualified boolean NOT NULL CHECK (NOT formal_model_qualified),
    formal_oos boolean NOT NULL CHECK (NOT formal_oos),
    calibrated boolean NOT NULL CHECK (NOT calibrated),
    production_authorized boolean NOT NULL CHECK (NOT production_authorized),
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' = 'research-model-inference-receipt/v1'
    ),
    executed_at timestamptz NOT NULL,
    UNIQUE (artifact_id, symbol, decision_time, receipt_hash)
);

CREATE INDEX research_model_inference_artifact_idx
ON research_model_inference_receipt(artifact_id, decision_time);

CREATE TABLE research_model_inference_source_binding (
    receipt_id text NOT NULL REFERENCES research_model_inference_receipt(receipt_id) ON DELETE RESTRICT,
    ordinal integer NOT NULL CHECK (ordinal > 0),
    artifact_kind text NOT NULL,
    artifact_id text NOT NULL,
    content_hash text NOT NULL CHECK (content_hash ~ '^sha256:[0-9a-f]{64}$'),
    PRIMARY KEY (receipt_id, ordinal),
    UNIQUE (receipt_id, artifact_kind, artifact_id, content_hash)
);

CREATE INDEX research_model_inference_source_owner_idx
ON research_model_inference_source_binding(artifact_kind, artifact_id);

CREATE TRIGGER research_model_training_request_no_update BEFORE UPDATE OR DELETE ON research_model_training_request FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER research_model_training_sample_no_update BEFORE UPDATE OR DELETE ON research_model_training_sample FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER research_model_training_feature_no_update BEFORE UPDATE OR DELETE ON research_model_training_feature FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER research_model_training_target_no_update BEFORE UPDATE OR DELETE ON research_model_training_target FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER research_model_walk_forward_fold_no_update BEFORE UPDATE OR DELETE ON research_model_walk_forward_fold FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER research_model_training_source_binding_no_update BEFORE UPDATE OR DELETE ON research_model_training_source_binding FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER research_model_artifact_no_update BEFORE UPDATE OR DELETE ON research_model_artifact FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER research_model_candidate_diagnostic_no_update BEFORE UPDATE OR DELETE ON research_model_candidate_diagnostic FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER research_model_coefficient_head_no_update BEFORE UPDATE OR DELETE ON research_model_coefficient_head FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER research_model_inference_receipt_no_update BEFORE UPDATE OR DELETE ON research_model_inference_receipt FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER research_model_inference_source_binding_no_update BEFORE UPDATE OR DELETE ON research_model_inference_source_binding FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
