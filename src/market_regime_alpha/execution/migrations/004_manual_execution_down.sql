PRAGMA foreign_keys = OFF;

DROP TRIGGER IF EXISTS manual_fills_no_delete;
DROP TRIGGER IF EXISTS manual_fills_no_update;
DROP TABLE IF EXISTS manual_fills;
DROP TABLE IF EXISTS manual_trade_events;
DROP TABLE IF EXISTS manual_trade_records;
DROP TABLE IF EXISTS execution_commands;
DELETE FROM pdl_schema_migrations WHERE version = 4;

PRAGMA foreign_keys = ON;
