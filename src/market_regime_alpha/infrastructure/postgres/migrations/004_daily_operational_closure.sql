-- Forward-only daily operational closure correction.
--
-- Historical ResearchPartition rows remain unchanged: the new source is null
-- for every existing row, so their complete-population meaning is preserved.
-- A daily Evaluation Partition may now narrow database-derived commitments to
-- one immutable, canonical DecisionRun.  This prevents another partial or
-- failed Run on the same session from changing the published Run's roster.

ALTER TABLE mra.research_partition
    ADD COLUMN source_decision_run_id uuid,
    ADD CONSTRAINT research_partition_decision_source_fk FOREIGN KEY (
        source_decision_run_id
    ) REFERENCES mra.decision_run(decision_run_id) ON DELETE RESTRICT,
    ADD CONSTRAINT research_partition_decision_source_shape_ck CHECK (
        source_decision_run_id IS NULL
        OR (
            purpose = 'DISCOVERY'
            AND source_backtest_run_id IS NULL
            AND source_backtest_arm_id IS NULL
            AND source_backtest_fold_id IS NULL
            AND source_backtest_sha256 IS NULL
            AND source_context_kind IS NULL
            AND source_context_state IS NULL
        )
    );

CREATE INDEX research_partition_decision_source_fk_idx
    ON mra.research_partition(source_decision_run_id)
    WHERE source_decision_run_id IS NOT NULL;

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

    IF NEW.source_decision_run_id IS NOT NULL AND NOT EXISTS (
        SELECT 1
        FROM mra.decision_run AS decision
        WHERE decision.decision_run_id = NEW.source_decision_run_id
          AND decision.research_purpose = 'DISCOVERY'
          AND NOT EXISTS (
              SELECT 1
              FROM mra.exploratory_retrospective_decision_run AS historical
              WHERE historical.decision_run_id = decision.decision_run_id
          )
    ) THEN
        RAISE EXCEPTION 'Decision-sourced Partition requires one canonical Discovery DecisionRun'
            USING ERRCODE = '55000';
    END IF;

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
      AND (NEW.source_decision_run_id IS NULL
           OR commitment.decision_run_id = NEW.source_decision_run_id)
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
                 AND (NEW.source_decision_run_id IS NULL
                      OR commitment.decision_run_id =
                         NEW.source_decision_run_id)
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
                 AND (NEW.source_decision_run_id IS NULL
                      OR commitment.decision_run_id =
                         NEW.source_decision_run_id)
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
        RAISE EXCEPTION 'ResearchPartition member roster is incomplete or outside declaration'
            USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;
