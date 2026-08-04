PRAGMA foreign_keys = OFF;

CREATE TEMP TABLE h4_5_down_guard (
    reducing_trade_count INTEGER NOT NULL CHECK (reducing_trade_count = 0)
);
INSERT INTO h4_5_down_guard(reducing_trade_count)
SELECT COUNT(*) FROM manual_trade_records WHERE authority_route = 'REDUCING';
DROP TABLE h4_5_down_guard;

DROP TRIGGER IF EXISTS risk_reducing_manual_trade_bindings_no_delete;
DROP TRIGGER IF EXISTS risk_reducing_manual_trade_bindings_no_update;
DROP TRIGGER IF EXISTS risk_reducing_manual_trade_binding_route_guard;
DROP TRIGGER IF EXISTS traceable_manual_trade_binding_route_guard;
DROP TRIGGER IF EXISTS risk_reduction_confirmation_commands_no_delete;
DROP TRIGGER IF EXISTS risk_reduction_confirmation_commands_no_update;
DROP TRIGGER IF EXISTS risk_reduction_confirmation_attempts_no_delete;
DROP TRIGGER IF EXISTS risk_reduction_confirmation_attempts_no_update;
DROP TRIGGER IF EXISTS operational_exit_directives_no_delete;
DROP TRIGGER IF EXISTS operational_exit_directives_no_update;

DROP TABLE IF EXISTS risk_reducing_manual_trade_bindings;
DROP TABLE IF EXISTS risk_reduction_confirmation_commands;
DROP INDEX IF EXISTS one_confirmed_intent_per_reducing_decision;
DROP TABLE IF EXISTS risk_reduction_confirmation_attempts;
DROP TABLE IF EXISTS operational_exit_directives;

CREATE TABLE manual_trade_records_v2 (
    manual_trade_id TEXT PRIMARY KEY,
    risk_decision_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
    state TEXT NOT NULL,
    filled_quantity INTEGER NOT NULL CHECK (filled_quantity >= 0),
    aggregate_json TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version >= 0)
);

INSERT INTO manual_trade_records_v2(
    manual_trade_id,
    risk_decision_id,
    account_id,
    symbol,
    side,
    state,
    filled_quantity,
    aggregate_json,
    version
)
SELECT
    manual_trade_id,
    risk_decision_id,
    account_id,
    symbol,
    side,
    state,
    filled_quantity,
    aggregate_json,
    version
FROM manual_trade_records
WHERE authority_route = 'INCREASING';

DROP TABLE manual_trade_records;
ALTER TABLE manual_trade_records_v2 RENAME TO manual_trade_records;

DELETE FROM pdl_schema_migrations WHERE version = 10;

PRAGMA foreign_keys = ON;
