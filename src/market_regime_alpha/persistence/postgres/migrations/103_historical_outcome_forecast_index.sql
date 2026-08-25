-- Keep external Historical Outcome labels in their immutable Artifact owner
-- while projecting one compact, target-specific locator set per component for
-- bounded Forecast sample reloads.

CREATE TABLE historical_corpus_outcome_forecast_index (
    component_id text PRIMARY KEY,
    component_hash text NOT NULL CHECK (
        component_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    trading_date date NOT NULL,
    target_id text NOT NULL,
    payload_json jsonb NOT NULL,
    FOREIGN KEY (component_id, component_hash, trading_date)
        REFERENCES historical_corpus_session_component(
            component_id, component_hash, trading_date
        )
        ON DELETE RESTRICT,
    CHECK (payload_json->>'schema_version' =
        'historical-outcome-forecast-index/v1'),
    CHECK (payload_json->>'component_id' = component_id),
    CHECK (payload_json->>'component_hash' = component_hash),
    CHECK ((payload_json->>'trading_date')::date = trading_date),
    CHECK (payload_json->>'target_id' = target_id),
    CHECK (jsonb_typeof(payload_json->'labels') = 'array'),
    CHECK (jsonb_array_length(payload_json->'labels') > 0)
);

CREATE INDEX historical_corpus_outcome_forecast_lookup_idx
ON historical_corpus_outcome_forecast_index(
    target_id, trading_date DESC, component_id
);

CREATE TRIGGER historical_corpus_outcome_forecast_index_no_update
BEFORE UPDATE OR DELETE ON historical_corpus_outcome_forecast_index
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

COMMENT ON TABLE historical_corpus_outcome_forecast_index IS
'Owner-derived 10:30 Forecast sample locators. Outcome values remain authoritative only in the exact Historical Outcome component.';
