CREATE FUNCTION reject_append_only_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION '% is append-only', TG_TABLE_NAME;
END;
$$;

CREATE TABLE execution_commands (
    idempotency_key text PRIMARY KEY,
    command_hash text NOT NULL,
    manual_trade_id text NOT NULL,
    fill_id text,
    result_version bigint NOT NULL CHECK (result_version >= 0),
    created_at timestamptz NOT NULL
);

CREATE TABLE manual_trade_records (
    manual_trade_id text PRIMARY KEY,
    risk_decision_id text NOT NULL,
    account_id text NOT NULL,
    symbol text NOT NULL,
    side text NOT NULL CHECK (side IN ('BUY', 'SELL')),
    state text NOT NULL,
    filled_quantity bigint NOT NULL CHECK (filled_quantity >= 0),
    aggregate_json text NOT NULL CHECK (aggregate_json IS JSON),
    version bigint NOT NULL CHECK (version >= 0)
);

CREATE TABLE manual_trade_events (
    manual_trade_id text NOT NULL,
    sequence bigint NOT NULL CHECK (sequence >= 0),
    state text NOT NULL,
    aggregate_json text NOT NULL CHECK (aggregate_json IS JSON),
    idempotency_key text NOT NULL UNIQUE,
    created_at timestamptz NOT NULL,
    PRIMARY KEY (manual_trade_id, sequence),
    FOREIGN KEY (manual_trade_id) REFERENCES manual_trade_records(manual_trade_id)
);

CREATE INDEX manual_trade_events_manual_trade_id_idx
ON manual_trade_events(manual_trade_id);

CREATE TABLE manual_fills (
    fill_id text PRIMARY KEY,
    external_fill_id text NOT NULL UNIQUE,
    manual_trade_id text NOT NULL,
    account_id text NOT NULL,
    symbol text NOT NULL,
    fill_kind text NOT NULL CHECK (fill_kind IN ('EXECUTION', 'CORRECTION')),
    correction_of_fill_id text UNIQUE,
    fill_json text NOT NULL CHECK (fill_json IS JSON),
    recorded_at timestamptz NOT NULL,
    idempotency_key text NOT NULL UNIQUE,
    FOREIGN KEY (manual_trade_id) REFERENCES manual_trade_records(manual_trade_id),
    FOREIGN KEY (correction_of_fill_id) REFERENCES manual_fills(fill_id)
);

CREATE INDEX manual_fills_manual_trade_id_idx ON manual_fills(manual_trade_id);

CREATE TRIGGER manual_fills_no_update
BEFORE UPDATE ON manual_fills
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER manual_fills_no_delete
BEFORE DELETE ON manual_fills
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
