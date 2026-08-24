CREATE TABLE controlled_operation_package_locator (
    package_id text PRIMARY KEY,
    package_hash text NOT NULL UNIQUE CHECK (
        package_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    operation_run_id text NOT NULL
        REFERENCES controlled_operation_run(run_id) ON DELETE RESTRICT,
    package_status text NOT NULL CHECK (
        package_status IN ('OUTCOME_PENDING', 'SETTLED')
    ),
    package_locator text NOT NULL CHECK (
        package_locator LIKE 'artifact-root-v1/%'
        AND package_locator NOT LIKE '%..%'
    ),
    created_at timestamptz NOT NULL
);

CREATE INDEX controlled_operation_package_locator_run_idx
ON controlled_operation_package_locator(operation_run_id, package_status, package_id);

CREATE TRIGGER controlled_operation_package_locator_no_update
BEFORE UPDATE OR DELETE ON controlled_operation_package_locator
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

ALTER TABLE prospective_outcome_settlement
DROP CONSTRAINT prospective_outcome_settlement_payload_json_check;

ALTER TABLE prospective_outcome_settlement
ADD COLUMN prediction_snapshot_id text,
ADD COLUMN prediction_snapshot_hash text CHECK (
    prediction_snapshot_hash IS NULL
    OR prediction_snapshot_hash ~ '^sha256:[0-9a-f]{64}$'
),
ADD COLUMN strategy_diagnostic_id text,
ADD COLUMN strategy_diagnostic_hash text CHECK (
    strategy_diagnostic_hash IS NULL
    OR strategy_diagnostic_hash ~ '^sha256:[0-9a-f]{64}$'
),
ADD CONSTRAINT prospective_outcome_prediction_snapshot_fkey
    FOREIGN KEY (prediction_snapshot_id)
    REFERENCES research_validation_artifact(artifact_id) ON DELETE RESTRICT,
ADD CONSTRAINT prospective_outcome_strategy_diagnostic_fkey
    FOREIGN KEY (strategy_diagnostic_id)
    REFERENCES multi_strategy_cycle(cycle_id) ON DELETE RESTRICT,
ADD CONSTRAINT prospective_outcome_daily_prediction_pair_check CHECK (
    (prediction_snapshot_id IS NULL) = (prediction_snapshot_hash IS NULL)
    AND (strategy_diagnostic_id IS NULL) = (strategy_diagnostic_hash IS NULL)
),
ADD CONSTRAINT prospective_outcome_payload_schema_check CHECK (
    jsonb_typeof(payload_json) = 'object'
    AND (
        (
            payload_json->>'schema_version' = 'prospective-shadow-outcome/v1'
            AND prediction_snapshot_id IS NULL
            AND strategy_diagnostic_id IS NULL
        )
        OR (
            payload_json->>'schema_version' = 'prospective-shadow-outcome/v2'
            AND prediction_snapshot_id IS NOT NULL
            AND strategy_diagnostic_id IS NOT NULL
            AND payload_json->'prediction_snapshot'->>'artifact_id'
                = prediction_snapshot_id
            AND payload_json->'prediction_snapshot'->>'content_hash'
                = prediction_snapshot_hash
            AND payload_json->'strategy_diagnostic'->>'artifact_id'
                = strategy_diagnostic_id
            AND payload_json->'strategy_diagnostic'->>'content_hash'
                = strategy_diagnostic_hash
        )
    )
);

CREATE INDEX prospective_outcome_prediction_snapshot_idx
ON prospective_outcome_settlement(prediction_snapshot_id)
WHERE prediction_snapshot_id IS NOT NULL;

CREATE INDEX prospective_outcome_strategy_diagnostic_idx
ON prospective_outcome_settlement(strategy_diagnostic_id)
WHERE strategy_diagnostic_id IS NOT NULL;
