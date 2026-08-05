PRAGMA foreign_keys = ON;

BEGIN IMMEDIATE;
DROP TRIGGER IF EXISTS longitudinal_operational_no_delete;
DROP TRIGGER IF EXISTS longitudinal_operational_no_update;
DROP TABLE IF EXISTS longitudinal_operational_index;
DELETE FROM longitudinal_operational_schema_migration WHERE version = 15;
DROP TABLE IF EXISTS longitudinal_operational_schema_migration;
COMMIT;
