CREATE TABLE decision_commands (
    idempotency_key text PRIMARY KEY,
    command_hash text NOT NULL,
    opportunity_id text,
    opportunity_version bigint,
    thesis_id text,
    thesis_version bigint,
    created_at timestamptz NOT NULL,
    CHECK (opportunity_version IS NULL OR opportunity_version >= 0),
    CHECK (thesis_version IS NULL OR thesis_version >= 0)
);

CREATE TABLE trading_opportunities (
    opportunity_id text PRIMARY KEY,
    symbol text NOT NULL,
    state text NOT NULL CHECK (
        state IN ('OPEN', 'CONFIRMED_TO_THESIS', 'REJECTED', 'EXPIRED')
    ),
    valid_until timestamptz NOT NULL,
    aggregate_json text NOT NULL CHECK (aggregate_json IS JSON),
    version bigint NOT NULL CHECK (version >= 0)
);

CREATE TABLE opportunity_events (
    opportunity_id text NOT NULL,
    sequence bigint NOT NULL CHECK (sequence >= 0),
    event_type text NOT NULL,
    actor text NOT NULL,
    reason text NOT NULL,
    aggregate_json text NOT NULL CHECK (aggregate_json IS JSON),
    idempotency_key text NOT NULL UNIQUE,
    created_at timestamptz NOT NULL,
    PRIMARY KEY (opportunity_id, sequence),
    FOREIGN KEY (opportunity_id) REFERENCES trading_opportunities(opportunity_id)
);

CREATE INDEX opportunity_events_opportunity_id_idx
ON opportunity_events(opportunity_id);

CREATE TABLE trading_theses (
    thesis_id text PRIMARY KEY,
    opportunity_id text NOT NULL UNIQUE,
    symbol text NOT NULL,
    state text NOT NULL CHECK (state IN ('APPROVED', 'INVALIDATED', 'CLOSED')),
    time_invalidation timestamptz NOT NULL,
    aggregate_json text NOT NULL CHECK (aggregate_json IS JSON),
    version bigint NOT NULL CHECK (version >= 0),
    FOREIGN KEY (opportunity_id) REFERENCES trading_opportunities(opportunity_id)
);

CREATE TABLE thesis_events (
    thesis_id text NOT NULL,
    sequence bigint NOT NULL CHECK (sequence >= 0),
    event_type text NOT NULL,
    actor text NOT NULL,
    reason text NOT NULL,
    aggregate_json text NOT NULL CHECK (aggregate_json IS JSON),
    idempotency_key text NOT NULL UNIQUE,
    created_at timestamptz NOT NULL,
    PRIMARY KEY (thesis_id, sequence),
    FOREIGN KEY (thesis_id) REFERENCES trading_theses(thesis_id)
);

CREATE INDEX thesis_events_thesis_id_idx ON thesis_events(thesis_id);
