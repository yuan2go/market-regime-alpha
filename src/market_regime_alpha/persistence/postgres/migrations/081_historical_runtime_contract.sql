-- Persist the executable Historical Runtime contract independently of command shape.

ALTER TABLE historical_research_run
ADD COLUMN runtime_contract_version text NOT NULL
DEFAULT 'PRE_E3_IMMUTABLE_RECEIPTS_V1';

ALTER TABLE historical_research_run
ALTER COLUMN runtime_contract_version
SET DEFAULT 'E3_LONGITUDINAL_V1';

ALTER TABLE historical_research_run
ADD CONSTRAINT historical_research_run_runtime_contract_check
CHECK (runtime_contract_version IN (
    'PRE_E3_IMMUTABLE_RECEIPTS_V1',
    'E3_LONGITUDINAL_V1'
));

CREATE OR REPLACE FUNCTION guard_historical_research_run_update()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.run_id IS DISTINCT FROM OLD.run_id
       OR NEW.command_hash IS DISTINCT FROM OLD.command_hash
       OR NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key
       OR NEW.start_date IS DISTINCT FROM OLD.start_date
       OR NEW.end_date IS DISTINCT FROM OLD.end_date
       OR NEW.trading_calendar_id IS DISTINCT FROM OLD.trading_calendar_id
       OR NEW.trading_calendar_hash IS DISTINCT FROM OLD.trading_calendar_hash
       OR NEW.runtime_scope_policy_id IS DISTINCT FROM OLD.runtime_scope_policy_id
       OR NEW.runtime_scope_policy_hash IS DISTINCT FROM OLD.runtime_scope_policy_hash
       OR NEW.target_protocol_id IS DISTINCT FROM OLD.target_protocol_id
       OR NEW.target_protocol_hash IS DISTINCT FROM OLD.target_protocol_hash
       OR NEW.experiment_definition_id IS DISTINCT FROM OLD.experiment_definition_id
       OR NEW.experiment_definition_hash IS DISTINCT FROM OLD.experiment_definition_hash
       OR NEW.data_authority_mode IS DISTINCT FROM OLD.data_authority_mode
       OR NEW.evidence_qualification IS DISTINCT FROM OLD.evidence_qualification
       OR NEW.runtime_contract_version IS DISTINCT FROM OLD.runtime_contract_version
       OR NEW.command_json IS DISTINCT FROM OLD.command_json
       OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
        RAISE EXCEPTION 'historical_research_run identity is immutable';
    END IF;
    RETURN NEW;
END;
$$;

COMMENT ON COLUMN historical_research_run.runtime_contract_version IS
'Migration 081 marks migrated Phase E2 runs as immutable receipts and new Phase E3 runs as longitudinal; command payload shape is not a compatibility authority.';
