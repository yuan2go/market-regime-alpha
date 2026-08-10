CREATE TABLE strategy_shadow_portfolio (
    portfolio_id text PRIMARY KEY,
    portfolio_hash text NOT NULL UNIQUE CHECK (
        portfolio_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    policy_id text NOT NULL UNIQUE,
    policy_hash text NOT NULL CHECK (
        policy_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    research_artifact_id text NOT NULL,
    candidate_artifact_id text NOT NULL,
    initial_cash numeric NOT NULL CHECK (initial_cash > 0),
    policy_json jsonb NOT NULL CHECK (
        jsonb_typeof(policy_json) = 'object'
        AND policy_json->>'schema_version' = 'shadow-portfolio-policy/v1'
    ),
    portfolio_json jsonb NOT NULL CHECK (
        jsonb_typeof(portfolio_json) = 'object'
        AND portfolio_json->>'schema_version' = 'shadow-portfolio/v1'
    ),
    real_order_authority boolean NOT NULL DEFAULT false CHECK (NOT real_order_authority),
    real_fill_authority boolean NOT NULL DEFAULT false CHECK (NOT real_fill_authority),
    real_position_authority boolean NOT NULL DEFAULT false CHECK (NOT real_position_authority),
    created_at timestamptz NOT NULL
);

CREATE INDEX strategy_shadow_portfolio_research_idx
ON strategy_shadow_portfolio(research_artifact_id, portfolio_id);

CREATE TABLE strategy_shadow_portfolio_day (
    state_id text PRIMARY KEY,
    state_hash text NOT NULL UNIQUE CHECK (
        state_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    portfolio_id text NOT NULL REFERENCES strategy_shadow_portfolio(portfolio_id) ON DELETE RESTRICT,
    previous_state_id text REFERENCES strategy_shadow_portfolio_day(state_id) ON DELETE RESTRICT,
    sequence integer NOT NULL CHECK (sequence > 0),
    trading_date date NOT NULL,
    cash numeric NOT NULL CHECK (cash >= 0),
    nav numeric NOT NULL CHECK (nav >= 0),
    gross_exposure numeric NOT NULL CHECK (gross_exposure >= 0),
    turnover numeric NOT NULL CHECK (turnover >= 0),
    drawdown numeric NOT NULL CHECK (drawdown <= 0),
    total_cost numeric NOT NULL CHECK (total_cost >= 0),
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' = 'shadow-portfolio-day-state/v1'
    ),
    real_trading_mutation boolean NOT NULL DEFAULT false CHECK (NOT real_trading_mutation),
    recorded_at timestamptz NOT NULL,
    UNIQUE (portfolio_id, sequence),
    UNIQUE (portfolio_id, trading_date),
    CHECK (
        (sequence = 1 AND previous_state_id IS NULL)
        OR (sequence > 1 AND previous_state_id IS NOT NULL)
    )
);

CREATE INDEX strategy_shadow_portfolio_day_previous_idx
ON strategy_shadow_portfolio_day(previous_state_id);

CREATE TRIGGER strategy_shadow_portfolio_no_update
BEFORE UPDATE OR DELETE ON strategy_shadow_portfolio
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER strategy_shadow_portfolio_day_no_update
BEFORE UPDATE OR DELETE ON strategy_shadow_portfolio_day
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

ALTER TABLE research_validation_artifact
DROP CONSTRAINT research_validation_artifact_artifact_kind_check;

ALTER TABLE research_validation_artifact
ADD CONSTRAINT research_validation_artifact_artifact_kind_check
CHECK (artifact_kind IN (
    'PANEL_ENRICHMENT', 'FACTOR_ABLATION', 'LIQUIDITY_CAPACITY',
    'FREE_HISTORICAL_DECISION',
    'FREE_HISTORICAL_MULTI_HORIZON_OUTCOME',
    'HISTORICAL_SAMPLE_DATASET', 'CALIBRATION_PROTOCOL',
    'CALIBRATION_FIT', 'CALIBRATION_EVALUATION', 'CALIBRATION_ARTIFACT',
    'FORMAL_EVALUATION_PROTOCOL', 'FORMAL_EVALUATION_RESULT',
    'ENTRY_RESEARCH_MODEL', 'ENTRY_RESEARCH_ASSESSMENT',
    'ENTRY_EVALUATION', 'ENTRY_QUALIFICATION_PROTOCOL',
    'ENTRY_QUALIFICATION_EVIDENCE', 'PRODUCTION_ADMISSION',
    'HOLDING_EXIT_PROTOCOL', 'HOLDING_EXIT_EVIDENCE',
    'STRATEGY_SHADOW_PROTOCOL', 'STRATEGY_SHADOW_EVIDENCE',
    'FACTOR_RESEARCH_CATALOG', 'FACTOR_DEDUPLICATION_REPORT',
    'PORTFOLIO_SHADOW_MARKET_OBSERVATION'
));

COMMENT ON CONSTRAINT research_validation_artifact_artifact_kind_check
ON research_validation_artifact IS
'Migration 049 adds immutable factor-research and Portfolio Shadow market-observation engineering evidence only; Migration 046 qualification and Production constraints remain authoritative.';
