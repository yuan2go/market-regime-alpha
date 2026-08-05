CREATE TABLE position_books (
    position_book_id text PRIMARY KEY,
    account_id text NOT NULL,
    symbol text NOT NULL,
    opportunity_id text NOT NULL,
    thesis_id text NOT NULL,
    state text NOT NULL CHECK (state IN ('OPEN', 'CLOSED')),
    version bigint NOT NULL CHECK (version >= 0),
    aggregate_json text NOT NULL CHECK (aggregate_json IS JSON),
    opened_at timestamptz NOT NULL,
    closed_at timestamptz
);

CREATE UNIQUE INDEX one_open_position_book_per_account_symbol
ON position_books(account_id, symbol)
WHERE state = 'OPEN';

CREATE TABLE position_book_events (
    position_book_id text NOT NULL,
    sequence bigint NOT NULL CHECK (sequence >= 0),
    state text NOT NULL CHECK (state IN ('OPEN', 'CLOSED')),
    aggregate_json text NOT NULL CHECK (aggregate_json IS JSON),
    idempotency_key text NOT NULL UNIQUE,
    created_at timestamptz NOT NULL,
    PRIMARY KEY (position_book_id, sequence),
    FOREIGN KEY (position_book_id) REFERENCES position_books(position_book_id)
);

CREATE INDEX position_book_events_position_book_id_idx
ON position_book_events(position_book_id);

CREATE TABLE traceable_manual_trade_bindings (
    manual_trade_id text PRIMARY KEY,
    position_book_id text NOT NULL,
    opportunity_id text NOT NULL,
    thesis_id text NOT NULL,
    portfolio_decision_id text NOT NULL,
    risk_decision_id text NOT NULL,
    post_trade_snapshot_id text NOT NULL,
    post_trade_snapshot_hash text NOT NULL,
    target_delta_hash text NOT NULL,
    created_at timestamptz NOT NULL,
    FOREIGN KEY (manual_trade_id) REFERENCES manual_trade_records(manual_trade_id),
    FOREIGN KEY (position_book_id) REFERENCES position_books(position_book_id)
);

CREATE INDEX traceable_manual_trade_bindings_position_book_idx
ON traceable_manual_trade_bindings(position_book_id);

CREATE TRIGGER traceable_manual_trade_bindings_no_update
BEFORE UPDATE ON traceable_manual_trade_bindings
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER traceable_manual_trade_bindings_no_delete
BEFORE DELETE ON traceable_manual_trade_bindings
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
