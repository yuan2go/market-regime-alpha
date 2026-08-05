ALTER TABLE feature_materialization_run
    ADD CONSTRAINT feature_materialization_run_hash_check CHECK (
        command_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    ADD CONSTRAINT feature_materialization_run_status_check CHECK (
        status IN ('RUNNING', 'FAILED', 'COMPLETE')
    ),
    ADD CONSTRAINT feature_materialization_run_version_check CHECK (version >= 1);

ALTER TABLE feature_materialization_task
    ADD COLUMN claim_epoch bigint NOT NULL DEFAULT 0 CHECK (claim_epoch >= 0),
    ADD COLUMN lease_acquired_at timestamptz,
    ADD COLUMN lease_expires_at timestamptz,
    ADD COLUMN heartbeat_at timestamptz;

UPDATE feature_materialization_task
SET status = 'FAILED',
    version = version + 1,
    claim_token = NULL,
    claimed_at = NULL,
    last_error = 'MIGRATION_013_RECOVERED_LEGACY_CLAIM'
WHERE status = 'IN_PROGRESS';

ALTER TABLE feature_materialization_task
    ADD CONSTRAINT feature_materialization_task_status_check CHECK (
        status IN ('PENDING', 'IN_PROGRESS', 'FAILED', 'COMPLETE')
    ),
    ADD CONSTRAINT feature_materialization_task_version_check CHECK (version >= 1),
    ADD CONSTRAINT feature_materialization_task_hash_check CHECK (
        artifact_hash IS NULL
        OR artifact_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    ADD CONSTRAINT feature_materialization_task_claim_check CHECK (
        (
            status = 'IN_PROGRESS'
            AND claim_token IS NOT NULL
            AND claimed_at IS NOT NULL
            AND lease_acquired_at IS NOT NULL
            AND lease_expires_at IS NOT NULL
            AND heartbeat_at IS NOT NULL
            AND claim_epoch >= 1
        ) OR (
            status != 'IN_PROGRESS'
            AND claim_token IS NULL
            AND claimed_at IS NULL
            AND lease_acquired_at IS NULL
            AND lease_expires_at IS NULL
            AND heartbeat_at IS NULL
        )
    ),
    ADD CONSTRAINT feature_materialization_task_artifact_check CHECK (
        (
            status = 'COMPLETE'
            AND artifact_id IS NOT NULL
            AND artifact_hash IS NOT NULL
        ) OR (
            status != 'COMPLETE'
            AND artifact_id IS NULL
            AND artifact_hash IS NULL
        )
    );

ALTER TABLE feature_materialization_attempt
    ADD COLUMN claim_epoch bigint,
    ADD COLUMN task_version bigint,
    ADD COLUMN lease_expires_at timestamptz,
    ADD COLUMN heartbeat_at timestamptz;

UPDATE feature_materialization_attempt
SET claim_epoch = attempt_number,
    task_version = 2,
    lease_expires_at = started_at,
    heartbeat_at = started_at,
    completed_at = COALESCE(completed_at, started_at),
    status = CASE WHEN status = 'STARTED' THEN 'LEASE_EXPIRED' ELSE status END,
    error_message = CASE
        WHEN status = 'STARTED' THEN 'MIGRATION_013_RECOVERED_LEGACY_CLAIM'
        ELSE error_message
    END;

ALTER TABLE feature_materialization_attempt
    ALTER COLUMN claim_epoch SET NOT NULL,
    ALTER COLUMN task_version SET NOT NULL,
    ALTER COLUMN lease_expires_at SET NOT NULL,
    ALTER COLUMN heartbeat_at SET NOT NULL,
    ADD CONSTRAINT feature_materialization_attempt_number_check CHECK (
        attempt_number >= 1
    ),
    ADD CONSTRAINT feature_materialization_attempt_epoch_check CHECK (
        claim_epoch >= 1
    ),
    ADD CONSTRAINT feature_materialization_attempt_version_check CHECK (
        task_version >= 2
    ),
    ADD CONSTRAINT feature_materialization_attempt_status_check CHECK (
        status IN ('STARTED', 'COMPLETE', 'FAILED', 'LEASE_EXPIRED')
    ),
    ADD CONSTRAINT feature_materialization_attempt_completion_check CHECK (
        (status = 'STARTED' AND completed_at IS NULL)
        OR (status != 'STARTED' AND completed_at IS NOT NULL)
    ),
    ADD CONSTRAINT feature_materialization_attempt_epoch_unique
        UNIQUE (run_id, task_key, claim_epoch);

ALTER TABLE feature_materialization_receipt
    ADD CONSTRAINT feature_materialization_receipt_hash_check CHECK (
        receipt_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    ADD CONSTRAINT feature_materialization_receipt_json_check CHECK (
        receipt_json IS JSON OBJECT
    );

ALTER TABLE feature_materialization_event
    ADD CONSTRAINT feature_materialization_event_json_check CHECK (
        payload_json IS JSON OBJECT
    ),
    ADD CONSTRAINT feature_materialization_event_task_fkey
        FOREIGN KEY (run_id, task_key)
        REFERENCES feature_materialization_task(run_id, task_key);

CREATE INDEX feature_materialization_task_claimable_idx
ON feature_materialization_task(run_id, status, task_key);
CREATE INDEX feature_materialization_task_lease_idx
ON feature_materialization_task(run_id, status, lease_expires_at);
CREATE INDEX feature_materialization_attempt_task_idx
ON feature_materialization_attempt(run_id, task_key, attempt_number);
CREATE INDEX feature_materialization_event_run_idx
ON feature_materialization_event(run_id, event_id);
CREATE INDEX feature_materialization_event_task_idx
ON feature_materialization_event(run_id, task_key);

CREATE TRIGGER feature_materialization_events_no_update
BEFORE UPDATE ON feature_materialization_event
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER feature_materialization_events_no_delete
BEFORE DELETE ON feature_materialization_event
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER feature_materialization_receipts_no_update
BEFORE UPDATE ON feature_materialization_receipt
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER feature_materialization_receipts_no_delete
BEFORE DELETE ON feature_materialization_receipt
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE FUNCTION guard_feature_attempt_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Feature materialization attempts are immutable history';
    END IF;
    IF OLD.status != 'STARTED' THEN
        RAISE EXCEPTION 'Settled Feature materialization attempt is immutable';
    END IF;
    IF NEW.status = 'STARTED' AND (
        NEW.run_id IS DISTINCT FROM OLD.run_id
        OR NEW.task_key IS DISTINCT FROM OLD.task_key
        OR NEW.attempt_number IS DISTINCT FROM OLD.attempt_number
        OR NEW.claim_token IS DISTINCT FROM OLD.claim_token
        OR NEW.claim_epoch IS DISTINCT FROM OLD.claim_epoch
    ) THEN
        RAISE EXCEPTION 'Feature materialization attempt identity is immutable';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER feature_materialization_attempts_no_delete
BEFORE DELETE ON feature_materialization_attempt
FOR EACH ROW EXECUTE FUNCTION guard_feature_attempt_mutation();
CREATE TRIGGER feature_materialization_attempt_transition_guard
BEFORE UPDATE ON feature_materialization_attempt
FOR EACH ROW EXECUTE FUNCTION guard_feature_attempt_mutation();

CREATE FUNCTION guard_feature_task_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Feature materialization tasks cannot be deleted';
    END IF;
    IF OLD.status = 'COMPLETE' THEN
        RAISE EXCEPTION 'Completed Feature materialization task is immutable';
    END IF;
    IF OLD.status = 'IN_PROGRESS' AND NEW.status = 'IN_PROGRESS' AND (
        NEW.claim_token IS DISTINCT FROM OLD.claim_token
        OR NEW.claim_epoch IS DISTINCT FROM OLD.claim_epoch
    ) THEN
        RAISE EXCEPTION 'Active Feature materialization claim owner cannot be overwritten';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER feature_materialization_tasks_no_delete
BEFORE DELETE ON feature_materialization_task
FOR EACH ROW EXECUTE FUNCTION guard_feature_task_mutation();
CREATE TRIGGER feature_materialization_completed_tasks_immutable
BEFORE UPDATE ON feature_materialization_task
FOR EACH ROW EXECUTE FUNCTION guard_feature_task_mutation();

CREATE FUNCTION guard_feature_run_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Feature materialization runs cannot be deleted';
    END IF;
    IF NEW.schema_version IS DISTINCT FROM OLD.schema_version
       OR NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key
       OR NEW.command_hash IS DISTINCT FROM OLD.command_hash
       OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
        RAISE EXCEPTION 'Feature materialization run command identity is immutable';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER feature_materialization_runs_no_delete
BEFORE DELETE ON feature_materialization_run
FOR EACH ROW EXECUTE FUNCTION guard_feature_run_mutation();
CREATE TRIGGER feature_materialization_run_identity_immutable
BEFORE UPDATE ON feature_materialization_run
FOR EACH ROW EXECUTE FUNCTION guard_feature_run_mutation();
