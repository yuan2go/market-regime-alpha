CREATE TABLE outcome_target_protocol (
    protocol_id text PRIMARY KEY,
    protocol_hash text NOT NULL UNIQUE CHECK (protocol_hash ~ '^sha256:[0-9a-f]{64}$'),
    protocol_version text NOT NULL,
    protocol_json jsonb NOT NULL CHECK (jsonb_typeof(protocol_json) = 'object'),
    created_at timestamptz NOT NULL
);

CREATE TABLE outcome_target_definition (
    protocol_id text NOT NULL REFERENCES outcome_target_protocol(protocol_id) ON DELETE RESTRICT,
    target_id text NOT NULL,
    target_hash text NOT NULL CHECK (target_hash ~ '^sha256:[0-9a-f]{64}$'),
    target_version text NOT NULL,
    checkpoint text NOT NULL CHECK (checkpoint IN ('OPEN', '09:45', '10:00', '10:30', '11:30', 'CLOSE')),
    target_json jsonb NOT NULL CHECK (jsonb_typeof(target_json) = 'object'),
    PRIMARY KEY (protocol_id, target_id),
    UNIQUE (protocol_id, target_hash)
);

CREATE TABLE targeted_shadow_outcome (
    settlement_id text PRIMARY KEY,
    settlement_hash text NOT NULL UNIQUE CHECK (settlement_hash ~ '^sha256:[0-9a-f]{64}$'),
    shadow_decision_id text NOT NULL REFERENCES shadow_research_decision(decision_id) ON DELETE RESTRICT,
    factual_outcome_v1_id text NOT NULL REFERENCES prospective_outcome_settlement(settlement_id) ON DELETE RESTRICT,
    target_protocol_id text NOT NULL REFERENCES outcome_target_protocol(protocol_id) ON DELETE RESTRICT,
    source_dataset_id text NOT NULL,
    next_session_date date NOT NULL,
    availability_status text NOT NULL CHECK (availability_status IN ('COMPLETE', 'PARTIAL', 'UNAVAILABLE')),
    outcome_available_at timestamptz NOT NULL,
    payload_json jsonb NOT NULL CHECK (jsonb_typeof(payload_json) = 'object'),
    created_at timestamptz NOT NULL,
    UNIQUE (shadow_decision_id, factual_outcome_v1_id, target_protocol_id)
);

CREATE TABLE targeted_shadow_outcome_label (
    settlement_id text NOT NULL REFERENCES targeted_shadow_outcome(settlement_id) ON DELETE RESTRICT,
    label_id text NOT NULL,
    label_hash text NOT NULL CHECK (label_hash ~ '^sha256:[0-9a-f]{64}$'),
    target_protocol_id text NOT NULL,
    target_id text NOT NULL,
    symbol text NOT NULL,
    label_interval_start timestamptz NOT NULL,
    label_interval_end timestamptz NOT NULL,
    availability_status text NOT NULL CHECK (availability_status IN ('COMPLETE', 'PARTIAL', 'UNAVAILABLE')),
    label_json jsonb NOT NULL CHECK (jsonb_typeof(label_json) = 'object'),
    PRIMARY KEY (settlement_id, label_id),
    UNIQUE (settlement_id, target_id, symbol),
    FOREIGN KEY (target_protocol_id, target_id)
        REFERENCES outcome_target_definition(protocol_id, target_id) ON DELETE RESTRICT,
    CHECK (label_interval_start < label_interval_end),
    CHECK (label_interval_end <= (label_json->>'outcome_available_at')::timestamptz)
);

CREATE INDEX targeted_shadow_outcome_decision_idx
ON targeted_shadow_outcome(shadow_decision_id, target_protocol_id);
CREATE INDEX targeted_shadow_outcome_v1_idx
ON targeted_shadow_outcome(factual_outcome_v1_id);
CREATE INDEX targeted_shadow_outcome_protocol_idx
ON targeted_shadow_outcome(target_protocol_id);
CREATE INDEX targeted_shadow_outcome_date_idx
ON targeted_shadow_outcome(next_session_date, availability_status);
CREATE INDEX targeted_shadow_label_interval_idx
ON targeted_shadow_outcome_label(label_interval_start, label_interval_end);
CREATE INDEX targeted_shadow_label_target_idx
ON targeted_shadow_outcome_label(target_protocol_id, target_id);

CREATE TRIGGER outcome_target_protocol_no_update BEFORE UPDATE ON outcome_target_protocol
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER outcome_target_protocol_no_delete BEFORE DELETE ON outcome_target_protocol
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER outcome_target_definition_no_update BEFORE UPDATE ON outcome_target_definition
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER outcome_target_definition_no_delete BEFORE DELETE ON outcome_target_definition
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER targeted_shadow_outcome_no_update BEFORE UPDATE ON targeted_shadow_outcome
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER targeted_shadow_outcome_no_delete BEFORE DELETE ON targeted_shadow_outcome
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER targeted_shadow_outcome_label_no_update BEFORE UPDATE ON targeted_shadow_outcome_label
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER targeted_shadow_outcome_label_no_delete BEFORE DELETE ON targeted_shadow_outcome_label
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
