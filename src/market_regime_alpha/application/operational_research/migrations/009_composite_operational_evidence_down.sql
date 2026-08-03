PRAGMA foreign_keys = OFF;

DROP TRIGGER IF EXISTS composite_operational_commands_no_delete;
DROP TRIGGER IF EXISTS composite_operational_commands_no_update;
DROP TRIGGER IF EXISTS composite_operational_field_authorities_no_delete;
DROP TRIGGER IF EXISTS composite_operational_field_authorities_no_update;
DROP TRIGGER IF EXISTS composite_operational_components_no_delete;
DROP TRIGGER IF EXISTS composite_operational_components_no_update;
DROP TRIGGER IF EXISTS composite_operational_manifests_no_delete;
DROP TRIGGER IF EXISTS composite_operational_manifests_no_update;

DROP TABLE IF EXISTS composite_operational_commands;
DROP TABLE IF EXISTS composite_operational_field_authorities;
DROP TABLE IF EXISTS composite_operational_components;
DROP TABLE IF EXISTS composite_operational_manifests;

DELETE FROM pdl_schema_migrations WHERE version = 9;

PRAGMA foreign_keys = ON;
