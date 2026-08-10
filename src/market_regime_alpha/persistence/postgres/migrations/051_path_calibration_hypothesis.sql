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
    'ENTRY_RESEARCH_MODEL', 'ENTRY_RESEARCH_ASSESSMENT',
    'ENTRY_EVALUATION', 'ENTRY_QUALIFICATION_PROTOCOL',
    'ENTRY_QUALIFICATION_EVIDENCE', 'PRODUCTION_ADMISSION',
    'HOLDING_EXIT_PROTOCOL', 'HOLDING_EXIT_EVIDENCE',
    'STRATEGY_SHADOW_PROTOCOL', 'STRATEGY_SHADOW_EVIDENCE',
    'FACTOR_RESEARCH_CATALOG', 'FACTOR_DEDUPLICATION_REPORT',
    'PORTFOLIO_SHADOW_MARKET_OBSERVATION'
));

COMMENT ON CONSTRAINT research_validation_artifact_artifact_kind_check
ON research_validation_artifact IS
'Migration 051 adds immutable positive/negative Path Calibration Hypothesis engineering evidence only; Migration 046 qualification and Production constraints remain authoritative.';
