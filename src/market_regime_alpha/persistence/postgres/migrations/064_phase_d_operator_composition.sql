CREATE TABLE runtime_scope_operational_input (
    scope_id text NOT NULL
        REFERENCES runtime_scope_receipt(scope_id) ON DELETE RESTRICT,
    ordinal integer NOT NULL CHECK (ordinal > 0),
    universe_id text NOT NULL,
    universe_hash text NOT NULL CHECK (
        universe_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    decision_date date NOT NULL,
    effective_at timestamptz NOT NULL,
    available_at timestamptz NOT NULL,
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' IN (
            'operational-universe-artifact-v1',
            'operational-universe-artifact-v2'
        )
    ),
    created_at timestamptz NOT NULL,
    PRIMARY KEY (scope_id, ordinal),
    UNIQUE (scope_id, universe_id, universe_hash),
    CHECK (available_at >= effective_at)
);

CREATE INDEX runtime_scope_operational_owner_idx
ON runtime_scope_operational_input(universe_id, universe_hash);

CREATE TRIGGER runtime_scope_operational_input_no_update
BEFORE UPDATE OR DELETE ON runtime_scope_operational_input
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
