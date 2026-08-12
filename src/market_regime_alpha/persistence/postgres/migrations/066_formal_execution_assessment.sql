CREATE TABLE formal_execution_request (
    request_id text PRIMARY KEY,
    request_hash text NOT NULL UNIQUE CHECK (request_hash ~ '^sha256:[0-9a-f]{64}$'),
    idempotency_key text NOT NULL UNIQUE,
    provider_requirement_count integer NOT NULL CHECK (provider_requirement_count > 0),
    formal_protocol_id text,
    assessed_at timestamptz NOT NULL,
    actor text NOT NULL CHECK (btrim(actor) <> ''),
    reason text NOT NULL CHECK (btrim(reason) <> ''),
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' = 'formal-execution-request/v1'
    )
);

CREATE TABLE formal_execution_provider_requirement (
    request_id text NOT NULL REFERENCES formal_execution_request(request_id) ON DELETE RESTRICT,
    ordinal integer NOT NULL CHECK (ordinal > 0),
    provider_id text NOT NULL,
    provider_contract text NOT NULL,
    fact_kind text NOT NULL,
    decision_id text,
    payload_json jsonb NOT NULL CHECK (jsonb_typeof(payload_json) = 'object'),
    PRIMARY KEY (request_id, ordinal),
    UNIQUE (request_id, provider_id, provider_contract, fact_kind)
);

CREATE INDEX formal_execution_provider_decision_idx
ON formal_execution_provider_requirement(decision_id)
WHERE decision_id IS NOT NULL;

CREATE TABLE formal_execution_assessment (
    assessment_id text PRIMARY KEY,
    assessment_hash text NOT NULL UNIQUE CHECK (assessment_hash ~ '^sha256:[0-9a-f]{64}$'),
    request_id text NOT NULL UNIQUE REFERENCES formal_execution_request(request_id) ON DELETE RESTRICT,
    status text NOT NULL CHECK (status IN (
        'SATISFIED', 'BLOCKED', 'INCOMPLETE', 'REJECTED', 'NOT_ESTIMABLE'
    )),
    terminal_stage text NOT NULL,
    formal_model_qualified boolean NOT NULL,
    formal_oos_alpha_established boolean NOT NULL,
    calibrated boolean NOT NULL,
    production_authorized boolean NOT NULL CHECK (NOT production_authorized),
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' = 'formal-execution-assessment/v1'
    ),
    assessed_at timestamptz NOT NULL,
    CHECK (NOT formal_oos_alpha_established OR formal_model_qualified),
    CHECK (NOT calibrated OR formal_oos_alpha_established),
    CHECK (
        status = 'SATISFIED'
        OR (NOT formal_model_qualified AND NOT formal_oos_alpha_established AND NOT calibrated)
    )
);

CREATE TABLE formal_execution_stage_assessment (
    assessment_id text NOT NULL REFERENCES formal_execution_assessment(assessment_id) ON DELETE RESTRICT,
    ordinal integer NOT NULL CHECK (ordinal > 0),
    stage text NOT NULL,
    status text NOT NULL CHECK (status IN (
        'SATISFIED', 'BLOCKED', 'INCOMPLETE', 'REJECTED', 'NOT_ESTIMABLE'
    )),
    payload_json jsonb NOT NULL CHECK (jsonb_typeof(payload_json) = 'object'),
    PRIMARY KEY (assessment_id, ordinal),
    UNIQUE (assessment_id, stage)
);

CREATE TABLE formal_execution_source_binding (
    assessment_id text NOT NULL REFERENCES formal_execution_assessment(assessment_id) ON DELETE RESTRICT,
    ordinal integer NOT NULL CHECK (ordinal > 0),
    artifact_kind text NOT NULL,
    artifact_id text NOT NULL,
    content_hash text NOT NULL CHECK (content_hash ~ '^sha256:[0-9a-f]{64}$'),
    PRIMARY KEY (assessment_id, ordinal),
    UNIQUE (assessment_id, artifact_kind, artifact_id, content_hash)
);

CREATE INDEX formal_execution_source_owner_idx
ON formal_execution_source_binding(artifact_kind, artifact_id);

CREATE TRIGGER formal_execution_request_no_update BEFORE UPDATE OR DELETE ON formal_execution_request FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER formal_execution_provider_requirement_no_update BEFORE UPDATE OR DELETE ON formal_execution_provider_requirement FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER formal_execution_assessment_no_update BEFORE UPDATE OR DELETE ON formal_execution_assessment FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER formal_execution_stage_assessment_no_update BEFORE UPDATE OR DELETE ON formal_execution_stage_assessment FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER formal_execution_source_binding_no_update BEFORE UPDATE OR DELETE ON formal_execution_source_binding FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
