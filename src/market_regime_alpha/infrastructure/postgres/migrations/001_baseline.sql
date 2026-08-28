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
    SELECT payload_encoding, source_availability_policy
    INTO product_row
    FROM mra.provider_product
    WHERE provider_product_id = NEW.provider_product_id
    FOR SHARE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Capture ProviderProduct does not exist' USING ERRCODE = '23503';
    END IF;
    IF product_row.source_availability_policy <> NEW.source_availability_status THEN
        RAISE EXCEPTION 'Capture availability semantics differ from ProviderProduct' USING ERRCODE = '55000';
    END IF;
    IF NEW.status = 'CAPTURED' THEN
        SELECT integrity_state INTO artifact_row
        FROM mra.artifact
        WHERE artifact_id = NEW.artifact_id
        FOR SHARE;
        IF NOT FOUND OR artifact_row.integrity_state <> 'AVAILABLE' THEN
            RAISE EXCEPTION 'Capture requires an AVAILABLE exact Artifact' USING ERRCODE = '55000';
        END IF;
        IF NEW.payload_encoding <> product_row.payload_encoding THEN
            RAISE EXCEPTION 'Capture encoding differs from ProviderProduct' USING ERRCODE = '55000';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION mra.validate_instrument_identifier_insert()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    PERFORM pg_advisory_xact_lock(
        hashtextextended('mra:instrument-identifier:' || NEW.identifier_scheme, 0)
    );
    IF EXISTS (
        SELECT 1
        FROM mra.instrument_identifier AS existing
        WHERE existing.identifier_scheme = NEW.identifier_scheme
          AND (
              (existing.identifier_value = NEW.identifier_value
               AND existing.instrument_id <> NEW.instrument_id)
              OR
              (existing.instrument_id = NEW.instrument_id
               AND existing.identifier_value <> NEW.identifier_value)
          )
          AND existing.effective_from < COALESCE(NEW.effective_to, 'infinity'::timestamptz)
          AND NEW.effective_from < COALESCE(existing.effective_to, 'infinity'::timestamptz)
    ) THEN
        RAISE EXCEPTION 'InstrumentIdentifier effective interval overlaps another Authority mapping' USING ERRCODE = '23P01';
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
              AND prior.revision = NEW.revision - 1
        ) INTO valid;
    ELSIF TG_TABLE_NAME = 'classification' THEN
        SELECT EXISTS (
            SELECT 1 FROM mra.classification AS prior
            WHERE prior.classification_id = NEW.supersedes_classification_id
              AND prior.classification_scheme = NEW.classification_scheme
              AND prior.classification_code = NEW.classification_code
              AND prior.revision = NEW.revision - 1
        ) INTO valid;
    ELSIF TG_TABLE_NAME = 'classification_membership_revision' THEN
        SELECT EXISTS (
            SELECT 1 FROM mra.classification_membership_revision AS prior
            WHERE prior.membership_revision_id = NEW.supersedes_membership_revision_id
              AND prior.classification_id = NEW.classification_id
              AND prior.instrument_id = NEW.instrument_id
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
              AND prior.adjustment_basis = NEW.adjustment_basis
              AND prior.event_start = NEW.event_start
              AND prior.event_end = NEW.event_end
              AND prior.revision = NEW.revision - 1
        ) INTO valid;
    ELSIF TG_TABLE_NAME = 'instrument_fact_revision' THEN
        SELECT EXISTS (
            SELECT 1 FROM mra.instrument_fact_revision AS prior
            WHERE prior.fact_revision_id = NEW.supersedes_revision_id
              AND prior.provider_product_id = NEW.provider_product_id
              AND prior.instrument_id = NEW.instrument_id
              AND prior.fact_kind = NEW.fact_kind
              AND prior.evidence_scope = NEW.evidence_scope
              AND prior.event_start = NEW.event_start
              AND prior.event_end = NEW.event_end
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

CREATE FUNCTION mra.reject_bar_gap_duality()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    conflict_exists boolean;
BEGIN
    IF TG_TABLE_NAME = 'market_bar_revision' THEN
        SELECT EXISTS (
            SELECT 1 FROM mra.source_gap AS gap
            WHERE gap.capture_id = NEW.capture_id
              AND gap.instrument_id = NEW.instrument_id
              AND gap.session_id = NEW.session_id
              AND gap.fact_kind = 'MARKET_BAR'
              AND gap.timeframe = NEW.timeframe
              AND gap.adjustment_basis = NEW.adjustment_basis
              AND gap.event_start = NEW.event_start
              AND gap.event_end = NEW.event_end
        ) INTO conflict_exists;
    ELSE
        SELECT NEW.fact_kind = 'MARKET_BAR' AND EXISTS (
            SELECT 1 FROM mra.market_bar_revision AS bar
            WHERE bar.capture_id = NEW.capture_id
              AND bar.instrument_id = NEW.instrument_id
              AND bar.session_id = NEW.session_id
              AND bar.timeframe = NEW.timeframe
              AND bar.adjustment_basis = NEW.adjustment_basis
              AND bar.event_start = NEW.event_start
              AND bar.event_end = NEW.event_end
        ) INTO conflict_exists;
    END IF;
    IF conflict_exists THEN
        RAISE EXCEPTION 'one Capture cannot assert both a valid MarketBar and a SourceGap' USING ERRCODE = '55000';
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
    CONSTRAINT artifact_verification_result_ck CHECK (result IN ('VERIFIED', 'MISSING', 'SIZE_MISMATCH', 'HASH_MISMATCH')),
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
    authority_ceiling text NOT NULL DEFAULT 'EXPLORATORY_UNQUALIFIED',
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT provider_code_ck CHECK (provider_code ~ '^[a-z][a-z0-9_-]{0,99}$'),
    CONSTRAINT provider_name_ck CHECK (display_name <> ''),
    CONSTRAINT provider_kind_ck CHECK (provider_kind IN ('PUBLIC_ENDPOINT', 'DATA_VENDOR', 'BROKER_FEED')),
    CONSTRAINT provider_authority_ceiling_ck CHECK (authority_ceiling = 'EXPLORATORY_UNQUALIFIED')
);

CREATE TABLE mra.provider_product (
    provider_product_id uuid PRIMARY KEY,
    provider_id uuid NOT NULL REFERENCES mra.provider(provider_id) ON DELETE RESTRICT,
    product_code text NOT NULL,
    revision integer NOT NULL,
    payload_family text NOT NULL,
    media_type text NOT NULL,
    payload_encoding text NOT NULL,
    decision_visibility_policy text NOT NULL DEFAULT 'KNOWN_AT',
    source_availability_policy text NOT NULL,
    contract_sha256 text NOT NULL,
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
    CONSTRAINT provider_product_visibility_ck CHECK (decision_visibility_policy = 'KNOWN_AT'),
    CONSTRAINT provider_product_availability_ck CHECK (source_availability_policy IN ('UNKNOWN', 'PROVIDER_REPORTED')),
    CONSTRAINT provider_product_contract_hash_ck CHECK (contract_sha256 ~ '^[0-9a-f]{64}$'),
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
    CONSTRAINT data_capture_identity_uk UNIQUE (provider_product_id, capture_key),
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
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT instrument_code_ck CHECK (canonical_code ~ '^[A-Z0-9][A-Z0-9._-]{0,31}$'),
    CONSTRAINT instrument_exchange_ck CHECK (exchange ~ '^[A-Z][A-Z0-9]{1,15}$'),
    CONSTRAINT instrument_type_ck CHECK (instrument_type IN ('EQUITY', 'ETF', 'INDEX', 'FUND', 'BOND')),
    CONSTRAINT instrument_currency_ck CHECK (currency ~ '^[A-Z]{3}$')
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
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
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
    CONSTRAINT instrument_identifier_no_self_ck CHECK (supersedes_identifier_id IS NULL OR supersedes_identifier_id <> instrument_identifier_id)
);
CREATE INDEX instrument_identifier_instrument_idx
    ON mra.instrument_identifier (instrument_id, identifier_scheme, effective_from DESC);
CREATE INDEX instrument_identifier_capture_idx ON mra.instrument_identifier (source_capture_id);
CREATE INDEX instrument_identifier_supersedes_idx ON mra.instrument_identifier (supersedes_identifier_id)
    WHERE supersedes_identifier_id IS NOT NULL;
CREATE INDEX instrument_identifier_asof_idx
    ON mra.instrument_identifier (identifier_scheme, identifier_value, effective_from DESC, effective_to);

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
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT trading_session_identity_uk UNIQUE (exchange, session_date),
    CONSTRAINT trading_session_exchange_ck CHECK (exchange ~ '^[A-Z][A-Z0-9]{1,15}$'),
    CONSTRAINT trading_session_timezone_ck CHECK (timezone_name <> ''),
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
    )
);
CREATE INDEX trading_session_capture_idx ON mra.trading_session (source_capture_id);
CREATE INDEX trading_session_calendar_idx ON mra.trading_session (exchange, session_date, session_id);

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
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT classification_identity_uk UNIQUE (classification_scheme, classification_code, revision),
    CONSTRAINT classification_scheme_ck CHECK (classification_scheme ~ '^[A-Z][A-Z0-9_]{0,31}$'),
    CONSTRAINT classification_code_ck CHECK (classification_code <> ''),
    CONSTRAINT classification_name_ck CHECK (display_name <> ''),
    CONSTRAINT classification_revision_ck CHECK (revision > 0),
    CONSTRAINT classification_interval_ck CHECK (effective_to IS NULL OR effective_to > effective_from),
    CONSTRAINT classification_revision_chain_ck CHECK (
        (revision = 1 AND supersedes_classification_id IS NULL) OR
        (revision > 1 AND supersedes_classification_id IS NOT NULL)
    ),
    CONSTRAINT classification_no_self_ck CHECK (supersedes_classification_id IS NULL OR supersedes_classification_id <> classification_id)
);
CREATE INDEX classification_capture_idx ON mra.classification (source_capture_id);
CREATE INDEX classification_supersedes_idx ON mra.classification (supersedes_classification_id)
    WHERE supersedes_classification_id IS NOT NULL;
CREATE INDEX classification_asof_idx
    ON mra.classification (classification_scheme, classification_code, effective_from DESC, effective_to, revision DESC);

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
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT classification_membership_identity_uk UNIQUE (classification_id, instrument_id, effective_from, revision),
    CONSTRAINT classification_membership_status_ck CHECK (membership_status IN ('MEMBER', 'NOT_MEMBER')),
    CONSTRAINT classification_membership_interval_ck CHECK (effective_to IS NULL OR effective_to > effective_from),
    CONSTRAINT classification_membership_revision_ck CHECK (revision > 0),
    CONSTRAINT classification_membership_revision_chain_ck CHECK (
        (revision = 1 AND supersedes_membership_revision_id IS NULL) OR
        (revision > 1 AND supersedes_membership_revision_id IS NOT NULL)
    ),
    CONSTRAINT classification_membership_no_self_ck CHECK (supersedes_membership_revision_id IS NULL OR supersedes_membership_revision_id <> membership_revision_id)
);
CREATE INDEX classification_membership_classification_idx
    ON mra.classification_membership_revision (classification_id, instrument_id, effective_from DESC, revision DESC);
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
    adjustment_basis text NOT NULL,
    event_start timestamptz NOT NULL,
    event_end timestamptz NOT NULL,
    revision integer NOT NULL,
    supersedes_revision_id uuid REFERENCES mra.market_bar_revision(bar_revision_id) ON DELETE RESTRICT,
    open_value numeric(30, 10) NOT NULL,
    high_value numeric(30, 10) NOT NULL,
    low_value numeric(30, 10) NOT NULL,
    close_value numeric(30, 10) NOT NULL,
    volume_value numeric(38, 10) NOT NULL,
    turnover_value numeric(38, 10),
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT market_bar_revision_identity_uk UNIQUE (
        provider_product_id, instrument_id, session_id, timeframe,
        adjustment_basis, event_start, event_end, revision
    ),
    CONSTRAINT market_bar_timeframe_ck CHECK (timeframe IN ('MINUTE_1', 'MINUTE_5', 'MINUTE_15', 'MINUTE_30', 'MINUTE_60', 'DAILY')),
    CONSTRAINT market_bar_basis_ck CHECK (adjustment_basis IN ('RAW_UNADJUSTED', 'FORWARD_ADJUSTED', 'BACKWARD_ADJUSTED')),
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
    CONSTRAINT market_bar_volume_ck CHECK (volume_value >= 0 AND (turnover_value IS NULL OR turnover_value >= 0))
);
CREATE INDEX market_bar_exact_asof_idx ON mra.market_bar_revision (
    provider_product_id, instrument_id, session_id, timeframe,
    adjustment_basis, event_end, event_start, revision DESC, capture_id
);
CREATE INDEX market_bar_capture_idx ON mra.market_bar_revision (capture_id);
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
    event_end timestamptz NOT NULL,
    value_kind text NOT NULL,
    status_value text,
    numeric_value numeric(38, 10),
    text_value text,
    unit_code text,
    revision integer NOT NULL,
    supersedes_revision_id uuid REFERENCES mra.instrument_fact_revision(fact_revision_id) ON DELETE RESTRICT,
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT instrument_fact_identity_uk UNIQUE (
        provider_product_id, instrument_id, fact_kind, evidence_scope,
        event_start, event_end, revision
    ),
    CONSTRAINT instrument_fact_kind_ck CHECK (fact_kind ~ '^[A-Z][A-Z0-9_]{0,99}$'),
    CONSTRAINT instrument_fact_scope_ck CHECK (evidence_scope IN ('DECISION_SESSION', 'PRIOR_SESSION', 'EFFECTIVE_INTERVAL')),
    CONSTRAINT instrument_fact_interval_ck CHECK (event_end > event_start),
    CONSTRAINT instrument_fact_value_kind_ck CHECK (value_kind IN ('STATUS', 'DECIMAL', 'TEXT')),
    CONSTRAINT instrument_fact_value_ck CHECK (
        (value_kind = 'STATUS' AND status_value IS NOT NULL AND numeric_value IS NULL AND text_value IS NULL) OR
        (value_kind = 'DECIMAL' AND status_value IS NULL AND numeric_value IS NOT NULL AND text_value IS NULL) OR
        (value_kind = 'TEXT' AND status_value IS NULL AND numeric_value IS NULL AND text_value IS NOT NULL)
    ),
    CONSTRAINT instrument_fact_security_status_ck CHECK (
        fact_kind <> 'SECURITY_STATUS' OR
        (value_kind = 'STATUS' AND status_value IN ('ACTIVE', 'SUSPENDED', 'UNKNOWN') AND session_id IS NOT NULL)
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
    CONSTRAINT instrument_fact_no_self_ck CHECK (supersedes_revision_id IS NULL OR supersedes_revision_id <> fact_revision_id)
);
CREATE INDEX instrument_fact_exact_asof_idx ON mra.instrument_fact_revision (
    provider_product_id, instrument_id, fact_kind, evidence_scope,
    session_id, event_end, revision DESC, capture_id
);
CREATE INDEX instrument_fact_capture_idx ON mra.instrument_fact_revision (capture_id);
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
    payable_at timestamptz,
    cash_amount numeric(30, 10),
    ratio_factor numeric(30, 12),
    currency text,
    revision integer NOT NULL,
    supersedes_revision_id uuid REFERENCES mra.corporate_action_revision(corporate_action_revision_id) ON DELETE RESTRICT,
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT corporate_action_identity_uk UNIQUE (provider_product_id, instrument_id, action_key, revision),
    CONSTRAINT corporate_action_key_ck CHECK (action_key <> ''),
    CONSTRAINT corporate_action_type_ck CHECK (action_type IN ('CASH_DIVIDEND', 'STOCK_DIVIDEND', 'SPLIT', 'RIGHTS_ISSUE', 'MERGER', 'DELISTING')),
    CONSTRAINT corporate_action_value_ck CHECK (
        (cash_amount IS NULL OR cash_amount >= 0)
        AND (ratio_factor IS NULL OR ratio_factor > 0)
        AND (currency IS NULL OR currency ~ '^[A-Z]{3}$')
        AND (cash_amount IS NULL OR currency IS NOT NULL)
        AND (cash_amount IS NOT NULL OR ratio_factor IS NOT NULL OR action_type IN ('MERGER', 'DELISTING'))
    ),
    CONSTRAINT corporate_action_revision_ck CHECK (revision > 0),
    CONSTRAINT corporate_action_revision_chain_ck CHECK (
        (revision = 1 AND supersedes_revision_id IS NULL) OR
        (revision > 1 AND supersedes_revision_id IS NOT NULL)
    ),
    CONSTRAINT corporate_action_no_self_ck CHECK (supersedes_revision_id IS NULL OR supersedes_revision_id <> corporate_action_revision_id)
);
CREATE INDEX corporate_action_exact_asof_idx
    ON mra.corporate_action_revision (provider_product_id, instrument_id, ex_session_id, action_key, revision DESC, capture_id);
CREATE INDEX corporate_action_capture_idx ON mra.corporate_action_revision (capture_id);
CREATE INDEX corporate_action_instrument_idx ON mra.corporate_action_revision (instrument_id, ex_session_id, action_key);
CREATE INDEX corporate_action_session_idx ON mra.corporate_action_revision (ex_session_id, instrument_id);
CREATE INDEX corporate_action_supersedes_idx ON mra.corporate_action_revision (supersedes_revision_id)
    WHERE supersedes_revision_id IS NOT NULL;

CREATE TABLE mra.source_gap (
    gap_id uuid PRIMARY KEY,
    provider_product_id uuid NOT NULL REFERENCES mra.provider_product(provider_product_id) ON DELETE RESTRICT,
    capture_id uuid NOT NULL REFERENCES mra.data_capture(capture_id) ON DELETE RESTRICT,
    instrument_id uuid REFERENCES mra.instrument(instrument_id) ON DELETE RESTRICT,
    session_id uuid REFERENCES mra.trading_session(session_id) ON DELETE RESTRICT,
    gap_kind text NOT NULL,
    reason_code text NOT NULL,
    fact_kind text NOT NULL,
    timeframe text,
    adjustment_basis text,
    event_start timestamptz,
    event_end timestamptz,
    detail text,
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT source_gap_identity_uk UNIQUE (
        capture_id, fact_kind, instrument_id, session_id,
        timeframe, adjustment_basis, event_start, event_end, gap_kind
    ),
    CONSTRAINT source_gap_kind_ck CHECK (gap_kind IN ('MISSING', 'PLACEHOLDER', 'PROVIDER_FAILURE', 'CONFLICT', 'INVALID_OHLC')),
    CONSTRAINT source_gap_reason_ck CHECK (reason_code ~ '^[A-Z][A-Z0-9_]{0,99}$'),
    CONSTRAINT source_gap_fact_kind_ck CHECK (fact_kind ~ '^[A-Z][A-Z0-9_]{0,99}$'),
    CONSTRAINT source_gap_bar_scope_ck CHECK (
        (timeframe IS NULL AND adjustment_basis IS NULL) OR
        (timeframe IN ('MINUTE_1', 'MINUTE_5', 'MINUTE_15', 'MINUTE_30', 'MINUTE_60', 'DAILY')
         AND adjustment_basis IN ('RAW_UNADJUSTED', 'FORWARD_ADJUSTED', 'BACKWARD_ADJUSTED'))
    ),
    CONSTRAINT source_gap_interval_ck CHECK (
        (event_start IS NULL AND event_end IS NULL) OR
        (event_start IS NOT NULL AND event_end > event_start)
    )
);
CREATE INDEX source_gap_exact_asof_idx ON mra.source_gap (
    provider_product_id, instrument_id, session_id, fact_kind,
    timeframe, adjustment_basis, event_end, capture_id
);
CREATE INDEX source_gap_capture_idx ON mra.source_gap (capture_id);
CREATE INDEX source_gap_instrument_idx ON mra.source_gap (instrument_id, fact_kind, event_end DESC)
    WHERE instrument_id IS NOT NULL;
CREATE INDEX source_gap_session_idx ON mra.source_gap (session_id, instrument_id, fact_kind)
    WHERE session_id IS NOT NULL;

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
CREATE TRIGGER instrument_append_only
BEFORE UPDATE OR DELETE ON mra.instrument
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER instrument_identifier_append_only
BEFORE UPDATE OR DELETE ON mra.instrument_identifier
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER instrument_identifier_validate_insert
BEFORE INSERT ON mra.instrument_identifier
FOR EACH ROW EXECUTE FUNCTION mra.validate_instrument_identifier_insert();
CREATE TRIGGER instrument_identifier_revision_predecessor
BEFORE INSERT ON mra.instrument_identifier
FOR EACH ROW EXECUTE FUNCTION mra.validate_market_revision_predecessor();
CREATE TRIGGER trading_session_append_only
BEFORE UPDATE OR DELETE ON mra.trading_session
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER classification_append_only
BEFORE UPDATE OR DELETE ON mra.classification
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER classification_revision_predecessor
BEFORE INSERT ON mra.classification
FOR EACH ROW EXECUTE FUNCTION mra.validate_market_revision_predecessor();
CREATE TRIGGER classification_membership_revision_append_only
BEFORE UPDATE OR DELETE ON mra.classification_membership_revision
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER classification_membership_revision_predecessor
BEFORE INSERT ON mra.classification_membership_revision
FOR EACH ROW EXECUTE FUNCTION mra.validate_market_revision_predecessor();
CREATE TRIGGER market_bar_revision_append_only
BEFORE UPDATE OR DELETE ON mra.market_bar_revision
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER market_bar_revision_predecessor
BEFORE INSERT ON mra.market_bar_revision
FOR EACH ROW EXECUTE FUNCTION mra.validate_market_revision_predecessor();
CREATE TRIGGER market_bar_gap_exclusive
BEFORE INSERT ON mra.market_bar_revision
FOR EACH ROW EXECUTE FUNCTION mra.reject_bar_gap_duality();
CREATE TRIGGER instrument_fact_revision_append_only
BEFORE UPDATE OR DELETE ON mra.instrument_fact_revision
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER instrument_fact_revision_predecessor
BEFORE INSERT ON mra.instrument_fact_revision
FOR EACH ROW EXECUTE FUNCTION mra.validate_market_revision_predecessor();
CREATE TRIGGER corporate_action_revision_append_only
BEFORE UPDATE OR DELETE ON mra.corporate_action_revision
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER corporate_action_revision_predecessor
BEFORE INSERT ON mra.corporate_action_revision
FOR EACH ROW EXECUTE FUNCTION mra.validate_market_revision_predecessor();
CREATE TRIGGER source_gap_append_only
BEFORE UPDATE OR DELETE ON mra.source_gap
FOR EACH ROW EXECUTE FUNCTION mra.reject_append_only_mutation();
CREATE TRIGGER source_gap_bar_exclusive
BEFORE INSERT ON mra.source_gap
FOR EACH ROW EXECUTE FUNCTION mra.reject_bar_gap_duality();

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
