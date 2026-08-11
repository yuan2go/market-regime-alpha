CREATE TABLE calibration_qualification_policy (
    policy_id text PRIMARY KEY,
    policy_hash text NOT NULL UNIQUE CHECK (
        policy_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    target_protocol_id text NOT NULL
        REFERENCES outcome_target_protocol(protocol_id) ON DELETE RESTRICT,
    target_id text NOT NULL,
    calibration_protocol_id text NOT NULL
        REFERENCES research_validation_artifact(artifact_id) ON DELETE RESTRICT,
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' =
            'calibration-qualification-policy/v1'
        AND (payload_json->>'method_selection_uses_locked_oos')::boolean = false
        AND (payload_json->>'engineering_default')::boolean = false
    ),
    locked_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL
);

CREATE INDEX calibration_qualification_policy_target_idx
ON calibration_qualification_policy(target_protocol_id, target_id);

CREATE INDEX calibration_qualification_policy_protocol_idx
ON calibration_qualification_policy(calibration_protocol_id);

CREATE TABLE formal_calibration_observation_binding (
    calibration_artifact_id text NOT NULL
        REFERENCES research_validation_artifact(artifact_id) ON DELETE RESTRICT,
    observation_id text NOT NULL,
    policy_id text NOT NULL
        REFERENCES calibration_qualification_policy(policy_id) ON DELETE RESTRICT,
    forecast_id text NOT NULL
        REFERENCES outcome_target_bound_forecast(forecast_id) ON DELETE RESTRICT,
    target_settlement_id text NOT NULL,
    label_id text NOT NULL,
    target_id text NOT NULL,
    barrier_id text NOT NULL,
    partition_name text NOT NULL CHECK (
        partition_name IN ('FIT', 'VALIDATION', 'OOS')
    ),
    score numeric NOT NULL,
    binary_outcome smallint NOT NULL CHECK (binary_outcome IN (0, 1)),
    forecast_hash text NOT NULL CHECK (forecast_hash ~ '^sha256:[0-9a-f]{64}$'),
    label_hash text NOT NULL CHECK (label_hash ~ '^sha256:[0-9a-f]{64}$'),
    payload_json jsonb NOT NULL CHECK (jsonb_typeof(payload_json) = 'object'),
    created_at timestamptz NOT NULL,
    PRIMARY KEY (calibration_artifact_id, observation_id),
    FOREIGN KEY (target_settlement_id, label_id)
        REFERENCES targeted_shadow_outcome_label(settlement_id, label_id)
        ON DELETE RESTRICT
);

CREATE INDEX formal_calibration_observation_policy_idx
ON formal_calibration_observation_binding(policy_id);

CREATE INDEX formal_calibration_observation_forecast_idx
ON formal_calibration_observation_binding(forecast_id);

CREATE INDEX formal_calibration_observation_label_idx
ON formal_calibration_observation_binding(target_settlement_id, label_id);

CREATE TABLE calibration_qualification_decision (
    decision_id text PRIMARY KEY,
    decision_hash text NOT NULL UNIQUE CHECK (
        decision_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    policy_id text NOT NULL
        REFERENCES calibration_qualification_policy(policy_id) ON DELETE RESTRICT,
    formal_protocol_id text NOT NULL
        REFERENCES formal_research_protocol(protocol_id) ON DELETE RESTRICT,
    formal_oos_decision_id text
        REFERENCES formal_oos_qualification_decision(decision_id) ON DELETE RESTRICT,
    calibration_artifact_id text
        REFERENCES research_validation_artifact(artifact_id) ON DELETE RESTRICT,
    outcome text NOT NULL CHECK (
        outcome IN ('SATISFIED', 'REJECTED', 'NOT_ESTIMABLE', 'BLOCKED')
    ),
    calibrated boolean NOT NULL,
    revision integer NOT NULL CHECK (revision > 0),
    supersedes_decision_id text
        REFERENCES calibration_qualification_decision(decision_id)
        ON DELETE RESTRICT,
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' =
            'calibration-qualification-decision/v1'
        AND (payload_json->>'production_authorized')::boolean = false
    ),
    evaluated_at timestamptz NOT NULL,
    UNIQUE (formal_protocol_id, policy_id, revision),
    CHECK (calibrated = (outcome = 'SATISFIED')),
    CHECK ((revision = 1) = (supersedes_decision_id IS NULL))
);

CREATE UNIQUE INDEX calibration_qualification_one_superseder_idx
ON calibration_qualification_decision(supersedes_decision_id)
WHERE supersedes_decision_id IS NOT NULL;

CREATE INDEX calibration_qualification_policy_decision_idx
ON calibration_qualification_decision(policy_id);

CREATE INDEX calibration_qualification_oos_idx
ON calibration_qualification_decision(formal_oos_decision_id);

CREATE INDEX calibration_qualification_artifact_idx
ON calibration_qualification_decision(calibration_artifact_id);

CREATE TABLE calibration_qualification_command (
    idempotency_key text PRIMARY KEY,
    command_hash text NOT NULL CHECK (
        command_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    decision_id text NOT NULL
        REFERENCES calibration_qualification_decision(decision_id)
        ON DELETE RESTRICT,
    created_at timestamptz NOT NULL
);

CREATE INDEX calibration_qualification_command_decision_idx
ON calibration_qualification_command(decision_id);

CREATE TRIGGER calibration_qualification_policy_no_update
BEFORE UPDATE OR DELETE ON calibration_qualification_policy
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER formal_calibration_observation_binding_no_update
BEFORE UPDATE OR DELETE ON formal_calibration_observation_binding
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER calibration_qualification_decision_no_update
BEFORE UPDATE OR DELETE ON calibration_qualification_decision
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER calibration_qualification_command_no_update
BEFORE UPDATE OR DELETE ON calibration_qualification_command
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
