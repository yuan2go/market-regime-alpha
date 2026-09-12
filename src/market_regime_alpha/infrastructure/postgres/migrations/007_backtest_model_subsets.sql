-- v2 explicitly permits exact per-Model ordered subsets of the Backtest data
-- roster. v1 and legacy retain their original ordinal/full-roster semantics.
CREATE OR REPLACE FUNCTION mra.model_backtest_feature_rosters_match(
    requested_model_id uuid, requested_backtest_run_id uuid
)
RETURNS boolean LANGUAGE plpgsql STABLE AS $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM mra.backtest_specification
        WHERE exploratory_backtest_run_id = requested_backtest_run_id
          AND specification_schema_version = 2
    ) THEN
        RETURN EXISTS (
            SELECT 1 FROM mra.model_feature_definition
            WHERE model_id = requested_model_id
        ) AND NOT EXISTS (
            SELECT 1 FROM mra.model_feature_definition AS feature
            WHERE feature.model_id = requested_model_id AND NOT EXISTS (
                SELECT 1 FROM mra.exploratory_backtest_feature AS available
                WHERE available.exploratory_backtest_run_id = requested_backtest_run_id
                  AND available.feature_definition_id = feature.feature_definition_id
                  AND available.feature_definition_sha256 = feature.feature_definition_sha256
            )
        );
    END IF;
    -- Model and Backtest use distinct aggregate-hash encodings. Compare their
    -- exact ordered child identities without rewriting either owner's hash.
    RETURN EXISTS (
        SELECT 1 FROM mra.model_feature_definition
        WHERE model_id = requested_model_id
    ) AND NOT EXISTS (
        SELECT 1
        FROM (
            SELECT ordinal, feature_definition_id, feature_definition_sha256
            FROM mra.model_feature_definition
            WHERE model_id = requested_model_id
        ) AS model_feature
        FULL JOIN (
            SELECT feature_ordinal AS ordinal,
                   feature_definition_id, feature_definition_sha256
            FROM mra.exploratory_backtest_feature
            WHERE exploratory_backtest_run_id = requested_backtest_run_id
        ) AS backtest_feature USING (ordinal)
        WHERE (model_feature.ordinal, model_feature.feature_definition_id,
               model_feature.feature_definition_sha256)
              IS DISTINCT FROM
              (backtest_feature.ordinal, backtest_feature.feature_definition_id,
               backtest_feature.feature_definition_sha256)
    );
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
         AND mra.model_backtest_feature_rosters_match(
             model.model_id, backtest.exploratory_backtest_run_id
         )
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
