-- Support the exact external Outcome owner foreign key introduced by 103.

CREATE INDEX historical_corpus_outcome_forecast_owner_fk_idx
ON historical_corpus_outcome_forecast_index(
    component_id, component_hash, trading_date
);
