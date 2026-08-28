WITH inserted_epoch AS (
    INSERT INTO mra.schema_epoch (
        singleton,
        epoch_name,
        schema_name,
        release_state,
        baseline_version,
        baseline_checksum,
        seed_checksum,
        catalog_checksum,
        reference_vocabulary_checksum
    )
    VALUES (
        true,
        'MRA_REFOUNDATION_1',
        'mra',
        'DRAFT',
        1,
        %s,
        %s,
        %s,
        %s
    )
    RETURNING epoch_name
)
INSERT INTO mra.schema_migrations (
    version,
    name,
    checksum,
    transactional,
    epoch_name
)
SELECT 1, '001_baseline', %s, true, epoch_name
FROM inserted_epoch;
