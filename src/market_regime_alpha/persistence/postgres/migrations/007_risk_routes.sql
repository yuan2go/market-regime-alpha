CREATE TABLE risk_reducing_decisions (
    decision_id text PRIMARY KEY,
    position_snapshot_id text NOT NULL,
    position_book_id text NOT NULL,
    thesis_id text NOT NULL,
    action text NOT NULL CHECK (action IN ('REDUCE', 'EXIT')),
    state text NOT NULL CHECK (
        state IN (
            'PERMITTED_FOR_MANUAL_CONFIRMATION',
            'BLOCKED',
            'DATA_INSUFFICIENT'
        )
    ),
    content_hash text NOT NULL UNIQUE,
    position_json text NOT NULL CHECK (position_json IS JSON),
    observation_json text NOT NULL CHECK (observation_json IS JSON),
    configuration_json text NOT NULL CHECK (configuration_json IS JSON),
    decision_json text NOT NULL CHECK (decision_json IS JSON),
    assessed_at timestamptz NOT NULL
);

CREATE TABLE risk_reducing_commands (
    idempotency_key text PRIMARY KEY,
    command_hash text NOT NULL,
    decision_id text NOT NULL,
    created_at timestamptz NOT NULL,
    FOREIGN KEY (decision_id) REFERENCES risk_reducing_decisions(decision_id)
);

CREATE INDEX risk_reducing_commands_decision_id_idx
ON risk_reducing_commands(decision_id);

CREATE TRIGGER risk_reducing_decisions_no_update
BEFORE UPDATE ON risk_reducing_decisions
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER risk_reducing_decisions_no_delete
BEFORE DELETE ON risk_reducing_decisions
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER risk_reducing_commands_no_update
BEFORE UPDATE ON risk_reducing_commands
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER risk_reducing_commands_no_delete
BEFORE DELETE ON risk_reducing_commands
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
