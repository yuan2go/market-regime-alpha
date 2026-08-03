PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS pdl_schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS thesis_health_observations (
    observation_id TEXT PRIMARY KEY,
    thesis_id TEXT NOT NULL,
    thesis_version INTEGER NOT NULL CHECK (thesis_version >= 0),
    observed_health_state TEXT NOT NULL CHECK (observed_health_state IN (
        'HEALTHY', 'WEAKENING', 'INVALIDATED', 'DATA_INSUFFICIENT'
    )),
    effective_health_state TEXT CHECK (effective_health_state IN (
        'HEALTHY', 'WEAKENING', 'INVALIDATED'
    )),
    content_hash TEXT NOT NULL UNIQUE,
    input_bundle_id TEXT NOT NULL UNIQUE,
    input_bundle_hash TEXT NOT NULL UNIQUE,
    configuration_id TEXT NOT NULL,
    configuration_hash TEXT NOT NULL,
    rule_set_id TEXT NOT NULL,
    rule_set_hash TEXT NOT NULL,
    prior_observation_id TEXT UNIQUE,
    prior_observation_hash TEXT,
    observation_json TEXT NOT NULL,
    input_bundle_json TEXT NOT NULL,
    configuration_json TEXT NOT NULL,
    rule_set_json TEXT NOT NULL,
    prior_observation_json TEXT,
    assessed_at TEXT NOT NULL,
    CHECK ((prior_observation_id IS NULL) = (prior_observation_hash IS NULL)),
    CHECK ((prior_observation_id IS NULL) = (prior_observation_json IS NULL)),
    UNIQUE (thesis_id, assessed_at),
    FOREIGN KEY (prior_observation_id)
        REFERENCES thesis_health_observations(observation_id)
);

CREATE TABLE IF NOT EXISTS thesis_health_commands (
    idempotency_key TEXT PRIMARY KEY,
    command_hash TEXT NOT NULL,
    observation_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (observation_id)
        REFERENCES thesis_health_observations(observation_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS thesis_health_one_root_per_thesis
ON thesis_health_observations(thesis_id)
WHERE prior_observation_id IS NULL;

CREATE TRIGGER IF NOT EXISTS thesis_health_observations_no_update
BEFORE UPDATE ON thesis_health_observations
BEGIN
    SELECT RAISE(ABORT, 'thesis health observations are append-only');
END;

CREATE TRIGGER IF NOT EXISTS thesis_health_observations_no_delete
BEFORE DELETE ON thesis_health_observations
BEGIN
    SELECT RAISE(ABORT, 'thesis health observations are append-only');
END;

CREATE TRIGGER IF NOT EXISTS thesis_health_commands_no_update
BEFORE UPDATE ON thesis_health_commands
BEGIN
    SELECT RAISE(ABORT, 'thesis health commands are append-only');
END;

CREATE TRIGGER IF NOT EXISTS thesis_health_commands_no_delete
BEFORE DELETE ON thesis_health_commands
BEGIN
    SELECT RAISE(ABORT, 'thesis health commands are append-only');
END;

INSERT OR IGNORE INTO pdl_schema_migrations(version, applied_at)
VALUES (8, CURRENT_TIMESTAMP);
