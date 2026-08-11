CREATE TABLE formal_research_protocol (
    protocol_id text PRIMARY KEY,
    protocol_hash text NOT NULL UNIQUE CHECK (
        protocol_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    protocol_version text NOT NULL,
    outcome_target_protocol_id text NOT NULL
        REFERENCES outcome_target_protocol(protocol_id) ON DELETE RESTRICT,
    evaluation_protocol_id text NOT NULL,
    trading_calendar_id text NOT NULL,
    trading_calendar_hash text NOT NULL CHECK (
        trading_calendar_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' = 'formal-research-protocol/v1'
    ),
    locked_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL
);

CREATE INDEX formal_research_protocol_target_idx
ON formal_research_protocol(outcome_target_protocol_id);

CREATE TABLE formal_research_protocol_component (
    protocol_id text NOT NULL
        REFERENCES formal_research_protocol(protocol_id) ON DELETE RESTRICT,
    component_role text NOT NULL CHECK (component_role IN (
        'trading_calendar_reference',
        'universe_reference', 'dataset_reference',
        'historical_sample_dataset_reference', 'feature_reference',
        'factor_reference', 'model_reference',
        'threshold_policy_reference',
        'formal_oos_qualification_policy_reference',
        'cost_policy_reference', 'calibration_policy_reference',
        'strategy_policy_reference',
        'entry_holding_exit_qualification_policy_reference'
    )),
    artifact_kind text NOT NULL,
    artifact_id text NOT NULL,
    artifact_hash text NOT NULL CHECK (
        artifact_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    payload_json jsonb NOT NULL CHECK (jsonb_typeof(payload_json) = 'object'),
    PRIMARY KEY (protocol_id, component_role)
);

CREATE INDEX formal_research_protocol_component_artifact_idx
ON formal_research_protocol_component(artifact_id, artifact_hash);

CREATE TABLE outcome_target_bound_forecast (
    forecast_id text PRIMARY KEY,
    forecast_hash text NOT NULL UNIQUE CHECK (
        forecast_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    target_protocol_id text NOT NULL
        REFERENCES outcome_target_protocol(protocol_id) ON DELETE RESTRICT,
    symbol text NOT NULL,
    decision_time timestamptz NOT NULL,
    model_id text NOT NULL,
    calibrated boolean NOT NULL DEFAULT false CHECK (NOT calibrated),
    production_authorized boolean NOT NULL DEFAULT false CHECK (
        NOT production_authorized
    ),
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' =
            'outcome-target-bound-multi-target-forecast/v1'
    ),
    created_at timestamptz NOT NULL
);

CREATE INDEX outcome_target_bound_forecast_lookup_idx
ON outcome_target_bound_forecast(target_protocol_id, symbol, decision_time);

CREATE TABLE outcome_target_bound_forecast_estimate (
    forecast_id text NOT NULL
        REFERENCES outcome_target_bound_forecast(forecast_id) ON DELETE RESTRICT,
    target_protocol_id text NOT NULL,
    target_id text NOT NULL,
    target_hash text NOT NULL CHECK (target_hash ~ '^sha256:[0-9a-f]{64}$'),
    status text NOT NULL CHECK (
        status IN ('AVAILABLE_FOR_RESEARCH', 'NOT_ESTIMABLE')
    ),
    payload_json jsonb NOT NULL CHECK (jsonb_typeof(payload_json) = 'object'),
    PRIMARY KEY (forecast_id, target_id),
    FOREIGN KEY (target_protocol_id, target_id)
        REFERENCES outcome_target_definition(protocol_id, target_id)
        ON DELETE RESTRICT
);

CREATE INDEX outcome_target_bound_forecast_estimate_target_idx
ON outcome_target_bound_forecast_estimate(target_protocol_id, target_id);

CREATE TABLE provider_fact_qualification_policy (
    policy_id text PRIMARY KEY,
    policy_hash text NOT NULL UNIQUE CHECK (
        policy_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    policy_json jsonb NOT NULL CHECK (
        jsonb_typeof(policy_json) = 'object'
        AND policy_json->>'schema_version' =
            'pit-provider-qualification-policy-v2'
        AND policy_json->>'scope' = 'PROVIDER_X_CONTRACT_X_FACT_KIND'
        AND (policy_json->>'silent_fallback')::boolean = false
    ),
    created_at timestamptz NOT NULL
);

CREATE TABLE provider_fact_qualification_decision (
    decision_id text PRIMARY KEY,
    decision_hash text NOT NULL UNIQUE CHECK (
        decision_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    policy_id text NOT NULL
        REFERENCES provider_fact_qualification_policy(policy_id)
        ON DELETE RESTRICT,
    provider_id text NOT NULL,
    provider_contract text NOT NULL,
    fact_kind text NOT NULL CHECK (fact_kind IN (
        'MARKET_DATA', 'TRADING_CALENDAR', 'UNIVERSE_MEMBERSHIP',
        'TRADING_STATUS', 'ST_STATUS', 'LISTING_STATUS',
        'TRADING_ELIGIBILITY', 'ADJUSTMENT_FACTOR',
        'FEATURE_MATERIALIZATION', 'FUNDAMENTAL', 'INDEX_MEMBERSHIP',
        'INDUSTRY_MEMBERSHIP', 'THEME_MEMBERSHIP', 'ETF_MEMBERSHIP'
    )),
    status text NOT NULL CHECK (status IN (
        'QUALIFIED', 'INCOMPLETE', 'REJECTED', 'SUSPENDED', 'REVOKED'
    )),
    revision integer NOT NULL CHECK (revision > 0),
    supersedes_decision_id text
        REFERENCES provider_fact_qualification_decision(decision_id)
        ON DELETE RESTRICT,
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' =
            'provider-fact-qualification-decision/v1'
    ),
    evaluated_at timestamptz NOT NULL,
    UNIQUE (provider_id, provider_contract, fact_kind, revision),
    CHECK ((revision = 1) = (supersedes_decision_id IS NULL))
);

CREATE UNIQUE INDEX provider_fact_qualification_one_superseder_idx
ON provider_fact_qualification_decision(supersedes_decision_id)
WHERE supersedes_decision_id IS NOT NULL;

CREATE INDEX provider_fact_qualification_scope_idx
ON provider_fact_qualification_decision(
    provider_id, provider_contract, fact_kind, revision DESC
);

CREATE INDEX provider_fact_qualification_policy_idx
ON provider_fact_qualification_decision(policy_id);

CREATE TABLE provider_fact_qualification_command (
    idempotency_key text PRIMARY KEY,
    command_hash text NOT NULL CHECK (
        command_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    decision_id text NOT NULL
        REFERENCES provider_fact_qualification_decision(decision_id)
        ON DELETE RESTRICT,
    created_at timestamptz NOT NULL
);

CREATE INDEX provider_fact_qualification_command_decision_idx
ON provider_fact_qualification_command(decision_id);

CREATE TRIGGER formal_research_protocol_no_update
BEFORE UPDATE OR DELETE ON formal_research_protocol
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER formal_research_protocol_component_no_update
BEFORE UPDATE OR DELETE ON formal_research_protocol_component
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER outcome_target_bound_forecast_no_update
BEFORE UPDATE OR DELETE ON outcome_target_bound_forecast
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER outcome_target_bound_forecast_estimate_no_update
BEFORE UPDATE OR DELETE ON outcome_target_bound_forecast_estimate
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER provider_fact_qualification_policy_no_update
BEFORE UPDATE OR DELETE ON provider_fact_qualification_policy
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER provider_fact_qualification_decision_no_update
BEFORE UPDATE OR DELETE ON provider_fact_qualification_decision
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER provider_fact_qualification_command_no_update
BEFORE UPDATE OR DELETE ON provider_fact_qualification_command
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
