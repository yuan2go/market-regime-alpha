-- Phase D correctness closure: forward-only exact lineage relationships.
-- Existing rows remain LEGACY_UNBOUND and readable; no lineage is inferred.

ALTER TABLE entry_holding_exit_qualification_policy
    DROP CONSTRAINT IF EXISTS
        entry_holding_exit_qualification_polic_portfolio_policy_id_fkey;

ALTER TABLE entry_holding_exit_qualification_policy
    ADD COLUMN portfolio_policy_hash text,
    ADD CONSTRAINT entry_holding_exit_portfolio_policy_hash_check CHECK (
        portfolio_policy_hash IS NULL
        OR
        portfolio_policy_hash ~ '^sha256:[0-9a-f]{64}$'
    );

CREATE FUNCTION require_exact_shadow_portfolio_policy_owner() RETURNS trigger AS $$
BEGIN
    IF NEW.portfolio_policy_hash IS NULL OR NOT EXISTS (
        SELECT 1 FROM strategy_shadow_portfolio AS portfolio
        WHERE portfolio.policy_id = NEW.portfolio_policy_id
          AND portfolio.policy_hash = NEW.portfolio_policy_hash
    ) THEN
        RAISE EXCEPTION 'Entry/Holding/Exit Portfolio Policy owner mismatch';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER entry_holding_exit_portfolio_policy_owner_guard
BEFORE INSERT ON entry_holding_exit_qualification_policy
FOR EACH ROW EXECUTE FUNCTION require_exact_shadow_portfolio_policy_owner();

ALTER TABLE strategy_shadow_portfolio
    DROP CONSTRAINT IF EXISTS strategy_shadow_portfolio_policy_id_key;

ALTER TABLE strategy_shadow_portfolio
    DROP CONSTRAINT IF EXISTS strategy_shadow_portfolio_portfolio_json_check,
    ADD CONSTRAINT strategy_shadow_portfolio_payload_schema_check CHECK (
        jsonb_typeof(portfolio_json) = 'object'
        AND portfolio_json->>'schema_version' IN (
            'shadow-portfolio/v1', 'shadow-portfolio/v2'
        )
    );

ALTER TABLE historical_research_session
    DROP CONSTRAINT IF EXISTS historical_research_session_session_json_check,
    ADD CONSTRAINT historical_research_session_payload_schema_check CHECK (
        jsonb_typeof(session_json) = 'object'
        AND session_json->>'schema_version' IN (
            'research-decision-session/v1',
            'research-decision-session/v2'
        )
    );

ALTER TABLE strategy_shadow_session
    ADD COLUMN lineage_status text NOT NULL DEFAULT 'LEGACY_UNBOUND' CHECK (
        lineage_status IN ('LEGACY_UNBOUND', 'EXACT_V1')
    );

CREATE OR REPLACE FUNCTION guard_strategy_shadow_session_update() RETURNS trigger AS $$
BEGIN
    IF NEW.session_id <> OLD.session_id
       OR NEW.trading_date <> OLD.trading_date
       OR NEW.scheduled_for <> OLD.scheduled_for
       OR NEW.research_shadow_id <> OLD.research_shadow_id
       OR NEW.runtime_run_id <> OLD.runtime_run_id
       OR NEW.runtime_tick_id <> OLD.runtime_tick_id
       OR NEW.policy_id <> OLD.policy_id
       OR NEW.lineage_status <> OLD.lineage_status
       OR NEW.created_at <> OLD.created_at
       OR NEW.revision <> OLD.revision + 1
       OR NEW.updated_at < OLD.updated_at THEN
        RAISE EXCEPTION 'Strategy Shadow session identity/CAS violation';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

ALTER TABLE strategy_shadow_portfolio
    ADD COLUMN research_artifact_hash text CHECK (
        research_artifact_hash IS NULL
        OR research_artifact_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    ADD COLUMN candidate_artifact_hash text CHECK (
        candidate_artifact_hash IS NULL
        OR candidate_artifact_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    ADD COLUMN strategy_session_id text REFERENCES strategy_shadow_session(session_id)
        ON DELETE RESTRICT,
    ADD COLUMN strategy_session_hash text CHECK (
        strategy_session_hash IS NULL
        OR strategy_session_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    ADD COLUMN lineage_status text NOT NULL DEFAULT 'LEGACY_UNBOUND' CHECK (
        lineage_status IN ('LEGACY_UNBOUND', 'EXACT_V1')
    ),
    ADD CONSTRAINT strategy_shadow_portfolio_exact_lineage_check CHECK (
        lineage_status = 'LEGACY_UNBOUND'
        OR (
            research_artifact_hash IS NOT NULL
            AND candidate_artifact_hash IS NOT NULL
            AND strategy_session_id IS NOT NULL
            AND strategy_session_hash IS NOT NULL
        )
    );

CREATE UNIQUE INDEX strategy_shadow_portfolio_exact_owner_key
ON strategy_shadow_portfolio(
    policy_id, policy_hash,
    research_artifact_id, research_artifact_hash,
    candidate_artifact_id, candidate_artifact_hash,
    strategy_session_id, strategy_session_hash,
    initial_cash
)
WHERE lineage_status = 'EXACT_V1';

CREATE INDEX strategy_shadow_portfolio_strategy_idx
ON strategy_shadow_portfolio(strategy_session_id, strategy_session_hash, portfolio_id);

CREATE TABLE strategy_shadow_session_lineage_binding (
    session_id text NOT NULL REFERENCES strategy_shadow_session(session_id)
        ON DELETE RESTRICT,
    ordinal integer NOT NULL CHECK (ordinal > 0),
    artifact_kind text NOT NULL CHECK (btrim(artifact_kind) <> ''),
    artifact_id text NOT NULL CHECK (btrim(artifact_id) <> ''),
    content_hash text NOT NULL CHECK (content_hash ~ '^sha256:[0-9a-f]{64}$'),
    PRIMARY KEY (session_id, ordinal),
    UNIQUE (session_id, artifact_kind, artifact_id, content_hash)
);

CREATE INDEX strategy_shadow_session_lineage_owner_idx
ON strategy_shadow_session_lineage_binding(
    artifact_kind, artifact_id, content_hash, session_id
);

CREATE TABLE strategy_shadow_portfolio_state_source_binding (
    state_id text NOT NULL REFERENCES strategy_shadow_portfolio_day(state_id)
        ON DELETE RESTRICT,
    ordinal integer NOT NULL CHECK (ordinal > 0),
    artifact_kind text NOT NULL CHECK (btrim(artifact_kind) <> ''),
    artifact_id text NOT NULL CHECK (btrim(artifact_id) <> ''),
    content_hash text NOT NULL CHECK (content_hash ~ '^sha256:[0-9a-f]{64}$'),
    PRIMARY KEY (state_id, ordinal),
    UNIQUE (state_id, artifact_kind, artifact_id, content_hash)
);

CREATE INDEX strategy_shadow_portfolio_state_source_owner_idx
ON strategy_shadow_portfolio_state_source_binding(
    artifact_kind, artifact_id, content_hash, state_id
);

CREATE TRIGGER strategy_shadow_session_lineage_binding_no_update
BEFORE UPDATE OR DELETE ON strategy_shadow_session_lineage_binding
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER strategy_shadow_portfolio_state_source_binding_no_update
BEFORE UPDATE OR DELETE ON strategy_shadow_portfolio_state_source_binding
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

COMMENT ON COLUMN strategy_shadow_portfolio.lineage_status IS
'Rows predating migration 067 remain LEGACY_UNBOUND; only EXACT_V1 rows are eligible for exact Historical lineage traversal.';

COMMENT ON COLUMN strategy_shadow_session.lineage_status IS
'Rows predating migration 067 remain LEGACY_UNBOUND; new typed-lineage sessions are EXACT_V1.';
