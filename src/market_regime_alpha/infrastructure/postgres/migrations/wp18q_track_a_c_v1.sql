ALTER TABLE mra.universe_revision ADD CONSTRAINT universe_revision_exact_scope_uk UNIQUE (
        universe_revision_id, universe_id, scope_content_sha256
    );

ALTER TABLE mra.candidate_policy ADD CONSTRAINT candidate_policy_identity_hash_uk UNIQUE (
        candidate_policy_id, content_sha256
    );

ALTER TABLE mra.context_policy ADD CONSTRAINT context_policy_identity_hash_uk UNIQUE (
        context_policy_id, content_sha256
    );

ALTER TABLE mra.evaluation_protocol ADD CONSTRAINT evaluation_protocol_identity_hash_uk UNIQUE (
        evaluation_protocol_id, content_sha256
    );

ALTER TABLE mra.model ADD CONSTRAINT model_identity_hash_uk UNIQUE (model_id, content_sha256);

ALTER TABLE mra.strategy_context_requirement DROP CONSTRAINT strategy_context_requirement_shape_ck, ADD CONSTRAINT strategy_context_requirement_shape_ck CHECK (
        ordinal > 0
        AND context_kind IN (
            'MARKET_REGIME', 'ETF_ROTATION', 'THEME_ROTATION', 'CAPITAL_BREADTH'
        )
        AND required_state IN ('POSITIVE', 'NEUTRAL', 'NEGATIVE')
        AND missing_action IN ('WAIT', 'UNKNOWN', 'NOT_ESTIMABLE', 'OBSERVE_ONLY')
        AND context_policy_content_sha256 ~ '^[0-9a-f]{64}$'
        AND content_sha256 ~ '^[0-9a-f]{64}$'
    );

ALTER TABLE mra.evaluation_protocol_metric DROP CONSTRAINT evaluation_protocol_metric_shape_ck, ADD CONSTRAINT evaluation_protocol_metric_shape_ck CHECK (
        ordinal > 0 AND metric_code ~ '^[a-z][a-z0-9_-]{0,99}$'
        AND source_metric_code ~ '^[a-z][a-z0-9_-]{0,99}$'
        AND source_value_type IN ('DECIMAL', 'BOOLEAN')
        AND source_kind IN ('OUTCOME_METRIC', 'FORECAST_OUTCOME_PAIR',
            'CANDIDATE_DISPOSITION', 'SIGNAL_STATUS', 'PORTFOLIO_LINE',
            'PORTFOLIO_OUTCOME', 'RISK_DECISION',
            'CANDIDATE_OUTCOME_PAIR')
        AND source_measure IN ('TARGET_VALUE', 'FORECAST_POINT_VS_TARGET',
            'CANDIDATE_SELECTED', 'SIGNAL_PRESENT', 'TARGET_WEIGHT',
            'TURNOVER', 'GROSS_PORTFOLIO_RETURN',
            'NET_PORTFOLIO_RETURN_ASSUMED_COST', 'RISK_REJECTED',
            'CANDIDATE_SCORE_VS_TARGET', 'CANDIDATE_TOP_K_RETURN',
            'CANDIDATE_HIT')
        AND ((source_kind = 'OUTCOME_METRIC' AND source_measure = 'TARGET_VALUE')
          OR (source_kind = 'FORECAST_OUTCOME_PAIR' AND source_measure = 'FORECAST_POINT_VS_TARGET')
          OR (source_kind = 'CANDIDATE_DISPOSITION' AND source_measure = 'CANDIDATE_SELECTED')
          OR (source_kind = 'SIGNAL_STATUS' AND source_measure = 'SIGNAL_PRESENT')
          OR (source_kind = 'PORTFOLIO_LINE' AND source_measure IN ('TARGET_WEIGHT', 'TURNOVER'))
          OR (source_kind = 'PORTFOLIO_OUTCOME' AND source_measure IN ('GROSS_PORTFOLIO_RETURN', 'NET_PORTFOLIO_RETURN_ASSUMED_COST'))
          OR (source_kind = 'RISK_DECISION' AND source_measure = 'RISK_REJECTED')
          OR (source_kind = 'CANDIDATE_OUTCOME_PAIR'
              AND source_measure IN ('CANDIDATE_SCORE_VS_TARGET',
                                     'CANDIDATE_TOP_K_RETURN',
                                     'CANDIDATE_HIT')))
        AND (source_kind = 'OUTCOME_METRIC'
          OR (source_kind IN ('FORECAST_OUTCOME_PAIR', 'PORTFOLIO_LINE',
                              'PORTFOLIO_OUTCOME')
              AND source_value_type = 'DECIMAL')
          OR (source_kind IN ('CANDIDATE_DISPOSITION', 'SIGNAL_STATUS',
                              'RISK_DECISION')
              AND source_value_type = 'BOOLEAN')
          OR (source_kind = 'CANDIDATE_OUTCOME_PAIR'
              AND ((source_measure IN ('CANDIDATE_SCORE_VS_TARGET',
                                       'CANDIDATE_TOP_K_RETURN')
                    AND source_value_type = 'DECIMAL')
                OR (source_measure = 'CANDIDATE_HIT'
                    AND source_value_type = 'BOOLEAN'))))
        AND reducer IN ('MEAN_DECIMAL', 'MEDIAN_DECIMAL', 'TRUE_RATE',
            'ESTIMABLE_RATE', 'SUM_DECIMAL', 'ABSOLUTE_MEAN_DECIMAL',
            'SPEARMAN_RANK_CORRELATION', 'MAX_DRAWDOWN',
            'TOP_BOTTOM_SPREAD')
        AND ((reducer IN ('MEAN_DECIMAL', 'MEDIAN_DECIMAL', 'SUM_DECIMAL',
                          'ABSOLUTE_MEAN_DECIMAL', 'SPEARMAN_RANK_CORRELATION',
                          'MAX_DRAWDOWN', 'TOP_BOTTOM_SPREAD')
              AND source_value_type = 'DECIMAL')
          OR (reducer = 'TRUE_RATE' AND source_value_type = 'BOOLEAN')
          OR reducer = 'ESTIMABLE_RATE')
        AND (reducer <> 'SPEARMAN_RANK_CORRELATION'
             OR source_kind IN ('FORECAST_OUTCOME_PAIR',
                                'CANDIDATE_OUTCOME_PAIR'))
        AND (reducer <> 'TOP_BOTTOM_SPREAD'
             OR (source_kind = 'CANDIDATE_OUTCOME_PAIR'
                 AND source_measure = 'CANDIDATE_SCORE_VS_TARGET'))
        AND (source_kind <> 'CANDIDATE_OUTCOME_PAIR'
             OR (source_measure = 'CANDIDATE_SCORE_VS_TARGET'
                 AND reducer IN ('SPEARMAN_RANK_CORRELATION',
                                 'TOP_BOTTOM_SPREAD', 'ESTIMABLE_RATE'))
             OR (source_measure = 'CANDIDATE_TOP_K_RETURN'
                 AND reducer IN ('MEAN_DECIMAL', 'MEDIAN_DECIMAL',
                                 'ESTIMABLE_RATE'))
             OR (source_measure = 'CANDIDATE_HIT'
                 AND reducer IN ('TRUE_RATE', 'ESTIMABLE_RATE')))
        AND (reducer <> 'MAX_DRAWDOWN'
             OR source_measure IN ('GROSS_PORTFOLIO_RETURN',
                                   'NET_PORTFOLIO_RETURN_ASSUMED_COST'))
        AND slice_kind IN ('ALL_MEMBERS', 'CANDIDATE_DISPOSITION',
                           'EXPLORATORY_BACKTEST_ARM')
        AND ((slice_kind = 'ALL_MEMBERS' AND candidate_disposition IS NULL
              AND backtest_arm_kind IS NULL)
          OR (slice_kind = 'CANDIDATE_DISPOSITION'
              AND candidate_disposition IN ('SELECTED', 'RANKED_NOT_SELECTED', 'UNRANKABLE')
              AND backtest_arm_kind IS NULL)
          OR (slice_kind = 'EXPLORATORY_BACKTEST_ARM'
              AND candidate_disposition IS NULL
              AND backtest_arm_kind IN (
                  'RULE_BASELINE', 'MODEL_CHALLENGER',
                  'RULE_CURRENT_CONTEXT', 'RIDGE_CURRENT_CONTEXT',
                  'RULE_CONTEXT_OBSERVATIONAL', 'RIDGE_CONTEXT_OBSERVATIONAL'
              )))
        AND direction IN ('HIGHER', 'LOWER', 'DESCRIPTIVE')
        AND inclusion_policy IN ('COMPLETE_ONLY', 'AVAILABLE_VALUE')
        AND missingness_policy IN ('RETAIN_AND_ESTIMATE', 'REQUIRE_COMPLETE_ROSTER')
        AND minimum_estimable_count > 0
        AND acceptance_operator IN ('NONE', 'AT_LEAST', 'AT_MOST')
        AND ((acceptance_operator = 'NONE' AND acceptance_threshold IS NULL AND direction = 'DESCRIPTIVE')
          OR (acceptance_operator <> 'NONE' AND acceptance_threshold IS NOT NULL AND direction <> 'DESCRIPTIVE'))
        AND content_sha256 ~ '^[0-9a-f]{64}$'
    );

ALTER TABLE mra.exploratory_backtest_arm DROP CONSTRAINT exploratory_backtest_arm_shape_ck, ADD CONSTRAINT exploratory_backtest_arm_shape_ck CHECK (
        ordinal > 0 AND arm_kind ~ '^[a-zA-Z][a-zA-Z0-9_-]{0,99}$'
        AND content_sha256 ~ '^[0-9a-f]{64}$'
    );

ALTER TABLE mra.evaluation_backtest_arm_source DROP CONSTRAINT evaluation_backtest_source_shape_ck, ADD CONSTRAINT evaluation_backtest_source_shape_ck CHECK (
        arm_kind IN (
            'RULE_BASELINE', 'MODEL_CHALLENGER',
            'RULE_CURRENT_CONTEXT', 'RIDGE_CURRENT_CONTEXT',
            'RULE_CONTEXT_OBSERVATIONAL', 'RIDGE_CONTEXT_OBSERVATIONAL'
        )
        AND content_sha256 ~ '^[0-9a-f]{64}$'
    );

ALTER TABLE mra.exploratory_backtest_fold_session DROP CONSTRAINT exploratory_backtest_fold_session_global_uk, ADD CONSTRAINT exploratory_backtest_fold_session_member_uk UNIQUE (
        exploratory_backtest_fold_id, trading_session_id
    );

-- WP-18 Target-aligned prospective generation companion. The existing
-- MarketArchive remains the executable root; this freezes session/Target/member
-- scheduling without rewriting WP-17P rows.
CREATE TABLE mra.prospective_archive_generation (
    market_archive_id uuid PRIMARY KEY
        REFERENCES mra.market_archive(market_archive_id) ON DELETE RESTRICT,
    series_code text NOT NULL,
    generation integer NOT NULL,
    predecessor_market_archive_id uuid
        REFERENCES mra.prospective_archive_generation(market_archive_id)
        ON DELETE RESTRICT,
    exchange_code text NOT NULL,
    target_definition_id uuid NOT NULL,
    target_version integer NOT NULL,
    target_definition_sha256 text NOT NULL,
    reference_checkpoint_id uuid NOT NULL,
    outcome_checkpoint_id uuid NOT NULL,
    decision_session_id uuid NOT NULL
        REFERENCES mra.trading_session(session_id) ON DELETE RESTRICT,
    outcome_session_id uuid NOT NULL
        REFERENCES mra.trading_session(session_id) ON DELETE RESTRICT,
    later_verification_session_id uuid NOT NULL
        REFERENCES mra.trading_session(session_id) ON DELETE RESTRICT,
    member_count integer NOT NULL,
    member_roster_sha256 text NOT NULL,
    schedule_count integer NOT NULL,
    schedule_roster_sha256 text NOT NULL,
    provenance_sha256 text NOT NULL,
    content_sha256 text NOT NULL UNIQUE,
    registered_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT prospective_archive_generation_series_uk UNIQUE (
        series_code, generation
    ),
    CONSTRAINT prospective_archive_generation_predecessor_uk UNIQUE (
        predecessor_market_archive_id
    ),
    CONSTRAINT prospective_archive_generation_target_fk FOREIGN KEY (
        target_definition_id, target_version, target_definition_sha256
    ) REFERENCES mra.target_definition(
        target_definition_id, version, content_sha256
    ) ON DELETE RESTRICT,
    CONSTRAINT prospective_archive_generation_reference_fk FOREIGN KEY (
        reference_checkpoint_id, target_definition_id
    ) REFERENCES mra.target_checkpoint(
        target_checkpoint_id, target_definition_id
    ) ON DELETE RESTRICT,
    CONSTRAINT prospective_archive_generation_outcome_fk FOREIGN KEY (
        outcome_checkpoint_id, target_definition_id
    ) REFERENCES mra.target_checkpoint(
        target_checkpoint_id, target_definition_id
    ) ON DELETE RESTRICT,
    CONSTRAINT prospective_archive_generation_shape_ck CHECK (
        series_code ~ '^[a-z][a-z0-9_-]{0,99}$'
        AND generation > 0
        AND ((generation = 1) = (predecessor_market_archive_id IS NULL))
        AND exchange_code IN ('XSHG', 'XSHE')
        AND target_version > 0
        AND target_definition_sha256 ~ '^[0-9a-f]{64}$'
        AND member_count > 0
        AND schedule_count = member_count * 9
        AND member_roster_sha256 ~ '^[0-9a-f]{64}$'
        AND schedule_roster_sha256 ~ '^[0-9a-f]{64}$'
        AND provenance_sha256 ~ '^[0-9a-f]{64}$'
        AND content_sha256 ~ '^[0-9a-f]{64}$'
    )
);

CREATE TABLE mra.prospective_archive_planning_gap (
    prospective_archive_planning_gap_id uuid PRIMARY KEY,
    series_code text NOT NULL,
    expected_generation integer NOT NULL,
    predecessor_market_archive_id uuid
        REFERENCES mra.prospective_archive_generation(market_archive_id)
        ON DELETE RESTRICT,
    target_definition_id uuid NOT NULL,
    target_version integer NOT NULL,
    target_definition_sha256 text NOT NULL,
    expected_decision_session_id uuid NOT NULL
        REFERENCES mra.trading_session(session_id) ON DELETE RESTRICT,
    detected_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    reason_code text NOT NULL,
    content_sha256 text NOT NULL UNIQUE,
    CONSTRAINT prospective_archive_planning_gap_scope_uk UNIQUE (
        series_code, expected_generation, expected_decision_session_id
    ),
    CONSTRAINT prospective_archive_planning_gap_target_fk FOREIGN KEY (
        target_definition_id, target_version, target_definition_sha256
    ) REFERENCES mra.target_definition(
        target_definition_id, version, content_sha256
    ) ON DELETE RESTRICT,
    CONSTRAINT prospective_archive_planning_gap_shape_ck CHECK (
        series_code ~ '^[a-z][a-z0-9_-]{0,99}$'
        AND expected_generation > 0
        AND ((expected_generation = 1) = (predecessor_market_archive_id IS NULL))
        AND target_version > 0
        AND target_definition_sha256 ~ '^[0-9a-f]{64}$'
        AND reason_code IN (
            'GENERATION_NOT_PREDECLARED', 'RUNTIME_OUTAGE',
            'CALENDAR_INCOMPLETE', 'TARGET_CONTRACT_UNAVAILABLE'
        )
        AND content_sha256 ~ '^[0-9a-f]{64}$'
    )
);

CREATE TABLE mra.prospective_archive_generation_member (
    market_archive_id uuid NOT NULL
        REFERENCES mra.prospective_archive_generation(market_archive_id)
        ON DELETE RESTRICT,
    ordinal integer NOT NULL,
    instrument_id uuid NOT NULL REFERENCES mra.instrument(instrument_id)
        ON DELETE RESTRICT,
    instrument_identifier_id uuid NOT NULL
        REFERENCES mra.instrument_identifier(instrument_identifier_id)
        ON DELETE RESTRICT,
    content_sha256 text NOT NULL,
    PRIMARY KEY (market_archive_id, ordinal),
    CONSTRAINT prospective_archive_member_instrument_uk UNIQUE (
        market_archive_id, instrument_id
    ),
    CONSTRAINT prospective_archive_member_scope_uk UNIQUE (
        market_archive_id, instrument_id, ordinal
    ),
    CONSTRAINT prospective_archive_member_shape_ck CHECK (
        ordinal > 0 AND content_sha256 ~ '^[0-9a-f]{64}$'
    )
);

CREATE TABLE mra.prospective_archive_slice_schedule (
    market_archive_slice_id uuid PRIMARY KEY,
    market_archive_id uuid NOT NULL,
    ordinal integer NOT NULL,
    instrument_id uuid NOT NULL,
    member_ordinal integer NOT NULL,
    schedule_slot text NOT NULL,
    trading_session_id uuid NOT NULL
        REFERENCES mra.trading_session(session_id) ON DELETE RESTRICT,
    target_checkpoint_id uuid NOT NULL,
    comparison_ordinal integer NOT NULL,
    content_sha256 text NOT NULL,
    planned_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT prospective_archive_schedule_slice_fk FOREIGN KEY (
        market_archive_id, market_archive_slice_id
    ) REFERENCES mra.market_archive_slice(
        market_archive_id, market_archive_slice_id
    ) ON DELETE RESTRICT,
    CONSTRAINT prospective_archive_schedule_member_fk FOREIGN KEY (
        market_archive_id, instrument_id, member_ordinal
    ) REFERENCES mra.prospective_archive_generation_member(
        market_archive_id, instrument_id, ordinal
    ) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT prospective_archive_schedule_ordinal_uk UNIQUE (
        market_archive_id, ordinal
    ),
    CONSTRAINT prospective_archive_schedule_slot_uk UNIQUE (
        market_archive_id, instrument_id, schedule_slot
    ),
    CONSTRAINT prospective_archive_schedule_shape_ck CHECK (
        ordinal > 0 AND member_ordinal > 0 AND comparison_ordinal > 0
        AND schedule_slot IN (
            'PRE_DECISION', 'DECISION_NEAR', 'POST_CLOSE',
            'EVENING_REVISION', 'OUTCOME_PRE_OPEN', 'OUTCOME_PATH',
            'OUTCOME_10_30', 'OUTCOME_POST_CLOSE',
            'REVISION_VERIFICATION'
        )
        AND content_sha256 ~ '^[0-9a-f]{64}$'
    )
);

CREATE TABLE mra.prospective_archive_slice_terminal (
    market_archive_slice_id uuid PRIMARY KEY,
    market_archive_id uuid NOT NULL,
    terminal_state text NOT NULL,
    reason_code text NOT NULL,
    terminal_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    content_sha256 text NOT NULL,
    CONSTRAINT prospective_archive_terminal_schedule_fk FOREIGN KEY (
        market_archive_slice_id
    ) REFERENCES mra.prospective_archive_slice_schedule(
        market_archive_slice_id
    ) ON DELETE RESTRICT,
    CONSTRAINT prospective_archive_terminal_slice_fk FOREIGN KEY (
        market_archive_id, market_archive_slice_id
    ) REFERENCES mra.market_archive_slice(
        market_archive_id, market_archive_slice_id
    ) ON DELETE RESTRICT,
    CONSTRAINT prospective_archive_terminal_shape_ck CHECK (
        terminal_state IN (
            'CAPTURED_ON_TIME', 'CAPTURED_LATE', 'MISSED',
            'PROVIDER_GAP', 'RESOURCE_STOP', 'FAILED'
        )
        AND reason_code ~ '^[A-Z][A-Z0-9_]{0,99}$'
        AND content_sha256 ~ '^[0-9a-f]{64}$'
    )
);

CREATE TABLE mra.prospective_archive_revision_observation (
    market_archive_capture_observation_id uuid PRIMARY KEY
        REFERENCES mra.market_archive_capture_observation(
            market_archive_capture_observation_id
        ) ON DELETE RESTRICT,
    market_archive_id uuid NOT NULL,
    market_archive_slice_id uuid NOT NULL,
    instrument_id uuid NOT NULL,
    target_checkpoint_id uuid NOT NULL
        REFERENCES mra.target_checkpoint(target_checkpoint_id) ON DELETE RESTRICT,
    comparison_ordinal integer NOT NULL,
    predecessor_observation_id uuid
        REFERENCES mra.prospective_archive_revision_observation(
            market_archive_capture_observation_id
        ) ON DELETE RESTRICT,
    relation text NOT NULL,
    artifact_sha256 text NOT NULL,
    normalized_revision_roster_sha256 text NOT NULL,
    content_sha256 text NOT NULL,
    observed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT prospective_archive_revision_schedule_fk FOREIGN KEY (
        market_archive_slice_id
    ) REFERENCES mra.prospective_archive_slice_schedule(
        market_archive_slice_id
    ) ON DELETE RESTRICT,
    CONSTRAINT prospective_archive_revision_ordinal_uk UNIQUE (
        market_archive_id, instrument_id, target_checkpoint_id,
        comparison_ordinal
    ),
    CONSTRAINT prospective_archive_revision_shape_ck CHECK (
        comparison_ordinal > 0
        AND relation IN ('FIRST', 'IDENTICAL', 'CHANGED')
        AND ((comparison_ordinal = 1) = (predecessor_observation_id IS NULL))
        AND ((comparison_ordinal = 1) = (relation = 'FIRST'))
        AND artifact_sha256 ~ '^[0-9a-f]{64}$'
        AND normalized_revision_roster_sha256 ~ '^[0-9a-f]{64}$'
        AND content_sha256 ~ '^[0-9a-f]{64}$'
    )
);

CREATE TABLE mra.operational_schema_upgrade_receipt (
    operational_schema_upgrade_receipt_id uuid PRIMARY KEY,
    upgrade_code text NOT NULL UNIQUE,
    database_oid oid NOT NULL,
    prior_baseline_sha256 text NOT NULL,
    next_baseline_sha256 text NOT NULL,
    backup_sha256 text NOT NULL,
    backup_size_bytes bigint NOT NULL,
    code_sha text NOT NULL,
    content_sha256 text NOT NULL UNIQUE,
    applied_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT operational_schema_upgrade_receipt_shape_ck CHECK (
        upgrade_code ~ '^[a-z][a-z0-9_-]{0,99}$'
        AND prior_baseline_sha256 ~ '^[0-9a-f]{64}$'
        AND next_baseline_sha256 ~ '^[0-9a-f]{64}$'
        AND backup_sha256 ~ '^[0-9a-f]{64}$'
        AND backup_size_bytes > 0
        AND code_sha ~ '^[0-9a-f]{40}([0-9a-f]{24})?$'
        AND content_sha256 ~ '^[0-9a-f]{64}$'
    )
);

CREATE TABLE mra.exploratory_backtest_arm_strategy (
    exploratory_backtest_arm_id uuid PRIMARY KEY,
    exploratory_backtest_run_id uuid NOT NULL,
    strategy_version_id uuid NOT NULL,
    strategy_version_sha256 text NOT NULL,
    context_mode text NOT NULL,
    content_sha256 text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT exploratory_backtest_arm_strategy_arm_fk FOREIGN KEY (
        exploratory_backtest_arm_id, exploratory_backtest_run_id
    ) REFERENCES mra.exploratory_backtest_arm(
        exploratory_backtest_arm_id, exploratory_backtest_run_id
    ) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT exploratory_backtest_arm_strategy_version_fk FOREIGN KEY (
        strategy_version_id, strategy_version_sha256
    ) REFERENCES mra.strategy_version(
        strategy_version_id, content_sha256
    ) ON DELETE RESTRICT,
    CONSTRAINT exploratory_backtest_arm_strategy_shape_ck CHECK (
        context_mode IN ('CURRENT_GATE', 'OBSERVATIONAL')
        AND strategy_version_sha256 ~ '^[0-9a-f]{64}$'
        AND content_sha256 ~ '^[0-9a-f]{64}$'
    )
);

CREATE TABLE mra.evaluation_candidate_outcome_source (
    evaluation_metric_observation_id uuid PRIMARY KEY,
    evaluation_run_id uuid NOT NULL,
    evaluation_protocol_metric_id uuid NOT NULL,
    source_measure text NOT NULL,
    commitment_id uuid NOT NULL
        REFERENCES mra.decision_target_commitment(commitment_id) ON DELETE RESTRICT,
    candidate_id uuid NOT NULL REFERENCES mra.candidate(candidate_id) ON DELETE RESTRICT,
    candidate_set_id uuid NOT NULL REFERENCES mra.candidate_set(candidate_set_id) ON DELETE RESTRICT,
    disposition text NOT NULL,
    composite_score numeric,
    competition_rank integer,
    market_target_outcome_metric_id uuid NOT NULL
        REFERENCES mra.market_target_outcome_metric(market_target_outcome_metric_id)
        ON DELETE RESTRICT,
    market_target_outcome_revision_id uuid NOT NULL
        REFERENCES mra.market_target_outcome_revision(market_target_outcome_revision_id)
        ON DELETE RESTRICT,
    outcome_decimal_value numeric,
    decimal_value numeric,
    secondary_decimal_value numeric,
    boolean_value boolean,
    source_status text NOT NULL,
    content_sha256 text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT evaluation_candidate_outcome_input_fk FOREIGN KEY (
        evaluation_metric_observation_id, evaluation_run_id,
        evaluation_protocol_metric_id
    ) REFERENCES mra.evaluation_metric_observation(
        evaluation_metric_observation_id, evaluation_run_id,
        evaluation_protocol_metric_id
    ) ON DELETE RESTRICT,
    CONSTRAINT evaluation_candidate_outcome_shape_ck CHECK (
        source_measure IN ('CANDIDATE_SCORE_VS_TARGET',
                           'CANDIDATE_TOP_K_RETURN', 'CANDIDATE_HIT')
        AND disposition IN ('SELECTED', 'RANKED_NOT_SELECTED', 'UNRANKABLE')
        AND source_status IN ('PARTIAL', 'COMPLETE', 'UNAVAILABLE')
        AND ((disposition = 'UNRANKABLE'
              AND composite_score IS NULL AND competition_rank IS NULL)
          OR (disposition <> 'UNRANKABLE'
              AND composite_score BETWEEN 0 AND 1
              AND competition_rank > 0))
        AND (
          source_status = 'UNAVAILABLE'
          OR (source_measure = 'CANDIDATE_SCORE_VS_TARGET'
              AND decimal_value = composite_score
              AND secondary_decimal_value = outcome_decimal_value
              AND boolean_value IS NULL
              AND decimal_value IS NOT NULL
              AND secondary_decimal_value IS NOT NULL)
          OR (source_measure = 'CANDIDATE_TOP_K_RETURN'
              AND disposition = 'SELECTED'
              AND decimal_value = outcome_decimal_value
              AND secondary_decimal_value IS NULL
              AND boolean_value IS NULL
              AND decimal_value IS NOT NULL)
          OR (source_measure = 'CANDIDATE_HIT'
              AND disposition = 'SELECTED'
              AND decimal_value IS NULL
              AND secondary_decimal_value IS NULL
              AND boolean_value IS NOT NULL)
        )
        AND content_sha256 ~ '^[0-9a-f]{64}$'
    )
);

-- WP-18Q current Backtest specification closure. ExploratoryBacktestRun remains
-- the only Backtest identity: this table deliberately reuses the run PK and
-- has no independently addressable business identifier.
CREATE TABLE mra.backtest_specification (
    exploratory_backtest_run_id uuid PRIMARY KEY,
    specification_schema_version integer NOT NULL,
    definition_version integer NOT NULL,
    specification_sha256 text NOT NULL,
    universe_revision_id uuid NOT NULL,
    universe_id uuid NOT NULL,
    universe_scope_sha256 text NOT NULL,
    sample_algorithm_code text NOT NULL,
    sample_algorithm_version integer NOT NULL,
    sample_input_key text NOT NULL,
    sample_seed bigint NOT NULL,
    sample_member_count integer NOT NULL,
    sample_roster_sha256 text NOT NULL,
    exchange_code text NOT NULL,
    first_trading_session_id uuid NOT NULL,
    last_trading_session_id uuid NOT NULL,
    distinct_trading_session_count integer NOT NULL,
    fold_session_binding_count integer NOT NULL,
    fold_dependency_count integer NOT NULL,
    fold_dependency_roster_sha256 text NOT NULL,
    arm_fold_count integer NOT NULL,
    arm_fold_roster_sha256 text NOT NULL,
    model_training_requirement_count integer NOT NULL,
    model_training_requirement_roster_sha256 text NOT NULL,
    walk_forward_policy_code text NOT NULL,
    walk_forward_policy_version integer NOT NULL,
    walk_forward_mode text NOT NULL,
    minimum_fit_sessions integer NOT NULL,
    minimum_validation_sessions integer NOT NULL,
    step_sessions integer NOT NULL,
    evaluation_requirement_count integer NOT NULL,
    evaluation_requirement_roster_sha256 text NOT NULL,
    retrospective_classification text NOT NULL,
    formal_provider_state text NOT NULL,
    formal_pit_state text NOT NULL,
    formal_oos_state text NOT NULL,
    prospective_proven boolean NOT NULL,
    alpha_proven boolean NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT backtest_specification_identity_hash_uk UNIQUE (
        exploratory_backtest_run_id, specification_sha256
    ),
    CONSTRAINT backtest_specification_run_fk FOREIGN KEY (
        exploratory_backtest_run_id
    ) REFERENCES mra.exploratory_backtest_run(
        exploratory_backtest_run_id
    ) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT backtest_specification_universe_fk FOREIGN KEY (
        universe_revision_id, universe_id, universe_scope_sha256
    ) REFERENCES mra.universe_revision(
        universe_revision_id, universe_id, scope_content_sha256
    ) ON DELETE RESTRICT,
    CONSTRAINT backtest_specification_first_session_fk FOREIGN KEY (
        first_trading_session_id
    ) REFERENCES mra.trading_session(session_id) ON DELETE RESTRICT,
    CONSTRAINT backtest_specification_last_session_fk FOREIGN KEY (
        last_trading_session_id
    ) REFERENCES mra.trading_session(session_id) ON DELETE RESTRICT,
    CONSTRAINT backtest_specification_shape_ck CHECK (
        specification_schema_version > 0 AND definition_version > 0
        AND specification_sha256 ~ '^[0-9a-f]{64}$'
        AND universe_scope_sha256 ~ '^[0-9a-f]{64}$'
        AND sample_algorithm_code ~ '^[a-z][a-z0-9_.-]{0,99}$'
        AND sample_algorithm_version > 0 AND sample_input_key <> ''
        AND sample_seed >= 0 AND sample_member_count > 0
        AND sample_roster_sha256 ~ '^[0-9a-f]{64}$'
        AND exchange_code IN ('XSHG', 'XSHE')
        AND distinct_trading_session_count > 0
        AND fold_session_binding_count >= distinct_trading_session_count
        AND fold_dependency_count > 0
        AND fold_dependency_roster_sha256 ~ '^[0-9a-f]{64}$'
        AND arm_fold_count > 0
        AND arm_fold_roster_sha256 ~ '^[0-9a-f]{64}$'
        AND model_training_requirement_count >= 0
        AND model_training_requirement_roster_sha256 ~ '^[0-9a-f]{64}$'
        AND walk_forward_policy_code ~ '^[a-z][a-z0-9_.-]{0,99}$'
        AND walk_forward_policy_version > 0
        AND walk_forward_mode IN ('FIXED', 'ROLLING', 'EXPANDING')
        AND minimum_fit_sessions > 0
        AND minimum_validation_sessions > 0 AND step_sessions > 0
        AND evaluation_requirement_count > 0
        AND evaluation_requirement_roster_sha256 ~ '^[0-9a-f]{64}$'
        AND retrospective_classification = 'EXPLORATORY_RETROSPECTIVE'
        AND formal_provider_state = 'BLOCKED'
        AND formal_pit_state = 'BLOCKED'
        AND formal_oos_state = 'NOT_RUN'
        AND NOT prospective_proven AND NOT alpha_proven
    )
);

CREATE TABLE mra.backtest_sample_member (
    exploratory_backtest_run_id uuid NOT NULL,
    specification_sha256 text NOT NULL,
    ordinal integer NOT NULL,
    universe_revision_id uuid NOT NULL,
    universe_member_id uuid NOT NULL,
    instrument_id uuid NOT NULL,
    content_sha256 text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (exploratory_backtest_run_id, ordinal),
    CONSTRAINT backtest_sample_member_instrument_uk UNIQUE (
        exploratory_backtest_run_id, instrument_id
    ),
    CONSTRAINT backtest_sample_member_owner_fk FOREIGN KEY (
        exploratory_backtest_run_id, specification_sha256
    ) REFERENCES mra.backtest_specification(
        exploratory_backtest_run_id, specification_sha256
    ) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT backtest_sample_member_universe_fk FOREIGN KEY (
        universe_member_id, universe_revision_id, instrument_id
    ) REFERENCES mra.universe_member(
        universe_member_id, universe_revision_id, instrument_id
    ) ON DELETE RESTRICT,
    CONSTRAINT backtest_sample_member_shape_ck CHECK (
        ordinal > 0 AND specification_sha256 ~ '^[0-9a-f]{64}$'
        AND content_sha256 ~ '^[0-9a-f]{64}$'
    )
);

CREATE TABLE mra.backtest_arm_specification (
    exploratory_backtest_arm_id uuid PRIMARY KEY,
    exploratory_backtest_run_id uuid NOT NULL,
    specification_sha256 text NOT NULL,
    execution_kind text NOT NULL,
    comparison_role text NOT NULL,
    context_mode text NOT NULL,
    candidate_policy_id uuid NOT NULL,
    candidate_policy_sha256 text NOT NULL,
    candidate_binding_source text NOT NULL,
    context_policy_id uuid NOT NULL,
    context_policy_sha256 text NOT NULL,
    context_binding_source text NOT NULL,
    strategy_version_id uuid NOT NULL,
    strategy_version_sha256 text NOT NULL,
    strategy_binding_source text NOT NULL,
    model_id uuid,
    model_sha256 text,
    portfolio_policy_id uuid NOT NULL,
    portfolio_policy_sha256 text NOT NULL,
    portfolio_binding_source text NOT NULL,
    risk_policy_id uuid NOT NULL,
    risk_policy_sha256 text NOT NULL,
    risk_binding_source text NOT NULL,
    effective_cost_roster_sha256 text NOT NULL,
    cost_binding_source text NOT NULL,
    content_sha256 text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT backtest_arm_specification_exact_uk UNIQUE (
        exploratory_backtest_arm_id, exploratory_backtest_run_id,
        specification_sha256
    ),
    CONSTRAINT backtest_arm_specification_arm_fk FOREIGN KEY (
        exploratory_backtest_arm_id, exploratory_backtest_run_id
    ) REFERENCES mra.exploratory_backtest_arm(
        exploratory_backtest_arm_id, exploratory_backtest_run_id
    ) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT backtest_arm_specification_owner_fk FOREIGN KEY (
        exploratory_backtest_run_id, specification_sha256
    ) REFERENCES mra.backtest_specification(
        exploratory_backtest_run_id, specification_sha256
    ) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT backtest_arm_specification_candidate_fk FOREIGN KEY (
        candidate_policy_id, candidate_policy_sha256
    ) REFERENCES mra.candidate_policy(
        candidate_policy_id, content_sha256
    ) ON DELETE RESTRICT,
    CONSTRAINT backtest_arm_specification_context_fk FOREIGN KEY (
        context_policy_id, context_policy_sha256
    ) REFERENCES mra.context_policy(
        context_policy_id, content_sha256
    ) ON DELETE RESTRICT,
    CONSTRAINT backtest_arm_specification_strategy_fk FOREIGN KEY (
        strategy_version_id, strategy_version_sha256
    ) REFERENCES mra.strategy_version(
        strategy_version_id, content_sha256
    ) ON DELETE RESTRICT,
    CONSTRAINT backtest_arm_specification_model_fk FOREIGN KEY (
        model_id, model_sha256
    ) REFERENCES mra.model(model_id, content_sha256) ON DELETE RESTRICT,
    CONSTRAINT backtest_arm_specification_portfolio_fk FOREIGN KEY (
        portfolio_policy_id, portfolio_policy_sha256
    ) REFERENCES mra.portfolio_policy(
        portfolio_policy_id, content_sha256
    ) ON DELETE RESTRICT,
    CONSTRAINT backtest_arm_specification_risk_fk FOREIGN KEY (
        risk_policy_id, risk_policy_sha256
    ) REFERENCES mra.risk_policy(
        risk_policy_id, content_sha256
    ) ON DELETE RESTRICT,
    CONSTRAINT backtest_arm_specification_shape_ck CHECK (
        execution_kind IN ('RULE', 'MODEL')
        AND comparison_role IN ('BASELINE', 'CHALLENGER', 'DIAGNOSTIC')
        AND context_mode IN ('CURRENT_GATE', 'OBSERVATIONAL')
        AND candidate_binding_source IN ('SHARED_DEFAULT', 'ARM_OVERRIDE')
        AND context_binding_source IN ('SHARED_DEFAULT', 'ARM_OVERRIDE')
        AND strategy_binding_source IN ('SHARED_DEFAULT', 'ARM_OVERRIDE')
        AND portfolio_binding_source IN ('SHARED_DEFAULT', 'ARM_OVERRIDE')
        AND risk_binding_source IN ('SHARED_DEFAULT', 'ARM_OVERRIDE')
        AND cost_binding_source IN ('SHARED_DEFAULT', 'ARM_OVERRIDE')
        AND ((execution_kind = 'RULE'
              AND model_id IS NULL AND model_sha256 IS NULL)
          OR (execution_kind = 'MODEL'
              AND model_id IS NOT NULL
              AND model_sha256 ~ '^[0-9a-f]{64}$'))
        AND specification_sha256 ~ '^[0-9a-f]{64}$'
        AND candidate_policy_sha256 ~ '^[0-9a-f]{64}$'
        AND context_policy_sha256 ~ '^[0-9a-f]{64}$'
        AND strategy_version_sha256 ~ '^[0-9a-f]{64}$'
        AND portfolio_policy_sha256 ~ '^[0-9a-f]{64}$'
        AND risk_policy_sha256 ~ '^[0-9a-f]{64}$'
        AND effective_cost_roster_sha256 ~ '^[0-9a-f]{64}$'
        AND content_sha256 ~ '^[0-9a-f]{64}$'
    )
);

CREATE TABLE mra.backtest_fold_dependency (
    backtest_fold_dependency_id uuid PRIMARY KEY,
    exploratory_backtest_run_id uuid NOT NULL,
    specification_sha256 text NOT NULL,
    ordinal integer NOT NULL,
    fit_fold_id uuid NOT NULL,
    validation_fold_id uuid NOT NULL,
    dependency_kind text NOT NULL,
    content_sha256 text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT backtest_fold_dependency_ordinal_uk UNIQUE (
        exploratory_backtest_run_id, ordinal
    ),
    CONSTRAINT backtest_fold_dependency_pair_uk UNIQUE (
        exploratory_backtest_run_id, fit_fold_id, validation_fold_id
    ),
    CONSTRAINT backtest_fold_dependency_owner_fk FOREIGN KEY (
        exploratory_backtest_run_id, specification_sha256
    ) REFERENCES mra.backtest_specification(
        exploratory_backtest_run_id, specification_sha256
    ) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT backtest_fold_dependency_fit_fk FOREIGN KEY (
        fit_fold_id, exploratory_backtest_run_id
    ) REFERENCES mra.exploratory_backtest_fold(
        exploratory_backtest_fold_id, exploratory_backtest_run_id
    ) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT backtest_fold_dependency_validation_fk FOREIGN KEY (
        validation_fold_id, exploratory_backtest_run_id
    ) REFERENCES mra.exploratory_backtest_fold(
        exploratory_backtest_fold_id, exploratory_backtest_run_id
    ) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT backtest_fold_dependency_shape_ck CHECK (
        ordinal > 0 AND fit_fold_id <> validation_fold_id
        AND dependency_kind = 'MODEL_TRAINING'
        AND specification_sha256 ~ '^[0-9a-f]{64}$'
        AND content_sha256 ~ '^[0-9a-f]{64}$'
    )
);

CREATE TABLE mra.backtest_arm_fold (
    backtest_arm_fold_id uuid PRIMARY KEY,
    exploratory_backtest_run_id uuid NOT NULL,
    specification_sha256 text NOT NULL,
    ordinal integer NOT NULL,
    exploratory_backtest_arm_id uuid NOT NULL,
    exploratory_backtest_fold_id uuid NOT NULL,
    content_sha256 text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT backtest_arm_fold_ordinal_uk UNIQUE (
        exploratory_backtest_run_id, ordinal
    ),
    CONSTRAINT backtest_arm_fold_pair_uk UNIQUE (
        exploratory_backtest_arm_id, exploratory_backtest_fold_id
    ),
    CONSTRAINT backtest_arm_fold_owner_fk FOREIGN KEY (
        exploratory_backtest_run_id, specification_sha256
    ) REFERENCES mra.backtest_specification(
        exploratory_backtest_run_id, specification_sha256
    ) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT backtest_arm_fold_arm_fk FOREIGN KEY (
        exploratory_backtest_arm_id, exploratory_backtest_run_id
    ) REFERENCES mra.exploratory_backtest_arm(
        exploratory_backtest_arm_id, exploratory_backtest_run_id
    ) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT backtest_arm_fold_fold_fk FOREIGN KEY (
        exploratory_backtest_fold_id, exploratory_backtest_run_id
    ) REFERENCES mra.exploratory_backtest_fold(
        exploratory_backtest_fold_id, exploratory_backtest_run_id
    ) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT backtest_arm_fold_shape_ck CHECK (
        ordinal > 0 AND specification_sha256 ~ '^[0-9a-f]{64}$'
        AND content_sha256 ~ '^[0-9a-f]{64}$'
    )
);

CREATE TABLE mra.backtest_model_training_requirement (
    backtest_model_training_requirement_id uuid PRIMARY KEY,
    exploratory_backtest_run_id uuid NOT NULL,
    specification_sha256 text NOT NULL,
    ordinal integer NOT NULL,
    exploratory_backtest_arm_id uuid NOT NULL,
    fit_fold_id uuid NOT NULL,
    validation_fold_id uuid NOT NULL,
    model_id uuid NOT NULL,
    model_sha256 text NOT NULL,
    required_fit_evaluation_protocol_id uuid NOT NULL,
    required_fit_evaluation_protocol_sha256 text NOT NULL,
    content_sha256 text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT backtest_model_requirement_ordinal_uk UNIQUE (
        exploratory_backtest_run_id, ordinal
    ),
    CONSTRAINT backtest_model_requirement_scope_uk UNIQUE (
        exploratory_backtest_arm_id, fit_fold_id, validation_fold_id
    ),
    CONSTRAINT backtest_model_requirement_owner_fk FOREIGN KEY (
        exploratory_backtest_run_id, specification_sha256
    ) REFERENCES mra.backtest_specification(
        exploratory_backtest_run_id, specification_sha256
    ) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT backtest_model_requirement_arm_fk FOREIGN KEY (
        exploratory_backtest_arm_id, exploratory_backtest_run_id,
        specification_sha256
    ) REFERENCES mra.backtest_arm_specification(
        exploratory_backtest_arm_id, exploratory_backtest_run_id,
        specification_sha256
    ) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT backtest_model_requirement_fit_fk FOREIGN KEY (
        fit_fold_id, exploratory_backtest_run_id
    ) REFERENCES mra.exploratory_backtest_fold(
        exploratory_backtest_fold_id, exploratory_backtest_run_id
    ) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT backtest_model_requirement_validation_fk FOREIGN KEY (
        validation_fold_id, exploratory_backtest_run_id
    ) REFERENCES mra.exploratory_backtest_fold(
        exploratory_backtest_fold_id, exploratory_backtest_run_id
    ) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT backtest_model_requirement_model_fk FOREIGN KEY (
        model_id, model_sha256
    ) REFERENCES mra.model(model_id, content_sha256) ON DELETE RESTRICT,
    CONSTRAINT backtest_model_requirement_protocol_fk FOREIGN KEY (
        required_fit_evaluation_protocol_id,
        required_fit_evaluation_protocol_sha256
    ) REFERENCES mra.evaluation_protocol(
        evaluation_protocol_id, content_sha256
    ) ON DELETE RESTRICT,
    CONSTRAINT backtest_model_requirement_shape_ck CHECK (
        ordinal > 0 AND fit_fold_id <> validation_fold_id
        AND specification_sha256 ~ '^[0-9a-f]{64}$'
        AND model_sha256 ~ '^[0-9a-f]{64}$'
        AND required_fit_evaluation_protocol_sha256 ~ '^[0-9a-f]{64}$'
        AND content_sha256 ~ '^[0-9a-f]{64}$'
    )
);

CREATE TABLE mra.backtest_evaluation_requirement (
    backtest_evaluation_requirement_id uuid PRIMARY KEY,
    exploratory_backtest_run_id uuid NOT NULL,
    specification_sha256 text NOT NULL,
    ordinal integer NOT NULL,
    scope_kind text NOT NULL,
    exploratory_backtest_arm_id uuid,
    exploratory_backtest_fold_id uuid,
    slice_key text,
    evaluation_protocol_id uuid NOT NULL,
    evaluation_protocol_sha256 text NOT NULL,
    is_primary boolean NOT NULL,
    content_sha256 text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT backtest_evaluation_requirement_ordinal_uk UNIQUE (
        exploratory_backtest_run_id, ordinal
    ),
    CONSTRAINT backtest_evaluation_requirement_owner_fk FOREIGN KEY (
        exploratory_backtest_run_id, specification_sha256
    ) REFERENCES mra.backtest_specification(
        exploratory_backtest_run_id, specification_sha256
    ) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT backtest_evaluation_requirement_arm_fk FOREIGN KEY (
        exploratory_backtest_arm_id, exploratory_backtest_run_id
    ) REFERENCES mra.exploratory_backtest_arm(
        exploratory_backtest_arm_id, exploratory_backtest_run_id
    ) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT backtest_evaluation_requirement_fold_fk FOREIGN KEY (
        exploratory_backtest_fold_id, exploratory_backtest_run_id
    ) REFERENCES mra.exploratory_backtest_fold(
        exploratory_backtest_fold_id, exploratory_backtest_run_id
    ) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT backtest_evaluation_requirement_protocol_fk FOREIGN KEY (
        evaluation_protocol_id, evaluation_protocol_sha256
    ) REFERENCES mra.evaluation_protocol(
        evaluation_protocol_id, content_sha256
    ) ON DELETE RESTRICT,
    CONSTRAINT backtest_evaluation_requirement_shape_ck CHECK (
        ordinal > 0
        AND scope_kind IN ('FOLD', 'AGGREGATE', 'MONTH', 'QUARTER', 'CONTEXT')
        AND ((scope_kind = 'AGGREGATE'
              AND exploratory_backtest_fold_id IS NULL AND slice_key IS NULL)
          OR (scope_kind = 'FOLD'
              AND exploratory_backtest_fold_id IS NOT NULL AND slice_key IS NULL)
          OR (scope_kind IN ('MONTH', 'QUARTER', 'CONTEXT')
              AND slice_key IS NOT NULL))
        AND specification_sha256 ~ '^[0-9a-f]{64}$'
        AND evaluation_protocol_sha256 ~ '^[0-9a-f]{64}$'
        AND content_sha256 ~ '^[0-9a-f]{64}$'
    )
);

ALTER TABLE mra.exploratory_backtest_run
    ALTER COLUMN session_count DROP NOT NULL,
    ADD COLUMN current_specification_sha256 text,
    DROP CONSTRAINT exploratory_backtest_run_shape_ck,
    ADD CONSTRAINT exploratory_backtest_run_shape_ck CHECK (
        run_code ~ '^[a-z][a-z0-9_-]{0,99}$' AND generation > 0
        AND evidence_lane = 'EXPLORATORY_RETROSPECTIVE'
        AND hypothesis <> '' AND target_version > 0
        AND feature_count > 0 AND arm_count > 0
        AND fold_count > 0
        AND cost_count > 0 AND random_seed >= 0
        AND (
            (current_specification_sha256 IS NULL
             AND session_count > 0
             AND ((generation = 1 AND arm_count = 2)
                  OR (generation > 1 AND arm_count = 4)))
            OR
            (current_specification_sha256 ~ '^[0-9a-f]{64}$'
             AND session_count IS NULL)
        )
        AND target_definition_sha256 ~ '^[0-9a-f]{64}$'
        AND candidate_policy_sha256 ~ '^[0-9a-f]{64}$'
        AND context_policy_sha256 ~ '^[0-9a-f]{64}$'
        AND strategy_version_sha256 ~ '^[0-9a-f]{64}$'
        AND portfolio_policy_sha256 ~ '^[0-9a-f]{64}$'
        AND risk_policy_sha256 ~ '^[0-9a-f]{64}$'
        AND feature_roster_sha256 ~ '^[0-9a-f]{64}$'
        AND arm_roster_sha256 ~ '^[0-9a-f]{64}$'
        AND fold_roster_sha256 ~ '^[0-9a-f]{64}$'
        AND cost_roster_sha256 ~ '^[0-9a-f]{64}$'
        AND code_content_sha256 ~ '^[0-9a-f]{64}$' AND code_size_bytes >= 0
        AND config_content_sha256 ~ '^[0-9a-f]{64}$' AND config_size_bytes >= 0
        AND provenance_sha256 ~ '^[0-9a-f]{64}$'
        AND definition_sha256 ~ '^[0-9a-f]{64}$'
        AND request_identity ~ '^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$'
        AND request_sha256 ~ '^[0-9a-f]{64}$'
    ),
    ADD CONSTRAINT backtest_run_current_specification_fk FOREIGN KEY (
        exploratory_backtest_run_id, current_specification_sha256
    ) REFERENCES mra.backtest_specification(
        exploratory_backtest_run_id, specification_sha256
    ) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED;

-- Existing historical children stay null in these companion columns. Current
-- writers must provide the exact owning specification hash; the deferred
-- closure validator rejects a mixed historical/current shape.
ALTER TABLE mra.exploratory_backtest_feature
    ADD COLUMN specification_sha256 text,
    ADD CONSTRAINT exploratory_backtest_feature_specification_fk FOREIGN KEY (
        exploratory_backtest_run_id, specification_sha256
    ) REFERENCES mra.backtest_specification(
        exploratory_backtest_run_id, specification_sha256
    ) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    ADD CONSTRAINT exploratory_backtest_feature_specification_shape_ck CHECK (
        specification_sha256 IS NULL
        OR specification_sha256 ~ '^[0-9a-f]{64}$'
    );

ALTER TABLE mra.exploratory_backtest_arm
    ADD COLUMN specification_sha256 text,
    ADD CONSTRAINT exploratory_backtest_arm_specification_fk FOREIGN KEY (
        exploratory_backtest_run_id, specification_sha256
    ) REFERENCES mra.backtest_specification(
        exploratory_backtest_run_id, specification_sha256
    ) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    ADD CONSTRAINT exploratory_backtest_arm_specification_shape_ck CHECK (
        specification_sha256 IS NULL
        OR specification_sha256 ~ '^[0-9a-f]{64}$'
    );

ALTER TABLE mra.exploratory_backtest_fold
    ADD COLUMN specification_sha256 text,
    ADD CONSTRAINT exploratory_backtest_fold_specification_fk FOREIGN KEY (
        exploratory_backtest_run_id, specification_sha256
    ) REFERENCES mra.backtest_specification(
        exploratory_backtest_run_id, specification_sha256
    ) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    ADD CONSTRAINT exploratory_backtest_fold_specification_shape_ck CHECK (
        specification_sha256 IS NULL
        OR specification_sha256 ~ '^[0-9a-f]{64}$'
    );

ALTER TABLE mra.exploratory_backtest_fold_session
    ADD COLUMN specification_sha256 text,
    ADD CONSTRAINT exploratory_backtest_fold_session_specification_fk
    FOREIGN KEY (exploratory_backtest_run_id, specification_sha256)
    REFERENCES mra.backtest_specification(
        exploratory_backtest_run_id, specification_sha256
    ) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    ADD CONSTRAINT exploratory_backtest_fold_session_specification_shape_ck
    CHECK (
        specification_sha256 IS NULL
        OR specification_sha256 ~ '^[0-9a-f]{64}$'
    );

ALTER TABLE mra.exploratory_backtest_cost_assumption
    ADD COLUMN specification_sha256 text,
    ADD COLUMN charge_side text,
    ADD COLUMN exploratory_backtest_arm_id uuid,
    ADD CONSTRAINT exploratory_backtest_cost_specification_fk FOREIGN KEY (
        exploratory_backtest_run_id, specification_sha256
    ) REFERENCES mra.backtest_specification(
        exploratory_backtest_run_id, specification_sha256
    ) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    ADD CONSTRAINT exploratory_backtest_cost_arm_fk FOREIGN KEY (
        exploratory_backtest_arm_id, exploratory_backtest_run_id
    ) REFERENCES mra.exploratory_backtest_arm(
        exploratory_backtest_arm_id, exploratory_backtest_run_id
    ) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    ADD CONSTRAINT exploratory_backtest_cost_current_shape_ck CHECK (
        (specification_sha256 IS NULL
         AND charge_side IS NULL AND exploratory_backtest_arm_id IS NULL)
        OR
        (specification_sha256 ~ '^[0-9a-f]{64}$'
         AND charge_side IN ('BUY', 'SELL', 'BOTH'))
    );

CREATE OR REPLACE FUNCTION mra.guard_evaluation_run_transition()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE actual_access_count integer;
DECLARE actual_observation_count integer;
DECLARE actual_metric_count integer;
DECLARE actual_metric_input_count bigint;
BEGIN
    IF ROW(OLD.evaluation_run_id, OLD.experiment_run_id, OLD.experiment_id,
           OLD.experiment_partition_id, OLD.research_partition_id,
           OLD.evaluation_protocol_id, OLD.target_definition_id,
           OLD.partition_purpose, OLD.requested_knowledge_cutoff,
           OLD.expected_member_count, OLD.expected_protocol_metric_count,
           OLD.code_artifact_id, OLD.code_content_sha256, OLD.code_size_bytes,
           OLD.config_artifact_id, OLD.config_content_sha256,
           OLD.config_size_bytes, OLD.provenance_sha256, OLD.content_sha256,
           OLD.request_identity, OLD.request_sha256, OLD.opened_at)
       IS DISTINCT FROM
       ROW(NEW.evaluation_run_id, NEW.experiment_run_id, NEW.experiment_id,
           NEW.experiment_partition_id, NEW.research_partition_id,
           NEW.evaluation_protocol_id, NEW.target_definition_id,
           NEW.partition_purpose, NEW.requested_knowledge_cutoff,
           NEW.expected_member_count, NEW.expected_protocol_metric_count,
           NEW.code_artifact_id, NEW.code_content_sha256, NEW.code_size_bytes,
           NEW.config_artifact_id, NEW.config_content_sha256,
           NEW.config_size_bytes, NEW.provenance_sha256, NEW.content_sha256,
           NEW.request_identity, NEW.request_sha256, NEW.opened_at) THEN
        RAISE EXCEPTION 'EvaluationRun frozen binding is immutable' USING ERRCODE = '55000';
    END IF;
    IF NOT ((OLD.status = 'OPEN' AND NEW.status IN ('INPUTS_ACQUIRED', 'FAILED'))
         OR (OLD.status = 'INPUTS_ACQUIRED' AND NEW.status IN ('COMPLETED', 'FAILED'))) THEN
        RAISE EXCEPTION 'invalid EvaluationRun lifecycle transition' USING ERRCODE = '55000';
    END IF;
    IF NEW.version <> OLD.version + 1 THEN
        RAISE EXCEPTION 'EvaluationRun version must increment exactly once' USING ERRCODE = '55000';
    END IF;
    IF NEW.status = 'INPUTS_ACQUIRED' THEN
        SELECT count(*) INTO actual_access_count
        FROM mra.research_partition_outcome_access
        WHERE evaluation_run_id = NEW.evaluation_run_id;
        SELECT count(*) INTO actual_observation_count
        FROM mra.evaluation_observation
        WHERE evaluation_run_id = NEW.evaluation_run_id;
        IF actual_access_count <> NEW.expected_member_count
           OR actual_observation_count <> NEW.expected_member_count
           OR NEW.access_count <> actual_access_count
           OR NEW.observation_count <> actual_observation_count
           OR NEW.input_roster_sha256 IS NULL THEN
            RAISE EXCEPTION 'Evaluation input roster does not reconcile' USING ERRCODE = '55000';
        END IF;
    END IF;
    IF NEW.status = 'COMPLETED' THEN
        SELECT count(*) INTO actual_metric_count
        FROM mra.evaluation_metric WHERE evaluation_run_id = NEW.evaluation_run_id;
        SELECT count(*) INTO actual_metric_input_count
        FROM mra.evaluation_metric_observation WHERE evaluation_run_id = NEW.evaluation_run_id;
        IF actual_metric_count <> NEW.expected_protocol_metric_count
           OR actual_metric_input_count <>
              NEW.expected_member_count::bigint * NEW.expected_protocol_metric_count::bigint
           OR NEW.metric_count <> actual_metric_count
           OR NEW.metric_observation_count <> actual_metric_input_count
           OR NEW.metric_roster_sha256 IS NULL THEN
            RAISE EXCEPTION 'Evaluation metric Cartesian roster does not reconcile' USING ERRCODE = '55000';
        END IF;
        IF EXISTS (
            SELECT 1
            FROM mra.evaluation_protocol_metric AS protocol_metric
            WHERE protocol_metric.evaluation_protocol_id =
                  NEW.evaluation_protocol_id
              AND (
                  ((protocol_metric.slice_kind = 'EXPLORATORY_BACKTEST_ARM'
                    OR protocol_metric.source_kind <> 'OUTCOME_METRIC')
                   AND (SELECT count(*)
                        FROM mra.evaluation_backtest_arm_source AS source
                        WHERE source.evaluation_run_id = NEW.evaluation_run_id
                          AND source.evaluation_protocol_metric_id =
                              protocol_metric.evaluation_protocol_metric_id)
                       <> NEW.expected_member_count)
               OR (protocol_metric.source_kind = 'CANDIDATE_DISPOSITION'
                   AND (SELECT count(*)
                        FROM mra.evaluation_candidate_source AS source
                        WHERE source.evaluation_run_id = NEW.evaluation_run_id
                          AND source.evaluation_protocol_metric_id =
                              protocol_metric.evaluation_protocol_metric_id)
                       <> NEW.expected_member_count)
               OR (protocol_metric.source_kind = 'CANDIDATE_OUTCOME_PAIR'
                   AND (SELECT count(*)
                        FROM mra.evaluation_candidate_outcome_source AS source
                        WHERE source.evaluation_run_id = NEW.evaluation_run_id
                          AND source.evaluation_protocol_metric_id =
                              protocol_metric.evaluation_protocol_metric_id)
                       <> NEW.expected_member_count)
               OR (protocol_metric.source_kind = 'SIGNAL_STATUS'
                   AND (SELECT count(*)
                        FROM mra.evaluation_signal_source AS source
                        WHERE source.evaluation_run_id = NEW.evaluation_run_id
                          AND source.evaluation_protocol_metric_id =
                              protocol_metric.evaluation_protocol_metric_id)
                       <> NEW.expected_member_count)
               OR (protocol_metric.source_kind = 'FORECAST_OUTCOME_PAIR'
                   AND (SELECT count(*)
                        FROM mra.evaluation_forecast_source AS source
                        WHERE source.evaluation_run_id = NEW.evaluation_run_id
                          AND source.evaluation_protocol_metric_id =
                              protocol_metric.evaluation_protocol_metric_id)
                       <> NEW.expected_member_count)
               OR (protocol_metric.source_kind IN ('PORTFOLIO_LINE',
                                                    'PORTFOLIO_OUTCOME')
                   AND (SELECT count(*)
                        FROM mra.evaluation_portfolio_source AS source
                        WHERE source.evaluation_run_id = NEW.evaluation_run_id
                          AND source.evaluation_protocol_metric_id =
                              protocol_metric.evaluation_protocol_metric_id)
                       <> NEW.expected_member_count)
               OR (protocol_metric.source_kind = 'RISK_DECISION'
                   AND (SELECT count(*)
                        FROM mra.evaluation_risk_source AS source
                        WHERE source.evaluation_run_id = NEW.evaluation_run_id
                          AND source.evaluation_protocol_metric_id =
                              protocol_metric.evaluation_protocol_metric_id)
                       <> NEW.expected_member_count)
              )
        ) THEN
            RAISE EXCEPTION 'Evaluation canonical source roster does not reconcile'
                USING ERRCODE = '55000';
        END IF;
        IF EXISTS (
            SELECT 1
            FROM mra.evaluation_portfolio_source AS source
            WHERE source.evaluation_run_id = NEW.evaluation_run_id
              AND source.source_measure =
                  'NET_PORTFOLIO_RETURN_ASSUMED_COST'
              AND (
                  source.cost_count IS NULL
                  OR source.cost_roster_sha256 IS NULL
                  OR (SELECT count(*)
                      FROM mra.evaluation_portfolio_cost_source AS cost
                      WHERE cost.evaluation_metric_observation_id =
                            source.evaluation_metric_observation_id)
                     <> source.cost_count
              )
        ) THEN
            RAISE EXCEPTION 'Evaluation assumed-cost source roster does not reconcile'
                USING ERRCODE = '55000';
        END IF;
        IF EXISTS (
            SELECT 1 FROM (
                SELECT source.evaluation_protocol_metric_id,
                       source.source_measure
                FROM mra.evaluation_candidate_source AS source
                WHERE source.evaluation_run_id = NEW.evaluation_run_id
                UNION ALL
                SELECT source.evaluation_protocol_metric_id,
                       source.source_measure
                FROM mra.evaluation_candidate_outcome_source AS source
                WHERE source.evaluation_run_id = NEW.evaluation_run_id
                UNION ALL
                SELECT source.evaluation_protocol_metric_id,
                       source.source_measure
                FROM mra.evaluation_signal_source AS source
                WHERE source.evaluation_run_id = NEW.evaluation_run_id
                UNION ALL
                SELECT source.evaluation_protocol_metric_id,
                       source.source_measure
                FROM mra.evaluation_forecast_source AS source
                WHERE source.evaluation_run_id = NEW.evaluation_run_id
                UNION ALL
                SELECT source.evaluation_protocol_metric_id,
                       source.source_measure
                FROM mra.evaluation_portfolio_source AS source
                WHERE source.evaluation_run_id = NEW.evaluation_run_id
                UNION ALL
                SELECT source.evaluation_protocol_metric_id,
                       source.source_measure
                FROM mra.evaluation_risk_source AS source
                WHERE source.evaluation_run_id = NEW.evaluation_run_id
            ) AS source
            JOIN mra.evaluation_protocol_metric AS metric
              ON metric.evaluation_protocol_metric_id =
                 source.evaluation_protocol_metric_id
            WHERE source.source_measure <> metric.source_measure
        ) THEN
            RAISE EXCEPTION 'Evaluation canonical source measure is mismatched'
                USING ERRCODE = '55000';
        END IF;
        IF EXISTS (
            SELECT 1
            FROM mra.evaluation_backtest_arm_source AS source
            JOIN mra.evaluation_metric_observation AS input
              ON input.evaluation_metric_observation_id =
                 source.evaluation_metric_observation_id
            JOIN mra.evaluation_observation AS observation
              ON observation.evaluation_observation_id =
                 input.evaluation_observation_id
            JOIN mra.research_partition_member AS member
              ON member.research_partition_member_id =
                 observation.research_partition_member_id
            JOIN mra.decision_target_commitment AS commitment
              ON commitment.commitment_id = member.commitment_id
            LEFT JOIN mra.exploratory_retrospective_decision_run AS decision
              ON decision.decision_run_id = commitment.decision_run_id
             AND decision.exploratory_backtest_run_id =
                 source.exploratory_backtest_run_id
             AND decision.exploratory_backtest_arm_id =
                 source.exploratory_backtest_arm_id
             AND decision.exploratory_backtest_fold_id =
                 source.exploratory_backtest_fold_id
             AND decision.exploratory_backtest_fold_session_id =
                 source.exploratory_backtest_fold_session_id
            LEFT JOIN mra.exploratory_backtest_arm AS arm
              ON arm.exploratory_backtest_arm_id =
                 source.exploratory_backtest_arm_id
             AND arm.exploratory_backtest_run_id =
                 source.exploratory_backtest_run_id
             AND arm.arm_kind = source.arm_kind
            WHERE source.evaluation_run_id = NEW.evaluation_run_id
              AND (decision.decision_run_id IS NULL OR arm.exploratory_backtest_arm_id IS NULL)
        ) THEN
            RAISE EXCEPTION 'Evaluation Backtest arm source is not exact'
                USING ERRCODE = '55000';
        END IF;
        IF EXISTS (
            SELECT 1
            FROM mra.evaluation_candidate_source AS source
            JOIN mra.evaluation_metric_observation AS input
              ON input.evaluation_metric_observation_id =
                 source.evaluation_metric_observation_id
            JOIN mra.evaluation_observation AS observation
              ON observation.evaluation_observation_id =
                 input.evaluation_observation_id
            JOIN mra.research_partition_member AS member
              ON member.research_partition_member_id =
                 observation.research_partition_member_id
            LEFT JOIN mra.decision_target_commitment AS commitment
              ON commitment.commitment_id = member.commitment_id
             AND commitment.commitment_id = source.commitment_id
             AND commitment.candidate_id = source.candidate_id
             AND commitment.candidate_disposition = source.disposition
            WHERE source.evaluation_run_id = NEW.evaluation_run_id
              AND commitment.commitment_id IS NULL
        ) THEN
            RAISE EXCEPTION 'Evaluation Candidate source is not exact'
                USING ERRCODE = '55000';
        END IF;
        IF EXISTS (
            SELECT 1
            FROM mra.evaluation_candidate_outcome_source AS source
            JOIN mra.evaluation_metric_observation AS input
              ON input.evaluation_metric_observation_id =
                 source.evaluation_metric_observation_id
            JOIN mra.evaluation_observation AS observation
              ON observation.evaluation_observation_id =
                 input.evaluation_observation_id
            JOIN mra.research_partition_member AS member
              ON member.research_partition_member_id =
                 observation.research_partition_member_id
            JOIN mra.evaluation_protocol_metric AS protocol_metric
              ON protocol_metric.evaluation_protocol_metric_id =
                 source.evaluation_protocol_metric_id
             AND protocol_metric.source_kind = 'CANDIDATE_OUTCOME_PAIR'
             AND protocol_metric.source_measure = source.source_measure
            LEFT JOIN mra.decision_target_commitment AS commitment
              ON commitment.commitment_id = member.commitment_id
             AND commitment.commitment_id = source.commitment_id
             AND commitment.candidate_id = source.candidate_id
             AND commitment.candidate_disposition = source.disposition
            LEFT JOIN mra.candidate AS candidate
              ON candidate.candidate_id = source.candidate_id
             AND candidate.candidate_set_id = source.candidate_set_id
             AND candidate.disposition = source.disposition
             AND candidate.composite_score IS NOT DISTINCT FROM
                 source.composite_score
             AND candidate.competition_rank IS NOT DISTINCT FROM
                 source.competition_rank
            LEFT JOIN mra.market_target_outcome_metric AS outcome_metric
              ON outcome_metric.market_target_outcome_metric_id =
                 source.market_target_outcome_metric_id
             AND outcome_metric.market_target_outcome_revision_id =
                 observation.market_target_outcome_revision_id
             AND outcome_metric.market_target_outcome_revision_id =
                 source.market_target_outcome_revision_id
             AND outcome_metric.target_metric_definition_id =
                 protocol_metric.source_target_metric_definition_id
             AND outcome_metric.decimal_value IS NOT DISTINCT FROM
                 source.outcome_decimal_value
            WHERE source.evaluation_run_id = NEW.evaluation_run_id
              AND (commitment.commitment_id IS NULL
                   OR candidate.candidate_id IS NULL
                   OR outcome_metric.market_target_outcome_metric_id IS NULL)
        ) THEN
            RAISE EXCEPTION 'Evaluation Candidate/Outcome source is not exact'
                USING ERRCODE = '55000';
        END IF;
        IF EXISTS (
            SELECT 1
            FROM mra.evaluation_signal_source AS source
            JOIN mra.evaluation_backtest_arm_source AS backtest
              ON backtest.evaluation_metric_observation_id =
                 source.evaluation_metric_observation_id
            LEFT JOIN mra.signal AS signal
              ON signal.signal_id = source.signal_id
             AND signal.decision_run_id = source.decision_run_id
             AND signal.decision_run_id = backtest.decision_run_id
             AND signal.candidate_id = source.candidate_id
             AND signal.status = source.signal_status
            WHERE source.evaluation_run_id = NEW.evaluation_run_id
              AND signal.signal_id IS NULL
        ) THEN
            RAISE EXCEPTION 'Evaluation Signal source is not exact'
                USING ERRCODE = '55000';
        END IF;
        IF EXISTS (
            SELECT 1
            FROM mra.evaluation_forecast_source AS source
            JOIN mra.evaluation_backtest_arm_source AS backtest
              ON backtest.evaluation_metric_observation_id =
                 source.evaluation_metric_observation_id
            LEFT JOIN mra.forecast AS forecast
              ON forecast.forecast_id = source.forecast_id
             AND forecast.commitment_id = source.commitment_id
             AND forecast.decision_run_id = source.decision_run_id
             AND forecast.decision_run_id = backtest.decision_run_id
             AND forecast.status = source.forecast_status
            LEFT JOIN mra.forecast_estimate AS estimate
              ON estimate.forecast_estimate_id = source.forecast_estimate_id
             AND estimate.forecast_id = forecast.forecast_id
             AND estimate.point_estimate IS NOT DISTINCT FROM
                 source.point_estimate
            WHERE source.evaluation_run_id = NEW.evaluation_run_id
              AND (forecast.forecast_id IS NULL
                   OR estimate.forecast_estimate_id IS NULL)
        ) THEN
            RAISE EXCEPTION 'Evaluation Forecast source is not exact'
                USING ERRCODE = '55000';
        END IF;
        IF EXISTS (
            SELECT 1
            FROM mra.evaluation_portfolio_source AS source
            JOIN mra.evaluation_backtest_arm_source AS backtest
              ON backtest.evaluation_metric_observation_id =
                 source.evaluation_metric_observation_id
            LEFT JOIN mra.portfolio_proposal AS proposal
              ON proposal.portfolio_proposal_id =
                 source.portfolio_proposal_id
             AND proposal.decision_run_id = source.decision_run_id
             AND proposal.decision_run_id = backtest.decision_run_id
            LEFT JOIN mra.portfolio_line AS line
              ON line.portfolio_line_id = source.portfolio_line_id
             AND line.portfolio_proposal_id = proposal.portfolio_proposal_id
             AND line.candidate_id = source.candidate_id
             AND line.status = source.line_status
             AND line.proposed_weight = source.proposed_weight
            LEFT JOIN mra.risk_decision AS risk
              ON risk.risk_decision_id = source.risk_decision_id
             AND risk.portfolio_proposal_id = proposal.portfolio_proposal_id
             AND risk.status = source.risk_status
            WHERE source.evaluation_run_id = NEW.evaluation_run_id
              AND (proposal.portfolio_proposal_id IS NULL
                   OR line.portfolio_line_id IS NULL
                   OR risk.risk_decision_id IS NULL)
        ) THEN
            RAISE EXCEPTION 'Evaluation Portfolio source is not exact'
                USING ERRCODE = '55000';
        END IF;
        IF EXISTS (
            SELECT 1
            FROM mra.evaluation_risk_source AS source
            JOIN mra.evaluation_backtest_arm_source AS backtest
              ON backtest.evaluation_metric_observation_id =
                 source.evaluation_metric_observation_id
            LEFT JOIN mra.risk_decision AS risk
              ON risk.risk_decision_id = source.risk_decision_id
             AND risk.portfolio_proposal_id = source.portfolio_proposal_id
             AND risk.decision_run_id = source.decision_run_id
             AND risk.decision_run_id = backtest.decision_run_id
             AND risk.status = source.risk_status
            WHERE source.evaluation_run_id = NEW.evaluation_run_id
              AND risk.risk_decision_id IS NULL
        ) THEN
            RAISE EXCEPTION 'Evaluation Risk source is not exact'
                USING ERRCODE = '55000';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION mra.validate_current_backtest_specification()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE root mra.exploratory_backtest_run%ROWTYPE;
DECLARE actual_count integer;
DECLARE actual_hash text;
DECLARE actual_distinct_sessions integer;
DECLARE actual_session_bindings integer;
DECLARE expected_definition text;
DECLARE expected_specification text;
DECLARE walk_forward_hash text;
BEGIN
    SELECT * INTO root
      FROM mra.exploratory_backtest_run
     WHERE exploratory_backtest_run_id = NEW.exploratory_backtest_run_id
     FOR SHARE;
    IF root.exploratory_backtest_run_id IS NULL
       OR root.current_specification_sha256 IS DISTINCT FROM
          NEW.specification_sha256 THEN
        RAISE EXCEPTION 'Current Backtest root/specification binding is invalid'
            USING ERRCODE = '55000';
    END IF;
    expected_definition := mra.canonical_sha256(mra.canonical_json_text(
        jsonb_build_object(
            'current_specification_sha256', NEW.specification_sha256,
            'exploratory_backtest_run_id', NEW.exploratory_backtest_run_id,
            'specification_schema_version', NEW.specification_schema_version
        )
    ));
    IF root.definition_sha256 <> expected_definition THEN
        RAISE EXCEPTION 'Current Backtest root definition hash is invalid'
            USING ERRCODE = '55000';
    END IF;
    IF (root.feature_count, root.feature_roster_sha256,
        root.arm_count, root.arm_roster_sha256,
        root.fold_count, root.fold_roster_sha256,
        root.cost_count, root.cost_roster_sha256)
       IS DISTINCT FROM (
        (SELECT count(*) FROM mra.exploratory_backtest_feature
          WHERE exploratory_backtest_run_id = NEW.exploratory_backtest_run_id),
        (SELECT mra.canonical_sha256(mra.canonical_json_text(coalesce(jsonb_agg(
             jsonb_build_object(
                 'feature_definition_id', feature_definition_id,
                 'content_sha256', feature_definition_sha256,
                 'ordinal', feature_ordinal
             ) ORDER BY feature_ordinal), '[]'::jsonb)))
           FROM mra.exploratory_backtest_feature
          WHERE exploratory_backtest_run_id = NEW.exploratory_backtest_run_id),
        (SELECT count(*) FROM mra.exploratory_backtest_arm
          WHERE exploratory_backtest_run_id = NEW.exploratory_backtest_run_id),
        (SELECT mra.canonical_sha256(mra.canonical_json_text(coalesce(jsonb_agg(
             jsonb_build_object(
                 'content_sha256', content_sha256,
                 'exploratory_backtest_arm_id', exploratory_backtest_arm_id,
                 'ordinal', ordinal
             ) ORDER BY ordinal), '[]'::jsonb)))
           FROM mra.exploratory_backtest_arm
          WHERE exploratory_backtest_run_id = NEW.exploratory_backtest_run_id),
        (SELECT count(*) FROM mra.exploratory_backtest_fold
          WHERE exploratory_backtest_run_id = NEW.exploratory_backtest_run_id),
        (SELECT mra.canonical_sha256(mra.canonical_json_text(coalesce(jsonb_agg(
             jsonb_build_object(
                 'content_sha256', content_sha256,
                 'exploratory_backtest_fold_id', exploratory_backtest_fold_id,
                 'ordinal', ordinal
             ) ORDER BY ordinal), '[]'::jsonb)))
           FROM mra.exploratory_backtest_fold
          WHERE exploratory_backtest_run_id = NEW.exploratory_backtest_run_id),
        (SELECT count(*) FROM mra.exploratory_backtest_cost_assumption
          WHERE exploratory_backtest_run_id = NEW.exploratory_backtest_run_id),
        (SELECT mra.canonical_sha256(mra.canonical_json_text(coalesce(jsonb_agg(
             jsonb_build_object(
                 'content_sha256', content_sha256,
                 'assumption_id',
                    exploratory_backtest_cost_assumption_id,
                 'ordinal', ordinal
             ) ORDER BY ordinal), '[]'::jsonb)))
           FROM mra.exploratory_backtest_cost_assumption
          WHERE exploratory_backtest_run_id = NEW.exploratory_backtest_run_id)
    ) THEN
        RAISE EXCEPTION 'Current Backtest root and base child rosters differ'
            USING ERRCODE = '55000', DETAIL = format(
                'feature=%s/%s:%s/%s arm=%s/%s:%s/%s fold=%s/%s:%s/%s cost=%s/%s:%s/%s',
                root.feature_count,
                (SELECT count(*) FROM mra.exploratory_backtest_feature WHERE exploratory_backtest_run_id = NEW.exploratory_backtest_run_id),
                root.feature_roster_sha256,
                (SELECT mra.canonical_sha256(mra.canonical_json_text(coalesce(jsonb_agg(jsonb_build_object('feature_definition_id', feature_definition_id, 'content_sha256', feature_definition_sha256, 'ordinal', feature_ordinal) ORDER BY feature_ordinal), '[]'::jsonb))) FROM mra.exploratory_backtest_feature WHERE exploratory_backtest_run_id = NEW.exploratory_backtest_run_id),
                root.arm_count,
                (SELECT count(*) FROM mra.exploratory_backtest_arm WHERE exploratory_backtest_run_id = NEW.exploratory_backtest_run_id),
                root.arm_roster_sha256,
                (SELECT mra.canonical_sha256(mra.canonical_json_text(coalesce(jsonb_agg(jsonb_build_object('content_sha256', content_sha256, 'exploratory_backtest_arm_id', exploratory_backtest_arm_id, 'ordinal', ordinal) ORDER BY ordinal), '[]'::jsonb))) FROM mra.exploratory_backtest_arm WHERE exploratory_backtest_run_id = NEW.exploratory_backtest_run_id),
                root.fold_count,
                (SELECT count(*) FROM mra.exploratory_backtest_fold WHERE exploratory_backtest_run_id = NEW.exploratory_backtest_run_id),
                root.fold_roster_sha256,
                (SELECT mra.canonical_sha256(mra.canonical_json_text(coalesce(jsonb_agg(jsonb_build_object('content_sha256', content_sha256, 'exploratory_backtest_fold_id', exploratory_backtest_fold_id, 'ordinal', ordinal) ORDER BY ordinal), '[]'::jsonb))) FROM mra.exploratory_backtest_fold WHERE exploratory_backtest_run_id = NEW.exploratory_backtest_run_id),
                root.cost_count,
                (SELECT count(*) FROM mra.exploratory_backtest_cost_assumption WHERE exploratory_backtest_run_id = NEW.exploratory_backtest_run_id),
                root.cost_roster_sha256,
                (SELECT mra.canonical_sha256(mra.canonical_json_text(coalesce(jsonb_agg(jsonb_build_object('content_sha256', content_sha256, 'assumption_id', exploratory_backtest_cost_assumption_id, 'ordinal', ordinal) ORDER BY ordinal), '[]'::jsonb))) FROM mra.exploratory_backtest_cost_assumption WHERE exploratory_backtest_run_id = NEW.exploratory_backtest_run_id)
            );
    END IF;
    IF EXISTS (
        SELECT 1 FROM (
            SELECT exploratory_backtest_run_id, specification_sha256
              FROM mra.exploratory_backtest_feature
            UNION ALL
            SELECT exploratory_backtest_run_id, specification_sha256
              FROM mra.exploratory_backtest_arm
            UNION ALL
            SELECT exploratory_backtest_run_id, specification_sha256
              FROM mra.exploratory_backtest_fold
            UNION ALL
            SELECT exploratory_backtest_run_id, specification_sha256
              FROM mra.exploratory_backtest_fold_session
            UNION ALL
            SELECT exploratory_backtest_run_id, specification_sha256
              FROM mra.exploratory_backtest_cost_assumption
        ) AS child
        WHERE child.exploratory_backtest_run_id =
              NEW.exploratory_backtest_run_id
          AND child.specification_sha256 IS DISTINCT FROM
              NEW.specification_sha256
    ) THEN
        RAISE EXCEPTION 'Current Backtest child lacks exact specification owner'
            USING ERRCODE = '55000';
    END IF;
    SELECT count(*), mra.canonical_sha256(mra.canonical_json_text(coalesce(
        jsonb_agg(jsonb_build_object(
            'content_sha256', content_sha256,
            'universe_revision_member_id', universe_member_id,
            'ordinal', ordinal
        ) ORDER BY ordinal), '[]'::jsonb)))
      INTO actual_count, actual_hash
      FROM mra.backtest_sample_member
     WHERE exploratory_backtest_run_id = NEW.exploratory_backtest_run_id;
    IF (actual_count, actual_hash) IS DISTINCT FROM
       (NEW.sample_member_count, NEW.sample_roster_sha256) THEN
        RAISE EXCEPTION 'Current Backtest sample roster differs'
            USING ERRCODE = '55000';
    END IF;
    IF EXISTS (
        SELECT 1 FROM mra.backtest_sample_member AS member
        JOIN mra.universe_member AS universe_member
          ON universe_member.universe_member_id = member.universe_member_id
         AND universe_member.universe_revision_id = member.universe_revision_id
         AND universe_member.instrument_id = member.instrument_id
        WHERE member.exploratory_backtest_run_id =
              NEW.exploratory_backtest_run_id
          AND (member.universe_revision_id <> NEW.universe_revision_id
               OR universe_member.membership_status <> 'INCLUDED')
    ) THEN
        RAISE EXCEPTION 'Current Backtest sample is outside exact UniverseRevision'
            USING ERRCODE = '55000';
    END IF;
    SELECT count(*), mra.canonical_sha256(mra.canonical_json_text(coalesce(
        jsonb_agg(jsonb_build_object(
            'content_sha256', content_sha256,
            'dependency_id', backtest_fold_dependency_id,
            'ordinal', ordinal
        ) ORDER BY ordinal), '[]'::jsonb)))
      INTO actual_count, actual_hash
      FROM mra.backtest_fold_dependency
     WHERE exploratory_backtest_run_id = NEW.exploratory_backtest_run_id;
    IF (actual_count, actual_hash) IS DISTINCT FROM
       (NEW.fold_dependency_count, NEW.fold_dependency_roster_sha256) THEN
        RAISE EXCEPTION 'Current Backtest FoldDependency roster differs'
            USING ERRCODE = '55000';
    END IF;
    IF EXISTS (
        SELECT 1
          FROM mra.backtest_fold_dependency AS dependency
          JOIN mra.exploratory_backtest_fold AS fit
            ON fit.exploratory_backtest_fold_id = dependency.fit_fold_id
           AND fit.exploratory_backtest_run_id =
               dependency.exploratory_backtest_run_id
          JOIN mra.exploratory_backtest_fold AS validation
            ON validation.exploratory_backtest_fold_id =
               dependency.validation_fold_id
           AND validation.exploratory_backtest_run_id =
               dependency.exploratory_backtest_run_id
         WHERE dependency.exploratory_backtest_run_id =
               NEW.exploratory_backtest_run_id
           AND (fit.purpose <> 'FIT' OR validation.purpose <> 'VALIDATION'
                OR fit.ordinal >= validation.ordinal
                OR (SELECT max(session_date)
                      FROM mra.exploratory_backtest_fold_session
                     WHERE exploratory_backtest_fold_id = fit.exploratory_backtest_fold_id)
                   >= (SELECT min(session_date)
                         FROM mra.exploratory_backtest_fold_session
                        WHERE exploratory_backtest_fold_id = validation.exploratory_backtest_fold_id
                          AND session_role = 'EVALUATION'))
    ) THEN
        RAISE EXCEPTION 'Current Backtest FoldDependency is not strict FIT to VALIDATION'
            USING ERRCODE = '55000';
    END IF;
    IF EXISTS (
        SELECT 1 FROM mra.exploratory_backtest_fold AS validation
        LEFT JOIN mra.backtest_fold_dependency AS dependency
          ON dependency.validation_fold_id =
             validation.exploratory_backtest_fold_id
         AND dependency.exploratory_backtest_run_id =
             validation.exploratory_backtest_run_id
        WHERE validation.exploratory_backtest_run_id =
              NEW.exploratory_backtest_run_id
          AND validation.purpose = 'VALIDATION'
        GROUP BY validation.exploratory_backtest_fold_id
        HAVING count(dependency.backtest_fold_dependency_id) <> 1
    ) THEN
        RAISE EXCEPTION 'Current Backtest VALIDATION lacks one exact FIT dependency'
            USING ERRCODE = '55000';
    END IF;
    SELECT count(*), mra.canonical_sha256(mra.canonical_json_text(coalesce(
        jsonb_agg(jsonb_build_object(
            'content_sha256', content_sha256,
            'arm_fold_id', backtest_arm_fold_id,
            'ordinal', ordinal
        ) ORDER BY ordinal), '[]'::jsonb)))
      INTO actual_count, actual_hash
      FROM mra.backtest_arm_fold
     WHERE exploratory_backtest_run_id = NEW.exploratory_backtest_run_id;
    IF (actual_count, actual_hash) IS DISTINCT FROM
       (NEW.arm_fold_count, NEW.arm_fold_roster_sha256) THEN
        RAISE EXCEPTION 'Current Backtest arm-fold participation roster differs'
            USING ERRCODE = '55000';
    END IF;
    IF EXISTS (
        SELECT 1 FROM mra.exploratory_backtest_arm AS arm
        LEFT JOIN mra.backtest_arm_fold AS participation
          ON participation.exploratory_backtest_arm_id =
             arm.exploratory_backtest_arm_id
         AND participation.exploratory_backtest_run_id =
             arm.exploratory_backtest_run_id
        WHERE arm.exploratory_backtest_run_id =
              NEW.exploratory_backtest_run_id
        GROUP BY arm.exploratory_backtest_arm_id
        HAVING count(participation.backtest_arm_fold_id) = 0
    ) OR EXISTS (
        SELECT 1 FROM mra.exploratory_backtest_fold AS fold
        LEFT JOIN mra.backtest_arm_fold AS participation
          ON participation.exploratory_backtest_fold_id =
             fold.exploratory_backtest_fold_id
         AND participation.exploratory_backtest_run_id =
             fold.exploratory_backtest_run_id
        WHERE fold.exploratory_backtest_run_id =
              NEW.exploratory_backtest_run_id
        GROUP BY fold.exploratory_backtest_fold_id
        HAVING count(participation.backtest_arm_fold_id) = 0
    ) THEN
        RAISE EXCEPTION 'Current Backtest requires non-empty arm and fold participation'
            USING ERRCODE = '55000';
    END IF;
    SELECT count(*), mra.canonical_sha256(mra.canonical_json_text(coalesce(
        jsonb_agg(jsonb_build_object(
            'content_sha256', content_sha256,
            'requirement_id', backtest_model_training_requirement_id,
            'ordinal', ordinal
        ) ORDER BY ordinal), '[]'::jsonb)))
      INTO actual_count, actual_hash
      FROM mra.backtest_model_training_requirement
     WHERE exploratory_backtest_run_id = NEW.exploratory_backtest_run_id;
    IF (actual_count, actual_hash) IS DISTINCT FROM
       (NEW.model_training_requirement_count,
        NEW.model_training_requirement_roster_sha256) THEN
        RAISE EXCEPTION 'Current Backtest Model requirement roster differs'
            USING ERRCODE = '55000';
    END IF;
    IF EXISTS (
        SELECT 1
          FROM mra.backtest_model_training_requirement AS requirement
          JOIN mra.backtest_arm_specification AS arm
            ON arm.exploratory_backtest_arm_id =
               requirement.exploratory_backtest_arm_id
           AND arm.exploratory_backtest_run_id =
               requirement.exploratory_backtest_run_id
           AND arm.specification_sha256 = requirement.specification_sha256
          LEFT JOIN mra.backtest_fold_dependency AS dependency
            ON dependency.fit_fold_id = requirement.fit_fold_id
           AND dependency.validation_fold_id = requirement.validation_fold_id
           AND dependency.exploratory_backtest_run_id =
               requirement.exploratory_backtest_run_id
          LEFT JOIN mra.backtest_arm_fold AS fit_participation
            ON fit_participation.exploratory_backtest_arm_id =
               requirement.exploratory_backtest_arm_id
           AND fit_participation.exploratory_backtest_fold_id =
               requirement.fit_fold_id
          LEFT JOIN mra.backtest_arm_fold AS validation_participation
            ON validation_participation.exploratory_backtest_arm_id =
               requirement.exploratory_backtest_arm_id
           AND validation_participation.exploratory_backtest_fold_id =
               requirement.validation_fold_id
         WHERE requirement.exploratory_backtest_run_id =
               NEW.exploratory_backtest_run_id
           AND (arm.execution_kind <> 'MODEL'
                OR dependency.backtest_fold_dependency_id IS NULL
                OR fit_participation.backtest_arm_fold_id IS NULL
                OR validation_participation.backtest_arm_fold_id IS NULL)
    ) OR EXISTS (
        SELECT 1
          FROM mra.backtest_arm_fold AS validation_participation
          JOIN mra.backtest_arm_specification AS arm
            ON arm.exploratory_backtest_arm_id =
               validation_participation.exploratory_backtest_arm_id
           AND arm.exploratory_backtest_run_id =
               validation_participation.exploratory_backtest_run_id
          JOIN mra.exploratory_backtest_fold AS validation
            ON validation.exploratory_backtest_fold_id =
               validation_participation.exploratory_backtest_fold_id
           AND validation.exploratory_backtest_run_id =
               validation_participation.exploratory_backtest_run_id
          JOIN mra.backtest_fold_dependency AS dependency
            ON dependency.validation_fold_id =
               validation.exploratory_backtest_fold_id
           AND dependency.exploratory_backtest_run_id =
               validation.exploratory_backtest_run_id
          LEFT JOIN mra.backtest_arm_fold AS fit_participation
            ON fit_participation.exploratory_backtest_arm_id =
               arm.exploratory_backtest_arm_id
           AND fit_participation.exploratory_backtest_fold_id =
               dependency.fit_fold_id
          LEFT JOIN mra.backtest_model_training_requirement AS requirement
            ON requirement.exploratory_backtest_arm_id =
               arm.exploratory_backtest_arm_id
           AND requirement.fit_fold_id = dependency.fit_fold_id
           AND requirement.validation_fold_id = dependency.validation_fold_id
         WHERE validation_participation.exploratory_backtest_run_id =
               NEW.exploratory_backtest_run_id
           AND arm.execution_kind = 'MODEL'
           AND (fit_participation.backtest_arm_fold_id IS NULL
                OR requirement.backtest_model_training_requirement_id IS NULL)
    ) THEN
        RAISE EXCEPTION 'Current Backtest Model requirements or participation are incomplete'
            USING ERRCODE = '55000';
    END IF;
    SELECT count(*), mra.canonical_sha256(mra.canonical_json_text(coalesce(
        jsonb_agg(jsonb_build_object(
            'content_sha256', content_sha256,
            'requirement_id', backtest_evaluation_requirement_id,
            'ordinal', ordinal
        ) ORDER BY ordinal), '[]'::jsonb)))
      INTO actual_count, actual_hash
      FROM mra.backtest_evaluation_requirement
     WHERE exploratory_backtest_run_id = NEW.exploratory_backtest_run_id;
    IF (actual_count, actual_hash) IS DISTINCT FROM
       (NEW.evaluation_requirement_count,
        NEW.evaluation_requirement_roster_sha256) THEN
        RAISE EXCEPTION 'Current Backtest Evaluation requirement roster differs'
            USING ERRCODE = '55000';
    END IF;
    IF (SELECT count(*) FROM mra.backtest_arm_specification
         WHERE exploratory_backtest_run_id = NEW.exploratory_backtest_run_id)
       <> root.arm_count THEN
        RAISE EXCEPTION 'Current Backtest Arm specification roster is incomplete'
            USING ERRCODE = '55000';
    END IF;
    IF EXISTS (
        SELECT 1
          FROM mra.exploratory_backtest_arm AS arm
          JOIN mra.backtest_arm_specification AS specification
            ON specification.exploratory_backtest_arm_id =
               arm.exploratory_backtest_arm_id
           AND specification.exploratory_backtest_run_id =
               arm.exploratory_backtest_run_id
         WHERE arm.exploratory_backtest_run_id =
               NEW.exploratory_backtest_run_id
           AND arm.content_sha256 <> mra.canonical_sha256(
               mra.canonical_json_text(jsonb_build_object(
                   'arm_code', arm.arm_kind,
                   'candidate', jsonb_build_object(
                       'authority_id', specification.candidate_policy_id,
                       'content_sha256', specification.candidate_policy_sha256
                   ),
                   'candidate_binding_source',
                       specification.candidate_binding_source,
                   'comparison_role', specification.comparison_role,
                   'context', jsonb_build_object(
                       'authority_id', specification.context_policy_id,
                       'content_sha256', specification.context_policy_sha256
                   ),
                   'context_binding_source',
                       specification.context_binding_source,
                   'context_mode', specification.context_mode,
                   'cost_binding_source', specification.cost_binding_source,
                   'effective_cost_roster_sha256',
                       specification.effective_cost_roster_sha256,
                   'execution_kind', specification.execution_kind,
                   'exploratory_backtest_arm_id',
                       arm.exploratory_backtest_arm_id,
                   'model', CASE
                       WHEN specification.model_id IS NULL THEN 'null'::jsonb
                       ELSE jsonb_build_object(
                           'authority_id', specification.model_id,
                           'content_sha256', specification.model_sha256
                       ) END,
                   'ordinal', arm.ordinal,
                   'portfolio', jsonb_build_object(
                       'authority_id', specification.portfolio_policy_id,
                       'content_sha256', specification.portfolio_policy_sha256
                   ),
                   'portfolio_binding_source',
                       specification.portfolio_binding_source,
                   'risk', jsonb_build_object(
                       'authority_id', specification.risk_policy_id,
                       'content_sha256', specification.risk_policy_sha256
                   ),
                   'risk_binding_source', specification.risk_binding_source,
                   'strategy', jsonb_build_object(
                       'authority_id', specification.strategy_version_id,
                       'content_sha256', specification.strategy_version_sha256
                   ),
                   'strategy_binding_source',
                       specification.strategy_binding_source
               )))
    ) THEN
        RAISE EXCEPTION 'Current Backtest Arm content hash is invalid'
            USING ERRCODE = '55000';
    END IF;
    SELECT count(DISTINCT trading_session_id), count(*)
      INTO actual_distinct_sessions, actual_session_bindings
      FROM mra.exploratory_backtest_fold_session
     WHERE exploratory_backtest_run_id = NEW.exploratory_backtest_run_id;
    IF (actual_distinct_sessions, actual_session_bindings)
       IS DISTINCT FROM
       (NEW.distinct_trading_session_count, NEW.fold_session_binding_count) THEN
        RAISE EXCEPTION 'Current Backtest Session counts differ'
            USING ERRCODE = '55000';
    END IF;
    IF (SELECT trading_session_id
          FROM mra.exploratory_backtest_fold_session
         WHERE exploratory_backtest_run_id = NEW.exploratory_backtest_run_id
         ORDER BY session_date, trading_session_id LIMIT 1)
       IS DISTINCT FROM NEW.first_trading_session_id
       OR (SELECT trading_session_id
             FROM mra.exploratory_backtest_fold_session
            WHERE exploratory_backtest_run_id = NEW.exploratory_backtest_run_id
            ORDER BY session_date DESC, trading_session_id DESC LIMIT 1)
          IS DISTINCT FROM NEW.last_trading_session_id THEN
        RAISE EXCEPTION 'Current Backtest Session range differs'
            USING ERRCODE = '55000';
    END IF;
    IF NEW.sample_seed <> root.random_seed THEN
        RAISE EXCEPTION 'Current Backtest sample seed differs from root seed'
            USING ERRCODE = '55000';
    END IF;
    walk_forward_hash := mra.canonical_sha256(mra.canonical_json_text(
        jsonb_build_object(
            'minimum_fit_sessions', NEW.minimum_fit_sessions,
            'mode', NEW.walk_forward_mode,
            'policy_code', NEW.walk_forward_policy_code,
            'policy_version', NEW.walk_forward_policy_version,
            'step_sessions', NEW.step_sessions,
            'validation_sessions', NEW.minimum_validation_sessions
        )
    ));
    expected_specification := mra.canonical_sha256(mra.canonical_json_text(
        jsonb_build_object(
            'arm_fold_roster_sha256', NEW.arm_fold_roster_sha256,
            'arm_roster_sha256', root.arm_roster_sha256,
            'code_artifact', jsonb_build_object(
                'artifact_id', root.code_artifact_id,
                'content_sha256', root.code_content_sha256,
                'size_bytes', root.code_size_bytes
            ),
            'config_artifact', jsonb_build_object(
                'artifact_id', root.config_artifact_id,
                'content_sha256', root.config_content_sha256,
                'size_bytes', root.config_size_bytes
            ),
            'cost_roster_sha256', root.cost_roster_sha256,
            'defaults', jsonb_build_object(
                'candidate', jsonb_build_object(
                    'authority_id', root.candidate_policy_id,
                    'content_sha256', root.candidate_policy_sha256
                ),
                'context', jsonb_build_object(
                    'authority_id', root.context_policy_id,
                    'content_sha256', root.context_policy_sha256
                ),
                'portfolio', jsonb_build_object(
                    'authority_id', root.portfolio_policy_id,
                    'content_sha256', root.portfolio_policy_sha256
                ),
                'risk', jsonb_build_object(
                    'authority_id', root.risk_policy_id,
                    'content_sha256', root.risk_policy_sha256
                ),
                'strategy', jsonb_build_object(
                    'authority_id', root.strategy_version_id,
                    'content_sha256', root.strategy_version_sha256
                )
            ),
            'definition_version', NEW.definition_version,
            'dependency_roster_sha256',
                NEW.fold_dependency_roster_sha256,
            'distinct_trading_session_count',
                NEW.distinct_trading_session_count,
            'evaluation_roster_sha256',
                NEW.evaluation_requirement_roster_sha256,
            'evidence_ceiling', jsonb_build_object(
                'alpha_proven', NEW.alpha_proven,
                'formal_oos_state', NEW.formal_oos_state,
                'formal_pit_state', NEW.formal_pit_state,
                'formal_provider_state', NEW.formal_provider_state,
                'prospective_proven', NEW.prospective_proven,
                'retrospective', NEW.retrospective_classification
            ),
            'evidence_lane', root.evidence_lane,
            'exchange_code', NEW.exchange_code,
            'exploratory_backtest_run_id',
                NEW.exploratory_backtest_run_id,
            'feature_roster_sha256', root.feature_roster_sha256,
            'first_trading_session_id', NEW.first_trading_session_id,
            'fold_roster_sha256', root.fold_roster_sha256,
            'fold_session_binding_count', NEW.fold_session_binding_count,
            'generation', root.generation,
            'hypothesis', root.hypothesis,
            'last_trading_session_id', NEW.last_trading_session_id,
            'market_archive', jsonb_build_object(
                'authority_id', root.market_archive_id,
                'content_sha256', (SELECT content_sha256
                    FROM mra.market_archive
                    WHERE market_archive_id = root.market_archive_id)
            ),
            'market_archive_seal', jsonb_build_object(
                'authority_id', root.market_archive_seal_id,
                'content_sha256', (SELECT content_sha256
                    FROM mra.market_archive_seal
                    WHERE market_archive_seal_id = root.market_archive_seal_id)
            ),
            'model_training_requirement_roster_sha256',
                NEW.model_training_requirement_roster_sha256,
            'provenance_sha256', root.provenance_sha256,
            'random_seed', root.random_seed,
            'run_code', root.run_code,
            'sample_algorithm_version', NEW.sample_algorithm_version,
            'sample_input_key', NEW.sample_input_key,
            'sample_roster_sha256', NEW.sample_roster_sha256,
            'sample_scope_code', NEW.sample_algorithm_code,
            'specification_schema_version',
                NEW.specification_schema_version,
            'target', jsonb_build_object(
                'authority_id', root.target_definition_id,
                'content_sha256', root.target_definition_sha256,
                'version', root.target_version
            ),
            'universe_revision', jsonb_build_object(
                'authority_id', NEW.universe_revision_id,
                'content_sha256', NEW.universe_scope_sha256
            ),
            'walk_forward_policy', jsonb_build_object(
                'content_sha256', walk_forward_hash,
                'minimum_fit_sessions', NEW.minimum_fit_sessions,
                'mode', NEW.walk_forward_mode,
                'policy_code', NEW.walk_forward_policy_code,
                'policy_version', NEW.walk_forward_policy_version,
                'step_sessions', NEW.step_sessions,
                'validation_sessions', NEW.minimum_validation_sessions
            )
        )
    ));
    IF NEW.specification_sha256 <> expected_specification THEN
        RAISE EXCEPTION 'Current Backtest specification hash is invalid'
            USING ERRCODE = '55000', DETAIL = format(
                'expected=%s observed=%s',
                expected_specification, NEW.specification_sha256
            );
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION mra.validate_evaluation_protocol_metric_source_type()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.source_kind IN ('OUTCOME_METRIC', 'CANDIDATE_OUTCOME_PAIR')
       AND NOT EXISTS (
        SELECT 1
        FROM mra.target_metric_definition AS target_metric
        WHERE target_metric.target_metric_definition_id =
              NEW.source_target_metric_definition_id
          AND target_metric.target_definition_id = NEW.target_definition_id
          AND target_metric.metric_code = NEW.source_metric_code
          AND (NEW.source_kind = 'CANDIDATE_OUTCOME_PAIR'
               AND target_metric.value_type = 'DECIMAL'
               OR NEW.source_kind = 'OUTCOME_METRIC'
               AND target_metric.value_type = NEW.source_value_type)
    ) THEN
        RAISE EXCEPTION 'Outcome Evaluation source type differs from exact Target metric'
            USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION mra.validate_exploratory_backtest_run()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE actual_feature_count integer;
DECLARE actual_feature_hash text;
DECLARE actual_arm_count integer;
DECLARE actual_arm_hash text;
DECLARE actual_fold_count integer;
DECLARE actual_fold_hash text;
DECLARE actual_session_count integer;
DECLARE actual_cost_count integer;
DECLARE actual_cost_hash text;
DECLARE expected_definition text;
BEGIN
    -- Current runs are reconciled by the root-owned specification closure
    -- trigger declared after all current relations. This early return preserves
    -- the byte-for-byte historical validator for nullable legacy companions.
    IF NEW.current_specification_sha256 IS NOT NULL THEN
        RETURN NEW;
    END IF;
    IF NOT EXISTS (
        SELECT 1
        FROM mra.market_archive AS archive
        JOIN mra.market_archive_seal AS seal
          ON seal.market_archive_id = archive.market_archive_id
         AND seal.market_archive_seal_id = NEW.market_archive_seal_id
        JOIN mra.candidate_policy AS candidate
          ON candidate.candidate_policy_id = NEW.candidate_policy_id
         AND candidate.content_sha256 = NEW.candidate_policy_sha256
        JOIN mra.context_policy AS context
          ON context.context_policy_id = NEW.context_policy_id
         AND context.content_sha256 = NEW.context_policy_sha256
        JOIN mra.strategy_version AS strategy
          ON strategy.strategy_version_id = NEW.strategy_version_id
         AND strategy.content_sha256 = NEW.strategy_version_sha256
        JOIN mra.portfolio_policy AS portfolio
          ON portfolio.portfolio_policy_id = NEW.portfolio_policy_id
         AND portfolio.content_sha256 = NEW.portfolio_policy_sha256
        JOIN mra.risk_policy AS risk
          ON risk.risk_policy_id = NEW.risk_policy_id
         AND risk.content_sha256 = NEW.risk_policy_sha256
        WHERE archive.market_archive_id = NEW.market_archive_id
          AND archive.lane = 'RETROSPECTIVE_BACKFILL'
          AND archive.evidence_class = 'EXPLORATORY_RETROSPECTIVE'
    ) THEN
        RAISE EXCEPTION 'Exploratory backtest parent or archive binding is invalid' USING ERRCODE = '55000';
    END IF;
    SELECT count(*), mra.canonical_sha256(mra.canonical_json_text(coalesce(jsonb_agg(
        jsonb_build_object(
            'feature_definition_id', feature_definition_id,
            'feature_definition_sha256', feature_definition_sha256,
            'ordinal', feature_ordinal
        )
        ORDER BY feature_ordinal
    ), '[]'::jsonb)))
      INTO actual_feature_count, actual_feature_hash
      FROM mra.exploratory_backtest_feature
     WHERE exploratory_backtest_run_id = NEW.exploratory_backtest_run_id;
    IF EXISTS (
        SELECT 1 FROM mra.exploratory_backtest_feature AS binding
        LEFT JOIN mra.feature_definition AS feature
          ON feature.feature_definition_id = binding.feature_definition_id
         AND feature.content_sha256 = binding.feature_definition_sha256
        WHERE binding.exploratory_backtest_run_id = NEW.exploratory_backtest_run_id
          AND feature.feature_definition_id IS NULL
    ) THEN
        RAISE EXCEPTION 'Exploratory backtest Feature binding is not exact' USING ERRCODE = '55000';
    END IF;
    SELECT count(*), mra.canonical_sha256(mra.canonical_json_text(coalesce(jsonb_agg(
        jsonb_build_object('content_sha256', content_sha256,
                           'exploratory_backtest_arm_id', exploratory_backtest_arm_id,
                           'ordinal', ordinal) ORDER BY ordinal
    ), '[]'::jsonb)))
      INTO actual_arm_count, actual_arm_hash
      FROM mra.exploratory_backtest_arm
     WHERE exploratory_backtest_run_id = NEW.exploratory_backtest_run_id;
    IF (SELECT array_agg(arm_kind ORDER BY ordinal)
        FROM mra.exploratory_backtest_arm
        WHERE exploratory_backtest_run_id = NEW.exploratory_backtest_run_id)
       <> (CASE WHEN NEW.generation = 1
           THEN ARRAY['RULE_BASELINE', 'MODEL_CHALLENGER']::text[]
           ELSE ARRAY[
               'RULE_CURRENT_CONTEXT', 'RIDGE_CURRENT_CONTEXT',
               'RULE_CONTEXT_OBSERVATIONAL', 'RIDGE_CONTEXT_OBSERVATIONAL'
           ]::text[] END)
       OR (NEW.generation = 1 AND EXISTS (
          SELECT 1 FROM mra.exploratory_backtest_arm
          WHERE exploratory_backtest_run_id = NEW.exploratory_backtest_run_id
            AND content_sha256 <> mra.canonical_sha256(mra.canonical_json_text(jsonb_build_object(
                'exploratory_backtest_arm_id', exploratory_backtest_arm_id,
                'kind', arm_kind, 'ordinal', ordinal
            )))
       )) THEN
        RAISE EXCEPTION 'Exploratory backtest arm roster is invalid' USING ERRCODE = '55000';
    END IF;
    IF (NEW.generation = 1 AND EXISTS (
            SELECT 1 FROM mra.exploratory_backtest_arm_strategy
            WHERE exploratory_backtest_run_id = NEW.exploratory_backtest_run_id
        )) OR (NEW.generation > 1 AND EXISTS (
            SELECT 1
            FROM mra.exploratory_backtest_arm AS arm
            LEFT JOIN mra.exploratory_backtest_arm_strategy AS binding
              ON binding.exploratory_backtest_arm_id = arm.exploratory_backtest_arm_id
             AND binding.exploratory_backtest_run_id = arm.exploratory_backtest_run_id
            WHERE arm.exploratory_backtest_run_id = NEW.exploratory_backtest_run_id
              AND (
                  binding.exploratory_backtest_arm_id IS NULL
                  OR binding.content_sha256 <> arm.content_sha256
                  OR binding.context_mode <> CASE
                      WHEN arm.arm_kind LIKE '%OBSERVATIONAL' THEN 'OBSERVATIONAL'
                      ELSE 'CURRENT_GATE' END
              )
        )) THEN
        RAISE EXCEPTION 'Exploratory backtest arm Strategy roster is incomplete' USING ERRCODE = '55000';
    END IF;
    IF EXISTS (
        SELECT 1
        FROM mra.exploratory_backtest_fold_session AS member
        JOIN mra.exploratory_backtest_fold AS fold
          ON fold.exploratory_backtest_fold_id = member.exploratory_backtest_fold_id
        LEFT JOIN mra.trading_session AS session
          ON session.session_id = member.trading_session_id
         AND session.session_date = member.session_date
         AND session.exchange = fold.exchange_code
        WHERE member.exploratory_backtest_run_id = NEW.exploratory_backtest_run_id
          AND (session.session_id IS NULL OR member.content_sha256 <>
              mra.canonical_sha256(mra.canonical_json_text(jsonb_build_object(
                  'exploratory_backtest_fold_session_id', member.exploratory_backtest_fold_session_id,
                  'ordinal', member.ordinal, 'role', member.session_role,
                  'session_date', member.session_date,
                  'trading_session_id', member.trading_session_id
              ))))
    ) THEN
        RAISE EXCEPTION 'Exploratory backtest session binding is invalid' USING ERRCODE = '55000';
    END IF;
    IF EXISTS (
        WITH ordered AS (
            SELECT member.*,
                   lag(member.session_date) OVER (
                       PARTITION BY member.exploratory_backtest_fold_id ORDER BY member.ordinal
                   ) AS prior_date,
                   lag(CASE member.session_role WHEN 'FIT_INPUT' THEN 1 WHEN 'PURGE' THEN 2
                       WHEN 'EVALUATION' THEN 3 ELSE 4 END) OVER (
                       PARTITION BY member.exploratory_backtest_fold_id ORDER BY member.ordinal
                   ) AS prior_role,
                   CASE member.session_role WHEN 'FIT_INPUT' THEN 1 WHEN 'PURGE' THEN 2
                       WHEN 'EVALUATION' THEN 3 ELSE 4 END AS role_order
            FROM mra.exploratory_backtest_fold_session AS member
            WHERE member.exploratory_backtest_run_id = NEW.exploratory_backtest_run_id
        )
        SELECT 1 FROM ordered
        WHERE (prior_date IS NOT NULL AND session_date <= prior_date)
           OR (prior_role IS NOT NULL AND role_order < prior_role)
    ) THEN
        RAISE EXCEPTION 'Exploratory backtest fold sessions are not chronological' USING ERRCODE = '55000';
    END IF;
    IF EXISTS (
        SELECT 1
        FROM mra.exploratory_backtest_fold AS fold
        LEFT JOIN mra.evaluation_protocol AS protocol
          ON protocol.evaluation_protocol_id = fold.evaluation_protocol_id
         AND protocol.content_sha256 = fold.evaluation_protocol_sha256
         AND protocol.target_definition_id = NEW.target_definition_id
         AND protocol.applicable_purpose = fold.purpose
        WHERE fold.exploratory_backtest_run_id = NEW.exploratory_backtest_run_id
          AND (
            protocol.evaluation_protocol_id IS NULL
            OR fold.session_count <> (SELECT count(*) FROM mra.exploratory_backtest_fold_session AS member WHERE member.exploratory_backtest_fold_id = fold.exploratory_backtest_fold_id)
            OR fold.purge_sessions <> (SELECT count(*) FROM mra.exploratory_backtest_fold_session AS member WHERE member.exploratory_backtest_fold_id = fold.exploratory_backtest_fold_id AND member.session_role = 'PURGE')
            OR fold.embargo_sessions <> (SELECT count(*) FROM mra.exploratory_backtest_fold_session AS member WHERE member.exploratory_backtest_fold_id = fold.exploratory_backtest_fold_id AND member.session_role = 'EMBARGO')
            OR NOT EXISTS (
                SELECT 1 FROM mra.exploratory_backtest_fold_session AS member
                WHERE member.exploratory_backtest_fold_id = fold.exploratory_backtest_fold_id
                  AND member.session_role = CASE
                      WHEN fold.purpose = 'FIT' THEN 'FIT_INPUT'
                      ELSE 'EVALUATION'
                  END
            )
            OR fold.session_roster_sha256 <> (
                SELECT mra.canonical_sha256(mra.canonical_json_text(coalesce(jsonb_agg(
                    jsonb_build_object('content_sha256', member.content_sha256,
                        'exploratory_backtest_fold_session_id', member.exploratory_backtest_fold_session_id,
                        'ordinal', member.ordinal) ORDER BY member.ordinal
                ), '[]'::jsonb)))
                FROM mra.exploratory_backtest_fold_session AS member
                WHERE member.exploratory_backtest_fold_id = fold.exploratory_backtest_fold_id
            )
            OR fold.content_sha256 <> mra.canonical_sha256(mra.canonical_json_text(jsonb_build_object(
                'embargo_sessions', fold.embargo_sessions,
                'evaluation_protocol_id', fold.evaluation_protocol_id,
                'evaluation_protocol_sha256', fold.evaluation_protocol_sha256,
                'exchange_code', fold.exchange_code,
                'exploratory_backtest_fold_id', fold.exploratory_backtest_fold_id,
                'ordinal', fold.ordinal, 'purge_sessions', fold.purge_sessions,
                'purpose', fold.purpose,
                'session_roster_sha256', fold.session_roster_sha256
            )))
          )
    ) THEN
        RAISE EXCEPTION 'Exploratory backtest fold roster is invalid' USING ERRCODE = '55000';
    END IF;
    SELECT count(*), mra.canonical_sha256(mra.canonical_json_text(coalesce(jsonb_agg(
        jsonb_build_object('content_sha256', content_sha256,
            'exploratory_backtest_fold_id', exploratory_backtest_fold_id,
            'ordinal', ordinal) ORDER BY ordinal
    ), '[]'::jsonb)))
      INTO actual_fold_count, actual_fold_hash
      FROM mra.exploratory_backtest_fold
     WHERE exploratory_backtest_run_id = NEW.exploratory_backtest_run_id;
    SELECT count(*) INTO actual_session_count
      FROM mra.exploratory_backtest_fold_session
     WHERE exploratory_backtest_run_id = NEW.exploratory_backtest_run_id;
    IF EXISTS (
        SELECT 1 FROM mra.exploratory_backtest_cost_assumption
        WHERE exploratory_backtest_run_id = NEW.exploratory_backtest_run_id
          AND content_sha256 <> mra.canonical_sha256(mra.canonical_json_text(jsonb_build_object(
              'amount_bps', amount_bps::text, 'cost_kind', cost_kind,
              'exploratory_backtest_cost_assumption_id', exploratory_backtest_cost_assumption_id,
              'ordinal', ordinal
          )))
    ) THEN
        RAISE EXCEPTION 'Exploratory backtest cost roster is invalid' USING ERRCODE = '55000';
    END IF;
    SELECT count(*), mra.canonical_sha256(mra.canonical_json_text(coalesce(jsonb_agg(
        jsonb_build_object('content_sha256', content_sha256,
            'exploratory_backtest_cost_assumption_id', exploratory_backtest_cost_assumption_id,
            'ordinal', ordinal) ORDER BY ordinal
    ), '[]'::jsonb)))
      INTO actual_cost_count, actual_cost_hash
      FROM mra.exploratory_backtest_cost_assumption
     WHERE exploratory_backtest_run_id = NEW.exploratory_backtest_run_id;
    IF (NEW.feature_count, NEW.feature_roster_sha256,
        NEW.arm_count, NEW.arm_roster_sha256,
        NEW.fold_count, NEW.fold_roster_sha256, NEW.session_count,
        NEW.cost_count, NEW.cost_roster_sha256)
       IS DISTINCT FROM
       (actual_feature_count, actual_feature_hash,
        actual_arm_count, actual_arm_hash,
        actual_fold_count, actual_fold_hash, actual_session_count,
        actual_cost_count, actual_cost_hash) THEN
        RAISE EXCEPTION 'Exploratory backtest root and child rosters differ' USING ERRCODE = '55000';
    END IF;
    expected_definition := mra.canonical_sha256(mra.canonical_json_text(jsonb_build_object(
        'arm_roster_sha256', NEW.arm_roster_sha256,
        'candidate_policy_id', NEW.candidate_policy_id,
        'candidate_policy_sha256', NEW.candidate_policy_sha256,
        'code_artifact', jsonb_build_object('artifact_id', NEW.code_artifact_id,
            'content_sha256', NEW.code_content_sha256, 'size_bytes', NEW.code_size_bytes),
        'config_artifact', jsonb_build_object('artifact_id', NEW.config_artifact_id,
            'content_sha256', NEW.config_content_sha256, 'size_bytes', NEW.config_size_bytes),
        'context_policy_id', NEW.context_policy_id,
        'context_policy_sha256', NEW.context_policy_sha256,
        'cost_roster_sha256', NEW.cost_roster_sha256,
        'evidence_lane', NEW.evidence_lane,
        'exploratory_backtest_run_id', NEW.exploratory_backtest_run_id,
        'feature_roster_sha256', NEW.feature_roster_sha256,
        'fold_roster_sha256', NEW.fold_roster_sha256,
        'generation', NEW.generation, 'hypothesis', NEW.hypothesis,
        'market_archive_id', NEW.market_archive_id,
        'market_archive_seal_id', NEW.market_archive_seal_id,
        'portfolio_policy_id', NEW.portfolio_policy_id,
        'portfolio_policy_sha256', NEW.portfolio_policy_sha256,
        'provenance_sha256', NEW.provenance_sha256,
        'random_seed', NEW.random_seed, 'risk_policy_id', NEW.risk_policy_id,
        'risk_policy_sha256', NEW.risk_policy_sha256,
        'session_count', NEW.session_count,
        'strategy_version_id', NEW.strategy_version_id,
        'strategy_version_sha256', NEW.strategy_version_sha256,
        'target_definition_id', NEW.target_definition_id,
        'target_definition_sha256', NEW.target_definition_sha256,
        'target_version', NEW.target_version
    )));
    IF NEW.definition_sha256 <> expected_definition THEN
        RAISE EXCEPTION 'Exploratory backtest definition hash is invalid' USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION mra.validate_forecast_model_binding()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE expected_input text;
DECLARE expected_output text;
DECLARE expected_content text;
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM mra.forecast AS forecast
        JOIN mra.forecast_estimate AS estimate
          ON estimate.forecast_estimate_id = NEW.forecast_estimate_id
         AND estimate.forecast_id = forecast.forecast_id
         AND estimate.forecast_group_id = forecast.forecast_group_id
         AND estimate.decision_run_id = forecast.decision_run_id
         AND estimate.strategy_version_id = forecast.strategy_version_id
         AND estimate.target_metric_definition_id =
             NEW.target_metric_definition_id
         AND estimate.content_sha256 =
             NEW.forecast_estimate_content_sha256
        JOIN mra.exploratory_retrospective_decision_run AS decision
          ON decision.decision_run_id = forecast.decision_run_id
         AND decision.dataset_id = NEW.dataset_id
         AND decision.exploratory_backtest_run_id =
             NEW.exploratory_backtest_run_id
         AND decision.exploratory_backtest_arm_id =
             NEW.exploratory_backtest_arm_id
         AND decision.exploratory_backtest_fold_id =
             NEW.exploratory_backtest_fold_id
         AND decision.exploratory_backtest_fold_session_id =
             NEW.exploratory_backtest_fold_session_id
        JOIN mra.exploratory_backtest_arm AS inference_arm
          ON inference_arm.exploratory_backtest_arm_id =
             decision.exploratory_backtest_arm_id
         AND inference_arm.exploratory_backtest_run_id =
             decision.exploratory_backtest_run_id
         AND inference_arm.arm_kind IN (
             'MODEL_CHALLENGER', 'RIDGE_CURRENT_CONTEXT',
             'RIDGE_CONTEXT_OBSERVATIONAL'
         )
        JOIN mra.exploratory_backtest_fold AS inference_fold
          ON inference_fold.exploratory_backtest_fold_id =
             decision.exploratory_backtest_fold_id
         AND inference_fold.exploratory_backtest_run_id =
             decision.exploratory_backtest_run_id
         AND inference_fold.ordinal = NEW.inference_fold_ordinal
         AND inference_fold.purpose IN ('DISCOVERY', 'VALIDATION')
        JOIN mra.exploratory_backtest_fold_session AS inference_session
          ON inference_session.exploratory_backtest_fold_session_id =
             decision.exploratory_backtest_fold_session_id
         AND inference_session.exploratory_backtest_fold_id =
             inference_fold.exploratory_backtest_fold_id
         AND inference_session.session_role = 'EVALUATION'
        JOIN mra.model_version AS version
          ON version.model_version_id = NEW.model_version_id
         AND version.model_id = NEW.model_id
         AND version.model_training_run_id = NEW.model_training_run_id
         AND version.fitted_model_artifact_id =
             NEW.fitted_model_artifact_id
         AND version.fitted_model_content_sha256 =
             NEW.fitted_model_content_sha256
         AND version.fitted_model_size_bytes =
             NEW.fitted_model_size_bytes
         AND version.registered_at = NEW.model_registered_at
         AND version.content_sha256 = NEW.model_version_sha256
        JOIN mra.model_training_run AS training
          ON training.model_training_run_id = version.model_training_run_id
         AND training.model_id = version.model_id
         AND training.exploratory_backtest_run_id =
             decision.exploratory_backtest_run_id
         AND training.exploratory_backtest_arm_id =
             decision.exploratory_backtest_arm_id
         AND training.exploratory_backtest_fold_id = NEW.training_fold_id
        JOIN mra.exploratory_backtest_fold AS training_fold
          ON training_fold.exploratory_backtest_fold_id =
             training.exploratory_backtest_fold_id
         AND training_fold.exploratory_backtest_run_id =
             training.exploratory_backtest_run_id
         AND training_fold.ordinal = NEW.training_fold_ordinal
         AND training_fold.purpose = 'FIT'
        JOIN mra.model AS model
          ON model.model_id = version.model_id
         AND model.target_definition_id = forecast.target_definition_id
        JOIN mra.evaluation_protocol_metric AS training_metric
          ON training_metric.evaluation_protocol_metric_id =
             training.evaluation_protocol_metric_id
         AND training_metric.source_target_metric_definition_id =
             estimate.target_metric_definition_id
        JOIN mra.decision_run AS decision_root
          ON decision_root.decision_run_id = forecast.decision_run_id
        WHERE forecast.forecast_id = NEW.forecast_id
          AND forecast.forecast_group_id = NEW.forecast_group_id
          AND forecast.decision_run_id = NEW.decision_run_id
          AND forecast.strategy_version_id = NEW.strategy_version_id
          AND forecast.commitment_id = NEW.commitment_id
          AND forecast.status = NEW.status
          AND forecast.calibration_status = NEW.calibration_status
          AND forecast.reason_code = NEW.reason_code
          AND estimate.point_estimate IS NOT DISTINCT FROM NEW.point_estimate
          AND forecast.recorded_at = NEW.forecast_recorded_at
          AND version.registered_at < forecast.recorded_at
          AND training_fold.ordinal < inference_fold.ordinal
          AND NOT EXISTS (
              SELECT 1
              FROM mra.model_training_sample AS sample
              JOIN mra.decision_run AS training_decision
                ON training_decision.decision_run_id = sample.decision_run_id
              WHERE sample.model_training_run_id =
                    training.model_training_run_id
                AND training_decision.decision_time >=
                    decision_root.decision_time
          )
    ) THEN
        RAISE EXCEPTION 'Forecast ModelVersion lineage is not later-generation exact'
            USING ERRCODE = '55000';
    END IF;

    expected_input := mra.canonical_sha256(mra.canonical_json_text(
        jsonb_build_object(
            'dataset_id', NEW.dataset_id,
            'feature_vector_sha256', NEW.feature_vector_sha256,
            'fitted_model_artifact_id', NEW.fitted_model_artifact_id,
            'fitted_model_content_sha256',
                NEW.fitted_model_content_sha256,
            'fitted_model_size_bytes', NEW.fitted_model_size_bytes,
            'model_version_id', NEW.model_version_id,
            'model_version_sha256', NEW.model_version_sha256
        )
    ));
    expected_output := mra.canonical_sha256(mra.canonical_json_text(
        jsonb_build_object(
            'forecast_estimate_id', NEW.forecast_estimate_id,
            'point_estimate', NEW.point_estimate::text,
            'reason_code', NEW.reason_code,
            'state', NEW.status
        )
    ));
    expected_content := mra.canonical_sha256(mra.canonical_json_text(
        jsonb_build_object(
            'commitment_id', NEW.commitment_id,
            'dataset_id', NEW.dataset_id,
            'decision_run_id', NEW.decision_run_id,
            'exploratory_backtest_arm_id',
                NEW.exploratory_backtest_arm_id,
            'exploratory_backtest_fold_id',
                NEW.exploratory_backtest_fold_id,
            'exploratory_backtest_fold_session_id',
                NEW.exploratory_backtest_fold_session_id,
            'exploratory_backtest_run_id',
                NEW.exploratory_backtest_run_id,
            'forecast_group_id', NEW.forecast_group_id,
            'forecast_id', NEW.forecast_id,
            'forecast_estimate_content_sha256',
                NEW.forecast_estimate_content_sha256,
            'forecast_model_binding_id', NEW.forecast_model_binding_id,
            'inference_fold_ordinal', NEW.inference_fold_ordinal,
            'inference_input_sha256', NEW.inference_input_sha256,
            'inference_output_sha256', NEW.inference_output_sha256,
            'model_id', NEW.model_id,
            'model_registered_at',
                mra.canonical_timestamptz_text(NEW.model_registered_at),
            'model_training_run_id', NEW.model_training_run_id,
            'model_version_id', NEW.model_version_id,
            'model_version_sha256', NEW.model_version_sha256,
            'prediction_state', NEW.status,
            'reason_code', NEW.reason_code,
            'training_fold_id', NEW.training_fold_id,
            'training_fold_ordinal', NEW.training_fold_ordinal,
            'target_metric_definition_id',
                NEW.target_metric_definition_id
        )
    ));
    IF NEW.inference_input_sha256 <> expected_input
       OR NEW.inference_output_sha256 <> expected_output
       OR NEW.content_sha256 <> expected_content THEN
        RAISE EXCEPTION 'Forecast Model binding hash is invalid'
            USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION mra.validate_model_training_run()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE actual_count integer;
DECLARE actual_estimable integer;
DECLARE actual_roster text;
DECLARE derived_count integer;
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM mra.model AS model
        JOIN mra.evaluation_run AS evaluation
          ON evaluation.evaluation_run_id = NEW.evaluation_run_id
         AND evaluation.target_definition_id = model.target_definition_id
         AND evaluation.status = 'COMPLETED'
         AND evaluation.partition_purpose = 'FIT'
         AND evaluation.completed_at < NEW.opened_at
        JOIN mra.evaluation_protocol_metric AS metric
          ON metric.evaluation_protocol_metric_id =
             NEW.evaluation_protocol_metric_id
         AND metric.evaluation_protocol_id = evaluation.evaluation_protocol_id
         AND metric.source_value_type = 'DECIMAL'
        JOIN mra.exploratory_backtest_run AS backtest
          ON backtest.exploratory_backtest_run_id =
             NEW.exploratory_backtest_run_id
         AND backtest.target_definition_id = model.target_definition_id
         AND backtest.evidence_lane = 'EXPLORATORY_RETROSPECTIVE'
         AND backtest.feature_count = model.feature_count
         AND backtest.feature_roster_sha256 = model.feature_roster_sha256
        JOIN mra.exploratory_backtest_arm AS arm
          ON arm.exploratory_backtest_arm_id = NEW.exploratory_backtest_arm_id
         AND arm.exploratory_backtest_run_id =
             backtest.exploratory_backtest_run_id
         AND arm.arm_kind IN (
             'MODEL_CHALLENGER', 'RIDGE_CURRENT_CONTEXT',
             'RIDGE_CONTEXT_OBSERVATIONAL'
         )
        JOIN mra.exploratory_backtest_fold AS fold
          ON fold.exploratory_backtest_fold_id = NEW.exploratory_backtest_fold_id
         AND fold.exploratory_backtest_run_id =
             backtest.exploratory_backtest_run_id
         AND fold.purpose = 'FIT'
         AND fold.evaluation_protocol_id = evaluation.evaluation_protocol_id
        WHERE model.model_id = NEW.model_id
          AND model.target_definition_id = NEW.target_definition_id
    ) THEN
        RAISE EXCEPTION 'Model training parent graph is invalid'
            USING ERRCODE = '55000';
    END IF;

    SELECT count(*)::integer,
           count(*) FILTER (WHERE sample_state = 'ESTIMABLE')::integer,
           mra.canonical_sha256(mra.canonical_json_text(jsonb_agg(
               jsonb_build_object(
                   'content_sha256', content_sha256,
                   'model_training_sample_id', model_training_sample_id,
                   'ordinal', ordinal
               ) ORDER BY ordinal
           )))
      INTO actual_count, actual_estimable, actual_roster
      FROM mra.model_training_sample
     WHERE model_training_run_id = NEW.model_training_run_id;
    IF actual_count <> NEW.sample_count
       OR actual_estimable <> NEW.estimable_count
       OR actual_roster IS DISTINCT FROM NEW.sample_roster_sha256 THEN
        RAISE EXCEPTION 'Model training sample roster is incomplete or changed'
            USING ERRCODE = '55000';
    END IF;

    SELECT count(*)::integer INTO derived_count
      FROM mra.evaluation_observation AS observation
      JOIN mra.evaluation_metric_observation AS input
        ON input.evaluation_run_id = observation.evaluation_run_id
       AND input.evaluation_observation_id =
           observation.evaluation_observation_id
       AND input.evaluation_protocol_metric_id =
           NEW.evaluation_protocol_metric_id
     WHERE observation.evaluation_run_id = NEW.evaluation_run_id;
    IF derived_count <> NEW.sample_count OR EXISTS (
        SELECT 1
        FROM mra.evaluation_observation AS observation
        JOIN mra.evaluation_metric_observation AS input
          ON input.evaluation_run_id = observation.evaluation_run_id
         AND input.evaluation_observation_id =
             observation.evaluation_observation_id
         AND input.evaluation_protocol_metric_id =
             NEW.evaluation_protocol_metric_id
        LEFT JOIN mra.model_training_sample AS sample
          ON sample.model_training_run_id = NEW.model_training_run_id
         AND sample.evaluation_observation_id =
             observation.evaluation_observation_id
         AND sample.evaluation_metric_observation_id =
             input.evaluation_metric_observation_id
       WHERE observation.evaluation_run_id = NEW.evaluation_run_id
         AND sample.model_training_sample_id IS NULL
    ) THEN
        RAISE EXCEPTION 'Model training omitted a FIT Evaluation member'
            USING ERRCODE = '55000';
    END IF;

    IF EXISTS (
        SELECT 1 FROM mra.model_training_sample AS sample
        WHERE sample.model_training_run_id = NEW.model_training_run_id
          AND NOT EXISTS (
              SELECT 1
              FROM mra.research_partition_member AS member
              JOIN mra.decision_target_commitment AS commitment
                ON commitment.commitment_id = member.commitment_id
              JOIN mra.candidate_set AS candidate_set
                ON candidate_set.candidate_set_id = commitment.candidate_set_id
               AND candidate_set.dataset_id = sample.dataset_id
              JOIN mra.exploratory_backtest_dataset AS dataset
                ON dataset.dataset_id = sample.dataset_id
               AND dataset.exploratory_backtest_run_id =
                   NEW.exploratory_backtest_run_id
               AND dataset.exploratory_backtest_arm_id =
                   NEW.exploratory_backtest_arm_id
               AND dataset.exploratory_backtest_fold_id =
                   NEW.exploratory_backtest_fold_id
              JOIN mra.exploratory_backtest_fold_session AS session
                ON session.exploratory_backtest_fold_session_id =
                   dataset.exploratory_backtest_fold_session_id
               AND session.session_role = 'FIT_INPUT'
              JOIN mra.market_target_outcome_metric AS outcome_metric
                ON outcome_metric.market_target_outcome_metric_id =
                   sample.source_outcome_metric_id
               AND outcome_metric.market_target_outcome_revision_id =
                   sample.market_target_outcome_revision_id
              JOIN mra.evaluation_protocol_metric AS protocol_metric
                ON protocol_metric.evaluation_protocol_metric_id =
                   NEW.evaluation_protocol_metric_id
               AND protocol_metric.source_target_metric_definition_id =
                   outcome_metric.target_metric_definition_id
              WHERE member.research_partition_member_id =
                    sample.research_partition_member_id
                AND member.commitment_id = sample.commitment_id
                AND commitment.commitment_id = sample.commitment_id
                AND commitment.decision_run_id = sample.decision_run_id
                AND commitment.candidate_id = sample.candidate_id
                AND commitment.instrument_id = sample.instrument_id
          )
    ) THEN
        RAISE EXCEPTION 'Model training sample lineage is invalid'
            USING ERRCODE = '55000';
    END IF;
    IF EXISTS (
        SELECT 1
        FROM mra.model_training_sample AS sample
        JOIN mra.market_target_outcome_metric AS outcome_metric
          ON outcome_metric.market_target_outcome_metric_id =
             sample.source_outcome_metric_id
        WHERE sample.model_training_run_id = NEW.model_training_run_id
          AND sample.sample_state = 'ESTIMABLE'
          AND (
              sample.evaluation_input_state <> 'INCLUDED'
              OR outcome_metric.value_status NOT IN ('COMPLETE', 'PARTIAL')
              OR outcome_metric.decimal_value IS DISTINCT FROM
                 sample.target_value
          )
    ) THEN
        RAISE EXCEPTION 'Model training target value differs from Evaluation input'
            USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION mra.validate_prospective_archive_generation()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE decision_date date;
DECLARE outcome_date date;
DECLARE later_date date;
DECLARE outcome_offset integer;
DECLARE expected_content text;
BEGIN
    SELECT decision.session_date, outcome.session_date, later.session_date,
           outcome_checkpoint.session_offset
      INTO decision_date, outcome_date, later_date, outcome_offset
      FROM mra.market_archive AS archive
      JOIN mra.trading_session AS decision
        ON decision.session_id = NEW.decision_session_id
       AND decision.exchange = NEW.exchange_code
      JOIN mra.trading_session AS outcome
        ON outcome.session_id = NEW.outcome_session_id
       AND outcome.exchange = NEW.exchange_code
      JOIN mra.trading_session AS later
        ON later.session_id = NEW.later_verification_session_id
       AND later.exchange = NEW.exchange_code
      JOIN mra.target_checkpoint AS reference_checkpoint
        ON reference_checkpoint.target_checkpoint_id = NEW.reference_checkpoint_id
       AND reference_checkpoint.target_definition_id = NEW.target_definition_id
       AND reference_checkpoint.checkpoint_role = 'DECISION_REFERENCE'
       AND reference_checkpoint.session_offset = 0
      JOIN mra.target_checkpoint AS outcome_checkpoint
        ON outcome_checkpoint.target_checkpoint_id = NEW.outcome_checkpoint_id
       AND outcome_checkpoint.target_definition_id = NEW.target_definition_id
       AND outcome_checkpoint.checkpoint_role = 'OUTCOME_OBSERVATION'
       AND outcome_checkpoint.session_offset > 0
     WHERE archive.market_archive_id = NEW.market_archive_id
       AND archive.lane = 'PROSPECTIVE_CONTEMPORANEOUS'
       AND archive.evidence_class = 'FIRST_PARTY_CONTEMPORANEOUS'
       AND archive.exchange_code = NEW.exchange_code;
    IF decision_date IS NULL OR NOT decision_date < outcome_date
       OR NOT outcome_date < later_date
       OR (SELECT count(*) FROM mra.trading_session
           WHERE exchange = NEW.exchange_code
             AND session_date > decision_date
             AND session_date <= outcome_date) <> outcome_offset THEN
        RAISE EXCEPTION 'Prospective generation Target/TradingSession binding is invalid'
            USING ERRCODE = '55000';
    END IF;
    IF NEW.generation > 1 AND NOT EXISTS (
        SELECT 1 FROM mra.prospective_archive_generation AS prior
        WHERE prior.market_archive_id = NEW.predecessor_market_archive_id
          AND prior.series_code = NEW.series_code
          AND prior.generation = NEW.generation - 1
          AND prior.exchange_code = NEW.exchange_code
          AND prior.target_definition_id = NEW.target_definition_id
          AND prior.target_version = NEW.target_version
          AND prior.target_definition_sha256 = NEW.target_definition_sha256
          AND prior.decision_session_id <> NEW.decision_session_id
          AND prior.member_roster_sha256 = NEW.member_roster_sha256
    ) THEN
        RAISE EXCEPTION 'Prospective generation predecessor is not exact'
            USING ERRCODE = '55000';
    END IF;
    expected_content := mra.canonical_sha256(mra.canonical_json_text(jsonb_build_object(
        'decision_session_id', NEW.decision_session_id,
        'exchange', NEW.exchange_code,
        'generation', NEW.generation,
        'later_verification_session_id', NEW.later_verification_session_id,
        'market_archive_id', NEW.market_archive_id,
        'member_roster_sha256', NEW.member_roster_sha256,
        'outcome_checkpoint_id', NEW.outcome_checkpoint_id,
        'outcome_session_id', NEW.outcome_session_id,
        'predecessor_market_archive_id', NEW.predecessor_market_archive_id,
        'provenance_sha256', NEW.provenance_sha256,
        'reference_checkpoint_id', NEW.reference_checkpoint_id,
        'schedule_roster_sha256', NEW.schedule_roster_sha256,
        'series_code', NEW.series_code,
        'target_definition_id', NEW.target_definition_id,
        'target_definition_sha256', NEW.target_definition_sha256,
        'target_version', NEW.target_version
    )));
    IF NEW.content_sha256 <> expected_content THEN
        RAISE EXCEPTION 'Prospective generation content hash is invalid'
            USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION mra.validate_prospective_archive_member()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE expected_content text;
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM mra.prospective_archive_generation AS generation
        JOIN mra.instrument AS instrument
          ON instrument.instrument_id = NEW.instrument_id
         AND instrument.exchange = generation.exchange_code
        JOIN mra.instrument_identifier AS identifier
          ON identifier.instrument_identifier_id = NEW.instrument_identifier_id
         AND identifier.instrument_id = instrument.instrument_id
        WHERE generation.market_archive_id = NEW.market_archive_id
    ) THEN
        RAISE EXCEPTION 'Prospective archive member identity/exchange is invalid'
            USING ERRCODE = '55000';
    END IF;
    expected_content := mra.canonical_sha256(mra.canonical_json_text(jsonb_build_object(
        'instrument_id', NEW.instrument_id,
        'instrument_identifier_id', NEW.instrument_identifier_id,
        'ordinal', NEW.ordinal
    )));
    IF NEW.content_sha256 <> expected_content THEN
        RAISE EXCEPTION 'Prospective archive member hash is invalid'
            USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION mra.validate_prospective_archive_planning_gap()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE expected_content text;
BEGIN
    IF NEW.expected_generation > 1 AND NOT EXISTS (
        SELECT 1
        FROM mra.prospective_archive_generation AS predecessor
        WHERE predecessor.market_archive_id = NEW.predecessor_market_archive_id
          AND predecessor.series_code = NEW.series_code
          AND predecessor.generation = NEW.expected_generation - 1
          AND predecessor.target_definition_id = NEW.target_definition_id
          AND predecessor.target_version = NEW.target_version
          AND predecessor.target_definition_sha256 = NEW.target_definition_sha256
    ) THEN
        RAISE EXCEPTION 'Prospective planning gap predecessor is not exact'
            USING ERRCODE = '55000';
    END IF;
    expected_content := mra.canonical_sha256(mra.canonical_json_text(jsonb_build_object(
        'detected_at', NEW.detected_at,
        'expected_decision_session_id', NEW.expected_decision_session_id,
        'expected_generation', NEW.expected_generation,
        'predecessor_market_archive_id', NEW.predecessor_market_archive_id,
        'prospective_archive_planning_gap_id', NEW.prospective_archive_planning_gap_id,
        'reason_code', NEW.reason_code,
        'series_code', NEW.series_code,
        'target_definition_id', NEW.target_definition_id,
        'target_definition_sha256', NEW.target_definition_sha256,
        'target_version', NEW.target_version
    )));
    IF NEW.content_sha256 <> expected_content THEN
        RAISE EXCEPTION 'Prospective planning gap hash is invalid'
            USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION mra.validate_prospective_archive_revision()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE observation mra.market_archive_capture_observation%ROWTYPE;
DECLARE schedule mra.prospective_archive_slice_schedule%ROWTYPE;
DECLARE prior mra.prospective_archive_revision_observation%ROWTYPE;
DECLARE expected_relation text;
DECLARE expected_content text;
BEGIN
    SELECT * INTO observation FROM mra.market_archive_capture_observation
    WHERE market_archive_capture_observation_id = NEW.market_archive_capture_observation_id
    FOR SHARE;
    SELECT * INTO schedule FROM mra.prospective_archive_slice_schedule
    WHERE market_archive_slice_id = NEW.market_archive_slice_id FOR SHARE;
    SELECT * INTO prior FROM mra.prospective_archive_revision_observation
    WHERE market_archive_id = NEW.market_archive_id
      AND instrument_id = NEW.instrument_id
      AND target_checkpoint_id = NEW.target_checkpoint_id
    ORDER BY comparison_ordinal DESC LIMIT 1 FOR SHARE;
    expected_relation := CASE
        WHEN prior.market_archive_capture_observation_id IS NULL THEN 'FIRST'
        WHEN prior.artifact_sha256 = observation.artifact_sha256
         AND prior.normalized_revision_roster_sha256 = observation.normalized_revision_roster_sha256
            THEN 'IDENTICAL'
        ELSE 'CHANGED' END;
    IF observation.market_archive_id <> NEW.market_archive_id
       OR observation.market_archive_slice_id <> NEW.market_archive_slice_id
       OR schedule.instrument_id <> NEW.instrument_id
       OR schedule.target_checkpoint_id <> NEW.target_checkpoint_id
       OR schedule.comparison_ordinal <> NEW.comparison_ordinal
       OR NEW.artifact_sha256 <> observation.artifact_sha256
       OR NEW.normalized_revision_roster_sha256 <> observation.normalized_revision_roster_sha256
       OR NEW.relation <> expected_relation
       OR (prior.market_archive_capture_observation_id IS NULL AND NEW.predecessor_observation_id IS NOT NULL)
       OR (prior.market_archive_capture_observation_id IS NOT NULL AND (
            NEW.predecessor_observation_id <> prior.market_archive_capture_observation_id
            OR NEW.comparison_ordinal <> prior.comparison_ordinal + 1
       )) THEN
        RAISE EXCEPTION 'Prospective archive revision chain is invalid'
            USING ERRCODE = '55000';
    END IF;
    expected_content := mra.canonical_sha256(mra.canonical_json_text(jsonb_build_object(
        'artifact_sha256', NEW.artifact_sha256,
        'comparison_ordinal', NEW.comparison_ordinal,
        'instrument_id', NEW.instrument_id,
        'market_archive_capture_observation_id', NEW.market_archive_capture_observation_id,
        'market_archive_id', NEW.market_archive_id,
        'market_archive_slice_id', NEW.market_archive_slice_id,
        'target_checkpoint_id', NEW.target_checkpoint_id,
        'normalized_revision_roster_sha256', NEW.normalized_revision_roster_sha256,
        'predecessor_observation_id', NEW.predecessor_observation_id,
        'relation', NEW.relation
    )));
    IF NEW.content_sha256 <> expected_content THEN
        RAISE EXCEPTION 'Prospective archive revision hash is invalid'
            USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION mra.validate_prospective_archive_roster()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE root_id uuid;
DECLARE generation mra.prospective_archive_generation%ROWTYPE;
DECLARE member_count integer;
DECLARE member_ordinals integer[];
DECLARE member_hash text;
DECLARE schedule_count integer;
DECLARE schedule_ordinals integer[];
DECLARE schedule_hash text;
BEGIN
    root_id := NEW.market_archive_id;
    SELECT * INTO generation FROM mra.prospective_archive_generation
    WHERE market_archive_id = root_id;
    SELECT count(*), array_agg(ordinal ORDER BY ordinal),
           mra.canonical_sha256(mra.canonical_json_text(coalesce(jsonb_agg(
               jsonb_build_object('content_sha256', content_sha256, 'ordinal', ordinal)
               ORDER BY ordinal
           ), '[]'::jsonb)))
      INTO member_count, member_ordinals, member_hash
      FROM mra.prospective_archive_generation_member
     WHERE market_archive_id = root_id;
    SELECT count(*), array_agg(ordinal ORDER BY ordinal),
           mra.canonical_sha256(mra.canonical_json_text(coalesce(jsonb_agg(
               jsonb_build_object('content_sha256', content_sha256, 'ordinal', ordinal)
               ORDER BY ordinal
           ), '[]'::jsonb)))
      INTO schedule_count, schedule_ordinals, schedule_hash
      FROM mra.prospective_archive_slice_schedule
     WHERE market_archive_id = root_id;
    IF member_count <> generation.member_count
       OR member_ordinals <> ARRAY(SELECT generate_series(1, generation.member_count))
       OR member_hash <> generation.member_roster_sha256
       OR schedule_count <> generation.schedule_count
       OR schedule_ordinals <> ARRAY(SELECT generate_series(1, generation.schedule_count))
       OR schedule_hash <> generation.schedule_roster_sha256
       OR schedule_count <> (
           SELECT count(*) FROM mra.market_archive_slice
           WHERE market_archive_id = root_id
       ) THEN
        RAISE EXCEPTION 'Prospective archive generation roster is incomplete'
            USING ERRCODE = '55000';
    END IF;
    RETURN NULL;
END;
$$;

CREATE OR REPLACE FUNCTION mra.validate_prospective_archive_schedule()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE generation mra.prospective_archive_generation%ROWTYPE;
DECLARE expected_session uuid;
DECLARE expected_checkpoint uuid;
DECLARE expected_content text;
BEGIN
    SELECT * INTO generation FROM mra.prospective_archive_generation
    WHERE market_archive_id = NEW.market_archive_id FOR SHARE;
    expected_session := CASE
        WHEN NEW.schedule_slot IN (
            'PRE_DECISION', 'DECISION_NEAR', 'POST_CLOSE', 'EVENING_REVISION'
        ) THEN generation.decision_session_id
        WHEN NEW.schedule_slot = 'REVISION_VERIFICATION'
            THEN generation.later_verification_session_id
        ELSE generation.outcome_session_id END;
    expected_checkpoint := CASE
        WHEN NEW.schedule_slot IN (
            'PRE_DECISION', 'DECISION_NEAR', 'POST_CLOSE', 'EVENING_REVISION'
        ) THEN generation.reference_checkpoint_id
        ELSE generation.outcome_checkpoint_id END;
    IF NEW.trading_session_id <> expected_session
       OR NEW.target_checkpoint_id <> expected_checkpoint
       OR NOT EXISTS (
           SELECT 1 FROM mra.market_archive_slice AS slice
           JOIN mra.trading_session AS session
             ON session.session_id = NEW.trading_session_id
           WHERE slice.market_archive_slice_id = NEW.market_archive_slice_id
             AND slice.market_archive_id = NEW.market_archive_id
             AND (slice.event_window_start AT TIME ZONE session.timezone_name)::date = session.session_date
             AND (slice.event_window_end AT TIME ZONE session.timezone_name)::date = session.session_date
       ) THEN
        RAISE EXCEPTION 'Prospective archive schedule session/Target binding is invalid'
            USING ERRCODE = '55000';
    END IF;
    expected_content := mra.canonical_sha256(mra.canonical_json_text(jsonb_build_object(
        'comparison_ordinal', NEW.comparison_ordinal,
        'instrument_id', NEW.instrument_id,
        'market_archive_slice_id', NEW.market_archive_slice_id,
        'ordinal', NEW.ordinal,
        'slot', NEW.schedule_slot,
        'target_checkpoint_id', NEW.target_checkpoint_id,
        'trading_session_id', NEW.trading_session_id
    )));
    IF NEW.content_sha256 <> expected_content THEN
        RAISE EXCEPTION 'Prospective archive schedule hash is invalid'
            USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION mra.validate_prospective_archive_terminal()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE slice_row mra.market_archive_slice%ROWTYPE;
DECLARE observed_timeliness text;
DECLARE has_gap boolean;
DECLARE has_resource boolean;
BEGIN
    NEW.terminal_at := clock_timestamp();
    SELECT * INTO slice_row FROM mra.market_archive_slice
    WHERE market_archive_slice_id = NEW.market_archive_slice_id FOR SHARE;
    SELECT timeliness INTO observed_timeliness
    FROM mra.market_archive_capture_observation
    WHERE market_archive_slice_id = NEW.market_archive_slice_id;
    has_gap := EXISTS (SELECT 1 FROM mra.market_archive_slice_gap
        WHERE market_archive_slice_id = NEW.market_archive_slice_id);
    has_resource := EXISTS (SELECT 1 FROM mra.market_archive_resource_stop
        WHERE market_archive_slice_id = NEW.market_archive_slice_id);
    IF (NEW.terminal_state = 'CAPTURED_ON_TIME' AND observed_timeliness IS DISTINCT FROM 'ON_TIME')
       OR (NEW.terminal_state = 'CAPTURED_LATE' AND observed_timeliness IS DISTINCT FROM 'LATE')
       OR (NEW.terminal_state IN ('PROVIDER_GAP', 'FAILED') AND NOT has_gap)
       OR (NEW.terminal_state = 'RESOURCE_STOP' AND NOT has_resource)
       OR (NEW.terminal_state = 'MISSED' AND (
            NEW.terminal_at <= slice_row.event_window_end
            OR observed_timeliness IS NOT NULL OR has_gap OR has_resource
       )) THEN
        RAISE EXCEPTION 'Prospective archive terminal evidence is invalid'
            USING ERRCODE = '55000';
    END IF;
    NEW.content_sha256 := mra.canonical_sha256(mra.canonical_json_text(jsonb_build_object(
        'market_archive_id', NEW.market_archive_id,
        'market_archive_slice_id', NEW.market_archive_slice_id,
        'reason_code', NEW.reason_code,
        'terminal_at', mra.canonical_timestamptz_text(NEW.terminal_at),
        'terminal_state', NEW.terminal_state
    )));
    RETURN NEW;
END;
$$;

CREATE INDEX prospective_archive_generation_target_idx
    ON mra.prospective_archive_generation(
        target_definition_id, target_version, target_definition_sha256
    );

CREATE INDEX prospective_archive_generation_sessions_idx
    ON mra.prospective_archive_generation(
        decision_session_id, outcome_session_id, later_verification_session_id
    );

CREATE INDEX prospective_archive_generation_outcome_session_idx
    ON mra.prospective_archive_generation(outcome_session_id);

CREATE INDEX prospective_archive_generation_later_session_idx
    ON mra.prospective_archive_generation(later_verification_session_id);

CREATE INDEX prospective_archive_generation_reference_idx
    ON mra.prospective_archive_generation(
        reference_checkpoint_id, target_definition_id
    );

CREATE INDEX prospective_archive_generation_outcome_idx
    ON mra.prospective_archive_generation(
        outcome_checkpoint_id, target_definition_id
    );

CREATE INDEX prospective_archive_planning_gap_predecessor_idx
    ON mra.prospective_archive_planning_gap(predecessor_market_archive_id);

CREATE INDEX prospective_archive_planning_gap_target_idx
    ON mra.prospective_archive_planning_gap(
        target_definition_id, target_version, target_definition_sha256
    );

CREATE INDEX prospective_archive_planning_gap_session_idx
    ON mra.prospective_archive_planning_gap(expected_decision_session_id);

CREATE INDEX prospective_archive_member_identifier_idx
    ON mra.prospective_archive_generation_member(instrument_identifier_id);

CREATE INDEX prospective_archive_member_instrument_idx
    ON mra.prospective_archive_generation_member(instrument_id);

CREATE INDEX prospective_archive_schedule_due_idx
    ON mra.prospective_archive_slice_schedule(
        market_archive_id, trading_session_id, schedule_slot
    );

CREATE INDEX prospective_archive_schedule_slice_scope_idx
    ON mra.prospective_archive_slice_schedule(
        market_archive_id, market_archive_slice_id
    );

CREATE INDEX prospective_archive_schedule_member_idx
    ON mra.prospective_archive_slice_schedule(
        market_archive_id, instrument_id, member_ordinal
    );

CREATE INDEX prospective_archive_schedule_session_idx
    ON mra.prospective_archive_slice_schedule(trading_session_id);

CREATE INDEX prospective_archive_schedule_checkpoint_idx
    ON mra.prospective_archive_slice_schedule(target_checkpoint_id);

CREATE INDEX prospective_archive_terminal_archive_idx
    ON mra.prospective_archive_slice_terminal(
        market_archive_id, terminal_state, market_archive_slice_id
    );

CREATE INDEX prospective_archive_terminal_slice_scope_idx
    ON mra.prospective_archive_slice_terminal(
        market_archive_id, market_archive_slice_id
    );

CREATE INDEX prospective_archive_revision_predecessor_idx
    ON mra.prospective_archive_revision_observation(predecessor_observation_id);

CREATE INDEX prospective_archive_revision_schedule_idx
    ON mra.prospective_archive_revision_observation(market_archive_slice_id);

CREATE INDEX prospective_archive_revision_checkpoint_idx
    ON mra.prospective_archive_revision_observation(target_checkpoint_id);

CREATE INDEX exploratory_backtest_arm_strategy_run_idx
    ON mra.exploratory_backtest_arm_strategy(
        exploratory_backtest_run_id, exploratory_backtest_arm_id
    );

CREATE INDEX exploratory_backtest_arm_strategy_scope_idx
    ON mra.exploratory_backtest_arm_strategy(
        exploratory_backtest_arm_id, exploratory_backtest_run_id
    );

CREATE INDEX exploratory_backtest_arm_strategy_version_idx
    ON mra.exploratory_backtest_arm_strategy(
        strategy_version_id, strategy_version_sha256
    );

CREATE INDEX evaluation_candidate_outcome_run_idx
    ON mra.evaluation_candidate_outcome_source(
        evaluation_run_id, evaluation_protocol_metric_id
    );

CREATE INDEX evaluation_candidate_outcome_input_idx
    ON mra.evaluation_candidate_outcome_source(
        evaluation_metric_observation_id, evaluation_run_id,
        evaluation_protocol_metric_id
    );

CREATE INDEX evaluation_candidate_outcome_commitment_idx
    ON mra.evaluation_candidate_outcome_source(commitment_id, candidate_id);

CREATE INDEX evaluation_candidate_outcome_candidate_idx
    ON mra.evaluation_candidate_outcome_source(candidate_id, candidate_set_id);

CREATE INDEX evaluation_candidate_outcome_candidate_set_idx
    ON mra.evaluation_candidate_outcome_source(candidate_set_id, candidate_id);

CREATE INDEX evaluation_candidate_outcome_metric_idx
    ON mra.evaluation_candidate_outcome_source(
        market_target_outcome_metric_id, market_target_outcome_revision_id
    );

CREATE INDEX evaluation_candidate_outcome_revision_idx
    ON mra.evaluation_candidate_outcome_source(
        market_target_outcome_revision_id, market_target_outcome_metric_id
    );

CREATE INDEX exploratory_backtest_feature_specification_idx
    ON mra.exploratory_backtest_feature(
        exploratory_backtest_run_id, specification_sha256
    );

CREATE INDEX exploratory_backtest_arm_specification_owner_idx
    ON mra.exploratory_backtest_arm(
        exploratory_backtest_run_id, specification_sha256
    );

CREATE INDEX exploratory_backtest_fold_specification_idx
    ON mra.exploratory_backtest_fold(
        exploratory_backtest_run_id, specification_sha256
    );

CREATE INDEX exploratory_backtest_fold_session_specification_idx
    ON mra.exploratory_backtest_fold_session(
        exploratory_backtest_run_id, specification_sha256
    );

CREATE INDEX exploratory_backtest_cost_specification_idx
    ON mra.exploratory_backtest_cost_assumption(
        exploratory_backtest_run_id, specification_sha256
    );

CREATE INDEX exploratory_backtest_cost_arm_idx
    ON mra.exploratory_backtest_cost_assumption(
        exploratory_backtest_arm_id, exploratory_backtest_run_id
    );

CREATE INDEX backtest_sample_member_revision_idx ON mra.backtest_sample_member(
    universe_revision_id, universe_member_id, instrument_id
);

CREATE INDEX backtest_sample_member_owner_idx ON mra.backtest_sample_member(
    exploratory_backtest_run_id, specification_sha256
);

CREATE INDEX backtest_sample_member_universe_idx ON mra.backtest_sample_member(
    universe_member_id, universe_revision_id, instrument_id
);

CREATE INDEX backtest_specification_universe_idx ON mra.backtest_specification(
    universe_revision_id, universe_id, universe_scope_sha256
);

CREATE INDEX backtest_specification_first_session_idx
    ON mra.backtest_specification(first_trading_session_id);

CREATE INDEX backtest_specification_last_session_idx
    ON mra.backtest_specification(last_trading_session_id);

CREATE INDEX backtest_run_current_specification_idx
    ON mra.exploratory_backtest_run(
        exploratory_backtest_run_id, current_specification_sha256
    );

CREATE INDEX backtest_arm_specification_run_idx ON mra.backtest_arm_specification(
    exploratory_backtest_run_id, exploratory_backtest_arm_id
);

CREATE INDEX backtest_arm_specification_owner_idx
    ON mra.backtest_arm_specification(
        exploratory_backtest_run_id, specification_sha256
    );

CREATE INDEX backtest_arm_specification_candidate_idx
    ON mra.backtest_arm_specification(
        candidate_policy_id, candidate_policy_sha256
    );

CREATE INDEX backtest_arm_specification_context_idx
    ON mra.backtest_arm_specification(
        context_policy_id, context_policy_sha256
    );

CREATE INDEX backtest_arm_specification_strategy_idx
    ON mra.backtest_arm_specification(
        strategy_version_id, strategy_version_sha256
    );

CREATE INDEX backtest_arm_specification_model_idx
    ON mra.backtest_arm_specification(model_id, model_sha256);

CREATE INDEX backtest_arm_specification_portfolio_idx
    ON mra.backtest_arm_specification(
        portfolio_policy_id, portfolio_policy_sha256
    );

CREATE INDEX backtest_arm_specification_risk_idx
    ON mra.backtest_arm_specification(risk_policy_id, risk_policy_sha256);

CREATE INDEX backtest_fold_dependency_run_idx ON mra.backtest_fold_dependency(
    exploratory_backtest_run_id, ordinal
);

CREATE INDEX backtest_fold_dependency_owner_idx
    ON mra.backtest_fold_dependency(
        exploratory_backtest_run_id, specification_sha256
    );

CREATE INDEX backtest_fold_dependency_fit_idx
    ON mra.backtest_fold_dependency(fit_fold_id, exploratory_backtest_run_id);

CREATE INDEX backtest_fold_dependency_validation_idx
    ON mra.backtest_fold_dependency(
        validation_fold_id, exploratory_backtest_run_id
    );

CREATE INDEX backtest_arm_fold_run_idx ON mra.backtest_arm_fold(
    exploratory_backtest_run_id, ordinal
);

CREATE INDEX backtest_arm_fold_owner_idx ON mra.backtest_arm_fold(
    exploratory_backtest_run_id, specification_sha256
);

CREATE INDEX backtest_arm_fold_arm_idx ON mra.backtest_arm_fold(
    exploratory_backtest_arm_id, exploratory_backtest_run_id
);

CREATE INDEX backtest_arm_fold_fold_idx ON mra.backtest_arm_fold(
    exploratory_backtest_fold_id, exploratory_backtest_run_id
);

CREATE INDEX backtest_model_requirement_run_idx
    ON mra.backtest_model_training_requirement(
        exploratory_backtest_run_id, ordinal
    );

CREATE INDEX backtest_model_requirement_owner_idx
    ON mra.backtest_model_training_requirement(
        exploratory_backtest_run_id, specification_sha256
    );

CREATE INDEX backtest_model_requirement_arm_idx
    ON mra.backtest_model_training_requirement(
        exploratory_backtest_arm_id, exploratory_backtest_run_id,
        specification_sha256
    );

CREATE INDEX backtest_model_requirement_fit_idx
    ON mra.backtest_model_training_requirement(
        fit_fold_id, exploratory_backtest_run_id
    );

CREATE INDEX backtest_model_requirement_validation_idx
    ON mra.backtest_model_training_requirement(
        validation_fold_id, exploratory_backtest_run_id
    );

CREATE INDEX backtest_model_requirement_model_idx
    ON mra.backtest_model_training_requirement(model_id, model_sha256);

CREATE INDEX backtest_model_requirement_protocol_idx
    ON mra.backtest_model_training_requirement(
        required_fit_evaluation_protocol_id,
        required_fit_evaluation_protocol_sha256
    );

CREATE INDEX backtest_evaluation_requirement_run_idx
    ON mra.backtest_evaluation_requirement(
        exploratory_backtest_run_id, ordinal
    );

CREATE INDEX backtest_evaluation_requirement_owner_idx
    ON mra.backtest_evaluation_requirement(
        exploratory_backtest_run_id, specification_sha256
    );

CREATE INDEX backtest_evaluation_requirement_arm_idx
    ON mra.backtest_evaluation_requirement(
        exploratory_backtest_arm_id, exploratory_backtest_run_id
    );

CREATE INDEX backtest_evaluation_requirement_fold_idx
    ON mra.backtest_evaluation_requirement(
        exploratory_backtest_fold_id, exploratory_backtest_run_id
    );

CREATE INDEX backtest_evaluation_requirement_protocol_idx
    ON mra.backtest_evaluation_requirement(
        evaluation_protocol_id, evaluation_protocol_sha256
    );

CREATE TRIGGER prospective_archive_planning_gap_guard
BEFORE INSERT ON mra.prospective_archive_planning_gap
FOR EACH ROW EXECUTE FUNCTION mra.validate_prospective_archive_planning_gap();

CREATE TRIGGER prospective_archive_generation_guard
BEFORE INSERT ON mra.prospective_archive_generation
FOR EACH ROW EXECUTE FUNCTION mra.validate_prospective_archive_generation();

CREATE TRIGGER prospective_archive_member_guard
BEFORE INSERT ON mra.prospective_archive_generation_member
FOR EACH ROW EXECUTE FUNCTION mra.validate_prospective_archive_member();

CREATE TRIGGER prospective_archive_schedule_guard
BEFORE INSERT ON mra.prospective_archive_slice_schedule
FOR EACH ROW EXECUTE FUNCTION mra.validate_prospective_archive_schedule();

CREATE CONSTRAINT TRIGGER prospective_archive_generation_roster_guard
AFTER INSERT ON mra.prospective_archive_generation
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
EXECUTE FUNCTION mra.validate_prospective_archive_roster();

CREATE CONSTRAINT TRIGGER prospective_archive_member_roster_guard
AFTER INSERT ON mra.prospective_archive_generation_member
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
EXECUTE FUNCTION mra.validate_prospective_archive_roster();

CREATE CONSTRAINT TRIGGER prospective_archive_schedule_roster_guard
AFTER INSERT ON mra.prospective_archive_slice_schedule
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
EXECUTE FUNCTION mra.validate_prospective_archive_roster();

CREATE TRIGGER prospective_archive_terminal_guard
BEFORE INSERT ON mra.prospective_archive_slice_terminal
FOR EACH ROW EXECUTE FUNCTION mra.validate_prospective_archive_terminal();

CREATE TRIGGER prospective_archive_revision_guard
BEFORE INSERT ON mra.prospective_archive_revision_observation
FOR EACH ROW EXECUTE FUNCTION mra.validate_prospective_archive_revision();

CREATE TRIGGER prospective_archive_generation_append_only
BEFORE UPDATE OR DELETE ON mra.prospective_archive_generation
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();

CREATE TRIGGER prospective_archive_planning_gap_append_only
BEFORE UPDATE OR DELETE ON mra.prospective_archive_planning_gap
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();

CREATE TRIGGER prospective_archive_member_append_only
BEFORE UPDATE OR DELETE ON mra.prospective_archive_generation_member
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();

CREATE TRIGGER prospective_archive_schedule_append_only
BEFORE UPDATE OR DELETE ON mra.prospective_archive_slice_schedule
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();

CREATE TRIGGER prospective_archive_terminal_append_only
BEFORE UPDATE OR DELETE ON mra.prospective_archive_slice_terminal
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();

CREATE TRIGGER prospective_archive_revision_append_only
BEFORE UPDATE OR DELETE ON mra.prospective_archive_revision_observation
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();

CREATE TRIGGER operational_schema_upgrade_receipt_append_only
BEFORE UPDATE OR DELETE ON mra.operational_schema_upgrade_receipt
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();

CREATE TRIGGER exploratory_backtest_arm_strategy_append_only BEFORE UPDATE OR DELETE ON mra.exploratory_backtest_arm_strategy FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();

CREATE TRIGGER evaluation_candidate_outcome_source_append_only BEFORE UPDATE OR DELETE ON mra.evaluation_candidate_outcome_source FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();

CREATE TRIGGER evaluation_candidate_outcome_source_insert_guard BEFORE INSERT ON mra.evaluation_candidate_outcome_source FOR EACH ROW EXECUTE FUNCTION mra.guard_evaluation_metric_insert();

CREATE CONSTRAINT TRIGGER backtest_specification_reconcile_guard
AFTER INSERT ON mra.backtest_specification
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION mra.validate_current_backtest_specification();

CREATE TRIGGER backtest_specification_append_only
BEFORE UPDATE OR DELETE ON mra.backtest_specification
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();

CREATE TRIGGER backtest_sample_member_append_only
BEFORE UPDATE OR DELETE ON mra.backtest_sample_member
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();

CREATE TRIGGER backtest_arm_specification_append_only
BEFORE UPDATE OR DELETE ON mra.backtest_arm_specification
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();

CREATE TRIGGER backtest_fold_dependency_append_only
BEFORE UPDATE OR DELETE ON mra.backtest_fold_dependency
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();

CREATE TRIGGER backtest_arm_fold_append_only
BEFORE UPDATE OR DELETE ON mra.backtest_arm_fold
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();

CREATE TRIGGER backtest_model_training_requirement_append_only
BEFORE UPDATE OR DELETE ON mra.backtest_model_training_requirement
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();

CREATE TRIGGER backtest_evaluation_requirement_append_only
BEFORE UPDATE OR DELETE ON mra.backtest_evaluation_requirement
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
