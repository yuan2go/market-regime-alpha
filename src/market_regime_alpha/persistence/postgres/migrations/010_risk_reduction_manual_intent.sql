ALTER TABLE manual_trade_records
    ADD COLUMN authority_route text NOT NULL DEFAULT 'INCREASING'
        CHECK (authority_route IN ('INCREASING', 'REDUCING')),
    ADD COLUMN risk_reducing_decision_id text,
    ADD COLUMN risk_reduction_confirmation_id text,
    ALTER COLUMN risk_decision_id DROP NOT NULL,
    ADD CONSTRAINT manual_trade_authority_route_check CHECK (
        (
            authority_route = 'INCREASING'
            AND risk_decision_id IS NOT NULL
            AND risk_reducing_decision_id IS NULL
            AND risk_reduction_confirmation_id IS NULL
        )
        OR
        (
            authority_route = 'REDUCING'
            AND risk_decision_id IS NULL
            AND risk_reducing_decision_id IS NOT NULL
            AND risk_reduction_confirmation_id IS NOT NULL
        )
    );

CREATE TABLE operational_exit_directives (
    directive_id text PRIMARY KEY,
    content_hash text NOT NULL UNIQUE,
    exit_assessment_id text NOT NULL,
    risk_reducing_decision_id text NOT NULL,
    thesis_health_observation_id text NOT NULL,
    composite_manifest_id text NOT NULL,
    directive_json text NOT NULL CHECK (directive_json IS JSON),
    exit_assessment_json text NOT NULL CHECK (exit_assessment_json IS JSON),
    created_at timestamptz NOT NULL
);

CREATE TABLE risk_reduction_confirmation_attempts (
    attempt_id text PRIMARY KEY,
    content_hash text NOT NULL UNIQUE,
    state text NOT NULL CHECK (
        state IN (
            'CONFIRMED_INTENT',
            'EXPIRED',
            'POSITION_CHANGED',
            'BLOCKED_ON_RECHECK',
            'DATA_INSUFFICIENT',
            'ACTION_SEMANTICS_CONFLICT'
        )
    ),
    risk_reducing_decision_id text NOT NULL,
    exit_directive_id text NOT NULL,
    manual_trade_id text UNIQUE,
    attempt_json text NOT NULL CHECK (attempt_json IS JSON),
    policy_json text NOT NULL CHECK (policy_json IS JSON),
    recheck_observation_json text NOT NULL CHECK (recheck_observation_json IS JSON),
    current_position_json text NOT NULL CHECK (current_position_json IS JSON),
    trading_calendar_json text NOT NULL CHECK (trading_calendar_json IS JSON),
    symbol_trading_status_json text NOT NULL
        CHECK (symbol_trading_status_json IS JSON),
    created_at timestamptz NOT NULL,
    FOREIGN KEY (exit_directive_id)
        REFERENCES operational_exit_directives(directive_id),
    FOREIGN KEY (manual_trade_id)
        REFERENCES manual_trade_records(manual_trade_id),
    CHECK (
        (state = 'CONFIRMED_INTENT' AND manual_trade_id IS NOT NULL)
        OR (state != 'CONFIRMED_INTENT' AND manual_trade_id IS NULL)
    )
);

CREATE INDEX risk_reduction_attempts_exit_directive_idx
ON risk_reduction_confirmation_attempts(exit_directive_id);

CREATE UNIQUE INDEX one_confirmed_intent_per_reducing_decision
ON risk_reduction_confirmation_attempts(risk_reducing_decision_id)
WHERE state = 'CONFIRMED_INTENT';

CREATE TABLE risk_reduction_confirmation_commands (
    idempotency_key text PRIMARY KEY,
    command_hash text NOT NULL,
    risk_reducing_decision_id text NOT NULL,
    attempt_id text NOT NULL,
    manual_trade_id text,
    created_at timestamptz NOT NULL,
    FOREIGN KEY (attempt_id)
        REFERENCES risk_reduction_confirmation_attempts(attempt_id),
    FOREIGN KEY (manual_trade_id)
        REFERENCES manual_trade_records(manual_trade_id)
);

CREATE INDEX risk_reduction_confirmation_commands_attempt_idx
ON risk_reduction_confirmation_commands(attempt_id);

CREATE INDEX risk_reduction_confirmation_commands_manual_trade_idx
ON risk_reduction_confirmation_commands(manual_trade_id);

CREATE TABLE risk_reducing_manual_trade_bindings (
    manual_trade_id text PRIMARY KEY,
    position_book_id text NOT NULL,
    opportunity_id text NOT NULL,
    thesis_id text NOT NULL,
    symbol text NOT NULL,
    risk_reducing_decision_id text NOT NULL UNIQUE,
    risk_reducing_decision_hash text NOT NULL,
    confirmation_attempt_id text NOT NULL UNIQUE,
    confirmation_attempt_hash text NOT NULL,
    source_position_snapshot_id text NOT NULL,
    source_position_snapshot_hash text NOT NULL,
    source_position_snapshot_version bigint NOT NULL
        CHECK (source_position_snapshot_version >= 0),
    target_quantity bigint NOT NULL CHECK (target_quantity >= 0),
    order_quantity bigint NOT NULL CHECK (order_quantity > 0),
    created_at timestamptz NOT NULL,
    FOREIGN KEY (manual_trade_id)
        REFERENCES manual_trade_records(manual_trade_id),
    FOREIGN KEY (position_book_id)
        REFERENCES position_books(position_book_id),
    FOREIGN KEY (confirmation_attempt_id)
        REFERENCES risk_reduction_confirmation_attempts(attempt_id)
);

CREATE INDEX risk_reducing_manual_trade_bindings_position_book_idx
ON risk_reducing_manual_trade_bindings(position_book_id);

CREATE TRIGGER operational_exit_directives_no_update
BEFORE UPDATE ON operational_exit_directives
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER operational_exit_directives_no_delete
BEFORE DELETE ON operational_exit_directives
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER risk_reduction_confirmation_attempts_no_update
BEFORE UPDATE ON risk_reduction_confirmation_attempts
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER risk_reduction_confirmation_attempts_no_delete
BEFORE DELETE ON risk_reduction_confirmation_attempts
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER risk_reduction_confirmation_commands_no_update
BEFORE UPDATE ON risk_reduction_confirmation_commands
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER risk_reduction_confirmation_commands_no_delete
BEFORE DELETE ON risk_reduction_confirmation_commands
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER risk_reducing_manual_trade_bindings_no_update
BEFORE UPDATE ON risk_reducing_manual_trade_bindings
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER risk_reducing_manual_trade_bindings_no_delete
BEFORE DELETE ON risk_reducing_manual_trade_bindings
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE FUNCTION guard_manual_trade_authority_route()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    stored_route text;
BEGIN
    SELECT authority_route INTO stored_route
    FROM manual_trade_records
    WHERE manual_trade_id = NEW.manual_trade_id;
    IF TG_TABLE_NAME = 'traceable_manual_trade_bindings' THEN
        IF stored_route != 'INCREASING'
           OR EXISTS (
               SELECT 1 FROM risk_reducing_manual_trade_bindings
               WHERE manual_trade_id = NEW.manual_trade_id
           ) THEN
            RAISE EXCEPTION 'manual trade authority route binding conflict';
        END IF;
    ELSE
        IF stored_route != 'REDUCING'
           OR EXISTS (
               SELECT 1 FROM traceable_manual_trade_bindings
               WHERE manual_trade_id = NEW.manual_trade_id
           ) THEN
            RAISE EXCEPTION 'manual trade authority route binding conflict';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER traceable_manual_trade_binding_route_guard
BEFORE INSERT ON traceable_manual_trade_bindings
FOR EACH ROW EXECUTE FUNCTION guard_manual_trade_authority_route();

CREATE TRIGGER risk_reducing_manual_trade_binding_route_guard
BEFORE INSERT ON risk_reducing_manual_trade_bindings
FOR EACH ROW EXECUTE FUNCTION guard_manual_trade_authority_route();
