PRAGMA foreign_keys = ON;

BEGIN IMMEDIATE;

CREATE TABLE IF NOT EXISTS longitudinal_operational_schema_migration (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS longitudinal_operational_index (
    decision_date TEXT NOT NULL CHECK (date(decision_date) = decision_date),
    operation_run_id TEXT PRIMARY KEY,
    universe_id TEXT NOT NULL,
    daily_dataset_id TEXT NOT NULL,
    minute_dataset_id TEXT NOT NULL,
    feature_set_id TEXT NOT NULL,
    signal_model_id TEXT NOT NULL,
    signal_model_version TEXT NOT NULL,
    configuration_hashes_json TEXT NOT NULL CHECK (
        json_valid(configuration_hashes_json)
        AND json_type(configuration_hashes_json) = 'array'
    ),
    candidate_count INTEGER NOT NULL CHECK (candidate_count >= 0),
    signal_state_counts_json TEXT NOT NULL CHECK (
        json_valid(signal_state_counts_json)
        AND json_type(signal_state_counts_json) = 'object'
    ),
    minute_success_count INTEGER NOT NULL CHECK (minute_success_count >= 0),
    minute_failure_count INTEGER NOT NULL CHECK (minute_failure_count >= 0),
    deadline_status TEXT NOT NULL,
    outcome_status TEXT NOT NULL CHECK (outcome_status IN ('OUTCOME_PENDING', 'SETTLED')),
    package_id TEXT NOT NULL UNIQUE,
    package_hash TEXT NOT NULL UNIQUE CHECK (
        length(package_hash) = 71
        AND substr(package_hash, 1, 7) = 'sha256:'
        AND substr(package_hash, 8) NOT GLOB '*[^0-9a-f]*'
    ),
    package_locator TEXT NOT NULL,
    indexed_at TEXT NOT NULL,
    CHECK (minute_success_count + minute_failure_count = candidate_count)
);

CREATE INDEX IF NOT EXISTS longitudinal_operational_date_idx
    ON longitudinal_operational_index(decision_date, operation_run_id);
CREATE INDEX IF NOT EXISTS longitudinal_operational_model_idx
    ON longitudinal_operational_index(signal_model_id, signal_model_version, decision_date);
CREATE INDEX IF NOT EXISTS longitudinal_operational_config_idx
    ON longitudinal_operational_index(configuration_hashes_json, decision_date);
CREATE INDEX IF NOT EXISTS longitudinal_operational_outcome_idx
    ON longitudinal_operational_index(outcome_status, decision_date);

CREATE TRIGGER IF NOT EXISTS longitudinal_operational_no_update
BEFORE UPDATE ON longitudinal_operational_index BEGIN
    SELECT RAISE(ABORT, 'Longitudinal Operational Index is append-only');
END;

CREATE TRIGGER IF NOT EXISTS longitudinal_operational_no_delete
BEFORE DELETE ON longitudinal_operational_index BEGIN
    SELECT RAISE(ABORT, 'Longitudinal Operational Index is append-only');
END;

INSERT OR IGNORE INTO longitudinal_operational_schema_migration(version, applied_at)
VALUES (15, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));

COMMIT;
