-- Phase D converges existing owners; it does not create a second Protocol or
-- Target authority.  V1 rows remain immutable and replayable.

ALTER TABLE formal_research_protocol
DROP CONSTRAINT formal_research_protocol_payload_json_check;

ALTER TABLE formal_research_protocol
ADD CONSTRAINT formal_research_protocol_payload_json_check CHECK (
    jsonb_typeof(payload_json) = 'object'
    AND payload_json->>'schema_version' IN (
        'formal-research-protocol/v1',
        'formal-research-protocol/v2'
    )
    AND (
        payload_json->>'schema_version' = 'formal-research-protocol/v1'
        OR (
            jsonb_typeof(payload_json->'experiment_definition') = 'object'
            AND payload_json->'experiment_definition'->>'schema_version' =
                'research-experiment-definition/v1'
            AND payload_json->'experiment_definition'->>'definition_hash'
                ~ '^sha256:[0-9a-f]{64}$'
        )
    )
);

ALTER TABLE frozen_hypothesis_family
DROP CONSTRAINT frozen_hypothesis_family_multiple_testing_method_check;

ALTER TABLE frozen_hypothesis_family
ADD CONSTRAINT frozen_hypothesis_family_multiple_testing_method_check CHECK (
    multiple_testing_method IN (
        'BONFERRONI', 'HOLM_BONFERRONI', 'BENJAMINI_HOCHBERG'
    )
);
