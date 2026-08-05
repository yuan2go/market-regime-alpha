CREATE TABLE lifecycle_runs (
    run_id text PRIMARY KEY,
    idempotency_key text NOT NULL UNIQUE,
    command_hash text NOT NULL CHECK (
        command_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    command_json text NOT NULL CHECK (command_json IS JSON),
    run_type text NOT NULL CHECK (
        run_type IN (
            'CANONICAL_DECISION_LIFECYCLE',
            'RISK_REDUCTION_CONTINUATION',
            'REPLAY'
        )
    ),
    decision_date date NOT NULL,
    as_of_time timestamptz NOT NULL,
    status text NOT NULL CHECK (
        status IN (
            'CREATED',
            'RUNNING',
            'RETRYING',
            'WAITING_FOR_ENTRY_CONFIRMATION',
            'BLOCKED_BY_MODEL_VALIDATION',
            'WAITING_FOR_MANUAL_CONFIRMATION',
            'WAITING_FOR_FILL',
            'POSITION_OPEN',
            'WAITING_FOR_T1',
            'READY_FOR_HOLDING_ASSESSMENT',
            'READY_FOR_EXIT_REVIEW',
            'COMPLETED',
            'FAILED'
        )
    ),
    current_stage text CHECK (
        current_stage IS NULL OR current_stage IN (
            'VERIFY_COMPOSITE_EVIDENCE',
            'PLATFORM_RESEARCH',
            'SIGNAL',
            'PATH_FORECAST',
            'ENTRY_ASSESSMENT',
            'OPPORTUNITY',
            'THESIS',
            'PORTFOLIO_RISK',
            'RISK_REDUCTION',
            'MANUAL_CONFIRMATION',
            'MANUAL_TRADE',
            'FILL_POSITION',
            'THESIS_HEALTH',
            'HOLDING_ASSESSMENT',
            'EXIT_ASSESSMENT',
            'OUTCOME_REVIEW'
        )
    ),
    input_manifest_id text,
    input_content_hash text CHECK (
        input_content_hash IS NULL
        OR input_content_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    run_json text NOT NULL CHECK (run_json IS JSON),
    version bigint NOT NULL CHECK (version > 0),
    claim_token bigint NOT NULL CHECK (claim_token >= 0),
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    completed_at timestamptz,
    CHECK ((input_manifest_id IS NULL) = (input_content_hash IS NULL))
);

CREATE TABLE lifecycle_stages (
    run_id text NOT NULL,
    stage_name text NOT NULL CHECK (
        stage_name IN (
            'VERIFY_COMPOSITE_EVIDENCE',
            'PLATFORM_RESEARCH',
            'SIGNAL',
            'PATH_FORECAST',
            'ENTRY_ASSESSMENT',
            'OPPORTUNITY',
            'THESIS',
            'PORTFOLIO_RISK',
            'RISK_REDUCTION',
            'MANUAL_CONFIRMATION',
            'MANUAL_TRADE',
            'FILL_POSITION',
            'THESIS_HEALTH',
            'HOLDING_ASSESSMENT',
            'EXIT_ASSESSMENT',
            'OUTCOME_REVIEW'
        )
    ),
    stage_status text NOT NULL CHECK (
        stage_status IN (
            'PENDING',
            'RUNNING',
            'COMPLETED',
            'WAITING',
            'BLOCKED',
            'FAILED',
            'SKIPPED_NOT_APPLICABLE'
        )
    ),
    attempt_count bigint NOT NULL CHECK (attempt_count >= 0),
    stage_json text NOT NULL CHECK (stage_json IS JSON),
    version bigint NOT NULL CHECK (version > 0),
    PRIMARY KEY (run_id, stage_name),
    FOREIGN KEY (run_id) REFERENCES lifecycle_runs(run_id) ON DELETE RESTRICT
);

CREATE TABLE lifecycle_attempts (
    attempt_id text PRIMARY KEY,
    run_id text NOT NULL,
    stage_name text NOT NULL,
    attempt_number bigint NOT NULL CHECK (attempt_number > 0),
    result text NOT NULL CHECK (
        result IN (
            'RUNNING',
            'COMPLETED',
            'WAITING',
            'BLOCKED',
            'FAILED',
            'SKIPPED_NOT_APPLICABLE'
        )
    ),
    attempt_json text NOT NULL CHECK (attempt_json IS JSON),
    claim_token bigint NOT NULL CHECK (claim_token > 0),
    started_at timestamptz NOT NULL,
    completed_at timestamptz,
    exception_type text,
    exception_message text,
    UNIQUE (run_id, stage_name, attempt_number),
    UNIQUE (attempt_id, run_id, stage_name),
    FOREIGN KEY (run_id, stage_name)
        REFERENCES lifecycle_stages(run_id, stage_name) ON DELETE RESTRICT,
    CHECK (
        (result = 'RUNNING' AND completed_at IS NULL)
        OR (result != 'RUNNING' AND completed_at IS NOT NULL)
    ),
    CHECK ((exception_type IS NULL) = (exception_message IS NULL)),
    CHECK ((result = 'FAILED') = (exception_type IS NOT NULL))
);

CREATE TABLE lifecycle_stage_receipts (
    receipt_id text PRIMARY KEY,
    run_id text NOT NULL,
    stage_name text NOT NULL,
    attempt_number bigint NOT NULL CHECK (attempt_number > 0),
    receipt_hash text NOT NULL CHECK (
        receipt_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    receipt_json text NOT NULL CHECK (receipt_json IS JSON),
    stage_result text NOT NULL CHECK (
        stage_result IN (
            'COMPLETED',
            'WAITING',
            'BLOCKED',
            'SKIPPED_NOT_APPLICABLE'
        )
    ),
    created_at timestamptz NOT NULL,
    UNIQUE (run_id, stage_name, receipt_hash),
    UNIQUE (receipt_id, run_id, stage_name),
    FOREIGN KEY (run_id, stage_name, attempt_number)
        REFERENCES lifecycle_attempts(run_id, stage_name, attempt_number)
        ON DELETE RESTRICT
);

CREATE INDEX lifecycle_stage_receipts_attempt_idx
ON lifecycle_stage_receipts(run_id, stage_name, attempt_number);

CREATE TABLE lifecycle_events (
    event_id text PRIMARY KEY,
    run_id text NOT NULL,
    sequence_number bigint NOT NULL CHECK (sequence_number > 0),
    event_type text NOT NULL CHECK (
        event_type IN (
            'RUN_CREATED',
            'RUN_CLAIMED',
            'RUN_STATUS_CHANGED',
            'STAGE_STATUS_CHANGED',
            'ATTEMPT_STARTED',
            'ATTEMPT_FINISHED',
            'RECEIPT_RECORDED'
        )
    ),
    stage_name text,
    attempt_id text,
    receipt_id text,
    event_json text NOT NULL CHECK (event_json IS JSON),
    payload_json text NOT NULL CHECK (payload_json IS JSON),
    payload_hash text NOT NULL CHECK (
        payload_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    created_at timestamptz NOT NULL,
    claim_token bigint NOT NULL CHECK (claim_token >= 0),
    UNIQUE (run_id, sequence_number),
    FOREIGN KEY (run_id) REFERENCES lifecycle_runs(run_id) ON DELETE RESTRICT,
    FOREIGN KEY (run_id, stage_name)
        REFERENCES lifecycle_stages(run_id, stage_name) ON DELETE RESTRICT,
    FOREIGN KEY (attempt_id, run_id, stage_name)
        REFERENCES lifecycle_attempts(attempt_id, run_id, stage_name)
        ON DELETE RESTRICT,
    FOREIGN KEY (receipt_id, run_id, stage_name)
        REFERENCES lifecycle_stage_receipts(receipt_id, run_id, stage_name)
        ON DELETE RESTRICT,
    CHECK (attempt_id IS NULL OR stage_name IS NOT NULL),
    CHECK (receipt_id IS NULL OR stage_name IS NOT NULL),
    CHECK (
        event_type NOT IN (
            'STAGE_STATUS_CHANGED',
            'ATTEMPT_STARTED',
            'ATTEMPT_FINISHED',
            'RECEIPT_RECORDED'
        ) OR stage_name IS NOT NULL
    ),
    CHECK (
        (event_type IN ('ATTEMPT_STARTED', 'ATTEMPT_FINISHED'))
        = (attempt_id IS NOT NULL)
    ),
    CHECK ((event_type = 'RECEIPT_RECORDED') = (receipt_id IS NOT NULL))
);

CREATE INDEX lifecycle_runs_status_decision_date_idx
ON lifecycle_runs(status, decision_date, run_id);
CREATE INDEX lifecycle_stages_status_idx
ON lifecycle_stages(stage_status, stage_name, run_id);
CREATE INDEX lifecycle_attempts_history_idx
ON lifecycle_attempts(run_id, stage_name, attempt_number);
CREATE INDEX lifecycle_receipts_history_idx
ON lifecycle_stage_receipts(run_id, created_at, receipt_id);
CREATE INDEX lifecycle_events_history_idx
ON lifecycle_events(run_id, sequence_number);
CREATE INDEX lifecycle_events_stage_idx
ON lifecycle_events(run_id, stage_name);
CREATE INDEX lifecycle_events_attempt_idx
ON lifecycle_events(attempt_id, run_id, stage_name);
CREATE INDEX lifecycle_events_receipt_idx
ON lifecycle_events(receipt_id, run_id, stage_name);

CREATE FUNCTION guard_lifecycle_attempt_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'lifecycle attempts are append-only';
    END IF;
    IF OLD.result != 'RUNNING' THEN
        RAISE EXCEPTION 'settled lifecycle attempts are append-only';
    END IF;
    IF NEW.attempt_id IS DISTINCT FROM OLD.attempt_id
       OR NEW.run_id IS DISTINCT FROM OLD.run_id
       OR NEW.stage_name IS DISTINCT FROM OLD.stage_name
       OR NEW.attempt_number IS DISTINCT FROM OLD.attempt_number
       OR NEW.claim_token IS DISTINCT FROM OLD.claim_token
       OR NEW.started_at IS DISTINCT FROM OLD.started_at
       OR NEW.result = 'RUNNING'
       OR NEW.completed_at IS NULL THEN
        RAISE EXCEPTION 'lifecycle attempt permits one completion only';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER lifecycle_attempts_no_delete
BEFORE DELETE ON lifecycle_attempts
FOR EACH ROW EXECUTE FUNCTION guard_lifecycle_attempt_mutation();
CREATE TRIGGER lifecycle_attempts_completion_only
BEFORE UPDATE ON lifecycle_attempts
FOR EACH ROW EXECUTE FUNCTION guard_lifecycle_attempt_mutation();

CREATE TRIGGER lifecycle_stage_receipts_no_update
BEFORE UPDATE ON lifecycle_stage_receipts
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER lifecycle_stage_receipts_no_delete
BEFORE DELETE ON lifecycle_stage_receipts
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER lifecycle_events_no_update
BEFORE UPDATE ON lifecycle_events
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER lifecycle_events_no_delete
BEFORE DELETE ON lifecycle_events
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE FUNCTION guard_lifecycle_stage_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'lifecycle stages cannot be deleted';
    END IF;
    IF OLD.stage_status IN ('COMPLETED', 'BLOCKED', 'SKIPPED_NOT_APPLICABLE') THEN
        RAISE EXCEPTION 'terminal lifecycle stages are immutable';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER lifecycle_terminal_stages_immutable
BEFORE UPDATE ON lifecycle_stages
FOR EACH ROW EXECUTE FUNCTION guard_lifecycle_stage_mutation();
CREATE TRIGGER lifecycle_stages_no_delete
BEFORE DELETE ON lifecycle_stages
FOR EACH ROW EXECUTE FUNCTION guard_lifecycle_stage_mutation();

CREATE FUNCTION guard_lifecycle_run_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'lifecycle runs cannot be deleted';
    END IF;
    IF NEW.run_id IS DISTINCT FROM OLD.run_id
       OR NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key
       OR NEW.command_hash IS DISTINCT FROM OLD.command_hash
       OR NEW.command_json IS DISTINCT FROM OLD.command_json
       OR NEW.run_type IS DISTINCT FROM OLD.run_type
       OR NEW.decision_date IS DISTINCT FROM OLD.decision_date
       OR NEW.as_of_time IS DISTINCT FROM OLD.as_of_time
       OR NEW.input_manifest_id IS DISTINCT FROM OLD.input_manifest_id
       OR NEW.input_content_hash IS DISTINCT FROM OLD.input_content_hash
       OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
        RAISE EXCEPTION 'lifecycle run command identity is immutable';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER lifecycle_runs_no_delete
BEFORE DELETE ON lifecycle_runs
FOR EACH ROW EXECUTE FUNCTION guard_lifecycle_run_mutation();
CREATE TRIGGER lifecycle_runs_identity_immutable
BEFORE UPDATE ON lifecycle_runs
FOR EACH ROW EXECUTE FUNCTION guard_lifecycle_run_mutation();
