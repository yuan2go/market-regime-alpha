CREATE TABLE runtime_database_bindings (
    scope_type text NOT NULL
        CHECK (scope_type IN ('CANONICAL_LIFECYCLE', 'CONTROLLED_OPERATION')),
    scope_id text NOT NULL CHECK (length(scope_id) > 0),
    backend text NOT NULL CHECK (backend IN ('postgres', 'sqlite')),
    locator text NOT NULL CHECK (length(locator) > 0),
    created_at timestamptz NOT NULL,
    PRIMARY KEY (scope_type, scope_id)
);

CREATE FUNCTION runtime_database_bindings_reject_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'runtime database bindings are immutable'
        USING ERRCODE = 'integrity_constraint_violation';
END;
$$;

CREATE TRIGGER runtime_database_bindings_no_update
BEFORE UPDATE ON runtime_database_bindings
FOR EACH ROW EXECUTE FUNCTION runtime_database_bindings_reject_mutation();

CREATE TRIGGER runtime_database_bindings_no_delete
BEFORE DELETE ON runtime_database_bindings
FOR EACH ROW EXECUTE FUNCTION runtime_database_bindings_reject_mutation();
