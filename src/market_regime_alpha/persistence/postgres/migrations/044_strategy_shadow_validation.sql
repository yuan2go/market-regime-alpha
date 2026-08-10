CREATE TABLE strategy_shadow_session (
    session_id text PRIMARY KEY,
    session_hash text NOT NULL CHECK (session_hash ~ '^sha256:[0-9a-f]{64}$'),
    trading_date date NOT NULL,
    scheduled_for timestamptz NOT NULL,
    research_shadow_id text NOT NULL,
    runtime_run_id text NOT NULL REFERENCES continuous_research_run(run_id) ON DELETE RESTRICT,
    runtime_tick_id text NOT NULL,
    policy_id text NOT NULL,
    status text NOT NULL CHECK (status IN ('SCHEDULED', 'RUNNING', 'SETTLED', 'FAILED')),
    revision bigint NOT NULL CHECK (revision >= 1),
    payload_json jsonb NOT NULL CHECK (jsonb_typeof(payload_json) = 'object'),
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    FOREIGN KEY (runtime_run_id, runtime_tick_id)
        REFERENCES continuous_runtime_tick(run_id, tick_id) ON DELETE RESTRICT
);

CREATE INDEX strategy_shadow_session_date_idx
ON strategy_shadow_session(trading_date, status);
CREATE INDEX strategy_shadow_session_run_idx
ON strategy_shadow_session(runtime_run_id);
CREATE INDEX strategy_shadow_session_tick_idx
ON strategy_shadow_session(runtime_run_id, runtime_tick_id);

CREATE TABLE strategy_shadow_event (
    session_id text NOT NULL REFERENCES strategy_shadow_session(session_id) ON DELETE RESTRICT,
    sequence bigint NOT NULL CHECK (sequence >= 1),
    event_id text NOT NULL UNIQUE,
    event_hash text NOT NULL UNIQUE CHECK (event_hash ~ '^sha256:[0-9a-f]{64}$'),
    event_kind text NOT NULL,
    occurred_at timestamptz NOT NULL,
    artifact_id text,
    payload_json jsonb NOT NULL CHECK (jsonb_typeof(payload_json) = 'object'),
    PRIMARY KEY (session_id, sequence)
);

CREATE TABLE strategy_shadow_artifact (
    artifact_id text PRIMARY KEY,
    artifact_hash text NOT NULL UNIQUE CHECK (artifact_hash ~ '^sha256:[0-9a-f]{64}$'),
    session_id text NOT NULL REFERENCES strategy_shadow_session(session_id) ON DELETE RESTRICT,
    artifact_kind text NOT NULL CHECK (artifact_kind IN (
        'POLICY', 'ENTRY', 'FILL', 'POSITION', 'HOLDING_ASSESSMENT',
        'EXIT_ASSESSMENT', 'STRATEGY_OUTCOME', 'DAILY_REPORT'
    )),
    real_trading_mutation boolean NOT NULL DEFAULT false CHECK (NOT real_trading_mutation),
    payload_json jsonb NOT NULL CHECK (jsonb_typeof(payload_json) = 'object'),
    created_at timestamptz NOT NULL
);

CREATE INDEX strategy_shadow_artifact_session_idx
ON strategy_shadow_artifact(session_id, artifact_kind, created_at);

CREATE FUNCTION guard_strategy_shadow_session_update() RETURNS trigger AS $$
BEGIN
    IF NEW.session_id <> OLD.session_id
       OR NEW.trading_date <> OLD.trading_date
       OR NEW.scheduled_for <> OLD.scheduled_for
       OR NEW.research_shadow_id <> OLD.research_shadow_id
       OR NEW.runtime_run_id <> OLD.runtime_run_id
       OR NEW.runtime_tick_id <> OLD.runtime_tick_id
       OR NEW.policy_id <> OLD.policy_id
       OR NEW.created_at <> OLD.created_at
       OR NEW.revision <> OLD.revision + 1
       OR NEW.updated_at < OLD.updated_at THEN
        RAISE EXCEPTION 'Strategy Shadow session identity/CAS violation';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER strategy_shadow_session_guard BEFORE UPDATE ON strategy_shadow_session
FOR EACH ROW EXECUTE FUNCTION guard_strategy_shadow_session_update();
CREATE TRIGGER strategy_shadow_session_no_delete BEFORE DELETE ON strategy_shadow_session
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER strategy_shadow_event_no_update BEFORE UPDATE ON strategy_shadow_event
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER strategy_shadow_event_no_delete BEFORE DELETE ON strategy_shadow_event
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER strategy_shadow_artifact_no_update BEFORE UPDATE ON strategy_shadow_artifact
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER strategy_shadow_artifact_no_delete BEFORE DELETE ON strategy_shadow_artifact
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
