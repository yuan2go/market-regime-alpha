PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS pdl_schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS governance_commands (
    idempotency_key TEXT PRIMARY KEY,
    aggregate_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    result_version INTEGER NOT NULL CHECK (result_version >= 0),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS model_registrations (
    model_id TEXT PRIMARY KEY,
    registration_json TEXT NOT NULL,
    definition_hash TEXT NOT NULL,
    lifecycle_status TEXT NOT NULL,
    evidence_level TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version >= 0)
);

CREATE TABLE IF NOT EXISTS model_lifecycle_transitions (
    model_id TEXT NOT NULL,
    sequence INTEGER NOT NULL CHECK (sequence > 0),
    transition_json TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    PRIMARY KEY (model_id, sequence),
    FOREIGN KEY (model_id) REFERENCES model_registrations(model_id)
);

CREATE TABLE IF NOT EXISTS governed_experiments (
    experiment_id TEXT PRIMARY KEY,
    protocol_json TEXT NOT NULL,
    protocol_hash TEXT NOT NULL,
    validation_access_count INTEGER NOT NULL DEFAULT 0 CHECK (validation_access_count >= 0),
    sealed_test_access_count INTEGER NOT NULL DEFAULT 0 CHECK (sealed_test_access_count >= 0),
    version INTEGER NOT NULL DEFAULT 0 CHECK (version >= 0)
);

CREATE TABLE IF NOT EXISTS experiment_access_events (
    experiment_id TEXT NOT NULL,
    sequence INTEGER NOT NULL CHECK (sequence > 0),
    access_kind TEXT NOT NULL CHECK (access_kind IN ('VALIDATION', 'SEALED_TEST')),
    validation_access_count INTEGER NOT NULL CHECK (validation_access_count >= 0),
    sealed_test_access_count INTEGER NOT NULL CHECK (sealed_test_access_count >= 0),
    idempotency_key TEXT NOT NULL UNIQUE,
    PRIMARY KEY (experiment_id, sequence),
    FOREIGN KEY (experiment_id) REFERENCES governed_experiments(experiment_id)
);

INSERT OR IGNORE INTO pdl_schema_migrations(version, applied_at)
VALUES (1, CURRENT_TIMESTAMP);
