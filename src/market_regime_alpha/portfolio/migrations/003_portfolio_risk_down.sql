PRAGMA foreign_keys = OFF;

DROP TABLE IF EXISTS risk_decisions;
DROP TABLE IF EXISTS portfolio_decisions;
DROP TABLE IF EXISTS portfolio_risk_commands;
DELETE FROM pdl_schema_migrations WHERE version = 3;

PRAGMA foreign_keys = ON;
