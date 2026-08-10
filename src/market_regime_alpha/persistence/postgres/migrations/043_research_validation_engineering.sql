CREATE TABLE research_validation_artifact (
    artifact_id text PRIMARY KEY,
    artifact_hash text NOT NULL UNIQUE CHECK (artifact_hash ~ '^sha256:[0-9a-f]{64}$'),
    artifact_kind text NOT NULL CHECK (artifact_kind IN (
        'PANEL_ENRICHMENT', 'FACTOR_ABLATION', 'LIQUIDITY_CAPACITY',
        'HISTORICAL_SAMPLE_DATASET', 'CALIBRATION_PROTOCOL',
        'CALIBRATION_FIT', 'CALIBRATION_EVALUATION', 'CALIBRATION_ARTIFACT',
        'FORMAL_EVALUATION_PROTOCOL', 'FORMAL_EVALUATION_RESULT',
        'ENTRY_RESEARCH_MODEL', 'ENTRY_RESEARCH_ASSESSMENT',
        'ENTRY_EVALUATION', 'ENTRY_QUALIFICATION_PROTOCOL',
        'ENTRY_QUALIFICATION_EVIDENCE', 'PRODUCTION_ADMISSION',
        'HOLDING_EXIT_PROTOCOL', 'HOLDING_EXIT_EVIDENCE',
        'STRATEGY_SHADOW_PROTOCOL', 'STRATEGY_SHADOW_EVIDENCE'
    )),
    evidence_authority text NOT NULL CHECK (evidence_authority IN (
        'EXPLORATORY', 'ENGINEERING_ONLY', 'FORMAL_OOS', 'BLOCKED',
        'ELIGIBLE_FOR_OPERATOR_REVIEW', 'AUTHORIZED'
    )),
    qualified boolean NOT NULL DEFAULT false,
    production_authorized boolean NOT NULL DEFAULT false,
    payload_json jsonb NOT NULL CHECK (jsonb_typeof(payload_json) = 'object'),
    created_at timestamptz NOT NULL,
    CHECK (NOT production_authorized OR (qualified AND evidence_authority = 'AUTHORIZED'))
);

CREATE INDEX research_validation_kind_created_idx
ON research_validation_artifact(artifact_kind, created_at);

CREATE TABLE research_panel_factor_exposure (
    enrichment_id text NOT NULL REFERENCES research_validation_artifact(artifact_id) ON DELETE RESTRICT,
    symbol text NOT NULL,
    factor_family text NOT NULL,
    factor_id text NOT NULL,
    timeframe text NOT NULL DEFAULT '',
    source_artifact_id text NOT NULL,
    source_content_hash text NOT NULL CHECK (source_content_hash ~ '^sha256:[0-9a-f]{64}$'),
    exposure_json jsonb NOT NULL CHECK (jsonb_typeof(exposure_json) = 'object'),
    PRIMARY KEY (enrichment_id, symbol, factor_family, factor_id, timeframe, source_artifact_id)
);

CREATE INDEX research_panel_factor_symbol_idx
ON research_panel_factor_exposure(symbol, factor_family, factor_id);

CREATE TABLE historical_path_sample_record (
    record_id text PRIMARY KEY,
    record_hash text NOT NULL UNIQUE CHECK (record_hash ~ '^sha256:[0-9a-f]{64}$'),
    dataset_id text NOT NULL REFERENCES research_validation_artifact(artifact_id) ON DELETE RESTRICT,
    sample_id text NOT NULL,
    symbol text NOT NULL,
    target_id text NOT NULL,
    sample_decision_time timestamptz NOT NULL,
    available_at timestamptz NOT NULL,
    qualification text NOT NULL CHECK (qualification IN (
        'UNQUALIFIED', 'PIT_ELIGIBLE', 'OOS_ELIGIBLE', 'QUALIFIED'
    )),
    payload_json jsonb NOT NULL CHECK (jsonb_typeof(payload_json) = 'object'),
    CHECK (available_at > sample_decision_time)
);

CREATE UNIQUE INDEX historical_path_sample_transition_idx
ON historical_path_sample_record(sample_id, qualification);

CREATE INDEX historical_path_sample_lookup_idx
ON historical_path_sample_record(target_id, symbol, available_at);
CREATE INDEX historical_path_sample_dataset_idx
ON historical_path_sample_record(dataset_id);

CREATE TABLE calibration_partition_binding (
    calibration_artifact_id text NOT NULL REFERENCES research_validation_artifact(artifact_id) ON DELETE RESTRICT,
    observation_id text NOT NULL,
    partition_name text NOT NULL CHECK (partition_name IN ('FIT', 'VALIDATION', 'OOS')),
    PRIMARY KEY (calibration_artifact_id, observation_id)
);

CREATE TRIGGER research_validation_artifact_no_update BEFORE UPDATE ON research_validation_artifact
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER research_validation_artifact_no_delete BEFORE DELETE ON research_validation_artifact
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER research_panel_factor_exposure_no_update BEFORE UPDATE ON research_panel_factor_exposure
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER research_panel_factor_exposure_no_delete BEFORE DELETE ON research_panel_factor_exposure
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER historical_path_sample_record_no_update BEFORE UPDATE ON historical_path_sample_record
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER historical_path_sample_record_no_delete BEFORE DELETE ON historical_path_sample_record
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER calibration_partition_binding_no_update BEFORE UPDATE ON calibration_partition_binding
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER calibration_partition_binding_no_delete BEFORE DELETE ON calibration_partition_binding
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
