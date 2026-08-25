-- Freeze the label-blind WP-ALPHA-PROOF-02 Locked OOS roster inside the
-- existing Research Validation authority.  This migration grants no Outcome
-- access, research support, Formal OOS, Strategy or Production authority.

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
    'FEATURE_DEFINITION_SET', 'FEATURE_SET_CONFIGURATION', 'THRESHOLD_POLICY',
    'HISTORICAL_CONTEXT_INSTRUMENT_SET',
    'RESEARCH_EXPERIMENT_DEFINITION',
    'HISTORICAL_STRATEGY_ECONOMICS_POLICY_SET',
    'TRADING_CALENDAR', 'FROZEN_TEMPORAL_VALIDATION_WINDOW',
    'OPERATIONAL_UNIVERSE',
    'DAILY_ALPHA_PREDICTION_SNAPSHOT',
    'FROZEN_LOCKED_OOS_SCOPE'
));

CREATE TABLE frozen_locked_oos_scope (
    scope_id text PRIMARY KEY,
    scope_hash text NOT NULL CHECK (
        scope_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    protocol_id text NOT NULL,
    protocol_hash text NOT NULL CHECK (
        protocol_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    trading_calendar_id text NOT NULL,
    trading_calendar_hash text NOT NULL CHECK (
        trading_calendar_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    universe_timeline_id text NOT NULL
        REFERENCES free_data_historical_constituent_timeline(timeline_id)
        ON DELETE RESTRICT,
    universe_timeline_hash text NOT NULL CHECK (
        universe_timeline_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    external_final_target_session date NOT NULL,
    data_cutoff timestamptz NOT NULL,
    decision_session_count integer NOT NULL CHECK (
        decision_session_count > 0
    ),
    target_binding_count integer NOT NULL CHECK (
        target_binding_count = decision_session_count
    ),
    outcome_values_read boolean NOT NULL DEFAULT false CHECK (
        outcome_values_read = false
    ),
    payload_json jsonb NOT NULL,
    created_at timestamptz NOT NULL,
    UNIQUE (scope_id, scope_hash),
    FOREIGN KEY (scope_id, scope_hash)
        REFERENCES research_validation_artifact(artifact_id, artifact_hash)
        ON DELETE RESTRICT,
    FOREIGN KEY (protocol_id, protocol_hash)
        REFERENCES research_validation_artifact(artifact_id, artifact_hash)
        ON DELETE RESTRICT,
    FOREIGN KEY (trading_calendar_id, trading_calendar_hash)
        REFERENCES research_validation_artifact(artifact_id, artifact_hash)
        ON DELETE RESTRICT,
    CHECK (external_final_target_session = DATE '2026-01-19'),
    CHECK (jsonb_typeof(payload_json) = 'object'),
    CHECK (payload_json->>'schema_version' = 'frozen-locked-oos-scope/v1'),
    CHECK (payload_json->>'scope_id' = scope_id),
    CHECK (payload_json->>'scope_hash' = scope_hash),
    CHECK (
        payload_json->'protocol_reference'->>'artifact_id' = protocol_id
        AND payload_json->'protocol_reference'->>'content_hash' = protocol_hash
    ),
    CHECK (
        payload_json->'calendar_reference'->>'artifact_id'
            = trading_calendar_id
        AND payload_json->'calendar_reference'->>'content_hash'
            = trading_calendar_hash
    ),
    CHECK (
        payload_json->'universe_timeline_reference'->>'artifact_id'
            = universe_timeline_id
        AND payload_json->'universe_timeline_reference'->>'content_hash'
            = universe_timeline_hash
    ),
    CHECK ((payload_json->>'outcome_values_read')::boolean = false),
    CHECK (
        jsonb_array_length(payload_json->'decision_sessions')
            = decision_session_count
        AND jsonb_array_length(payload_json->'target_session_bindings')
            = target_binding_count
        AND jsonb_array_length(payload_json->'session_universe_references')
            = decision_session_count
    )
);

CREATE INDEX frozen_locked_oos_scope_protocol_idx
ON frozen_locked_oos_scope(protocol_id, protocol_hash, scope_id);

CREATE INDEX frozen_locked_oos_scope_timeline_idx
ON frozen_locked_oos_scope(
    universe_timeline_id, universe_timeline_hash, scope_id
);

CREATE INDEX frozen_locked_oos_scope_calendar_idx
ON frozen_locked_oos_scope(
    trading_calendar_id, trading_calendar_hash, scope_id
);

CREATE TRIGGER frozen_locked_oos_scope_no_update
BEFORE UPDATE OR DELETE ON frozen_locked_oos_scope
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

COMMENT ON TABLE frozen_locked_oos_scope IS
'Label-blind WP-ALPHA-PROOF-02 Locked OOS roster. Outcome access remains independently gated by exact Formal PIT and physical correctness Evidence.';
