-- Phase E3 owner-resolved historical Industry, shares and corporate actions.

CREATE TABLE free_data_historical_security_fact_set (
    owner_id text PRIMARY KEY CHECK (btrim(owner_id) <> ''),
    owner_hash text NOT NULL CHECK (owner_hash ~ '^sha256:[0-9a-f]{64}$'),
    first_effective_date date NOT NULL,
    last_effective_date date NOT NULL,
    known_at timestamptz NOT NULL,
    provider_id text NOT NULL CHECK (btrim(provider_id) <> ''),
    source_manifest_id text NOT NULL CHECK (btrim(source_manifest_id) <> ''),
    source_manifest_hash text NOT NULL CHECK (
        source_manifest_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    raw_archive_id text NOT NULL CHECK (btrim(raw_archive_id) <> ''),
    fact_count integer NOT NULL CHECK (fact_count > 0),
    data_eligibility text NOT NULL CHECK (data_eligibility = 'EXPLORATORY'),
    evidence_ceiling text NOT NULL CHECK (evidence_ceiling = 'PIT_INCOMPLETE'),
    formal_pit boolean NOT NULL CHECK (formal_pit = false),
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' = 'historical-security-facts-owner/v1'
        AND payload_json->>'owner_id' = owner_id
        AND payload_json->>'owner_hash' = owner_hash
        AND jsonb_array_length(payload_json->'facts') = fact_count
    ),
    created_at timestamptz NOT NULL,
    UNIQUE (owner_id, owner_hash),
    CHECK (first_effective_date <= last_effective_date),
    CHECK (created_at >= known_at)
);

CREATE INDEX free_data_historical_security_fact_set_range_idx
ON free_data_historical_security_fact_set(
    first_effective_date, last_effective_date, owner_id, owner_hash
);

CREATE TABLE free_data_historical_security_fact (
    owner_id text NOT NULL,
    owner_hash text NOT NULL CHECK (owner_hash ~ '^sha256:[0-9a-f]{64}$'),
    fact_id text NOT NULL CHECK (btrim(fact_id) <> ''),
    fact_hash text NOT NULL CHECK (fact_hash ~ '^sha256:[0-9a-f]{64}$'),
    symbol text NOT NULL CHECK (btrim(symbol) <> ''),
    fact_kind text NOT NULL CHECK (fact_kind IN (
        'INDUSTRY', 'SHARE_CAPITAL', 'ADJUSTMENT_EVENT', 'DIVIDEND_EVENT'
    )),
    effective_date date NOT NULL,
    published_date date,
    source_artifact_kind text NOT NULL CHECK (btrim(source_artifact_kind) <> ''),
    source_artifact_id text NOT NULL CHECK (btrim(source_artifact_id) <> ''),
    source_content_hash text NOT NULL CHECK (
        source_content_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' = 'historical-security-fact/v1'
        AND payload_json->>'fact_id' = fact_id
        AND payload_json->>'fact_hash' = fact_hash
        AND payload_json->>'symbol' = symbol
        AND payload_json->>'fact_kind' = fact_kind
        AND (payload_json->>'effective_date')::date = effective_date
    ),
    PRIMARY KEY (owner_id, fact_id),
    UNIQUE (owner_id, fact_hash),
    FOREIGN KEY (owner_id, owner_hash)
        REFERENCES free_data_historical_security_fact_set(owner_id, owner_hash)
        ON DELETE RESTRICT
);

CREATE INDEX free_data_historical_security_fact_lookup_idx
ON free_data_historical_security_fact(
    owner_id, symbol, fact_kind, effective_date DESC,
    published_date DESC, fact_id
);

CREATE INDEX free_data_historical_security_fact_owner_fk_idx
ON free_data_historical_security_fact(owner_id, owner_hash);

CREATE TRIGGER free_data_historical_security_fact_set_no_update
BEFORE UPDATE OR DELETE ON free_data_historical_security_fact_set
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER free_data_historical_security_fact_no_update
BEFORE UPDATE OR DELETE ON free_data_historical_security_fact
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

COMMENT ON TABLE free_data_historical_security_fact_set IS
'Immutable exploratory owner for historical Industry, published shares and corporate actions; never Formal PIT.';

COMMENT ON TABLE free_data_historical_security_fact IS
'Exact effective/publication-dated fact projection consumed by Phase E3 Historical materialization.';
