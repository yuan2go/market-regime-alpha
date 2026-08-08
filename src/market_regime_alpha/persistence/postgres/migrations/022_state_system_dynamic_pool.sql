CREATE TABLE market_regime_state_observation (
    observation_id text PRIMARY KEY,
    observation_hash text NOT NULL UNIQUE CHECK (observation_hash ~ '^sha256:[0-9a-f]{64}$'),
    run_id text NOT NULL,
    tick_id text NOT NULL,
    as_of_time timestamptz NOT NULL,
    available_at timestamptz NOT NULL,
    artifact_json text NOT NULL CHECK (artifact_json IS JSON OBJECT),
    created_at timestamptz NOT NULL,
    FOREIGN KEY (run_id, tick_id) REFERENCES continuous_runtime_tick(run_id, tick_id) ON DELETE RESTRICT,
    CHECK (available_at <= as_of_time)
);

CREATE TABLE market_regime_state (
    state_id text PRIMARY KEY,
    state_hash text NOT NULL UNIQUE CHECK (state_hash ~ '^sha256:[0-9a-f]{64}$'),
    observation_id text NOT NULL UNIQUE REFERENCES market_regime_state_observation(observation_id) ON DELETE RESTRICT,
    previous_state_id text REFERENCES market_regime_state(state_id) ON DELETE RESTRICT,
    scope_key text NOT NULL,
    effective_state text NOT NULL,
    artifact_json text NOT NULL CHECK (artifact_json IS JSON OBJECT),
    created_at timestamptz NOT NULL
);

CREATE TABLE market_regime_state_transition (
    transition_id text PRIMARY KEY,
    transition_hash text NOT NULL UNIQUE CHECK (transition_hash ~ '^sha256:[0-9a-f]{64}$'),
    state_id text NOT NULL UNIQUE REFERENCES market_regime_state(state_id) ON DELETE RESTRICT,
    artifact_json text NOT NULL CHECK (artifact_json IS JSON OBJECT),
    created_at timestamptz NOT NULL
);

CREATE TABLE etf_rotation_state_observation (
    observation_id text PRIMARY KEY,
    observation_hash text NOT NULL UNIQUE CHECK (observation_hash ~ '^sha256:[0-9a-f]{64}$'),
    run_id text NOT NULL,
    tick_id text NOT NULL,
    as_of_time timestamptz NOT NULL,
    available_at timestamptz NOT NULL,
    artifact_json text NOT NULL CHECK (artifact_json IS JSON OBJECT),
    created_at timestamptz NOT NULL,
    FOREIGN KEY (run_id, tick_id) REFERENCES continuous_runtime_tick(run_id, tick_id) ON DELETE RESTRICT,
    CHECK (available_at <= as_of_time)
);

CREATE TABLE etf_rotation_state (
    state_id text PRIMARY KEY,
    state_hash text NOT NULL UNIQUE CHECK (state_hash ~ '^sha256:[0-9a-f]{64}$'),
    observation_id text NOT NULL UNIQUE REFERENCES etf_rotation_state_observation(observation_id) ON DELETE RESTRICT,
    previous_state_id text REFERENCES etf_rotation_state(state_id) ON DELETE RESTRICT,
    scope_key text NOT NULL,
    effective_state text NOT NULL,
    artifact_json text NOT NULL CHECK (artifact_json IS JSON OBJECT),
    created_at timestamptz NOT NULL
);

CREATE TABLE etf_rotation_state_transition (
    transition_id text PRIMARY KEY,
    transition_hash text NOT NULL UNIQUE CHECK (transition_hash ~ '^sha256:[0-9a-f]{64}$'),
    state_id text NOT NULL UNIQUE REFERENCES etf_rotation_state(state_id) ON DELETE RESTRICT,
    artifact_json text NOT NULL CHECK (artifact_json IS JSON OBJECT),
    created_at timestamptz NOT NULL
);

CREATE TABLE theme_rotation_state_observation (
    observation_id text PRIMARY KEY,
    observation_hash text NOT NULL UNIQUE CHECK (observation_hash ~ '^sha256:[0-9a-f]{64}$'),
    run_id text NOT NULL,
    tick_id text NOT NULL,
    as_of_time timestamptz NOT NULL,
    available_at timestamptz NOT NULL,
    artifact_json text NOT NULL CHECK (artifact_json IS JSON OBJECT),
    created_at timestamptz NOT NULL,
    FOREIGN KEY (run_id, tick_id) REFERENCES continuous_runtime_tick(run_id, tick_id) ON DELETE RESTRICT,
    CHECK (available_at <= as_of_time)
);

CREATE TABLE theme_rotation_state (
    state_id text PRIMARY KEY,
    state_hash text NOT NULL UNIQUE CHECK (state_hash ~ '^sha256:[0-9a-f]{64}$'),
    observation_id text NOT NULL UNIQUE REFERENCES theme_rotation_state_observation(observation_id) ON DELETE RESTRICT,
    previous_state_id text REFERENCES theme_rotation_state(state_id) ON DELETE RESTRICT,
    scope_key text NOT NULL,
    effective_state text NOT NULL,
    artifact_json text NOT NULL CHECK (artifact_json IS JSON OBJECT),
    created_at timestamptz NOT NULL
);

CREATE TABLE theme_rotation_state_transition (
    transition_id text PRIMARY KEY,
    transition_hash text NOT NULL UNIQUE CHECK (transition_hash ~ '^sha256:[0-9a-f]{64}$'),
    state_id text NOT NULL UNIQUE REFERENCES theme_rotation_state(state_id) ON DELETE RESTRICT,
    artifact_json text NOT NULL CHECK (artifact_json IS JSON OBJECT),
    created_at timestamptz NOT NULL
);

CREATE TABLE capital_state_observation (
    observation_id text PRIMARY KEY,
    observation_hash text NOT NULL UNIQUE CHECK (observation_hash ~ '^sha256:[0-9a-f]{64}$'),
    run_id text NOT NULL,
    tick_id text NOT NULL,
    as_of_time timestamptz NOT NULL,
    available_at timestamptz NOT NULL,
    artifact_json text NOT NULL CHECK (artifact_json IS JSON OBJECT),
    created_at timestamptz NOT NULL,
    FOREIGN KEY (run_id, tick_id) REFERENCES continuous_runtime_tick(run_id, tick_id) ON DELETE RESTRICT,
    CHECK (available_at <= as_of_time)
);

CREATE TABLE capital_state (
    state_id text PRIMARY KEY,
    state_hash text NOT NULL UNIQUE CHECK (state_hash ~ '^sha256:[0-9a-f]{64}$'),
    observation_id text NOT NULL UNIQUE REFERENCES capital_state_observation(observation_id) ON DELETE RESTRICT,
    previous_state_id text REFERENCES capital_state(state_id) ON DELETE RESTRICT,
    scope_key text NOT NULL,
    effective_state text NOT NULL,
    artifact_json text NOT NULL CHECK (artifact_json IS JSON OBJECT),
    created_at timestamptz NOT NULL
);

CREATE TABLE capital_state_transition (
    transition_id text PRIMARY KEY,
    transition_hash text NOT NULL UNIQUE CHECK (transition_hash ~ '^sha256:[0-9a-f]{64}$'),
    state_id text NOT NULL UNIQUE REFERENCES capital_state(state_id) ON DELETE RESTRICT,
    artifact_json text NOT NULL CHECK (artifact_json IS JSON OBJECT),
    created_at timestamptz NOT NULL
);

CREATE TABLE state_current_pointer (
    domain text NOT NULL CHECK (domain IN ('MARKET_REGIME', 'ETF_ROTATION', 'THEME_ROTATION', 'CAPITAL_STATE', 'DYNAMIC_POOL')),
    scope_key text NOT NULL,
    current_artifact_id text NOT NULL,
    current_artifact_hash text NOT NULL CHECK (current_artifact_hash ~ '^sha256:[0-9a-f]{64}$'),
    version bigint NOT NULL CHECK (version >= 1),
    last_fencing_token bigint NOT NULL CHECK (last_fencing_token >= 1),
    updated_at timestamptz NOT NULL,
    PRIMARY KEY (domain, scope_key)
);

CREATE TABLE dynamic_stock_pool (
    pool_id text PRIMARY KEY,
    pool_hash text NOT NULL UNIQUE CHECK (pool_hash ~ '^sha256:[0-9a-f]{64}$'),
    previous_pool_id text REFERENCES dynamic_stock_pool(pool_id) ON DELETE RESTRICT,
    pool_version bigint NOT NULL CHECK (pool_version >= 1),
    run_id text NOT NULL,
    tick_id text NOT NULL,
    claim_id text NOT NULL,
    fencing_token bigint NOT NULL CHECK (fencing_token >= 1),
    tick_version bigint NOT NULL CHECK (tick_version >= 1),
    effective_at timestamptz NOT NULL,
    available_at timestamptz NOT NULL,
    decision_time timestamptz NOT NULL,
    material_state_hash text NOT NULL CHECK (material_state_hash ~ '^sha256:[0-9a-f]{64}$'),
    configuration_id text NOT NULL,
    configuration_hash text NOT NULL CHECK (configuration_hash ~ '^sha256:[0-9a-f]{64}$'),
    pool_json text NOT NULL CHECK (pool_json IS JSON OBJECT),
    created_at timestamptz NOT NULL,
    UNIQUE (run_id, pool_version),
    UNIQUE (run_id, tick_id),
    FOREIGN KEY (run_id, tick_id) REFERENCES continuous_runtime_tick(run_id, tick_id) ON DELETE RESTRICT,
    CHECK (available_at <= decision_time),
    CHECK (effective_at <= decision_time)
);

CREATE TABLE dynamic_stock_pool_member (
    pool_id text NOT NULL REFERENCES dynamic_stock_pool(pool_id) ON DELETE RESTRICT,
    symbol text NOT NULL,
    included boolean NOT NULL,
    rank bigint CHECK (rank IS NULL OR rank >= 1),
    member_json text NOT NULL CHECK (member_json IS JSON OBJECT),
    PRIMARY KEY (pool_id, symbol),
    UNIQUE (pool_id, rank),
    CHECK ((included AND rank IS NOT NULL) OR (NOT included AND rank IS NULL))
);

CREATE TABLE dynamic_stock_pool_change (
    pool_id text NOT NULL REFERENCES dynamic_stock_pool(pool_id) ON DELETE RESTRICT,
    symbol text NOT NULL,
    change_type text NOT NULL CHECK (change_type IN ('ADDED', 'REMOVED')),
    change_json text NOT NULL CHECK (change_json IS JSON OBJECT),
    PRIMARY KEY (pool_id, symbol, change_type)
);

CREATE TABLE state_runtime_receipt (
    receipt_id text PRIMARY KEY,
    receipt_hash text NOT NULL UNIQUE CHECK (receipt_hash ~ '^sha256:[0-9a-f]{64}$'),
    run_id text NOT NULL,
    tick_id text NOT NULL UNIQUE,
    pool_id text REFERENCES dynamic_stock_pool(pool_id) ON DELETE RESTRICT,
    status text NOT NULL CHECK (status IN ('COMPLETED', 'NO_MATERIAL_CHANGE', 'DATA_INSUFFICIENT')),
    receipt_json text NOT NULL CHECK (receipt_json IS JSON OBJECT),
    created_at timestamptz NOT NULL,
    FOREIGN KEY (run_id, tick_id) REFERENCES continuous_runtime_tick(run_id, tick_id) ON DELETE RESTRICT
);

CREATE INDEX market_regime_state_scope_idx ON market_regime_state(scope_key, created_at DESC);
CREATE INDEX market_regime_state_observation_tick_idx ON market_regime_state_observation(run_id, tick_id);
CREATE INDEX market_regime_state_previous_idx ON market_regime_state(previous_state_id) WHERE previous_state_id IS NOT NULL;
CREATE INDEX etf_rotation_state_scope_idx ON etf_rotation_state(scope_key, created_at DESC);
CREATE INDEX etf_rotation_state_observation_tick_idx ON etf_rotation_state_observation(run_id, tick_id);
CREATE INDEX etf_rotation_state_previous_idx ON etf_rotation_state(previous_state_id) WHERE previous_state_id IS NOT NULL;
CREATE INDEX theme_rotation_state_scope_idx ON theme_rotation_state(scope_key, created_at DESC);
CREATE INDEX theme_rotation_state_observation_tick_idx ON theme_rotation_state_observation(run_id, tick_id);
CREATE INDEX theme_rotation_state_previous_idx ON theme_rotation_state(previous_state_id) WHERE previous_state_id IS NOT NULL;
CREATE INDEX capital_state_scope_idx ON capital_state(scope_key, created_at DESC);
CREATE INDEX capital_state_observation_tick_idx ON capital_state_observation(run_id, tick_id);
CREATE INDEX capital_state_previous_idx ON capital_state(previous_state_id) WHERE previous_state_id IS NOT NULL;
CREATE INDEX dynamic_stock_pool_run_idx ON dynamic_stock_pool(run_id, pool_version DESC);
CREATE INDEX dynamic_stock_pool_previous_idx ON dynamic_stock_pool(previous_pool_id) WHERE previous_pool_id IS NOT NULL;
CREATE INDEX state_runtime_receipt_tick_idx ON state_runtime_receipt(run_id, tick_id);
CREATE INDEX state_runtime_receipt_pool_idx ON state_runtime_receipt(pool_id) WHERE pool_id IS NOT NULL;

CREATE FUNCTION guard_state_current_pointer_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'State current pointers cannot be deleted';
    END IF;
    IF NEW.domain IS DISTINCT FROM OLD.domain OR NEW.scope_key IS DISTINCT FROM OLD.scope_key THEN
        RAISE EXCEPTION 'State current pointer identity is immutable';
    END IF;
    IF NEW.version != OLD.version + 1 THEN
        RAISE EXCEPTION 'State current pointer version must advance by one';
    END IF;
    IF NEW.last_fencing_token < OLD.last_fencing_token THEN
        RAISE EXCEPTION 'State current pointer fencing token cannot regress';
    END IF;
    IF NEW.current_artifact_id = OLD.current_artifact_id THEN
        RAISE EXCEPTION 'State current pointer cannot advance to identical Artifact';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER state_current_pointer_no_delete BEFORE DELETE ON state_current_pointer
FOR EACH ROW EXECUTE FUNCTION guard_state_current_pointer_mutation();
CREATE TRIGGER state_current_pointer_cas_guard BEFORE UPDATE ON state_current_pointer
FOR EACH ROW EXECUTE FUNCTION guard_state_current_pointer_mutation();

CREATE TRIGGER market_regime_state_observation_no_update BEFORE UPDATE ON market_regime_state_observation FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER market_regime_state_observation_no_delete BEFORE DELETE ON market_regime_state_observation FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER market_regime_state_no_update BEFORE UPDATE ON market_regime_state FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER market_regime_state_no_delete BEFORE DELETE ON market_regime_state FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER market_regime_state_transition_no_update BEFORE UPDATE ON market_regime_state_transition FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER market_regime_state_transition_no_delete BEFORE DELETE ON market_regime_state_transition FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER etf_rotation_state_observation_no_update BEFORE UPDATE ON etf_rotation_state_observation FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER etf_rotation_state_observation_no_delete BEFORE DELETE ON etf_rotation_state_observation FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER etf_rotation_state_no_update BEFORE UPDATE ON etf_rotation_state FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER etf_rotation_state_no_delete BEFORE DELETE ON etf_rotation_state FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER etf_rotation_state_transition_no_update BEFORE UPDATE ON etf_rotation_state_transition FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER etf_rotation_state_transition_no_delete BEFORE DELETE ON etf_rotation_state_transition FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER theme_rotation_state_observation_no_update BEFORE UPDATE ON theme_rotation_state_observation FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER theme_rotation_state_observation_no_delete BEFORE DELETE ON theme_rotation_state_observation FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER theme_rotation_state_no_update BEFORE UPDATE ON theme_rotation_state FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER theme_rotation_state_no_delete BEFORE DELETE ON theme_rotation_state FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER theme_rotation_state_transition_no_update BEFORE UPDATE ON theme_rotation_state_transition FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER theme_rotation_state_transition_no_delete BEFORE DELETE ON theme_rotation_state_transition FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER capital_state_observation_no_update BEFORE UPDATE ON capital_state_observation FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER capital_state_observation_no_delete BEFORE DELETE ON capital_state_observation FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER capital_state_no_update BEFORE UPDATE ON capital_state FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER capital_state_no_delete BEFORE DELETE ON capital_state FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER capital_state_transition_no_update BEFORE UPDATE ON capital_state_transition FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER capital_state_transition_no_delete BEFORE DELETE ON capital_state_transition FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER dynamic_stock_pool_no_update BEFORE UPDATE ON dynamic_stock_pool FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER dynamic_stock_pool_no_delete BEFORE DELETE ON dynamic_stock_pool FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER dynamic_stock_pool_member_no_update BEFORE UPDATE ON dynamic_stock_pool_member FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER dynamic_stock_pool_member_no_delete BEFORE DELETE ON dynamic_stock_pool_member FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER dynamic_stock_pool_change_no_update BEFORE UPDATE ON dynamic_stock_pool_change FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER dynamic_stock_pool_change_no_delete BEFORE DELETE ON dynamic_stock_pool_change FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER state_runtime_receipt_no_update BEFORE UPDATE ON state_runtime_receipt FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER state_runtime_receipt_no_delete BEFORE DELETE ON state_runtime_receipt FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
