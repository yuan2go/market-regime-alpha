PRAGMA foreign_keys = OFF;

DROP TRIGGER IF EXISTS thesis_health_commands_no_delete;
DROP TRIGGER IF EXISTS thesis_health_commands_no_update;
DROP TRIGGER IF EXISTS thesis_health_observations_no_delete;
DROP TRIGGER IF EXISTS thesis_health_observations_no_update;
DROP TABLE IF EXISTS thesis_health_commands;
DROP TABLE IF EXISTS thesis_health_observations;
DELETE FROM pdl_schema_migrations WHERE version = 8;

PRAGMA foreign_keys = ON;
