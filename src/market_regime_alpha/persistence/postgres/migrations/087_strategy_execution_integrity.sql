-- Converge Strategy Proposal execution onto the existing Manual Execution and
-- allocated-Fill authorities.  No new ledger or Runtime plane is introduced.

ALTER TABLE manual_account_observation
    ADD CONSTRAINT manual_account_observation_identity_unique
    UNIQUE (observation_id, content_hash);

ALTER TABLE pit_trading_calendar_canonical_snapshot
    ADD CONSTRAINT pit_trading_calendar_identity_unique
    UNIQUE (calendar_id, calendar_hash);

ALTER TABLE manual_trade_records
    DROP CONSTRAINT manual_trade_records_authority_route_check,
    DROP CONSTRAINT manual_trade_authority_route_check,
    ADD COLUMN strategy_authorization_id text,
    ADD COLUMN strategy_authorization_hash text CHECK (
        strategy_authorization_hash IS NULL
        OR strategy_authorization_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    ADD COLUMN strategy_portfolio_decision_id text,
    ADD COLUMN strategy_portfolio_decision_hash text,
    ADD COLUMN strategy_proposal_id text,
    ADD COLUMN strategy_proposal_hash text,
    ADD COLUMN strategy_version_id text,
    ADD COLUMN strategy_version_hash text,
    ADD COLUMN strategy_account_observation_id text,
    ADD COLUMN strategy_account_observation_hash text,
    ADD COLUMN strategy_calendar_id text,
    ADD COLUMN strategy_calendar_hash text,
    ADD CONSTRAINT manual_trade_records_authority_route_check CHECK (
        authority_route IN ('INCREASING', 'REDUCING', 'STRATEGY')
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
    ADD CONSTRAINT strategy_trade_authorization_unique
        UNIQUE (strategy_authorization_id),
    ADD CONSTRAINT strategy_trade_portfolio_fk
        FOREIGN KEY (
            strategy_portfolio_decision_id,
            strategy_portfolio_decision_hash
        ) REFERENCES cross_strategy_portfolio_decision(
            decision_id, decision_hash
        ) ON DELETE RESTRICT,
    ADD CONSTRAINT strategy_trade_proposal_fk
        FOREIGN KEY (
            strategy_proposal_id, strategy_proposal_hash,
            strategy_version_id, strategy_version_hash
        ) REFERENCES strategy_proposal(
            proposal_id, proposal_hash,
            strategy_version_id, strategy_version_hash
        ) ON DELETE RESTRICT,
    ADD CONSTRAINT strategy_trade_account_observation_fk
        FOREIGN KEY (
            strategy_account_observation_id,
            strategy_account_observation_hash
        ) REFERENCES manual_account_observation(
            observation_id, content_hash
        ) ON DELETE RESTRICT,
    ADD CONSTRAINT strategy_trade_calendar_fk
        FOREIGN KEY (strategy_calendar_id, strategy_calendar_hash)
        REFERENCES pit_trading_calendar_canonical_snapshot(
            calendar_id, calendar_hash
        ) ON DELETE RESTRICT;

CREATE INDEX strategy_trade_portfolio_idx
ON manual_trade_records(
    strategy_portfolio_decision_id, strategy_portfolio_decision_hash
)
WHERE authority_route = 'STRATEGY';

CREATE INDEX strategy_trade_proposal_idx
ON manual_trade_records(
    strategy_proposal_id, strategy_proposal_hash,
    strategy_version_id, strategy_version_hash
)
WHERE authority_route = 'STRATEGY';

CREATE INDEX strategy_trade_account_idx
ON manual_trade_records(
    strategy_account_observation_id, strategy_account_observation_hash
)
WHERE authority_route = 'STRATEGY';

CREATE INDEX strategy_trade_calendar_idx
ON manual_trade_records(strategy_calendar_id, strategy_calendar_hash)
WHERE authority_route = 'STRATEGY';

-- Realized economics remain append-only.  A correction creates a revision
-- that supersedes exactly one prior result; callers query the revision head.

ALTER TABLE strategy_realized_outcome
    ADD COLUMN revision bigint NOT NULL DEFAULT 1 CHECK (revision >= 1),
    ADD COLUMN supersedes_outcome_id text,
    ADD COLUMN supersedes_outcome_hash text CHECK (
        supersedes_outcome_hash IS NULL
        OR supersedes_outcome_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    DROP CONSTRAINT strategy_realized_outcome_payload_json_check,
    ADD CONSTRAINT strategy_realized_outcome_payload_json_check CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' IN (
            'fill-derived-strategy-outcome/v1',
            'fill-derived-strategy-outcome/v2'
        )
    ),
    ADD CONSTRAINT strategy_realized_outcome_revision_lineage_check CHECK (
        (revision = 1) = (supersedes_outcome_id IS NULL)
        AND (supersedes_outcome_id IS NULL)
            = (supersedes_outcome_hash IS NULL)
    );

DO $$
DECLARE
    constraint_name text;
BEGIN
    SELECT c.conname INTO constraint_name
    FROM pg_constraint AS c
    WHERE c.conrelid = 'strategy_realized_outcome'::regclass
      AND c.contype = 'u'
      AND pg_get_constraintdef(c.oid) =
          'UNIQUE (account_id, strategy_version_id, symbol, entry_proposal_id)';
    IF constraint_name IS NULL THEN
        RAISE EXCEPTION 'legacy Strategy Outcome lifecycle constraint is missing';
    END IF;
    EXECUTE format(
        'ALTER TABLE strategy_realized_outcome DROP CONSTRAINT %I',
        constraint_name
    );
END;
$$;

ALTER TABLE strategy_realized_outcome
    ADD CONSTRAINT strategy_realized_outcome_lifecycle_revision_unique
        UNIQUE (
            account_id, strategy_version_id, symbol,
            entry_proposal_id, revision
        ),
    ADD CONSTRAINT strategy_realized_outcome_supersedes_unique
        UNIQUE (supersedes_outcome_id),
    ADD CONSTRAINT strategy_realized_outcome_supersedes_fk
        FOREIGN KEY (supersedes_outcome_id, supersedes_outcome_hash)
        REFERENCES strategy_realized_outcome(outcome_id, outcome_hash)
        ON DELETE RESTRICT;

CREATE INDEX strategy_realized_outcome_head_idx
ON strategy_realized_outcome(
    account_id, strategy_version_id, symbol,
    entry_proposal_id, revision DESC
);

CREATE INDEX strategy_realized_outcome_supersedes_fk_idx
ON strategy_realized_outcome(
    supersedes_outcome_id, supersedes_outcome_hash
);

COMMENT ON COLUMN strategy_realized_outcome.supersedes_outcome_id IS
'Exact prior immutable economic result superseded by allocated Fill correction.';
