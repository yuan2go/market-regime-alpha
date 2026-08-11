CREATE TABLE shadow_performance_policy (
    policy_id text PRIMARY KEY,
    policy_hash text NOT NULL UNIQUE CHECK (
        policy_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    policy_version text NOT NULL CHECK (btrim(policy_version) <> ''),
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' = 'shadow-performance-policy/v1'
    ),
    created_at timestamptz NOT NULL
);

CREATE TABLE shadow_performance_report (
    report_id text PRIMARY KEY,
    report_hash text NOT NULL UNIQUE CHECK (
        report_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    portfolio_id text NOT NULL
        REFERENCES strategy_shadow_portfolio(portfolio_id) ON DELETE RESTRICT,
    portfolio_hash text NOT NULL CHECK (
        portfolio_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    policy_id text NOT NULL
        REFERENCES shadow_performance_policy(policy_id) ON DELETE RESTRICT,
    policy_hash text NOT NULL CHECK (
        policy_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    start_date date NOT NULL,
    end_date date NOT NULL CHECK (end_date >= start_date),
    generated_at timestamptz NOT NULL,
    reconciliation_difference numeric NOT NULL,
    negative_results_preserved boolean NOT NULL CHECK (negative_results_preserved),
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' = 'shadow-portfolio-performance/v1'
    ),
    created_at timestamptz NOT NULL,
    UNIQUE (portfolio_id, start_date, end_date, policy_id)
);

CREATE INDEX shadow_performance_report_portfolio_idx
ON shadow_performance_report(portfolio_id, start_date, end_date, policy_id);

CREATE INDEX shadow_performance_report_policy_idx
ON shadow_performance_report(policy_id);

CREATE TABLE shadow_performance_state_binding (
    report_id text NOT NULL
        REFERENCES shadow_performance_report(report_id) ON DELETE RESTRICT,
    ordinal integer NOT NULL CHECK (ordinal > 0),
    state_id text NOT NULL
        REFERENCES strategy_shadow_portfolio_day(state_id) ON DELETE RESTRICT,
    state_hash text NOT NULL CHECK (state_hash ~ '^sha256:[0-9a-f]{64}$'),
    PRIMARY KEY (report_id, ordinal),
    UNIQUE (report_id, state_id)
);

CREATE INDEX shadow_performance_state_owner_idx
ON shadow_performance_state_binding(state_id);

CREATE TABLE shadow_performance_metric (
    report_id text NOT NULL
        REFERENCES shadow_performance_report(report_id) ON DELETE RESTRICT,
    metric_name text NOT NULL CHECK (btrim(metric_name) <> ''),
    estimation_status text NOT NULL CHECK (
        estimation_status IN ('ESTIMATED', 'NOT_ESTIMABLE')
    ),
    metric_value numeric,
    payload_json jsonb NOT NULL CHECK (jsonb_typeof(payload_json) = 'object'),
    PRIMARY KEY (report_id, metric_name),
    CHECK (
        (estimation_status = 'ESTIMATED' AND metric_value IS NOT NULL)
        OR (estimation_status = 'NOT_ESTIMABLE' AND metric_value IS NULL)
    )
);

CREATE TABLE shadow_performance_period_return (
    report_id text NOT NULL
        REFERENCES shadow_performance_report(report_id) ON DELETE RESTRICT,
    period_kind text NOT NULL CHECK (period_kind IN ('MONTHLY', 'YEARLY')),
    period_key text NOT NULL CHECK (btrim(period_key) <> ''),
    return_value numeric NOT NULL,
    payload_json jsonb NOT NULL CHECK (jsonb_typeof(payload_json) = 'object'),
    PRIMARY KEY (report_id, period_kind, period_key)
);

CREATE TABLE shadow_performance_attribution (
    report_id text NOT NULL
        REFERENCES shadow_performance_report(report_id) ON DELETE RESTRICT,
    dimension text NOT NULL CHECK (btrim(dimension) <> ''),
    attribution_key text NOT NULL CHECK (btrim(attribution_key) <> ''),
    estimation_status text NOT NULL CHECK (
        estimation_status IN ('ESTIMATED', 'NOT_ESTIMABLE')
    ),
    contribution numeric,
    payload_json jsonb NOT NULL CHECK (jsonb_typeof(payload_json) = 'object'),
    PRIMARY KEY (report_id, dimension, attribution_key),
    CHECK (
        (estimation_status = 'ESTIMATED' AND contribution IS NOT NULL)
        OR (estimation_status = 'NOT_ESTIMABLE' AND contribution IS NULL)
    )
);

CREATE TRIGGER shadow_performance_policy_no_update
BEFORE UPDATE OR DELETE ON shadow_performance_policy
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER shadow_performance_report_no_update
BEFORE UPDATE OR DELETE ON shadow_performance_report
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER shadow_performance_state_binding_no_update
BEFORE UPDATE OR DELETE ON shadow_performance_state_binding
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER shadow_performance_metric_no_update
BEFORE UPDATE OR DELETE ON shadow_performance_metric
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER shadow_performance_period_return_no_update
BEFORE UPDATE OR DELETE ON shadow_performance_period_return
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER shadow_performance_attribution_no_update
BEFORE UPDATE OR DELETE ON shadow_performance_attribution
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
