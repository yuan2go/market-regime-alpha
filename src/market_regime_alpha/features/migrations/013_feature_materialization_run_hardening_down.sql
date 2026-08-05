PRAGMA foreign_keys=OFF;

BEGIN IMMEDIATE;

DROP TRIGGER IF EXISTS feature_materialization_run_identity_immutable;
DROP TRIGGER IF EXISTS feature_materialization_runs_no_delete;
DROP TRIGGER IF EXISTS feature_materialization_claim_owner_guard;
DROP TRIGGER IF EXISTS feature_materialization_completed_tasks_immutable;
DROP TRIGGER IF EXISTS feature_materialization_tasks_no_delete;
DROP TRIGGER IF EXISTS feature_materialization_attempt_transition_guard;
DROP TRIGGER IF EXISTS feature_materialization_settled_attempts_no_update;
DROP TRIGGER IF EXISTS feature_materialization_attempts_no_delete;
DROP TRIGGER IF EXISTS feature_materialization_receipts_no_delete;
DROP TRIGGER IF EXISTS feature_materialization_receipts_no_update;
DROP TRIGGER IF EXISTS feature_materialization_events_no_delete;
DROP TRIGGER IF EXISTS feature_materialization_events_no_update;

DROP INDEX IF EXISTS feature_materialization_event_run_idx;
DROP INDEX IF EXISTS feature_materialization_attempt_task_idx;
DROP INDEX IF EXISTS feature_materialization_task_lease_idx;
DROP INDEX IF EXISTS feature_materialization_task_claimable_idx;

DELETE FROM feature_materialization_schema_migration WHERE version = 13;

COMMIT;

PRAGMA foreign_keys=ON;
