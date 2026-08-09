CREATE TABLE state_policy_authority (
    policy_id text PRIMARY KEY,
    policy_hash text NOT NULL UNIQUE CHECK (policy_hash ~ '^sha256:[0-9a-f]{64}$'),
    policy_version text NOT NULL,
    domain text NOT NULL CHECK (
        domain IN ('MARKET_REGIME', 'ETF_ROTATION', 'THEME_ROTATION', 'CAPITAL_STATE', 'DYNAMIC_POOL')
    ),
    policy_json text NOT NULL CHECK (policy_json IS JSON OBJECT),
    created_at timestamptz NOT NULL
);

CREATE TABLE state_series (
    series_id text PRIMARY KEY,
    series_hash text NOT NULL UNIQUE CHECK (series_hash ~ '^sha256:[0-9a-f]{64}$'),
    domain text NOT NULL CHECK (
        domain IN ('MARKET_REGIME', 'ETF_ROTATION', 'THEME_ROTATION', 'CAPITAL_STATE', 'DYNAMIC_POOL')
    ),
    logical_scope text NOT NULL,
    research_family text NOT NULL,
    authority_mode text NOT NULL,
    universe_policy_id text NOT NULL,
    universe_policy_hash text NOT NULL CHECK (universe_policy_hash ~ '^sha256:[0-9a-f]{64}$'),
    model_id text NOT NULL,
    model_version text NOT NULL,
    configuration_id text NOT NULL,
    configuration_hash text NOT NULL CHECK (configuration_hash ~ '^sha256:[0-9a-f]{64}$'),
    state_policy_id text NOT NULL REFERENCES state_policy_authority(policy_id) ON DELETE RESTRICT,
    state_policy_version text NOT NULL,
    state_policy_hash text NOT NULL CHECK (state_policy_hash ~ '^sha256:[0-9a-f]{64}$'),
    series_json text NOT NULL CHECK (series_json IS JSON OBJECT),
    created_at timestamptz NOT NULL,
    UNIQUE (domain, logical_scope, research_family, authority_mode,
            universe_policy_hash, model_id, model_version,
            configuration_hash, state_policy_hash)
);

CREATE TABLE state_series_link (
    link_id text PRIMARY KEY,
    link_hash text NOT NULL UNIQUE CHECK (link_hash ~ '^sha256:[0-9a-f]{64}$'),
    series_id text NOT NULL REFERENCES state_series(series_id) ON DELETE RESTRICT,
    previous_link_id text REFERENCES state_series_link(link_id) ON DELETE RESTRICT,
    previous_artifact_id text,
    artifact_id text NOT NULL,
    artifact_hash text NOT NULL CHECK (artifact_hash ~ '^sha256:[0-9a-f]{64}$'),
    market_regime_state_id text REFERENCES market_regime_state(state_id) ON DELETE RESTRICT,
    etf_rotation_state_id text REFERENCES etf_rotation_state(state_id) ON DELETE RESTRICT,
    theme_rotation_state_id text REFERENCES theme_rotation_state(state_id) ON DELETE RESTRICT,
    capital_state_id text REFERENCES capital_state(state_id) ON DELETE RESTRICT,
    dynamic_pool_id text REFERENCES dynamic_stock_pool(pool_id) ON DELETE RESTRICT,
    run_id text NOT NULL,
    tick_id text NOT NULL,
    trading_date date NOT NULL,
    tick_sequence bigint NOT NULL CHECK (tick_sequence >= 1),
    fencing_token bigint NOT NULL CHECK (fencing_token >= 1),
    as_of_time timestamptz NOT NULL,
    available_at timestamptz NOT NULL,
    link_json text NOT NULL CHECK (link_json IS JSON OBJECT),
    created_at timestamptz NOT NULL,
    FOREIGN KEY (run_id, tick_id) REFERENCES continuous_runtime_tick(run_id, tick_id) ON DELETE RESTRICT,
    CHECK (available_at <= as_of_time),
    CHECK (
        (market_regime_state_id IS NOT NULL)::integer
      + (etf_rotation_state_id IS NOT NULL)::integer
      + (theme_rotation_state_id IS NOT NULL)::integer
      + (capital_state_id IS NOT NULL)::integer
      + (dynamic_pool_id IS NOT NULL)::integer = 1
    ),
    CHECK (
        (market_regime_state_id IS NULL OR artifact_id = market_regime_state_id)
        AND (etf_rotation_state_id IS NULL OR artifact_id = etf_rotation_state_id)
        AND (theme_rotation_state_id IS NULL OR artifact_id = theme_rotation_state_id)
        AND (capital_state_id IS NULL OR artifact_id = capital_state_id)
        AND (dynamic_pool_id IS NULL OR artifact_id = dynamic_pool_id)
    ),
    UNIQUE (series_id, artifact_id),
    UNIQUE (series_id, run_id, tick_id)
);

CREATE TABLE state_series_head (
    series_id text PRIMARY KEY REFERENCES state_series(series_id) ON DELETE RESTRICT,
    current_link_id text NOT NULL UNIQUE REFERENCES state_series_link(link_id) ON DELETE RESTRICT,
    current_artifact_id text NOT NULL,
    current_artifact_hash text NOT NULL CHECK (current_artifact_hash ~ '^sha256:[0-9a-f]{64}$'),
    current_run_id text NOT NULL,
    current_tick_id text NOT NULL,
    current_tick_sequence bigint NOT NULL CHECK (current_tick_sequence >= 1),
    current_as_of_time timestamptz NOT NULL,
    version bigint NOT NULL CHECK (version >= 1),
    last_fencing_token bigint NOT NULL CHECK (last_fencing_token >= 1),
    updated_at timestamptz NOT NULL,
    FOREIGN KEY (current_run_id, current_tick_id)
        REFERENCES continuous_runtime_tick(run_id, tick_id) ON DELETE RESTRICT
);

CREATE INDEX state_series_scope_idx ON state_series(domain, logical_scope, series_id);
CREATE INDEX state_series_policy_idx ON state_series(state_policy_id);
CREATE INDEX state_series_link_chain_idx ON state_series_link(series_id, as_of_time, link_id);
CREATE INDEX state_series_link_date_idx ON state_series_link(trading_date, series_id);
CREATE INDEX state_series_link_previous_idx ON state_series_link(previous_link_id)
WHERE previous_link_id IS NOT NULL;
CREATE INDEX state_series_link_market_idx ON state_series_link(market_regime_state_id)
WHERE market_regime_state_id IS NOT NULL;
CREATE INDEX state_series_link_etf_idx ON state_series_link(etf_rotation_state_id)
WHERE etf_rotation_state_id IS NOT NULL;
CREATE INDEX state_series_link_theme_idx ON state_series_link(theme_rotation_state_id)
WHERE theme_rotation_state_id IS NOT NULL;
CREATE INDEX state_series_link_capital_idx ON state_series_link(capital_state_id)
WHERE capital_state_id IS NOT NULL;
CREATE INDEX state_series_link_pool_idx ON state_series_link(dynamic_pool_id)
WHERE dynamic_pool_id IS NOT NULL;
CREATE INDEX state_series_link_tick_idx ON state_series_link(run_id, tick_id);
CREATE INDEX state_series_head_tick_idx ON state_series_head(current_run_id, current_tick_id);

CREATE FUNCTION guard_state_series_head_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'State Series heads cannot be deleted';
    END IF;
    IF NEW.series_id IS DISTINCT FROM OLD.series_id THEN
        RAISE EXCEPTION 'State Series head identity is immutable';
    END IF;
    IF NEW.version != OLD.version + 1 THEN
        RAISE EXCEPTION 'State Series head version must advance by one';
    END IF;
    IF NEW.current_as_of_time <= OLD.current_as_of_time THEN
        RAISE EXCEPTION 'State Series AsOfTime must advance';
    END IF;
    IF NEW.current_run_id = OLD.current_run_id THEN
        IF NEW.current_tick_sequence <= OLD.current_tick_sequence THEN
            RAISE EXCEPTION 'State Series Tick sequence must advance within a Run';
        END IF;
        IF NEW.last_fencing_token < OLD.last_fencing_token THEN
            RAISE EXCEPTION 'State Series fencing token cannot regress within a Run';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER state_series_head_no_delete
BEFORE DELETE ON state_series_head
FOR EACH ROW EXECUTE FUNCTION guard_state_series_head_mutation();
CREATE TRIGGER state_series_head_cas_guard
BEFORE UPDATE ON state_series_head
FOR EACH ROW EXECUTE FUNCTION guard_state_series_head_mutation();

CREATE TRIGGER state_policy_authority_no_update BEFORE UPDATE ON state_policy_authority
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER state_policy_authority_no_delete BEFORE DELETE ON state_policy_authority
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER state_series_no_update BEFORE UPDATE ON state_series
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER state_series_no_delete BEFORE DELETE ON state_series
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER state_series_link_no_update BEFORE UPDATE ON state_series_link
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER state_series_link_no_delete BEFORE DELETE ON state_series_link
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
