CREATE TABLE thesis_health_observations (
    observation_id text PRIMARY KEY,
    thesis_id text NOT NULL,
    thesis_version bigint NOT NULL CHECK (thesis_version >= 0),
    observed_health_state text NOT NULL CHECK (
        observed_health_state IN (
            'HEALTHY', 'WEAKENING', 'INVALIDATED', 'DATA_INSUFFICIENT'
        )
    ),
    effective_health_state text CHECK (
        effective_health_state IN ('HEALTHY', 'WEAKENING', 'INVALIDATED')
    ),
    content_hash text NOT NULL UNIQUE,
    input_bundle_id text NOT NULL UNIQUE,
    input_bundle_hash text NOT NULL UNIQUE,
    configuration_id text NOT NULL,
    configuration_hash text NOT NULL,
    rule_set_id text NOT NULL,
    rule_set_hash text NOT NULL,
    prior_observation_id text UNIQUE,
    prior_observation_hash text,
    observation_json text NOT NULL CHECK (observation_json IS JSON),
    input_bundle_json text NOT NULL CHECK (input_bundle_json IS JSON),
    configuration_json text NOT NULL CHECK (configuration_json IS JSON),
    rule_set_json text NOT NULL CHECK (rule_set_json IS JSON),
    prior_observation_json text CHECK (
        prior_observation_json IS NULL OR prior_observation_json IS JSON
    ),
    assessed_at timestamptz NOT NULL,
    CHECK ((prior_observation_id IS NULL) = (prior_observation_hash IS NULL)),
    CHECK ((prior_observation_id IS NULL) = (prior_observation_json IS NULL)),
    UNIQUE (thesis_id, assessed_at),
    FOREIGN KEY (prior_observation_id)
        REFERENCES thesis_health_observations(observation_id)
);

CREATE TABLE thesis_health_commands (
    idempotency_key text PRIMARY KEY,
    command_hash text NOT NULL,
    observation_id text NOT NULL,
    created_at timestamptz NOT NULL,
    FOREIGN KEY (observation_id)
        REFERENCES thesis_health_observations(observation_id)
);

CREATE INDEX thesis_health_commands_observation_id_idx
ON thesis_health_commands(observation_id);

CREATE UNIQUE INDEX thesis_health_one_root_per_thesis
ON thesis_health_observations(thesis_id)
WHERE prior_observation_id IS NULL;

CREATE TRIGGER thesis_health_observations_no_update
BEFORE UPDATE ON thesis_health_observations
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER thesis_health_observations_no_delete
BEFORE DELETE ON thesis_health_observations
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER thesis_health_commands_no_update
BEFORE UPDATE ON thesis_health_commands
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER thesis_health_commands_no_delete
BEFORE DELETE ON thesis_health_commands
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
