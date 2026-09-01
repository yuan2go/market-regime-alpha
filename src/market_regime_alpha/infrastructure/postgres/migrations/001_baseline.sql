CREATE SCHEMA mra;

COMMENT ON SCHEMA mra IS
    'Market Regime Alpha MRA_REFOUNDATION_1 unreleased draft authority schema';

CREATE FUNCTION mra.reject_append_only_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION '% is append-only', TG_TABLE_NAME USING ERRCODE = '55000';
END;
$$;

CREATE FUNCTION mra.canonical_sha256(canonical_text text)
RETURNS text
LANGUAGE sql
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT encode(sha256(convert_to(canonical_text, 'UTF8')), 'hex');
$$;

CREATE FUNCTION mra.canonical_timestamptz_text(value timestamptz)
RETURNS text
LANGUAGE sql
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT CASE
        WHEN extract(microseconds FROM value)::bigint % 1000000 = 0
        THEN to_char(value AT TIME ZONE 'UTC',
                     'YYYY-MM-DD"T"HH24:MI:SS') || '+00:00'
        ELSE to_char(value AT TIME ZONE 'UTC',
                     'YYYY-MM-DD"T"HH24:MI:SS.US') || '+00:00'
    END;
$$;

CREATE FUNCTION mra.target_algorithm_binding_sha256(
    algorithm_code text,
    algorithm_version text,
    algorithm_sha256 text,
    code_artifact_id uuid,
    code_content_sha256 text,
    code_size_bytes bigint,
    config_artifact_id uuid,
    config_content_sha256 text,
    config_size_bytes bigint
)
RETURNS text
LANGUAGE sql
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT mra.canonical_sha256(
        replace(
            json_build_object(
                'algorithm_code', algorithm_code,
                'algorithm_sha256', algorithm_sha256,
                'algorithm_version', algorithm_version,
                'code_artifact', json_build_object(
                    'artifact_id', code_artifact_id,
                    'content_sha256', code_content_sha256,
                    'size_bytes', code_size_bytes
                ),
                'config_artifact', json_build_object(
                    'artifact_id', config_artifact_id,
                    'content_sha256', config_content_sha256,
                    'size_bytes', config_size_bytes
                )
            )::text,
            ' ',
            ''
        )
    );
$$;

CREATE FUNCTION mra.target_checkpoint_content_sha256(
    availability_rule text,
    checkpoint_code text,
    finality_rule text,
    local_time time,
    ordinal integer,
    price_basis text,
    reference_rule text,
    checkpoint_role text,
    session_offset integer,
    timeframe text,
    timezone_name text,
    timing_rule text,
    value_field text
)
RETURNS text
LANGUAGE sql
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT mra.canonical_sha256(
        replace(
            json_build_object(
                'availability_rule', availability_rule,
                'checkpoint_code', checkpoint_code,
                'finality_rule', finality_rule,
                'local_time', local_time::text,
                'ordinal', ordinal,
                'price_basis', price_basis,
                'reference_rule', reference_rule,
                'role', checkpoint_role,
                'session_offset', session_offset,
                'timeframe', timeframe,
                'timezone_name', timezone_name,
                'timing_rule', timing_rule,
                'value_field', value_field
            )::text,
            ' ',
            ''
        )
    );
$$;

CREATE FUNCTION mra.target_metric_dependency_content_sha256(
    ordinal integer,
    dependency_role text,
    target_checkpoint_id uuid,
    target_metric_definition_id uuid
)
RETURNS text
LANGUAGE sql
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT mra.canonical_sha256(
        replace(
            json_build_object(
                'ordinal', ordinal,
                'role', dependency_role,
                'target_checkpoint_id', target_checkpoint_id,
                'target_metric_definition_id', target_metric_definition_id
            )::text,
            ' ',
            ''
        )
    );
$$;

CREATE FUNCTION mra.target_metric_content_sha256(
    algorithm_code text,
    algorithm_version text,
    algorithm_sha256 text,
    algorithm_binding_sha256 text,
    code_artifact_id uuid,
    code_content_sha256 text,
    code_size_bytes bigint,
    config_artifact_id uuid,
    config_content_sha256 text,
    config_size_bytes bigint,
    barrier_direction text,
    barrier_threshold numeric,
    completion_rule text,
    metric_code text,
    metric_kind text,
    ordinal integer,
    unit text,
    value_type text
)
RETURNS text
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
AS $$
    SELECT mra.canonical_sha256(
        replace(
            json_build_object(
                'algorithm', json_build_object(
                    'algorithm_code', algorithm_code,
                    'algorithm_sha256', algorithm_sha256,
                    'algorithm_version', algorithm_version,
                    'code_artifact', json_build_object(
                        'artifact_id', code_artifact_id,
                        'content_sha256', code_content_sha256,
                        'size_bytes', code_size_bytes
                    ),
                    'config_artifact', json_build_object(
                        'artifact_id', config_artifact_id,
                        'content_sha256', config_content_sha256,
                        'size_bytes', config_size_bytes
                    ),
                    'content_sha256', algorithm_binding_sha256
                ),
                'barrier_direction', barrier_direction,
                'barrier_threshold', barrier_threshold::text,
                'completion_rule', completion_rule,
                'metric_code', metric_code,
                'metric_kind', metric_kind,
                'ordinal', ordinal,
                'unit', unit,
                'value_type', value_type
            )::text,
            ' ',
            ''
        )
    );
$$;

CREATE FUNCTION mra.target_definition_content_sha256(
    algorithm_code text,
    algorithm_version text,
    algorithm_sha256 text,
    algorithm_binding_sha256 text,
    code_artifact_id uuid,
    code_content_sha256 text,
    code_size_bytes bigint,
    config_artifact_id uuid,
    config_content_sha256 text,
    config_size_bytes bigint,
    checkpoint_count integer,
    checkpoint_roster_sha256 text,
    dependency_count integer,
    dependency_roster_sha256 text,
    instrument_scope text,
    market_scope text,
    metric_count integer,
    metric_roster_sha256 text,
    registration_status text,
    supersedes_target_definition_id uuid,
    target_code text,
    version integer
)
RETURNS text
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
AS $$
    SELECT mra.canonical_sha256(
        replace(
            json_build_object(
                'algorithm', json_build_object(
                    'algorithm_code', algorithm_code,
                    'algorithm_sha256', algorithm_sha256,
                    'algorithm_version', algorithm_version,
                    'code_artifact', json_build_object(
                        'artifact_id', code_artifact_id,
                        'content_sha256', code_content_sha256,
                        'size_bytes', code_size_bytes
                    ),
                    'config_artifact', json_build_object(
                        'artifact_id', config_artifact_id,
                        'content_sha256', config_content_sha256,
                        'size_bytes', config_size_bytes
                    ),
                    'content_sha256', algorithm_binding_sha256
                ),
                'checkpoint_count', checkpoint_count,
                'checkpoint_roster_sha256', checkpoint_roster_sha256,
                'dependency_count', dependency_count,
                'dependency_roster_sha256', dependency_roster_sha256,
                'instrument_scope', instrument_scope,
                'market_scope', market_scope,
                'metric_count', metric_count,
                'metric_roster_sha256', metric_roster_sha256,
                'registration_status', registration_status,
                'supersedes_target_definition_id', supersedes_target_definition_id,
                'target_code', target_code,
                'version', version
            )::text,
            ' ',
            ''
        )
    );
$$;

CREATE FUNCTION mra.decision_run_target_content_sha256(
    ordinal integer,
    provider_id uuid,
    provider_product_id uuid,
    provider_product_revision integer,
    target_checkpoint_id uuid,
    target_checkpoint_sha256 text,
    target_definition_id uuid,
    target_definition_sha256 text,
    target_version integer
)
RETURNS text
LANGUAGE sql
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT mra.canonical_sha256(
        replace(
            json_build_object(
                'ordinal', ordinal,
                'provider_id', provider_id,
                'provider_product_id', provider_product_id,
                'provider_product_revision', provider_product_revision,
                'target_checkpoint_id', target_checkpoint_id,
                'target_checkpoint_sha256', target_checkpoint_sha256,
                'target_definition_id', target_definition_id,
                'target_definition_sha256', target_definition_sha256,
                'target_version', target_version
            )::text,
            ' ',
            ''
        )
    );
$$;

CREATE FUNCTION mra.decision_reference_content_sha256(
    availability_status text,
    bar_revision integer,
    bar_revision_id uuid,
    candidate_id uuid,
    capture_id uuid,
    decimal_value numeric,
    decision_run_target_id uuid,
    event_end timestamptz,
    event_start timestamptz,
    finality_status text,
    instrument_id uuid,
    known_at timestamptz,
    observation_time timestamptz,
    price_basis text,
    provider_product_id uuid,
    source_recorded_at timestamptz,
    session_id uuid,
    source_gap_id uuid,
    source_gap_kind text,
    source_gap_reason_code text,
    source_kind text,
    target_checkpoint_id uuid,
    timeframe text,
    value_field text,
    value_status text
)
RETURNS text
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
AS $$
    SELECT mra.canonical_sha256(
        replace(
            json_build_object(
                'availability_status', availability_status,
                'bar_revision', bar_revision,
                'bar_revision_id', bar_revision_id,
                'candidate_id', candidate_id,
                'capture_id', capture_id,
                'decimal_value', decimal_value::text,
                'decision_run_target_id', decision_run_target_id,
                'event_end', mra.canonical_timestamptz_text(event_end),
                'event_start', mra.canonical_timestamptz_text(event_start),
                'finality_status', finality_status,
                'instrument_id', instrument_id,
                'known_at', mra.canonical_timestamptz_text(known_at),
                'observation_time',
                    mra.canonical_timestamptz_text(observation_time),
                'price_basis', price_basis,
                'provider_product_id', provider_product_id,
                'recorded_at',
                    mra.canonical_timestamptz_text(source_recorded_at),
                'session_id', session_id,
                'source_gap_id', source_gap_id,
                'source_gap_kind', source_gap_kind,
                'source_gap_reason_code', source_gap_reason_code,
                'source_kind', source_kind,
                'target_checkpoint_id', target_checkpoint_id,
                'timeframe', timeframe,
                'value_field', value_field,
                'value_status', value_status
            )::text,
            ' ',
            ''
        )
    );
$$;

CREATE FUNCTION mra.decision_commitment_content_sha256(
    candidate_disposition text,
    candidate_id uuid,
    decision_reference_observation_id uuid,
    decision_reference_sha256 text,
    decision_run_target_id uuid,
    instrument_id uuid,
    runtime_mode text,
    target_definition_id uuid
)
RETURNS text
LANGUAGE sql
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT mra.canonical_sha256(
        replace(
            json_build_object(
                'candidate_disposition', candidate_disposition,
                'candidate_id', candidate_id,
                'decision_reference_observation_id',
                    decision_reference_observation_id,
                'decision_reference_sha256', decision_reference_sha256,
                'decision_run_target_id', decision_run_target_id,
                'instrument_id', instrument_id,
                'runtime_mode', runtime_mode,
                'target_definition_id', target_definition_id
            )::text,
            ' ',
            ''
        )
    );
$$;

CREATE FUNCTION mra.decision_run_definition_summary_sha256(
    candidate_count integer,
    candidate_roster_sha256 text,
    candidate_set_content_sha256 text,
    candidate_set_id uuid,
    commitment_count bigint,
    commitment_roster_sha256 text,
    decision_time timestamptz,
    reference_count bigint,
    request_sha256 text,
    runtime_mode text,
    target_count integer,
    target_roster_sha256 text
)
RETURNS text
LANGUAGE sql
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT mra.canonical_sha256(
        replace(
            json_build_object(
                'candidate_count', candidate_count,
                'candidate_roster_sha256', candidate_roster_sha256,
                'candidate_set_content_sha256', candidate_set_content_sha256,
                'candidate_set_id', candidate_set_id,
                'commitment_count', commitment_count,
                'commitment_roster_sha256', commitment_roster_sha256,
                'decision_time',
                    mra.canonical_timestamptz_text(decision_time),
                'reference_count', reference_count,
                'request_sha256', request_sha256,
                'runtime_mode', runtime_mode,
                'target_count', target_count,
                'target_roster_sha256', target_roster_sha256
            )::text,
            ' ',
            ''
        )
    );
$$;

CREATE FUNCTION mra.artifact_has_verified_integrity(
    integrity_state text,
    last_verified_at timestamptz
)
RETURNS boolean
LANGUAGE sql
STABLE
PARALLEL SAFE
AS $$
    SELECT integrity_state = 'AVAILABLE'
       AND last_verified_at IS NOT NULL;
$$;

COMMENT ON FUNCTION mra.artifact_has_verified_integrity(text, timestamptz) IS
    'Foundation integrity invariant: AVAILABLE bytes have a physical hash/size verification';

CREATE FUNCTION mra.market_artifact_is_readable(
    integrity_state text,
    last_verified_at timestamptz
)
RETURNS boolean
LANGUAGE sql
STABLE
PARALLEL SAFE
AS $$
    SELECT mra.artifact_has_verified_integrity(
               integrity_state,
               last_verified_at
           )
       AND last_verified_at >= transaction_timestamp() - interval '24 hours';
$$;

COMMENT ON FUNCTION mra.market_artifact_is_readable(text, timestamptz) IS
    'WP-04 Market consumer policy: verified exact bytes observed within 24 hours';

CREATE FUNCTION mra.require_market_authority_capture(
    authority_capture_id uuid,
    authority_kind text
)
RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
    readable boolean := false;
BEGIN
    SELECT true
    INTO readable
    FROM mra.data_capture AS capture
    JOIN mra.artifact AS artifact ON artifact.artifact_id = capture.artifact_id
    WHERE capture.capture_id = authority_capture_id
      AND capture.status = 'CAPTURED'
      AND mra.market_artifact_is_readable(
          artifact.integrity_state,
          artifact.last_verified_at
      )
    FOR SHARE OF capture, artifact;
    IF NOT COALESCE(readable, false) THEN
        RAISE EXCEPTION '% Authority Artifact is not authoritatively readable', authority_kind
            USING ERRCODE = '55000';
    END IF;
END;
$$;

CREATE FUNCTION mra.validate_market_fact_temporal()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    evidence_capture_id uuid;
    evidence_capture record;
    evidence_gap_kind text;
BEGIN
    evidence_capture_id := COALESCE(
        (to_jsonb(NEW) ->> 'capture_id')::uuid,
        (to_jsonb(NEW) ->> 'source_capture_id')::uuid
    );
    evidence_gap_kind := to_jsonb(NEW) ->> 'gap_kind';
    SELECT capture.capture_completed_at, capture.status,
           artifact.integrity_state AS artifact_integrity_state,
           artifact.last_verified_at AS artifact_last_verified_at
    INTO evidence_capture
    FROM mra.data_capture AS capture
    LEFT JOIN mra.artifact AS artifact
      ON artifact.artifact_id = capture.artifact_id
    WHERE capture_id = evidence_capture_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Market fact Capture does not exist' USING ERRCODE = '23503';
    END IF;
    IF TG_TABLE_NAME = 'source_gap'
       AND (
           (evidence_gap_kind = 'PROVIDER_FAILURE'
            AND evidence_capture.status <> 'PROVIDER_FAILURE')
           OR
           (evidence_gap_kind <> 'PROVIDER_FAILURE'
            AND (
                evidence_capture.status <> 'CAPTURED'
                OR NOT mra.market_artifact_is_readable(
                    evidence_capture.artifact_integrity_state,
                    evidence_capture.artifact_last_verified_at
                )
            ))
       ) THEN
        RAISE EXCEPTION 'SourceGap kind is incompatible with its Capture evidence' USING ERRCODE = '55000';
    ELSIF TG_TABLE_NAME <> 'source_gap'
       AND (
           evidence_capture.status <> 'CAPTURED'
           OR NOT mra.market_artifact_is_readable(
               evidence_capture.artifact_integrity_state,
               evidence_capture.artifact_last_verified_at
           )
       ) THEN
        RAISE EXCEPTION 'normalized Market facts require a CAPTURED source with an AVAILABLE Artifact' USING ERRCODE = '55000';
    END IF;
    IF NEW.known_at <> GREATEST(
        evidence_capture.capture_completed_at,
        NEW.recorded_at
    ) THEN
        RAISE EXCEPTION 'Market fact known_at is not canonical' USING ERRCODE = '23514';
    END IF;
    IF NEW.decision_visible_at <> NEW.known_at THEN
        RAISE EXCEPTION 'unqualified Market fact visibility must equal known_at' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION mra.guard_runtime_schedule_update()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF ROW(
        NEW.schedule_id, NEW.schedule_code, NEW.revision, NEW.runtime_mode,
        NEW.schedule_expression, NEW.timezone_name, NEW.step_catalog_hash,
        NEW.created_at, NEW.supersedes_schedule_id
    ) IS DISTINCT FROM ROW(
        OLD.schedule_id, OLD.schedule_code, OLD.revision, OLD.runtime_mode,
        OLD.schedule_expression, OLD.timezone_name, OLD.step_catalog_hash,
        OLD.created_at, OLD.supersedes_schedule_id
    ) THEN
        RAISE EXCEPTION 'runtime_schedule immutable definition changed' USING ERRCODE = '55000';
    END IF;
    IF NEW.enabled IS NOT DISTINCT FROM OLD.enabled THEN
        RAISE EXCEPTION 'runtime_schedule update did not change enablement' USING ERRCODE = '55000';
    END IF;
    NEW.updated_at := clock_timestamp();
    RETURN NEW;
END;
$$;

CREATE FUNCTION mra.guard_runtime_run_update()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    allowed boolean;
BEGIN
    IF ROW(
        NEW.run_id, NEW.schedule_id, NEW.fire_key, NEW.runtime_mode,
        NEW.requested_at, NEW.decision_time, NEW.code_sha,
        NEW.config_artifact_id, NEW.config_hash, NEW.schema_epoch,
        NEW.parent_run_id, NEW.original_run_id, NEW.created_at
    ) IS DISTINCT FROM ROW(
        OLD.run_id, OLD.schedule_id, OLD.fire_key, OLD.runtime_mode,
        OLD.requested_at, OLD.decision_time, OLD.code_sha,
        OLD.config_artifact_id, OLD.config_hash, OLD.schema_epoch,
        OLD.parent_run_id, OLD.original_run_id, OLD.created_at
    ) THEN
        RAISE EXCEPTION 'runtime_run immutable envelope changed' USING ERRCODE = '55000';
    END IF;
    allowed := (OLD.state, NEW.state) IN (
        ('QUEUED', 'RUNNING'), ('QUEUED', 'CANCELLED'),
        ('RUNNING', 'WAITING'), ('RUNNING', 'SUCCEEDED'),
        ('RUNNING', 'BLOCKED'), ('RUNNING', 'FAILED'),
        ('RUNNING', 'CANCELLED'), ('WAITING', 'RUNNING'),
        ('WAITING', 'BLOCKED'), ('WAITING', 'FAILED'),
        ('WAITING', 'CANCELLED')
    );
    IF NOT allowed THEN
        RAISE EXCEPTION 'invalid runtime_run transition % -> %', OLD.state, NEW.state USING ERRCODE = '55000';
    END IF;
    IF NEW.version <> OLD.version + 1 THEN
        RAISE EXCEPTION 'runtime_run version must increment once' USING ERRCODE = '40001';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION mra.guard_runtime_step_update()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    allowed boolean;
BEGIN
    IF ROW(
        NEW.step_id, NEW.run_id, NEW.step_key, NEW.step_kind,
        NEW.implementation, NEW.implementation_version, NEW.required,
        NEW.ordinal, NEW.request_hash, NEW.input_evidence_hash,
        NEW.max_attempts, NEW.retry_backoff_ms, NEW.retryable_error_codes,
        NEW.deadline_at, NEW.external_effect_class, NEW.created_at
    ) IS DISTINCT FROM ROW(
        OLD.step_id, OLD.run_id, OLD.step_key, OLD.step_kind,
        OLD.implementation, OLD.implementation_version, OLD.required,
        OLD.ordinal, OLD.request_hash, OLD.input_evidence_hash,
        OLD.max_attempts, OLD.retry_backoff_ms, OLD.retryable_error_codes,
        OLD.deadline_at, OLD.external_effect_class, OLD.created_at
    ) THEN
        RAISE EXCEPTION 'runtime_step immutable plan changed' USING ERRCODE = '55000';
    END IF;
    allowed := (OLD.state, NEW.state) IN (
        ('PENDING', 'READY'), ('PENDING', 'SKIPPED'),
        ('PENDING', 'CANCELLED'), ('READY', 'CLAIMED'),
        ('READY', 'CANCELLED'), ('CLAIMED', 'RUNNING'),
        ('CLAIMED', 'READY'), ('CLAIMED', 'CANCELLED'),
        ('RUNNING', 'READY'), ('RUNNING', 'WAITING'),
        ('RUNNING', 'SUCCEEDED'), ('RUNNING', 'BLOCKED'),
        ('RUNNING', 'FAILED'), ('RUNNING', 'CANCELLED'),
        ('WAITING', 'READY'), ('WAITING', 'CANCELLED')
    );
    IF NOT allowed THEN
        RAISE EXCEPTION 'invalid runtime_step transition % -> %', OLD.state, NEW.state USING ERRCODE = '55000';
    END IF;
    IF NEW.version <> OLD.version + 1 THEN
        RAISE EXCEPTION 'runtime_step version must increment once' USING ERRCODE = '40001';
    END IF;
    IF OLD.state = 'READY' AND NEW.state = 'CLAIMED' THEN
        IF NEW.current_fence <> OLD.current_fence + 1 OR NEW.current_attempt_id IS NULL THEN
            RAISE EXCEPTION 'claim must increment fence and bind current Attempt' USING ERRCODE = '55000';
        END IF;
    ELSIF NEW.current_fence <> OLD.current_fence THEN
        RAISE EXCEPTION 'Step fence changes only during claim' USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION mra.guard_runtime_attempt_update()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    allowed boolean;
BEGIN
    IF ROW(
        NEW.attempt_id, NEW.step_id, NEW.attempt_no, NEW.fence_token,
        NEW.lease_owner, NEW.lease_acquired_at, NEW.external_effect_class,
        NEW.created_at
    ) IS DISTINCT FROM ROW(
        OLD.attempt_id, OLD.step_id, OLD.attempt_no, OLD.fence_token,
        OLD.lease_owner, OLD.lease_acquired_at, OLD.external_effect_class,
        OLD.created_at
    ) THEN
        RAISE EXCEPTION 'runtime_attempt immutable claim changed' USING ERRCODE = '55000';
    END IF;
    IF OLD.state = NEW.state THEN
        IF OLD.state NOT IN ('CLAIMED', 'RUNNING') THEN
            RAISE EXCEPTION 'terminal runtime_attempt is immutable' USING ERRCODE = '55000';
        END IF;
        IF NEW.lease_until <= OLD.lease_until OR NEW.last_heartbeat_at <= OLD.last_heartbeat_at THEN
            RAISE EXCEPTION 'heartbeat must extend a live lease' USING ERRCODE = '55000';
        END IF;
        IF ROW(
            NEW.error_class, NEW.error_code, NEW.result_receipt_id,
            NEW.result_hash, NEW.started_at, NEW.finished_at
        ) IS DISTINCT FROM ROW(
            OLD.error_class, OLD.error_code, OLD.result_receipt_id,
            OLD.result_hash, OLD.started_at, OLD.finished_at
        ) THEN
            RAISE EXCEPTION 'heartbeat may change only lease timestamps' USING ERRCODE = '55000';
        END IF;
        RETURN NEW;
    END IF;
    allowed := (OLD.state, NEW.state) IN (
        ('CLAIMED', 'RUNNING'), ('CLAIMED', 'ABANDONED'),
        ('RUNNING', 'SUCCEEDED'), ('RUNNING', 'FAILED_RETRYABLE'),
        ('RUNNING', 'FAILED_TERMINAL'), ('RUNNING', 'ABANDONED'),
        ('RUNNING', 'RECONCILIATION_REQUIRED')
    );
    IF NOT allowed THEN
        RAISE EXCEPTION 'invalid runtime_attempt transition % -> %', OLD.state, NEW.state USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION mra.guard_command_receipt_update()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF ROW(
        NEW.receipt_id, NEW.command_kind, NEW.scope_id, NEW.idempotency_key,
        NEW.request_hash, NEW.created_at
    ) IS DISTINCT FROM ROW(
        OLD.receipt_id, OLD.command_kind, OLD.scope_id, OLD.idempotency_key,
        OLD.request_hash, OLD.created_at
    ) THEN
        RAISE EXCEPTION 'command_receipt identity changed' USING ERRCODE = '55000';
    END IF;
    IF OLD.status <> 'PENDING' OR NEW.status NOT IN ('SUCCEEDED', 'BLOCKED', 'FAILED') THEN
        RAISE EXCEPTION 'invalid command_receipt transition % -> %', OLD.status, NEW.status USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION mra.guard_artifact_update()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    allowed boolean;
BEGIN
    IF ROW(
        NEW.artifact_id, NEW.content_sha256, NEW.size_bytes, NEW.media_type,
        NEW.locator, NEW.created_at
    ) IS DISTINCT FROM ROW(
        OLD.artifact_id, OLD.content_sha256, OLD.size_bytes, OLD.media_type,
        OLD.locator, OLD.created_at
    ) THEN
        RAISE EXCEPTION 'artifact content identity changed' USING ERRCODE = '55000';
    END IF;
    allowed := OLD.integrity_state = NEW.integrity_state OR (OLD.integrity_state, NEW.integrity_state) IN (
        ('AVAILABLE', 'MISSING'), ('AVAILABLE', 'CORRUPT'),
        ('AVAILABLE', 'QUARANTINED'), ('MISSING', 'AVAILABLE'),
        ('CORRUPT', 'AVAILABLE'), ('QUARANTINED', 'AVAILABLE'),
        ('QUARANTINED', 'DELETED')
    );
    IF NOT allowed THEN
        RAISE EXCEPTION 'invalid artifact integrity transition % -> %', OLD.integrity_state, NEW.integrity_state USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION mra.validate_runtime_run_config()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    config_row record;
BEGIN
    SELECT content_sha256, integrity_state
    INTO config_row
    FROM mra.artifact
    WHERE artifact_id = NEW.config_artifact_id
    FOR SHARE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'runtime Run config Artifact does not exist' USING ERRCODE = '23503';
    END IF;
    IF config_row.content_sha256 <> NEW.config_hash
       OR config_row.integrity_state <> 'AVAILABLE' THEN
        RAISE EXCEPTION 'runtime Run config Artifact is not exact and AVAILABLE' USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION mra.guard_artifact_gc_candidate_update()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    allowed boolean;
BEGIN
    IF NEW.content_sha256 IS DISTINCT FROM OLD.content_sha256
       OR (
           NEW.artifact_id IS DISTINCT FROM OLD.artifact_id
           AND NOT (OLD.artifact_id IS NULL AND NEW.artifact_id IS NOT NULL)
       ) THEN
        RAISE EXCEPTION 'artifact GC candidate identity changed' USING ERRCODE = '55000';
    END IF;
    allowed := (OLD.state, NEW.state) IN (
        ('OBSERVED', 'OBSERVED'), ('OBSERVED', 'QUARANTINE_PENDING'),
        ('OBSERVED', 'CLEARED'), ('QUARANTINE_PENDING', 'QUARANTINED'),
        ('QUARANTINE_PENDING', 'CLEARED'), ('QUARANTINED', 'DELETE_PENDING'),
        ('QUARANTINED', 'CLEARED'), ('DELETE_PENDING', 'DELETED'),
        ('CLEARED', 'OBSERVED')
    );
    IF NOT allowed THEN
        RAISE EXCEPTION 'invalid artifact GC transition % -> %', OLD.state, NEW.state USING ERRCODE = '55000';
    END IF;
    IF (OLD.state, NEW.state) <> ('CLEARED', 'OBSERVED')
       AND ROW(NEW.first_seen_at, NEW.grace_until)
           IS DISTINCT FROM ROW(OLD.first_seen_at, OLD.grace_until) THEN
        RAISE EXCEPTION 'artifact GC observation window changed mid-cycle' USING ERRCODE = '55000';
    END IF;
    IF (OLD.state, NEW.state) = ('CLEARED', 'OBSERVED')
       AND (NEW.first_seen_at <= OLD.cleared_at OR NEW.cleared_at IS NOT NULL) THEN
        RAISE EXCEPTION 'artifact GC restart requires a new observation window' USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION mra.validate_data_capture_insert()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    product_row record;
    artifact_row record;
BEGIN
    SELECT payload_encoding, media_type, source_availability_policy
    INTO product_row
    FROM mra.provider_product
    WHERE provider_product_id = NEW.provider_product_id
    FOR SHARE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Capture ProviderProduct does not exist' USING ERRCODE = '23503';
    END IF;
    IF NEW.status = 'CAPTURED'
       AND product_row.source_availability_policy <> NEW.source_availability_status THEN
        RAISE EXCEPTION 'Capture availability semantics differ from ProviderProduct' USING ERRCODE = '55000';
    END IF;
    IF NEW.status = 'PROVIDER_FAILURE'
       AND (
           NEW.source_availability_status <> 'UNKNOWN'
           OR NEW.source_available_at IS NOT NULL
       ) THEN
        RAISE EXCEPTION 'Provider failure cannot assert source availability' USING ERRCODE = '55000';
    END IF;
    IF NEW.status = 'CAPTURED' THEN
        SELECT integrity_state, media_type, last_verified_at INTO artifact_row
        FROM mra.artifact
        WHERE artifact_id = NEW.artifact_id
        FOR SHARE;
        IF NOT FOUND OR NOT mra.market_artifact_is_readable(
            artifact_row.integrity_state,
            artifact_row.last_verified_at
        ) THEN
            RAISE EXCEPTION 'Capture requires an authoritatively readable exact Artifact' USING ERRCODE = '55000';
        END IF;
        IF NEW.payload_encoding <> product_row.payload_encoding THEN
            RAISE EXCEPTION 'Capture encoding differs from ProviderProduct' USING ERRCODE = '55000';
        END IF;
        IF artifact_row.media_type <> product_row.media_type THEN
            RAISE EXCEPTION 'Capture Artifact media type differs from ProviderProduct' USING ERRCODE = '55000';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION mra.validate_instrument_identifier_insert()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    instrument_capture_id uuid;
BEGIN
    SELECT source_capture_id
    INTO instrument_capture_id
    FROM mra.instrument
    WHERE instrument_id = NEW.instrument_id
    FOR SHARE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'InstrumentIdentifier Instrument does not exist' USING ERRCODE = '23503';
    END IF;
    PERFORM mra.require_market_authority_capture(
        instrument_capture_id,
        'InstrumentIdentifier Instrument'
    );
    PERFORM pg_advisory_xact_lock(
        hashtextextended('mra:instrument-identifier:' || NEW.identifier_scheme, 0)
    );
    IF EXISTS (
        WITH current_identifier AS (
            SELECT DISTINCT ON (
                existing.instrument_id,
                existing.identifier_scheme,
                existing.identifier_value,
                existing.effective_from
            )
                existing.instrument_id,
                existing.identifier_scheme,
                existing.identifier_value,
                existing.effective_from,
                existing.effective_to
            FROM mra.instrument_identifier AS existing
            WHERE existing.identifier_scheme = NEW.identifier_scheme
            ORDER BY existing.instrument_id,
                     existing.identifier_scheme,
                     existing.identifier_value,
                     existing.effective_from,
                     existing.decision_visible_at DESC,
                     existing.revision DESC,
                     existing.instrument_identifier_id DESC
        )
        SELECT 1
        FROM current_identifier AS existing
        WHERE NOT (
              existing.instrument_id = NEW.instrument_id
              AND existing.identifier_value = NEW.identifier_value
              AND existing.effective_from = NEW.effective_from
          )
          AND (
              existing.identifier_value = NEW.identifier_value
              OR existing.instrument_id = NEW.instrument_id
          )
          AND existing.effective_from < COALESCE(
              NEW.effective_to,
              'infinity'::timestamptz
          )
          AND NEW.effective_from < COALESCE(
              existing.effective_to,
              'infinity'::timestamptz
          )
    ) THEN
        RAISE EXCEPTION 'InstrumentIdentifier effective interval overlaps another Authority mapping' USING ERRCODE = '23P01';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION mra.validate_market_bar_session()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    session_row record;
    instrument_exchange text;
    grid_anchor timestamptz;
    duration_seconds bigint;
BEGIN
    IF TG_TABLE_NAME = 'source_gap' THEN
        IF NEW.fact_kind <> 'MARKET_BAR' THEN
            RETURN NEW;
        END IF;
    END IF;
    SELECT exchange, open_at, break_start_at, break_end_at, close_at
    INTO session_row
    FROM mra.trading_session
    WHERE session_id = NEW.session_id
    FOR SHARE;
    SELECT exchange INTO instrument_exchange
    FROM mra.instrument
    WHERE instrument_id = NEW.instrument_id
    FOR SHARE;
    IF NOT FOUND OR session_row.exchange IS NULL THEN
        RAISE EXCEPTION 'MarketBar evidence requires exact Instrument and Session' USING ERRCODE = '23503';
    END IF;
    IF instrument_exchange <> session_row.exchange THEN
        RAISE EXCEPTION 'MarketBar evidence Instrument and Session exchanges differ' USING ERRCODE = '23514';
    END IF;
    PERFORM mra.require_market_authority_capture(
        (SELECT source_capture_id FROM mra.instrument WHERE instrument_id = NEW.instrument_id),
        'MarketBar Instrument'
    );
    PERFORM mra.require_market_authority_capture(
        (SELECT source_capture_id FROM mra.trading_session WHERE session_id = NEW.session_id),
        'MarketBar TradingSession'
    );
    IF NEW.timeframe = 'DAILY' THEN
        IF NEW.event_start <> session_row.open_at OR NEW.event_end <> session_row.close_at THEN
            RAISE EXCEPTION 'Daily MarketBar evidence must span the exact Session' USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END IF;
    duration_seconds := CASE NEW.timeframe
        WHEN 'MINUTE_1' THEN 60
        WHEN 'MINUTE_5' THEN 300
        WHEN 'MINUTE_15' THEN 900
        WHEN 'MINUTE_30' THEN 1800
        WHEN 'MINUTE_60' THEN 3600
    END;
    IF NEW.event_start < session_row.open_at OR NEW.event_end > session_row.close_at THEN
        RAISE EXCEPTION 'MarketBar evidence lies outside its Session' USING ERRCODE = '23514';
    END IF;
    IF session_row.break_start_at IS NOT NULL THEN
        IF NEW.event_end <= session_row.break_start_at THEN
            grid_anchor := session_row.open_at;
        ELSIF NEW.event_start >= session_row.break_end_at THEN
            grid_anchor := session_row.break_end_at;
        ELSE
            RAISE EXCEPTION 'MarketBar evidence crosses the Session break' USING ERRCODE = '23514';
        END IF;
    ELSE
        grid_anchor := session_row.open_at;
    END IF;
    IF NEW.event_start <> NEW.event_end - make_interval(secs => duration_seconds)
       OR mod(
           extract(epoch FROM NEW.event_end - grid_anchor)::bigint,
           duration_seconds
       ) <> 0 THEN
        RAISE EXCEPTION 'MarketBar evidence does not align to the Session grid' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION mra.validate_classification_membership_insert()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    classification_row record;
    instrument_capture_id uuid;
    current_membership_id uuid;
    current_revision integer;
BEGIN
    SELECT classification_scheme, classification_code, source_capture_id
    INTO classification_row
    FROM mra.classification
    WHERE classification_id = NEW.classification_id
    FOR SHARE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'ClassificationMembership Classification does not exist' USING ERRCODE = '23503';
    END IF;
    SELECT source_capture_id
    INTO instrument_capture_id
    FROM mra.instrument
    WHERE instrument_id = NEW.instrument_id
    FOR SHARE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'ClassificationMembership Instrument does not exist' USING ERRCODE = '23503';
    END IF;
    PERFORM mra.require_market_authority_capture(
        classification_row.source_capture_id,
        'ClassificationMembership Classification'
    );
    PERFORM mra.require_market_authority_capture(
        instrument_capture_id,
        'ClassificationMembership Instrument'
    );
    PERFORM pg_advisory_xact_lock(
        hashtextextended(
            'mra:classification-membership:' ||
            classification_row.classification_scheme || ':' ||
            classification_row.classification_code || ':' ||
            NEW.instrument_id::text,
            0
        )
    );
    SELECT existing.membership_revision_id, existing.revision
    INTO current_membership_id, current_revision
    FROM mra.classification_membership_revision AS existing
    JOIN mra.classification AS existing_classification
      ON existing_classification.classification_id = existing.classification_id
    WHERE existing.instrument_id = NEW.instrument_id
      AND existing.effective_from = NEW.effective_from
      AND existing_classification.classification_scheme =
          classification_row.classification_scheme
      AND existing_classification.classification_code =
          classification_row.classification_code
    ORDER BY existing.decision_visible_at DESC,
             existing.revision DESC,
             existing.membership_revision_id DESC
    LIMIT 1;
    IF NEW.revision = 1 AND current_membership_id IS NOT NULL THEN
        RAISE EXCEPTION 'ClassificationMembership stable lineage already has this interval root' USING ERRCODE = '23505';
    END IF;
    IF NEW.revision > 1 AND (
        current_membership_id IS NULL
        OR current_membership_id IS DISTINCT FROM NEW.supersedes_membership_revision_id
        OR NEW.revision <> current_revision + 1
    ) THEN
        RAISE EXCEPTION 'ClassificationMembership must supersede the single current stable-lineage revision' USING ERRCODE = '55000';
    END IF;
    IF EXISTS (
        WITH current_membership AS (
            SELECT DISTINCT ON (
                existing_classification.classification_scheme,
                existing_classification.classification_code,
                existing.instrument_id,
                existing.effective_from
            )
                existing.instrument_id,
                existing.effective_from,
                existing.effective_to
            FROM mra.classification_membership_revision AS existing
            JOIN mra.classification AS existing_classification
              ON existing_classification.classification_id = existing.classification_id
            WHERE existing.instrument_id = NEW.instrument_id
              AND existing_classification.classification_scheme =
                  classification_row.classification_scheme
              AND existing_classification.classification_code =
                  classification_row.classification_code
            ORDER BY existing_classification.classification_scheme,
                     existing_classification.classification_code,
                     existing.instrument_id,
                     existing.effective_from,
                     existing.decision_visible_at DESC,
                     existing.revision DESC,
                     existing.membership_revision_id DESC
        )
        SELECT 1
        FROM current_membership AS existing
        WHERE existing.effective_from <> NEW.effective_from
          AND existing.effective_from < COALESCE(
              NEW.effective_to,
              'infinity'::timestamptz
          )
          AND NEW.effective_from < COALESCE(
              existing.effective_to,
              'infinity'::timestamptz
          )
    ) THEN
        RAISE EXCEPTION 'ClassificationMembership effective interval overlaps its stable classification lineage' USING ERRCODE = '23P01';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION mra.validate_classification_insert()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    current_classification_id uuid;
    current_revision integer;
BEGIN
    PERFORM pg_advisory_xact_lock(
        hashtextextended(
            'mra:classification:' || NEW.classification_scheme || ':' ||
            NEW.classification_code,
            0
        )
    );
    SELECT existing.classification_id, existing.revision
    INTO current_classification_id, current_revision
    FROM mra.classification AS existing
    WHERE existing.classification_scheme = NEW.classification_scheme
      AND existing.classification_code = NEW.classification_code
      AND existing.effective_from = NEW.effective_from
    ORDER BY existing.decision_visible_at DESC,
             existing.revision DESC,
             existing.classification_id DESC
    LIMIT 1;
    IF NEW.revision = 1 AND current_classification_id IS NOT NULL THEN
        RAISE EXCEPTION 'Classification already has this effective root' USING ERRCODE = '23505';
    END IF;
    IF NEW.revision > 1 AND (
        current_classification_id IS NULL
        OR current_classification_id IS DISTINCT FROM NEW.supersedes_classification_id
        OR NEW.revision <> current_revision + 1
    ) THEN
        RAISE EXCEPTION 'Classification must supersede the single current effective-root revision' USING ERRCODE = '55000';
    END IF;
    IF EXISTS (
        WITH current_root AS (
            SELECT DISTINCT ON (existing.effective_from)
                existing.effective_from,
                existing.effective_to
            FROM mra.classification AS existing
            WHERE existing.classification_scheme = NEW.classification_scheme
              AND existing.classification_code = NEW.classification_code
            ORDER BY existing.effective_from,
                     existing.decision_visible_at DESC,
                     existing.revision DESC,
                     existing.classification_id DESC
        )
        SELECT 1
        FROM current_root AS existing
        WHERE existing.effective_from <> NEW.effective_from
          AND existing.effective_from < COALESCE(
              NEW.effective_to,
              'infinity'::timestamptz
          )
          AND NEW.effective_from < COALESCE(
              existing.effective_to,
              'infinity'::timestamptz
          )
    ) THEN
        RAISE EXCEPTION 'Classification current effective intervals overlap' USING ERRCODE = '23P01';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION mra.validate_instrument_fact_session()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    session_row record;
    instrument_exchange text;
    instrument_currency text;
    instrument_capture_id uuid;
BEGIN
    SELECT exchange, currency, source_capture_id
    INTO instrument_exchange, instrument_currency, instrument_capture_id
    FROM mra.instrument
    WHERE instrument_id = NEW.instrument_id
    FOR SHARE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'InstrumentFact Instrument does not exist' USING ERRCODE = '23503';
    END IF;
    PERFORM mra.require_market_authority_capture(
        instrument_capture_id,
        'InstrumentFact Instrument'
    );
    IF NEW.session_id IS NULL THEN
        RETURN NEW;
    END IF;
    SELECT exchange, open_at, close_at, source_capture_id
    INTO session_row
    FROM mra.trading_session
    WHERE session_id = NEW.session_id
    FOR SHARE;
    IF session_row.exchange IS NULL THEN
        RAISE EXCEPTION 'InstrumentFact requires exact Instrument and Session' USING ERRCODE = '23503';
    END IF;
    PERFORM mra.require_market_authority_capture(
        session_row.source_capture_id,
        'InstrumentFact TradingSession'
    );
    IF instrument_exchange <> session_row.exchange
       OR NEW.event_start < session_row.open_at
       OR NEW.event_end IS NULL
       OR NEW.event_end > session_row.close_at THEN
        RAISE EXCEPTION 'InstrumentFact interval does not belong to its Session' USING ERRCODE = '23514';
    END IF;
    IF NEW.fact_kind = 'SECURITY_STATUS'
       AND (
           NEW.event_start <> session_row.open_at
           OR NEW.event_end <> session_row.close_at
       ) THEN
        RAISE EXCEPTION 'SecurityStatus must cover the exact referenced Session' USING ERRCODE = '23514';
    END IF;
    IF NEW.fact_kind IN ('LIMIT_UP_PRICE', 'LIMIT_DOWN_PRICE', 'REFERENCE_PRICE')
       AND NEW.unit_code <> instrument_currency THEN
        RAISE EXCEPTION 'InstrumentFact Money currency does not match Instrument' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION mra.validate_instrument_fact_timeline_insert()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    current_fact_id uuid;
    current_revision integer;
BEGIN
    IF NEW.evidence_scope <> 'EFFECTIVE_INTERVAL' THEN
        RETURN NEW;
    END IF;
    PERFORM pg_advisory_xact_lock(
        hashtextextended(
            'mra:instrument-fact-timeline:' || NEW.provider_product_id::text ||
            ':' || NEW.instrument_id::text || ':' || NEW.fact_kind,
            0
        )
    );
    SELECT existing.fact_revision_id, existing.revision
    INTO current_fact_id, current_revision
    FROM mra.instrument_fact_revision AS existing
    WHERE existing.provider_product_id = NEW.provider_product_id
      AND existing.instrument_id = NEW.instrument_id
      AND existing.fact_kind = NEW.fact_kind
      AND existing.evidence_scope = 'EFFECTIVE_INTERVAL'
      AND existing.event_start = NEW.event_start
    ORDER BY existing.decision_visible_at DESC,
             existing.revision DESC,
             existing.fact_revision_id DESC
    LIMIT 1;
    IF NEW.revision = 1 AND current_fact_id IS NOT NULL THEN
        RAISE EXCEPTION 'InstrumentFact timeline already has this interval root' USING ERRCODE = '23505';
    END IF;
    IF NEW.revision > 1 AND (
        current_fact_id IS NULL
        OR current_fact_id IS DISTINCT FROM NEW.supersedes_revision_id
        OR NEW.revision <> current_revision + 1
    ) THEN
        RAISE EXCEPTION 'InstrumentFact must supersede the single current timeline revision' USING ERRCODE = '55000';
    END IF;
    IF EXISTS (
        WITH current_interval AS (
            SELECT DISTINCT ON (existing.event_start)
                existing.event_start,
                existing.event_end
            FROM mra.instrument_fact_revision AS existing
            WHERE existing.provider_product_id = NEW.provider_product_id
              AND existing.instrument_id = NEW.instrument_id
              AND existing.fact_kind = NEW.fact_kind
              AND existing.evidence_scope = 'EFFECTIVE_INTERVAL'
            ORDER BY existing.event_start,
                     existing.decision_visible_at DESC,
                     existing.revision DESC,
                     existing.fact_revision_id DESC
        )
        SELECT 1
        FROM current_interval AS existing
        WHERE existing.event_start <> NEW.event_start
          AND existing.event_start < COALESCE(
              NEW.event_end,
              'infinity'::timestamptz
          )
          AND NEW.event_start < COALESCE(
              existing.event_end,
              'infinity'::timestamptz
          )
    ) THEN
        RAISE EXCEPTION 'InstrumentFact current effective intervals overlap' USING ERRCODE = '23P01';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION mra.validate_corporate_action_sessions()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    instrument_exchange text;
    instrument_currency text;
    instrument_capture_id uuid;
    ex_row record;
    record_exchange text;
    record_date date;
    record_capture_id uuid;
    pay_exchange text;
    pay_date date;
    pay_capture_id uuid;
    successor_capture_id uuid;
BEGIN
    SELECT exchange, currency, source_capture_id
    INTO instrument_exchange, instrument_currency, instrument_capture_id
    FROM mra.instrument
    WHERE instrument_id = NEW.instrument_id
    FOR SHARE;
    SELECT exchange, session_date, source_capture_id INTO ex_row
    FROM mra.trading_session
    WHERE session_id = NEW.ex_session_id
    FOR SHARE;
    IF instrument_exchange IS NULL OR ex_row.exchange IS NULL
       OR instrument_exchange <> ex_row.exchange THEN
        RAISE EXCEPTION 'CorporateAction ex Session does not match Instrument exchange' USING ERRCODE = '23514';
    END IF;
    PERFORM mra.require_market_authority_capture(
        instrument_capture_id,
        'CorporateAction Instrument'
    );
    PERFORM mra.require_market_authority_capture(
        ex_row.source_capture_id,
        'CorporateAction ex TradingSession'
    );
    IF NEW.currency IS NOT NULL AND NEW.currency <> instrument_currency THEN
        RAISE EXCEPTION 'CorporateAction currency does not match Instrument' USING ERRCODE = '23514';
    END IF;
    IF NEW.record_session_id IS NOT NULL THEN
        SELECT exchange, session_date, source_capture_id
        INTO record_exchange, record_date, record_capture_id
        FROM mra.trading_session
        WHERE session_id = NEW.record_session_id
        FOR SHARE;
        IF record_exchange IS NULL OR record_exchange <> instrument_exchange
           OR record_date > ex_row.session_date THEN
            RAISE EXCEPTION 'CorporateAction record Session is inconsistent' USING ERRCODE = '23514';
        END IF;
        PERFORM mra.require_market_authority_capture(
            record_capture_id,
            'CorporateAction record TradingSession'
        );
    END IF;
    IF NEW.pay_session_id IS NOT NULL THEN
        SELECT exchange, session_date, source_capture_id
        INTO pay_exchange, pay_date, pay_capture_id
        FROM mra.trading_session
        WHERE session_id = NEW.pay_session_id
        FOR SHARE;
        IF pay_exchange IS NULL OR pay_exchange <> instrument_exchange
           OR pay_date < ex_row.session_date THEN
            RAISE EXCEPTION 'CorporateAction pay Session is inconsistent' USING ERRCODE = '23514';
        END IF;
        PERFORM mra.require_market_authority_capture(
            pay_capture_id,
            'CorporateAction pay TradingSession'
        );
    END IF;
    IF NEW.successor_instrument_id IS NOT NULL THEN
        SELECT source_capture_id
        INTO successor_capture_id
        FROM mra.instrument
        WHERE instrument_id = NEW.successor_instrument_id
        FOR SHARE;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'CorporateAction successor Instrument does not exist' USING ERRCODE = '23503';
        END IF;
        PERFORM mra.require_market_authority_capture(
            successor_capture_id,
            'CorporateAction successor Instrument'
        );
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION mra.validate_market_revision_predecessor()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    valid boolean := false;
BEGIN
    IF NEW.revision = 1 THEN
        RETURN NEW;
    END IF;
    IF TG_TABLE_NAME = 'provider_product' THEN
        SELECT EXISTS (
            SELECT 1 FROM mra.provider_product AS prior
            WHERE prior.provider_product_id = NEW.supersedes_provider_product_id
              AND prior.provider_id = NEW.provider_id
              AND prior.product_code = NEW.product_code
              AND prior.revision = NEW.revision - 1
        ) INTO valid;
    ELSIF TG_TABLE_NAME = 'instrument_identifier' THEN
        SELECT EXISTS (
            SELECT 1 FROM mra.instrument_identifier AS prior
            WHERE prior.instrument_identifier_id = NEW.supersedes_identifier_id
              AND prior.instrument_id = NEW.instrument_id
              AND prior.identifier_scheme = NEW.identifier_scheme
              AND prior.identifier_value = NEW.identifier_value
              AND prior.effective_from = NEW.effective_from
              AND prior.revision = NEW.revision - 1
        ) INTO valid;
    ELSIF TG_TABLE_NAME = 'classification' THEN
        SELECT EXISTS (
            SELECT 1 FROM mra.classification AS prior
            WHERE prior.classification_id = NEW.supersedes_classification_id
              AND prior.classification_scheme = NEW.classification_scheme
              AND prior.classification_code = NEW.classification_code
              AND prior.effective_from = NEW.effective_from
              AND prior.revision = NEW.revision - 1
        ) INTO valid;
    ELSIF TG_TABLE_NAME = 'classification_membership_revision' THEN
        SELECT EXISTS (
            SELECT 1
            FROM mra.classification_membership_revision AS prior
            JOIN mra.classification AS prior_classification
              ON prior_classification.classification_id = prior.classification_id
            JOIN mra.classification AS next_classification
              ON next_classification.classification_id = NEW.classification_id
            WHERE prior.membership_revision_id = NEW.supersedes_membership_revision_id
              AND prior_classification.classification_scheme =
                  next_classification.classification_scheme
              AND prior_classification.classification_code =
                  next_classification.classification_code
              AND prior.instrument_id = NEW.instrument_id
              AND prior.effective_from = NEW.effective_from
              AND prior.revision = NEW.revision - 1
        ) INTO valid;
    ELSIF TG_TABLE_NAME = 'market_bar_revision' THEN
        SELECT EXISTS (
            SELECT 1 FROM mra.market_bar_revision AS prior
            WHERE prior.bar_revision_id = NEW.supersedes_revision_id
              AND prior.provider_product_id = NEW.provider_product_id
              AND prior.instrument_id = NEW.instrument_id
              AND prior.session_id = NEW.session_id
              AND prior.timeframe = NEW.timeframe
              AND prior.price_basis = NEW.price_basis
              AND prior.event_start = NEW.event_start
              AND prior.event_end IS NOT DISTINCT FROM NEW.event_end
              AND prior.revision = NEW.revision - 1
        ) INTO valid;
    ELSIF TG_TABLE_NAME = 'instrument_fact_revision' THEN
        SELECT EXISTS (
            SELECT 1 FROM mra.instrument_fact_revision AS prior
            WHERE prior.fact_revision_id = NEW.supersedes_revision_id
              AND prior.provider_product_id = NEW.provider_product_id
              AND prior.instrument_id = NEW.instrument_id
              AND prior.session_id IS NOT DISTINCT FROM NEW.session_id
              AND prior.fact_kind = NEW.fact_kind
              AND prior.evidence_scope = NEW.evidence_scope
              AND prior.event_start = NEW.event_start
              AND (
                  NEW.evidence_scope = 'EFFECTIVE_INTERVAL'
                  OR prior.event_end IS NOT DISTINCT FROM NEW.event_end
              )
              AND prior.revision = NEW.revision - 1
        ) INTO valid;
    ELSIF TG_TABLE_NAME = 'corporate_action_revision' THEN
        SELECT EXISTS (
            SELECT 1 FROM mra.corporate_action_revision AS prior
            WHERE prior.corporate_action_revision_id = NEW.supersedes_revision_id
              AND prior.provider_product_id = NEW.provider_product_id
              AND prior.instrument_id = NEW.instrument_id
              AND prior.action_key = NEW.action_key
              AND prior.revision = NEW.revision - 1
        ) INTO valid;
    END IF;
    IF NOT valid THEN
        RAISE EXCEPTION '% revision predecessor is not the same logical fact', TG_TABLE_NAME USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION mra.reject_fact_gap_duality()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    conflict_exists boolean;
    capture_key uuid;
BEGIN
    IF TG_TABLE_NAME IN (
        'instrument', 'instrument_identifier', 'trading_session',
        'classification', 'classification_membership_revision'
    ) THEN
        capture_key := NEW.source_capture_id;
    ELSE
        capture_key := NEW.capture_id;
    END IF;
    PERFORM pg_advisory_xact_lock(
        hashtextextended('mra:capture-normalization:' || capture_key::text, 0)
    );
    IF TG_TABLE_NAME = 'instrument' THEN
        SELECT EXISTS (
            SELECT 1 FROM mra.source_gap AS gap
            WHERE gap.capture_id = capture_key
              AND gap.fact_kind = 'INSTRUMENT'
              AND gap.instrument_code = NEW.canonical_code
        ) INTO conflict_exists;
    ELSIF TG_TABLE_NAME = 'instrument_identifier' THEN
        SELECT EXISTS (
            SELECT 1 FROM mra.source_gap AS gap
            WHERE gap.capture_id = capture_key
              AND gap.fact_kind = 'INSTRUMENT_IDENTIFIER'
              AND gap.identifier_scheme = NEW.identifier_scheme
              AND gap.identifier_value = NEW.identifier_value
              AND (gap.instrument_id IS NULL OR gap.instrument_id = NEW.instrument_id)
              AND gap.effective_from = NEW.effective_from
              AND gap.effective_to IS NOT DISTINCT FROM NEW.effective_to
        ) INTO conflict_exists;
    ELSIF TG_TABLE_NAME = 'trading_session' THEN
        SELECT EXISTS (
            SELECT 1 FROM mra.source_gap AS gap
            WHERE gap.capture_id = capture_key
              AND gap.fact_kind = 'TRADING_SESSION'
              AND gap.exchange = NEW.exchange
              AND gap.session_date = NEW.session_date
        ) INTO conflict_exists;
    ELSIF TG_TABLE_NAME = 'classification' THEN
        SELECT EXISTS (
            SELECT 1 FROM mra.source_gap AS gap
            WHERE gap.capture_id = capture_key
              AND gap.fact_kind = 'CLASSIFICATION'
              AND gap.classification_scheme = NEW.classification_scheme
              AND gap.classification_code = NEW.classification_code
              AND gap.effective_from = NEW.effective_from
              AND gap.effective_to IS NOT DISTINCT FROM NEW.effective_to
        ) INTO conflict_exists;
    ELSIF TG_TABLE_NAME = 'classification_membership_revision' THEN
        SELECT EXISTS (
            SELECT 1
            FROM mra.source_gap AS gap
            JOIN mra.classification AS classification
              ON classification.classification_id = NEW.classification_id
            WHERE gap.capture_id = capture_key
              AND gap.fact_kind = 'CLASSIFICATION_MEMBERSHIP'
              AND gap.classification_scheme = classification.classification_scheme
              AND gap.classification_code = classification.classification_code
              AND gap.instrument_id = NEW.instrument_id
              AND gap.effective_from = NEW.effective_from
              AND gap.effective_to IS NOT DISTINCT FROM NEW.effective_to
        ) INTO conflict_exists;
    ELSIF TG_TABLE_NAME = 'market_bar_revision' THEN
        SELECT EXISTS (
            SELECT 1 FROM mra.source_gap AS gap
            WHERE gap.capture_id = capture_key
              AND gap.instrument_id = NEW.instrument_id
              AND gap.session_id = NEW.session_id
              AND gap.fact_kind = 'MARKET_BAR'
              AND gap.timeframe = NEW.timeframe
              AND gap.price_basis = NEW.price_basis
              AND gap.event_start = NEW.event_start
              AND gap.event_end = NEW.event_end
        ) INTO conflict_exists;
    ELSIF TG_TABLE_NAME = 'instrument_fact_revision' THEN
        SELECT EXISTS (
            SELECT 1 FROM mra.source_gap AS gap
            WHERE gap.capture_id = capture_key
              AND gap.fact_kind = 'INSTRUMENT_FACT'
              AND gap.instrument_id = NEW.instrument_id
              AND gap.instrument_fact_kind = NEW.fact_kind
              AND gap.evidence_scope = NEW.evidence_scope
              AND gap.session_id IS NOT DISTINCT FROM NEW.session_id
              AND (
                  (NEW.evidence_scope = 'EFFECTIVE_INTERVAL'
                   AND gap.effective_from = NEW.event_start
                   AND gap.effective_to IS NOT DISTINCT FROM NEW.event_end)
                  OR
                  (NEW.evidence_scope <> 'EFFECTIVE_INTERVAL'
                   AND gap.event_start = NEW.event_start
                   AND gap.event_end IS NOT DISTINCT FROM NEW.event_end)
              )
        ) INTO conflict_exists;
    ELSIF TG_TABLE_NAME = 'corporate_action_revision' THEN
        SELECT EXISTS (
            SELECT 1 FROM mra.source_gap AS gap
            WHERE gap.capture_id = capture_key
              AND gap.fact_kind = 'CORPORATE_ACTION'
              AND gap.instrument_id = NEW.instrument_id
              AND gap.session_id = NEW.ex_session_id
              AND gap.action_key = NEW.action_key
        ) INTO conflict_exists;
    ELSE
        IF NEW.fact_kind = 'DATA_CAPTURE' THEN
            conflict_exists := false;
        ELSIF NEW.fact_kind = 'INSTRUMENT' THEN
            SELECT EXISTS (
                SELECT 1 FROM mra.instrument AS fact
                WHERE fact.source_capture_id = capture_key
                  AND fact.canonical_code = NEW.instrument_code
            ) INTO conflict_exists;
        ELSIF NEW.fact_kind = 'INSTRUMENT_IDENTIFIER' THEN
            SELECT EXISTS (
                SELECT 1 FROM mra.instrument_identifier AS fact
                WHERE fact.source_capture_id = capture_key
                  AND fact.identifier_scheme = NEW.identifier_scheme
                  AND fact.identifier_value = NEW.identifier_value
                  AND (NEW.instrument_id IS NULL OR fact.instrument_id = NEW.instrument_id)
                  AND fact.effective_from = NEW.effective_from
                  AND fact.effective_to IS NOT DISTINCT FROM NEW.effective_to
            ) INTO conflict_exists;
        ELSIF NEW.fact_kind = 'TRADING_SESSION' THEN
            SELECT EXISTS (
                SELECT 1 FROM mra.trading_session AS fact
                WHERE fact.source_capture_id = capture_key
                  AND fact.exchange = NEW.exchange
                  AND fact.session_date = NEW.session_date
            ) INTO conflict_exists;
        ELSIF NEW.fact_kind = 'CLASSIFICATION' THEN
            SELECT EXISTS (
                SELECT 1 FROM mra.classification AS fact
                WHERE fact.source_capture_id = capture_key
                  AND fact.classification_scheme = NEW.classification_scheme
                  AND fact.classification_code = NEW.classification_code
                  AND fact.effective_from = NEW.effective_from
                  AND fact.effective_to IS NOT DISTINCT FROM NEW.effective_to
            ) INTO conflict_exists;
        ELSIF NEW.fact_kind = 'CLASSIFICATION_MEMBERSHIP' THEN
            SELECT EXISTS (
                SELECT 1
                FROM mra.classification_membership_revision AS fact
                JOIN mra.classification AS classification
                  ON classification.classification_id = fact.classification_id
                WHERE fact.source_capture_id = capture_key
                  AND classification.classification_scheme = NEW.classification_scheme
                  AND classification.classification_code = NEW.classification_code
                  AND fact.instrument_id = NEW.instrument_id
                  AND fact.effective_from = NEW.effective_from
                  AND fact.effective_to IS NOT DISTINCT FROM NEW.effective_to
            ) INTO conflict_exists;
        ELSIF NEW.fact_kind = 'MARKET_BAR' THEN
            SELECT EXISTS (
                SELECT 1 FROM mra.market_bar_revision AS fact
                WHERE fact.capture_id = capture_key
                  AND fact.instrument_id = NEW.instrument_id
                  AND fact.session_id = NEW.session_id
                  AND fact.timeframe = NEW.timeframe
                  AND fact.price_basis = NEW.price_basis
                  AND fact.event_start = NEW.event_start
                  AND fact.event_end = NEW.event_end
            ) INTO conflict_exists;
        ELSIF NEW.fact_kind = 'INSTRUMENT_FACT' THEN
            SELECT EXISTS (
                SELECT 1 FROM mra.instrument_fact_revision AS fact
                WHERE fact.capture_id = capture_key
                  AND fact.instrument_id = NEW.instrument_id
                  AND fact.fact_kind = NEW.instrument_fact_kind
                  AND fact.evidence_scope = NEW.evidence_scope
                  AND fact.session_id IS NOT DISTINCT FROM NEW.session_id
                  AND (
                      (NEW.evidence_scope = 'EFFECTIVE_INTERVAL'
                       AND fact.event_start = NEW.effective_from
                       AND fact.event_end IS NOT DISTINCT FROM NEW.effective_to)
                      OR
                      (NEW.evidence_scope <> 'EFFECTIVE_INTERVAL'
                       AND fact.event_start = NEW.event_start
                       AND fact.event_end IS NOT DISTINCT FROM NEW.event_end)
                  )
            ) INTO conflict_exists;
        ELSE
            SELECT EXISTS (
                SELECT 1 FROM mra.corporate_action_revision AS fact
                WHERE fact.capture_id = capture_key
                  AND fact.instrument_id = NEW.instrument_id
                  AND fact.ex_session_id = NEW.session_id
                  AND fact.action_key = NEW.action_key
            ) INTO conflict_exists;
        END IF;
    END IF;
    IF conflict_exists THEN
        RAISE EXCEPTION 'one Capture cannot assert both a canonical Market fact and a SourceGap for the same expected observation' USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TABLE mra.schema_epoch (
    singleton boolean PRIMARY KEY DEFAULT true,
    epoch_name text NOT NULL UNIQUE,
    schema_name text NOT NULL,
    release_state text NOT NULL,
    baseline_version smallint NOT NULL,
    baseline_checksum text NOT NULL,
    seed_checksum text NOT NULL,
    catalog_checksum text NOT NULL,
    reference_vocabulary_checksum text NOT NULL,
    installed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT schema_epoch_singleton_ck CHECK (singleton),
    CONSTRAINT schema_epoch_name_ck CHECK (epoch_name = 'MRA_REFOUNDATION_1'),
    CONSTRAINT schema_epoch_schema_ck CHECK (schema_name = 'mra'),
    CONSTRAINT schema_epoch_release_state_ck CHECK (release_state IN ('DRAFT', 'RELEASED')),
    CONSTRAINT schema_epoch_baseline_version_ck CHECK (baseline_version > 0),
    CONSTRAINT schema_epoch_baseline_checksum_ck CHECK (baseline_checksum ~ '^[0-9a-f]{64}$'),
    CONSTRAINT schema_epoch_seed_checksum_ck CHECK (seed_checksum ~ '^[0-9a-f]{64}$'),
    CONSTRAINT schema_epoch_catalog_checksum_ck CHECK (catalog_checksum ~ '^[0-9a-f]{64}$'),
    CONSTRAINT schema_epoch_vocabulary_checksum_ck CHECK (reference_vocabulary_checksum ~ '^[0-9a-f]{64}$')
);

CREATE TABLE mra.schema_migrations (
    version integer PRIMARY KEY,
    name text NOT NULL UNIQUE,
    checksum text NOT NULL,
    transactional boolean NOT NULL,
    epoch_name text NOT NULL REFERENCES mra.schema_epoch(epoch_name) ON DELETE RESTRICT,
    applied_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT schema_migrations_version_ck CHECK (version > 0),
    CONSTRAINT schema_migrations_name_ck CHECK (name ~ '^[0-9]{3}_[a-z0-9_]+$'),
    CONSTRAINT schema_migrations_checksum_ck CHECK (checksum ~ '^[0-9a-f]{64}$')
);
CREATE INDEX schema_migrations_epoch_idx ON mra.schema_migrations (epoch_name);

CREATE TABLE mra.artifact (
    artifact_id uuid PRIMARY KEY,
    content_sha256 text NOT NULL UNIQUE,
    size_bytes bigint NOT NULL,
    media_type text NOT NULL,
    locator text NOT NULL UNIQUE,
    integrity_state text NOT NULL,
    retention_until timestamptz,
    pin_reason_code text,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    last_verified_at timestamptz,
    CONSTRAINT artifact_exact_identity_uk UNIQUE (
        artifact_id, content_sha256, size_bytes
    ),
    CONSTRAINT artifact_hash_ck CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT artifact_size_ck CHECK (size_bytes >= 0),
    CONSTRAINT artifact_media_type_ck CHECK (media_type ~ '^[A-Za-z0-9][A-Za-z0-9.+-]+/[A-Za-z0-9][A-Za-z0-9.+-]+$'),
    CONSTRAINT artifact_locator_ck CHECK (locator <> ''),
    CONSTRAINT artifact_integrity_state_ck CHECK (integrity_state IN ('AVAILABLE', 'MISSING', 'CORRUPT', 'QUARANTINED', 'DELETED')),
    CONSTRAINT artifact_pin_reason_ck CHECK (pin_reason_code IS NULL OR pin_reason_code ~ '^[A-Z][A-Z0-9_]{0,99}$')
);
CREATE INDEX artifact_unhealthy_idx ON mra.artifact (integrity_state, created_at)
    WHERE integrity_state <> 'AVAILABLE';
CREATE INDEX artifact_retention_idx ON mra.artifact (retention_until)
    WHERE retention_until IS NOT NULL;

CREATE TABLE mra.artifact_dependency (
    child_artifact_id uuid NOT NULL REFERENCES mra.artifact(artifact_id) ON DELETE RESTRICT,
    parent_artifact_id uuid NOT NULL REFERENCES mra.artifact(artifact_id) ON DELETE RESTRICT,
    dependency_role text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (child_artifact_id, parent_artifact_id, dependency_role),
    CONSTRAINT artifact_dependency_no_self_ck CHECK (child_artifact_id <> parent_artifact_id),
    CONSTRAINT artifact_dependency_role_ck CHECK (dependency_role ~ '^[A-Z][A-Z0-9_]{0,99}$')
);
CREATE INDEX artifact_dependency_parent_idx ON mra.artifact_dependency (parent_artifact_id, child_artifact_id);

CREATE TABLE mra.artifact_verification (
    verification_id uuid PRIMARY KEY,
    artifact_id uuid NOT NULL REFERENCES mra.artifact(artifact_id) ON DELETE RESTRICT,
    command_receipt_id uuid NOT NULL,
    verifier_id text NOT NULL,
    verification_policy text NOT NULL,
    result text NOT NULL,
    observed_exists boolean NOT NULL,
    observed_size_bytes bigint,
    observed_sha256 text,
    verified_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT artifact_verification_verifier_ck CHECK (verifier_id <> ''),
    CONSTRAINT artifact_verification_policy_ck CHECK (verification_policy ~ '^[A-Z][A-Z0-9_]{0,99}$'),
    CONSTRAINT artifact_verification_result_ck CHECK (result IN (
        'VERIFIED', 'MISSING', 'SIZE_MISMATCH', 'HASH_MISMATCH',
        'INTEGRITY_ERROR'
    )),
    CONSTRAINT artifact_verification_size_ck CHECK (observed_size_bytes IS NULL OR observed_size_bytes >= 0),
    CONSTRAINT artifact_verification_hash_ck CHECK (observed_sha256 IS NULL OR observed_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT artifact_verification_observation_ck CHECK (
        (observed_exists AND observed_size_bytes IS NOT NULL) OR
        (NOT observed_exists AND observed_size_bytes IS NULL AND observed_sha256 IS NULL)
    )
);
CREATE INDEX artifact_verification_artifact_idx ON mra.artifact_verification (artifact_id, verified_at DESC);
CREATE INDEX artifact_verification_receipt_idx ON mra.artifact_verification (command_receipt_id);
CREATE INDEX artifact_verification_failure_idx ON mra.artifact_verification (verified_at, artifact_id)
    WHERE result <> 'VERIFIED';

CREATE TABLE mra.artifact_gc_candidate (
    content_sha256 text PRIMARY KEY,
    artifact_id uuid REFERENCES mra.artifact(artifact_id) ON DELETE RESTRICT,
    state text NOT NULL,
    first_seen_at timestamptz NOT NULL,
    last_seen_at timestamptz NOT NULL,
    grace_until timestamptz NOT NULL,
    second_seen_at timestamptz,
    operation_token uuid,
    quarantined_at timestamptz,
    deleted_at timestamptz,
    cleared_at timestamptz,
    operator_id text,
    disposition_reason_code text,
    CONSTRAINT artifact_gc_candidate_hash_ck CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT artifact_gc_candidate_state_ck CHECK (state IN ('OBSERVED', 'QUARANTINE_PENDING', 'QUARANTINED', 'DELETE_PENDING', 'DELETED', 'CLEARED')),
    CONSTRAINT artifact_gc_candidate_times_ck CHECK (last_seen_at >= first_seen_at AND grace_until >= first_seen_at),
    CONSTRAINT artifact_gc_candidate_operator_ck CHECK (operator_id IS NULL OR operator_id <> ''),
    CONSTRAINT artifact_gc_candidate_reason_ck CHECK (disposition_reason_code IS NULL OR disposition_reason_code ~ '^[A-Z][A-Z0-9_]{0,99}$')
);
CREATE UNIQUE INDEX artifact_gc_candidate_artifact_idx ON mra.artifact_gc_candidate (artifact_id)
    WHERE artifact_id IS NOT NULL;
CREATE INDEX artifact_gc_candidate_due_idx ON mra.artifact_gc_candidate (state, grace_until)
    WHERE state IN ('OBSERVED', 'QUARANTINE_PENDING', 'QUARANTINED', 'DELETE_PENDING');

CREATE TABLE mra.provider (
    provider_id uuid PRIMARY KEY,
    provider_code text NOT NULL UNIQUE,
    display_name text NOT NULL,
    provider_kind text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT provider_code_ck CHECK (provider_code ~ '^[a-z][a-z0-9_-]{0,99}$'),
    CONSTRAINT provider_name_ck CHECK (display_name <> ''),
    CONSTRAINT provider_kind_ck CHECK (provider_kind IN ('PUBLIC_ENDPOINT', 'DATA_VENDOR', 'BROKER_FEED'))
);

CREATE TABLE mra.provider_product (
    provider_product_id uuid PRIMARY KEY,
    provider_id uuid NOT NULL REFERENCES mra.provider(provider_id) ON DELETE RESTRICT,
    product_code text NOT NULL,
    revision integer NOT NULL,
    payload_family text NOT NULL,
    media_type text NOT NULL,
    payload_encoding text NOT NULL,
    fact_kinds text[] NOT NULL,
    instrument_fact_kinds text[] NOT NULL,
    bar_timeframes text[] NOT NULL,
    price_bases text[] NOT NULL,
    decision_visibility_policy text NOT NULL DEFAULT 'KNOWN_AT',
    source_availability_policy text NOT NULL,
    supersedes_provider_product_id uuid REFERENCES mra.provider_product(provider_product_id) ON DELETE RESTRICT,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT provider_product_identity_uk UNIQUE (provider_id, product_code, revision),
    CONSTRAINT provider_product_code_ck CHECK (product_code ~ '^[a-z][a-z0-9_.-]{0,99}$'),
    CONSTRAINT provider_product_revision_ck CHECK (revision > 0),
    CONSTRAINT provider_product_revision_chain_ck CHECK (
        (revision = 1 AND supersedes_provider_product_id IS NULL) OR
        (revision > 1 AND supersedes_provider_product_id IS NOT NULL)
    ),
    CONSTRAINT provider_product_payload_ck CHECK (payload_family ~ '^[A-Z][A-Z0-9_]{0,99}$'),
    CONSTRAINT provider_product_media_type_ck CHECK (media_type ~ '^[A-Za-z0-9][A-Za-z0-9.+-]+/[A-Za-z0-9][A-Za-z0-9.+-]+$'),
    CONSTRAINT provider_product_encoding_ck CHECK (payload_encoding <> ''),
    CONSTRAINT provider_product_fact_kinds_ck CHECK (
        cardinality(fact_kinds) > 0
        AND array_position(fact_kinds, NULL) IS NULL
        AND fact_kinds <@ ARRAY[
            'INSTRUMENT', 'INSTRUMENT_IDENTIFIER', 'TRADING_SESSION',
            'CLASSIFICATION', 'CLASSIFICATION_MEMBERSHIP', 'MARKET_BAR',
            'INSTRUMENT_FACT', 'CORPORATE_ACTION'
        ]::text[]
    ),
    CONSTRAINT provider_product_instrument_fact_kinds_ck CHECK (
        array_position(instrument_fact_kinds, NULL) IS NULL
        AND instrument_fact_kinds <@ ARRAY[
            'SECURITY_STATUS', 'LISTING_STATUS',
            'SPECIAL_TREATMENT_STATUS', 'TOTAL_SHARES', 'FREE_FLOAT_SHARES',
            'LIMIT_UP_PRICE', 'LIMIT_DOWN_PRICE', 'REFERENCE_PRICE'
        ]::text[]
    ),
    CONSTRAINT provider_product_bar_timeframes_ck CHECK (
        array_position(bar_timeframes, NULL) IS NULL
        AND bar_timeframes <@ ARRAY[
            'MINUTE_1', 'MINUTE_5', 'MINUTE_15', 'MINUTE_30',
            'MINUTE_60', 'DAILY'
        ]::text[]
    ),
    CONSTRAINT provider_product_price_bases_ck CHECK (
        array_position(price_bases, NULL) IS NULL
        AND price_bases <@ ARRAY[
            'RAW_UNADJUSTED', 'FORWARD_ADJUSTED', 'BACKWARD_ADJUSTED'
        ]::text[]
    ),
    CONSTRAINT provider_product_bar_contract_ck CHECK (
        ('MARKET_BAR' = ANY(fact_kinds)) = (cardinality(bar_timeframes) > 0)
        AND ('MARKET_BAR' = ANY(fact_kinds)) = (cardinality(price_bases) > 0)
    ),
    CONSTRAINT provider_product_instrument_fact_contract_ck CHECK (
        ('INSTRUMENT_FACT' = ANY(fact_kinds)) =
        (cardinality(instrument_fact_kinds) > 0)
    ),
    CONSTRAINT provider_product_visibility_ck CHECK (decision_visibility_policy = 'KNOWN_AT'),
    CONSTRAINT provider_product_availability_ck CHECK (source_availability_policy IN ('UNKNOWN', 'PROVIDER_REPORTED')),
    CONSTRAINT provider_product_no_self_ck CHECK (supersedes_provider_product_id IS NULL OR supersedes_provider_product_id <> provider_product_id)
);
CREATE INDEX provider_product_provider_idx ON mra.provider_product (provider_id, product_code, revision DESC);
CREATE INDEX provider_product_supersedes_idx ON mra.provider_product (supersedes_provider_product_id)
    WHERE supersedes_provider_product_id IS NOT NULL;

CREATE TABLE mra.data_capture (
    capture_id uuid PRIMARY KEY,
    provider_product_id uuid NOT NULL REFERENCES mra.provider_product(provider_product_id) ON DELETE RESTRICT,
    capture_key text NOT NULL,
    request_hash text NOT NULL,
    artifact_id uuid REFERENCES mra.artifact(artifact_id) ON DELETE RESTRICT,
    status text NOT NULL,
    provider_time timestamptz,
    source_availability_status text NOT NULL,
    source_available_at timestamptz,
    capture_started_at timestamptz NOT NULL,
    capture_completed_at timestamptz NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    known_at timestamptz NOT NULL,
    decision_visible_at timestamptz NOT NULL,
    error_code text,
    limitation_code text,
    payload_encoding text,
    CONSTRAINT data_capture_product_identity_uk UNIQUE (capture_id, provider_product_id),
    CONSTRAINT data_capture_key_ck CHECK (capture_key ~ '^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$'),
    CONSTRAINT data_capture_request_hash_ck CHECK (request_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT data_capture_status_ck CHECK (status IN ('CAPTURED', 'PROVIDER_FAILURE')),
    CONSTRAINT data_capture_source_availability_ck CHECK (
        (source_availability_status = 'UNKNOWN' AND source_available_at IS NULL) OR
        (source_availability_status = 'PROVIDER_REPORTED' AND source_available_at IS NOT NULL)
    ),
    CONSTRAINT data_capture_time_order_ck CHECK (
        capture_completed_at >= capture_started_at
        AND known_at >= capture_completed_at
        AND (source_available_at IS NULL OR source_available_at <= known_at)
    ),
    CONSTRAINT data_capture_known_time_ck CHECK (
        known_at = GREATEST(capture_completed_at, recorded_at)
    ),
    CONSTRAINT data_capture_visibility_ck CHECK (decision_visible_at = known_at),
    CONSTRAINT data_capture_outcome_ck CHECK (
        (status = 'CAPTURED' AND artifact_id IS NOT NULL AND error_code IS NULL AND payload_encoding IS NOT NULL) OR
        (status = 'PROVIDER_FAILURE' AND error_code IS NOT NULL)
    ),
    CONSTRAINT data_capture_error_ck CHECK (error_code IS NULL OR error_code ~ '^[A-Z][A-Z0-9_]{0,99}$'),
    CONSTRAINT data_capture_limitation_ck CHECK (limitation_code IS NULL OR limitation_code ~ '^[A-Z][A-Z0-9_]{0,99}$')
);
CREATE INDEX data_capture_product_visibility_idx
    ON mra.data_capture (provider_product_id, decision_visible_at DESC, capture_id);
CREATE INDEX data_capture_correlation_idx
    ON mra.data_capture (
        provider_product_id, capture_key, decision_visible_at DESC, capture_id
    );
CREATE INDEX data_capture_artifact_idx ON mra.data_capture (artifact_id)
    WHERE artifact_id IS NOT NULL;
CREATE INDEX data_capture_failure_idx ON mra.data_capture (provider_product_id, known_at DESC)
    WHERE status = 'PROVIDER_FAILURE';

CREATE TABLE mra.instrument (
    instrument_id uuid PRIMARY KEY,
    canonical_code text NOT NULL UNIQUE,
    exchange text NOT NULL,
    instrument_type text NOT NULL,
    currency text NOT NULL,
    source_capture_id uuid NOT NULL REFERENCES mra.data_capture(capture_id) ON DELETE RESTRICT,
    recorded_at timestamptz NOT NULL,
    known_at timestamptz NOT NULL,
    decision_visible_at timestamptz NOT NULL,
    CONSTRAINT instrument_code_ck CHECK (canonical_code ~ '^[A-Z0-9][A-Z0-9._-]{0,31}$'),
    CONSTRAINT instrument_exchange_ck CHECK (exchange ~ '^[A-Z][A-Z0-9]{1,15}$'),
    CONSTRAINT instrument_type_ck CHECK (instrument_type IN ('EQUITY', 'ETF', 'INDEX', 'FUND', 'BOND')),
    CONSTRAINT instrument_currency_ck CHECK (currency ~ '^[A-Z]{3}$'),
    CONSTRAINT instrument_temporal_ck CHECK (
        known_at >= recorded_at AND decision_visible_at = known_at
    )
);
CREATE INDEX instrument_capture_idx ON mra.instrument (source_capture_id);
CREATE INDEX instrument_exchange_code_idx ON mra.instrument (exchange, canonical_code);

CREATE TABLE mra.instrument_identifier (
    instrument_identifier_id uuid PRIMARY KEY,
    instrument_id uuid NOT NULL REFERENCES mra.instrument(instrument_id) ON DELETE RESTRICT,
    identifier_scheme text NOT NULL,
    identifier_value text NOT NULL,
    effective_from timestamptz NOT NULL,
    effective_to timestamptz,
    revision integer NOT NULL,
    supersedes_identifier_id uuid REFERENCES mra.instrument_identifier(instrument_identifier_id) ON DELETE RESTRICT,
    source_capture_id uuid NOT NULL REFERENCES mra.data_capture(capture_id) ON DELETE RESTRICT,
    recorded_at timestamptz NOT NULL,
    known_at timestamptz NOT NULL,
    decision_visible_at timestamptz NOT NULL,
    CONSTRAINT instrument_identifier_identity_uk UNIQUE (instrument_id, identifier_scheme, effective_from, revision),
    CONSTRAINT instrument_identifier_lookup_uk UNIQUE (identifier_scheme, identifier_value, effective_from, revision),
    CONSTRAINT instrument_identifier_scheme_ck CHECK (identifier_scheme ~ '^[A-Z][A-Z0-9_]{0,31}$'),
    CONSTRAINT instrument_identifier_value_ck CHECK (identifier_value <> ''),
    CONSTRAINT instrument_identifier_interval_ck CHECK (effective_to IS NULL OR effective_to > effective_from),
    CONSTRAINT instrument_identifier_revision_ck CHECK (revision > 0),
    CONSTRAINT instrument_identifier_revision_chain_ck CHECK (
        (revision = 1 AND supersedes_identifier_id IS NULL) OR
        (revision > 1 AND supersedes_identifier_id IS NOT NULL)
    ),
    CONSTRAINT instrument_identifier_no_self_ck CHECK (supersedes_identifier_id IS NULL OR supersedes_identifier_id <> instrument_identifier_id),
    CONSTRAINT instrument_identifier_temporal_ck CHECK (
        known_at >= recorded_at AND decision_visible_at = known_at
    )
);
CREATE INDEX instrument_identifier_instrument_idx
    ON mra.instrument_identifier (instrument_id, identifier_scheme, effective_from DESC);
CREATE INDEX instrument_identifier_capture_idx ON mra.instrument_identifier (source_capture_id);
CREATE INDEX instrument_identifier_supersedes_idx ON mra.instrument_identifier (supersedes_identifier_id)
    WHERE supersedes_identifier_id IS NOT NULL;
CREATE INDEX instrument_identifier_asof_idx
    ON mra.instrument_identifier (
        identifier_scheme, identifier_value, effective_from DESC, effective_to,
        decision_visible_at DESC, revision DESC
    );

CREATE TABLE mra.trading_session (
    session_id uuid PRIMARY KEY,
    exchange text NOT NULL,
    session_date date NOT NULL,
    timezone_name text NOT NULL,
    open_at timestamptz NOT NULL,
    break_start_at timestamptz,
    break_end_at timestamptz,
    close_at timestamptz NOT NULL,
    decision_reference_at timestamptz NOT NULL,
    source_capture_id uuid NOT NULL REFERENCES mra.data_capture(capture_id) ON DELETE RESTRICT,
    recorded_at timestamptz NOT NULL,
    known_at timestamptz NOT NULL,
    decision_visible_at timestamptz NOT NULL,
    CONSTRAINT trading_session_identity_uk UNIQUE (exchange, session_date),
    CONSTRAINT trading_session_exchange_ck CHECK (exchange ~ '^[A-Z][A-Z0-9]{1,15}$'),
    CONSTRAINT trading_session_timezone_ck CHECK (timezone_name = 'Asia/Shanghai'),
    CONSTRAINT trading_session_break_ck CHECK ((break_start_at IS NULL) = (break_end_at IS NULL)),
    CONSTRAINT trading_session_order_ck CHECK (
        open_at < close_at
        AND decision_reference_at > open_at
        AND decision_reference_at <= close_at
        AND (open_at AT TIME ZONE timezone_name)::date = session_date
        AND (close_at AT TIME ZONE timezone_name)::date = session_date
        AND (decision_reference_at AT TIME ZONE timezone_name)::date = session_date
        AND (decision_reference_at AT TIME ZONE timezone_name)::time = TIME '14:55:00'
        AND (
            break_start_at IS NULL OR
            (open_at < break_start_at AND break_start_at < break_end_at AND break_end_at < close_at)
        )
    ),
    CONSTRAINT trading_session_temporal_ck CHECK (
        known_at >= recorded_at AND decision_visible_at = known_at
    )
);
CREATE INDEX trading_session_capture_idx ON mra.trading_session (source_capture_id);
CREATE INDEX trading_session_calendar_idx ON mra.trading_session (
    exchange, session_date, decision_visible_at DESC, session_id
);

CREATE TABLE mra.classification (
    classification_id uuid PRIMARY KEY,
    classification_scheme text NOT NULL,
    classification_code text NOT NULL,
    display_name text NOT NULL,
    revision integer NOT NULL,
    effective_from timestamptz NOT NULL,
    effective_to timestamptz,
    supersedes_classification_id uuid REFERENCES mra.classification(classification_id) ON DELETE RESTRICT,
    source_capture_id uuid NOT NULL REFERENCES mra.data_capture(capture_id) ON DELETE RESTRICT,
    recorded_at timestamptz NOT NULL,
    known_at timestamptz NOT NULL,
    decision_visible_at timestamptz NOT NULL,
    CONSTRAINT classification_identity_uk UNIQUE (
        classification_scheme, classification_code, effective_from, revision
    ),
    CONSTRAINT classification_scheme_ck CHECK (classification_scheme ~ '^[A-Z][A-Z0-9_]{0,31}$'),
    CONSTRAINT classification_code_ck CHECK (classification_code <> ''),
    CONSTRAINT classification_name_ck CHECK (display_name <> ''),
    CONSTRAINT classification_revision_ck CHECK (revision > 0),
    CONSTRAINT classification_interval_ck CHECK (effective_to IS NULL OR effective_to > effective_from),
    CONSTRAINT classification_revision_chain_ck CHECK (
        (revision = 1 AND supersedes_classification_id IS NULL) OR
        (revision > 1 AND supersedes_classification_id IS NOT NULL)
    ),
    CONSTRAINT classification_no_self_ck CHECK (supersedes_classification_id IS NULL OR supersedes_classification_id <> classification_id),
    CONSTRAINT classification_temporal_ck CHECK (
        known_at >= recorded_at AND decision_visible_at = known_at
    )
);
CREATE INDEX classification_capture_idx ON mra.classification (source_capture_id);
CREATE INDEX classification_supersedes_idx ON mra.classification (supersedes_classification_id)
    WHERE supersedes_classification_id IS NOT NULL;
CREATE INDEX classification_asof_idx
    ON mra.classification (
        classification_scheme, classification_code, effective_from DESC,
        effective_to, decision_visible_at DESC, revision DESC
    );

CREATE TABLE mra.classification_membership_revision (
    membership_revision_id uuid PRIMARY KEY,
    classification_id uuid NOT NULL REFERENCES mra.classification(classification_id) ON DELETE RESTRICT,
    instrument_id uuid NOT NULL REFERENCES mra.instrument(instrument_id) ON DELETE RESTRICT,
    source_capture_id uuid NOT NULL REFERENCES mra.data_capture(capture_id) ON DELETE RESTRICT,
    membership_status text NOT NULL,
    effective_from timestamptz NOT NULL,
    effective_to timestamptz,
    revision integer NOT NULL,
    supersedes_membership_revision_id uuid REFERENCES mra.classification_membership_revision(membership_revision_id) ON DELETE RESTRICT,
    recorded_at timestamptz NOT NULL,
    known_at timestamptz NOT NULL,
    decision_visible_at timestamptz NOT NULL,
    CONSTRAINT classification_membership_identity_uk UNIQUE (classification_id, instrument_id, effective_from, revision),
    CONSTRAINT classification_membership_status_ck CHECK (membership_status IN ('MEMBER', 'NOT_MEMBER')),
    CONSTRAINT classification_membership_interval_ck CHECK (effective_to IS NULL OR effective_to > effective_from),
    CONSTRAINT classification_membership_revision_ck CHECK (revision > 0),
    CONSTRAINT classification_membership_revision_chain_ck CHECK (
        (revision = 1 AND supersedes_membership_revision_id IS NULL) OR
        (revision > 1 AND supersedes_membership_revision_id IS NOT NULL)
    ),
    CONSTRAINT classification_membership_no_self_ck CHECK (supersedes_membership_revision_id IS NULL OR supersedes_membership_revision_id <> membership_revision_id),
    CONSTRAINT classification_membership_temporal_ck CHECK (
        known_at >= recorded_at AND decision_visible_at = known_at
    )
);
CREATE INDEX classification_membership_classification_idx
    ON mra.classification_membership_revision (
        classification_id, instrument_id, effective_from DESC,
        decision_visible_at DESC, revision DESC
    );
CREATE INDEX classification_membership_instrument_idx
    ON mra.classification_membership_revision (instrument_id, classification_id, effective_from DESC);
CREATE INDEX classification_membership_capture_idx
    ON mra.classification_membership_revision (source_capture_id);
CREATE INDEX classification_membership_supersedes_idx
    ON mra.classification_membership_revision (supersedes_membership_revision_id)
    WHERE supersedes_membership_revision_id IS NOT NULL;

CREATE TABLE mra.market_bar_revision (
    bar_revision_id uuid PRIMARY KEY,
    provider_product_id uuid NOT NULL REFERENCES mra.provider_product(provider_product_id) ON DELETE RESTRICT,
    capture_id uuid NOT NULL REFERENCES mra.data_capture(capture_id) ON DELETE RESTRICT,
    instrument_id uuid NOT NULL REFERENCES mra.instrument(instrument_id) ON DELETE RESTRICT,
    session_id uuid NOT NULL REFERENCES mra.trading_session(session_id) ON DELETE RESTRICT,
    timeframe text NOT NULL,
    price_basis text NOT NULL,
    event_start timestamptz NOT NULL,
    event_end timestamptz NOT NULL,
    revision integer NOT NULL,
    supersedes_revision_id uuid REFERENCES mra.market_bar_revision(bar_revision_id) ON DELETE RESTRICT,
    open_value numeric NOT NULL,
    high_value numeric NOT NULL,
    low_value numeric NOT NULL,
    close_value numeric NOT NULL,
    volume_value numeric NOT NULL,
    turnover_value numeric,
    recorded_at timestamptz NOT NULL,
    known_at timestamptz NOT NULL,
    decision_visible_at timestamptz NOT NULL,
    CONSTRAINT market_bar_capture_product_fk FOREIGN KEY (
        capture_id, provider_product_id
    ) REFERENCES mra.data_capture(capture_id, provider_product_id) ON DELETE RESTRICT,
    CONSTRAINT market_bar_revision_identity_uk UNIQUE (
        provider_product_id, instrument_id, session_id, timeframe,
        price_basis, event_start, event_end, revision
    ),
    CONSTRAINT market_bar_timeframe_ck CHECK (timeframe IN ('MINUTE_1', 'MINUTE_5', 'MINUTE_15', 'MINUTE_30', 'MINUTE_60', 'DAILY')),
    CONSTRAINT market_bar_basis_ck CHECK (price_basis IN ('RAW_UNADJUSTED', 'FORWARD_ADJUSTED', 'BACKWARD_ADJUSTED')),
    CONSTRAINT market_bar_interval_ck CHECK (
        event_end > event_start
        AND (timeframe <> 'MINUTE_1' OR event_end - event_start = interval '1 minute')
        AND (timeframe <> 'MINUTE_5' OR event_end - event_start = interval '5 minutes')
        AND (timeframe <> 'MINUTE_15' OR event_end - event_start = interval '15 minutes')
        AND (timeframe <> 'MINUTE_30' OR event_end - event_start = interval '30 minutes')
        AND (timeframe <> 'MINUTE_60' OR event_end - event_start = interval '60 minutes')
    ),
    CONSTRAINT market_bar_revision_ck CHECK (revision > 0),
    CONSTRAINT market_bar_revision_chain_ck CHECK (
        (revision = 1 AND supersedes_revision_id IS NULL) OR
        (revision > 1 AND supersedes_revision_id IS NOT NULL)
    ),
    CONSTRAINT market_bar_no_self_ck CHECK (supersedes_revision_id IS NULL OR supersedes_revision_id <> bar_revision_id),
    CONSTRAINT market_bar_ohlc_ck CHECK (
        open_value > 0 AND high_value > 0 AND low_value > 0 AND close_value > 0
        AND high_value >= greatest(open_value, close_value, low_value)
        AND low_value <= least(open_value, close_value, high_value)
    ),
    CONSTRAINT market_bar_money_bounds_ck CHECK (
        scale(open_value) <= 10 AND abs(open_value) < 1e20
        AND scale(high_value) <= 10 AND abs(high_value) < 1e20
        AND scale(low_value) <= 10 AND abs(low_value) < 1e20
        AND scale(close_value) <= 10 AND abs(close_value) < 1e20
        AND (
            turnover_value IS NULL OR
            (scale(turnover_value) <= 10 AND abs(turnover_value) < 1e20)
        )
    ),
    CONSTRAINT market_bar_quantity_bounds_ck CHECK (
        scale(volume_value) <= 10 AND abs(volume_value) < 1e28
    ),
    CONSTRAINT market_bar_volume_ck CHECK (volume_value >= 0 AND (turnover_value IS NULL OR turnover_value >= 0)),
    CONSTRAINT market_bar_temporal_ck CHECK (
        known_at >= recorded_at
        AND known_at >= event_end
        AND decision_visible_at = known_at
    )
);
CREATE INDEX market_bar_exact_asof_idx ON mra.market_bar_revision (
    provider_product_id, instrument_id, session_id, timeframe,
    price_basis, event_end, event_start, decision_visible_at DESC,
    revision DESC, capture_id
);
CREATE INDEX market_bar_capture_idx ON mra.market_bar_revision (
    capture_id, provider_product_id
);
CREATE INDEX market_bar_instrument_idx ON mra.market_bar_revision (instrument_id, event_end DESC);
CREATE INDEX market_bar_session_idx ON mra.market_bar_revision (session_id, instrument_id, event_end);
CREATE INDEX market_bar_supersedes_idx ON mra.market_bar_revision (supersedes_revision_id)
    WHERE supersedes_revision_id IS NOT NULL;

CREATE TABLE mra.instrument_fact_revision (
    fact_revision_id uuid PRIMARY KEY,
    provider_product_id uuid NOT NULL REFERENCES mra.provider_product(provider_product_id) ON DELETE RESTRICT,
    capture_id uuid NOT NULL REFERENCES mra.data_capture(capture_id) ON DELETE RESTRICT,
    instrument_id uuid NOT NULL REFERENCES mra.instrument(instrument_id) ON DELETE RESTRICT,
    session_id uuid REFERENCES mra.trading_session(session_id) ON DELETE RESTRICT,
    fact_kind text NOT NULL,
    evidence_scope text NOT NULL,
    event_start timestamptz NOT NULL,
    event_end timestamptz,
    value_kind text NOT NULL,
    status_value text,
    numeric_value numeric,
    unit_code text,
    revision integer NOT NULL,
    supersedes_revision_id uuid REFERENCES mra.instrument_fact_revision(fact_revision_id) ON DELETE RESTRICT,
    recorded_at timestamptz NOT NULL,
    known_at timestamptz NOT NULL,
    decision_visible_at timestamptz NOT NULL,
    CONSTRAINT instrument_fact_capture_product_fk FOREIGN KEY (
        capture_id, provider_product_id
    ) REFERENCES mra.data_capture(capture_id, provider_product_id) ON DELETE RESTRICT,
    CONSTRAINT instrument_fact_identity_uk UNIQUE NULLS NOT DISTINCT (
        provider_product_id, instrument_id, session_id, fact_kind,
        evidence_scope, event_start, revision
    ),
    CONSTRAINT instrument_fact_kind_ck CHECK (fact_kind IN (
        'SECURITY_STATUS', 'LISTING_STATUS', 'SPECIAL_TREATMENT_STATUS',
        'TOTAL_SHARES', 'FREE_FLOAT_SHARES',
        'LIMIT_UP_PRICE', 'LIMIT_DOWN_PRICE', 'REFERENCE_PRICE'
    )),
    CONSTRAINT instrument_fact_scope_ck CHECK (evidence_scope IN ('DECISION_SESSION', 'PRIOR_SESSION', 'EFFECTIVE_INTERVAL')),
    CONSTRAINT instrument_fact_interval_ck CHECK (
        event_end IS NULL OR event_end > event_start
    ),
    CONSTRAINT instrument_fact_value_kind_ck CHECK (value_kind IN ('STATUS', 'DECIMAL')),
    CONSTRAINT instrument_fact_value_ck CHECK (
        (value_kind = 'STATUS' AND status_value IS NOT NULL AND numeric_value IS NULL) OR
        (value_kind = 'DECIMAL' AND status_value IS NULL AND numeric_value IS NOT NULL)
    ),
    CONSTRAINT instrument_fact_security_status_ck CHECK (
        fact_kind <> 'SECURITY_STATUS' OR
        (value_kind = 'STATUS'
         AND status_value IN ('ACTIVE', 'SUSPENDED', 'UNKNOWN')
         AND session_id IS NOT NULL
         AND evidence_scope IN ('DECISION_SESSION', 'PRIOR_SESSION')
         AND event_end IS NOT NULL
         AND unit_code IS NULL)
    ),
    CONSTRAINT instrument_fact_lifecycle_status_ck CHECK (
        (fact_kind = 'LISTING_STATUS'
         AND value_kind = 'STATUS'
         AND status_value IN ('PRE_LISTING', 'LISTED', 'DELISTED', 'UNKNOWN')
         AND session_id IS NULL
         AND evidence_scope = 'EFFECTIVE_INTERVAL'
         AND unit_code IS NULL)
        OR
        (fact_kind = 'SPECIAL_TREATMENT_STATUS'
         AND value_kind = 'STATUS'
         AND status_value IN ('NORMAL', 'ST', 'STAR_ST', 'UNKNOWN')
         AND session_id IS NULL
         AND evidence_scope = 'EFFECTIVE_INTERVAL'
         AND unit_code IS NULL)
        OR
        fact_kind NOT IN ('LISTING_STATUS', 'SPECIAL_TREATMENT_STATUS')
    ),
    CONSTRAINT instrument_fact_kind_value_ck CHECK (
        (fact_kind IN ('TOTAL_SHARES', 'FREE_FLOAT_SHARES')
         AND value_kind = 'DECIMAL'
         AND numeric_value >= 0
         AND scale(numeric_value) <= 10
         AND abs(numeric_value) < 1e28
         AND unit_code = 'SHARES'
         AND evidence_scope = 'EFFECTIVE_INTERVAL'
         AND session_id IS NULL)
        OR
        (fact_kind IN ('LIMIT_UP_PRICE', 'LIMIT_DOWN_PRICE', 'REFERENCE_PRICE')
         AND value_kind = 'DECIMAL'
         AND numeric_value > 0
         AND scale(numeric_value) <= 10
         AND abs(numeric_value) < 1e20
         AND unit_code ~ '^[A-Z]{3}$'
         AND evidence_scope IN ('DECISION_SESSION', 'PRIOR_SESSION')
         AND event_end IS NOT NULL
         AND session_id IS NOT NULL)
        OR
        fact_kind IN (
            'SECURITY_STATUS', 'LISTING_STATUS', 'SPECIAL_TREATMENT_STATUS'
        )
    ),
    CONSTRAINT instrument_fact_session_scope_ck CHECK (
        evidence_scope = 'EFFECTIVE_INTERVAL' OR session_id IS NOT NULL
    ),
    CONSTRAINT instrument_fact_unit_ck CHECK (unit_code IS NULL OR unit_code ~ '^[A-Z][A-Z0-9_]{0,31}$'),
    CONSTRAINT instrument_fact_revision_ck CHECK (revision > 0),
    CONSTRAINT instrument_fact_revision_chain_ck CHECK (
        (revision = 1 AND supersedes_revision_id IS NULL) OR
        (revision > 1 AND supersedes_revision_id IS NOT NULL)
    ),
    CONSTRAINT instrument_fact_no_self_ck CHECK (supersedes_revision_id IS NULL OR supersedes_revision_id <> fact_revision_id),
    CONSTRAINT instrument_fact_temporal_ck CHECK (
        known_at >= recorded_at AND decision_visible_at = known_at
    )
);
CREATE INDEX instrument_fact_current_asof_idx ON mra.instrument_fact_revision (
    provider_product_id, instrument_id, fact_kind, evidence_scope,
    event_start, decision_visible_at DESC, revision DESC, fact_revision_id
);
CREATE INDEX instrument_fact_capture_idx ON mra.instrument_fact_revision (
    capture_id, provider_product_id
);
CREATE INDEX instrument_fact_instrument_idx ON mra.instrument_fact_revision (instrument_id, fact_kind, event_end DESC);
CREATE INDEX instrument_fact_session_idx ON mra.instrument_fact_revision (session_id, instrument_id, fact_kind)
    WHERE session_id IS NOT NULL;
CREATE INDEX instrument_fact_supersedes_idx ON mra.instrument_fact_revision (supersedes_revision_id)
    WHERE supersedes_revision_id IS NOT NULL;

CREATE TABLE mra.corporate_action_revision (
    corporate_action_revision_id uuid PRIMARY KEY,
    provider_product_id uuid NOT NULL REFERENCES mra.provider_product(provider_product_id) ON DELETE RESTRICT,
    capture_id uuid NOT NULL REFERENCES mra.data_capture(capture_id) ON DELETE RESTRICT,
    instrument_id uuid NOT NULL REFERENCES mra.instrument(instrument_id) ON DELETE RESTRICT,
    action_key text NOT NULL,
    action_type text NOT NULL,
    ex_session_id uuid NOT NULL REFERENCES mra.trading_session(session_id) ON DELETE RESTRICT,
    record_session_id uuid REFERENCES mra.trading_session(session_id) ON DELETE RESTRICT,
    pay_session_id uuid REFERENCES mra.trading_session(session_id) ON DELETE RESTRICT,
    successor_instrument_id uuid REFERENCES mra.instrument(instrument_id) ON DELETE RESTRICT,
    cash_amount_per_share numeric,
    ratio_factor numeric,
    subscription_price numeric,
    currency text,
    revision integer NOT NULL,
    supersedes_revision_id uuid REFERENCES mra.corporate_action_revision(corporate_action_revision_id) ON DELETE RESTRICT,
    recorded_at timestamptz NOT NULL,
    known_at timestamptz NOT NULL,
    decision_visible_at timestamptz NOT NULL,
    CONSTRAINT corporate_action_capture_product_fk FOREIGN KEY (
        capture_id, provider_product_id
    ) REFERENCES mra.data_capture(capture_id, provider_product_id) ON DELETE RESTRICT,
    CONSTRAINT corporate_action_identity_uk UNIQUE (provider_product_id, instrument_id, action_key, revision),
    CONSTRAINT corporate_action_key_ck CHECK (action_key <> ''),
    CONSTRAINT corporate_action_type_ck CHECK (action_type IN (
        'CASH_DIVIDEND', 'STOCK_DIVIDEND', 'SPLIT', 'RIGHTS_ISSUE',
        'CONVERSION', 'MERGER'
    )),
    CONSTRAINT corporate_action_successor_ck CHECK (
        (action_type IN ('CONVERSION', 'MERGER')
         AND successor_instrument_id IS NOT NULL
         AND successor_instrument_id <> instrument_id)
        OR
        (action_type NOT IN ('CONVERSION', 'MERGER')
         AND successor_instrument_id IS NULL)
    ),
    CONSTRAINT corporate_action_value_ck CHECK (
        (action_type = 'CASH_DIVIDEND'
         AND cash_amount_per_share >= 0
         AND scale(cash_amount_per_share) <= 10
         AND abs(cash_amount_per_share) < 1e20
         AND ratio_factor IS NULL
         AND subscription_price IS NULL
         AND currency ~ '^[A-Z]{3}$')
        OR
        (action_type IN ('STOCK_DIVIDEND', 'SPLIT')
         AND cash_amount_per_share IS NULL
         AND ratio_factor > 0
         AND scale(ratio_factor) <= 12
         AND abs(ratio_factor) < 1e18
         AND subscription_price IS NULL
         AND currency IS NULL)
        OR
        (action_type IN ('CONVERSION', 'MERGER')
         AND cash_amount_per_share IS NULL
         AND ratio_factor > 0
         AND scale(ratio_factor) <= 12
         AND abs(ratio_factor) < 1e18
         AND subscription_price IS NULL
         AND currency IS NULL)
        OR
        (action_type = 'RIGHTS_ISSUE'
         AND cash_amount_per_share IS NULL
         AND ratio_factor > 0
         AND scale(ratio_factor) <= 12
         AND abs(ratio_factor) < 1e18
         AND subscription_price > 0
         AND scale(subscription_price) <= 10
         AND abs(subscription_price) < 1e20
         AND currency ~ '^[A-Z]{3}$')
    ),
    CONSTRAINT corporate_action_revision_ck CHECK (revision > 0),
    CONSTRAINT corporate_action_revision_chain_ck CHECK (
        (revision = 1 AND supersedes_revision_id IS NULL) OR
        (revision > 1 AND supersedes_revision_id IS NOT NULL)
    ),
    CONSTRAINT corporate_action_no_self_ck CHECK (supersedes_revision_id IS NULL OR supersedes_revision_id <> corporate_action_revision_id),
    CONSTRAINT corporate_action_temporal_ck CHECK (
        known_at >= recorded_at AND decision_visible_at = known_at
    )
);
CREATE INDEX corporate_action_exact_asof_idx
    ON mra.corporate_action_revision (
        provider_product_id, instrument_id, ex_session_id, action_key,
        decision_visible_at DESC, revision DESC, capture_id
    );
CREATE INDEX corporate_action_capture_idx ON mra.corporate_action_revision (
    capture_id, provider_product_id
);
CREATE INDEX corporate_action_instrument_idx ON mra.corporate_action_revision (instrument_id, ex_session_id, action_key);
CREATE INDEX corporate_action_session_idx ON mra.corporate_action_revision (ex_session_id, instrument_id);
CREATE INDEX corporate_action_record_session_idx
    ON mra.corporate_action_revision (record_session_id, instrument_id)
    WHERE record_session_id IS NOT NULL;
CREATE INDEX corporate_action_pay_session_idx
    ON mra.corporate_action_revision (pay_session_id, instrument_id)
    WHERE pay_session_id IS NOT NULL;
CREATE INDEX corporate_action_successor_instrument_idx
    ON mra.corporate_action_revision (successor_instrument_id, ex_session_id)
    WHERE successor_instrument_id IS NOT NULL;
CREATE INDEX corporate_action_supersedes_idx ON mra.corporate_action_revision (supersedes_revision_id)
    WHERE supersedes_revision_id IS NOT NULL;

CREATE TABLE mra.source_gap (
    gap_id uuid PRIMARY KEY,
    provider_product_id uuid NOT NULL REFERENCES mra.provider_product(provider_product_id) ON DELETE RESTRICT,
    capture_id uuid NOT NULL REFERENCES mra.data_capture(capture_id) ON DELETE RESTRICT,
    instrument_id uuid REFERENCES mra.instrument(instrument_id) ON DELETE RESTRICT,
    session_id uuid REFERENCES mra.trading_session(session_id) ON DELETE RESTRICT,
    instrument_code text,
    identifier_scheme text,
    identifier_value text,
    exchange text,
    session_date date,
    classification_scheme text,
    classification_code text,
    action_key text,
    gap_kind text NOT NULL,
    reason_code text NOT NULL,
    fact_kind text NOT NULL,
    instrument_fact_kind text,
    evidence_scope text,
    timeframe text,
    price_basis text,
    event_start timestamptz,
    event_end timestamptz,
    effective_from timestamptz,
    effective_to timestamptz,
    detail text,
    recorded_at timestamptz NOT NULL,
    known_at timestamptz NOT NULL,
    decision_visible_at timestamptz NOT NULL,
    CONSTRAINT source_gap_capture_product_fk FOREIGN KEY (
        capture_id, provider_product_id
    ) REFERENCES mra.data_capture(capture_id, provider_product_id) ON DELETE RESTRICT,
    CONSTRAINT source_gap_identity_uk UNIQUE NULLS NOT DISTINCT (
        capture_id, fact_kind, instrument_id, session_id,
        instrument_code, identifier_scheme, identifier_value,
        exchange, session_date, classification_scheme,
        classification_code, action_key,
        instrument_fact_kind, evidence_scope, timeframe, price_basis,
        event_start, event_end, effective_from, effective_to
    ),
    CONSTRAINT source_gap_kind_ck CHECK (gap_kind IN ('MISSING', 'PLACEHOLDER', 'PROVIDER_FAILURE', 'CONFLICT', 'INVALID_OHLC')),
    CONSTRAINT source_gap_reason_ck CHECK (reason_code IN (
        'PROVIDER_FAILURE', 'NO_ROWS_RETURNED',
        'EXPECTED_OBSERVATION_MISSING', 'EXACT_BAR_MISSING',
        'NULL_OHLC_PLACEHOLDER', 'CONFLICTING_SOURCE_REVISIONS',
        'INVALID_OHLC'
    )),
    CONSTRAINT source_gap_reason_kind_ck CHECK (
        (gap_kind = 'MISSING' AND reason_code IN (
            'NO_ROWS_RETURNED', 'EXPECTED_OBSERVATION_MISSING',
            'EXACT_BAR_MISSING'
        )) OR
        (gap_kind = 'PLACEHOLDER' AND reason_code = 'NULL_OHLC_PLACEHOLDER') OR
        (gap_kind = 'PROVIDER_FAILURE' AND reason_code = 'PROVIDER_FAILURE') OR
        (gap_kind = 'CONFLICT' AND reason_code = 'CONFLICTING_SOURCE_REVISIONS') OR
        (gap_kind = 'INVALID_OHLC' AND reason_code = 'INVALID_OHLC')
    ),
    CONSTRAINT source_gap_reason_fact_ck CHECK (
        reason_code NOT IN (
            'EXACT_BAR_MISSING', 'NULL_OHLC_PLACEHOLDER', 'INVALID_OHLC'
        ) OR fact_kind = 'MARKET_BAR'
    ),
    CONSTRAINT source_gap_fact_kind_ck CHECK (fact_kind IN (
        'DATA_CAPTURE', 'INSTRUMENT',
        'INSTRUMENT_IDENTIFIER', 'TRADING_SESSION', 'CLASSIFICATION',
        'CLASSIFICATION_MEMBERSHIP', 'MARKET_BAR', 'INSTRUMENT_FACT',
        'CORPORATE_ACTION'
    )),
    CONSTRAINT source_gap_instrument_code_ck CHECK (
        instrument_code IS NULL OR instrument_code ~ '^[A-Z0-9][A-Z0-9._-]{0,31}$'
    ),
    CONSTRAINT source_gap_identifier_scheme_ck CHECK (
        identifier_scheme IS NULL OR identifier_scheme ~ '^[A-Z][A-Z0-9_]{0,31}$'
    ),
    CONSTRAINT source_gap_identifier_value_ck CHECK (
        identifier_value IS NULL OR identifier_value <> ''
    ),
    CONSTRAINT source_gap_exchange_ck CHECK (
        exchange IS NULL OR exchange ~ '^[A-Z][A-Z0-9]{1,15}$'
    ),
    CONSTRAINT source_gap_classification_scheme_ck CHECK (
        classification_scheme IS NULL OR
        classification_scheme ~ '^[A-Z][A-Z0-9_]{0,31}$'
    ),
    CONSTRAINT source_gap_classification_code_ck CHECK (
        classification_code IS NULL OR classification_code <> ''
    ),
    CONSTRAINT source_gap_action_key_ck CHECK (
        action_key IS NULL OR action_key <> ''
    ),
    CONSTRAINT source_gap_instrument_fact_kind_ck CHECK (
        (fact_kind = 'INSTRUMENT_FACT' AND instrument_fact_kind IN (
            'SECURITY_STATUS', 'LISTING_STATUS',
            'SPECIAL_TREATMENT_STATUS', 'TOTAL_SHARES', 'FREE_FLOAT_SHARES',
            'LIMIT_UP_PRICE', 'LIMIT_DOWN_PRICE', 'REFERENCE_PRICE'
        )) OR
        (fact_kind <> 'INSTRUMENT_FACT' AND instrument_fact_kind IS NULL)
    ),
    CONSTRAINT source_gap_evidence_scope_ck CHECK (
        (fact_kind = 'INSTRUMENT_FACT' AND evidence_scope IN (
            'DECISION_SESSION', 'PRIOR_SESSION', 'EFFECTIVE_INTERVAL'
        )) OR
        (fact_kind <> 'INSTRUMENT_FACT' AND evidence_scope IS NULL)
    ),
    CONSTRAINT source_gap_bar_scope_ck CHECK (
        (fact_kind <> 'MARKET_BAR' AND timeframe IS NULL AND price_basis IS NULL) OR
        (fact_kind = 'MARKET_BAR'
         AND instrument_id IS NOT NULL
         AND session_id IS NOT NULL
         AND event_start IS NOT NULL
         AND event_end IS NOT NULL
         AND timeframe IN ('MINUTE_1', 'MINUTE_5', 'MINUTE_15', 'MINUTE_30', 'MINUTE_60', 'DAILY')
         AND price_basis IN ('RAW_UNADJUSTED', 'FORWARD_ADJUSTED', 'BACKWARD_ADJUSTED'))
    ),
    CONSTRAINT source_gap_exact_scope_ck CHECK (
        (fact_kind = 'DATA_CAPTURE'
         AND instrument_id IS NULL AND session_id IS NULL
         AND instrument_code IS NULL
         AND identifier_scheme IS NULL AND identifier_value IS NULL
         AND exchange IS NULL AND session_date IS NULL
         AND classification_scheme IS NULL AND classification_code IS NULL
         AND action_key IS NULL
         AND instrument_fact_kind IS NULL
         AND evidence_scope IS NULL
         AND timeframe IS NULL AND price_basis IS NULL
         AND event_start IS NULL AND event_end IS NULL
         AND effective_from IS NULL AND effective_to IS NULL)
        OR
        (fact_kind = 'INSTRUMENT'
         AND instrument_code IS NOT NULL
         AND instrument_id IS NULL AND session_id IS NULL
         AND identifier_scheme IS NULL AND identifier_value IS NULL
         AND exchange IS NULL AND session_date IS NULL
         AND classification_scheme IS NULL AND classification_code IS NULL
         AND action_key IS NULL
         AND evidence_scope IS NULL
         AND event_start IS NULL AND event_end IS NULL
         AND effective_from IS NULL AND effective_to IS NULL)
        OR
        (fact_kind = 'INSTRUMENT_IDENTIFIER'
         AND identifier_scheme IS NOT NULL AND identifier_value IS NOT NULL
         AND session_id IS NULL AND instrument_code IS NULL
         AND exchange IS NULL AND session_date IS NULL
         AND classification_scheme IS NULL AND classification_code IS NULL
         AND action_key IS NULL
         AND evidence_scope IS NULL
         AND event_start IS NULL AND event_end IS NULL
         AND effective_from IS NOT NULL)
        OR
        (fact_kind = 'TRADING_SESSION'
         AND exchange IS NOT NULL AND session_date IS NOT NULL
         AND instrument_id IS NULL AND session_id IS NULL
         AND instrument_code IS NULL
         AND identifier_scheme IS NULL AND identifier_value IS NULL
         AND classification_scheme IS NULL AND classification_code IS NULL
         AND action_key IS NULL
         AND evidence_scope IS NULL
         AND event_start IS NULL AND event_end IS NULL
         AND effective_from IS NULL AND effective_to IS NULL)
        OR
        (fact_kind = 'CLASSIFICATION'
         AND classification_scheme IS NOT NULL
         AND classification_code IS NOT NULL
         AND instrument_id IS NULL AND session_id IS NULL
         AND instrument_code IS NULL
         AND identifier_scheme IS NULL AND identifier_value IS NULL
         AND exchange IS NULL AND session_date IS NULL
         AND action_key IS NULL
         AND evidence_scope IS NULL
         AND event_start IS NULL AND event_end IS NULL
         AND effective_from IS NOT NULL)
        OR
        (fact_kind = 'CLASSIFICATION_MEMBERSHIP'
         AND classification_scheme IS NOT NULL
         AND classification_code IS NOT NULL
         AND instrument_id IS NOT NULL AND session_id IS NULL
         AND instrument_code IS NULL
         AND identifier_scheme IS NULL AND identifier_value IS NULL
         AND exchange IS NULL AND session_date IS NULL
         AND action_key IS NULL
         AND evidence_scope IS NULL
         AND event_start IS NULL AND event_end IS NULL
         AND effective_from IS NOT NULL)
        OR
        (fact_kind = 'MARKET_BAR'
         AND instrument_id IS NOT NULL AND session_id IS NOT NULL
         AND instrument_code IS NULL
         AND identifier_scheme IS NULL AND identifier_value IS NULL
         AND exchange IS NULL AND session_date IS NULL
         AND classification_scheme IS NULL AND classification_code IS NULL
         AND action_key IS NULL
         AND instrument_fact_kind IS NULL
         AND evidence_scope IS NULL
         AND event_start IS NOT NULL AND event_end IS NOT NULL
         AND effective_from IS NULL AND effective_to IS NULL)
        OR
        (fact_kind = 'INSTRUMENT_FACT'
         AND instrument_id IS NOT NULL AND instrument_fact_kind IS NOT NULL
         AND instrument_code IS NULL
         AND identifier_scheme IS NULL AND identifier_value IS NULL
         AND exchange IS NULL AND session_date IS NULL
         AND classification_scheme IS NULL AND classification_code IS NULL
         AND action_key IS NULL
         AND (
             (instrument_fact_kind IN (
                 'SECURITY_STATUS', 'LIMIT_UP_PRICE',
                 'LIMIT_DOWN_PRICE', 'REFERENCE_PRICE'
              )
              AND session_id IS NOT NULL
              AND evidence_scope IN ('DECISION_SESSION', 'PRIOR_SESSION')
              AND event_start IS NOT NULL AND event_end IS NOT NULL
              AND effective_from IS NULL AND effective_to IS NULL)
             OR
             (instrument_fact_kind IN (
                 'LISTING_STATUS', 'SPECIAL_TREATMENT_STATUS',
                 'TOTAL_SHARES', 'FREE_FLOAT_SHARES'
              )
              AND session_id IS NULL
              AND evidence_scope = 'EFFECTIVE_INTERVAL'
              AND event_start IS NULL AND event_end IS NULL
              AND effective_from IS NOT NULL)
         ))
        OR
        (fact_kind = 'CORPORATE_ACTION'
         AND instrument_id IS NOT NULL AND session_id IS NOT NULL
         AND action_key IS NOT NULL
         AND instrument_code IS NULL
         AND identifier_scheme IS NULL AND identifier_value IS NULL
         AND exchange IS NULL AND session_date IS NULL
         AND classification_scheme IS NULL AND classification_code IS NULL
         AND instrument_fact_kind IS NULL
         AND evidence_scope IS NULL
         AND event_start IS NULL AND event_end IS NULL
         AND effective_from IS NULL AND effective_to IS NULL)
    ),
    CONSTRAINT source_gap_interval_ck CHECK (
        (event_start IS NULL AND event_end IS NULL) OR
        (event_start IS NOT NULL AND event_end > event_start)
    ),
    CONSTRAINT source_gap_effective_interval_ck CHECK (
        (effective_from IS NULL AND effective_to IS NULL) OR
        (effective_from IS NOT NULL
         AND (effective_to IS NULL OR effective_to > effective_from))
    ),
    CONSTRAINT source_gap_temporal_ck CHECK (
        known_at >= recorded_at
        AND (fact_kind <> 'MARKET_BAR' OR known_at >= event_end)
        AND decision_visible_at = known_at
    )
);
CREATE INDEX source_gap_exact_asof_idx ON mra.source_gap (
    provider_product_id, instrument_id, session_id, fact_kind,
    instrument_fact_kind, evidence_scope, timeframe, price_basis,
    event_start, event_end, effective_from, effective_to,
    decision_visible_at DESC, capture_id
);
CREATE INDEX source_gap_capture_idx ON mra.source_gap (
    capture_id, provider_product_id
);
CREATE INDEX source_gap_instrument_idx ON mra.source_gap (instrument_id, fact_kind, event_end DESC)
    WHERE instrument_id IS NOT NULL;
CREATE INDEX source_gap_session_idx ON mra.source_gap (session_id, instrument_id, fact_kind)
    WHERE session_id IS NOT NULL;
CREATE INDEX source_gap_session_calendar_idx ON mra.source_gap (
    provider_product_id, exchange, session_date, decision_visible_at DESC
) WHERE fact_kind = 'TRADING_SESSION';
CREATE INDEX source_gap_classification_idx ON mra.source_gap (
    provider_product_id, classification_scheme, classification_code,
    decision_visible_at DESC
) WHERE fact_kind IN ('CLASSIFICATION', 'CLASSIFICATION_MEMBERSHIP');

CREATE TABLE mra.universe (
    universe_id uuid PRIMARY KEY,
    universe_code text NOT NULL UNIQUE,
    purpose text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT universe_code_ck CHECK (
        universe_code ~ '^[a-z][a-z0-9_-]{0,99}$'
    ),
    CONSTRAINT universe_purpose_ck CHECK (purpose <> '')
);

CREATE TABLE mra.universe_revision (
    universe_revision_id uuid PRIMARY KEY,
    universe_id uuid NOT NULL REFERENCES mra.universe(universe_id) ON DELETE RESTRICT,
    revision integer NOT NULL,
    decision_time timestamptz NOT NULL,
    scope_artifact_id uuid NOT NULL,
    scope_content_sha256 text NOT NULL,
    scope_size_bytes bigint NOT NULL,
    market_provider_product_id uuid NOT NULL
        REFERENCES mra.provider_product(provider_product_id) ON DELETE RESTRICT,
    classification_scheme text NOT NULL,
    classification_code text NOT NULL,
    total_count integer NOT NULL,
    included_count integer NOT NULL,
    excluded_count integer NOT NULL,
    unknown_count integer NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT universe_revision_number_uk UNIQUE (universe_id, revision),
    CONSTRAINT universe_revision_decision_join_uk UNIQUE (
        universe_revision_id, decision_time
    ),
    CONSTRAINT universe_revision_scope_uk UNIQUE (
        universe_id, decision_time, scope_content_sha256
    ),
    CONSTRAINT universe_revision_artifact_fk FOREIGN KEY (
        scope_artifact_id, scope_content_sha256, scope_size_bytes
    ) REFERENCES mra.artifact(
        artifact_id, content_sha256, size_bytes
    ) ON DELETE RESTRICT,
    CONSTRAINT universe_revision_revision_ck CHECK (revision > 0),
    CONSTRAINT universe_revision_hash_ck CHECK (
        scope_content_sha256 ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT universe_revision_size_ck CHECK (scope_size_bytes >= 0),
    CONSTRAINT universe_revision_classification_scheme_ck CHECK (
        classification_scheme ~ '^[A-Z][A-Z0-9_]{0,31}$'
    ),
    CONSTRAINT universe_revision_classification_code_ck CHECK (
        classification_code <> ''
    ),
    CONSTRAINT universe_revision_counts_ck CHECK (
        total_count >= 0
        AND included_count >= 0
        AND excluded_count >= 0
        AND unknown_count >= 0
        AND total_count = included_count + excluded_count + unknown_count
    )
);
CREATE INDEX universe_revision_decision_idx
    ON mra.universe_revision (universe_id, decision_time DESC, revision DESC);
CREATE INDEX universe_revision_scope_artifact_idx
    ON mra.universe_revision (
        scope_artifact_id, scope_content_sha256, scope_size_bytes
    );
CREATE INDEX universe_revision_provider_product_idx
    ON mra.universe_revision (market_provider_product_id);

CREATE TABLE mra.universe_member (
    universe_member_id uuid PRIMARY KEY,
    universe_revision_id uuid NOT NULL
        REFERENCES mra.universe_revision(universe_revision_id) ON DELETE RESTRICT,
    instrument_id uuid NOT NULL REFERENCES mra.instrument(instrument_id) ON DELETE RESTRICT,
    membership_status text NOT NULL,
    evidence_status text NOT NULL,
    observed_membership_status text,
    classification_id uuid REFERENCES mra.classification(classification_id) ON DELETE RESTRICT,
    classification_membership_revision_id uuid
        REFERENCES mra.classification_membership_revision(membership_revision_id)
        ON DELETE RESTRICT,
    source_gap_id uuid REFERENCES mra.source_gap(gap_id) ON DELETE RESTRICT,
    market_capture_id uuid REFERENCES mra.data_capture(capture_id) ON DELETE RESTRICT,
    market_decision_visible_at timestamptz,
    reason_code text NOT NULL,
    lineage_hash text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT universe_member_identity_uk UNIQUE (
        universe_revision_id, instrument_id
    ),
    CONSTRAINT universe_member_join_uk UNIQUE (
        universe_member_id, universe_revision_id, instrument_id
    ),
    CONSTRAINT universe_member_population_join_uk UNIQUE (
        universe_member_id, universe_revision_id, instrument_id,
        membership_status
    ),
    CONSTRAINT universe_member_status_ck CHECK (
        membership_status IN ('INCLUDED', 'EXCLUDED', 'UNKNOWN')
    ),
    CONSTRAINT universe_member_evidence_status_ck CHECK (
        evidence_status IN ('AVAILABLE', 'MISSING', 'STALE', 'GAP', 'CONFLICT')
    ),
    CONSTRAINT universe_member_observed_status_ck CHECK (
        observed_membership_status IS NULL
        OR observed_membership_status IN ('MEMBER', 'NOT_MEMBER')
    ),
    CONSTRAINT universe_member_reason_ck CHECK (
        reason_code IN (
            'CLASSIFICATION_MEMBER', 'CLASSIFICATION_NOT_MEMBER',
            'MARKET_EVIDENCE_MISSING', 'MARKET_EVIDENCE_STALE',
            'MARKET_EVIDENCE_GAP', 'MARKET_EVIDENCE_CONFLICT'
        )
    ),
    CONSTRAINT universe_member_lineage_hash_ck CHECK (
        lineage_hash ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT universe_member_disposition_ck CHECK (
        (
            evidence_status = 'AVAILABLE'
            AND classification_id IS NOT NULL
            AND classification_membership_revision_id IS NOT NULL
            AND source_gap_id IS NULL
            AND market_capture_id IS NOT NULL
            AND market_decision_visible_at IS NOT NULL
            AND (
                (membership_status = 'INCLUDED'
                 AND observed_membership_status = 'MEMBER'
                 AND reason_code = 'CLASSIFICATION_MEMBER')
                OR
                (membership_status = 'EXCLUDED'
                 AND observed_membership_status = 'NOT_MEMBER'
                 AND reason_code = 'CLASSIFICATION_NOT_MEMBER')
            )
        )
        OR
        (
            membership_status = 'UNKNOWN'
            AND evidence_status <> 'AVAILABLE'
            AND reason_code IN (
                'MARKET_EVIDENCE_MISSING', 'MARKET_EVIDENCE_STALE',
                'MARKET_EVIDENCE_GAP', 'MARKET_EVIDENCE_CONFLICT'
            )
        )
    )
);
CREATE INDEX universe_member_status_idx
    ON mra.universe_member (universe_revision_id, membership_status, instrument_id);
CREATE INDEX universe_member_instrument_idx
    ON mra.universe_member (instrument_id, universe_revision_id);
CREATE INDEX universe_member_membership_lineage_idx
    ON mra.universe_member (classification_membership_revision_id)
    WHERE classification_membership_revision_id IS NOT NULL;
CREATE INDEX universe_member_gap_lineage_idx
    ON mra.universe_member (source_gap_id)
    WHERE source_gap_id IS NOT NULL;
CREATE INDEX universe_member_classification_lineage_idx
    ON mra.universe_member (classification_id)
    WHERE classification_id IS NOT NULL;
CREATE INDEX universe_member_capture_lineage_idx
    ON mra.universe_member (market_capture_id)
    WHERE market_capture_id IS NOT NULL;

CREATE TABLE mra.eligibility_policy (
    eligibility_policy_id uuid PRIMARY KEY,
    market_provider_product_id uuid NOT NULL
        REFERENCES mra.provider_product(provider_product_id) ON DELETE RESTRICT,
    policy_code text NOT NULL,
    version integer NOT NULL,
    content_sha256 text NOT NULL UNIQUE,
    rule_count integer NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT eligibility_policy_identity_uk UNIQUE (policy_code, version),
    CONSTRAINT eligibility_policy_code_ck CHECK (
        policy_code ~ '^[a-z][a-z0-9_-]{0,99}$'
    ),
    CONSTRAINT eligibility_policy_version_ck CHECK (version > 0),
    CONSTRAINT eligibility_policy_hash_ck CHECK (
        content_sha256 ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT eligibility_policy_rule_count_ck CHECK (rule_count > 0)
);

CREATE TABLE mra.eligibility_rule (
    eligibility_rule_id uuid PRIMARY KEY,
    eligibility_policy_id uuid NOT NULL
        REFERENCES mra.eligibility_policy(eligibility_policy_id) ON DELETE RESTRICT,
    rule_code text NOT NULL,
    ordinal integer NOT NULL,
    rule_kind text NOT NULL,
    measure_code text NOT NULL,
    aggregation text NOT NULL,
    window_value integer NOT NULL,
    window_unit text NOT NULL,
    value_kind text NOT NULL,
    operator text NOT NULL,
    threshold_decimal numeric,
    threshold_status text,
    threshold_count integer,
    value_unit text NOT NULL,
    missing_result text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT eligibility_rule_code_uk UNIQUE (
        eligibility_policy_id, rule_code
    ),
    CONSTRAINT eligibility_rule_ordinal_uk UNIQUE (
        eligibility_policy_id, ordinal
    ),
    CONSTRAINT eligibility_rule_policy_join_uk UNIQUE (
        eligibility_policy_id, eligibility_rule_id
    ),
    CONSTRAINT eligibility_rule_code_ck CHECK (
        rule_code ~ '^[A-Z][A-Z0-9_]{0,99}$'
    ),
    CONSTRAINT eligibility_rule_ordinal_ck CHECK (ordinal > 0),
    CONSTRAINT eligibility_rule_kind_ck CHECK (
        rule_kind IN (
            'NOT_SUSPENDED', 'NOT_SPECIAL_TREATMENT', 'MIN_LISTING_AGE',
            'MIN_LIQUIDITY', 'LIMIT_METADATA_PRESENT'
        )
    ),
    CONSTRAINT eligibility_rule_measure_ck CHECK (
        measure_code IN (
            'SECURITY_STATUS', 'SPECIAL_TREATMENT_STATUS', 'LISTING_AGE',
            'TURNOVER_VALUE', 'LIMIT_PRICE_FACT_COUNT'
        )
    ),
    CONSTRAINT eligibility_rule_aggregation_ck CHECK (
        aggregation IN ('POINT', 'ELAPSED', 'MEAN', 'COUNT')
    ),
    CONSTRAINT eligibility_rule_window_ck CHECK (
        window_value >= 0
        AND window_unit IN ('NONE', 'SESSION')
    ),
    CONSTRAINT eligibility_rule_value_kind_ck CHECK (
        value_kind IN ('STATUS', 'DECIMAL', 'COUNT')
    ),
    CONSTRAINT eligibility_rule_operator_ck CHECK (
        operator IN ('EQ', 'GTE')
    ),
    CONSTRAINT eligibility_rule_decimal_ck CHECK (
        threshold_decimal IS NULL
        OR (scale(threshold_decimal) <= 10 AND abs(threshold_decimal) < 1e20)
    ),
    CONSTRAINT eligibility_rule_count_ck CHECK (
        threshold_count IS NULL OR threshold_count >= 0
    ),
    CONSTRAINT eligibility_rule_unit_ck CHECK (
        value_unit ~ '^[A-Z][A-Z0-9_]{0,31}$'
    ),
    CONSTRAINT eligibility_rule_missing_ck CHECK (missing_result = 'UNKNOWN'),
    CONSTRAINT eligibility_rule_shape_ck CHECK (
        (rule_kind = 'NOT_SUSPENDED'
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
    )
);
CREATE INDEX eligibility_policy_provider_product_idx
    ON mra.eligibility_policy (market_provider_product_id);

CREATE TABLE mra.eligibility_assessment (
    eligibility_assessment_id uuid PRIMARY KEY,
    universe_revision_id uuid NOT NULL
        REFERENCES mra.universe_revision(universe_revision_id) ON DELETE RESTRICT,
    universe_member_id uuid NOT NULL,
    eligibility_policy_id uuid NOT NULL
        REFERENCES mra.eligibility_policy(eligibility_policy_id) ON DELETE RESTRICT,
    instrument_id uuid NOT NULL REFERENCES mra.instrument(instrument_id) ON DELETE RESTRICT,
    decision_time timestamptz NOT NULL,
    result text NOT NULL,
    rule_count integer NOT NULL,
    pass_count integer NOT NULL,
    fail_count integer NOT NULL,
    unknown_count integer NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT eligibility_assessment_identity_uk UNIQUE (
        universe_revision_id, eligibility_policy_id, instrument_id, decision_time
    ),
    CONSTRAINT eligibility_assessment_population_join_uk UNIQUE (
        eligibility_assessment_id, universe_member_id, universe_revision_id,
        eligibility_policy_id, instrument_id, decision_time, result
    ),
    CONSTRAINT eligibility_assessment_member_fk FOREIGN KEY (
        universe_member_id, universe_revision_id, instrument_id
    ) REFERENCES mra.universe_member(
        universe_member_id, universe_revision_id, instrument_id
    ) ON DELETE RESTRICT,
    CONSTRAINT eligibility_assessment_result_ck CHECK (
        result IN ('ELIGIBLE', 'INELIGIBLE', 'UNKNOWN')
    ),
    CONSTRAINT eligibility_assessment_counts_ck CHECK (
        rule_count > 0
        AND pass_count >= 0 AND fail_count >= 0 AND unknown_count >= 0
        AND rule_count = pass_count + fail_count + unknown_count
    ),
    CONSTRAINT eligibility_assessment_aggregate_ck CHECK (
        (result = 'INELIGIBLE' AND fail_count > 0)
        OR
        (result = 'UNKNOWN' AND fail_count = 0 AND unknown_count > 0)
        OR
        (result = 'ELIGIBLE'
         AND pass_count = rule_count AND fail_count = 0 AND unknown_count = 0)
    )
);
CREATE INDEX eligibility_assessment_result_idx
    ON mra.eligibility_assessment (
        universe_revision_id, eligibility_policy_id, result, instrument_id
    );
CREATE INDEX eligibility_assessment_instrument_idx
    ON mra.eligibility_assessment (instrument_id, decision_time DESC);
CREATE INDEX eligibility_assessment_policy_idx
    ON mra.eligibility_assessment (eligibility_policy_id, decision_time DESC);
CREATE INDEX eligibility_assessment_member_idx
    ON mra.eligibility_assessment (
        universe_member_id, universe_revision_id, instrument_id
    );

CREATE TABLE mra.eligibility_reason (
    eligibility_reason_id uuid PRIMARY KEY,
    eligibility_assessment_id uuid NOT NULL
        REFERENCES mra.eligibility_assessment(eligibility_assessment_id)
        ON DELETE RESTRICT,
    eligibility_policy_id uuid NOT NULL,
    eligibility_rule_id uuid NOT NULL,
    criterion_result text NOT NULL,
    observed_value_kind text NOT NULL,
    observed_decimal numeric,
    observed_status text,
    observed_count integer,
    measure_code text NOT NULL,
    aggregation text NOT NULL,
    window_value integer NOT NULL,
    window_unit text NOT NULL,
    operator text NOT NULL,
    threshold_decimal numeric,
    threshold_status text,
    threshold_count integer,
    value_unit text NOT NULL,
    reason_code text NOT NULL,
    market_fact_revision_ids uuid[] NOT NULL DEFAULT '{}',
    market_bar_revision_ids uuid[] NOT NULL DEFAULT '{}',
    market_gap_ids uuid[] NOT NULL DEFAULT '{}',
    market_session_ids uuid[] NOT NULL DEFAULT '{}',
    market_capture_ids uuid[] NOT NULL DEFAULT '{}',
    lineage_hash text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT eligibility_reason_identity_uk UNIQUE (
        eligibility_assessment_id, eligibility_rule_id
    ),
    CONSTRAINT eligibility_reason_rule_fk FOREIGN KEY (
        eligibility_policy_id, eligibility_rule_id
    ) REFERENCES mra.eligibility_rule(
        eligibility_policy_id, eligibility_rule_id
    ) ON DELETE RESTRICT,
    CONSTRAINT eligibility_reason_result_ck CHECK (
        criterion_result IN ('PASS', 'FAIL', 'UNKNOWN')
    ),
    CONSTRAINT eligibility_reason_observed_kind_ck CHECK (
        observed_value_kind IN ('STATUS', 'DECIMAL', 'COUNT', 'MISSING')
    ),
    CONSTRAINT eligibility_reason_observed_ck CHECK (
        (observed_value_kind = 'STATUS'
         AND observed_status IS NOT NULL
         AND observed_decimal IS NULL AND observed_count IS NULL)
        OR
        (observed_value_kind = 'DECIMAL'
         AND observed_decimal IS NOT NULL
         AND observed_status IS NULL AND observed_count IS NULL)
        OR
        (observed_value_kind = 'COUNT'
         AND observed_count IS NOT NULL
         AND observed_status IS NULL AND observed_decimal IS NULL)
        OR
        (observed_value_kind = 'MISSING'
         AND observed_status IS NULL
         AND observed_decimal IS NULL AND observed_count IS NULL)
    ),
    CONSTRAINT eligibility_reason_explicit_result_ck CHECK (
        criterion_result = 'UNKNOWN' OR observed_value_kind <> 'MISSING'
    ),
    CONSTRAINT eligibility_reason_numeric_ck CHECK (
        (observed_decimal IS NULL
         OR (scale(observed_decimal) <= 10 AND abs(observed_decimal) < 1e20))
        AND
        (threshold_decimal IS NULL
         OR (scale(threshold_decimal) <= 10 AND abs(threshold_decimal) < 1e20))
    ),
    CONSTRAINT eligibility_reason_count_ck CHECK (
        (observed_count IS NULL OR observed_count >= 0)
        AND (threshold_count IS NULL OR threshold_count >= 0)
        AND window_value >= 0
    ),
    CONSTRAINT eligibility_reason_reason_ck CHECK (
        reason_code IN (
            'CRITERION_PASSED', 'EXPLICIT_CRITERION_FAILED',
            'EVIDENCE_MISSING', 'EVIDENCE_STALE', 'EVIDENCE_GAP',
            'EVIDENCE_CONFLICT', 'EVIDENCE_UNKNOWN_STATUS'
        )
        AND (
            (criterion_result = 'PASS' AND reason_code = 'CRITERION_PASSED')
            OR
            (criterion_result = 'FAIL'
             AND reason_code = 'EXPLICIT_CRITERION_FAILED')
            OR
            (criterion_result = 'UNKNOWN'
             AND reason_code IN (
                 'EVIDENCE_MISSING', 'EVIDENCE_STALE', 'EVIDENCE_GAP',
                 'EVIDENCE_CONFLICT', 'EVIDENCE_UNKNOWN_STATUS'
             ))
        )
    ),
    CONSTRAINT eligibility_reason_unit_ck CHECK (
        value_unit ~ '^[A-Z][A-Z0-9_]{0,31}$'
    ),
    CONSTRAINT eligibility_reason_lineage_ck CHECK (
        lineage_hash ~ '^[0-9a-f]{64}$'
        AND array_position(market_fact_revision_ids, NULL) IS NULL
        AND array_position(market_bar_revision_ids, NULL) IS NULL
        AND array_position(market_gap_ids, NULL) IS NULL
        AND array_position(market_session_ids, NULL) IS NULL
        AND array_position(market_capture_ids, NULL) IS NULL
    )
);
CREATE INDEX eligibility_reason_assessment_idx
    ON mra.eligibility_reason (eligibility_assessment_id, eligibility_rule_id);
CREATE INDEX eligibility_reason_rule_idx
    ON mra.eligibility_reason (eligibility_policy_id, eligibility_rule_id);
CREATE INDEX eligibility_reason_fact_lineage_gin
    ON mra.eligibility_reason USING gin (market_fact_revision_ids);
CREATE INDEX eligibility_reason_bar_lineage_gin
    ON mra.eligibility_reason USING gin (market_bar_revision_ids);
CREATE INDEX eligibility_reason_gap_lineage_gin
    ON mra.eligibility_reason USING gin (market_gap_ids);
CREATE INDEX eligibility_reason_capture_lineage_gin
    ON mra.eligibility_reason USING gin (market_capture_ids);

CREATE TABLE mra.feature_definition (
    feature_definition_id uuid PRIMARY KEY,
    feature_code text NOT NULL,
    version integer NOT NULL,
    value_type text NOT NULL,
    value_unit text NOT NULL,
    frequency_value integer NOT NULL,
    frequency_unit text NOT NULL,
    window_value integer NOT NULL,
    window_unit text NOT NULL,
    lookback_value integer NOT NULL,
    lookback_unit text NOT NULL,
    source_requirements text[] NOT NULL,
    availability_rule text NOT NULL,
    missingness_policy text NOT NULL,
    algorithm_code text NOT NULL,
    algorithm_version text NOT NULL,
    algorithm_sha256 text NOT NULL,
    code_artifact_id uuid NOT NULL,
    code_content_sha256 text NOT NULL,
    code_size_bytes bigint NOT NULL,
    config_artifact_id uuid NOT NULL,
    config_content_sha256 text NOT NULL,
    config_size_bytes bigint NOT NULL,
    content_sha256 text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT feature_definition_identity_uk UNIQUE (feature_code, version),
    CONSTRAINT feature_definition_content_uk UNIQUE (content_sha256),
    CONSTRAINT feature_definition_candidate_join_uk UNIQUE (
        feature_definition_id, content_sha256, value_type
    ),
    CONSTRAINT feature_definition_code_artifact_fk FOREIGN KEY (
        code_artifact_id, code_content_sha256, code_size_bytes
    ) REFERENCES mra.artifact(
        artifact_id, content_sha256, size_bytes
    ) ON DELETE RESTRICT,
    CONSTRAINT feature_definition_config_artifact_fk FOREIGN KEY (
        config_artifact_id, config_content_sha256, config_size_bytes
    ) REFERENCES mra.artifact(
        artifact_id, content_sha256, size_bytes
    ) ON DELETE RESTRICT,
    CONSTRAINT feature_definition_code_ck CHECK (
        feature_code ~ '^[a-z][a-z0-9_-]{0,99}$'
    ),
    CONSTRAINT feature_definition_version_ck CHECK (version > 0),
    CONSTRAINT feature_definition_value_type_ck CHECK (
        value_type IN ('DECIMAL', 'INTEGER', 'BOOLEAN', 'TEXT')
    ),
    CONSTRAINT feature_definition_unit_ck CHECK (
        value_unit ~ '^[A-Z][A-Z0-9_]{0,31}$'
    ),
    CONSTRAINT feature_definition_frequency_ck CHECK (
        frequency_value > 0
        AND frequency_unit IN ('MINUTE', 'TRADING_SESSION', 'CALENDAR_DAY')
    ),
    CONSTRAINT feature_definition_window_ck CHECK (
        window_value > 0
        AND window_unit IN ('MINUTE', 'TRADING_SESSION', 'CALENDAR_DAY')
    ),
    CONSTRAINT feature_definition_lookback_ck CHECK (
        lookback_value >= 0
        AND lookback_unit IN ('MINUTE', 'TRADING_SESSION', 'CALENDAR_DAY')
    ),
    CONSTRAINT feature_definition_sources_ck CHECK (
        cardinality(source_requirements) > 0
        AND array_position(source_requirements, NULL) IS NULL
        AND source_requirements <@ ARRAY[
            'MARKET_BAR_REVISION', 'INSTRUMENT_FACT_REVISION',
            'TRADING_SESSION', 'UNIVERSE_MEMBER',
            'ELIGIBILITY_ASSESSMENT'
        ]::text[]
    ),
    CONSTRAINT feature_definition_availability_ck CHECK (
        availability_rule = 'DECISION_VISIBLE_AT_OR_BEFORE'
    ),
    CONSTRAINT feature_definition_missingness_ck CHECK (
        missingness_policy = 'EXPLICIT_STATUS'
    ),
    CONSTRAINT feature_definition_algorithm_code_ck CHECK (
        algorithm_code ~ '^[a-z][a-z0-9_-]{0,99}$'
    ),
    CONSTRAINT feature_definition_algorithm_version_ck CHECK (
        algorithm_version ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$'
    ),
    CONSTRAINT feature_definition_hashes_ck CHECK (
        algorithm_sha256 ~ '^[0-9a-f]{64}$'
        AND code_content_sha256 ~ '^[0-9a-f]{64}$'
        AND config_content_sha256 ~ '^[0-9a-f]{64}$'
        AND content_sha256 ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT feature_definition_sizes_ck CHECK (
        code_size_bytes >= 0 AND config_size_bytes >= 0
    )
);
CREATE INDEX feature_definition_code_artifact_idx
    ON mra.feature_definition (
        code_artifact_id, code_content_sha256, code_size_bytes
    );
CREATE INDEX feature_definition_config_artifact_idx
    ON mra.feature_definition (
        config_artifact_id, config_content_sha256, config_size_bytes
    );

CREATE TABLE mra.dataset (
    dataset_id uuid PRIMARY KEY,
    dataset_code text NOT NULL,
    version integer NOT NULL,
    dataset_kind text NOT NULL,
    decision_time timestamptz NOT NULL,
    universe_revision_id uuid NOT NULL,
    eligibility_policy_id uuid NOT NULL
        REFERENCES mra.eligibility_policy(eligibility_policy_id)
        ON DELETE RESTRICT,
    manifest_artifact_id uuid NOT NULL,
    manifest_content_sha256 text NOT NULL,
    manifest_size_bytes bigint NOT NULL,
    code_artifact_id uuid NOT NULL,
    code_content_sha256 text NOT NULL,
    code_size_bytes bigint NOT NULL,
    config_artifact_id uuid NOT NULL,
    config_content_sha256 text NOT NULL,
    config_size_bytes bigint NOT NULL,
    content_sha256 text NOT NULL,
    row_count integer NOT NULL,
    feature_count integer NOT NULL,
    source_count integer NOT NULL,
    cell_count integer NOT NULL,
    available_cell_count integer NOT NULL,
    missing_cell_count integer NOT NULL,
    unknown_cell_count integer NOT NULL,
    stale_cell_count integer NOT NULL,
    conflict_cell_count integer NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT dataset_identity_uk UNIQUE (dataset_code, version),
    CONSTRAINT dataset_content_uk UNIQUE (content_sha256),
    CONSTRAINT dataset_scope_join_uk UNIQUE (
        dataset_id, universe_revision_id, eligibility_policy_id, decision_time
    ),
    CONSTRAINT dataset_candidate_join_uk UNIQUE (
        dataset_id, content_sha256, universe_revision_id,
        eligibility_policy_id, decision_time, row_count
    ),
    CONSTRAINT dataset_universe_decision_fk FOREIGN KEY (
        universe_revision_id, decision_time
    ) REFERENCES mra.universe_revision(
        universe_revision_id, decision_time
    ) ON DELETE RESTRICT,
    CONSTRAINT dataset_manifest_artifact_fk FOREIGN KEY (
        manifest_artifact_id, manifest_content_sha256, manifest_size_bytes
    ) REFERENCES mra.artifact(
        artifact_id, content_sha256, size_bytes
    ) ON DELETE RESTRICT,
    CONSTRAINT dataset_code_artifact_fk FOREIGN KEY (
        code_artifact_id, code_content_sha256, code_size_bytes
    ) REFERENCES mra.artifact(
        artifact_id, content_sha256, size_bytes
    ) ON DELETE RESTRICT,
    CONSTRAINT dataset_config_artifact_fk FOREIGN KEY (
        config_artifact_id, config_content_sha256, config_size_bytes
    ) REFERENCES mra.artifact(
        artifact_id, content_sha256, size_bytes
    ) ON DELETE RESTRICT,
    CONSTRAINT dataset_code_ck CHECK (
        dataset_code ~ '^[a-z][a-z0-9_-]{0,99}$'
    ),
    CONSTRAINT dataset_version_ck CHECK (version > 0),
    CONSTRAINT dataset_kind_ck CHECK (dataset_kind = 'DECISION_INPUT'),
    CONSTRAINT dataset_hashes_ck CHECK (
        manifest_content_sha256 ~ '^[0-9a-f]{64}$'
        AND code_content_sha256 ~ '^[0-9a-f]{64}$'
        AND config_content_sha256 ~ '^[0-9a-f]{64}$'
        AND content_sha256 ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT dataset_sizes_ck CHECK (
        manifest_size_bytes > 0
        AND code_size_bytes >= 0
        AND config_size_bytes >= 0
    ),
    CONSTRAINT dataset_counts_ck CHECK (
        row_count >= 0
        AND feature_count > 0
        AND source_count >= row_count + feature_count
        AND cell_count = row_count * feature_count
        AND available_cell_count >= 0
        AND missing_cell_count >= 0
        AND unknown_cell_count >= 0
        AND stale_cell_count >= 0
        AND conflict_cell_count >= 0
        AND cell_count = available_cell_count + missing_cell_count
            + unknown_cell_count + stale_cell_count + conflict_cell_count
    )
);
CREATE INDEX dataset_decision_scope_idx
    ON mra.dataset (
        universe_revision_id, eligibility_policy_id, decision_time, dataset_id
    );
CREATE INDEX dataset_universe_decision_idx
    ON mra.dataset (universe_revision_id, decision_time);
CREATE INDEX dataset_eligibility_policy_idx
    ON mra.dataset (eligibility_policy_id, dataset_id);
CREATE INDEX dataset_manifest_artifact_idx
    ON mra.dataset (
        manifest_artifact_id, manifest_content_sha256, manifest_size_bytes
    );
CREATE INDEX dataset_code_artifact_idx
    ON mra.dataset (code_artifact_id, code_content_sha256, code_size_bytes);
CREATE INDEX dataset_config_artifact_idx
    ON mra.dataset (
        config_artifact_id, config_content_sha256, config_size_bytes
    );

CREATE TABLE mra.dataset_source (
    dataset_source_id uuid PRIMARY KEY,
    dataset_id uuid NOT NULL
        REFERENCES mra.dataset(dataset_id) ON DELETE RESTRICT,
    source_role text NOT NULL,
    instrument_id uuid REFERENCES mra.instrument(instrument_id)
        ON DELETE RESTRICT,
    universe_revision_id uuid,
    universe_member_id uuid,
    eligibility_policy_id uuid,
    eligibility_assessment_id uuid,
    decision_time timestamptz,
    membership_status text,
    eligibility_result text,
    feature_definition_id uuid
        REFERENCES mra.feature_definition(feature_definition_id)
        ON DELETE RESTRICT,
    market_bar_revision_id uuid
        REFERENCES mra.market_bar_revision(bar_revision_id) ON DELETE RESTRICT,
    market_instrument_fact_revision_id uuid
        REFERENCES mra.instrument_fact_revision(fact_revision_id)
        ON DELETE RESTRICT,
    market_trading_session_id uuid
        REFERENCES mra.trading_session(session_id) ON DELETE RESTRICT,
    market_source_gap_id uuid
        REFERENCES mra.source_gap(gap_id) ON DELETE RESTRICT,
    market_capture_id uuid
        REFERENCES mra.data_capture(capture_id) ON DELETE RESTRICT,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT dataset_source_candidate_population_uk UNIQUE (
        dataset_source_id, dataset_id, instrument_id, source_role
    ),
    CONSTRAINT dataset_source_candidate_feature_uk UNIQUE (
        dataset_id, feature_definition_id
    ),
    CONSTRAINT dataset_source_dataset_scope_fk FOREIGN KEY (
        dataset_id, universe_revision_id, eligibility_policy_id, decision_time
    ) REFERENCES mra.dataset(
        dataset_id, universe_revision_id, eligibility_policy_id, decision_time
    ) ON DELETE RESTRICT,
    CONSTRAINT dataset_source_population_member_fk FOREIGN KEY (
        universe_member_id, universe_revision_id, instrument_id,
        membership_status
    ) REFERENCES mra.universe_member(
        universe_member_id, universe_revision_id, instrument_id,
        membership_status
    ) ON DELETE RESTRICT,
    CONSTRAINT dataset_source_population_assessment_fk FOREIGN KEY (
        eligibility_assessment_id, universe_member_id, universe_revision_id,
        eligibility_policy_id, instrument_id, decision_time,
        eligibility_result
    ) REFERENCES mra.eligibility_assessment(
        eligibility_assessment_id, universe_member_id, universe_revision_id,
        eligibility_policy_id, instrument_id, decision_time, result
    ) ON DELETE RESTRICT,
    CONSTRAINT dataset_source_role_ck CHECK (
        source_role IN (
            'POPULATION', 'FEATURE_DEFINITION', 'MARKET_BAR_REVISION',
            'MARKET_INSTRUMENT_FACT_REVISION', 'MARKET_TRADING_SESSION',
            'MARKET_SOURCE_GAP', 'MARKET_CAPTURE'
        )
    ),
    CONSTRAINT dataset_source_shape_ck CHECK (
        (
            source_role = 'POPULATION'
            AND instrument_id IS NOT NULL
            AND universe_revision_id IS NOT NULL
            AND universe_member_id IS NOT NULL
            AND eligibility_policy_id IS NOT NULL
            AND eligibility_assessment_id IS NOT NULL
            AND decision_time IS NOT NULL
            AND membership_status = 'INCLUDED'
            AND eligibility_result = 'ELIGIBLE'
            AND feature_definition_id IS NULL
            AND market_bar_revision_id IS NULL
            AND market_instrument_fact_revision_id IS NULL
            AND market_trading_session_id IS NULL
            AND market_source_gap_id IS NULL
            AND market_capture_id IS NULL
        )
        OR
        (
            source_role = 'FEATURE_DEFINITION'
            AND feature_definition_id IS NOT NULL
            AND instrument_id IS NULL
            AND universe_revision_id IS NULL
            AND universe_member_id IS NULL
            AND eligibility_policy_id IS NULL
            AND eligibility_assessment_id IS NULL
            AND decision_time IS NULL
            AND membership_status IS NULL
            AND eligibility_result IS NULL
            AND market_bar_revision_id IS NULL
            AND market_instrument_fact_revision_id IS NULL
            AND market_trading_session_id IS NULL
            AND market_source_gap_id IS NULL
            AND market_capture_id IS NULL
        )
        OR
        (
            source_role = 'MARKET_BAR_REVISION'
            AND market_bar_revision_id IS NOT NULL
            AND instrument_id IS NULL
            AND universe_revision_id IS NULL
            AND universe_member_id IS NULL
            AND eligibility_policy_id IS NULL
            AND eligibility_assessment_id IS NULL
            AND decision_time IS NULL
            AND membership_status IS NULL
            AND eligibility_result IS NULL
            AND feature_definition_id IS NULL
            AND market_instrument_fact_revision_id IS NULL
            AND market_trading_session_id IS NULL
            AND market_source_gap_id IS NULL
            AND market_capture_id IS NULL
        )
        OR
        (
            source_role = 'MARKET_INSTRUMENT_FACT_REVISION'
            AND market_instrument_fact_revision_id IS NOT NULL
            AND instrument_id IS NULL
            AND universe_revision_id IS NULL
            AND universe_member_id IS NULL
            AND eligibility_policy_id IS NULL
            AND eligibility_assessment_id IS NULL
            AND decision_time IS NULL
            AND membership_status IS NULL
            AND eligibility_result IS NULL
            AND feature_definition_id IS NULL
            AND market_bar_revision_id IS NULL
            AND market_trading_session_id IS NULL
            AND market_source_gap_id IS NULL
            AND market_capture_id IS NULL
        )
        OR
        (
            source_role = 'MARKET_TRADING_SESSION'
            AND market_trading_session_id IS NOT NULL
            AND instrument_id IS NULL
            AND universe_revision_id IS NULL
            AND universe_member_id IS NULL
            AND eligibility_policy_id IS NULL
            AND eligibility_assessment_id IS NULL
            AND decision_time IS NULL
            AND membership_status IS NULL
            AND eligibility_result IS NULL
            AND feature_definition_id IS NULL
            AND market_bar_revision_id IS NULL
            AND market_instrument_fact_revision_id IS NULL
            AND market_source_gap_id IS NULL
            AND market_capture_id IS NULL
        )
        OR
        (
            source_role = 'MARKET_SOURCE_GAP'
            AND market_source_gap_id IS NOT NULL
            AND instrument_id IS NULL
            AND universe_revision_id IS NULL
            AND universe_member_id IS NULL
            AND eligibility_policy_id IS NULL
            AND eligibility_assessment_id IS NULL
            AND decision_time IS NULL
            AND membership_status IS NULL
            AND eligibility_result IS NULL
            AND feature_definition_id IS NULL
            AND market_bar_revision_id IS NULL
            AND market_instrument_fact_revision_id IS NULL
            AND market_trading_session_id IS NULL
            AND market_capture_id IS NULL
        )
        OR
        (
            source_role = 'MARKET_CAPTURE'
            AND market_capture_id IS NOT NULL
            AND instrument_id IS NULL
            AND universe_revision_id IS NULL
            AND universe_member_id IS NULL
            AND eligibility_policy_id IS NULL
            AND eligibility_assessment_id IS NULL
            AND decision_time IS NULL
            AND membership_status IS NULL
            AND eligibility_result IS NULL
            AND feature_definition_id IS NULL
            AND market_bar_revision_id IS NULL
            AND market_instrument_fact_revision_id IS NULL
            AND market_trading_session_id IS NULL
            AND market_source_gap_id IS NULL
        )
    )
);
CREATE INDEX dataset_source_dataset_role_idx
    ON mra.dataset_source (dataset_id, source_role, dataset_source_id);
CREATE INDEX dataset_source_dataset_scope_idx
    ON mra.dataset_source (
        dataset_id, universe_revision_id, eligibility_policy_id, decision_time
    );
CREATE UNIQUE INDEX dataset_source_population_uk
    ON mra.dataset_source (dataset_id, instrument_id)
    WHERE source_role = 'POPULATION';
CREATE UNIQUE INDEX dataset_source_feature_uk
    ON mra.dataset_source (dataset_id, feature_definition_id)
    WHERE source_role = 'FEATURE_DEFINITION';
CREATE INDEX dataset_source_feature_fk_idx
    ON mra.dataset_source (feature_definition_id, dataset_id)
    WHERE feature_definition_id IS NOT NULL;
CREATE INDEX dataset_source_instrument_idx
    ON mra.dataset_source (instrument_id, dataset_id)
    WHERE instrument_id IS NOT NULL;
CREATE INDEX dataset_source_population_member_idx
    ON mra.dataset_source (
        universe_member_id, universe_revision_id, instrument_id,
        membership_status
    )
    WHERE universe_member_id IS NOT NULL;
CREATE INDEX dataset_source_population_assessment_idx
    ON mra.dataset_source (
        eligibility_assessment_id, universe_member_id, universe_revision_id,
        eligibility_policy_id, instrument_id, decision_time,
        eligibility_result
    )
    WHERE eligibility_assessment_id IS NOT NULL;
CREATE INDEX dataset_source_market_bar_idx
    ON mra.dataset_source (market_bar_revision_id, dataset_id)
    WHERE market_bar_revision_id IS NOT NULL;
CREATE UNIQUE INDEX dataset_source_market_bar_uk
    ON mra.dataset_source (dataset_id, market_bar_revision_id)
    WHERE source_role = 'MARKET_BAR_REVISION';
CREATE INDEX dataset_source_instrument_fact_idx
    ON mra.dataset_source (market_instrument_fact_revision_id, dataset_id)
    WHERE market_instrument_fact_revision_id IS NOT NULL;
CREATE UNIQUE INDEX dataset_source_instrument_fact_uk
    ON mra.dataset_source (dataset_id, market_instrument_fact_revision_id)
    WHERE source_role = 'MARKET_INSTRUMENT_FACT_REVISION';
CREATE INDEX dataset_source_session_idx
    ON mra.dataset_source (market_trading_session_id, dataset_id)
    WHERE market_trading_session_id IS NOT NULL;
CREATE UNIQUE INDEX dataset_source_session_uk
    ON mra.dataset_source (dataset_id, market_trading_session_id)
    WHERE source_role = 'MARKET_TRADING_SESSION';
CREATE INDEX dataset_source_gap_idx
    ON mra.dataset_source (market_source_gap_id, dataset_id)
    WHERE market_source_gap_id IS NOT NULL;
CREATE UNIQUE INDEX dataset_source_gap_uk
    ON mra.dataset_source (dataset_id, market_source_gap_id)
    WHERE source_role = 'MARKET_SOURCE_GAP';
CREATE INDEX dataset_source_capture_idx
    ON mra.dataset_source (market_capture_id, dataset_id)
    WHERE market_capture_id IS NOT NULL;
CREATE UNIQUE INDEX dataset_source_capture_uk
    ON mra.dataset_source (dataset_id, market_capture_id)
    WHERE source_role = 'MARKET_CAPTURE';

CREATE TABLE mra.candidate_policy (
    candidate_policy_id uuid PRIMARY KEY,
    policy_code text NOT NULL,
    version integer NOT NULL,
    content_sha256 text NOT NULL,
    normalization_method text NOT NULL,
    rank_method text NOT NULL,
    missing_policy text NOT NULL,
    selection_method text NOT NULL,
    tie_policy text NOT NULL,
    score_semantics text NOT NULL,
    decimal_projection_method text NOT NULL,
    decimal_projection_version integer NOT NULL,
    requested_top_k integer NOT NULL,
    component_count integer NOT NULL,
    code_artifact_id uuid NOT NULL,
    code_content_sha256 text NOT NULL,
    code_size_bytes bigint NOT NULL,
    config_artifact_id uuid NOT NULL,
    config_content_sha256 text NOT NULL,
    config_size_bytes bigint NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT candidate_policy_identity_uk UNIQUE (policy_code, version),
    CONSTRAINT candidate_policy_content_uk UNIQUE (content_sha256),
    CONSTRAINT candidate_policy_scope_uk UNIQUE (
        candidate_policy_id, content_sha256, requested_top_k, component_count
    ),
    CONSTRAINT candidate_policy_code_artifact_fk FOREIGN KEY (
        code_artifact_id, code_content_sha256, code_size_bytes
    ) REFERENCES mra.artifact(
        artifact_id, content_sha256, size_bytes
    ) ON DELETE RESTRICT,
    CONSTRAINT candidate_policy_config_artifact_fk FOREIGN KEY (
        config_artifact_id, config_content_sha256, config_size_bytes
    ) REFERENCES mra.artifact(
        artifact_id, content_sha256, size_bytes
    ) ON DELETE RESTRICT,
    CONSTRAINT candidate_policy_shape_ck CHECK (
        policy_code ~ '^[a-z][a-z0-9_]{0,99}$'
        AND version > 0
        AND content_sha256 ~ '^[0-9a-f]{64}$'
        AND normalization_method = 'ARITHMETIC_MIDRANK'
        AND rank_method = 'COMPETITION'
        AND missing_policy = 'STRICT_COMPLETE_CASE'
        AND selection_method = 'TOP_K'
        AND tie_policy = 'INCLUDE_ALL_BOUNDARY_TIES'
        AND score_semantics = 'DESCRIPTIVE_RANK_SCORE'
        AND decimal_projection_method =
            'EXACT_RATIONAL_ADAPTIVE_HALF_EVEN'
        AND decimal_projection_version = 1
        AND requested_top_k > 0
        AND component_count > 0
        AND code_content_sha256 ~ '^[0-9a-f]{64}$'
        AND config_content_sha256 ~ '^[0-9a-f]{64}$'
        AND code_size_bytes >= 0
        AND config_size_bytes >= 0
    )
);
CREATE INDEX candidate_policy_code_artifact_idx
    ON mra.candidate_policy (
        code_artifact_id, code_content_sha256, code_size_bytes
    );
CREATE INDEX candidate_policy_config_artifact_idx
    ON mra.candidate_policy (
        config_artifact_id, config_content_sha256, config_size_bytes
    );

CREATE TABLE mra.candidate_policy_component (
    candidate_policy_component_id uuid PRIMARY KEY,
    candidate_policy_id uuid NOT NULL
        REFERENCES mra.candidate_policy(candidate_policy_id)
        ON DELETE RESTRICT,
    component_code text NOT NULL,
    ordinal integer NOT NULL,
    feature_definition_id uuid NOT NULL,
    feature_content_sha256 text NOT NULL,
    feature_value_type text NOT NULL,
    direction text NOT NULL,
    declared_weight numeric NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT candidate_policy_component_identity_uk UNIQUE (
        candidate_policy_id, component_code
    ),
    CONSTRAINT candidate_policy_component_ordinal_uk UNIQUE (
        candidate_policy_id, ordinal
    ),
    CONSTRAINT candidate_policy_component_feature_uk UNIQUE (
        candidate_policy_id, feature_definition_id
    ),
    CONSTRAINT candidate_policy_component_scope_uk UNIQUE (
        candidate_policy_component_id, candidate_policy_id,
        feature_definition_id, feature_content_sha256, feature_value_type
    ),
    CONSTRAINT candidate_policy_component_feature_fk FOREIGN KEY (
        feature_definition_id, feature_content_sha256, feature_value_type
    ) REFERENCES mra.feature_definition(
        feature_definition_id, content_sha256, value_type
    ) ON DELETE RESTRICT,
    CONSTRAINT candidate_policy_component_shape_ck CHECK (
        component_code ~ '^[a-z][a-z0-9_]{0,99}$'
        AND ordinal > 0
        AND feature_content_sha256 ~ '^[0-9a-f]{64}$'
        AND feature_value_type IN ('DECIMAL', 'INTEGER')
        AND direction IN ('HIGHER_IS_BETTER', 'LOWER_IS_BETTER')
        AND declared_weight > 0
        AND declared_weight < 'Infinity'::numeric
    )
);
CREATE INDEX candidate_policy_component_feature_binding_idx
    ON mra.candidate_policy_component (
        feature_definition_id, feature_content_sha256, feature_value_type
    );
CREATE INDEX candidate_policy_component_feature_idx
    ON mra.candidate_policy_component (
        feature_definition_id, candidate_policy_id
    );

CREATE TABLE mra.candidate_set (
    candidate_set_id uuid PRIMARY KEY,
    candidate_policy_id uuid NOT NULL,
    candidate_policy_content_sha256 text NOT NULL,
    dataset_id uuid NOT NULL,
    dataset_content_sha256 text NOT NULL,
    universe_revision_id uuid NOT NULL,
    eligibility_policy_id uuid NOT NULL,
    decision_time timestamptz NOT NULL,
    requested_top_k integer NOT NULL,
    component_count integer NOT NULL,
    decimal_projection_precision integer NOT NULL,
    population_count integer NOT NULL,
    rankable_count integer NOT NULL,
    unrankable_count integer NOT NULL,
    selected_count integer NOT NULL,
    ranked_not_selected_count integer NOT NULL,
    score_component_count bigint NOT NULL,
    available_component_count integer NOT NULL,
    constant_component_count integer NOT NULL,
    not_estimable_component_count integer NOT NULL,
    ranking_status text NOT NULL,
    composite_distinct_count integer NOT NULL,
    boundary_score numeric,
    boundary_rank integer,
    strictly_above_boundary_count integer NOT NULL,
    boundary_group_count integer NOT NULL,
    selected_overflow_count integer NOT NULL,
    boundary_has_tie boolean NOT NULL,
    boundary_tie_expanded boolean NOT NULL,
    dependency_sha256 text NOT NULL,
    content_sha256 text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT candidate_set_identity_uk UNIQUE (
        candidate_policy_id, dataset_id
    ),
    CONSTRAINT candidate_set_content_uk UNIQUE (content_sha256),
    CONSTRAINT candidate_set_scope_uk UNIQUE (
        candidate_set_id, candidate_policy_id, dataset_id
    ),
    CONSTRAINT candidate_set_policy_fk FOREIGN KEY (
        candidate_policy_id, candidate_policy_content_sha256,
        requested_top_k, component_count
    ) REFERENCES mra.candidate_policy(
        candidate_policy_id, content_sha256,
        requested_top_k, component_count
    ) ON DELETE RESTRICT,
    CONSTRAINT candidate_set_dataset_fk FOREIGN KEY (
        dataset_id, dataset_content_sha256, universe_revision_id,
        eligibility_policy_id, decision_time, population_count
    ) REFERENCES mra.dataset(
        dataset_id, content_sha256, universe_revision_id,
        eligibility_policy_id, decision_time, row_count
    ) ON DELETE RESTRICT,
    CONSTRAINT candidate_set_counts_ck CHECK (
        population_count >= 0
        AND rankable_count >= 0
        AND unrankable_count >= 0
        AND selected_count >= 0
        AND ranked_not_selected_count >= 0
        AND score_component_count >= 0
        AND population_count = rankable_count + unrankable_count
        AND rankable_count = selected_count + ranked_not_selected_count
        AND score_component_count =
            population_count::bigint * component_count::bigint
    ),
    CONSTRAINT candidate_set_component_counts_ck CHECK (
        available_component_count >= 0
        AND constant_component_count >= 0
        AND not_estimable_component_count >= 0
        AND available_component_count + constant_component_count
            + not_estimable_component_count = component_count
    ),
    CONSTRAINT candidate_set_ranking_ck CHECK (
        requested_top_k > 0
        AND component_count > 0
        AND decimal_projection_precision IN (
            64, 128, 256, 512, 1024, 2048, 4096
        )
        AND dependency_sha256 ~ '^[0-9a-f]{64}$'
        AND content_sha256 ~ '^[0-9a-f]{64}$'
        AND (
            (
                rankable_count = 0
                AND ranking_status = 'NOT_ESTIMABLE'
                AND available_component_count = 0
                AND constant_component_count = 0
                AND not_estimable_component_count = component_count
                AND composite_distinct_count = 0
            )
            OR
            (
                rankable_count > 0
                AND ranking_status = 'CONSTANT'
                AND available_component_count = 0
                AND constant_component_count = component_count
                AND not_estimable_component_count = 0
                AND composite_distinct_count = 1
            )
            OR
            (
                rankable_count > 0
                AND ranking_status = 'AVAILABLE'
                AND available_component_count > 0
                AND available_component_count + constant_component_count
                    = component_count
                AND not_estimable_component_count = 0
                AND composite_distinct_count BETWEEN 1 AND rankable_count
            )
        )
    ),
    CONSTRAINT candidate_set_boundary_ck CHECK (
        (
            rankable_count = 0
            AND selected_count = 0
            AND boundary_score IS NULL
            AND boundary_rank IS NULL
            AND strictly_above_boundary_count = 0
            AND boundary_group_count = 0
            AND selected_overflow_count = 0
            AND NOT boundary_has_tie
            AND NOT boundary_tie_expanded
        )
        OR
        (
            rankable_count > 0
            AND boundary_score BETWEEN 0 AND 1
            AND boundary_rank = strictly_above_boundary_count + 1
            AND boundary_rank > 0
            AND boundary_rank <= LEAST(requested_top_k, rankable_count)
            AND strictly_above_boundary_count >= 0
            AND boundary_group_count > 0
            AND selected_count =
                strictly_above_boundary_count + boundary_group_count
            AND selected_overflow_count =
                GREATEST(selected_count - requested_top_k, 0)
            AND boundary_has_tie = (boundary_group_count > 1)
            AND boundary_tie_expanded = (selected_overflow_count > 0)
        )
    )
);
CREATE INDEX candidate_set_policy_binding_idx
    ON mra.candidate_set (
        candidate_policy_id, candidate_policy_content_sha256,
        requested_top_k, component_count
    );
CREATE INDEX candidate_set_dataset_binding_idx
    ON mra.candidate_set (
        dataset_id, dataset_content_sha256, universe_revision_id,
        eligibility_policy_id, decision_time, population_count
    );
CREATE INDEX candidate_set_dataset_policy_idx
    ON mra.candidate_set (dataset_id, candidate_policy_id);
CREATE INDEX candidate_set_decision_time_idx
    ON mra.candidate_set (decision_time, candidate_set_id);

CREATE TABLE mra.candidate (
    candidate_id uuid PRIMARY KEY,
    candidate_set_id uuid NOT NULL,
    candidate_policy_id uuid NOT NULL,
    dataset_id uuid NOT NULL,
    dataset_population_source_id uuid NOT NULL,
    dataset_source_role text NOT NULL,
    instrument_id uuid NOT NULL,
    disposition text NOT NULL,
    composite_score numeric,
    competition_rank integer,
    reason_code text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT candidate_identity_uk UNIQUE (
        candidate_set_id, instrument_id
    ),
    CONSTRAINT candidate_population_source_uk UNIQUE (
        candidate_set_id, dataset_population_source_id
    ),
    CONSTRAINT candidate_scope_uk UNIQUE (
        candidate_id, candidate_set_id, candidate_policy_id,
        dataset_id, instrument_id, disposition
    ),
    CONSTRAINT candidate_set_scope_fk FOREIGN KEY (
        candidate_set_id, candidate_policy_id, dataset_id
    ) REFERENCES mra.candidate_set(
        candidate_set_id, candidate_policy_id, dataset_id
    ) ON DELETE RESTRICT,
    CONSTRAINT candidate_population_source_fk FOREIGN KEY (
        dataset_population_source_id, dataset_id,
        instrument_id, dataset_source_role
    ) REFERENCES mra.dataset_source(
        dataset_source_id, dataset_id, instrument_id, source_role
    ) ON DELETE RESTRICT,
    CONSTRAINT candidate_disposition_ck CHECK (
        dataset_source_role = 'POPULATION'
        AND (
            (
                disposition IN ('SELECTED', 'RANKED_NOT_SELECTED')
                AND composite_score BETWEEN 0 AND 1
                AND competition_rank > 0
            )
            OR
            (
                disposition = 'UNRANKABLE'
                AND composite_score IS NULL
                AND competition_rank IS NULL
            )
        )
    ),
    CONSTRAINT candidate_reason_ck CHECK (
        reason_code IN (
            'ALL_RANKABLE_SELECTED', 'ABOVE_BOUNDARY', 'AT_BOUNDARY',
            'BOUNDARY_TIE_INCLUDED', 'BELOW_BOUNDARY',
            'STRICT_COMPLETE_CASE_REQUIRED_FEATURE_UNAVAILABLE'
        )
        AND (
            (
                disposition = 'SELECTED'
                AND reason_code IN (
                    'ALL_RANKABLE_SELECTED', 'ABOVE_BOUNDARY', 'AT_BOUNDARY',
                    'BOUNDARY_TIE_INCLUDED'
                )
            )
            OR
            (
                disposition = 'RANKED_NOT_SELECTED'
                AND reason_code = 'BELOW_BOUNDARY'
            )
            OR
            (
                disposition = 'UNRANKABLE'
                AND reason_code =
                    'STRICT_COMPLETE_CASE_REQUIRED_FEATURE_UNAVAILABLE'
            )
        )
    )
);
CREATE INDEX candidate_set_scope_fk_idx
    ON mra.candidate (
        candidate_set_id, candidate_policy_id, dataset_id
    );
CREATE INDEX candidate_population_source_fk_idx
    ON mra.candidate (
        dataset_population_source_id, dataset_id,
        instrument_id, dataset_source_role
    );
CREATE INDEX candidate_set_disposition_idx
    ON mra.candidate (candidate_set_id, disposition, candidate_id);
CREATE INDEX candidate_set_rank_idx
    ON mra.candidate (candidate_set_id, competition_rank)
    WHERE competition_rank IS NOT NULL;
CREATE INDEX candidate_set_disposition_rank_idx
    ON mra.candidate (
        candidate_set_id, disposition, competition_rank, candidate_id
    );
CREATE INDEX candidate_instrument_dossier_idx
    ON mra.candidate (instrument_id, candidate_set_id);

CREATE TABLE mra.candidate_score_component (
    candidate_score_component_id uuid PRIMARY KEY,
    candidate_id uuid NOT NULL,
    candidate_set_id uuid NOT NULL,
    candidate_policy_id uuid NOT NULL,
    dataset_id uuid NOT NULL,
    instrument_id uuid NOT NULL,
    candidate_disposition text NOT NULL,
    candidate_policy_component_id uuid NOT NULL,
    feature_definition_id uuid NOT NULL,
    feature_content_sha256 text NOT NULL,
    feature_value_type text NOT NULL,
    raw_status text NOT NULL,
    raw_decimal_value numeric,
    raw_integer_value numeric,
    raw_reason_code text NOT NULL,
    cell_source_lineage_hash text NOT NULL,
    normalized_weight numeric NOT NULL,
    percentile numeric,
    contribution numeric,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT candidate_score_component_identity_uk UNIQUE (
        candidate_id, candidate_policy_component_id
    ),
    CONSTRAINT candidate_score_component_candidate_fk FOREIGN KEY (
        candidate_id, candidate_set_id, candidate_policy_id,
        dataset_id, instrument_id, candidate_disposition
    ) REFERENCES mra.candidate(
        candidate_id, candidate_set_id, candidate_policy_id,
        dataset_id, instrument_id, disposition
    ) ON DELETE RESTRICT,
    CONSTRAINT candidate_score_component_policy_component_fk FOREIGN KEY (
        candidate_policy_component_id, candidate_policy_id,
        feature_definition_id, feature_content_sha256, feature_value_type
    ) REFERENCES mra.candidate_policy_component(
        candidate_policy_component_id, candidate_policy_id,
        feature_definition_id, feature_content_sha256, feature_value_type
    ) ON DELETE RESTRICT,
    CONSTRAINT candidate_score_component_dataset_feature_fk FOREIGN KEY (
        dataset_id, feature_definition_id
    ) REFERENCES mra.dataset_source(
        dataset_id, feature_definition_id
    ) ON DELETE RESTRICT,
    CONSTRAINT candidate_score_component_raw_ck CHECK (
        raw_status IN (
            'AVAILABLE', 'MISSING', 'UNKNOWN', 'STALE', 'CONFLICT'
        )
        AND raw_reason_code ~ '^[A-Z][A-Z0-9_]{0,99}$'
        AND cell_source_lineage_hash ~ '^[0-9a-f]{64}$'
        AND (
            (
                raw_status = 'AVAILABLE'
                AND (
                    (
                        feature_value_type = 'DECIMAL'
                        AND raw_decimal_value IS NOT NULL
                        AND raw_decimal_value > '-Infinity'::numeric
                        AND raw_decimal_value < 'Infinity'::numeric
                        AND scale(raw_decimal_value) <= 12
                        AND abs(raw_decimal_value) <
                            100000000000000000000000000::numeric
                        AND raw_integer_value IS NULL
                    )
                    OR
                    (
                        feature_value_type = 'INTEGER'
                        AND raw_decimal_value IS NULL
                        AND raw_integer_value IS NOT NULL
                        AND raw_integer_value > '-Infinity'::numeric
                        AND raw_integer_value < 'Infinity'::numeric
                        AND scale(raw_integer_value) = 0
                    )
                )
            )
            OR
            (
                raw_status IN ('MISSING', 'UNKNOWN', 'STALE', 'CONFLICT')
                AND raw_decimal_value IS NULL
                AND raw_integer_value IS NULL
            )
        )
    ),
    CONSTRAINT candidate_score_component_ranking_ck CHECK (
        normalized_weight > 0 AND normalized_weight <= 1
        AND (
            (
                candidate_disposition IN (
                    'SELECTED', 'RANKED_NOT_SELECTED'
                )
                AND raw_status = 'AVAILABLE'
                AND percentile BETWEEN 0 AND 1
                AND contribution BETWEEN 0 AND 1
                AND contribution <= normalized_weight
            )
            OR
            (
                candidate_disposition = 'UNRANKABLE'
                AND percentile IS NULL
                AND contribution IS NULL
            )
        )
    )
);
CREATE INDEX candidate_score_component_candidate_fk_idx
    ON mra.candidate_score_component (
        candidate_id, candidate_set_id, candidate_policy_id,
        dataset_id, instrument_id, candidate_disposition
    );
CREATE INDEX candidate_score_component_policy_binding_idx
    ON mra.candidate_score_component (
        candidate_policy_component_id, candidate_policy_id,
        feature_definition_id, feature_content_sha256, feature_value_type
    );
CREATE INDEX candidate_score_component_dataset_feature_idx
    ON mra.candidate_score_component (dataset_id, feature_definition_id);
CREATE INDEX candidate_score_component_set_component_idx
    ON mra.candidate_score_component (
        candidate_set_id, candidate_policy_component_id, raw_status,
        candidate_id
    );
CREATE INDEX candidate_score_component_feature_set_idx
    ON mra.candidate_score_component (
        feature_definition_id, candidate_set_id, candidate_id
    );

CREATE TABLE mra.target_definition (
    target_definition_id uuid PRIMARY KEY,
    target_code text NOT NULL,
    version integer NOT NULL,
    registration_status text NOT NULL,
    supersedes_target_definition_id uuid,
    instrument_scope text NOT NULL,
    market_scope text NOT NULL,
    algorithm_code text NOT NULL,
    algorithm_version text NOT NULL,
    algorithm_sha256 text NOT NULL,
    algorithm_binding_sha256 text NOT NULL,
    code_artifact_id uuid NOT NULL,
    code_content_sha256 text NOT NULL,
    code_size_bytes bigint NOT NULL,
    config_artifact_id uuid NOT NULL,
    config_content_sha256 text NOT NULL,
    config_size_bytes bigint NOT NULL,
    checkpoint_count integer NOT NULL,
    checkpoint_roster_sha256 text NOT NULL,
    metric_count integer NOT NULL,
    metric_roster_sha256 text NOT NULL,
    dependency_count integer NOT NULL,
    dependency_roster_sha256 text NOT NULL,
    content_sha256 text NOT NULL,
    registration_request_identity text NOT NULL,
    registration_request_sha256 text NOT NULL,
    registered_by_actor_type text NOT NULL,
    registered_by_actor_id text NOT NULL,
    registered_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT target_definition_identity_uk UNIQUE (target_code, version),
    CONSTRAINT target_definition_content_uk UNIQUE (content_sha256),
    CONSTRAINT target_definition_supersedes_uk UNIQUE (supersedes_target_definition_id),
    CONSTRAINT target_definition_exact_identity_uk UNIQUE (
        target_definition_id, version, content_sha256
    ),
    CONSTRAINT target_definition_request_uk UNIQUE (
        target_code, registration_request_identity
    ),
    CONSTRAINT target_definition_supersedes_fk FOREIGN KEY (
        supersedes_target_definition_id
    ) REFERENCES mra.target_definition(target_definition_id) ON DELETE RESTRICT,
    CONSTRAINT target_definition_code_artifact_fk FOREIGN KEY (
        code_artifact_id, code_content_sha256, code_size_bytes
    ) REFERENCES mra.artifact(
        artifact_id, content_sha256, size_bytes
    ) ON DELETE RESTRICT,
    CONSTRAINT target_definition_config_artifact_fk FOREIGN KEY (
        config_artifact_id, config_content_sha256, config_size_bytes
    ) REFERENCES mra.artifact(
        artifact_id, content_sha256, size_bytes
    ) ON DELETE RESTRICT,
    CONSTRAINT target_definition_code_ck CHECK (
        target_code ~ '^[a-z][a-z0-9_]{0,99}$'
    ),
    CONSTRAINT target_definition_version_chain_ck CHECK (
        (version = 1 AND supersedes_target_definition_id IS NULL)
        OR (version > 1 AND supersedes_target_definition_id IS NOT NULL)
    ),
    CONSTRAINT target_definition_status_ck CHECK (
        registration_status = 'REGISTERED'
    ),
    CONSTRAINT target_definition_scope_ck CHECK (
        instrument_scope = 'A_SHARE_EQUITY'
        AND market_scope = 'SSE_SZSE'
    ),
    CONSTRAINT target_definition_algorithm_ck CHECK (
        algorithm_code ~ '^[a-z][a-z0-9_]{0,99}$'
        AND algorithm_version ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$'
        AND algorithm_sha256 ~ '^[0-9a-f]{64}$'
        AND algorithm_binding_sha256 =
            mra.target_algorithm_binding_sha256(
                algorithm_code, algorithm_version, algorithm_sha256,
                code_artifact_id, code_content_sha256, code_size_bytes,
                config_artifact_id, config_content_sha256,
                config_size_bytes
            )
    ),
    CONSTRAINT target_definition_counts_ck CHECK (
        checkpoint_count >= 2
        AND metric_count > 0
        AND dependency_count > 0
    ),
    CONSTRAINT target_definition_hashes_ck CHECK (
        checkpoint_roster_sha256 ~ '^[0-9a-f]{64}$'
        AND metric_roster_sha256 ~ '^[0-9a-f]{64}$'
        AND dependency_roster_sha256 ~ '^[0-9a-f]{64}$'
        AND content_sha256 ~ '^[0-9a-f]{64}$'
        AND registration_request_sha256 ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT target_definition_request_ck CHECK (
        registration_request_identity ~
            '^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$'
        AND registered_by_actor_type IN ('SYSTEM', 'OPERATOR', 'WORKER')
        AND registered_by_actor_id <> ''
    ),
    CONSTRAINT target_definition_content_ck CHECK (
        content_sha256 = mra.target_definition_content_sha256(
            algorithm_code, algorithm_version, algorithm_sha256,
            algorithm_binding_sha256,
            code_artifact_id, code_content_sha256, code_size_bytes,
            config_artifact_id, config_content_sha256, config_size_bytes,
            checkpoint_count, checkpoint_roster_sha256,
            dependency_count, dependency_roster_sha256,
            instrument_scope, market_scope, metric_count,
            metric_roster_sha256, registration_status,
            supersedes_target_definition_id, target_code, version
        )
    )
);
CREATE INDEX target_definition_code_version_idx
    ON mra.target_definition (target_code, version DESC, target_definition_id);
CREATE INDEX target_definition_supersedes_idx
    ON mra.target_definition (supersedes_target_definition_id)
    WHERE supersedes_target_definition_id IS NOT NULL;
CREATE INDEX target_definition_code_artifact_idx
    ON mra.target_definition (
        code_artifact_id, code_content_sha256, code_size_bytes
    );
CREATE INDEX target_definition_config_artifact_idx
    ON mra.target_definition (
        config_artifact_id, config_content_sha256, config_size_bytes
    );

CREATE TABLE mra.target_checkpoint (
    target_checkpoint_id uuid PRIMARY KEY,
    target_definition_id uuid NOT NULL,
    checkpoint_code text NOT NULL,
    ordinal integer NOT NULL,
    checkpoint_role text NOT NULL,
    session_offset integer NOT NULL,
    timing_rule text NOT NULL,
    local_time time NOT NULL,
    timezone_name text NOT NULL,
    timeframe text NOT NULL,
    price_basis text NOT NULL,
    value_field text NOT NULL,
    reference_rule text NOT NULL,
    availability_rule text NOT NULL,
    finality_rule text NOT NULL,
    content_sha256 text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT target_checkpoint_definition_fk FOREIGN KEY (
        target_definition_id
    ) REFERENCES mra.target_definition(target_definition_id)
      ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT target_checkpoint_exact_identity_uk UNIQUE (
        target_checkpoint_id, target_definition_id
    ),
    CONSTRAINT target_checkpoint_ordinal_uk UNIQUE (
        target_definition_id, ordinal
    ),
    CONSTRAINT target_checkpoint_code_uk UNIQUE (
        target_definition_id, checkpoint_code
    ),
    CONSTRAINT target_checkpoint_code_ck CHECK (
        checkpoint_code ~ '^[a-z][a-z0-9_]{0,99}$'
    ),
    CONSTRAINT target_checkpoint_vocabulary_ck CHECK (
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
        AND reference_rule = 'EXACT_SESSION_BAR'
        AND availability_rule = 'EXACT_REVISION_OR_SOURCE_GAP'
        AND finality_rule = 'RECORD_UNKNOWN'
    ),
    CONSTRAINT target_checkpoint_ordinal_ck CHECK (ordinal > 0),
    CONSTRAINT target_checkpoint_role_horizon_ck CHECK (
        (checkpoint_role = 'DECISION_REFERENCE' AND session_offset = 0)
        OR
        (checkpoint_role = 'OUTCOME_OBSERVATION' AND session_offset > 0)
    ),
    CONSTRAINT target_checkpoint_time_ck CHECK (
        extract(second FROM local_time) = 0
        AND timezone_name ~ '^[A-Za-z_]+/[A-Za-z_]+$'
    ),
    CONSTRAINT target_checkpoint_content_ck CHECK (
        content_sha256 = mra.target_checkpoint_content_sha256(
            availability_rule, checkpoint_code, finality_rule,
            local_time, ordinal, price_basis, reference_rule,
            checkpoint_role, session_offset, timeframe, timezone_name,
            timing_rule, value_field
        )
    )
);
CREATE INDEX target_checkpoint_definition_idx
    ON mra.target_checkpoint (
        target_definition_id, ordinal, target_checkpoint_id
    );

CREATE TABLE mra.target_metric_definition (
    target_metric_definition_id uuid PRIMARY KEY,
    target_definition_id uuid NOT NULL,
    metric_code text NOT NULL,
    ordinal integer NOT NULL,
    metric_kind text NOT NULL,
    value_type text NOT NULL,
    unit text NOT NULL,
    completion_rule text NOT NULL,
    barrier_direction text,
    barrier_threshold numeric,
    algorithm_code text NOT NULL,
    algorithm_version text NOT NULL,
    algorithm_sha256 text NOT NULL,
    algorithm_binding_sha256 text NOT NULL,
    code_artifact_id uuid NOT NULL,
    code_content_sha256 text NOT NULL,
    code_size_bytes bigint NOT NULL,
    config_artifact_id uuid NOT NULL,
    config_content_sha256 text NOT NULL,
    config_size_bytes bigint NOT NULL,
    content_sha256 text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT target_metric_definition_fk FOREIGN KEY (
        target_definition_id
    ) REFERENCES mra.target_definition(target_definition_id)
      ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT target_metric_exact_identity_uk UNIQUE (
        target_metric_definition_id, target_definition_id
    ),
    CONSTRAINT target_metric_ordinal_uk UNIQUE (
        target_definition_id, ordinal
    ),
    CONSTRAINT target_metric_code_uk UNIQUE (
        target_definition_id, metric_code
    ),
    CONSTRAINT target_metric_code_artifact_fk FOREIGN KEY (
        code_artifact_id, code_content_sha256, code_size_bytes
    ) REFERENCES mra.artifact(
        artifact_id, content_sha256, size_bytes
    ) ON DELETE RESTRICT,
    CONSTRAINT target_metric_config_artifact_fk FOREIGN KEY (
        config_artifact_id, config_content_sha256, config_size_bytes
    ) REFERENCES mra.artifact(
        artifact_id, content_sha256, size_bytes
    ) ON DELETE RESTRICT,
    CONSTRAINT target_metric_vocabulary_ck CHECK (
        metric_code ~ '^[a-z][a-z0-9_]{0,99}$'
        AND ordinal > 0
        AND metric_kind IN (
            'SIMPLE_RETURN', 'MAX_FAVORABLE_EXCURSION',
            'MAX_ADVERSE_EXCURSION', 'BARRIER_HIT',
            'OBSERVATION_VALUE'
        )
        AND value_type IN ('DECIMAL', 'BOOLEAN')
        AND unit IN ('RATIO', 'PRICE', 'BOOLEAN')
        AND completion_rule IN ('REQUIRED', 'OPTIONAL')
    ),
    CONSTRAINT target_metric_value_shape_ck CHECK (
        (metric_kind IN (
            'SIMPLE_RETURN', 'MAX_FAVORABLE_EXCURSION',
            'MAX_ADVERSE_EXCURSION'
         ) AND value_type = 'DECIMAL' AND unit = 'RATIO')
        OR
        (metric_kind = 'OBSERVATION_VALUE'
         AND value_type = 'DECIMAL' AND unit = 'PRICE')
        OR
        (metric_kind = 'BARRIER_HIT'
         AND value_type = 'BOOLEAN' AND unit = 'BOOLEAN')
    ),
    CONSTRAINT target_metric_barrier_shape_ck CHECK (
        (metric_kind = 'BARRIER_HIT'
         AND barrier_direction IN ('UP', 'DOWN')
         AND barrier_threshold > 0
         AND barrier_threshold < 'Infinity'::numeric)
        OR
        (metric_kind <> 'BARRIER_HIT'
         AND barrier_direction IS NULL
         AND barrier_threshold IS NULL)
    ),
    CONSTRAINT target_metric_algorithm_ck CHECK (
        algorithm_code ~ '^[a-z][a-z0-9_]{0,99}$'
        AND algorithm_version ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$'
        AND algorithm_sha256 ~ '^[0-9a-f]{64}$'
        AND algorithm_binding_sha256 =
            mra.target_algorithm_binding_sha256(
                algorithm_code, algorithm_version, algorithm_sha256,
                code_artifact_id, code_content_sha256, code_size_bytes,
                config_artifact_id, config_content_sha256,
                config_size_bytes
            )
    ),
    CONSTRAINT target_metric_content_ck CHECK (
        content_sha256 = mra.target_metric_content_sha256(
            algorithm_code, algorithm_version, algorithm_sha256,
            algorithm_binding_sha256,
            code_artifact_id, code_content_sha256, code_size_bytes,
            config_artifact_id, config_content_sha256, config_size_bytes,
            barrier_direction, barrier_threshold, completion_rule,
            metric_code, metric_kind, ordinal, unit, value_type
        )
    )
);
CREATE INDEX target_metric_definition_target_idx
    ON mra.target_metric_definition (
        target_definition_id, ordinal, target_metric_definition_id
    );
CREATE INDEX target_metric_code_artifact_idx
    ON mra.target_metric_definition (
        code_artifact_id, code_content_sha256, code_size_bytes
    );
CREATE INDEX target_metric_config_artifact_idx
    ON mra.target_metric_definition (
        config_artifact_id, config_content_sha256, config_size_bytes
    );

CREATE TABLE mra.target_metric_dependency (
    target_metric_dependency_id uuid PRIMARY KEY,
    target_definition_id uuid NOT NULL,
    target_metric_definition_id uuid NOT NULL,
    target_checkpoint_id uuid NOT NULL,
    ordinal integer NOT NULL,
    dependency_role text NOT NULL,
    content_sha256 text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT target_metric_dependency_definition_fk FOREIGN KEY (
        target_definition_id
    ) REFERENCES mra.target_definition(target_definition_id)
      ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT target_metric_dependency_metric_fk FOREIGN KEY (
        target_metric_definition_id, target_definition_id
    ) REFERENCES mra.target_metric_definition(
        target_metric_definition_id, target_definition_id
    ) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT target_metric_dependency_checkpoint_fk FOREIGN KEY (
        target_checkpoint_id, target_definition_id
    ) REFERENCES mra.target_checkpoint(
        target_checkpoint_id, target_definition_id
    ) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT target_metric_dependency_ordinal_uk UNIQUE (
        target_definition_id, ordinal
    ),
    CONSTRAINT target_metric_dependency_binding_uk UNIQUE (
        target_metric_definition_id, target_checkpoint_id, dependency_role
    ),
    CONSTRAINT target_metric_dependency_vocabulary_ck CHECK (
        ordinal > 0
        AND dependency_role IN ('REFERENCE', 'OBSERVATION', 'PATH_MEMBER')
    ),
    CONSTRAINT target_metric_dependency_content_ck CHECK (
        content_sha256 = mra.target_metric_dependency_content_sha256(
            ordinal, dependency_role, target_checkpoint_id,
            target_metric_definition_id
        )
    )
);
CREATE INDEX target_metric_dependency_target_idx
    ON mra.target_metric_dependency (
        target_definition_id, ordinal, target_metric_dependency_id
    );
CREATE INDEX target_metric_dependency_metric_idx
    ON mra.target_metric_dependency (
        target_metric_definition_id, target_definition_id, ordinal
    );
CREATE INDEX target_metric_dependency_checkpoint_idx
    ON mra.target_metric_dependency (
        target_checkpoint_id, target_definition_id
    );

CREATE TABLE mra.runtime_schedule (
    schedule_id uuid PRIMARY KEY,
    schedule_code text NOT NULL,
    revision integer NOT NULL,
    runtime_mode text NOT NULL,
    schedule_expression text,
    timezone_name text NOT NULL,
    step_catalog_hash text NOT NULL,
    enabled boolean NOT NULL,
    supersedes_schedule_id uuid REFERENCES mra.runtime_schedule(schedule_id) ON DELETE RESTRICT,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT runtime_schedule_identity_uk UNIQUE (schedule_code, revision),
    CONSTRAINT runtime_schedule_code_ck CHECK (schedule_code ~ '^[a-z][a-z0-9_-]{0,99}$'),
    CONSTRAINT runtime_schedule_revision_ck CHECK (revision > 0),
    CONSTRAINT runtime_schedule_mode_ck CHECK (runtime_mode IN ('OPERATIONAL', 'HISTORICAL', 'REPLAY', 'SHADOW', 'PROSPECTIVE')),
    CONSTRAINT runtime_schedule_timezone_ck CHECK (timezone_name <> ''),
    CONSTRAINT runtime_schedule_catalog_hash_ck CHECK (step_catalog_hash ~ '^[0-9a-f]{64}$')
);
CREATE UNIQUE INDEX runtime_schedule_one_enabled_idx ON mra.runtime_schedule (schedule_code)
    WHERE enabled;
CREATE INDEX runtime_schedule_supersedes_idx ON mra.runtime_schedule (supersedes_schedule_id)
    WHERE supersedes_schedule_id IS NOT NULL;

CREATE TABLE mra.runtime_run (
    run_id uuid PRIMARY KEY,
    schedule_id uuid NOT NULL REFERENCES mra.runtime_schedule(schedule_id) ON DELETE RESTRICT,
    fire_key text NOT NULL,
    runtime_mode text NOT NULL,
    requested_at timestamptz NOT NULL,
    decision_time timestamptz,
    code_sha text NOT NULL,
    config_artifact_id uuid NOT NULL REFERENCES mra.artifact(artifact_id) ON DELETE RESTRICT,
    config_hash text NOT NULL,
    schema_epoch text NOT NULL,
    parent_run_id uuid REFERENCES mra.runtime_run(run_id) ON DELETE RESTRICT,
    original_run_id uuid REFERENCES mra.runtime_run(run_id) ON DELETE RESTRICT,
    state text NOT NULL,
    terminal_reason_code text,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    started_at timestamptz,
    finished_at timestamptz,
    version bigint NOT NULL DEFAULT 1,
    CONSTRAINT runtime_run_fire_uk UNIQUE (schedule_id, fire_key),
    CONSTRAINT runtime_run_fire_key_ck CHECK (fire_key <> ''),
    CONSTRAINT runtime_run_mode_ck CHECK (runtime_mode IN ('OPERATIONAL', 'HISTORICAL', 'REPLAY', 'SHADOW', 'PROSPECTIVE')),
    CONSTRAINT runtime_run_code_sha_ck CHECK (code_sha ~ '^[0-9a-f]{40}([0-9a-f]{24})?$'),
    CONSTRAINT runtime_run_config_hash_ck CHECK (config_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT runtime_run_schema_epoch_ck CHECK (schema_epoch = 'MRA_REFOUNDATION_1'),
    CONSTRAINT runtime_run_state_ck CHECK (state IN ('QUEUED', 'RUNNING', 'WAITING', 'SUCCEEDED', 'BLOCKED', 'FAILED', 'CANCELLED')),
    CONSTRAINT runtime_run_reason_ck CHECK (terminal_reason_code IS NULL OR terminal_reason_code ~ '^[A-Z][A-Z0-9_]{0,99}$'),
    CONSTRAINT runtime_run_terminal_reason_ck CHECK (
        (state IN ('BLOCKED', 'FAILED', 'CANCELLED') AND terminal_reason_code IS NOT NULL) OR
        (state NOT IN ('BLOCKED', 'FAILED', 'CANCELLED'))
    ),
    CONSTRAINT runtime_run_self_parent_ck CHECK (parent_run_id IS NULL OR parent_run_id <> run_id),
    CONSTRAINT runtime_run_self_original_ck CHECK (original_run_id IS NULL OR original_run_id <> run_id),
    CONSTRAINT runtime_run_timestamps_ck CHECK (
        (state = 'QUEUED' AND started_at IS NULL AND finished_at IS NULL) OR
        (state IN ('RUNNING', 'WAITING') AND started_at IS NOT NULL AND finished_at IS NULL) OR
        (state IN ('SUCCEEDED', 'BLOCKED', 'FAILED', 'CANCELLED') AND finished_at IS NOT NULL)
    ),
    CONSTRAINT runtime_run_version_ck CHECK (version > 0)
);
CREATE INDEX runtime_run_schedule_idx ON mra.runtime_run (schedule_id, created_at DESC);
CREATE INDEX runtime_run_config_artifact_idx ON mra.runtime_run (config_artifact_id)
    WHERE config_artifact_id IS NOT NULL;
CREATE INDEX runtime_run_parent_idx ON mra.runtime_run (parent_run_id)
    WHERE parent_run_id IS NOT NULL;
CREATE INDEX runtime_run_original_idx ON mra.runtime_run (original_run_id)
    WHERE original_run_id IS NOT NULL;
CREATE INDEX runtime_run_state_idx ON mra.runtime_run (state, created_at)
    WHERE state IN ('QUEUED', 'RUNNING', 'WAITING');

CREATE TABLE mra.runtime_step (
    step_id uuid PRIMARY KEY,
    run_id uuid NOT NULL REFERENCES mra.runtime_run(run_id) ON DELETE RESTRICT,
    step_key text NOT NULL,
    step_kind text NOT NULL,
    implementation text NOT NULL,
    implementation_version text NOT NULL,
    required boolean NOT NULL,
    ordinal integer NOT NULL,
    request_hash text NOT NULL,
    input_evidence_hash text,
    max_attempts smallint NOT NULL,
    retry_backoff_ms bigint[] NOT NULL,
    retryable_error_codes text[] NOT NULL,
    deadline_at timestamptz,
    external_effect_class text NOT NULL,
    state text NOT NULL,
    current_fence bigint NOT NULL DEFAULT 0,
    current_attempt_id uuid,
    ready_at timestamptz,
    terminal_reason_code text,
    branch_rule_code text,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    started_at timestamptz,
    finished_at timestamptz,
    version bigint NOT NULL DEFAULT 1,
    CONSTRAINT runtime_step_run_id_uk UNIQUE (run_id, step_id),
    CONSTRAINT runtime_step_run_key_uk UNIQUE (run_id, step_key),
    CONSTRAINT runtime_step_run_ordinal_uk UNIQUE (run_id, ordinal),
    CONSTRAINT runtime_step_key_ck CHECK (step_key ~ '^[a-z][a-z0-9_-]{0,99}$'),
    CONSTRAINT runtime_step_kind_ck CHECK (step_kind IN ('CAPTURE', 'NORMALIZE_PIT', 'FREEZE_UNIVERSE', 'ASSESS_ELIGIBILITY', 'REGISTER_DATASET', 'BUILD_CANDIDATE_SET', 'OPEN_DECISION_RUN', 'ASSESS_CONTEXT', 'SIGNAL_AND_FORECAST', 'DECIDE_AND_RISK', 'PERSIST_DECISION', 'SETTLE_OUTCOME', 'ATTRIBUTE', 'ASSESS_RESEARCH')),
    CONSTRAINT runtime_step_implementation_ck CHECK (implementation <> '' AND implementation_version <> ''),
    CONSTRAINT runtime_step_ordinal_ck CHECK (ordinal >= 0),
    CONSTRAINT runtime_step_request_hash_ck CHECK (request_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT runtime_step_input_hash_ck CHECK (input_evidence_hash IS NULL OR input_evidence_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT runtime_step_attempt_budget_ck CHECK (max_attempts BETWEEN 1 AND 64 AND cardinality(retry_backoff_ms) <= max_attempts - 1),
    CONSTRAINT runtime_step_backoff_ck CHECK (array_position(retry_backoff_ms, NULL) IS NULL AND 0 <= ALL (retry_backoff_ms)),
    CONSTRAINT runtime_step_retry_codes_ck CHECK (array_position(retryable_error_codes, NULL) IS NULL),
    CONSTRAINT runtime_step_effect_ck CHECK (external_effect_class IN ('NONE', 'PURE_READ', 'CONTENT_PUT', 'IDEMPOTENT_REMOTE_COMMAND', 'NON_IDEMPOTENT_REMOTE_COMMAND', 'OBSERVATION_ONLY')),
    CONSTRAINT runtime_step_state_ck CHECK (state IN ('PENDING', 'READY', 'CLAIMED', 'RUNNING', 'WAITING', 'SUCCEEDED', 'BLOCKED', 'FAILED', 'CANCELLED', 'SKIPPED')),
    CONSTRAINT runtime_step_fence_ck CHECK (current_fence >= 0),
    CONSTRAINT runtime_step_current_attempt_ck CHECK (
        (state IN ('CLAIMED', 'RUNNING') AND current_attempt_id IS NOT NULL) OR
        (state NOT IN ('CLAIMED', 'RUNNING') AND current_attempt_id IS NULL)
    ),
    CONSTRAINT runtime_step_reason_ck CHECK (terminal_reason_code IS NULL OR terminal_reason_code ~ '^[A-Z][A-Z0-9_]{0,99}$'),
    CONSTRAINT runtime_step_terminal_reason_ck CHECK (
        (state IN ('BLOCKED', 'FAILED', 'CANCELLED') AND terminal_reason_code IS NOT NULL) OR
        (state NOT IN ('BLOCKED', 'FAILED', 'CANCELLED'))
    ),
    CONSTRAINT runtime_step_skip_rule_ck CHECK (state <> 'SKIPPED' OR branch_rule_code IS NOT NULL),
    CONSTRAINT runtime_step_timestamps_ck CHECK (
        (state IN ('PENDING', 'READY', 'CLAIMED') AND finished_at IS NULL) OR
        (state IN ('RUNNING', 'WAITING') AND started_at IS NOT NULL AND finished_at IS NULL) OR
        (state IN ('SUCCEEDED', 'BLOCKED', 'FAILED', 'CANCELLED', 'SKIPPED') AND finished_at IS NOT NULL)
    ),
    CONSTRAINT runtime_step_version_ck CHECK (version > 0)
);
CREATE INDEX runtime_step_run_idx ON mra.runtime_step (run_id, state, ordinal);
CREATE INDEX runtime_step_due_idx ON mra.runtime_step (ready_at, run_id, ordinal)
    WHERE state = 'READY';

CREATE TABLE mra.runtime_step_dependency (
    run_id uuid NOT NULL REFERENCES mra.runtime_run(run_id) ON DELETE RESTRICT,
    predecessor_step_id uuid NOT NULL,
    successor_step_id uuid NOT NULL,
    dependency_kind text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (run_id, predecessor_step_id, successor_step_id, dependency_kind),
    CONSTRAINT runtime_step_dependency_predecessor_fk FOREIGN KEY (run_id, predecessor_step_id)
        REFERENCES mra.runtime_step(run_id, step_id) ON DELETE RESTRICT,
    CONSTRAINT runtime_step_dependency_successor_fk FOREIGN KEY (run_id, successor_step_id)
        REFERENCES mra.runtime_step(run_id, step_id) ON DELETE RESTRICT,
    CONSTRAINT runtime_step_dependency_no_self_ck CHECK (predecessor_step_id <> successor_step_id),
    CONSTRAINT runtime_step_dependency_kind_ck CHECK (dependency_kind IN ('REQUIRED_SUCCESS', 'TERMINAL'))
);
CREATE INDEX runtime_step_dependency_predecessor_idx ON mra.runtime_step_dependency (predecessor_step_id, successor_step_id);
CREATE INDEX runtime_step_dependency_successor_idx ON mra.runtime_step_dependency (run_id, successor_step_id, predecessor_step_id);

CREATE FUNCTION mra.validate_runtime_decision_chain()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    affected_run_id uuid := COALESCE(NEW.run_id, OLD.run_id);
    chain_count integer;
    build_step record;
    open_step record;
    context_step record;
BEGIN
    SELECT count(*)
    INTO chain_count
    FROM mra.runtime_step
    WHERE run_id = affected_run_id
      AND step_kind IN (
          'BUILD_CANDIDATE_SET', 'OPEN_DECISION_RUN', 'ASSESS_CONTEXT'
      );
    IF chain_count = 0 THEN
        RETURN COALESCE(NEW, OLD);
    END IF;
    IF chain_count <> 3 THEN
        RAISE EXCEPTION 'Runtime Decision chain requires exactly three steps'
            USING ERRCODE = '23514';
    END IF;
    SELECT step_id, ordinal, required
    INTO build_step
    FROM mra.runtime_step
    WHERE run_id = affected_run_id
      AND step_kind = 'BUILD_CANDIDATE_SET';
    SELECT step_id, ordinal, required
    INTO open_step
    FROM mra.runtime_step
    WHERE run_id = affected_run_id
      AND step_kind = 'OPEN_DECISION_RUN';
    SELECT step_id, ordinal, required
    INTO context_step
    FROM mra.runtime_step
    WHERE run_id = affected_run_id
      AND step_kind = 'ASSESS_CONTEXT';
    IF build_step.step_id IS NULL
       OR open_step.step_id IS NULL
       OR context_step.step_id IS NULL
       OR NOT build_step.required
       OR NOT open_step.required
       OR NOT context_step.required
       OR NOT (
           build_step.ordinal < open_step.ordinal
           AND open_step.ordinal < context_step.ordinal
       ) THEN
        RAISE EXCEPTION 'Runtime Decision chain shape is invalid'
            USING ERRCODE = '23514';
    END IF;
    IF NOT EXISTS (
        SELECT 1
        FROM mra.runtime_step_dependency
        WHERE run_id = affected_run_id
          AND predecessor_step_id = build_step.step_id
          AND successor_step_id = open_step.step_id
          AND dependency_kind = 'REQUIRED_SUCCESS'
    ) OR NOT EXISTS (
        SELECT 1
        FROM mra.runtime_step_dependency
        WHERE run_id = affected_run_id
          AND predecessor_step_id = open_step.step_id
          AND successor_step_id = context_step.step_id
          AND dependency_kind = 'REQUIRED_SUCCESS'
    ) OR EXISTS (
        SELECT 1
        FROM mra.runtime_step_dependency
        WHERE run_id = affected_run_id
          AND predecessor_step_id = build_step.step_id
          AND successor_step_id = context_step.step_id
    ) THEN
        RAISE EXCEPTION 'Runtime Decision chain edge is invalid'
            USING ERRCODE = '23514';
    END IF;
    RETURN COALESCE(NEW, OLD);
END;
$$;

CREATE CONSTRAINT TRIGGER runtime_step_decision_chain_guard
AFTER INSERT OR UPDATE OR DELETE ON mra.runtime_step
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION mra.validate_runtime_decision_chain();

CREATE CONSTRAINT TRIGGER runtime_dependency_decision_chain_guard
AFTER INSERT OR UPDATE OR DELETE ON mra.runtime_step_dependency
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION mra.validate_runtime_decision_chain();

CREATE TABLE mra.command_receipt (
    receipt_id uuid PRIMARY KEY,
    command_kind text NOT NULL,
    scope_id text NOT NULL,
    idempotency_key text NOT NULL,
    request_hash text NOT NULL,
    status text NOT NULL,
    runtime_step_id uuid,
    runtime_attempt_id uuid,
    fence_token bigint,
    result_aggregate_kind text,
    result_aggregate_id text,
    result_aggregate_version bigint,
    result_hash text,
    result_artifact_id uuid REFERENCES mra.artifact(artifact_id) ON DELETE RESTRICT,
    error_code text,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    completed_at timestamptz,
    CONSTRAINT command_receipt_idempotency_uk UNIQUE (command_kind, scope_id, idempotency_key),
    CONSTRAINT command_receipt_kind_ck CHECK (command_kind ~ '^[A-Z][A-Z0-9_]{0,99}$'),
    CONSTRAINT command_receipt_scope_ck CHECK (scope_id <> ''),
    CONSTRAINT command_receipt_key_ck CHECK (idempotency_key ~ '^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$'),
    CONSTRAINT command_receipt_request_hash_ck CHECK (request_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT command_receipt_status_ck CHECK (status IN ('PENDING', 'SUCCEEDED', 'BLOCKED', 'FAILED')),
    CONSTRAINT command_receipt_fence_ck CHECK (
        (runtime_step_id IS NULL AND runtime_attempt_id IS NULL AND fence_token IS NULL) OR
        (runtime_step_id IS NOT NULL AND runtime_attempt_id IS NOT NULL AND fence_token > 0)
    ),
    CONSTRAINT command_receipt_result_hash_ck CHECK (result_hash IS NULL OR result_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT command_receipt_error_ck CHECK (error_code IS NULL OR error_code ~ '^[A-Z][A-Z0-9_]{0,99}$'),
    CONSTRAINT command_receipt_terminal_ck CHECK (
        (status = 'PENDING' AND completed_at IS NULL) OR
        (status <> 'PENDING' AND completed_at IS NOT NULL)
    ),
    CONSTRAINT command_receipt_result_ck CHECK (
        (status = 'PENDING'
         AND result_aggregate_kind IS NULL AND result_aggregate_id IS NULL
         AND result_aggregate_version IS NULL AND result_hash IS NULL
         AND result_artifact_id IS NULL AND error_code IS NULL)
        OR
        (status = 'SUCCEEDED'
         AND result_aggregate_kind IS NOT NULL AND result_aggregate_id IS NOT NULL
         AND result_aggregate_version IS NOT NULL AND result_hash IS NOT NULL
         AND error_code IS NULL)
        OR
        (status IN ('BLOCKED', 'FAILED')
         AND result_aggregate_kind IS NULL AND result_aggregate_id IS NULL
         AND result_aggregate_version IS NULL AND result_hash IS NULL
         AND result_artifact_id IS NULL AND error_code IS NOT NULL)
    )
);
CREATE INDEX command_receipt_runtime_step_idx ON mra.command_receipt (runtime_step_id, created_at)
    WHERE runtime_step_id IS NOT NULL;
CREATE INDEX command_receipt_result_artifact_idx ON mra.command_receipt (result_artifact_id)
    WHERE result_artifact_id IS NOT NULL;

CREATE TABLE mra.runtime_attempt (
    attempt_id uuid PRIMARY KEY,
    step_id uuid NOT NULL REFERENCES mra.runtime_step(step_id) ON DELETE RESTRICT,
    attempt_no smallint NOT NULL,
    fence_token bigint NOT NULL,
    lease_owner text NOT NULL,
    lease_acquired_at timestamptz NOT NULL,
    lease_until timestamptz NOT NULL,
    last_heartbeat_at timestamptz NOT NULL,
    state text NOT NULL,
    external_effect_class text NOT NULL,
    error_class text,
    error_code text,
    result_receipt_id uuid REFERENCES mra.command_receipt(receipt_id) ON DELETE RESTRICT,
    result_hash text,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    started_at timestamptz,
    finished_at timestamptz,
    CONSTRAINT runtime_attempt_number_uk UNIQUE (step_id, attempt_no),
    CONSTRAINT runtime_attempt_fence_uk UNIQUE (step_id, fence_token),
    CONSTRAINT runtime_attempt_claim_identity_uk UNIQUE (attempt_id, step_id, fence_token),
    CONSTRAINT runtime_attempt_no_ck CHECK (attempt_no > 0),
    CONSTRAINT runtime_attempt_fence_ck CHECK (fence_token > 0),
    CONSTRAINT runtime_attempt_owner_ck CHECK (lease_owner <> ''),
    CONSTRAINT runtime_attempt_lease_ck CHECK (lease_until > lease_acquired_at AND last_heartbeat_at >= lease_acquired_at),
    CONSTRAINT runtime_attempt_state_ck CHECK (state IN ('CLAIMED', 'RUNNING', 'SUCCEEDED', 'FAILED_RETRYABLE', 'FAILED_TERMINAL', 'ABANDONED', 'RECONCILIATION_REQUIRED')),
    CONSTRAINT runtime_attempt_effect_ck CHECK (external_effect_class IN ('NONE', 'PURE_READ', 'CONTENT_PUT', 'IDEMPOTENT_REMOTE_COMMAND', 'NON_IDEMPOTENT_REMOTE_COMMAND', 'OBSERVATION_ONLY')),
    CONSTRAINT runtime_attempt_error_class_ck CHECK (error_class IS NULL OR error_class ~ '^[A-Z][A-Z0-9_]{0,99}$'),
    CONSTRAINT runtime_attempt_error_code_ck CHECK (error_code IS NULL OR error_code ~ '^[A-Z][A-Z0-9_]{0,99}$'),
    CONSTRAINT runtime_attempt_result_hash_ck CHECK (result_hash IS NULL OR result_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT runtime_attempt_result_ck CHECK (
        (state IN ('CLAIMED', 'RUNNING')
         AND result_receipt_id IS NULL AND result_hash IS NULL
         AND error_class IS NULL AND error_code IS NULL)
        OR
        (state = 'SUCCEEDED'
         AND result_receipt_id IS NOT NULL AND result_hash IS NOT NULL
         AND error_class IS NULL AND error_code IS NULL)
        OR
        (state IN ('FAILED_RETRYABLE', 'FAILED_TERMINAL', 'ABANDONED', 'RECONCILIATION_REQUIRED')
         AND result_receipt_id IS NOT NULL
         AND error_class IS NOT NULL AND error_code IS NOT NULL)
    ),
    CONSTRAINT runtime_attempt_timestamps_ck CHECK (
        (state = 'CLAIMED' AND started_at IS NULL AND finished_at IS NULL) OR
        (state = 'RUNNING' AND started_at IS NOT NULL AND finished_at IS NULL) OR
        (state IN ('SUCCEEDED', 'FAILED_RETRYABLE', 'FAILED_TERMINAL', 'ABANDONED', 'RECONCILIATION_REQUIRED') AND finished_at IS NOT NULL)
    )
);
CREATE UNIQUE INDEX runtime_attempt_one_live_idx ON mra.runtime_attempt (step_id)
    WHERE state IN ('CLAIMED', 'RUNNING');
CREATE INDEX runtime_attempt_lease_expiry_idx ON mra.runtime_attempt (lease_until, step_id)
    WHERE state IN ('CLAIMED', 'RUNNING');
CREATE INDEX runtime_attempt_result_receipt_idx ON mra.runtime_attempt (result_receipt_id)
    WHERE result_receipt_id IS NOT NULL;

ALTER TABLE mra.runtime_step
    ADD CONSTRAINT runtime_step_current_attempt_fk
    FOREIGN KEY (current_attempt_id, step_id, current_fence)
    REFERENCES mra.runtime_attempt(attempt_id, step_id, fence_token) ON DELETE RESTRICT;
CREATE INDEX runtime_step_current_claim_idx
    ON mra.runtime_step (current_attempt_id, step_id, current_fence)
    WHERE current_attempt_id IS NOT NULL;

ALTER TABLE mra.command_receipt
    ADD CONSTRAINT command_receipt_runtime_claim_fk
    FOREIGN KEY (runtime_attempt_id, runtime_step_id, fence_token)
    REFERENCES mra.runtime_attempt(attempt_id, step_id, fence_token) ON DELETE RESTRICT;
CREATE INDEX command_receipt_runtime_claim_idx
    ON mra.command_receipt (runtime_attempt_id, runtime_step_id, fence_token)
    WHERE runtime_attempt_id IS NOT NULL;

ALTER TABLE mra.artifact_verification
    ADD CONSTRAINT artifact_verification_receipt_fk
    FOREIGN KEY (command_receipt_id) REFERENCES mra.command_receipt(receipt_id) ON DELETE RESTRICT;

CREATE TABLE mra.audit_event (
    audit_event_id uuid PRIMARY KEY,
    command_receipt_id uuid REFERENCES mra.command_receipt(receipt_id) ON DELETE RESTRICT,
    runtime_step_id uuid REFERENCES mra.runtime_step(step_id) ON DELETE RESTRICT,
    fence_token bigint,
    actor_type text NOT NULL,
    actor_id text NOT NULL,
    aggregate_kind text NOT NULL,
    aggregate_id text NOT NULL,
    action text NOT NULL,
    reason_code text NOT NULL,
    event_at timestamptz NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    before_version bigint,
    after_version bigint,
    CONSTRAINT audit_event_runtime_fence_ck CHECK (
        (runtime_step_id IS NULL AND fence_token IS NULL) OR
        (runtime_step_id IS NOT NULL AND fence_token > 0)
    ),
    CONSTRAINT audit_event_actor_type_ck CHECK (actor_type IN ('SYSTEM', 'OPERATOR', 'WORKER')),
    CONSTRAINT audit_event_actor_id_ck CHECK (actor_id <> ''),
    CONSTRAINT audit_event_aggregate_kind_ck CHECK (aggregate_kind ~ '^[A-Z][A-Z0-9_]{0,99}$'),
    CONSTRAINT audit_event_aggregate_id_ck CHECK (aggregate_id <> ''),
    CONSTRAINT audit_event_action_ck CHECK (action ~ '^[A-Z][A-Z0-9_]{0,99}$'),
    CONSTRAINT audit_event_reason_ck CHECK (reason_code ~ '^[A-Z][A-Z0-9_]{0,99}$'),
    CONSTRAINT audit_event_versions_ck CHECK (
        (before_version IS NULL OR before_version >= 0) AND
        (after_version IS NULL OR after_version >= 0)
    )
);
CREATE INDEX audit_event_receipt_idx ON mra.audit_event (command_receipt_id, recorded_at)
    WHERE command_receipt_id IS NOT NULL;
CREATE INDEX audit_event_runtime_step_idx ON mra.audit_event (runtime_step_id, recorded_at)
    WHERE runtime_step_id IS NOT NULL;
CREATE INDEX audit_event_aggregate_idx ON mra.audit_event (aggregate_kind, aggregate_id, recorded_at);

ALTER TABLE mra.candidate_set
    ADD CONSTRAINT candidate_set_decision_authority_uk UNIQUE (
        candidate_set_id, content_sha256, dataset_id, candidate_policy_id,
        decision_time, population_count, selected_count,
        ranked_not_selected_count, unrankable_count
    );

ALTER TABLE mra.candidate
    ADD CONSTRAINT candidate_decision_scope_uk UNIQUE (
        candidate_id, candidate_set_id, instrument_id, disposition
    );

ALTER TABLE mra.target_checkpoint
    ADD CONSTRAINT target_checkpoint_decision_reference_uk UNIQUE (
        target_checkpoint_id, target_definition_id, content_sha256,
        ordinal, checkpoint_role, timeframe, price_basis, value_field,
        reference_rule, availability_rule, finality_rule
    );

ALTER TABLE mra.target_definition
    ADD CONSTRAINT target_definition_decision_authority_uk UNIQUE (
        target_definition_id, target_code, version, content_sha256
    );

ALTER TABLE mra.provider_product
    ADD CONSTRAINT provider_product_decision_authority_uk UNIQUE (
        provider_product_id, provider_id, product_code, revision,
        decision_visibility_policy, source_availability_policy
    );

ALTER TABLE mra.provider_product
    ADD CONSTRAINT provider_product_decision_scope_uk UNIQUE (
        provider_product_id, provider_id
    );

ALTER TABLE mra.market_bar_revision
    ADD CONSTRAINT market_bar_decision_reference_uk UNIQUE (
        bar_revision_id, provider_product_id, capture_id, instrument_id,
        session_id, timeframe, price_basis, event_start, event_end,
        revision, recorded_at, known_at
    );

ALTER TABLE mra.source_gap
    ADD CONSTRAINT source_gap_decision_reference_uk UNIQUE (
        gap_id, provider_product_id, capture_id, instrument_id, session_id,
        timeframe, price_basis, event_start, event_end,
        gap_kind, reason_code, recorded_at, known_at
    );

ALTER TABLE mra.runtime_run
    ADD CONSTRAINT runtime_run_decision_authority_uk UNIQUE (
        run_id, runtime_mode, decision_time, code_sha,
        config_artifact_id, config_hash
    );

ALTER TABLE mra.runtime_step
    ADD CONSTRAINT runtime_step_decision_authority_uk UNIQUE (
        step_id, run_id, step_key, step_kind
    );

ALTER TABLE mra.command_receipt
    ADD CONSTRAINT command_receipt_decision_claim_uk UNIQUE (
        receipt_id, command_kind, scope_id, idempotency_key, request_hash,
        runtime_step_id, runtime_attempt_id, fence_token
    );

CREATE TABLE mra.decision_run (
    decision_run_id uuid PRIMARY KEY,
    status text NOT NULL,
    candidate_set_id uuid NOT NULL,
    candidate_set_content_sha256 text NOT NULL,
    dataset_id uuid NOT NULL,
    candidate_policy_id uuid NOT NULL,
    candidate_count integer NOT NULL,
    selected_count integer NOT NULL,
    ranked_not_selected_count integer NOT NULL,
    unrankable_count integer NOT NULL,
    candidate_roster_sha256 text NOT NULL,
    target_count integer NOT NULL,
    target_roster_sha256 text NOT NULL,
    commitment_count bigint NOT NULL,
    reference_count bigint NOT NULL,
    commitment_roster_sha256 text NOT NULL,
    runtime_mode text NOT NULL,
    decision_time timestamptz NOT NULL,
    commitment_recorded_at timestamptz NOT NULL,
    request_received_at timestamptz NOT NULL,
    runtime_run_id uuid NOT NULL,
    runtime_step_id uuid NOT NULL,
    runtime_attempt_id uuid NOT NULL,
    runtime_fence_token bigint NOT NULL,
    runtime_step_key text NOT NULL,
    runtime_step_kind text NOT NULL,
    code_sha text NOT NULL,
    config_artifact_id uuid NOT NULL,
    config_hash text NOT NULL,
    request_kind text NOT NULL,
    request_scope_id text NOT NULL,
    request_identity text NOT NULL,
    request_sha256 text NOT NULL,
    command_receipt_id uuid NOT NULL,
    created_by_actor_type text NOT NULL,
    created_by_actor_id text NOT NULL,
    creation_reason_code text NOT NULL,
    definition_summary_sha256 text NOT NULL,
    created_at timestamptz NOT NULL,
    CONSTRAINT decision_run_candidate_set_uk UNIQUE (candidate_set_id),
    CONSTRAINT decision_run_exact_identity_uk UNIQUE (
        decision_run_id, candidate_set_id, decision_time, runtime_mode,
        commitment_recorded_at
    ),
    CONSTRAINT decision_run_request_uk UNIQUE (
        candidate_set_id, request_identity
    ),
    CONSTRAINT decision_run_receipt_uk UNIQUE (command_receipt_id),
    CONSTRAINT decision_run_candidate_set_fk FOREIGN KEY (
        candidate_set_id, candidate_set_content_sha256,
        dataset_id, candidate_policy_id, decision_time, candidate_count,
        selected_count, ranked_not_selected_count, unrankable_count
    ) REFERENCES mra.candidate_set(
        candidate_set_id, content_sha256, dataset_id, candidate_policy_id,
        decision_time, population_count, selected_count,
        ranked_not_selected_count, unrankable_count
    ) ON DELETE RESTRICT,
    CONSTRAINT decision_run_runtime_run_fk FOREIGN KEY (
        runtime_run_id, runtime_mode, decision_time, code_sha,
        config_artifact_id, config_hash
    ) REFERENCES mra.runtime_run(
        run_id, runtime_mode, decision_time, code_sha,
        config_artifact_id, config_hash
    ) ON DELETE RESTRICT,
    CONSTRAINT decision_run_runtime_step_fk FOREIGN KEY (
        runtime_step_id, runtime_run_id, runtime_step_key, runtime_step_kind
    ) REFERENCES mra.runtime_step(
        step_id, run_id, step_key, step_kind
    ) ON DELETE RESTRICT,
    CONSTRAINT decision_run_runtime_attempt_fk FOREIGN KEY (
        runtime_attempt_id, runtime_step_id, runtime_fence_token
    ) REFERENCES mra.runtime_attempt(
        attempt_id, step_id, fence_token
    ) ON DELETE RESTRICT,
    CONSTRAINT decision_run_receipt_claim_fk FOREIGN KEY (
        command_receipt_id, request_kind, request_scope_id,
        request_identity, request_sha256, runtime_step_id,
        runtime_attempt_id, runtime_fence_token
    ) REFERENCES mra.command_receipt(
        receipt_id, command_kind, scope_id, idempotency_key, request_hash,
        runtime_step_id, runtime_attempt_id, fence_token
    ) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT decision_run_status_ck CHECK (status = 'OPENED'),
    CONSTRAINT decision_run_counts_ck CHECK (
        candidate_count >= 0
        AND selected_count >= 0
        AND ranked_not_selected_count >= 0
        AND unrankable_count >= 0
        AND candidate_count = selected_count
            + ranked_not_selected_count + unrankable_count
        AND target_count > 0
        AND commitment_count = candidate_count::bigint * target_count::bigint
        AND reference_count = commitment_count
    ),
    CONSTRAINT decision_run_hashes_ck CHECK (
        candidate_set_content_sha256 ~ '^[0-9a-f]{64}$'
        AND candidate_roster_sha256 ~ '^[0-9a-f]{64}$'
        AND target_roster_sha256 ~ '^[0-9a-f]{64}$'
        AND commitment_roster_sha256 ~ '^[0-9a-f]{64}$'
        AND request_sha256 ~ '^[0-9a-f]{64}$'
        AND definition_summary_sha256 ~ '^[0-9a-f]{64}$'
        AND config_hash ~ '^[0-9a-f]{64}$'
        AND code_sha ~ '^[0-9a-f]{40}([0-9a-f]{24})?$'
    ),
    CONSTRAINT decision_run_runtime_ck CHECK (
        runtime_mode IN (
            'OPERATIONAL', 'HISTORICAL', 'REPLAY', 'SHADOW', 'PROSPECTIVE'
        )
        AND runtime_step_kind = 'OPEN_DECISION_RUN'
        AND runtime_step_key ~ '^[a-z][a-z0-9_-]{0,99}$'
        AND runtime_fence_token > 0
    ),
    CONSTRAINT decision_run_request_ck CHECK (
        request_kind = 'OPEN_DECISION_RUN'
        AND request_scope_id = candidate_set_id::text
        AND request_identity ~ '^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$'
        AND created_by_actor_type IN ('SYSTEM', 'OPERATOR', 'WORKER')
        AND created_by_actor_id <> ''
        AND creation_reason_code ~ '^[A-Z][A-Z0-9_]{0,99}$'
    ),
    CONSTRAINT decision_run_time_ck CHECK (
        request_received_at <= commitment_recorded_at
        AND created_at = commitment_recorded_at
    ),
    CONSTRAINT decision_run_definition_summary_ck CHECK (
        definition_summary_sha256 =
            mra.decision_run_definition_summary_sha256(
                candidate_count, candidate_roster_sha256,
                candidate_set_content_sha256, candidate_set_id,
                commitment_count, commitment_roster_sha256,
                decision_time, reference_count, request_sha256,
                runtime_mode, target_count, target_roster_sha256
            )
    )
);
CREATE INDEX decision_run_candidate_set_idx
    ON mra.decision_run (candidate_set_id, decision_run_id);
CREATE INDEX decision_run_request_idx
    ON mra.decision_run (
        request_kind, request_scope_id, request_identity, request_sha256
    );
CREATE INDEX decision_run_runtime_idx
    ON mra.decision_run (
        runtime_run_id, runtime_step_id, runtime_attempt_id,
        runtime_fence_token
    );
CREATE INDEX decision_run_candidate_fk_idx
    ON mra.decision_run (
        candidate_set_id, candidate_set_content_sha256,
        dataset_id, candidate_policy_id, decision_time, candidate_count,
        selected_count, ranked_not_selected_count, unrankable_count
    );
CREATE INDEX decision_run_runtime_run_fk_idx
    ON mra.decision_run (
        runtime_run_id, runtime_mode, decision_time, code_sha,
        config_artifact_id, config_hash
    );
CREATE INDEX decision_run_runtime_step_fk_idx
    ON mra.decision_run (
        runtime_step_id, runtime_run_id, runtime_step_key, runtime_step_kind
    );
CREATE INDEX decision_run_runtime_attempt_fk_idx
    ON mra.decision_run (
        runtime_attempt_id, runtime_step_id, runtime_fence_token
    );
CREATE INDEX decision_run_receipt_claim_fk_idx
    ON mra.decision_run (
        command_receipt_id, request_kind, request_scope_id,
        request_identity, request_sha256, runtime_step_id,
        runtime_attempt_id, runtime_fence_token
    );

CREATE TABLE mra.decision_run_target (
    decision_run_target_id uuid PRIMARY KEY,
    decision_run_id uuid NOT NULL,
    ordinal integer NOT NULL,
    target_definition_id uuid NOT NULL,
    target_code text NOT NULL,
    target_version integer NOT NULL,
    target_definition_sha256 text NOT NULL,
    target_checkpoint_id uuid NOT NULL,
    target_checkpoint_sha256 text NOT NULL,
    target_checkpoint_ordinal integer NOT NULL,
    target_checkpoint_role text NOT NULL,
    timeframe text NOT NULL,
    price_basis text NOT NULL,
    value_field text NOT NULL,
    reference_rule text NOT NULL,
    availability_rule text NOT NULL,
    finality_rule text NOT NULL,
    reference_provider_product_id uuid NOT NULL,
    reference_provider_id uuid NOT NULL,
    reference_provider_product_code text NOT NULL,
    reference_provider_product_revision integer NOT NULL,
    decision_visibility_policy text NOT NULL,
    source_availability_policy text NOT NULL,
    commitment_recorded_at timestamptz NOT NULL,
    content_sha256 text NOT NULL,
    created_at timestamptz NOT NULL,
    CONSTRAINT decision_run_target_ordinal_uk UNIQUE (
        decision_run_id, ordinal
    ),
    CONSTRAINT decision_run_target_definition_uk UNIQUE (
        decision_run_id, target_definition_id
    ),
    CONSTRAINT decision_run_target_scope_uk UNIQUE (
        decision_run_target_id, decision_run_id, target_definition_id,
        target_checkpoint_id, reference_provider_product_id,
        commitment_recorded_at
    ),
    CONSTRAINT decision_run_target_run_fk FOREIGN KEY (
        decision_run_id
    ) REFERENCES mra.decision_run(decision_run_id)
      ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT decision_run_target_definition_fk FOREIGN KEY (
        target_definition_id, target_code, target_version,
        target_definition_sha256
    ) REFERENCES mra.target_definition(
        target_definition_id, target_code, version, content_sha256
    ) ON DELETE RESTRICT,
    CONSTRAINT decision_run_target_checkpoint_fk FOREIGN KEY (
        target_checkpoint_id, target_definition_id,
        target_checkpoint_sha256, target_checkpoint_ordinal,
        target_checkpoint_role, timeframe, price_basis, value_field,
        reference_rule, availability_rule, finality_rule
    ) REFERENCES mra.target_checkpoint(
        target_checkpoint_id, target_definition_id, content_sha256,
        ordinal, checkpoint_role, timeframe, price_basis, value_field,
        reference_rule, availability_rule, finality_rule
    ) ON DELETE RESTRICT,
    CONSTRAINT decision_run_target_provider_product_fk FOREIGN KEY (
        reference_provider_product_id, reference_provider_id,
        reference_provider_product_code,
        reference_provider_product_revision,
        decision_visibility_policy, source_availability_policy
    ) REFERENCES mra.provider_product(
        provider_product_id, provider_id, product_code, revision,
        decision_visibility_policy, source_availability_policy
    ) ON DELETE RESTRICT,
    CONSTRAINT decision_run_target_shape_ck CHECK (
        ordinal > 0
        AND target_code ~ '^[a-z][a-z0-9_]{0,99}$'
        AND target_version > 0
        AND target_checkpoint_ordinal > 0
        AND target_checkpoint_role = 'DECISION_REFERENCE'
        AND reference_provider_product_revision > 0
        AND decision_visibility_policy = 'KNOWN_AT'
        AND content_sha256 ~ '^[0-9a-f]{64}$'
        AND target_definition_sha256 ~ '^[0-9a-f]{64}$'
        AND target_checkpoint_sha256 ~ '^[0-9a-f]{64}$'
        AND created_at = commitment_recorded_at
    ),
    CONSTRAINT decision_run_target_content_ck CHECK (
        content_sha256 = mra.decision_run_target_content_sha256(
            ordinal, reference_provider_id,
            reference_provider_product_id,
            reference_provider_product_revision,
            target_checkpoint_id, target_checkpoint_sha256,
            target_definition_id, target_definition_sha256,
            target_version
        )
    )
);
CREATE INDEX decision_run_target_replay_idx
    ON mra.decision_run_target (
        decision_run_id, ordinal, decision_run_target_id
    );
CREATE INDEX decision_run_target_definition_idx
    ON mra.decision_run_target (
        target_definition_id, target_version,
        target_definition_sha256, decision_run_id
    );
CREATE INDEX decision_run_target_definition_fk_idx
    ON mra.decision_run_target (
        target_definition_id, target_code, target_version,
        target_definition_sha256
    );
CREATE INDEX decision_run_target_checkpoint_fk_idx
    ON mra.decision_run_target (
        target_checkpoint_id, target_definition_id,
        target_checkpoint_sha256, target_checkpoint_ordinal,
        target_checkpoint_role, timeframe, price_basis, value_field,
        reference_rule, availability_rule, finality_rule
    );
CREATE INDEX decision_run_target_product_fk_idx
    ON mra.decision_run_target (
        reference_provider_product_id, reference_provider_id,
        reference_provider_product_code,
        reference_provider_product_revision,
        decision_visibility_policy, source_availability_policy
    );

CREATE TABLE mra.decision_target_commitment (
    commitment_id uuid PRIMARY KEY,
    decision_run_id uuid NOT NULL,
    decision_run_target_id uuid NOT NULL,
    candidate_set_id uuid NOT NULL,
    candidate_id uuid NOT NULL,
    instrument_id uuid NOT NULL,
    candidate_disposition text NOT NULL,
    target_definition_id uuid NOT NULL,
    target_checkpoint_id uuid NOT NULL,
    reference_provider_product_id uuid NOT NULL,
    decision_time timestamptz NOT NULL,
    runtime_mode text NOT NULL,
    commitment_recorded_at timestamptz NOT NULL,
    decision_reference_observation_id uuid NOT NULL,
    decision_reference_sha256 text NOT NULL,
    content_sha256 text NOT NULL,
    created_at timestamptz NOT NULL,
    CONSTRAINT decision_commitment_candidate_target_uk UNIQUE (
        decision_run_id, candidate_id, target_definition_id
    ),
    CONSTRAINT decision_commitment_scope_uk UNIQUE (
        commitment_id, decision_run_id, decision_run_target_id,
        candidate_set_id, candidate_id, target_definition_id,
        target_checkpoint_id, instrument_id,
        reference_provider_product_id, decision_time, runtime_mode,
        commitment_recorded_at
    ),
    CONSTRAINT decision_commitment_reference_scope_uk UNIQUE (
        decision_reference_observation_id, commitment_id,
        decision_run_id, decision_run_target_id, candidate_set_id,
        candidate_id, target_definition_id, target_checkpoint_id,
        instrument_id, reference_provider_product_id, decision_time,
        runtime_mode, commitment_recorded_at, decision_reference_sha256
    ),
    CONSTRAINT decision_commitment_candidate_fk FOREIGN KEY (
        candidate_id, candidate_set_id, instrument_id,
        candidate_disposition
    ) REFERENCES mra.candidate(
        candidate_id, candidate_set_id, instrument_id, disposition
    ) ON DELETE RESTRICT,
    CONSTRAINT decision_commitment_run_target_fk FOREIGN KEY (
        decision_run_target_id, decision_run_id, target_definition_id,
        target_checkpoint_id, reference_provider_product_id,
        commitment_recorded_at
    ) REFERENCES mra.decision_run_target(
        decision_run_target_id, decision_run_id, target_definition_id,
        target_checkpoint_id, reference_provider_product_id,
        commitment_recorded_at
    ) ON DELETE RESTRICT,
    CONSTRAINT decision_commitment_run_scope_fk FOREIGN KEY (
        decision_run_id, candidate_set_id, decision_time,
        runtime_mode, commitment_recorded_at
    ) REFERENCES mra.decision_run(
        decision_run_id, candidate_set_id, decision_time,
        runtime_mode, commitment_recorded_at
    ) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT decision_commitment_shape_ck CHECK (
        candidate_disposition IN (
            'SELECTED', 'RANKED_NOT_SELECTED', 'UNRANKABLE'
        )
        AND runtime_mode IN (
            'OPERATIONAL', 'HISTORICAL', 'REPLAY', 'SHADOW', 'PROSPECTIVE'
        )
        AND decision_reference_sha256 ~ '^[0-9a-f]{64}$'
        AND content_sha256 ~ '^[0-9a-f]{64}$'
        AND created_at = commitment_recorded_at
    ),
    CONSTRAINT decision_commitment_content_ck CHECK (
        content_sha256 = mra.decision_commitment_content_sha256(
            candidate_disposition, candidate_id,
            decision_reference_observation_id,
            decision_reference_sha256, decision_run_target_id,
            instrument_id, runtime_mode, target_definition_id
        )
    )
);
CREATE INDEX decision_commitment_cross_product_idx
    ON mra.decision_target_commitment (
        decision_run_id, decision_run_target_id, candidate_id
    );
CREATE INDEX decision_commitment_candidate_idx
    ON mra.decision_target_commitment (
        candidate_set_id, candidate_id, decision_run_id
    );
CREATE INDEX decision_commitment_target_idx
    ON mra.decision_target_commitment (
        target_definition_id, decision_run_id, candidate_id
    );
CREATE INDEX decision_commitment_candidate_fk_idx
    ON mra.decision_target_commitment (
        candidate_id, candidate_set_id, instrument_id,
        candidate_disposition
    );
CREATE INDEX decision_commitment_run_target_fk_idx
    ON mra.decision_target_commitment (
        decision_run_target_id, decision_run_id, target_definition_id,
        target_checkpoint_id, reference_provider_product_id,
        commitment_recorded_at
    );
CREATE INDEX decision_commitment_run_scope_fk_idx
    ON mra.decision_target_commitment (
        decision_run_id, candidate_set_id, decision_time,
        runtime_mode, commitment_recorded_at
    );

CREATE TABLE mra.decision_reference_observation (
    decision_reference_observation_id uuid PRIMARY KEY,
    commitment_id uuid NOT NULL,
    decision_run_id uuid NOT NULL,
    decision_run_target_id uuid NOT NULL,
    candidate_set_id uuid NOT NULL,
    candidate_id uuid NOT NULL,
    target_definition_id uuid NOT NULL,
    target_checkpoint_id uuid NOT NULL,
    instrument_id uuid NOT NULL,
    reference_provider_product_id uuid NOT NULL,
    reference_provider_id uuid NOT NULL,
    capture_id uuid NOT NULL,
    session_id uuid NOT NULL,
    timeframe text NOT NULL,
    price_basis text NOT NULL,
    value_field text NOT NULL,
    event_start timestamptz NOT NULL,
    event_end timestamptz NOT NULL,
    observation_time timestamptz NOT NULL,
    source_recorded_at timestamptz NOT NULL,
    known_at timestamptz NOT NULL,
    decision_time timestamptz NOT NULL,
    runtime_mode text NOT NULL,
    commitment_recorded_at timestamptz NOT NULL,
    source_kind text NOT NULL,
    value_status text NOT NULL,
    availability_status text NOT NULL,
    finality_status text NOT NULL,
    decimal_value numeric,
    bar_revision_id uuid,
    bar_revision integer,
    source_gap_id uuid,
    source_gap_kind text,
    source_gap_reason_code text,
    content_sha256 text NOT NULL,
    created_at timestamptz NOT NULL,
    CONSTRAINT decision_reference_commitment_uk UNIQUE (commitment_id),
    CONSTRAINT decision_reference_scope_uk UNIQUE (
        decision_reference_observation_id, commitment_id,
        decision_run_id, decision_run_target_id, candidate_set_id,
        candidate_id, target_definition_id, target_checkpoint_id,
        instrument_id, reference_provider_product_id, decision_time,
        runtime_mode, commitment_recorded_at, content_sha256
    ),
    CONSTRAINT decision_reference_commitment_fk FOREIGN KEY (
        commitment_id, decision_run_id, decision_run_target_id,
        candidate_set_id, candidate_id, target_definition_id,
        target_checkpoint_id, instrument_id,
        reference_provider_product_id, decision_time,
        runtime_mode, commitment_recorded_at
    ) REFERENCES mra.decision_target_commitment(
        commitment_id, decision_run_id, decision_run_target_id,
        candidate_set_id, candidate_id, target_definition_id,
        target_checkpoint_id, instrument_id,
        reference_provider_product_id, decision_time, runtime_mode,
        commitment_recorded_at
    ) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT decision_reference_run_target_fk FOREIGN KEY (
        decision_run_target_id, decision_run_id, target_definition_id,
        target_checkpoint_id, reference_provider_product_id,
        commitment_recorded_at
    ) REFERENCES mra.decision_run_target(
        decision_run_target_id, decision_run_id, target_definition_id,
        target_checkpoint_id, reference_provider_product_id,
        commitment_recorded_at
    ) ON DELETE RESTRICT,
    CONSTRAINT decision_reference_provider_fk FOREIGN KEY (
        reference_provider_product_id, reference_provider_id
    ) REFERENCES mra.provider_product(provider_product_id, provider_id)
      ON DELETE RESTRICT,
    CONSTRAINT decision_reference_bar_fk FOREIGN KEY (
        bar_revision_id, reference_provider_product_id, capture_id,
        instrument_id, session_id, timeframe, price_basis,
        event_start, event_end, bar_revision, source_recorded_at, known_at
    ) REFERENCES mra.market_bar_revision(
        bar_revision_id, provider_product_id, capture_id,
        instrument_id, session_id, timeframe, price_basis,
        event_start, event_end, revision, recorded_at, known_at
    ) ON DELETE RESTRICT,
    CONSTRAINT decision_reference_gap_fk FOREIGN KEY (
        source_gap_id, reference_provider_product_id, capture_id,
        instrument_id, session_id, timeframe, price_basis,
        event_start, event_end, source_gap_kind, source_gap_reason_code,
        source_recorded_at, known_at
    ) REFERENCES mra.source_gap(
        gap_id, provider_product_id, capture_id,
        instrument_id, session_id, timeframe, price_basis,
        event_start, event_end, gap_kind, reason_code,
        recorded_at, known_at
    ) ON DELETE RESTRICT,
    CONSTRAINT decision_reference_source_ck CHECK (
        (
            source_kind = 'BAR_REVISION'
            AND bar_revision_id IS NOT NULL AND bar_revision > 0
            AND source_gap_id IS NULL
            AND source_gap_kind IS NULL
            AND source_gap_reason_code IS NULL
            AND decimal_value IS NOT NULL
            AND decimal_value > 0
            AND decimal_value < 'Infinity'::numeric
        )
        OR
        (
            source_kind = 'SOURCE_GAP'
            AND source_gap_id IS NOT NULL
            AND source_gap_kind IN (
                'MISSING', 'PLACEHOLDER', 'PROVIDER_FAILURE',
                'CONFLICT', 'INVALID_OHLC'
            )
            AND source_gap_reason_code IN (
                'PROVIDER_FAILURE', 'NO_ROWS_RETURNED',
                'EXPECTED_OBSERVATION_MISSING', 'EXACT_BAR_MISSING',
                'NULL_OHLC_PLACEHOLDER',
                'CONFLICTING_SOURCE_REVISIONS', 'INVALID_OHLC'
            )
            AND bar_revision_id IS NULL AND bar_revision IS NULL
            AND decimal_value IS NULL
        )
    ),
    CONSTRAINT decision_reference_state_ck CHECK (
        finality_status = 'UNKNOWN'
        AND (
            (
                source_kind = 'BAR_REVISION'
                AND value_status = 'PRESENT'
                AND availability_status = 'AVAILABLE'
            )
            OR
            (
                source_kind = 'SOURCE_GAP'
                AND source_gap_kind IN ('MISSING', 'PLACEHOLDER')
                AND value_status = 'UNAVAILABLE'
                AND availability_status = 'UNAVAILABLE'
            )
            OR
            (
                source_kind = 'SOURCE_GAP'
                AND source_gap_kind IN (
                    'PROVIDER_FAILURE', 'CONFLICT', 'INVALID_OHLC'
                )
                AND value_status = 'FAILED'
                AND availability_status = 'FAILED'
            )
        )
    ),
    CONSTRAINT decision_reference_known_at_ck CHECK (
        event_end > event_start
        AND observation_time = event_end
        AND known_at >= source_recorded_at
        AND known_at <= decision_time
        AND runtime_mode IN (
            'OPERATIONAL', 'HISTORICAL', 'REPLAY', 'SHADOW', 'PROSPECTIVE'
        )
        AND created_at = commitment_recorded_at
    ),
    CONSTRAINT decision_reference_value_ck CHECK (
        timeframe IN (
            'MINUTE_1', 'MINUTE_5', 'MINUTE_15',
            'MINUTE_30', 'MINUTE_60', 'DAILY'
        )
        AND price_basis IN (
            'RAW_UNADJUSTED', 'FORWARD_ADJUSTED', 'BACKWARD_ADJUSTED'
        )
        AND value_field IN ('OPEN', 'HIGH', 'LOW', 'CLOSE')
        AND content_sha256 ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT decision_reference_content_ck CHECK (
        content_sha256 = mra.decision_reference_content_sha256(
            availability_status, bar_revision, bar_revision_id,
            candidate_id, capture_id, decimal_value,
            decision_run_target_id, event_end, event_start,
            finality_status, instrument_id, known_at,
            observation_time, price_basis,
            reference_provider_product_id, source_recorded_at,
            session_id, source_gap_id, source_gap_kind,
            source_gap_reason_code, source_kind,
            target_checkpoint_id, timeframe, value_field, value_status
        )
    )
);
CREATE INDEX decision_reference_replay_idx
    ON mra.decision_reference_observation (
        decision_run_id, decision_run_target_id, candidate_id
    );
CREATE INDEX decision_reference_bar_idx
    ON mra.decision_reference_observation (bar_revision_id)
    WHERE bar_revision_id IS NOT NULL;
CREATE INDEX decision_reference_gap_idx
    ON mra.decision_reference_observation (source_gap_id)
    WHERE source_gap_id IS NOT NULL;
CREATE INDEX decision_reference_known_at_idx
    ON mra.decision_reference_observation (
        decision_run_id, known_at, candidate_id
    );
CREATE INDEX decision_reference_commitment_fk_idx
    ON mra.decision_reference_observation (
        commitment_id, decision_run_id, decision_run_target_id,
        candidate_set_id, candidate_id, target_definition_id,
        target_checkpoint_id, instrument_id,
        reference_provider_product_id, decision_time,
        runtime_mode, commitment_recorded_at
    );
CREATE INDEX decision_reference_run_target_fk_idx
    ON mra.decision_reference_observation (
        decision_run_target_id, decision_run_id, target_definition_id,
        target_checkpoint_id, reference_provider_product_id,
        commitment_recorded_at
    );
CREATE INDEX decision_reference_provider_fk_idx
    ON mra.decision_reference_observation (
        reference_provider_product_id, reference_provider_id
    );
CREATE INDEX decision_reference_bar_fk_idx
    ON mra.decision_reference_observation (
        bar_revision_id, reference_provider_product_id, capture_id,
        instrument_id, session_id, timeframe, price_basis,
        event_start, event_end, bar_revision, source_recorded_at, known_at
    );
CREATE INDEX decision_reference_gap_fk_idx
    ON mra.decision_reference_observation (
        source_gap_id, reference_provider_product_id, capture_id,
        instrument_id, session_id, timeframe, price_basis,
        event_start, event_end, source_gap_kind, source_gap_reason_code,
        source_recorded_at, known_at
    );

ALTER TABLE mra.decision_target_commitment
    ADD CONSTRAINT decision_commitment_reference_fk FOREIGN KEY (
        decision_reference_observation_id, commitment_id,
        decision_run_id, decision_run_target_id, candidate_set_id,
        candidate_id, target_definition_id, target_checkpoint_id,
        instrument_id, reference_provider_product_id, decision_time,
        runtime_mode, commitment_recorded_at, decision_reference_sha256
    ) REFERENCES mra.decision_reference_observation(
        decision_reference_observation_id, commitment_id,
        decision_run_id, decision_run_target_id, candidate_set_id,
        candidate_id, target_definition_id, target_checkpoint_id,
        instrument_id, reference_provider_product_id, decision_time,
        runtime_mode, commitment_recorded_at, content_sha256
    ) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE mra.trading_session
    ADD CONSTRAINT trading_session_outcome_authority_uk UNIQUE (
        session_id, exchange, session_date, timezone_name,
        open_at, close_at, source_capture_id, recorded_at, known_at
    );

ALTER TABLE mra.trading_session
    ADD CONSTRAINT trading_session_calendar_authority_uk UNIQUE (
        session_id, exchange, session_date, timezone_name
    );

ALTER TABLE mra.target_checkpoint
    ADD CONSTRAINT target_checkpoint_outcome_authority_uk UNIQUE (
        target_checkpoint_id, target_definition_id, ordinal,
        checkpoint_role, session_offset, local_time, timezone_name,
        timeframe, price_basis, value_field, content_sha256
    );

ALTER TABLE mra.target_metric_definition
    ADD CONSTRAINT target_metric_outcome_authority_uk UNIQUE NULLS NOT DISTINCT (
        target_metric_definition_id, target_definition_id, ordinal,
        metric_code, metric_kind, value_type, unit, completion_rule,
        barrier_direction, barrier_threshold,
        algorithm_code, algorithm_version, algorithm_sha256,
        code_artifact_id, code_content_sha256, code_size_bytes,
        config_artifact_id, config_content_sha256, config_size_bytes,
        content_sha256
    );

ALTER TABLE mra.target_metric_dependency
    ADD CONSTRAINT target_dependency_outcome_authority_uk UNIQUE (
        target_metric_dependency_id, target_definition_id,
        target_metric_definition_id, target_checkpoint_id,
        ordinal, dependency_role, content_sha256
    );

CREATE TABLE mra.market_target_outcome (
    market_target_outcome_id uuid PRIMARY KEY,
    commitment_id uuid NOT NULL,
    decision_run_id uuid NOT NULL,
    decision_run_target_id uuid NOT NULL,
    candidate_set_id uuid NOT NULL,
    candidate_id uuid NOT NULL,
    target_definition_id uuid NOT NULL,
    target_version integer NOT NULL,
    target_definition_sha256 text NOT NULL,
    target_checkpoint_id uuid NOT NULL,
    instrument_id uuid NOT NULL,
    reference_provider_product_id uuid NOT NULL,
    decision_time timestamptz NOT NULL,
    runtime_mode text NOT NULL,
    commitment_recorded_at timestamptz NOT NULL,
    decision_reference_observation_id uuid NOT NULL,
    decision_reference_sha256 text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT market_target_outcome_commitment_uk UNIQUE (commitment_id),
    CONSTRAINT market_target_outcome_scope_uk UNIQUE (
        market_target_outcome_id, commitment_id, decision_run_id,
        decision_run_target_id, candidate_set_id, candidate_id,
        target_definition_id, target_checkpoint_id, instrument_id,
        reference_provider_product_id, decision_time, runtime_mode,
        commitment_recorded_at, decision_reference_observation_id,
        decision_reference_sha256
    ),
    CONSTRAINT market_target_outcome_reference_scope_uk UNIQUE (
        market_target_outcome_id, decision_reference_observation_id,
        commitment_id, target_definition_id, instrument_id,
        decision_reference_sha256
    ),
    CONSTRAINT market_target_outcome_revision_scope_uk UNIQUE (
        market_target_outcome_id, commitment_id, target_definition_id,
        decision_reference_observation_id, decision_reference_sha256
    ),
    CONSTRAINT market_target_outcome_reference_identity_uk UNIQUE (
        market_target_outcome_id, decision_reference_observation_id
    ),
    CONSTRAINT market_target_outcome_commitment_fk FOREIGN KEY (
        decision_reference_observation_id, commitment_id,
        decision_run_id, decision_run_target_id, candidate_set_id,
        candidate_id, target_definition_id, target_checkpoint_id,
        instrument_id, reference_provider_product_id, decision_time,
        runtime_mode, commitment_recorded_at, decision_reference_sha256
    ) REFERENCES mra.decision_target_commitment(
        decision_reference_observation_id, commitment_id,
        decision_run_id, decision_run_target_id, candidate_set_id,
        candidate_id, target_definition_id, target_checkpoint_id,
        instrument_id, reference_provider_product_id, decision_time,
        runtime_mode, commitment_recorded_at, decision_reference_sha256
    ) ON DELETE RESTRICT,
    CONSTRAINT market_target_outcome_reference_fk FOREIGN KEY (
        decision_reference_observation_id, commitment_id,
        decision_run_id, decision_run_target_id, candidate_set_id,
        candidate_id, target_definition_id, target_checkpoint_id,
        instrument_id, reference_provider_product_id, decision_time,
        runtime_mode, commitment_recorded_at, decision_reference_sha256
    ) REFERENCES mra.decision_reference_observation(
        decision_reference_observation_id, commitment_id,
        decision_run_id, decision_run_target_id, candidate_set_id,
        candidate_id, target_definition_id, target_checkpoint_id,
        instrument_id, reference_provider_product_id, decision_time,
        runtime_mode, commitment_recorded_at, content_sha256
    ) ON DELETE RESTRICT,
    CONSTRAINT market_target_outcome_target_fk FOREIGN KEY (
        target_definition_id, target_version, target_definition_sha256
    ) REFERENCES mra.target_definition(
        target_definition_id, version, content_sha256
    ) ON DELETE RESTRICT,
    CONSTRAINT market_target_outcome_shape_ck CHECK (
        target_version > 0
        AND target_definition_sha256 ~ '^[0-9a-f]{64}$'
        AND decision_reference_sha256 ~ '^[0-9a-f]{64}$'
        AND runtime_mode IN (
            'OPERATIONAL', 'HISTORICAL', 'REPLAY', 'SHADOW', 'PROSPECTIVE'
        )
        AND created_at >= commitment_recorded_at
    )
);
CREATE INDEX market_target_outcome_commitment_idx
    ON mra.market_target_outcome (
        commitment_id, market_target_outcome_id, target_definition_id
    );
CREATE INDEX market_target_outcome_commitment_authority_idx
    ON mra.market_target_outcome (
        decision_reference_observation_id, commitment_id,
        decision_run_id, decision_run_target_id, candidate_set_id,
        candidate_id, target_definition_id, target_checkpoint_id,
        instrument_id, reference_provider_product_id, decision_time,
        runtime_mode, commitment_recorded_at, decision_reference_sha256
    );
CREATE INDEX market_target_outcome_reference_idx
    ON mra.market_target_outcome (
        decision_reference_observation_id, commitment_id,
        decision_reference_sha256
    );
CREATE INDEX market_target_outcome_target_idx
    ON mra.market_target_outcome (
        target_definition_id, target_version, target_definition_sha256
    );

CREATE TABLE mra.market_target_outcome_revision (
    market_target_outcome_revision_id uuid PRIMARY KEY,
    market_target_outcome_id uuid NOT NULL,
    revision_ordinal integer NOT NULL,
    supersedes_revision_id uuid,
    supersedes_revision_ordinal integer,
    commitment_id uuid NOT NULL,
    target_definition_id uuid NOT NULL,
    decision_reference_observation_id uuid NOT NULL,
    decision_reference_sha256 text NOT NULL,
    observation_cutoff timestamptz NOT NULL,
    knowledge_cutoff timestamptz NOT NULL,
    outcome_status text NOT NULL,
    availability_status text NOT NULL,
    finality_status text NOT NULL,
    source_count integer NOT NULL,
    source_roster_sha256 text NOT NULL,
    observation_count integer NOT NULL,
    observation_roster_sha256 text NOT NULL,
    metric_count integer NOT NULL,
    metric_roster_sha256 text NOT NULL,
    reference_dependency_count integer NOT NULL,
    reference_dependency_roster_sha256 text NOT NULL,
    observation_dependency_count integer NOT NULL,
    observation_dependency_roster_sha256 text NOT NULL,
    reason_count integer NOT NULL,
    reason_roster_sha256 text NOT NULL,
    definition_summary_sha256 text NOT NULL,
    request_received_at timestamptz NOT NULL,
    settled_at timestamptz NOT NULL,
    runtime_run_id uuid NOT NULL,
    runtime_step_id uuid NOT NULL,
    runtime_attempt_id uuid NOT NULL,
    runtime_fence_token bigint NOT NULL,
    runtime_step_key text NOT NULL,
    runtime_step_kind text NOT NULL,
    runtime_mode text NOT NULL,
    runtime_decision_time timestamptz NOT NULL,
    runtime_code_sha text NOT NULL,
    runtime_config_artifact_id uuid NOT NULL,
    runtime_config_hash text NOT NULL,
    request_kind text NOT NULL,
    request_scope_id text NOT NULL,
    request_identity text NOT NULL,
    request_sha256 text NOT NULL,
    command_receipt_id uuid NOT NULL,
    created_by_actor_type text NOT NULL,
    created_by_actor_id text NOT NULL,
    creation_reason_code text NOT NULL,
    created_at timestamptz NOT NULL,
    CONSTRAINT outcome_revision_ordinal_uk UNIQUE (
        market_target_outcome_id, revision_ordinal
    ),
    CONSTRAINT outcome_revision_exact_identity_uk UNIQUE (
        market_target_outcome_revision_id, market_target_outcome_id,
        revision_ordinal, observation_cutoff, knowledge_cutoff
    ),
    CONSTRAINT outcome_revision_chain_identity_uk UNIQUE (
        market_target_outcome_revision_id, market_target_outcome_id,
        revision_ordinal
    ),
    CONSTRAINT outcome_revision_request_hash_uk UNIQUE (
        market_target_outcome_id, request_sha256
    ),
    CONSTRAINT outcome_revision_request_identity_uk UNIQUE (
        commitment_id, request_identity
    ),
    CONSTRAINT outcome_revision_receipt_uk UNIQUE (command_receipt_id),
    CONSTRAINT outcome_revision_supersedes_uk UNIQUE (supersedes_revision_id),
    CONSTRAINT outcome_revision_root_fk FOREIGN KEY (
        market_target_outcome_id, commitment_id, target_definition_id,
        decision_reference_observation_id, decision_reference_sha256
    ) REFERENCES mra.market_target_outcome(
        market_target_outcome_id, commitment_id, target_definition_id,
        decision_reference_observation_id, decision_reference_sha256
    ) ON DELETE RESTRICT,
    CONSTRAINT outcome_revision_supersedes_fk FOREIGN KEY (
        supersedes_revision_id, market_target_outcome_id,
        supersedes_revision_ordinal
    ) REFERENCES mra.market_target_outcome_revision(
        market_target_outcome_revision_id, market_target_outcome_id,
        revision_ordinal
    ) ON DELETE RESTRICT,
    CONSTRAINT outcome_revision_runtime_run_fk FOREIGN KEY (
        runtime_run_id, runtime_mode, runtime_decision_time,
        runtime_code_sha, runtime_config_artifact_id, runtime_config_hash
    ) REFERENCES mra.runtime_run(
        run_id, runtime_mode, decision_time, code_sha,
        config_artifact_id, config_hash
    ) ON DELETE RESTRICT,
    CONSTRAINT outcome_revision_runtime_step_fk FOREIGN KEY (
        runtime_step_id, runtime_run_id, runtime_step_key, runtime_step_kind
    ) REFERENCES mra.runtime_step(
        step_id, run_id, step_key, step_kind
    ) ON DELETE RESTRICT,
    CONSTRAINT outcome_revision_runtime_attempt_fk FOREIGN KEY (
        runtime_attempt_id, runtime_step_id, runtime_fence_token
    ) REFERENCES mra.runtime_attempt(
        attempt_id, step_id, fence_token
    ) ON DELETE RESTRICT,
    CONSTRAINT outcome_revision_receipt_claim_fk FOREIGN KEY (
        command_receipt_id, request_kind, request_scope_id,
        request_identity, request_sha256, runtime_step_id,
        runtime_attempt_id, runtime_fence_token
    ) REFERENCES mra.command_receipt(
        receipt_id, command_kind, scope_id, idempotency_key, request_hash,
        runtime_step_id, runtime_attempt_id, fence_token
    ) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT outcome_revision_chain_ck CHECK (
        (revision_ordinal = 1
         AND supersedes_revision_id IS NULL
         AND supersedes_revision_ordinal IS NULL)
        OR
        (revision_ordinal > 1
         AND supersedes_revision_id IS NOT NULL
         AND supersedes_revision_ordinal = revision_ordinal - 1)
    ),
    CONSTRAINT outcome_revision_cutoffs_ck CHECK (
        observation_cutoff > '-infinity'::timestamptz
        AND observation_cutoff < 'infinity'::timestamptz
        AND knowledge_cutoff > '-infinity'::timestamptz
        AND knowledge_cutoff < 'infinity'::timestamptz
    ),
    CONSTRAINT outcome_revision_counts_ck CHECK (
        source_count > 0
        AND observation_count > 0
        AND metric_count > 0
        AND reference_dependency_count >= 0
        AND observation_dependency_count >= 0
        AND reference_dependency_count + observation_dependency_count > 0
        AND reason_count >= 0
    ),
    CONSTRAINT outcome_revision_state_ck CHECK (
        outcome_status IN ('PARTIAL', 'COMPLETE', 'UNAVAILABLE', 'FAILED')
        AND availability_status IN ('AVAILABLE', 'UNAVAILABLE', 'FAILED')
        AND finality_status = 'UNKNOWN'
        AND (
            (outcome_status = 'COMPLETE' AND availability_status = 'AVAILABLE')
            OR (outcome_status = 'FAILED' AND availability_status = 'FAILED')
            OR (outcome_status = 'UNAVAILABLE'
                AND availability_status = 'UNAVAILABLE')
            OR (outcome_status = 'PARTIAL'
                AND availability_status IN ('AVAILABLE', 'UNAVAILABLE'))
        )
    ),
    CONSTRAINT outcome_revision_hashes_ck CHECK (
        source_roster_sha256 ~ '^[0-9a-f]{64}$'
        AND observation_roster_sha256 ~ '^[0-9a-f]{64}$'
        AND metric_roster_sha256 ~ '^[0-9a-f]{64}$'
        AND reference_dependency_roster_sha256 ~ '^[0-9a-f]{64}$'
        AND observation_dependency_roster_sha256 ~ '^[0-9a-f]{64}$'
        AND reason_roster_sha256 ~ '^[0-9a-f]{64}$'
        AND definition_summary_sha256 ~ '^[0-9a-f]{64}$'
        AND decision_reference_sha256 ~ '^[0-9a-f]{64}$'
        AND request_sha256 ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT outcome_revision_runtime_ck CHECK (
        runtime_step_kind = 'SETTLE_OUTCOME'
        AND runtime_mode IN (
            'OPERATIONAL', 'HISTORICAL', 'REPLAY', 'SHADOW', 'PROSPECTIVE'
        )
        AND runtime_code_sha ~ '^[0-9a-f]{40}([0-9a-f]{24})?$'
        AND runtime_config_hash ~ '^[0-9a-f]{64}$'
        AND runtime_step_key ~ '^[a-z][a-z0-9_-]{0,99}$'
        AND runtime_fence_token > 0
    ),
    CONSTRAINT outcome_revision_request_ck CHECK (
        request_kind = 'SETTLE_MARKET_TARGET_OUTCOME'
        AND request_scope_id = commitment_id::text
        AND request_identity ~ '^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$'
        AND created_by_actor_type IN ('SYSTEM', 'OPERATOR', 'WORKER')
        AND created_by_actor_id <> ''
        AND creation_reason_code ~ '^[A-Z][A-Z0-9_]{0,99}$'
    ),
    CONSTRAINT outcome_revision_time_ck CHECK (
        request_received_at <= settled_at AND created_at = settled_at
    )
);
CREATE INDEX outcome_revision_leaf_idx
    ON mra.market_target_outcome_revision (
        market_target_outcome_id, revision_ordinal DESC,
        market_target_outcome_revision_id
    );
CREATE INDEX outcome_revision_request_idx
    ON mra.market_target_outcome_revision (
        commitment_id, request_identity, request_sha256
    );
CREATE INDEX outcome_revision_runtime_idx
    ON mra.market_target_outcome_revision (
        runtime_run_id, runtime_step_id, runtime_attempt_id,
        runtime_fence_token
    );
CREATE INDEX outcome_revision_runtime_run_authority_idx
    ON mra.market_target_outcome_revision (
        runtime_run_id, runtime_mode, runtime_decision_time,
        runtime_code_sha, runtime_config_artifact_id, runtime_config_hash
    );
CREATE INDEX outcome_revision_supersedes_idx
    ON mra.market_target_outcome_revision (supersedes_revision_id)
    WHERE supersedes_revision_id IS NOT NULL;
CREATE INDEX outcome_revision_root_authority_idx
    ON mra.market_target_outcome_revision (
        market_target_outcome_id, commitment_id, target_definition_id,
        decision_reference_observation_id, decision_reference_sha256
    );
CREATE INDEX outcome_revision_supersedes_authority_idx
    ON mra.market_target_outcome_revision (
        supersedes_revision_id, market_target_outcome_id,
        supersedes_revision_ordinal
    ) WHERE supersedes_revision_id IS NOT NULL;
CREATE INDEX outcome_revision_runtime_step_authority_idx
    ON mra.market_target_outcome_revision (
        runtime_step_id, runtime_run_id, runtime_step_key, runtime_step_kind
    );
CREATE INDEX outcome_revision_runtime_attempt_authority_idx
    ON mra.market_target_outcome_revision (
        runtime_attempt_id, runtime_step_id, runtime_fence_token
    );
CREATE INDEX outcome_revision_receipt_authority_idx
    ON mra.market_target_outcome_revision (
        command_receipt_id, request_kind, request_scope_id,
        request_identity, request_sha256, runtime_step_id,
        runtime_attempt_id, runtime_fence_token
    );

CREATE TABLE mra.market_target_outcome_source (
    market_target_outcome_source_id uuid PRIMARY KEY,
    market_target_outcome_revision_id uuid NOT NULL,
    market_target_outcome_id uuid NOT NULL,
    revision_ordinal integer NOT NULL,
    source_ordinal integer NOT NULL,
    source_role text NOT NULL,
    source_kind text NOT NULL,
    target_definition_id uuid NOT NULL,
    target_checkpoint_id uuid,
    provider_product_id uuid NOT NULL,
    capture_id uuid NOT NULL,
    session_provider_product_id uuid NOT NULL,
    session_capture_id uuid NOT NULL,
    instrument_id uuid,
    trading_session_id uuid NOT NULL,
    session_offset integer NOT NULL,
    exchange text,
    session_date date,
    timezone_name text,
    session_open_at timestamptz,
    session_close_at timestamptz,
    timeframe text,
    price_basis text,
    event_start timestamptz,
    event_end timestamptz,
    source_recorded_at timestamptz NOT NULL,
    known_at timestamptz NOT NULL,
    session_recorded_at timestamptz NOT NULL,
    session_known_at timestamptz NOT NULL,
    bar_revision_id uuid,
    bar_revision integer,
    source_gap_id uuid,
    source_gap_kind text,
    source_gap_reason_code text,
    observation_cutoff timestamptz NOT NULL,
    knowledge_cutoff timestamptz NOT NULL,
    content_sha256 text NOT NULL,
    created_at timestamptz NOT NULL,
    CONSTRAINT outcome_source_ordinal_uk UNIQUE (
        market_target_outcome_revision_id, source_ordinal
    ),
    CONSTRAINT outcome_source_role_scope_uk UNIQUE NULLS NOT DISTINCT (
        market_target_outcome_revision_id, source_role,
        session_offset, target_checkpoint_id
    ),
    CONSTRAINT outcome_source_scope_uk UNIQUE NULLS NOT DISTINCT (
        market_target_outcome_source_id,
        market_target_outcome_revision_id, market_target_outcome_id,
        revision_ordinal, target_checkpoint_id, source_kind,
        event_start, event_end, known_at
    ),
    CONSTRAINT outcome_source_revision_fk FOREIGN KEY (
        market_target_outcome_revision_id, market_target_outcome_id,
        revision_ordinal, observation_cutoff, knowledge_cutoff
    ) REFERENCES mra.market_target_outcome_revision(
        market_target_outcome_revision_id, market_target_outcome_id,
        revision_ordinal, observation_cutoff, knowledge_cutoff
    ) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT outcome_source_checkpoint_fk FOREIGN KEY (
        target_checkpoint_id, target_definition_id
    ) REFERENCES mra.target_checkpoint(
        target_checkpoint_id, target_definition_id
    ) ON DELETE RESTRICT,
    CONSTRAINT outcome_source_observation_provenance_fk FOREIGN KEY (
        capture_id, provider_product_id
    ) REFERENCES mra.data_capture(
        capture_id, provider_product_id
    ) ON DELETE RESTRICT,
    CONSTRAINT outcome_source_session_provenance_fk FOREIGN KEY (
        session_capture_id, session_provider_product_id
    ) REFERENCES mra.data_capture(
        capture_id, provider_product_id
    ) ON DELETE RESTRICT,
    CONSTRAINT outcome_source_session_fk FOREIGN KEY (
        trading_session_id, exchange, session_date, timezone_name,
        session_open_at, session_close_at, session_capture_id,
        session_recorded_at, session_known_at
    ) REFERENCES mra.trading_session(
        session_id, exchange, session_date, timezone_name,
        open_at, close_at, source_capture_id, recorded_at, known_at
    ) ON DELETE RESTRICT,
    CONSTRAINT outcome_source_bar_fk FOREIGN KEY (
        bar_revision_id, provider_product_id, capture_id,
        instrument_id, trading_session_id, timeframe, price_basis,
        event_start, event_end, bar_revision, source_recorded_at, known_at
    ) REFERENCES mra.market_bar_revision(
        bar_revision_id, provider_product_id, capture_id,
        instrument_id, session_id, timeframe, price_basis,
        event_start, event_end, revision, recorded_at, known_at
    ) ON DELETE RESTRICT,
    CONSTRAINT outcome_source_gap_fk FOREIGN KEY (
        source_gap_id, provider_product_id, capture_id,
        instrument_id, trading_session_id, timeframe, price_basis,
        event_start, event_end, source_gap_kind, source_gap_reason_code,
        source_recorded_at, known_at
    ) REFERENCES mra.source_gap(
        gap_id, provider_product_id, capture_id,
        instrument_id, session_id, timeframe, price_basis,
        event_start, event_end, gap_kind, reason_code,
        recorded_at, known_at
    ) ON DELETE RESTRICT,
    CONSTRAINT outcome_source_shape_ck CHECK (
        source_ordinal > 0 AND session_offset > 0
        AND exchange IS NOT NULL AND session_date IS NOT NULL
        AND timezone_name IS NOT NULL
        AND session_open_at IS NOT NULL AND session_close_at IS NOT NULL
        AND content_sha256 ~ '^[0-9a-f]{64}$'
        AND created_at >= source_recorded_at
        AND (
            (source_kind = 'TRADING_SESSION'
             AND source_role = 'CALENDAR_SESSION'
             AND provider_product_id = session_provider_product_id
             AND capture_id = session_capture_id
             AND source_recorded_at = session_recorded_at
             AND known_at = session_known_at
             AND target_checkpoint_id IS NULL
             AND instrument_id IS NULL
             AND exchange IS NOT NULL AND session_date IS NOT NULL
             AND timezone_name IS NOT NULL
             AND session_open_at IS NOT NULL AND session_close_at IS NOT NULL
             AND timeframe IS NULL AND price_basis IS NULL
             AND event_start IS NULL AND event_end IS NULL
             AND bar_revision_id IS NULL AND bar_revision IS NULL
             AND source_gap_id IS NULL AND source_gap_kind IS NULL
             AND source_gap_reason_code IS NULL)
            OR
            (source_kind = 'BAR_REVISION'
             AND source_role = 'OUTCOME_OBSERVATION'
             AND target_checkpoint_id IS NOT NULL
             AND instrument_id IS NOT NULL
             AND timeframe IS NOT NULL AND price_basis IS NOT NULL
             AND event_start IS NOT NULL AND event_end IS NOT NULL
             AND bar_revision_id IS NOT NULL AND bar_revision > 0
             AND source_gap_id IS NULL AND source_gap_kind IS NULL
             AND source_gap_reason_code IS NULL)
            OR
            (source_kind = 'SOURCE_GAP'
             AND source_role = 'OUTCOME_OBSERVATION'
             AND target_checkpoint_id IS NOT NULL
             AND instrument_id IS NOT NULL
             AND timeframe IS NOT NULL AND price_basis IS NOT NULL
             AND event_start IS NOT NULL AND event_end IS NOT NULL
             AND source_gap_id IS NOT NULL
             AND source_gap_kind IN (
                 'MISSING', 'PLACEHOLDER', 'PROVIDER_FAILURE',
                 'CONFLICT', 'INVALID_OHLC'
             )
             AND source_gap_reason_code IS NOT NULL
             AND bar_revision_id IS NULL AND bar_revision IS NULL)
        )
    ),
    CONSTRAINT outcome_source_cutoffs_ck CHECK (
        known_at >= source_recorded_at
        AND session_known_at >= session_recorded_at
        AND known_at <= knowledge_cutoff
        AND session_known_at <= knowledge_cutoff
        AND (event_end IS NULL OR event_end <= observation_cutoff)
        AND created_at >= greatest(known_at, session_known_at)
    )
);
CREATE INDEX outcome_source_revision_idx
    ON mra.market_target_outcome_source (
        market_target_outcome_revision_id, source_ordinal
    );
CREATE INDEX outcome_source_revision_authority_idx
    ON mra.market_target_outcome_source (
        market_target_outcome_revision_id, market_target_outcome_id,
        revision_ordinal, observation_cutoff, knowledge_cutoff
    );
CREATE INDEX outcome_source_bar_idx
    ON mra.market_target_outcome_source (bar_revision_id)
    WHERE bar_revision_id IS NOT NULL;
CREATE INDEX outcome_source_gap_idx
    ON mra.market_target_outcome_source (source_gap_id)
    WHERE source_gap_id IS NOT NULL;
CREATE INDEX outcome_source_session_idx
    ON mra.market_target_outcome_source (
        trading_session_id, session_offset,
        market_target_outcome_revision_id
    );
CREATE INDEX outcome_source_capture_product_idx
    ON mra.market_target_outcome_source (capture_id, provider_product_id);
CREATE INDEX outcome_source_session_capture_product_idx
    ON mra.market_target_outcome_source (
        session_capture_id, session_provider_product_id
    );
CREATE INDEX outcome_source_session_authority_idx
    ON mra.market_target_outcome_source (
        trading_session_id, exchange, session_date, timezone_name,
        session_open_at, session_close_at, session_capture_id,
        session_recorded_at, session_known_at
    );
CREATE INDEX outcome_source_bar_authority_idx
    ON mra.market_target_outcome_source (
        bar_revision_id, provider_product_id, capture_id,
        instrument_id, trading_session_id, timeframe, price_basis,
        event_start, event_end, bar_revision, source_recorded_at, known_at
    ) WHERE bar_revision_id IS NOT NULL;
CREATE INDEX outcome_source_gap_authority_idx
    ON mra.market_target_outcome_source (
        source_gap_id, provider_product_id, capture_id,
        instrument_id, trading_session_id, timeframe, price_basis,
        event_start, event_end, source_gap_kind, source_gap_reason_code,
        source_recorded_at, known_at
    ) WHERE source_gap_id IS NOT NULL;
CREATE INDEX outcome_source_checkpoint_idx
    ON mra.market_target_outcome_source (
        target_checkpoint_id, target_definition_id
    ) WHERE target_checkpoint_id IS NOT NULL;

CREATE TABLE mra.market_target_outcome_observation (
    market_target_outcome_observation_id uuid PRIMARY KEY,
    market_target_outcome_revision_id uuid NOT NULL,
    market_target_outcome_id uuid NOT NULL,
    revision_ordinal integer NOT NULL,
    observation_ordinal integer NOT NULL,
    target_definition_id uuid NOT NULL,
    target_checkpoint_id uuid NOT NULL,
    market_target_outcome_source_id uuid NOT NULL,
    source_kind text NOT NULL,
    value_status text NOT NULL,
    availability_status text NOT NULL,
    finality_status text NOT NULL,
    selected_value numeric,
    open_value numeric,
    high_value numeric,
    low_value numeric,
    close_value numeric,
    event_start timestamptz NOT NULL,
    event_end timestamptz NOT NULL,
    known_at timestamptz NOT NULL,
    observation_cutoff timestamptz NOT NULL,
    knowledge_cutoff timestamptz NOT NULL,
    content_sha256 text NOT NULL,
    created_at timestamptz NOT NULL,
    CONSTRAINT outcome_observation_ordinal_uk UNIQUE (
        market_target_outcome_revision_id, observation_ordinal
    ),
    CONSTRAINT outcome_observation_checkpoint_uk UNIQUE (
        market_target_outcome_revision_id, target_checkpoint_id
    ),
    CONSTRAINT outcome_observation_source_uk UNIQUE (
        market_target_outcome_revision_id, market_target_outcome_source_id
    ),
    CONSTRAINT outcome_observation_scope_uk UNIQUE (
        market_target_outcome_observation_id,
        market_target_outcome_revision_id, market_target_outcome_id,
        revision_ordinal, target_definition_id, target_checkpoint_id
    ),
    CONSTRAINT outcome_observation_revision_fk FOREIGN KEY (
        market_target_outcome_revision_id, market_target_outcome_id,
        revision_ordinal, observation_cutoff, knowledge_cutoff
    ) REFERENCES mra.market_target_outcome_revision(
        market_target_outcome_revision_id, market_target_outcome_id,
        revision_ordinal, observation_cutoff, knowledge_cutoff
    ) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT outcome_observation_checkpoint_fk FOREIGN KEY (
        target_checkpoint_id, target_definition_id
    ) REFERENCES mra.target_checkpoint(
        target_checkpoint_id, target_definition_id
    ) ON DELETE RESTRICT,
    CONSTRAINT outcome_observation_source_fk FOREIGN KEY (
        market_target_outcome_source_id,
        market_target_outcome_revision_id, market_target_outcome_id,
        revision_ordinal, target_checkpoint_id, source_kind,
        event_start, event_end, known_at
    ) REFERENCES mra.market_target_outcome_source(
        market_target_outcome_source_id,
        market_target_outcome_revision_id, market_target_outcome_id,
        revision_ordinal, target_checkpoint_id, source_kind,
        event_start, event_end, known_at
    ) ON DELETE RESTRICT,
    CONSTRAINT outcome_observation_state_ck CHECK (
        observation_ordinal > 0
        AND source_kind IN ('BAR_REVISION', 'SOURCE_GAP')
        AND value_status IN ('PARTIAL', 'COMPLETE', 'UNAVAILABLE', 'FAILED')
        AND availability_status IN ('AVAILABLE', 'UNAVAILABLE', 'FAILED')
        AND finality_status = 'UNKNOWN'
        AND content_sha256 ~ '^[0-9a-f]{64}$'
        AND (
            (value_status IN ('COMPLETE', 'PARTIAL')
             AND source_kind = 'BAR_REVISION'
             AND availability_status = 'AVAILABLE'
             AND selected_value IS NOT NULL
             AND open_value IS NOT NULL AND high_value IS NOT NULL
             AND low_value IS NOT NULL AND close_value IS NOT NULL
             AND selected_value > 0
             AND high_value >= greatest(open_value, low_value, close_value)
             AND low_value <= least(open_value, high_value, close_value))
            OR
            (value_status = 'UNAVAILABLE'
             AND source_kind = 'SOURCE_GAP'
             AND availability_status = 'UNAVAILABLE'
             AND selected_value IS NULL AND open_value IS NULL
             AND high_value IS NULL AND low_value IS NULL
             AND close_value IS NULL)
            OR
            (value_status = 'FAILED'
             AND source_kind = 'SOURCE_GAP'
             AND availability_status = 'FAILED'
             AND selected_value IS NULL AND open_value IS NULL
             AND high_value IS NULL AND low_value IS NULL
             AND close_value IS NULL)
        )
        AND event_end > event_start
        AND event_end <= observation_cutoff
        AND known_at <= knowledge_cutoff
        AND created_at >= known_at
    )
);
CREATE INDEX outcome_observation_revision_idx
    ON mra.market_target_outcome_observation (
        market_target_outcome_revision_id, observation_ordinal
    );
CREATE INDEX outcome_observation_revision_authority_idx
    ON mra.market_target_outcome_observation (
        market_target_outcome_revision_id, market_target_outcome_id,
        revision_ordinal, observation_cutoff, knowledge_cutoff
    );
CREATE INDEX outcome_observation_source_idx
    ON mra.market_target_outcome_observation (
        market_target_outcome_source_id,
        market_target_outcome_revision_id
    );
CREATE INDEX outcome_observation_source_authority_idx
    ON mra.market_target_outcome_observation (
        market_target_outcome_source_id,
        market_target_outcome_revision_id, market_target_outcome_id,
        revision_ordinal, target_checkpoint_id, source_kind,
        event_start, event_end, known_at
    );
CREATE INDEX outcome_observation_checkpoint_idx
    ON mra.market_target_outcome_observation (
        target_checkpoint_id, target_definition_id
    );

CREATE TABLE mra.market_target_outcome_metric (
    market_target_outcome_metric_id uuid PRIMARY KEY,
    market_target_outcome_revision_id uuid NOT NULL,
    market_target_outcome_id uuid NOT NULL,
    revision_ordinal integer NOT NULL,
    target_definition_id uuid NOT NULL,
    target_metric_definition_id uuid NOT NULL,
    metric_ordinal integer NOT NULL,
    metric_code text NOT NULL,
    metric_kind text NOT NULL,
    value_type text NOT NULL,
    unit text NOT NULL,
    completion_rule text NOT NULL,
    barrier_direction text,
    barrier_threshold numeric,
    value_status text NOT NULL,
    availability_status text NOT NULL,
    finality_status text NOT NULL,
    decimal_value numeric,
    boolean_value boolean,
    first_passage_at timestamptz,
    algorithm_code text NOT NULL,
    algorithm_version text NOT NULL,
    algorithm_sha256 text NOT NULL,
    code_artifact_id uuid NOT NULL,
    code_content_sha256 text NOT NULL,
    code_size_bytes bigint NOT NULL,
    config_artifact_id uuid NOT NULL,
    config_content_sha256 text NOT NULL,
    config_size_bytes bigint NOT NULL,
    target_metric_sha256 text NOT NULL,
    content_sha256 text NOT NULL,
    created_at timestamptz NOT NULL,
    CONSTRAINT outcome_metric_ordinal_uk UNIQUE (
        market_target_outcome_revision_id, metric_ordinal
    ),
    CONSTRAINT outcome_metric_definition_uk UNIQUE (
        market_target_outcome_revision_id, target_metric_definition_id
    ),
    CONSTRAINT outcome_metric_scope_uk UNIQUE (
        market_target_outcome_metric_id,
        market_target_outcome_revision_id, market_target_outcome_id,
        revision_ordinal, target_definition_id,
        target_metric_definition_id
    ),
    CONSTRAINT outcome_metric_revision_fk FOREIGN KEY (
        market_target_outcome_revision_id, market_target_outcome_id,
        revision_ordinal
    ) REFERENCES mra.market_target_outcome_revision(
        market_target_outcome_revision_id, market_target_outcome_id,
        revision_ordinal
    ) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT outcome_metric_definition_fk FOREIGN KEY (
        target_metric_definition_id, target_definition_id,
        metric_ordinal, metric_code, metric_kind, value_type, unit,
        completion_rule, barrier_direction, barrier_threshold,
        algorithm_code, algorithm_version, algorithm_sha256,
        code_artifact_id, code_content_sha256, code_size_bytes,
        config_artifact_id, config_content_sha256, config_size_bytes,
        target_metric_sha256
    ) REFERENCES mra.target_metric_definition(
        target_metric_definition_id, target_definition_id,
        ordinal, metric_code, metric_kind, value_type, unit,
        completion_rule, barrier_direction, barrier_threshold,
        algorithm_code, algorithm_version, algorithm_sha256,
        code_artifact_id, code_content_sha256, code_size_bytes,
        config_artifact_id, config_content_sha256, config_size_bytes,
        content_sha256
    ) ON DELETE RESTRICT,
    CONSTRAINT outcome_metric_state_ck CHECK (
        metric_ordinal > 0
        AND metric_kind IN (
            'SIMPLE_RETURN', 'MAX_FAVORABLE_EXCURSION',
            'MAX_ADVERSE_EXCURSION', 'BARRIER_HIT',
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
    )
);
CREATE INDEX outcome_metric_revision_idx
    ON mra.market_target_outcome_metric (
        market_target_outcome_revision_id, metric_ordinal
    );
CREATE INDEX outcome_metric_revision_authority_idx
    ON mra.market_target_outcome_metric (
        market_target_outcome_revision_id, market_target_outcome_id,
        revision_ordinal
    );
CREATE INDEX outcome_metric_definition_idx
    ON mra.market_target_outcome_metric (
        target_metric_definition_id, target_definition_id
    );
CREATE INDEX outcome_metric_definition_authority_idx
    ON mra.market_target_outcome_metric (
        target_metric_definition_id, target_definition_id,
        metric_ordinal, metric_code, metric_kind, value_type, unit,
        completion_rule, barrier_direction, barrier_threshold,
        algorithm_code, algorithm_version, algorithm_sha256,
        code_artifact_id, code_content_sha256, code_size_bytes,
        config_artifact_id, config_content_sha256, config_size_bytes,
        target_metric_sha256
    );

CREATE TABLE mra.market_target_outcome_metric_reference (
    market_target_outcome_metric_reference_id uuid PRIMARY KEY,
    market_target_outcome_revision_id uuid NOT NULL,
    market_target_outcome_id uuid NOT NULL,
    revision_ordinal integer NOT NULL,
    dependency_ordinal integer NOT NULL,
    target_definition_id uuid NOT NULL,
    target_metric_definition_id uuid NOT NULL,
    market_target_outcome_metric_id uuid NOT NULL,
    target_metric_dependency_id uuid NOT NULL,
    target_checkpoint_id uuid NOT NULL,
    dependency_role text NOT NULL,
    target_dependency_sha256 text NOT NULL,
    decision_reference_observation_id uuid NOT NULL,
    content_sha256 text NOT NULL,
    created_at timestamptz NOT NULL,
    CONSTRAINT outcome_metric_reference_ordinal_uk UNIQUE (
        market_target_outcome_revision_id, dependency_ordinal
    ),
    CONSTRAINT outcome_metric_reference_dependency_uk UNIQUE (
        market_target_outcome_revision_id, target_metric_dependency_id
    ),
    CONSTRAINT outcome_metric_reference_revision_fk FOREIGN KEY (
        market_target_outcome_revision_id, market_target_outcome_id,
        revision_ordinal
    ) REFERENCES mra.market_target_outcome_revision(
        market_target_outcome_revision_id, market_target_outcome_id,
        revision_ordinal
    ) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT outcome_metric_reference_metric_fk FOREIGN KEY (
        market_target_outcome_metric_id,
        market_target_outcome_revision_id, market_target_outcome_id,
        revision_ordinal, target_definition_id,
        target_metric_definition_id
    ) REFERENCES mra.market_target_outcome_metric(
        market_target_outcome_metric_id,
        market_target_outcome_revision_id, market_target_outcome_id,
        revision_ordinal, target_definition_id,
        target_metric_definition_id
    ) ON DELETE RESTRICT,
    CONSTRAINT outcome_metric_reference_dependency_fk FOREIGN KEY (
        target_metric_dependency_id, target_definition_id,
        target_metric_definition_id, target_checkpoint_id,
        dependency_ordinal, dependency_role, target_dependency_sha256
    ) REFERENCES mra.target_metric_dependency(
        target_metric_dependency_id, target_definition_id,
        target_metric_definition_id, target_checkpoint_id,
        ordinal, dependency_role, content_sha256
    ) ON DELETE RESTRICT,
    CONSTRAINT outcome_metric_reference_root_fk FOREIGN KEY (
        market_target_outcome_id, decision_reference_observation_id
    ) REFERENCES mra.market_target_outcome(
        market_target_outcome_id, decision_reference_observation_id
    ) ON DELETE RESTRICT,
    CONSTRAINT outcome_metric_reference_observation_fk FOREIGN KEY (
        decision_reference_observation_id
    ) REFERENCES mra.decision_reference_observation(
        decision_reference_observation_id
    ) ON DELETE RESTRICT,
    CONSTRAINT outcome_metric_reference_role_ck CHECK (
        dependency_ordinal > 0
        AND dependency_role = 'REFERENCE'
        AND target_dependency_sha256 ~ '^[0-9a-f]{64}$'
        AND content_sha256 ~ '^[0-9a-f]{64}$'
    )
);
CREATE INDEX outcome_metric_reference_revision_idx
    ON mra.market_target_outcome_metric_reference (
        market_target_outcome_revision_id, dependency_ordinal
    );
CREATE INDEX outcome_metric_reference_revision_authority_idx
    ON mra.market_target_outcome_metric_reference (
        market_target_outcome_revision_id, market_target_outcome_id,
        revision_ordinal
    );
CREATE INDEX outcome_metric_reference_observation_idx
    ON mra.market_target_outcome_metric_reference (
        decision_reference_observation_id, market_target_outcome_id
    );
CREATE INDEX outcome_metric_reference_metric_idx
    ON mra.market_target_outcome_metric_reference (
        market_target_outcome_metric_id,
        market_target_outcome_revision_id
    );
CREATE INDEX outcome_metric_reference_metric_authority_idx
    ON mra.market_target_outcome_metric_reference (
        market_target_outcome_metric_id,
        market_target_outcome_revision_id, market_target_outcome_id,
        revision_ordinal, target_definition_id,
        target_metric_definition_id
    );
CREATE INDEX outcome_metric_reference_dependency_authority_idx
    ON mra.market_target_outcome_metric_reference (
        target_metric_dependency_id, target_definition_id,
        target_metric_definition_id, target_checkpoint_id,
        dependency_ordinal, dependency_role, target_dependency_sha256
    );
CREATE INDEX outcome_metric_reference_root_authority_idx
    ON mra.market_target_outcome_metric_reference (
        market_target_outcome_id, decision_reference_observation_id
    );

CREATE TABLE mra.market_target_outcome_metric_observation (
    market_target_outcome_metric_observation_id uuid PRIMARY KEY,
    market_target_outcome_revision_id uuid NOT NULL,
    market_target_outcome_id uuid NOT NULL,
    revision_ordinal integer NOT NULL,
    dependency_ordinal integer NOT NULL,
    target_definition_id uuid NOT NULL,
    target_metric_definition_id uuid NOT NULL,
    market_target_outcome_metric_id uuid NOT NULL,
    target_metric_dependency_id uuid NOT NULL,
    target_checkpoint_id uuid NOT NULL,
    dependency_role text NOT NULL,
    target_dependency_sha256 text NOT NULL,
    market_target_outcome_observation_id uuid NOT NULL,
    content_sha256 text NOT NULL,
    created_at timestamptz NOT NULL,
    CONSTRAINT outcome_metric_observation_ordinal_uk UNIQUE (
        market_target_outcome_revision_id, dependency_ordinal
    ),
    CONSTRAINT outcome_metric_observation_dependency_uk UNIQUE (
        market_target_outcome_revision_id, target_metric_dependency_id
    ),
    CONSTRAINT outcome_metric_observation_revision_fk FOREIGN KEY (
        market_target_outcome_revision_id, market_target_outcome_id,
        revision_ordinal
    ) REFERENCES mra.market_target_outcome_revision(
        market_target_outcome_revision_id, market_target_outcome_id,
        revision_ordinal
    ) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT outcome_metric_observation_metric_fk FOREIGN KEY (
        market_target_outcome_metric_id,
        market_target_outcome_revision_id, market_target_outcome_id,
        revision_ordinal, target_definition_id,
        target_metric_definition_id
    ) REFERENCES mra.market_target_outcome_metric(
        market_target_outcome_metric_id,
        market_target_outcome_revision_id, market_target_outcome_id,
        revision_ordinal, target_definition_id,
        target_metric_definition_id
    ) ON DELETE RESTRICT,
    CONSTRAINT outcome_metric_observation_dependency_fk FOREIGN KEY (
        target_metric_dependency_id, target_definition_id,
        target_metric_definition_id, target_checkpoint_id,
        dependency_ordinal, dependency_role, target_dependency_sha256
    ) REFERENCES mra.target_metric_dependency(
        target_metric_dependency_id, target_definition_id,
        target_metric_definition_id, target_checkpoint_id,
        ordinal, dependency_role, content_sha256
    ) ON DELETE RESTRICT,
    CONSTRAINT outcome_metric_observation_fact_fk FOREIGN KEY (
        market_target_outcome_observation_id,
        market_target_outcome_revision_id, market_target_outcome_id,
        revision_ordinal, target_definition_id, target_checkpoint_id
    ) REFERENCES mra.market_target_outcome_observation(
        market_target_outcome_observation_id,
        market_target_outcome_revision_id, market_target_outcome_id,
        revision_ordinal, target_definition_id, target_checkpoint_id
    ) ON DELETE RESTRICT,
    CONSTRAINT outcome_metric_observation_role_ck CHECK (
        dependency_ordinal > 0
        AND dependency_role IN ('OBSERVATION', 'PATH_MEMBER')
        AND target_dependency_sha256 ~ '^[0-9a-f]{64}$'
        AND content_sha256 ~ '^[0-9a-f]{64}$'
    )
);
CREATE INDEX outcome_metric_observation_revision_idx
    ON mra.market_target_outcome_metric_observation (
        market_target_outcome_revision_id, dependency_ordinal
    );
CREATE INDEX outcome_metric_observation_revision_authority_idx
    ON mra.market_target_outcome_metric_observation (
        market_target_outcome_revision_id, market_target_outcome_id,
        revision_ordinal
    );
CREATE INDEX outcome_metric_observation_fact_idx
    ON mra.market_target_outcome_metric_observation (
        market_target_outcome_observation_id,
        market_target_outcome_revision_id
    );
CREATE INDEX outcome_metric_observation_fact_authority_idx
    ON mra.market_target_outcome_metric_observation (
        market_target_outcome_observation_id,
        market_target_outcome_revision_id, market_target_outcome_id,
        revision_ordinal, target_definition_id, target_checkpoint_id
    );
CREATE INDEX outcome_metric_observation_metric_idx
    ON mra.market_target_outcome_metric_observation (
        market_target_outcome_metric_id,
        market_target_outcome_revision_id
    );
CREATE INDEX outcome_metric_observation_metric_authority_idx
    ON mra.market_target_outcome_metric_observation (
        market_target_outcome_metric_id,
        market_target_outcome_revision_id, market_target_outcome_id,
        revision_ordinal, target_definition_id,
        target_metric_definition_id
    );
CREATE INDEX outcome_metric_observation_dependency_authority_idx
    ON mra.market_target_outcome_metric_observation (
        target_metric_dependency_id, target_definition_id,
        target_metric_definition_id, target_checkpoint_id,
        dependency_ordinal, dependency_role, target_dependency_sha256
    );

CREATE TABLE mra.market_target_outcome_reason (
    market_target_outcome_reason_id uuid PRIMARY KEY,
    market_target_outcome_revision_id uuid NOT NULL,
    market_target_outcome_id uuid NOT NULL,
    revision_ordinal integer NOT NULL,
    reason_ordinal integer NOT NULL,
    reason_dimension text NOT NULL,
    reason_code text NOT NULL,
    market_target_outcome_source_id uuid,
    market_target_outcome_observation_id uuid,
    market_target_outcome_metric_id uuid,
    content_sha256 text NOT NULL,
    created_at timestamptz NOT NULL,
    CONSTRAINT outcome_reason_ordinal_uk UNIQUE (
        market_target_outcome_revision_id, reason_ordinal
    ),
    CONSTRAINT outcome_reason_identity_uk UNIQUE NULLS NOT DISTINCT (
        market_target_outcome_revision_id, reason_dimension, reason_code,
        market_target_outcome_source_id,
        market_target_outcome_observation_id,
        market_target_outcome_metric_id
    ),
    CONSTRAINT outcome_reason_revision_fk FOREIGN KEY (
        market_target_outcome_revision_id, market_target_outcome_id,
        revision_ordinal
    ) REFERENCES mra.market_target_outcome_revision(
        market_target_outcome_revision_id, market_target_outcome_id,
        revision_ordinal
    ) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT outcome_reason_source_fk FOREIGN KEY (
        market_target_outcome_source_id
    ) REFERENCES mra.market_target_outcome_source(
        market_target_outcome_source_id
    ) ON DELETE RESTRICT,
    CONSTRAINT outcome_reason_observation_fk FOREIGN KEY (
        market_target_outcome_observation_id
    ) REFERENCES mra.market_target_outcome_observation(
        market_target_outcome_observation_id
    ) ON DELETE RESTRICT,
    CONSTRAINT outcome_reason_metric_fk FOREIGN KEY (
        market_target_outcome_metric_id
    ) REFERENCES mra.market_target_outcome_metric(
        market_target_outcome_metric_id
    ) ON DELETE RESTRICT,
    CONSTRAINT outcome_reason_shape_ck CHECK (
        reason_ordinal > 0
        AND reason_dimension IN ('REVISION', 'SOURCE', 'OBSERVATION', 'METRIC')
        AND reason_code ~ '^[A-Z][A-Z0-9_]{0,99}$'
        AND content_sha256 ~ '^[0-9a-f]{64}$'
        AND (
            (reason_dimension = 'REVISION'
             AND market_target_outcome_source_id IS NULL
             AND market_target_outcome_observation_id IS NULL
             AND market_target_outcome_metric_id IS NULL)
            OR
            (reason_dimension = 'SOURCE'
             AND market_target_outcome_source_id IS NOT NULL
             AND market_target_outcome_observation_id IS NULL
             AND market_target_outcome_metric_id IS NULL)
            OR
            (reason_dimension = 'OBSERVATION'
             AND market_target_outcome_source_id IS NULL
             AND market_target_outcome_observation_id IS NOT NULL
             AND market_target_outcome_metric_id IS NULL)
            OR
            (reason_dimension = 'METRIC'
             AND market_target_outcome_source_id IS NULL
             AND market_target_outcome_observation_id IS NULL
             AND market_target_outcome_metric_id IS NOT NULL)
        )
    )
);
CREATE INDEX outcome_reason_revision_idx
    ON mra.market_target_outcome_reason (
        market_target_outcome_revision_id, reason_ordinal
    );
CREATE INDEX outcome_reason_revision_authority_idx
    ON mra.market_target_outcome_reason (
        market_target_outcome_revision_id, market_target_outcome_id,
        revision_ordinal
    );
CREATE INDEX outcome_reason_source_idx
    ON mra.market_target_outcome_reason (market_target_outcome_source_id)
    WHERE market_target_outcome_source_id IS NOT NULL;
CREATE INDEX outcome_reason_observation_idx
    ON mra.market_target_outcome_reason (market_target_outcome_observation_id)
    WHERE market_target_outcome_observation_id IS NOT NULL;
CREATE INDEX outcome_reason_metric_idx
    ON mra.market_target_outcome_reason (market_target_outcome_metric_id)
    WHERE market_target_outcome_metric_id IS NOT NULL;

CREATE FUNCTION mra.guard_open_outcome_child_insert()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM mra.market_target_outcome_revision AS revision
        WHERE revision.market_target_outcome_revision_id =
              NEW.market_target_outcome_revision_id
    ) THEN
        RAISE EXCEPTION 'MarketTargetOutcomeRevision is already closed'
            USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION mra.validate_outcome_revision_predecessor()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    leaf_revision_id uuid;
    leaf_revision_ordinal integer;
BEGIN
    PERFORM 1
    FROM mra.market_target_outcome
    WHERE market_target_outcome_id = NEW.market_target_outcome_id
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'MarketTargetOutcome root is absent'
            USING ERRCODE = '23503';
    END IF;

    SELECT revision.market_target_outcome_revision_id,
           revision.revision_ordinal
    INTO leaf_revision_id, leaf_revision_ordinal
    FROM mra.market_target_outcome_revision AS revision
    WHERE revision.market_target_outcome_id = NEW.market_target_outcome_id
      AND NOT EXISTS (
          SELECT 1
          FROM mra.market_target_outcome_revision AS successor
          WHERE successor.supersedes_revision_id =
                revision.market_target_outcome_revision_id
      )
    ORDER BY revision.revision_ordinal DESC
    LIMIT 1
    ;

    IF NEW.revision_ordinal = 1 THEN
        IF leaf_revision_id IS NOT NULL
           OR NEW.supersedes_revision_id IS NOT NULL THEN
            RAISE EXCEPTION 'Outcome revision one requires an empty root'
                USING ERRCODE = '55000';
        END IF;
    ELSIF leaf_revision_id IS NULL
       OR NEW.supersedes_revision_id <>
          leaf_revision_id
       OR NEW.supersedes_revision_ordinal <> leaf_revision_ordinal
       OR NEW.revision_ordinal <> leaf_revision_ordinal + 1 THEN
        RAISE EXCEPTION 'Outcome revision must directly supersede the current leaf'
            USING ERRCODE = '40001';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION mra.validate_outcome_revision_closure()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    actual_source_count bigint;
    actual_observation_count bigint;
    actual_metric_count bigint;
    actual_reference_dependency_count bigint;
    actual_observation_dependency_count bigint;
    actual_reason_count bigint;
    expected_observation_count bigint;
    expected_session_count bigint;
    expected_metric_count bigint;
    expected_reference_dependency_count bigint;
    expected_observation_dependency_count bigint;
    source_min integer;
    source_max integer;
    observation_min integer;
    observation_max integer;
    metric_min integer;
    metric_max integer;
    reason_min integer;
    reason_max integer;
    actual_source_hash text;
    actual_observation_hash text;
    actual_metric_hash text;
    actual_reference_dependency_hash text;
    actual_observation_dependency_hash text;
    actual_reason_hash text;
    actual_definition_summary_hash text;
    required_count bigint;
    required_complete_count bigint;
    required_unavailable_count bigint;
    required_failed_count bigint;
BEGIN
    SELECT count(*), min(source_ordinal), max(source_ordinal),
           mra.canonical_sha256(
               replace(
                   COALESCE(
                       json_agg(
                           json_build_object(
                               'content_sha256', content_sha256,
                               'market_target_outcome_source_id',
                                   market_target_outcome_source_id,
                               'ordinal', source_ordinal
                           ) ORDER BY source_ordinal
                       )::text,
                       '[]'
                   ),
                   ' ', ''
               )
           )
    INTO actual_source_count, source_min, source_max, actual_source_hash
    FROM mra.market_target_outcome_source
    WHERE market_target_outcome_revision_id =
          NEW.market_target_outcome_revision_id;

    SELECT count(*), min(observation_ordinal), max(observation_ordinal),
           mra.canonical_sha256(
               replace(
                   COALESCE(
                       json_agg(
                           json_build_object(
                               'content_sha256', content_sha256,
                               'market_target_outcome_observation_id',
                                   market_target_outcome_observation_id,
                               'ordinal', observation_ordinal
                           ) ORDER BY observation_ordinal
                       )::text,
                       '[]'
                   ),
                   ' ', ''
               )
           )
    INTO actual_observation_count, observation_min, observation_max,
         actual_observation_hash
    FROM mra.market_target_outcome_observation
    WHERE market_target_outcome_revision_id =
          NEW.market_target_outcome_revision_id;

    SELECT count(*), min(metric_ordinal), max(metric_ordinal),
           mra.canonical_sha256(
               replace(
                   COALESCE(
                       json_agg(
                           json_build_object(
                               'content_sha256', content_sha256,
                               'market_target_outcome_metric_id',
                                   market_target_outcome_metric_id,
                               'ordinal', metric_ordinal
                           ) ORDER BY metric_ordinal
                       )::text,
                       '[]'
                   ),
                   ' ', ''
               )
           )
    INTO actual_metric_count, metric_min, metric_max, actual_metric_hash
    FROM mra.market_target_outcome_metric
    WHERE market_target_outcome_revision_id =
          NEW.market_target_outcome_revision_id;

    SELECT count(*),
           mra.canonical_sha256(
               replace(
                   COALESCE(
                       json_agg(
                           json_build_object(
                               'content_sha256', content_sha256,
                               'market_target_outcome_metric_reference_id',
                                   market_target_outcome_metric_reference_id,
                               'ordinal', dependency_ordinal
                           ) ORDER BY dependency_ordinal
                       )::text,
                       '[]'
                   ),
                   ' ', ''
               )
           )
    INTO actual_reference_dependency_count,
         actual_reference_dependency_hash
    FROM mra.market_target_outcome_metric_reference
    WHERE market_target_outcome_revision_id =
          NEW.market_target_outcome_revision_id;

    SELECT count(*),
           mra.canonical_sha256(
               replace(
                   COALESCE(
                       json_agg(
                           json_build_object(
                               'content_sha256', content_sha256,
                               'market_target_outcome_metric_observation_id',
                                   market_target_outcome_metric_observation_id,
                               'ordinal', dependency_ordinal
                           ) ORDER BY dependency_ordinal
                       )::text,
                       '[]'
                   ),
                   ' ', ''
               )
           )
    INTO actual_observation_dependency_count,
         actual_observation_dependency_hash
    FROM mra.market_target_outcome_metric_observation
    WHERE market_target_outcome_revision_id =
          NEW.market_target_outcome_revision_id;

    SELECT count(*), min(reason_ordinal), max(reason_ordinal),
           mra.canonical_sha256(
               replace(
                   COALESCE(
                       json_agg(
                           json_build_object(
                               'content_sha256', content_sha256,
                               'market_target_outcome_reason_id',
                                   market_target_outcome_reason_id,
                               'ordinal', reason_ordinal
                           ) ORDER BY reason_ordinal
                       )::text,
                       '[]'
                   ),
                   ' ', ''
               )
           )
    INTO actual_reason_count, reason_min, reason_max, actual_reason_hash
    FROM mra.market_target_outcome_reason
    WHERE market_target_outcome_revision_id =
          NEW.market_target_outcome_revision_id;

    SELECT count(*) FILTER (
               WHERE checkpoint_role = 'OUTCOME_OBSERVATION'
           ),
           count(DISTINCT session_offset) FILTER (
               WHERE checkpoint_role = 'OUTCOME_OBSERVATION'
           )
    INTO expected_observation_count, expected_session_count
    FROM mra.target_checkpoint
    WHERE target_definition_id = NEW.target_definition_id;

    SELECT count(*)
    INTO expected_metric_count
    FROM mra.target_metric_definition
    WHERE target_definition_id = NEW.target_definition_id;

    SELECT count(*) FILTER (WHERE dependency_role = 'REFERENCE'),
           count(*) FILTER (
               WHERE dependency_role IN ('OBSERVATION', 'PATH_MEMBER')
           )
    INTO expected_reference_dependency_count,
         expected_observation_dependency_count
    FROM mra.target_metric_dependency
    WHERE target_definition_id = NEW.target_definition_id;

    IF actual_source_count <> NEW.source_count
       OR actual_observation_count <> NEW.observation_count
       OR actual_metric_count <> NEW.metric_count
       OR actual_reference_dependency_count <>
          NEW.reference_dependency_count
       OR actual_observation_dependency_count <>
          NEW.observation_dependency_count
       OR actual_reason_count <> NEW.reason_count
       OR actual_source_count <>
          expected_observation_count + expected_session_count
       OR actual_observation_count <> expected_observation_count
       OR actual_metric_count <> expected_metric_count
       OR actual_reference_dependency_count <>
          expected_reference_dependency_count
       OR actual_observation_dependency_count <>
          expected_observation_dependency_count
       OR source_min <> 1 OR source_max <> actual_source_count
       OR observation_min <> 1
       OR observation_max <> actual_observation_count
       OR metric_min <> 1 OR metric_max <> actual_metric_count
       OR (actual_reason_count > 0
           AND (reason_min <> 1 OR reason_max <> actual_reason_count)) THEN
        RAISE EXCEPTION 'Outcome revision child roster is incomplete'
            USING ERRCODE = '55000';
    END IF;

    IF actual_source_hash <> NEW.source_roster_sha256
       OR actual_observation_hash <> NEW.observation_roster_sha256
       OR actual_metric_hash <> NEW.metric_roster_sha256
       OR actual_reference_dependency_hash <>
          NEW.reference_dependency_roster_sha256
       OR actual_observation_dependency_hash <>
          NEW.observation_dependency_roster_sha256
       OR actual_reason_hash <> NEW.reason_roster_sha256 THEN
        RAISE EXCEPTION 'Outcome revision roster hash does not reconcile'
            USING ERRCODE = '55000';
    END IF;

    SELECT mra.canonical_sha256(
        replace(
            json_build_object(
                'availability_status', NEW.availability_status,
                'decision_reference_observation_id',
                    NEW.decision_reference_observation_id,
                'decision_reference_sha256', NEW.decision_reference_sha256,
                'finality_status', NEW.finality_status,
                'knowledge_cutoff',
                    mra.canonical_timestamptz_text(NEW.knowledge_cutoff),
                'metric_count', NEW.metric_count,
                'metric_roster_sha256', NEW.metric_roster_sha256,
                'observation_count', NEW.observation_count,
                'observation_cutoff',
                    mra.canonical_timestamptz_text(NEW.observation_cutoff),
                'observation_dependency_count',
                    NEW.observation_dependency_count,
                'observation_dependency_roster_sha256',
                    NEW.observation_dependency_roster_sha256,
                'observation_roster_sha256',
                    NEW.observation_roster_sha256,
                'outcome_status', NEW.outcome_status,
                'reason_count', NEW.reason_count,
                'reason_roster_sha256', NEW.reason_roster_sha256,
                'reference_dependency_count',
                    NEW.reference_dependency_count,
                'reference_dependency_roster_sha256',
                    NEW.reference_dependency_roster_sha256,
                'source_count', NEW.source_count,
                'source_roster_sha256', NEW.source_roster_sha256,
                'target_definition_id', NEW.target_definition_id,
                'target_definition_sha256',
                    (SELECT definition.content_sha256
                     FROM mra.target_definition AS definition
                     WHERE definition.target_definition_id =
                           NEW.target_definition_id)
            )::text,
            ' ', ''
        )
    ) INTO actual_definition_summary_hash;
    IF actual_definition_summary_hash <> NEW.definition_summary_sha256 THEN
        RAISE EXCEPTION 'Outcome definition summary hash does not reconcile'
            USING ERRCODE = '55000';
    END IF;

    IF EXISTS (
        SELECT checkpoint.session_offset
        FROM mra.target_checkpoint AS checkpoint
        WHERE checkpoint.target_definition_id = NEW.target_definition_id
          AND checkpoint.checkpoint_role = 'OUTCOME_OBSERVATION'
        GROUP BY checkpoint.session_offset
        EXCEPT
        SELECT source.session_offset
        FROM mra.market_target_outcome_source AS source
        WHERE source.market_target_outcome_revision_id =
              NEW.market_target_outcome_revision_id
          AND source.source_kind = 'TRADING_SESSION'
          AND source.source_role = 'CALENDAR_SESSION'
    ) OR EXISTS (
        SELECT 1
        FROM mra.market_target_outcome_source AS source
        WHERE source.market_target_outcome_revision_id =
              NEW.market_target_outcome_revision_id
          AND (
              (source.source_kind = 'TRADING_SESSION'
               AND source.source_role <> 'CALENDAR_SESSION')
              OR
              (source.source_kind IN ('BAR_REVISION', 'SOURCE_GAP')
               AND source.source_role <> 'OUTCOME_OBSERVATION')
          )
    ) THEN
        RAISE EXCEPTION 'Outcome exact Session/source coverage is incomplete'
            USING ERRCODE = '55000';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM mra.target_checkpoint AS checkpoint
        LEFT JOIN mra.market_target_outcome_observation AS observation
          ON observation.market_target_outcome_revision_id =
             NEW.market_target_outcome_revision_id
         AND observation.target_checkpoint_id =
             checkpoint.target_checkpoint_id
        WHERE checkpoint.target_definition_id = NEW.target_definition_id
          AND checkpoint.checkpoint_role = 'OUTCOME_OBSERVATION'
          AND observation.market_target_outcome_observation_id IS NULL
    ) OR EXISTS (
        SELECT 1
        FROM mra.target_metric_definition AS definition
        LEFT JOIN mra.market_target_outcome_metric AS metric
          ON metric.market_target_outcome_revision_id =
             NEW.market_target_outcome_revision_id
         AND metric.target_metric_definition_id =
             definition.target_metric_definition_id
        WHERE definition.target_definition_id = NEW.target_definition_id
          AND metric.market_target_outcome_metric_id IS NULL
    ) OR EXISTS (
        SELECT 1
        FROM mra.target_metric_dependency AS dependency
        LEFT JOIN mra.market_target_outcome_metric_reference AS reference
          ON reference.market_target_outcome_revision_id =
             NEW.market_target_outcome_revision_id
         AND reference.target_metric_dependency_id =
             dependency.target_metric_dependency_id
        LEFT JOIN mra.market_target_outcome_metric_observation AS observation
          ON observation.market_target_outcome_revision_id =
             NEW.market_target_outcome_revision_id
         AND observation.target_metric_dependency_id =
             dependency.target_metric_dependency_id
        WHERE dependency.target_definition_id = NEW.target_definition_id
          AND (
              (dependency.dependency_role = 'REFERENCE'
               AND reference.market_target_outcome_metric_reference_id IS NULL)
              OR
              (dependency.dependency_role IN ('OBSERVATION', 'PATH_MEMBER')
               AND observation.market_target_outcome_metric_observation_id IS NULL)
          )
    ) THEN
        RAISE EXCEPTION 'Outcome Target fact/dependency closure is incomplete'
            USING ERRCODE = '55000';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM mra.market_target_outcome_observation AS observation
        JOIN mra.market_target_outcome_source AS source
          ON source.market_target_outcome_source_id =
             observation.market_target_outcome_source_id
        JOIN mra.market_bar_revision AS bar
          ON bar.bar_revision_id = source.bar_revision_id
        JOIN mra.target_checkpoint AS checkpoint
          ON checkpoint.target_checkpoint_id =
             observation.target_checkpoint_id
        WHERE observation.market_target_outcome_revision_id =
              NEW.market_target_outcome_revision_id
          AND observation.source_kind = 'BAR_REVISION'
          AND (
              observation.open_value IS DISTINCT FROM bar.open_value
              OR observation.high_value IS DISTINCT FROM bar.high_value
              OR observation.low_value IS DISTINCT FROM bar.low_value
              OR observation.close_value IS DISTINCT FROM bar.close_value
              OR observation.selected_value IS DISTINCT FROM
                 CASE checkpoint.value_field
                     WHEN 'OPEN' THEN bar.open_value
                     WHEN 'HIGH' THEN bar.high_value
                     WHEN 'LOW' THEN bar.low_value
                     WHEN 'CLOSE' THEN bar.close_value
                 END
          )
    ) THEN
        RAISE EXCEPTION 'Outcome observation differs from exact Market revision'
            USING ERRCODE = '55000';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM mra.market_target_outcome_reason AS reason
        LEFT JOIN mra.market_target_outcome_source AS source
          ON source.market_target_outcome_source_id =
             reason.market_target_outcome_source_id
        LEFT JOIN mra.market_target_outcome_observation AS observation
          ON observation.market_target_outcome_observation_id =
             reason.market_target_outcome_observation_id
        LEFT JOIN mra.market_target_outcome_metric AS metric
          ON metric.market_target_outcome_metric_id =
             reason.market_target_outcome_metric_id
        WHERE reason.market_target_outcome_revision_id =
              NEW.market_target_outcome_revision_id
          AND (
              (source.market_target_outcome_source_id IS NOT NULL
               AND source.market_target_outcome_revision_id <>
                   NEW.market_target_outcome_revision_id)
              OR
              (observation.market_target_outcome_observation_id IS NOT NULL
               AND observation.market_target_outcome_revision_id <>
                   NEW.market_target_outcome_revision_id)
              OR
              (metric.market_target_outcome_metric_id IS NOT NULL
               AND metric.market_target_outcome_revision_id <>
                   NEW.market_target_outcome_revision_id)
          )
    ) THEN
        RAISE EXCEPTION 'Outcome reason crosses revision boundary'
            USING ERRCODE = '55000';
    END IF;

    SELECT count(*),
           count(*) FILTER (WHERE metric.value_status = 'COMPLETE'),
           count(*) FILTER (WHERE metric.value_status = 'UNAVAILABLE'),
           count(*) FILTER (WHERE metric.value_status = 'FAILED')
    INTO required_count, required_complete_count,
         required_unavailable_count, required_failed_count
    FROM mra.market_target_outcome_metric AS metric
    WHERE metric.market_target_outcome_revision_id =
          NEW.market_target_outcome_revision_id
      AND metric.completion_rule = 'REQUIRED';

    IF required_count = 0
       OR (required_failed_count > 0
           AND (NEW.outcome_status <> 'FAILED'
                OR NEW.availability_status <> 'FAILED'))
       OR (required_failed_count = 0
           AND required_complete_count = required_count
           AND (NEW.outcome_status <> 'COMPLETE'
                OR NEW.availability_status <> 'AVAILABLE'))
       OR (required_failed_count = 0
           AND required_unavailable_count = required_count
           AND (NEW.outcome_status <> 'UNAVAILABLE'
                OR NEW.availability_status <> 'UNAVAILABLE'))
       OR (required_failed_count = 0
           AND required_complete_count <> required_count
           AND required_unavailable_count <> required_count
           AND (
               NEW.outcome_status <> 'PARTIAL'
               OR NEW.availability_status <>
                  CASE WHEN required_unavailable_count > 0
                       THEN 'UNAVAILABLE' ELSE 'AVAILABLE' END
           )) THEN
        RAISE EXCEPTION 'Outcome aggregate state does not reconcile'
            USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION mra.guard_open_target_child_insert()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM mra.target_definition AS definition
        WHERE definition.target_definition_id = NEW.target_definition_id
    ) THEN
        RAISE EXCEPTION 'TargetDefinition is already closed'
            USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION mra.guard_open_decision_child_insert()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM mra.decision_run AS decision
        WHERE decision.decision_run_id = NEW.decision_run_id
    ) THEN
        RAISE EXCEPTION 'DecisionRun is already closed'
            USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION mra.validate_decision_run_closure()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    actual_target_count bigint;
    actual_commitment_count bigint;
    actual_reference_count bigint;
    target_min integer;
    target_max integer;
    missing_commitment_count bigint;
    actual_candidate_hash text;
    actual_target_hash text;
    actual_commitment_hash text;
BEGIN
    SELECT count(*), min(ordinal), max(ordinal)
    INTO actual_target_count, target_min, target_max
    FROM mra.decision_run_target
    WHERE decision_run_id = NEW.decision_run_id;

    SELECT count(*)
    INTO actual_commitment_count
    FROM mra.decision_target_commitment
    WHERE decision_run_id = NEW.decision_run_id;

    SELECT count(*)
    INTO actual_reference_count
    FROM mra.decision_reference_observation
    WHERE decision_run_id = NEW.decision_run_id;

    SELECT count(*)
    INTO missing_commitment_count
    FROM mra.candidate AS candidate
    CROSS JOIN mra.decision_run_target AS target
    LEFT JOIN mra.decision_target_commitment AS commitment
      ON commitment.decision_run_id = target.decision_run_id
     AND commitment.decision_run_target_id = target.decision_run_target_id
     AND commitment.candidate_id = candidate.candidate_id
    WHERE candidate.candidate_set_id = NEW.candidate_set_id
      AND target.decision_run_id = NEW.decision_run_id
      AND commitment.commitment_id IS NULL;

    IF actual_target_count <> NEW.target_count
       OR actual_commitment_count <> NEW.commitment_count
       OR actual_reference_count <> NEW.reference_count
       OR target_min <> 1
       OR target_max <> actual_target_count
       OR missing_commitment_count <> 0 THEN
        RAISE EXCEPTION 'DecisionRun child roster is incomplete'
            USING ERRCODE = '55000';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM mra.decision_target_commitment AS commitment
        LEFT JOIN mra.decision_reference_observation AS reference
          ON reference.decision_reference_observation_id =
             commitment.decision_reference_observation_id
         AND reference.commitment_id = commitment.commitment_id
         AND reference.content_sha256 =
             commitment.decision_reference_sha256
        WHERE commitment.decision_run_id = NEW.decision_run_id
          AND reference.decision_reference_observation_id IS NULL
    ) OR EXISTS (
        SELECT 1
        FROM mra.decision_reference_observation AS reference
        LEFT JOIN mra.decision_target_commitment AS commitment
          ON commitment.commitment_id = reference.commitment_id
         AND commitment.decision_reference_observation_id =
             reference.decision_reference_observation_id
         AND commitment.decision_reference_sha256 = reference.content_sha256
        WHERE reference.decision_run_id = NEW.decision_run_id
          AND commitment.commitment_id IS NULL
    ) THEN
        RAISE EXCEPTION 'Decision commitment/reference binding is incomplete'
            USING ERRCODE = '55000';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM mra.decision_run_target AS target
        JOIN mra.provider_product AS product
          ON product.provider_product_id =
             target.reference_provider_product_id
        WHERE target.decision_run_id = NEW.decision_run_id
          AND (
              NOT ('MARKET_BAR' = ANY(product.fact_kinds))
              OR NOT (target.timeframe = ANY(product.bar_timeframes))
              OR NOT (target.price_basis = ANY(product.price_bases))
          )
    ) THEN
        RAISE EXCEPTION 'Decision reference Provider Product lacks Target capability'
            USING ERRCODE = '55000';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM mra.decision_reference_observation AS reference
        JOIN mra.market_bar_revision AS bar
          ON bar.bar_revision_id = reference.bar_revision_id
        WHERE reference.decision_run_id = NEW.decision_run_id
          AND reference.source_kind = 'BAR_REVISION'
          AND reference.decimal_value IS DISTINCT FROM
              CASE reference.value_field
                  WHEN 'OPEN' THEN bar.open_value
                  WHEN 'HIGH' THEN bar.high_value
                  WHEN 'LOW' THEN bar.low_value
                  WHEN 'CLOSE' THEN bar.close_value
              END
    ) THEN
        RAISE EXCEPTION 'Decision reference value differs from exact Market revision'
            USING ERRCODE = '55000';
    END IF;

    SELECT mra.canonical_sha256(
               replace(
                   COALESCE(
                       json_agg(
                           json_build_object(
                               'candidate_id', candidate_id,
                               'disposition', disposition,
                               'instrument_id', instrument_id
                           ) ORDER BY candidate_id
                       )::text,
                       '[]'
                   ),
                   ' ',
                   ''
               )
           )
    INTO actual_candidate_hash
    FROM mra.candidate
    WHERE candidate_set_id = NEW.candidate_set_id;

    SELECT mra.canonical_sha256(
               replace(
                   json_agg(
                       json_build_object(
                           'content_sha256', content_sha256,
                           'decision_run_target_id', decision_run_target_id,
                           'ordinal', ordinal
                       ) ORDER BY ordinal
                   )::text,
                   ' ',
                   ''
               )
           )
    INTO actual_target_hash
    FROM mra.decision_run_target
    WHERE decision_run_id = NEW.decision_run_id;

    SELECT mra.canonical_sha256(
               replace(
                   COALESCE(
                       json_agg(
                           json_build_object(
                               'commitment_id', commitment.commitment_id,
                               'content_sha256', commitment.content_sha256,
                               'decision_run_target_id',
                                   commitment.decision_run_target_id
                           ) ORDER BY target.ordinal,
                                      commitment.candidate_id
                       )::text,
                       '[]'
                   ),
                   ' ',
                   ''
               )
           )
    INTO actual_commitment_hash
    FROM mra.decision_target_commitment AS commitment
    JOIN mra.decision_run_target AS target
      ON target.decision_run_target_id = commitment.decision_run_target_id
    WHERE commitment.decision_run_id = NEW.decision_run_id;

    IF actual_candidate_hash <> NEW.candidate_roster_sha256
       OR actual_target_hash <> NEW.target_roster_sha256
       OR actual_commitment_hash <> NEW.commitment_roster_sha256 THEN
        RAISE EXCEPTION 'DecisionRun roster hash does not reconcile'
            USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION mra.validate_target_definition_closure()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    actual_checkpoint_count bigint;
    actual_metric_count bigint;
    actual_dependency_count bigint;
    reference_count bigint;
    outcome_count bigint;
    required_metric_count bigint;
    checkpoint_min integer;
    checkpoint_max integer;
    metric_min integer;
    metric_max integer;
    dependency_min integer;
    dependency_max integer;
    actual_checkpoint_hash text;
    actual_metric_hash text;
    actual_dependency_hash text;
    predecessor record;
BEGIN
    SELECT count(*),
           count(*) FILTER (WHERE checkpoint_role = 'DECISION_REFERENCE'),
           count(*) FILTER (WHERE checkpoint_role = 'OUTCOME_OBSERVATION'),
           min(ordinal), max(ordinal)
    INTO actual_checkpoint_count, reference_count, outcome_count,
         checkpoint_min, checkpoint_max
    FROM mra.target_checkpoint
    WHERE target_definition_id = NEW.target_definition_id;

    SELECT count(*),
           count(*) FILTER (WHERE completion_rule = 'REQUIRED'),
           min(ordinal), max(ordinal)
    INTO actual_metric_count, required_metric_count, metric_min, metric_max
    FROM mra.target_metric_definition
    WHERE target_definition_id = NEW.target_definition_id;

    SELECT count(*), min(ordinal), max(ordinal)
    INTO actual_dependency_count, dependency_min, dependency_max
    FROM mra.target_metric_dependency
    WHERE target_definition_id = NEW.target_definition_id;

    IF actual_checkpoint_count <> NEW.checkpoint_count
       OR actual_metric_count <> NEW.metric_count
       OR actual_dependency_count <> NEW.dependency_count
       OR reference_count <> 1
       OR outcome_count < 1
       OR checkpoint_min <> 1
       OR checkpoint_max <> actual_checkpoint_count
       OR metric_min <> 1
       OR metric_max <> actual_metric_count
       OR dependency_min <> 1
       OR dependency_max <> actual_dependency_count
       OR required_metric_count < 1 THEN
        RAISE EXCEPTION 'TargetDefinition child roster is incomplete'
            USING ERRCODE = '55000';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM mra.target_metric_definition AS metric
        LEFT JOIN mra.target_metric_dependency AS dependency
          ON dependency.target_metric_definition_id =
             metric.target_metric_definition_id
         AND dependency.target_definition_id = metric.target_definition_id
        WHERE metric.target_definition_id = NEW.target_definition_id
        GROUP BY metric.target_metric_definition_id
        HAVING count(dependency.target_metric_dependency_id) = 0
    ) THEN
        RAISE EXCEPTION 'every Target metric requires a dependency'
            USING ERRCODE = '55000';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM mra.target_metric_definition AS metric
        JOIN mra.target_metric_dependency AS dependency
          ON dependency.target_metric_definition_id =
             metric.target_metric_definition_id
         AND dependency.target_definition_id = metric.target_definition_id
        WHERE metric.target_definition_id = NEW.target_definition_id
        GROUP BY metric.target_metric_definition_id, metric.metric_kind
        HAVING
            (metric.metric_kind = 'SIMPLE_RETURN'
             AND (count(*) <> 2
                  OR count(*) FILTER (
                      WHERE dependency.dependency_role = 'REFERENCE'
                  ) <> 1
                  OR count(*) FILTER (
                      WHERE dependency.dependency_role = 'OBSERVATION'
                  ) <> 1))
            OR
            (metric.metric_kind = 'OBSERVATION_VALUE'
             AND (count(*) <> 1
                  OR count(*) FILTER (
                      WHERE dependency.dependency_role = 'OBSERVATION'
                  ) <> 1))
            OR
            (metric.metric_kind IN (
                 'MAX_FAVORABLE_EXCURSION',
                 'MAX_ADVERSE_EXCURSION',
                 'BARRIER_HIT'
             )
             AND (count(*) FILTER (
                      WHERE dependency.dependency_role = 'REFERENCE'
                  ) <> 1
                  OR count(*) FILTER (
                      WHERE dependency.dependency_role = 'PATH_MEMBER'
                  ) < 1
                  OR count(*) FILTER (
                      WHERE dependency.dependency_role NOT IN (
                          'REFERENCE', 'PATH_MEMBER'
                      )
                  ) <> 0))
    ) THEN
        RAISE EXCEPTION 'Target metric dependency shape is Outcome-incompatible'
            USING ERRCODE = '55000';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM mra.target_metric_dependency AS dependency
        JOIN mra.target_checkpoint AS checkpoint
          ON checkpoint.target_checkpoint_id = dependency.target_checkpoint_id
         AND checkpoint.target_definition_id = dependency.target_definition_id
        WHERE dependency.target_definition_id = NEW.target_definition_id
          AND (
              (dependency.dependency_role = 'REFERENCE'
               AND checkpoint.checkpoint_role <> 'DECISION_REFERENCE')
              OR
              (dependency.dependency_role IN ('OBSERVATION', 'PATH_MEMBER')
               AND checkpoint.checkpoint_role <> 'OUTCOME_OBSERVATION')
          )
    ) THEN
        RAISE EXCEPTION 'Target dependency role/checkpoint shape is invalid'
            USING ERRCODE = '55000';
    END IF;

    IF NEW.version > 1 THEN
        SELECT target_code, version
        INTO predecessor
        FROM mra.target_definition
        WHERE target_definition_id = NEW.supersedes_target_definition_id
        FOR SHARE;
        IF NOT FOUND
           OR predecessor.target_code <> NEW.target_code
           OR predecessor.version + 1 <> NEW.version THEN
            RAISE EXCEPTION 'Target supersession is not the immediate same-code version'
                USING ERRCODE = '55000';
        END IF;
    END IF;

    SELECT mra.canonical_sha256(
               replace(
                   json_agg(
                       json_build_object(
                           'content_sha256', content_sha256,
                           'ordinal', ordinal,
                           'target_checkpoint_id', target_checkpoint_id
                       ) ORDER BY ordinal
                   )::text,
                   ' ',
                   ''
               )
           )
    INTO actual_checkpoint_hash
    FROM mra.target_checkpoint
    WHERE target_definition_id = NEW.target_definition_id;

    SELECT mra.canonical_sha256(
               replace(
                   json_agg(
                       json_build_object(
                           'content_sha256', content_sha256,
                           'ordinal', ordinal,
                           'target_metric_definition_id',
                               target_metric_definition_id
                       ) ORDER BY ordinal
                   )::text,
                   ' ',
                   ''
               )
           )
    INTO actual_metric_hash
    FROM mra.target_metric_definition
    WHERE target_definition_id = NEW.target_definition_id;

    SELECT mra.canonical_sha256(
               replace(
                   json_agg(
                       json_build_object(
                           'content_sha256', content_sha256,
                           'ordinal', ordinal,
                           'target_metric_dependency_id',
                               target_metric_dependency_id
                       ) ORDER BY ordinal
                   )::text,
                   ' ',
                   ''
               )
           )
    INTO actual_dependency_hash
    FROM mra.target_metric_dependency
    WHERE target_definition_id = NEW.target_definition_id;

    IF actual_checkpoint_hash <> NEW.checkpoint_roster_sha256
       OR actual_metric_hash <> NEW.metric_roster_sha256
       OR actual_dependency_hash <> NEW.dependency_roster_sha256 THEN
        RAISE EXCEPTION 'TargetDefinition roster hash does not reconcile'
            USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER schema_epoch_append_only
BEFORE UPDATE OR DELETE ON mra.schema_epoch
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER schema_migrations_append_only
BEFORE UPDATE OR DELETE ON mra.schema_migrations
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER artifact_dependency_append_only
BEFORE UPDATE OR DELETE ON mra.artifact_dependency
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER artifact_verification_append_only
BEFORE UPDATE OR DELETE ON mra.artifact_verification
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER audit_event_append_only
BEFORE UPDATE OR DELETE ON mra.audit_event
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER runtime_schedule_guard
BEFORE UPDATE ON mra.runtime_schedule
FOR EACH ROW EXECUTE FUNCTION mra.guard_runtime_schedule_update();
CREATE TRIGGER runtime_schedule_no_delete
BEFORE DELETE ON mra.runtime_schedule
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER runtime_run_guard
BEFORE UPDATE ON mra.runtime_run
FOR EACH ROW EXECUTE FUNCTION mra.guard_runtime_run_update();
CREATE TRIGGER runtime_run_config_guard
BEFORE INSERT ON mra.runtime_run
FOR EACH ROW EXECUTE FUNCTION mra.validate_runtime_run_config();
CREATE TRIGGER runtime_run_no_delete
BEFORE DELETE ON mra.runtime_run
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER runtime_step_guard
BEFORE UPDATE ON mra.runtime_step
FOR EACH ROW EXECUTE FUNCTION mra.guard_runtime_step_update();
CREATE TRIGGER runtime_step_no_delete
BEFORE DELETE ON mra.runtime_step
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER runtime_attempt_guard
BEFORE UPDATE ON mra.runtime_attempt
FOR EACH ROW EXECUTE FUNCTION mra.guard_runtime_attempt_update();
CREATE TRIGGER runtime_attempt_no_delete
BEFORE DELETE ON mra.runtime_attempt
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER command_receipt_guard
BEFORE UPDATE ON mra.command_receipt
FOR EACH ROW EXECUTE FUNCTION mra.guard_command_receipt_update();
CREATE TRIGGER command_receipt_no_delete
BEFORE DELETE ON mra.command_receipt
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER artifact_guard
BEFORE UPDATE ON mra.artifact
FOR EACH ROW EXECUTE FUNCTION mra.guard_artifact_update();
CREATE TRIGGER artifact_no_delete
BEFORE DELETE ON mra.artifact
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER artifact_gc_candidate_guard
BEFORE UPDATE ON mra.artifact_gc_candidate
FOR EACH ROW EXECUTE FUNCTION mra.guard_artifact_gc_candidate_update();
CREATE TRIGGER artifact_gc_candidate_no_delete
BEFORE DELETE ON mra.artifact_gc_candidate
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER runtime_step_dependency_append_only
BEFORE UPDATE OR DELETE ON mra.runtime_step_dependency
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER provider_append_only
BEFORE UPDATE OR DELETE ON mra.provider
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER provider_product_revision_predecessor
BEFORE INSERT ON mra.provider_product
FOR EACH ROW EXECUTE FUNCTION mra.validate_market_revision_predecessor();
CREATE TRIGGER provider_product_append_only
BEFORE UPDATE OR DELETE ON mra.provider_product
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER data_capture_validate_insert
BEFORE INSERT ON mra.data_capture
FOR EACH ROW EXECUTE FUNCTION mra.validate_data_capture_insert();
CREATE TRIGGER data_capture_append_only
BEFORE UPDATE OR DELETE ON mra.data_capture
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER instrument_temporal_validate
BEFORE INSERT ON mra.instrument
FOR EACH ROW EXECUTE FUNCTION mra.validate_market_fact_temporal();
CREATE TRIGGER instrument_gap_exclusive
BEFORE INSERT ON mra.instrument
FOR EACH ROW EXECUTE FUNCTION mra.reject_fact_gap_duality();
CREATE TRIGGER instrument_append_only
BEFORE UPDATE OR DELETE ON mra.instrument
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER instrument_identifier_append_only
BEFORE UPDATE OR DELETE ON mra.instrument_identifier
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER instrument_identifier_temporal_validate
BEFORE INSERT ON mra.instrument_identifier
FOR EACH ROW EXECUTE FUNCTION mra.validate_market_fact_temporal();
CREATE TRIGGER instrument_identifier_validate_insert
BEFORE INSERT ON mra.instrument_identifier
FOR EACH ROW EXECUTE FUNCTION mra.validate_instrument_identifier_insert();
CREATE TRIGGER instrument_identifier_revision_predecessor
BEFORE INSERT ON mra.instrument_identifier
FOR EACH ROW EXECUTE FUNCTION mra.validate_market_revision_predecessor();
CREATE TRIGGER instrument_identifier_gap_exclusive
BEFORE INSERT ON mra.instrument_identifier
FOR EACH ROW EXECUTE FUNCTION mra.reject_fact_gap_duality();
CREATE TRIGGER trading_session_append_only
BEFORE UPDATE OR DELETE ON mra.trading_session
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER trading_session_temporal_validate
BEFORE INSERT ON mra.trading_session
FOR EACH ROW EXECUTE FUNCTION mra.validate_market_fact_temporal();
CREATE TRIGGER trading_session_gap_exclusive
BEFORE INSERT ON mra.trading_session
FOR EACH ROW EXECUTE FUNCTION mra.reject_fact_gap_duality();
CREATE TRIGGER classification_append_only
BEFORE UPDATE OR DELETE ON mra.classification
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER classification_temporal_validate
BEFORE INSERT ON mra.classification
FOR EACH ROW EXECUTE FUNCTION mra.validate_market_fact_temporal();
CREATE TRIGGER classification_revision_predecessor
BEFORE INSERT ON mra.classification
FOR EACH ROW EXECUTE FUNCTION mra.validate_market_revision_predecessor();
CREATE TRIGGER classification_validate_insert
BEFORE INSERT ON mra.classification
FOR EACH ROW EXECUTE FUNCTION mra.validate_classification_insert();
CREATE TRIGGER classification_gap_exclusive
BEFORE INSERT ON mra.classification
FOR EACH ROW EXECUTE FUNCTION mra.reject_fact_gap_duality();
CREATE TRIGGER classification_membership_revision_append_only
BEFORE UPDATE OR DELETE ON mra.classification_membership_revision
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER classification_membership_temporal_validate
BEFORE INSERT ON mra.classification_membership_revision
FOR EACH ROW EXECUTE FUNCTION mra.validate_market_fact_temporal();
CREATE TRIGGER classification_membership_revision_predecessor
BEFORE INSERT ON mra.classification_membership_revision
FOR EACH ROW EXECUTE FUNCTION mra.validate_market_revision_predecessor();
CREATE TRIGGER classification_membership_validate_insert
BEFORE INSERT ON mra.classification_membership_revision
FOR EACH ROW EXECUTE FUNCTION mra.validate_classification_membership_insert();
CREATE TRIGGER classification_membership_gap_exclusive
BEFORE INSERT ON mra.classification_membership_revision
FOR EACH ROW EXECUTE FUNCTION mra.reject_fact_gap_duality();
CREATE TRIGGER market_bar_revision_append_only
BEFORE UPDATE OR DELETE ON mra.market_bar_revision
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER market_bar_temporal_validate
BEFORE INSERT ON mra.market_bar_revision
FOR EACH ROW EXECUTE FUNCTION mra.validate_market_fact_temporal();
CREATE TRIGGER market_bar_revision_predecessor
BEFORE INSERT ON mra.market_bar_revision
FOR EACH ROW EXECUTE FUNCTION mra.validate_market_revision_predecessor();
CREATE TRIGGER market_bar_session_validate
BEFORE INSERT ON mra.market_bar_revision
FOR EACH ROW EXECUTE FUNCTION mra.validate_market_bar_session();
CREATE TRIGGER market_bar_gap_exclusive
BEFORE INSERT ON mra.market_bar_revision
FOR EACH ROW EXECUTE FUNCTION mra.reject_fact_gap_duality();
CREATE TRIGGER instrument_fact_revision_append_only
BEFORE UPDATE OR DELETE ON mra.instrument_fact_revision
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER instrument_fact_temporal_validate
BEFORE INSERT ON mra.instrument_fact_revision
FOR EACH ROW EXECUTE FUNCTION mra.validate_market_fact_temporal();
CREATE TRIGGER instrument_fact_revision_predecessor
BEFORE INSERT ON mra.instrument_fact_revision
FOR EACH ROW EXECUTE FUNCTION mra.validate_market_revision_predecessor();
CREATE TRIGGER instrument_fact_session_validate
BEFORE INSERT ON mra.instrument_fact_revision
FOR EACH ROW EXECUTE FUNCTION mra.validate_instrument_fact_session();
CREATE TRIGGER instrument_fact_timeline_validate
BEFORE INSERT ON mra.instrument_fact_revision
FOR EACH ROW EXECUTE FUNCTION mra.validate_instrument_fact_timeline_insert();
CREATE TRIGGER instrument_fact_gap_exclusive
BEFORE INSERT ON mra.instrument_fact_revision
FOR EACH ROW EXECUTE FUNCTION mra.reject_fact_gap_duality();
CREATE TRIGGER corporate_action_revision_append_only
BEFORE UPDATE OR DELETE ON mra.corporate_action_revision
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER corporate_action_temporal_validate
BEFORE INSERT ON mra.corporate_action_revision
FOR EACH ROW EXECUTE FUNCTION mra.validate_market_fact_temporal();
CREATE TRIGGER corporate_action_revision_predecessor
BEFORE INSERT ON mra.corporate_action_revision
FOR EACH ROW EXECUTE FUNCTION mra.validate_market_revision_predecessor();
CREATE TRIGGER corporate_action_session_validate
BEFORE INSERT ON mra.corporate_action_revision
FOR EACH ROW EXECUTE FUNCTION mra.validate_corporate_action_sessions();
CREATE TRIGGER corporate_action_gap_exclusive
BEFORE INSERT ON mra.corporate_action_revision
FOR EACH ROW EXECUTE FUNCTION mra.reject_fact_gap_duality();
CREATE TRIGGER source_gap_append_only
BEFORE UPDATE OR DELETE ON mra.source_gap
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER source_gap_temporal_validate
BEFORE INSERT ON mra.source_gap
FOR EACH ROW EXECUTE FUNCTION mra.validate_market_fact_temporal();
CREATE TRIGGER source_gap_session_validate
BEFORE INSERT ON mra.source_gap
FOR EACH ROW EXECUTE FUNCTION mra.validate_market_bar_session();
CREATE TRIGGER source_gap_bar_exclusive
BEFORE INSERT ON mra.source_gap
FOR EACH ROW EXECUTE FUNCTION mra.reject_fact_gap_duality();
CREATE TRIGGER universe_append_only
BEFORE UPDATE OR DELETE ON mra.universe
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER universe_revision_append_only
BEFORE UPDATE OR DELETE ON mra.universe_revision
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER universe_member_append_only
BEFORE UPDATE OR DELETE ON mra.universe_member
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER eligibility_policy_append_only
BEFORE UPDATE OR DELETE ON mra.eligibility_policy
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER eligibility_rule_append_only
BEFORE UPDATE OR DELETE ON mra.eligibility_rule
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER eligibility_assessment_append_only
BEFORE UPDATE OR DELETE ON mra.eligibility_assessment
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER eligibility_reason_append_only
BEFORE UPDATE OR DELETE ON mra.eligibility_reason
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER feature_definition_append_only
BEFORE UPDATE OR DELETE ON mra.feature_definition
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER dataset_append_only
BEFORE UPDATE OR DELETE ON mra.dataset
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER dataset_source_append_only
BEFORE UPDATE OR DELETE ON mra.dataset_source
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER candidate_policy_append_only
BEFORE UPDATE OR DELETE ON mra.candidate_policy
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER candidate_policy_component_append_only
BEFORE UPDATE OR DELETE ON mra.candidate_policy_component
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER candidate_set_append_only
BEFORE UPDATE OR DELETE ON mra.candidate_set
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER candidate_append_only
BEFORE UPDATE OR DELETE ON mra.candidate
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER candidate_score_component_append_only
BEFORE UPDATE OR DELETE ON mra.candidate_score_component
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER target_definition_append_only
BEFORE UPDATE OR DELETE ON mra.target_definition
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER target_definition_closure_guard
BEFORE INSERT ON mra.target_definition
FOR EACH ROW EXECUTE FUNCTION mra.validate_target_definition_closure();
CREATE TRIGGER target_checkpoint_append_only
BEFORE UPDATE OR DELETE ON mra.target_checkpoint
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER target_checkpoint_open_guard
BEFORE INSERT ON mra.target_checkpoint
FOR EACH ROW EXECUTE FUNCTION mra.guard_open_target_child_insert();
CREATE TRIGGER target_metric_definition_append_only
BEFORE UPDATE OR DELETE ON mra.target_metric_definition
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER target_metric_open_guard
BEFORE INSERT ON mra.target_metric_definition
FOR EACH ROW EXECUTE FUNCTION mra.guard_open_target_child_insert();
CREATE TRIGGER target_metric_dependency_append_only
BEFORE UPDATE OR DELETE ON mra.target_metric_dependency
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER target_metric_dependency_open_guard
BEFORE INSERT ON mra.target_metric_dependency
FOR EACH ROW EXECUTE FUNCTION mra.guard_open_target_child_insert();
CREATE TRIGGER decision_run_append_only
BEFORE UPDATE OR DELETE ON mra.decision_run
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER decision_run_closure_guard
BEFORE INSERT ON mra.decision_run
FOR EACH ROW EXECUTE FUNCTION mra.validate_decision_run_closure();
CREATE TRIGGER decision_run_target_append_only
BEFORE UPDATE OR DELETE ON mra.decision_run_target
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER decision_run_target_open_guard
BEFORE INSERT ON mra.decision_run_target
FOR EACH ROW EXECUTE FUNCTION mra.guard_open_decision_child_insert();
CREATE TRIGGER decision_commitment_append_only
BEFORE UPDATE OR DELETE ON mra.decision_target_commitment
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER decision_commitment_open_guard
BEFORE INSERT ON mra.decision_target_commitment
FOR EACH ROW EXECUTE FUNCTION mra.guard_open_decision_child_insert();
CREATE TRIGGER decision_reference_append_only
BEFORE UPDATE OR DELETE ON mra.decision_reference_observation
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER decision_reference_open_guard
BEFORE INSERT ON mra.decision_reference_observation
FOR EACH ROW EXECUTE FUNCTION mra.guard_open_decision_child_insert();
CREATE TRIGGER market_target_outcome_append_only
BEFORE UPDATE OR DELETE ON mra.market_target_outcome
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER market_target_outcome_revision_append_only
BEFORE UPDATE OR DELETE ON mra.market_target_outcome_revision
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER outcome_revision_predecessor_guard
BEFORE INSERT ON mra.market_target_outcome_revision
FOR EACH ROW EXECUTE FUNCTION mra.validate_outcome_revision_predecessor();
CREATE TRIGGER outcome_revision_closure_guard
BEFORE INSERT ON mra.market_target_outcome_revision
FOR EACH ROW EXECUTE FUNCTION mra.validate_outcome_revision_closure();
CREATE TRIGGER market_target_outcome_source_append_only
BEFORE UPDATE OR DELETE ON mra.market_target_outcome_source
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER outcome_source_open_guard
BEFORE INSERT ON mra.market_target_outcome_source
FOR EACH ROW EXECUTE FUNCTION mra.guard_open_outcome_child_insert();
CREATE TRIGGER market_target_outcome_observation_append_only
BEFORE UPDATE OR DELETE ON mra.market_target_outcome_observation
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER outcome_observation_open_guard
BEFORE INSERT ON mra.market_target_outcome_observation
FOR EACH ROW EXECUTE FUNCTION mra.guard_open_outcome_child_insert();
CREATE TRIGGER market_target_outcome_metric_append_only
BEFORE UPDATE OR DELETE ON mra.market_target_outcome_metric
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER outcome_metric_open_guard
BEFORE INSERT ON mra.market_target_outcome_metric
FOR EACH ROW EXECUTE FUNCTION mra.guard_open_outcome_child_insert();
CREATE TRIGGER market_target_outcome_metric_reference_append_only
BEFORE UPDATE OR DELETE ON mra.market_target_outcome_metric_reference
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER outcome_metric_reference_open_guard
BEFORE INSERT ON mra.market_target_outcome_metric_reference
FOR EACH ROW EXECUTE FUNCTION mra.guard_open_outcome_child_insert();
CREATE TRIGGER market_target_outcome_metric_observation_append_only
BEFORE UPDATE OR DELETE ON mra.market_target_outcome_metric_observation
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER outcome_metric_observation_open_guard
BEFORE INSERT ON mra.market_target_outcome_metric_observation
FOR EACH ROW EXECUTE FUNCTION mra.guard_open_outcome_child_insert();
CREATE TRIGGER market_target_outcome_reason_append_only
BEFORE UPDATE OR DELETE ON mra.market_target_outcome_reason
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER outcome_reason_open_guard
BEFORE INSERT ON mra.market_target_outcome_reason
FOR EACH ROW EXECUTE FUNCTION mra.guard_open_outcome_child_insert();

CREATE VIEW mra.candidate_component_diagnostic AS
SELECT
    candidate_set.candidate_set_id,
    component.candidate_policy_component_id,
    component.feature_definition_id,
    candidate_set.population_count,
    count(score.candidate_score_component_id) FILTER (
        WHERE score.percentile IS NOT NULL
    ) AS observed_count,
    count(DISTINCT ROW(
        score.raw_decimal_value, score.raw_integer_value
    )) FILTER (
        WHERE score.percentile IS NOT NULL
    ) AS distinct_count,
    count(score.candidate_score_component_id) FILTER (
        WHERE score.raw_status = 'AVAILABLE'
    ) AS raw_available_count,
    count(score.candidate_score_component_id) FILTER (
        WHERE score.raw_status = 'MISSING'
    ) AS missing_count,
    count(score.candidate_score_component_id) FILTER (
        WHERE score.raw_status = 'UNKNOWN'
    ) AS unknown_count,
    count(score.candidate_score_component_id) FILTER (
        WHERE score.raw_status = 'STALE'
    ) AS stale_count,
    count(score.candidate_score_component_id) FILTER (
        WHERE score.raw_status = 'CONFLICT'
    ) AS conflict_count,
    count(score.candidate_score_component_id) FILTER (
        WHERE score.raw_status = 'AVAILABLE'
    ) - count(score.candidate_score_component_id) FILTER (
        WHERE score.percentile IS NOT NULL
    ) AS available_but_not_observed_count,
    CASE
        WHEN candidate_set.rankable_count = 0 THEN 'NOT_ESTIMABLE'
        WHEN count(DISTINCT ROW(
            score.raw_decimal_value, score.raw_integer_value
        )) FILTER (WHERE score.percentile IS NOT NULL) = 1 THEN 'CONSTANT'
        ELSE 'AVAILABLE'
    END AS rank_information_status
FROM mra.candidate_set AS candidate_set
JOIN mra.candidate_policy_component AS component
  ON component.candidate_policy_id = candidate_set.candidate_policy_id
LEFT JOIN mra.candidate_score_component AS score
  ON score.candidate_set_id = candidate_set.candidate_set_id
 AND score.candidate_policy_component_id =
     component.candidate_policy_component_id
GROUP BY
    candidate_set.candidate_set_id,
    component.candidate_policy_component_id,
    component.feature_definition_id,
    candidate_set.population_count,
    candidate_set.rankable_count;

CREATE VIEW mra.candidate_funnel AS
SELECT
    candidate_set.candidate_set_id,
    candidate_set.candidate_policy_id,
    candidate_set.dataset_id,
    dataset.row_count AS dataset_population_count,
    candidate_set.population_count,
    candidate_set.rankable_count,
    candidate_set.unrankable_count,
    candidate_set.selected_count,
    candidate_set.ranked_not_selected_count,
    candidate_set.score_component_count,
    candidate_set.ranking_status,
    candidate_set.composite_distinct_count,
    candidate_set.requested_top_k,
    candidate_set.boundary_score,
    candidate_set.boundary_rank,
    candidate_set.strictly_above_boundary_count,
    candidate_set.boundary_group_count,
    candidate_set.selected_overflow_count,
    candidate_set.boundary_has_tie,
    candidate_set.boundary_tie_expanded,
    candidate_counts.actual_population_count,
    candidate_counts.actual_selected_count,
    candidate_counts.actual_ranked_not_selected_count,
    candidate_counts.actual_unrankable_count,
    candidate_counts.strict_complete_case_unrankable_count,
    score_counts.actual_score_component_count,
    candidate_set.population_count =
        candidate_counts.actual_population_count AS population_reconciled,
    candidate_set.rankable_count =
        candidate_counts.actual_selected_count
        + candidate_counts.actual_ranked_not_selected_count
        AS rankable_reconciled,
    candidate_set.score_component_count =
        score_counts.actual_score_component_count
        AND candidate_set.score_component_count =
            candidate_set.population_count::bigint
            * candidate_set.component_count::bigint
        AS score_matrix_reconciled
FROM mra.candidate_set AS candidate_set
JOIN mra.dataset AS dataset
  ON dataset.dataset_id = candidate_set.dataset_id
LEFT JOIN LATERAL (
    SELECT
        count(*) AS actual_population_count,
        count(*) FILTER (
            WHERE candidate.disposition = 'SELECTED'
        ) AS actual_selected_count,
        count(*) FILTER (
            WHERE candidate.disposition = 'RANKED_NOT_SELECTED'
        ) AS actual_ranked_not_selected_count,
        count(*) FILTER (
            WHERE candidate.disposition = 'UNRANKABLE'
        ) AS actual_unrankable_count,
        count(*) FILTER (
            WHERE candidate.reason_code =
                'STRICT_COMPLETE_CASE_REQUIRED_FEATURE_UNAVAILABLE'
        ) AS strict_complete_case_unrankable_count
    FROM mra.candidate AS candidate
    WHERE candidate.candidate_set_id = candidate_set.candidate_set_id
) AS candidate_counts ON true
LEFT JOIN LATERAL (
    SELECT count(*) AS actual_score_component_count
    FROM mra.candidate_score_component AS score
    WHERE score.candidate_set_id = candidate_set.candidate_set_id
) AS score_counts ON true;

CREATE VIEW mra.run_trace AS
SELECT
    run.run_id,
    run.state AS run_state,
    step.step_id,
    step.step_key,
    step.state AS step_state,
    step.current_fence,
    attempt.attempt_id,
    attempt.attempt_no,
    attempt.state AS attempt_state,
    attempt.lease_owner,
    attempt.lease_until
FROM mra.runtime_run AS run
LEFT JOIN mra.runtime_step AS step ON step.run_id = run.run_id
LEFT JOIN mra.runtime_attempt AS attempt ON attempt.step_id = step.step_id;

CREATE VIEW mra.artifact_integrity_status AS
SELECT
    artifact.artifact_id,
    artifact.content_sha256,
    artifact.size_bytes,
    artifact.integrity_state,
    verification.result AS latest_verification_result,
    verification.verified_at AS latest_verified_at
FROM mra.artifact AS artifact
LEFT JOIN LATERAL (
    SELECT item.result, item.verified_at
    FROM mra.artifact_verification AS item
    WHERE item.artifact_id = artifact.artifact_id
    ORDER BY item.verified_at DESC, item.verification_id DESC
    LIMIT 1
) AS verification ON true;

-- WP-11: integrated Research & Qualification validity/evaluation Authority.
-- The schema epoch is still unreleased, so these permanent relations extend
-- this baseline instead of introducing a later migration.

ALTER TABLE mra.decision_target_commitment
    ADD CONSTRAINT decision_commitment_research_authority_uk UNIQUE (
        commitment_id, target_definition_id, decision_time,
        candidate_disposition, commitment_recorded_at, runtime_mode
    );

ALTER TABLE mra.decision_reference_observation
    ADD CONSTRAINT decision_reference_research_session_uk UNIQUE (
        decision_reference_observation_id, commitment_id,
        target_definition_id, session_id, decision_time,
        runtime_mode, commitment_recorded_at
    );

ALTER TABLE mra.market_target_outcome_revision
    ADD CONSTRAINT outcome_revision_research_authority_uk UNIQUE (
        market_target_outcome_revision_id, market_target_outcome_id,
        revision_ordinal, commitment_id, target_definition_id,
        observation_cutoff, knowledge_cutoff, settled_at, outcome_status
    );

ALTER TABLE mra.market_target_outcome_metric
    ADD CONSTRAINT outcome_metric_research_authority_uk UNIQUE (
        market_target_outcome_metric_id, market_target_outcome_revision_id,
        target_metric_definition_id, value_type, value_status
    );

CREATE TABLE mra.research_partition (
    research_partition_id uuid PRIMARY KEY,
    partition_code text NOT NULL UNIQUE,
    status text NOT NULL,
    target_definition_id uuid NOT NULL,
    target_version integer NOT NULL,
    target_definition_sha256 text NOT NULL,
    purpose text NOT NULL,
    population_scope text NOT NULL,
    overlap_policy text NOT NULL,
    exchange_code text NOT NULL,
    timezone_name text NOT NULL,
    calendar_session_count integer NOT NULL,
    calendar_roster_sha256 text NOT NULL,
    decision_start_session_id uuid NOT NULL REFERENCES mra.trading_session(session_id) ON DELETE RESTRICT,
    decision_end_session_id uuid NOT NULL REFERENCES mra.trading_session(session_id) ON DELETE RESTRICT,
    decision_start_date date NOT NULL,
    decision_end_date date NOT NULL,
    outcome_horizon_sessions integer NOT NULL,
    purge_before_sessions integer NOT NULL,
    purge_after_sessions integer NOT NULL,
    embargo_sessions integer NOT NULL,
    protected_start_session_id uuid NOT NULL REFERENCES mra.trading_session(session_id) ON DELETE RESTRICT,
    protected_end_session_id uuid NOT NULL REFERENCES mra.trading_session(session_id) ON DELETE RESTRICT,
    protected_start_date date NOT NULL,
    protected_end_date date NOT NULL,
    series_code text NOT NULL,
    fold_ordinal integer NOT NULL,
    member_count integer NOT NULL,
    member_roster_sha256 text NOT NULL,
    code_artifact_id uuid NOT NULL,
    code_content_sha256 text NOT NULL,
    code_size_bytes bigint NOT NULL,
    config_artifact_id uuid NOT NULL,
    config_content_sha256 text NOT NULL,
    config_size_bytes bigint NOT NULL,
    provenance_sha256 text NOT NULL,
    content_sha256 text NOT NULL,
    request_identity text NOT NULL,
    request_sha256 text NOT NULL,
    frozen_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT research_partition_exact_uk UNIQUE (
        research_partition_id, target_definition_id, target_version,
        target_definition_sha256, purpose, member_count,
        member_roster_sha256, content_sha256, frozen_at
    ),
    CONSTRAINT research_partition_member_authority_uk UNIQUE (
        research_partition_id, target_definition_id
    ),
    CONSTRAINT research_partition_calendar_authority_uk UNIQUE (
        research_partition_id, target_definition_id,
        exchange_code, timezone_name
    ),
    CONSTRAINT research_partition_experiment_authority_uk UNIQUE (
        research_partition_id, target_definition_id, target_version,
        target_definition_sha256, purpose, content_sha256
    ),
    CONSTRAINT research_partition_evaluation_authority_uk UNIQUE (
        research_partition_id, target_definition_id, purpose, member_count
    ),
    CONSTRAINT research_partition_request_uk UNIQUE (partition_code, request_identity),
    CONSTRAINT research_partition_target_fk FOREIGN KEY (
        target_definition_id, target_version, target_definition_sha256
    ) REFERENCES mra.target_definition(
        target_definition_id, version, content_sha256
    ) ON DELETE RESTRICT,
    CONSTRAINT research_partition_decision_start_calendar_fk FOREIGN KEY (
        decision_start_session_id, exchange_code,
        decision_start_date, timezone_name
    ) REFERENCES mra.trading_session(
        session_id, exchange, session_date, timezone_name
    ) ON DELETE RESTRICT,
    CONSTRAINT research_partition_decision_end_calendar_fk FOREIGN KEY (
        decision_end_session_id, exchange_code,
        decision_end_date, timezone_name
    ) REFERENCES mra.trading_session(
        session_id, exchange, session_date, timezone_name
    ) ON DELETE RESTRICT,
    CONSTRAINT research_partition_protected_start_calendar_fk FOREIGN KEY (
        protected_start_session_id, exchange_code,
        protected_start_date, timezone_name
    ) REFERENCES mra.trading_session(
        session_id, exchange, session_date, timezone_name
    ) ON DELETE RESTRICT,
    CONSTRAINT research_partition_protected_end_calendar_fk FOREIGN KEY (
        protected_end_session_id, exchange_code,
        protected_end_date, timezone_name
    ) REFERENCES mra.trading_session(
        session_id, exchange, session_date, timezone_name
    ) ON DELETE RESTRICT,
    CONSTRAINT research_partition_code_artifact_fk FOREIGN KEY (
        code_artifact_id, code_content_sha256, code_size_bytes
    ) REFERENCES mra.artifact(artifact_id, content_sha256, size_bytes) ON DELETE RESTRICT,
    CONSTRAINT research_partition_config_artifact_fk FOREIGN KEY (
        config_artifact_id, config_content_sha256, config_size_bytes
    ) REFERENCES mra.artifact(artifact_id, content_sha256, size_bytes) ON DELETE RESTRICT,
    CONSTRAINT research_partition_shape_ck CHECK (
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
        AND embargo_sessions >= 0 AND fold_ordinal > 0 AND member_count > 0
        AND decision_start_date <= decision_end_date
        AND protected_start_date <= decision_start_date
        AND protected_end_date >= decision_end_date
        AND member_roster_sha256 ~ '^[0-9a-f]{64}$'
        AND provenance_sha256 ~ '^[0-9a-f]{64}$'
        AND content_sha256 ~ '^[0-9a-f]{64}$'
        AND request_sha256 ~ '^[0-9a-f]{64}$'
    )
);
CREATE INDEX research_partition_target_window_idx ON mra.research_partition (
    target_definition_id, exchange_code, purpose,
    protected_start_date, protected_end_date
);
CREATE INDEX research_partition_series_fold_idx ON mra.research_partition (
    series_code, fold_ordinal, purpose
);
CREATE INDEX research_partition_target_fk_idx ON mra.research_partition (
    target_definition_id, target_version, target_definition_sha256
);
CREATE INDEX research_partition_decision_start_fk_idx ON mra.research_partition (decision_start_session_id);
CREATE INDEX research_partition_decision_end_fk_idx ON mra.research_partition (decision_end_session_id);
CREATE INDEX research_partition_protected_start_fk_idx ON mra.research_partition (protected_start_session_id);
CREATE INDEX research_partition_protected_end_fk_idx ON mra.research_partition (protected_end_session_id);
CREATE INDEX research_partition_decision_start_calendar_fk_idx
    ON mra.research_partition (
        decision_start_session_id, exchange_code,
        decision_start_date, timezone_name
    );
CREATE INDEX research_partition_decision_end_calendar_fk_idx
    ON mra.research_partition (
        decision_end_session_id, exchange_code,
        decision_end_date, timezone_name
    );
CREATE INDEX research_partition_protected_start_calendar_fk_idx
    ON mra.research_partition (
        protected_start_session_id, exchange_code,
        protected_start_date, timezone_name
    );
CREATE INDEX research_partition_protected_end_calendar_fk_idx
    ON mra.research_partition (
        protected_end_session_id, exchange_code,
        protected_end_date, timezone_name
    );
CREATE INDEX research_partition_code_artifact_fk_idx ON mra.research_partition (
    code_artifact_id, code_content_sha256, code_size_bytes
);
CREATE INDEX research_partition_config_artifact_fk_idx ON mra.research_partition (
    config_artifact_id, config_content_sha256, config_size_bytes
);

CREATE TABLE mra.research_partition_member (
    research_partition_member_id uuid PRIMARY KEY,
    research_partition_id uuid NOT NULL,
    member_ordinal integer NOT NULL,
    commitment_id uuid NOT NULL,
    decision_reference_observation_id uuid NOT NULL,
    target_definition_id uuid NOT NULL,
    decision_time timestamptz NOT NULL,
    candidate_disposition text NOT NULL,
    commitment_recorded_at timestamptz NOT NULL,
    runtime_mode text NOT NULL,
    decision_session_id uuid NOT NULL REFERENCES mra.trading_session(session_id) ON DELETE RESTRICT,
    decision_session_date date NOT NULL,
    exchange_code text NOT NULL,
    timezone_name text NOT NULL,
    earliest_outcome_event_at timestamptz NOT NULL,
    outcome_due_at timestamptz NOT NULL,
    content_sha256 text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT research_partition_member_ordinal_uk UNIQUE (research_partition_id, member_ordinal),
    CONSTRAINT research_partition_member_commitment_uk UNIQUE (research_partition_id, commitment_id),
    CONSTRAINT research_partition_member_exact_uk UNIQUE (
        research_partition_member_id, research_partition_id, commitment_id,
        target_definition_id, candidate_disposition, outcome_due_at
    ),
    CONSTRAINT research_partition_member_access_authority_uk UNIQUE (
        research_partition_member_id, research_partition_id, commitment_id,
        target_definition_id
    ),
    CONSTRAINT research_partition_member_observation_authority_uk UNIQUE (
        research_partition_member_id, research_partition_id
    ),
    CONSTRAINT research_partition_member_partition_fk FOREIGN KEY (
        research_partition_id, target_definition_id
    ) REFERENCES mra.research_partition(
        research_partition_id, target_definition_id
    ) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT research_partition_member_calendar_fk FOREIGN KEY (
        research_partition_id, target_definition_id,
        exchange_code, timezone_name
    ) REFERENCES mra.research_partition(
        research_partition_id, target_definition_id,
        exchange_code, timezone_name
    ) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT research_partition_member_session_calendar_fk FOREIGN KEY (
        decision_session_id, exchange_code,
        decision_session_date, timezone_name
    ) REFERENCES mra.trading_session(
        session_id, exchange, session_date, timezone_name
    ) ON DELETE RESTRICT,
    CONSTRAINT research_partition_member_commitment_fk FOREIGN KEY (
        commitment_id, target_definition_id, decision_time,
        candidate_disposition, commitment_recorded_at, runtime_mode
    ) REFERENCES mra.decision_target_commitment(
        commitment_id, target_definition_id, decision_time,
        candidate_disposition, commitment_recorded_at, runtime_mode
    ) ON DELETE RESTRICT,
    CONSTRAINT research_partition_member_reference_session_fk FOREIGN KEY (
        decision_reference_observation_id, commitment_id,
        target_definition_id, decision_session_id, decision_time,
        runtime_mode, commitment_recorded_at
    ) REFERENCES mra.decision_reference_observation(
        decision_reference_observation_id, commitment_id,
        target_definition_id, session_id, decision_time,
        runtime_mode, commitment_recorded_at
    ) ON DELETE RESTRICT,
    CONSTRAINT research_partition_member_shape_ck CHECK (
        member_ordinal > 0
        AND candidate_disposition IN ('SELECTED', 'RANKED_NOT_SELECTED', 'UNRANKABLE')
        AND runtime_mode IN ('OPERATIONAL', 'HISTORICAL', 'REPLAY', 'SHADOW', 'PROSPECTIVE')
        AND exchange_code ~ '^[A-Z][A-Z0-9]{1,15}$'
        AND timezone_name = 'Asia/Shanghai'
        AND earliest_outcome_event_at <= outcome_due_at
        AND content_sha256 ~ '^[0-9a-f]{64}$'
    )
);
CREATE INDEX research_partition_member_commitment_idx ON mra.research_partition_member (
    commitment_id, research_partition_id
);
CREATE INDEX research_partition_member_partition_fk_idx ON mra.research_partition_member (
    research_partition_id, target_definition_id
);
CREATE INDEX research_partition_member_calendar_fk_idx
    ON mra.research_partition_member (
        research_partition_id, target_definition_id,
        exchange_code, timezone_name
    );
CREATE INDEX research_partition_member_commitment_fk_idx ON mra.research_partition_member (
    commitment_id, target_definition_id, decision_time,
    candidate_disposition, commitment_recorded_at, runtime_mode
);
CREATE INDEX research_partition_member_session_fk_idx ON mra.research_partition_member (decision_session_id);
CREATE INDEX research_partition_member_session_calendar_fk_idx
    ON mra.research_partition_member (
        decision_session_id, exchange_code,
        decision_session_date, timezone_name
    );
CREATE INDEX research_partition_member_reference_session_fk_idx
    ON mra.research_partition_member (
        decision_reference_observation_id, commitment_id,
        target_definition_id, decision_session_id, decision_time,
        runtime_mode, commitment_recorded_at
    );

CREATE TABLE mra.experiment (
    experiment_id uuid PRIMARY KEY,
    experiment_code text NOT NULL UNIQUE,
    status text NOT NULL,
    research_question text NOT NULL,
    primary_change text NOT NULL,
    hypothesis text NOT NULL,
    target_definition_id uuid NOT NULL,
    target_version integer NOT NULL,
    target_definition_sha256 text NOT NULL,
    protocol_identity text NOT NULL,
    acceptance_semantics text NOT NULL,
    code_artifact_id uuid NOT NULL,
    code_content_sha256 text NOT NULL,
    code_size_bytes bigint NOT NULL,
    config_artifact_id uuid NOT NULL,
    config_content_sha256 text NOT NULL,
    config_size_bytes bigint NOT NULL,
    provenance_sha256 text NOT NULL,
    definition_sha256 text NOT NULL,
    partition_count integer NOT NULL,
    partition_roster_sha256 text NOT NULL,
    content_sha256 text NOT NULL,
    request_identity text NOT NULL,
    request_sha256 text NOT NULL,
    registered_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT experiment_exact_uk UNIQUE (
        experiment_id, target_definition_id, target_version,
        target_definition_sha256, definition_sha256,
        partition_count, partition_roster_sha256,
        content_sha256, registered_at
    ),
    CONSTRAINT experiment_partition_authority_uk UNIQUE (
        experiment_id, target_definition_id, target_version,
        target_definition_sha256
    ),
    CONSTRAINT experiment_request_uk UNIQUE (experiment_code, request_identity),
    CONSTRAINT experiment_target_fk FOREIGN KEY (
        target_definition_id, target_version, target_definition_sha256
    ) REFERENCES mra.target_definition(target_definition_id, version, content_sha256) ON DELETE RESTRICT,
    CONSTRAINT experiment_code_artifact_fk FOREIGN KEY (
        code_artifact_id, code_content_sha256, code_size_bytes
    ) REFERENCES mra.artifact(artifact_id, content_sha256, size_bytes) ON DELETE RESTRICT,
    CONSTRAINT experiment_config_artifact_fk FOREIGN KEY (
        config_artifact_id, config_content_sha256, config_size_bytes
    ) REFERENCES mra.artifact(artifact_id, content_sha256, size_bytes) ON DELETE RESTRICT,
    CONSTRAINT experiment_shape_ck CHECK (
        status = 'REGISTERED' AND experiment_code ~ '^[a-z][a-z0-9_-]{0,99}$'
        AND research_question <> '' AND primary_change <> '' AND hypothesis <> ''
        AND protocol_identity <> '' AND acceptance_semantics <> ''
        AND provenance_sha256 ~ '^[0-9a-f]{64}$'
        AND definition_sha256 ~ '^[0-9a-f]{64}$'
        AND partition_count > 0
        AND partition_roster_sha256 ~ '^[0-9a-f]{64}$'
        AND content_sha256 ~ '^[0-9a-f]{64}$'
        AND request_sha256 ~ '^[0-9a-f]{64}$'
    )
);

CREATE TABLE mra.experiment_partition (
    experiment_partition_id uuid PRIMARY KEY,
    experiment_id uuid NOT NULL,
    binding_ordinal integer NOT NULL,
    research_partition_id uuid NOT NULL,
    target_definition_id uuid NOT NULL,
    target_version integer NOT NULL,
    target_definition_sha256 text NOT NULL,
    partition_purpose text NOT NULL,
    partition_content_sha256 text NOT NULL,
    content_sha256 text NOT NULL,
    bound_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT experiment_partition_ordinal_uk UNIQUE (
        experiment_id, binding_ordinal
    ),
    CONSTRAINT experiment_partition_pair_uk UNIQUE (experiment_id, research_partition_id),
    CONSTRAINT experiment_partition_exact_uk UNIQUE (
        experiment_partition_id, experiment_id, research_partition_id,
        target_definition_id, partition_purpose, bound_at
    ),
    CONSTRAINT experiment_partition_run_authority_uk UNIQUE (
        experiment_partition_id, experiment_id, research_partition_id
    ),
    CONSTRAINT experiment_partition_evaluation_authority_uk UNIQUE (
        experiment_partition_id, experiment_id, research_partition_id,
        target_definition_id, partition_purpose
    ),
    CONSTRAINT experiment_partition_experiment_fk FOREIGN KEY (
        experiment_id, target_definition_id, target_version, target_definition_sha256
    ) REFERENCES mra.experiment(
        experiment_id, target_definition_id, target_version, target_definition_sha256
    ) ON DELETE RESTRICT,
    CONSTRAINT experiment_partition_partition_fk FOREIGN KEY (
        research_partition_id, target_definition_id, target_version,
        target_definition_sha256, partition_purpose,
        partition_content_sha256
    ) REFERENCES mra.research_partition(
        research_partition_id, target_definition_id, target_version,
        target_definition_sha256, purpose, content_sha256
    ) ON DELETE RESTRICT,
    CONSTRAINT experiment_partition_shape_ck CHECK (
        binding_ordinal > 0
        AND partition_purpose IN ('DISCOVERY', 'FIT', 'VALIDATION', 'LOCKED_OOS', 'PROSPECTIVE')
        AND partition_content_sha256 ~ '^[0-9a-f]{64}$'
        AND content_sha256 ~ '^[0-9a-f]{64}$'
    )
);
CREATE INDEX experiment_target_fk_idx ON mra.experiment (
    target_definition_id, target_version, target_definition_sha256
);
CREATE INDEX experiment_code_artifact_fk_idx ON mra.experiment (
    code_artifact_id, code_content_sha256, code_size_bytes
);
CREATE INDEX experiment_config_artifact_fk_idx ON mra.experiment (
    config_artifact_id, config_content_sha256, config_size_bytes
);
CREATE INDEX experiment_partition_experiment_fk_idx ON mra.experiment_partition (
    experiment_id, target_definition_id, target_version, target_definition_sha256
);
CREATE INDEX experiment_partition_partition_fk_idx ON mra.experiment_partition (
    research_partition_id, target_definition_id, target_version,
    target_definition_sha256, partition_purpose, partition_content_sha256
);

CREATE TABLE mra.experiment_run (
    experiment_run_id uuid PRIMARY KEY,
    experiment_id uuid NOT NULL,
    experiment_partition_id uuid NOT NULL,
    research_partition_id uuid NOT NULL,
    status text NOT NULL,
    run_identity text NOT NULL,
    content_sha256 text NOT NULL,
    opened_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT experiment_run_identity_uk UNIQUE (experiment_id, run_identity),
    CONSTRAINT experiment_run_exact_uk UNIQUE (
        experiment_run_id, experiment_id, experiment_partition_id,
        research_partition_id, opened_at
    ),
    CONSTRAINT experiment_run_evaluation_authority_uk UNIQUE (
        experiment_run_id, experiment_id, experiment_partition_id,
        research_partition_id
    ),
    CONSTRAINT experiment_run_partition_fk FOREIGN KEY (
        experiment_partition_id, experiment_id, research_partition_id
    ) REFERENCES mra.experiment_partition(
        experiment_partition_id, experiment_id, research_partition_id
    ) ON DELETE RESTRICT,
    CONSTRAINT experiment_run_shape_ck CHECK (
        status = 'OPENED' AND run_identity <> ''
        AND content_sha256 ~ '^[0-9a-f]{64}$'
    )
);
CREATE INDEX experiment_run_partition_fk_idx ON mra.experiment_run (
    experiment_partition_id, experiment_id, research_partition_id
);

CREATE TABLE mra.evaluation_protocol (
    evaluation_protocol_id uuid PRIMARY KEY,
    protocol_code text NOT NULL,
    protocol_version integer NOT NULL,
    status text NOT NULL,
    target_definition_id uuid NOT NULL,
    target_version integer NOT NULL,
    target_definition_sha256 text NOT NULL,
    applicable_purpose text NOT NULL,
    decision_rule text NOT NULL,
    metric_count integer NOT NULL,
    metric_roster_sha256 text NOT NULL,
    code_artifact_id uuid NOT NULL,
    code_content_sha256 text NOT NULL,
    code_size_bytes bigint NOT NULL,
    config_artifact_id uuid NOT NULL,
    config_content_sha256 text NOT NULL,
    config_size_bytes bigint NOT NULL,
    provenance_sha256 text NOT NULL,
    content_sha256 text NOT NULL,
    request_identity text NOT NULL,
    request_sha256 text NOT NULL,
    frozen_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT evaluation_protocol_exact_uk UNIQUE (
        evaluation_protocol_id, target_definition_id, target_version,
        target_definition_sha256, applicable_purpose, metric_count,
        metric_roster_sha256, content_sha256, frozen_at
    ),
    CONSTRAINT evaluation_protocol_identity_uk UNIQUE (
        protocol_code, protocol_version
    ),
    CONSTRAINT evaluation_protocol_metric_authority_uk UNIQUE (
        evaluation_protocol_id, target_definition_id
    ),
    CONSTRAINT evaluation_protocol_run_authority_uk UNIQUE (
        evaluation_protocol_id, target_definition_id,
        applicable_purpose, metric_count
    ),
    CONSTRAINT evaluation_protocol_request_uk UNIQUE (protocol_code, request_identity),
    CONSTRAINT evaluation_protocol_target_fk FOREIGN KEY (
        target_definition_id, target_version, target_definition_sha256
    ) REFERENCES mra.target_definition(target_definition_id, version, content_sha256) ON DELETE RESTRICT,
    CONSTRAINT evaluation_protocol_code_artifact_fk FOREIGN KEY (
        code_artifact_id, code_content_sha256, code_size_bytes
    ) REFERENCES mra.artifact(artifact_id, content_sha256, size_bytes) ON DELETE RESTRICT,
    CONSTRAINT evaluation_protocol_config_artifact_fk FOREIGN KEY (
        config_artifact_id, config_content_sha256, config_size_bytes
    ) REFERENCES mra.artifact(artifact_id, content_sha256, size_bytes) ON DELETE RESTRICT,
    CONSTRAINT evaluation_protocol_shape_ck CHECK (
        status = 'FROZEN' AND protocol_code ~ '^[a-z][a-z0-9_-]{0,99}$'
        AND protocol_version > 0
        AND applicable_purpose IN ('DISCOVERY', 'FIT', 'VALIDATION', 'LOCKED_OOS', 'PROSPECTIVE')
        AND decision_rule <> '' AND metric_count > 0
        AND metric_roster_sha256 ~ '^[0-9a-f]{64}$'
        AND provenance_sha256 ~ '^[0-9a-f]{64}$'
        AND content_sha256 ~ '^[0-9a-f]{64}$'
        AND request_sha256 ~ '^[0-9a-f]{64}$'
    )
);

ALTER TABLE mra.target_metric_definition
    ADD CONSTRAINT target_metric_evaluation_authority_uk UNIQUE (
        target_metric_definition_id, target_definition_id, value_type
    ),
    ADD CONSTRAINT target_metric_evaluation_code_authority_uk UNIQUE (
        target_metric_definition_id, target_definition_id,
        value_type, metric_code
    );

CREATE TABLE mra.evaluation_protocol_metric (
    evaluation_protocol_metric_id uuid PRIMARY KEY,
    evaluation_protocol_id uuid NOT NULL,
    target_definition_id uuid NOT NULL,
    ordinal integer NOT NULL,
    metric_code text NOT NULL,
    source_target_metric_definition_id uuid NOT NULL,
    source_metric_code text NOT NULL,
    source_value_type text NOT NULL,
    reducer text NOT NULL,
    slice_kind text NOT NULL,
    candidate_disposition text,
    direction text NOT NULL,
    inclusion_policy text NOT NULL,
    missingness_policy text NOT NULL,
    minimum_estimable_count integer NOT NULL,
    acceptance_operator text NOT NULL,
    acceptance_threshold numeric,
    content_sha256 text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT evaluation_protocol_metric_ordinal_uk UNIQUE (evaluation_protocol_id, ordinal),
    CONSTRAINT evaluation_protocol_metric_code_uk UNIQUE (evaluation_protocol_id, metric_code),
    CONSTRAINT evaluation_protocol_metric_exact_uk UNIQUE (
        evaluation_protocol_metric_id, evaluation_protocol_id,
        source_target_metric_definition_id, source_value_type
    ),
    CONSTRAINT evaluation_protocol_metric_metric_authority_uk UNIQUE (
        evaluation_protocol_metric_id, evaluation_protocol_id
    ),
    CONSTRAINT evaluation_protocol_metric_protocol_fk FOREIGN KEY (
        evaluation_protocol_id, target_definition_id
    ) REFERENCES mra.evaluation_protocol(
        evaluation_protocol_id, target_definition_id
    ) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT evaluation_protocol_metric_source_fk FOREIGN KEY (
        source_target_metric_definition_id, target_definition_id,
        source_value_type, source_metric_code
    ) REFERENCES mra.target_metric_definition(
        target_metric_definition_id, target_definition_id,
        value_type, metric_code
    ) ON DELETE RESTRICT,
    CONSTRAINT evaluation_protocol_metric_shape_ck CHECK (
        ordinal > 0 AND metric_code ~ '^[a-z][a-z0-9_-]{0,99}$'
        AND source_metric_code ~ '^[a-z][a-z0-9_-]{0,99}$'
        AND source_value_type IN ('DECIMAL', 'BOOLEAN')
        AND reducer IN ('MEAN_DECIMAL', 'MEDIAN_DECIMAL', 'TRUE_RATE', 'ESTIMABLE_RATE')
        AND ((reducer IN ('MEAN_DECIMAL', 'MEDIAN_DECIMAL') AND source_value_type = 'DECIMAL')
          OR (reducer = 'TRUE_RATE' AND source_value_type = 'BOOLEAN')
          OR reducer = 'ESTIMABLE_RATE')
        AND slice_kind IN ('ALL_MEMBERS', 'CANDIDATE_DISPOSITION')
        AND ((slice_kind = 'ALL_MEMBERS' AND candidate_disposition IS NULL)
          OR (slice_kind = 'CANDIDATE_DISPOSITION' AND candidate_disposition IN ('SELECTED', 'RANKED_NOT_SELECTED', 'UNRANKABLE')))
        AND direction IN ('HIGHER', 'LOWER', 'DESCRIPTIVE')
        AND inclusion_policy IN ('COMPLETE_ONLY', 'AVAILABLE_VALUE')
        AND missingness_policy IN ('RETAIN_AND_ESTIMATE', 'REQUIRE_COMPLETE_ROSTER')
        AND minimum_estimable_count > 0
        AND acceptance_operator IN ('NONE', 'AT_LEAST', 'AT_MOST')
        AND ((acceptance_operator = 'NONE' AND acceptance_threshold IS NULL AND direction = 'DESCRIPTIVE')
          OR (acceptance_operator <> 'NONE' AND acceptance_threshold IS NOT NULL AND direction <> 'DESCRIPTIVE'))
        AND content_sha256 ~ '^[0-9a-f]{64}$'
    )
);
CREATE INDEX evaluation_protocol_target_fk_idx ON mra.evaluation_protocol (
    target_definition_id, target_version, target_definition_sha256
);
CREATE INDEX evaluation_protocol_code_artifact_fk_idx ON mra.evaluation_protocol (
    code_artifact_id, code_content_sha256, code_size_bytes
);
CREATE INDEX evaluation_protocol_config_artifact_fk_idx ON mra.evaluation_protocol (
    config_artifact_id, config_content_sha256, config_size_bytes
);
CREATE INDEX evaluation_protocol_metric_protocol_fk_idx ON mra.evaluation_protocol_metric (
    evaluation_protocol_id, target_definition_id
);
CREATE INDEX evaluation_protocol_metric_source_fk_idx ON mra.evaluation_protocol_metric (
    source_target_metric_definition_id, target_definition_id,
    source_value_type, source_metric_code
);

CREATE TABLE mra.evaluation_run (
    evaluation_run_id uuid PRIMARY KEY,
    experiment_run_id uuid NOT NULL,
    experiment_id uuid NOT NULL,
    experiment_partition_id uuid NOT NULL,
    research_partition_id uuid NOT NULL,
    evaluation_protocol_id uuid NOT NULL,
    target_definition_id uuid NOT NULL,
    partition_purpose text NOT NULL,
    requested_knowledge_cutoff timestamptz NOT NULL,
    expected_member_count integer NOT NULL,
    expected_protocol_metric_count integer NOT NULL,
    code_artifact_id uuid NOT NULL,
    code_content_sha256 text NOT NULL,
    code_size_bytes bigint NOT NULL,
    config_artifact_id uuid NOT NULL,
    config_content_sha256 text NOT NULL,
    config_size_bytes bigint NOT NULL,
    provenance_sha256 text NOT NULL,
    content_sha256 text NOT NULL,
    status text NOT NULL,
    request_identity text NOT NULL,
    request_sha256 text NOT NULL,
    opened_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    inputs_acquired_at timestamptz,
    completed_at timestamptz,
    failed_at timestamptz,
    failure_reason_code text,
    access_count integer NOT NULL DEFAULT 0,
    observation_count integer NOT NULL DEFAULT 0,
    metric_count integer NOT NULL DEFAULT 0,
    metric_observation_count bigint NOT NULL DEFAULT 0,
    input_roster_sha256 text,
    metric_roster_sha256 text,
    version bigint NOT NULL DEFAULT 1,
    CONSTRAINT evaluation_run_identity_uk UNIQUE (experiment_run_id, request_identity),
    CONSTRAINT evaluation_run_exact_uk UNIQUE (
        evaluation_run_id, experiment_run_id, research_partition_id,
        evaluation_protocol_id, target_definition_id, content_sha256
    ),
    CONSTRAINT evaluation_run_access_authority_uk UNIQUE (
        evaluation_run_id, research_partition_id, target_definition_id
    ),
    CONSTRAINT evaluation_run_metric_authority_uk UNIQUE (
        evaluation_run_id, evaluation_protocol_id
    ),
    CONSTRAINT evaluation_run_experiment_fk FOREIGN KEY (
        experiment_run_id, experiment_id, experiment_partition_id,
        research_partition_id
    ) REFERENCES mra.experiment_run(
        experiment_run_id, experiment_id, experiment_partition_id,
        research_partition_id
    ) ON DELETE RESTRICT,
    CONSTRAINT evaluation_run_experiment_partition_fk FOREIGN KEY (
        experiment_partition_id, experiment_id, research_partition_id,
        target_definition_id, partition_purpose
    ) REFERENCES mra.experiment_partition(
        experiment_partition_id, experiment_id, research_partition_id,
        target_definition_id, partition_purpose
    ) ON DELETE RESTRICT,
    CONSTRAINT evaluation_run_partition_fk FOREIGN KEY (
        research_partition_id, target_definition_id, partition_purpose,
        expected_member_count
    ) REFERENCES mra.research_partition(
        research_partition_id, target_definition_id, purpose, member_count
    ) ON DELETE RESTRICT,
    CONSTRAINT evaluation_run_protocol_fk FOREIGN KEY (
        evaluation_protocol_id, target_definition_id, partition_purpose,
        expected_protocol_metric_count
    ) REFERENCES mra.evaluation_protocol(
        evaluation_protocol_id, target_definition_id, applicable_purpose, metric_count
    ) ON DELETE RESTRICT,
    CONSTRAINT evaluation_run_code_artifact_fk FOREIGN KEY (
        code_artifact_id, code_content_sha256, code_size_bytes
    ) REFERENCES mra.artifact(artifact_id, content_sha256, size_bytes) ON DELETE RESTRICT,
    CONSTRAINT evaluation_run_config_artifact_fk FOREIGN KEY (
        config_artifact_id, config_content_sha256, config_size_bytes
    ) REFERENCES mra.artifact(artifact_id, content_sha256, size_bytes) ON DELETE RESTRICT,
    CONSTRAINT evaluation_run_shape_ck CHECK (
        partition_purpose IN ('DISCOVERY', 'FIT', 'VALIDATION', 'LOCKED_OOS', 'PROSPECTIVE')
        AND expected_member_count > 0 AND expected_protocol_metric_count > 0
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
    )
);
CREATE INDEX evaluation_run_state_idx ON mra.evaluation_run(status, opened_at);
CREATE INDEX evaluation_run_experiment_fk_idx ON mra.evaluation_run (
    experiment_run_id, experiment_id, experiment_partition_id, research_partition_id
);
CREATE INDEX evaluation_run_experiment_partition_fk_idx ON mra.evaluation_run (
    experiment_partition_id, experiment_id, research_partition_id,
    target_definition_id, partition_purpose
);
CREATE INDEX evaluation_run_partition_fk_idx ON mra.evaluation_run (
    research_partition_id, target_definition_id, partition_purpose, expected_member_count
);
CREATE INDEX evaluation_run_protocol_fk_idx ON mra.evaluation_run (
    evaluation_protocol_id, target_definition_id, partition_purpose,
    expected_protocol_metric_count
);
CREATE INDEX evaluation_run_code_artifact_fk_idx ON mra.evaluation_run (
    code_artifact_id, code_content_sha256, code_size_bytes
);
CREATE INDEX evaluation_run_config_artifact_fk_idx ON mra.evaluation_run (
    config_artifact_id, config_content_sha256, config_size_bytes
);

CREATE TABLE mra.research_partition_outcome_access (
    research_partition_outcome_access_id uuid PRIMARY KEY,
    evaluation_run_id uuid NOT NULL,
    research_partition_member_id uuid NOT NULL,
    research_partition_id uuid NOT NULL,
    commitment_id uuid NOT NULL,
    target_definition_id uuid NOT NULL,
    market_target_outcome_revision_id uuid NOT NULL,
    market_target_outcome_id uuid NOT NULL,
    revision_ordinal integer NOT NULL,
    observation_cutoff timestamptz NOT NULL,
    knowledge_cutoff timestamptz NOT NULL,
    settled_at timestamptz NOT NULL,
    outcome_status text NOT NULL,
    access_ordinal integer NOT NULL,
    accessed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    content_sha256 text NOT NULL,
    CONSTRAINT research_outcome_access_run_member_uk UNIQUE (evaluation_run_id, research_partition_member_id),
    CONSTRAINT research_outcome_access_member_ordinal_uk UNIQUE (research_partition_member_id, access_ordinal),
    CONSTRAINT research_outcome_access_exact_uk UNIQUE (
        research_partition_outcome_access_id, evaluation_run_id,
        research_partition_member_id, research_partition_id,
        market_target_outcome_revision_id
    ),
    CONSTRAINT research_outcome_access_run_fk FOREIGN KEY (
        evaluation_run_id, research_partition_id, target_definition_id
    ) REFERENCES mra.evaluation_run(
        evaluation_run_id, research_partition_id, target_definition_id
    ) ON DELETE RESTRICT,
    CONSTRAINT research_outcome_access_member_fk FOREIGN KEY (
        research_partition_member_id, research_partition_id, commitment_id,
        target_definition_id
    ) REFERENCES mra.research_partition_member(
        research_partition_member_id, research_partition_id, commitment_id,
        target_definition_id
    ) ON DELETE RESTRICT,
    CONSTRAINT research_outcome_access_revision_fk FOREIGN KEY (
        market_target_outcome_revision_id, market_target_outcome_id,
        revision_ordinal, commitment_id, target_definition_id,
        observation_cutoff, knowledge_cutoff, settled_at, outcome_status
    ) REFERENCES mra.market_target_outcome_revision(
        market_target_outcome_revision_id, market_target_outcome_id,
        revision_ordinal, commitment_id, target_definition_id,
        observation_cutoff, knowledge_cutoff, settled_at, outcome_status
    ) ON DELETE RESTRICT,
    CONSTRAINT research_outcome_access_shape_ck CHECK (
        access_ordinal > 0
        AND outcome_status IN ('PARTIAL', 'COMPLETE', 'UNAVAILABLE', 'FAILED')
        AND observation_cutoff <= knowledge_cutoff
        AND settled_at <= accessed_at
        AND content_sha256 ~ '^[0-9a-f]{64}$'
    )
);

CREATE TABLE mra.evaluation_observation (
    evaluation_observation_id uuid PRIMARY KEY,
    evaluation_run_id uuid NOT NULL,
    research_partition_member_id uuid NOT NULL,
    research_partition_id uuid NOT NULL,
    outcome_access_id uuid NOT NULL,
    market_target_outcome_revision_id uuid NOT NULL,
    candidate_disposition text NOT NULL,
    outcome_status text NOT NULL,
    content_sha256 text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT evaluation_observation_run_member_uk UNIQUE (evaluation_run_id, research_partition_member_id),
    CONSTRAINT evaluation_observation_exact_uk UNIQUE (
        evaluation_observation_id, evaluation_run_id,
        research_partition_member_id, market_target_outcome_revision_id
    ),
    CONSTRAINT evaluation_observation_access_fk FOREIGN KEY (
        outcome_access_id, evaluation_run_id, research_partition_member_id,
        research_partition_id, market_target_outcome_revision_id
    ) REFERENCES mra.research_partition_outcome_access(
        research_partition_outcome_access_id, evaluation_run_id,
        research_partition_member_id, research_partition_id,
        market_target_outcome_revision_id
    ) ON DELETE RESTRICT,
    CONSTRAINT evaluation_observation_member_fk FOREIGN KEY (
        research_partition_member_id, research_partition_id
    ) REFERENCES mra.research_partition_member(
        research_partition_member_id, research_partition_id
    ) ON DELETE RESTRICT,
    CONSTRAINT evaluation_observation_shape_ck CHECK (
        candidate_disposition IN ('SELECTED', 'RANKED_NOT_SELECTED', 'UNRANKABLE')
        AND outcome_status IN ('PARTIAL', 'COMPLETE', 'UNAVAILABLE', 'FAILED')
        AND content_sha256 ~ '^[0-9a-f]{64}$'
    )
);
CREATE INDEX research_outcome_access_run_fk_idx ON mra.research_partition_outcome_access (
    evaluation_run_id, research_partition_id, target_definition_id
);
CREATE INDEX research_outcome_access_member_fk_idx ON mra.research_partition_outcome_access (
    research_partition_member_id, research_partition_id, commitment_id,
    target_definition_id
);
CREATE INDEX research_outcome_access_revision_fk_idx ON mra.research_partition_outcome_access (
    market_target_outcome_revision_id, market_target_outcome_id,
    revision_ordinal, commitment_id, target_definition_id,
    observation_cutoff, knowledge_cutoff, settled_at, outcome_status
);
CREATE INDEX evaluation_observation_access_fk_idx ON mra.evaluation_observation (
    outcome_access_id, evaluation_run_id, research_partition_member_id,
    research_partition_id, market_target_outcome_revision_id
);
CREATE INDEX evaluation_observation_member_fk_idx ON mra.evaluation_observation (
    research_partition_member_id, research_partition_id
);

CREATE TABLE mra.evaluation_metric (
    evaluation_metric_id uuid PRIMARY KEY,
    evaluation_run_id uuid NOT NULL,
    evaluation_protocol_metric_id uuid NOT NULL,
    evaluation_protocol_id uuid NOT NULL,
    metric_state text NOT NULL,
    decimal_value numeric,
    boolean_value boolean,
    estimable_count integer NOT NULL,
    acceptance_state text NOT NULL,
    content_sha256 text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT evaluation_metric_run_protocol_metric_uk UNIQUE (evaluation_run_id, evaluation_protocol_metric_id),
    CONSTRAINT evaluation_metric_exact_uk UNIQUE (
        evaluation_metric_id, evaluation_run_id,
        evaluation_protocol_metric_id
    ),
    CONSTRAINT evaluation_metric_run_fk FOREIGN KEY (
        evaluation_run_id, evaluation_protocol_id
    ) REFERENCES mra.evaluation_run(
        evaluation_run_id, evaluation_protocol_id
    ) ON DELETE RESTRICT,
    CONSTRAINT evaluation_metric_protocol_fk FOREIGN KEY (
        evaluation_protocol_metric_id, evaluation_protocol_id
    ) REFERENCES mra.evaluation_protocol_metric(
        evaluation_protocol_metric_id, evaluation_protocol_id
    ) ON DELETE RESTRICT,
    CONSTRAINT evaluation_metric_shape_ck CHECK (
        metric_state IN ('ESTIMATED', 'NOT_ESTIMABLE')
        AND estimable_count >= 0
        AND acceptance_state IN ('ACCEPTED', 'REJECTED', 'NOT_APPLICABLE', 'NOT_ESTIMABLE')
        AND ((metric_state = 'NOT_ESTIMABLE' AND decimal_value IS NULL AND boolean_value IS NULL AND acceptance_state = 'NOT_ESTIMABLE')
          OR (metric_state = 'ESTIMATED' AND (decimal_value IS NOT NULL OR boolean_value IS NOT NULL)))
        AND content_sha256 ~ '^[0-9a-f]{64}$'
    )
);

CREATE TABLE mra.evaluation_metric_observation (
    evaluation_metric_observation_id uuid PRIMARY KEY,
    evaluation_metric_id uuid NOT NULL,
    evaluation_run_id uuid NOT NULL,
    evaluation_protocol_metric_id uuid NOT NULL,
    evaluation_observation_id uuid NOT NULL,
    research_partition_member_id uuid NOT NULL,
    market_target_outcome_revision_id uuid NOT NULL,
    source_outcome_metric_id uuid NOT NULL,
    source_target_metric_definition_id uuid NOT NULL,
    source_value_type text NOT NULL,
    source_value_status text NOT NULL,
    input_state text NOT NULL,
    reason_code text NOT NULL,
    content_sha256 text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT evaluation_metric_observation_matrix_uk UNIQUE (evaluation_metric_id, evaluation_observation_id),
    CONSTRAINT evaluation_metric_observation_run_matrix_uk UNIQUE (
        evaluation_run_id, evaluation_protocol_metric_id,
        research_partition_member_id
    ),
    CONSTRAINT evaluation_metric_observation_metric_fk FOREIGN KEY (
        evaluation_metric_id, evaluation_run_id,
        evaluation_protocol_metric_id
    ) REFERENCES mra.evaluation_metric(
        evaluation_metric_id, evaluation_run_id,
        evaluation_protocol_metric_id
    ) ON DELETE RESTRICT,
    CONSTRAINT evaluation_metric_observation_observation_fk FOREIGN KEY (
        evaluation_observation_id, evaluation_run_id,
        research_partition_member_id, market_target_outcome_revision_id
    ) REFERENCES mra.evaluation_observation(
        evaluation_observation_id, evaluation_run_id,
        research_partition_member_id, market_target_outcome_revision_id
    ) ON DELETE RESTRICT,
    CONSTRAINT evaluation_metric_observation_source_fk FOREIGN KEY (
        source_outcome_metric_id, market_target_outcome_revision_id,
        source_target_metric_definition_id, source_value_type,
        source_value_status
    ) REFERENCES mra.market_target_outcome_metric(
        market_target_outcome_metric_id, market_target_outcome_revision_id,
        target_metric_definition_id, value_type, value_status
    ) ON DELETE RESTRICT,
    CONSTRAINT evaluation_metric_observation_shape_ck CHECK (
        source_value_type IN ('DECIMAL', 'BOOLEAN')
        AND source_value_status IN ('PARTIAL', 'COMPLETE', 'UNAVAILABLE', 'FAILED')
        AND input_state IN ('INCLUDED', 'EXCLUDED', 'NOT_ESTIMABLE')
        AND reason_code ~ '^[A-Z][A-Z0-9_]{0,99}$'
        AND content_sha256 ~ '^[0-9a-f]{64}$'
    )
);
CREATE INDEX evaluation_metric_run_fk_idx ON mra.evaluation_metric (
    evaluation_run_id, evaluation_protocol_id
);
CREATE INDEX evaluation_metric_protocol_fk_idx ON mra.evaluation_metric (
    evaluation_protocol_metric_id, evaluation_protocol_id
);
CREATE INDEX evaluation_metric_observation_metric_fk_idx ON mra.evaluation_metric_observation (
    evaluation_metric_id, evaluation_run_id, evaluation_protocol_metric_id
);
CREATE INDEX evaluation_metric_observation_observation_fk_idx ON mra.evaluation_metric_observation (
    evaluation_observation_id, evaluation_run_id,
    research_partition_member_id, market_target_outcome_revision_id
);
CREATE INDEX evaluation_metric_observation_source_fk_idx ON mra.evaluation_metric_observation (
    source_outcome_metric_id, market_target_outcome_revision_id,
    source_target_metric_definition_id, source_value_type, source_value_status
);

ALTER TABLE mra.evaluation_run
    ADD CONSTRAINT evaluation_run_evidence_authority_uk UNIQUE (
        evaluation_run_id, experiment_id, evaluation_protocol_id,
        target_definition_id, partition_purpose
    );

CREATE TABLE mra.evidence_item (
    evidence_item_id uuid PRIMARY KEY,
    evidence_code text NOT NULL,
    evaluation_run_id uuid NOT NULL,
    experiment_id uuid NOT NULL,
    evaluation_protocol_id uuid NOT NULL,
    target_definition_id uuid NOT NULL,
    partition_purpose text NOT NULL,
    evaluation_metric_id uuid,
    evaluation_protocol_metric_id uuid,
    evidence_scope text NOT NULL,
    evidence_class text NOT NULL,
    origin_class text NOT NULL,
    evidence_role text NOT NULL,
    evidence_direction text NOT NULL,
    proof_ceiling text NOT NULL,
    evaluation_terminal_at timestamptz NOT NULL,
    source_generation_max_decision_time timestamptz NOT NULL,
    observed_at timestamptz NOT NULL,
    evidence_artifact_id uuid NOT NULL,
    evidence_content_sha256 text NOT NULL,
    evidence_size_bytes bigint NOT NULL,
    code_artifact_id uuid NOT NULL,
    code_content_sha256 text NOT NULL,
    code_size_bytes bigint NOT NULL,
    config_artifact_id uuid NOT NULL,
    config_content_sha256 text NOT NULL,
    config_size_bytes bigint NOT NULL,
    provenance_sha256 text NOT NULL,
    dependency_count integer NOT NULL,
    dependency_roster_sha256 text NOT NULL,
    content_sha256 text NOT NULL,
    request_identity text NOT NULL,
    request_sha256 text NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT evidence_item_code_uk UNIQUE (evaluation_run_id, evidence_code),
    CONSTRAINT evidence_item_request_uk UNIQUE (evaluation_run_id, request_identity),
    CONSTRAINT evidence_item_exact_uk UNIQUE (
        evidence_item_id, evaluation_run_id, evidence_direction,
        evidence_class, origin_class, evidence_role
    ),
    CONSTRAINT evidence_item_run_authority_uk UNIQUE (
        evidence_item_id, evaluation_run_id
    ),
    CONSTRAINT evidence_item_evaluation_fk FOREIGN KEY (
        evaluation_run_id, experiment_id, evaluation_protocol_id,
        target_definition_id, partition_purpose
    ) REFERENCES mra.evaluation_run(
        evaluation_run_id, experiment_id, evaluation_protocol_id,
        target_definition_id, partition_purpose
    ) ON DELETE RESTRICT,
    CONSTRAINT evidence_item_metric_fk FOREIGN KEY (
        evaluation_metric_id, evaluation_run_id,
        evaluation_protocol_metric_id
    ) REFERENCES mra.evaluation_metric(
        evaluation_metric_id, evaluation_run_id,
        evaluation_protocol_metric_id
    ) ON DELETE RESTRICT,
    CONSTRAINT evidence_item_evidence_artifact_fk FOREIGN KEY (
        evidence_artifact_id, evidence_content_sha256, evidence_size_bytes
    ) REFERENCES mra.artifact(
        artifact_id, content_sha256, size_bytes
    ) ON DELETE RESTRICT,
    CONSTRAINT evidence_item_code_artifact_fk FOREIGN KEY (
        code_artifact_id, code_content_sha256, code_size_bytes
    ) REFERENCES mra.artifact(
        artifact_id, content_sha256, size_bytes
    ) ON DELETE RESTRICT,
    CONSTRAINT evidence_item_config_artifact_fk FOREIGN KEY (
        config_artifact_id, config_content_sha256, config_size_bytes
    ) REFERENCES mra.artifact(
        artifact_id, content_sha256, size_bytes
    ) ON DELETE RESTRICT,
    CONSTRAINT evidence_item_shape_ck CHECK (
        evidence_code ~ '^[a-z][a-z0-9_-]{0,99}$'
        AND partition_purpose IN ('DISCOVERY', 'FIT', 'VALIDATION', 'LOCKED_OOS', 'PROSPECTIVE')
        AND evidence_scope IN ('RUN', 'METRIC')
        AND evidence_class IN ('SOFTWARE_VERIFICATION', 'SOURCE_CAPTURE', 'TEMPORAL_LINEAGE', 'DATASET_LINEAGE', 'RESEARCH_RESULT', 'OUTCOME_OBSERVATION', 'REPLAY_COMPARISON', 'OPERATOR_ATTESTATION')
        AND origin_class IN ('FIXTURE', 'RECORDED_PROVIDER', 'QUALIFIED_ARCHIVE', 'PROSPECTIVE_CAPTURE', 'DERIVED_CANONICAL', 'OPERATOR_ATTESTED')
        AND evidence_role IN ('PRIMARY_RESULT', 'ROBUSTNESS', 'LINEAGE', 'MISSINGNESS', 'LIMITATION', 'REPLAY', 'PROCESS_CONTROL')
        AND evidence_direction IN ('SUPPORT', 'COUNTER', 'NEUTRAL')
        AND proof_ceiling IN ('ENGINEERING', 'EXPLORATORY', 'PIT_QUALIFIED', 'FORMAL_OOS', 'PROSPECTIVE')
        AND ((evidence_scope = 'RUN' AND evaluation_metric_id IS NULL AND evaluation_protocol_metric_id IS NULL)
          OR (evidence_scope = 'METRIC' AND evaluation_metric_id IS NOT NULL AND evaluation_protocol_metric_id IS NOT NULL))
        AND dependency_count >= 0
        AND evaluation_terminal_at <= observed_at AND observed_at <= recorded_at
        AND evidence_content_sha256 ~ '^[0-9a-f]{64}$'
        AND code_content_sha256 ~ '^[0-9a-f]{64}$'
        AND config_content_sha256 ~ '^[0-9a-f]{64}$'
        AND provenance_sha256 ~ '^[0-9a-f]{64}$'
        AND dependency_roster_sha256 ~ '^[0-9a-f]{64}$'
        AND content_sha256 ~ '^[0-9a-f]{64}$'
        AND request_sha256 ~ '^[0-9a-f]{64}$'
    )
);

CREATE TABLE mra.evidence_dependency (
    evidence_dependency_id uuid PRIMARY KEY,
    child_evidence_item_id uuid NOT NULL,
    parent_evidence_item_id uuid NOT NULL,
    dependency_ordinal integer NOT NULL,
    dependency_role text NOT NULL,
    content_sha256 text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT evidence_dependency_child_ordinal_uk UNIQUE (
        child_evidence_item_id, dependency_ordinal
    ),
    CONSTRAINT evidence_dependency_child_parent_uk UNIQUE (
        child_evidence_item_id, parent_evidence_item_id
    ),
    CONSTRAINT evidence_dependency_child_fk FOREIGN KEY (
        child_evidence_item_id
    ) REFERENCES mra.evidence_item(evidence_item_id)
      ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT evidence_dependency_parent_fk FOREIGN KEY (
        parent_evidence_item_id
    ) REFERENCES mra.evidence_item(evidence_item_id) ON DELETE RESTRICT,
    CONSTRAINT evidence_dependency_shape_ck CHECK (
        child_evidence_item_id <> parent_evidence_item_id
        AND dependency_ordinal > 0
        AND dependency_role IN ('DERIVED_FROM', 'CORROBORATES', 'QUALIFIES', 'CONTRADICTS')
        AND content_sha256 ~ '^[0-9a-f]{64}$'
    )
);

CREATE TABLE mra.research_assessment (
    research_assessment_id uuid PRIMARY KEY,
    assessment_code text NOT NULL,
    revision integer NOT NULL,
    supersedes_assessment_id uuid,
    experiment_id uuid NOT NULL,
    target_definition_id uuid NOT NULL,
    target_version integer NOT NULL,
    target_definition_sha256 text NOT NULL,
    knowledge_cutoff timestamptz NOT NULL,
    assessment_status text NOT NULL,
    reason_code text NOT NULL,
    evaluation_count integer NOT NULL,
    evaluation_roster_sha256 text NOT NULL,
    evidence_count integer NOT NULL,
    evidence_roster_sha256 text NOT NULL,
    source_generation_min_decision_time timestamptz NOT NULL,
    source_generation_max_decision_time timestamptz NOT NULL,
    terminal_evaluation_ceiling timestamptz NOT NULL,
    code_artifact_id uuid NOT NULL,
    code_content_sha256 text NOT NULL,
    code_size_bytes bigint NOT NULL,
    config_artifact_id uuid NOT NULL,
    config_content_sha256 text NOT NULL,
    config_size_bytes bigint NOT NULL,
    provenance_sha256 text NOT NULL,
    content_sha256 text NOT NULL,
    request_identity text NOT NULL,
    request_sha256 text NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT research_assessment_series_uk UNIQUE (assessment_code, revision),
    CONSTRAINT research_assessment_supersedes_uk UNIQUE (supersedes_assessment_id),
    CONSTRAINT research_assessment_request_uk UNIQUE (
        assessment_code, request_identity
    ),
    CONSTRAINT research_assessment_decision_authority_uk UNIQUE (
        research_assessment_id, experiment_id, target_definition_id,
        assessment_status
    ),
    CONSTRAINT research_assessment_supersedes_fk FOREIGN KEY (
        supersedes_assessment_id
    ) REFERENCES mra.research_assessment(research_assessment_id) ON DELETE RESTRICT,
    CONSTRAINT research_assessment_experiment_fk FOREIGN KEY (
        experiment_id, target_definition_id, target_version,
        target_definition_sha256
    ) REFERENCES mra.experiment(
        experiment_id, target_definition_id, target_version,
        target_definition_sha256
    ) ON DELETE RESTRICT,
    CONSTRAINT research_assessment_code_artifact_fk FOREIGN KEY (
        code_artifact_id, code_content_sha256, code_size_bytes
    ) REFERENCES mra.artifact(artifact_id, content_sha256, size_bytes) ON DELETE RESTRICT,
    CONSTRAINT research_assessment_config_artifact_fk FOREIGN KEY (
        config_artifact_id, config_content_sha256, config_size_bytes
    ) REFERENCES mra.artifact(artifact_id, content_sha256, size_bytes) ON DELETE RESTRICT,
    CONSTRAINT research_assessment_shape_ck CHECK (
        assessment_code ~ '^[a-z][a-z0-9_-]{0,99}$'
        AND ((revision = 1 AND supersedes_assessment_id IS NULL)
          OR (revision > 1 AND supersedes_assessment_id IS NOT NULL))
        AND assessment_status IN ('SUPPORTED', 'REJECTED', 'NOT_ESTIMABLE', 'INCONCLUSIVE', 'BLOCKED', 'FAILED')
        AND reason_code ~ '^[A-Z][A-Z0-9_]{0,99}$'
        AND evaluation_count > 0 AND evidence_count > 0
        AND source_generation_min_decision_time <= source_generation_max_decision_time
        AND terminal_evaluation_ceiling <= recorded_at
        AND evaluation_roster_sha256 ~ '^[0-9a-f]{64}$'
        AND evidence_roster_sha256 ~ '^[0-9a-f]{64}$'
        AND provenance_sha256 ~ '^[0-9a-f]{64}$'
        AND content_sha256 ~ '^[0-9a-f]{64}$'
        AND request_sha256 ~ '^[0-9a-f]{64}$'
    )
);

CREATE TABLE mra.research_assessment_evaluation (
    research_assessment_evaluation_id uuid PRIMARY KEY,
    research_assessment_id uuid NOT NULL,
    evaluation_ordinal integer NOT NULL,
    evaluation_run_id uuid NOT NULL,
    experiment_id uuid NOT NULL,
    evaluation_protocol_id uuid NOT NULL,
    target_definition_id uuid NOT NULL,
    partition_purpose text NOT NULL,
    evaluation_status text NOT NULL,
    terminal_at timestamptz NOT NULL,
    metric_count integer NOT NULL,
    rejected_metric_count integer NOT NULL,
    not_estimable_metric_count integer NOT NULL,
    source_generation_min_decision_time timestamptz NOT NULL,
    source_generation_max_decision_time timestamptz NOT NULL,
    content_sha256 text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT research_assessment_evaluation_ordinal_uk UNIQUE (
        research_assessment_id, evaluation_ordinal
    ),
    CONSTRAINT research_assessment_evaluation_run_uk UNIQUE (
        research_assessment_id, evaluation_run_id
    ),
    CONSTRAINT research_assessment_evaluation_exact_uk UNIQUE (
        research_assessment_evaluation_id, research_assessment_id,
        evaluation_run_id
    ),
    CONSTRAINT research_assessment_evaluation_assessment_fk FOREIGN KEY (
        research_assessment_id
    ) REFERENCES mra.research_assessment(research_assessment_id)
      ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT research_assessment_evaluation_run_fk FOREIGN KEY (
        evaluation_run_id, experiment_id, evaluation_protocol_id,
        target_definition_id, partition_purpose
    ) REFERENCES mra.evaluation_run(
        evaluation_run_id, experiment_id, evaluation_protocol_id,
        target_definition_id, partition_purpose
    ) ON DELETE RESTRICT,
    CONSTRAINT research_assessment_evaluation_shape_ck CHECK (
        evaluation_ordinal > 0
        AND evaluation_status IN ('COMPLETED', 'FAILED')
        AND partition_purpose IN ('DISCOVERY', 'FIT', 'VALIDATION', 'LOCKED_OOS', 'PROSPECTIVE')
        AND metric_count >= 0 AND rejected_metric_count >= 0
        AND not_estimable_metric_count >= 0
        AND rejected_metric_count + not_estimable_metric_count <= metric_count
        AND source_generation_min_decision_time <= source_generation_max_decision_time
        AND content_sha256 ~ '^[0-9a-f]{64}$'
    )
);

CREATE TABLE mra.research_assessment_evidence (
    research_assessment_evidence_id uuid PRIMARY KEY,
    research_assessment_id uuid NOT NULL,
    research_assessment_evaluation_id uuid NOT NULL,
    evidence_ordinal integer NOT NULL,
    evidence_item_id uuid NOT NULL,
    evaluation_run_id uuid NOT NULL,
    evidence_class text NOT NULL,
    origin_class text NOT NULL,
    evidence_role text NOT NULL,
    evidence_direction text NOT NULL,
    content_sha256 text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT research_assessment_evidence_ordinal_uk UNIQUE (
        research_assessment_id, evidence_ordinal
    ),
    CONSTRAINT research_assessment_evidence_item_uk UNIQUE (
        research_assessment_id, evidence_item_id
    ),
    CONSTRAINT research_assessment_evidence_exact_uk UNIQUE (
        research_assessment_evidence_id, research_assessment_id,
        evidence_item_id
    ),
    CONSTRAINT research_assessment_evidence_assessment_fk FOREIGN KEY (
        research_assessment_id
    ) REFERENCES mra.research_assessment(research_assessment_id)
      ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT research_assessment_evidence_evaluation_fk FOREIGN KEY (
        research_assessment_evaluation_id, research_assessment_id,
        evaluation_run_id
    ) REFERENCES mra.research_assessment_evaluation(
        research_assessment_evaluation_id, research_assessment_id,
        evaluation_run_id
    ) ON DELETE RESTRICT,
    CONSTRAINT research_assessment_evidence_item_fk FOREIGN KEY (
        evidence_item_id, evaluation_run_id, evidence_direction,
        evidence_class, origin_class, evidence_role
    ) REFERENCES mra.evidence_item(
        evidence_item_id, evaluation_run_id, evidence_direction,
        evidence_class, origin_class, evidence_role
    ) ON DELETE RESTRICT,
    CONSTRAINT research_assessment_evidence_shape_ck CHECK (
        evidence_ordinal > 0
        AND evidence_direction IN ('SUPPORT', 'COUNTER', 'NEUTRAL')
        AND content_sha256 ~ '^[0-9a-f]{64}$'
    )
);

CREATE TABLE mra.research_qualification_policy (
    research_qualification_policy_id uuid PRIMARY KEY,
    policy_code text NOT NULL,
    version integer NOT NULL,
    supersedes_policy_id uuid,
    target_definition_id uuid NOT NULL,
    target_version integer NOT NULL,
    target_definition_sha256 text NOT NULL,
    qualification_purpose text NOT NULL,
    required_assessment_status text NOT NULL,
    require_preaccess_freeze boolean NOT NULL,
    floor_count integer NOT NULL,
    floor_roster_sha256 text NOT NULL,
    code_artifact_id uuid NOT NULL,
    code_content_sha256 text NOT NULL,
    code_size_bytes bigint NOT NULL,
    config_artifact_id uuid NOT NULL,
    config_content_sha256 text NOT NULL,
    config_size_bytes bigint NOT NULL,
    provenance_sha256 text NOT NULL,
    content_sha256 text NOT NULL,
    request_identity text NOT NULL,
    request_sha256 text NOT NULL,
    frozen_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT research_qualification_policy_series_uk UNIQUE (policy_code, version),
    CONSTRAINT research_qualification_policy_supersedes_uk UNIQUE (supersedes_policy_id),
    CONSTRAINT research_qualification_policy_request_uk UNIQUE (
        policy_code, request_identity
    ),
    CONSTRAINT research_qualification_policy_decision_authority_uk UNIQUE (
        research_qualification_policy_id, target_definition_id,
        qualification_purpose
    ),
    CONSTRAINT research_qualification_policy_supersedes_fk FOREIGN KEY (
        supersedes_policy_id
    ) REFERENCES mra.research_qualification_policy(
        research_qualification_policy_id
    ) ON DELETE RESTRICT,
    CONSTRAINT research_qualification_policy_target_fk FOREIGN KEY (
        target_definition_id, target_version, target_definition_sha256
    ) REFERENCES mra.target_definition(
        target_definition_id, version, content_sha256
    ) ON DELETE RESTRICT,
    CONSTRAINT research_qualification_policy_code_artifact_fk FOREIGN KEY (
        code_artifact_id, code_content_sha256, code_size_bytes
    ) REFERENCES mra.artifact(artifact_id, content_sha256, size_bytes) ON DELETE RESTRICT,
    CONSTRAINT research_qualification_policy_config_artifact_fk FOREIGN KEY (
        config_artifact_id, config_content_sha256, config_size_bytes
    ) REFERENCES mra.artifact(artifact_id, content_sha256, size_bytes) ON DELETE RESTRICT,
    CONSTRAINT research_qualification_policy_shape_ck CHECK (
        policy_code ~ '^[a-z][a-z0-9_-]{0,99}$'
        AND ((version = 1 AND supersedes_policy_id IS NULL)
          OR (version > 1 AND supersedes_policy_id IS NOT NULL))
        AND qualification_purpose IN ('DISCOVERY', 'VALIDATION', 'LOCKED_OOS', 'PROSPECTIVE')
        AND required_assessment_status IN ('SUPPORTED', 'REJECTED', 'NOT_ESTIMABLE', 'INCONCLUSIVE', 'BLOCKED', 'FAILED')
        AND (qualification_purpose NOT IN ('LOCKED_OOS', 'PROSPECTIVE') OR require_preaccess_freeze)
        AND floor_count > 0
        AND floor_roster_sha256 ~ '^[0-9a-f]{64}$'
        AND provenance_sha256 ~ '^[0-9a-f]{64}$'
        AND content_sha256 ~ '^[0-9a-f]{64}$'
        AND request_sha256 ~ '^[0-9a-f]{64}$'
    )
);

CREATE TABLE mra.research_qualification_policy_floor (
    research_qualification_policy_floor_id uuid PRIMARY KEY,
    research_qualification_policy_id uuid NOT NULL,
    floor_code text NOT NULL,
    floor_ordinal integer NOT NULL,
    evaluation_protocol_id uuid NOT NULL,
    evaluation_protocol_metric_id uuid NOT NULL,
    source_target_metric_definition_id uuid NOT NULL,
    evaluation_protocol_metric_sha256 text NOT NULL,
    required_partition_purpose text NOT NULL,
    required_evaluation_status text NOT NULL,
    metric_code text NOT NULL,
    source_value_type text NOT NULL,
    reducer text NOT NULL,
    slice_kind text NOT NULL,
    candidate_disposition text,
    direction text NOT NULL,
    qualification_operator text NOT NULL,
    decimal_threshold numeric,
    boolean_threshold boolean,
    minimum_member_count integer NOT NULL,
    minimum_estimable_count integer NOT NULL,
    missingness_policy text NOT NULL,
    required_evidence_class text NOT NULL,
    required_origin_class text NOT NULL,
    required_evidence_role text NOT NULL,
    minimum_support_evidence_count integer NOT NULL,
    maximum_counter_evidence_count integer NOT NULL,
    required boolean NOT NULL,
    content_sha256 text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT research_qualification_policy_floor_ordinal_uk UNIQUE (
        research_qualification_policy_id, floor_ordinal
    ),
    CONSTRAINT research_qualification_policy_floor_code_uk UNIQUE (
        research_qualification_policy_id, floor_code
    ),
    CONSTRAINT research_qualification_policy_floor_exact_uk UNIQUE (
        research_qualification_policy_floor_id,
        research_qualification_policy_id
    ),
    CONSTRAINT research_qualification_policy_floor_policy_fk FOREIGN KEY (
        research_qualification_policy_id
    ) REFERENCES mra.research_qualification_policy(
        research_qualification_policy_id
    ) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT research_qualification_policy_floor_metric_fk FOREIGN KEY (
        evaluation_protocol_metric_id, evaluation_protocol_id,
        source_target_metric_definition_id, source_value_type
    ) REFERENCES mra.evaluation_protocol_metric(
        evaluation_protocol_metric_id, evaluation_protocol_id,
        source_target_metric_definition_id, source_value_type
    ) ON DELETE RESTRICT,
    CONSTRAINT research_qualification_policy_floor_shape_ck CHECK (
        floor_code ~ '^[a-z][a-z0-9_-]{0,99}$' AND floor_ordinal > 0
        AND evaluation_protocol_metric_sha256 ~ '^[0-9a-f]{64}$'
        AND required_partition_purpose IN ('DISCOVERY', 'FIT', 'VALIDATION', 'LOCKED_OOS', 'PROSPECTIVE')
        AND required_evaluation_status = 'COMPLETED'
        AND metric_code ~ '^[a-z][a-z0-9_-]{0,99}$'
        AND source_value_type IN ('DECIMAL', 'BOOLEAN')
        AND reducer IN ('MEAN_DECIMAL', 'MEDIAN_DECIMAL', 'TRUE_RATE', 'ESTIMABLE_RATE')
        AND slice_kind IN ('ALL_MEMBERS', 'CANDIDATE_DISPOSITION')
        AND ((slice_kind = 'ALL_MEMBERS' AND candidate_disposition IS NULL)
          OR (slice_kind = 'CANDIDATE_DISPOSITION' AND candidate_disposition IN ('SELECTED', 'RANKED_NOT_SELECTED', 'UNRANKABLE')))
        AND direction IN ('HIGHER', 'LOWER', 'DESCRIPTIVE')
        AND qualification_operator IN ('AT_LEAST', 'AT_MOST', 'EQUALS')
        AND ((source_value_type = 'DECIMAL' AND decimal_threshold IS NOT NULL AND boolean_threshold IS NULL AND qualification_operator <> 'EQUALS')
          OR (source_value_type = 'BOOLEAN' AND decimal_threshold IS NULL AND boolean_threshold IS NOT NULL AND qualification_operator = 'EQUALS'))
        AND minimum_member_count > 0 AND minimum_estimable_count > 0
        AND missingness_policy IN ('REJECT', 'INCONCLUSIVE')
        AND minimum_support_evidence_count >= 0
        AND maximum_counter_evidence_count >= 0
        AND content_sha256 ~ '^[0-9a-f]{64}$'
    )
);

CREATE TABLE mra.research_qualification_decision (
    research_qualification_decision_id uuid PRIMARY KEY,
    decision_code text NOT NULL,
    revision integer NOT NULL,
    supersedes_decision_id uuid,
    research_assessment_id uuid NOT NULL,
    research_qualification_policy_id uuid NOT NULL,
    experiment_id uuid NOT NULL,
    target_definition_id uuid NOT NULL,
    assessment_status text NOT NULL,
    qualification_purpose text NOT NULL,
    decision_status text NOT NULL,
    reason_code text NOT NULL,
    floor_count integer NOT NULL,
    floor_result_roster_sha256 text NOT NULL,
    source_generation_max_decision_time timestamptz NOT NULL,
    effective_at timestamptz NOT NULL,
    known_at timestamptz NOT NULL,
    code_artifact_id uuid NOT NULL,
    code_content_sha256 text NOT NULL,
    code_size_bytes bigint NOT NULL,
    config_artifact_id uuid NOT NULL,
    config_content_sha256 text NOT NULL,
    config_size_bytes bigint NOT NULL,
    provenance_sha256 text NOT NULL,
    content_sha256 text NOT NULL,
    request_identity text NOT NULL,
    request_sha256 text NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT research_qualification_decision_series_uk UNIQUE (
        decision_code, revision
    ),
    CONSTRAINT research_qualification_decision_supersedes_uk UNIQUE (
        supersedes_decision_id
    ),
    CONSTRAINT research_qualification_decision_request_uk UNIQUE (
        decision_code, request_identity
    ),
    CONSTRAINT research_qualification_decision_supersedes_fk FOREIGN KEY (
        supersedes_decision_id
    ) REFERENCES mra.research_qualification_decision(
        research_qualification_decision_id
    ) ON DELETE RESTRICT,
    CONSTRAINT research_qualification_decision_assessment_fk FOREIGN KEY (
        research_assessment_id, experiment_id, target_definition_id,
        assessment_status
    ) REFERENCES mra.research_assessment(
        research_assessment_id, experiment_id, target_definition_id,
        assessment_status
    ) ON DELETE RESTRICT,
    CONSTRAINT research_qualification_decision_policy_fk FOREIGN KEY (
        research_qualification_policy_id, target_definition_id,
        qualification_purpose
    ) REFERENCES mra.research_qualification_policy(
        research_qualification_policy_id, target_definition_id,
        qualification_purpose
    ) ON DELETE RESTRICT,
    CONSTRAINT research_qualification_decision_code_artifact_fk FOREIGN KEY (
        code_artifact_id, code_content_sha256, code_size_bytes
    ) REFERENCES mra.artifact(artifact_id, content_sha256, size_bytes) ON DELETE RESTRICT,
    CONSTRAINT research_qualification_decision_config_artifact_fk FOREIGN KEY (
        config_artifact_id, config_content_sha256, config_size_bytes
    ) REFERENCES mra.artifact(artifact_id, content_sha256, size_bytes) ON DELETE RESTRICT,
    CONSTRAINT research_qualification_decision_shape_ck CHECK (
        decision_code ~ '^[a-z][a-z0-9_-]{0,99}$'
        AND ((revision = 1 AND supersedes_decision_id IS NULL)
          OR (revision > 1 AND supersedes_decision_id IS NOT NULL))
        AND decision_status IN ('ADMITTED', 'REJECTED', 'INCONCLUSIVE')
        AND reason_code ~ '^[A-Z][A-Z0-9_]{0,99}$'
        AND floor_count > 0
        AND source_generation_max_decision_time < effective_at
        AND effective_at <= known_at AND known_at <= recorded_at
        AND floor_result_roster_sha256 ~ '^[0-9a-f]{64}$'
        AND provenance_sha256 ~ '^[0-9a-f]{64}$'
        AND content_sha256 ~ '^[0-9a-f]{64}$'
        AND request_sha256 ~ '^[0-9a-f]{64}$'
    )
);

ALTER TABLE mra.evaluation_metric
    ADD CONSTRAINT evaluation_metric_result_authority_uk UNIQUE (
        evaluation_metric_id, evaluation_run_id
    );

CREATE TABLE mra.research_qualification_floor_result (
    research_qualification_floor_result_id uuid PRIMARY KEY,
    research_qualification_decision_id uuid NOT NULL,
    research_qualification_policy_floor_id uuid NOT NULL,
    research_qualification_policy_id uuid NOT NULL,
    result_ordinal integer NOT NULL,
    research_assessment_evaluation_id uuid,
    research_assessment_id uuid NOT NULL,
    evaluation_run_id uuid,
    evaluation_metric_id uuid,
    result_status text NOT NULL,
    observed_decimal_value numeric,
    observed_boolean_value boolean,
    member_count integer NOT NULL,
    estimable_count integer NOT NULL,
    not_estimable_count integer NOT NULL,
    support_evidence_count integer NOT NULL,
    counter_evidence_count integer NOT NULL,
    evidence_roster_sha256 text NOT NULL,
    reason_code text NOT NULL,
    content_sha256 text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT research_qualification_floor_result_ordinal_uk UNIQUE (
        research_qualification_decision_id, result_ordinal
    ),
    CONSTRAINT research_qualification_floor_result_floor_uk UNIQUE (
        research_qualification_decision_id,
        research_qualification_policy_floor_id
    ),
    CONSTRAINT research_qualification_floor_result_exact_uk UNIQUE (
        research_qualification_floor_result_id,
        research_qualification_decision_id,
        research_assessment_id
    ),
    CONSTRAINT research_qualification_floor_result_decision_fk FOREIGN KEY (
        research_qualification_decision_id
    ) REFERENCES mra.research_qualification_decision(
        research_qualification_decision_id
    ) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT research_qualification_floor_result_floor_fk FOREIGN KEY (
        research_qualification_policy_floor_id,
        research_qualification_policy_id
    ) REFERENCES mra.research_qualification_policy_floor(
        research_qualification_policy_floor_id,
        research_qualification_policy_id
    ) ON DELETE RESTRICT,
    CONSTRAINT research_qualification_floor_result_assessment_fk FOREIGN KEY (
        research_assessment_evaluation_id, research_assessment_id,
        evaluation_run_id
    ) REFERENCES mra.research_assessment_evaluation(
        research_assessment_evaluation_id, research_assessment_id,
        evaluation_run_id
    ) ON DELETE RESTRICT,
    CONSTRAINT research_qualification_floor_result_metric_fk FOREIGN KEY (
        evaluation_metric_id, evaluation_run_id
    ) REFERENCES mra.evaluation_metric(
        evaluation_metric_id, evaluation_run_id
    ) ON DELETE RESTRICT,
    CONSTRAINT research_qualification_floor_result_shape_ck CHECK (
        result_ordinal > 0
        AND result_status IN ('SATISFIED', 'REJECTED', 'MISSING', 'NOT_ESTIMABLE', 'INCONCLUSIVE', 'BLOCKED')
        AND member_count >= 0 AND estimable_count >= 0
        AND not_estimable_count >= 0
        AND estimable_count + not_estimable_count <= member_count
        AND support_evidence_count >= 0 AND counter_evidence_count >= 0
        AND ((evaluation_metric_id IS NULL AND evaluation_run_id IS NULL AND research_assessment_evaluation_id IS NULL)
          OR (evaluation_metric_id IS NOT NULL AND evaluation_run_id IS NOT NULL AND research_assessment_evaluation_id IS NOT NULL))
        AND evidence_roster_sha256 ~ '^[0-9a-f]{64}$'
        AND reason_code ~ '^[A-Z][A-Z0-9_]{0,99}$'
        AND content_sha256 ~ '^[0-9a-f]{64}$'
    )
);

CREATE TABLE mra.research_qualification_floor_evidence (
    research_qualification_floor_evidence_id uuid PRIMARY KEY,
    research_qualification_decision_id uuid NOT NULL,
    research_qualification_floor_result_id uuid NOT NULL,
    research_assessment_id uuid NOT NULL,
    research_assessment_evidence_id uuid NOT NULL,
    evidence_item_id uuid NOT NULL,
    evidence_ordinal integer NOT NULL,
    evidence_direction text NOT NULL,
    content_sha256 text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT research_qualification_floor_evidence_ordinal_uk UNIQUE (
        research_qualification_floor_result_id, evidence_ordinal
    ),
    CONSTRAINT research_qualification_floor_evidence_item_uk UNIQUE (
        research_qualification_floor_result_id,
        research_assessment_evidence_id
    ),
    CONSTRAINT research_qualification_floor_evidence_result_fk FOREIGN KEY (
        research_qualification_floor_result_id,
        research_qualification_decision_id,
        research_assessment_id
    ) REFERENCES mra.research_qualification_floor_result(
        research_qualification_floor_result_id,
        research_qualification_decision_id,
        research_assessment_id
    ) ON DELETE RESTRICT,
    CONSTRAINT research_qualification_floor_evidence_assessment_fk FOREIGN KEY (
        research_assessment_evidence_id, research_assessment_id,
        evidence_item_id
    ) REFERENCES mra.research_assessment_evidence(
        research_assessment_evidence_id, research_assessment_id,
        evidence_item_id
    ) ON DELETE RESTRICT,
    CONSTRAINT research_qualification_floor_evidence_shape_ck CHECK (
        evidence_ordinal > 0
        AND evidence_direction IN ('SUPPORT', 'COUNTER', 'NEUTRAL')
        AND content_sha256 ~ '^[0-9a-f]{64}$'
    )
);

CREATE INDEX evidence_item_evaluation_fk_idx ON mra.evidence_item (
    evaluation_run_id, experiment_id, evaluation_protocol_id,
    target_definition_id, partition_purpose
);
CREATE INDEX evidence_item_metric_fk_idx ON mra.evidence_item (
    evaluation_metric_id, evaluation_run_id, evaluation_protocol_metric_id
);
CREATE INDEX evidence_item_evidence_artifact_fk_idx ON mra.evidence_item (
    evidence_artifact_id, evidence_content_sha256, evidence_size_bytes
);
CREATE INDEX evidence_item_code_artifact_fk_idx ON mra.evidence_item (
    code_artifact_id, code_content_sha256, code_size_bytes
);
CREATE INDEX evidence_item_config_artifact_fk_idx ON mra.evidence_item (
    config_artifact_id, config_content_sha256, config_size_bytes
);
CREATE INDEX evidence_dependency_child_fk_idx ON mra.evidence_dependency (child_evidence_item_id);
CREATE INDEX evidence_dependency_parent_fk_idx ON mra.evidence_dependency (parent_evidence_item_id);
CREATE INDEX research_assessment_supersedes_fk_idx ON mra.research_assessment (supersedes_assessment_id);
CREATE INDEX research_assessment_experiment_fk_idx ON mra.research_assessment (
    experiment_id, target_definition_id, target_version, target_definition_sha256
);
CREATE INDEX research_assessment_code_artifact_fk_idx ON mra.research_assessment (
    code_artifact_id, code_content_sha256, code_size_bytes
);
CREATE INDEX research_assessment_config_artifact_fk_idx ON mra.research_assessment (
    config_artifact_id, config_content_sha256, config_size_bytes
);
CREATE INDEX research_assessment_evaluation_assessment_fk_idx ON mra.research_assessment_evaluation (research_assessment_id);
CREATE INDEX research_assessment_evaluation_run_fk_idx ON mra.research_assessment_evaluation (
    evaluation_run_id, experiment_id, evaluation_protocol_id,
    target_definition_id, partition_purpose
);
CREATE INDEX research_assessment_evidence_assessment_fk_idx ON mra.research_assessment_evidence (research_assessment_id);
CREATE INDEX research_assessment_evidence_evaluation_fk_idx ON mra.research_assessment_evidence (
    research_assessment_evaluation_id, research_assessment_id, evaluation_run_id
);
CREATE INDEX research_assessment_evidence_item_fk_idx ON mra.research_assessment_evidence (
    evidence_item_id, evaluation_run_id, evidence_direction,
    evidence_class, origin_class, evidence_role
);
CREATE INDEX research_qualification_policy_supersedes_fk_idx ON mra.research_qualification_policy (supersedes_policy_id);
CREATE INDEX research_qualification_policy_target_fk_idx ON mra.research_qualification_policy (
    target_definition_id, target_version, target_definition_sha256
);
CREATE INDEX research_qualification_policy_code_artifact_fk_idx ON mra.research_qualification_policy (
    code_artifact_id, code_content_sha256, code_size_bytes
);
CREATE INDEX research_qualification_policy_config_artifact_fk_idx ON mra.research_qualification_policy (
    config_artifact_id, config_content_sha256, config_size_bytes
);
CREATE INDEX research_qualification_policy_floor_policy_fk_idx ON mra.research_qualification_policy_floor (research_qualification_policy_id);
CREATE INDEX research_qualification_policy_floor_metric_fk_idx ON mra.research_qualification_policy_floor (
    evaluation_protocol_metric_id, evaluation_protocol_id,
    source_target_metric_definition_id, source_value_type
);
CREATE INDEX research_qualification_decision_supersedes_fk_idx ON mra.research_qualification_decision (supersedes_decision_id);
CREATE INDEX research_qualification_decision_assessment_fk_idx ON mra.research_qualification_decision (
    research_assessment_id, experiment_id, target_definition_id,
    assessment_status
);
CREATE INDEX research_qualification_decision_policy_fk_idx ON mra.research_qualification_decision (
    research_qualification_policy_id, target_definition_id,
    qualification_purpose
);
CREATE INDEX research_qualification_decision_code_artifact_fk_idx ON mra.research_qualification_decision (
    code_artifact_id, code_content_sha256, code_size_bytes
);
CREATE INDEX research_qualification_decision_config_artifact_fk_idx ON mra.research_qualification_decision (
    config_artifact_id, config_content_sha256, config_size_bytes
);
CREATE INDEX research_qualification_floor_result_decision_fk_idx ON mra.research_qualification_floor_result (research_qualification_decision_id);
CREATE INDEX research_qualification_floor_result_floor_fk_idx ON mra.research_qualification_floor_result (
    research_qualification_policy_floor_id, research_qualification_policy_id
);
CREATE INDEX research_qualification_floor_result_assessment_fk_idx ON mra.research_qualification_floor_result (
    research_assessment_evaluation_id, research_assessment_id, evaluation_run_id
);
CREATE INDEX research_qualification_floor_result_metric_fk_idx ON mra.research_qualification_floor_result (
    evaluation_metric_id, evaluation_run_id
);
CREATE INDEX research_qualification_floor_evidence_result_fk_idx ON mra.research_qualification_floor_evidence (
    research_qualification_floor_result_id,
    research_qualification_decision_id, research_assessment_id
);
CREATE INDEX research_qualification_floor_evidence_assessment_fk_idx ON mra.research_qualification_floor_evidence (
    research_assessment_evidence_id, research_assessment_id,
    evidence_item_id
);

CREATE FUNCTION mra.guard_evidence_dependency_insert()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE parent_recorded_at timestamptz;
BEGIN
    IF EXISTS (
        SELECT 1 FROM mra.evidence_item
        WHERE evidence_item_id = NEW.child_evidence_item_id
    ) THEN
        RAISE EXCEPTION 'Evidence dependency roster is already frozen'
            USING ERRCODE = '55000';
    END IF;
    SELECT recorded_at INTO parent_recorded_at
    FROM mra.evidence_item
    WHERE evidence_item_id = NEW.parent_evidence_item_id
    FOR SHARE;
    IF parent_recorded_at IS NULL OR parent_recorded_at >= NEW.created_at THEN
        RAISE EXCEPTION 'Evidence dependency parent must be an earlier immutable EvidenceItem'
            USING ERRCODE = '55000';
    END IF;
    IF NEW.content_sha256 <> mra.canonical_sha256(
        replace(
            json_build_object(
                'dependency_role', NEW.dependency_role,
                'evidence_dependency_id', NEW.evidence_dependency_id,
                'ordinal', NEW.dependency_ordinal,
                'parent_evidence_item_id', NEW.parent_evidence_item_id
            )::text,
            ' ',
            ''
        )
    ) THEN
        RAISE EXCEPTION 'Evidence dependency content hash is invalid'
            USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION mra.validate_evidence_item_closure()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE actual_count integer;
DECLARE minimum_ordinal integer;
DECLARE maximum_ordinal integer;
DECLARE actual_roster_hash text;
DECLARE actual_terminal_at timestamptz;
DECLARE actual_generation_max timestamptz;
DECLARE actual_status text;
BEGIN
    SELECT count(*), min(dependency_ordinal), max(dependency_ordinal),
           mra.canonical_sha256(
               replace(
                   coalesce(
                       json_agg(
                           json_build_object(
                               'content_sha256', content_sha256,
                               'dependency_role', dependency_role,
                               'evidence_dependency_id', evidence_dependency_id,
                               'ordinal', dependency_ordinal,
                               'parent_evidence_item_id', parent_evidence_item_id
                           ) ORDER BY dependency_ordinal
                       ),
                       '[]'::json
                   )::text,
                   ' ',
                   ''
               )
           )
      INTO actual_count, minimum_ordinal, maximum_ordinal, actual_roster_hash
    FROM mra.evidence_dependency
    WHERE child_evidence_item_id = NEW.evidence_item_id;

    SELECT run.status, coalesce(run.completed_at, run.failed_at),
           max(member.decision_time)
      INTO actual_status, actual_terminal_at, actual_generation_max
    FROM mra.evaluation_run AS run
    JOIN mra.research_partition_member AS member
      ON member.research_partition_id = run.research_partition_id
    WHERE run.evaluation_run_id = NEW.evaluation_run_id
    GROUP BY run.status, run.completed_at, run.failed_at;

    IF actual_status NOT IN ('COMPLETED', 'FAILED')
       OR actual_terminal_at IS NULL
       OR actual_terminal_at <> NEW.evaluation_terminal_at
       OR actual_generation_max <> NEW.source_generation_max_decision_time
       OR actual_count <> NEW.dependency_count
       OR actual_roster_hash <> NEW.dependency_roster_sha256
       OR (actual_count > 0 AND (
           minimum_ordinal <> 1 OR maximum_ordinal <> actual_count
       ))
       OR EXISTS (
           SELECT 1
           FROM mra.evidence_dependency AS dependency
           JOIN mra.evidence_item AS parent
             ON parent.evidence_item_id = dependency.parent_evidence_item_id
           WHERE dependency.child_evidence_item_id = NEW.evidence_item_id
             AND parent.recorded_at >= NEW.recorded_at
       ) THEN
        RAISE EXCEPTION 'EvidenceItem dependency or Evaluation closure is invalid'
            USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION mra.guard_research_assessment_child_insert()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM mra.research_assessment
        WHERE research_assessment_id = NEW.research_assessment_id
    ) THEN
        RAISE EXCEPTION 'ResearchAssessment roster is already frozen'
            USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION mra.guard_research_assessment_insert()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE predecessor record;
BEGIN
    PERFORM pg_advisory_xact_lock(
        hashtextextended('research-assessment:' || NEW.assessment_code, 0)
    );
    IF NEW.knowledge_cutoff > NEW.recorded_at THEN
        RAISE EXCEPTION 'ResearchAssessment knowledge cutoff is in the future'
            USING ERRCODE = '55000';
    END IF;
    IF NEW.revision > 1 THEN
        SELECT assessment_code, experiment_id, revision, recorded_at
          INTO predecessor
        FROM mra.research_assessment
        WHERE research_assessment_id = NEW.supersedes_assessment_id
        FOR SHARE;
        IF predecessor.assessment_code IS DISTINCT FROM NEW.assessment_code
           OR predecessor.experiment_id IS DISTINCT FROM NEW.experiment_id
           OR predecessor.revision + 1 <> NEW.revision
           OR predecessor.recorded_at >= NEW.recorded_at THEN
            RAISE EXCEPTION 'ResearchAssessment supersession chain is invalid'
                USING ERRCODE = '55000';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION mra.validate_research_assessment_closure()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE actual_evaluation_count integer;
DECLARE actual_evidence_count integer;
DECLARE minimum_evaluation_ordinal integer;
DECLARE maximum_evaluation_ordinal integer;
DECLARE minimum_evidence_ordinal integer;
DECLARE maximum_evidence_ordinal integer;
DECLARE actual_evaluation_hash text;
DECLARE actual_evidence_hash text;
DECLARE actual_min_generation timestamptz;
DECLARE actual_max_generation timestamptz;
DECLARE actual_terminal_ceiling timestamptz;
DECLARE derived_status text;
BEGIN
    SELECT count(*), min(evaluation_ordinal), max(evaluation_ordinal),
           mra.canonical_sha256(
               replace(
                   json_agg(
                       json_build_object(
                           'content_sha256', content_sha256,
                           'evaluation_ordinal', evaluation_ordinal,
                           'evaluation_run_id', evaluation_run_id,
                           'research_assessment_evaluation_id',
                               research_assessment_evaluation_id
                       ) ORDER BY evaluation_ordinal
                   )::text,
                   ' ',
                   ''
               )
           ),
           min(source_generation_min_decision_time),
           max(source_generation_max_decision_time),
           max(terminal_at)
      INTO actual_evaluation_count, minimum_evaluation_ordinal,
           maximum_evaluation_ordinal, actual_evaluation_hash,
           actual_min_generation, actual_max_generation,
           actual_terminal_ceiling
    FROM mra.research_assessment_evaluation
    WHERE research_assessment_id = NEW.research_assessment_id;

    SELECT count(*), min(evidence_ordinal), max(evidence_ordinal),
           mra.canonical_sha256(
               replace(
                   json_agg(
                       json_build_object(
                           'content_sha256', content_sha256,
                           'evidence_item_id', evidence_item_id,
                           'evidence_ordinal', evidence_ordinal,
                           'research_assessment_evidence_id',
                               research_assessment_evidence_id
                       ) ORDER BY evidence_ordinal
                   )::text,
                   ' ',
                   ''
               )
           )
      INTO actual_evidence_count, minimum_evidence_ordinal,
           maximum_evidence_ordinal, actual_evidence_hash
    FROM mra.research_assessment_evidence
    WHERE research_assessment_id = NEW.research_assessment_id;

    SELECT CASE
        WHEN bool_or(evaluation_status = 'FAILED') THEN 'BLOCKED'
        WHEN bool_or(rejected_metric_count > 0) THEN 'REJECTED'
        WHEN sum(metric_count) > 0
             AND sum(not_estimable_metric_count) = sum(metric_count)
          THEN 'NOT_ESTIMABLE'
        WHEN bool_or(not_estimable_metric_count > 0)
             OR EXISTS (
                 SELECT 1 FROM mra.research_assessment_evidence
                 WHERE research_assessment_id = NEW.research_assessment_id
                   AND evidence_direction = 'COUNTER'
             )
             OR NOT EXISTS (
                 SELECT 1 FROM mra.research_assessment_evidence
                 WHERE research_assessment_id = NEW.research_assessment_id
                   AND evidence_direction = 'SUPPORT'
             )
          THEN 'INCONCLUSIVE'
        ELSE 'SUPPORTED'
    END INTO derived_status
    FROM mra.research_assessment_evaluation
    WHERE research_assessment_id = NEW.research_assessment_id;

    IF actual_evaluation_count <> NEW.evaluation_count
       OR minimum_evaluation_ordinal <> 1
       OR maximum_evaluation_ordinal <> NEW.evaluation_count
       OR actual_evaluation_hash <> NEW.evaluation_roster_sha256
       OR actual_evidence_count <> NEW.evidence_count
       OR minimum_evidence_ordinal <> 1
       OR maximum_evidence_ordinal <> NEW.evidence_count
       OR actual_evidence_hash <> NEW.evidence_roster_sha256
       OR actual_min_generation <> NEW.source_generation_min_decision_time
       OR actual_max_generation <> NEW.source_generation_max_decision_time
       OR actual_terminal_ceiling <> NEW.terminal_evaluation_ceiling
       OR derived_status <> NEW.assessment_status
       OR EXISTS (
           SELECT 1
           FROM mra.research_assessment_evaluation AS item
           JOIN mra.evaluation_run AS run
             ON run.evaluation_run_id = item.evaluation_run_id
           WHERE item.research_assessment_id = NEW.research_assessment_id
             AND (
                 run.experiment_id <> NEW.experiment_id
                 OR run.status <> item.evaluation_status
                 OR coalesce(run.completed_at, run.failed_at) <> item.terminal_at
                 OR run.opened_at > NEW.knowledge_cutoff
             )
       )
       OR EXISTS (
           (SELECT run.evaluation_run_id
            FROM mra.evaluation_run AS run
            WHERE run.experiment_id = NEW.experiment_id
              AND run.opened_at <= NEW.knowledge_cutoff)
           EXCEPT
           (SELECT item.evaluation_run_id
            FROM mra.research_assessment_evaluation AS item
            WHERE item.research_assessment_id = NEW.research_assessment_id)
       )
       OR EXISTS (
           SELECT 1
           FROM mra.research_assessment_evaluation AS item
           WHERE item.research_assessment_id = NEW.research_assessment_id
             AND NOT EXISTS (
                 SELECT 1 FROM mra.research_assessment_evidence AS evidence
                 WHERE evidence.research_assessment_evaluation_id =
                       item.research_assessment_evaluation_id
             )
       )
       OR EXISTS (
           (SELECT evidence.evidence_item_id
            FROM mra.evidence_item AS evidence
            JOIN mra.evaluation_run AS run
              ON run.evaluation_run_id = evidence.evaluation_run_id
            WHERE run.experiment_id = NEW.experiment_id
              AND run.opened_at <= NEW.knowledge_cutoff
              AND evidence.recorded_at <= NEW.knowledge_cutoff)
           EXCEPT
           (SELECT item.evidence_item_id
            FROM mra.research_assessment_evidence AS item
            WHERE item.research_assessment_id = NEW.research_assessment_id)
       ) THEN
        RAISE EXCEPTION 'ResearchAssessment roster or derived conclusion is incomplete'
            USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION mra.guard_research_qualification_policy_floor_insert()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM mra.research_qualification_policy
        WHERE research_qualification_policy_id =
              NEW.research_qualification_policy_id
    ) THEN
        RAISE EXCEPTION 'ResearchQualificationPolicy floor roster is already frozen'
            USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION mra.validate_research_qualification_policy_closure()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE actual_count integer;
DECLARE minimum_ordinal integer;
DECLARE maximum_ordinal integer;
DECLARE actual_roster_hash text;
DECLARE predecessor record;
BEGIN
    SELECT count(*), min(floor_ordinal), max(floor_ordinal),
           mra.canonical_sha256(
               replace(
                   json_agg(
                       json_build_object(
                           'boolean_threshold', boolean_threshold,
                           'candidate_disposition', candidate_disposition,
                           'content_sha256', content_sha256,
                           'decimal_threshold', decimal_threshold::text,
                           'direction', direction,
                           'evaluation_protocol_id', evaluation_protocol_id,
                           'evaluation_protocol_metric_id', evaluation_protocol_metric_id,
                           'evaluation_protocol_metric_sha256', evaluation_protocol_metric_sha256,
                           'floor_code', floor_code,
                           'maximum_counter_evidence_count', maximum_counter_evidence_count,
                           'minimum_estimable_count', minimum_estimable_count,
                           'minimum_member_count', minimum_member_count,
                           'minimum_support_evidence_count', minimum_support_evidence_count,
                           'missingness_policy', missingness_policy,
                           'operator', qualification_operator,
                           'ordinal', floor_ordinal,
                           'reducer', reducer,
                           'required', required,
                           'required_evaluation_status', required_evaluation_status,
                           'required_evidence_class', required_evidence_class,
                           'required_evidence_role', required_evidence_role,
                           'required_origin_class', required_origin_class,
                           'required_partition_purpose', required_partition_purpose,
                           'research_qualification_policy_floor_id', research_qualification_policy_floor_id,
                           'slice_kind', slice_kind,
                           'source_value_type', source_value_type
                       ) ORDER BY floor_ordinal
                   )::text,
                   ' ',
                   ''
               )
           )
      INTO actual_count, minimum_ordinal, maximum_ordinal, actual_roster_hash
    FROM mra.research_qualification_policy_floor
    WHERE research_qualification_policy_id = NEW.research_qualification_policy_id;

    IF NEW.version > 1 THEN
        SELECT policy_code, version, target_definition_id,
               qualification_purpose, frozen_at
          INTO predecessor
        FROM mra.research_qualification_policy
        WHERE research_qualification_policy_id = NEW.supersedes_policy_id
        FOR SHARE;
    END IF;

    IF actual_count <> NEW.floor_count
       OR minimum_ordinal <> 1 OR maximum_ordinal <> NEW.floor_count
       OR actual_roster_hash <> NEW.floor_roster_sha256
       OR (NEW.version > 1 AND (
           predecessor.policy_code IS DISTINCT FROM NEW.policy_code
           OR predecessor.version + 1 <> NEW.version
           OR predecessor.target_definition_id IS DISTINCT FROM NEW.target_definition_id
           OR predecessor.qualification_purpose IS DISTINCT FROM NEW.qualification_purpose
           OR predecessor.frozen_at >= NEW.frozen_at
       ))
       OR EXISTS (
           SELECT 1
           FROM mra.research_qualification_policy_floor AS floor
           JOIN mra.evaluation_protocol_metric AS metric
             ON metric.evaluation_protocol_metric_id =
                floor.evaluation_protocol_metric_id
           WHERE floor.research_qualification_policy_id =
                 NEW.research_qualification_policy_id
             AND (
                 metric.content_sha256 <> floor.evaluation_protocol_metric_sha256
                 OR metric.metric_code <> floor.metric_code
                 OR metric.source_value_type <> floor.source_value_type
                 OR metric.reducer <> floor.reducer
                 OR metric.slice_kind <> floor.slice_kind
                 OR metric.candidate_disposition IS DISTINCT FROM floor.candidate_disposition
                 OR metric.direction <> floor.direction
                 OR (floor.reducer IN ('MEAN_DECIMAL', 'MEDIAN_DECIMAL', 'ESTIMABLE_RATE')
                     AND floor.source_value_type <> 'DECIMAL')
                 OR (floor.reducer = 'TRUE_RATE'
                     AND floor.source_value_type <> 'BOOLEAN')
             )
       )
       OR EXISTS (
           SELECT 1
           FROM mra.research_qualification_policy_floor AS floor
           WHERE floor.research_qualification_policy_id =
                 NEW.research_qualification_policy_id
             AND NOT (
                 (NEW.qualification_purpose = 'DISCOVERY'
                  AND floor.required_partition_purpose IN ('DISCOVERY', 'FIT'))
                 OR (NEW.qualification_purpose = 'VALIDATION'
                     AND floor.required_partition_purpose IN ('FIT', 'VALIDATION'))
                 OR (NEW.qualification_purpose = 'LOCKED_OOS'
                     AND floor.required_partition_purpose IN ('FIT', 'VALIDATION', 'LOCKED_OOS'))
                 OR (NEW.qualification_purpose = 'PROSPECTIVE'
                     AND floor.required_partition_purpose IN ('FIT', 'VALIDATION', 'LOCKED_OOS', 'PROSPECTIVE'))
             )
       ) THEN
        RAISE EXCEPTION 'ResearchQualificationPolicy floor closure is invalid'
            USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION mra.guard_research_qualification_child_insert()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM mra.research_qualification_decision
        WHERE research_qualification_decision_id =
              NEW.research_qualification_decision_id
    ) THEN
        RAISE EXCEPTION 'ResearchQualificationDecision result roster is already frozen'
            USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION mra.guard_research_qualification_decision_insert()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE predecessor record;
DECLARE policy_frozen_at timestamptz;
DECLARE assessment_recorded_at timestamptz;
DECLARE assessment_generation timestamptz;
BEGIN
    PERFORM pg_advisory_xact_lock(
        hashtextextended('research-qualification:' || NEW.decision_code, 0)
    );
    SELECT policy.frozen_at, assessment.recorded_at,
           assessment.source_generation_max_decision_time
      INTO policy_frozen_at, assessment_recorded_at, assessment_generation
    FROM mra.research_qualification_policy AS policy
    CROSS JOIN mra.research_assessment AS assessment
    WHERE policy.research_qualification_policy_id =
          NEW.research_qualification_policy_id
      AND assessment.research_assessment_id = NEW.research_assessment_id
    FOR SHARE;
    IF policy_frozen_at IS NULL
       OR assessment_recorded_at >= NEW.recorded_at
       OR assessment_generation <> NEW.source_generation_max_decision_time
       OR NEW.source_generation_max_decision_time >= NEW.effective_at THEN
        RAISE EXCEPTION 'ResearchQualificationDecision generation ordering is invalid'
            USING ERRCODE = '55000';
    END IF;
    IF NEW.revision > 1 THEN
        SELECT decision_code, revision, research_assessment_id,
               research_qualification_policy_id, recorded_at
          INTO predecessor
        FROM mra.research_qualification_decision
        WHERE research_qualification_decision_id = NEW.supersedes_decision_id
        FOR SHARE;
        IF predecessor.decision_code IS DISTINCT FROM NEW.decision_code
           OR predecessor.revision + 1 <> NEW.revision
           OR predecessor.recorded_at >= NEW.recorded_at THEN
            RAISE EXCEPTION 'ResearchQualificationDecision supersession chain is invalid'
                USING ERRCODE = '55000';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION mra.validate_research_qualification_decision_closure()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE actual_count integer;
DECLARE minimum_ordinal integer;
DECLARE maximum_ordinal integer;
DECLARE actual_roster_hash text;
DECLARE required_count integer;
DECLARE derived_status text;
DECLARE first_access_at timestamptz;
BEGIN
    SELECT count(*), min(result_ordinal), max(result_ordinal),
           mra.canonical_sha256(
               replace(
                   json_agg(
                       json_build_object(
                           'content_sha256', content_sha256,
                           'research_qualification_floor_result_id',
                               research_qualification_floor_result_id,
                           'research_qualification_policy_floor_id',
                               research_qualification_policy_floor_id,
                           'result_ordinal', result_ordinal
                       ) ORDER BY result_ordinal
                   )::text,
                   ' ',
                   ''
               )
           )
      INTO actual_count, minimum_ordinal, maximum_ordinal, actual_roster_hash
    FROM mra.research_qualification_floor_result
    WHERE research_qualification_decision_id =
          NEW.research_qualification_decision_id;

    SELECT count(*) INTO required_count
    FROM mra.research_qualification_policy_floor
    WHERE research_qualification_policy_id =
          NEW.research_qualification_policy_id
      AND required;

    SELECT CASE
        WHEN NEW.assessment_status = 'REJECTED'
          OR EXISTS (
              SELECT 1
              FROM mra.research_qualification_floor_result AS result
              JOIN mra.research_qualification_policy_floor AS floor
                ON floor.research_qualification_policy_floor_id =
                   result.research_qualification_policy_floor_id
              WHERE result.research_qualification_decision_id =
                    NEW.research_qualification_decision_id
                AND floor.required AND result.result_status = 'REJECTED'
          ) THEN 'REJECTED'
        WHEN NEW.assessment_status = (
                 SELECT required_assessment_status
                 FROM mra.research_qualification_policy
                 WHERE research_qualification_policy_id =
                       NEW.research_qualification_policy_id
             )
             AND required_count > 0
             AND NOT EXISTS (
                 SELECT 1
                 FROM mra.research_qualification_floor_result AS result
                 JOIN mra.research_qualification_policy_floor AS floor
                   ON floor.research_qualification_policy_floor_id =
                      result.research_qualification_policy_floor_id
                 WHERE result.research_qualification_decision_id =
                       NEW.research_qualification_decision_id
                   AND floor.required
                   AND result.result_status <> 'SATISFIED'
             ) THEN 'ADMITTED'
        ELSE 'INCONCLUSIVE'
    END INTO derived_status;

    SELECT min(access.accessed_at) INTO first_access_at
    FROM mra.research_assessment_evaluation AS item
    JOIN mra.evaluation_run AS run
      ON run.evaluation_run_id = item.evaluation_run_id
    JOIN mra.research_partition_outcome_access AS access
      ON access.evaluation_run_id = run.evaluation_run_id
    WHERE item.research_assessment_id = NEW.research_assessment_id;

    IF actual_count <> NEW.floor_count
       OR minimum_ordinal <> 1 OR maximum_ordinal <> NEW.floor_count
       OR actual_roster_hash <> NEW.floor_result_roster_sha256
       OR derived_status <> NEW.decision_status
       OR EXISTS (
           (SELECT floor.research_qualification_policy_floor_id
            FROM mra.research_qualification_policy_floor AS floor
            WHERE floor.research_qualification_policy_id =
                  NEW.research_qualification_policy_id)
           EXCEPT
           (SELECT result.research_qualification_policy_floor_id
            FROM mra.research_qualification_floor_result AS result
            WHERE result.research_qualification_decision_id =
                  NEW.research_qualification_decision_id)
       )
       OR EXISTS (
           SELECT 1
           FROM mra.research_qualification_floor_result AS result
           JOIN mra.research_qualification_policy_floor AS floor
             ON floor.research_qualification_policy_floor_id =
                result.research_qualification_policy_floor_id
           WHERE result.research_qualification_decision_id =
                 NEW.research_qualification_decision_id
             AND (result.research_qualification_policy_id <>
                  NEW.research_qualification_policy_id
                  OR result.result_ordinal <> floor.floor_ordinal)
       )
       OR EXISTS (
           SELECT 1
           FROM mra.research_qualification_policy AS policy
           WHERE policy.research_qualification_policy_id =
                 NEW.research_qualification_policy_id
             AND policy.require_preaccess_freeze
             AND first_access_at IS NOT NULL
             AND policy.frozen_at >= first_access_at
       ) THEN
        RAISE EXCEPTION 'ResearchQualificationDecision floor closure is invalid'
            USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION mra.guard_research_partition_overlap()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    PERFORM pg_advisory_xact_lock(
        hashtextextended(
            'research-partition-overlap:' || NEW.target_definition_id::text
            || ':' || NEW.exchange_code,
            0
        )
    );
    IF EXISTS (
        SELECT 1 FROM mra.research_partition AS existing
        WHERE existing.target_definition_id = NEW.target_definition_id
          AND existing.exchange_code = NEW.exchange_code
          AND ((NEW.overlap_policy = 'ISOLATED_PROTECTED'
                AND existing.overlap_policy <> 'DIAGNOSTIC_REUSE')
            OR (existing.overlap_policy = 'ISOLATED_PROTECTED'
                AND NEW.overlap_policy <> 'DIAGNOSTIC_REUSE'))
          AND (existing.population_scope = 'ALL_COMMITMENTS'
               OR NEW.population_scope = 'ALL_COMMITMENTS'
               OR existing.population_scope = NEW.population_scope)
          AND daterange(existing.protected_start_date, existing.protected_end_date, '[]')
              && daterange(NEW.protected_start_date, NEW.protected_end_date, '[]')
    ) THEN
        RAISE EXCEPTION 'protected ResearchPartition overlap is forbidden' USING ERRCODE = '55000';
    END IF;
    IF NEW.overlap_policy = 'PURGED_WALK_FORWARD' AND EXISTS (
        SELECT 1 FROM mra.research_partition AS existing
        WHERE existing.target_definition_id = NEW.target_definition_id
          AND existing.exchange_code = NEW.exchange_code
          AND existing.series_code = NEW.series_code
          AND existing.fold_ordinal = NEW.fold_ordinal
          AND existing.overlap_policy = 'PURGED_WALK_FORWARD'
          AND (existing.population_scope = 'ALL_COMMITMENTS'
               OR NEW.population_scope = 'ALL_COMMITMENTS'
               OR existing.population_scope = NEW.population_scope)
          AND daterange(existing.protected_start_date, existing.protected_end_date, '[]')
              && daterange(NEW.protected_start_date, NEW.protected_end_date, '[]')
    ) THEN
        RAISE EXCEPTION 'same-fold protected range overlap is forbidden' USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION mra.validate_research_partition_member()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    partition_purpose text;
    partition_scope text;
    runtime_requested_at timestamptz;
    runtime_created_at timestamptz;
BEGIN
    SELECT partition.purpose, partition.population_scope
      INTO partition_purpose, partition_scope
    FROM mra.research_partition AS partition
    WHERE partition.research_partition_id = NEW.research_partition_id
      AND partition.xmin::text = pg_current_xact_id()::text;
    IF partition_purpose IS NULL THEN
        RAISE EXCEPTION 'ResearchPartition roster is already frozen' USING ERRCODE = '55000';
    END IF;
    IF partition_scope <> 'ALL_COMMITMENTS' AND partition_scope <> NEW.candidate_disposition THEN
        RAISE EXCEPTION 'Partition member is outside declared population scope' USING ERRCODE = '55000';
    END IF;
    IF partition_purpose = 'PROSPECTIVE' THEN
        IF NEW.commitment_recorded_at >= NEW.earliest_outcome_event_at THEN
            RAISE EXCEPTION 'Prospective commitment must precede earliest Outcome event' USING ERRCODE = '55000';
        END IF;
        IF NEW.runtime_mode IN ('HISTORICAL', 'REPLAY') THEN
            RAISE EXCEPTION 'retrospective commitment cannot be Prospective' USING ERRCODE = '55000';
        END IF;
        SELECT runtime.requested_at, runtime.created_at
          INTO runtime_requested_at, runtime_created_at
        FROM mra.decision_target_commitment AS commitment
        JOIN mra.decision_run AS decision ON decision.decision_run_id = commitment.decision_run_id
        JOIN mra.runtime_run AS runtime ON runtime.run_id = decision.runtime_run_id
        WHERE commitment.commitment_id = NEW.commitment_id;
        IF runtime_requested_at > NEW.decision_time OR runtime_created_at > NEW.decision_time THEN
            RAISE EXCEPTION 'commitment does not satisfy canonical live-clock facts' USING ERRCODE = '55000';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION mra.validate_research_partition_closure()
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
    WHERE commitment.target_definition_id = NEW.target_definition_id
      AND session.exchange = NEW.exchange_code
      AND session.session_date BETWEEN
          NEW.decision_start_date AND NEW.decision_end_date
      AND (NEW.population_scope = 'ALL_COMMITMENTS'
           OR commitment.candidate_disposition = NEW.population_scope);

    SELECT mra.canonical_sha256(
               replace(
                   json_agg(
                       json_build_object(
                           'commitment_id', commitment_id,
                           'content_sha256', content_sha256,
                           'member_ordinal', member_ordinal
                       ) ORDER BY member_ordinal
                   )::text,
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
       OR minimum_ordinal <> 1
       OR maximum_ordinal <> NEW.member_count OR EXISTS (
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
               WHERE commitment.target_definition_id =
                     NEW.target_definition_id
                 AND session.exchange = NEW.exchange_code
                 AND session.session_date BETWEEN
                     NEW.decision_start_date AND NEW.decision_end_date
                 AND (NEW.population_scope = 'ALL_COMMITMENTS'
                      OR commitment.candidate_disposition =
                         NEW.population_scope)
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
               WHERE commitment.target_definition_id =
                     NEW.target_definition_id
                 AND session.exchange = NEW.exchange_code
                 AND session.session_date BETWEEN
                     NEW.decision_start_date AND NEW.decision_end_date
                 AND (NEW.population_scope = 'ALL_COMMITMENTS'
                      OR commitment.candidate_disposition =
                         NEW.population_scope)
           )
       ) THEN
        RAISE EXCEPTION 'ResearchPartition member roster is incomplete or outside declaration' USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION mra.guard_experiment_partition_order()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    partition_frozen_at timestamptz;
    experiment_registered_at timestamptz;
    protected_purpose text;
BEGIN
    SELECT frozen_at, purpose INTO partition_frozen_at, protected_purpose
    FROM mra.research_partition WHERE research_partition_id = NEW.research_partition_id FOR SHARE;
    SELECT registered_at INTO experiment_registered_at
    FROM mra.experiment
    WHERE experiment_id = NEW.experiment_id
      AND xmin::text = pg_current_xact_id()::text
    FOR SHARE;
    IF experiment_registered_at IS NULL THEN
        RAISE EXCEPTION 'Experiment Partition roster is already frozen'
            USING ERRCODE = '55000';
    END IF;
    IF NOT (partition_frozen_at < experiment_registered_at AND experiment_registered_at <= NEW.bound_at) THEN
        RAISE EXCEPTION 'Partition must precede Experiment registration and binding' USING ERRCODE = '55000';
    END IF;
    IF EXISTS (
        SELECT 1 FROM mra.experiment_run
        WHERE experiment_id = NEW.experiment_id
    ) THEN
        RAISE EXCEPTION 'ExperimentPartition cannot be bound after an ExperimentRun opens' USING ERRCODE = '55000';
    END IF;
    IF protected_purpose IN ('LOCKED_OOS', 'PROSPECTIVE') AND EXISTS (
        SELECT 1 FROM mra.research_partition_outcome_access AS access
        JOIN mra.research_partition_member AS member
          ON member.research_partition_member_id = access.research_partition_member_id
        WHERE member.research_partition_id = NEW.research_partition_id
    ) THEN
        RAISE EXCEPTION 'protected Partition was already accessed' USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION mra.validate_experiment_partition_closure()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE actual_count integer;
DECLARE minimum_ordinal integer;
DECLARE maximum_ordinal integer;
DECLARE actual_roster_hash text;
DECLARE actual_content_hash text;
BEGIN
    SELECT count(*), min(binding_ordinal), max(binding_ordinal),
           mra.canonical_sha256(
               replace(
                   json_agg(
                       json_build_object(
                           'binding_ordinal', binding_ordinal,
                           'content_sha256', content_sha256,
                           'experiment_partition_id', experiment_partition_id,
                           'research_partition_id', research_partition_id
                       ) ORDER BY binding_ordinal
                   )::text,
                   ' ',
                   ''
               )
           )
      INTO actual_count, minimum_ordinal, maximum_ordinal,
           actual_roster_hash
    FROM mra.experiment_partition
    WHERE experiment_id = NEW.experiment_id;

    actual_content_hash := mra.canonical_sha256(
        replace(
            json_build_object(
                'definition_sha256', NEW.definition_sha256,
                'partition_count', NEW.partition_count,
                'partition_roster_sha256', NEW.partition_roster_sha256
            )::text,
            ' ',
            ''
        )
    );

    IF actual_count <> NEW.partition_count
       OR minimum_ordinal <> 1
       OR maximum_ordinal <> NEW.partition_count
       OR actual_roster_hash <> NEW.partition_roster_sha256
       OR actual_content_hash <> NEW.content_sha256
       OR EXISTS (
           SELECT 1
           FROM mra.experiment_partition AS binding
           WHERE binding.experiment_id = NEW.experiment_id
             AND binding.content_sha256 <> mra.canonical_sha256(
                 replace(
                     json_build_object(
                         'binding_ordinal', binding.binding_ordinal,
                         'experiment_id', binding.experiment_id,
                         'experiment_partition_id',
                             binding.experiment_partition_id,
                         'partition_content_sha256',
                             binding.partition_content_sha256,
                         'partition_purpose', binding.partition_purpose,
                         'research_partition_id',
                             binding.research_partition_id,
                         'target_definition_id',
                             binding.target_definition_id,
                         'target_definition_sha256',
                             binding.target_definition_sha256,
                         'target_version', binding.target_version
                     )::text,
                     ' ',
                     ''
                 )
             )
       ) THEN
        RAISE EXCEPTION 'Experiment Partition roster is incomplete or mismatched'
            USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION mra.guard_open_evaluation_protocol_metric()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM mra.evaluation_protocol
        WHERE evaluation_protocol_id = NEW.evaluation_protocol_id
    ) THEN
        RAISE EXCEPTION 'EvaluationProtocol is already frozen' USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION mra.validate_evaluation_protocol_closure()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE actual_count integer;
DECLARE minimum_ordinal integer;
DECLARE maximum_ordinal integer;
BEGIN
    SELECT count(*), min(ordinal), max(ordinal)
      INTO actual_count, minimum_ordinal, maximum_ordinal
    FROM mra.evaluation_protocol_metric
    WHERE evaluation_protocol_id = NEW.evaluation_protocol_id;
    IF actual_count <> NEW.metric_count OR minimum_ordinal <> 1
       OR maximum_ordinal <> NEW.metric_count THEN
        RAISE EXCEPTION 'EvaluationProtocol metric roster is incomplete' USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION mra.guard_experiment_run_order()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE registration_time timestamptz;
DECLARE protected_purpose text;
BEGIN
    SELECT registered_at INTO registration_time FROM mra.experiment
    WHERE experiment_id = NEW.experiment_id FOR SHARE;
    IF registration_time >= NEW.opened_at THEN
        RAISE EXCEPTION 'Experiment registration must precede ExperimentRun' USING ERRCODE = '55000';
    END IF;
    SELECT partition_purpose INTO protected_purpose
    FROM mra.experiment_partition
    WHERE experiment_partition_id = NEW.experiment_partition_id;
    IF protected_purpose IN ('LOCKED_OOS', 'PROSPECTIVE') AND EXISTS (
        SELECT 1 FROM mra.research_partition_outcome_access AS access
        JOIN mra.research_partition_member AS member
          ON member.research_partition_member_id = access.research_partition_member_id
        WHERE member.research_partition_id = NEW.research_partition_id
    ) THEN
        RAISE EXCEPTION 'protected ExperimentRun must open before first Outcome access' USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION mra.guard_evaluation_run_open()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE experiment_opened_at timestamptz;
DECLARE protocol_frozen_at timestamptz;
BEGIN
    SELECT opened_at INTO experiment_opened_at FROM mra.experiment_run
    WHERE experiment_run_id = NEW.experiment_run_id FOR SHARE;
    SELECT frozen_at INTO protocol_frozen_at FROM mra.evaluation_protocol
    WHERE evaluation_protocol_id = NEW.evaluation_protocol_id FOR SHARE;
    IF NEW.requested_knowledge_cutoff > NEW.opened_at THEN
        RAISE EXCEPTION 'EvaluationRun knowledge cutoff cannot be in the future'
            USING ERRCODE = '55000';
    END IF;
    IF experiment_opened_at >= NEW.opened_at OR protocol_frozen_at >= NEW.opened_at THEN
        RAISE EXCEPTION 'ExperimentRun and Protocol must precede EvaluationRun' USING ERRCODE = '55000';
    END IF;
    IF NEW.partition_purpose IN ('LOCKED_OOS', 'PROSPECTIVE') THEN
        PERFORM pg_advisory_xact_lock(
            hashtextextended(
                'research-protected-access:' || NEW.research_partition_id::text,
                0
            )
        );
        IF EXISTS (
            SELECT 1
            FROM mra.research_partition_outcome_access AS access
            JOIN mra.research_partition_member AS member
              ON member.research_partition_member_id =
                 access.research_partition_member_id
            WHERE member.research_partition_id = NEW.research_partition_id
        ) THEN
            RAISE EXCEPTION 'protected EvaluationRun requires zero prior Partition access' USING ERRCODE = '55000';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION mra.guard_evaluation_run_transition()
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
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION mra.guard_evaluation_observation_insert()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM mra.evaluation_run
        WHERE evaluation_run_id = NEW.evaluation_run_id AND status = 'OPEN'
    ) THEN
        RAISE EXCEPTION 'EvaluationObservation requires OPEN acquisition transaction' USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION mra.guard_evaluation_metric_insert()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM mra.evaluation_run
        WHERE evaluation_run_id = NEW.evaluation_run_id
          AND status = 'INPUTS_ACQUIRED'
    ) THEN
        RAISE EXCEPTION 'EvaluationMetric requires INPUTS_ACQUIRED run' USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION mra.guard_research_outcome_access()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE run_status text;
DECLARE run_opened_at timestamptz;
DECLARE cutoff timestamptz;
DECLARE partition_id uuid;
DECLARE partition_purpose text;
DECLARE expected_ordinal integer;
DECLARE visible_leaf_count integer;
BEGIN
    PERFORM 1
    FROM mra.market_target_outcome AS root
    WHERE root.market_target_outcome_id = NEW.market_target_outcome_id
      AND root.commitment_id = NEW.commitment_id
      AND root.target_definition_id = NEW.target_definition_id
    FOR SHARE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Outcome access root is absent or mismatched'
            USING ERRCODE = '23503';
    END IF;
    SELECT status, opened_at, requested_knowledge_cutoff,
           research_partition_id, evaluation_run.partition_purpose
      INTO run_status, run_opened_at, cutoff,
           partition_id, partition_purpose
    FROM mra.evaluation_run WHERE evaluation_run_id = NEW.evaluation_run_id FOR UPDATE;
    IF run_status <> 'OPEN' THEN
        RAISE EXCEPTION 'Outcome acquisition requires EvaluationRun OPEN' USING ERRCODE = '55000';
    END IF;
    IF cutoff > NEW.accessed_at
       OR NEW.accessed_at <= run_opened_at OR NEW.knowledge_cutoff > cutoff
       OR NEW.observation_cutoff > cutoff OR NEW.settled_at > cutoff THEN
        RAISE EXCEPTION 'Outcome access ordering/cutoff is invalid' USING ERRCODE = '55000';
    END IF;
    IF partition_purpose IN ('LOCKED_OOS', 'PROSPECTIVE') THEN
        PERFORM pg_advisory_xact_lock(
            hashtextextended(
                'research-protected-access:' || partition_id::text,
                0
            )
        );
    END IF;
    SELECT coalesce(max(access_ordinal), 0) + 1 INTO expected_ordinal
    FROM mra.research_partition_outcome_access
    WHERE research_partition_member_id = NEW.research_partition_member_id;
    IF NEW.access_ordinal <> expected_ordinal THEN
        RAISE EXCEPTION 'Outcome access ordinal is not globally sequential for member' USING ERRCODE = '55000';
    END IF;
    IF partition_purpose IN ('LOCKED_OOS', 'PROSPECTIVE')
       AND expected_ordinal <> 1 THEN
        RAISE EXCEPTION 'protected Outcome access must remain first access' USING ERRCODE = '55000';
    END IF;

    SELECT count(*) INTO visible_leaf_count
    FROM mra.market_target_outcome_revision AS candidate
    WHERE candidate.commitment_id = NEW.commitment_id
      AND candidate.target_definition_id = NEW.target_definition_id
      AND candidate.observation_cutoff <= cutoff
      AND candidate.knowledge_cutoff <= cutoff
      AND candidate.settled_at <= cutoff
      AND NOT EXISTS (
          SELECT 1
          FROM mra.market_target_outcome_revision AS successor
          WHERE successor.supersedes_revision_id =
                candidate.market_target_outcome_revision_id
            AND successor.commitment_id = NEW.commitment_id
            AND successor.target_definition_id = NEW.target_definition_id
            AND successor.observation_cutoff <= cutoff
            AND successor.knowledge_cutoff <= cutoff
            AND successor.settled_at <= cutoff
      );
    IF visible_leaf_count <> 1 OR NOT EXISTS (
        SELECT 1
        FROM mra.market_target_outcome_revision AS candidate
        WHERE candidate.market_target_outcome_revision_id =
              NEW.market_target_outcome_revision_id
          AND candidate.commitment_id = NEW.commitment_id
          AND candidate.target_definition_id = NEW.target_definition_id
          AND candidate.observation_cutoff <= cutoff
          AND candidate.knowledge_cutoff <= cutoff
          AND candidate.settled_at <= cutoff
          AND NOT EXISTS (
              SELECT 1
              FROM mra.market_target_outcome_revision AS successor
              WHERE successor.supersedes_revision_id =
                    candidate.market_target_outcome_revision_id
                AND successor.commitment_id = NEW.commitment_id
                AND successor.target_definition_id = NEW.target_definition_id
                AND successor.observation_cutoff <= cutoff
                AND successor.knowledge_cutoff <= cutoff
                AND successor.settled_at <= cutoff
          )
    ) THEN
        RAISE EXCEPTION 'Outcome access revision is not the unique visible leaf' USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER research_partition_overlap_guard
BEFORE INSERT ON mra.research_partition
FOR EACH ROW EXECUTE FUNCTION mra.guard_research_partition_overlap();
CREATE TRIGGER research_partition_append_only
BEFORE UPDATE OR DELETE ON mra.research_partition
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE CONSTRAINT TRIGGER research_partition_closure_guard
AFTER INSERT ON mra.research_partition
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION mra.validate_research_partition_closure();
CREATE TRIGGER research_partition_member_validate
BEFORE INSERT ON mra.research_partition_member
FOR EACH ROW EXECUTE FUNCTION mra.validate_research_partition_member();
CREATE TRIGGER research_partition_member_append_only
BEFORE UPDATE OR DELETE ON mra.research_partition_member
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER experiment_append_only
BEFORE UPDATE OR DELETE ON mra.experiment
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE CONSTRAINT TRIGGER experiment_partition_closure_guard
AFTER INSERT ON mra.experiment
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION mra.validate_experiment_partition_closure();
CREATE TRIGGER experiment_partition_order_guard
BEFORE INSERT ON mra.experiment_partition
FOR EACH ROW EXECUTE FUNCTION mra.guard_experiment_partition_order();
CREATE TRIGGER experiment_partition_append_only
BEFORE UPDATE OR DELETE ON mra.experiment_partition
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER experiment_run_order_guard
BEFORE INSERT ON mra.experiment_run
FOR EACH ROW EXECUTE FUNCTION mra.guard_experiment_run_order();
CREATE TRIGGER experiment_run_append_only
BEFORE UPDATE OR DELETE ON mra.experiment_run
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER evaluation_protocol_append_only
BEFORE UPDATE OR DELETE ON mra.evaluation_protocol
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER evaluation_protocol_closure_guard
BEFORE INSERT ON mra.evaluation_protocol
FOR EACH ROW EXECUTE FUNCTION mra.validate_evaluation_protocol_closure();
CREATE TRIGGER evaluation_protocol_metric_append_only
BEFORE UPDATE OR DELETE ON mra.evaluation_protocol_metric
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER evaluation_protocol_metric_open_guard
BEFORE INSERT ON mra.evaluation_protocol_metric
FOR EACH ROW EXECUTE FUNCTION mra.guard_open_evaluation_protocol_metric();
CREATE TRIGGER evaluation_run_open_guard
BEFORE INSERT ON mra.evaluation_run
FOR EACH ROW EXECUTE FUNCTION mra.guard_evaluation_run_open();
CREATE TRIGGER evaluation_run_transition_guard
BEFORE UPDATE OR DELETE ON mra.evaluation_run
FOR EACH ROW EXECUTE FUNCTION mra.guard_evaluation_run_transition();
CREATE TRIGGER research_outcome_access_guard
BEFORE INSERT ON mra.research_partition_outcome_access
FOR EACH ROW EXECUTE FUNCTION mra.guard_research_outcome_access();
CREATE TRIGGER research_outcome_access_append_only
BEFORE UPDATE OR DELETE ON mra.research_partition_outcome_access
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER evaluation_observation_append_only
BEFORE UPDATE OR DELETE ON mra.evaluation_observation
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER evaluation_observation_insert_guard
BEFORE INSERT ON mra.evaluation_observation
FOR EACH ROW EXECUTE FUNCTION mra.guard_evaluation_observation_insert();
CREATE TRIGGER evaluation_metric_append_only
BEFORE UPDATE OR DELETE ON mra.evaluation_metric
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER evaluation_metric_insert_guard
BEFORE INSERT ON mra.evaluation_metric
FOR EACH ROW EXECUTE FUNCTION mra.guard_evaluation_metric_insert();
CREATE TRIGGER evaluation_metric_observation_append_only
BEFORE UPDATE OR DELETE ON mra.evaluation_metric_observation
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER evaluation_metric_observation_insert_guard
BEFORE INSERT ON mra.evaluation_metric_observation
FOR EACH ROW EXECUTE FUNCTION mra.guard_evaluation_metric_insert();

CREATE TRIGGER evidence_item_append_only
BEFORE UPDATE OR DELETE ON mra.evidence_item
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE CONSTRAINT TRIGGER evidence_item_closure_guard
AFTER INSERT ON mra.evidence_item
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION mra.validate_evidence_item_closure();
CREATE TRIGGER evidence_dependency_insert_guard
BEFORE INSERT ON mra.evidence_dependency
FOR EACH ROW EXECUTE FUNCTION mra.guard_evidence_dependency_insert();
CREATE TRIGGER evidence_dependency_append_only
BEFORE UPDATE OR DELETE ON mra.evidence_dependency
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();

CREATE TRIGGER research_assessment_insert_guard
BEFORE INSERT ON mra.research_assessment
FOR EACH ROW EXECUTE FUNCTION mra.guard_research_assessment_insert();
CREATE TRIGGER research_assessment_append_only
BEFORE UPDATE OR DELETE ON mra.research_assessment
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE CONSTRAINT TRIGGER research_assessment_closure_guard
AFTER INSERT ON mra.research_assessment
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION mra.validate_research_assessment_closure();
CREATE TRIGGER research_assessment_evaluation_insert_guard
BEFORE INSERT ON mra.research_assessment_evaluation
FOR EACH ROW EXECUTE FUNCTION mra.guard_research_assessment_child_insert();
CREATE TRIGGER research_assessment_evaluation_append_only
BEFORE UPDATE OR DELETE ON mra.research_assessment_evaluation
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER research_assessment_evidence_insert_guard
BEFORE INSERT ON mra.research_assessment_evidence
FOR EACH ROW EXECUTE FUNCTION mra.guard_research_assessment_child_insert();
CREATE TRIGGER research_assessment_evidence_append_only
BEFORE UPDATE OR DELETE ON mra.research_assessment_evidence
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();

CREATE TRIGGER research_qualification_policy_append_only
BEFORE UPDATE OR DELETE ON mra.research_qualification_policy
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE CONSTRAINT TRIGGER research_qualification_policy_closure_guard
AFTER INSERT ON mra.research_qualification_policy
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION mra.validate_research_qualification_policy_closure();
CREATE TRIGGER research_qualification_policy_floor_insert_guard
BEFORE INSERT ON mra.research_qualification_policy_floor
FOR EACH ROW EXECUTE FUNCTION mra.guard_research_qualification_policy_floor_insert();
CREATE TRIGGER research_qualification_policy_floor_append_only
BEFORE UPDATE OR DELETE ON mra.research_qualification_policy_floor
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();

CREATE TRIGGER research_qualification_decision_insert_guard
BEFORE INSERT ON mra.research_qualification_decision
FOR EACH ROW EXECUTE FUNCTION mra.guard_research_qualification_decision_insert();
CREATE TRIGGER research_qualification_decision_append_only
BEFORE UPDATE OR DELETE ON mra.research_qualification_decision
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE CONSTRAINT TRIGGER research_qualification_decision_closure_guard
AFTER INSERT ON mra.research_qualification_decision
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION mra.validate_research_qualification_decision_closure();
CREATE TRIGGER research_qualification_floor_result_insert_guard
BEFORE INSERT ON mra.research_qualification_floor_result
FOR EACH ROW EXECUTE FUNCTION mra.guard_research_qualification_child_insert();
CREATE TRIGGER research_qualification_floor_result_append_only
BEFORE UPDATE OR DELETE ON mra.research_qualification_floor_result
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER research_qualification_floor_evidence_insert_guard
BEFORE INSERT ON mra.research_qualification_floor_evidence
FOR EACH ROW EXECUTE FUNCTION mra.guard_research_qualification_child_insert();
CREATE TRIGGER research_qualification_floor_evidence_append_only
BEFORE UPDATE OR DELETE ON mra.research_qualification_floor_evidence
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
