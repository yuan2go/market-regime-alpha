-- Admit Alpha Research Phase II into existing PostgreSQL owners.  No table,
-- Runtime, scheduler, Candidate engine or Evidence authority is added.

ALTER TABLE historical_research_evidence
    DROP CONSTRAINT historical_research_evidence_evidence_kind_check,
    ADD CONSTRAINT historical_research_evidence_evidence_kind_check
    CHECK (evidence_kind IN (
        'CORPUS_SUMMARY', 'ALPHA_ABLATION', 'STRATEGY_ECONOMICS',
        'PORTFOLIO_PERFORMANCE', 'EXPLORATORY_MODEL',
        'METHODOLOGY_ASSESSMENT', 'ALPHA_CORRECTNESS',
        'EXTERNAL_VALIDATION', 'CONTEXT_CONDITIONAL', 'CANDIDATE_POLICY',
        'CONDITIONAL_PREDICTION'
    ));

ALTER TABLE strategy_contract
    DROP CONSTRAINT strategy_contract_family_check,
    ADD CONSTRAINT strategy_contract_family_check
        CHECK (family IN ('OVERNIGHT', 'SWING_STATE', 'CONDITIONAL_PREDICTION')),
    DROP CONSTRAINT strategy_contract_payload_json_check,
    ADD CONSTRAINT strategy_contract_payload_json_check CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' IN (
            'strategy-contract/v1', 'strategy-contract/v2'
        )
    );

ALTER TABLE strategy_version
    DROP CONSTRAINT strategy_version_family_check,
    ADD CONSTRAINT strategy_version_family_check
        CHECK (family IN ('OVERNIGHT', 'SWING_STATE', 'CONDITIONAL_PREDICTION'));

COMMENT ON COLUMN historical_research_evidence.evidence_kind IS
'Append-only evidence kinds for discovery, correctness, external validation, context, Candidate policy and conditional prediction; kind alone grants no qualification authority.';

COMMENT ON COLUMN strategy_contract.payload_json IS
'V2 makes Forecast required/not-required semantics explicit; Forecast-required Runtime inputs fail closed without Signal, Forecast, Context, Risk and Model lineage.';
