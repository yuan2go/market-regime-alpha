CREATE TABLE research_universe_policy (
    policy_id text PRIMARY KEY,
    policy_hash text NOT NULL UNIQUE CHECK (
        policy_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    policy_version text NOT NULL CHECK (btrim(policy_version) <> ''),
    data_authority text NOT NULL CHECK (btrim(data_authority) <> ''),
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' = 'research-universe-policy/v1'
    ),
    created_at timestamptz NOT NULL
);

CREATE TABLE runtime_scope_receipt (
    scope_id text PRIMARY KEY,
    scope_hash text NOT NULL UNIQUE CHECK (
        scope_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    policy_id text NOT NULL
        REFERENCES research_universe_policy(policy_id) ON DELETE RESTRICT,
    policy_hash text NOT NULL CHECK (
        policy_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    as_of timestamptz NOT NULL,
    built_at timestamptz NOT NULL,
    code_revision text NOT NULL CHECK (btrim(code_revision) <> ''),
    data_eligibility text NOT NULL CHECK (
        data_eligibility IN ('UNQUALIFIED', 'EXPLORATORY', 'REHEARSAL', 'FORMAL_RESEARCH')
    ),
    evidence_ceiling text NOT NULL CHECK (btrim(evidence_ceiling) <> ''),
    formal_pit boolean NOT NULL,
    member_count integer NOT NULL CHECK (member_count > 0),
    included_count integer NOT NULL CHECK (
        included_count >= 0 AND included_count <= member_count
    ),
    unknown_count integer NOT NULL CHECK (
        unknown_count >= 0 AND unknown_count <= member_count
    ),
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' = 'runtime-scope-receipt/v1'
        AND (payload_json->>'formal_pit')::boolean = formal_pit
    ),
    created_at timestamptz NOT NULL,
    CHECK (NOT formal_pit OR evidence_ceiling = 'FORMAL_PIT_PROVIDER')
);

CREATE INDEX runtime_scope_policy_asof_idx
ON runtime_scope_receipt(policy_id, as_of, built_at, scope_id);

CREATE TABLE runtime_scope_input_reference (
    scope_id text NOT NULL
        REFERENCES runtime_scope_receipt(scope_id) ON DELETE RESTRICT,
    ordinal integer NOT NULL CHECK (ordinal > 0),
    artifact_kind text NOT NULL CHECK (btrim(artifact_kind) <> ''),
    artifact_id text NOT NULL CHECK (btrim(artifact_id) <> ''),
    content_hash text NOT NULL CHECK (
        content_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    PRIMARY KEY (scope_id, ordinal),
    UNIQUE (scope_id, artifact_kind, artifact_id, content_hash)
);

CREATE INDEX runtime_scope_input_owner_idx
ON runtime_scope_input_reference(artifact_kind, artifact_id, content_hash);

CREATE TABLE runtime_scope_member (
    scope_id text NOT NULL
        REFERENCES runtime_scope_receipt(scope_id) ON DELETE RESTRICT,
    symbol text NOT NULL CHECK (btrim(symbol) <> ''),
    decision text NOT NULL CHECK (
        decision IN ('INCLUDED', 'EXCLUDED', 'UNKNOWN')
    ),
    payload_json jsonb NOT NULL CHECK (jsonb_typeof(payload_json) = 'object'),
    PRIMARY KEY (scope_id, symbol)
);

CREATE INDEX runtime_scope_member_decision_idx
ON runtime_scope_member(scope_id, decision, symbol);

CREATE TRIGGER research_universe_policy_no_update
BEFORE UPDATE OR DELETE ON research_universe_policy
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER runtime_scope_receipt_no_update
BEFORE UPDATE OR DELETE ON runtime_scope_receipt
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER runtime_scope_input_reference_no_update
BEFORE UPDATE OR DELETE ON runtime_scope_input_reference
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER runtime_scope_member_no_update
BEFORE UPDATE OR DELETE ON runtime_scope_member
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
