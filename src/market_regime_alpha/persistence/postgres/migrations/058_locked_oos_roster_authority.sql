CREATE TABLE formal_locked_oos_roster (
    roster_id text PRIMARY KEY,
    roster_hash text NOT NULL UNIQUE CHECK (
        roster_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    family_id text NOT NULL UNIQUE
        REFERENCES frozen_hypothesis_family(family_id) ON DELETE RESTRICT,
    family_hash text NOT NULL CHECK (family_hash ~ '^sha256:[0-9a-f]{64}$'),
    formal_protocol_id text NOT NULL UNIQUE
        REFERENCES formal_research_protocol(protocol_id) ON DELETE RESTRICT,
    formal_protocol_hash text NOT NULL CHECK (
        formal_protocol_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    idempotency_key text NOT NULL UNIQUE CHECK (btrim(idempotency_key) <> ''),
    command_hash text NOT NULL CHECK (command_hash ~ '^sha256:[0-9a-f]{64}$'),
    locked_date_count integer NOT NULL CHECK (locked_date_count > 0),
    subject_date_count integer NOT NULL CHECK (subject_date_count > 0),
    target_observation_count integer NOT NULL CHECK (
        target_observation_count > 0
    ),
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' = 'formal-locked-oos-roster/v1'
    ),
    frozen_at timestamptz NOT NULL
);

CREATE TABLE formal_locked_oos_roster_member (
    roster_id text NOT NULL
        REFERENCES formal_locked_oos_roster(roster_id) ON DELETE RESTRICT,
    member_hash text NOT NULL CHECK (member_hash ~ '^sha256:[0-9a-f]{64}$'),
    target_protocol_id text NOT NULL,
    target_protocol_hash text NOT NULL CHECK (
        target_protocol_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    target_id text NOT NULL,
    target_hash text NOT NULL CHECK (target_hash ~ '^sha256:[0-9a-f]{64}$'),
    subject text NOT NULL CHECK (btrim(subject) <> ''),
    decision_time timestamptz NOT NULL,
    outcome_time timestamptz NOT NULL CHECK (outcome_time > decision_time),
    formal_pit_evidence_id text NOT NULL
        REFERENCES formal_pit_validation_evidence(evidence_id) ON DELETE RESTRICT,
    formal_pit_evidence_hash text NOT NULL CHECK (
        formal_pit_evidence_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    forecast_id text NOT NULL
        REFERENCES outcome_target_bound_forecast(forecast_id) ON DELETE RESTRICT,
    forecast_hash text NOT NULL CHECK (forecast_hash ~ '^sha256:[0-9a-f]{64}$'),
    settlement_id text NOT NULL,
    label_id text NOT NULL,
    label_hash text NOT NULL CHECK (label_hash ~ '^sha256:[0-9a-f]{64}$'),
    observation_set_id text NOT NULL
        REFERENCES formal_evaluation_observation_set(observation_set_id)
        ON DELETE RESTRICT,
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' = 'formal-locked-oos-roster-member/v1'
    ),
    PRIMARY KEY (roster_id, target_id, subject, decision_time),
    UNIQUE (roster_id, member_hash),
    UNIQUE (roster_id, settlement_id, label_id),
    FOREIGN KEY (target_protocol_id, target_id)
        REFERENCES outcome_target_definition(protocol_id, target_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (settlement_id, label_id)
        REFERENCES targeted_shadow_outcome_label(settlement_id, label_id)
        ON DELETE RESTRICT
);

CREATE INDEX formal_locked_oos_roster_member_forecast_idx
ON formal_locked_oos_roster_member(forecast_id);

CREATE INDEX formal_locked_oos_roster_member_target_idx
ON formal_locked_oos_roster_member(target_protocol_id, target_id);

CREATE INDEX formal_locked_oos_roster_member_pit_idx
ON formal_locked_oos_roster_member(formal_pit_evidence_id);

CREATE INDEX formal_locked_oos_roster_member_label_idx
ON formal_locked_oos_roster_member(settlement_id, label_id);

CREATE INDEX formal_locked_oos_roster_member_observation_set_idx
ON formal_locked_oos_roster_member(observation_set_id);

CREATE TRIGGER formal_locked_oos_roster_no_update
BEFORE UPDATE OR DELETE ON formal_locked_oos_roster
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER formal_locked_oos_roster_member_no_update
BEFORE UPDATE OR DELETE ON formal_locked_oos_roster_member
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

COMMENT ON TABLE formal_locked_oos_roster IS
'Label-value-blind, pre-read Locked OOS scope claimed after Train/Validation readiness and before any Locked label payload is read.';

COMMENT ON TABLE formal_locked_oos_roster_member IS
'Exact PIT, Forecast, Target Label metadata and observation-set roster; contains no realized Forecast outcome values.';
