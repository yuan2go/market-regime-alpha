CREATE TABLE research_evaluation_dataset (
    dataset_id text PRIMARY KEY,
    dataset_hash text NOT NULL UNIQUE CHECK (
        dataset_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    protocol_id text NOT NULL,
    protocol_hash text NOT NULL CHECK (
        protocol_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    observation_count integer NOT NULL CHECK (observation_count >= 0),
    included_count integer NOT NULL CHECK (included_count >= 0),
    excluded_count integer NOT NULL CHECK (excluded_count >= 0),
    missing_count integer NOT NULL CHECK (missing_count >= 0),
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' =
            'frozen-research-evaluation-dataset/v1'
    ),
    artifact_locator text NOT NULL,
    created_at timestamptz NOT NULL,
    CHECK (
        observation_count = included_count + excluded_count + missing_count
    )
);

CREATE TABLE research_evaluation_dataset_settlement (
    dataset_id text NOT NULL
        REFERENCES research_evaluation_dataset(dataset_id) ON DELETE RESTRICT,
    settlement_id text NOT NULL
        REFERENCES prospective_outcome_settlement(settlement_id) ON DELETE RESTRICT,
    settlement_hash text NOT NULL CHECK (
        settlement_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    shadow_decision_id text NOT NULL
        REFERENCES shadow_research_decision(decision_id) ON DELETE RESTRICT,
    PRIMARY KEY (dataset_id, settlement_id)
);

CREATE INDEX research_evaluation_dataset_created_idx
ON research_evaluation_dataset(created_at, dataset_id);

CREATE INDEX research_evaluation_settlement_idx
ON research_evaluation_dataset_settlement(settlement_id);

CREATE INDEX research_evaluation_shadow_decision_idx
ON research_evaluation_dataset_settlement(shadow_decision_id);

CREATE TRIGGER research_evaluation_dataset_no_update
BEFORE UPDATE OR DELETE ON research_evaluation_dataset
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER research_evaluation_dataset_settlement_no_update
BEFORE UPDATE OR DELETE ON research_evaluation_dataset_settlement
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
