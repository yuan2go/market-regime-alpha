CREATE UNIQUE INDEX continuous_research_single_parent_per_trading_date
ON continuous_research_run(trading_date);

CREATE TABLE continuous_runtime_schedule (
    schedule_id text PRIMARY KEY,
    schedule_hash text NOT NULL UNIQUE CHECK (
        schedule_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    run_id text NOT NULL UNIQUE,
    policy_id text NOT NULL,
    policy_hash text NOT NULL CHECK (
        policy_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    trading_calendar_id text NOT NULL,
    trading_calendar_hash text NOT NULL CHECK (
        trading_calendar_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    status text NOT NULL CHECK (
        status IN ('ACTIVE', 'NON_TRADING_DAY', 'CLOSED')
    ),
    next_tick_at timestamptz,
    last_reserved_tick_id text,
    last_reserved_at timestamptz,
    version bigint NOT NULL CHECK (version >= 1),
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    closed_at timestamptz,
    FOREIGN KEY (run_id)
        REFERENCES continuous_research_run(run_id) ON DELETE RESTRICT,
    FOREIGN KEY (run_id, last_reserved_tick_id)
        REFERENCES continuous_runtime_tick(run_id, tick_id) ON DELETE RESTRICT,
    CHECK ((last_reserved_tick_id IS NULL) = (last_reserved_at IS NULL)),
    CHECK ((status = 'ACTIVE') = (next_tick_at IS NOT NULL)),
    CHECK ((status = 'CLOSED') = (closed_at IS NOT NULL))
);

CREATE INDEX continuous_runtime_schedule_due_idx
ON continuous_runtime_schedule(status, next_tick_at, run_id)
WHERE status = 'ACTIVE';

CREATE INDEX continuous_runtime_schedule_last_tick_idx
ON continuous_runtime_schedule(run_id, last_reserved_tick_id)
WHERE last_reserved_tick_id IS NOT NULL;

CREATE FUNCTION guard_continuous_runtime_schedule_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Continuous Runtime schedules cannot be deleted';
    END IF;
    IF NEW.schedule_id IS DISTINCT FROM OLD.schedule_id
       OR NEW.schedule_hash IS DISTINCT FROM OLD.schedule_hash
       OR NEW.run_id IS DISTINCT FROM OLD.run_id
       OR NEW.policy_id IS DISTINCT FROM OLD.policy_id
       OR NEW.policy_hash IS DISTINCT FROM OLD.policy_hash
       OR NEW.trading_calendar_id IS DISTINCT FROM OLD.trading_calendar_id
       OR NEW.trading_calendar_hash IS DISTINCT FROM OLD.trading_calendar_hash
       OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
        RAISE EXCEPTION 'Continuous Runtime schedule identity is immutable';
    END IF;
    IF NEW.version != OLD.version + 1 THEN
        RAISE EXCEPTION 'Continuous Runtime schedule version must advance by one';
    END IF;
    IF OLD.status IN ('NON_TRADING_DAY', 'CLOSED') AND NEW IS DISTINCT FROM OLD THEN
        RAISE EXCEPTION 'Terminal Continuous Runtime schedule is immutable';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER continuous_runtime_schedule_no_delete
BEFORE DELETE ON continuous_runtime_schedule
FOR EACH ROW EXECUTE FUNCTION guard_continuous_runtime_schedule_mutation();

CREATE TRIGGER continuous_runtime_schedule_identity_immutable
BEFORE UPDATE ON continuous_runtime_schedule
FOR EACH ROW EXECUTE FUNCTION guard_continuous_runtime_schedule_mutation();
