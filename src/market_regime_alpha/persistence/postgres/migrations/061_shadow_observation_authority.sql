CREATE TABLE shadow_observation_policy (
    policy_id text PRIMARY KEY,
    policy_hash text NOT NULL UNIQUE CHECK (
        policy_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    policy_version text NOT NULL CHECK (btrim(policy_version) <> ''),
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' = 'shadow-observation-policy/v1'
    ),
    created_at timestamptz NOT NULL
);

CREATE TABLE shadow_observation_receipt (
    receipt_id text PRIMARY KEY,
    receipt_hash text NOT NULL UNIQUE CHECK (
        receipt_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    observation_kind text NOT NULL CHECK (
        observation_kind IN ('STRATEGY', 'PORTFOLIO')
    ),
    build_status text NOT NULL CHECK (
        build_status IN ('READY', 'NOT_ESTIMABLE')
    ),
    research_trading_date date NOT NULL,
    trading_date date NOT NULL CHECK (trading_date >= research_trading_date),
    observed_at timestamptz NOT NULL,
    symbol text,
    symbol_key text GENERATED ALWAYS AS (coalesce(symbol, '')) STORED,
    policy_id text NOT NULL
        REFERENCES shadow_observation_policy(policy_id) ON DELETE RESTRICT,
    policy_hash text NOT NULL CHECK (
        policy_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    formal_pit boolean NOT NULL CHECK (NOT formal_pit),
    formal_oos boolean NOT NULL CHECK (NOT formal_oos),
    calibrated boolean NOT NULL CHECK (NOT calibrated),
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' = 'shadow-observation-receipt/v1'
    ),
    created_at timestamptz NOT NULL,
    UNIQUE (
        observation_kind, research_trading_date, trading_date,
        observed_at, symbol_key, policy_id
    )
);

CREATE INDEX shadow_observation_receipt_lookup_idx
ON shadow_observation_receipt(
    observation_kind, research_trading_date, trading_date, policy_id
);

CREATE INDEX shadow_observation_receipt_policy_idx
ON shadow_observation_receipt(policy_id);

CREATE TABLE shadow_observation_value (
    receipt_id text NOT NULL
        REFERENCES shadow_observation_receipt(receipt_id) ON DELETE RESTRICT,
    value_name text NOT NULL CHECK (btrim(value_name) <> ''),
    provenance text NOT NULL CHECK (
        provenance IN (
            'OBSERVED_FACT', 'CALIBRATED_PARAMETER',
            'ENGINEERING_ASSUMPTION', 'OPERATOR_INPUT'
        )
    ),
    source_artifact_id text NOT NULL,
    source_content_hash text NOT NULL CHECK (
        source_content_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    effective_at timestamptz NOT NULL,
    available_at timestamptz NOT NULL,
    payload_json jsonb NOT NULL CHECK (jsonb_typeof(payload_json) = 'object'),
    PRIMARY KEY (receipt_id, value_name)
);

CREATE INDEX shadow_observation_value_source_idx
ON shadow_observation_value(source_artifact_id, receipt_id);

CREATE TABLE shadow_observation_source_binding (
    receipt_id text NOT NULL
        REFERENCES shadow_observation_receipt(receipt_id) ON DELETE RESTRICT,
    ordinal integer NOT NULL CHECK (ordinal > 0),
    artifact_kind text NOT NULL CHECK (btrim(artifact_kind) <> ''),
    artifact_id text NOT NULL,
    content_hash text NOT NULL CHECK (
        content_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    PRIMARY KEY (receipt_id, ordinal),
    UNIQUE (receipt_id, artifact_kind, artifact_id, content_hash)
);

CREATE INDEX shadow_observation_source_owner_idx
ON shadow_observation_source_binding(artifact_kind, artifact_id);

CREATE TRIGGER shadow_observation_policy_no_update
BEFORE UPDATE OR DELETE ON shadow_observation_policy
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER shadow_observation_receipt_no_update
BEFORE UPDATE OR DELETE ON shadow_observation_receipt
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER shadow_observation_value_no_update
BEFORE UPDATE OR DELETE ON shadow_observation_value
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER shadow_observation_source_binding_no_update
BEFORE UPDATE OR DELETE ON shadow_observation_source_binding
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
