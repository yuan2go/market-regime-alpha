CREATE TABLE strategy_shadow_policy_authority (
    policy_id text PRIMARY KEY,
    policy_hash text NOT NULL UNIQUE CHECK (
        policy_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    policy_json jsonb NOT NULL CHECK (
        jsonb_typeof(policy_json) = 'object'
        AND policy_json->>'schema' = 'strategy-shadow-policy/v1'
    ),
    real_order_authority boolean NOT NULL DEFAULT false CHECK (
        NOT real_order_authority
    ),
    real_fill_authority boolean NOT NULL DEFAULT false CHECK (
        NOT real_fill_authority
    ),
    real_position_authority boolean NOT NULL DEFAULT false CHECK (
        NOT real_position_authority
    ),
    created_at timestamptz NOT NULL
);

-- Forward-compatible adoption of immutable Phase B session-local Policy rows.
-- They remain historical Artifacts; the new owner makes the same identity
-- reusable across future sessions without rewriting migration 044 evidence.
INSERT INTO strategy_shadow_policy_authority(
    policy_id, policy_hash, policy_json, created_at
)
SELECT artifact_id, artifact_hash, payload_json, min(created_at)
FROM strategy_shadow_artifact
WHERE artifact_kind = 'POLICY'
GROUP BY artifact_id, artifact_hash, payload_json
ON CONFLICT (policy_id) DO NOTHING;

CREATE TABLE entry_holding_exit_qualification_policy (
    policy_id text PRIMARY KEY,
    policy_hash text NOT NULL UNIQUE CHECK (
        policy_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    entry_model_id text NOT NULL
        REFERENCES research_validation_artifact(artifact_id) ON DELETE RESTRICT,
    strategy_policy_id text NOT NULL
        REFERENCES strategy_shadow_policy_authority(policy_id) ON DELETE RESTRICT,
    portfolio_policy_id text NOT NULL
        REFERENCES strategy_shadow_portfolio(policy_id) ON DELETE RESTRICT,
    policy_json jsonb NOT NULL CHECK (
        jsonb_typeof(policy_json) = 'object'
        AND policy_json->>'schema_version' =
            'entry-holding-exit-qualification-policy/v1'
        AND (policy_json->>'required_formal_oos')::boolean
        AND (policy_json->>'required_calibration')::boolean
        AND (policy_json->>'required_cost_capacity')::boolean
        AND (policy_json->>'required_independent_governance_approval')::boolean
        AND NOT (policy_json->>'canonical_entry_unlock_automatic')::boolean
    ),
    locked_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL
);

CREATE INDEX entry_holding_exit_policy_entry_model_idx
ON entry_holding_exit_qualification_policy(entry_model_id);
CREATE INDEX entry_holding_exit_policy_strategy_idx
ON entry_holding_exit_qualification_policy(strategy_policy_id);
CREATE INDEX entry_holding_exit_policy_portfolio_idx
ON entry_holding_exit_qualification_policy(portfolio_policy_id);

CREATE TABLE prospective_shadow_qualification_policy (
    policy_id text PRIMARY KEY,
    policy_hash text NOT NULL UNIQUE CHECK (
        policy_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    strategy_policy_id text NOT NULL,
    strategy_policy_hash text NOT NULL CHECK (
        strategy_policy_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    portfolio_policy_id text NOT NULL,
    portfolio_policy_hash text NOT NULL CHECK (
        portfolio_policy_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' =
            'prospective-shadow-qualification-policy/v1'
        AND (payload_json->>'replay_or_fixture_counts_as_prospective')::boolean = false
    ),
    locked_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL,
    FOREIGN KEY (strategy_policy_id)
        REFERENCES strategy_shadow_policy_authority(policy_id)
        ON DELETE RESTRICT
);

CREATE INDEX prospective_shadow_qualification_strategy_policy_idx
ON prospective_shadow_qualification_policy(strategy_policy_id);

CREATE TABLE phase_c_stage_decision (
    decision_id text PRIMARY KEY,
    decision_hash text NOT NULL UNIQUE CHECK (
        decision_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    stage text NOT NULL CHECK (stage IN (
        'ENTRY_HOLDING_EXIT_QUALIFICATION',
        'PROSPECTIVE_STRATEGY_SHADOW',
        'CONTROLLED_EXECUTION_READINESS'
    )),
    scope_id text NOT NULL,
    policy_id text,
    outcome text NOT NULL CHECK (outcome IN (
        'SATISFIED', 'REJECTED', 'NOT_ESTIMABLE',
        'BLOCKED', 'ACCUMULATING'
    )),
    qualification_established boolean NOT NULL,
    revision integer NOT NULL CHECK (revision > 0),
    supersedes_decision_id text
        REFERENCES phase_c_stage_decision(decision_id) ON DELETE RESTRICT,
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' = 'phase-c-stage-decision/v1'
        AND (payload_json->>'production_authorized')::boolean = false
        AND (payload_json->>'broker_mutation_authorized')::boolean = false
        AND (payload_json->>'automatic_promotion')::boolean = false
    ),
    evaluated_at timestamptz NOT NULL,
    UNIQUE (stage, scope_id, revision),
    CHECK (qualification_established = (outcome = 'SATISFIED')),
    CHECK ((revision = 1) = (supersedes_decision_id IS NULL))
);

CREATE UNIQUE INDEX phase_c_stage_decision_one_superseder_idx
ON phase_c_stage_decision(supersedes_decision_id)
WHERE supersedes_decision_id IS NOT NULL;

CREATE INDEX phase_c_stage_decision_scope_idx
ON phase_c_stage_decision(stage, scope_id, revision DESC);

CREATE INDEX phase_c_stage_decision_policy_idx
ON phase_c_stage_decision(policy_id);

CREATE TABLE production_admission_decision_authority (
    decision_id text PRIMARY KEY,
    decision_hash text NOT NULL UNIQUE CHECK (
        decision_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    formal_protocol_id text NOT NULL
        REFERENCES formal_research_protocol(protocol_id) ON DELETE RESTRICT,
    status text NOT NULL CHECK (status = 'BLOCKED'),
    production_authorized boolean NOT NULL DEFAULT false CHECK (
        NOT production_authorized
    ),
    revision integer NOT NULL CHECK (revision > 0),
    supersedes_decision_id text
        REFERENCES production_admission_decision_authority(decision_id)
        ON DELETE RESTRICT,
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' = 'production-admission-decision/v1'
        AND (payload_json->>'automatic_promotion')::boolean = false
    ),
    evaluated_at timestamptz NOT NULL,
    UNIQUE (formal_protocol_id, revision),
    CHECK ((revision = 1) = (supersedes_decision_id IS NULL))
);

CREATE UNIQUE INDEX production_admission_one_superseder_idx
ON production_admission_decision_authority(supersedes_decision_id)
WHERE supersedes_decision_id IS NOT NULL;

CREATE TABLE phase_c_gate_command (
    idempotency_key text PRIMARY KEY,
    command_hash text NOT NULL CHECK (
        command_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    result_kind text NOT NULL CHECK (
        result_kind IN ('PHASE_C_STAGE_DECISION', 'PRODUCTION_ADMISSION_DECISION')
    ),
    result_id text NOT NULL,
    created_at timestamptz NOT NULL
);

CREATE TRIGGER prospective_shadow_qualification_policy_no_update
BEFORE UPDATE OR DELETE ON prospective_shadow_qualification_policy
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER strategy_shadow_policy_authority_no_update
BEFORE UPDATE OR DELETE ON strategy_shadow_policy_authority
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER entry_holding_exit_qualification_policy_no_update
BEFORE UPDATE OR DELETE ON entry_holding_exit_qualification_policy
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER phase_c_stage_decision_no_update
BEFORE UPDATE OR DELETE ON phase_c_stage_decision
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER production_admission_decision_authority_no_update
BEFORE UPDATE OR DELETE ON production_admission_decision_authority
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER phase_c_gate_command_no_update
BEFORE UPDATE OR DELETE ON phase_c_gate_command
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
