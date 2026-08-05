CREATE TABLE free_data_operation_blocked (
    scope_type text NOT NULL DEFAULT 'FREE_DATA_OPERATION'
        CHECK (scope_type = 'FREE_DATA_OPERATION'),
    command_hash text NOT NULL
        CHECK (command_hash ~ '^sha256:[0-9a-f]{64}$'),
    artifact_id text NOT NULL UNIQUE CHECK (length(artifact_id) > 0),
    content_hash text NOT NULL
        CHECK (content_hash ~ '^sha256:[0-9a-f]{64}$'),
    source_archive_id text NOT NULL CHECK (length(source_archive_id) > 0),
    source_manifest_id text NOT NULL CHECK (length(source_manifest_id) > 0),
    source_manifest_hash text NOT NULL
        CHECK (source_manifest_hash ~ '^sha256:[0-9a-f]{64}$'),
    provider_result_hash text NOT NULL
        CHECK (provider_result_hash ~ '^sha256:[0-9a-f]{64}$'),
    locator text NOT NULL CHECK (length(locator) > 0),
    reason_code text NOT NULL CHECK (length(reason_code) > 0),
    error_type text NOT NULL CHECK (length(error_type) > 0),
    code_revision text NOT NULL CHECK (length(code_revision) > 0),
    created_at timestamptz NOT NULL,
    PRIMARY KEY (scope_type, command_hash),
    FOREIGN KEY (scope_type, command_hash)
        REFERENCES runtime_database_bindings(scope_type, scope_id)
);

CREATE FUNCTION free_data_operation_blocked_reject_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'free-data blocked projections are immutable'
        USING ERRCODE = 'integrity_constraint_violation';
END;
$$;

CREATE TRIGGER free_data_operation_blocked_no_update
BEFORE UPDATE ON free_data_operation_blocked
FOR EACH ROW EXECUTE FUNCTION free_data_operation_blocked_reject_mutation();

CREATE TRIGGER free_data_operation_blocked_no_delete
BEFORE DELETE ON free_data_operation_blocked
FOR EACH ROW EXECUTE FUNCTION free_data_operation_blocked_reject_mutation();
