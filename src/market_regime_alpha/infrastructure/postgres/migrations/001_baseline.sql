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
