ALTER TABLE continuous_child_run
DROP CONSTRAINT continuous_child_run_child_kind_check;

ALTER TABLE continuous_child_run
ADD CONSTRAINT continuous_child_run_child_kind_check
CHECK (
    child_kind IN (
        'DAILY_DATASET',
        'FEATURE_MATERIALIZATION',
        'STATE_SYSTEM',
        'CONTROLLED_OPERATION',
        'CANONICAL_LIFECYCLE'
    )
);
