-- Bind Phase E3 command/methodology identity and exact Historical fact projections.

ALTER TABLE historical_research_run
DROP CONSTRAINT historical_research_run_command_json_check;

ALTER TABLE historical_research_run
ADD CONSTRAINT historical_research_run_command_json_check CHECK (
    jsonb_typeof(command_json) = 'object'
    AND (
        (
            command_json->>'schema_version' = 'historical-research-command/v1'
            AND runtime_contract_version = 'PRE_E3_IMMUTABLE_RECEIPTS_V1'
            AND NOT (command_json ? 'runtime_contract_version')
        )
        OR (
            command_json->>'schema_version' = 'historical-research-command/v2'
            AND runtime_contract_version = 'E3_LONGITUDINAL_V1'
            AND command_json->>'runtime_contract_version'
                = runtime_contract_version
        )
    )
);

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
    'PATH_CALIBRATION_HYPOTHESIS',
    'FORMAL_EVALUATION_PROTOCOL', 'FORMAL_EVALUATION_RESULT',
    'FORMAL_HYPOTHESIS_FAMILY_EVALUATION_RESULT',
    'ENTRY_RESEARCH_MODEL', 'ENTRY_RESEARCH_ASSESSMENT',
    'ENTRY_EVALUATION', 'ENTRY_QUALIFICATION_PROTOCOL',
    'ENTRY_QUALIFICATION_EVIDENCE', 'PRODUCTION_ADMISSION',
    'HOLDING_EXIT_PROTOCOL', 'HOLDING_EXIT_EVIDENCE',
    'STRATEGY_SHADOW_PROTOCOL', 'STRATEGY_SHADOW_EVIDENCE',
    'FACTOR_RESEARCH_CATALOG', 'FACTOR_DEDUPLICATION_REPORT',
    'PORTFOLIO_SHADOW_MARKET_OBSERVATION',
    'FEATURE_DEFINITION_SET', 'THRESHOLD_POLICY',
    'HISTORICAL_CONTEXT_INSTRUMENT_SET',
    'RESEARCH_EXPERIMENT_DEFINITION',
    'HISTORICAL_STRATEGY_ECONOMICS_POLICY_SET'
));

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM free_data_historical_security_fact_set AS owner
        WHERE owner.payload_json->'facts' IS DISTINCT FROM COALESCE(
            (
                SELECT jsonb_agg(
                    child.payload_json
                    ORDER BY child.symbol, child.effective_date,
                             child.fact_kind,
                             child.published_date NULLS FIRST,
                             child.fact_id
                )
                FROM free_data_historical_security_fact AS child
                WHERE child.owner_id = owner.owner_id
                  AND child.owner_hash = owner.owner_hash
            ),
            '[]'::jsonb
        )
    ) OR EXISTS (
        SELECT 1
        FROM free_data_historical_security_fact AS child
        WHERE child.fact_id <> child.payload_json->>'fact_id'
           OR child.fact_hash <> child.payload_json->>'fact_hash'
           OR child.symbol <> child.payload_json->>'symbol'
           OR child.fact_kind <> child.payload_json->>'fact_kind'
           OR child.effective_date
                <> (child.payload_json->>'effective_date')::date
           OR child.published_date IS DISTINCT FROM
                CASE
                    WHEN child.payload_json->>'published_date' IS NULL THEN NULL
                    ELSE (child.payload_json->>'published_date')::date
                END
    ) THEN
        RAISE EXCEPTION
            'existing Historical security fact projection is not an exact owner member';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM free_data_historical_security_fact_set AS owner
        WHERE owner.payload_json->'coverage_gaps' IS DISTINCT FROM COALESCE(
            (
                SELECT jsonb_agg(
                    child.payload_json
                    ORDER BY child.symbol, child.coverage_start,
                             child.coverage_end, child.fact_kind,
                             child.gap_id
                )
                FROM free_data_historical_security_fact_coverage_gap AS child
                WHERE child.owner_id = owner.owner_id
                  AND child.owner_hash = owner.owner_hash
            ),
            '[]'::jsonb
        )
    ) THEN
        RAISE EXCEPTION
            'existing Historical fact gap projection is not an exact owner member';
    END IF;
END;
$$;

ALTER TABLE free_data_historical_security_fact
ADD CONSTRAINT free_data_historical_security_fact_published_date_projection_check
CHECK (
    published_date IS NOT DISTINCT FROM
    CASE
        WHEN payload_json->>'published_date' IS NULL THEN NULL
        ELSE (payload_json->>'published_date')::date
    END
);

CREATE OR REPLACE FUNCTION guard_historical_security_fact_membership()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    owner_payload jsonb;
BEGIN
    SELECT payload_json INTO owner_payload
    FROM free_data_historical_security_fact_set
    WHERE owner_id = NEW.owner_id AND owner_hash = NEW.owner_hash;

    IF owner_payload IS NULL
       OR NOT EXISTS (
           SELECT 1
           FROM jsonb_array_elements(owner_payload->'facts') AS member
           WHERE member = NEW.payload_json
       ) THEN
        RAISE EXCEPTION 'historical security fact is not an exact member of its owner';
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION guard_historical_security_fact_gap_membership()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    owner_payload jsonb;
BEGIN
    SELECT payload_json INTO owner_payload
    FROM free_data_historical_security_fact_set
    WHERE owner_id = NEW.owner_id AND owner_hash = NEW.owner_hash;

    IF owner_payload IS NULL
       OR NOT EXISTS (
           SELECT 1
           FROM jsonb_array_elements(owner_payload->'coverage_gaps') AS member
           WHERE member = NEW.payload_json
       ) THEN
        RAISE EXCEPTION
            'historical security fact gap is not an exact member of its owner';
    END IF;
    RETURN NEW;
END;
$$;

COMMENT ON CONSTRAINT historical_research_run_command_json_check
ON historical_research_run IS
'Migration 083 binds the Runtime contract to immutable v1/v2 command identity.';

COMMENT ON CONSTRAINT free_data_historical_security_fact_published_date_projection_check
ON free_data_historical_security_fact IS
'Migration 083 prevents publication-time drift between the immutable fact payload and temporal SQL projection.';
