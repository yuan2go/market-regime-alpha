CREATE TABLE governance_commands (
    idempotency_key text PRIMARY KEY,
    aggregate_type text NOT NULL,
    aggregate_id text NOT NULL,
    payload_hash text NOT NULL,
    result_version bigint NOT NULL CHECK (result_version >= 0),
    created_at timestamptz NOT NULL
);

CREATE TABLE model_registrations (
    model_id text PRIMARY KEY,
    registration_json text NOT NULL CHECK (registration_json IS JSON),
    definition_hash text NOT NULL,
    lifecycle_status text NOT NULL,
    evidence_level text NOT NULL,
    version bigint NOT NULL CHECK (version >= 0)
);

CREATE TABLE model_lifecycle_transitions (
    model_id text NOT NULL,
    sequence bigint NOT NULL CHECK (sequence > 0),
    transition_json text NOT NULL CHECK (transition_json IS JSON),
    idempotency_key text NOT NULL UNIQUE,
    PRIMARY KEY (model_id, sequence),
    FOREIGN KEY (model_id) REFERENCES model_registrations(model_id)
);

CREATE INDEX model_lifecycle_transitions_model_id_idx
ON model_lifecycle_transitions(model_id);

CREATE TABLE governed_experiments (
    experiment_id text PRIMARY KEY,
    protocol_json text NOT NULL CHECK (protocol_json IS JSON),
    protocol_hash text NOT NULL,
    validation_access_count bigint NOT NULL DEFAULT 0
        CHECK (validation_access_count >= 0),
    sealed_test_access_count bigint NOT NULL DEFAULT 0
        CHECK (sealed_test_access_count >= 0),
    version bigint NOT NULL DEFAULT 0 CHECK (version >= 0)
);

CREATE TABLE experiment_access_events (
    experiment_id text NOT NULL,
    sequence bigint NOT NULL CHECK (sequence > 0),
    access_kind text NOT NULL CHECK (
        access_kind IN ('VALIDATION', 'SEALED_TEST')
    ),
    validation_access_count bigint NOT NULL
        CHECK (validation_access_count >= 0),
    sealed_test_access_count bigint NOT NULL
        CHECK (sealed_test_access_count >= 0),
    idempotency_key text NOT NULL UNIQUE,
    PRIMARY KEY (experiment_id, sequence),
    FOREIGN KEY (experiment_id) REFERENCES governed_experiments(experiment_id)
);

CREATE INDEX experiment_access_events_experiment_id_idx
ON experiment_access_events(experiment_id);
