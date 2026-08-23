-- Admit the immutable Daily Alpha prediction projection as the terminal output
-- of the existing Continuous Runtime.  No scheduler, write authority, Feature,
-- Candidate, Forecast, Strategy or Outcome engine is introduced here.

ALTER TABLE continuous_child_run
DROP CONSTRAINT continuous_child_run_child_kind_check;

ALTER TABLE continuous_child_run
ADD CONSTRAINT continuous_child_run_child_kind_check
CHECK (
    child_kind IN (
        'DAILY_DATASET',
        'FEATURE_MATERIALIZATION',
        'STATE_SYSTEM',
        'CONTROLLED_OPERATION',
        'CANONICAL_LIFECYCLE',
        'DECISION_SYSTEM',
        'STRATEGY_RUNTIME',
        'DAILY_ALPHA_SNAPSHOT'
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
    'FEATURE_DEFINITION_SET', 'FEATURE_SET_CONFIGURATION', 'THRESHOLD_POLICY',
    'HISTORICAL_CONTEXT_INSTRUMENT_SET',
    'RESEARCH_EXPERIMENT_DEFINITION',
    'HISTORICAL_STRATEGY_ECONOMICS_POLICY_SET',
    'TRADING_CALENDAR', 'FROZEN_TEMPORAL_VALIDATION_WINDOW',
    'OPERATIONAL_UNIVERSE',
    'DAILY_ALPHA_PREDICTION_SNAPSHOT'
));

COMMENT ON CONSTRAINT research_validation_artifact_artifact_kind_check
ON research_validation_artifact IS
'Migration 095 admits a content-addressed Daily Alpha prediction projection with engineering-only authority and immutable source-owner lineage.';
