CREATE TABLE formal_oos_qualification_policy (
    policy_id text PRIMARY KEY,
    policy_hash text NOT NULL UNIQUE CHECK (
        policy_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' =
            'formal-oos-qualification-policy/v1'
        AND (payload_json->>'multiple_testing_required')::boolean
        AND (payload_json->>'locked_oos_reuse_prohibited')::boolean
        AND NOT (payload_json->>'engineering_default')::boolean
    ),
    locked_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL
);

CREATE TABLE formal_evaluation_observation_set (
    observation_set_id text PRIMARY KEY,
    observation_set_hash text NOT NULL UNIQUE CHECK (
        observation_set_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    formal_protocol_id text NOT NULL
        REFERENCES formal_research_protocol(protocol_id) ON DELETE RESTRICT,
    panel_id text NOT NULL
        REFERENCES research_evaluation_panel_v2(panel_id) ON DELETE RESTRICT,
    target_protocol_id text NOT NULL,
    target_id text NOT NULL,
    target_hash text NOT NULL CHECK (target_hash ~ '^sha256:[0-9a-f]{64}$'),
    observation_count bigint NOT NULL CHECK (observation_count > 0),
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' =
            'formal-evaluation-observation-set/v1'
    ),
    created_at timestamptz NOT NULL,
    UNIQUE (observation_set_id, panel_id),
    FOREIGN KEY (target_protocol_id, target_id)
        REFERENCES outcome_target_definition(protocol_id, target_id)
        ON DELETE RESTRICT
);

CREATE TABLE formal_evaluation_observation_binding (
    observation_set_id text NOT NULL,
    observation_id text NOT NULL,
    forecast_id text NOT NULL
        REFERENCES outcome_target_bound_forecast(forecast_id) ON DELETE RESTRICT,
    forecast_hash text NOT NULL CHECK (forecast_hash ~ '^sha256:[0-9a-f]{64}$'),
    settlement_id text NOT NULL,
    label_id text NOT NULL,
    label_hash text NOT NULL CHECK (label_hash ~ '^sha256:[0-9a-f]{64}$'),
    panel_id text NOT NULL,
    slice_id text NOT NULL,
    row_id text NOT NULL,
    row_hash text NOT NULL CHECK (row_hash ~ '^sha256:[0-9a-f]{64}$'),
    session_date date NOT NULL,
    label_end_date date NOT NULL,
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' =
            'formal-evaluation-observation-binding/v1'
    ),
    PRIMARY KEY (observation_set_id, observation_id),
    UNIQUE (observation_set_id, forecast_id, label_id),
    FOREIGN KEY (observation_set_id, panel_id)
        REFERENCES formal_evaluation_observation_set(
            observation_set_id, panel_id
        ) ON DELETE RESTRICT,
    FOREIGN KEY (settlement_id, label_id)
        REFERENCES targeted_shadow_outcome_label(settlement_id, label_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (panel_id, slice_id, row_id)
        REFERENCES research_evaluation_panel_row_v2(panel_id, slice_id, row_id)
        ON DELETE RESTRICT,
    CHECK (label_end_date >= session_date)
);

CREATE INDEX formal_evaluation_observation_set_protocol_idx
ON formal_evaluation_observation_set(formal_protocol_id, target_id);

CREATE INDEX formal_evaluation_observation_set_panel_idx
ON formal_evaluation_observation_set(panel_id);

CREATE INDEX formal_evaluation_observation_set_target_idx
ON formal_evaluation_observation_set(target_protocol_id, target_id);

CREATE INDEX formal_evaluation_observation_binding_forecast_idx
ON formal_evaluation_observation_binding(forecast_id, label_id);

CREATE INDEX formal_evaluation_observation_binding_set_panel_idx
ON formal_evaluation_observation_binding(observation_set_id, panel_id);

CREATE INDEX formal_evaluation_observation_binding_label_idx
ON formal_evaluation_observation_binding(settlement_id, label_id);

CREATE INDEX formal_evaluation_observation_binding_panel_row_idx
ON formal_evaluation_observation_binding(panel_id, slice_id, row_id);

CREATE TABLE historical_sample_qualification_decision (
    decision_id text PRIMARY KEY,
    decision_hash text NOT NULL UNIQUE CHECK (
        decision_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    dataset_id text NOT NULL
        REFERENCES research_validation_artifact(artifact_id) ON DELETE RESTRICT,
    formal_protocol_id text
        REFERENCES formal_research_protocol(protocol_id) ON DELETE RESTRICT,
    formal_pit_evidence_id text
        REFERENCES formal_pit_validation_evidence(evidence_id) ON DELETE RESTRICT,
    outcome text NOT NULL CHECK (
        outcome IN ('SATISFIED', 'REJECTED', 'NOT_ESTIMABLE', 'BLOCKED')
    ),
    qualified boolean NOT NULL,
    revision integer NOT NULL CHECK (revision > 0),
    supersedes_decision_id text
        REFERENCES historical_sample_qualification_decision(decision_id)
        ON DELETE RESTRICT,
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' =
            'historical-sample-qualification-decision/v1'
    ),
    evaluated_at timestamptz NOT NULL,
    UNIQUE (dataset_id, revision),
    CHECK (qualified = (outcome = 'SATISFIED')),
    CHECK ((revision = 1) = (supersedes_decision_id IS NULL))
);

CREATE UNIQUE INDEX historical_sample_qualification_one_superseder_idx
ON historical_sample_qualification_decision(supersedes_decision_id)
WHERE supersedes_decision_id IS NOT NULL;

CREATE INDEX historical_sample_qualification_protocol_idx
ON historical_sample_qualification_decision(formal_protocol_id);

CREATE INDEX historical_sample_qualification_pit_idx
ON historical_sample_qualification_decision(formal_pit_evidence_id);

CREATE TABLE formal_oos_qualification_decision (
    decision_id text PRIMARY KEY,
    decision_hash text NOT NULL UNIQUE CHECK (
        decision_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    policy_id text NOT NULL
        REFERENCES formal_oos_qualification_policy(policy_id) ON DELETE RESTRICT,
    formal_protocol_id text NOT NULL
        REFERENCES formal_research_protocol(protocol_id) ON DELETE RESTRICT,
    evaluation_result_id text NOT NULL
        REFERENCES research_validation_artifact(artifact_id) ON DELETE RESTRICT,
    historical_sample_decision_id text NOT NULL
        REFERENCES historical_sample_qualification_decision(decision_id)
        ON DELETE RESTRICT,
    formal_pit_evidence_id text NOT NULL
        REFERENCES formal_pit_validation_evidence(evidence_id) ON DELETE RESTRICT,
    outcome text NOT NULL CHECK (
        outcome IN ('SATISFIED', 'REJECTED', 'NOT_ESTIMABLE', 'BLOCKED')
    ),
    formal_evaluation_complete boolean NOT NULL,
    formal_oos_passed boolean NOT NULL,
    revision integer NOT NULL CHECK (revision > 0),
    supersedes_decision_id text
        REFERENCES formal_oos_qualification_decision(decision_id)
        ON DELETE RESTRICT,
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' =
            'formal-oos-qualification-decision/v1'
    ),
    evaluated_at timestamptz NOT NULL,
    UNIQUE (formal_protocol_id, evaluation_result_id, revision),
    CHECK (formal_evaluation_complete = (outcome <> 'BLOCKED')),
    CHECK (formal_oos_passed = (outcome = 'SATISFIED')),
    CHECK ((revision = 1) = (supersedes_decision_id IS NULL))
);

CREATE UNIQUE INDEX formal_oos_qualification_one_superseder_idx
ON formal_oos_qualification_decision(supersedes_decision_id)
WHERE supersedes_decision_id IS NOT NULL;

CREATE INDEX formal_oos_qualification_policy_idx
ON formal_oos_qualification_decision(policy_id);

CREATE INDEX formal_oos_qualification_sample_idx
ON formal_oos_qualification_decision(historical_sample_decision_id);

CREATE INDEX formal_oos_qualification_pit_idx
ON formal_oos_qualification_decision(formal_pit_evidence_id);

CREATE INDEX formal_oos_qualification_result_idx
ON formal_oos_qualification_decision(evaluation_result_id);

CREATE TABLE research_qualification_command (
    idempotency_key text PRIMARY KEY,
    command_hash text NOT NULL CHECK (
        command_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    action_kind text NOT NULL CHECK (action_kind IN (
        'QUALIFY_HISTORICAL_SAMPLE', 'QUALIFY_FORMAL_OOS'
    )),
    decision_id text NOT NULL,
    created_at timestamptz NOT NULL
);

CREATE TRIGGER formal_oos_qualification_policy_no_update
BEFORE UPDATE OR DELETE ON formal_oos_qualification_policy
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER formal_evaluation_observation_binding_no_update
BEFORE UPDATE OR DELETE ON formal_evaluation_observation_binding
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER formal_evaluation_observation_set_no_update
BEFORE UPDATE OR DELETE ON formal_evaluation_observation_set
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER historical_sample_qualification_decision_no_update
BEFORE UPDATE OR DELETE ON historical_sample_qualification_decision
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER formal_oos_qualification_decision_no_update
BEFORE UPDATE OR DELETE ON formal_oos_qualification_decision
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER research_qualification_command_no_update
BEFORE UPDATE OR DELETE ON research_qualification_command
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
