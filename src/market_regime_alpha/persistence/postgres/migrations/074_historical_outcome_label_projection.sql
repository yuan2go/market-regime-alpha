CREATE TABLE historical_corpus_outcome_label (
    component_id text NOT NULL REFERENCES historical_corpus_session_component(component_id) ON DELETE RESTRICT,
    component_hash text NOT NULL CHECK (component_hash ~ '^sha256:[0-9a-f]{64}$'),
    trading_date date NOT NULL,
    label_id text NOT NULL,
    label_hash text NOT NULL CHECK (label_hash ~ '^sha256:[0-9a-f]{64}$'),
    symbol text NOT NULL,
    target_id text NOT NULL,
    label_interval_end timestamptz NOT NULL,
    outcome_available_at timestamptz NOT NULL,
    availability_status text NOT NULL,
    payload_json jsonb NOT NULL,
    PRIMARY KEY (component_id, label_id),
    CHECK (payload_json->>'label_id' = label_id),
    CHECK (payload_json->>'label_hash' = label_hash),
    CHECK (payload_json->>'symbol' = symbol),
    CHECK (payload_json->'target'->>'artifact_id' = target_id)
);

CREATE INDEX historical_corpus_outcome_label_lookup_idx
ON historical_corpus_outcome_label(symbol, target_id, trading_date, component_id, label_id);

INSERT INTO historical_corpus_outcome_label(
    component_id, component_hash, trading_date, label_id, label_hash,
    symbol, target_id, label_interval_end, outcome_available_at,
    availability_status, payload_json
)
SELECT component.component_id,
       component.component_hash,
       component.trading_date,
       label.value->>'label_id',
       label.value->>'label_hash',
       label.value->>'symbol',
       label.value->'target'->>'artifact_id',
       (label.value->>'label_interval_end')::timestamptz,
       (label.value->>'outcome_available_at')::timestamptz,
       label.value->>'availability_status',
       label.value
FROM historical_corpus_session_component AS component
CROSS JOIN LATERAL jsonb_array_elements(
    component.payload_json->'payload'->'labels'
) AS label(value)
WHERE component.component_kind = 'OUTCOME';

CREATE TRIGGER historical_corpus_outcome_label_no_update
BEFORE UPDATE OR DELETE ON historical_corpus_outcome_label
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
