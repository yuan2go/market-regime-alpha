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

CREATE FUNCTION mra.artifact_is_authoritatively_readable(
    integrity_state text,
    last_verified_at timestamptz
)
RETURNS boolean
LANGUAGE sql
STABLE
PARALLEL SAFE
AS $$
    SELECT integrity_state = 'AVAILABLE'
       AND last_verified_at IS NOT NULL
       AND last_verified_at >= transaction_timestamp() - interval '24 hours';
$$;

COMMENT ON FUNCTION mra.artifact_is_authoritatively_readable(text, timestamptz) IS
    'WP-04 authoritative-read policy: AVAILABLE plus physical hash/size verification within 24 hours';

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
      AND mra.artifact_is_authoritatively_readable(
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
                OR NOT mra.artifact_is_authoritatively_readable(
                    evidence_capture.artifact_integrity_state,
                    evidence_capture.artifact_last_verified_at
                )
            ))
       ) THEN
        RAISE EXCEPTION 'SourceGap kind is incompatible with its Capture evidence' USING ERRCODE = '55000';
    ELSIF TG_TABLE_NAME <> 'source_gap'
       AND (
           evidence_capture.status <> 'CAPTURED'
           OR NOT mra.artifact_is_authoritatively_readable(
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
        IF NOT FOUND OR NOT mra.artifact_is_authoritatively_readable(
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
    CONSTRAINT runtime_step_kind_ck CHECK (step_kind IN ('CAPTURE', 'NORMALIZE_PIT', 'FREEZE_UNIVERSE', 'ASSESS_ELIGIBILITY', 'BUILD_CANDIDATES', 'ASSESS_CONTEXT', 'SIGNAL_AND_FORECAST', 'DECIDE_AND_RISK', 'PERSIST_DECISION', 'SETTLE_OUTCOME', 'ATTRIBUTE', 'ASSESS_RESEARCH')),
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
