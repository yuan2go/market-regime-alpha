-- Add the two independent pre-Strategy business facts required by Conditional
-- Prediction.  Existing account, Position, Candidate, Signal, Forecast,
-- Context, Model and Strategy owners remain authoritative; these rows bind
-- their exact references without copying those facts.

CREATE TABLE pre_strategy_risk_state (
    risk_state_id text PRIMARY KEY,
    risk_state_hash text NOT NULL UNIQUE CHECK (
        risk_state_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    account_scope text NOT NULL CHECK (btrim(account_scope) <> ''),
    candidate_id text NOT NULL,
    candidate_hash text NOT NULL CHECK (
        candidate_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    decision_time timestamptz NOT NULL,
    available_at timestamptz NOT NULL CHECK (available_at <= decision_time),
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' = 'pre-strategy-risk-state/v1'
    ),
    created_at timestamptz NOT NULL,
    UNIQUE (risk_state_id, risk_state_hash)
);

CREATE TABLE pre_strategy_risk_source_binding (
    risk_state_id text NOT NULL,
    risk_state_hash text NOT NULL,
    ordinal bigint NOT NULL CHECK (ordinal >= 1),
    reference_kind text NOT NULL CHECK (btrim(reference_kind) <> ''),
    artifact_id text NOT NULL CHECK (btrim(artifact_id) <> ''),
    content_hash text NOT NULL CHECK (
        content_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    PRIMARY KEY (risk_state_id, ordinal),
    UNIQUE (risk_state_id, reference_kind, artifact_id, content_hash),
    FOREIGN KEY (risk_state_id, risk_state_hash)
        REFERENCES pre_strategy_risk_state(risk_state_id, risk_state_hash)
        ON DELETE RESTRICT
);

CREATE INDEX pre_strategy_risk_candidate_time_idx
ON pre_strategy_risk_state(candidate_id, candidate_hash, decision_time);

CREATE TABLE strategy_opportunity (
    opportunity_id text PRIMARY KEY,
    opportunity_hash text NOT NULL UNIQUE CHECK (
        opportunity_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    strategy_version_id text NOT NULL,
    strategy_version_hash text NOT NULL,
    candidate_id text NOT NULL,
    candidate_hash text NOT NULL CHECK (
        candidate_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    risk_state_id text NOT NULL,
    risk_state_hash text NOT NULL,
    symbol text NOT NULL CHECK (btrim(symbol) <> ''),
    decision_time timestamptz NOT NULL,
    available_at timestamptz NOT NULL CHECK (available_at <= decision_time),
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' = 'strategy-opportunity/v1'
    ),
    created_at timestamptz NOT NULL,
    UNIQUE (opportunity_id, opportunity_hash),
    UNIQUE (
        strategy_version_id, strategy_version_hash,
        candidate_id, candidate_hash, symbol, decision_time
    ),
    FOREIGN KEY (strategy_version_id, strategy_version_hash)
        REFERENCES strategy_version(version_id, version_hash) ON DELETE RESTRICT,
    FOREIGN KEY (risk_state_id, risk_state_hash)
        REFERENCES pre_strategy_risk_state(risk_state_id, risk_state_hash)
        ON DELETE RESTRICT
);

CREATE TABLE strategy_opportunity_source_binding (
    opportunity_id text NOT NULL,
    opportunity_hash text NOT NULL,
    ordinal bigint NOT NULL CHECK (ordinal >= 1),
    reference_kind text NOT NULL CHECK (btrim(reference_kind) <> ''),
    artifact_id text NOT NULL CHECK (btrim(artifact_id) <> ''),
    content_hash text NOT NULL CHECK (
        content_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    PRIMARY KEY (opportunity_id, ordinal),
    UNIQUE (opportunity_id, reference_kind, artifact_id, content_hash),
    FOREIGN KEY (opportunity_id, opportunity_hash)
        REFERENCES strategy_opportunity(opportunity_id, opportunity_hash)
        ON DELETE RESTRICT
);

CREATE INDEX strategy_opportunity_candidate_time_idx
ON strategy_opportunity(candidate_id, candidate_hash, decision_time);

CREATE INDEX strategy_opportunity_version_time_idx
ON strategy_opportunity(strategy_version_id, strategy_version_hash, decision_time);

CREATE TRIGGER pre_strategy_risk_state_no_update
BEFORE UPDATE OR DELETE ON pre_strategy_risk_state
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER pre_strategy_risk_source_binding_no_update
BEFORE UPDATE OR DELETE ON pre_strategy_risk_source_binding
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER strategy_opportunity_no_update
BEFORE UPDATE OR DELETE ON strategy_opportunity
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER strategy_opportunity_source_binding_no_update
BEFORE UPDATE OR DELETE ON strategy_opportunity_source_binding
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

COMMENT ON TABLE pre_strategy_risk_state IS
'DecisionTime-safe pre-Strategy composition of existing account, Position, liquidity, constraint, limit and restriction owner facts; never post-Portfolio Complete Account Risk.';

COMMENT ON TABLE strategy_opportunity IS
'Immutable owner-resolved Candidate/Signal/Forecast/Context/PRE_STRATEGY_RISK_STATE/Model/Strategy binding consumed by shared Strategy semantics.';
