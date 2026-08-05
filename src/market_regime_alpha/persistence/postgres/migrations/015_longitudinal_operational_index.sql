CREATE TABLE longitudinal_operational_index (
    decision_date date NOT NULL,
    operation_run_id text PRIMARY KEY,
    universe_id text NOT NULL,
    daily_dataset_id text NOT NULL,
    minute_dataset_id text NOT NULL,
    feature_set_id text NOT NULL,
    signal_model_id text NOT NULL,
    signal_model_version text NOT NULL,
    configuration_hashes_json text NOT NULL CHECK (
        configuration_hashes_json IS JSON ARRAY
    ),
    candidate_count bigint NOT NULL CHECK (candidate_count >= 0),
    signal_state_counts_json text NOT NULL CHECK (
        signal_state_counts_json IS JSON OBJECT
    ),
    minute_success_count bigint NOT NULL CHECK (minute_success_count >= 0),
    minute_failure_count bigint NOT NULL CHECK (minute_failure_count >= 0),
    deadline_status text NOT NULL,
    outcome_status text NOT NULL CHECK (
        outcome_status IN ('OUTCOME_PENDING', 'SETTLED')
    ),
    package_id text NOT NULL UNIQUE,
    package_hash text NOT NULL UNIQUE CHECK (
        package_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    package_locator text NOT NULL,
    indexed_at timestamptz NOT NULL,
    CHECK (minute_success_count + minute_failure_count = candidate_count)
);

CREATE INDEX longitudinal_operational_date_idx
ON longitudinal_operational_index(decision_date, operation_run_id);
CREATE INDEX longitudinal_operational_model_idx
ON longitudinal_operational_index(
    signal_model_id,
    signal_model_version,
    decision_date
);
CREATE INDEX longitudinal_operational_config_idx
ON longitudinal_operational_index(configuration_hashes_json, decision_date);
CREATE INDEX longitudinal_operational_outcome_idx
ON longitudinal_operational_index(outcome_status, decision_date);

CREATE TRIGGER longitudinal_operational_no_update
BEFORE UPDATE ON longitudinal_operational_index
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER longitudinal_operational_no_delete
BEFORE DELETE ON longitudinal_operational_index
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
