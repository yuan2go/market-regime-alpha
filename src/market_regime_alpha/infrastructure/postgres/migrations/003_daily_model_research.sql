-- Daily post-close research contract v1. Prior migration bytes and facts remain unchanged.

CREATE FUNCTION mra.validate_daily_observation_return() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM mra.target_metric_definition metric
        WHERE metric.target_definition_id = NEW.target_definition_id
          AND metric.metric_kind = 'OBSERVATION_RETURN'
          AND NOT EXISTS (
            SELECT 1 FROM mra.target_metric_dependency a
            JOIN mra.target_metric_dependency b ON b.target_metric_definition_id = a.target_metric_definition_id AND b.ordinal = 2
            JOIN mra.target_checkpoint start ON start.target_checkpoint_id = a.target_checkpoint_id
            JOIN mra.target_checkpoint finish ON finish.target_checkpoint_id = b.target_checkpoint_id
            WHERE a.target_metric_definition_id = metric.target_metric_definition_id AND a.ordinal = 1
              AND a.dependency_role = 'OBSERVATION' AND b.dependency_role = 'OBSERVATION'
              AND start.checkpoint_role = 'OUTCOME_OBSERVATION' AND finish.checkpoint_role = 'OUTCOME_OBSERVATION'
              AND start.session_offset > 0 AND start.session_offset = finish.session_offset
              AND start.local_time = finish.local_time AND start.timezone_name = finish.timezone_name
              AND start.timeframe = 'DAILY' AND finish.timeframe = 'DAILY'
              AND start.price_basis = 'RAW_UNADJUSTED' AND finish.price_basis = 'RAW_UNADJUSTED'
              AND start.value_field = 'OPEN' AND finish.value_field = 'CLOSE'
              AND (SELECT count(*) FROM mra.target_metric_dependency d WHERE d.target_metric_definition_id = metric.target_metric_definition_id) = 2
          )
    ) THEN
        RAISE EXCEPTION 'OBSERVATION_RETURN requires two exact same-session raw daily OPEN/CLOSE observations' USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;

CREATE CONSTRAINT TRIGGER target_daily_return_guard AFTER INSERT ON mra.target_definition
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION mra.validate_daily_observation_return();
CREATE CONSTRAINT TRIGGER target_metric_daily_return_guard AFTER INSERT ON mra.target_metric_definition
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION mra.validate_daily_observation_return();
CREATE CONSTRAINT TRIGGER target_dependency_daily_return_guard AFTER INSERT ON mra.target_metric_dependency
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION mra.validate_daily_observation_return();

ALTER TABLE mra.target_metric_definition
    DROP CONSTRAINT target_metric_vocabulary_ck,
    ADD CONSTRAINT target_metric_vocabulary_ck CHECK (
        metric_code ~ '^[a-z][a-z0-9_]{0,99}$'
        AND ordinal > 0
        AND metric_kind IN (
            'SIMPLE_RETURN', 'MAX_FAVORABLE_EXCURSION',
            'MAX_ADVERSE_EXCURSION', 'OBSERVATION_RETURN', 'BARRIER_HIT',
            'OBSERVATION_VALUE'
        )
        AND value_type IN ('DECIMAL', 'BOOLEAN')
        AND unit IN ('RATIO', 'PRICE', 'BOOLEAN')
        AND completion_rule IN ('REQUIRED', 'OPTIONAL')
    );

ALTER TABLE mra.target_metric_definition
    DROP CONSTRAINT target_metric_value_shape_ck,
    ADD CONSTRAINT target_metric_value_shape_ck CHECK (
        (metric_kind IN (
            'SIMPLE_RETURN', 'MAX_FAVORABLE_EXCURSION',
            'MAX_ADVERSE_EXCURSION', 'OBSERVATION_RETURN'
         ) AND value_type = 'DECIMAL' AND unit = 'RATIO')
        OR
        (metric_kind = 'OBSERVATION_VALUE'
         AND value_type = 'DECIMAL' AND unit = 'PRICE')
        OR
        (metric_kind = 'BARRIER_HIT'
         AND value_type = 'BOOLEAN' AND unit = 'BOOLEAN')
    );

ALTER TABLE mra.market_target_outcome_metric
    DROP CONSTRAINT outcome_metric_state_ck,
    ADD CONSTRAINT outcome_metric_state_ck CHECK (
        metric_ordinal > 0
        AND metric_kind IN (
            'SIMPLE_RETURN', 'MAX_FAVORABLE_EXCURSION',
            'MAX_ADVERSE_EXCURSION', 'OBSERVATION_RETURN', 'BARRIER_HIT',
            'OBSERVATION_VALUE'
        )
        AND value_type IN ('DECIMAL', 'BOOLEAN')
        AND unit IN ('RATIO', 'PRICE', 'BOOLEAN')
        AND completion_rule IN ('REQUIRED', 'OPTIONAL')
        AND value_status IN ('PARTIAL', 'COMPLETE', 'UNAVAILABLE', 'FAILED')
        AND availability_status IN ('AVAILABLE', 'UNAVAILABLE', 'FAILED')
        AND finality_status = 'UNKNOWN'
        AND target_metric_sha256 ~ '^[0-9a-f]{64}$'
        AND content_sha256 ~ '^[0-9a-f]{64}$'
        AND (
            (value_status IN ('COMPLETE', 'PARTIAL')
             AND availability_status = 'AVAILABLE'
             AND ((value_type = 'DECIMAL'
                   AND decimal_value IS NOT NULL AND boolean_value IS NULL)
                  OR
                  (value_type = 'BOOLEAN'
                   AND decimal_value IS NULL AND boolean_value IS NOT NULL)))
            OR
            (value_status = 'UNAVAILABLE'
             AND availability_status = 'UNAVAILABLE'
             AND decimal_value IS NULL AND boolean_value IS NULL
             AND first_passage_at IS NULL)
            OR
            (value_status = 'FAILED'
             AND availability_status = 'FAILED'
             AND decimal_value IS NULL AND boolean_value IS NULL
             AND first_passage_at IS NULL)
        )
        AND (first_passage_at IS NULL OR metric_kind = 'BARRIER_HIT')
        AND created_at >= first_passage_at
    );

CREATE TABLE mra.experimental_model_use (
    experimental_model_use_id uuid PRIMARY KEY,
    model_version_id uuid NOT NULL REFERENCES mra.model_version(model_version_id) ON DELETE RESTRICT,
    target_metric_definition_id uuid NOT NULL REFERENCES mra.target_metric_definition(target_metric_definition_id) ON DELETE RESTRICT,
    baseline_strategy_version_id uuid NOT NULL REFERENCES mra.strategy_version(strategy_version_id) ON DELETE RESTRICT,
    feature_roster_sha256 text NOT NULL,
    protocol_artifact_id uuid NOT NULL,
    protocol_content_sha256 text NOT NULL,
    protocol_size_bytes bigint NOT NULL,
    valid_from timestamptz NOT NULL,
    expires_at timestamptz NOT NULL,
    purpose text NOT NULL,
    content_sha256 text NOT NULL,
    registered_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT experimental_use_protocol_fk FOREIGN KEY (protocol_artifact_id, protocol_content_sha256, protocol_size_bytes)
        REFERENCES mra.artifact(artifact_id, content_sha256, size_bytes) ON DELETE RESTRICT,
    CONSTRAINT experimental_use_shape_ck CHECK (
        purpose = 'POST_CLOSE_RESEARCH' AND feature_roster_sha256 ~ '^[0-9a-f]{64}$'
        AND content_sha256 ~ '^[0-9a-f]{64}$' AND valid_from < expires_at AND registered_at < expires_at
        AND valid_from > '-infinity'::timestamptz AND expires_at < 'infinity'::timestamptz
    ),
    CONSTRAINT experimental_use_hash_ck CHECK (content_sha256 = mra.canonical_sha256(mra.canonical_json_text(jsonb_build_object(
        'experimental_model_use_id', experimental_model_use_id, 'model_version_id', model_version_id,
        'baseline_strategy_version_id', baseline_strategy_version_id, 'target_metric_definition_id', target_metric_definition_id, 'feature_roster_sha256', feature_roster_sha256,
        'protocol_artifact', jsonb_build_object('artifact_id', protocol_artifact_id, 'content_sha256', jsonb_build_object('value',protocol_content_sha256), 'size_bytes', protocol_size_bytes),
        'valid_from', mra.canonical_timestamptz_text(valid_from), 'expires_at', mra.canonical_timestamptz_text(expires_at), 'purpose', purpose
    ))))
);
CREATE INDEX experimental_use_baseline_idx ON mra.experimental_model_use(baseline_strategy_version_id);
CREATE INDEX experimental_use_model_idx ON mra.experimental_model_use(model_version_id);
CREATE INDEX experimental_use_target_idx ON mra.experimental_model_use(target_metric_definition_id);
CREATE INDEX experimental_use_protocol_idx ON mra.experimental_model_use(protocol_artifact_id, protocol_content_sha256, protocol_size_bytes);
CREATE TRIGGER experimental_use_append_only BEFORE UPDATE OR DELETE ON mra.experimental_model_use
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();

CREATE TABLE mra.experimental_model_use_revocation (
    experimental_model_use_id uuid PRIMARY KEY REFERENCES mra.experimental_model_use(experimental_model_use_id) ON DELETE RESTRICT,
    revoked_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TRIGGER experimental_use_revocation_append_only BEFORE UPDATE OR DELETE ON mra.experimental_model_use_revocation
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();

CREATE FUNCTION mra.validate_experimental_model_use() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM mra.model_version version JOIN mra.model model USING (model_id)
        JOIN mra.model_training_run training ON training.model_training_run_id=version.model_training_run_id
        JOIN mra.model_training_reproducibility repro ON repro.model_training_run_id=training.model_training_run_id
        JOIN mra.evaluation_run evaluation ON evaluation.evaluation_run_id=training.evaluation_run_id
          AND evaluation.status='COMPLETED' AND evaluation.partition_purpose='FIT'
        JOIN mra.evaluation_protocol_metric metric ON metric.evaluation_protocol_metric_id=training.evaluation_protocol_metric_id
        JOIN mra.target_metric_definition target ON target.target_metric_definition_id=metric.source_target_metric_definition_id
          AND target.target_definition_id=model.target_definition_id
        WHERE version.model_version_id=NEW.model_version_id AND version.registered_at < NEW.registered_at
          AND model.feature_roster_sha256=NEW.feature_roster_sha256
          AND target.target_metric_definition_id=NEW.target_metric_definition_id AND target.metric_kind='OBSERVATION_RETURN'
          AND repro.training_knowledge_cutoff <= version.registered_at
          AND training.algorithm_code='deterministic_ridge'
          AND EXISTS (SELECT 1 FROM mra.strategy_forecast_rule rule WHERE rule.strategy_version_id=NEW.baseline_strategy_version_id
            AND rule.target_metric_definition_id=NEW.target_metric_definition_id AND rule.target_definition_id=model.target_definition_id)
    ) THEN
        RAISE EXCEPTION 'experimental use requires a completed compatible reproducible FIT model' USING ERRCODE='55000';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER experimental_use_guard BEFORE INSERT ON mra.experimental_model_use
FOR EACH ROW EXECUTE FUNCTION mra.validate_experimental_model_use();

ALTER TABLE mra.forecast_model_binding
    ADD COLUMN experimental_model_use_id uuid REFERENCES mra.experimental_model_use(experimental_model_use_id) ON DELETE RESTRICT,
    ALTER COLUMN exploratory_backtest_run_id DROP NOT NULL,
    ALTER COLUMN exploratory_backtest_arm_id DROP NOT NULL,
    ALTER COLUMN exploratory_backtest_fold_id DROP NOT NULL,
    ALTER COLUMN exploratory_backtest_fold_session_id DROP NOT NULL,
    ALTER COLUMN inference_fold_ordinal DROP NOT NULL,
    DROP CONSTRAINT forecast_model_decision_fk,
    DROP CONSTRAINT forecast_model_dataset_fk,
    ADD CONSTRAINT forecast_model_decision_fk FOREIGN KEY (decision_run_id) REFERENCES mra.decision_run(decision_run_id) ON DELETE RESTRICT,
    ADD CONSTRAINT forecast_model_dataset_fk FOREIGN KEY (dataset_id) REFERENCES mra.dataset(dataset_id) ON DELETE RESTRICT,
    ADD CONSTRAINT forecast_model_use_scope_ck CHECK (
        (experimental_model_use_id IS NULL AND exploratory_backtest_run_id IS NOT NULL
          AND exploratory_backtest_arm_id IS NOT NULL AND exploratory_backtest_fold_id IS NOT NULL
          AND exploratory_backtest_fold_session_id IS NOT NULL AND inference_fold_ordinal IS NOT NULL)
        OR
        (experimental_model_use_id IS NOT NULL AND exploratory_backtest_run_id IS NULL
          AND exploratory_backtest_arm_id IS NULL AND exploratory_backtest_fold_id IS NULL
          AND exploratory_backtest_fold_session_id IS NULL AND inference_fold_ordinal IS NULL)
    );
CREATE INDEX forecast_model_experimental_use_idx ON mra.forecast_model_binding(experimental_model_use_id);
-- Old function/serialization remains exact, and is used only for its original lane.
DROP TRIGGER forecast_model_binding_guard ON mra.forecast_model_binding;
CREATE TRIGGER forecast_model_binding_guard BEFORE INSERT ON mra.forecast_model_binding
FOR EACH ROW WHEN (NEW.experimental_model_use_id IS NULL) EXECUTE FUNCTION mra.validate_forecast_model_binding();

CREATE FUNCTION mra.validate_experimental_forecast_model_binding() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE expected_input text;
DECLARE expected_output text;
DECLARE expected_content text;
BEGIN
    PERFORM experimental_model_use_id FROM mra.experimental_model_use WHERE experimental_model_use_id=NEW.experimental_model_use_id FOR SHARE;
    IF NOT EXISTS (
        SELECT 1 FROM mra.experimental_model_use usage
        JOIN mra.model_version version ON version.model_version_id=usage.model_version_id
        JOIN mra.model model ON model.model_id=version.model_id AND model.feature_roster_sha256=usage.feature_roster_sha256
        JOIN mra.model_training_run training ON training.model_training_run_id=version.model_training_run_id
          AND training.exploratory_backtest_fold_id=NEW.training_fold_id
        JOIN mra.exploratory_backtest_fold fold ON fold.exploratory_backtest_fold_id=training.exploratory_backtest_fold_id AND fold.ordinal=NEW.training_fold_ordinal AND fold.purpose='FIT'
        JOIN mra.model_training_reproducibility repro ON repro.model_training_run_id=training.model_training_run_id
        JOIN mra.decision_run decision ON decision.decision_run_id=NEW.decision_run_id AND decision.dataset_id=NEW.dataset_id
        JOIN mra.forecast forecast ON forecast.forecast_id=NEW.forecast_id AND forecast.target_definition_id=model.target_definition_id
        JOIN mra.forecast_estimate estimate ON estimate.forecast_estimate_id=NEW.forecast_estimate_id AND estimate.forecast_id=forecast.forecast_id
        WHERE usage.experimental_model_use_id=NEW.experimental_model_use_id AND usage.purpose='POST_CLOSE_RESEARCH'
          AND usage.model_version_id=NEW.model_version_id AND usage.target_metric_definition_id=NEW.target_metric_definition_id
          AND usage.registered_at < decision.decision_time AND usage.valid_from <= decision.decision_time
          AND version.registered_at < decision.decision_time AND decision.decision_time < forecast.recorded_at
          AND forecast.recorded_at < usage.expires_at AND clock_timestamp() < usage.expires_at
          AND decision.research_purpose='DISCOVERY'
          AND mra.experimental_forecast_window_is_open(decision.decision_run_id, NEW.forecast_recorded_at)
          AND mra.experimental_forecast_window_is_open(decision.decision_run_id, clock_timestamp())
          AND NOT EXISTS (SELECT 1 FROM mra.exploratory_retrospective_dataset r WHERE r.dataset_id=decision.dataset_id)
          AND NOT EXISTS (SELECT 1 FROM mra.experimental_model_use_revocation r WHERE r.experimental_model_use_id=usage.experimental_model_use_id)
          AND EXISTS (SELECT 1 FROM mra.forecast baseline
            JOIN mra.forecast_estimate baseline_estimate ON baseline_estimate.forecast_id=baseline.forecast_id
            WHERE baseline.commitment_id=NEW.commitment_id AND baseline.target_definition_id=model.target_definition_id
              AND baseline.strategy_version_id=usage.baseline_strategy_version_id
              AND baseline_estimate.target_metric_definition_id=NEW.target_metric_definition_id
              AND baseline.recorded_at<=forecast.recorded_at AND baseline.recorded_at>decision.decision_time)
          AND forecast.forecast_group_id=NEW.forecast_group_id AND forecast.decision_run_id=NEW.decision_run_id
          AND forecast.strategy_version_id=NEW.strategy_version_id AND forecast.commitment_id=NEW.commitment_id
          AND forecast.recorded_at=NEW.forecast_recorded_at AND forecast.status=NEW.status
          AND forecast.calibration_status=NEW.calibration_status AND forecast.reason_code=NEW.reason_code
          AND estimate.target_metric_definition_id=NEW.target_metric_definition_id
          AND estimate.point_estimate IS NOT DISTINCT FROM NEW.point_estimate
          AND repro.training_knowledge_cutoff <= version.registered_at
          AND NOT EXISTS (SELECT 1 FROM mra.model_training_sample sample
              JOIN mra.decision_run source ON source.decision_run_id=sample.decision_run_id
              JOIN mra.market_target_outcome_revision outcome ON outcome.market_target_outcome_revision_id=sample.market_target_outcome_revision_id
              WHERE sample.model_training_run_id=training.model_training_run_id
              AND (source.decision_time >= decision.decision_time OR outcome.knowledge_cutoff > repro.training_knowledge_cutoff))
    ) THEN
        RAISE EXCEPTION 'experimental model inference is incompatible, expired, revoked or temporally invalid' USING ERRCODE='55000';
    END IF;
    expected_input := mra.canonical_sha256(mra.canonical_json_text(
        jsonb_build_object(
            'experimental_model_use_id', NEW.experimental_model_use_id,
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
            'experimental_model_use_id', NEW.experimental_model_use_id,
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
CREATE TRIGGER experimental_forecast_model_binding_guard BEFORE INSERT ON mra.forecast_model_binding
FOR EACH ROW WHEN (NEW.experimental_model_use_id IS NOT NULL) EXECUTE FUNCTION mra.validate_experimental_forecast_model_binding();

ALTER TABLE mra.evaluation_protocol_metric DROP CONSTRAINT evaluation_protocol_metric_shape_ck, ADD CONSTRAINT evaluation_protocol_metric_shape_ck CHECK (
        ordinal > 0 AND metric_code ~ '^[a-z][a-z0-9_-]{0,99}$'
        AND source_metric_code ~ '^[a-z][a-z0-9_-]{0,99}$'
        AND source_value_type IN ('DECIMAL', 'BOOLEAN')
        AND source_kind IN ('OUTCOME_METRIC', 'FORECAST_OUTCOME_PAIR', 'EXPERIMENTAL_FORECAST_OUTCOME_PAIR',
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
          OR (source_kind IN ('FORECAST_OUTCOME_PAIR', 'EXPERIMENTAL_FORECAST_OUTCOME_PAIR') AND source_measure = 'FORECAST_POINT_VS_TARGET')
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
          OR (source_kind IN ('FORECAST_OUTCOME_PAIR', 'EXPERIMENTAL_FORECAST_OUTCOME_PAIR', 'PORTFOLIO_LINE',
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
             OR source_kind IN ('FORECAST_OUTCOME_PAIR', 'EXPERIMENTAL_FORECAST_OUTCOME_PAIR',
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

-- Existing outcome/backtest transitions keep their full original checks.
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
                    OR protocol_metric.source_kind NOT IN ('OUTCOME_METRIC', 'EXPERIMENTAL_FORECAST_OUTCOME_PAIR'))
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
               OR (protocol_metric.source_kind IN ('FORECAST_OUTCOME_PAIR', 'EXPERIMENTAL_FORECAST_OUTCOME_PAIR')
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

CREATE FUNCTION mra.validate_experimental_evaluation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.status <> 'COMPLETED' THEN RETURN NEW; END IF;
    IF EXISTS (
        SELECT 1 FROM mra.evaluation_protocol_metric metric
        JOIN mra.evaluation_metric_observation observation ON observation.evaluation_protocol_metric_id=metric.evaluation_protocol_metric_id
          AND observation.evaluation_run_id=NEW.evaluation_run_id
        LEFT JOIN mra.evaluation_metric_formula formula ON formula.evaluation_protocol_metric_id=metric.evaluation_protocol_metric_id
        LEFT JOIN mra.evaluation_formula_parameter parameter ON parameter.evaluation_protocol_metric_id=metric.evaluation_protocol_metric_id
          AND parameter.parameter_code='experimental_model_use_id' AND parameter.value_type='TEXT'
        LEFT JOIN mra.experimental_model_use usage ON usage.experimental_model_use_id::text=parameter.text_value
          AND usage.target_metric_definition_id=metric.source_target_metric_definition_id
        LEFT JOIN mra.evaluation_forecast_source source ON source.evaluation_metric_observation_id=observation.evaluation_metric_observation_id
        LEFT JOIN mra.evaluation_formula_parameter role ON role.evaluation_protocol_metric_id=metric.evaluation_protocol_metric_id
          AND role.parameter_code='forecast_role' AND role.value_type='TEXT'
        LEFT JOIN mra.forecast_model_binding binding ON binding.experimental_model_use_id=usage.experimental_model_use_id
          AND binding.commitment_id=source.commitment_id AND binding.decision_run_id=source.decision_run_id
        LEFT JOIN mra.forecast forecast ON forecast.forecast_id=source.forecast_id AND forecast.status=source.forecast_status
          AND forecast.commitment_id=binding.commitment_id
          AND ((coalesce(role.text_value,'MODEL')='MODEL' AND forecast.forecast_id=binding.forecast_id)
            OR (role.text_value='RULE_BASELINE' AND forecast.strategy_version_id=usage.baseline_strategy_version_id
              AND forecast.recorded_at<=binding.forecast_recorded_at))
        LEFT JOIN mra.forecast_estimate estimate ON estimate.forecast_estimate_id=source.forecast_estimate_id AND estimate.forecast_id=forecast.forecast_id
          AND estimate.target_metric_definition_id=metric.source_target_metric_definition_id
          AND estimate.point_estimate IS NOT DISTINCT FROM source.point_estimate
        JOIN mra.market_target_outcome_metric outcome ON outcome.market_target_outcome_metric_id=observation.source_outcome_metric_id
        WHERE metric.evaluation_protocol_id=NEW.evaluation_protocol_id AND metric.source_kind='EXPERIMENTAL_FORECAST_OUTCOME_PAIR'
          AND (formula.formula_version IS DISTINCT FROM 1 OR formula.surface_code IS DISTINCT FROM 'SIGNAL_FORECAST'
            OR metric.slice_kind <> 'ALL_MEMBERS' OR usage.experimental_model_use_id IS NULL
            OR binding.forecast_model_binding_id IS NULL OR forecast.forecast_id IS NULL OR estimate.forecast_estimate_id IS NULL
            OR outcome.decimal_value IS DISTINCT FROM source.outcome_decimal_value)
    ) THEN
        RAISE EXCEPTION 'independent experimental Forecast Evaluation lineage is not exact' USING ERRCODE='55000';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER experimental_evaluation_guard BEFORE UPDATE ON mra.evaluation_run
FOR EACH ROW EXECUTE FUNCTION mra.validate_experimental_evaluation();

CREATE FUNCTION mra.experimental_forecast_window_is_open(decision_id uuid, published_at timestamptz)
RETURNS boolean LANGUAGE sql STABLE AS $$
    SELECT coalesce((SELECT count(*) = decision.commitment_count AND bool_and(
        reference.timeframe='DAILY' AND reference.price_basis='RAW_UNADJUSTED'
        AND reference.event_end=input.close_at AND input.close_at <= decision.decision_time
        AND decision.decision_time < published_at AND published_at < next_session.open_at
        AND next_session.known_at <= decision.decision_time)
    FROM mra.decision_reference_observation reference
    JOIN mra.trading_session input ON input.session_id=reference.session_id
    JOIN LATERAL (
        SELECT following.open_at, capture.recorded_at AS known_at
        FROM mra.trading_session following JOIN mra.data_capture capture ON capture.capture_id=following.source_capture_id
        WHERE following.exchange=input.exchange AND following.session_date>input.session_date
        ORDER BY following.session_date LIMIT 1
    ) next_session ON true
    WHERE reference.decision_run_id=decision.decision_run_id), false)
    FROM mra.decision_run decision WHERE decision.decision_run_id=decision_id;
$$;

ALTER TABLE mra.target_checkpoint DROP CONSTRAINT target_checkpoint_vocabulary_ck, ADD CONSTRAINT target_checkpoint_vocabulary_ck CHECK (
        checkpoint_role IN ('DECISION_REFERENCE', 'OUTCOME_OBSERVATION')
        AND timing_rule = 'SESSION_LOCAL_BAR_END'
        AND timeframe IN (
            'MINUTE_1', 'MINUTE_5', 'MINUTE_15',
            'MINUTE_30', 'MINUTE_60', 'DAILY'
        )
        AND price_basis IN (
            'RAW_UNADJUSTED', 'FORWARD_ADJUSTED', 'BACKWARD_ADJUSTED'
        )
        AND value_field IN ('OPEN', 'HIGH', 'LOW', 'CLOSE')
        AND (reference_rule = 'EXACT_SESSION_BAR' OR (reference_rule = 'EXACT_COMPLETED_SESSION_DAILY_BAR' AND checkpoint_role='DECISION_REFERENCE' AND timeframe='DAILY' AND price_basis='RAW_UNADJUSTED' AND value_field='CLOSE'))
        AND availability_rule = 'EXACT_REVISION_OR_SOURCE_GAP'
        AND finality_rule = 'RECORD_UNKNOWN'
    );

-- Explicit post-close eligibility; existing NOT_SUSPENDED retains its session.
ALTER TABLE mra.eligibility_rule DROP CONSTRAINT eligibility_rule_kind_ck;
ALTER TABLE mra.eligibility_rule ADD CONSTRAINT eligibility_rule_kind_ck CHECK (
        rule_kind IN (
            'NOT_SUSPENDED', 'LAST_COMPLETED_SESSION_ACTIVE', 'NOT_SPECIAL_TREATMENT', 'MIN_LISTING_AGE',
            'MIN_LIQUIDITY', 'LIMIT_METADATA_PRESENT'
        )
    );
ALTER TABLE mra.eligibility_rule DROP CONSTRAINT eligibility_rule_shape_ck;
ALTER TABLE mra.eligibility_rule ADD CONSTRAINT eligibility_rule_shape_ck CHECK (
        (rule_kind IN ('NOT_SUSPENDED', 'LAST_COMPLETED_SESSION_ACTIVE')
         AND measure_code = 'SECURITY_STATUS'
         AND aggregation = 'POINT'
         AND window_value = 1 AND window_unit = 'SESSION'
         AND value_kind = 'STATUS' AND operator = 'EQ'
         AND threshold_status = 'ACTIVE'
         AND threshold_decimal IS NULL AND threshold_count IS NULL
         AND value_unit = 'STATUS')
        OR
        (rule_kind = 'NOT_SPECIAL_TREATMENT'
         AND measure_code = 'SPECIAL_TREATMENT_STATUS'
         AND aggregation = 'POINT'
         AND window_value = 0 AND window_unit = 'NONE'
         AND value_kind = 'STATUS' AND operator = 'EQ'
         AND threshold_status = 'NORMAL'
         AND threshold_decimal IS NULL AND threshold_count IS NULL
         AND value_unit = 'STATUS')
        OR
        (rule_kind = 'MIN_LISTING_AGE'
         AND measure_code = 'LISTING_AGE'
         AND aggregation = 'ELAPSED'
         AND window_value = 0 AND window_unit = 'NONE'
         AND value_kind = 'DECIMAL' AND operator = 'GTE'
         AND threshold_decimal >= 0
         AND threshold_status IS NULL AND threshold_count IS NULL
         AND value_unit = 'CALENDAR_DAYS')
        OR
        (rule_kind = 'MIN_LIQUIDITY'
         AND measure_code = 'TURNOVER_VALUE'
         AND aggregation = 'MEAN'
         AND window_value > 0 AND window_unit = 'SESSION'
         AND value_kind = 'DECIMAL' AND operator = 'GTE'
         AND threshold_decimal >= 0
         AND threshold_status IS NULL AND threshold_count IS NULL
         AND value_unit ~ '^[A-Z]{3}$')
        OR
        (rule_kind = 'LIMIT_METADATA_PRESENT'
         AND measure_code = 'LIMIT_PRICE_FACT_COUNT'
         AND aggregation = 'COUNT'
         AND window_value = 1 AND window_unit = 'SESSION'
         AND value_kind = 'COUNT' AND operator = 'GTE'
         AND threshold_count = 3
         AND threshold_status IS NULL AND threshold_decimal IS NULL
         AND value_unit = 'FACT_COUNT')
    );


ALTER TABLE mra.feature_definition ADD CONSTRAINT daily_feature_shape_ck CHECK (
    algorithm_code <> 'session_open_close_move_v1' OR (
        algorithm_version='1' AND value_type='DECIMAL' AND value_unit='RATIO'
        AND frequency_value=1 AND window_value=1 AND lookback_value=0
        AND frequency_unit='TRADING_SESSION' AND window_unit='TRADING_SESSION' AND lookback_unit='TRADING_SESSION'
        AND source_requirements=ARRAY['MARKET_BAR_REVISION']::text[]
        AND availability_rule='DECISION_VISIBLE_AT_OR_BEFORE' AND missingness_policy='EXPLICIT_STATUS'
    )
);
