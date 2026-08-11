CREATE TABLE trading_calendar_authority (
    calendar_id text PRIMARY KEY,
    calendar_hash text NOT NULL UNIQUE CHECK (
        calendar_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    source_dataset_id text NOT NULL,
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' = 'trading-calendar-artifact-v1'
    ),
    recorded_at timestamptz NOT NULL
);

CREATE TABLE formal_research_protocol_component_owner_resolution (
    protocol_id text NOT NULL
        REFERENCES formal_research_protocol(protocol_id) ON DELETE RESTRICT,
    component_role text NOT NULL CHECK (component_role IN (
        'outcome_target_protocol_reference',
        'evaluation_protocol_reference',
        'trading_calendar_reference',
        'universe_reference', 'dataset_reference',
        'historical_sample_dataset_reference', 'feature_reference',
        'factor_reference', 'model_reference',
        'threshold_policy_reference',
        'formal_oos_qualification_policy_reference',
        'cost_policy_reference', 'calibration_policy_reference',
        'strategy_policy_reference',
        'entry_holding_exit_qualification_policy_reference'
    )),
    artifact_kind text NOT NULL,
    artifact_id text NOT NULL,
    artifact_hash text NOT NULL CHECK (
        artifact_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    owner_kind text NOT NULL CHECK (owner_kind IN (
        'OUTCOME_TARGET_AUTHORITY',
        'TRADING_CALENDAR_AUTHORITY',
        'PIT_ARTIFACT_AUTHORITY',
        'RESEARCH_VALIDATION_AUTHORITY',
        'MODEL_GOVERNANCE_AUTHORITY',
        'FORMAL_OOS_POLICY_AUTHORITY',
        'SHADOW_PORTFOLIO_POLICY_AUTHORITY',
        'CALIBRATION_POLICY_AUTHORITY',
        'STRATEGY_SHADOW_POLICY_AUTHORITY',
        'ENTRY_HOLDING_EXIT_POLICY_AUTHORITY'
    )),
    owner_artifact_id text NOT NULL,
    owner_artifact_hash text NOT NULL CHECK (
        owner_artifact_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    owner_payload_hash text NOT NULL CHECK (
        owner_payload_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    owner_payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(owner_payload_json) = 'object'
    ),
    owner_recorded_at timestamptz NOT NULL,
    resolved_at timestamptz NOT NULL,
    PRIMARY KEY (protocol_id, component_role),
    UNIQUE (protocol_id, artifact_id, artifact_hash)
);

CREATE INDEX formal_protocol_component_owner_artifact_idx
ON formal_research_protocol_component_owner_resolution(
    artifact_id, artifact_hash, owner_kind
);

CREATE TABLE locked_oos_evidence_consumption (
    evidence_identity_hash text PRIMARY KEY CHECK (
        evidence_identity_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    dataset_id text NOT NULL,
    dataset_hash text NOT NULL CHECK (
        dataset_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    universe_id text NOT NULL,
    universe_hash text NOT NULL CHECK (
        universe_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    target_protocol_id text NOT NULL
        REFERENCES outcome_target_protocol(protocol_id) ON DELETE RESTRICT,
    target_protocol_hash text NOT NULL CHECK (
        target_protocol_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    target_id text NOT NULL,
    target_hash text NOT NULL CHECK (
        target_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    label_id text NOT NULL,
    label_hash text NOT NULL CHECK (
        label_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    session_date date NOT NULL,
    label_end_date date NOT NULL CHECK (label_end_date >= session_date),
    partition_kind text NOT NULL CHECK (partition_kind = 'LOCKED_OOS'),
    first_formal_protocol_id text NOT NULL
        REFERENCES formal_research_protocol(protocol_id) ON DELETE RESTRICT,
    first_formal_protocol_hash text NOT NULL CHECK (
        first_formal_protocol_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    first_model_id text NOT NULL,
    first_model_hash text NOT NULL CHECK (
        first_model_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    first_forecast_id text NOT NULL
        REFERENCES outcome_target_bound_forecast(forecast_id) ON DELETE RESTRICT,
    first_forecast_hash text NOT NULL CHECK (
        first_forecast_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    observation_set_id text NOT NULL
        REFERENCES formal_evaluation_observation_set(observation_set_id)
        ON DELETE RESTRICT,
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' =
            'locked-oos-evidence-consumption/v1'
    ),
    consumed_at timestamptz NOT NULL,
    UNIQUE (label_id, partition_kind),
    UNIQUE (
        dataset_id, dataset_hash, universe_id, universe_hash,
        target_protocol_id, target_protocol_hash, target_id, target_hash,
        label_id, label_hash, session_date, label_end_date, partition_kind
    )
);

CREATE INDEX locked_oos_evidence_consumption_protocol_idx
ON locked_oos_evidence_consumption(first_formal_protocol_id);

CREATE INDEX locked_oos_evidence_consumption_model_idx
ON locked_oos_evidence_consumption(first_model_id);

CREATE INDEX locked_oos_evidence_consumption_target_protocol_idx
ON locked_oos_evidence_consumption(target_protocol_id);

CREATE INDEX locked_oos_evidence_consumption_forecast_idx
ON locked_oos_evidence_consumption(first_forecast_id);

CREATE INDEX locked_oos_evidence_consumption_observation_set_idx
ON locked_oos_evidence_consumption(observation_set_id);

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
'Migration 056 adds only typed C0 Feature/Threshold owner artifacts; Migration 046 qualification and Production constraints remain authoritative.';

CREATE TRIGGER trading_calendar_authority_no_update
BEFORE UPDATE OR DELETE ON trading_calendar_authority
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER formal_research_protocol_component_owner_resolution_no_update
BEFORE UPDATE OR DELETE
ON formal_research_protocol_component_owner_resolution
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER locked_oos_evidence_consumption_no_update
BEFORE UPDATE OR DELETE ON locked_oos_evidence_consumption
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
