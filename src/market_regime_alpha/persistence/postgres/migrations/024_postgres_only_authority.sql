ALTER TABLE runtime_database_bindings
    DROP CONSTRAINT runtime_database_bindings_backend_check;

ALTER TABLE runtime_database_bindings
    ADD CONSTRAINT runtime_database_bindings_backend_check
    CHECK (backend = 'postgres');
