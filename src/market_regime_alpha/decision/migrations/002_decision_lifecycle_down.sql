PRAGMA foreign_keys = OFF;

DROP TABLE IF EXISTS thesis_events;
DROP TABLE IF EXISTS trading_theses;
DROP TABLE IF EXISTS opportunity_events;
DROP TABLE IF EXISTS trading_opportunities;
DROP TABLE IF EXISTS decision_commands;
DELETE FROM pdl_schema_migrations WHERE version = 2;

PRAGMA foreign_keys = ON;
