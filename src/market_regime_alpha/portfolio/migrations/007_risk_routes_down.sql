PRAGMA foreign_keys = OFF;

DROP TRIGGER IF EXISTS risk_reducing_decisions_no_delete;
DROP TRIGGER IF EXISTS risk_reducing_decisions_no_update;
DROP TABLE IF EXISTS risk_reducing_commands;
DROP TABLE IF EXISTS risk_reducing_decisions;
DELETE FROM pdl_schema_migrations WHERE version = 7;

PRAGMA foreign_keys = ON;
