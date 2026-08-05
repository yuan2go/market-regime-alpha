ALTER TABLE runtime_database_bindings
DROP CONSTRAINT runtime_database_bindings_scope_type_check;

ALTER TABLE runtime_database_bindings
ADD CONSTRAINT runtime_database_bindings_scope_type_check
CHECK (
    scope_type IN (
        'CANONICAL_LIFECYCLE',
        'CONTROLLED_OPERATION',
        'DAILY_LOOP',
        'FREE_DATA_OPERATION'
    )
);
