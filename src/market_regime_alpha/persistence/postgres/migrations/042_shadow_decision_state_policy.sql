ALTER TABLE shadow_research_decision
    DROP CONSTRAINT shadow_research_decision_payload_json_check;

ALTER TABLE shadow_research_decision
    ADD CONSTRAINT shadow_research_decision_payload_json_check CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' IN (
            'shadow-decision/v1',
            'shadow-decision/v2'
        )
    );

CREATE TABLE shadow_research_decision_state_policy (
    decision_id text NOT NULL
        REFERENCES shadow_research_decision(decision_id) ON DELETE RESTRICT,
    policy_id text NOT NULL
        REFERENCES state_policy_authority(policy_id) ON DELETE RESTRICT,
    policy_hash text NOT NULL CHECK (policy_hash ~ '^sha256:[0-9a-f]{64}$'),
    PRIMARY KEY (decision_id, policy_id)
);

CREATE INDEX shadow_decision_state_policy_policy_idx
ON shadow_research_decision_state_policy(policy_id);

CREATE TRIGGER shadow_decision_state_policy_no_update
BEFORE UPDATE ON shadow_research_decision_state_policy
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER shadow_decision_state_policy_no_delete
BEFORE DELETE ON shadow_research_decision_state_policy
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
