CREATE TABLE composite_operational_manifests (
    manifest_id text PRIMARY KEY,
    content_hash text NOT NULL UNIQUE,
    status text NOT NULL CHECK (
        status IN ('VERIFIED', 'DATA_INSUFFICIENT', 'CONFLICTED')
    ),
    decision_time timestamptz NOT NULL,
    created_at timestamptz NOT NULL,
    policy_id text NOT NULL,
    policy_hash text NOT NULL,
    builder_revision text NOT NULL,
    package_path text NOT NULL,
    daily_package_path text NOT NULL,
    supplemental_package_path text NOT NULL,
    artifact_json text NOT NULL CHECK (artifact_json IS JSON),
    policy_json text NOT NULL CHECK (policy_json IS JSON)
);

CREATE TABLE composite_operational_components (
    manifest_id text NOT NULL,
    role text NOT NULL,
    scope_key text NOT NULL,
    artifact_id text NOT NULL,
    content_hash text NOT NULL,
    source_manifest_id text NOT NULL,
    source_manifest_hash text NOT NULL,
    availability_time timestamptz NOT NULL,
    data_eligibility text NOT NULL CHECK (data_eligibility = 'EXPLORATORY'),
    PRIMARY KEY (manifest_id, role, scope_key),
    FOREIGN KEY (manifest_id)
        REFERENCES composite_operational_manifests(manifest_id)
);

CREATE TABLE composite_operational_field_authorities (
    manifest_id text NOT NULL,
    field_group text NOT NULL,
    scope_key text NOT NULL,
    component_role text NOT NULL,
    artifact_id text NOT NULL,
    content_hash text NOT NULL,
    PRIMARY KEY (manifest_id, field_group, scope_key),
    FOREIGN KEY (manifest_id)
        REFERENCES composite_operational_manifests(manifest_id)
);

CREATE TABLE composite_operational_commands (
    idempotency_key text PRIMARY KEY,
    command_hash text NOT NULL,
    manifest_id text NOT NULL,
    command_json text NOT NULL CHECK (command_json IS JSON),
    created_at timestamptz NOT NULL,
    FOREIGN KEY (manifest_id)
        REFERENCES composite_operational_manifests(manifest_id)
);

CREATE INDEX composite_operational_commands_manifest_id_idx
ON composite_operational_commands(manifest_id);

CREATE TRIGGER composite_operational_manifests_no_update
BEFORE UPDATE ON composite_operational_manifests
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER composite_operational_manifests_no_delete
BEFORE DELETE ON composite_operational_manifests
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER composite_operational_components_no_update
BEFORE UPDATE ON composite_operational_components
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER composite_operational_components_no_delete
BEFORE DELETE ON composite_operational_components
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER composite_operational_field_authorities_no_update
BEFORE UPDATE ON composite_operational_field_authorities
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER composite_operational_field_authorities_no_delete
BEFORE DELETE ON composite_operational_field_authorities
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER composite_operational_commands_no_update
BEFORE UPDATE ON composite_operational_commands
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER composite_operational_commands_no_delete
BEFORE DELETE ON composite_operational_commands
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
