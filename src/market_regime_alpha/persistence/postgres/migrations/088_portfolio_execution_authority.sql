-- Extend the existing ManualTrade aggregate with owner-resolved execution
-- lineage. Reservations remain reconstructible from ManualTrade state and
-- effective append-only Fills; this migration does not create another ledger.

ALTER TABLE account_reconciliation
    ADD CONSTRAINT account_reconciliation_identity_unique
    UNIQUE (reconciliation_id, content_hash);

ALTER TABLE manual_trade_records
    ADD COLUMN strategy_execution_authority_version text,
    ADD COLUMN strategy_reconciliation_id text,
    ADD COLUMN strategy_reconciliation_hash text CHECK (
        strategy_reconciliation_hash IS NULL
        OR strategy_reconciliation_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    ADD COLUMN strategy_price_owner_id text,
    ADD COLUMN strategy_price_owner_hash text CHECK (
        strategy_price_owner_hash IS NULL
        OR strategy_price_owner_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    ADD COLUMN strategy_price_source_id text,
    ADD COLUMN strategy_price_source_hash text CHECK (
        strategy_price_source_hash IS NULL
        OR strategy_price_source_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    ADD COLUMN strategy_price_observed_at timestamptz,
    ADD COLUMN strategy_price_available_at timestamptz,
    ADD COLUMN strategy_authorized_quantity bigint CHECK (
        strategy_authorized_quantity IS NULL
        OR strategy_authorized_quantity > 0
    );

UPDATE manual_trade_records
SET strategy_execution_authority_version = 'CALLER_PRICE_V1'
WHERE authority_route = 'STRATEGY';

ALTER TABLE manual_trade_records
    DROP CONSTRAINT manual_trade_authority_route_check,
    ADD CONSTRAINT strategy_execution_authority_version_check CHECK (
        (
            authority_route <> 'STRATEGY'
            AND strategy_execution_authority_version IS NULL
        )
        OR
        (
            authority_route = 'STRATEGY'
            AND strategy_execution_authority_version IN (
                'CALLER_PRICE_V1', 'OWNER_RESOLVED_V2'
            )
        )
    ),
    ADD CONSTRAINT strategy_execution_owner_projection_check CHECK (
        (
            strategy_execution_authority_version = 'CALLER_PRICE_V1'
            AND strategy_reconciliation_id IS NULL
            AND strategy_reconciliation_hash IS NULL
            AND strategy_price_owner_id IS NULL
            AND strategy_price_owner_hash IS NULL
            AND strategy_price_source_id IS NULL
            AND strategy_price_source_hash IS NULL
            AND strategy_price_observed_at IS NULL
            AND strategy_price_available_at IS NULL
            AND strategy_authorized_quantity IS NULL
        )
        OR
        (
            strategy_execution_authority_version = 'OWNER_RESOLVED_V2'
            AND strategy_reconciliation_id IS NOT NULL
            AND strategy_reconciliation_hash IS NOT NULL
            AND strategy_price_owner_id IS NOT NULL
            AND strategy_price_owner_hash IS NOT NULL
            AND strategy_price_source_id IS NOT NULL
            AND strategy_price_source_hash IS NOT NULL
            AND strategy_price_observed_at IS NOT NULL
            AND strategy_price_available_at IS NOT NULL
            AND strategy_price_available_at >= strategy_price_observed_at
            AND strategy_authorized_quantity IS NOT NULL
        )
        OR
        (
            authority_route <> 'STRATEGY'
            AND strategy_reconciliation_id IS NULL
            AND strategy_reconciliation_hash IS NULL
            AND strategy_price_owner_id IS NULL
            AND strategy_price_owner_hash IS NULL
            AND strategy_price_source_id IS NULL
            AND strategy_price_source_hash IS NULL
            AND strategy_price_observed_at IS NULL
            AND strategy_price_available_at IS NULL
            AND strategy_authorized_quantity IS NULL
        )
    ),
    ADD CONSTRAINT manual_trade_authority_route_check CHECK (
        (
            authority_route = 'INCREASING'
            AND risk_decision_id IS NOT NULL
            AND risk_reducing_decision_id IS NULL
            AND risk_reduction_confirmation_id IS NULL
            AND strategy_authorization_id IS NULL
            AND strategy_proposal_id IS NULL
        )
        OR
        (
            authority_route = 'REDUCING'
            AND risk_decision_id IS NULL
            AND risk_reducing_decision_id IS NOT NULL
            AND risk_reduction_confirmation_id IS NOT NULL
            AND strategy_authorization_id IS NULL
            AND strategy_proposal_id IS NULL
        )
        OR
        (
            authority_route = 'STRATEGY'
            AND risk_decision_id IS NULL
            AND risk_reducing_decision_id IS NULL
            AND risk_reduction_confirmation_id IS NULL
            AND strategy_authorization_id IS NOT NULL
            AND strategy_authorization_hash IS NOT NULL
            AND strategy_portfolio_decision_id IS NOT NULL
            AND strategy_portfolio_decision_hash IS NOT NULL
            AND strategy_proposal_id IS NOT NULL
            AND strategy_proposal_hash IS NOT NULL
            AND strategy_version_id IS NOT NULL
            AND strategy_version_hash IS NOT NULL
            AND strategy_account_observation_id IS NOT NULL
            AND strategy_account_observation_hash IS NOT NULL
            AND strategy_calendar_id IS NOT NULL
            AND strategy_calendar_hash IS NOT NULL
        )
    ),
    ADD CONSTRAINT strategy_trade_reconciliation_fk
        FOREIGN KEY (
            strategy_reconciliation_id,
            strategy_reconciliation_hash
        ) REFERENCES account_reconciliation(
            reconciliation_id, content_hash
        ) ON DELETE RESTRICT;

CREATE INDEX strategy_trade_active_account_budget_idx
ON manual_trade_records(account_id, symbol, strategy_version_id)
WHERE authority_route = 'STRATEGY'
  AND state IN (
      'RECORDED', 'PARTIALLY_FILLED',
      'UNKNOWN', 'RECONCILIATION_REQUIRED'
  );

CREATE INDEX strategy_trade_reconciliation_fk_idx
ON manual_trade_records(
    strategy_reconciliation_id, strategy_reconciliation_hash
)
WHERE strategy_reconciliation_id IS NOT NULL;

COMMENT ON COLUMN manual_trade_records.strategy_execution_authority_version IS
'CALLER_PRICE_V1 is immutable historical compatibility; OWNER_RESOLVED_V2 is required for new Strategy Intent creation.';

COMMENT ON COLUMN manual_trade_records.strategy_authorized_quantity IS
'Immutable Proposal quantity ceiling captured at first owner-resolved authorization; current remaining authority is reconstructed from all Proposal Intent and effective Fill facts.';
