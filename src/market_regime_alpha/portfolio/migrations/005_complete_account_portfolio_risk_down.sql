PRAGMA foreign_keys = OFF;

DROP TABLE IF EXISTS complete_account_risk_decisions;
DROP TABLE IF EXISTS complete_account_portfolio_decisions;
DROP TABLE IF EXISTS authoritative_account_portfolio_snapshots;
DROP TABLE IF EXISTS complete_account_risk_commands;
DELETE FROM pdl_schema_migrations WHERE version = 5;

PRAGMA foreign_keys = ON;
