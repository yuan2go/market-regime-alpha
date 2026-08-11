CREATE TABLE historical_research_run (
    run_id text PRIMARY KEY,
    command_hash text NOT NULL UNIQUE CHECK (
        command_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    idempotency_key text NOT NULL UNIQUE CHECK (btrim(idempotency_key) <> ''),
    start_date date NOT NULL,
    end_date date NOT NULL CHECK (end_date >= start_date),
    trading_calendar_id text NOT NULL CHECK (btrim(trading_calendar_id) <> ''),
    trading_calendar_hash text NOT NULL CHECK (
        trading_calendar_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    runtime_scope_policy_id text NOT NULL
        REFERENCES research_universe_policy(policy_id) ON DELETE RESTRICT,
    runtime_scope_policy_hash text NOT NULL CHECK (
        runtime_scope_policy_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    data_authority_mode text NOT NULL CHECK (data_authority_mode IN (
        'RECORDED_LIVE_RESEARCH', 'FREE_RESEARCH_ARCHIVE', 'QUALIFIED_FORMAL_PIT'
    )),
    evidence_qualification text NOT NULL CHECK (evidence_qualification IN (
        'EXPLORATORY_PIT_INCOMPLETE', 'FORMAL_PIT_QUALIFIED'
    )),
    status text NOT NULL CHECK (status IN (
        'PENDING', 'RUNNING', 'COMPLETE', 'COMPLETE_WITH_BLOCKS', 'FAILED'
    )),
    version integer NOT NULL CHECK (version > 0),
    command_json jsonb NOT NULL CHECK (
        jsonb_typeof(command_json) = 'object'
        AND command_json->>'schema_version' = 'historical-research-command/v1'
    ),
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    completed_at timestamptz
);

CREATE INDEX historical_research_run_period_idx
ON historical_research_run(start_date, end_date, status, run_id);

CREATE INDEX historical_research_run_scope_policy_idx
ON historical_research_run(runtime_scope_policy_id);

CREATE TABLE historical_research_session (
    run_id text NOT NULL
        REFERENCES historical_research_run(run_id) ON DELETE RESTRICT,
    session_id text NOT NULL,
    session_hash text NOT NULL CHECK (session_hash ~ '^sha256:[0-9a-f]{64}$'),
    session_ordinal integer NOT NULL CHECK (session_ordinal > 0),
    trading_date date NOT NULL,
    status text NOT NULL CHECK (status IN (
        'PENDING', 'RUNNING', 'COMPLETE', 'BLOCKED', 'FAILED'
    )),
    next_stage_ordinal integer NOT NULL CHECK (
        next_stage_ordinal BETWEEN 1 AND 6
    ),
    version integer NOT NULL CHECK (version > 0),
    fencing_token integer NOT NULL CHECK (fencing_token >= 0),
    active_claim_id text,
    lease_acquired_at timestamptz,
    lease_expires_at timestamptz,
    heartbeat_at timestamptz,
    session_json jsonb NOT NULL CHECK (
        jsonb_typeof(session_json) = 'object'
        AND session_json->>'schema_version' = 'research-decision-session/v1'
    ),
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    completed_at timestamptz,
    PRIMARY KEY (run_id, session_id),
    UNIQUE (run_id, session_ordinal),
    UNIQUE (run_id, trading_date),
    CHECK (
        (active_claim_id IS NULL AND lease_acquired_at IS NULL
         AND lease_expires_at IS NULL AND heartbeat_at IS NULL)
        OR
        (active_claim_id IS NOT NULL AND lease_acquired_at IS NOT NULL
         AND lease_expires_at IS NOT NULL AND heartbeat_at IS NOT NULL
         AND lease_expires_at > lease_acquired_at
         AND heartbeat_at >= lease_acquired_at
         AND heartbeat_at < lease_expires_at)
    )
);

CREATE INDEX historical_research_session_next_idx
ON historical_research_session(run_id, session_ordinal, status);

CREATE TABLE historical_research_stage_receipt (
    receipt_id text PRIMARY KEY,
    receipt_hash text NOT NULL UNIQUE CHECK (
        receipt_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    run_id text NOT NULL,
    session_id text NOT NULL,
    stage text NOT NULL CHECK (stage IN (
        'SCOPE', 'DECISION', 'STRATEGY', 'PORTFOLIO', 'OUTCOME', 'PERFORMANCE'
    )),
    stage_ordinal integer NOT NULL CHECK (stage_ordinal BETWEEN 1 AND 6),
    status text NOT NULL CHECK (status IN (
        'COMPLETE', 'BLOCKED', 'NOT_ESTIMABLE'
    )),
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' = 'research-session-stage-receipt/v1'
    ),
    created_at timestamptz NOT NULL,
    UNIQUE (run_id, session_id, stage_ordinal),
    FOREIGN KEY (run_id, session_id)
        REFERENCES historical_research_session(run_id, session_id)
        ON DELETE RESTRICT
);

CREATE INDEX historical_research_stage_session_idx
ON historical_research_stage_receipt(run_id, session_id, stage_ordinal);

CREATE TABLE historical_research_attempt (
    run_id text NOT NULL,
    session_id text NOT NULL,
    attempt_number integer NOT NULL CHECK (attempt_number > 0),
    claim_id text NOT NULL UNIQUE,
    stage text NOT NULL CHECK (stage IN (
        'SCOPE', 'DECISION', 'STRATEGY', 'PORTFOLIO', 'OUTCOME', 'PERFORMANCE'
    )),
    stage_ordinal integer NOT NULL CHECK (stage_ordinal BETWEEN 1 AND 6),
    fencing_token integer NOT NULL CHECK (fencing_token > 0),
    status text NOT NULL CHECK (status IN (
        'ACTIVE', 'COMPLETED', 'EXPIRED', 'FAILED'
    )),
    started_at timestamptz NOT NULL,
    lease_expires_at timestamptz NOT NULL,
    completed_at timestamptz,
    error_code text,
    PRIMARY KEY (run_id, session_id, attempt_number),
    FOREIGN KEY (run_id, session_id)
        REFERENCES historical_research_session(run_id, session_id)
        ON DELETE RESTRICT
);

CREATE INDEX historical_research_attempt_active_idx
ON historical_research_attempt(run_id, status, lease_expires_at);

CREATE TABLE historical_research_event (
    event_id bigserial PRIMARY KEY,
    run_id text NOT NULL
        REFERENCES historical_research_run(run_id) ON DELETE RESTRICT,
    session_id text,
    event_type text NOT NULL CHECK (btrim(event_type) <> ''),
    event_json jsonb NOT NULL CHECK (jsonb_typeof(event_json) = 'object'),
    created_at timestamptz NOT NULL
);

CREATE INDEX historical_research_event_run_idx
ON historical_research_event(run_id, event_id);

CREATE OR REPLACE FUNCTION guard_historical_research_run_update()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.run_id IS DISTINCT FROM OLD.run_id
       OR NEW.command_hash IS DISTINCT FROM OLD.command_hash
       OR NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key
       OR NEW.start_date IS DISTINCT FROM OLD.start_date
       OR NEW.end_date IS DISTINCT FROM OLD.end_date
       OR NEW.trading_calendar_id IS DISTINCT FROM OLD.trading_calendar_id
       OR NEW.trading_calendar_hash IS DISTINCT FROM OLD.trading_calendar_hash
       OR NEW.runtime_scope_policy_id IS DISTINCT FROM OLD.runtime_scope_policy_id
       OR NEW.runtime_scope_policy_hash IS DISTINCT FROM OLD.runtime_scope_policy_hash
       OR NEW.data_authority_mode IS DISTINCT FROM OLD.data_authority_mode
       OR NEW.evidence_qualification IS DISTINCT FROM OLD.evidence_qualification
       OR NEW.command_json IS DISTINCT FROM OLD.command_json
       OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
        RAISE EXCEPTION 'historical_research_run identity is immutable';
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION guard_historical_research_session_update()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.run_id IS DISTINCT FROM OLD.run_id
       OR NEW.session_id IS DISTINCT FROM OLD.session_id
       OR NEW.session_hash IS DISTINCT FROM OLD.session_hash
       OR NEW.session_ordinal IS DISTINCT FROM OLD.session_ordinal
       OR NEW.trading_date IS DISTINCT FROM OLD.trading_date
       OR NEW.session_json IS DISTINCT FROM OLD.session_json
       OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
        RAISE EXCEPTION 'historical_research_session identity is immutable';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER historical_research_run_identity_immutable
BEFORE UPDATE ON historical_research_run
FOR EACH ROW EXECUTE FUNCTION guard_historical_research_run_update();

CREATE TRIGGER historical_research_run_no_delete
BEFORE DELETE ON historical_research_run
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER historical_research_session_identity_immutable
BEFORE UPDATE ON historical_research_session
FOR EACH ROW EXECUTE FUNCTION guard_historical_research_session_update();

CREATE TRIGGER historical_research_session_no_delete
BEFORE DELETE ON historical_research_session
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER historical_research_stage_receipt_no_update
BEFORE UPDATE OR DELETE ON historical_research_stage_receipt
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER historical_research_attempt_no_delete
BEFORE DELETE ON historical_research_attempt
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER historical_research_event_no_update
BEFORE UPDATE OR DELETE ON historical_research_event
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
