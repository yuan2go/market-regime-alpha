-- Phase E3 owner-bound Outcome label time projection for Forecast sampling.

ALTER TABLE historical_corpus_session_component
ADD CONSTRAINT historical_corpus_session_component_temporal_owner_key
UNIQUE (component_id, component_hash, trading_date);

ALTER TABLE historical_corpus_session_component
ADD CONSTRAINT historical_corpus_session_component_payload_projection_check CHECK (
    payload_json->>'schema_version' = 'historical-session-component/v1'
    AND payload_json->>'component_id' = component_id
    AND payload_json->>'component_hash' = component_hash
    AND payload_json->>'run_id' = run_id
    AND payload_json->>'session_id' = session_id
    AND (payload_json->>'trading_date')::date = trading_date
    AND payload_json->>'component_kind' = component_kind
    AND (payload_json->>'source_max_event_time')::timestamptz = source_max_event_time
    AND (payload_json->>'materialized_at')::timestamptz = materialized_at
);

ALTER TABLE historical_corpus_outcome_label
ADD CONSTRAINT historical_corpus_outcome_label_temporal_owner_fk
FOREIGN KEY (component_id, component_hash, trading_date)
REFERENCES historical_corpus_session_component(
    component_id, component_hash, trading_date
)
ON DELETE RESTRICT;

CREATE INDEX historical_corpus_outcome_label_temporal_owner_fk_idx
ON historical_corpus_outcome_label(
    component_id, component_hash, trading_date
);

COMMENT ON CONSTRAINT historical_corpus_outcome_label_temporal_owner_fk
ON historical_corpus_outcome_label IS
'Forecast cutoff/order date is the immutable owning Outcome component session date.';
