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
        'STRATEGY_SHADOW_PROTOCOL', 'STRATEGY_SHADOW_EVIDENCE'
    ));

COMMENT ON CONSTRAINT research_validation_artifact_artifact_kind_check
ON research_validation_artifact IS
'Migration 047 adds free retrospective Decision/Outcome lineage and an immutable Strategy Shadow liquidity owner kind only. Migration 046 qualification and Production constraints remain authoritative.';

ALTER TABLE strategy_shadow_artifact
    DROP CONSTRAINT strategy_shadow_artifact_artifact_kind_check;

ALTER TABLE strategy_shadow_artifact
    ADD CONSTRAINT strategy_shadow_artifact_artifact_kind_check
    CHECK (artifact_kind IN (
        'POLICY', 'LIQUIDITY_OBSERVATION', 'ENTRY', 'FILL', 'POSITION',
        'HOLDING_ASSESSMENT', 'EXIT_ASSESSMENT', 'STRATEGY_OUTCOME',
        'DAILY_REPORT'
    ));

COMMENT ON CONSTRAINT strategy_shadow_artifact_artifact_kind_check
ON strategy_shadow_artifact IS
'Free-data Strategy Shadow liquidity observations are immutable engineering evidence; they grant no Fill, Position, Order or Broker authority.';
