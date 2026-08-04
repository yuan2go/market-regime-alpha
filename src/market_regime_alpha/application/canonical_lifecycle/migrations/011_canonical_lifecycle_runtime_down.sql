PRAGMA foreign_keys = OFF;

BEGIN IMMEDIATE;

DROP TRIGGER IF EXISTS lifecycle_terminal_stages_immutable;
DROP TRIGGER IF EXISTS lifecycle_stages_no_delete;
DROP TRIGGER IF EXISTS lifecycle_runs_identity_immutable;
DROP TRIGGER IF EXISTS lifecycle_runs_no_delete;
DROP TRIGGER IF EXISTS lifecycle_events_no_delete;
DROP TRIGGER IF EXISTS lifecycle_events_no_update;
DROP TRIGGER IF EXISTS lifecycle_stage_receipts_no_delete;
DROP TRIGGER IF EXISTS lifecycle_stage_receipts_no_update;
DROP TRIGGER IF EXISTS lifecycle_attempts_completion_only;
DROP TRIGGER IF EXISTS lifecycle_attempts_terminal_immutable;
DROP TRIGGER IF EXISTS lifecycle_attempts_no_delete;

DROP INDEX IF EXISTS lifecycle_events_history_idx;
DROP INDEX IF EXISTS lifecycle_receipts_history_idx;
DROP INDEX IF EXISTS lifecycle_attempts_history_idx;
DROP INDEX IF EXISTS lifecycle_stages_status_idx;
DROP INDEX IF EXISTS lifecycle_runs_status_decision_date_idx;

DROP TABLE IF EXISTS lifecycle_events;
DROP TABLE IF EXISTS lifecycle_stage_receipts;
DROP TABLE IF EXISTS lifecycle_attempts;
DROP TABLE IF EXISTS lifecycle_stages;
DROP TABLE IF EXISTS lifecycle_runs;

DELETE FROM pdl_schema_migrations WHERE version = 11;

COMMIT;

PRAGMA foreign_keys = ON;
