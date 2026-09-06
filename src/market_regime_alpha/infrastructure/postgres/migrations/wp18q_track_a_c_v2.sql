ALTER TABLE mra.eligibility_policy ADD CONSTRAINT eligibility_policy_identity_hash_uk UNIQUE (
        eligibility_policy_id, content_sha256
    );

ALTER TABLE mra.evaluation_protocol_metric ADD CONSTRAINT evaluation_protocol_metric_hash_authority_uk UNIQUE (
        evaluation_protocol_metric_id, evaluation_protocol_id, content_sha256
    );

ALTER TABLE mra.backtest_evaluation_requirement ADD CONSTRAINT backtest_evaluation_requirement_scope_uk UNIQUE NULLS NOT DISTINCT (
        exploratory_backtest_run_id, scope_kind,
        exploratory_backtest_arm_id, exploratory_backtest_fold_id, slice_key
    );

ALTER TABLE mra.runtime_step DROP CONSTRAINT runtime_step_kind_ck, ADD CONSTRAINT runtime_step_kind_ck CHECK (step_kind IN ('CAPTURE', 'NORMALIZE_PIT', 'FREEZE_UNIVERSE', 'ASSESS_ELIGIBILITY', 'REGISTER_DATASET', 'BUILD_CANDIDATE_SET', 'OPEN_DECISION_RUN', 'ASSESS_CONTEXT', 'SIGNAL_AND_FORECAST', 'DECIDE_AND_RISK', 'PERSIST_DECISION', 'SETTLE_OUTCOME', 'FREEZE_PARTITION', 'REGISTER_EXPERIMENT', 'OPEN_EXPERIMENT_RUN', 'OPEN_EVALUATION', 'ACQUIRE_OUTCOME_INPUTS', 'EVALUATE', 'OPEN_MODEL_TRAINING_RUN', 'REGISTER_MODEL_VERSION', 'RECORD_EVIDENCE', 'ATTRIBUTE', 'ASSESS_RESEARCH', 'QUALIFY'));

ALTER TABLE mra.evaluation_run DROP CONSTRAINT evaluation_run_shape_ck, ADD CONSTRAINT evaluation_run_shape_ck CHECK (
        partition_purpose IN ('DISCOVERY', 'FIT', 'VALIDATION', 'LOCKED_OOS', 'PROSPECTIVE')
        AND expected_member_count >= 0 AND expected_protocol_metric_count > 0
        AND status IN ('OPEN', 'INPUTS_ACQUIRED', 'COMPLETED', 'FAILED')
        AND request_sha256 ~ '^[0-9a-f]{64}$' AND version > 0
        AND provenance_sha256 ~ '^[0-9a-f]{64}$'
        AND content_sha256 ~ '^[0-9a-f]{64}$'
        AND access_count >= 0 AND observation_count >= 0
        AND metric_count >= 0 AND metric_observation_count >= 0
        AND (input_roster_sha256 IS NULL OR input_roster_sha256 ~ '^[0-9a-f]{64}$')
        AND (metric_roster_sha256 IS NULL OR metric_roster_sha256 ~ '^[0-9a-f]{64}$')
        AND ((status = 'OPEN' AND inputs_acquired_at IS NULL AND completed_at IS NULL AND failed_at IS NULL AND failure_reason_code IS NULL)
          OR (status = 'INPUTS_ACQUIRED' AND inputs_acquired_at IS NOT NULL AND completed_at IS NULL AND failed_at IS NULL AND failure_reason_code IS NULL)
          OR (status = 'COMPLETED' AND inputs_acquired_at IS NOT NULL AND completed_at IS NOT NULL AND failed_at IS NULL AND failure_reason_code IS NULL)
          OR (status = 'FAILED' AND failed_at IS NOT NULL AND completed_at IS NULL AND failure_reason_code ~ '^[A-Z][A-Z0-9_]{0,99}$'))
    );

ALTER TABLE mra.evaluation_backtest_arm_source DROP CONSTRAINT evaluation_backtest_source_shape_ck, ADD CONSTRAINT evaluation_backtest_source_shape_ck CHECK (
        arm_kind ~ '^[a-zA-Z][a-zA-Z0-9_-]{0,99}$'
        AND content_sha256 ~ '^[0-9a-f]{64}$'
    );

ALTER TABLE mra.backtest_evaluation_requirement DROP CONSTRAINT backtest_evaluation_requirement_shape_ck, ADD CONSTRAINT backtest_evaluation_requirement_shape_ck CHECK (
        ordinal > 0
        AND scope_kind IN ('FOLD', 'AGGREGATE', 'MONTH', 'QUARTER', 'CONTEXT')
        AND exploratory_backtest_arm_id IS NOT NULL
        AND ((scope_kind = 'AGGREGATE'
              AND exploratory_backtest_fold_id IS NULL AND slice_key IS NULL)
          OR (scope_kind = 'FOLD'
              AND exploratory_backtest_fold_id IS NOT NULL AND slice_key IS NULL)
          OR (scope_kind = 'MONTH'
              AND exploratory_backtest_fold_id IS NULL
              AND slice_key ~ '^[0-9]{4}-(0[1-9]|1[0-2])$')
          OR (scope_kind = 'QUARTER'
              AND exploratory_backtest_fold_id IS NULL
              AND slice_key ~ '^[0-9]{4}-Q[1-4]$')
          OR (scope_kind = 'CONTEXT'
              AND exploratory_backtest_fold_id IS NULL
              AND slice_key ~ '^(MARKET_REGIME|ETF_ROTATION|THEME_ROTATION|CAPITAL_BREADTH):(POSITIVE|NEUTRAL|NEGATIVE|UNKNOWN)$'))
        AND specification_sha256 ~ '^[0-9a-f]{64}$'
        AND evaluation_protocol_sha256 ~ '^[0-9a-f]{64}$'
        AND content_sha256 ~ '^[0-9a-f]{64}$'
    );

ALTER TABLE mra.model_training_run DROP CONSTRAINT model_training_shape_ck, ADD CONSTRAINT model_training_shape_ck CHECK (
        algorithm_code ~ '^[a-z][a-z0-9_-]{0,99}$'
        AND algorithm_version ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$'
        AND algorithm_sha256 ~ '^[0-9a-f]{64}$'
        AND (algorithm_code <> 'deterministic_ridge' OR ridge_alpha IS NOT NULL)
        AND (ridge_alpha IS NULL OR ridge_alpha >= 0) AND random_seed >= 0
        AND sample_count > 0 AND estimable_count >= 2
        AND estimable_count <= sample_count
        AND sample_roster_sha256 ~ '^[0-9a-f]{64}$'
        AND provenance_sha256 ~ '^[0-9a-f]{64}$'
        AND content_sha256 ~ '^[0-9a-f]{64}$'
        AND request_sha256 ~ '^[0-9a-f]{64}$'
    );

ALTER TABLE mra.model_training_run ALTER COLUMN ridge_alpha DROP NOT NULL;

ALTER TABLE mra.exploratory_backtest_fold ADD CONSTRAINT exploratory_backtest_fold_current_exact_uk UNIQUE (
        exploratory_backtest_fold_id, exploratory_backtest_run_id,
        specification_sha256
    );

ALTER TABLE mra.exploratory_backtest_cost_assumption DROP CONSTRAINT exploratory_backtest_cost_kind_uk, ADD CONSTRAINT exploratory_backtest_cost_kind_uk UNIQUE NULLS NOT DISTINCT (
            exploratory_backtest_run_id, exploratory_backtest_arm_id,
            cost_kind
        );

-- Kept as an additive suffix so a populated prior epoch reaches the exact
-- same column order without rewriting immutable Evaluation rows.
ALTER TABLE mra.evaluation_metric
    ADD COLUMN reason_code text,
    DROP CONSTRAINT evaluation_metric_shape_ck,
    ADD CONSTRAINT evaluation_metric_shape_ck CHECK (
        metric_state IN ('ESTIMATED', 'NOT_ESTIMABLE')
        AND estimable_count >= 0
        AND acceptance_state IN ('ACCEPTED', 'REJECTED', 'NOT_APPLICABLE', 'NOT_ESTIMABLE')
        AND (reason_code IS NULL OR reason_code ~ '^[A-Z][A-Z0-9_]{0,99}$')
        AND ((metric_state = 'NOT_ESTIMABLE' AND decimal_value IS NULL AND boolean_value IS NULL AND acceptance_state = 'NOT_ESTIMABLE')
          OR (metric_state = 'ESTIMATED' AND (decimal_value IS NOT NULL OR boolean_value IS NOT NULL)))
        AND content_sha256 ~ '^[0-9a-f]{64}$'
    );

-- Current eligibility ownership was introduced after the first WP-18Q
-- operational route.  The suffix preserves exact column ordinals on both a
-- fresh bootstrap and an additive upgrade of populated evidence.
ALTER TABLE mra.backtest_specification
    ADD COLUMN eligibility_policy_id uuid NOT NULL,
    ADD COLUMN eligibility_policy_sha256 text NOT NULL,
    ADD CONSTRAINT backtest_specification_eligibility_fk FOREIGN KEY (
        eligibility_policy_id, eligibility_policy_sha256
    ) REFERENCES mra.eligibility_policy(
        eligibility_policy_id, content_sha256
    ) ON DELETE RESTRICT,
    DROP CONSTRAINT backtest_specification_shape_ck,
    ADD CONSTRAINT backtest_specification_shape_ck CHECK (
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
        AND eligibility_policy_sha256 ~ '^[0-9a-f]{64}$'
    );

-- Model recipe fields remain an additive suffix for exact V1-to-current
-- operational upgrades; no existing training requirement row is rewritten.
ALTER TABLE mra.backtest_model_training_requirement
    ADD COLUMN required_fit_evaluation_protocol_metric_id uuid NOT NULL,
    ADD COLUMN required_fit_evaluation_metric_sha256 text NOT NULL,
    ADD COLUMN planned_model_version integer NOT NULL,
    ADD COLUMN algorithm_code text NOT NULL,
    ADD COLUMN algorithm_version text NOT NULL,
    ADD COLUMN implementation_sha256 text NOT NULL,
    ADD COLUMN python_implementation text NOT NULL,
    ADD COLUMN python_version text NOT NULL,
    ADD COLUMN runtime_code text NOT NULL,
    ADD COLUMN runtime_version text NOT NULL,
    ADD COLUMN uv_lock_sha256 text NOT NULL,
    ADD COLUMN dependency_count integer NOT NULL,
    ADD COLUMN dependency_roster_sha256 text NOT NULL,
    ADD COLUMN hyperparameter_count integer NOT NULL,
    ADD COLUMN hyperparameter_roster_sha256 text NOT NULL,
    ADD COLUMN environment_sha256 text NOT NULL,
    ADD COLUMN recipe_sha256 text NOT NULL,
    ADD CONSTRAINT backtest_model_requirement_version_uk UNIQUE (
        model_id, planned_model_version
    ),
    ADD CONSTRAINT backtest_model_requirement_child_owner_uk UNIQUE (
        backtest_model_training_requirement_id,
        exploratory_backtest_run_id, specification_sha256
    ),
    ADD CONSTRAINT backtest_model_requirement_metric_fk FOREIGN KEY (
        required_fit_evaluation_protocol_metric_id,
        required_fit_evaluation_protocol_id,
        required_fit_evaluation_metric_sha256
    ) REFERENCES mra.evaluation_protocol_metric(
        evaluation_protocol_metric_id, evaluation_protocol_id,
        content_sha256
    ) ON DELETE RESTRICT,
    DROP CONSTRAINT backtest_model_requirement_shape_ck,
    ADD CONSTRAINT backtest_model_requirement_shape_ck CHECK (
        ordinal > 0 AND fit_fold_id <> validation_fold_id
        AND planned_model_version > 0
        AND algorithm_code ~ '^[a-z][a-z0-9_-]{0,99}$'
        AND algorithm_version ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$'
        AND implementation_sha256 ~ '^[0-9a-f]{64}$'
        AND python_implementation ~ '^[a-z][a-z0-9_-]{0,99}$'
        AND python_version ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$'
        AND runtime_code ~ '^[a-z][a-z0-9_-]{0,99}$'
        AND runtime_version ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$'
        AND uv_lock_sha256 ~ '^[0-9a-f]{64}$'
        AND dependency_count > 0
        AND dependency_roster_sha256 ~ '^[0-9a-f]{64}$'
        AND hyperparameter_count >= 0
        AND hyperparameter_roster_sha256 ~ '^[0-9a-f]{64}$'
        AND environment_sha256 ~ '^[0-9a-f]{64}$'
        AND recipe_sha256 ~ '^[0-9a-f]{64}$'
        AND specification_sha256 ~ '^[0-9a-f]{64}$'
        AND model_sha256 ~ '^[0-9a-f]{64}$'
        AND required_fit_evaluation_protocol_sha256 ~ '^[0-9a-f]{64}$'
        AND required_fit_evaluation_metric_sha256 ~ '^[0-9a-f]{64}$'
        AND content_sha256 ~ '^[0-9a-f]{64}$'
    );

-- A generic Evaluation Partition still derives its complete roster inside
-- PostgreSQL.  These nullable columns narrow that derivation to an exact
-- current Backtest arm/fold without accepting a caller-supplied commitment
-- roster.  Historical Partition rows remain null and retain their meaning.
ALTER TABLE mra.research_partition
    ADD COLUMN source_backtest_run_id uuid,
    ADD COLUMN source_backtest_arm_id uuid,
    ADD COLUMN source_backtest_fold_id uuid,
    ADD COLUMN source_backtest_sha256 text,
    ADD COLUMN source_context_kind text,
    ADD COLUMN source_context_state text,
    ADD CONSTRAINT research_partition_backtest_run_fk FOREIGN KEY (
        source_backtest_run_id, source_backtest_sha256
    ) REFERENCES mra.backtest_specification(
        exploratory_backtest_run_id, specification_sha256
    ) ON DELETE RESTRICT,
    ADD CONSTRAINT research_partition_backtest_arm_fk FOREIGN KEY (
        source_backtest_arm_id, source_backtest_run_id,
        source_backtest_sha256
    ) REFERENCES mra.backtest_arm_specification(
        exploratory_backtest_arm_id, exploratory_backtest_run_id,
        specification_sha256
    ) ON DELETE RESTRICT,
    ADD CONSTRAINT research_partition_backtest_fold_fk FOREIGN KEY (
        source_backtest_fold_id, source_backtest_run_id,
        source_backtest_sha256
    ) REFERENCES mra.exploratory_backtest_fold(
        exploratory_backtest_fold_id, exploratory_backtest_run_id,
        specification_sha256
    ) ON DELETE RESTRICT,
    ADD CONSTRAINT research_partition_backtest_source_shape_ck CHECK (
        (source_backtest_run_id IS NULL
         AND source_backtest_arm_id IS NULL
         AND source_backtest_fold_id IS NULL
         AND source_backtest_sha256 IS NULL
         AND source_context_kind IS NULL
         AND source_context_state IS NULL)
        OR
        (source_backtest_run_id IS NOT NULL
         AND source_backtest_arm_id IS NOT NULL
         AND source_backtest_sha256 ~ '^[0-9a-f]{64}$'
         AND ((source_context_kind IS NULL
               AND source_context_state IS NULL)
           OR (source_context_kind IN (
                   'MARKET_REGIME', 'ETF_ROTATION',
                   'THEME_ROTATION', 'CAPITAL_BREADTH'
               )
               AND source_context_state IN (
                   'POSITIVE', 'NEUTRAL', 'NEGATIVE', 'UNKNOWN'
               ))))
    ),
    DROP CONSTRAINT research_partition_shape_ck,
    ADD CONSTRAINT research_partition_shape_ck CHECK (
        status = 'FROZEN'
        AND purpose IN ('DISCOVERY', 'FIT', 'VALIDATION', 'LOCKED_OOS', 'PROSPECTIVE')
        AND population_scope IN ('ALL_COMMITMENTS', 'SELECTED', 'RANKED_NOT_SELECTED', 'UNRANKABLE')
        AND overlap_policy IN ('DIAGNOSTIC_REUSE', 'PURGED_WALK_FORWARD', 'ISOLATED_PROTECTED')
        AND ((purpose = 'DISCOVERY' AND overlap_policy = 'DIAGNOSTIC_REUSE')
          OR (purpose IN ('FIT', 'VALIDATION') AND overlap_policy IN ('DIAGNOSTIC_REUSE', 'PURGED_WALK_FORWARD'))
          OR (purpose IN ('LOCKED_OOS', 'PROSPECTIVE') AND overlap_policy = 'ISOLATED_PROTECTED'))
        AND partition_code ~ '^[a-z][a-z0-9_-]{0,99}$'
        AND series_code ~ '^[a-z][a-z0-9_-]{0,99}$'
        AND exchange_code ~ '^[A-Z][A-Z0-9]{1,15}$'
        AND timezone_name = 'Asia/Shanghai'
        AND calendar_session_count > 0
        AND calendar_roster_sha256 ~ '^[0-9a-f]{64}$'
        AND target_version > 0 AND outcome_horizon_sessions >= 0
        AND purge_before_sessions >= 0 AND purge_after_sessions >= 0
        AND embargo_sessions >= 0 AND fold_ordinal > 0
        AND (member_count > 0 OR (
            member_count = 0 AND source_backtest_run_id IS NOT NULL
        ))
        AND decision_start_date <= decision_end_date
        AND protected_start_date <= decision_start_date
        AND protected_end_date >= decision_end_date
        AND member_roster_sha256 ~ '^[0-9a-f]{64}$'
        AND provenance_sha256 ~ '^[0-9a-f]{64}$'
        AND content_sha256 ~ '^[0-9a-f]{64}$'
        AND request_sha256 ~ '^[0-9a-f]{64}$'
    );

-- Current generic Backtests freeze the exact numerical implementation as a
-- root-owned companion.  Historical EvaluationProtocolMetric rows remain
-- valid without this companion and are never rewritten.
CREATE TABLE mra.evaluation_metric_formula (
    evaluation_protocol_metric_id uuid PRIMARY KEY,
    evaluation_protocol_id uuid NOT NULL,
    surface_code text NOT NULL,
    formula_code text NOT NULL,
    formula_version integer NOT NULL,
    decimal_precision integer NOT NULL,
    rounding_mode text NOT NULL,
    parameter_count integer NOT NULL,
    parameter_roster_sha256 text NOT NULL,
    content_sha256 text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT evaluation_metric_formula_exact_uk UNIQUE (
        evaluation_protocol_metric_id, evaluation_protocol_id,
        content_sha256
    ),
    CONSTRAINT evaluation_metric_formula_metric_fk FOREIGN KEY (
        evaluation_protocol_metric_id, evaluation_protocol_id
    ) REFERENCES mra.evaluation_protocol_metric(
        evaluation_protocol_metric_id, evaluation_protocol_id
    ) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT evaluation_metric_formula_shape_ck CHECK (
        surface_code IN (
            'DATA', 'CANDIDATE', 'CONTEXT', 'SIGNAL_FORECAST',
            'PORTFOLIO_RISK', 'ECONOMICS', 'STABILITY'
        )
        AND formula_code IN (
            'coverage_rate', 'missingness_rate', 'source_gap_rate',
            'unavailable_rate', 'mean', 'sample_stddev', 'icir',
            'rank_ic', 'top_k_return', 'top_bottom_spread', 'hit_rate',
            'selected_ratio', 'predictive_bias', 'predictive_mae',
            'predictive_rmse', 'gross_exposure', 'net_exposure',
            'turnover', 'net_return_assumed_cost', 'cumulative_return',
            'annualized_return', 'volatility', 'sharpe', 'sortino',
            'calmar', 'max_drawdown', 'win_rate', 'mfe_mean',
            'max_adverse_excursion_mean'
        )
        AND formula_version > 0
        AND decimal_precision BETWEEN 16 AND 100
        AND rounding_mode IN (
            'ROUND_DOWN', 'ROUND_HALF_EVEN', 'ROUND_HALF_UP', 'ROUND_UP'
        )
        AND parameter_count >= 0
        AND parameter_roster_sha256 ~ '^[0-9a-f]{64}$'
        AND content_sha256 ~ '^[0-9a-f]{64}$'
    )
);

CREATE TABLE mra.evaluation_formula_parameter (
    formula_parameter_id uuid PRIMARY KEY,
    evaluation_protocol_metric_id uuid NOT NULL,
    evaluation_protocol_id uuid NOT NULL,
    formula_content_sha256 text NOT NULL,
    ordinal integer NOT NULL,
    parameter_code text NOT NULL,
    value_type text NOT NULL,
    decimal_value numeric,
    integer_value bigint,
    boolean_value boolean,
    text_value text,
    content_sha256 text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT evaluation_formula_parameter_ordinal_uk UNIQUE (
        evaluation_protocol_metric_id, ordinal
    ),
    CONSTRAINT evaluation_formula_parameter_code_uk UNIQUE (
        evaluation_protocol_metric_id, parameter_code
    ),
    CONSTRAINT evaluation_formula_parameter_owner_fk FOREIGN KEY (
        evaluation_protocol_metric_id, evaluation_protocol_id,
        formula_content_sha256
    ) REFERENCES mra.evaluation_metric_formula(
        evaluation_protocol_metric_id, evaluation_protocol_id,
        content_sha256
    ) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT evaluation_formula_parameter_shape_ck CHECK (
        ordinal > 0
        AND parameter_code ~ '^[a-z][a-z0-9_-]{0,99}$'
        AND value_type IN ('DECIMAL', 'INTEGER', 'BOOLEAN', 'TEXT')
        AND (
            (value_type = 'DECIMAL' AND decimal_value IS NOT NULL
             AND integer_value IS NULL AND boolean_value IS NULL
             AND text_value IS NULL)
         OR (value_type = 'INTEGER' AND decimal_value IS NULL
             AND integer_value IS NOT NULL AND boolean_value IS NULL
             AND text_value IS NULL)
         OR (value_type = 'BOOLEAN' AND decimal_value IS NULL
             AND integer_value IS NULL AND boolean_value IS NOT NULL
             AND text_value IS NULL)
         OR (value_type = 'TEXT' AND decimal_value IS NULL
             AND integer_value IS NULL AND boolean_value IS NULL
             AND text_value IS NOT NULL AND text_value <> '')
        )
        AND formula_content_sha256 ~ '^[0-9a-f]{64}$'
        AND content_sha256 ~ '^[0-9a-f]{64}$'
    )
);

CREATE TABLE mra.model_training_reproducibility (
    model_training_run_id uuid PRIMARY KEY,
    training_knowledge_cutoff timestamptz NOT NULL,
    implementation_sha256 text NOT NULL,
    python_implementation text NOT NULL,
    python_version text NOT NULL,
    runtime_code text NOT NULL,
    runtime_version text NOT NULL,
    uv_lock_sha256 text NOT NULL,
    dependency_count integer NOT NULL,
    dependency_roster_sha256 text NOT NULL,
    hyperparameter_count integer NOT NULL,
    hyperparameter_roster_sha256 text NOT NULL,
    environment_sha256 text NOT NULL,
    content_sha256 text NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT model_training_reproducibility_run_fk FOREIGN KEY (
        model_training_run_id
    ) REFERENCES mra.model_training_run(model_training_run_id)
        ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT model_training_reproducibility_shape_ck CHECK (
        training_knowledge_cutoff > '-infinity'::timestamptz
        AND training_knowledge_cutoff < 'infinity'::timestamptz
        AND implementation_sha256 ~ '^[0-9a-f]{64}$'
        AND python_implementation ~ '^[a-z][a-z0-9_-]{0,99}$'
        AND python_version ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$'
        AND runtime_code ~ '^[a-z][a-z0-9_-]{0,99}$'
        AND runtime_version ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$'
        AND uv_lock_sha256 ~ '^[0-9a-f]{64}$'
        AND dependency_count > 0
        AND dependency_roster_sha256 ~ '^[0-9a-f]{64}$'
        AND hyperparameter_count >= 0
        AND hyperparameter_roster_sha256 ~ '^[0-9a-f]{64}$'
        AND environment_sha256 ~ '^[0-9a-f]{64}$'
        AND content_sha256 ~ '^[0-9a-f]{64}$'
    )
);

CREATE TABLE mra.model_training_dependency (
    model_training_run_id uuid NOT NULL,
    ordinal integer NOT NULL,
    package_name text NOT NULL,
    package_version text NOT NULL,
    distribution_sha256 text NOT NULL,
    content_sha256 text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (model_training_run_id, ordinal),
    CONSTRAINT model_training_dependency_package_uk UNIQUE (
        model_training_run_id, package_name
    ),
    CONSTRAINT model_training_dependency_owner_fk FOREIGN KEY (
        model_training_run_id
    ) REFERENCES mra.model_training_reproducibility(model_training_run_id)
        ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT model_training_dependency_shape_ck CHECK (
        ordinal > 0
        AND package_name ~ '^[a-z][a-z0-9_-]{0,99}$'
        AND package_version ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$'
        AND distribution_sha256 ~ '^[0-9a-f]{64}$'
        AND content_sha256 ~ '^[0-9a-f]{64}$'
    )
);

CREATE TABLE mra.model_training_hyperparameter (
    model_training_run_id uuid NOT NULL,
    ordinal integer NOT NULL,
    parameter_code text NOT NULL,
    value_type text NOT NULL,
    decimal_value numeric(48, 18),
    integer_value bigint,
    boolean_value boolean,
    text_value text,
    content_sha256 text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (model_training_run_id, ordinal),
    CONSTRAINT model_training_hyperparameter_code_uk UNIQUE (
        model_training_run_id, parameter_code
    ),
    CONSTRAINT model_training_hyperparameter_owner_fk FOREIGN KEY (
        model_training_run_id
    ) REFERENCES mra.model_training_reproducibility(model_training_run_id)
        ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT model_training_hyperparameter_shape_ck CHECK (
        ordinal > 0
        AND parameter_code ~ '^[a-z][a-z0-9_-]{0,99}$'
        AND value_type IN ('DECIMAL', 'INTEGER', 'BOOLEAN', 'TEXT')
        AND content_sha256 ~ '^[0-9a-f]{64}$'
        AND num_nonnulls(
            decimal_value, integer_value, boolean_value, text_value
        ) = 1
        AND ((value_type = 'DECIMAL' AND decimal_value IS NOT NULL)
          OR (value_type = 'INTEGER' AND integer_value IS NOT NULL)
          OR (value_type = 'BOOLEAN' AND boolean_value IS NOT NULL)
          OR (value_type = 'TEXT' AND text_value IS NOT NULL
              AND text_value <> ''))
    )
);

CREATE TABLE mra.backtest_model_training_dependency (
    backtest_model_training_requirement_id uuid NOT NULL,
    exploratory_backtest_run_id uuid NOT NULL,
    specification_sha256 text NOT NULL,
    ordinal integer NOT NULL,
    package_name text NOT NULL,
    package_version text NOT NULL,
    distribution_sha256 text NOT NULL,
    content_sha256 text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (backtest_model_training_requirement_id, ordinal),
    CONSTRAINT backtest_model_training_dependency_package_uk UNIQUE (
        backtest_model_training_requirement_id, package_name
    ),
    CONSTRAINT backtest_model_training_dependency_owner_fk FOREIGN KEY (
        backtest_model_training_requirement_id,
        exploratory_backtest_run_id, specification_sha256
    ) REFERENCES mra.backtest_model_training_requirement(
        backtest_model_training_requirement_id,
        exploratory_backtest_run_id, specification_sha256
    ) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT backtest_model_training_dependency_shape_ck CHECK (
        ordinal > 0
        AND package_name ~ '^[a-z][a-z0-9_-]{0,99}$'
        AND package_version ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$'
        AND distribution_sha256 ~ '^[0-9a-f]{64}$'
        AND specification_sha256 ~ '^[0-9a-f]{64}$'
        AND content_sha256 ~ '^[0-9a-f]{64}$'
    )
);

CREATE TABLE mra.backtest_model_training_hyperparameter (
    backtest_model_training_requirement_id uuid NOT NULL,
    exploratory_backtest_run_id uuid NOT NULL,
    specification_sha256 text NOT NULL,
    ordinal integer NOT NULL,
    parameter_code text NOT NULL,
    value_type text NOT NULL,
    decimal_value numeric(48, 18),
    integer_value bigint,
    boolean_value boolean,
    text_value text,
    content_sha256 text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (backtest_model_training_requirement_id, ordinal),
    CONSTRAINT backtest_model_training_hyperparameter_code_uk UNIQUE (
        backtest_model_training_requirement_id, parameter_code
    ),
    CONSTRAINT backtest_model_training_hyperparameter_owner_fk FOREIGN KEY (
        backtest_model_training_requirement_id,
        exploratory_backtest_run_id, specification_sha256
    ) REFERENCES mra.backtest_model_training_requirement(
        backtest_model_training_requirement_id,
        exploratory_backtest_run_id, specification_sha256
    ) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT backtest_model_training_hyperparameter_shape_ck CHECK (
        ordinal > 0
        AND parameter_code ~ '^[a-z][a-z0-9_-]{0,99}$'
        AND value_type IN ('DECIMAL', 'INTEGER', 'BOOLEAN', 'TEXT')
        AND num_nonnulls(
            decimal_value, integer_value, boolean_value, text_value
        ) = 1
        AND ((value_type = 'DECIMAL' AND decimal_value IS NOT NULL)
          OR (value_type = 'INTEGER' AND integer_value IS NOT NULL)
          OR (value_type = 'BOOLEAN' AND boolean_value IS NOT NULL)
          OR (value_type = 'TEXT' AND text_value IS NOT NULL
              AND text_value <> ''))
        AND specification_sha256 ~ '^[0-9a-f]{64}$'
        AND content_sha256 ~ '^[0-9a-f]{64}$'
    )
);

-- Execution lineage only. Runtime and Evaluation remain the lifecycle and
-- metric Authorities; these immutable rows bind a derived generic action to
-- the exact canonical owner it invoked and deliberately contain no state or
-- mutable cursor.
CREATE TABLE mra.backtest_runtime_binding (
    backtest_runtime_binding_id uuid PRIMARY KEY,
    exploratory_backtest_run_id uuid NOT NULL,
    specification_sha256 text NOT NULL,
    action_id uuid NOT NULL,
    action_kind text NOT NULL,
    action_content_sha256 text NOT NULL,
    exploratory_backtest_arm_id uuid,
    exploratory_backtest_fold_id uuid,
    exploratory_backtest_fold_session_id uuid,
    model_training_requirement_id uuid,
    evaluation_requirement_id uuid,
    runtime_run_id uuid NOT NULL,
    content_sha256 text NOT NULL,
    bound_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT backtest_runtime_binding_action_uk UNIQUE (
        exploratory_backtest_run_id, action_id
    ),
    CONSTRAINT backtest_runtime_binding_runtime_uk UNIQUE (runtime_run_id),
    CONSTRAINT backtest_runtime_binding_specification_fk FOREIGN KEY (
        exploratory_backtest_run_id, specification_sha256
    ) REFERENCES mra.backtest_specification(
        exploratory_backtest_run_id, specification_sha256
    ) ON DELETE RESTRICT,
    CONSTRAINT backtest_runtime_binding_arm_fk FOREIGN KEY (
        exploratory_backtest_arm_id, exploratory_backtest_run_id
    ) REFERENCES mra.exploratory_backtest_arm(
        exploratory_backtest_arm_id, exploratory_backtest_run_id
    ) ON DELETE RESTRICT,
    CONSTRAINT backtest_runtime_binding_fold_fk FOREIGN KEY (
        exploratory_backtest_fold_id, exploratory_backtest_run_id
    ) REFERENCES mra.exploratory_backtest_fold(
        exploratory_backtest_fold_id, exploratory_backtest_run_id
    ) ON DELETE RESTRICT,
    CONSTRAINT backtest_runtime_binding_session_fk FOREIGN KEY (
        exploratory_backtest_fold_session_id
    ) REFERENCES mra.exploratory_backtest_fold_session(
        exploratory_backtest_fold_session_id
    ) ON DELETE RESTRICT,
    CONSTRAINT backtest_runtime_binding_model_requirement_fk FOREIGN KEY (
        model_training_requirement_id
    ) REFERENCES mra.backtest_model_training_requirement(
        backtest_model_training_requirement_id
    ) ON DELETE RESTRICT,
    CONSTRAINT backtest_runtime_binding_evaluation_requirement_fk FOREIGN KEY (
        evaluation_requirement_id
    ) REFERENCES mra.backtest_evaluation_requirement(
        backtest_evaluation_requirement_id
    ) ON DELETE RESTRICT,
    CONSTRAINT backtest_runtime_binding_runtime_fk FOREIGN KEY (runtime_run_id)
        REFERENCES mra.runtime_run(run_id) ON DELETE RESTRICT,
    CONSTRAINT backtest_runtime_binding_shape_ck CHECK (
        action_kind IN (
            'MATERIALIZE_DATASET', 'GENERATE_DECISION_SUPPORT',
            'SETTLE_OUTCOME', 'COMPLETE_FOLD_EVALUATION',
            'TRAIN_MODEL', 'COMPLETE_AGGREGATE_EVALUATION'
        )
        AND specification_sha256 ~ '^[0-9a-f]{64}$'
        AND action_content_sha256 ~ '^[0-9a-f]{64}$'
        AND content_sha256 ~ '^[0-9a-f]{64}$'
        AND ((action_kind IN (
                  'MATERIALIZE_DATASET', 'GENERATE_DECISION_SUPPORT',
                  'SETTLE_OUTCOME'
              )
              AND exploratory_backtest_arm_id IS NOT NULL
              AND exploratory_backtest_fold_id IS NOT NULL
              AND exploratory_backtest_fold_session_id IS NOT NULL
              AND model_training_requirement_id IS NULL
              AND evaluation_requirement_id IS NULL)
          OR (action_kind = 'TRAIN_MODEL'
              AND exploratory_backtest_arm_id IS NOT NULL
              AND exploratory_backtest_fold_id IS NOT NULL
              AND exploratory_backtest_fold_session_id IS NULL
              AND model_training_requirement_id IS NOT NULL
              AND evaluation_requirement_id IS NULL)
          OR (action_kind = 'COMPLETE_FOLD_EVALUATION'
              AND exploratory_backtest_arm_id IS NOT NULL
              AND exploratory_backtest_fold_id IS NOT NULL
              AND exploratory_backtest_fold_session_id IS NULL
              AND model_training_requirement_id IS NULL
              AND evaluation_requirement_id IS NOT NULL)
          OR (action_kind = 'COMPLETE_AGGREGATE_EVALUATION'
              AND exploratory_backtest_arm_id IS NOT NULL
              AND exploratory_backtest_fold_id IS NULL
              AND exploratory_backtest_fold_session_id IS NULL
              AND model_training_requirement_id IS NULL
              AND evaluation_requirement_id IS NOT NULL))
    )
);

CREATE TABLE mra.backtest_evaluation_execution (
    backtest_evaluation_execution_id uuid PRIMARY KEY,
    exploratory_backtest_run_id uuid NOT NULL,
    specification_sha256 text NOT NULL,
    backtest_evaluation_requirement_id uuid NOT NULL,
    evaluation_run_id uuid NOT NULL,
    evaluation_protocol_id uuid NOT NULL,
    evaluation_metric_count integer NOT NULL,
    evaluation_metric_roster_sha256 text NOT NULL,
    content_sha256 text NOT NULL,
    bound_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT backtest_evaluation_execution_requirement_uk UNIQUE (
        backtest_evaluation_requirement_id
    ),
    CONSTRAINT backtest_evaluation_execution_run_uk UNIQUE (evaluation_run_id),
    CONSTRAINT backtest_evaluation_execution_specification_fk FOREIGN KEY (
        exploratory_backtest_run_id, specification_sha256
    ) REFERENCES mra.backtest_specification(
        exploratory_backtest_run_id, specification_sha256
    ) ON DELETE RESTRICT,
    CONSTRAINT backtest_evaluation_execution_requirement_fk FOREIGN KEY (
        backtest_evaluation_requirement_id
    ) REFERENCES mra.backtest_evaluation_requirement(
        backtest_evaluation_requirement_id
    ) ON DELETE RESTRICT,
    CONSTRAINT backtest_evaluation_execution_run_fk FOREIGN KEY (
        evaluation_run_id, evaluation_protocol_id
    ) REFERENCES mra.evaluation_run(
        evaluation_run_id, evaluation_protocol_id
    ) ON DELETE RESTRICT,
    CONSTRAINT backtest_evaluation_execution_shape_ck CHECK (
        evaluation_metric_count > 0
        AND specification_sha256 ~ '^[0-9a-f]{64}$'
        AND evaluation_metric_roster_sha256 ~ '^[0-9a-f]{64}$'
        AND content_sha256 ~ '^[0-9a-f]{64}$'
    )
);

CREATE TABLE mra.backtest_model_lineage (
    backtest_model_lineage_id uuid PRIMARY KEY,
    exploratory_backtest_run_id uuid NOT NULL,
    specification_sha256 text NOT NULL,
    model_training_requirement_id uuid NOT NULL,
    backtest_evaluation_execution_id uuid NOT NULL,
    fit_evaluation_run_id uuid NOT NULL,
    model_id uuid NOT NULL,
    model_training_run_id uuid NOT NULL,
    model_training_run_sha256 text NOT NULL,
    model_training_reproducibility_sha256 text NOT NULL,
    model_version_id uuid NOT NULL,
    model_version_sha256 text NOT NULL,
    content_sha256 text NOT NULL UNIQUE,
    bound_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT backtest_model_lineage_requirement_uk UNIQUE (
        model_training_requirement_id
    ),
    CONSTRAINT backtest_model_lineage_training_uk UNIQUE (
        model_training_run_id
    ),
    CONSTRAINT backtest_model_lineage_version_uk UNIQUE (model_version_id),
    CONSTRAINT backtest_model_lineage_specification_fk FOREIGN KEY (
        exploratory_backtest_run_id, specification_sha256
    ) REFERENCES mra.backtest_specification(
        exploratory_backtest_run_id, specification_sha256
    ) ON DELETE RESTRICT,
    CONSTRAINT backtest_model_lineage_requirement_fk FOREIGN KEY (
        model_training_requirement_id
    ) REFERENCES mra.backtest_model_training_requirement(
        backtest_model_training_requirement_id
    ) ON DELETE RESTRICT,
    CONSTRAINT backtest_model_lineage_evaluation_fk FOREIGN KEY (
        backtest_evaluation_execution_id
    ) REFERENCES mra.backtest_evaluation_execution(
        backtest_evaluation_execution_id
    ) ON DELETE RESTRICT,
    CONSTRAINT backtest_model_lineage_training_fk FOREIGN KEY (
        model_training_run_id
    ) REFERENCES mra.model_training_run(model_training_run_id)
        ON DELETE RESTRICT,
    CONSTRAINT backtest_model_lineage_reproducibility_fk FOREIGN KEY (
        model_training_run_id
    ) REFERENCES mra.model_training_reproducibility(model_training_run_id)
        ON DELETE RESTRICT,
    CONSTRAINT backtest_model_lineage_version_fk FOREIGN KEY (
        model_version_id
    ) REFERENCES mra.model_version(model_version_id) ON DELETE RESTRICT,
    CONSTRAINT backtest_model_lineage_model_fk FOREIGN KEY (model_id)
        REFERENCES mra.model(model_id) ON DELETE RESTRICT,
    CONSTRAINT backtest_model_lineage_shape_ck CHECK (
        specification_sha256 ~ '^[0-9a-f]{64}$'
        AND model_training_run_sha256 ~ '^[0-9a-f]{64}$'
        AND model_training_reproducibility_sha256 ~ '^[0-9a-f]{64}$'
        AND model_version_sha256 ~ '^[0-9a-f]{64}$'
        AND content_sha256 ~ '^[0-9a-f]{64}$'
    )
);

CREATE TABLE mra.backtest_report_artifact (
    backtest_report_artifact_id uuid PRIMARY KEY,
    exploratory_backtest_run_id uuid NOT NULL,
    specification_sha256 text NOT NULL,
    evaluation_count integer NOT NULL,
    evaluation_roster_sha256 text NOT NULL,
    source_projection_sha256 text NOT NULL,
    code_content_sha256 text NOT NULL,
    config_content_sha256 text NOT NULL,
    report_schema text NOT NULL,
    renderer_version text NOT NULL,
    json_artifact_id uuid NOT NULL,
    json_content_sha256 text NOT NULL,
    json_size_bytes bigint NOT NULL,
    markdown_artifact_id uuid NOT NULL,
    markdown_content_sha256 text NOT NULL,
    markdown_size_bytes bigint NOT NULL,
    content_sha256 text NOT NULL,
    published_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT backtest_report_artifact_projection_uk UNIQUE (
        exploratory_backtest_run_id, source_projection_sha256,
        renderer_version
    ),
    CONSTRAINT backtest_report_artifact_specification_fk FOREIGN KEY (
        exploratory_backtest_run_id, specification_sha256
    ) REFERENCES mra.backtest_specification(
        exploratory_backtest_run_id, specification_sha256
    ) ON DELETE RESTRICT,
    CONSTRAINT backtest_report_artifact_json_fk FOREIGN KEY (
        json_artifact_id, json_content_sha256, json_size_bytes
    ) REFERENCES mra.artifact(
        artifact_id, content_sha256, size_bytes
    ) ON DELETE RESTRICT,
    CONSTRAINT backtest_report_artifact_markdown_fk FOREIGN KEY (
        markdown_artifact_id, markdown_content_sha256, markdown_size_bytes
    ) REFERENCES mra.artifact(
        artifact_id, content_sha256, size_bytes
    ) ON DELETE RESTRICT,
    CONSTRAINT backtest_report_artifact_shape_ck CHECK (
        evaluation_count > 0
        AND report_schema = 'mra-backtest-report-v1'
        AND renderer_version = '1'
        AND json_size_bytes >= 0 AND markdown_size_bytes >= 0
        AND specification_sha256 ~ '^[0-9a-f]{64}$'
        AND evaluation_roster_sha256 ~ '^[0-9a-f]{64}$'
        AND source_projection_sha256 ~ '^[0-9a-f]{64}$'
        AND code_content_sha256 ~ '^[0-9a-f]{64}$'
        AND config_content_sha256 ~ '^[0-9a-f]{64}$'
        AND json_content_sha256 ~ '^[0-9a-f]{64}$'
        AND markdown_content_sha256 ~ '^[0-9a-f]{64}$'
        AND content_sha256 ~ '^[0-9a-f]{64}$'
    )
);

CREATE OR REPLACE FUNCTION mra.guard_evaluation_metric_formula_result()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE has_formula boolean;
BEGIN
    SELECT EXISTS (
        SELECT 1
        FROM mra.evaluation_metric_formula AS formula
        WHERE formula.evaluation_protocol_metric_id =
              NEW.evaluation_protocol_metric_id
          AND formula.evaluation_protocol_id = NEW.evaluation_protocol_id
    ) INTO has_formula;
    IF has_formula IS DISTINCT FROM (NEW.reason_code IS NOT NULL) THEN
        RAISE EXCEPTION 'EvaluationMetric formula result reason shape is invalid'
            USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION mra.validate_backtest_evaluation_execution()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE requirement_row record;
DECLARE evaluation_row record;
DECLARE actual_count integer;
DECLARE actual_roster text;
DECLARE expected_content text;
BEGIN
    SELECT evaluation_protocol_id
      INTO requirement_row
      FROM mra.backtest_evaluation_requirement
     WHERE backtest_evaluation_requirement_id =
           NEW.backtest_evaluation_requirement_id
       AND exploratory_backtest_run_id = NEW.exploratory_backtest_run_id
       AND specification_sha256 = NEW.specification_sha256
     FOR SHARE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Backtest Evaluation requirement binding is not exact'
            USING ERRCODE = '55000';
    END IF;
    SELECT status, evaluation_protocol_id, metric_count,
           metric_roster_sha256, completed_at
      INTO evaluation_row
      FROM mra.evaluation_run
     WHERE evaluation_run_id = NEW.evaluation_run_id
     FOR SHARE;
    IF NOT FOUND OR evaluation_row.status <> 'COMPLETED'
       OR evaluation_row.evaluation_protocol_id <>
          requirement_row.evaluation_protocol_id
       OR NEW.evaluation_protocol_id <>
          requirement_row.evaluation_protocol_id
       OR NEW.evaluation_metric_count <> evaluation_row.metric_count
       OR NEW.evaluation_metric_roster_sha256 <>
          evaluation_row.metric_roster_sha256 THEN
        RAISE EXCEPTION 'Backtest Evaluation execution is not completed and exact'
            USING ERRCODE = '55000';
    END IF;
    SELECT count(*)::integer,
           mra.canonical_sha256(mra.canonical_json_text(jsonb_agg(
               jsonb_build_array(
                   metric.evaluation_metric_id,
                   metric.content_sha256
               ) ORDER BY protocol.ordinal
           )))
      INTO actual_count, actual_roster
      FROM mra.evaluation_metric AS metric
      JOIN mra.evaluation_protocol_metric AS protocol
        ON protocol.evaluation_protocol_metric_id =
           metric.evaluation_protocol_metric_id
     WHERE metric.evaluation_run_id = NEW.evaluation_run_id;
    IF actual_count <> NEW.evaluation_metric_count
       OR actual_roster <> NEW.evaluation_metric_roster_sha256 THEN
        RAISE EXCEPTION 'Backtest Evaluation metric roster is not exact'
            USING ERRCODE = '55000';
    END IF;
    expected_content := mra.canonical_sha256(mra.canonical_json_text(
        jsonb_build_object(
            'backtest_evaluation_requirement_id',
                NEW.backtest_evaluation_requirement_id,
            'evaluation_metric_count', NEW.evaluation_metric_count,
            'evaluation_metric_roster_sha256',
                NEW.evaluation_metric_roster_sha256,
            'evaluation_protocol_id', NEW.evaluation_protocol_id,
            'evaluation_run_id', NEW.evaluation_run_id,
            'exploratory_backtest_run_id', NEW.exploratory_backtest_run_id,
            'specification_sha256', NEW.specification_sha256
        )
    ));
    IF NEW.content_sha256 <> expected_content THEN
        RAISE EXCEPTION 'Backtest Evaluation execution hash is invalid'
            USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION mra.validate_backtest_model_lineage()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE expected_content text;
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM mra.backtest_model_training_requirement AS requirement
        JOIN mra.exploratory_backtest_run AS backtest
          ON backtest.exploratory_backtest_run_id =
             requirement.exploratory_backtest_run_id
         AND backtest.current_specification_sha256 =
             requirement.specification_sha256
        JOIN mra.backtest_evaluation_execution AS execution
          ON execution.backtest_evaluation_execution_id =
             NEW.backtest_evaluation_execution_id
         AND execution.exploratory_backtest_run_id =
             requirement.exploratory_backtest_run_id
         AND execution.specification_sha256 =
             requirement.specification_sha256
         AND execution.evaluation_run_id = NEW.fit_evaluation_run_id
         AND execution.evaluation_protocol_id =
             requirement.required_fit_evaluation_protocol_id
        JOIN mra.backtest_evaluation_requirement AS evaluation_requirement
          ON evaluation_requirement.backtest_evaluation_requirement_id =
             execution.backtest_evaluation_requirement_id
         AND evaluation_requirement.exploratory_backtest_run_id =
             requirement.exploratory_backtest_run_id
         AND evaluation_requirement.specification_sha256 =
             requirement.specification_sha256
         AND evaluation_requirement.scope_kind = 'FOLD'
         AND evaluation_requirement.exploratory_backtest_arm_id =
             requirement.exploratory_backtest_arm_id
         AND evaluation_requirement.exploratory_backtest_fold_id =
             requirement.fit_fold_id
        JOIN mra.model_training_run AS training
          ON training.model_training_run_id = NEW.model_training_run_id
         AND training.content_sha256 = NEW.model_training_run_sha256
         AND training.model_id = requirement.model_id
         AND training.evaluation_run_id = execution.evaluation_run_id
         AND training.exploratory_backtest_run_id =
             requirement.exploratory_backtest_run_id
         AND training.exploratory_backtest_arm_id =
             requirement.exploratory_backtest_arm_id
         AND training.exploratory_backtest_fold_id = requirement.fit_fold_id
         AND training.evaluation_protocol_metric_id =
             requirement.required_fit_evaluation_protocol_metric_id
         AND training.algorithm_code = requirement.algorithm_code
         AND training.algorithm_version = requirement.algorithm_version
         AND training.algorithm_sha256 = requirement.implementation_sha256
         AND training.random_seed = backtest.random_seed
         AND training.code_artifact_id = backtest.code_artifact_id
         AND training.code_content_sha256 = backtest.code_content_sha256
         AND training.code_size_bytes = backtest.code_size_bytes
         AND training.config_artifact_id = backtest.config_artifact_id
         AND training.config_content_sha256 = backtest.config_content_sha256
         AND training.config_size_bytes = backtest.config_size_bytes
         AND training.provenance_sha256 = backtest.provenance_sha256
        JOIN mra.model_training_reproducibility AS reproducibility
          ON reproducibility.model_training_run_id =
             training.model_training_run_id
         AND reproducibility.content_sha256 =
             NEW.model_training_reproducibility_sha256
         AND reproducibility.implementation_sha256 =
             requirement.implementation_sha256
         AND reproducibility.python_implementation =
             requirement.python_implementation
         AND reproducibility.python_version = requirement.python_version
         AND reproducibility.runtime_code = requirement.runtime_code
         AND reproducibility.runtime_version = requirement.runtime_version
         AND reproducibility.uv_lock_sha256 = requirement.uv_lock_sha256
         AND reproducibility.dependency_count = requirement.dependency_count
         AND reproducibility.dependency_roster_sha256 =
             requirement.dependency_roster_sha256
         AND reproducibility.hyperparameter_count =
             requirement.hyperparameter_count
         AND reproducibility.hyperparameter_roster_sha256 =
             requirement.hyperparameter_roster_sha256
         AND reproducibility.environment_sha256 =
             requirement.environment_sha256
        JOIN mra.model_version AS version
          ON version.model_version_id = NEW.model_version_id
         AND version.content_sha256 = NEW.model_version_sha256
         AND version.model_id = training.model_id
         AND version.model_training_run_id = training.model_training_run_id
         AND version.version = requirement.planned_model_version
         AND version.registered_at >= training.opened_at
        WHERE requirement.backtest_model_training_requirement_id =
              NEW.model_training_requirement_id
          AND requirement.exploratory_backtest_run_id =
              NEW.exploratory_backtest_run_id
          AND requirement.specification_sha256 = NEW.specification_sha256
          AND requirement.model_id = NEW.model_id
    ) THEN
        RAISE EXCEPTION 'Backtest Model lineage is not exact FIT training lineage'
            USING ERRCODE = '55000';
    END IF;

    expected_content := mra.canonical_sha256(mra.canonical_json_text(
        jsonb_build_object(
            'backtest_evaluation_execution_id',
                NEW.backtest_evaluation_execution_id,
            'backtest_model_lineage_id', NEW.backtest_model_lineage_id,
            'exploratory_backtest_run_id', NEW.exploratory_backtest_run_id,
            'fit_evaluation_run_id', NEW.fit_evaluation_run_id,
            'model_id', NEW.model_id,
            'model_training_reproducibility_sha256',
                NEW.model_training_reproducibility_sha256,
            'model_training_requirement_id',
                NEW.model_training_requirement_id,
            'model_training_run_id', NEW.model_training_run_id,
            'model_training_run_sha256', NEW.model_training_run_sha256,
            'model_version_id', NEW.model_version_id,
            'model_version_sha256', NEW.model_version_sha256,
            'specification_sha256', NEW.specification_sha256
        )
    ));
    IF NEW.content_sha256 <> expected_content THEN
        RAISE EXCEPTION 'Backtest Model lineage hash is invalid'
            USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION mra.validate_backtest_report_artifact()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE root_row record;
DECLARE actual_count integer;
DECLARE actual_roster text;
DECLARE expected_content text;
BEGIN
    SELECT code_content_sha256, config_content_sha256
      INTO root_row
      FROM mra.exploratory_backtest_run
     WHERE exploratory_backtest_run_id = NEW.exploratory_backtest_run_id
       AND current_specification_sha256 = NEW.specification_sha256
     FOR SHARE;
    IF NOT FOUND OR root_row.code_content_sha256 <>
                    NEW.code_content_sha256
       OR root_row.config_content_sha256 <> NEW.config_content_sha256 THEN
        RAISE EXCEPTION 'Backtest report code/config binding is not exact'
            USING ERRCODE = '55000';
    END IF;
    SELECT count(*)::integer,
           mra.canonical_sha256(mra.canonical_json_text(jsonb_agg(
               jsonb_build_object(
                   'evaluation_run_id', execution.evaluation_run_id,
                   'ordinal', requirement.ordinal
               ) ORDER BY requirement.ordinal
           )))
      INTO actual_count, actual_roster
      FROM mra.backtest_evaluation_requirement AS requirement
      JOIN mra.backtest_evaluation_execution AS execution
        ON execution.backtest_evaluation_requirement_id =
           requirement.backtest_evaluation_requirement_id
     WHERE requirement.exploratory_backtest_run_id =
           NEW.exploratory_backtest_run_id;
    IF actual_count <> NEW.evaluation_count
       OR actual_roster <> NEW.evaluation_roster_sha256 THEN
        RAISE EXCEPTION 'Backtest report Evaluation roster is not exact'
            USING ERRCODE = '55000';
    END IF;
    expected_content := mra.canonical_sha256(mra.canonical_json_text(
        jsonb_build_object(
            'code_content_sha256', NEW.code_content_sha256,
            'config_content_sha256', NEW.config_content_sha256,
            'evaluation_count', NEW.evaluation_count,
            'evaluation_roster_sha256', NEW.evaluation_roster_sha256,
            'exploratory_backtest_run_id', NEW.exploratory_backtest_run_id,
            'json_artifact', jsonb_build_object(
                'artifact_id', NEW.json_artifact_id,
                'content_sha256', NEW.json_content_sha256,
                'size_bytes', NEW.json_size_bytes
            ),
            'markdown_artifact', jsonb_build_object(
                'artifact_id', NEW.markdown_artifact_id,
                'content_sha256', NEW.markdown_content_sha256,
                'size_bytes', NEW.markdown_size_bytes
            ),
            'renderer_version', NEW.renderer_version,
            'report_schema', NEW.report_schema,
            'source_projection_sha256', NEW.source_projection_sha256,
            'specification_sha256', NEW.specification_sha256
        )
    ));
    IF expected_content <> NEW.content_sha256 THEN
        RAISE EXCEPTION 'Backtest report Artifact binding hash is invalid'
            USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION mra.validate_backtest_runtime_binding()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE runtime_row record;
DECLARE root_row record;
DECLARE expected_content text;
BEGIN
    SELECT runtime_mode, code_sha, config_artifact_id, config_hash
      INTO runtime_row
      FROM mra.runtime_run
     WHERE run_id = NEW.runtime_run_id
     FOR SHARE;
    SELECT code_content_sha256, config_artifact_id, config_content_sha256
      INTO root_row
      FROM mra.exploratory_backtest_run
     WHERE exploratory_backtest_run_id = NEW.exploratory_backtest_run_id
       AND current_specification_sha256 = NEW.specification_sha256
     FOR SHARE;
    IF NOT FOUND OR runtime_row.runtime_mode NOT IN ('HISTORICAL', 'REPLAY')
       OR runtime_row.code_sha <> root_row.code_content_sha256
       OR runtime_row.config_artifact_id <> root_row.config_artifact_id
       OR runtime_row.config_hash <> root_row.config_content_sha256 THEN
        RAISE EXCEPTION 'Backtest Runtime binding is not exact'
            USING ERRCODE = '55000';
    END IF;
    expected_content := mra.canonical_sha256(mra.canonical_json_text(
        jsonb_build_object(
            'action_content_sha256', NEW.action_content_sha256,
            'action_id', NEW.action_id,
            'action_kind', NEW.action_kind,
            'evaluation_requirement_id', NEW.evaluation_requirement_id,
            'exploratory_backtest_arm_id', NEW.exploratory_backtest_arm_id,
            'exploratory_backtest_fold_id', NEW.exploratory_backtest_fold_id,
            'exploratory_backtest_fold_session_id',
                NEW.exploratory_backtest_fold_session_id,
            'exploratory_backtest_run_id', NEW.exploratory_backtest_run_id,
            'model_training_requirement_id',
                NEW.model_training_requirement_id,
            'runtime_run_id', NEW.runtime_run_id,
            'specification_sha256', NEW.specification_sha256
        )
    ));
    IF NEW.content_sha256 <> expected_content THEN
        RAISE EXCEPTION 'Backtest Runtime binding hash is invalid'
            USING ERRCODE = '55000';
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
    IF NOT EXISTS (
        SELECT 1
          FROM mra.universe_revision AS universe_revision
          JOIN mra.eligibility_policy AS eligibility_policy
            ON eligibility_policy.eligibility_policy_id =
               NEW.eligibility_policy_id
           AND eligibility_policy.content_sha256 =
               NEW.eligibility_policy_sha256
           AND eligibility_policy.market_provider_product_id =
               universe_revision.market_provider_product_id
         WHERE universe_revision.universe_revision_id =
               NEW.universe_revision_id
           AND universe_revision.universe_id = NEW.universe_id
           AND universe_revision.scope_content_sha256 =
               NEW.universe_scope_sha256
    ) THEN
        RAISE EXCEPTION 'Current Backtest eligibility policy is outside the exact UniverseRevision provider scope'
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
          CROSS JOIN LATERAL (
              SELECT count(*)::integer AS actual_count,
                     min(ordinal) AS minimum_ordinal,
                     max(ordinal) AS maximum_ordinal,
                     mra.canonical_sha256(mra.canonical_json_text(coalesce(
                         jsonb_agg(jsonb_build_object(
                             'content_sha256', content_sha256,
                             'ordinal', ordinal,
                             'package_name', package_name
                         ) ORDER BY ordinal), '[]'::jsonb))) AS roster_sha256,
                     coalesce(bool_or(
                         content_sha256 <> mra.canonical_sha256(
                             mra.canonical_json_text(jsonb_build_object(
                                 'distribution_sha256', distribution_sha256,
                                 'ordinal', ordinal,
                                 'package_name', package_name,
                                 'package_version', package_version
                             ))
                         )
                     ), false) AS invalid_child
                FROM mra.backtest_model_training_dependency
               WHERE backtest_model_training_requirement_id =
                     requirement.backtest_model_training_requirement_id
          ) AS dependencies
          CROSS JOIN LATERAL (
              SELECT count(*)::integer AS actual_count,
                     min(ordinal) AS minimum_ordinal,
                     max(ordinal) AS maximum_ordinal,
                     mra.canonical_sha256(mra.canonical_json_text(coalesce(
                         jsonb_agg(jsonb_build_object(
                             'content_sha256', content_sha256,
                             'ordinal', ordinal,
                             'parameter_code', parameter_code
                         ) ORDER BY ordinal), '[]'::jsonb))) AS roster_sha256,
                     coalesce(bool_or(
                         content_sha256 <> mra.canonical_sha256(
                             mra.canonical_json_text(jsonb_build_object(
                                 'boolean_value', boolean_value,
                                 'decimal_value', CASE
                                     WHEN decimal_value IS NULL THEN NULL
                                     ELSE decimal_value::text END,
                                 'integer_value', integer_value,
                                 'ordinal', ordinal,
                                 'parameter_code', parameter_code,
                                 'text_value', text_value,
                                 'value_type', value_type
                             ))
                         )
                     ), false) AS invalid_child
                FROM mra.backtest_model_training_hyperparameter
               WHERE backtest_model_training_requirement_id =
                     requirement.backtest_model_training_requirement_id
          ) AS hyperparameters
         WHERE requirement.exploratory_backtest_run_id =
               NEW.exploratory_backtest_run_id
           AND (
               dependencies.actual_count <> requirement.dependency_count
               OR dependencies.minimum_ordinal <> 1
               OR dependencies.maximum_ordinal <> requirement.dependency_count
               OR dependencies.roster_sha256 <>
                  requirement.dependency_roster_sha256
               OR dependencies.invalid_child
               OR hyperparameters.actual_count <>
                  requirement.hyperparameter_count
               OR (requirement.hyperparameter_count > 0 AND (
                   hyperparameters.minimum_ordinal <> 1
                   OR hyperparameters.maximum_ordinal <>
                      requirement.hyperparameter_count
               ))
               OR (requirement.hyperparameter_count = 0 AND (
                   hyperparameters.minimum_ordinal IS NOT NULL
                   OR hyperparameters.maximum_ordinal IS NOT NULL
               ))
               OR hyperparameters.roster_sha256 <>
                  requirement.hyperparameter_roster_sha256
               OR hyperparameters.invalid_child
               OR requirement.environment_sha256 <>
                  mra.canonical_sha256(mra.canonical_json_text(
                      jsonb_build_object(
                          'dependency_roster_sha256',
                              requirement.dependency_roster_sha256,
                          'python_implementation',
                              requirement.python_implementation,
                          'python_version', requirement.python_version,
                          'runtime_code', requirement.runtime_code,
                          'runtime_version', requirement.runtime_version,
                          'uv_lock_sha256', requirement.uv_lock_sha256
                      )
                  ))
               OR requirement.recipe_sha256 <>
                  mra.canonical_sha256(mra.canonical_json_text(
                      jsonb_build_object(
                          'algorithm_code', requirement.algorithm_code,
                          'algorithm_version', requirement.algorithm_version,
                          'environment_sha256', requirement.environment_sha256,
                          'hyperparameter_roster_sha256',
                              requirement.hyperparameter_roster_sha256,
                          'implementation_sha256',
                              requirement.implementation_sha256
                      )
                  ))
               OR requirement.content_sha256 <>
                  mra.canonical_sha256(mra.canonical_json_text(
                      jsonb_build_object(
                          'fit_fold_id', requirement.fit_fold_id,
                          'model_arm_id',
                              requirement.exploratory_backtest_arm_id,
                          'model_definition', jsonb_build_object(
                              'authority_id', requirement.model_id,
                              'content_sha256', requirement.model_sha256
                          ),
                          'ordinal', requirement.ordinal,
                          'planned_model_version',
                              requirement.planned_model_version,
                          'recipe_sha256', requirement.recipe_sha256,
                          'requirement_id',
                              requirement.backtest_model_training_requirement_id,
                          'training_metric', jsonb_build_object(
                              'authority_id',
                                  requirement.required_fit_evaluation_protocol_metric_id,
                              'content_sha256',
                                  requirement.required_fit_evaluation_metric_sha256
                          ),
                          'validation_fold_id', requirement.validation_fold_id
                      )
                  ))
           )
    ) THEN
        RAISE EXCEPTION 'Current Backtest Model recipe does not reconcile'
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
    IF EXISTS (
        SELECT 1
          FROM mra.backtest_arm_fold AS participation
          JOIN mra.exploratory_backtest_fold AS fold
            ON fold.exploratory_backtest_fold_id =
               participation.exploratory_backtest_fold_id
           AND fold.exploratory_backtest_run_id =
               participation.exploratory_backtest_run_id
          LEFT JOIN mra.backtest_evaluation_requirement AS requirement
            ON requirement.exploratory_backtest_run_id =
               participation.exploratory_backtest_run_id
           AND requirement.scope_kind = 'FOLD'
           AND requirement.exploratory_backtest_arm_id =
               participation.exploratory_backtest_arm_id
           AND requirement.exploratory_backtest_fold_id =
               participation.exploratory_backtest_fold_id
           AND requirement.evaluation_protocol_id = fold.evaluation_protocol_id
           AND requirement.evaluation_protocol_sha256 =
               fold.evaluation_protocol_sha256
         WHERE participation.exploratory_backtest_run_id =
               NEW.exploratory_backtest_run_id
           AND requirement.backtest_evaluation_requirement_id IS NULL
    ) THEN
        RAISE EXCEPTION 'Current Backtest arm-fold Evaluation coverage is incomplete'
            USING ERRCODE = '55000';
    END IF;
    IF EXISTS (
        SELECT 1
          FROM mra.backtest_arm_specification AS arm
          LEFT JOIN mra.backtest_evaluation_requirement AS requirement
            ON requirement.exploratory_backtest_run_id =
               arm.exploratory_backtest_run_id
           AND requirement.scope_kind = 'AGGREGATE'
           AND requirement.exploratory_backtest_arm_id =
               arm.exploratory_backtest_arm_id
         WHERE arm.exploratory_backtest_run_id =
               NEW.exploratory_backtest_run_id
           AND requirement.backtest_evaluation_requirement_id IS NULL
    ) THEN
        RAISE EXCEPTION 'Current Backtest aggregate Evaluation coverage is incomplete'
            USING ERRCODE = '55000';
    END IF;
    IF EXISTS (
        SELECT 1
          FROM mra.backtest_evaluation_requirement AS requirement
          JOIN mra.evaluation_protocol_metric AS metric
            ON metric.evaluation_protocol_id =
               requirement.evaluation_protocol_id
          LEFT JOIN mra.evaluation_metric_formula AS formula
            ON formula.evaluation_protocol_metric_id =
               metric.evaluation_protocol_metric_id
           AND formula.evaluation_protocol_id =
               metric.evaluation_protocol_id
         WHERE requirement.exploratory_backtest_run_id =
               NEW.exploratory_backtest_run_id
           AND formula.evaluation_protocol_metric_id IS NULL
    ) THEN
        RAISE EXCEPTION 'Current Backtest Evaluation formula closure is incomplete'
            USING ERRCODE = '55000';
    END IF;
    IF EXISTS (
        SELECT 1
          FROM mra.backtest_evaluation_requirement AS requirement
          JOIN mra.backtest_arm_specification AS arm
            ON arm.exploratory_backtest_arm_id =
               requirement.exploratory_backtest_arm_id
           AND arm.exploratory_backtest_run_id =
               requirement.exploratory_backtest_run_id
           AND arm.specification_sha256 = requirement.specification_sha256
          LEFT JOIN mra.context_policy_metric AS context_metric
            ON context_metric.context_policy_id = arm.context_policy_id
           AND context_metric.context_kind =
               split_part(requirement.slice_key, ':', 1)
         WHERE requirement.exploratory_backtest_run_id =
               NEW.exploratory_backtest_run_id
           AND requirement.scope_kind = 'CONTEXT'
           AND context_metric.context_policy_metric_id IS NULL
    ) THEN
        RAISE EXCEPTION 'Current Backtest Context Evaluation kind is not frozen by the Arm policy'
            USING ERRCODE = '55000';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM mra.exploratory_backtest_cost_assumption
         WHERE exploratory_backtest_run_id = NEW.exploratory_backtest_run_id
           AND exploratory_backtest_arm_id IS NULL
    ) OR EXISTS (
        SELECT 1 FROM mra.exploratory_backtest_cost_assumption AS cost
         WHERE cost.exploratory_backtest_run_id = NEW.exploratory_backtest_run_id
           AND cost.content_sha256 <> mra.canonical_sha256(
               mra.canonical_json_text(jsonb_build_object(
                   'amount_bps', cost.amount_bps::text,
                   'arm_id', cost.exploratory_backtest_arm_id,
                   'assumption_id',
                       cost.exploratory_backtest_cost_assumption_id,
                   'charge_side', cost.charge_side,
                   'cost_kind', cost.cost_kind,
                   'ordinal', cost.ordinal
               ))
           )
    ) OR EXISTS (
        SELECT 1
          FROM mra.backtest_arm_specification AS arm
          CROSS JOIN LATERAL (
              SELECT count(*) AS item_count,
                     mra.canonical_sha256(mra.canonical_json_text(coalesce(
                         jsonb_agg(jsonb_build_object(
                             'content_sha256', cost.content_sha256,
                             'assumption_id',
                                 cost.exploratory_backtest_cost_assumption_id,
                             'ordinal', cost.ordinal
                         ) ORDER BY cost.ordinal), '[]'::jsonb
                     ))) AS roster_sha256
                FROM mra.exploratory_backtest_cost_assumption AS cost
               WHERE cost.exploratory_backtest_run_id =
                     arm.exploratory_backtest_run_id
                 AND cost.exploratory_backtest_arm_id IS NOT DISTINCT FROM
                     CASE WHEN arm.cost_binding_source = 'ARM_OVERRIDE'
                          THEN arm.exploratory_backtest_arm_id
                          ELSE NULL::uuid END
          ) AS effective
         WHERE arm.exploratory_backtest_run_id = NEW.exploratory_backtest_run_id
           AND (effective.item_count = 0
                OR effective.roster_sha256 <>
                   arm.effective_cost_roster_sha256)
    ) OR EXISTS (
        SELECT 1
          FROM mra.exploratory_backtest_cost_assumption AS cost
          JOIN mra.backtest_arm_specification AS arm
            ON arm.exploratory_backtest_arm_id =
               cost.exploratory_backtest_arm_id
           AND arm.exploratory_backtest_run_id =
               cost.exploratory_backtest_run_id
         WHERE cost.exploratory_backtest_run_id = NEW.exploratory_backtest_run_id
           AND cost.exploratory_backtest_arm_id IS NOT NULL
           AND arm.cost_binding_source <> 'ARM_OVERRIDE'
    ) THEN
        RAISE EXCEPTION 'Current Backtest Cost scope does not reconcile'
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
            'eligibility_policy', jsonb_build_object(
                'authority_id', NEW.eligibility_policy_id,
                'content_sha256', NEW.eligibility_policy_sha256
            ),
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

CREATE OR REPLACE FUNCTION mra.validate_evaluation_formula_closure()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE actual_count integer;
DECLARE actual_hash text;
DECLARE expected_hash text;
DECLARE expected_metric_hash text;
BEGIN
    SELECT count(*), mra.canonical_sha256(mra.canonical_json_text(coalesce(
        jsonb_agg(jsonb_build_object(
            'content_sha256', content_sha256,
            'formula_parameter_id', formula_parameter_id,
            'ordinal', ordinal
        ) ORDER BY ordinal), '[]'::jsonb)))
      INTO actual_count, actual_hash
      FROM mra.evaluation_formula_parameter
     WHERE evaluation_protocol_metric_id =
           NEW.evaluation_protocol_metric_id;
    IF (actual_count, actual_hash) IS DISTINCT FROM
       (NEW.parameter_count, NEW.parameter_roster_sha256) THEN
        RAISE EXCEPTION 'Evaluation formula parameter roster is incomplete'
            USING ERRCODE = '55000';
    END IF;
    IF EXISTS (
        SELECT 1
          FROM mra.evaluation_formula_parameter AS parameter
         WHERE parameter.evaluation_protocol_metric_id =
               NEW.evaluation_protocol_metric_id
           AND parameter.content_sha256 <> mra.canonical_sha256(
               mra.canonical_json_text(jsonb_build_object(
                   'boolean_value', parameter.boolean_value,
                   'decimal_value', parameter.decimal_value::text,
                   'formula_parameter_id', parameter.formula_parameter_id,
                   'integer_value', parameter.integer_value,
                   'ordinal', parameter.ordinal,
                   'parameter_code', parameter.parameter_code,
                   'text_value', parameter.text_value,
                   'value_type', parameter.value_type
               )))
    ) THEN
        RAISE EXCEPTION 'Evaluation formula parameter content hash is invalid'
            USING ERRCODE = '55000';
    END IF;
    expected_hash := mra.canonical_sha256(mra.canonical_json_text(
        jsonb_build_object(
            'decimal_precision', NEW.decimal_precision,
            'evaluation_protocol_metric_id',
                NEW.evaluation_protocol_metric_id,
            'formula_code', NEW.formula_code,
            'formula_version', NEW.formula_version,
            'parameter_count', NEW.parameter_count,
            'parameter_roster_sha256', NEW.parameter_roster_sha256,
            'rounding_mode', NEW.rounding_mode,
            'surface', NEW.surface_code
        )
    ));
    IF NEW.content_sha256 <> expected_hash THEN
        RAISE EXCEPTION 'Evaluation formula content hash is invalid'
            USING ERRCODE = '55000';
    END IF;
    SELECT mra.canonical_sha256(mra.canonical_json_text(jsonb_build_object(
        'acceptance_operator', metric.acceptance_operator,
        'acceptance_threshold', metric.acceptance_threshold::text,
        'backtest_arm_kind', metric.backtest_arm_kind,
        'candidate_disposition', metric.candidate_disposition,
        'direction', metric.direction,
        'formula_content_sha256', NEW.content_sha256,
        'inclusion_policy', metric.inclusion_policy,
        'metric_code', metric.metric_code,
        'minimum_estimable_count', metric.minimum_estimable_count,
        'missingness_policy', metric.missingness_policy,
        'ordinal', metric.ordinal,
        'reducer', metric.reducer,
        'slice_kind', metric.slice_kind,
        'source_kind', metric.source_kind,
        'source_measure', metric.source_measure,
        'source_metric_code', metric.source_metric_code,
        'source_target_metric_definition_id',
            metric.source_target_metric_definition_id,
        'source_value_type', metric.source_value_type
    ))) INTO expected_metric_hash
      FROM mra.evaluation_protocol_metric AS metric
     WHERE metric.evaluation_protocol_metric_id =
           NEW.evaluation_protocol_metric_id
       AND metric.evaluation_protocol_id = NEW.evaluation_protocol_id;
    IF expected_metric_hash IS NULL OR EXISTS (
        SELECT 1
          FROM mra.evaluation_protocol_metric AS metric
         WHERE metric.evaluation_protocol_metric_id =
               NEW.evaluation_protocol_metric_id
           AND metric.content_sha256 <> expected_metric_hash
    ) THEN
        RAISE EXCEPTION 'Evaluation metric and formula hashes are not bound'
            USING ERRCODE = '55000', DETAIL = format(
                'expected=%s observed=%s',
                expected_metric_hash,
                (SELECT metric.content_sha256
                   FROM mra.evaluation_protocol_metric AS metric
                  WHERE metric.evaluation_protocol_metric_id =
                        NEW.evaluation_protocol_metric_id)
            );
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
        LEFT JOIN mra.backtest_specification AS specification
          ON specification.exploratory_backtest_run_id =
             decision.exploratory_backtest_run_id
        LEFT JOIN mra.backtest_arm_specification AS arm_specification
          ON arm_specification.exploratory_backtest_arm_id =
             inference_arm.exploratory_backtest_arm_id
         AND arm_specification.exploratory_backtest_run_id =
             inference_arm.exploratory_backtest_run_id
         AND arm_specification.specification_sha256 =
             specification.specification_sha256
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
          AND (
              (specification.exploratory_backtest_run_id IS NOT NULL
               AND arm_specification.execution_kind = 'MODEL'
               AND arm_specification.model_id = version.model_id
               AND EXISTS (
                   SELECT 1
                   FROM mra.backtest_model_lineage AS lineage
                   JOIN mra.backtest_model_training_requirement AS requirement
                     ON requirement.backtest_model_training_requirement_id =
                        lineage.model_training_requirement_id
                    AND requirement.exploratory_backtest_run_id =
                        decision.exploratory_backtest_run_id
                    AND requirement.exploratory_backtest_arm_id =
                        decision.exploratory_backtest_arm_id
                    AND requirement.fit_fold_id =
                        training.exploratory_backtest_fold_id
                    AND requirement.validation_fold_id =
                        inference_fold.exploratory_backtest_fold_id
                   JOIN mra.backtest_fold_dependency AS dependency
                     ON dependency.exploratory_backtest_run_id =
                        requirement.exploratory_backtest_run_id
                    AND dependency.fit_fold_id = requirement.fit_fold_id
                    AND dependency.validation_fold_id =
                        requirement.validation_fold_id
                   WHERE lineage.model_training_run_id =
                         training.model_training_run_id
                     AND lineage.model_version_id = version.model_version_id
               ))
              OR
              (specification.exploratory_backtest_run_id IS NULL
               AND inference_arm.arm_kind IN (
                   'MODEL_CHALLENGER', 'RIDGE_CURRENT_CONTEXT',
                   'RIDGE_CONTEXT_OBSERVATIONAL'
               )
               AND training_fold.ordinal < inference_fold.ordinal)
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

CREATE OR REPLACE FUNCTION mra.validate_model_training_reproducibility()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE actual_dependency_count integer;
DECLARE minimum_dependency_ordinal integer;
DECLARE maximum_dependency_ordinal integer;
DECLARE actual_dependency_roster text;
DECLARE actual_hyperparameter_count integer;
DECLARE minimum_hyperparameter_ordinal integer;
DECLARE maximum_hyperparameter_ordinal integer;
DECLARE actual_hyperparameter_roster text;
DECLARE expected_environment text;
DECLARE expected_content text;
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM mra.model_training_run AS training
        JOIN mra.backtest_specification AS specification
          ON specification.exploratory_backtest_run_id =
             training.exploratory_backtest_run_id
        WHERE training.model_training_run_id = NEW.model_training_run_id
          AND training.algorithm_sha256 = NEW.implementation_sha256
    ) THEN
        RAISE EXCEPTION 'Model reproducibility requires exact current training root'
            USING ERRCODE = '55000';
    END IF;

    SELECT count(*)::integer, min(ordinal), max(ordinal),
           mra.canonical_sha256(mra.canonical_json_text(coalesce(jsonb_agg(
               jsonb_build_object(
                   'content_sha256', content_sha256,
                   'ordinal', ordinal,
                   'package_name', package_name
               ) ORDER BY ordinal
           ), '[]'::jsonb)))
      INTO actual_dependency_count, minimum_dependency_ordinal,
           maximum_dependency_ordinal, actual_dependency_roster
      FROM mra.model_training_dependency
     WHERE model_training_run_id = NEW.model_training_run_id;
    IF actual_dependency_count <> NEW.dependency_count
       OR minimum_dependency_ordinal <> 1
       OR maximum_dependency_ordinal <> NEW.dependency_count
       OR actual_dependency_roster <> NEW.dependency_roster_sha256
       OR EXISTS (
           SELECT 1 FROM mra.model_training_dependency
           WHERE model_training_run_id = NEW.model_training_run_id
             AND content_sha256 <> mra.canonical_sha256(
                 mra.canonical_json_text(jsonb_build_object(
                     'distribution_sha256', distribution_sha256,
                     'ordinal', ordinal,
                     'package_name', package_name,
                     'package_version', package_version
                 ))
             )
       ) THEN
        RAISE EXCEPTION 'Model dependency roster does not reconcile'
            USING ERRCODE = '55000';
    END IF;

    SELECT count(*)::integer, min(ordinal), max(ordinal),
           mra.canonical_sha256(mra.canonical_json_text(coalesce(jsonb_agg(
               jsonb_build_object(
                   'content_sha256', content_sha256,
                   'ordinal', ordinal,
                   'parameter_code', parameter_code
               ) ORDER BY ordinal
           ), '[]'::jsonb)))
      INTO actual_hyperparameter_count, minimum_hyperparameter_ordinal,
           maximum_hyperparameter_ordinal, actual_hyperparameter_roster
      FROM mra.model_training_hyperparameter
     WHERE model_training_run_id = NEW.model_training_run_id;
    IF actual_hyperparameter_count <> NEW.hyperparameter_count
       OR (NEW.hyperparameter_count > 0 AND (
           minimum_hyperparameter_ordinal <> 1
           OR maximum_hyperparameter_ordinal <> NEW.hyperparameter_count
       ))
       OR (NEW.hyperparameter_count = 0 AND (
           minimum_hyperparameter_ordinal IS NOT NULL
           OR maximum_hyperparameter_ordinal IS NOT NULL
       ))
       OR actual_hyperparameter_roster <> NEW.hyperparameter_roster_sha256
       OR EXISTS (
           SELECT 1 FROM mra.model_training_hyperparameter
           WHERE model_training_run_id = NEW.model_training_run_id
             AND content_sha256 <> mra.canonical_sha256(
                 mra.canonical_json_text(jsonb_build_object(
                     'boolean_value', boolean_value,
                     'decimal_value', CASE WHEN decimal_value IS NULL
                         THEN NULL ELSE decimal_value::text END,
                     'integer_value', integer_value,
                     'ordinal', ordinal,
                     'parameter_code', parameter_code,
                     'text_value', text_value,
                     'value_type', value_type
                 ))
             )
       ) THEN
        RAISE EXCEPTION 'Model hyperparameter roster does not reconcile'
            USING ERRCODE = '55000';
    END IF;

    expected_environment := mra.canonical_sha256(mra.canonical_json_text(
        jsonb_build_object(
            'dependency_roster_sha256', NEW.dependency_roster_sha256,
            'python_implementation', NEW.python_implementation,
            'python_version', NEW.python_version,
            'runtime_code', NEW.runtime_code,
            'runtime_version', NEW.runtime_version,
            'uv_lock_sha256', NEW.uv_lock_sha256
        )
    ));
    expected_content := mra.canonical_sha256(mra.canonical_json_text(
        jsonb_build_object(
            'environment_sha256', expected_environment,
            'hyperparameter_roster_sha256',
                NEW.hyperparameter_roster_sha256,
            'implementation_sha256', NEW.implementation_sha256,
            'model_training_run_id', NEW.model_training_run_id,
            'training_knowledge_cutoff',
                mra.canonical_timestamptz_text(
                    NEW.training_knowledge_cutoff
                )
        )
    ));
    IF NEW.environment_sha256 <> expected_environment
       OR NEW.content_sha256 <> expected_content THEN
        RAISE EXCEPTION 'Model reproducibility hash does not reconcile'
            USING ERRCODE = '55000';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM mra.model_training_run AS training
        WHERE training.model_training_run_id = NEW.model_training_run_id
          AND training.algorithm_code = 'deterministic_ridge'
          AND (
              SELECT count(*) <> 1 OR coalesce(bool_or(
                  value_type <> 'DECIMAL'
                  OR decimal_value IS DISTINCT FROM training.ridge_alpha
              ), true)
              FROM mra.model_training_hyperparameter
              WHERE model_training_run_id = NEW.model_training_run_id
                AND parameter_code = 'ridge_alpha'
          )
    ) THEN
        RAISE EXCEPTION 'deterministic ridge typed alpha differs from training root'
            USING ERRCODE = '55000';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM mra.model_training_sample AS sample
        JOIN mra.model_training_reproducibility AS reproducibility
          ON reproducibility.model_training_run_id =
             sample.model_training_run_id
        JOIN mra.market_target_outcome_revision AS outcome
          ON outcome.market_target_outcome_revision_id =
             sample.market_target_outcome_revision_id
        WHERE sample.model_training_run_id = NEW.model_training_run_id
          AND outcome.knowledge_cutoff > reproducibility.training_knowledge_cutoff
    ) THEN
        RAISE EXCEPTION 'Model training used an Outcome unavailable at cutoff'
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
        LEFT JOIN mra.backtest_specification AS specification
          ON specification.exploratory_backtest_run_id =
             backtest.exploratory_backtest_run_id
        LEFT JOIN mra.backtest_arm_specification AS arm_specification
          ON arm_specification.exploratory_backtest_arm_id =
             arm.exploratory_backtest_arm_id
         AND arm_specification.exploratory_backtest_run_id =
             arm.exploratory_backtest_run_id
         AND arm_specification.specification_sha256 =
             specification.specification_sha256
        JOIN mra.exploratory_backtest_fold AS fold
          ON fold.exploratory_backtest_fold_id = NEW.exploratory_backtest_fold_id
         AND fold.exploratory_backtest_run_id =
             backtest.exploratory_backtest_run_id
         AND fold.purpose = 'FIT'
         AND fold.evaluation_protocol_id = evaluation.evaluation_protocol_id
        WHERE model.model_id = NEW.model_id
          AND model.target_definition_id = NEW.target_definition_id
          AND (
              (specification.exploratory_backtest_run_id IS NOT NULL
               AND arm_specification.execution_kind = 'MODEL'
               AND arm_specification.model_id = model.model_id)
              OR
              (specification.exploratory_backtest_run_id IS NULL
               AND arm.arm_kind IN (
                   'MODEL_CHALLENGER', 'RIDGE_CURRENT_CONTEXT',
                   'RIDGE_CONTEXT_OBSERVATIONAL'
               ))
          )
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
    IF EXISTS (
        SELECT 1 FROM mra.backtest_specification
        WHERE exploratory_backtest_run_id = NEW.exploratory_backtest_run_id
    ) AND NOT EXISTS (
        SELECT 1 FROM mra.model_training_reproducibility
        WHERE model_training_run_id = NEW.model_training_run_id
    ) THEN
        RAISE EXCEPTION 'current Backtest ModelTrainingRun requires reproducibility closure'
            USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION mra.validate_research_partition_closure()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE actual_count integer;
DECLARE declared_population_count integer;
DECLARE minimum_ordinal integer;
DECLARE maximum_ordinal integer;
DECLARE actual_roster_hash text;
DECLARE actual_calendar_count integer;
DECLARE actual_calendar_hash text;
BEGIN
    LOCK TABLE mra.decision_target_commitment IN SHARE MODE;
    LOCK TABLE mra.context_assessment IN SHARE MODE;
    SELECT count(*), min(member_ordinal), max(member_ordinal)
      INTO actual_count, minimum_ordinal, maximum_ordinal
    FROM mra.research_partition_member
    WHERE research_partition_id = NEW.research_partition_id;

    SELECT count(*),
           mra.canonical_sha256(
               replace(
                   json_agg(
                       json_build_object(
                           'break_end_at', break_end_at,
                           'break_start_at', break_start_at,
                           'close_at', close_at,
                           'decision_reference_at', decision_reference_at,
                           'decision_visible_at', decision_visible_at,
                           'exchange_code', exchange,
                           'known_at', known_at,
                           'open_at', open_at,
                           'recorded_at', recorded_at,
                           'session_date', session_date,
                           'session_id', session_id,
                           'source_capture_id', source_capture_id,
                           'timezone_name', timezone_name
                       ) ORDER BY session_date, session_id
                   )::text,
                   ' ',
                   ''
               )
           )
      INTO actual_calendar_count, actual_calendar_hash
    FROM mra.trading_session
    WHERE exchange = NEW.exchange_code
      AND session_date BETWEEN
          NEW.protected_start_date AND NEW.protected_end_date;

    SELECT count(*) INTO declared_population_count
    FROM mra.decision_target_commitment AS commitment
    JOIN mra.decision_reference_observation AS reference
      ON reference.decision_reference_observation_id =
         commitment.decision_reference_observation_id
    JOIN mra.trading_session AS session
      ON session.session_id = reference.session_id
    LEFT JOIN mra.exploratory_retrospective_decision_run AS backtest
      ON backtest.decision_run_id = commitment.decision_run_id
    WHERE commitment.target_definition_id = NEW.target_definition_id
      AND session.exchange = NEW.exchange_code
      AND session.session_date BETWEEN
          NEW.decision_start_date AND NEW.decision_end_date
      AND (NEW.population_scope = 'ALL_COMMITMENTS'
           OR commitment.candidate_disposition = NEW.population_scope)
      AND (NEW.source_backtest_run_id IS NULL OR (
            backtest.exploratory_backtest_run_id = NEW.source_backtest_run_id
        AND backtest.exploratory_backtest_arm_id = NEW.source_backtest_arm_id
        AND ((NEW.source_backtest_fold_id IS NOT NULL
              AND backtest.exploratory_backtest_fold_id =
                  NEW.source_backtest_fold_id)
          OR (NEW.source_backtest_fold_id IS NULL AND EXISTS (
              SELECT 1 FROM mra.exploratory_backtest_fold AS source_fold
              WHERE source_fold.exploratory_backtest_fold_id =
                    backtest.exploratory_backtest_fold_id
                AND source_fold.exploratory_backtest_run_id =
                    NEW.source_backtest_run_id
                AND source_fold.purpose = 'VALIDATION'
          )))))
      AND (NEW.source_context_kind IS NULL OR EXISTS (
          SELECT 1
          FROM mra.context_assessment AS context
          JOIN mra.backtest_arm_specification AS source_arm
            ON source_arm.exploratory_backtest_run_id =
               NEW.source_backtest_run_id
           AND source_arm.exploratory_backtest_arm_id =
               NEW.source_backtest_arm_id
           AND source_arm.specification_sha256 =
               NEW.source_backtest_sha256
          WHERE context.decision_run_id = commitment.decision_run_id
            AND context.context_policy_id = source_arm.context_policy_id
            AND context.context_policy_content_sha256 =
                source_arm.context_policy_sha256
            AND context.context_kind = NEW.source_context_kind
            AND context.assessment_state = NEW.source_context_state
      ));

    SELECT mra.canonical_sha256(
               replace(
                   coalesce(json_agg(
                       json_build_object(
                           'commitment_id', commitment_id,
                           'content_sha256', content_sha256,
                           'member_ordinal', member_ordinal
                       ) ORDER BY member_ordinal
                   ), '[]'::json)::text,
                   ' ',
                   ''
               )
           )
      INTO actual_roster_hash
    FROM mra.research_partition_member
    WHERE research_partition_id = NEW.research_partition_id;

    IF actual_calendar_count <> NEW.calendar_session_count
       OR actual_calendar_hash <> NEW.calendar_roster_sha256
       OR actual_count <> NEW.member_count
       OR actual_count <> declared_population_count
       OR actual_roster_hash <> NEW.member_roster_sha256
       OR NOT (
           (actual_count > 0 AND minimum_ordinal = 1
            AND maximum_ordinal = NEW.member_count)
           OR (actual_count = 0 AND NEW.source_backtest_run_id IS NOT NULL
               AND minimum_ordinal IS NULL AND maximum_ordinal IS NULL)
       ) OR EXISTS (
           SELECT 1 FROM mra.research_partition_member AS member
           JOIN mra.trading_session AS session
             ON session.session_id = member.decision_session_id
           WHERE member.research_partition_id = NEW.research_partition_id
             AND (member.target_definition_id <> NEW.target_definition_id
                  OR member.exchange_code <> NEW.exchange_code
                  OR member.timezone_name <> NEW.timezone_name
                  OR member.decision_session_date <> session.session_date
                  OR session.session_date NOT BETWEEN
                     NEW.decision_start_date AND NEW.decision_end_date)
       ) OR EXISTS (
           (
               SELECT commitment.commitment_id
               FROM mra.decision_target_commitment AS commitment
               JOIN mra.decision_reference_observation AS reference
                 ON reference.decision_reference_observation_id =
                    commitment.decision_reference_observation_id
               JOIN mra.trading_session AS session
                 ON session.session_id = reference.session_id
               LEFT JOIN mra.exploratory_retrospective_decision_run AS backtest
                 ON backtest.decision_run_id = commitment.decision_run_id
               WHERE commitment.target_definition_id =
                     NEW.target_definition_id
                 AND session.exchange = NEW.exchange_code
                 AND session.session_date BETWEEN
                     NEW.decision_start_date AND NEW.decision_end_date
                 AND (NEW.population_scope = 'ALL_COMMITMENTS'
                      OR commitment.candidate_disposition =
                         NEW.population_scope)
                 AND (NEW.source_backtest_run_id IS NULL OR (
                       backtest.exploratory_backtest_run_id =
                           NEW.source_backtest_run_id
                   AND backtest.exploratory_backtest_arm_id =
                           NEW.source_backtest_arm_id
                   AND ((NEW.source_backtest_fold_id IS NOT NULL
                         AND backtest.exploratory_backtest_fold_id =
                             NEW.source_backtest_fold_id)
                     OR (NEW.source_backtest_fold_id IS NULL AND EXISTS (
                         SELECT 1
                         FROM mra.exploratory_backtest_fold AS source_fold
                         WHERE source_fold.exploratory_backtest_fold_id =
                               backtest.exploratory_backtest_fold_id
                           AND source_fold.exploratory_backtest_run_id =
                               NEW.source_backtest_run_id
                           AND source_fold.purpose = 'VALIDATION'
                     )))))
                 AND (NEW.source_context_kind IS NULL OR EXISTS (
                     SELECT 1
                     FROM mra.context_assessment AS context
                     JOIN mra.backtest_arm_specification AS source_arm
                       ON source_arm.exploratory_backtest_run_id =
                          NEW.source_backtest_run_id
                      AND source_arm.exploratory_backtest_arm_id =
                          NEW.source_backtest_arm_id
                      AND source_arm.specification_sha256 =
                          NEW.source_backtest_sha256
                     WHERE context.decision_run_id = commitment.decision_run_id
                       AND context.context_policy_id =
                           source_arm.context_policy_id
                       AND context.context_policy_content_sha256 =
                           source_arm.context_policy_sha256
                       AND context.context_kind = NEW.source_context_kind
                       AND context.assessment_state = NEW.source_context_state
                 ))
           )
           EXCEPT
           (
               SELECT member.commitment_id
               FROM mra.research_partition_member AS member
               WHERE member.research_partition_id =
                     NEW.research_partition_id
           )
       ) OR EXISTS (
           (
               SELECT member.commitment_id
               FROM mra.research_partition_member AS member
               WHERE member.research_partition_id =
                     NEW.research_partition_id
           )
           EXCEPT
           (
               SELECT commitment.commitment_id
               FROM mra.decision_target_commitment AS commitment
               JOIN mra.decision_reference_observation AS reference
                 ON reference.decision_reference_observation_id =
                    commitment.decision_reference_observation_id
               JOIN mra.trading_session AS session
                 ON session.session_id = reference.session_id
               LEFT JOIN mra.exploratory_retrospective_decision_run AS backtest
                 ON backtest.decision_run_id = commitment.decision_run_id
               WHERE commitment.target_definition_id =
                     NEW.target_definition_id
                 AND session.exchange = NEW.exchange_code
                 AND session.session_date BETWEEN
                     NEW.decision_start_date AND NEW.decision_end_date
                 AND (NEW.population_scope = 'ALL_COMMITMENTS'
                      OR commitment.candidate_disposition =
                         NEW.population_scope)
                 AND (NEW.source_backtest_run_id IS NULL OR (
                       backtest.exploratory_backtest_run_id =
                           NEW.source_backtest_run_id
                   AND backtest.exploratory_backtest_arm_id =
                           NEW.source_backtest_arm_id
                   AND ((NEW.source_backtest_fold_id IS NOT NULL
                         AND backtest.exploratory_backtest_fold_id =
                             NEW.source_backtest_fold_id)
                     OR (NEW.source_backtest_fold_id IS NULL AND EXISTS (
                         SELECT 1
                         FROM mra.exploratory_backtest_fold AS source_fold
                         WHERE source_fold.exploratory_backtest_fold_id =
                               backtest.exploratory_backtest_fold_id
                           AND source_fold.exploratory_backtest_run_id =
                               NEW.source_backtest_run_id
                           AND source_fold.purpose = 'VALIDATION'
                     )))))
                 AND (NEW.source_context_kind IS NULL OR EXISTS (
                     SELECT 1
                     FROM mra.context_assessment AS context
                     JOIN mra.backtest_arm_specification AS source_arm
                       ON source_arm.exploratory_backtest_run_id =
                          NEW.source_backtest_run_id
                      AND source_arm.exploratory_backtest_arm_id =
                          NEW.source_backtest_arm_id
                      AND source_arm.specification_sha256 =
                          NEW.source_backtest_sha256
                     WHERE context.decision_run_id = commitment.decision_run_id
                       AND context.context_policy_id =
                           source_arm.context_policy_id
                       AND context.context_policy_content_sha256 =
                           source_arm.context_policy_sha256
                       AND context.context_kind = NEW.source_context_kind
                       AND context.assessment_state = NEW.source_context_state
                 ))
           )
       ) THEN
        RAISE EXCEPTION 'ResearchPartition member roster is incomplete or outside declaration' USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;

CREATE INDEX evaluation_metric_formula_protocol_idx
    ON mra.evaluation_metric_formula(evaluation_protocol_id);

CREATE INDEX evaluation_formula_parameter_owner_idx
    ON mra.evaluation_formula_parameter(
        evaluation_protocol_metric_id, evaluation_protocol_id,
        formula_content_sha256
    );

CREATE INDEX backtest_specification_eligibility_idx
    ON mra.backtest_specification (
        eligibility_policy_id, eligibility_policy_sha256
    );

CREATE INDEX backtest_runtime_binding_run_idx
    ON mra.backtest_runtime_binding(exploratory_backtest_run_id, action_kind);

CREATE INDEX backtest_runtime_binding_action_idx
    ON mra.backtest_runtime_binding(action_id, action_content_sha256);

CREATE INDEX backtest_runtime_binding_specification_idx
    ON mra.backtest_runtime_binding(
        exploratory_backtest_run_id, specification_sha256
    );

CREATE INDEX backtest_model_lineage_run_idx
    ON mra.backtest_model_lineage(exploratory_backtest_run_id);

CREATE INDEX backtest_model_lineage_specification_idx
    ON mra.backtest_model_lineage(
        exploratory_backtest_run_id, specification_sha256
    );

CREATE INDEX backtest_model_lineage_model_idx
    ON mra.backtest_model_lineage(model_id);

CREATE INDEX backtest_model_lineage_evaluation_idx
    ON mra.backtest_model_lineage(backtest_evaluation_execution_id);

CREATE INDEX backtest_model_lineage_training_idx
    ON mra.backtest_model_lineage(model_training_run_id);

CREATE INDEX backtest_model_lineage_version_idx
    ON mra.backtest_model_lineage(model_version_id);

CREATE INDEX backtest_runtime_binding_arm_idx
    ON mra.backtest_runtime_binding(
        exploratory_backtest_arm_id, exploratory_backtest_run_id
    );

CREATE INDEX backtest_runtime_binding_fold_idx
    ON mra.backtest_runtime_binding(
        exploratory_backtest_fold_id, exploratory_backtest_run_id
    );

CREATE INDEX backtest_runtime_binding_session_idx
    ON mra.backtest_runtime_binding(exploratory_backtest_fold_session_id);

CREATE INDEX backtest_runtime_binding_model_requirement_idx
    ON mra.backtest_runtime_binding(model_training_requirement_id);

CREATE INDEX backtest_runtime_binding_evaluation_requirement_idx
    ON mra.backtest_runtime_binding(evaluation_requirement_id);

CREATE INDEX backtest_evaluation_execution_backtest_idx
    ON mra.backtest_evaluation_execution(exploratory_backtest_run_id);

CREATE INDEX backtest_evaluation_execution_specification_idx
    ON mra.backtest_evaluation_execution(
        exploratory_backtest_run_id, specification_sha256
    );

CREATE INDEX backtest_evaluation_execution_protocol_idx
    ON mra.backtest_evaluation_execution(evaluation_protocol_id);

CREATE INDEX backtest_evaluation_execution_run_idx
    ON mra.backtest_evaluation_execution(
        evaluation_run_id, evaluation_protocol_id
    );

CREATE INDEX backtest_report_artifact_specification_idx
    ON mra.backtest_report_artifact(
        exploratory_backtest_run_id, specification_sha256
    );

CREATE INDEX backtest_report_artifact_json_idx
    ON mra.backtest_report_artifact(
        json_artifact_id, json_content_sha256, json_size_bytes
    );

CREATE INDEX backtest_report_artifact_markdown_idx
    ON mra.backtest_report_artifact(
        markdown_artifact_id, markdown_content_sha256, markdown_size_bytes
    );

CREATE INDEX research_partition_backtest_source_idx
    ON mra.research_partition(
        source_backtest_run_id, source_backtest_arm_id,
        source_backtest_fold_id, source_context_kind, source_context_state
    ) WHERE source_backtest_run_id IS NOT NULL;

CREATE INDEX research_partition_backtest_run_fk_idx
    ON mra.research_partition(
        source_backtest_run_id, source_backtest_sha256
    );

CREATE INDEX research_partition_backtest_arm_fk_idx
    ON mra.research_partition(
        source_backtest_arm_id, source_backtest_run_id,
        source_backtest_sha256
    );

CREATE INDEX research_partition_backtest_fold_fk_idx
    ON mra.research_partition(
        source_backtest_fold_id, source_backtest_run_id,
        source_backtest_sha256
    );

CREATE INDEX backtest_model_requirement_metric_idx
    ON mra.backtest_model_training_requirement(
        required_fit_evaluation_protocol_metric_id,
        required_fit_evaluation_protocol_id,
        required_fit_evaluation_metric_sha256
    );

CREATE INDEX backtest_model_training_dependency_owner_idx
    ON mra.backtest_model_training_dependency(
        backtest_model_training_requirement_id,
        exploratory_backtest_run_id, specification_sha256
    );

CREATE INDEX backtest_model_training_hyperparameter_owner_idx
    ON mra.backtest_model_training_hyperparameter(
        backtest_model_training_requirement_id,
        exploratory_backtest_run_id, specification_sha256
    );

CREATE TRIGGER evaluation_metric_formula_append_only
BEFORE UPDATE OR DELETE ON mra.evaluation_metric_formula
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();

CREATE TRIGGER evaluation_metric_formula_open_guard
BEFORE INSERT ON mra.evaluation_metric_formula
FOR EACH ROW EXECUTE FUNCTION mra.guard_open_evaluation_protocol_metric();

CREATE CONSTRAINT TRIGGER evaluation_metric_formula_closure_guard
AFTER INSERT ON mra.evaluation_metric_formula
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION mra.validate_evaluation_formula_closure();

CREATE TRIGGER evaluation_formula_parameter_append_only
BEFORE UPDATE OR DELETE ON mra.evaluation_formula_parameter
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();

CREATE TRIGGER evaluation_formula_parameter_open_guard
BEFORE INSERT ON mra.evaluation_formula_parameter
FOR EACH ROW EXECUTE FUNCTION mra.guard_open_evaluation_protocol_metric();

CREATE TRIGGER evaluation_metric_formula_result_guard
BEFORE INSERT ON mra.evaluation_metric
FOR EACH ROW EXECUTE FUNCTION mra.guard_evaluation_metric_formula_result();

CREATE CONSTRAINT TRIGGER model_training_reproducibility_reconcile_guard
AFTER INSERT ON mra.model_training_reproducibility
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION mra.validate_model_training_reproducibility();

CREATE TRIGGER model_training_reproducibility_append_only
BEFORE UPDATE OR DELETE ON mra.model_training_reproducibility
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();

CREATE TRIGGER model_training_dependency_append_only
BEFORE UPDATE OR DELETE ON mra.model_training_dependency
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();

CREATE TRIGGER model_training_hyperparameter_append_only
BEFORE UPDATE OR DELETE ON mra.model_training_hyperparameter
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();

CREATE TRIGGER backtest_runtime_binding_guard
BEFORE INSERT ON mra.backtest_runtime_binding
FOR EACH ROW EXECUTE FUNCTION mra.validate_backtest_runtime_binding();

CREATE TRIGGER backtest_runtime_binding_append_only
BEFORE UPDATE OR DELETE ON mra.backtest_runtime_binding
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();

CREATE TRIGGER backtest_evaluation_execution_guard
BEFORE INSERT ON mra.backtest_evaluation_execution
FOR EACH ROW EXECUTE FUNCTION mra.validate_backtest_evaluation_execution();

CREATE TRIGGER backtest_evaluation_execution_append_only
BEFORE UPDATE OR DELETE ON mra.backtest_evaluation_execution
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();

CREATE TRIGGER backtest_model_lineage_guard
BEFORE INSERT ON mra.backtest_model_lineage
FOR EACH ROW EXECUTE FUNCTION mra.validate_backtest_model_lineage();

CREATE TRIGGER backtest_model_lineage_append_only
BEFORE UPDATE OR DELETE ON mra.backtest_model_lineage
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();

CREATE TRIGGER backtest_report_artifact_guard
BEFORE INSERT ON mra.backtest_report_artifact
FOR EACH ROW EXECUTE FUNCTION mra.validate_backtest_report_artifact();

CREATE TRIGGER backtest_report_artifact_append_only
BEFORE UPDATE OR DELETE ON mra.backtest_report_artifact
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();

CREATE TRIGGER backtest_model_training_dependency_append_only
BEFORE UPDATE OR DELETE ON mra.backtest_model_training_dependency
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();

CREATE TRIGGER backtest_model_training_hyperparameter_append_only
BEFORE UPDATE OR DELETE ON mra.backtest_model_training_hyperparameter
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
