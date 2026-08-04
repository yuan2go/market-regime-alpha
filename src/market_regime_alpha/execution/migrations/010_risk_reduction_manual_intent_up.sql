PRAGMA foreign_keys = OFF;

CREATE TABLE IF NOT EXISTS manual_trade_records_v3 (
    manual_trade_id TEXT PRIMARY KEY,
    authority_route TEXT NOT NULL DEFAULT 'INCREASING'
        CHECK (authority_route IN ('INCREASING', 'REDUCING')),
    risk_decision_id TEXT,
    risk_reducing_decision_id TEXT,
    risk_reduction_confirmation_id TEXT,
    account_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
    state TEXT NOT NULL,
    filled_quantity INTEGER NOT NULL CHECK (filled_quantity >= 0),
    aggregate_json TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version >= 0),
    CHECK (
        (
            authority_route = 'INCREASING'
            AND risk_decision_id IS NOT NULL
            AND risk_reducing_decision_id IS NULL
            AND risk_reduction_confirmation_id IS NULL
        )
        OR
        (
            authority_route = 'REDUCING'
            AND risk_decision_id IS NULL
            AND risk_reducing_decision_id IS NOT NULL
            AND risk_reduction_confirmation_id IS NOT NULL
        )
    )
);

INSERT OR IGNORE INTO manual_trade_records_v3(
    manual_trade_id,
    authority_route,
    risk_decision_id,
    risk_reducing_decision_id,
    risk_reduction_confirmation_id,
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
    'INCREASING',
    risk_decision_id,
    NULL,
    NULL,
    account_id,
    symbol,
    side,
    state,
    filled_quantity,
    aggregate_json,
    version
FROM manual_trade_records;

DROP TABLE manual_trade_records;
ALTER TABLE manual_trade_records_v3 RENAME TO manual_trade_records;

CREATE TABLE IF NOT EXISTS operational_exit_directives (
    directive_id TEXT PRIMARY KEY,
    content_hash TEXT NOT NULL UNIQUE,
    exit_assessment_id TEXT NOT NULL,
    risk_reducing_decision_id TEXT NOT NULL,
    thesis_health_observation_id TEXT NOT NULL,
    composite_manifest_id TEXT NOT NULL,
    directive_json TEXT NOT NULL,
    exit_assessment_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS risk_reduction_confirmation_attempts (
    attempt_id TEXT PRIMARY KEY,
    content_hash TEXT NOT NULL UNIQUE,
    state TEXT NOT NULL CHECK (
        state IN (
            'CONFIRMED_INTENT',
            'EXPIRED',
            'POSITION_CHANGED',
            'BLOCKED_ON_RECHECK',
            'DATA_INSUFFICIENT',
            'ACTION_SEMANTICS_CONFLICT'
        )
    ),
    risk_reducing_decision_id TEXT NOT NULL,
    exit_directive_id TEXT NOT NULL,
    manual_trade_id TEXT UNIQUE,
    attempt_json TEXT NOT NULL,
    policy_json TEXT NOT NULL,
    recheck_observation_json TEXT NOT NULL,
    current_position_json TEXT NOT NULL,
    trading_calendar_json TEXT NOT NULL,
    symbol_trading_status_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (exit_directive_id)
        REFERENCES operational_exit_directives(directive_id),
    FOREIGN KEY (manual_trade_id)
        REFERENCES manual_trade_records(manual_trade_id),
    CHECK (
        (state = 'CONFIRMED_INTENT' AND manual_trade_id IS NOT NULL)
        OR (state != 'CONFIRMED_INTENT' AND manual_trade_id IS NULL)
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS one_confirmed_intent_per_reducing_decision
ON risk_reduction_confirmation_attempts(risk_reducing_decision_id)
WHERE state = 'CONFIRMED_INTENT';

CREATE TABLE IF NOT EXISTS risk_reduction_confirmation_commands (
    idempotency_key TEXT PRIMARY KEY,
    command_hash TEXT NOT NULL,
    risk_reducing_decision_id TEXT NOT NULL,
    attempt_id TEXT NOT NULL,
    manual_trade_id TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (attempt_id)
        REFERENCES risk_reduction_confirmation_attempts(attempt_id),
    FOREIGN KEY (manual_trade_id)
        REFERENCES manual_trade_records(manual_trade_id)
);

CREATE TABLE IF NOT EXISTS risk_reducing_manual_trade_bindings (
    manual_trade_id TEXT PRIMARY KEY,
    position_book_id TEXT NOT NULL,
    opportunity_id TEXT NOT NULL,
    thesis_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    risk_reducing_decision_id TEXT NOT NULL UNIQUE,
    risk_reducing_decision_hash TEXT NOT NULL,
    confirmation_attempt_id TEXT NOT NULL UNIQUE,
    confirmation_attempt_hash TEXT NOT NULL,
    source_position_snapshot_id TEXT NOT NULL,
    source_position_snapshot_hash TEXT NOT NULL,
    source_position_snapshot_version INTEGER NOT NULL
        CHECK (source_position_snapshot_version >= 0),
    target_quantity INTEGER NOT NULL CHECK (target_quantity >= 0),
    order_quantity INTEGER NOT NULL CHECK (order_quantity > 0),
    created_at TEXT NOT NULL,
    FOREIGN KEY (manual_trade_id)
        REFERENCES manual_trade_records(manual_trade_id),
    FOREIGN KEY (position_book_id)
        REFERENCES position_books(position_book_id),
    FOREIGN KEY (confirmation_attempt_id)
        REFERENCES risk_reduction_confirmation_attempts(attempt_id)
);

CREATE TRIGGER IF NOT EXISTS operational_exit_directives_no_update
BEFORE UPDATE ON operational_exit_directives
BEGIN
    SELECT RAISE(ABORT, 'operational exit directives are append-only');
END;

CREATE TRIGGER IF NOT EXISTS operational_exit_directives_no_delete
BEFORE DELETE ON operational_exit_directives
BEGIN
    SELECT RAISE(ABORT, 'operational exit directives are append-only');
END;

CREATE TRIGGER IF NOT EXISTS risk_reduction_confirmation_attempts_no_update
BEFORE UPDATE ON risk_reduction_confirmation_attempts
BEGIN
    SELECT RAISE(ABORT, 'risk reduction confirmation attempts are append-only');
END;

CREATE TRIGGER IF NOT EXISTS risk_reduction_confirmation_attempts_no_delete
BEFORE DELETE ON risk_reduction_confirmation_attempts
BEGIN
    SELECT RAISE(ABORT, 'risk reduction confirmation attempts are append-only');
END;

CREATE TRIGGER IF NOT EXISTS risk_reduction_confirmation_commands_no_update
BEFORE UPDATE ON risk_reduction_confirmation_commands
BEGIN
    SELECT RAISE(ABORT, 'risk reduction confirmation commands are append-only');
END;

CREATE TRIGGER IF NOT EXISTS risk_reduction_confirmation_commands_no_delete
BEFORE DELETE ON risk_reduction_confirmation_commands
BEGIN
    SELECT RAISE(ABORT, 'risk reduction confirmation commands are append-only');
END;

CREATE TRIGGER IF NOT EXISTS risk_reducing_manual_trade_bindings_no_update
BEFORE UPDATE ON risk_reducing_manual_trade_bindings
BEGIN
    SELECT RAISE(ABORT, 'risk reducing manual trade bindings are append-only');
END;

CREATE TRIGGER IF NOT EXISTS risk_reducing_manual_trade_bindings_no_delete
BEFORE DELETE ON risk_reducing_manual_trade_bindings
BEGIN
    SELECT RAISE(ABORT, 'risk reducing manual trade bindings are append-only');
END;

CREATE TRIGGER IF NOT EXISTS traceable_manual_trade_binding_route_guard
BEFORE INSERT ON traceable_manual_trade_bindings
WHEN (
    SELECT authority_route FROM manual_trade_records
    WHERE manual_trade_id = NEW.manual_trade_id
) != 'INCREASING'
OR EXISTS (
    SELECT 1 FROM risk_reducing_manual_trade_bindings
    WHERE manual_trade_id = NEW.manual_trade_id
)
BEGIN
    SELECT RAISE(ABORT, 'manual trade authority route binding conflict');
END;

CREATE TRIGGER IF NOT EXISTS risk_reducing_manual_trade_binding_route_guard
BEFORE INSERT ON risk_reducing_manual_trade_bindings
WHEN (
    SELECT authority_route FROM manual_trade_records
    WHERE manual_trade_id = NEW.manual_trade_id
) != 'REDUCING'
OR EXISTS (
    SELECT 1 FROM traceable_manual_trade_bindings
    WHERE manual_trade_id = NEW.manual_trade_id
)
BEGIN
    SELECT RAISE(ABORT, 'manual trade authority route binding conflict');
END;

INSERT OR IGNORE INTO pdl_schema_migrations(version, applied_at)
VALUES (10, CURRENT_TIMESTAMP);

PRAGMA foreign_keys = ON;
