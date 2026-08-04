PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS pdl_schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS composite_operational_manifests (
    manifest_id TEXT PRIMARY KEY,
    content_hash TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL CHECK (status IN (
        'VERIFIED', 'DATA_INSUFFICIENT', 'CONFLICTED'
    )),
    decision_time TEXT NOT NULL,
    created_at TEXT NOT NULL,
    policy_id TEXT NOT NULL,
    policy_hash TEXT NOT NULL,
    builder_revision TEXT NOT NULL,
    package_path TEXT NOT NULL,
    daily_package_path TEXT NOT NULL,
    supplemental_package_path TEXT NOT NULL,
    artifact_json TEXT NOT NULL,
    policy_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS composite_operational_components (
    manifest_id TEXT NOT NULL,
    role TEXT NOT NULL,
    scope_key TEXT NOT NULL,
    artifact_id TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    source_manifest_id TEXT NOT NULL,
    source_manifest_hash TEXT NOT NULL,
    availability_time TEXT NOT NULL,
    data_eligibility TEXT NOT NULL CHECK (data_eligibility = 'EXPLORATORY'),
    PRIMARY KEY (manifest_id, role, scope_key),
    FOREIGN KEY (manifest_id)
        REFERENCES composite_operational_manifests(manifest_id)
);

CREATE TABLE IF NOT EXISTS composite_operational_field_authorities (
    manifest_id TEXT NOT NULL,
    field_group TEXT NOT NULL,
    scope_key TEXT NOT NULL,
    component_role TEXT NOT NULL,
    artifact_id TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    PRIMARY KEY (manifest_id, field_group, scope_key),
    FOREIGN KEY (manifest_id)
        REFERENCES composite_operational_manifests(manifest_id)
);

CREATE TABLE IF NOT EXISTS composite_operational_commands (
    idempotency_key TEXT PRIMARY KEY,
    command_hash TEXT NOT NULL,
    manifest_id TEXT NOT NULL,
    command_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (manifest_id)
        REFERENCES composite_operational_manifests(manifest_id)
);

CREATE TRIGGER IF NOT EXISTS composite_operational_manifests_no_update
BEFORE UPDATE ON composite_operational_manifests
BEGIN
    SELECT RAISE(ABORT, 'composite operational manifests are append-only');
END;

CREATE TRIGGER IF NOT EXISTS composite_operational_manifests_no_delete
BEFORE DELETE ON composite_operational_manifests
BEGIN
    SELECT RAISE(ABORT, 'composite operational manifests are append-only');
END;

CREATE TRIGGER IF NOT EXISTS composite_operational_components_no_update
BEFORE UPDATE ON composite_operational_components
BEGIN
    SELECT RAISE(ABORT, 'composite operational components are append-only');
END;

CREATE TRIGGER IF NOT EXISTS composite_operational_components_no_delete
BEFORE DELETE ON composite_operational_components
BEGIN
    SELECT RAISE(ABORT, 'composite operational components are append-only');
END;

CREATE TRIGGER IF NOT EXISTS composite_operational_field_authorities_no_update
BEFORE UPDATE ON composite_operational_field_authorities
BEGIN
    SELECT RAISE(ABORT, 'composite operational field authorities are append-only');
END;

CREATE TRIGGER IF NOT EXISTS composite_operational_field_authorities_no_delete
BEFORE DELETE ON composite_operational_field_authorities
BEGIN
    SELECT RAISE(ABORT, 'composite operational field authorities are append-only');
END;

CREATE TRIGGER IF NOT EXISTS composite_operational_commands_no_update
BEFORE UPDATE ON composite_operational_commands
BEGIN
    SELECT RAISE(ABORT, 'composite operational commands are append-only');
END;

CREATE TRIGGER IF NOT EXISTS composite_operational_commands_no_delete
BEFORE DELETE ON composite_operational_commands
BEGIN
    SELECT RAISE(ABORT, 'composite operational commands are append-only');
END;

INSERT OR IGNORE INTO pdl_schema_migrations(version, applied_at)
VALUES (9, CURRENT_TIMESTAMP);
