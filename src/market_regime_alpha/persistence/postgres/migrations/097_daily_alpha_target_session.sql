ALTER TABLE research_validation_artifact
ADD CONSTRAINT research_validation_artifact_identity_unique
UNIQUE (artifact_id, artifact_hash);

CREATE TABLE daily_alpha_prediction_target_session (
    snapshot_id text PRIMARY KEY,
    snapshot_hash text NOT NULL CHECK (
        snapshot_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    decision_session date NOT NULL,
    target_session date NOT NULL CHECK (target_session > decision_session),
    trading_calendar_id text NOT NULL,
    trading_calendar_hash text NOT NULL CHECK (
        trading_calendar_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    created_at timestamptz NOT NULL,
    FOREIGN KEY (snapshot_id, snapshot_hash)
        REFERENCES research_validation_artifact(artifact_id, artifact_hash)
        ON DELETE RESTRICT,
    FOREIGN KEY (trading_calendar_id, trading_calendar_hash)
        REFERENCES pit_trading_calendar_canonical_snapshot(
            calendar_id, calendar_hash
        ) ON DELETE RESTRICT
);

CREATE INDEX daily_alpha_prediction_target_due_idx
ON daily_alpha_prediction_target_session(target_session, snapshot_id);

CREATE INDEX daily_alpha_prediction_target_snapshot_fk_idx
ON daily_alpha_prediction_target_session(snapshot_id, snapshot_hash);

CREATE INDEX daily_alpha_prediction_target_calendar_fk_idx
ON daily_alpha_prediction_target_session(
    trading_calendar_id, trading_calendar_hash
);

CREATE TRIGGER daily_alpha_prediction_target_session_no_update
BEFORE UPDATE OR DELETE ON daily_alpha_prediction_target_session
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
