ALTER TABLE outcome_target_bound_forecast
ADD COLUMN forecast_authority text NOT NULL
DEFAULT 'EXPLORATORY_CALLER_SUBMITTED'
CHECK (forecast_authority IN (
    'EXPLORATORY_CALLER_SUBMITTED', 'FORMAL_OWNER_COMPUTED'
));

CREATE TABLE frozen_hypothesis_family (
    family_id text PRIMARY KEY,
    family_hash text NOT NULL UNIQUE CHECK (
        family_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    formal_protocol_id text NOT NULL UNIQUE
        REFERENCES formal_research_protocol(protocol_id) ON DELETE RESTRICT,
    formal_protocol_hash text NOT NULL CHECK (
        formal_protocol_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    evaluation_protocol_id text NOT NULL,
    evaluation_protocol_hash text NOT NULL CHECK (
        evaluation_protocol_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    target_protocol_id text NOT NULL
        REFERENCES outcome_target_protocol(protocol_id) ON DELETE RESTRICT,
    target_protocol_hash text NOT NULL CHECK (
        target_protocol_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    hypothesis_family_key text NOT NULL CHECK (btrim(hypothesis_family_key) <> ''),
    multiple_testing_method text NOT NULL CHECK (
        multiple_testing_method IN ('BONFERRONI', 'BENJAMINI_HOCHBERG')
    ),
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' = 'frozen-hypothesis-family/v1'
        AND jsonb_typeof(payload_json->'metric_names') = 'array'
        AND jsonb_typeof(payload_json->'slice_kinds') = 'array'
        AND btrim(payload_json->>'evaluation_implementation_identity') <> ''
    ),
    frozen_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL
);

CREATE TABLE frozen_hypothesis_family_target (
    family_id text NOT NULL
        REFERENCES frozen_hypothesis_family(family_id) ON DELETE RESTRICT,
    target_protocol_id text NOT NULL,
    target_id text NOT NULL,
    target_hash text NOT NULL CHECK (target_hash ~ '^sha256:[0-9a-f]{64}$'),
    ordinal integer NOT NULL CHECK (ordinal > 0),
    PRIMARY KEY (family_id, target_id),
    UNIQUE (family_id, ordinal),
    FOREIGN KEY (target_protocol_id, target_id)
        REFERENCES outcome_target_definition(protocol_id, target_id)
        ON DELETE RESTRICT
);

CREATE INDEX frozen_hypothesis_family_evaluation_idx
ON frozen_hypothesis_family(evaluation_protocol_id, target_protocol_id);

CREATE INDEX frozen_hypothesis_family_target_protocol_idx
ON frozen_hypothesis_family(target_protocol_id);

CREATE INDEX frozen_hypothesis_family_target_owner_idx
ON frozen_hypothesis_family_target(target_protocol_id, target_id);

CREATE TABLE formal_forecast_computation_receipt (
    receipt_id text PRIMARY KEY,
    receipt_hash text NOT NULL UNIQUE CHECK (
        receipt_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    request_hash text NOT NULL CHECK (request_hash ~ '^sha256:[0-9a-f]{64}$'),
    formal_protocol_id text NOT NULL
        REFERENCES formal_research_protocol(protocol_id) ON DELETE RESTRICT,
    formal_pit_evidence_id text NOT NULL
        REFERENCES formal_pit_validation_evidence(evidence_id) ON DELETE RESTRICT,
    forecast_id text NOT NULL UNIQUE
        REFERENCES outcome_target_bound_forecast(forecast_id) ON DELETE RESTRICT,
    model_id text NOT NULL,
    model_hash text NOT NULL CHECK (model_hash ~ '^sha256:[0-9a-f]{64}$'),
    configuration_id text NOT NULL,
    configuration_hash text NOT NULL CHECK (
        configuration_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    executor_identity text NOT NULL CHECK (btrim(executor_identity) <> ''),
    decision_time timestamptz NOT NULL,
    materialized_at timestamptz NOT NULL CHECK (materialized_at >= decision_time),
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' =
            'formal-forecast-computation-receipt/v1'
        AND NOT (payload_json->>'production_authorized')::boolean
    )
);

CREATE TABLE formal_forecast_computation_command (
    idempotency_key text PRIMARY KEY,
    command_hash text NOT NULL CHECK (command_hash ~ '^sha256:[0-9a-f]{64}$'),
    request_hash text NOT NULL CHECK (request_hash ~ '^sha256:[0-9a-f]{64}$'),
    receipt_id text NOT NULL
        REFERENCES formal_forecast_computation_receipt(receipt_id)
        ON DELETE RESTRICT,
    created_at timestamptz NOT NULL
);

CREATE INDEX formal_forecast_computation_protocol_idx
ON formal_forecast_computation_receipt(formal_protocol_id, decision_time);

CREATE INDEX formal_forecast_computation_pit_idx
ON formal_forecast_computation_receipt(formal_pit_evidence_id);

CREATE INDEX formal_forecast_computation_command_receipt_idx
ON formal_forecast_computation_command(receipt_id);

CREATE TABLE locked_oos_raw_evidence_unlock (
    raw_evidence_identity_hash text PRIMARY KEY CHECK (
        raw_evidence_identity_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    subject text NOT NULL CHECK (btrim(subject) <> ''),
    decision_session_date date NOT NULL,
    outcome_session_date date NOT NULL CHECK (
        outcome_session_date >= decision_session_date
    ),
    partition_kind text NOT NULL CHECK (partition_kind = 'LOCKED_OOS'),
    first_family_id text NOT NULL
        REFERENCES frozen_hypothesis_family(family_id) ON DELETE RESTRICT,
    first_family_hash text NOT NULL CHECK (
        first_family_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    first_formal_protocol_id text NOT NULL
        REFERENCES formal_research_protocol(protocol_id) ON DELETE RESTRICT,
    first_formal_protocol_hash text NOT NULL CHECK (
        first_formal_protocol_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    first_dataset_id text NOT NULL,
    first_dataset_hash text NOT NULL CHECK (
        first_dataset_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    first_universe_id text NOT NULL,
    first_universe_hash text NOT NULL CHECK (
        first_universe_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    first_model_id text NOT NULL,
    first_model_hash text NOT NULL CHECK (
        first_model_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' = 'locked-oos-raw-unlock/v1'
    ),
    unlocked_at timestamptz NOT NULL,
    UNIQUE (
        subject, decision_session_date, outcome_session_date, partition_kind
    )
);

CREATE TABLE locked_oos_target_observation_consumption (
    consumption_id text PRIMARY KEY,
    consumption_hash text NOT NULL UNIQUE CHECK (
        consumption_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    raw_evidence_identity_hash text NOT NULL
        REFERENCES locked_oos_raw_evidence_unlock(raw_evidence_identity_hash)
        ON DELETE RESTRICT,
    family_id text NOT NULL
        REFERENCES frozen_hypothesis_family(family_id) ON DELETE RESTRICT,
    family_hash text NOT NULL CHECK (family_hash ~ '^sha256:[0-9a-f]{64}$'),
    target_id text NOT NULL,
    target_hash text NOT NULL CHECK (target_hash ~ '^sha256:[0-9a-f]{64}$'),
    forecast_id text NOT NULL
        REFERENCES outcome_target_bound_forecast(forecast_id) ON DELETE RESTRICT,
    forecast_hash text NOT NULL CHECK (forecast_hash ~ '^sha256:[0-9a-f]{64}$'),
    label_id text NOT NULL,
    label_hash text NOT NULL CHECK (label_hash ~ '^sha256:[0-9a-f]{64}$'),
    observation_set_id text NOT NULL
        REFERENCES formal_evaluation_observation_set(observation_set_id)
        ON DELETE RESTRICT,
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' =
            'locked-oos-target-observation-consumption/v1'
    ),
    consumed_at timestamptz NOT NULL,
    UNIQUE (raw_evidence_identity_hash, target_id),
    UNIQUE (family_id, target_id, observation_set_id)
);

CREATE INDEX locked_oos_raw_unlock_family_idx
ON locked_oos_raw_evidence_unlock(first_family_id);

CREATE INDEX locked_oos_raw_unlock_protocol_idx
ON locked_oos_raw_evidence_unlock(first_formal_protocol_id);

CREATE INDEX locked_oos_target_consumption_forecast_idx
ON locked_oos_target_observation_consumption(forecast_id, label_id);

CREATE INDEX locked_oos_target_consumption_observation_set_idx
ON locked_oos_target_observation_consumption(observation_set_id);

CREATE TABLE formal_hypothesis_family_evaluation (
    result_id text PRIMARY KEY
        REFERENCES research_validation_artifact(artifact_id) ON DELETE RESTRICT,
    result_hash text NOT NULL UNIQUE CHECK (
        result_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    family_id text NOT NULL
        REFERENCES frozen_hypothesis_family(family_id) ON DELETE RESTRICT,
    family_hash text NOT NULL CHECK (family_hash ~ '^sha256:[0-9a-f]{64}$'),
    formal_protocol_id text NOT NULL
        REFERENCES formal_research_protocol(protocol_id) ON DELETE RESTRICT,
    formal_pit_evidence_id text NOT NULL
        REFERENCES formal_pit_validation_evidence(evidence_id) ON DELETE RESTRICT,
    target_count integer NOT NULL CHECK (target_count > 0),
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' =
            'formal-hypothesis-family-evaluation-result/v1'
        AND NOT (payload_json->>'formal_oos')::boolean
    ),
    created_at timestamptz NOT NULL,
    UNIQUE (family_id, result_id)
);

CREATE TABLE formal_hypothesis_family_evaluation_target (
    result_id text NOT NULL
        REFERENCES formal_hypothesis_family_evaluation(result_id)
        ON DELETE RESTRICT,
    family_id text NOT NULL
        REFERENCES frozen_hypothesis_family(family_id) ON DELETE RESTRICT,
    target_id text NOT NULL,
    target_hash text NOT NULL CHECK (target_hash ~ '^sha256:[0-9a-f]{64}$'),
    observation_set_id text NOT NULL UNIQUE
        REFERENCES formal_evaluation_observation_set(observation_set_id)
        ON DELETE RESTRICT,
    PRIMARY KEY (result_id, target_id)
);

CREATE INDEX formal_family_evaluation_protocol_idx
ON formal_hypothesis_family_evaluation(formal_protocol_id);

CREATE INDEX formal_family_evaluation_pit_idx
ON formal_hypothesis_family_evaluation(formal_pit_evidence_id);

CREATE INDEX formal_family_evaluation_target_family_idx
ON formal_hypothesis_family_evaluation_target(family_id);

CREATE TABLE phase_c_formal_operator_command (
    idempotency_key text PRIMARY KEY,
    command_hash text NOT NULL CHECK (command_hash ~ '^sha256:[0-9a-f]{64}$'),
    action_kind text NOT NULL CHECK (action_kind IN (
        'FREEZE_TARGET_PROTOCOL', 'FREEZE_TRADING_CALENDAR',
        'FREEZE_EVALUATION_PROTOCOL', 'FREEZE_FEATURE_DEFINITION_SET',
        'FREEZE_FACTOR_CATALOG', 'FREEZE_THRESHOLD_POLICY',
        'FREEZE_FORMAL_OOS_POLICY', 'FREEZE_CALIBRATION_POLICY',
        'FREEZE_COST_POLICY', 'FREEZE_STRATEGY_POLICY',
        'FREEZE_ENTRY_HOLDING_EXIT_POLICY', 'FREEZE_FORMAL_PROTOCOL',
        'COMPUTE_FORMAL_FORECAST', 'EVALUATE_FORMAL_FAMILY'
    )),
    result_artifact_id text NOT NULL,
    result_artifact_hash text NOT NULL CHECK (
        result_artifact_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    actor text NOT NULL CHECK (btrim(actor) <> ''),
    reason text NOT NULL CHECK (btrim(reason) <> ''),
    payload_json jsonb NOT NULL CHECK (jsonb_typeof(payload_json) = 'object'),
    created_at timestamptz NOT NULL
);

ALTER TABLE research_validation_artifact
DROP CONSTRAINT research_validation_artifact_artifact_kind_check;

ALTER TABLE research_validation_artifact
ADD CONSTRAINT research_validation_artifact_artifact_kind_check
CHECK (artifact_kind IN (
    'PANEL_ENRICHMENT', 'FACTOR_ABLATION', 'LIQUIDITY_CAPACITY',
    'FREE_HISTORICAL_DECISION',
    'FREE_HISTORICAL_MULTI_HORIZON_OUTCOME',
    'HISTORICAL_SAMPLE_DATASET', 'CALIBRATION_PROTOCOL',
    'CALIBRATION_FIT', 'CALIBRATION_EVALUATION', 'CALIBRATION_ARTIFACT',
    'PATH_CALIBRATION_HYPOTHESIS',
    'FORMAL_EVALUATION_PROTOCOL', 'FORMAL_EVALUATION_RESULT',
    'FORMAL_HYPOTHESIS_FAMILY_EVALUATION_RESULT',
    'ENTRY_RESEARCH_MODEL', 'ENTRY_RESEARCH_ASSESSMENT',
    'ENTRY_EVALUATION', 'ENTRY_QUALIFICATION_PROTOCOL',
    'ENTRY_QUALIFICATION_EVIDENCE', 'PRODUCTION_ADMISSION',
    'HOLDING_EXIT_PROTOCOL', 'HOLDING_EXIT_EVIDENCE',
    'STRATEGY_SHADOW_PROTOCOL', 'STRATEGY_SHADOW_EVIDENCE',
    'FACTOR_RESEARCH_CATALOG', 'FACTOR_DEDUPLICATION_REPORT',
    'PORTFOLIO_SHADOW_MARKET_OBSERVATION',
    'FEATURE_DEFINITION_SET', 'THRESHOLD_POLICY'
));

COMMENT ON CONSTRAINT research_validation_artifact_artifact_kind_check
ON research_validation_artifact IS
'Migration 057 adds family-level engineering evidence only; Migration 046 qualification and Production constraints remain authoritative.';

CREATE TRIGGER frozen_hypothesis_family_no_update
BEFORE UPDATE OR DELETE ON frozen_hypothesis_family
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER frozen_hypothesis_family_target_no_update
BEFORE UPDATE OR DELETE ON frozen_hypothesis_family_target
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER formal_forecast_computation_receipt_no_update
BEFORE UPDATE OR DELETE ON formal_forecast_computation_receipt
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER formal_forecast_computation_command_no_update
BEFORE UPDATE OR DELETE ON formal_forecast_computation_command
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER locked_oos_raw_evidence_unlock_no_update
BEFORE UPDATE OR DELETE ON locked_oos_raw_evidence_unlock
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER locked_oos_target_observation_consumption_no_update
BEFORE UPDATE OR DELETE ON locked_oos_target_observation_consumption
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER formal_hypothesis_family_evaluation_no_update
BEFORE UPDATE OR DELETE ON formal_hypothesis_family_evaluation
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER formal_hypothesis_family_evaluation_target_no_update
BEFORE UPDATE OR DELETE ON formal_hypothesis_family_evaluation_target
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER phase_c_formal_operator_command_no_update
BEFORE UPDATE OR DELETE ON phase_c_formal_operator_command
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
