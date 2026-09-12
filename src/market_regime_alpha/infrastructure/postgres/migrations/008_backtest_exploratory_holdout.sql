-- Exploratory temporal holdout facts belong to Backtest. Existing Partition
-- access remains the only label-access ledger. No formal purpose is enabled.
CREATE TABLE mra.backtest_holdout_reservation (
    reservation_id uuid PRIMARY KEY,
    development_run_id uuid NOT NULL REFERENCES mra.backtest_specification(exploratory_backtest_run_id) ON DELETE RESTRICT,
    development_specification_sha256 text NOT NULL,
    future_run_id uuid NOT NULL UNIQUE,
    future_study_code text NOT NULL,
    fit_dates date[] NOT NULL,
    purge_dates date[] NOT NULL,
    embargo_dates date[] NOT NULL,
    validation_dates date[] NOT NULL,
    selection_arm_codes text[] NOT NULL,
    protocol_artifact_id uuid NOT NULL,
    protocol_content_sha256 text NOT NULL,
    protocol_size_bytes bigint NOT NULL,
    instrument_ids uuid[] NOT NULL,
    protected_start timestamptz NOT NULL,
    protected_end timestamptz NOT NULL,
    content_sha256 text NOT NULL,
    reserved_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE(reservation_id, content_sha256),
    CHECK (cardinality(instrument_ids) BETWEEN 1 AND 500 AND protected_start < protected_end),
    FOREIGN KEY(development_run_id,development_specification_sha256)
        REFERENCES mra.backtest_specification(exploratory_backtest_run_id,specification_sha256) ON DELETE RESTRICT,
    FOREIGN KEY(protocol_artifact_id,protocol_content_sha256,protocol_size_bytes)
        REFERENCES mra.artifact(artifact_id,content_sha256,size_bytes) ON DELETE RESTRICT,
    CHECK (cardinality(fit_dates) BETWEEN 1 AND 250 AND cardinality(validation_dates) BETWEEN 1 AND 60
        AND cardinality(purge_dates)>0 AND cardinality(embargo_dates)>0
        AND cardinality(selection_arm_codes) BETWEEN 1 AND 13
        AND future_study_code ~ '^[a-z][a-z0-9_]{0,49}$'
        AND content_sha256 ~ '^[0-9a-f]{64}$')
);
CREATE INDEX backtest_holdout_reservation_window_idx ON mra.backtest_holdout_reservation(protected_start,protected_end);
CREATE INDEX backtest_holdout_reservation_development_idx ON mra.backtest_holdout_reservation(development_run_id,development_specification_sha256);
CREATE INDEX backtest_holdout_reservation_protocol_idx ON mra.backtest_holdout_reservation(protocol_artifact_id,protocol_content_sha256,protocol_size_bytes);

CREATE TABLE mra.backtest_holdout_opening (
    reservation_id uuid PRIMARY KEY REFERENCES mra.backtest_holdout_reservation(reservation_id) ON DELETE RESTRICT,
    reservation_sha256 text NOT NULL,
    heldout_run_id uuid NOT NULL UNIQUE REFERENCES mra.backtest_specification(exploratory_backtest_run_id) ON DELETE RESTRICT,
    heldout_specification_sha256 text NOT NULL,
    selected_development_arm_id uuid NOT NULL REFERENCES mra.exploratory_backtest_arm(exploratory_backtest_arm_id) ON DELETE RESTRICT,
    selected_arm_code text NOT NULL,
    development_projection_sha256 text NOT NULL,
    selection_artifact_id uuid NOT NULL,
    selection_content_sha256 text NOT NULL,
    selection_size_bytes bigint NOT NULL,
    allowed_evaluation_ids uuid[] NOT NULL,
    allowed_partition_ids uuid[] NOT NULL,
    allowed_experiment_run_ids uuid[] NOT NULL,
    allowed_requirement_ids uuid[] NOT NULL,
    development_evaluation_ids uuid[] NOT NULL,
    development_evaluation_plan_hashes text[] NOT NULL,
    development_evaluation_input_hashes text[] NOT NULL,
    development_evaluation_metric_hashes text[] NOT NULL,
    content_sha256 text NOT NULL,
    opened_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK (cardinality(allowed_evaluation_ids) BETWEEN 1 AND 200
        AND cardinality(allowed_evaluation_ids)=cardinality(allowed_partition_ids)
        AND cardinality(allowed_evaluation_ids)=cardinality(allowed_experiment_run_ids)
        AND cardinality(allowed_evaluation_ids)=cardinality(allowed_requirement_ids)),
    FOREIGN KEY(reservation_id,reservation_sha256) REFERENCES mra.backtest_holdout_reservation(reservation_id,content_sha256) ON DELETE RESTRICT,
    FOREIGN KEY(heldout_run_id,heldout_specification_sha256)
        REFERENCES mra.backtest_specification(exploratory_backtest_run_id,specification_sha256) ON DELETE RESTRICT,
    FOREIGN KEY(selection_artifact_id,selection_content_sha256,selection_size_bytes)
        REFERENCES mra.artifact(artifact_id,content_sha256,size_bytes) ON DELETE RESTRICT,
    CHECK (cardinality(development_evaluation_ids) BETWEEN 1 AND 300
        AND cardinality(development_evaluation_ids)=cardinality(development_evaluation_plan_hashes)
        AND cardinality(development_evaluation_ids)=cardinality(development_evaluation_input_hashes)
        AND cardinality(development_evaluation_ids)=cardinality(development_evaluation_metric_hashes)
        AND development_projection_sha256 ~ '^[0-9a-f]{64}$'
        AND content_sha256 ~ '^[0-9a-f]{64}$')
);
CREATE INDEX backtest_holdout_opening_selection_idx ON mra.backtest_holdout_opening(selection_artifact_id,selection_content_sha256,selection_size_bytes);
CREATE INDEX backtest_holdout_opening_reservation_idx ON mra.backtest_holdout_opening(reservation_id,reservation_sha256);
CREATE INDEX backtest_holdout_opening_run_idx ON mra.backtest_holdout_opening(heldout_run_id,heldout_specification_sha256);

-- JSON is only a transient canonical hash encoding, never stored owner state.
CREATE FUNCTION mra.backtest_holdout_reservation_payload(fact mra.backtest_holdout_reservation)
RETURNS jsonb LANGUAGE sql IMMUTABLE AS $$
    SELECT jsonb_build_object(
        'schema','mra-backtest-exploratory-holdout-v1',
        'reservation_id',fact.reservation_id,'development_run_id',fact.development_run_id,
        'development_specification_sha256',fact.development_specification_sha256,
        'future_run_id',fact.future_run_id,'future_study_code',fact.future_study_code,
        'time_split',jsonb_build_object('fit_dates',fact.fit_dates,'purge_dates',fact.purge_dates,
            'embargo_dates',fact.embargo_dates,'validation_dates',fact.validation_dates),
        'selection_arm_codes',fact.selection_arm_codes,
        'protocol_artifact',jsonb_build_object('artifact_id',fact.protocol_artifact_id,
            'content_sha256',fact.protocol_content_sha256,'size_bytes',fact.protocol_size_bytes),
        'selection_rule','ALL_ARM_COMMON_VALIDATION_MAE_TIES_BY_FROZEN_ORDINAL',
        'authority','EXPLORATORY_TEMPORAL_ONLY_NOT_FORMAL_OOS_OR_PIT')
$$;
CREATE FUNCTION mra.backtest_holdout_opening_payload(fact mra.backtest_holdout_opening)
RETURNS jsonb LANGUAGE sql IMMUTABLE AS $$
    SELECT jsonb_build_object(
        'schema','mra-backtest-exploratory-holdout-opening-v1',
        'reservation_id',fact.reservation_id,'reservation_sha256',fact.reservation_sha256,
        'heldout_run_id',fact.heldout_run_id,'heldout_specification_sha256',fact.heldout_specification_sha256,
        'selected_development_arm_id',fact.selected_development_arm_id,'selected_arm_code',fact.selected_arm_code,
        'development_projection_sha256',fact.development_projection_sha256,
        'selection_artifact',jsonb_build_object('artifact_id',fact.selection_artifact_id,
            'content_sha256',fact.selection_content_sha256,'size_bytes',fact.selection_size_bytes),
        'allowed_evaluation_ids',fact.allowed_evaluation_ids,
        'evaluation_scopes',(SELECT jsonb_agg(jsonb_build_array(fact.allowed_evaluation_ids[i],fact.allowed_partition_ids[i],
            fact.allowed_experiment_run_ids[i],fact.allowed_requirement_ids[i]) ORDER BY i)
            FROM generate_subscripts(fact.allowed_evaluation_ids,1) i),
        'development_evaluation_roster',(SELECT jsonb_agg(jsonb_build_array(
            fact.development_evaluation_ids[i],fact.development_evaluation_plan_hashes[i],
            fact.development_evaluation_input_hashes[i],fact.development_evaluation_metric_hashes[i]) ORDER BY i)
            FROM generate_subscripts(fact.development_evaluation_ids,1) i))
$$;
ALTER TABLE mra.backtest_holdout_reservation ADD CONSTRAINT backtest_holdout_reservation_hash_ck
    CHECK(content_sha256=mra.canonical_sha256(mra.canonical_json_text(mra.backtest_holdout_reservation_payload(backtest_holdout_reservation))));
ALTER TABLE mra.backtest_holdout_opening ADD CONSTRAINT backtest_holdout_opening_hash_ck
    CHECK(content_sha256=mra.canonical_sha256(mra.canonical_json_text(mra.backtest_holdout_opening_payload(backtest_holdout_opening))));

CREATE TRIGGER backtest_holdout_reservation_append_only BEFORE UPDATE OR DELETE ON mra.backtest_holdout_reservation
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE INDEX backtest_holdout_opening_selected_arm_idx ON mra.backtest_holdout_opening(selected_development_arm_id);
CREATE TRIGGER backtest_holdout_opening_append_only BEFORE UPDATE OR DELETE ON mra.backtest_holdout_opening
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();

-- A conservative upper bound derived solely from the original Target/Calendar,
-- never prices or weekday inference. Unknown coverage cannot evade reservation.
CREATE FUNCTION mra.backtest_holdout_commitment_end(requested_commitment uuid)
RETURNS timestamptz LANGUAGE sql STABLE AS $$
    SELECT coalesce((
        SELECT future.close_at + interval '1 day'
        FROM mra.trading_session future
        WHERE future.exchange=calendar.exchange AND future.session_date>calendar.session_date
        ORDER BY future.session_date
        OFFSET greatest((SELECT max(session_offset)-1 FROM mra.target_checkpoint
            WHERE target_definition_id=commitment.target_definition_id AND checkpoint_role='OUTCOME_OBSERVATION'),0)
        LIMIT 1
    ),'infinity'::timestamptz)
    FROM mra.decision_target_commitment commitment
    JOIN mra.decision_reference_observation reference USING(decision_reference_observation_id)
    JOIN mra.trading_session calendar ON calendar.session_id=reference.session_id
    WHERE commitment.commitment_id=requested_commitment
$$;

-- New reservations serialize with every first Decision commitment. Reservation
-- refuses any pre-existing overlapping commitment, including failed/in-flight
-- Outcome attempts; an unknown prior label read cannot become an unseen sample.
CREATE FUNCTION mra.lock_backtest_holdout_commitment_admission()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    PERFORM pg_advisory_xact_lock_shared(hashtextextended('mra:backtest-holdout-admission',0));
    RETURN NEW;
END;
$$;
CREATE TRIGGER backtest_holdout_commitment_admission BEFORE INSERT ON mra.decision_target_commitment
FOR EACH ROW EXECUTE FUNCTION mra.lock_backtest_holdout_commitment_admission();

CREATE FUNCTION mra.guard_backtest_holdout_reservation()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE expected_instruments uuid[];
DECLARE calendar_dates date[];
DECLARE expected_start timestamptz;
DECLARE expected_end timestamptz;
DECLARE exchange_name text;
DECLARE development_end date;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended('mra:backtest-holdout-admission',0));
    SELECT exchange_code INTO exchange_name FROM mra.backtest_specification WHERE exploratory_backtest_run_id=NEW.development_run_id;
    SELECT max(session_date) INTO development_end FROM mra.exploratory_backtest_fold_session WHERE exploratory_backtest_run_id=NEW.development_run_id;
    SELECT array_agg(session_date ORDER BY session_date),
           max(close_at) FILTER(WHERE session_date=NEW.validation_dates[1])
      INTO calendar_dates,expected_start FROM mra.trading_session
    WHERE exchange=exchange_name AND session_date BETWEEN NEW.fit_dates[1] AND NEW.validation_dates[cardinality(NEW.validation_dates)];
    SELECT close_at INTO expected_end FROM mra.trading_session WHERE exchange=exchange_name
        AND session_date>NEW.validation_dates[cardinality(NEW.validation_dates)] ORDER BY session_date LIMIT 1;
    SELECT array_agg(instrument_id ORDER BY instrument_id) INTO expected_instruments
    FROM mra.backtest_sample_member WHERE exploratory_backtest_run_id=NEW.development_run_id;
    IF NEW.instrument_ids IS DISTINCT FROM expected_instruments
       OR calendar_dates IS DISTINCT FROM NEW.fit_dates||NEW.purge_dates||NEW.embargo_dates||NEW.validation_dates
       OR NEW.protected_start IS DISTINCT FROM expected_start OR NEW.protected_end IS DISTINCT FROM expected_end
       OR development_end IS NULL OR development_end>=NEW.fit_dates[1]
       OR NOT EXISTS (SELECT 1 FROM mra.backtest_specification WHERE exploratory_backtest_run_id=NEW.development_run_id
            AND specification_sha256=NEW.development_specification_sha256)
       OR EXISTS (SELECT 1 FROM mra.backtest_holdout_reservation prior
            WHERE prior.instrument_ids && NEW.instrument_ids
              AND prior.protected_start < NEW.protected_end AND prior.protected_end > NEW.protected_start)
       OR EXISTS (SELECT 1 FROM mra.decision_target_commitment commitment
            WHERE commitment.instrument_id=ANY(NEW.instrument_ids)
              AND commitment.decision_time < NEW.protected_end
              AND mra.backtest_holdout_commitment_end(commitment.commitment_id) >= NEW.protected_start)
    THEN
        RAISE EXCEPTION 'EXPLORATORY_HOLDOUT_RESERVATION_REJECTED: exact scope or zero prior commitment prerequisite failed'
            USING ERRCODE='55000';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER backtest_holdout_reservation_guard BEFORE INSERT ON mra.backtest_holdout_reservation
FOR EACH ROW EXECUTE FUNCTION mra.guard_backtest_holdout_reservation();

CREATE FUNCTION mra.guard_backtest_holdout_opening()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE reservation mra.backtest_holdout_reservation%ROWTYPE;
DECLARE expected_evaluations jsonb;
DECLARE expected_allowed_count integer;
DECLARE expected_requirements uuid[];
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended('mra:backtest-holdout-admission',0));
    SELECT * INTO STRICT reservation FROM mra.backtest_holdout_reservation WHERE reservation_id=NEW.reservation_id;
    SELECT jsonb_agg(jsonb_build_array(evaluation.evaluation_run_id::text,evaluation.content_sha256,
               evaluation.input_roster_sha256,evaluation.metric_roster_sha256) ORDER BY requirement.ordinal)
      INTO expected_evaluations
    FROM mra.backtest_evaluation_requirement requirement
    JOIN mra.backtest_evaluation_execution execution USING(backtest_evaluation_requirement_id)
    JOIN mra.evaluation_run evaluation USING(evaluation_run_id)
    WHERE requirement.exploratory_backtest_run_id=reservation.development_run_id AND evaluation.status='COMPLETED';
    SELECT count(*),array_agg(requirement.backtest_evaluation_requirement_id ORDER BY requirement.backtest_evaluation_requirement_id)
      INTO expected_allowed_count,expected_requirements FROM mra.backtest_evaluation_requirement requirement
    LEFT JOIN mra.exploratory_backtest_fold fold USING(exploratory_backtest_fold_id)
    WHERE requirement.exploratory_backtest_run_id=NEW.heldout_run_id
      AND (requirement.scope_kind='AGGREGATE' OR fold.purpose='VALIDATION');
    IF NEW.heldout_run_id<>reservation.future_run_id
       OR reservation.content_sha256<>NEW.reservation_sha256
       OR expected_evaluations IS DISTINCT FROM mra.backtest_holdout_opening_payload(NEW)->'development_evaluation_roster'
       OR cardinality(NEW.allowed_evaluation_ids)<>expected_allowed_count
       OR (SELECT array_agg(identity ORDER BY identity) FROM unnest(NEW.allowed_requirement_ids) identity) IS DISTINCT FROM expected_requirements
       OR (SELECT count(DISTINCT identity) FROM unnest(NEW.allowed_evaluation_ids) identity)<>expected_allowed_count
       OR (SELECT count(DISTINCT identity) FROM unnest(NEW.allowed_partition_ids) identity)<>expected_allowed_count
       OR (SELECT count(DISTINCT identity) FROM unnest(NEW.allowed_experiment_run_ids) identity)<>expected_allowed_count
       OR EXISTS (SELECT 1 FROM mra.backtest_runtime_binding WHERE exploratory_backtest_run_id=NEW.heldout_run_id)
       OR NOT EXISTS (
            SELECT 1 FROM mra.exploratory_backtest_run development
            JOIN mra.exploratory_backtest_run heldout ON heldout.exploratory_backtest_run_id=NEW.heldout_run_id
            JOIN mra.backtest_specification specification ON specification.exploratory_backtest_run_id=heldout.exploratory_backtest_run_id
            WHERE development.exploratory_backtest_run_id=reservation.development_run_id
              AND heldout.run_code=reservation.future_study_code
              AND specification.specification_sha256=NEW.heldout_specification_sha256
              AND heldout.market_archive_id=development.market_archive_id
              AND heldout.market_archive_seal_id=development.market_archive_seal_id
              AND heldout.target_definition_id=development.target_definition_id
              AND heldout.feature_roster_sha256=development.feature_roster_sha256
       )
       OR NOT EXISTS (
            SELECT 1 FROM mra.exploratory_backtest_arm arm
            WHERE arm.exploratory_backtest_arm_id=NEW.selected_development_arm_id
              AND arm.exploratory_backtest_run_id=reservation.development_run_id
              AND arm.arm_kind=NEW.selected_arm_code
              AND arm.arm_kind=ANY(reservation.selection_arm_codes)
       )
    THEN
        RAISE EXCEPTION 'EXPLORATORY_HOLDOUT_OPENING_REJECTED: immutable reservation, selection, contract or zero execution prerequisite failed'
            USING ERRCODE='55000';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER backtest_holdout_opening_guard BEFORE INSERT ON mra.backtest_holdout_opening
FOR EACH ROW EXECUTE FUNCTION mra.guard_backtest_holdout_opening();

-- UUIDv5 identities are independently reconstructed by the transaction-bound
-- Backtest repository from these immutable requirements (no new PG extension).
-- SQL additionally checks the entire concrete execution scope at Evaluation
-- opening and again before accessing labels; an allowed UUID is not authority.
CREATE FUNCTION mra.backtest_holdout_partition_matches(
    opening mra.backtest_holdout_opening, scope_ordinal integer,
    partition mra.research_partition, evaluation mra.evaluation_run
) RETURNS boolean LANGUAGE sql STABLE AS $$
    SELECT EXISTS(
               SELECT 1 FROM mra.backtest_evaluation_requirement requirement
               JOIN mra.exploratory_backtest_run root ON root.exploratory_backtest_run_id=opening.heldout_run_id
               LEFT JOIN mra.exploratory_backtest_fold fold ON fold.exploratory_backtest_fold_id=requirement.exploratory_backtest_fold_id
               CROSS JOIN LATERAL (
                   SELECT (array_agg(session.trading_session_id ORDER BY session.session_date))[1] first_session,
                          (array_agg(session.trading_session_id ORDER BY session.session_date DESC))[1] last_session
                   FROM mra.exploratory_backtest_fold_session session
                   JOIN mra.exploratory_backtest_fold participating USING(exploratory_backtest_fold_id)
                   WHERE session.exploratory_backtest_run_id=opening.heldout_run_id
                     AND session.session_role='EVALUATION' AND participating.purpose='VALIDATION'
                     AND (requirement.exploratory_backtest_fold_id IS NULL OR session.exploratory_backtest_fold_id=requirement.exploratory_backtest_fold_id)
               ) label_window
               WHERE requirement.backtest_evaluation_requirement_id=opening.allowed_requirement_ids[scope_ordinal]
                 AND partition.research_partition_id=evaluation.research_partition_id
                 AND partition.source_backtest_run_id=opening.heldout_run_id
                 AND partition.source_backtest_arm_id=requirement.exploratory_backtest_arm_id
                 AND partition.source_backtest_fold_id IS NOT DISTINCT FROM requirement.exploratory_backtest_fold_id
                 AND partition.source_backtest_sha256=opening.heldout_specification_sha256
                 AND partition.population_scope='ALL_COMMITMENTS' AND partition.overlap_policy='PURGED_WALK_FORWARD'
                 AND partition.source_context_kind IS NULL AND partition.source_context_state IS NULL
                 AND partition.decision_start_session_id=label_window.first_session AND partition.decision_end_session_id=label_window.last_session
                 AND partition.purge_before_sessions=coalesce(fold.purge_sessions,0) AND partition.purge_after_sessions=0
                 AND partition.embargo_sessions=coalesce(fold.embargo_sessions,0)
                 AND partition.fold_ordinal=coalesce(fold.ordinal,requirement.ordinal)
                 AND partition.code_artifact_id=root.code_artifact_id AND partition.code_content_sha256=root.code_content_sha256
                 AND partition.config_artifact_id=root.config_artifact_id AND partition.config_content_sha256=root.config_content_sha256
                 AND partition.provenance_sha256=root.provenance_sha256
                 AND evaluation.evaluation_protocol_id=requirement.evaluation_protocol_id
                 AND evaluation.partition_purpose='VALIDATION'
                 AND partition.purpose='VALIDATION'
    )
$$;

CREATE FUNCTION mra.require_backtest_holdout_evaluation_scope(evaluation mra.evaluation_run)
RETURNS void LANGUAGE plpgsql AS $$
DECLARE opening mra.backtest_holdout_opening%ROWTYPE;
DECLARE position integer;
BEGIN
    FOR opening IN SELECT * FROM mra.backtest_holdout_opening
        WHERE evaluation.evaluation_run_id=ANY(allowed_evaluation_ids)
    LOOP
        position := array_position(opening.allowed_evaluation_ids,evaluation.evaluation_run_id);
        IF evaluation.research_partition_id<>opening.allowed_partition_ids[position]
           OR evaluation.experiment_run_id<>opening.allowed_experiment_run_ids[position]
           OR NOT EXISTS (
               SELECT 1 FROM mra.research_partition partition
               WHERE partition.research_partition_id=evaluation.research_partition_id
                 AND mra.backtest_holdout_partition_matches(opening,position,partition,evaluation)
           ) THEN
            RAISE EXCEPTION 'EXPLORATORY_HOLDOUT_EVALUATION_SCOPE_BLOCKED: planned UUID requires its exact Partition, Experiment, protocol and Backtest scope' USING ERRCODE='55000';
        END IF;
    END LOOP;
END;
$$;
CREATE FUNCTION mra.guard_backtest_holdout_evaluation_open()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    PERFORM mra.require_backtest_holdout_evaluation_scope(NEW);
    RETURN NEW;
END;
$$;
CREATE TRIGGER backtest_holdout_evaluation_open_guard BEFORE INSERT ON mra.evaluation_run
FOR EACH ROW EXECUTE FUNCTION mra.guard_backtest_holdout_evaluation_open();

CREATE FUNCTION mra.require_backtest_holdout_access(
    requested_commitment uuid, requested_due timestamptz,
    requested_evaluation uuid DEFAULT NULL, requested_training boolean DEFAULT false
) RETURNS void LANGUAGE plpgsql AS $$
DECLARE reservation record;
DECLARE actual_run uuid;
DECLARE evaluation mra.evaluation_run%ROWTYPE;
BEGIN
    IF requested_evaluation IS NOT NULL THEN
        SELECT * INTO evaluation FROM mra.evaluation_run WHERE evaluation_run_id=requested_evaluation;
        PERFORM mra.require_backtest_holdout_evaluation_scope(evaluation);
    END IF;
    FOR reservation IN
        SELECT protected.* FROM mra.backtest_holdout_reservation protected
        JOIN mra.decision_target_commitment commitment ON commitment.commitment_id=requested_commitment
        WHERE commitment.instrument_id=ANY(protected.instrument_ids)
          AND commitment.decision_time < protected.protected_end
          AND requested_due >= protected.protected_start
    LOOP
        PERFORM pg_advisory_xact_lock_shared(hashtextextended('mra:backtest-holdout-admission',0));
        SELECT dataset.exploratory_backtest_run_id INTO actual_run
        FROM mra.decision_target_commitment commitment
        JOIN mra.decision_run decision USING(decision_run_id)
        JOIN mra.exploratory_backtest_dataset dataset ON dataset.dataset_id=decision.dataset_id
        WHERE commitment.commitment_id=requested_commitment;
        IF requested_training OR NOT EXISTS (
            SELECT 1 FROM mra.backtest_holdout_opening opening
            JOIN mra.backtest_specification specification ON specification.exploratory_backtest_run_id=opening.heldout_run_id
            WHERE opening.reservation_id=reservation.reservation_id
              AND opening.heldout_run_id=actual_run
              AND specification.specification_sha256=opening.heldout_specification_sha256
              AND (requested_evaluation IS NULL OR requested_evaluation=ANY(opening.allowed_evaluation_ids))
        ) THEN
            RAISE EXCEPTION 'EXPLORATORY_HOLDOUT_ACCESS_BLOCKED: reserved labels require the one frozen opening and Evaluation roster'
                USING ERRCODE='55000';
        END IF;
    END LOOP;
END;
$$;

CREATE FUNCTION mra.guard_backtest_holdout_outcome()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    PERFORM mra.require_backtest_holdout_access(NEW.commitment_id,
        mra.backtest_holdout_commitment_end(NEW.commitment_id));
    RETURN NEW;
END;
$$;
CREATE TRIGGER backtest_holdout_outcome_guard BEFORE INSERT ON mra.market_target_outcome
FOR EACH ROW EXECUTE FUNCTION mra.guard_backtest_holdout_outcome();
CREATE TRIGGER backtest_holdout_revision_guard BEFORE INSERT ON mra.market_target_outcome_revision
FOR EACH ROW EXECUTE FUNCTION mra.guard_backtest_holdout_outcome();

CREATE FUNCTION mra.guard_backtest_holdout_evaluation_access()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    PERFORM mra.require_backtest_holdout_access(NEW.commitment_id,
        (SELECT outcome_due_at FROM mra.research_partition_member WHERE research_partition_member_id=NEW.research_partition_member_id),
        NEW.evaluation_run_id);
    RETURN NEW;
END;
$$;
CREATE TRIGGER backtest_holdout_evaluation_access_guard BEFORE INSERT ON mra.research_partition_outcome_access
FOR EACH ROW EXECUTE FUNCTION mra.guard_backtest_holdout_evaluation_access();

CREATE FUNCTION mra.require_backtest_holdout_training_access(requested_evaluation uuid)
RETURNS void LANGUAGE plpgsql AS $$
DECLARE member record;
BEGIN
    FOR member IN SELECT population.commitment_id,population.outcome_due_at
        FROM mra.evaluation_run evaluation
        JOIN mra.research_partition_member population USING(research_partition_id)
        WHERE evaluation.evaluation_run_id=requested_evaluation
    LOOP
        PERFORM mra.require_backtest_holdout_access(member.commitment_id,member.outcome_due_at,requested_evaluation,true);
    END LOOP;
END;
$$;
CREATE FUNCTION mra.guard_backtest_holdout_training()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    PERFORM mra.require_backtest_holdout_training_access(NEW.evaluation_run_id);
    RETURN NEW;
END;
$$;
CREATE TRIGGER backtest_holdout_training_guard BEFORE INSERT ON mra.model_training_run
FOR EACH ROW EXECUTE FUNCTION mra.guard_backtest_holdout_training();
